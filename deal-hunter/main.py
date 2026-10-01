"""
Deal Hunter — hlavný vstupný bod.

Postup jedného behu:
1. Spustí zapnuté scrapery (config.ENABLED_SCRAPERS).
2. Odfiltruje nezmysly (malá zľava, príliš nízka cena, podozrivo veľká zľava).
3. Zahodí duplicity — voči sebe navzájom aj voči tomu, čo už je v databáze
   (vrátane už zamietnutých návrhov).
4. Vyberie najlepšie kúsky, ale tak, aby nešli všetky z jedného obchodu.
5. Zapíše ich do Firestore ako status "pending" — čakajú na tvoje schválenie
   v admin paneli na https://henkukaj.sk/admin.html
6. Zároveň označí za exspirované dealy, ktorým uplynul dátum platnosti.

Spúšťa sa cez GitHub Actions (.github/workflows/deal-hunter.yml).
Lokálny test bez zápisu:  DRY_RUN=true python main.py
"""

import logging
import sys
from collections import defaultdict

import config
import merchant_links
import price_history
import price_watch
from models import DealCandidate, guess_category
from scrapers import AVAILABLE_SCRAPERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("deal_hunter")


def run_scrapers() -> list[DealCandidate]:
    candidates: list[DealCandidate] = []

    for name in config.ENABLED_SCRAPERS:
        scraper_cls = AVAILABLE_SCRAPERS.get(name)
        if not scraper_cls:
            logger.error(
                "Neznámy scraper '%s' (dostupné: %s)",
                name,
                ", ".join(AVAILABLE_SCRAPERS),
            )
            continue

        scraper = scraper_cls()
        logger.info("Spúšťam zdroj: %s", scraper.source_name)
        try:
            found = scraper.fetch_candidates()
            logger.info("%s: %d kandidátov", scraper.source_name, len(found))
            candidates.extend(found)
        except Exception as e:
            # Jeden padnutý zdroj nesmie zhodiť celý beh.
            logger.error("Zdroj %s zlyhal: %s", scraper.source_name, e, exc_info=True)

    return candidates


def is_sane(candidate: DealCandidate) -> bool:
    """Základná kontrola zmysluplnosti — chráni pred šumom aj chybami v dátach."""
    discount = candidate.discount_percent

    if discount < config.MIN_DISCOUNT_PERCENT:
        return False
    # Zľava 99 % býva preklep v zdroji, nie deal storočia.
    if discount > config.MAX_DISCOUNT_PERCENT:
        logger.debug("Podozrivá zľava %.0f %% pri '%s' — vynechávam", discount, candidate.title)
        return False
    if candidate.deal_price < config.MIN_DEAL_PRICE:
        return False
    if not candidate.title.strip() or not candidate.url:
        return False
    # Vzorky nie sú deal. Stoja pár eur, v obchode sa dajú kúpiť len k
    # inej objednávke a GymBeam ich má vo feede, hoci ich stránky na
    # webe neexistujú - takto sa na stránku dostal deal vedúci na 404.
    nazov = candidate.title.lower()
    if any(slovo in nazov for slovo in config.EXCLUDED_TITLE_WORDS):
        return False
    # Akcia, ktorej platnosť už uplynula, nemá čo robiť na stránke.
    if candidate.is_already_expired:
        return False

    # Bez známeho predajcu by odkaz skončil na zdroji, teda na cudzej
    # stránke. Radšej deal vynechať a obchod doplniť do tabuľky.
    if (config.REQUIRE_KNOWN_MERCHANT and not candidate.direct_url
            and not merchant_links.is_known(candidate.store)):
        logger.warning(
            "Vynechávam '%s' — predajcu '%s' nepoznám, odkaz by viedol na zdroj. "
            "Doplň ho do merchant_links.py alebo v admin paneli.",
            candidate.title[:40], candidate.store,
        )
        return False

    return True


def deduplicate(
    candidates: list[DealCandidate], seen_keys: set[str], seen_urls: set[str]
) -> list[DealCandidate]:
    """Zahodí duplicity voči databáze aj v rámci tohto behu."""
    unique: list[DealCandidate] = []
    keys_in_run: set[str] = set()

    for candidate in candidates:
        key = candidate.dedupe_key
        url = candidate.url.rstrip("/")

        if key in seen_keys or url in seen_urls or key in keys_in_run:
            continue

        keys_in_run.add(key)
        unique.append(candidate)

    return unique


