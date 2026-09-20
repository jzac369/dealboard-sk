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
    # Akcia, ktorej platnosť už uplynula, nemá čo robiť na stránke.
    if candidate.is_already_expired:
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

    for candidate in ranked:
        store = candidate.store or candidate.source
        category = guess_category(candidate.title, candidate.category_hint)

        if per_store[store] >= config.MAX_PER_STORE:
            continue
        if per_category[category] >= config.MAX_PER_CATEGORY:
            continue

        per_store[store] += 1
        per_category[category] += 1
        selected.append(candidate)
        if len(selected) >= limit:
            break

    return selected


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


def main() -> int:
    logger.info("=== Deal Hunter — začiatok behu ===")
    logger.info("Zapnuté zdroje: %s", ", ".join(config.ENABLED_SCRAPERS))

    raw = run_scrapers()
    logger.info("Spolu nájdených: %d", len(raw))

    sane = [c for c in raw if is_sane(c)]
    logger.info("Po filtrovaní (zľava >= %.0f %%): %d", config.MIN_DISCOUNT_PERCENT, len(sane))

    if config.DRY_RUN:
        logger.info("DRY_RUN — do Firestore sa nezapisuje.")
        unique = deduplicate(sane, set(), set())
        selected = select_best(unique, config.MAX_DEALS_PER_RUN)
        log_preview(selected)
        logger.info("=== Koniec (dry run). Zapísalo by sa %d návrhov. ===", len(selected))
        return 0

    # Import až tu, aby sa dal DRY_RUN spustiť bez Firebase knižníc a kľúčov.
    import firestore_client

    db = firestore_client.get_client()

    if config.FIX_URLS:
        firestore_client.fix_merchant_urls(db)

    if config.RESET_PENDING:
        firestore_client.reset_agent_pending(db)

    # Najprv upraceme: čo už neplatí, dostane štítok EXSPIROVANÉ.
    firestore_client.expire_past_deals(db)

    # Jednorazová pomôcka na rozbeh - pri plánovaných behoch vypnutá.
    firestore_client.boost_existing_deals(db)

    seen_keys, seen_urls = firestore_client.get_existing_keys(db)
    logger.info("Známych dealov na deduplikáciu: %d", len(seen_keys) + len(seen_urls))

    unique = deduplicate(sane, seen_keys, seen_urls)
    logger.info("Po deduplikácii: %d", len(unique))

    selected = select_best(unique, config.MAX_DEALS_PER_RUN)
    log_preview(selected)

    if not selected:
        logger.info("=== Koniec. Nič nové na pridanie. ===")
        return 0

    written = firestore_client.write_pending_deals(
        db, [d.to_firestore_dict() for d in selected]
    )
    notify_telegram(written)

    logger.info("=== Koniec. Zapísaných %d návrhov, čakajú na schválenie. ===", len(written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
