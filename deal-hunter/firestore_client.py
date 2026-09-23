"""
Zápis a čítanie z Firestore (projekt dealboard-e60bf).

Používa service account, ktorý obchádza bežné security rules — preto
kvôli agentovi netreba nič meniť vo firestore.rules.

POZNÁMKA K NÁKLADOM
Firestore sa účtuje za prečítané dokumenty, nie za veľkosť dotazu. Preto
si agent NEPREČÍTAVA všetky čakajúce a zamietnuté návrhy — po roku by
ich boli tisíce a každý beh by ich čítal znova. Namiesto toho si vedie
jediný dokument (agent_state/seen_keys) so zoznamom všetkého, čo kedy
navrhol. To je 1 prečítanie za beh namiesto tisícov.
"""

import logging
import random
from datetime import date, datetime, timedelta, timezone

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.oauth2 import service_account

import config

logger = logging.getLogger(__name__)

# Kde si agent pamätá, čo už navrhol.
STATE_COLLECTION = "agent_state"
STATE_DOCUMENT = "seen_keys"

# Firestore dokument má limit 1 MiB. Kľúč má ~60 bajtov, takže sa ich
# zmestí okolo 16 000. Držíme sa bezpečne pod tým a najstaršie zahadzujeme.
MAX_REMEMBERED_KEYS = 12000


def get_client() -> firestore.Client:
    credentials = service_account.Credentials.from_service_account_file(
        config.FIREBASE_CREDENTIALS_PATH
    )
    return firestore.Client(
        project=config.FIRESTORE_PROJECT_ID, credentials=credentials
    )


def _state_ref(db: firestore.Client):
    return db.collection(STATE_COLLECTION).document(STATE_DOCUMENT)


def get_existing_keys(db: firestore.Client) -> tuple[set[str], set[str]]:
    """
    Vráti (dedupe kľúče, URL adresy) toho, čo sa už nemá navrhovať.

    Skladá sa z dvoch častí:
    1. Pamäť agenta — všetko, čo kedy navrhol (schválené, zamietnuté aj
       čakajúce). Keď nejaký návrh odmietneš, agent ti ho nemá o tri
       hodiny ponúknuť znova. Stojí to 1 prečítanie.
    2. Dealy pridané za posledných N dní — zachytí aj tie, ktoré pridal
       ručne ty alebo návštevník, nie agent.
    """
    keys: set[str] = set()
    urls: set[str] = set()

    # 1) Pamäť agenta — jeden dokument, jedno prečítanie.
    try:
        snapshot = _state_ref(db).get()
        if snapshot.exists:
            data = snapshot.to_dict() or {}
            keys.update(data.get("keys", []))
            logger.info("Pamäť agenta: %d známych kľúčov", len(keys))
        else:
            logger.info("Pamäť agenta zatiaľ neexistuje — vytvorí sa po prvom zápise.")
    except Exception as e:
        # Bez pamäte beh pokračuje, len hrozia duplicity — to je menšie
        # zlo než spadnutý beh.
        logger.warning("Pamäť agenta sa nepodarilo načítať: %s", e)

    # 2) Nedávno pridané dealy (aj tie, ktoré agent nevytvoril).
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.DEDUPE_LOOKBACK_DAYS)
    try:
        recent = (
            db.collection(config.DEALS_COLLECTION)
            .where(filter=FieldFilter("timestamp", ">=", cutoff))
            .stream()
        )
        count = 0
        for doc in recent:
            count += 1
            data = doc.to_dict() or {}
            if data.get("dedupeKey"):
                keys.add(data["dedupeKey"])
            if data.get("url"):
                urls.add(data["url"].rstrip("/"))
        logger.info("Nedávnych dealov prečítaných: %d", count)
    except Exception as e:
        logger.warning("Dotaz na nedávne dealy zlyhal: %s", e)

    return keys, urls


