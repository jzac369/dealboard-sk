"""
Stiahne logá e-shopov, z ktorých máme zľavové kódy.

PREČO RAZ A K NÁM, A NIE ZA BEHU
Existujú služby, ktoré logo k doméne vrátia na požiadanie (napr.
Googlov favicon endpoint). Lenže to by znamenalo, že pri každom
otvorení stránky ide požiadavka k tretej strane a tá sa dozvie, ktoré
kupóny si kto pozerá. Radšej ich stiahneme raz sem a servírujeme
z vlastnej domény.

Logá sa sťahujú pre obchody z kupónov aj z dealov. Pre dealy navyše
vznikne assets/eshopy/obchody.json - mapa "kľúč obchodu" -> súbor loga.
Deal sa s logom páruje cez názov obchodu, nie cez doménu odkazu: odkaz
môže byť presmerovanie (tidd.ly) alebo subdoména (leaflets.kaufland.com),
kým "Lidl" a "Lidl.sk" sú ten istý obchod.

Spustenie:  python fetch_shop_logos.py
Len výpis:  python fetch_shop_logos.py --skuska
"""

import json
import unicodedata

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

# Bežný prehliadač: časť obchodov robotov s vlastným menom odmieta,
# hoci logo je verejne na ich úvodnej stránke.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"),
    "Accept": "*/*",
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


def _je_obrazok(data: bytes) -> bool:
    zaciatok = data[:400].lstrip()
    if zaciatok.startswith(b"<svg") or (zaciatok.startswith(b"<?xml") and b"<svg" in data[:2000]):
        return True
    return _dost_velke(data, 16)


def _dost_velke(data: bytes, minimum: int) -> bool:
    from PIL import Image
    try:
        return min(Image.open(io.BytesIO(data)).size) >= minimum
    except Exception:
        return False


def _velkost(data: bytes) -> int:
    """Kratšia strana obrázka; SVG je ostré v každej veľkosti."""
    zaciatok = data[:400].lstrip()
    if zaciatok.startswith(b"<svg") or (zaciatok.startswith(b"<?xml") and b"<svg" in data[:2000]):
        return 10_000
    from PIL import Image
    try:
        return min(Image.open(io.BytesIO(data)).size)
    except Exception:
        return 0


def _zo_stranky(domain: str) -> bytes | None:
    # Časť obchodov beží len na www. a holá doména im nič nevráti.
    for host in (domain, f"www.{domain}"):
        for path in CANDIDATES:
            data = _get(f"https://{host}{path}", expect_image=True)
            if data and _je_obrazok(data):
                return data
        for url in _from_html(host):
            # data: je zástupný obrázok (napr. 1 px GIF), nie logo.
            if url.startswith("data:"):
                continue
            data = _get(url, expect_image=True)
            if data and _je_obrazok(data):
                return data
    return None


def _od_googlu(domain: str) -> bytes | None:
    # Veľké obchody (Alza, Dr.Max...) robotov na svojej stránke odmietajú
    # a iné majú len 16 px favicon. Googlova služba ikon pozná väčšiu
    # verziu; stiahneme ju raz a servírujeme od nás, takže návštevníci
    # ku Googlu nechodia. Neznámej doméne vráti 16 px zemeguľu - tú
    # nechceme, preto minimum 32 px.
    for host in (domain, f"www.{domain}"):
        data = _get(f"https://www.google.com/s2/favicons?domain={host}&sz=128", expect_image=True)
        if data and _dost_velke(data, 32):
            return data
    return None


def fetch_logo(domain: str) -> bytes | None:
    data = _zo_stranky(domain)
    if data and _velkost(data) >= SIZE:
        return data
    zaloha = _od_googlu(domain)
    kandidati = [d for d in (data, zaloha) if d]
    return max(kandidati, key=_velkost) if kandidati else None


