from scrapers.alza import AlzaScraper
from scrapers.allegro import AllegroScraper

# Sem sa pridajú ďalšie zdroje, napr.:
# from scrapers.zlacnene import ZlacneneScraper

ALL_SCRAPERS = [
    AllegroScraper,
    AlzaScraper,  # momentálne blokovaný Cloudflare ochranou, necháme pre budúcnosť
]
