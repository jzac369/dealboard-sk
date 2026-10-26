"""
Denné sledovanie cien zverejnených dealov (beží na domácom serveri).

NAČO
Cena v deale je z chvíle, keď sa našiel. Obchod ju medzitým môže zmeniť
alebo akcia skončí skôr. Raz denne preto prejdeme stránky zverejnených
dealov, prečítame aktuálnu cenu a uložíme ju do histórie (`priceHistory`
v dokumente dealu). Z nej sa na stránke ukáže „sledovaná cena“ a podľa
nej vieme poctivo povedať, či je cena naozaj najnižšia, akú sme videli.

ČO SA NEMENÍ
Cena dealu (`dealPrice`) sa nikdy neprepisuje sama. Ak sa cena u predajcu
zvýšila, príde zoznam do Telegramu a o deale rozhodneš ty.

AKO ŠETRÍME CUDZIE SERVERY
- Za beh sa skontroluje najviac LIMIT dealov, tie s najstaršou kontrolou
  ako prvé. Pri väčšom počte dealov sa postupne vystrieda všetky.
- Dodržiava sa robots.txt a pauza medzi požiadavkami (http_client).
- Obchody, ktoré blokujú automatické čítanie (Allegro), sa preskakujú.

POUŽITIE
  python sledovanie_cien.py            -> skontroluje a zapíše
  python sledovanie_cien.py --skuska   -> len vypíše, nič nezapisuje
"""

from __future__ import annotations

import logging
import sys
from datetime import date

import config
import firestore_client
import http_client
import price_history
from scrapers.overenie import extrahuj_ponuku

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sledovanie_cien")

LIMIT = 150
# O koľko % vyššia cena ako v deale už stojí za upozornenie.
PRAH_ZVYSENIA_PERCENT = 5.0
PRESKOCIT_DOMENY = ("allegro.", "ryanair.", "zlacnene.sk", "dognet.", "ehub.")

SKUSKA = "--skuska" in sys.argv


def posudit_zmenu(cena_deal: float, cena_dnes: float) -> str | None:
    """'vyssia' / 'nizsia' / None podľa toho, ako sa cena líši od ceny v deale."""
    if not cena_deal or cena_deal <= 0 or cena_dnes <= 0:
        return None
    rozdiel = (cena_dnes / cena_deal - 1) * 100
    if rozdiel >= PRAH_ZVYSENIA_PERCENT:
        return "vyssia"
    if rozdiel <= -PRAH_ZVYSENIA_PERCENT:
        return "nizsia"
    return None


def je_porovnatelna(d: dict, cena_dnes: float) -> bool:
    """
    Dá sa cenu na stránke porovnať s cenou v deale?

    Nie, keď je deal viazaný na zľavový kód (cena na stránke je bez neho
    vyššia) alebo keď sa cena líši viac než o polovicu - takmer iste
    stránka ukazuje iný variant či balenie. Taká hodnota by v histórii
    cien robila nezmyselné skoky a v Telegrame falošné poplachy.
    """
    nazov = (d.get("title") or "").lower()
    if "kód" in nazov or "kod " in nazov or "kodom" in nazov:
        return False
    cena_deal = float(d.get("dealPrice") or 0)
    if cena_deal <= 0:
        return False
    return 0.5 <= cena_dnes / cena_deal <= 1.5


def vyber_na_kontrolu(dokumenty: list, limit: int = LIMIT) -> list:
    """Zverejnené, neskončené dealy s priamou adresou; najstaršia kontrola prvá."""
    kandidati = []
    for doc in dokumenty:
        d = doc.to_dict() or {}
        if d.get("expired") is True:
            continue
        url = d.get("sourceUrl") or d.get("url") or ""
        if not url.startswith("http") or any(x in url for x in PRESKOCIT_DOMENY):
            continue
        if d.get("category") == "Cestovanie":
            continue
        kandidati.append((str(d.get("cenaKontrola") or ""), doc, url))
    kandidati.sort(key=lambda x: x[0])
    return [(doc, url) for _k, doc, url in kandidati[:limit]]


def main() -> int:
    from google.cloud.firestore_v1.base_query import FieldFilter

    db = firestore_client.get_client()
    dokumenty = list(db.collection(config.DEALS_COLLECTION)
                     .where(filter=FieldFilter("status", "==", "approved")).stream())
    na_kontrolu = vyber_na_kontrolu(dokumenty)
    logger.info("Zverejnených dealov %d, dnes kontrolujem %d", len(dokumenty), len(na_kontrolu))

    dnes = date.today().isoformat()
    davka = db.batch()
    v_davke = 0
    precitane = 0
    vyssie: list[tuple[str, float, float]] = []
    nizsie = 0

    for doc, url in na_kontrolu:
        d = doc.to_dict() or {}
        try:
            html = http_client.get(url, check_robots=True)
            ponuka = extrahuj_ponuku(html) if html else None
        except Exception as e:
            logger.warning("%s: %s", url[:70], e)
            continue
        if not ponuka:
            # Stránka sa nenačítala alebo nemá cenu. Nič nezapisujeme,
            # aby chýbajúce údaje nevyzerali ako zmena ceny.
            continue

        cena = ponuka["cena"]
        if not je_porovnatelna(d, cena):
            logger.info("Preskakujem (kód alebo iný variant): %s", (d.get("title") or "")[:50])
            continue
        precitane += 1
        zmena = posudit_zmenu(float(d.get("dealPrice") or 0), cena)
        if zmena == "vyssia":
            vyssie.append((d.get("title", "?"), float(d.get("dealPrice") or 0), cena))
        elif zmena == "nizsia":
            nizsie += 1

        if SKUSKA:
            logger.info("%-50s deal %7.2f -> dnes %7.2f %s", (d.get("title") or "")[:50],
                        float(d.get("dealPrice") or 0), cena, zmena or "")
            continue

        historia = price_history.append_price_point(d.get("priceHistory"), cena)
        davka.update(doc.reference, {"priceHistory": historia, "cenaDnes": round(cena, 2),
                                     "cenaKontrola": dnes})
        v_davke += 1
        if v_davke >= 400:
            davka.commit()
            davka, v_davke = db.batch(), 0

    if v_davke and not SKUSKA:
        davka.commit()

    logger.info("Prečítaných cien %d, vyššia než v deale %d, nižšia %d",
                precitane, len(vyssie), nizsie)

    if vyssie and not SKUSKA:
        import telegram_bot
        riadky = [f"- {t[:48]}: {a:.2f} € -> {b:.2f} €" for t, a, b in vyssie[:12]]
        extra = f"\n… a {len(vyssie) - 12} ďalších" if len(vyssie) > 12 else ""
        telegram_bot.send_text(
            f"Cena u predajcu je vyššia než v deale ({len(vyssie)}):\n" + "\n".join(riadky) + extra
            + "\nAkcia už možno skončila. Skontroluj v admine:\nhttps://henkukaj.sk/admin.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
