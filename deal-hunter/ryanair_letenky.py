"""
Ranné hľadanie lacných leteniek Ryanair z Bratislavy.

Používa verejné rozhranie, na ktorom stojí vlastný vyhľadávač lacných
letov na ryanair.com (services-api.ryanair.com/farfnd). Nie je to
obchádzanie ochrany - je to ten istý zdroj, z ktorého číta ich stránka,
keď na nej klikneš na "Fare Finder".

KRITÉRIÁ
  jednosmerne  do 30 € kamkoľvek
  spiatočne    do 50 € spolu, pobyt 1 až 14 dní

ČO SI PAMÄTÁME
Bez pamäte by ti každé ráno prišla tá istá Barcelona za 14,99. Preto si
odkladáme, čo sme už poslali, a hlásime len nové spojenie alebo také,
ktoré odvtedy zlacnelo. Stačí na to súbor vedľa skriptu - je to osobné
upozornenie, nie obsah stránky, do Firestore nepatrí.

Spúšťa to plánovaná úloha "HenKukaj - letenky" cez letenky.cmd.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta

import requests

logger = logging.getLogger("letenky")

API = "https://services-api.ryanair.com/farfnd/v4"
LETISKO = os.environ.get("RYANAIR_ORIGIN", "BTS")

MAX_JEDNOSMERNE = float(os.environ.get("RYANAIR_MAX_ONEWAY", 30))
MAX_SPIATOCNE = float(os.environ.get("RYANAIR_MAX_RETURN", 50))
POBYT_OD = int(os.environ.get("RYANAIR_STAY_FROM", 1))
POBYT_DO = int(os.environ.get("RYANAIR_STAY_TO", 14))

# Ako ďaleko dopredu sa pozeráme.
DNI_DOPREDU = int(os.environ.get("RYANAIR_HORIZON_DAYS", 120))

# Strop, ktorý si určuje Ryanair: spiatočné rozhranie odmietne limit
# väčší než 20 chybou InvalidLimit. Jednosmerné znesie 200.
LIMIT_SPIATOCNE = 20
LIMIT_JEDNOSMERNE = 200

PAMAT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "letenky-poslane.json")

HLAVICKY = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-GB,en;q=0.9",
}


# ── volanie Ryanairu ──────────────────────────────────────────────────

def _ziskaj(cesta: str, parametre: dict) -> dict:
    r = requests.get(f"{API}/{cesta}", params=parametre, headers=HLAVICKY, timeout=40)
    r.raise_for_status()
    return r.json()


def jednosmerne() -> list[dict]:
    dnes = date.today()
    data = _ziskaj("oneWayFares", {
        "departureAirportIataCode": LETISKO,
        "outboundDepartureDateFrom": dnes.isoformat(),
        "outboundDepartureDateTo": (dnes + timedelta(days=DNI_DOPREDU)).isoformat(),
        "priceValueTo": MAX_JEDNOSMERNE,
        "currency": "EUR",
        "limit": LIMIT_JEDNOSMERNE,
        "offset": 0,
    })
    vysledok = []
    for f in data.get("fares", []):
        o = f.get("outbound") or {}
        cena = (o.get("price") or {}).get("value")
        if cena is None or float(cena) > MAX_JEDNOSMERNE:
            continue
        letisko = o.get("arrivalAirport") or {}
        vysledok.append({
            "druh": "one",
            "kam": letisko.get("iataCode", "?"),
            "mesto": letisko.get("name", ""),
            "krajina": (letisko.get("countryName") or ""),
            "odlet": (o.get("departureDate") or "")[:16],
            "cena": round(float(cena), 2),
            "dni": None,
        })
    return vysledok


def spiatocne() -> list[dict]:
    dnes = date.today()
    do = dnes + timedelta(days=DNI_DOPREDU)
    data = _ziskaj("roundTripFares", {
        "departureAirportIataCode": LETISKO,
        "outboundDepartureDateFrom": dnes.isoformat(),
        "outboundDepartureDateTo": do.isoformat(),
        "inboundDepartureDateFrom": dnes.isoformat(),
        "inboundDepartureDateTo": (do + timedelta(days=POBYT_DO)).isoformat(),
        "durationFrom": POBYT_OD,
        "durationTo": POBYT_DO,
        "priceValueTo": MAX_SPIATOCNE,
        "currency": "EUR",
        "limit": LIMIT_SPIATOCNE,
        "offset": 0,
    })
    vysledok = []
    for f in data.get("fares", []):
        o = f.get("outbound") or {}
        i = f.get("inbound") or {}
        co = (o.get("price") or {}).get("value")
        ci = (i.get("price") or {}).get("value")
        if co is None or ci is None:
            continue
        spolu = round(float(co) + float(ci), 2)
        if spolu > MAX_SPIATOCNE:
            continue
        try:
            dni = (date.fromisoformat((i.get("departureDate") or "")[:10])
                   - date.fromisoformat((o.get("departureDate") or "")[:10])).days
        except ValueError:
            dni = None
        # Ryanair už filtruje podľa durationFrom/To, ale keby parametre
        # ignoroval, nechceme ti poslať trojtýždňový pobyt.
        if dni is not None and not (POBYT_OD <= dni <= POBYT_DO):
            continue
        letisko = o.get("arrivalAirport") or {}
        vysledok.append({
            "druh": "return",
            "kam": letisko.get("iataCode", "?"),
            "mesto": letisko.get("name", ""),
            "krajina": (letisko.get("countryName") or ""),
            "odlet": (o.get("departureDate") or "")[:16],
            "navrat": (i.get("departureDate") or "")[:16],
            "cena": spolu,
            "dni": dni,
        })
    return vysledok


# ── pamäť už poslaného ────────────────────────────────────────────────

def _kluc(let: dict) -> str:
    return f"{let['druh']}|{let['kam']}|{let['odlet'][:10]}|{let.get('navrat', '')[:10]}"


def _nacitaj_pamat() -> dict:
    try:
        with open(PAMAT, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        # Poškodený súbor nesmie zhodiť ranné hlásenie. Radšej pošleme
        # aj to, čo sme už poslali, než nič.
        logger.warning("Pamäť poslaných leteniek sa nedá prečítať (%s) - začínam odznova", e)
        return {}


def _uloz_pamat(pamat: dict) -> None:
    # Staré záznamy zahadzujeme, inak by súbor rástol donekonečna a po
    # čase by ti zamlčal aj ponuku, ktorá sa vrátila po mesiaci.
    hranica = (date.today() - timedelta(days=7)).isoformat()
    ocistena = {k: v for k, v in pamat.items() if v.get("kedy", "") >= hranica}
    with open(PAMAT, "w", encoding="utf-8") as f:
        json.dump(ocistena, f, ensure_ascii=False, indent=1)


def novinky(lety: list[dict], pamat: dict) -> list[dict]:
    """Nechá len to, čo sme ešte neposlali alebo čo odvtedy zlacnelo."""
    von = []
    for let in lety:
        stare = pamat.get(_kluc(let))
        if stare and let["cena"] >= float(stare.get("cena", 0)):
            continue
        if stare:
            let["zlacnelo_z"] = float(stare["cena"])
        von.append(let)
    return von


# ── správa do Telegramu ───────────────────────────────────────────────

def _odkaz(let: dict) -> str:
    """Odkaz priamo na dané spojenie na ryanair.com."""
    den = let["odlet"][:10]
    zaklad = "https://www.ryanair.com/sk/sk/trip/flights/select?adults=1"
    if let["druh"] == "return":
        spat = let.get("navrat", "")[:10]
        return (f"{zaklad}&dateOut={den}&dateIn={spat}&isReturn=true"
                f"&originIata={LETISKO}&destinationIata={let['kam']}")
    return (f"{zaklad}&dateOut={den}&isReturn=false"
            f"&originIata={LETISKO}&destinationIata={let['kam']}")


def _dni_slovom(n) -> str:
    """1 deň, 2-4 dni, 5 a viac dní."""
    if n is None:
        return ""
    if n == 1:
        return "1 deň"
    if 2 <= n <= 4:
        return f"{n} dni"
    return f"{n} dní"


def _riadok(let: dict) -> str:
    import telegram_bot
    e = telegram_bot._escape
    kam = f"{e(let['mesto'])} ({e(let['kam'])})"
    kedy = let["odlet"].replace("T", " ")
    if let["druh"] == "return":
        detail = (f"{kedy} - {let.get('navrat', '').replace('T', ' ')}"
                  f" · {_dni_slovom(let['dni'])}")
    else:
        detail = f"{kedy} · jednosmerne"
    cena = f"<b>{let['cena']:.2f} €</b>"
    if "zlacnelo_z" in let:
        cena += f" <i>(bolo {let['zlacnelo_z']:.2f})</i>"
    return f'• <a href="{_odkaz(let)}">{kam}</a> - {cena}\n   <i>{e(detail)}</i>'


def zostav_spravu(nove_one: list[dict], nove_ret: list[dict]) -> str:
    casti = [f"✈️ <b>Lacné letenky z {LETISKO}</b> - {date.today().strftime('%d.%m.%Y')}"]
    if nove_ret:
        casti.append(f"\n<b>Spiatočné do {MAX_SPIATOCNE:.0f} € ({POBYT_OD}-{POBYT_DO} dní)</b>")
        casti += [_riadok(x) for x in nove_ret[:12]]
    if nove_one:
        casti.append(f"\n<b>Jednosmerné do {MAX_JEDNOSMERNE:.0f} €</b>")
        casti += [_riadok(x) for x in nove_one[:15]]
    sprava = "\n".join(casti)
    # Telegram odmietne správu nad 4096 znakov.
    if len(sprava) > 4000:
        sprava = sprava[:3950] + "\n\n<i>… zvyšok vynechaný, bolo toho priveľa.</i>"
    return sprava


def posli(nove_one: list[dict], nove_ret: list[dict]) -> bool:
    import telegram_bot
    if not telegram_bot.is_configured():
        logger.error("Telegram nie je nastavený - správu neposielam.")
        return False
    return telegram_bot._call("sendMessage", {
        "chat_id": telegram_bot.config.TELEGRAM_CHAT_ID,
        "text": zostav_spravu(nove_one, nove_ret),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }) is not None


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("=== Letenky z %s - začiatok ===", LETISKO)

    try:
        one = jednosmerne()
    except Exception as e:
        logger.error("Jednosmerné sa nepodarilo načítať: %s", e)
        one = []
    try:
        ret = spiatocne()
    except Exception as e:
        logger.error("Spiatočné sa nepodarilo načítať: %s", e)
        ret = []

    logger.info("Nájdené: %d jednosmerných, %d spiatočných", len(one), len(ret))
    if not one and not ret:
        # Obe naraz prázdne neznamená, že nič nie je v akcii - skôr že sa
        # zmenilo rozhranie. Nech to skončí nenulovým kódom a plánovaná
        # úloha to vie ohlásiť.
        logger.error("Ryanair nevrátil nič - buď je rozhranie mimo, alebo zmenili parametre.")
        return 1

    pamat = _nacitaj_pamat()
    nove_one = sorted(novinky(one, pamat), key=lambda x: x["cena"])
    nove_ret = sorted(novinky(ret, pamat), key=lambda x: x["cena"])
    logger.info("Z toho nových alebo zlacnených: %d + %d", len(nove_one), len(nove_ret))

    if not nove_one and not nove_ret:
        logger.info("Nič nové oproti včerajšku - správu neposielam.")
        return 0

    if not posli(nove_one, nove_ret):
        logger.error("Odoslanie do Telegramu zlyhalo - pamäť nechávam nedotknutú.")
        return 1

    dnes = date.today().isoformat()
    for let in nove_one + nove_ret:
        pamat[_kluc(let)] = {"cena": let["cena"], "kedy": dnes}
    _uloz_pamat(pamat)

    logger.info("=== Hotovo. Poslaných %d ponúk. ===", len(nove_one) + len(nove_ret))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