def select_best(candidates: list[DealCandidate], limit: int) -> list[DealCandidate]:
    """
    Zoradí podľa zľavy a vyberie top N so stropom na obchod aj kategóriu.

    Bez stropu na kategóriu by výber tvorili takmer len potraviny — letáky
    reťazcov sú prevažne potravinové, takže najväčšie zľavy sú tam. Strop
    prepustí aj nábytok, náradie či oblečenie, aj keď majú menšiu zľavu.
    """
    ranked = sorted(candidates, key=lambda c: c.discount_percent, reverse=True)

    selected: list[DealCandidate] = []
    per_store: dict[str, int] = defaultdict(int)
    per_category: dict[str, int] = defaultdict(int)

    # Koľko kusov smie mať obmedzená kategória v tomto behu. Aspoň
    # jeden - pri malom limite by zaokrúhlenie nadol znamenalo nulu a
    # strop by sa zmenil na zákaz.
    strop_podielu = max(1, int(limit * config.CAPPED_CATEGORY_SHARE))

    preskocene_kategorie = 0
    videne_skupiny: set[tuple[str, str]] = set()
    for candidate in ranked:
        # Z variantov (veľkosti, farby) necháme len ten s najväčšou
        # zľavou - poradie je už zoradené, takže prvý je najlepší.
        if candidate.group_id:
            skupina = ((candidate.store or candidate.source).lower(), candidate.group_id)
            if skupina in videne_skupiny:
                continue
            videne_skupiny.add(skupina)

        store = candidate.store or candidate.source
        category = guess_category(candidate.title, candidate.category_hint)

        # Kategórie zakázané úplne.
        if category in config.BLOCKED_CATEGORIES:
            preskocene_kategorie += 1
            continue

        # Kategórie so stropom podielu. Potraviny zdroj nájde najviac a
        # bez stropu by zaplnili celý výber; takto sa do neho zmestia,
        # ale nechajú miesto elektronike a ostatnému.
        if category in config.CAPPED_CATEGORIES and per_category[category] >= strop_podielu:
            preskocene_kategorie += 1
            continue

        if per_store[store] >= config.MAX_PER_STORE:
            continue
        if per_category[category] >= config.MAX_PER_CATEGORY:
            continue

        per_store[store] += 1
        per_category[category] += 1
        selected.append(candidate)
        if len(selected) >= limit:
            break

    if preskocene_kategorie:
        logger.info(
            "Preskočených pre kategóriu (zakázané: %s; strop %d ks pre %s): %d",
            ", ".join(config.BLOCKED_CATEGORIES) or "žiadne",
            strop_podielu, ", ".join(config.CAPPED_CATEGORIES),
            preskocene_kategorie,
        )
    return selected


def drop_dead_links(candidates: list[DealCandidate]) -> list[DealCandidate]:
    """
    Vyradí dealy, ktorých stránka u predajcu neexistuje.

    Feedy nie sú vždy aktuálne - obchod produkt z webu stiahne, ale vo
    feede ho nechá. Takto sa na stránku dostal GymBeam "Vzorka FueRide"
    vedúci na 404.

    Overujeme PÔVODNÚ adresu obchodu (candidate.url), nikdy nie odkaz
    zabalený do Dognetu. Kontrola cez preklikávač by sa rátala ako
    preklik - kazila by štatistiky a v sieti by vyzerala ako podvodná
    premávka.

    Beží až na vybraných dealoch, teda najviac MAX_DEALS_PER_RUN
    požiadaviek za beh.
    """
    import http_client

    zive: list[DealCandidate] = []
    for c in candidates:
        # Len tvrdé 404/410. Presmerovanie za mŕtvy odkaz nepovažujeme:
        # e-shopy bežne presmerujú variant produktu na jeho hlavnú
        # stránku (GymBeam "Vitamín C 180 tbl" -> "Vitamín C") a
        # heuristika na mäkké 404 by vyradila živý deal.
        if http_client.is_reachable(c.url, detect_soft_404=False):
            zive.append(c)
        else:
            logger.warning("Vyraďujem '%s' — stránka u predajcu neexistuje (%s)",
                           c.title[:50], c.url[:80])
    if len(zive) < len(candidates):
        logger.info("Po kontrole odkazov: %d z %d", len(zive), len(candidates))
    return zive


