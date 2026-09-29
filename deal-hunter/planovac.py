"""
Plánovač úloh riadený z admin zóny.

PREČO NIE CRON V SÚBOROCH WORKFLOW
Časy behov boli zapísané v .github/workflows/*.yml. Zmeniť ich z admina
by znamenalo dať stránke GitHub token - a ten by si ktokoľvek vytiahol
z kódu verejnej stránky. Rozvrh je preto v databáze (settings/schedule),
kam admin zapisuje bezpečne cez prihlásenie, a GitHub sa sem každých
15 minút pozrie, čo je na rade.

ČAS
Časy sa zadávajú v slovenskom čase (Europe/Bratislava), nie v UTC ako
cron. Zmena letného a zimného času tak nič neposunie.

AKO SA ROZHODUJE, ČI ÚLOHA BEŽÍ
Pre každú úlohu nájdeme najnovší naplánovaný čas, ktorý už nastal. Ak
sme ho ešte nespustili a nie je príliš starý, spustíme. Zapamätáme si
presne ten čas, takže každý termín prebehne najviac raz - aj keď GitHub
kontrolu pustí s oneskorením alebo dvakrát.

"Príliš starý" chráni pred tým, aby po dlhšom výpadku naraz dobehli
všetky zmeškané termíny. V cloude je to 3 hodiny. Ceny potravín bežia
na tvojom počítači, ktorý môže byť vypnutý, tak tam je to 12 hodín:
keď počítač zapneš poobede, ranné ceny sa ešte stiahnu.

Spustenie:
  python planovac.py              rozhodne a spustí úlohy v cloude
  python planovac.py --nasucho    len vypíše, čo by spustil
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger("planovac")

ZONA = ZoneInfo("Europe/Bratislava")

# Úloha -> čo sa spustí. "lokalne" beží na tvojom počítači (ceny potravín),
# cloudový plánovač ju preskočí a rozhoduje o nej refresh_food_prices.py.
ULOHY = {
    "agent":     {"workflow": "deal-hunter.yml", "okno_h": 3},
    "letenky":   {"workflow": "letenky.yml",     "okno_h": 3},
    "ziar":      {"workflow": "denny-ziar.yml",  "okno_h": 3},
    "facebook":  {"workflow": "facebook.yml",    "okno_h": 3},
    "potraviny": {"lokalne": True,               "okno_h": 12},
}

# Rozvrh, ktorý platí, kým ho v admine niekto nezmení. Zodpovedá časom,
# ktoré boli doteraz v cron-e (prepočítané na letný čas).
PREDVOLENY = {
    "agent":     {"enabled": True, "times": ["07:30", "12:30", "18:30"]},
    "letenky":   {"enabled": True, "times": ["07:30"]},
    "ziar":      {"enabled": True, "times": ["06:10"]},
    "facebook":  {"enabled": True, "times": ["09:00", "17:00"]},
    "potraviny": {"enabled": True, "times": ["07:15", "13:00"]},
}


def _casy(zoznam) -> list[time]:
    """"07:30" -> time(7, 30). Nezmysly ticho vynechá - chybne zadaný
    čas v admine nesmie zhodiť plánovač pre všetky ostatné úlohy."""
    vysledok = []
    for t in zoznam or []:
        try:
            h, m = str(t).strip().split(":")
            vysledok.append(time(int(h), int(m)))
        except (ValueError, TypeError):
            logger.warning("Neplatný čas v rozvrhu: %r — vynechávam", t)
    return vysledok


def na_rade(casy, posledny_termin: str | None, teraz: datetime,
            okno_h: float) -> datetime | None:
    """
    Vráti termín, ktorý má teraz bežať, alebo None.

    teraz musí byť s časovou zónou. posledny_termin je ISO reťazec
    termínu, ktorý už raz prebehol.
    """
    terminy = []
    for den in (teraz.date() - timedelta(days=1), teraz.date()):
        for t in _casy(casy):
            terminy.append(datetime.combine(den, t, tzinfo=ZONA))

    minule = [t for t in terminy if t <= teraz]
    if not minule:
        return None
    termin = max(minule)

    if teraz - termin > timedelta(hours=okno_h):
        return None                         # príliš starý, nedobiehame
    if posledny_termin == termin.isoformat():
        return None                         # tento termín už prebehol
    return termin


def nacitaj(db) -> dict:
    """Rozvrh z databázy doplnený o predvolené hodnoty."""
    try:
        data = db.document("settings/schedule").get().to_dict() or {}
    except Exception as e:
        logger.error("Rozvrh sa nepodarilo načítať (%s) — používam predvolený", e)
        data = {}
    ulohy = {k: {**v, **(data.get("jobs") or {}).get(k, {})} for k, v in PREDVOLENY.items()}
    return {"jobs": ulohy, "runNow": data.get("runNow") or {}, "stav": data.get("stav") or {}}


def zapis_beh(db, uloha: str, termin: str | None, rucne: bool) -> None:
    from google.cloud import firestore

    zmena = {
        f"stav.{uloha}.lastRun": firestore.SERVER_TIMESTAMP,
        f"stav.{uloha}.manual": rucne,
    }
    if termin:
        zmena[f"stav.{uloha}.lastSlot"] = termin
    if rucne:
        zmena[f"runNow.{uloha}"] = firestore.DELETE_FIELD
    try:
        db.document("settings/schedule").update(zmena)
    except Exception:
        # Dokument ešte neexistuje - update by zlyhal, set s merge nie.
        db.document("settings/schedule").set({}, merge=True)
        db.document("settings/schedule").update(zmena)


def co_spustit(rozvrh: dict, teraz: datetime, lokalne: bool = False) -> list[tuple[str, str | None, bool]]:
    """Zoznam (úloha, termín, spustené ručne) na spustenie."""
    vysledok = []
    for meno, info in ULOHY.items():
        if bool(info.get("lokalne")) != lokalne:
            continue
        nast = rozvrh["jobs"].get(meno, {})
        if rozvrh["runNow"].get(meno):
            vysledok.append((meno, None, True))
            continue
        if not nast.get("enabled", True):
            continue
        termin = na_rade(nast.get("times"), (rozvrh["stav"].get(meno) or {}).get("lastSlot"),
                         teraz, info["okno_h"])
        if termin:
            vysledok.append((meno, termin.isoformat(), False))
    return vysledok


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    nasucho = "--nasucho" in sys.argv

    import firestore_client
    db = firestore_client.get_client()
    rozvrh = nacitaj(db)
    teraz = datetime.now(ZONA)
    logger.info("Plánovač — %s", teraz.strftime("%d.%m.%Y %H:%M"))

    spustit = co_spustit(rozvrh, teraz)
    if not spustit:
        logger.info("Nič nie je na rade.")
        return 0

    for meno, termin, rucne in spustit:
        workflow = ULOHY[meno]["workflow"]
        dovod = "ručne z admina" if rucne else f"termín {termin[11:16]}"
        if nasucho:
            logger.info("Spustil by som %s (%s)", meno, dovod)
            continue
        r = subprocess.run(["gh", "workflow", "run", workflow], capture_output=True, text=True)
        if r.returncode != 0:
            # Termín NEzapisujeme - ďalšia kontrola o 15 minút to skúsi
            # znova. Opačné poradie by zlyhanú úlohu potichu vynechalo.
            logger.error("Spustenie %s zlyhalo: %s", meno, (r.stderr or r.stdout).strip()[:300])
            continue
        # Keby tento zápis zlyhal, úloha môže bežať dvakrát. To je
        # neškodné: duplicitné dealy, lety aj príspevky na Facebook sú
        # ošetrené na vlastnej úrovni. Vypadnutý beh by bol horší.
        zapis_beh(db, meno, termin, rucne)
        logger.info("Spustené: %s (%s)", meno, dovod)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
