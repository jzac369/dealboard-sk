"""
Scraper pre alza.sk - sekcia "Cenové bomby" (vypredaj-akcia-zlava).
Alza renderuje zoznam produktov cez JavaScript, preto používame Selenium
namiesto obyčajného requests + BeautifulSoup.

POZNÁMKA: Selektory (CSS/XPath) sú založené na bežnej štruktúre Alza e-shopov,
no Alza si štruktúru stránky mení pomerne často. Pri prvom nasadení treba
overiť/doladiť selektory podľa aktuálneho HTML — návod na to je v README.
"""

import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scrapers.base import BaseScraper, DealCandidate, parse_price
import config

logger = logging.getLogger(__name__)

ALZA_URL = "https://www.alza.sk/vypredaj-akcia-zlava/e0.htm"


class AlzaScraper(BaseScraper):
    source_name = "alza.sk"

    def _build_driver(self):
        options = Options()
        if config.HEADLESS:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1400,2000")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
        # Selenium 4.6+ vie sám riadiť chromedriver (Selenium Manager),
        # takže netreba manuálne sťahovať driver binárku.
        return webdriver.Chrome(options=options)

    def fetch_candidates(self) -> list[DealCandidate]:
        driver = self._build_driver()
        candidates: list[DealCandidate] = []

        try:
            driver.get(ALZA_URL)
            WebDriverWait(driver, config.PAGE_LOAD_TIMEOUT_SECONDS).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.browsingitem"))
            )
            time.sleep(config.REQUEST_DELAY_SECONDS)

            items = driver.find_elements(By.CSS_SELECTOR, "div.browsingitem")
            logger.info("Alza: nájdených %d produktových kariet", len(items))

            for item in items:
                try:
                    candidate = self._parse_item(item)
                    if candidate:
                        candidates.append(candidate)
                except Exception as e:
                    logger.warning("Alza: preskakujem položku, chyba pri parsovaní: %s", e)
                    continue

        finally:
            driver.quit()

        return candidates

    def _parse_item(self, item) -> DealCandidate | None:
        title_el = item.find_elements(By.CSS_SELECTOR, "h3.name, .name a")
        if not title_el:
            return None
        title = title_el[0].text.strip()

        link_el = item.find_elements(By.CSS_SELECTOR, "a.name, h3.name a")
        source_url = link_el[0].get_attribute("href") if link_el else None
        if not source_url:
            return None

        # Aktuálna (zľavnená) cena
        new_price_el = item.find_elements(By.CSS_SELECTOR, ".price-box__price, .price")
        new_price = parse_price(new_price_el[0].text) if new_price_el else None

        # Pôvodná cena (prečiarknutá)
        old_price_el = item.find_elements(
            By.CSS_SELECTOR, ".price-box__old-price, .price-old, del"
        )
        old_price = parse_price(old_price_el[0].text) if old_price_el else None

        img_el = item.find_elements(By.CSS_SELECTOR, "img")
        image_url = img_el[0].get_attribute("src") if img_el else None

        if not title or new_price is None or old_price is None:
            return None
        if old_price <= new_price:
            return None  # nevalidný/nulový discount, preskočiť

        return DealCandidate(
            title=title,
            old_price=old_price,
            new_price=new_price,
            source_url=source_url,
            source_site=self.source_name,
            image_url=image_url,
        )
