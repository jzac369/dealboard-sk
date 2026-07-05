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
        # Zníženie šance, že stránka rozpozná automatizovaný prehliadač
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--lang=sk-SK")

        driver = webdriver.Chrome(options=options)
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """
            },
        )
        return driver

    def _accept_cookies_if_present(self, driver):
        """Skúsi zavrieť cookie/consent banner, ak sa objaví. Ticho zlyhá, ak nie je."""
        possible_texts = ["Súhlasím", "Prijať všetky", "Rozumiem", "Povoliť všetky", "Accept all"]
        for text in possible_texts:
            try:
                btn = driver.find_element(
                    By.XPATH, f"//button[contains(., '{text}')]"
                )
                btn.click()
                time.sleep(0.5)
                logger.info("Alza: zatvoril som cookie banner (text: %s)", text)
                return
            except Exception:
                continue

    def fetch_candidates(self) -> list[DealCandidate]:
        driver = self._build_driver()
        candidates: list[DealCandidate] = []

        try:
            driver.get(ALZA_URL)
            time.sleep(2)
            self._accept_cookies_if_present(driver)

            try:
                WebDriverWait(driver, config.PAGE_LOAD_TIMEOUT_SECONDS).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.box.browsingitem")
                    )
                )
            except Exception:
                # Diagnostika - uložíme čo presne stránka vrátila, aby sme vedeli,
                # či ide o cookie banner, CAPTCHA, blokáciu bota, alebo zmenu HTML.
                import os

                os.makedirs("debug-alza", exist_ok=True)
                driver.save_screenshot("debug-alza/screenshot.png")
                with open("debug-alza/page_source.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                logger.error(
                    "Alza: nenašiel som produkty. Uložený screenshot a HTML do "
                    "debug-alza/ pre diagnostiku. Dĺžka page_source: %d znakov, "
                    "title stránky: '%s'",
                    len(driver.page_source),
                    driver.title,
                )
                raise

            time.sleep(config.REQUEST_DELAY_SECONDS)

            items = driver.find_elements(By.CSS_SELECTOR, "div.box.browsingitem")
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
        # Názov + link na produkt
        link_el = item.find_elements(By.CSS_SELECTOR, "a.name.browsinglink")
        if not link_el:
            return None
        title = link_el[0].text.strip()
        source_url = link_el[0].get_attribute("href")
        if not title or not source_url:
            return None

        # Aktuálna (zľavnená) cena, napr. "426 €"
        new_price_el = item.find_elements(
            By.CSS_SELECTOR, ".ads-pb__price-value, .js-price-box__primary-price-value"
        )
        new_price = parse_price(new_price_el[0].text) if new_price_el else None

        # Alza neukazuje priamo starú cenu, len sumu úspory: "Ušetríte 53 €"
        savings_el = item.find_elements(By.CSS_SELECTOR, ".ads-pb__original-price")
        savings = parse_price(savings_el[0].text) if savings_el else None

        img_el = item.find_elements(By.CSS_SELECTOR, "img")
        image_url = img_el[0].get_attribute("src") if img_el else None

        if new_price is None or savings is None or savings <= 0:
            # Bez informácie o úspore nevieme spočítať % zľavy - preskočiť
            return None

        old_price = round(new_price + savings, 2)

        return DealCandidate(
            title=title,
            old_price=old_price,
            new_price=new_price,
            source_url=source_url,
            source_site=self.source_name,
            image_url=image_url,
        )
