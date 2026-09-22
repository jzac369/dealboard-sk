"""
Stiahne logá e-shopov, z ktorých máme zľavové kódy.

PREČO RAZ A K NÁM, A NIE ZA BEHU
Existujú služby, ktoré logo k doméne vrátia na požiadanie (napr.
Googlov favicon endpoint). Lenže to by znamenalo, že pri každom
otvorení stránky ide požiadavka k tretej strane a tá sa dozvie, ktoré
kupóny si kto pozerá. Radšej ich stiahneme raz sem a servírujeme
z vlastnej domény.

Spustenie:  python fetch_shop_logos.py
Len výpis:  python fetch_shop_logos.py --skuska
"""

import io
import logging
import os
import re
import sys
import urllib.request
from urllib.parse import urljoin, urlparse

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("logos")

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "eshopy")
SIZE = 96
TIMEOUT = 12

# Poradie je zámerné: apple-touch-icon býva najväčší a najčistejší,
# favicon.ico najmenší a často rozmazaný.
CANDIDATES = [
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/favicon.png",
    "/favicon.ico",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HenKukajBot/1.0; +https://henkukaj.sk)",
    "Accept": "image/*,*/*;q=0.8",
}


def _get(url: str, expect_image: bool = False) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            if r.status != 200:
                return None
            data = r.read(2 * 1024 * 1024)
            if not data:
                return None
            # Časť e-shopov na chýbajúcu ikonu nevráti 404, ale rovno
            # svoju úvodnú stránku. Bez tejto kontroly by sme HTML
            # považovali za logo a pokus o ikonu by sa tým "podaril".
            if expect_image:
                typ = (r.headers.get("Content-Type") or "").lower()
                if "html" in typ or data[:200].lstrip().lower().startswith((b"<!doctype", b"<html", b"<style")):
                    return None
            return data
    except Exception:
        return None


def _from_html(domain: str) -> list[str]:
    """Adresy ikon vyčítané z <link rel="icon"> na úvodnej stránke."""
    html = _get(f"https://{domain}/")
    if not html:
        return []
    try:
        text = html.decode("utf-8", "ignore")
    except Exception:
        return []

    found = []
    for m in re.finditer(r'<link[^>]+rel=["\'][^"\']*icon[^"\']*["\'][^>]*>', text, re.I):
        href = re.search(r'href=["\']([^"\']+)["\']', m.group(0), re.I)
        if href:
            found.append(urljoin(f"https://{domain}/", href.group(1)))
    return found


def fetch_logo(domain: str) -> bytes | None:
    for path in CANDIDATES:
        data = _get(f"https://{domain}{path}", expect_image=True)
        if data:
            return data
    for url in _from_html(domain):
        data = _get(url, expect_image=True)
        if data:
            return data
    return None


def save(domain: str, data: bytes) -> bool:
    # SVG logo je text, nie rastrový obrázok - spracovateľ obrázkov ho
    # neotvorí. Prehliadač ho ale zobrazí bez problémov a v akejkoľvek
    # veľkosti ostro, tak ho uložíme tak, ako prišlo.
    zaciatok = data[:400].lstrip()
    if zaciatok.startswith(b"<svg") or (zaciatok.startswith(b"<?xml") and b"<svg" in data[:2000]):
        if b"<script" in data.lower():
            logger.warning("   %s: SVG obsahuje skript, preskakujem", domain)
            return False
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, f"{domain}.svg"), "wb") as f:
            f.write(data)
        return True

    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        # .ico nesie viac veľkostí naraz - vyberieme najväčšiu.
        if getattr(im, "n_frames", 1) > 1 or im.format == "ICO":
            try:
                im = Image.open(io.BytesIO(data))
                im.size  # noqa - Pillow pri ICO vyberie najväčšiu sám
            except Exception:
                pass
        im = im.convert("RGBA")
        if min(im.size) < 16:
            return False          # príliš malé, vyzeralo by rozmazane
        im.thumbnail((SIZE, SIZE), Image.LANCZOS)

        # Na štvorec, aby všetky logá sedeli v rovnakom krúžku.
        plocha = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
        plocha.paste(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2), im)

        os.makedirs(OUT_DIR, exist_ok=True)
        plocha.save(os.path.join(OUT_DIR, f"{domain}.png"), "PNG", optimize=True)
        return True
    except Exception as e:
        logger.warning("   %s: obrázok sa nepodarilo spracovať (%s)", domain, e)
        return False


def domains_from_firestore() -> list[str]:
    import firestore_client
    db = firestore_client.get_client()
    out = set()
    for doc in db.collection("coupons").stream():
        c = doc.to_dict() or {}
        if c.get("status") != "approved":
            continue
        host = (urlparse(c.get("url", "")).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host:
            out.add(host)
    return sorted(out)


def main() -> int:
    dry = "--skuska" in sys.argv
    domeny = domains_from_firestore()
    logger.info("Domén na spracovanie: %d\n", len(domeny))

    # Domény, ktorých logo vedome nepoužívame (prázdne, cudzia značka
    # alebo nás server odmieta). Bez tohto by sa sťahovali pri každom
    # spustení znova a s rovnakým výsledkom.
    vynechane = set()
    zoznam = os.path.join(OUT_DIR, "BEZ-LOGA.txt")
    if os.path.exists(zoznam):
        for riadok in open(zoznam, encoding="utf-8"):
            riadok = riadok.strip()
            if riadok and not riadok.startswith("#"):
                vynechane.add(riadok.split()[0])

    ok = zlyhalo = preskocene = 0
    for d in domeny:
        if d in vynechane:
            logger.info(" x %s (vedome vynechané)", d)
            preskocene += 1
            continue
        if any(os.path.exists(os.path.join(OUT_DIR, f"{d}{p}")) for p in (".png", ".svg")):
            logger.info(" = %s (už máme)", d)
            preskocene += 1
            continue
        if dry:
            logger.info(" ? %s", d)
            continue
        data = fetch_logo(d)
        if data and save(d, data):
            logger.info(" + %s", d)
            ok += 1
        else:
            logger.info(" - %s (logo sa nenašlo)", d)
            zlyhalo += 1

    logger.info("\nStiahnutých %d, bez loga %d, preskočených %d.", ok, zlyhalo, preskocene)
    return 0


if __name__ == "__main__":
    sys.exit(main())
