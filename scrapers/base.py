"""
Spoločný dátový model a základná trieda pre všetky scrapery zdrojov.
Každý nový zdroj (Alza, zlacnene.sk, kompaszliav.sk, ...) implementuje
triedu BaseScraper a vracia zoznam DealCandidate objektov.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import re


@dataclass
class DealCandidate:
    title: str
    old_price: float
    new_price: float
    source_url: str
    source_site: str
    image_url: Optional[str] = None
    currency: str = "EUR"
    category_guess: Optional[str] = None
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def discount_percent(self) -> float:
        if self.old_price <= 0:
            return 0.0
        return round((self.old_price - self.new_price) / self.old_price * 100, 1)

    def to_firestore_dict(self) -> dict:
        return {
            "title": self.title,
            "oldPrice": self.old_price,
            "newPrice": self.new_price,
            "discountPercent": self.discount_percent,
            "currency": self.currency,
            "sourceUrl": self.source_url,
            "sourceSite": self.source_site,
            "imageUrl": self.image_url,
            "categoryGuess": self.category_guess,
            "scrapedAt": self.scraped_at,
            "status": "pending",
        }


def parse_price(raw: str) -> Optional[float]:
    """
    Prevedie textovú reprezentáciu ceny (napr. '1 399,50 €', '23,12€', '1399.50')
    na float. Vráti None, ak sa cenu nepodarí rozparsovať.
    """
    if not raw:
        return None
    cleaned = raw.replace("\xa0", " ").strip()
    cleaned = re.sub(r"[^\d,.\s]", "", cleaned)
    cleaned = cleaned.replace(" ", "")
    # slovenský formát používa čiarku ako desatinný oddeľovač
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


class BaseScraper:
    """Rozhranie, ktoré musí implementovať každý zdroj dealov."""

    source_name: str = "unknown"

    def fetch_candidates(self) -> list[DealCandidate]:
        raise NotImplementedError(
            f"Scraper pre {self.source_name} musí implementovať fetch_candidates()"
        )
