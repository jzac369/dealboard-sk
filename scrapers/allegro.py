"""
Scraper pre allegro.sk - stránka "Allegro Dni" (cenovehity/allegro-dni).

Na rozdiel od Alzy, Allegro je server-side renderované, takže stačí obyčajný
requests + BeautifulSoup - nepotrebujeme Selenium ani headless Chrome.

Namiesto CSS tried (tie sú na Allegre automaticky hashované a menia sa pri
každom nasadení) parsujeme podľa STABILNÉHO textového vzoru, ktorý Allegro
používa pri každej ponuke so zľavou:

    -10% 29,99 € cena za posledných 30 dní
    Najnižšia cena ponuky za posledných 30 dní pred znížením ceny
    26,74 €
    Názov produktu (link obsahuje ?offerId=XXXXXXXX)

Kde:
  - "-10%"   = percento zľavy (informatívne, prepočítavame si vlastné)
  - "29,99 €" = referenčná cena za posledných 30 dní (= naša "stará cena")
  - "26,74 €" = aktuálna cena
  - offerId   = stabilný identifikátor ponuky, nezávislý na dizajne stránky

Ponuky bez jasného "-X% ... cena za posledných 30 dní" vzoru (napr. "Len v
apke" špeciálne mobilné ceny) preskakujeme - nemajú porovnateľnú referenčnú
cenu.
"""

import re
import logging
import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, DealCandidate, parse_price
import config

logger = logging.getLogger(__name__)

ALLEGRO_URL = "https://allegro.sk/cenovehity/allegro-dni"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "sk-SK,sk;q=0.9,en;q=0.8",
}

DISCOUNT_PATTERN = re.compile(
    r"-(\d+)%\s*([\d\s.,]+)\s*€\s*cena za posledn", re.IGNORECASE
)
CURRENT_PRICE_PATTERN = re.compile(r"znížením ceny\s*([\d\s.,]+)\s*€")


class AllegroScraper(BaseScraper):
    source_name = "allegro.sk"

    def fetch_candidates(self) -> list[DealCandidate]:
        candidates: list[DealCandidate] = []

        response = requests.get(ALLEGRO_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        seen_offer_ids = set()

        for link in soup.select('a[href*="offerId="]'):
            href = link.get("href", "")
            offer_id_match = re.search(r"offerId=(\d+)", href)
            if not offer_id_match:
                continue
            offer_id = offer_id_match.group(1)
            if offer_id in seen_offer_ids:
                continue
            seen_offer_ids.add(offer_id)

            title = link.get_text(strip=True)
            if not title:
                continue

            try:
                candidate = self._parse_card(link, href, title)
                if candidate:
                    candidates.append(candidate)
            except Exception as e:
                logger.warning(
                    "Allegro: preskakujem ponuku '%s', chyba pri parsovaní: %s",
                    title,
                    e,
                )
                continue

        logger.info("Allegro: spracovaných %d unikátnych offerId", len(seen_offer_ids))
        return candidates

    def _parse_card(self, link, href: str, title: str) -> DealCandidate | None:
        # Nájdeme najbližší rodičovský kontajner karty (li alebo div), aby sme
        # mali textový kontext s cenami okolo tohto konkrétneho produktu.
        card = link.find_parent("li") or link.find_parent("div")
        if card is None:
            return None

        block_text = card.get_text(separator=" ", strip=True)

        discount_match = DISCOUNT_PATTERN.search(block_text)
        if not discount_match:
            # napr. "Len v apke" ponuky bez jasnej referenčnej ceny - preskočiť
            return None

        old_price = parse_price(discount_match.group(2))

        current_match = CURRENT_PRICE_PATTERN.search(block_text)
        new_price = parse_price(current_match.group(1)) if current_match else None

        if old_price is None or new_price is None or old_price <= new_price:
            return None

        # Skús nájsť obrázok - Allegro obrázky bývajú lazy-loaded, skús viac atribútov
        image_url = None
        img_el = card.find("img")
        if img_el:
            image_url = (
                img_el.get("data-src")
                or img_el.get("data-original")
                or img_el.get("src")
            )

        return DealCandidate(
            title=title,
            old_price=old_price,
            new_price=new_price,
            source_url=href,
            source_site=self.source_name,
            image_url=image_url,
        )
