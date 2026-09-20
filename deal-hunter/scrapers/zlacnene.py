"""
Scraper pre zlacnene.sk — akciový tovar z letákov reťazcov.

Prečo práve tento zdroj:
- Pokrýva naraz potraviny, letáky (BILLA, Lidl, Kaufland, Tesco...) aj bežné akcie.
- Stránka používa schema.org microdata (itemprop="price", "seller", "image"),
  čo je strojovo čitateľný kontrakt — prežije redizajn oveľa lepšie než CSS triedy.
- robots.txt to dovoľuje, len žiada Crawl-delay 1 s (držíme 1,5 s).

Parsujeme <div itemtype="http://schema.org/Product">, v ktorom je jeden
alebo viac <div itemtype="http://schema.org/Offer"> (jeden na predajcu).
Berieme ponuku s najnižšou cenou.
"""

import logging
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import config
import http_client
from models import DealCandidate, parse_price
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.zlacnene.sk"
LISTING_URL = f"{BASE_URL}/akciovy-tovar/"

# Kategórie zlacnene.sk -> kategórie na henkukaj.sk.
#
# Prečo sťahujeme po kategóriách a nie len zo všeobecného zoznamu:
# 1. Vieme kategóriu, nemusíme ju hádať z názvu. Hádanie zlyháva na
#    značkách — "Lindt Excellence" ani "Zlatý Bažant" nemá v názve nič,
#    z čoho by sa dalo určiť, že ide o potraviny.
# 2. Všeobecný zoznam je zaplavený potravinami, lebo letáky reťazcov sú
#    prevažne potravinové. Bez kategórií by na stránke bolo len jedlo.
#
# Zoznam je overený: každá z týchto kategórií reálne vracala tovar.
# Kategórie mobily/pc-tablety/tv-video sú tu zámerne vynechané — sú
# prázdne a vracajú len odporúčaný blok z inej kategórie.
CATEGORY_MAP: dict[str, str] = {
    # nábytok a domácnosť
    "sedacie-supravy": "Dom & Záhrada",
    "stolicky-stoly": "Dom & Záhrada",
    "spalne": "Dom & Záhrada",
    "kuchyne": "Dom & Záhrada",
    "kupelne": "Dom & Záhrada",
    "svietidla": "Dom & Záhrada",
    "koberce-podlahy": "Dom & Záhrada",
    "ulozne-priestory": "Dom & Záhrada",
    "textil-bytovy": "Dom & Záhrada",
    # náradie a stavba
    "naradie": "Dom & Záhrada",
    "zahradna-technika": "Dom & Záhrada",
    "stavebne-materialy": "Dom & Záhrada",
    # POZNÁMKA K ELEKTRONIKE
    # Kategórie mobily, pc-tablety, tv-video, foto, audio, cd-dvd,
    # ostatna-elektronika ani chladnicky-mraznicky tu zámerne NIE SÚ.
    # Všetky sú prázdne a vracajú odporúčaný blok z inej kategórie -
    # do "Elektroniky" by sa tak dostal vysávač alebo nástenné hodiny.
    # Zdroj je postavený na letákoch potravinových a nábytkárskych
    # reťazcov; spotrebná elektronika v nich jednoducho nie je.
    # ostatné
    "knihy-papiernictvo": "Iné",
    "hracky": "Hračky",
    "sportove-vybavenie": "Šport",
    "obuv": "Móda",
    "oblecenie-panske": "Móda",
    "oblecenie-damske": "Móda",
    "oblecenie-detske": "Móda",
    "domaci-maznacikovia": "Iné",
    # drogéria a domácnosť
    "cistiace-prostriedky": "Iné",
    "pracie-prostriedky": "Iné",
    "umyvanie-riadu": "Iné",
    "toaletny-papier-vreckovky": "Iné",
    "ostatna-drogeria": "Iné",
    "toaletne-vody-a-parfumy": "Iné",
    "detska-vyziva": "Iné",
    "sezona": "Iné",
    "okna-dvere": "Dom & Záhrada",
    "kempovanie": "Šport",
    # potraviny
    "maso": "Jedlo & Nápoje",
    "pecivo": "Jedlo & Nápoje",
    "mrazeny-tovar": "Jedlo & Nápoje",
    "udeniny-lahodky": "Jedlo & Nápoje",
    "teple-napoje": "Jedlo & Nápoje",
    "dochucovadla": "Jedlo & Nápoje",
    "ostatne-potraviny": "Jedlo & Nápoje",
    "ostatne-chladene": "Jedlo & Nápoje",
    "mliecne-vyrobky": "Jedlo & Nápoje",
    "ovocie": "Jedlo & Nápoje",
    "zelenina": "Jedlo & Nápoje",
    "napoje-nealkoholicke": "Jedlo & Nápoje",
    "napoje-alkoholicke": "Jedlo & Nápoje",
    "cukrovinky-pochutiny": "Jedlo & Nápoje",
    "trvanlive": "Jedlo & Nápoje",
}