def write_pending_deals(
    db: firestore.Client, deals: list[dict]
) -> list[tuple[str, dict]]:
    """
    Zapíše návrhy do kolekcie deals so statusom pending a zároveň si ich
    kľúče poznačí do pamäte agenta. Oboje v jednej dávke, takže buď
    prejde všetko, alebo nič — pamäť sa nikdy nerozíde so skutočnosťou.

    Vracia dvojice (id dokumentu, deal). ID treba na Telegram tlačidlá —
    bez neho by sa nedalo povedať, o ktorom deale sa rozhoduje.
    """
    if not deals:
        return []

    batch = db.batch()
    collection = db.collection(config.DEALS_COLLECTION)

    written: list[tuple[str, dict]] = []
    new_keys: list[str] = []
    for deal in deals:
        document = dict(deal)
        # Čas určuje server, nie stroj, na ktorom beží scraper.
        document["timestamp"] = firestore.SERVER_TIMESTAMP
        document["author"] = config.AGENT_AUTHOR_NAME
        document["votes"] = _random_boost()

        doc_ref = collection.document()
        batch.set(doc_ref, document)
        written.append((doc_ref.id, document))
        if document.get("dedupeKey"):
            new_keys.append(document["dedupeKey"])

    _remember_keys(db, batch, new_keys)

    batch.commit()
    logger.info("Zapísaných %d návrhov do kolekcie '%s'", len(deals), config.DEALS_COLLECTION)
    return written


def _remember_keys(db: firestore.Client, batch, new_keys: list[str]) -> None:
    """
    Pridá kľúče do pamäte agenta. Zoznam sa oreže na MAX_REMEMBERED_KEYS
    (najstaršie idú preč), aby dokument nikdy nenarazil na 1 MiB limit.
    """
    if not new_keys:
        return

    existing: list[str] = []
    try:
        snapshot = _state_ref(db).get()
        if snapshot.exists:
            existing = (snapshot.to_dict() or {}).get("keys", [])
    except Exception as e:
        logger.warning("Pamäť agenta sa nepodarilo prečítať pred zápisom: %s", e)

    # Nové na koniec, duplicity preč, poradie zachované.
    merged = list(dict.fromkeys(existing + new_keys))
    if len(merged) > MAX_REMEMBERED_KEYS:
        merged = merged[-MAX_REMEMBERED_KEYS:]

    batch.set(
        _state_ref(db),
        {"keys": merged, "updatedAt": firestore.SERVER_TIMESTAMP},
    )


def expire_past_deals(db: firestore.Client) -> int:
    """
    Označí za exspirované dealy, ktorým uplynul dátum platnosti z letáku.

    Dotazuje sa na validUntilISO < dnes. Pozor na hranicu: "Platí do:
    22.9.2026" znamená, že 22.9. ešte platí a exspiruje až 23.9. Preto
    ostrá nerovnosť, nie <=. Je to dotaz na jedno pole, takže
    nepotrebuje composite index, a týka sa len dealov, pri ktorých dátum
    platnosti poznáme (teda tých od agenta) — ručne pridaných sa nedotkne.

    Pole 'expired' je to isté, ktoré prepína tlačidlo "Označiť exspirované"
    v admin paneli, takže sa to na stránke prejaví rovnakým červeným
    štítkom EXSPIROVANÉ.
    """
    today = date.today().isoformat()

    try:
        stale = (
            db.collection(config.DEALS_COLLECTION)
            .where(filter=FieldFilter("validUntilISO", "<", today))
            .stream()
        )
        candidates = list(stale)
    except Exception as e:
        logger.warning("Dotaz na exspirované dealy zlyhal: %s", e)
        return 0

    batch = db.batch()
    count = 0
    for doc in candidates:
        data = doc.to_dict() or {}
        # Už označené preskakujeme, nech zbytočne nezapisujeme.
        if data.get("expired") is True:
            continue
        batch.update(doc.reference, {"expired": True})
        count += 1

    if count:
        batch.commit()
        logger.info("Označených ako exspirované: %d dealov", count)
    else:
        logger.info("Žiadne dealy na exspiráciu (prezretých %d).", len(candidates))

    return count


