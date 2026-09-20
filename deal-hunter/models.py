"""
Dátový model kandidáta na deal + mapovanie na Firestore schému henkukaj.sk.

DÔLEŽITÉ: názvy polí v to_firestore_dict() musia PRESNE sedieť s tým, čo
číta index.html a admin.html na henkukaj.sk:

    title, store, category, originalPrice, dealPrice, currency, url,
    imageUrl, description, author, votes, comments, discountPercent,
    status, expired, timestamp

Ak sa tu názov rozíde (napr. newPrice namiesto dealPrice), deal sa síce
zapíše, ale na stránke sa vykreslí prázdna karta.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional
import re
import unicodedata

from descriptions import build_description

# Kategórie presne tak, ako ich ponúka formulár na henkukaj.sk (index.html).
VALID_CATEGORIES = [
    "Elektronika",
    "Dom & Záhrada",
    "Móda",
    "Hračky",
    "Šport",
    "Jedlo & Nápoje",
    "Cestovanie",
    "Iné",
]

# Kľúčové slová -> kategória. Poradie rozhoduje: prvá zhoda vyhráva,
# preto sú špecifickejšie kategórie hore.
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("Elektronika", (
        "notebook", "laptop", "mobil", "smartfon", "telefon", "televizor",
        "monitor", "sluchadl", "reproduktor", "tablet", "fotoaparat",
        "smartwatch", "konzola", "playstation", "xbox", "ssd", "usb",
        "router", "tlaciaren", "klavesnic", "powerbank", "nabijac", "herna",
    )),
    ("Jedlo & Nápoje", (
        "cokolad", "kava", "pivo", "vino", "syr", "maso", "bravcov",
        "hovadzi", "kuracie", "mlieko", "jogurt", "chlieb", "pecivo", "ovocie",
        "zelenina", "jablk", "banan", "karfiol", "zemiak", "cukor", "muka",
        "olej", "ryza", "cestovin", "napoj", "dzus", "salam", "paradajk",
        "maslo", "vajcia", "susienk", "zmrzlin", "konzerv", "klobas", "smotan",
        "hrozno", "figy", "paprik", "uhork", "cibul", "mrkv", "kapust", "salat",
        "citron", "pomaranc", "jahod", "maliny", "hruska", "broskyn", "slivk",
        "radler", "kofola", "malinovk", "sirup", "horcic", "kecup", "majonez",
        "ryba", "losos", "tuniak", "saláma", "parky", "spekacky", "tvaroh",
    )),
    ("Dom & Záhrada", (
        "sedacia", "gauc", "postel", "matrac", "stolicka", "skrin",
        "kuchyn", "hrniec", "panvic", "vysavac", "prack", "chladnick", "rura",
        "mikrovln", "kosacka", "gril", "zahrad", "naradie", "vrtacka",
        "lampa", "koberec", "zaclon", "vankus", "perina", "uterak", "nabytok",
    )),
    ("Móda", (
        "tricko", "nohavice", "bunda", "kabat", "mikina", "kosela", "saty",
        "sukna", "topanky", "tenisky", "obuv", "kabelka", "batoh", "opasok",
        "ponozky", "bielizen", "sperk", "okuliare", "cepic",
    )),
    ("Šport", (
        "bicykel", "cyklo", "fitnes", "fitness", "cinky", "bezeck", "lyze",
        "snowboard", "korcule", "lopta", "stan", "spacak", "turistick",
        "plavk", "joga", "trenaz", "posilnov",
    )),
    ("Hračky", (
        "hracka", "hracky", "lego", "puzzle", "plysov", "babik",
        "stavebnic", "spolocenska hra", "kocik", "auticko",
    )),
    ("Cestovanie", (
        "letenk", "dovolenk", "zajazd", "hotel", "ubytovan", "wellness",
        "kupele", "pobyt", "aquapark",
    )),
]


def _strip_diacritics(text: str) -> str:
    """'Bravčové karé' -> 'bravcove kare' — aby kľúčové slová sedeli bez ohľadu na diakritiku."""
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def guess_category(title: str, hint: Optional[str] = None) -> str:
    """Odhadne kategóriu z názvu produktu. Admin ju vie pred schválením prepísať."""
    if hint and hint in VALID_CATEGORIES:
        return hint

    haystack = _strip_diacritics(title)
    for category, keywords in _CATEGORY_KEYWORDS:
        for keyword in keywords:
            if _strip_diacritics(keyword) in haystack:
                return category
    return "Iné"


def parse_valid_until(raw: Optional[str]) -> Optional[str]:
    """
    '22.9.2026' -> '2026-09-22'. Vráti None, ak sa dátum nedá prečítať.

    Textový tvar sa nedá porovnávať ("3.1.2027" < "22.9.2026" ako text),
    preto si popri ňom držíme aj ISO tvar - podľa neho vie agent deal
    automaticky označiť za exspirovaný.
    """
    if not raw:
        return None
    parts = raw.strip().rstrip(".").split(".")
    if len(parts) != 3:
        return None
    try:
        day, month, year = (int(p) for p in parts)
        return date(year, month, day).isoformat()
    except ValueError:
        # Neexistujúci dátum (31.2.) alebo nečíselný text.
        return None


def parse_price(raw: Optional[str]) -> Optional[float]:
    """
    '1 399,50 EUR' / '23,12' / '1399.50' -> float. Vráti None, ak sa to nepodarí.

    Pozor na slovenský formát: čiarka je desatinný oddeľovač, medzera
    (aj nezalomiteľná) je oddeľovač tisícov.
    """
    if not raw:
        return None

    cleaned = raw.replace("\xa0", " ").replace(" ", " ").strip()
    # Rozsah cien ("2,99 - 3,29") -> berieme tú nižšiu, teda prvú.
    if " - " in cleaned:
        cleaned = cleaned.split(" - ")[0]

    cleaned = re.sub(r"[^\d,.\s]", "", cleaned).replace(" ", "")
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        # '1.399,50' -> bodka je oddeľovač tisícov
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")

    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value > 0 else None


@dataclass
class DealCandidate:
    """Jeden nájdený deal, ešte pred zápisom do Firestore."""

    title: str
    deal_price: float
    url: str
    source: str                       # napr. "zlacnene.sk" - odkiaľ sme to našli
    store: str = ""                   # napr. "BILLA" - kde sa to dá kúpiť
    original_price: Optional[float] = None
    explicit_discount_percent: Optional[float] = None  # ak ho zdroj udáva priamo
    image_url: Optional[str] = None
    description: str = ""
    category_hint: Optional[str] = None
    valid_until: Optional[str] = None  # dátum platnosti, ak ho zdroj pozná
    currency: str = "€"
    found_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def discount_percent(self) -> float:
        """
        Zľava v %. Uprednostní hodnotu, ktorú udáva zdroj - tá býva presnejšia
        než dopočet, lebo zdroj pozná bežnú cenu aj vtedy, keď ju nezobrazuje.
        """
        if self.explicit_discount_percent is not None:
            return round(self.explicit_discount_percent, 1)
        if self.original_price and self.original_price > self.deal_price:
            return round(
                (self.original_price - self.deal_price) / self.original_price * 100, 1
            )
        return 0.0

    @property
    def effective_original_price(self) -> float:
        """
        Pôvodná cena. Ak ju zdroj neuvádza, ale pozná % zľavy, dopočítame ju -
        stránka pole originalPrice zobrazuje a bez neho karta vyzerá neúplne.
        """
        if self.original_price and self.original_price > self.deal_price:
            return round(self.original_price, 2)
        if self.explicit_discount_percent and 0 < self.explicit_discount_percent < 100:
            return round(self.deal_price / (1 - self.explicit_discount_percent / 100), 2)
        return round(self.deal_price, 2)

    @property
    def valid_until_iso(self) -> Optional[str]:
        """Dátum platnosti v tvare YYYY-MM-DD, ak sa dá prečítať."""
        return parse_valid_until(self.valid_until)

    @property
    def is_already_expired(self) -> bool:
        """True, ak akcia skončila skôr, než sme ju stihli navrhnúť."""
        iso = self.valid_until_iso
        return bool(iso and iso < date.today().isoformat())

    @property
    def dedupe_key(self) -> str:
        """
        Kľúč na rozpoznanie duplicity. Nie URL - ten istý produkt má na rôznych
        zdrojoch rôzne URL. Kombinácia obchod + normalizovaný názov + cena
        zachytí aj to, keď ten istý deal nájdu dva scrapery.
        """
        title_key = re.sub(r"[^a-z0-9]+", "", _strip_diacritics(self.title))[:60]
        return f"{_strip_diacritics(self.store)}|{title_key}|{self.deal_price:.2f}"

    def to_firestore_dict(self) -> dict:
        """
        Prevod na dokument presne v schéme, ktorú číta henkukaj.sk.
        Pole 'timestamp' sem zámerne NEPATRÍ - dopĺňa ho firestore_client
        cez SERVER_TIMESTAMP, aby čas určil server, nie bežiaci scraper.
        """
        category = guess_category(self.title, self.category_hint)

        # Ak zdroj vlastný popis nedal (letáky ho nemajú takmer nikdy),
        # zložíme ho z dát. Popis od zdroja má prednosť — je konkrétnejší.
        description = self.description.strip()
        if not description:
            description = build_description(
                store=self.store,
                category=category,
                old_price=self.effective_original_price,
                new_price=self.deal_price,
                discount_percent=self.discount_percent,
                valid_until=self.valid_until,
                seed=self.dedupe_key,
            )
        elif self.valid_until:
            description = f"{description}\n\nPlatí do: {self.valid_until}"

        return {
            # -- polia, ktoré zobrazuje stránka --
            "title": self.title.strip()[:200],
            "store": self.store.strip() or self.source,
            "category": category,
            "originalPrice": self.effective_original_price,
            "dealPrice": round(self.deal_price, 2),
            "discountPercent": round(self.discount_percent),
            "currency": self.currency,
            "url": self.url,
            "imageUrl": self.image_url,
            "description": description[:1000],
            "votes": 0,
            "comments": 0,
            "status": "pending",
            "expired": False,
            # -- metadáta agenta (stránka ich ignoruje, pomáhajú pri ladení) --
            "autoGenerated": True,
            "sourceSite": self.source,
            "dedupeKey": self.dedupe_key,
            "foundAt": self.found_at,
            "validUntil": self.valid_until,
            # ISO tvar sa dá porovnávať aj dotazovať - podľa neho beží
            # automatická exspirácia.
            "validUntilISO": self.valid_until_iso,
        }
