"""
Overí, že sandboxový kľúč Kayaku funguje, a ohmatá cesty k ďalším API.

Dokumentácia je za prihlásením, takže cesty okrem autocomplete nepoznáme
a skúšame tie najpravdepodobnejšie. Je to sandbox - testovacie prostredie
presne na toto - ale aj tak voláme striedmo, s pauzou medzi pokusmi.

Spustenie: python kayak_skuska.py
"""
import json
import logging
import os
import sys
import time
import urllib.error

import kayak

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kayak")

# Čo chceme nájsť: "najlacnejšie ceny, aké naposledy videli cestujúci".
# Tvar ciest odhadujeme podľa jedinej známej (autocomplete/v1/flights).
KANDIDATI = [
    "/api/affiliate/flights/v1/price-insights",
    "/api/affiliate/price-insights/v1/flights",
    "/api/affiliate/flights/v1/priceinsights",
    "/api/affiliate/insights/v1/flights",
    "/api/affiliate/flights/v1/prices",
]

PARAMETRE = {"origin": "BTS", "destination": "LON", "currency": "EUR"}


def ukazka(data, znakov=600):
    return json.dumps(data, ensure_ascii=False)[:znakov]


def telo_chyby(e) -> str:
    """Text chybovej odpovede. Server v ňom býva povie, čo mu chýba."""
    try:
        t = e.read().decode("utf-8", "replace")[:300]
    except Exception:
        return ""
    # Kľúč by sa v odpovedi objaviť nemal, ale radšej ho zamažeme.
    return t.replace(kayak.KLUC, "***") if kayak.KLUC else t


def ohmataj() -> int:
    """Vypíše, čo server odpovedá na rôzne názvy parametra s kľúčom."""
    import urllib.parse, urllib.request
    nazvy = ["apikey", "apiKey", "api_key", "key", "affiliateKey", "affiliate_key"]
    hladane = ["searchTerm", "term", "query", "search"]
    logger.info("--- Názov parametra s kľúčom ---")
    for n in nazvy:
        for h in hladane[:1]:
            url = (kayak.ZAKLAD + kayak.AUTOCOMPLETE + "?" +
                   urllib.parse.urlencode({n: kayak.KLUC, h: "Bratislava"}))
            try:
                with urllib.request.urlopen(urllib.request.Request(
                        url, headers={"Accept": "application/json",
                                      "User-Agent": "henkukaj.sk/1.0"}), timeout=20) as o:
                    logger.info("%-14s OK — %s", n, o.read().decode("utf-8")[:400])
                    return 0
            except urllib.error.HTTPError as e:
                logger.info("%-14s HTTP %s — %s", n, e.code, telo_chyby(e))
            except Exception as e:
                logger.info("%-14s %s", n, type(e).__name__)
            time.sleep(1)
    return 1


def main() -> int:
    logger.info("=== Kayak sandbox — skúška kľúča ===")
    if os.environ.get("OHMATAJ"):
        return ohmataj()
    try:
        hlavicky, parametre = kayak.najdi_sposob()
    except kayak.KayakChyba as e:
        logger.error("%s", e)
        return 1
    logger.info("Kľúč prijatý. Posiela sa cez: %s",
                ", ".join(list(hlavicky) + list(parametre)) or "nič?")

    logger.info("--- Autocomplete (jediná istá cesta) ---")
    try:
        data = kayak.zavolaj(kayak.AUTOCOMPLETE, searchTerm="Bratislava")
        logger.info("Odpoveď: %s", ukazka(data))
    except Exception as e:
        logger.warning("Autocomplete zlyhalo: %s", e)

    logger.info("--- Hľadám Price Insights ---")
    for cesta in KANDIDATI:
        try:
            data = kayak.zavolaj(cesta, **PARAMETRE)
        except urllib.error.HTTPError as e:
            logger.info("%-46s HTTP %s", cesta, e.code)
            time.sleep(1)
            continue
        except Exception as e:
            logger.info("%-46s %s", cesta, type(e).__name__)
            time.sleep(1)
            continue
        logger.info("%-46s OK", cesta)
        logger.info("Odpoveď: %s", ukazka(data, 1500))
        return 0

    logger.info("Ani jedna z odhadovaných ciest nesedela — presnú cestu")
    logger.info("treba odpísať z dokumentácie po prihlásení.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