def _orez(im):
    """Odreže prázdny (priehľadný alebo biely) okraj okolo značky.

    Viaceré obchody majú v ikone malú značku uprostred veľkej bielej
    plochy - v 20 px bublinke by z nej zostala bodka.
    """
    from PIL import ImageChops
    plne = im.getchannel("A").point(lambda a: 255 if a > 24 else 0)
    biele = ImageChops.invert(im.convert("L").point(lambda v: 255 if v > 245 else 0))
    obsah = ImageChops.multiply(plne, biele).getbbox()
    if not obsah:
        return im
    x0, y0, x1, y1 = obsah
    okraj = round(max(x1 - x0, y1 - y0) * 0.06)
    x0, y0 = max(0, x0 - okraj), max(0, y0 - okraj)
    x1, y1 = min(im.width, x1 + okraj), min(im.height, y1 + okraj)
    return im.crop((x0, y0, x1, y1))


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
        im = _orez(im)
        if max(im.size) < 32:
            return False          # zväčšená 16 px ikona je len kopa štvorčekov
        # Na veľkosť štvorca - aj nahor, inak by malá ikona zostala
        # bodkou uprostred prázdnej plochy.
        mierka = SIZE / max(im.size)
        im = im.resize((max(1, round(im.width * mierka)), max(1, round(im.height * mierka))), Image.LANCZOS)

        # Na štvorec, aby všetky logá sedeli v rovnakom krúžku.
        plocha = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
        plocha.paste(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2), im)

        os.makedirs(OUT_DIR, exist_ok=True)
        plocha.save(os.path.join(OUT_DIR, f"{domain}.png"), "PNG", optimize=True)
        return True
    except Exception as e:
        logger.warning("   %s: obrázok sa nepodarilo spracovať (%s)", domain, e)
        return False


MAPA = os.path.join(OUT_DIR, "obchody.json")

# Odkazy, z ktorých sa doména obchodu vyčítať nedá.
PRESMEROVANIA = {"tidd.ly", "go.dognet.com", "bit.ly", "t.co", "l.facebook.com",
                 "zlacnene.sk", "kompaszliav.sk"}

# Obchody, ktorých odkazy vedú inde než na hlavnú stránku so značkou.
DOMENA_OBCHODU = {
    "kaufland": "kaufland.com",
    "tesco": "tesco.sk",
    "hebe": "hebe.sk",
    "momondo": "momondo.com",
    "dennikn": "dennikn.sk",
}


def kluc_obchodu(nazov: str) -> str:
    """Rovnaké pravidlo ako storeKey() v index.html - musia sa zhodovať."""
    t = unicodedata.normalize("NFD", (nazov or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"\.(sk|cz|com|eu|digital|net|org)$", "", t.strip())
    return re.sub(r"[^a-z0-9]", "", t)


def _hlavna_domena(host: str) -> str:
    host = host.lower().removeprefix("www.")
    casti = host.split(".")
    return ".".join(casti[-2:]) if len(casti) > 2 else host


def obchody_z_dealov(db) -> dict[str, str]:
    """kľúč obchodu -> doména, z ktorej stiahneme logo."""
    hlasy: dict[str, dict[str, int]] = {}
    for doc in db.collection("deals").stream():
        d = doc.to_dict() or {}
        if d.get("status") not in ("approved", "pending"):
            continue
        kluc = kluc_obchodu(d.get("store", ""))
        if not kluc:
            continue
        host = (urlparse(d.get("url", "")).hostname or "").lower().removeprefix("www.")
        if not host or host in PRESMEROVANIA:
            continue
        dom = _hlavna_domena(host)
        hlasy.setdefault(kluc, {})
        hlasy[kluc][dom] = hlasy[kluc].get(dom, 0) + 1
    out = {k: max(v, key=v.get) for k, v in hlasy.items()}
    out.update({k: v for k, v in DOMENA_OBCHODU.items() if k in out or k in hlasy})
    return out


def domains_from_firestore(db) -> list[str]:
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
    import firestore_client
    db = firestore_client.get_client()
    obchody = obchody_z_dealov(db)
    domeny = sorted(set(domains_from_firestore(db)) | set(obchody.values()))
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
            # Zapíšeme, aby sa hodinový beh v cloude nepokúšal stále
            # znova. Kto chce skúsiť znova, riadok zo súboru zmaže.
            from datetime import date
            with open(zoznam, "a", encoding="utf-8") as f:
                f.write(f"{d:<21} logo sa nenaslo ({date.today().isoformat()})\n")
            vynechane.add(d)

    logger.info("\nStiahnutých %d, bez loga %d, preskočených %d.", ok, zlyhalo, preskocene)

    # Mapa pre karty dealov: len obchody, ktorých logo naozaj máme.
    mapa = {}
    for kluc, dom in sorted(obchody.items()):
        if dom in vynechane:
            continue
        for pripona in (".svg", ".png"):
            if os.path.exists(os.path.join(OUT_DIR, dom + pripona)):
                mapa[kluc] = dom + pripona
                break
    if not dry:
        with open(MAPA, "w", encoding="utf-8") as f:
            json.dump(mapa, f, ensure_ascii=False, indent=0, sort_keys=True)
            f.write("\n")
    logger.info("Obchodov z dealov: %d, s logom: %d.", len(obchody), len(mapa))
    return 0


if __name__ == "__main__":
    sys.exit(main())
