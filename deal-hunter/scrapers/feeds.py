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


# Ako sa obchod volá na stránke. Kľúč je doména z odkazu na produkt.
# Obchod NEBERIEME z MANUFACTURER / brand - to je výrobca, nie predajca,
# a na stránke by sa potom písalo "Hanah Home", hoci to predáva 4Home.
_OBCHODY = {
    "4home.sk": "4Home", "gymbeam.sk": "GymBeam", "emos.sk": "EMOS",
    "cbelektro.sk": "CBelektro", "e-spotrebice.sk": "E-spotrebice",
    "merkurymarket.sk": "MerkuryMarket", "mikona.sk": "Mikona",
    "kinekus.sk": "Kinekus", "efarby.sk": "eFarby", "lidl.sk": "Lidl",
    "iprobio.sk": "iProbio", "lieky24.sk": "Lieky24",
    "benulekaren.sk": "BENU lekáreň", "pantarhei.sk": "Panta Rhei",
    "inlibri.online": "inLibri", "knihyprekazdeho.sk": "Knihy pre každého",
    "preskoly.sk": "PreŠkoly", "chutnekytice.sk": "Chutné kytice",
    "faxcopy.sk": "Faxcopy", "colorland.com": "Colorland",
}


def obchod_z_url(url: str) -> str:
    """Názov predajcu podľa domény odkazu; neznámu doménu aspoň učeše.
    Názvy zadané v admine (pri feede) majú prednosť pred tabuľkou tu."""
    from urllib.parse import urlparse

    host = (urlparse(url or "").hostname or "").lower()
    cisty = host.replace("www.", "")
    if cisty in config.NAZVY_OBCHODOV:
        return config.NAZVY_OBCHODOV[cisty]
    for domena, nazov in _OBCHODY.items():
        if host == domena or host.endswith("." + domena):
            return nazov
    zaklad = host.removeprefix("www.").split(".")[0] if host else ""
    return zaklad[:1].upper() + zaklad[1:]


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
        # Parsovanie a výber sú zámerne oddelené: parse_feed len číta,
        # čo vo feede je (a tak sa dá testovať), _vyber rozhoduje, čo
        # z toho pôjde ďalej.
        return self._vyber(self.parse_feed(xml_text, feed_url), feed_url)

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
            # Google Merchant chodí v dvoch obaloch: RSS 2.0 s <item> a
            # Atom s <entry>. Polia vnútri sú rovnaké. CBelektro posiela
            # Atom a bez tejto vetvy by sme z jeho 67 000 položiek
            # nenašli ani jednu - feed by vyzeral ako prázdny.
            items = root.findall(".//item")
            if not items:
                items = (root.findall(".//{http://www.w3.org/2005/Atom}entry")
                         or root.findall(".//entry"))
            parser = self._parse_google_item

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

    @staticmethod
    def _vyber(candidates: list[DealCandidate], feed_url: str = "") -> list[DealCandidate]:
        """
        Rozhodne, čo z feedu pôjde ďalej.

        PREČO TO JE POTREBNÉ
        Položka bez ceny pred zľavou ide do sledovania cien (price_watch),
        ktoré má tvrdý strop: Firestore dovolí dokument najviac 1 MiB a
        do 20 vedierok sa zmestí rádovo 216 000 produktov. Schválené
        feedy majú spolu vyše 800 000 položiek - keby išli všetky, strop
        by sa prekročil a zápisy by začali zlyhávať.

        PRAVIDLO
        - Feed, ktorý zľavy uvádza sám (ORIGINAL_PRICE, sale_price):
          obchod nám hovorí, čo je v akcii. Berieme len tie položky a
          nič nesledujeme. Položka bez zľavy v takom feede jednoducho nie
          je v akcii - merať jej cenu by stálo miesto a nič by neprinieslo.
        - Feed, ktorý zľavy neuvádza: iná cesta nie je, treba sledovať.
          Ale najviac FEED_WATCH_MAX najdrahších položiek - pri cenovom
          prepade je to tovar, ktorý ľudí zaujíma. (Strop podľa poradia
          vo feede by bol náhodný výber.)
        """
        zdroj = feed_url.split("/")[2] if feed_url.count("/") >= 2 else "feed"

        # Lacné položky von ešte pred sledovaním cien - to beží PRED
        # is_sane, takže bez tohto by sa do vedierok dostala každá
        # pätnásťcentová skrutka.
        pred = len(candidates)
        candidates = [c for c in candidates if c.deal_price >= config.MIN_DEAL_PRICE]
        if pred - len(candidates):
            logger.info("%s: vynechaných %d položiek pod %.2f €",
                        zdroj, pred - len(candidates), config.MIN_DEAL_PRICE)

        so_zlavou = [c for c in candidates if c.original_price]

        # Feed, v ktorom je "v akcii" väčšina sortimentu, nemá skutočnú
        # pôvodnú cenu - má trvalo prečiarknutú. 4Home tvrdí zľavu pri
        # 81 % produktov a stolík za 33 € "zlacnený z 293 €" by bol na
        # stránke najväčší deal dňa. Takému feedu v zľavách neveríme a
        # zistíme ich sami sledovaním cien, rovnako ako pri feede bez zliav.
        if candidates and len(so_zlavou) / len(candidates) > config.FEED_MAX_SALE_SHARE:
            logger.warning("%s: v akcii %d %% sortimentu — prečiarknutým cenám neverím, "
                           "zľavy overím sledovaním cien",
                           zdroj, round(len(so_zlavou) / len(candidates) * 100))
            for c in candidates:
                c.original_price = None
                c.explicit_discount_percent = None
            so_zlavou = []

        if so_zlavou:
            logger.info("%s: uvádza zľavy — v akcii %d z %d, sledovanie netreba",
                        zdroj, len(so_zlavou), len(candidates))
            return so_zlavou

        if len(candidates) > config.FEED_WATCH_MAX:
            logger.info("%s: zľavy neuvádza — sledujem %d najdrahších z %d",
                        zdroj, config.FEED_WATCH_MAX, len(candidates))
            candidates = sorted(candidates, key=lambda c: c.deal_price,
                                reverse=True)[: config.FEED_WATCH_MAX]
        else:
            logger.info("%s: zľavy neuvádza — sledujem všetkých %d",
                        zdroj, len(candidates))
        return candidates

    def _parse_google_item(self, item: ET.Element) -> Optional[DealCandidate]:
        title = _first(item, f"{_G_NS}title", "title")
        url = _first(item, f"{_G_NS}link", "link")
        # Bežná a akciová cena. Keď akciová chýba, položku nezahadzujeme -
        # rozhodne o nej sledovanie cien (price_watch).
        regular = parse_price(_first(item, f"{_G_NS}price", "price"))
        sale = parse_price(_first(item, f"{_G_NS}sale_price", "sale_price"))

        if not title or not url:
            return None
        # Bez akciovej ceny berieme bežnú a necháme rozhodnúť sledovanie cien.
        price = sale if sale is not None else regular
        if price is None:
            return None
        original = regular if (sale is not None and regular and sale < regular) else None

        return DealCandidate(
            title=title,
            deal_price=price,
            original_price=original,
            url=url,
            source=self.source_name,
            direct_url=True,   # feed dáva odkaz rovno na produkt
            store=obchod_z_url(url),
            group_id=_first(item, f"{_G_NS}item_group_id", "item_group_id"),
            image_url=_first(item, f"{_G_NS}image_link", "image_link"),
            description=_first(item, f"{_G_NS}description", "description") or "",
        )

    def _parse_heureka_item(self, item: ET.Element) -> Optional[DealCandidate]:
        title = _first(item, "PRODUCTNAME", "PRODUCT")
        url = _first(item, "URL")
        price = parse_price(_first(item, "PRICE_VAT", "PRICE"))

        if not title or not url or price is None:
            return None

        # Heureka formát bežnú cenu štandardne neuvádza. Ak ju partner
        # posiela vo vlastnom tagu, použijeme ju. Ak nie, položku
        # NEZAHADZUJEME - pošleme ju na sledovanie ceny (price_watch)
        # a zverejní sa, keď cena reálne spadne. Zahadzovanie by pri
        # feedoch znamenalo, že neprejde takmer nič.
        # ORIGINAL_PRICE je tu zámerne prvé: presne tak volá bežnú cenu
        # feed GymBeamu a bez neho by sa jeho 9 500 položiek tvárilo, že
        # cenu pred zľavou neuvádzajú, a museli by roky čakať na
        # sledovanie cien. Ostatné názvy používajú iné e-shopy.
        original = parse_price(_first(
            item,
            "ORIGINAL_PRICE", "PRICE_BEFORE_DISCOUNT",
            "STANDARD_PRICE", "LIST_PRICE", "PRICE_STANDARD",
        ))
        if original is not None and original <= price:
            original = None

        return DealCandidate(
            title=title,
            deal_price=price,
            original_price=original,
            url=url,
            source=self.source_name,
            direct_url=True,   # feed dáva odkaz rovno na produkt
            store=obchod_z_url(url),
            group_id=_first(item, "ITEMGROUP_ID"),
            image_url=_first(item, "IMGURL"),
            description=_first(item, "DESCRIPTION") or "",
        )