def notify_telegram(written: list[tuple[str, dict]]) -> None:
    """Pošle každý návrh do Telegramu s tlačidlami Schváliť / Zamietnuť."""
    import telegram_bot

    if not (written and telegram_bot.is_configured()):
        return

    try:
        telegram_bot.send_summary(len(written))
        for deal_id, deal in written:
            telegram_bot.send_deal_for_approval(deal_id, deal)
    except Exception as e:
        # Neúspešná notifikácia nie je dôvod označiť celý beh za zlyhaný —
        # dealy sú zapísané a schváliť sa dajú aj v admin paneli.
        logger.warning("Telegram notifikácia zlyhala: %s", e)


def log_preview(deals: list[DealCandidate]) -> None:
    logger.info("--- Vybrané návrhy ---")
    for deal in deals:
        logger.info(
            "  %5.0f %% | %7.2f € (pôv. %7.2f €) | %-14s | %s",
            deal.discount_percent,
            deal.deal_price,
            deal.effective_original_price,
            (deal.store or deal.source)[:14],
            deal.title[:60],
        )


def resolve_feed_prices(
    candidates: list[DealCandidate], db
) -> list[DealCandidate]:
    """
    Rozhodne o položkách z feedov, ktoré neuvádzajú pôvodnú cenu.

    Zverejní sa len tá, ktorej cena spadla pod doteraz najnižšiu videnú.
    Ako "pôvodnú cenu" ukážeme to minimum — je to tvrdenie doložené
    vlastným meraním, na rozdiel od "bežnej ceny", ktorú si predajca
    určuje sám.

    Prvé dni feed nevydá nič, kým sa nenazbierajú dáta. To je zámer, nie
    porucha.
    """
    watched = [c for c in candidates if c.direct_url and c.original_price is None]
    if not watched:
        return candidates

    known = price_watch.load(db, [c.product_key for c in watched])

    passed: list[DealCandidate] = []
    updates: dict[str, dict] = {}
    novych = 0

    for candidate in watched:
        publish, reference, record = price_watch.evaluate(
            candidate.product_key, candidate.deal_price, known,
            config.FEED_MIN_DROP_PERCENT,
        )
        updates[candidate.product_key] = record
        if candidate.product_key not in known:
            novych += 1
        if publish and reference:
            candidate.original_price = reference
            passed.append(candidate)

    price_watch.save(db, updates)
    logger.info(
        "Feedy: sledovaných %d položiek (%d nových), prepad ceny má %d",
        len(watched), novych, len(passed),
    )

    # Ostatné kandidátov necháme tak - tie majú pôvodnú cenu od zdroja.
    rest = [c for c in candidates if not (c.direct_url and c.original_price is None)]
    return rest + passed


def enrich_with_price_history(
    selected: list[DealCandidate], history: dict[str, list]
) -> list[dict]:
    """
    Doplní dealom históriu cien a vyhodí tie, pri ktorých je „pôvodná
    cena" zjavne nafúknutá.

    Falošnú zľavu zahadzujeme, nielen označujeme: deal stránka, ktorá
    zverejní vymyslenú zľavu ako trhák, klame vlastných čitateľov.
    Bez histórie sa nič nezahadzuje - obviňovať bez dôkazu je horšie
    než mlčať.
    """
    documents: list[dict] = []

    for deal in selected:
        past = history.get(deal.product_key)

        fake, reason = price_history.looks_like_fake_discount(
            past, deal.effective_original_price, deal.deal_price
        )
        if fake:
            logger.warning("Vynechávam '%s': %s", deal.title[:45], reason)
            continue

        document = deal.to_firestore_dict()
        document["priceHistory"] = price_history.append_price_point(past, deal.deal_price)
        document["isRealLow"] = price_history.is_real_low(past, deal.deal_price)
        documents.append(document)

    return documents


