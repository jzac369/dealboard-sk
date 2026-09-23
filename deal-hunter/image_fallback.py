"""
Doplnenie chýbajúceho obrázka z produktovej stránky.

Väčšina dealov obrázok má - zdroje ho dávajú spolu s cenou. Toto je
poistka pre tie, ktoré ho nemajú: karta bez obrázka vyzerá na stránke
ako chyba načítania a musel by si ho dopĺňať ručne v admine.

Berieme len og:image a twitter:image, teda obrázok, ktorý stránka sama
označila ako svoj náhľadový. Prvý <img> v HTML by bolo logo alebo
ikona košíka.

Sťahujeme až po výbere dealov a len pre tie bez obrázka - v bežnom behu
to znamená nula alebo jedno stiahnutie navyše.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import http_client
from models import DealCandidate

logger = logging.getLogger(__name__)

# Meta značky v poradí dôveryhodnosti.
_META_PATTERNS = [
    re.compile(
        r'<meta[^>]+property=["\']og:image(?::secure_url|:url)?["\'][^>]+'
        r'content=["\']([^"\']+)["\']', re.I),
    re.compile(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+'
        r'property=["\']og:image(?::secure_url|:url)?["\']', re.I),
    re.compile(
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+'
        r'content=["\']([^"\']+)["\']', re.I),
]

# Zástupné obrázky, ktoré e-shopy vracajú, keď náhľad nemajú. Taký
# obrázok je horší než žiadny - tvári sa ako produkt a nie je ním.
_NEVHODNE = ("placeholder", "no-image", "noimage", "default.", "logo.")


def _z_html(html: str, base_url: str) -> str | None:
    for vzor in _META_PATTERNS:
        zhoda = vzor.search(html)
        if not zhoda:
            continue
        adresa = (zhoda.group(1) or "").strip()
        if not adresa:
            continue
        adresa = urljoin(base_url, adresa)
        if not adresa.lower().startswith(("http://", "https://")):
            continue
        if any(s in adresa.lower() for s in _NEVHODNE):
            logger.debug("Náhľadový obrázok vyzerá ako zástupný: %s", adresa)
            continue
        return adresa
    return None


def fill_missing_images(candidates: list[DealCandidate]) -> int:
    """Doplní image_url tam, kde chýba. Vráti počet doplnených."""
    chybajuce = [c for c in candidates if not (c.image_url or "").strip()]
    if not chybajuce:
        return 0

    logger.info("Bez obrázka: %d — skúšam doplniť z produktovej stránky", len(chybajuce))
    doplnene = 0
    for c in chybajuce:
        if not c.url:
            continue
        try:
            html = http_client.get(c.url)
        except Exception as e:                      # sieť, timeout, čokoľvek
            logger.debug("Obrázok pre '%s' sa nepodarilo stiahnuť: %s", c.title[:40], e)
            continue
        if not html:
            continue
        adresa = _z_html(html, c.url)
        if adresa:
            c.image_url = adresa
            doplnene += 1
            logger.info("Doplnený obrázok pre '%s'", c.title[:50])

    if doplnene < len(chybajuce):
        logger.info(
            "Bez obrázka zostalo: %d (stránka ho neponúka v og:image)",
            len(chybajuce) - doplnene,
        )
    return doplnene
