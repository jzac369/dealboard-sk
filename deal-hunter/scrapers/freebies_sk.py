"""
Slovenské freebies: vzorky, produkty zadarmo a darčeky k nákupu.

TRI CESTY (štvrtá - položky za 0 € z affiliate feedov - je vo feeds.py)
1. Vyhľadávač Brave (BRAVE_API_KEY): denne vyhľadá typické frázy ("vzorky
   zadarmo", "produkt zadarmo na vyskúšanie"...) a každú stránku overí sám
   agent - na stránke musí byť ponuka naozaj zadarmo (overenie.over_stranku).
   Bez kľúča sa táto cesta preskočí. Bezplatný plán Brave má ~2000 dopytov
   mesačne; dva behy denne po DOPYTOV_NA_BEH sa do neho zmestia.
2. Sledované stránky (nastavenia_admin/freebies_stranky, spravuje sa v
   paneli na serveri): stránky značiek a obchodov, kde sa vzorky alebo
   darčeky objavujú. Typ "vzorka" sa overuje ako freebie, typ "darcek"
   hľadá na stránke vetu o darčeku zadarmo k nákupu.
3. Darčeky k nákupu z tých istých sledovaných stránok (typ "darcek") -
   nie sú to čisté freebies, preto majú v názve "k nákupu" a podmienku.

Nič z toho sa nezverejní samo - ide to do schvaľovania ako ostatné zdroje.
"""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse

import requests

import config
import http_client
from models import DealCandidate
from scrapers.base import BaseScraper
from scrapers.feeds import obchod_z_url
from scrapers.overenie import ZAKAZANE_DOMENY, ZAKAZANE_SLOVA, meta, nazov_stranky, over_stranku, text_stranky

logger = logging.getLogger(__name__)

DOPYTY = [
    "vzorky zadarmo", "vzorka zadarmo poštou", "objednajte si vzorku zadarmo",
    "produkt zadarmo na vyskúšanie", "získajte zadarmo", "testovanie produktov zadarmo",
    "e-kniha zadarmo na stiahnutie", "vzorky zadarmo kozmetika", "vzorky zadarmo pre deti",
    "darček zadarmo k nákupu",
]
DOPYTOV_NA_BEH = 5
MAX_STRANOK = 25

# Veta o darčeku k nákupu, napr. "DARČEK ZADARMO V HODNOTE 10 € A VIAC K NÁKUPU NAD 50 €".
_DARCEK = re.compile(
    r"((?:darček|darcek|darčeky)[^.!\n]{0,80}?zadarmo[^.!\n]{0,80}?(?:k (?:nákupu|nakupu|objednávke|objednavke))"
    # Veta končí podmienkou ("nad 50 €"); ďalší text na stránke už k nej nepatrí.
    r"(?:\s+nad\s+\d+(?:[.,]\d+)?\s*(?:€|eur))?)", re.I)


def brave_hladaj(dotaz: str, kluc: str) -> list[str]:
    try:
        r = requests.get("https://api.search.brave.com/res/v1/web/search",
                         params={"q": dotaz, "country": "SK", "search_lang": "sk", "count": 10, "freshness": "pm"},
                         headers={"X-Subscription-Token": kluc, "Accept": "application/json"}, timeout=20)
        if r.status_code != 200:
            logger.warning("freebies SK: Brave HTTP %s", r.status_code)
            return []
        return [x["url"] for x in (r.json().get("web") or {}).get("results", []) if x.get("url")]
    except Exception as e:
        logger.warning("freebies SK: Brave zlyhal (%s)", e)
        return []


def _povolena(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return url.startswith("https://") and not any(z in host for z in ZAKAZANE_DOMENY)


def darcek_zo_stranky(url: str, html: str) -> DealCandidate | None:
    """Darček zadarmo k nákupu podľa vety na stránke. Čisté - testovateľné."""
    text = re.sub(r"\s+", " ", text_stranky(html))
    m = _DARCEK.search(text)
    if not m:
        return None
    veta = m.group(1).strip(" ,;:-")
    if any(s in veta for s in ZAKAZANE_SLOVA):
        return None
    obchod = obchod_z_url(url)
    veta_pekne = veta[0].upper() + veta[1:]
    return DealCandidate(
        title=f"{obchod}: {veta_pekne}"[:150], deal_price=0.0, original_price=None,
        explicit_discount_percent=100, zadarmo=True, url=url, direct_url=True,
        source="freebies-sk", store=obchod, category_hint="Iné",
        image_url=(lambda i: i if i and i.startswith("https://") else None)(meta(html, "og:image")),
        description=(f"{obchod} dáva darček zadarmo k nákupu: {veta}. Nejde o produkt úplne zadarmo - "
                     f"darček dostaneš pri splnení podmienky obchodu (napr. minimálna hodnota nákupu)."),
    )


def vzorka_zo_stranky(url: str, html: str) -> DealCandidate | None:
    c = over_stranku(url, html, "freebie", "")
    if not c:
        return None
    c.source = "freebies-sk"
    if not c.description or len(c.description) < 40:
        c.description = f"{c.store} ponúka {nazov_stranky(html) or 'produkt'} zadarmo. Podmienky nájdeš na stránke ponuky."
    return c


class FreebiesSkScraper(BaseScraper):
    source_name = "freebies_sk"

    def fetch_candidates(self) -> list[DealCandidate]:
        out = self._sledovane()
        kluc = os.environ.get("BRAVE_API_KEY", "").strip()
        if kluc:
            out += self._brave(kluc)
        else:
            logger.info("freebies SK: BRAVE_API_KEY nie je nastavený, vyhľadávanie preskakujem.")
        return out

    def _sledovane(self) -> list[DealCandidate]:
        try:
            import firestore_client
            data = firestore_client.get_client().document("nastavenia_admin/freebies_stranky").get().to_dict() or {}
        except Exception as e:
            logger.warning("freebies SK: zoznam stránok sa nenačítal: %s", e)
            return []
        out = []
        for s in data.get("stranky", []):
            url = str(s.get("url") or "").strip()
            if s.get("zap") is False or not _povolena(url):
                continue
            html = http_client.get(url, check_robots=True)
            if not html:
                continue
            c = darcek_zo_stranky(url, html) if s.get("typ") == "darcek" else vzorka_zo_stranky(url, html)
            if c:
                out.append(c)
        logger.info("freebies SK: sledované stránky %d, nájdené %d", len(data.get("stranky", [])), len(out))
        return out

    def _brave(self, kluc: str) -> list[DealCandidate]:
        import random
        dopyty = random.sample(DOPYTY, min(DOPYTOV_NA_BEH, len(DOPYTY)))
        videne, out = set(), []
        for dotaz in dopyty:
            for url in brave_hladaj(dotaz, kluc):
                if url in videne or len(videne) >= MAX_STRANOK or not _povolena(url):
                    continue
                videne.add(url)
                html = http_client.get(url, check_robots=True)
                if not html:
                    continue
                c = darcek_zo_stranky(url, html) if "darček" in dotaz else vzorka_zo_stranky(url, html)
                if c:
                    out.append(c)
        logger.info("freebies SK (Brave): overených %d z %d stránok", len(out), len(videne))
        return out