def run_feed_diagnostics() -> int:
    """
    Vypíše štruktúru nastavených feedov a skončí. Slúži na doladenie
    parsera na konkrétnu sieť bez toho, aby sa čokoľvek zapisovalo.

    Adresa feedu obsahuje partnerské ID, takže sa do logu nikdy nedostane
    - hlásime len doménu a názvy parametrov, nikdy ich hodnoty.
    """
    import json
    import http_client
    from scrapers.feeds import describe_feed

    if not config.FEED_URLS:
        logger.error("FEED_URLS nie je nastavené - niet čo diagnostikovať.")
        return 1

    for index, url in enumerate(config.FEED_URLS, 1):
        # Doménu feedu vypísať môžeme - inzerenta aj tak poznáš, je to
        # tvoja kampaň. Tajná je cesta a parametre, kde je partnerské ID,
        # a tie sa do logu nedostanú.
        from urllib.parse import urlparse as _up
        logger.info("=== Feed %d z %d — %s ===", index, len(config.FEED_URLS),
                    _up(url).netloc or "?")
        xml_text = http_client.get(url, check_robots=False)
        if not xml_text:
            logger.error("Feed sa nepodarilo stiahnuť.")
            continue

        # Vypisujeme po riadkoch, nie ako jeden blok JSON. GitHub Actions
        # zamaskuje celý riadok, v ktorom nájde hodnotu secretu, a pri
        # jednom veľkom bloku tak zmizne aj to, čo je neškodné.
        import re as _re
        import xml.etree.ElementTree as _ET
        from collections import Counter as _Counter
        from urllib.parse import urlparse as _urlparse

        heureka = xml_text.count("<SHOPITEM")
        google = xml_text.count("<item>")
        logger.info("  formát: %s", "Heureka XML" if heureka else ("Google Merchant" if google else "neznámy"))
        logger.info("  položiek: %d", heureka or google)

        try:
            koren = _ET.fromstring(xml_text)
        except _ET.ParseError as e:
            logger.error("  nie je platné XML: %s", e)
            continue

        polozky = koren.findall(".//SHOPITEM") or koren.findall(".//item")
        if not polozky:
            # Feed môže byť platné XML v inom tvare, než čakáme. Nech
            # nekončíme pri "0 položiek" - vypíšeme, ako naozaj vyzerá,
            # aby sa dalo rozhodnúť, či ho vieme dorobiť.
            deti = _Counter(d.tag.split("}")[-1] for d in koren)
            logger.warning("  žiadne SHOPITEM ani item — koreň je <%s>, priame deti: %s",
                           koren.tag.split("}")[-1],
                           ", ".join(f"{t} ({n})" for t, n in deti.most_common(6)) or "žiadne")
            prve = list(koren)[:1]
            if prve:
                vnutro = _Counter(d.tag.split("}")[-1] for d in prve[0])
                logger.warning("  polia v prvom prvku: %s",
                               ", ".join(sorted(vnutro)) or "žiadne")
            continue

        polia = _Counter()
        for p in polozky[:200]:
            for dieta in p:
                polia[dieta.tag.split("}")[-1]] += 1
        logger.info("  polia: %s", ", ".join(sorted(polia)))

        # Najdôležitejšia otázka: vedie odkaz cez sieť (a teda zarába),
        # alebo rovno do e-shopu? Vypisujeme len doménu, nikdy celú
        # adresu - tá obsahuje partnerské ID.
        domeny = _Counter()
        for p in polozky[:50]:
            for tag in ("URL", "link", "{http://base.google.com/ns/1.0}link"):
                uzol = p.find(tag)
                if uzol is not None and uzol.text:
                    domeny[(_urlparse(uzol.text.strip()).netloc or "?")] += 1
                    break
        for d, n in domeny.most_common(3):
            trackovane = any(k in d.lower() for k in ("dognet", "go.", "track", "click"))
            logger.info("  odkazy vedú na: %-34s %s", d,
                        "<- cez sieť, zarábajú" if trackovane else "<- priamo do e-shopu")

        # Máme z čoho spočítať zľavu?
        cenove = [t for t in polia if _re.search(r"price|cena|PRICE", t, _re.I)]
        logger.info("  cenové polia: %s", ", ".join(sorted(cenove)) or "žiadne")

    return 0


