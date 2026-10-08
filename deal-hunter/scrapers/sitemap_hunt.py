"""
Vlastné "vyhľadávanie" v e-shopoch cez ich sitemap.xml - bez cudzej služby a bez kľúča.

Každý e-shop zverejňuje sitemap.xml so zoznamom všetkých produktových stránok.
Agent z nej vyberie náhodnú vzorku, stiahne produktové stránky a z
štruktúrovaných dát (JSON-LD) prečíta cenu a prečiarknutú pôvodnú cenu.
Zľavu prijme len keď ju stránka sama ukazuje - rovnaké overenie ako pri
hľadaní cez vyhľadávač (scrapers/web_hunt.py).

Vzorka je malá (SITEMAP_STRANA_NA_OBCHOD stránok na obchod a beh), aby
sme obchody nezaťažovali: pauzu medzi požiadavkami a robots.txt rieši
http_client. Za pár dní sa tak prejde veľká časť sortimentu.
"""

from __future__ import annotations

import gzip
import logging
import random
import re
from urllib.parse import urlparse

import requests

import config
import http_client
from models import DealCandidate
from scrapers.base import BaseScraper
from scrapers.web_hunt import over_stranku

logger = logging.getLogger(__name__)

MAX_URL_NA_SITEMAP = 60000


def parsuj_sitemapu(obsah: bytes) -> tuple[list[str], list[str]]:
    """Vráti (odkazy na stránky, odkazy na ďalšie sitemapy). Zvláda aj .gz."""
    if obsah[:2] == b"\x1f\x8b":
        obsah = gzip.decompress(obsah)
    text = obsah.decode("utf-8", "ignore")
    locs = [re.sub(r"&amp;", "&", u).strip() for u in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", text)]
    if "<sitemapindex" in text[:600].lower() or "<sitemap>" in text[:2000].lower():
        return [], locs
    return locs, []


def vyber_vzorku(urls: list[str], n: int, rng: random.Random | None = None) -> list[str]:
    """Náhodná vzorka bez opakovania; cez deň iná, takže sa sortiment postupne prejde."""
    rng = rng or random
    return rng.sample(urls, min(n, len(urls)))


class SitemapHuntScraper(BaseScraper):
    source_name = "sitemap"

    def fetch_candidates(self) -> list[DealCandidate]:
        out: list[DealCandidate] = []
        for obchod in config.SITEMAP_OBCHODY:
            try:
                out += self._obchod(obchod)
            except Exception as e:
                # Jeden obchod (zmena webu, blokovanie) nesmie zhodiť ostatné.
                logger.warning("sitemap: %s zlyhal: %s", obchod.get("domena"), e)
        return out

    def _stiahni_sitemapu(self, url: str, hlbka: int = 0) -> list[str]:
        if hlbka > 2:
            return []
        r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=30)
        if r.status_code != 200:
            logger.warning("sitemap: %s -> HTTP %s", url[:80], r.status_code)
            return []
        stranky, dalsie = parsuj_sitemapu(r.content)
        for d in dalsie[:5]:
            stranky += self._stiahni_sitemapu(d, hlbka + 1)
        return stranky[:MAX_URL_NA_SITEMAP]

    def _obchod(self, obchod: dict) -> list[DealCandidate]:
        domena = obchod["domena"]
        urls: list[str] = []
        for sm in obchod["sitemapy"]:
            urls += self._stiahni_sitemapu(sm)
        # Len adresy z domény obchodu (sitemapa nesmie viesť na cudzie weby).
        urls = [u for u in urls if (urlparse(u).hostname or "").endswith(domena)]
        if not urls:
            return []
        pocet = int(obchod.get("strana") or config.SITEMAP_STRANA_NA_OBCHOD)
        vzorka = vyber_vzorku(urls, pocet)
        najdene: list[DealCandidate] = []
        for url in vzorka:
            try:
                html = http_client.get(url, check_robots=True)
                c = over_stranku(url, html, "deal", "") if html else None
            except Exception as e:
                logger.warning("sitemap: %s: %s", url[:70], e)
                continue
            if c:
                najdene.append(c)
        logger.info("sitemap %s: %d stránok z %d, so zľavou %d", domena, len(vzorka), len(urls), len(najdene))
        # Obchod, ktorý má "v akcii" väčšinu sortimentu, má prečiarknuté ceny
        # trvalo - rovnaké pravidlo ako pri feedoch (FEED_MAX_SALE_SHARE).
        if len(vzorka) >= 10 and len(najdene) / len(vzorka) > config.FEED_MAX_SALE_SHARE:
            logger.warning("sitemap %s: v akcii %d %% vzorky - prečiarknutým cenám neverím, zahadzujem",
                           domena, round(len(najdene) / len(vzorka) * 100))
            return []
        return najdene
