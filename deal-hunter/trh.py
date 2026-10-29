"""
Trhová kontrola: je cena dealu naozaj najnižšia na Slovensku?

PREČO
Zľava, ktorú uvádza obchodník (prečiarknutá „pôvodná cena"), nehovorí nič
o tom, či ten istý produkt inde nepredávajú lacnejšie. HenKukaj má ukazovať
najlacnejšie ponuky na Slovensku, preto každý kandidát musí prejsť porovnaním
s trhom. Čo sa overiť nedá, sa nenavrhuje.

ODKIAĽ BERIEME CENY TRHU
Z porovnávača Pricemania.sk:
- Zoznam produktov je vo verejných sitemapách (robots.txt ich sám uvádza).
- Produktová stránka má strojovo čitateľný súhrn ponúk (schema.org
  AggregateOffer): najnižšia cena, najvyššia cena, počet obchodov.
- Vyhľadávanie (/vyhladavanie/) robots.txt zakazuje, preto ho nepoužívame.
  Produkt hľadáme vo vlastnom indexe zostavenom zo sitemáp.
Heureka automatické čítanie blokuje a Najnakup.sk zakazuje AI robotov, tie
nepoužívame.

AKO SA PÁRUJE PRODUKT
Podľa slov v adrese produktu na Pricemanii (napr. „walmark-omega-3-rybi-olej-
forte-180-cps"). Musí sedieť značka (prvé slovo), všetky čísla z názvu na
Pricemanii (balenie, gramáž, model) musia byť aj v názve kandidáta a väčšina
slov sa musí zhodovať. Radšej žiadna zhoda ako zlá: nespárovaný kandidát sa
nenavrhne, kým zle spárovaný by dostal nepravdivé tvrdenie o najnižšej cene.

POUŽITIE
  index = Index.nacitaj()             # stiahne sitemapy, uloží do cache
  vysledok = over(kandidat, index)    # dict alebo None
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)

ROBOTS = "https://www.pricemania.sk/robots.txt"
# Sitemapy, ktoré nie sú produkty, alebo ich nechceme.
NEPRODUKTOVE = ("category", "cms", "images", "shop.xml", "manufacturer", "eroticke")
CACHE = Path(os.environ.get("TRH_CACHE", Path.home() / ".cache" / "henkukaj" / "pricemania-index.json.gz"))
CACHE_DNI = 7

MIN_POKRYTIE = 0.75
# Slovo, ktoré má menej produktov, je "vzácne" a určuje konkrétny produkt.
VZACNE_SLOVO = 300

_SLOVA_NAVYSE = {"a", "s", "so", "na", "pre", "do", "z", "zo", "v", "vo", "x", "ks", "kus", "kusov",
                 "sk", "the", "and", "with", "for", "new", "novy", "nova", "nove"}
# Jednotky, ktoré sa píšu rôzne (180 kapsúl = 180 cps = 180 tbl).
# Porovnávač píše kapsuly aj tablety ako "tbl", preto ich zjednotíme.
_JEDNOTKY = {"kapsul": "tbl", "kapsula": "tbl", "kapsuly": "tbl", "kaps": "tbl", "caps": "tbl", "cps": "tbl",
             "tablet": "tbl", "tabliet": "tbl", "tablety": "tbl", "tab": "tbl", "tbl": "tbl",
             "mililitrov": "ml", "gramov": "g", "kilogram": "kg"}


def _bez_diakritiky(text: str) -> str:
    n = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in n if not unicodedata.combining(ch))


_JEDNOTKY_CISEL = {"w", "kw", "v", "mah", "wh", "cm", "mm", "m", "l", "ml", "dl", "g", "kg", "mg", "mcg",
                   "gb", "tb", "mb", "hz", "ghz", "mhz", "cps", "tbl", "ks", "dni", "dni", "palcov", "inch",
                   "x", "iu", "percent", "w2", "lm", "db", "bar", "ot", "min", "h"}


def tokeny(text: str) -> list[str]:
    """Slová a čísla z názvu: '180tbl' -> ['180', 'tbl'], jednotky zjednotené."""
    t = _bez_diakritiky(text).replace("'", "").replace("’", "").replace("%", " percent ")
    t = re.sub(r"(\d)([a-z])", r"\1 \2", t)            # 180tbl -> 180 tbl
    # Písmená pred číslom oddelíme len pri dlhšom slove (bxfpa1200 -> bxfpa 1200).
    # Krátke predpony sú súčasť modelu: S25 a A25 sú iné telefóny, HC5550 je model.
    t = re.sub(r"([a-z]{3,})(\d)", r"\1 \2", t)
    out = []
    for w in re.split(r"[^a-z0-9]+", t):
        if not w or w in _SLOVA_NAVYSE:
            continue
        out.append(_JEDNOTKY.get(w, w))
    return out


def _holé_cisla(toks: list[str]) -> set[str]:
    """
    Čísla, ktoré určujú produkt (model, verzia, diel): '8' v 'Buds 8 Lite',
    '6' v 'Doprava 6'. Čísla s jednotkou (1450 W, 180 tbl) sú parametre,
    tie nemusí mať porovnávač v názve.
    """
    out = set()
    for i, t in enumerate(toks):
        if t.isdigit():
            dalsie = toks[i + 1] if i + 1 < len(toks) else ""
            if dalsie not in _JEDNOTKY_CISEL and not dalsie.isdigit():
                out.add(t)
    return out


def _cisla(toks: list[str]) -> set[str]:
    return {t for t in toks if t.isdigit()}


class Index:
    """Zoznam produktov z Pricemanie s rýchlym hľadaním podľa slov."""

    def __init__(self, produkty: list[tuple[str, list[str]]]):
        self.produkty = produkty
        self._podla_slova: dict[str, list[int]] = {}
        for i, (_url, toks) in enumerate(produkty):
            for t in set(toks):
                if not t.isdigit():
                    self._podla_slova.setdefault(t, []).append(i)

    @classmethod
    def nacitaj(cls, obnovit: bool = False) -> "Index":
        if not obnovit and CACHE.exists() and (time.time() - CACHE.stat().st_mtime) < CACHE_DNI * 86400:
            with gzip.open(CACHE, "rt", encoding="utf-8") as f:
                urls = json.load(f)
            logger.info("Trh: index z cache, %d produktov", len(urls))
        else:
            urls = cls._stiahni()
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(CACHE, "wt", encoding="utf-8") as f:
                json.dump(urls, f)
            logger.info("Trh: index stiahnutý, %d produktov", len(urls))
        return cls([(u, tokeny(u.rstrip("/").rsplit("/", 1)[-1])) for u in urls])

    @staticmethod
    def _get(url: str) -> bytes | None:
        try:
            r = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=60)
        except requests.RequestException as e:
            logger.warning("Trh: %s sa nestiahol: %s", url, e)
            return None
        if r.status_code != 200:
            return None
        b = r.content
        return gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b

    @classmethod
    def _stiahni(cls) -> list[str]:
        robots = (cls._get(ROBOTS) or b"").decode("utf-8", "ignore")
        mapy = [m for m in re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots)
                if not any(x in m for x in NEPRODUKTOVE)]
        urls: list[str] = []
        for mapa in mapy:
            obsah = (cls._get(mapa) or b"").decode("utf-8", "ignore")
            locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", obsah)
            if "<sitemapindex" in obsah[:500]:
                for pod in locs:
                    o = (cls._get(pod) or b"").decode("utf-8", "ignore")
                    urls += re.findall(r"<loc>\s*([^<]+?)\s*</loc>", o)
                    time.sleep(0.5)
            else:
                urls += locs
            time.sleep(0.5)
        return sorted(set(u for u in urls if u.startswith("https://www.pricemania.sk/")))

    def najdi(self, nazov: str) -> tuple[str, float] | None:
        """Najlepšia zhoda (adresa, pokrytie) alebo None."""
        c = tokeny(nazov)
        if not c:
            return None
        cs, c_cisla, c_hole = set(c), _cisla(c), _holé_cisla(c)
        # Kandidáti: produkty, ktoré majú aspoň najvzácnejšie slovo z názvu.
        slova = sorted((t for t in cs if t in self._podla_slova), key=lambda t: len(self._podla_slova[t]))
        if not slova:
            return None
        kandidati = set(self._podla_slova[slova[0]])
        if len(slova) > 1:
            kandidati |= set(self._podla_slova[slova[1]])
        najlepsi = None
        for i in kandidati:
            url, p = self.produkty[i]
            if not p or p[0] not in cs:                     # značka musí sedieť
                continue
            p_cisla = _cisla(p)
            if not p_cisla <= c_cisla:                      # balenie, model, gramáž
                continue
            if not c_hole <= p_cisla:                       # model/verzia kandidáta musí byť aj tu
                continue
            spolocne = set(p) & cs
            # Vzácne slová z názvu na porovnávači (meno modelu či vône, napr.
            # 'maahir') musí mať aj kandidát - inak ide o iný produkt tej istej
            # značky. Bežné slová (voda, olej, tb) chýbať smú.
            if any(len(self._podla_slova.get(t, ())) < VZACNE_SLOVO for t in set(p) - cs if not t.isdigit() and t not in _JEDNOTKY_CISEL):
                continue
            pokrytie = len(spolocne) / len(set(p))
            if pokrytie < MIN_POKRYTIE or len(spolocne) / len(cs) < 0.4:
                continue
            skore = (pokrytie, -len(p))
            if najlepsi is None or skore > najlepsi[0]:
                najlepsi = (skore, url, pokrytie)
        return (najlepsi[1], najlepsi[2]) if najlepsi else None


def ponuky(url: str) -> dict | None:
    """Súhrn ponúk z produktovej stránky: najnižšia, najvyššia cena, počet obchodov."""
    import http_client

    html = http_client.get(url, check_robots=True)
    if not html:
        return None
    for blok in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        if '"Product"' not in blok or '"offers"' not in blok:
            continue
        try:
            data = json.loads(blok)
        except json.JSONDecodeError:
            continue
        o = data.get("offers") or {}
        try:
            return {
                "nazov": str(data.get("name") or "").strip(),
                "najnizsia": float(o.get("lowPrice") or o.get("price")),
                "najvyssia": float(o.get("highPrice") or o.get("lowPrice") or o.get("price")),
                "obchodov": int(o.get("offerCount") or 1),
            }
        except (TypeError, ValueError):
            return None
    return None


def posud(cena: float, p: dict) -> tuple[bool, str]:
    """Je cena najnižšia na trhu? (rozhodnutie, dôvod)"""
    min_obchodov, tolerancia = config.TRH_MIN_OBCHODOV, config.TRH_TOLERANCIA
    if p["obchodov"] < min_obchodov:
        return False, f"len {p['obchodov']} obchod(y) na trhu - nedá sa porovnať"
    if cena > p["najnizsia"] * (1 + tolerancia):
        return False, f"inde lacnejšie: {p['najnizsia']:.2f} € (my {cena:.2f} €)"
    return True, f"najnižšia cena spomedzi {p['obchodov']} obchodov (inde od {p['najnizsia']:.2f} €)"


POSLEDNY_DOVOD = ""


def over(kandidat, index: Index) -> dict | None:
    """
    Overí kandidáta. Vráti údaje o trhu, keď je cena najnižšia, inak None.
    Freebies (zadarmo) sa neporovnávajú - zadarmo je vždy najlacnejšie.
    """
    global POSLEDNY_DOVOD
    zhoda = index.najdi(kandidat.title)
    if not zhoda:
        POSLEDNY_DOVOD = "produkt sa na trhu nenašiel"
        logger.info("Trh: bez zhody na trhu - %s", kandidat.title[:60])
        return None
    url, pokrytie = zhoda
    p = ponuky(url)
    if not p:
        POSLEDNY_DOVOD = "ponuky na trhu sa nenačítali"
        logger.info("Trh: %s - ponuky sa nenačítali", url)
        return None
    ok, dovod = posud(kandidat.deal_price, p)
    POSLEDNY_DOVOD = dovod
    logger.info("Trh: %s %s | %s", "OK " if ok else "NIE", kandidat.title[:50], dovod)
    if not ok:
        return None
    return {"najnizsia": p["najnizsia"], "najvyssia": p["najvyssia"], "obchodov": p["obchodov"],
            "porovnane": date.today().isoformat(), "zdroj": "pricemania.sk", "zhoda": round(pokrytie, 2)}