# ── diagnostika ───────────────────────────────────────────────────────

def describe_feed(xml_text: str) -> dict:
    """
    Popíše štruktúru feedu BEZ toho, aby prezradila čokoľvek citlivé.

    Slúži na doladenie parsera na konkrétnu sieť: adresa feedu obsahuje
    partnerské ID, takže sa nikdy nesmie dostať do logu. Preto z odkazov
    hlásime len doménu a NÁZVY parametrov, nikdy ich hodnoty.
    """
    import xml.etree.ElementTree as ET
    from collections import Counter
    from urllib.parse import urlparse, parse_qs

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return {"chyba": f"neplatné XML: {e}"}

    shop_items = root.findall(".//SHOPITEM")
    items = shop_items or root.findall(".//item")
    fmt = "Heureka (SHOPITEM)" if shop_items else "Google/RSS (item)"

    tags = Counter()
    hosts = Counter()
    params = Counter()
    s_price = s_orig = 0

    for item in items[:400]:
        for child in item:
            name = child.tag.split("}")[-1]
            tags[name] += 1
            if name in ("PRICE_VAT", "PRICE", "price", "sale_price"):
                s_price += 1
            if name in ("PRICE_BEFORE_DISCOUNT", "STANDARD_PRICE", "LIST_PRICE"):
                s_orig += 1
            if name in ("URL", "link", "LINK") and (child.text or "").startswith("http"):
                parsed = urlparse(child.text.strip())
                hosts[parsed.netloc] += 1
                for key in parse_qs(parsed.query):
                    params[key] += 1

    tracking = {"a_aid", "a_bid", "a_cid", "utm_source", "utm_medium", "aff", "affid", "pid", "clickref"}
    return {
        "format": fmt,
        "poloziek_celkom": len(items),
        "najcastejsie_tagy": [t for t, _ in tags.most_common(14)],
        "ma_aktualnu_cenu": s_price > 0,
        "ma_povodnu_cenu": s_orig > 0,
        "domeny_odkazov": [h for h, _ in hosts.most_common(4)],
        "parametre_v_odkazoch": sorted(params),
        "odkazy_vyzeraju_otagovane": bool(tracking & set(params)),
    }