def reset_agent_pending(db: firestore.Client) -> int:
    """
    Zmaže návrhy od agenta, ktoré ešte čakajú na schválenie, a vyprázdni
    jeho pamäť. Slúži na čistý štart po väčšej zmene (napr. keď pribudli
    popisky a staré návrhy ich ešte nemajú).

    Maže VÝHRADNE dokumenty, ktoré má agent na svedomí a ktoré si nikto
    neschválil: autoGenerated == True A ZÁROVEŇ status == "pending".
    Schválených, zamietnutých ani ručne pridaných dealov sa nedotkne.
    """
    try:
        docs = list(
            db.collection(config.DEALS_COLLECTION)
            .where(filter=FieldFilter("status", "==", "pending"))
            .stream()
        )
    except Exception as e:
        logger.error("Nepodarilo sa načítať čakajúce návrhy: %s", e)
        return 0

    batch = db.batch()
    count = 0
    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("autoGenerated") is not True:
            continue  # ručne pridaný deal - nechávame na pokoji
        batch.delete(doc.reference)
        count += 1

    # Pamäť musí ísť preč tiež, inak by agent tie isté dealy považoval
    # za už navrhnuté a nenahradil by ich.
    batch.delete(_state_ref(db))

    batch.commit()
    logger.warning(
        "RESET: zmazaných %d čakajúcich návrhov od agenta a vyprázdnená pamäť.", count
    )
    return count


def _random_boost() -> int:
    """
    Náhodný štartovací žiar. Vráti 0, keď je funkcia vypnutá (predvolené).

    Zámerne je to jediné miesto, kde sa žiar prideľuje - aby sa dalo na
    jednom mieste overiť, že bez výslovného zapnutia je vždy nula.
    """
    if config.VOTE_BOOST_MAX <= 0:
        return 0
    low = max(0, config.VOTE_BOOST_MIN)
    high = max(low, config.VOTE_BOOST_MAX)
    return random.randint(low, high)


def boost_existing_deals(db: firestore.Client) -> int:
    """
    Pridelí štartovací žiar dealom od agenta, ktoré ešte nemajú ani jeden
    hlas. Jednorazová pomôcka na rozbeh stránky.

    Dotkne sa len dealov s autoGenerated == True a votes == 0, takže
    nikomu neprepíše skutočné hlasy od návštevníkov.
    """
    if config.VOTE_BOOST_MAX <= 0:
        return 0

    try:
        docs = list(
            db.collection(config.DEALS_COLLECTION)
            .where(filter=FieldFilter("autoGenerated", "==", True))
            .stream()
        )
    except Exception as e:
        logger.warning("Nepodarilo sa načítať dealy na boost: %s", e)
        return 0

    batch = db.batch()
    count = 0
    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("votes"):
            continue  # už má hlasy - skutočné alebo z predošlého boostu
        batch.update(doc.reference, {"votes": _random_boost()})
        count += 1

    if count:
        batch.commit()
        logger.warning(
            "BOOST: %d dealom pridelený štartovací žiar %d-%d stupňov.",
            count, config.VOTE_BOOST_MIN, config.VOTE_BOOST_MAX,
        )
    return count


