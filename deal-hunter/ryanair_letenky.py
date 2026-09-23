"""
Ranné hľadanie lacných leteniek Ryanair z Bratislavy.

Používa verejné rozhranie, na ktorom stojí vlastný vyhľadávač lacných
letov na ryanair.com (services-api.ryanair.com/farfnd). Nie je to
obchádzanie ochrany - je to ten istý zdroj, z ktorého číta ich stránka,
keď na nej klikneš na "Fare Finder".

AKO DLHO SA NIEKDE ZDRŽÍ
Dĺžka pobytu nie je jedno číslo pre všetko. Na Barcelonu, Rím či do
Gdanska sa chodí na predĺžený víkend, k moru na týždeň. Preto sú
destinácie rozdelené na dve skupiny a pre každú sa pýtame inú dĺžku
pobytu - inak by vyhľadávanie ponúkalo dvojdňovú Mallorcu a
desaťdňový Brusel.

ODKIAĽ BERIEME "PÔVODNÚ CENU"
Feed s ponukami udáva len tú najlacnejšiu cenu a nič, s čím by sa dala
porovnať. Preto si pre každú trasu stiahneme ceny po dňoch v danom
mesiaci (cheapestPerDay) a ako bežnú cenu berieme medián. Je to údaj z
toho istého zdroja a dá sa obhájiť: "takto to na tejto trase vychádza
bežne, dnes je to za toľkoto".

ČO SA S NÁJDENÝM STANE
Tri najlacnejšie ponuky sa zapíšu ako návrhy dealov (status pending,
kategória Cestovanie) a pošlú sa do Telegramu s tlačidlami Schváliť a
Zamietnuť - rovnako ako návrhy od agenta. Schválené sa objavia na
stránke, zamietnuté nikde.

Spúšťa to plánovaná úloha "HenKukaj - letenky" cez letenky.cmd.
"""

from __future__ import annotations

import json
import logging
import os
import statistics
from datetime import date, timedelta

import requests

logger = logging.getLogger("letenky")

API = "https://services-api.ryanair.com/farfnd/v4"
LETISKO = os.environ.get("RYANAIR_ORIGIN", "BTS")

MAX_SPIATOCNE = float(os.environ.get("RYANAIR_MAX_RETURN", 50))
KOLKO_PONUK = int(os.environ.get("RYANAIR_DAILY_PICKS", 3))

# Ako ďaleko dopredu sa pozeráme.
DNI_DOPREDU = int(os.environ.get("RYANAIR_HORIZON_DAYS", 120))

# Strop, ktorý si určuje Ryanair: spiatočné rozhranie odmietne limit
# väčší než 20 chybou InvalidLimit.
LIMIT_SPIATOCNE = 20

KATEGORIA = "Cestovanie"
OBCHOD = "Ryanair"

HLAVICKY = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-GB,en;q=0.9",
}


# ── rozdelenie destinácií ─────────────────────────────────────────────
# Zoznam vychádza zo skutočných destinácií, ktoré Ryanair z Bratislavy
# lieta (overené 23. 9. 2026). Keď pribudne nová, spadne do MESTO -
# predĺžený víkend je bezpečnejší odhad než týždeň pri mori.
#
# Delenie je podľa toho, na čo tam ľudia chodia, nie podľa zemepisu.
# Barcelona, Rím aj Atény sú pri mori, ale chodí sa do nich za mestom -
# preto sú medzi mestami, presne ako si ich zaradil ty.

MESTO = {
    "ATH": "Atény", "BCN": "Barcelona", "CIA": "Rím", "CRL": "Brusel",
    "DUB": "Dublin", "EDI": "Edinburgh", "EIN": "Eindhoven", "GDN": "Gdansk",
    "LBA": "Leeds", "MAN": "Manchester", "MXP": "Miláno", "NAP": "Neapol",
    "PSA": "Pisa", "SKG": "Solún", "STN": "Londýn", "TIA": "Tirana",
    "TRN": "Turín", "WMI": "Varšava",
}

MORE = {
    "ACE": "Lanzarote", "AGA": "Agadir", "AGP": "Málaga", "AHO": "Alghero",
    "ALC": "Alicante", "BOJ": "Burgas", "BRI": "Bari", "CFU": "Korfu",
    "DLM": "Dalaman", "JSI": "Skiathos", "MLA": "Malta", "PFO": "Paphos",
    "PMI": "Mallorca", "PMO": "Palermo", "SUF": "Lamezia", "TPS": "Trapani",
    "ZAD": "Zadar",
}

