"""
Denná záloha databázy Firestore na disk.

PREČO
Firestore zálohuje Google len na požiadanie a platene. Chyba v skripte,
omylom zmazaná kolekcia alebo prepísané nastavenia by sa inak nedali
vrátiť. Táto záloha je jednoduchá: každý deň jeden priečinok s JSON
súbormi, uchová sa posledných 30 dní.

ČO SA ZÁLOHUJE
Všetky kolekcie z koreňa databázy vrátane jednej úrovne podkolekcií
(napr. komentáre pod dealmi). Zálohujú sa aj tajné nastavenia
(nastavenia_admin - feedy s partnerskými ID), preto má priečinok s
zálohami práva len pre majiteľa (700) a súbory 600. Nikdy nepatrí do
Gitu ani do verejného úložiska.

POUŽITIE
  python zaloha_firestore.py                 -> ~/zalohy/RRRR-MM-DD/
  python zaloha_firestore.py --ciel /cesta   -> inam

Obnova zatiaľ nie je automatická: súbory sú čitateľné JSON (gzip), takže
sa dá obnoviť jednotlivý záznam ručne. Časové hodnoty a odkazy majú tvar
{"__typ": ..., "hodnota": ...}.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import firestore_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("zaloha")

UCHOVAT_DNI = 30


def _json_hodnota(v):
    """Firestore typy -> JSON, s dôrazom na to, aby sa dali pri obnove vrátiť."""
    if isinstance(v, datetime):
        return {"__typ": "cas", "hodnota": v.astimezone(timezone.utc).isoformat()}
    if isinstance(v, bytes):
        return {"__typ": "bajty", "hodnota": v.hex()}
    if isinstance(v, dict):
        return {k: _json_hodnota(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_hodnota(x) for x in v]
    if hasattr(v, "path") and hasattr(v, "id"):  # DocumentReference
        return {"__typ": "ref", "hodnota": v.path}
    if hasattr(v, "latitude") and hasattr(v, "longitude"):  # GeoPoint
        return {"__typ": "geo", "hodnota": [v.latitude, v.longitude]}
    return v


def zalohuj_kolekciu(kolekcia, hlbka: int = 0) -> list[dict]:
    zaznamy: list[dict] = []
    for doc in kolekcia.stream():
        zaznamy.append({"id": doc.id, "cesta": doc.reference.path,
                        "data": _json_hodnota(doc.to_dict() or {})})
        if hlbka < 1:
            try:
                for pod in doc.reference.collections():
                    zaznamy += zalohuj_kolekciu(pod, hlbka + 1)
            except Exception as e:
                logger.warning("Podkolekcie %s sa nepodarilo načítať: %s", doc.reference.path, e)
    return zaznamy


def zalohuj(db, cielovy: Path) -> dict[str, int]:
    cielovy.mkdir(parents=True, exist_ok=True)
    os.chmod(cielovy, 0o700)
    pocty: dict[str, int] = {}
    for kolekcia in db.collections():
        try:
            zaznamy = zalohuj_kolekciu(kolekcia)
        except Exception as e:
            logger.error("Kolekcia %s sa nezálohovala: %s", kolekcia.id, e)
            continue
        subor = cielovy / f"{kolekcia.id}.json.gz"
        with gzip.open(subor, "wt", encoding="utf-8") as f:
            json.dump(zaznamy, f, ensure_ascii=False)
        os.chmod(subor, 0o600)
        pocty[kolekcia.id] = len(zaznamy)
        logger.info("%-24s %6d záznamov", kolekcia.id, len(zaznamy))
    return pocty


def zmaz_stare(koren: Path, dni: int = UCHOVAT_DNI) -> int:
    hranica = date.today() - timedelta(days=dni)
    zmazane = 0
    for d in koren.iterdir():
        try:
            den = date.fromisoformat(d.name)
        except ValueError:
            continue  # cudzie priečinky nechávame na pokoji
        if den < hranica and d.is_dir():
            shutil.rmtree(d)
            zmazane += 1
    return zmazane


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ciel", dest="ciel", default=str(Path.home() / "zalohy"))
    args = ap.parse_args()

    koren = Path(args.ciel)
    koren.mkdir(parents=True, exist_ok=True)
    os.chmod(koren, 0o700)
    cielovy = koren / date.today().isoformat()

    db = firestore_client.get_client()
    pocty = zalohuj(db, cielovy)
    if not pocty:
        logger.error("Nezálohovalo sa nič - kontrolujem prístup k databáze.")
        return 1

    # Záloha bez dokumentov dealov by bola podozrivá - radšej to nahlásime.
    if not pocty.get("deals"):
        logger.error("V zálohe chýbajú dealy (deals) - niečo je zle.")
        return 1

    zmazane = zmaz_stare(koren)
    velkost = sum(p.stat().st_size for p in cielovy.glob("*.json.gz")) / 1_048_576
    logger.info("Záloha hotová: %d kolekcií, %.1f MB, zmazaných starých záloh: %d",
                len(pocty), velkost, zmazane)
    return 0


if __name__ == "__main__":
    sys.exit(main())
