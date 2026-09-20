"""
Scraper pre affiliate produktové feedy (Dognet a podobné siete).

Prečo je toto najlepší zdroj:
- Dáta sú štruktúrované — žiadne CSS selektory, ktoré sa rozbijú pri redizajne.
- Odkazy sú rovno affiliate (zarábajú), ak do feedu vložíš svoje partner ID.
- Partner ti feed poskytuje zámerne, takže scrapovanie nikoho neobťažuje.

Feedy sa nastavujú cez premennú prostredia FEED_URLS (oddelené čiarkami),
nie v kóde — každý partner má vlastnú URL aj tvoje partnerské ID v nej,
a to do repozitára nepatrí.

Podporované formáty (rozpozná sa automaticky podľa štruktúry XML):
- Google Merchant / RSS 2.0 s namespace g:  (<item><g:price>, <g:sale_price>)
- Heureka XML                               (<SHOPITEM><PRICE_VAT>)
"""

import logging
import xml.etree.ElementTree as ET
from typing import Optional

import config
import http_client
from models import DealCandidate, parse_price
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Namespace Google Merchant feedov.
_G_NS = "{http://base.google.com/ns/1.0}"


def _text(node: Optional[ET.Element]) -> Optional[str]:
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def _first(item: ET.Element, *paths: str) -> Optional[str]:
    """Vráti text prvého tagu, ktorý v položke existuje. Skratka pre feedy,
    ktoré ten istý údaj volajú rôzne (URL vs LINK vs link)."""
    for path in paths:
        value = _text(item.find(path))
        if value:
            return value
    return None


class FeedsScraper(BaseScraper):
    source_name = "affiliate-feed"

    def fetch_candidates(self) -> list[DealCandidate]:
        if not config.FEED_URLS:
            logger.info(
                "Žiadne feedy nie sú nastavené (premenná FEED_URLS je prázdna) — preskakujem."
            )
            return []

        candidates: list[DealCandidate] = []
        for feed_url in config.FEED_URLS:
            try:
                found = self._fetch_one_feed(feed_url)
                logger.info("feed %s -> %d kandidátov", feed_url, len(found))
                candidates.extend(found)
            except Exception as e:
                # Jeden rozbitý feed nesmie zhodiť ostatné.
                logger.error("Feed %s zlyhal: %s", feed_url, e, exc_info=True)

        return candidates

    def _fetch_one_feed(self, feed_url: str) -> list[DealCandidate]:
        # Feed nám partner poskytuje zámerne, robots.txt sa naň nevzťahuje.
        xml_text = http_client.get(feed_url, check_robots=False)
        if not xml_text:
            return []
        return self.parse_feed(xml_text, feed_url)

    # ── parsovanie (oddelené, aby sa dalo testovať offline) ───────────

    def parse_feed(self, xml_text: str, feed_url: str = "") -> list[DealCandidate]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error("Feed %s nie je platné XML: %s", feed_url, e)
            return []

        shop_items = root.findall(".//SHOPITEM")
        if shop_items:
            items, parser = shop_items, self._parse_heureka_item
        else:
            items, parser = root.findall(".//item"), self._parse_google_item

        candidates: list[DealCandidate] = []
        for item in items[: config.FEED_MAX_ITEMS]:
            try:
                candidate = parser(item)
            except Exception as e:
                logger.warning("Feed %s: preskakujem položku (%s)", feed_url, e)
                continue
            if candidate:
                candidates.append(candidate)

        return candidates

    def _parse_google_item(self, item: ET.Element) -> Optional[DealCandidate]:
        title = _first(item, f"{_G_NS}title", "title")
        url = _first(item, f"{_G_NS}link", "link")
        # Bežná cena a akciová cena. Bez akciovej ceny nemáme zľavu,
        # a bez zľavy to na deal stránku nepatrí.
        regular = parse_price(_first(item, f"{_G_NS}price", "price"))
        sale = parse_price(_first(item, f"{_G_NS}sale_price", "sale_price"))

        if not title or not url or regular is None or sale is None:
            return None
        if sale >= regular:
            return None

        return DealCandidate(
            title=title,
            deal_price=sale,
            original_price=regular,
            url=url,
            source=self.source_name,
            store=_first(item, f"{_G_NS}brand", "brand") or "",
            image_url=_first(item, f"{_G_NS}image_link", "image_link"),
            description=_first(item, f"{_G_NS}description", "description") or "",
        )

    def _parse_heureka_item(self, item: ET.Element) -> Optional[DealCandidate]:
        title = _first(item, "PRODUCTNAME", "PRODUCT")
        url = _first(item, "URL")
        price = parse_price(_first(item, "PRICE_VAT", "PRICE"))

        if not title or not url or price is None:
            return None

        # Heureka formát bežnú cenu štandardne neuvádza. Niektorí partneri
        # ju posielajú ako vlastný tag — ak chýba, zľavu nevieme určiť
        # a položku preskočíme, aby sa na stránku nedostala "zľava 0 %".
        original = parse_price(_first(item, "PRICE_BEFORE_DISCOUNT", "STANDARD_PRICE", "LIST_PRICE"))
        if original is None or original <= price:
            return None

        return DealCandidate(
            title=title,
            deal_price=price,
            original_price=original,
            url=url,
            source=self.source_name,
            store=_first(item, "MANUFACTURER") or "",
            image_url=_first(item, "IMGURL"),
            description=_first(item, "DESCRIPTION") or "",
        )