# (od, do) dní pobytu pre každú skupinu.
POBYT_MESTO = (int(os.environ.get("RYANAIR_CITY_FROM", 2)),
               int(os.environ.get("RYANAIR_CITY_TO", 4)))
POBYT_MORE = (int(os.environ.get("RYANAIR_SEA_FROM", 4)),
              int(os.environ.get("RYANAIR_SEA_TO", 10)))


def skupina(iata: str) -> str:
    if iata in MORE:
        return "more"
    if iata not in MESTO:
        # Nová destinácia. Spadne medzi mestá (predĺžený víkend je
        # bezpečnejší odhad než týždeň), ale nech to nezostane ticho -
        # Alghero takto raz skončilo medzi mestami, hoci je to Sardínia.
        logger.warning("Neznáma destinácia %s — zaraďujem medzi mestá. "
                       "Ak je prímorská, dopln ju do MORE.", iata)
    return "mesto"


def nazov_skupiny(druh: str) -> str:
    return "pri mori" if druh == "more" else "mestský pobyt"


# ── volanie Ryanairu ──────────────────────────────────────────────────

def _ziskaj(cesta: str, parametre: dict) -> dict:
    r = requests.get(f"{API}/{cesta}", params=parametre, headers=HLAVICKY, timeout=40)
    r.raise_for_status()
    return r.json()