# "-40%" v badge alebo "-40<span>%</span>" v ponuke
_DISCOUNT_RE = re.compile(r"-\s*(\d{1,3})\s*%")
# "Platí do: 22.9.2026"
_VALID_UNTIL_RE = re.compile(r"Platí do:\s*([\d.]+\d)")


class ZlacneneScraper(BaseScraper):
    source_name = "zlacnene.sk"

    def fetch_candidates(self) -> list[DealCandidate]:
        candidates: list[DealCandidate] = []
        # Poradie je dôležité: deduplikácia si drží prvý výskyt, a položka
        # z kategórie nesie správnu kategóriu, kým tá zo všeobecného
        # zoznamu ju má len odhadnutú z názvu.
        candidates.extend(self._fetch_categories())

        # Keď si niekto vyžiada konkrétne kategórie, všeobecný zoznam
        # preskakujeme — je plný potravín a prepašoval by ich do výberu
        # napriek tomu, že sa pýtal na niečo iné.
        if config.ZLACNENE_CATEGORIES:
            logger.info(
                "%s: vyžiadané konkrétne kategórie — všeobecný zoznam preskakujem",
                self.source_name,
            )
        else:
            candidates.extend(self._fetch_general_listing())

        return candidates

    def _fetch_general_listing(self) -> list[DealCandidate]:
        """Všeobecný zoznam — tu bývajú najväčšie zľavy naprieč kategóriami."""
        candidates: list[DealCandidate] = []

        for page in range(1, config.ZLACNENE_MAX_PAGES + 1):
            url = LISTING_URL if page == 1 else f"{LISTING_URL}strana-{page}/"
            html = http_client.get(url)
            if not html:
                logger.warning("%s: strana %d sa nenačítala, končím stránkovanie", self.source_name, page)
                break

            page_candidates = self.parse_listing(html)
            logger.info("%s: strana %d -> %d kandidátov", self.source_name, page, len(page_candidates))
            if not page_candidates:
                # Prázdna strana = buď koniec zoznamu, alebo zmenená štruktúra.
                break
            candidates.extend(page_candidates)

        return candidates

    def _fetch_categories(self) -> list[DealCandidate]:
        """
        Prejde jednotlivé kategórie. Vďaka tomu kategóriu poznáme (nehádame)
        a na stránku sa dostane aj nepotravinový tovar.
        """
        slugs = config.ZLACNENE_CATEGORIES or list(CATEGORY_MAP)
        per_category: dict[str, list[DealCandidate]] = {}

        for slug in slugs:
            site_category = CATEGORY_MAP.get(slug)
            if site_category is None:
                logger.warning("%s: neznáma kategória '%s' — preskakujem", self.source_name, slug)
                continue

            html = http_client.get(f"{LISTING_URL}{slug}/")
            if not html:
                continue

            found = self.parse_listing(html, category_hint=site_category)
            logger.info("%s: kategória %s -> %d kandidátov", self.source_name, slug, len(found))
            per_category[slug] = found

        return self._drop_fallback_blocks(per_category)

    @staticmethod
    def _drop_fallback_blocks(
        per_category: dict[str, list[DealCandidate]]
    ) -> list[DealCandidate]:
        """
        Zahodí kategórie, ktoré v skutočnosti nič neobsahujú.

        Prázdna kategória na zlacnene.sk nevráti prázdny zoznam, ale
        odporúčaný blok s tovarom odinakiaľ — a ten je pre všetky prázdne
        kategórie rovnaký. Bez tejto kontroly by sa do "Elektroniky"
        dostal vysávač len preto, že kategória `foto` je prázdna.

        Rozoznáme to podľa toho, že dve rôzne kategórie vrátili presne
        ten istý zoznam položiek. Dva naozaj rôzne úseky letáku sa takto
        zhodovať nemôžu.
        """
        signatures: dict[tuple, list[str]] = {}
        for slug, items in per_category.items():
            if not items:
                continue
            signature = tuple(sorted((c.title, c.deal_price) for c in items))
            signatures.setdefault(signature, []).append(slug)

        candidates: list[DealCandidate] = []
        for signature, slugs_with_it in signatures.items():
            if len(slugs_with_it) > 1:
                logger.warning(
                    "Kategórie %s vrátili identický obsah — sú prázdne a "
                    "zobrazujú odporúčaný blok. Vynechávam ich.",
                    ", ".join(sorted(slugs_with_it)),
                )
                continue
            candidates.extend(per_category[slugs_with_it[0]])

        return candidates

    # ── parsovanie ────────────────────────────────────────────────────
    # Oddelené od sťahovania, aby sa dalo testovať offline na uloženom
    # HTML (tests/fixtures) bez toho, aby sme zaťažovali cudzí server.

    def parse_listing(self, html: str, category_hint: str | None = None) -> list[DealCandidate]:
        soup = BeautifulSoup(html, "html.parser")
        products = soup.find_all(attrs={"itemtype": re.compile(r"schema\.org/Product")})

        candidates: list[DealCandidate] = []
        for product in products:
            try:
                candidate = self._parse_product(product, category_hint)
            except Exception as e:
                # Jedna chybná karta nesmie zhodiť zvyšok strany.
                logger.warning("%s: preskakujem položku (%s)", self.source_name, e)
                continue
            if candidate:
                candidates.append(candidate)

        return candidates

    def _parse_product(self, product, category_hint: str | None = None) -> Optional[DealCandidate]:
        title = self._itemprop_content(product, "name")
        rel_url = self._itemprop_content(product, "url")
        if not title or not rel_url:
            return None

        image = product.find(attrs={"itemprop": "image"})
        image_url = image.get("src") if image else None

        offers = product.find_all(attrs={"itemtype": re.compile(r"schema\.org/Offer")})
        best = self._best_offer(offers)
        if not best:
            return None

        price, store, valid_until, offer_discount = best

        # Zľavu udáva buď badge pri produkte, alebo konkrétna ponuka.
        discount = offer_discount or self._find_discount(product)
        if discount is None:
            # Časť položiek v letáku je bez uvedenej zľavy (len akciová cena).
            # Bez zľavy nevieme dopočítať pôvodnú cenu a na deal stránke by
            # z toho bola karta s "-0 %" — takže ju rovno preskočíme.
            return None

        return DealCandidate(
            title=title,
            deal_price=price,
            url=urljoin(BASE_URL, rel_url),
            source=self.source_name,
            store=store,
            explicit_discount_percent=discount,
            image_url=image_url,
            valid_until=valid_until,
            category_hint=category_hint,
        )

    def _best_offer(self, offers) -> Optional[tuple[float, str, Optional[str], Optional[float]]]:
        """Z ponúk viacerých predajcov vyberie tú s najnižšou cenou."""
        parsed: list[tuple[float, str, Optional[str], Optional[float]]] = []

        for offer in offers:
            price = parse_price(self._itemprop_content(offer, "price"))
            if price is None:
                continue

            seller = offer.find(attrs={"itemprop": "seller"})
            store = self._itemprop_content(seller, "name") if seller else ""

            text = offer.get_text(" ", strip=True)
            valid_match = _VALID_UNTIL_RE.search(text)
            valid_until = valid_match.group(1) if valid_match else None

            parsed.append((price, store or "", valid_until, self._find_discount(offer)))

        if not parsed:
            return None
        return min(parsed, key=lambda item: item[0])

    @staticmethod
    def _itemprop_content(node, prop: str) -> Optional[str]:
        """
        Prečíta hodnotu microdata vlastnosti. Hodnota býva v atribúte
        content=, ale niekedy len ako text uzla — skúsime oboje.
        """
        if node is None:
            return None
        el = node.find(attrs={"itemprop": prop})
        if el is None:
            return None
        value = el.get("content") or el.get_text(strip=True)
        return value.strip() if value else None

    @staticmethod
    def _find_discount(node) -> Optional[float]:
        match = _DISCOUNT_RE.search(node.get_text(" ", strip=True))
        if not match:
            return None
        value = float(match.group(1))
        return value if 0 < value < 100 else None
