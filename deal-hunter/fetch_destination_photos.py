"""
Stiahne jednu fotku ku každej destinácii Ryanairu z Bratislavy.

PREČO RAZ A NATRVALO, NIE ZA BEHU
Fotku potrebuje karta letenky. Ťahať ju z Wikipédie pri každom
zobrazení by znamenalo závislosť na cudzom serveri a pomalé karty.
Stiahneme ju teda raz, uložíme medzi ostatné obrázky stránky a
odkazujeme na vlastnú kópiu.

LICENCIE - TOTO NIE JE FORMALITA
Obrázky na Wikimedia Commons sú voľné, ale väčšina z nich vyžaduje
uvedenie autora. Preto si ku každej fotke ukladáme autora, licenciu a
odkaz na zdroj do fotky.json - stránka to potom zobrazí pri deale.
Fotku, ktorej licenciu sa nepodarí zistiť, radšej nestiahneme.

Spustenie:  python fetch_destination_photos.py
Beží ručne, nie v dennom behu - destinácie pribúdajú raz za čas.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import sys

import requests
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("fotky")

KONTAKT = "HenKukajBot/1.0 (https://henkukaj.sk)"
HLAVICKY = {"User-Agent": KONTAKT}

KAM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "assets", "destinacie")

# Rozmer karty na stránke. Fotku orežeme na 16:9, aby karty nepreskakovali.
SIRKA, VYSKA = 800, 450

# IATA kód -> názov článku na anglickej Wikipédii.
DESTINACIE = {
    # mestá
    "ATH": "Athens", "BCN": "Barcelona", "CIA": "Rome", "CRL": "Brussels",
    "DUB": "Dublin", "EDI": "Edinburgh", "EIN": "Eindhoven", "GDN": "Gdańsk",
    "LBA": "Leeds", "MAN": "Manchester", "MXP": "Milan", "NAP": "Naples",
    "PSA": "Pisa", "SKG": "Thessaloniki", "STN": "London", "TIA": "Tirana",
    "TRN": "Turin", "WMI": "Warsaw",
    # pri mori
    "ACE": "Lanzarote", "AGA": "Agadir", "AGP": "Málaga", "AHO": "it:Alghero",
    "ALC": "Alicante", "BOJ": "Burgas", "BRI": "Bari", "CFU": "Corfu",
    "DLM": "Dalaman", "JSI": "Skiathos", "MLA": "Malta", "PFO": "Paphos",
    "PMI": "Palma de Mallorca", "PMO": "Palermo", "SUF": "Lamezia Terme",
    "TPS": "Trapani", "ZAD": "Zadar",
}


def _bez_znaciek(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(text))).strip()


def nahlad(clanok: str) -> tuple[str, str] | None:
    """
    Vráti (adresa obrázka, názov súboru na Commons).

    Článok môže byť zapísaný aj ako "it:Alghero" - anglická Wikipédia
    nemá ku každému mestu úvodnú fotku (Alghero je taký prípad), miestna
    verzia ju spravidla má.
    """
    jazyk = "en"
    if ":" in clanok and len(clanok.split(":", 1)[0]) <= 3:
        jazyk, clanok = clanok.split(":", 1)
    r = requests.get(
        f"https://{jazyk}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(clanok)}",
        headers=HLAVICKY, timeout=25)
    if r.status_code != 200:
        logger.warning("  článok %s: HTTP %s", clanok, r.status_code)
        return None
    d = r.json()
    adresa = (d.get("originalimage") or {}).get("source") or \
             (d.get("thumbnail") or {}).get("source")
    if not adresa:
        return None
    # Z adresy vytiahneme názov súboru: pri zmenšeninách je v ceste
    # ".../thumb/a/a6/Nazov.jpg/3840px-Nazov.jpg", teda predposledný diel.
    cast = adresa.split("?")[0]
    if "/thumb/" in cast:
        nazov = cast.split("/thumb/")[1].split("/")[2]
    else:
        nazov = cast.rsplit("/", 1)[-1]
    return adresa, requests.utils.unquote(nazov)


def licencia(subor: str) -> dict | None:
    r = requests.get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "titles": f"File:{subor}", "prop": "imageinfo",
        "iiprop": "extmetadata|url", "format": "json",
    }, headers=HLAVICKY, timeout=25)
    strany = r.json().get("query", {}).get("pages", {})
    if not strany:
        return None
    info = (list(strany.values())[0].get("imageinfo") or [{}])[0]
    meta = info.get("extmetadata", {})

    def pole(k: str) -> str:
        return _bez_znaciek(meta.get(k, {}).get("value", ""))

    nazov_licencie = pole("LicenseShortName")
    if not nazov_licencie:
        return None
    return {
        "licencia": nazov_licencie,
        "autor": pole("Artist") or "neuvedený",
        "zdroj": info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/File:{subor}",
    }


def uloz_obrazok(adresa: str, cielovy: str) -> bool:
    r = requests.get(adresa, headers=HLAVICKY, timeout=60)
    if r.status_code != 200:
        logger.warning("  obrázok sa nestiahol: HTTP %s", r.status_code)
        return False
    try:
        obr = Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception as e:
        logger.warning("  obrázok sa nedá otvoriť: %s", e)
        return False

    # Orežeme na stred v pomere 16:9 a až potom zmenšíme - obyčajné
    # zmenšenie by fotku roztiahlo.
    ciel_pomer = SIRKA / VYSKA
    sirka, vyska = obr.size
    if sirka / vyska > ciel_pomer:
        nova = int(vyska * ciel_pomer)
        lavy = (sirka - nova) // 2
        obr = obr.crop((lavy, 0, lavy + nova, vyska))
    else:
        nova = int(sirka / ciel_pomer)
        horny = (vyska - nova) // 2
        obr = obr.crop((0, horny, sirka, horny + nova))

    obr = obr.resize((SIRKA, VYSKA), Image.LANCZOS)
    obr.save(cielovy, "WEBP", quality=82, method=6)
    return True


def main() -> int:
    os.makedirs(KAM, exist_ok=True)
    popis_path = os.path.join(KAM, "fotky.json")
    try:
        with open(popis_path, encoding="utf-8") as f:
            popisy = json.load(f)
    except FileNotFoundError:
        popisy = {}

    iba = sys.argv[1:] or list(DESTINACIE)
    hotovo, preskocene = 0, 0

    for iata in iba:
        clanok = DESTINACIE.get(iata)
        if not clanok:
            logger.warning("%s: nepoznám článok, preskakujem", iata)
            continue

        cielovy = os.path.join(KAM, f"{iata}.webp")
        if os.path.exists(cielovy) and iata in popisy:
            preskocene += 1
            continue

        logger.info("%s (%s):", iata, clanok)
        n = nahlad(clanok)
        if not n:
            logger.warning("  bez obrázka, preskakujem")
            continue
        adresa, subor = n

        lic = licencia(subor)
        if not lic:
            # Bez známej licencie fotku nepoužijeme. Nie je to opatrnosť
            # navyše - väčšina z nich vyžaduje uvedenie autora a bez
            # týchto údajov by sme ho uviesť nevedeli.
            logger.warning("  licenciu sa nepodarilo zistiť, fotku nepoužijem")
            continue

        if not uloz_obrazok(adresa, cielovy):
            continue

        popisy[iata] = {"subor": subor, **lic}
        kb = os.path.getsize(cielovy) // 1024
        logger.info("  uložené (%d kB) · %s · %s", kb, lic["licencia"], lic["autor"][:40])
        hotovo += 1

    with open(popis_path, "w", encoding="utf-8") as f:
        json.dump(popisy, f, ensure_ascii=False, indent=1, sort_keys=True)

    logger.info("\nStiahnutých %d, už existovalo %d, popisov spolu %d",
                hotovo, preskocene, len(popisy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
