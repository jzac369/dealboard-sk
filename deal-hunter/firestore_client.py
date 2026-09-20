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


def write_pending_deals(db: firestore.Client, deals: list[dict]) -> int:
    """
    Zapíše návrhy do kolekcie deals so statusom pending a zároveň si ich
    kľúče poznačí do pamäte agenta. Oboje v jednej dávke, takže buď
    prejde všetko, alebo nič — pamäť sa nikdy nerozíde so skutočnosťou.
    """
    if not deals:
        return 0

    batch = db.batch()
    collection = db.collection(config.DEALS_COLLECTION)

    new_keys: list[str] = []
    for deal in deals:
        document = dict(deal)
        # Čas určuje server, nie stroj, na ktorom beží scraper.
        document["timestamp"] = firestore.SERVER_TIMESTAMP
        document["author"] = config.AGENT_AUTHOR_NAME
        document["votes"] = _random_boost()
        batch.set(collection.document(), document)
        if document.get("dedupeKey"):
            new_keys.append(document["dedupeKey"])

    _remember_keys(db, batch, new_keys)

    batch.commit()
    logger.info("Zapísaných %d návrhov do kolekcie '%s'", len(deals), config.DEALS_COLLECTION)
    return len(deals)


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

    Dotazuje sa na validUntilISO <= dnes. Je to dotaz na jedno pole, takže
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
            .where(filter=FieldFilter("validUntilISO", "<=", today))
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
