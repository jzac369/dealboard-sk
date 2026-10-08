"""
Úlohy zadané z admin zóny (kolekcia admin_ulohy).

PREČO CEZ PLÁNOVAČ
Stránka beží na GitHub Pages a nemá vlastný server. Niektoré veci sa z
prehliadača urobiť nedajú: cudzí e-shop nepustí stránku k svojmu HTML
(CORS) a spustiť úlohu na GitHube by znamenalo dať do verejnej stránky
GitHub token. Admin preto len zapíše úlohu do databázy a plánovač, ktorý
beží nepretržite v GitHub Actions, ju vykoná a zapíše výsledok.

Plánovač kolekciu sleduje živým odberom (on_snapshot), takže úloha
začne do pár sekúnd - nečaká na ďalšiu päťminútovú kontrolu.

Dokument:
  typ       nacitaj_url | kontrola_platnosti | spusti_workflow | zopakuj_beh
  vstup     parametre úlohy
  stav      caka -> bezi -> hotovo | chyba
  vysledok  výsledok pre admin
"""

from __future__ import annotations

import html as _html
import json
import logging
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import requests

logger = logging.getLogger("admin_ulohy")

# Spúšťať sa dajú len tieto - nie ľubovoľný súbor, ktorý by si niekto
# do úlohy vpísal.
POVOLENE_WORKFLOW = {
    "deal-hunter.yml", "letenky.yml", "denny-ziar.yml", "facebook.yml",
    "letenky-mapa.yml", "generate-deal-pages.yml", "telegram-approve.yml",
}

# Prehliadačový identifikátor so stránkou a kontaktom. Nič sa tu
# neobchádza: keď e-shop automatické čítanie odmietne, admin to oznámi
# a údaje sa doplnia ručne.
UA = ("Mozilla/5.0 (compatible; HenKukajAdmin/1.0; +https://henkukaj.sk; "
      "kontakt: info@henkukaj.sk)")


# ── Načítanie údajov o produkte z odkazu ─────────────────────────────
def _meta(html: str, *mena: str) -> str | None:
    for meno in mena:
        for vzor in (
            rf'<meta[^>]+(?:property|name|itemprop)=["\']{re.escape(meno)}["\'][^>]*content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\']{re.escape(meno)}["\']',
        ):
            m = re.search(vzor, html, re.I)
            if m:
                return _html.unescape(m.group(1)).strip()
    return None


def _cena(text) -> float | None:
    if text is None:
        return None
    t = str(text).replace("\xa0", "").replace(" ", "")
    m = re.search(r"\d+(?:[.,]\d{3})*(?:[.,]\d{1,2})?", t)
    if not m:
        return None
    c = m.group(0)
    # 1.299,90 / 1,299.90 / 129,90 / 129.90
    if "," in c and "." in c:
        c = c.replace(".", "").replace(",", ".") if c.rfind(",") > c.rfind(".") else c.replace(",", "")
    elif "," in c:
        c = c.replace(",", ".")
    try:
        v = float(c)
    except ValueError:
        return None
    return v if 0 < v < 1_000_000 else None


def _json_ld(html: str) -> list[dict]:
    """Všetky objekty zo <script type="application/ld+json">, aj vnorené v @graph."""
    vysledok = []
    for blok in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(blok.strip())
        except Exception:
            continue
        zasobnik = [data]
        while zasobnik:
            x = zasobnik.pop()
            if isinstance(x, list):
                zasobnik.extend(x)
            elif isinstance(x, dict):
                vysledok.append(x)
                if "@graph" in x:
                    zasobnik.append(x["@graph"])
    return vysledok


def nacitaj_url(db, vstup: dict) -> dict:
    url = str(vstup.get("url") or "").strip()
    if not re.match(r"^https?://", url, re.I):
        raise ValueError("Adresa musí začínať http:// alebo https://")
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "sk,cs;q=0.8"},
                         timeout=20, allow_redirects=True)
    except requests.RequestException as e:
        raise ValueError(f"Stránka neodpovedá ({e.__class__.__name__}).")
    if r.status_code in (404, 410):
        raise ValueError(f"Stránka neexistuje ({r.status_code}) - skontroluj adresu.")
    if r.status_code >= 400:
        raise ValueError(f"E-shop odpovedal chybou {r.status_code} - automatické čítanie asi nepovoľuje. "
                         "Údaje doplň ručne.")
    html = r.text[:2_000_000]

    produkt = next((x for x in _json_ld(html)
                    if "Product" in (x.get("@type") if isinstance(x.get("@type"), list) else [x.get("@type")])), {})
    ponuka = produkt.get("offers") or {}
    if isinstance(ponuka, list):
        ponuka = ponuka[0] if ponuka else {}

    titul = (produkt.get("name") or _meta(html, "og:title", "twitter:title")
             or (re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I) or [None, None])[1] or "")
    titul = re.sub(r"\s+", " ", _html.unescape(str(titul))).strip()
    obrazok = produkt.get("image")
    if isinstance(obrazok, list):
        obrazok = obrazok[0] if obrazok else None
    if isinstance(obrazok, dict):
        obrazok = obrazok.get("url")
    obrazok = obrazok or _meta(html, "og:image", "twitter:image")
    if obrazok and obrazok.startswith("//"):
        obrazok = "https:" + obrazok
    cena = (_cena(ponuka.get("price") or ponuka.get("lowPrice"))
            or _cena(_meta(html, "product:price:amount", "og:price:amount", "price")))
    host = urlparse(r.url).hostname or ""
    obchod = (_meta(html, "og:site_name") or host.replace("www.", "")).strip()
    popis = produkt.get("description") or _meta(html, "og:description", "description") or ""
    popis = re.sub(r"<[^>]+>", " ", _html.unescape(str(popis)))
    popis = re.sub(r"\s+", " ", popis).strip()[:400]
    dostupnost = str(ponuka.get("availability") or "")
    return {
        "url": r.url,
        "title": titul[:180],
        "imageUrl": obrazok if obrazok and obrazok.startswith("http") else None,
        "dealPrice": cena,
        "currency": ponuka.get("priceCurrency") or "EUR",
        "store": obchod[:60],
        "description": popis,
        "vypredane": "OutOfStock" in dostupnost or "SoldOut" in dostupnost,
    }


