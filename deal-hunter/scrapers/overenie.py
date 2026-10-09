"""
Overenie ponuky priamo zo stránky obchodu - bez AI a bez cudzích služieb.

Čo sa tvrdí (cena, pôvodná cena, zadarmo), musí na stránke naozaj byť,
inak sa ponuka zahodí. Ceny a prečiarknutú cenu čítame zo štruktúrovaných
dát (JSON-LD Product/Offer) a z prečiarknutých prvkov stránky.
Používa to prehľadávanie sitemap (scrapers/sitemap_hunt.py).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from urllib.parse import urlparse

import config
import http_client
from models import DealCandidate, parse_price
from scrapers.feeds import obchod_z_url

logger = logging.getLogger(__name__)

# Skupina -> kategória na stránke.
KATEGORIE = {
    "technológie a gaming": "Elektronika",
    "domácnosť a záhrada": "Dom & Záhrada",
    "deti a rodina": "Hračky",
    "kozmetika a starostlivosť": "Iné",
    "šport a outdoor": "Šport",
    "cestovanie": "Cestovanie",
    "móda": "Móda",
    "knihy a vzdelávanie": "Iné",
    "jedlo a nápoje": "Jedlo & Nápoje",
    "auto-moto": "Iné",
    "domáce zvieratá": "Iné",
    "softvér a predplatné": "Elektronika",
}

# Odkazy, ktoré nechceme ako cieľ dealu (agregátory, ktoré len odkazujú ďalej).
ZAKAZANE_DOMENY = ("zlacnene.sk", "heureka.sk", "heureka.cz", "pepper.", "dealgo.", "google.", "facebook.",
                   "instagram.", "youtube.", "tiktok.", "reddit.")

# Obsah, ktorý na stránke (a pre AdSense) nechceme, bez ohľadu na zľavu.
ZAKAZANE_SLOVA = ("alkohol", "vodka", "whisky", "víno", "vino ", "pivo", "tabak", "tabak", "cigar", "vape",
                  "erotic", "sex", "kasíno", "casino", "stávk", "sazk", "zbraň", "zbran", "pôžičk", "pozick",
                  "kryptomen", "bitcoin", "mlm")

def text_stranky(html: str) -> str:
    """Čitateľný text stránky malými písmenami (bez skriptov a štýlov)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).lower()


def cena_v_texte(text: str, cena: float) -> bool:
    """Je cena (v tvare 12,99 / 12.99 / 12 €) naozaj na stránke?"""
    c = f"{cena:.2f}"
    cele, des = c.split(".")
    varianty = [rf"{cele}[.,]{des}"]
    if des == "00":
        varianty.append(rf"{cele}(?:[.,]0+)?\s*(?:€|eur)")
    else:
        varianty.append(rf"{cele}[.,]{des[0]}(?!\d)")
    return any(re.search(rf"(?<![\d.,]){v}(?!\d)", text) for v in varianty)


def meta(html: str, *kluce: str) -> str | None:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for k in kluce:
        el = soup.find("meta", attrs={"property": k}) or soup.find("meta", attrs={"name": k})
        if el and el.get("content", "").strip():
            return el["content"].strip()
    return None


def nazov_stranky(html: str) -> str:
    n = meta(html, "og:title")
    if not n:
        from bs4 import BeautifulSoup
        t = BeautifulSoup(html, "html.parser").title
        n = t.get_text().strip() if t else ""
    return re.split(r"\s[|–—-]\s", n)[0].strip()[:150]


