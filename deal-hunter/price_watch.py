"""
Sledovanie cien produktov z affiliate feedov.

PREČO TO POTREBUJEME
Feedy vo formáte Heureka (ktorý používa Dognet) uvádzajú len aktuálnu
cenu — pole s cenou pred zľavou v nich spravidla nie je. Bez nej sa
zľava nedá spočítať a parser by zahodil úplne všetko.

Riešenie je nečakať na to, čo o zľave tvrdí predajca, a sledovať cenu
samostatne. Keď spadne pod doteraz najnižšiu videnú hodnotu, je to
skutočná zľava — a poctivejšia definícia než tá, ktorú si predajca
určuje sám.

Cena za to: prvé dni feed nevydá nič, kým sa nenazbierajú dáta.

AKO SA TO UKLADÁ, ABY TO NESTÁLO MAJETOK
Firestore sa účtuje za dokumenty, nie za bajty. Feed má bežne tisíce
položiek; jeden dokument na produkt by znamenal tisíce zápisov denne
a rýchlo by minul denný limit.

Preto sú produkty poskladané do niekoľkých „vedierok" — jeden dokument
drží mapu {productKey: {min, last, updated}} pre stovky produktov.
Pri BUCKET_COUNT vedierkach to vyjde na toľko istých čítaní a zápisov
za beh, bez ohľadu na veľkosť feedu.
"""

import hashlib
import logging
from datetime import date

logger = logging.getLogger(__name__)

COLLECTION = "price_watch"

# Koľko dokumentov si delí všetky sledované produkty. Dokument má limit
# 1 MiB, jeden záznam zaberá zhruba 80 bajtov — do jedného vedierka sa
# teda zmestí rádovo 12 000 produktov.
BUCKET_COUNT = 20


def bucket_of(product_key: str) -> str:
    """Rozdelí produkty rovnomerne medzi vedierka podľa hashu kľúča."""
    digest = hashlib.md5(product_key.encode("utf-8")).hexdigest()
    return f"b{int(digest[:8], 16) % BUCKET_COUNT:02d}"


def load(db, product_keys: list[str]) -> dict[str, dict]:
    """
    Načíta sledované ceny pre dané produkty. Číta len tie vedierka,
    v ktorých sa nejaký hľadaný produkt nachádza.
    """
    wanted = set(product_keys)
    if not wanted:
        return {}

    buckets = {bucket_of(k) for k in wanted}
    known: dict[str, dict] = {}

    for bucket in sorted(buckets):
        try:
            snapshot = db.collection(COLLECTION).document(bucket).get()
        except Exception as e:
            logger.warning("Vedierko %s sa nepodarilo načítať: %s", bucket, e)
            continue
        if not snapshot.exists:
            continue
        for key, record in (snapshot.to_dict() or {}).items():
            if key in wanted and isinstance(record, dict):
                known[key] = record

    logger.info("Sledovaných cien načítaných: %d (z %d vedierok)", len(known), len(buckets))
    return known


def save(db, updates: dict[str, dict]) -> int:
    """
    Zapíše aktualizované záznamy. Zlúči ich do vedierok, takže počet
    zápisov závisí od počtu vedierok, nie od počtu produktov.
    """
    if not updates:
        return 0

    by_bucket: dict[str, dict] = {}
    for key, record in updates.items():
        by_bucket.setdefault(bucket_of(key), {})[key] = record

    batch = db.batch()
    for bucket, records in by_bucket.items():
        batch.set(db.collection(COLLECTION).document(bucket), records, merge=True)

    try:
        batch.commit()
    except Exception as e:
        logger.warning("Sledované ceny sa nepodarilo uložiť: %s", e)
        return 0

    logger.info("Uložených %d sledovaných cien do %d vedierok", len(updates), len(by_bucket))
    return len(by_bucket)


def evaluate(
    product_key: str, price: float, known: dict[str, dict], min_drop_percent: float
) -> tuple[bool, float | None, dict]:
    """
    Posúdi jednu položku z feedu.

    Vráti (zverejniť, referenčná_cena, nový_záznam).

    `referenčná_cena` je doteraz najnižšia videná cena — tú ukážeme ako
    pôvodnú. Je to tvrdenie, ktoré vieme doložiť vlastným meraním, na
    rozdiel od „bežnej ceny", ktorú si predajca určuje sám.
    """
    today = date.today().isoformat()
    record = known.get(product_key)

    if not record or not isinstance(record.get("min"), (int, float)):
        # Produkt vidíme prvýkrát — nemáme s čím porovnávať.
        return False, None, {"min": round(price, 2), "last": round(price, 2), "updated": today}

    previous_min = float(record["min"])
    new_record = {
        "min": round(min(previous_min, price), 2),
        "last": round(price, 2),
        "updated": today,
    }

    if previous_min <= 0 or price >= previous_min:
        return False, None, new_record

    drop = (previous_min - price) / previous_min * 100
    if drop < min_drop_percent:
        return False, None, new_record

    return True, round(previous_min, 2), new_record