# ── Kontrola platnosti ───────────────────────────────────────────────
def _skontroluj(url: str) -> tuple[str, str]:
    """('ok' | 'mrtvy' | 'neiste', dôvod)."""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15, allow_redirects=True, stream=True)
        kod = r.status_code
        r.close()
    except requests.RequestException as e:
        return "neiste", f"neodpovedá ({e.__class__.__name__})"
    if kod in (404, 410):
        return "mrtvy", f"stránka neexistuje ({kod})"
    if kod >= 400:
        # 403 a 429 bývajú ochrana proti robotom, nie skončená akcia.
        return "neiste", f"e-shop odmietol kontrolu ({kod})"
    return "ok", str(kod)


def kontrola_platnosti(db, vstup: dict) -> dict:
    import firestore_client
    from google.cloud.firestore_v1.base_query import FieldFilter

    exspirovane_datum = firestore_client.expire_past_deals(db)
    docs = list(db.collection("deals").where(filter=FieldFilter("status", "==", "approved")).stream())
    na_kontrolu = []
    for d in docs:
        x = d.to_dict() or {}
        if x.get("expired"):
            continue
        url = x.get("url") or ""
        if url.startswith("http"):
            na_kontrolu.append((d, x, url))
    na_kontrolu = na_kontrolu[: int(vstup.get("limit") or 200)]

    with ThreadPoolExecutor(max_workers=6) as ex:
        vysledky = list(ex.map(lambda t: _skontroluj(t[2]), na_kontrolu))

    teraz = datetime.now(timezone.utc)
    problemy = []
    batch = db.batch()
    for (d, x, url), (stav, dovod) in zip(na_kontrolu, vysledky):
        batch.update(d.reference, {"kontrola": {"kedy": teraz, "stav": stav, "dovod": dovod}})
        if stav != "ok":
            problemy.append({"id": d.id, "title": (x.get("title") or "")[:120], "store": x.get("store") or "",
                             "stav": stav, "dovod": dovod})
    batch.commit()
    return {
        "skontrolovanych": len(na_kontrolu),
        "exspirovanychPodlaDatumu": exspirovane_datum,
        "mrtvych": sum(1 for p in problemy if p["stav"] == "mrtvy"),
        "neistych": sum(1 for p in problemy if p["stav"] == "neiste"),
        "problemy": problemy[:150],
        "den": date.today().isoformat(),
    }


# ── GitHub ───────────────────────────────────────────────────────────
def spusti_workflow(db, vstup: dict) -> dict:
    wf = str(vstup.get("workflow") or "")
    if wf not in POVOLENE_WORKFLOW:
        raise ValueError("Tento workflow sa z admina spustiť nedá.")
    r = subprocess.run(["gh", "workflow", "run", wf], capture_output=True, text=True)
    if r.returncode != 0:
        raise ValueError((r.stderr or r.stdout).strip()[:300])
    return {"spustene": wf}


def zopakuj_beh(db, vstup: dict) -> dict:
    beh = str(vstup.get("runId") or "")
    if not beh.isdigit():
        raise ValueError("Neplatné číslo behu.")
    r = subprocess.run(["gh", "run", "rerun", beh, "--failed"], capture_output=True, text=True)
    if r.returncode != 0:
        raise ValueError((r.stderr or r.stdout).strip()[:300])
    return {"zopakovane": beh}


