"""Spoločné rozhranie pre všetky zdroje dealov."""

from models import DealCandidate


class BaseScraper:
    """
    Rozhranie, ktoré musí implementovať každý zdroj.

    Pravidlo: fetch_candidates() nesmie nikdy vyhodiť výnimku kvôli jednej
    chybnej položke. Zlú položku preskočí a pokračuje — inak by jeden
    rozbitý produkt zhodil celý denný beh.
    """

    source_name: str = "unknown"

    def fetch_candidates(self) -> list[DealCandidate]:
        raise NotImplementedError(
            f"Scraper {self.source_name} musí implementovať fetch_candidates()"
        )