def spiatocne_pre_pobyt(pobyt_od: int, pobyt_do: int) -> list[dict]:
    """Spiatočné lety s danou dĺžkou pobytu, lacnejšie než strop."""
    dnes = date.today()
    do = dnes + timedelta(days=DNI_DOPREDU)
    data = _ziskaj("roundTripFares", {
        "departureAirportIataCode": LETISKO,
        "outboundDepartureDateFrom": dnes.isoformat(),
        "outboundDepartureDateTo": do.isoformat(),
        "inboundDepartureDateFrom": dnes.isoformat(),
        "inboundDepartureDateTo": (do + timedelta(days=pobyt_do)).isoformat(),
        "durationFrom": pobyt_od,
        "durationTo": pobyt_do,
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

        odlet = (o.get("departureDate") or "")[:16]
        navrat = (i.get("departureDate") or "")[:16]
        try:
            dni = (date.fromisoformat(navrat[:10]) - date.fromisoformat(odlet[:10])).days
        except ValueError:
            continue
        if not (pobyt_od <= dni <= pobyt_do):
            continue

        letisko = o.get("arrivalAirport") or {}
        vysledok.append({
            "kam": letisko.get("iataCode", "?"),
            "letisko": letisko.get("name", ""),
            "krajina": letisko.get("countryName") or "",
            "odlet": odlet,
            "navrat": navrat,
            "dni": dni,
            "cena": spolu,
            "cena_tam": round(float(co), 2),
            "cena_spat": round(float(ci), 2),
        })
    return vysledok


def _median_trasy(odkial: str, kam: str, den: str) -> float | None:
    """
    Bežná cena jedného smeru na trase v mesiaci daného dátumu.

    Medián, nie priemer: jeden let za 148 € by priemer vytiahol tak, že
    by každá ponuka vyzerala ako zľava storočia.
    """
    mesiac = f"{den[:7]}-01"
    try:
        data = _ziskaj(f"oneWayFares/{odkial}/{kam}/cheapestPerDay",
                       {"outboundMonthOfDate": mesiac, "currency": "EUR"})
    except Exception as e:
        logger.debug("Ceny po dňoch pre %s-%s (%s) sa nepodarili: %s", odkial, kam, mesiac, e)
        return None

    ceny = [f["price"]["value"] for f in (data.get("outbound") or {}).get("fares", [])
            if f.get("price") and f["price"].get("value")]
    if len(ceny) < 5:
        # Z troch dní sa bežná cena určiť nedá.
        return None
    return round(float(statistics.median(ceny)), 2)


def dopln_beznu_cenu(let: dict) -> dict:
    """Pripočíta bežnú cenu trasy tam aj späť. Keď ju nezistíme, nechá None."""
    tam = _median_trasy(LETISKO, let["kam"], let["odlet"])
    spat = _median_trasy(let["kam"], LETISKO, let["navrat"])
    if tam is None or spat is None:
        let["bezna"] = None
        return let
    bezna = round(tam + spat, 2)
    # Bežná cena nižšia než dnešná ponuka nie je bežná cena. Vtedy radšej
    # nepíšeme nič, než aby na stránke svietila záporná zľava.
    let["bezna"] = bezna if bezna > let["cena"] else None
    return let


# ── zostavenie dealu ──────────────────────────────────────────────────

def _odkaz(let: dict) -> str:
    return ("https://www.ryanair.com/sk/sk/trip/flights/select?adults=1"
            f"&dateOut={let['odlet'][:10]}&dateIn={let['navrat'][:10]}&isReturn=true"
            f"&originIata={LETISKO}&destinationIata={let['kam']}")


def _mesto(let: dict) -> str:
    return MORE.get(let["kam"]) or MESTO.get(let["kam"]) or let["letisko"] or let["kam"]


def _dni_slovom(n: int) -> str:
    if n == 1:
        return "1 deň"
    if 2 <= n <= 4:
        return f"{n} dni"
    return f"{n} dní"


def _sk_datum(iso: str) -> str:
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return iso[:10]
    return f"{d.day}.{d.month}.{d.year}"


MESIACE = ("", "januári", "februári", "marci", "apríli", "máji", "júni",
           "júli", "auguste", "septembri", "októbri", "novembri", "decembri")


def _mesiac_slovom(iso: str) -> str:
    """V titulku je mesiac užitočnejší než presný dátum - povie, na kedy
    ponuka je, a nezaberie pol riadka."""
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return ""
    return f"{MESIACE[d.month]} {d.year}"


def _cena_sk(hodnota: float) -> str:
    """Slovenský zápis s desatinnou čiarkou."""
    return f"{hodnota:.2f}".replace(".", ",")


_FOTKY_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "assets", "destinacie", "fotky.json")
_FOTKY: dict | None = None


def _fotka_popis(iata: str) -> dict | None:
    """
    Autor a licencia fotky. Väčšina obrázkov z Wikimedia Commons vyžaduje
    uvedenie autora, takže to musí ísť spolu s dealom až na stránku.
    """
    global _FOTKY
    if _FOTKY is None:
        try:
            with open(_FOTKY_JSON, encoding="utf-8") as f:
                _FOTKY = json.load(f)
        except Exception as e:
            logger.warning("Popisy fotiek sa nedajú načítať (%s)", e)
            _FOTKY = {}
    zaznam = _FOTKY.get(iata)
    if not zaznam:
        return None
    return {
        "autor": zaznam.get("autor", "neuvedený"),
        "licencia": zaznam.get("licencia", ""),
        "zdroj": zaznam.get("zdroj", ""),
    }


def na_deal(let: dict) -> dict:
    mesto = _mesto(let)
    dni = _dni_slovom(let["dni"])
    druh = nazov_skupiny(skupina(let["kam"]))

    popis = (
        f"Spiatočná letenka z Bratislavy do mesta {mesto} "
        f"({let['krajina']}). Odlet {_sk_datum(let['odlet'])}, "
        f"návrat {_sk_datum(let['navrat'])} — {dni} na mieste. "
        f"Cena je za oba smery ({let['cena_tam']:.2f} € tam, "
        f"{let['cena_spat']:.2f} € späť), batožina podľa podmienok Ryanairu."
    )
    if let.get("bezna"):
        popis += (f" Bežne táto trasa v danom mesiaci vychádza okolo "
                  f"{let['bezna']:.2f} €.")

    zlava = 0
    if let.get("bezna") and let["bezna"] > let["cena"]:
        zlava = round((1 - let["cena"] / let["bezna"]) * 100)

    deal = {
        # Titulok hovorí kam, na ako dlho, na kedy a za koľko. Mesiac je
        # v ňom zámerne: bez neho sa ponuky na ten istý smer nedajú
        # rozoznať a nevidno, či je to o dva týždne alebo o štyri mesiace.
        "title": (f"{mesto} na {dni} v {_mesiac_slovom(let['odlet'])} "
                  f"— spiatočne za {_cena_sk(let['cena'])} €"),
        "store": OBCHOD,
        "category": KATEGORIA,
        "dealPrice": let["cena"],
        "originalPrice": let.get("bezna"),
        "discountPercent": zlava,
        "currency": "€",
        "url": _odkaz(let),
        # Fotku destinácie máme stiahnutú vo vlastných súboroch (pozri
        # fetch_destination_photos.py). Absolútna adresa zámerne: tú istú
        # hodnotu posiela Telegram do sendPhoto a relatívna cesta by mu
        # nič nepovedala.
        "imageUrl": f"https://henkukaj.sk/assets/destinacie/{let['kam']}.webp",
        "photoCredit": _fotka_popis(let["kam"]),
        "description": popis,
        "status": "pending",
        "expired": False,
        "autoGenerated": True,
        "sourceSite": "ryanair.com",
        # Platnosť ponuky končí odletom - potom je bezpredmetná.
        "validUntil": _sk_datum(let["odlet"]),
        "validUntilISO": let["odlet"][:10],
        "dedupeKey": f"ryanair|{let['kam']}|{let['odlet'][:10]}|{let['navrat'][:10]}",
    }
    return deal


# ── hlavný beh ────────────────────────────────────────────────────────

def najdi() -> list[dict]:
    """Vráti lety oboch skupín, každú s jej vlastnou dĺžkou pobytu."""
    vsetky: list[dict] = []

    for druh, (od, do) in (("mesto", POBYT_MESTO), ("more", POBYT_MORE)):
        try:
            lety = spiatocne_pre_pobyt(od, do)
        except Exception as e:
            logger.error("Lety pre %s (%d-%d dní) zlyhali: %s", nazov_skupiny(druh), od, do, e)
            continue
        # Z odpovede si necháme len destinácie tejto skupiny. Ryanair
        # nevie, že Mallorcu chceme na týždeň a Brusel na víkend.
        patria = [x for x in lety if skupina(x["kam"]) == druh]
        logger.info("%s (%d-%d dní): %d letov, z toho do tejto skupiny %d",
                    nazov_skupiny(druh), od, do, len(lety), len(patria))
        vsetky.extend(patria)

    return vsetky


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("=== Letenky z %s - začiatok ===", LETISKO)

    lety = najdi()
    if not lety:
        logger.error("Ryanair nevrátil nič - buď je rozhranie mimo, alebo nič nespĺňa kritériá.")
        return 1

    import firestore_client
    import telegram_bot

    db = firestore_client.get_client()
    zname_kluce, zname_url = firestore_client.get_existing_keys(db)

    # Čo sme už raz navrhli, nenavrhujeme znova - ani keď to zamietol.
    nove = [x for x in lety
            if f"ryanair|{x['kam']}|{x['odlet'][:10]}|{x['navrat'][:10]}" not in zname_kluce]
    logger.info("Spolu %d letov, z toho ešte nenavrhnutých %d", len(lety), len(nove))
    if not nove:
        logger.info("Nič nové oproti minulým dňom - nič neposielam.")
        return 0

    # Tri najlacnejšie. Bežnú cenu dopĺňame až tu, aby sme nerobili
    # desiatky volaní navyše pre lety, ktoré aj tak neposielame.
    vybrane = sorted(nove, key=lambda x: x["cena"])[:KOLKO_PONUK]
    vybrane = [dopln_beznu_cenu(x) for x in vybrane]

    dealy = [na_deal(x) for x in vybrane]
    for d in dealy:
        logger.info("  %s | %.2f € | bežne %s", d["title"], d["dealPrice"],
                    f"{d['originalPrice']:.2f} €" if d["originalPrice"] else "nezistené")

    zapisane = firestore_client.write_pending_deals(db, dealy)
    logger.info("Zapísaných návrhov: %d", len(zapisane))

    if not telegram_bot.is_configured():
        logger.warning("Telegram nie je nastavený - návrhy sú v admine, správa nešla.")
        return 0

    poslane = 0
    for deal_id, deal in zapisane:
        if telegram_bot.send_deal_for_approval(deal_id, deal):
            poslane += 1
    logger.info("=== Hotovo. Poslaných na schválenie: %d z %d. ===", poslane, len(zapisane))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