def fix_merchant_urls(db: firestore.Client) -> int:
    """
    Prepočíta odkazy pri dealoch od agenta, ktoré ešte mieria na zdroj
    namiesto na predajcu. Jednorazová oprava pre dealy zapísané predtým,
    než odkazy k predajcom pribudli.
    """
    from merchant_links import build_merchant_url

    try:
        docs = list(
            db.collection(config.DEALS_COLLECTION)
            .where(filter=FieldFilter("autoGenerated", "==", True))
            .stream()
        )
    except Exception as e:
        logger.warning("Nepodarilo sa načítať dealy na opravu odkazov: %s", e)
        return 0

    batch = db.batch()
    count = 0
    for doc in docs:
        data = doc.to_dict() or {}
        current = data.get("url") or ""
        if "zlacnene.sk" not in current:
            continue  # už opravené alebo odkaz zadal človek

        new_url = build_merchant_url(
            data.get("store", ""), data.get("title", ""), current
        )
        if new_url == current:
            continue  # predajcu nepoznáme, nechávame tak

        update = {"url": new_url}
        # Pôvodný odkaz si odložíme, ak tam ešte nie je.
        if not data.get("sourceUrl"):
            update["sourceUrl"] = current
        batch.update(doc.reference, update)
        count += 1

    if count:
        batch.commit()
        logger.warning("Opravených odkazov na predajcu: %d", count)
    else:
        logger.info("Žiadne odkazy na opravu (prezretých %d).", len(docs))
    return count


