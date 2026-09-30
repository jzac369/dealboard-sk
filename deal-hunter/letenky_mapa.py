"""
Dáta pre letenkovú mapu na stránke (záložka Letenky).

ČO TO ROBÍ
Pre každú trasu z Bratislavy, Viedne a Košíc stiahne najlacnejšiu cenu
na každý deň - tam aj späť - na zhruba štyri mesiace dopredu. Výsledok
je jeden statický súbor assets/letenky/ceny.json, ktorý si stránka
načíta a kombinácie "odlet + návrat" si podľa filtrov návštevníka
(cena, dĺžka pobytu, víkend...) poskladá sama v prehliadači.

Prečo po dňoch a nie hotové spiatočné ponuky: spiatočné rozhranie
vráti jednu najlacnejšiu kombináciu na destináciu pre jednu dĺžku
pobytu. Filtre na stránke by potom museli mať vopred pripravenú
odpoveď pre každú kombináciu. Z cien po dňoch sa dá odpovedať na
akúkoľvek otázku a súbor je aj tak malý (~100 kB, zbalený oveľa menej).

ZDROJE
Ryanair - verejné rozhranie, z ktorého číta ich vlastný Fare Finder
(rovnaké ako v ryanair_letenky.py).

Wizz Air má rozhranie chránené proti robotom; obchádzať to nebudeme.
Ostatné nízkonákladovky (Wizz, easyJet, Eurowings...) sa dajú doplniť
cez dátové API Travelpayouts - stačí jeho token v tajomstve
TRAVELPAYOUTS_TOKEN. Kým nie je, zbiera sa len Ryanair.

Súbor nič nezapisuje do Firestore, takže nestojí ani jedno čítanie.

Spustenie:  python letenky_mapa.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("letenky-mapa")

VYSTUP = os.path.join(os.path.dirname(__file__), "..", "assets", "letenky", "ceny.json")

ODKIAL = {
    "BTS": {"n": "Bratislava", "lat": 48.1702, "lon": 17.2127},
    "VIE": {"n": "Viedeň", "lat": 48.1103, "lon": 16.5697},
    "KSC": {"n": "Košice", "lat": 48.6631, "lon": 21.2411},
}

DNI_DOPREDU = int(os.environ.get("LETENKY_DNI", 120))
VLAKNA = 4          # zdvorilá paralelnosť; 1100 požiadaviek za ~3 minúty

RYANAIR_TRASY = "https://www.ryanair.com/api/views/locate/searchWidget/routes/en/airport/{}"
RYANAIR_DNI = "https://services-api.ryanair.com/farfnd/v4/oneWayFares/{}/{}/cheapestPerDay"

HLAVICKY = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-GB,en;q=0.9",
}

# Slovenské názvy a druh pobytu. "more" = chodí sa k moru (dlhší pobyt),
# "mesto" = mestský výlet. Ryanair dáva len anglické názvy; čo tu
# chýba, ukáže sa po anglicky a skript to pripomenie vo výpise.
DESTINACIE = {
    # mestá
    "AMM": ("Ammán", "mesto"), "ARN": ("Štokholm", "mesto"), "ATH": ("Atény", "mesto"),
    "BCN": ("Barcelona", "mesto"), "BGY": ("Miláno (Bergamo)", "mesto"),
    "BLQ": ("Bologna", "mesto"), "BNX": ("Banja Luka", "mesto"),
    "BVA": ("Paríž (Beauvais)", "mesto"), "CGN": ("Kolín nad Rýnom", "mesto"),
    "CIA": ("Rím (Ciampino)", "mesto"), "CPH": ("Kodaň", "mesto"),
    "CRL": ("Brusel (Charleroi)", "mesto"), "DUB": ("Dublin", "mesto"),
    "EDI": ("Edinburgh", "mesto"), "EIN": ("Eindhoven", "mesto"),
    "FCO": ("Rím (Fiumicino)", "mesto"), "GDN": ("Gdansk", "mesto"),
    "HEL": ("Helsinki", "mesto"), "INI": ("Niš", "mesto"), "KRK": ("Krakov", "mesto"),
    "LBA": ("Leeds", "mesto"), "LIS": ("Lisabon", "mesto"), "LPL": ("Liverpool", "mesto"),
    "MAD": ("Madrid", "mesto"), "MAN": ("Manchester", "mesto"),
    "MRS": ("Marseille", "mesto"), "MXP": ("Miláno (Malpensa)", "mesto"),
    "NAP": ("Neapol", "mesto"), "OPO": ("Porto", "mesto"),
    "OTP": ("Bukurešť", "mesto"), "PRG": ("Praha", "mesto"), "PSA": ("Pisa", "mesto"),
    "SKG": ("Solún", "mesto"), "SOF": ("Sofia", "mesto"), "STN": ("Londýn (Stansted)", "mesto"),
    "TIA": ("Tirana", "mesto"), "TRN": ("Turín", "mesto"),
    "TSF": ("Benátky (Treviso)", "mesto"), "VCE": ("Benátky", "mesto"),
    "VLC": ("Valencia", "mesto"), "VNO": ("Vilnius", "mesto"),
    "WAW": ("Varšava (Chopin)", "mesto"), "WMI": ("Varšava (Modlin)", "mesto"),
    # more
    "ACE": ("Lanzarote", "more"), "AGA": ("Agadir", "more"), "AGP": ("Málaga", "more"),
    "AHO": ("Alghero", "more"), "ALC": ("Alicante", "more"), "BOJ": ("Burgas", "more"),
    "BRI": ("Bari", "more"), "CAG": ("Cagliari", "more"), "CFU": ("Korfu", "more"),
    "CHQ": ("Chania (Kréta)", "more"), "CTA": ("Catania", "more"),
    "DBV": ("Dubrovník", "more"), "DLM": ("Dalaman", "more"), "EFL": ("Kefalónia", "more"),
    "FAO": ("Faro", "more"), "FUE": ("Fuerteventura", "more"),
    "HER": ("Heraklion (Kréta)", "more"), "IBZ": ("Ibiza", "more"),
    "JMK": ("Mykonos", "more"), "JSI": ("Skiathos", "more"), "JTR": ("Santorini", "more"),
    "KGS": ("Kos", "more"), "KLX": ("Kalamata", "more"), "LCA": ("Larnaka", "more"),
    "LPA": ("Gran Canaria", "more"), "MLA": ("Malta", "more"), "OLB": ("Olbia", "more"),
    "PFO": ("Paphos", "more"), "PMI": ("Mallorca", "more"), "PMO": ("Palermo", "more"),
    "PUY": ("Pula", "more"), "PVK": ("Preveza", "more"),
    "QSR": ("Salerno (Amalfi)", "more"), "RHO": ("Rodos", "more"), "RMI": ("Rimini", "more"),
    "SUF": ("Lamezia", "more"), "TFS": ("Tenerife", "more"), "TPS": ("Trapani", "more"),
    "ZAD": ("Zadar", "more"), "ZTH": ("Zakynthos", "more"),
}

KRAJINY = {
    "es": "Španielsko", "it": "Taliansko", "gr": "Grécko", "gb": "Veľká Británia",
    "ie": "Írsko", "fr": "Francúzsko", "de": "Nemecko", "be": "Belgicko",
    "nl": "Holandsko", "pl": "Poľsko", "pt": "Portugalsko", "hr": "Chorvátsko",
    "mt": "Malta", "cy": "Cyprus", "bg": "Bulharsko", "ro": "Rumunsko",
    "al": "Albánsko", "ma": "Maroko", "tr": "Turecko", "dk": "Dánsko",
    "se": "Švédsko", "fi": "Fínsko", "lt": "Litva", "cz": "Česko",
    "rs": "Srbsko", "ba": "Bosna a Hercegovina", "jo": "Jordánsko",
    "at": "Rakúsko", "sk": "Slovensko", "hu": "Maďarsko", "no": "Nórsko",
    "lv": "Lotyšsko", "ee": "Estónsko", "me": "Čierna Hora", "mk": "Severné Macedónsko",
}

_session = requests.Session()
_session.headers.update(HLAVICKY)


def _json(url: str, params: dict | None = None, pokusy: int = 3):
    for i in range(pokusy):
        try:
            r = _session.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 + 3 * i)
                continue
            return None
        except (requests.RequestException, ValueError):
            time.sleep(2 + 3 * i)
    return None


def _mesiace(od: date, dni: int) -> list[str]:
    out, d = [], od.replace(day=1)
    koniec = od + timedelta(days=dni)
    while d <= koniec:
        out.append(d.isoformat())
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def ceny_po_dnoch(odkial: str, kam: str, zaciatok: date, dni: int) -> list[float]:
    """Najlacnejšia cena na každý deň od `zaciatok`; 0 = v ten deň neletí."""
    ceny = [0.0] * dni
    for mesiac in _mesiace(zaciatok, dni):
        data = _json(RYANAIR_DNI.format(odkial, kam),
                     {"outboundMonthOfDate": mesiac, "currency": "EUR"})
        for f in ((data or {}).get("outbound") or {}).get("fares") or []:
            if f.get("unavailable") or f.get("soldOut") or not f.get("price"):
                continue
            try:
                i = (date.fromisoformat(f["day"]) - zaciatok).days
            except (KeyError, ValueError):
                continue
            if 0 <= i < dni:
                ceny[i] = round(float(f["price"]["value"]), 2)
    return ceny


def ryanair(zaciatok: date, dni: int) -> tuple[dict, list[dict]]:
    letiska: dict[str, dict] = {}
    ulohy = []
    for odkial in ODKIAL:
        trasy = _json(RYANAIR_TRASY.format(odkial)) or []
        logger.info("Ryanair %s: %d trás", odkial, len(trasy))
        for t in trasy:
            a = t.get("arrivalAirport") or {}
            kod = a.get("code")
            if not kod or kod in ODKIAL:
                continue
            sk = DESTINACIE.get(kod)
            if not sk:
                logger.warning("  %s (%s) nemá slovenský názov - doplň do DESTINACIE", kod, a.get("name"))
            k = (a.get("country") or {}).get("code", "")
            letiska[kod] = {
                "n": sk[0] if sk else a.get("name", kod),
                "k": KRAJINY.get(k, (a.get("country") or {}).get("name", "")),
                "lat": round(a["coordinates"]["latitude"], 3),
                "lon": round(a["coordinates"]["longitude"], 3),
                "d": sk[1] if sk else "mesto",
            }
            ulohy.append((odkial, kod))

    def jedna(par):
        odkial, kam = par
        return {"a": "FR", "z": odkial, "do": kam,
                "t": ceny_po_dnoch(odkial, kam, zaciatok, dni),
                "s": ceny_po_dnoch(kam, odkial, zaciatok, dni)}

    with ThreadPoolExecutor(VLAKNA) as ex:
        trasy = list(ex.map(jedna, ulohy))
    # Trasa, na ktorej v celom období neletí nič, je na mape zbytočná.
    trasy = [t for t in trasy if any(t["t"]) and any(t["s"])]
    return letiska, trasy


def main() -> int:
    zaciatok = date.today() + timedelta(days=1)   # dnešné lety už neodletia
    letiska, trasy = ryanair(zaciatok, DNI_DOPREDU)

    if len(trasy) < 20:
        # Radšej ponechať včerajšie dáta než mapu vyprázdniť kvôli
        # dočasnému výpadku rozhrania.
        logger.error("Len %d trás - súbor neprepisujem.", len(trasy))
        return 1

    # Fotky destinácií sú z Wikimedia Commons a väčšina licencií
    # vyžaduje uviesť autora - údaje idú rovno sem, nech stránka nemusí
    # sťahovať ďalší súbor.
    priecinok = os.path.join(os.path.dirname(__file__), "..", "assets", "destinacie")
    try:
        with open(os.path.join(priecinok, "fotky.json"), encoding="utf-8") as f:
            popisy = json.load(f)
    except (OSError, ValueError):
        popisy = {}
    for kod, l in letiska.items():
        p = popisy.get(kod)
        if p and os.path.exists(os.path.join(priecinok, f"{kod}.jpg")):
            l["f"] = {"a": p.get("autor", ""), "l": p.get("licencia", ""), "z": p.get("zdroj", "")}

    vystup = {
        "vytvorene": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "zaciatok": zaciatok.isoformat(),
        "dni": DNI_DOPREDU,
        "odkial": ODKIAL,
        "letiska": dict(sorted(letiska.items())),
        "spolocnosti": {"FR": "Ryanair"},
        "trasy": trasy,
    }
    os.makedirs(os.path.dirname(VYSTUP), exist_ok=True)
    with open(VYSTUP, "w", encoding="utf-8") as f:
        json.dump(vystup, f, ensure_ascii=False, separators=(",", ":"))
    velkost = os.path.getsize(VYSTUP) // 1024
    logger.info("Zapísané: %d trás, %d destinácií, %d kB", len(trasy), len(letiska), velkost)
    return 0


if __name__ == "__main__":
    sys.exit(main())
