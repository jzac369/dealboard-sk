"""
Overí sandbox Kayaku: kľúč, vyhľadanie miesta a obe Price Insights volania.

Sandbox vracia vymyslené ceny - ide len o to, či integrácia drží tvar.
Na stránku sa z neho nesmie dostať nič.

Spustenie: python kayak_skuska.py
"""
import json
import logging
import sys
import urllib.error
from datetime import date

import kayak

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kayak")


def chyba(e) -> str:
    try:
        t = e.read().decode("utf-8", "replace")[:300]
    except Exception:
        return ""
    return t.replace(kayak.KLUC, "***") if kayak.KLUC else t


def main() -> int:
    logger.info("=== Kayak sandbox ===")
    try:
        kayak.najdi_sposob()
    except kayak.KayakChyba as e:
        logger.error("%s", e)
        return 1

    logger.info("--- Miesta ---")
    miesta = {}
    for nazov in ("Bratislava", "London", "Barcelona"):
        try:
            m = kayak.miesto(nazov)
        except Exception as e:
            logger.warning("%s: %s", nazov, e)
            continue
        if not m:
            logger.warning("%s: nič sa nenašlo", nazov)
            continue
        miesta[nazov] = m
        logger.info("%-12s placeId %-8s %s (%s)", nazov, m.get("placeId"),
                    m.get("name"), m.get("iataCode"))

    if "Bratislava" not in miesta or "London" not in miesta:
        logger.error("Bez placeId sa ďalej nedá.")
        return 1
    odkial, kam = miesta["Bratislava"]["placeId"], miesta["London"]["placeId"]

    buduci = date.today().replace(day=1)
    buduci = buduci.replace(year=buduci.year + (buduci.month == 12),
                            month=buduci.month % 12 + 1)
    mesiac = buduci.strftime("%Y-%m")

    logger.info("--- Routes: Bratislava -> London, %s ---", mesiac)
    try:
        data = kayak.routes(odkial, kam, dates={"departureDate": buduci.isoformat()})
        vysledky = (data or {}).get("results") or []
        logger.info("Výsledkov: %d", len(vysledky))
        for r in vysledky[:3]:
            noha = r.get("outboundLeg") or {}
            cena = r.get("price") or {}
            logger.info("  %s-%s  %s  %s %s  %s prestup(ov)",
                        noha.get("origin"), noha.get("destination"),
                        (noha.get("departureDateTime") or "")[:10],
                        cena.get("price"), cena.get("currency"), noha.get("stops"))
        if vysledky:
            logger.info("  odkaz: %s", (vysledky[0].get("deeplinkUrl") or "")[:120])
    except urllib.error.HTTPError as e:
        logger.error("routes: HTTP %s %s", e.code, chyba(e))
    except Exception as e:
        logger.error("routes: %s", e)

    logger.info("--- Calendar: Bratislava -> London, %s ---", mesiac)
    try:
        data = kayak.calendar(odkial, kam, mesiac, mesiac)
        vysledky = (data or {}).get("results") or []
        logger.info("Výsledkov: %d", len(vysledky))
        for r in vysledky[:5]:
            noha = r.get("outboundLeg") or {}
            spat = (r.get("inboundLegs") or [{}])[0]
            cena = spat.get("price") or r.get("price") or {}
            logger.info("  %s  %s-%s  %s %s%s", noha.get("departureDate"),
                        noha.get("origin"), noha.get("destination"),
                        cena.get("price"), cena.get("currency"),
                        "  (predpoveď)" if r.get("predicted") else "")
    except urllib.error.HTTPError as e:
        logger.error("calendar: HTTP %s %s", e.code, chyba(e))
    except Exception as e:
        logger.error("calendar: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