def load_price_history(db: firestore.Client, dedupe_keys: list[str]) -> dict[str, list]:
    """
    Načíta históriu cien pre dané produkty. Kľúčom je dedupe kľúč bez
    ceny — ten istý produkt má pri každej cene iný plný kľúč, takže by
    sa história nikdy nespojila.
    """
    if not dedupe_keys:
        return {}

    history: dict[str, list] = {}
    try:
        docs = (
            db.collection(config.DEALS_COLLECTION)
            .where(filter=FieldFilter("autoGenerated", "==", True))
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            key = data.get("productKey")
            points = data.get("priceHistory")
            if not key or not points:
                continue
            # Ak ten istý produkt existuje viackrát, spojíme záznamy.
            merged = history.setdefault(key, [])
            merged.extend(points)
    except Exception as e:
        logger.warning("História cien sa nepodarila načítať: %s", e)
        return {}

    # Zoradiť a odstrániť duplicitné dni.
    for key, points in history.items():
        by_date = {p.get("date"): p for p in points if p.get("date")}
        history[key] = sorted(by_date.values(), key=lambda p: p["date"])

    return history


def expire_dead_deals(db: firestore.Client, limit: int = 30) -> int:
    """
    Označí za exspirované dealy, ktorých pôvodná stránka už neexistuje.

    Dopĺňa exspiráciu podľa dátumu: zachytí aj akcie, ktoré predajca
    stiahol skôr, než mali skončiť. Kontroluje sa najviac `limit`
    dealov za beh, aby to nenafúklo čas behu ani zaťaženie cudzieho webu.
    """
    import http_client

    try:
        docs = list(
            db.collection(config.DEALS_COLLECTION)
            .where(filter=FieldFilter("autoGenerated", "==", True))
            .stream()
        )
    except Exception as e:
        logger.warning("Nepodarilo sa načítať dealy na kontrolu odkazov: %s", e)
        return 0

    checked = 0
    dead = 0
    batch = db.batch()

    for doc in docs:
        if checked >= limit:
            break
        data = doc.to_dict() or {}
        if data.get("expired") is True or data.get("status") == "rejected":
            continue
        source = data.get("sourceUrl")
        if not source:
            continue

        checked += 1
        if http_client.is_reachable(source, detect_soft_404=True):
            continue

        batch.update(doc.reference, {"expired": True})
        dead += 1
        logger.info("Zdroj dealu zmizol, označujem exspirované: %s", data.get("title", "")[:50])

    if dead:
        batch.commit()
    logger.info("Kontrola odkazov: prezretých %d, mŕtvych %d", checked, dead)
    return dead


def boost_coupons(db: firestore.Client) -> int:
    """
    Jednorazovo pridelí zľavovým kódom štartovací žiar.

    Rovnaká pomôcka ako pri dealoch a s rovnakým obmedzením: beží len pri
    ručnom spustení, plánované behy ju nikdy nezapnú.

    Časť kódov dostane zámerne zápornú hodnotu. Zoznam, kde má úplne
    všetko kladné číslo, vyzerá nedôveryhodne - pri kupónoch je bežné, že
    časť nefunguje, a práve to dáva hlasovaniu zmysel.

    Dotkne sa len kódov, ktoré ešte nemajú ani jeden hlas.
    """
    if config.COUPON_BOOST_MAX <= 0:
        return 0

    try:
        docs = list(db.collection("coupons").stream())
    except Exception as e:
        logger.warning("Nepodarilo sa načítať zľavové kódy: %s", e)
        return 0

    batch = db.batch()
    count = 0
    cold = 0

    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("votes"):
            continue  # už má hlasy, skutočné alebo z predošlého behu

        if random.random() < config.COUPON_FREEZE_CHANCE:
            value = random.randint(config.COUPON_FREEZE_MIN, config.COUPON_FREEZE_MAX)
            cold += 1
        else:
            value = random.randint(config.COUPON_BOOST_MIN, config.COUPON_BOOST_MAX)

        batch.update(doc.reference, {"votes": value})
        count += 1

    if count:
        batch.commit()
        logger.warning(
            "BOOST kupónov: %d kódom pridelený žiar (%d z nich záporný).", count, cold
        )
    else:
        logger.info("Žiadne kódy na boost (prezretých %d).", len(docs))
    return count




def purge_expired_coupons(db: firestore.Client) -> int:
    """
    Nenávratne zmaže zľavové kódy, ktoré sú po platnosti dlhšie, než
    dovoľuje nastavenie v admin paneli.

    PREČO JE TO PREDVOLENE VYPNUTÉ
    Mazanie sa nedá vrátiť späť. Keby sa zapínalo samo tým, že sa
    doplní kód, stačilo by jedno zle vyplnené pole "platí do" a kupón
    by zmizol bez stopy. Zapína to človek v admin paneli vedome.

    Kódy bez dátumu platnosti sa nemažú nikdy - nevieme o nich povedať,
    či ešte platia.
    """
    try:
        nastavenia = (db.document("settings/moderation").get().to_dict() or {})
    except Exception as e:
        logger.warning("Nastavenia sa nepodarilo prečítať, nemažem nič: %s", e)
        return 0

    if nastavenia.get("purgeExpiredCoupons") is not True:
        return 0

    mesiace = nastavenia.get("purgeAfterMonths")
    try:
        mesiace = int(mesiace)
    except (TypeError, ValueError):
        mesiace = 3
    mesiace = max(1, min(36, mesiace))

    # Mesiac berieme ako 30 dní. Presný posun po kalendári by tu nič
    # nezmenil - rozdiel jedného dňa pri trojmesačnej lehote je šum.
    hranica = (date.today() - timedelta(days=mesiace * 30)).isoformat()

    try:
        stare = (
            db.collection("coupons")
            .where(filter=FieldFilter("expiryISO", "<", hranica))
            .stream()
        )
        kandidati = list(stare)
    except Exception as e:
        logger.warning("Dotaz na staré kupóny zlyhal: %s", e)
        return 0

    if not kandidati:
        return 0

    batch = db.batch()
    count = 0
    for doc in kandidati:
        data = doc.to_dict() or {}
        logger.info("Mažem kupón po platnosti: %s / %s (platil do %s)",
                    data.get("store", "?"), data.get("code", "?"), data.get("expiryISO"))
        batch.delete(doc.reference)
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()

    if count % 400:
        batch.commit()

    logger.info("Zmazaných kupónov po platnosti dlhšie než %d mesiacov: %d", mesiace, count)
    return count


FOOD_PRICES_DOC = "food_prices/current"

# Koľko dní histórie držíme. Tridsať je to, s čím počíta graf na
# stránke; šesťdesiat je rezerva, aby sa dalo neskôr porovnávať aj
# dlhšie obdobie bez toho, aby dokument narástol do nezmyslu.
FOOD_HISTORY_DAYS = 60


def _food_history(ref, data: dict) -> dict:
    """
    K existujúcej histórii pridá dnešnú najnižšiu cenu každej položky.

    Históriu držíme v tom istom dokumente, nie vo vlastnej kolekcii:
    stránka ju číta spolu s cenami jedným dotazom a Firestore účtuje
    za dokument, nie za jeho veľkosť. Desať položiek krát šesťdesiat
    dní je pár kilobajtov.

    Porovnávač vracia ceny raz denne, takže dnešný záznam prepisujeme,
    nie pridávame - inak by tri behy agenta spravili tri body za deň.
    """
    try:
        current = (ref.get().to_dict() or {}).get("history") or {}
    except Exception as e:
        logger.warning("Históriu cien sa nepodarilo prečítať: %s", e)
        current = {}

    day = data.get("reportDate") or date.today().isoformat()
    history: dict[str, list] = {}

    for item in data["items"]:
        prices = item.get("prices") or []
        if not prices:
            continue
        cheapest = min(p["price"] for p in prices)
        series = [row for row in current.get(item["label"], []) if row.get("d") != day]
        series.append({"d": day, "p": cheapest})
        series.sort(key=lambda row: row["d"])
        history[item["label"]] = series[-FOOD_HISTORY_DAYS:]

    days = max((len(s) for s in history.values()), default=0)
    logger.info("História cien: %d položiek, najdlhší rad %d dní.", len(history), days)
    return history


def refresh_food_prices(db: firestore.Client, snapshot_data: dict | None = None) -> bool:
    """
    Raz denne obnoví prehľad cien základných potravín.

    Ceny v porovnávači sa menia raz za deň, takže pri troch behoch denne
    by sťahovanie pri každom bolo len zbytočné zaťaženie cudzieho servera.

    `snapshot_data` je pre volajúceho, ktorý si ceny už stiahol sám
    (refresh_food_prices.py si ich pýta, aby ich vypísal do denníka).
    Bez toho by sa ťahali dvakrát za sebou z cudzieho servera — nechcem
    od národného porovnávača brať dvojnásobok toho, čo naozaj potrebujem.
    """
    import food_prices

    today = date.today().isoformat()
    ref = db.document(FOOD_PRICES_DOC)

    # Keď ceny prišli od volajúceho, už ich stiahol a chce ich zapísať.
    # Preskakovať vtedy nemá čo — kontrola je tu len proti zbytočnému
    # sťahovaniu, nie proti zápisu.
    if snapshot_data is None:
        try:
            snapshot = ref.get()
            if snapshot.exists and (snapshot.to_dict() or {}).get("fetchedAt") == today:
                logger.info("Ceny potravín sú už dnešné, sťahovanie preskakujem.")
                return False
        except Exception as e:
            logger.warning("Stav cien potravín sa nepodarilo prečítať: %s", e)

    # Zber cien beží aj v cloude, kde ho zdroj blokuje a volanie vyprší.
    # Keby to vyhodilo výnimku, zhodilo by to celý beh agenta - a dealy
    # by neprišli len preto, že sa nepodarili potraviny. Preto sem, a nie
    # k volajúcemu: sem patrí vedomosť o tom, že tento zdroj je krehký.
    #
    # Zároveň je to poistka do budúcna: keď cenyslovensko.sk dátové
    # centrá odblokuje, cloud jednoducho začne uspievať a lokálna
    # plánovaná úloha sa stane zbytočnou bez zásahu do kódu.
    try:
        data = snapshot_data if snapshot_data else food_prices.build_snapshot()
    except Exception as e:
        logger.warning("Ceny potravín sa nepodarilo stiahnuť (%s) — "
                       "nechávam včerajšie.", e)
        return False
    if data and data.get("items"):
        data["history"] = _food_history(ref, data)
    if not data or not data.get("items"):
        # Radšej necháme včerajšie ceny než prázdnu sekciu.
        return False

    try:
        ref.set(data)
    except Exception as e:
        logger.error("Ceny potravín sa nepodarilo uložiť: %s", e)
        return False

    logger.info("Ceny potravín obnovené (%d položiek, zber %s).",
                len(data["items"]), data["reportDate"])
    return True
