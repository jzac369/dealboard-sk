"""
Produktové feedy slovenských e-shopov (formát Heureka).

PREČO PRÁVE TOTO
Pôvodný zdroj (zlacnene.sk) stojí na letákoch potravinových a
nábytkárskych reťazcov. Elektronika v ňom nie je - jej kategórie na
tom webe vôbec neexistujú a vracajú náhradný obsah z inej kategórie.
Priame sťahovanie z veľkých e-shopov je zavreté: Alza, Notino, Mall aj
Heureka vracajú HTTP 403, Martinus anti-bot výzvu.

Tieto feedy sú iná vec. E-shop ich zverejňuje zámerne a presne na to,
aby ich čítali porovnávače - je to jeho vlastný kanál na propagáciu
tovaru. Obe adresy nižšie sú verejné a robots.txt oboch obchodov má
"Allow: /".

ČO Z FEEDU VIEME A ČO NIE
Heureka formát uvádza len aktuálnu cenu, nie cenu pred zľavou. Zľava sa
teda z feedu spočítať nedá a všetko ide cez sledovanie cien
(price_watch): produkt sa zverejní až vtedy, keď jeho cena reálne
spadne pod doteraz najnižšiu videnú. Prvé dni preto tento zdroj nevydá
nič - najprv sa musí nazbierať porovnanie.

PREČO FILTRUJEME UŽ TU
Jeden z feedov má 51 302 položiek a 128 MB. Väčšina sú vrtáky, drezy a
naberačky. Sledovať ich všetky by nemalo zmysel a zbytočne by to
napchalo vedierka price_watch. Filter necháva zhruba 7 800 položiek,
ktoré niekoho naozaj zaujímajú.
"""

from __future__ import annotations

import logging
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import config
from models import DealCandidate, parse_price
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class ShopFeed:
    """Jeden e-shop a jeho verejný feed."""

    def __init__(self, store: str, url: str, host: str):
        self.store = store      # ako sa obchod zobrazí na stránke
        self.url = url          # adresa feedu
        self.host = host        # doména, na ktorú MUSIA viesť odkazy


# Overené 23. 9. 2026: obe adresy vracajú platný Heureka XML a robots.txt
# oboch obchodov povoľuje "/". Tretí kandidát (xzone.sk) je tu zámerne
# NIE: na slovenskej adrese servíruje český obchod - odkazy vedú na
# xzone.cz a ceny sú v korunách.
SHOP_FEEDS = [
    # Ten istý sortiment predáva aj andreashop.sk s rovnakým feedom, ale
    # jeho certifikát je 23. 9. 2026 po expirácii - spojenie sa nedá
    # overiť. Overovanie certifikátu nevypíname, berieme tpd.sk, ktorý
    # má platný a odkazy vo feede vedú naňho.
    ShopFeed("TPD",     "https://www.tpd.sk/heureka.xml",      "tpd.sk"),
    ShopFeed("iStores", "https://www.istores.sk/feed/heureka", "istores.sk"),
]

# Čo nás zaujíma. Porovnáva sa s kategóriou aj názvom, malými písmenami
# a bez ohľadu na diakritiku zdroja (preto sú tu obe podoby).
ZAUJIMAVE = (
    "notebook", "monitor", "televíz", "televiz", "tablet", "slúchad", "sluchad",
    "telefón", "telefon", "hodinky", "konzol", "fotoaparát", "fotoaparat",
    "reproduktor", "chladnič", "chladnic", "práčk", "prack", "umývačk", "umyvack",
    "kávovar", "kavovar", "vysávač", "vysavac", "airfryer", "fritéz", "fritez",
    "mikrovln", "herné", "herna", "grafick", "procesor", "klávesnic", "klavesnic",
    "myš", "apple", "dron",
)

# Pod päťdesiat eur sú v týchto feedoch prevažne káble, obaly a
# náhradné diely. Zľava na osemeurovom puzdre nie je deal.
MIN_CENA = 50.0

# Poistka proti feedu, ktorý sa nafúkne alebo sa zmení jeho štruktúra.
MAX_Z_JEDNEHO_FEEDU = 12000