def test_feed(db, vstup: dict) -> dict:
    """Stiahne začiatok feedu a povie, čo v ňom je - aby sa dal v admine
    overiť skôr, než ho agent začne používať."""
    import xml.etree.ElementTree as ET
    from collections import Counter

    url = str(vstup.get("url") or "").strip()
    if not re.match(r"^https?://", url, re.I):
        raise ValueError("Adresa feedu musí začínať http:// alebo https://")
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/xml,text/xml"},
                         timeout=90, stream=True)
    except requests.RequestException as e:
        raise ValueError(f"Feed sa nepodarilo stiahnuť ({e.__class__.__name__}).")
    if r.status_code != 200:
        raise ValueError(f"Feed odpovedal chybou {r.status_code}.")
    # Čítame len začiatok - feedy majú bežne desiatky megabajtov.
    data = b""
    for kus in r.iter_content(200000):
        data += kus
        if len(data) > 3_000_000:
            break
    r.close()
    text = data.decode("utf-8", "ignore")
    # Posledná neúplná položka by rozbila parsovanie, tak ju odrežeme.
    for koniec in ("</SHOPITEM>", "</item>", "</entry>"):
        i = text.rfind(koniec)
        if i > 0:
            text = text[: i + len(koniec)]
            koren = {"</SHOPITEM>": "SHOP", "</item>": "rss", "</entry>": "feed"}[koniec]
            text = text[text.index("<"):] + f"</channel></{koren}>" if koren == "rss" else text + f"</{koren}>"
            break
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"Feed nie je platné XML: {str(e)[:120]}")

    import scrapers.feeds as feeds
    polozky = feeds.FeedsScraper().parse_feed(ET.tostring(root, encoding="unicode"), url)
    if not polozky:
        raise ValueError("Vo feede sme nenašli žiadne produkty. Je to naozaj produktový feed (Heureka alebo Google Merchant)?")
    domeny = Counter()
    for k in polozky:
        from urllib.parse import urlparse as _u
        domeny[(_u(k.url).hostname or "").replace("www.", "").lower()] += 1
    ukazka = [{"nazov": k.title[:70], "cena": k.deal_price, "povodna": k.original_price,
               "url": k.url[:90]} for k in polozky[:5]]
    return {
        "poloziek": len(polozky),
        "format": "Heureka" if "<SHOPITEM" in text[:200000].upper() else "Google Merchant",
        "domeny": [{"domena": d, "pocet": n} for d, n in domeny.most_common(3)],
        "sPovodnouCenou": sum(1 for k in polozky if k.original_price),
        "ukazka": ukazka,
    }


def test_email(db, vstup: dict) -> dict:
    import emaily
    return emaily.test(db, vstup)


def ehub_obnov(db, vstup: dict) -> dict:
    import ehub
    v = ehub.obnov(db, force=True)
    if v is None:
        raise ValueError("Prehľad sa neobnovil - skontroluj API kľúč eHUB v nastaveniach alebo chybu na stránke.")
    return v


SPRACOVATELIA = {
    "ehub_obnov": ehub_obnov,
    "test_email": test_email,
    "test_feed": test_feed,
    "nacitaj_url": nacitaj_url,
    "kontrola_platnosti": kontrola_platnosti,
    "spusti_workflow": spusti_workflow,
    "zopakuj_beh": zopakuj_beh,
}


def spracuj(db, ref) -> None:
    """Vykoná jednu úlohu. Stav 'bezi' sa zapíše transakciou, takže
    úlohu nevykonajú dvaja naraz (napr. pri prekrytí dvoch slučiek)."""
    from google.cloud import firestore

    @firestore.transactional
    def prevezmi(tx):
        snap = ref.get(transaction=tx)
        if not snap.exists or (snap.to_dict() or {}).get("stav") != "caka":
            return None
        tx.update(ref, {"stav": "bezi", "zaciatok": firestore.SERVER_TIMESTAMP})
        return snap.to_dict()

    data = prevezmi(db.transaction())
    if not data:
        return
    typ = data.get("typ")
    logger.info("Úloha z admina: %s", typ)
    try:
        fn = SPRACOVATELIA.get(typ)
        if not fn:
            raise ValueError(f"Neznámy typ úlohy: {typ}")
        vysledok = fn(db, data.get("vstup") or {})
        ref.update({"stav": "hotovo", "vysledok": vysledok, "koniec": firestore.SERVER_TIMESTAMP})
    except Exception as e:
        logger.warning("Úloha %s zlyhala: %s", typ, e)
        ref.update({"stav": "chyba", "chyba": str(e)[:400], "koniec": firestore.SERVER_TIMESTAMP})


def sleduj(db, fronta) -> object | None:
    """Živý odber čakajúcich úloh - ID dokumentov dáva do fronty."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    def zmena(snimky, zmeny, _cas):
        for z in zmeny:
            if z.type.name in ("ADDED", "MODIFIED"):
                fronta.put(z.document.reference)

    try:
        return (db.collection("admin_ulohy")
                .where(filter=FieldFilter("stav", "==", "caka"))
                .on_snapshot(zmena))
    except Exception as e:
        logger.warning("Odber úloh z admina sa nepodarilo spustiť: %s", e)
        return None