def over_navrh(n: dict, html: str) -> DealCandidate | None:
    """Prijme návrh len keď ho potvrdzuje stránka. Čisté (bez siete) -> testovateľné."""
    url = str(n.get("url") or "").strip()
    typ = n.get("typ")
    if not url.startswith("https://") or typ not in ("deal", "freebie"):
        return None
    host = (urlparse(url).hostname or "").lower()
    if any(z in host for z in ZAKAZANE_DOMENY):
        return None

    text = text_stranky(html)
    titul = nazov_stranky(html) or str(n.get("nazov") or "")[:150]
    if not titul:
        return None
    zaklad = f"{titul.lower()} {text[:600]}"
    if any(s in zaklad for s in ZAKAZANE_SLOVA):
        return None

    platnost = None
    p = str(n.get("platnost_do") or "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p):
        try:
            d = date.fromisoformat(p)
        except ValueError:
            d = None
        # Dátum prevezmeme len keď ho stránka naozaj spomína (d. m. alebo ISO).
        if d and d >= date.today() and (p in text or f"{d.day}. {d.month}." in text
                                       or f"{d.day}.{d.month}." in text):
            platnost = p

    spolocne = dict(
        title=titul, url=url, source="web-hunt", direct_url=True, store=obchod_z_url(url),
        image_url=(lambda i: i if i and i.startswith("https://") else None)(meta(html, "og:image")),
        description=(meta(html, "og:description", "description") or "")[:400],
        category_hint=KATEGORIE.get(str(n.get("skupina") or "").lower()),
        valid_until=platnost,
    )

    if typ == "freebie":
        if not re.search(r"zadarmo|zdarma|bezplatn|free|gratis", text):
            return None
        if not spolocne["description"]:
            spolocne["description"] = f"Ponuka zadarmo na {spolocne['store']}: {titul}."
        return DealCandidate(deal_price=0.0, original_price=None, explicit_discount_percent=100,
                             zadarmo=True, **spolocne)

    cena, povodna = parse_price(str(n.get("cena"))), parse_price(str(n.get("povodna_cena")))
    if not cena or not povodna or povodna <= cena:
        return None
    if not (cena_v_texte(text, cena) and cena_v_texte(text, povodna)):
        return None
    return DealCandidate(deal_price=cena, original_price=povodna, **spolocne)


# ── bezplatný režim: extrakcia ponuky priamo zo stránky ───────────────

def _jsonld_produkty(html: str) -> list[dict]:
    from bs4 import BeautifulSoup
    out: list[dict] = []

    def chod(x):
        if isinstance(x, list):
            for i in x:
                chod(i)
        elif isinstance(x, dict):
            t = x.get("@type")
            ts = t if isinstance(t, list) else [t]
            if "Product" in ts:
                out.append(x)
            for v in x.values():
                if isinstance(v, (list, dict)):
                    chod(v)

    for sc in BeautifulSoup(html, "html.parser").find_all("script", type="application/ld+json"):
        try:
            chod(json.loads(sc.string or sc.get_text() or ""))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def extrahuj_ponuku(html: str) -> dict | None:
    """Z produktovej stránky vytiahne názov, cenu a pôvodnú (prečiarknutú) cenu.
    Vracia None, ak stránka nie je produkt s cenou v eurách a skladom."""
    from bs4 import BeautifulSoup
    for prod in _jsonld_produkty(html):
        ponuky = prod.get("offers")
        ponuky = ponuky if isinstance(ponuky, list) else [ponuky]
        for o in [x for x in ponuky if isinstance(x, dict)]:
            mena = str(o.get("priceCurrency") or "EUR").upper()
            cena = parse_price(str(o.get("price") if o.get("price") is not None else o.get("lowPrice")))
            if mena != "EUR" or cena is None:
                continue
            dost = str(o.get("availability") or "")
            if dost and "InStock" not in dost and "LimitedAvailability" not in dost and "PreOrder" not in dost:
                continue
            povodna = None
            specs = o.get("priceSpecification")
            for sp in (specs if isinstance(specs, list) else [specs]):
                if isinstance(sp, dict) and re.search(r"list|strike|msrp", str(sp.get("priceType") or ""), re.I):
                    povodna = parse_price(str(sp.get("price")))
            if povodna is None:
                soup = BeautifulSoup(html, "html.parser")
                kandidati = soup.find_all(["del", "s", "strike"]) + soup.find_all(
                    class_=re.compile(r"old[-_]?price|price[-_]?old|was[-_]?price|original[-_]?price|"
                                      r"price[-_]?before|crossed|strike", re.I))
                for el in kandidati:
                    v = parse_price(el.get_text(" ", strip=True)[:40])
                    # Prečiarknutá cena na stránke môže patriť inému produktu
                    # (podobné, kusová cena, iná mena). Viac ako 4-násobok
                    # ceny je takmer vždy chyba, nie zľava 75 %+.
                    if v and v > cena and v <= cena * 4 and (povodna is None or v > povodna):
                        povodna = v
            return {"nazov": str(prod.get("name") or "").strip(), "cena": cena, "povodna": povodna,
                    "platnost": str(o.get("priceValidUntil") or "")[:10] or None}
    return None


def over_stranku(url: str, html: str, typ: str, skupina: str) -> DealCandidate | None:
    """Overí stránku z vyhľadávania BEZ pomoci AI - len podľa toho, čo je na nej."""
    if typ == "freebie":
        c = over_navrh({"typ": "freebie", "url": url, "skupina": skupina}, html)
        if not c:
            return None
        # Zadarmo musí potvrdiť aj štruktúra, nielen náhodné slovo v texte.
        e = extrahuj_ponuku(html)
        if e and e["cena"] > 0:
            return None
        if not e and not re.search(
                r"vzork\w* zadarmo|zadarmo na vyskúšanie|produkt zadarmo|zdarma k objednávke|gratis",
                text_stranky(html)):
            return None
        return c
    e = extrahuj_ponuku(html)
    if not e or not e["povodna"] or e["povodna"] <= e["cena"]:
        return None
    n = {"typ": "deal", "url": url, "skupina": skupina, "cena": e["cena"], "povodna_cena": e["povodna"],
         "platnost_do": e["platnost"]}
    return over_navrh(n, html)
