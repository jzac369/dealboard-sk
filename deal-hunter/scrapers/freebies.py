"""
Freebies: veci úplne zadarmo z oficiálnych zdrojov.

ZDROJE
- Epic Games Store: týždenné hry zadarmo. Verejný zoznam akcií obchodu
  (freeGamesPromotions), ten istý, z ktorého si obchod kreslí svoju stránku.
  Berieme len hru s aktívnou akciou, ktorej cena po zľave je 0.
- Steam: hry a doplnky zľavnené na 0 € (vyhľadávanie obchodu, robots.txt ho
  povoľuje). Steam má veľa bezcenných kúskov bez hodnotení, preto berieme len
  také, ktoré majú používateľské hodnotenie - inak by to nestálo za to.
- GOG: katalóg s filtrom cena 0 a zľava (rozdávania hier).

Všetko sú to ponuky „zadarmo navždy" (hra ostane v knižnici), nie skúšobné
verzie. Platnosť akcie berieme priamo zo zdroja.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta, timezone

import requests

import config
from models import DealCandidate
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

EPIC = ("https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"
        "?locale=sk&country=SK&allowCountries=SK")
STEAM = ("https://store.steampowered.com/search/results/?maxprice=free&specials=1&infinite=1"
         "&count=50&cc=sk&l=slovak")
GOG = ("https://catalog.gog.com/v1/catalog?limit=24&price=between:0,0&discounted=eq:true"
       "&order=desc:trending&countryCode=SK&currencyCode=EUR&locale=sk-SK")


def _get_json(url: str):
    try:
        r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=30)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logger.warning("freebies: %s zlyhal: %s", url.split("/")[2], e)
        return None


def _datum(iso: str | None) -> str | None:
    """'2026-11-05T16:00:00.000Z' -> '5.11.2026' (formát, ktorý používa zvyšok agenta)."""
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{d.day}.{d.month}.{d.year}"
    except ValueError:
        return None


def _cena(text: str) -> float | None:
    m = re.search(r"(\d+[.,]\d{2})", text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def epic_freebies(data: dict) -> list[DealCandidate]:
    """Čistá funkcia (bez siete) - testovateľná na uloženej odpovedi."""
    out = []
    for e in ((data or {}).get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])):
        akcie = [o for p in ((e.get("promotions") or {}).get("promotionalOffers") or [])
                 for o in p.get("promotionalOffers", [])]
        cena = (e.get("price") or {}).get("totalPrice") or {}
        if not akcie or cena.get("discountPrice", 1) != 0:
            continue
        # Akcia, ktorá skončí do 3 hodín (alebo už skončila), sa nestihne
        # schváliť a zverejniť - návštevník by prišiel neskoro.
        try:
            koniec = datetime.fromisoformat(str(akcie[0].get("endDate")).replace("Z", "+00:00"))
            if koniec <= datetime.now(timezone.utc) + timedelta(hours=3):
                continue
        except ValueError:
            pass
        povodna = (cena.get("originalPrice") or 0) / 100
        if povodna <= 0:
            continue                       # hra, ktorá je zadarmo stále, nie je akcia
        slug = ((e.get("catalogNs") or {}).get("mappings") or [{}])[0].get("pageSlug") or e.get("productSlug")
        if not slug:
            continue
        obrazok = next((k.get("url") for k in e.get("keyImages", []) if k.get("type") in ("OfferImageWide", "Thumbnail")), None)
        do = _datum(akcie[0].get("endDate"))
        nazov = e.get("title", "").strip()
        out.append(DealCandidate(
            title=f"{nazov} – hra zadarmo na Epic Games Store",
            deal_price=0.0, original_price=povodna, explicit_discount_percent=100, zadarmo=True,
            url=f"https://store.epicgames.com/sk/p/{slug}", direct_url=True,
            source="epicgames.com", store="Epic Games Store", image_url=obrazok, category_hint="Iné",
            valid_until=do,
            description=(f"Hru {nazov} si na Epic Games Store pridáš do knižnice zadarmo a ostane ti natrvalo "
                         f"(bežne stojí {povodna:.2f} €). Stačí sa prihlásiť do účtu Epic Games a kliknúť na Získať."
                         + (f" Akcia platí do {do}." if do else "")),
        ))
    return out


def steam_freebies(data: dict) -> list[DealCandidate]:
    out = []
    h = (data or {}).get("results_html", "")
    for blok in re.findall(r'<a href="https://store\.steampowered\.com/app/.*?</a>', h, re.S):
        url = re.search(r'href="(https://store\.steampowered\.com/app/\d+/[^"?]*)', blok)
        nazov = re.search(r'<span class="title">([^<]+)</span>', blok)
        if not url or not nazov or 'data-discount="100"' not in blok:
            continue
        # Bez hodnotení (prázdny search_reviewscore) to býva bezcenný kúsok.
        if "search_review_summary" not in blok:
            continue
        povodna = _cena((re.search(r'discount_original_price">([^<]+)<', blok) or [None, ""])[1])
        obrazok = (re.search(r'<img src="([^"]+)"', blok) or [None, None])[1]
        n = html.unescape(nazov.group(1)).strip()
        out.append(DealCandidate(
            title=f"{n} – zadarmo na Steame", deal_price=0.0, original_price=povodna,
            explicit_discount_percent=100, zadarmo=True, url=url.group(1), direct_url=True,
            source="steampowered.com", store="Steam", image_url=obrazok, category_hint="Iné",
            description=(f"{n} je teraz na Steame zadarmo" + (f" (bežne {povodna:.2f} €)" if povodna else "")
                         + ". Po pridaní do knižnice ti ostane natrvalo."),
        ))
    return out


def gog_freebies(data: dict) -> list[DealCandidate]:
    out = []
    for p in (data or {}).get("products", []):
        cena = p.get("price") or {}
        if _cena(str(cena.get("final"))) not in (0.0, None) or not p.get("storeLink"):
            continue
        povodna = _cena(str(cena.get("base")))
        if not povodna:
            continue
        n = p.get("title", "").strip()
        out.append(DealCandidate(
            title=f"{n} – hra zadarmo na GOG", deal_price=0.0, original_price=povodna,
            explicit_discount_percent=100, zadarmo=True, url=p["storeLink"], direct_url=True,
            source="gog.com", store="GOG", image_url=p.get("coverHorizontal"), category_hint="Iné",
            description=f"Hru {n} rozdáva GOG zadarmo (bežne {povodna:.2f} €). Bez DRM, ostane ti natrvalo.",
        ))
    return out


class FreebiesScraper(BaseScraper):
    source_name = "freebies"

    def fetch_candidates(self) -> list[DealCandidate]:
        out: list[DealCandidate] = []
        for meno, url, fn in (("Epic", EPIC, epic_freebies), ("Steam", STEAM, steam_freebies), ("GOG", GOG, gog_freebies)):
            try:
                najdene = fn(_get_json(url))
            except Exception as e:
                logger.warning("freebies %s: %s", meno, e)
                najdene = []
            logger.info("freebies %s: %d", meno, len(najdene))
            out += najdene
        return out