def _text(item: ET.Element, *mena: str) -> str:
    for m in mena:
        uzol = item.find(m)
        if uzol is not None and uzol.text and uzol.text.strip():
            return uzol.text.strip()
    return ""


class ShopFeedsScraper(BaseScraper):
    source_name = "shop-feeds"

    def fetch_candidates(self) -> list[DealCandidate]:
        vsetky: list[DealCandidate] = []
        for shop in SHOP_FEEDS:
            try:
                najdene = self._jeden_feed(shop)
                logger.info("%s: %d sledovaných položiek", shop.store, len(najdene))
                vsetky.extend(najdene)
            except Exception as e:
                # Jeden nedostupný obchod nesmie zhodiť ostatné.
                logger.error("Feed obchodu %s zlyhal: %s", shop.store, e, exc_info=True)
        return vsetky

    def _jeden_feed(self, shop: ShopFeed) -> list[DealCandidate]:
        # Sťahujeme prúdom a parsujeme po položkách. Načítať 128 MB do
        # pamäti naraz a až potom to dať ET.fromstring() by znamenalo
        # rádovo gigabajt pamäti pre jeden obchod.
        hlavicky = {
            "User-Agent": config.USER_AGENT,
            "Accept": "application/xml, text/xml",
        }
        ziadost = urllib.request.Request(shop.url, headers=hlavicky)
        kontext = ssl.create_default_context()

        vysledok: list[DealCandidate] = []
        preskocene_cudzie = 0
        spolu = 0

        with urllib.request.urlopen(ziadost, timeout=240, context=kontext) as odpoved:
            for udalost, prvok in ET.iterparse(odpoved, events=("end",)):
                if prvok.tag != "SHOPITEM":
                    continue
                spolu += 1
                kandidat, cudzi = self._z_polozky(prvok, shop)
                if cudzi:
                    preskocene_cudzie += 1
                if kandidat:
                    vysledok.append(kandidat)
                # Uvoľníme spracovanú položku, inak si strom aj tak
                # postupne zoberie celú pamäť.
                prvok.clear()
                if len(vysledok) >= MAX_Z_JEDNEHO_FEEDU:
                    logger.warning(
                        "%s: dosiahnutý strop %d položiek, zvyšok feedu preskakujem",
                        shop.store, MAX_Z_JEDNEHO_FEEDU,
                    )
                    break

        # Feed, ktorý vedie inam, než sľubuje. Presne to robí xzone.sk:
        # na slovenskej adrese vracia český obchod. Radšej nič než
        # dealy s cenami v inej mene a odkazmi do cudzieho e-shopu.
        if spolu and preskocene_cudzie > spolu * 0.5:
            logger.error(
                "%s: %d z %d položiek vedie mimo %s — feed vyzerá na iný trh, zahadzujem ho",
                shop.store, preskocene_cudzie, spolu, shop.host,
            )
            return []

        logger.info("%s: prezreté %d položiek, vybrané %d", shop.store, spolu, len(vysledok))
        return vysledok

    def _z_polozky(self, item: ET.Element, shop: ShopFeed) -> tuple[DealCandidate | None, bool]:
        """Vráti (kandidát alebo None, či odkaz vedie mimo obchodu)."""
        nazov = _text(item, "PRODUCTNAME", "PRODUCT")
        odkaz = _text(item, "URL")
        cena = parse_price(_text(item, "PRICE_VAT", "PRICE"))

        if not nazov or not odkaz or cena is None:
            return None, False

        cudzi = shop.host not in (urlparse(odkaz).netloc or "").lower()
        if cudzi:
            return None, True

        if cena < MIN_CENA:
            return None, False

        kategoria = _text(item, "CATEGORYTEXT")
        text = f"{kategoria} {nazov}".lower()
        if not any(s in text for s in ZAUJIMAVE):
            return None, False

        return DealCandidate(
            title=nazov,
            deal_price=cena,
            original_price=None,     # feed ju neuvádza — rozhodne sledovanie cien
            url=odkaz,
            source=self.source_name,
            direct_url=True,         # odkaz vedie rovno na produkt
            store=shop.store,
            image_url=_text(item, "IMGURL") or None,
            description=_text(item, "DESCRIPTION"),
            category_hint=kategoria.split("|")[-1].strip() or None,
        ), False
