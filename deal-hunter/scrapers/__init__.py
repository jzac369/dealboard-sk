"""
Register zdrojov. Nový zdroj sa pridá sem a hneď funguje — main.py aj
deduplikácia s ním pracujú univerzálne.
"""

from scrapers.feeds import FeedsScraper
from scrapers.shop_feeds import ShopFeedsScraper
from scrapers.zlacnene import ZlacneneScraper

# Kľúč = názov, ktorý sa píše do premennej ENABLED_SCRAPERS.
AVAILABLE_SCRAPERS = {
    "zlacnene": ZlacneneScraper,
    "feeds": FeedsScraper,
    "shop_feeds": ShopFeedsScraper,
}