def main() -> int:
    logger.info("=== Deal Hunter — začiatok behu ===")

    # Nastavenia z admin zóny (settings/agent) musia platiť ešte pred
    # výberom zdrojov. Bez databázy (DRY_RUN bez kľúča) ostanú predvolené.
    try:
        import firestore_client as _fc0
        from google.cloud import firestore as _fs
        _db0 = _fc0.get_client()
        config.pouzi_nastavenia(_db0.document("settings/agent").get().to_dict() or {})
        # Pre admin: ktoré zdroje a feedy existujú (feed len doménou).
        _db0.document("admin_info/agent").set({**config.info_pre_admin(),
                                                "aktualizovane": _fs.SERVER_TIMESTAMP})
    except Exception as e:
        logger.warning("Nastavenia z admina sa nepodarilo načítať, platia predvolené: %s", e)
    logger.info("Zapnuté zdroje: %s", ", ".join(config.ENABLED_SCRAPERS))

    if config.FEED_DIAGNOSTICS:
        return run_feed_diagnostics()

    raw = run_scrapers()
    logger.info("Spolu nájdených: %d", len(raw))

    # Položky z feedov bez pôvodnej ceny musia najprv prejsť sledovaním,
    # inak by ich is_sane zahodil pre nulovú zľavu.
    if not config.DRY_RUN:
        import firestore_client as _fc
        raw = resolve_feed_prices(raw, _fc.get_client())

    sane = [c for c in raw if is_sane(c)]
    logger.info("Po filtrovaní (zľava >= %.0f %%): %d", config.MIN_DISCOUNT_PERCENT, len(sane))

    if config.DRY_RUN:
        logger.info("DRY_RUN — do Firestore sa nezapisuje.")
        unique = deduplicate(sane, set(), set())
        selected = select_best(unique, config.MAX_DEALS_PER_RUN)
        selected = drop_dead_links(selected)
        log_preview(selected)
        logger.info("=== Koniec (dry run). Zapísalo by sa %d návrhov. ===", len(selected))
        return 0

    # Import až tu, aby sa dal DRY_RUN spustiť bez Firebase knižníc a kľúčov.
    import firestore_client

    db = firestore_client.get_client()

    # Predajcovia spravovaní z admin panelu majú prednosť pred tabuľkou
    # v kóde. Načítame ich skôr, než začneme skladať odkazy.
    import merchant_links
    merchant_links.load_overrides(db)

    if config.FIX_URLS:
        firestore_client.fix_merchant_urls(db)

    if config.RESET_PENDING:
        firestore_client.reset_agent_pending(db)

    # Najprv upraceme: čo už neplatí, dostane štítok EXSPIROVANÉ.
    firestore_client.expire_past_deals(db)

    # Ceny základných potravín z národného porovnávača (raz denne).
    firestore_client.refresh_food_prices(db)

    # Akcie stiahnuté skôr, než mali skončiť - dátum ich nezachytí.
    firestore_client.expire_dead_deals(db)

    # Zľavové kódy dlho po platnosti. Beží len vtedy, keď je mazanie
    # zapnuté v admin paneli - je nevratné, tak sa nezapína samo.
    firestore_client.purge_expired_coupons(db)

    # Jednorazové pomôcky na rozbeh - pri plánovaných behoch vypnuté.
    firestore_client.boost_existing_deals(db)
    firestore_client.boost_coupons(db)

    seen_keys, seen_urls = firestore_client.get_existing_keys(db)
    logger.info("Známych dealov na deduplikáciu: %d", len(seen_keys) + len(seen_urls))

    unique = deduplicate(sane, seen_keys, seen_urls)
    logger.info("Po deduplikácii: %d", len(unique))

    selected = select_best(unique, config.MAX_DEALS_PER_RUN)
    selected = drop_dead_links(selected)

    # Karta bez obrázka vyzerá ako chyba načítania. Skúsime ho dotiahnuť
    # z produktovej stránky skôr, než sa deal dostane do fronty.
    import image_fallback
    image_fallback.fill_missing_images(selected)

    log_preview(selected)

    if not selected:
        logger.info("=== Koniec. Nič nové na pridanie. ===")
        return 0

    history = firestore_client.load_price_history(
        db, [d.product_key for d in selected]
    )
    logger.info("Produktov so známou históriou cien: %d", len(history))

    documents = enrich_with_price_history(selected, history)
    if len(documents) < len(selected):
        logger.info("Vynechaných pre podozrivú zľavu: %d", len(selected) - len(documents))

    written = firestore_client.write_pending_deals(db, documents)
    notify_telegram(written)

    logger.info("=== Koniec. Zapísaných %d návrhov, čakajú na schválenie. ===", len(written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
