"""
Plánovač úloh riadený z admin zóny.

PREČO NIE CRON V SÚBOROCH WORKFLOW
Časy behov boli zapísané v .github/workflows/*.yml. Zmeniť ich z admina
by znamenalo dať stránke GitHub token - a ten by si ktokoľvek vytiahol
z kódu verejnej stránky. Rozvrh je preto v databáze (settings/schedule),
kam admin zapisuje bezpečne cez prihlásenie, a plánovač sa sem každých
5 minút pozrie, čo je na rade.

PREČO SLUČKA A NIE CRON KAŽDÝCH 15 MINÚT
GitHub naplánované behy (cron) pri bezplatných projektoch obmedzuje -
"*/15" v skutočnosti spúšťal raz za 4-5 hodín. Plánovač preto beží ako
jedna dlhá úloha: takmer 6 hodín (strop GitHubu) kontroluje každých
5 minút a pred koncom spustí svojho nástupcu. Reťaz tak beží
nepretržite. Cron v planovac.yml ostal ako záloha: keby sa reťaz
pretrhla (výpadok GitHubu), do pár hodín ju znova naštartuje. Dve
slučky naraz nebežia - workflow má concurrency skupinu.

ČAS
Časy sa zadávajú v slovenskom čase (Europe/Bratislava), nie v UTC ako
cron. Zmena letného a zimného času tak nič neposunie.

AKO SA ROZHODUJE, ČI ÚLOHA BEŽÍ
Pre každú úlohu nájdeme najnovší naplánovaný čas, ktorý už nastal. Ak
sme ho ešte nespustili a nie je príliš starý, spustíme. Zapamätáme si
presne ten čas, takže každý termín prebehne najviac raz - aj keď GitHub
kontrolu pustí s oneskorením alebo dvakrát.

"Príliš starý" chráni pred tým, aby po dlhšom výpadku naraz dobehli
všetky zmeškané termíny. V cloude je to 8 hodín (poistka pre prípad,
že sa reťaz slučiek pretrhne a čaká sa na záložný cron). Ceny potravín bežia
na tvojom počítači, ktorý môže byť vypnutý, tak tam je to 12 hodín:
keď počítač zapneš poobede, ranné ceny sa ešte stiahnu.

Spustenie:
  python planovac.py              jedna kontrola: rozhodne a spustí úlohy
  python planovac.py --slucka     kontrola každých 5 minút ~5 h 40 min,
                                  potom spustí nástupcu (tak beží v cloude)
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
#
# Okno 8 hodín je poistka: bežne slučka spustí úlohu do 5 minút od
# termínu. Keby sa reťaz slučiek pretrhla, záložný cron GitHubu príde
# až o 4-5 hodín - s užším oknom by sa termín medzitým stratil.
ULOHY = {
    "agent":     {"workflow": "deal-hunter.yml", "okno_h": 8},
    "letenky":   {"workflow": "letenky.yml",     "okno_h": 8},
    "ziar":      {"workflow": "denny-ziar.yml",  "okno_h": 8},
    "facebook":  {"workflow": "facebook.yml",    "okno_h": 8},
    "mapa":      {"workflow": "letenky-mapa.yml", "okno_h": 8},
    "potraviny": {"lokalne": True,               "okno_h": 12},
}

# Rozvrh, ktorý platí, kým ho v admine niekto nezmení. Zodpovedá časom,
# ktoré boli doteraz v cron-e (prepočítané na letný čas).
PREDVOLENY = {
    "agent":     {"enabled": True, "times": ["07:30", "12:30", "18:30"]},
    "letenky":   {"enabled": True, "times": ["07:30"]},
    "ziar":      {"enabled": True, "times": ["06:10"]},
    "facebook":  {"enabled": True, "times": ["09:00", "17:00"]},
    "mapa":      {"enabled": True, "times": ["05:30"]},
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


def odosli_naplanovane(db, teraz: datetime, nasucho: bool) -> None:
    """
    Dealy pripravené dopredu (status "scheduled" a čas sendAt) pošle v
    určený čas do Telegramu na schválenie. Dovtedy ich nevidí nikto -
    ani stránka, ani zoznam na schválenie v admine.

    Status sa mení na "pending" PRED odoslaním: keby správa neodišla,
    deal aspoň čaká v admine, namiesto toho, aby ho každá ďalšia
    kontrola posielala znova.
    """
    from google.cloud.firestore_v1.base_query import FieldFilter
    import telegram_bot

    try:
        docs = list(db.collection("deals").where(filter=FieldFilter("status", "==", "scheduled")).stream())
    except Exception as e:
        logger.warning("Naplánované dealy sa nepodarilo načítať: %s", e)
        return
    for d in docs:
        deal = d.to_dict() or {}
        kedy = deal.get("sendAt")
        if not kedy or kedy > teraz:
            continue
        if nasucho:
            logger.info("Poslal by som naplánovaný deal %s: %s", d.id, deal.get("title"))
            continue
        # Čas dealu = čas odoslania, nie prípravy - inak by sa po
        # schválení na stránke ukázal ako niekoľko dní starý.
        d.reference.update({"status": "pending", "timestamp": teraz})
        if telegram_bot.send_deal_for_approval(d.id, deal):
            logger.info("Naplánovaný deal poslaný na schválenie: %s", deal.get("title"))
        else:
            logger.warning("Telegram správu neprijal - deal %s čaká v admine.", d.id)


def kontrola(db, nasucho: bool) -> None:
    rozvrh = nacitaj(db)
    teraz = datetime.now(ZONA)
    logger.info("Plánovač — %s", teraz.strftime("%d.%m.%Y %H:%M"))

    odosli_naplanovane(db, teraz, nasucho)
    zverejni_naplanovane(db, teraz, nasucho)
    posli_pripomienky(db, teraz, nasucho)
    spusti_facebook_naplanovane(db, teraz, nasucho)
    try:
        import emaily
        emaily.spracuj_registracie(db, nasucho)
        emaily.strazcovia(db, nasucho)
    except Exception as e:
        logger.warning("E-maily zlyhali: %s", e)

    raz_za_hodinu(db, teraz, nasucho)

    spustit = co_spustit(rozvrh, teraz)
    if not spustit:
        logger.info("Nič nie je na rade.")
        return

    for meno, termin, rucne in spustit:
        workflow = ULOHY[meno]["workflow"]
        dovod = "ručne z admina" if rucne else f"termín {termin[11:16]}"
        if nasucho:
            logger.info("Spustil by som %s (%s)", meno, dovod)
            continue
        r = subprocess.run(["gh", "workflow", "run", workflow], capture_output=True, text=True)
        if r.returncode != 0:
            # Termín NEzapisujeme - ďalšia kontrola to skúsi znova.
            # Opačné poradie by zlyhanú úlohu potichu vynechalo.
            logger.error("Spustenie %s zlyhalo: %s", meno, (r.stderr or r.stdout).strip()[:300])
            continue
        # Keby tento zápis zlyhal, úloha môže bežať dvakrát. To je
        # neškodné: duplicitné dealy, lety aj príspevky na Facebook sú
        # ošetrené na vlastnej úrovni. Vypadnutý beh by bol horší.
        zapis_beh(db, meno, termin, rucne)
        logger.info("Spustené: %s (%s)", meno, dovod)


# Slučka: 5 minút medzi kontrolami (tlačidlo "Spustiť teraz" v admine
# tak zareaguje do 5 minút) a koniec rezervu pred 6-hodinovým stropom
# GitHubu, aby stihla spustiť nástupcu.
INTERVAL_MIN = 5
DLZKA_SLUCKY_MIN = int(os.environ.get("PLANOVAC_SLUCKA_MIN", 340))


def slucka(db) -> None:
    import queue
    import time as _time
    import admin_ulohy

    # Úlohy z admina (načítanie odkazu, kontrola platnosti, spustenie
    # workflow) prichádzajú živým odberom - vykonajú sa hneď počas
    # čakania medzi kontrolami, nie až o päť minút.
    fronta: queue.Queue = queue.Queue()
    odber = admin_ulohy.sleduj(db, fronta)

    def cakaj(sekundy: float) -> None:
        do = _time.monotonic() + sekundy
        while True:
            zostava = do - _time.monotonic()
            if zostava <= 0:
                return
            try:
                ref = fronta.get(timeout=zostava)
            except queue.Empty:
                return
            try:
                admin_ulohy.spracuj(db, ref)
            except Exception:
                logger.exception("Úloha z admina zlyhala")

    koniec = _time.monotonic() + DLZKA_SLUCKY_MIN * 60
    while True:
        try:
            kontrola(db, nasucho=False)
        except Exception:
            # Jedna zlyhaná kontrola (výpadok siete, Firestore) nesmie
            # ukončiť celú slučku - ďalšia o 5 minút to skúsi znova.
            logger.exception("Kontrola zlyhala, pokračujem")
        zostava = koniec - _time.monotonic()
        if zostava <= INTERVAL_MIN * 60:
            break
        # Na celé päťminútovky, nech kontroly sedia s časmi v rozvrhu.
        teraz = datetime.now(ZONA)
        dalsia = (teraz.replace(second=5, microsecond=0)
                  + timedelta(minutes=INTERVAL_MIN - teraz.minute % INTERVAL_MIN))
        cakaj(max(30, (dalsia - teraz).total_seconds()))

    if odber:
        odber.unsubscribe()
    r = subprocess.run(["gh", "workflow", "run", "planovac.yml"], capture_output=True, text=True)
    if r.returncode == 0:
        logger.info("Slučka končí, nástupca spustený.")
    else:
        # Nevadí - záložný cron reťaz znova naštartuje.
        logger.error("Nástupcu sa nepodarilo spustiť: %s", (r.stderr or r.stdout).strip()[:300])


def posli_pripomienky(db, teraz: datetime, nasucho: bool) -> None:
    """
    Pripomienky do Telegramu (kolekcia "pripomienky": text, sendAt,
    odoslane). Zapisuje ich admin alebo Claude, keď si niečo treba
    pripomenúť o pár dní - napr. zapnúť vynucovanie App Check.
    """
    from google.cloud.firestore_v1.base_query import FieldFilter
    import telegram_bot

    try:
        docs = list(db.collection("pripomienky").where(filter=FieldFilter("odoslane", "==", False)).stream())
    except Exception as e:
        logger.warning("Pripomienky sa nepodarilo načítať: %s", e)
        return
    for d in docs:
        p = d.to_dict() or {}
        if not p.get("sendAt") or p["sendAt"] > teraz:
            continue
        if nasucho:
            logger.info("Poslal by som pripomienku: %s", (p.get("text") or "")[:60])
            continue
        if telegram_bot.send_text("🔔 <b>Pripomienka</b>\n\n" + (p.get("text") or "")):
            d.reference.update({"odoslane": True, "odoslaneKedy": teraz})
            logger.info("Pripomienka odoslaná: %s", (p.get("text") or "")[:60])
        else:
            logger.warning("Pripomienku %s sa nepodarilo poslať, skúsim znova.", d.id)


def zverejni_naplanovane(db, teraz: datetime, nasucho: bool) -> None:
    """
    Dealy schválené s odloženým zverejnením (status "planned", čas
    publishAt) v určený čas zverejní. Čas dealu sa nastaví na čas
    zverejnenia, aby sa na stránke zaradil medzi najnovšie a aby ho
    zdieľanie na Facebook nepovažovalo za starý.
    """
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter

    try:
        docs = list(db.collection("deals").where(filter=FieldFilter("status", "==", "planned")).stream())
    except Exception as e:
        logger.warning("Dealy na zverejnenie sa nepodarilo načítať: %s", e)
        return
    zverejnene = 0
    for d in docs:
        deal = d.to_dict() or {}
        kedy = deal.get("publishAt")
        if not kedy or kedy > teraz:
            continue
        if nasucho:
            logger.info("Zverejnil by som %s: %s", d.id, deal.get("title"))
            continue
        d.reference.update({"status": "approved", "timestamp": firestore.SERVER_TIMESTAMP})
        db.collection("audit_log").add({
            "dealId": d.id, "action": "approved", "detail": deal.get("title"),
            "by": "Plánovač (odložené zverejnenie)", "timestamp": firestore.SERVER_TIMESTAMP,
        })
        logger.info("Zverejnený naplánovaný deal: %s", deal.get("title"))
        zverejnene += 1
    if zverejnene:
        # Stránka dealu hneď - bez nej by zdieľanie na Facebook čakalo
        # na hodinové generovanie.
        r = subprocess.run(["gh", "workflow", "run", "generate-deal-pages.yml"], capture_output=True, text=True)
        if r.returncode != 0:
            logger.warning("Generovanie stránok sa nepodarilo spustiť: %s", (r.stderr or r.stdout).strip()[:200])


def spusti_facebook_naplanovane(db, teraz: datetime, nasucho: bool) -> None:
    """
    Príspevky naplánované v admine (kolekcia fb_posty) odosiela
    facebook_post.py - len ten má token stránky. Plánovač ho spustí,
    keď je niektorý príspevok na rade. Značka "spustene" bráni tomu,
    aby sa workflow spúšťal každých 5 minút, kým beh ešte čaká v rade.
    """
    from google.cloud.firestore_v1.base_query import FieldFilter

    try:
        docs = list(db.collection("fb_posty").where(filter=FieldFilter("stav", "==", "naplanovany")).stream())
    except Exception as e:
        logger.warning("Naplánované príspevky sa nepodarilo načítať: %s", e)
        return
    na_rade = []
    for d in docs:
        p = d.to_dict() or {}
        if not p.get("sendAt") or p["sendAt"] > teraz:
            continue
        spustene = p.get("spustene")
        if spustene and teraz - spustene < timedelta(minutes=30):
            continue
        na_rade.append(d)
    if not na_rade:
        return
    if nasucho:
        logger.info("Spustil by som zdieľanie %d naplánovaných príspevkov.", len(na_rade))
        return
    r = subprocess.run(["gh", "workflow", "run", "facebook.yml", "-f", "rezim=naplanovane"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        logger.error("Zdieľanie naplánovaných príspevkov sa nepodarilo spustiť: %s",
                     (r.stderr or r.stdout).strip()[:300])
        return
    for d in na_rade:
        d.reference.update({"spustene": teraz})
    logger.info("Spustené zdieľanie %d naplánovaných príspevkov.", len(na_rade))


def raz_za_hodinu(db, teraz: datetime, nasucho: bool) -> None:
    """Body a odznaky prispievateľov a denný e-mail o lacných letenkách.
    Prechádza všetky dealy a používateľov, tak to nerobíme každých 5 minút."""
    from google.cloud import firestore

    ref = db.document("nastavenia_admin/komunita_stav")
    try:
        posledny = (ref.get().to_dict() or {}).get("poslednyBeh")
        if posledny and teraz - posledny < timedelta(minutes=55):
            return
    except Exception as e:
        logger.warning("Stav komunity sa nepodarilo načítať: %s", e)
        return
    if nasucho:
        logger.info("Prepočítal by som body prispievateľov a poslal letenky.")
        return
    ref.set({"poslednyBeh": firestore.SERVER_TIMESTAMP}, merge=True)
    try:
        import komunita
        komunita.prepocitaj(db)
    except Exception as e:
        logger.warning("Body prispievateľov sa nepodarilo prepočítať: %s", e)
    try:
        import emaily
        emaily.letenky(db, nasucho)
    except Exception as e:
        logger.warning("E-maily o letenkách zlyhali: %s", e)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    nasucho = "--nasucho" in sys.argv

    import firestore_client
    db = firestore_client.get_client()
    if "--slucka" in sys.argv and not nasucho:
        slucka(db)
    else:
        kontrola(db, nasucho)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
