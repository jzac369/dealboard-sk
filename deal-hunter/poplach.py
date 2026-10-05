"""
Poplach - keď sa niečo pokazí, dozvieme sa o tom do Telegramu.

PREČO TOTO EXISTUJE
5. 10. 2026 sa vyčerpala kvóta Firestore. Agent kvôli tomu navrhol tie
isté dealy dookola a hlasovanie na stránke prestalo fungovať. Chyby boli
pritom celý čas v logoch GitHub Actions - len ich nikto nečítal, lebo nič
neupozornilo, že je problém. Poplach to mení: keď niečo zlyhá, prídeš o
tom správa do Telegramu a nemusíš nič kontrolovať.

Posiela sa striedmo - rovnaký problém najviac raz za pár hodín, aby sa z
poplachu nestal ďalší zdroj stoviek správ.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Čo sa už v tomto behu ohlásilo. Keď sa nedá zapísať do databázy (a
# práve vtedy poplach najviac treba), drží sa pamäť aspoň tu.
_OHLASENE: dict[str, datetime] = {}

ODKAZ_KVOTA = "https://console.firebase.google.com/project/dealboard-e60bf/usage"

# Ľudské vysvetlenie pre bežné poruchy. Bez neho by správa bola len
# anglický výpis výnimky.
RADY = {
    "kvota": ("Vyčerpaná denná kvóta Firestore. Stránka môže prestať "
              f"reagovať, obnoví sa o 9:00. Spotreba: {ODKAZ_KVOTA}"),
    "pamat": ("Agent vynechal beh - nedokázal prečítať pamäť toho, čo už "
              "navrhol. Je to tak správne: inak by poslal všetko odznova."),
    "zapis": ("Plánovač nedokázal zapísať, že úlohu už spustil. V tomto "
              "behu ju znova nespustí, ale treba zistiť prečo."),
    "rozvrh": ("Plánovač nedokázal prečítať rozvrh, takže nič nespustil. "
               "Automatické úlohy sa medzitým neodbavujú."),
    "historia": ("Ceny potravín sa dnes neobnovili - nedá sa prečítať "
                 "doterajšia história a prepisovať ju naslepo by zmazalo grafy."),
    "spustenie": "Plánovaču sa nepodarilo spustiť úlohu na GitHube.",
    "slucka": ("Poistka zastavila opakované spúšťanie tej istej úlohy. "
               "Niečo je v plánovači pokazené - pozri logy."),
}


def je_kvota(chyba: object) -> bool:
    """Rozpozná vyčerpanú kvótu Firestore - tá si žiada inú radu."""
    t = str(chyba).lower()
    return "quota" in t or "429" in t or "resource_exhausted" in t


def nahlas(kod: str, podrobnosti: str = "", db=None,
           raz_za_hodin: int = 6) -> None:
    """
    Pošle poplach do Telegramu. Nikdy nevyhodí výnimku - poplach o chybe
    nesmie byť sám ďalšou chybou.

    `kod` je druh poruchy (kľúč do RADY). Rovnaký druh sa neposiela
    častejšie než raz za `raz_za_hodin` hodín.
    """
    try:
        teraz = datetime.now(timezone.utc)
        if kod in _OHLASENE and teraz - _OHLASENE[kod] < timedelta(hours=raz_za_hodin):
            return
        _OHLASENE[kod] = teraz

        import telegram_bot
        rada = RADY.get(kod, "")
        riadky = ["⚠️ <b>Henkukaj - niečo sa pokazilo</b>"]
        if rada:
            riadky.append(rada)
        if podrobnosti:
            riadky.append(f"<code>{telegram_bot._escape(podrobnosti[:400])}</code>")
        riadky.append("Opravovať nič nemusíš hneď - stránka beží ďalej.")
        telegram_bot.send_text("\n\n".join(riadky))
        logger.warning("Poplach odoslaný: %s", kod)
    except Exception as e:
        logger.warning("Poplach sa nepodarilo odoslať: %s", e)


def chyba(kod: str, vynimka: object, db=None) -> None:
    """Ako `nahlas`, ale vyčerpanú kvótu ohlási ako kvótu."""
    nahlas("kvota" if je_kvota(vynimka) else kod, str(vynimka), db)
