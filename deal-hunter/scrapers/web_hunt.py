"""
Agent, ktorý sám hľadá dealy a freebies na internete (Claude + vyhľadávanie).

AKO TO FUNGUJE
1. Claude dostane zoznam záujmových skupín a cez vyhľadávanie na webe nájde
   konkrétne ponuky (dealy aj produkty/vzorky zadarmo).
2. Claude je len NÁPOVEDA, nie zdroj pravdy. Každý odkaz, ktorý vráti, si
   agent sám stiahne a over: musia sa na stránke nachádzať presne tie ceny,
   ktoré Claude uviedol. Čo sa nepotvrdí, zahodí sa. Pri minulom pokuse s
   inou AI si model ceny a kódy domýšľal - preto nikdy neveríme číslam z
   odpovede, len tomu, čo je na stránke.
3. Overené návrhy idú ďalej rovnako ako ostatné zdroje: výber, deduplikácia a
   schválenie v adminovi/Telegrame. Nič sa nezverejní samo.

REŽIMY (zapnú sa tým, aký kľúč je nastavený; oba sa dajú spojiť)
- BRAVE_API_KEY (BEZPLATNÉ): bežné vyhľadávanie Brave Search API (free plán,
  ~2000 dopytov mesačne). Výsledky stránku po stránke overí agent sám cez
  štruktúrované dáta (JSON-LD Product/Offer) a prečiarknutú cenu.
- ANTHROPIC_API_KEY (PLATENÉ): Claude s vyhľadávaním, rozumnejšie výsledky.
Bez kľúča sa zdroj preskočí. Beh ide najviac raz za WEB_HUNT_INTERVAL_HOURS.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import config
import http_client
from models import DealCandidate, parse_price
from scrapers.base import BaseScraper
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

SYSTEM = (
    "Si hľadač dealov pre slovenskú zľavovú stránku HenKukaj.sk. Používaš vyhľadávanie na webe. "
    "Nikdy si nevymýšľaš ceny, názvy ani odkazy - uvádzaš len to, čo si skutočne videl na stránke."
)


def _prompt(skupiny: list[str], max_navrhov: int) -> str:
    return f"""Nájdi aktuálne ponuky pre zákazníkov zo Slovenska. Dnes je {date.today().isoformat()}.

Záujmové skupiny (zober z každej aspoň jednu, ak nájdeš kvalitnú ponuku):
{chr(10).join('- ' + s for s in skupiny)}

Hľadáme dva druhy ponúk:
1. "deal" - konkrétny produkt s výrazne zníženou cenou (aspoň 25 %), na slovenskom alebo českom e-shope,
   ktorý doručuje na Slovensko.
2. "freebie" - produkt, vzorka, e-kniha, softvér alebo služba skutočne ZADARMO (bez nákupu; prípadne len
   poštovné). Nie súťaže, žrebovania ani zľavy.

Pravidlá:
- Odkaz musí viesť priamo na stránku konkrétnej ponuky (nie na kategóriu, nie na zoznam, nie na agregátor
  ako zlacnene.sk, heureka.sk, pepper). Najlepšie priamo na e-shop alebo oficiálnu stránku akcie.
- Cenu a pôvodnú cenu napíš PRESNE tak, ako ich vidíš na stránke. Ak si cenou nie si istý, ponuku vynechaj.
- Nezaraďuj alkohol, tabak, erotiku, hazard, zbrane, lieky na predpis, pôžičky, kryptomeny ani MLM.
- Žiadne ponuky, ktorých platnosť už skončila.
- Radšej menej, ale overených ponúk. Najviac {max_navrhov}.

Odpovedz IBA JSON poľom (žiadny iný text), každá položka:
{{"typ": "deal" | "freebie", "skupina": "<jedna zo skupín vyššie>", "url": "https://...",
  "nazov": "<názov ponuky>", "cena": <číslo v eurách, pri freebie 0>, "povodna_cena": <číslo alebo null>,
  "platnost_do": "YYYY-MM-DD alebo null"}}"""


def vytiahni_json(text: str) -> list[dict]:
    """Z odpovede vytiahne prvé JSON pole; pri nezmysle vráti prázdny zoznam."""
    a, b = text.find("["), text.rfind("]")
    if a < 0 or b <= a:
        return []
    try:
        data = json.loads(text[a:b + 1])
    except json.JSONDecodeError:
        return []
    return [x for x in data if isinstance(x, dict)]


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
                    if v and v > cena and (povodna is None or v > povodna):
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


SABLONY_DEALOV = ("{s} zľava výpredaj akcia", "{s} zľava až 50 % akciová ponuka", "{s} zľavnený tovar eshop SK")
SABLONY_FREEBIES = ("vzorka zadarmo {s}", "{s} produkt zadarmo vyskúšať bez nákupu")


def brave_hladaj(dotaz: str, kluc: str, freshness: str = "pm") -> list[str]:
    import requests
    try:
        r = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": dotaz, "country": "SK", "search_lang": "sk", "count": 10, "freshness": freshness},
            headers={"X-Subscription-Token": kluc, "Accept": "application/json"}, timeout=20)
        if r.status_code != 200:
            logger.warning("web-hunt: Brave HTTP %s", r.status_code)
            return []
        return [x["url"] for x in (r.json().get("web") or {}).get("results", []) if x.get("url")]
    except Exception as e:
        logger.warning("web-hunt: Brave zlyhal (%s)", e)
        return []


class WebHuntScraper(BaseScraper):
    source_name = "web-hunt"

    def fetch_candidates(self) -> list[DealCandidate]:
        brave = os.environ.get("BRAVE_API_KEY")
        claude = os.environ.get("ANTHROPIC_API_KEY")
        if not (brave or claude):
            logger.info("web-hunt: chýba BRAVE_API_KEY aj ANTHROPIC_API_KEY, preskakujem.")
            return []
        db = self._db()
        if db is not None and not self._je_cas(db):
            logger.info("web-hunt: bežal pred menej než %d h, preskakujem.", config.WEB_HUNT_INTERVAL_HOURS)
            return []

        out: list[DealCandidate] = []
        if brave:
            out += self._brave(brave)
        if claude:
            out += self._claude()
        if db is not None:
            self._zapis_beh(db)
        return out

    def _stiahni(self, url: str) -> str | None:
        try:
            return http_client.get(url, check_robots=True)
        except Exception as e:
            logger.warning("web-hunt: stiahnutie zlyhalo (%s)", e)
            return None

    def _brave(self, kluc: str) -> list[DealCandidate]:
        import random
        skupiny = list(config.WEB_HUNT_SKUPINY)
        random.shuffle(skupiny)      # každý deň iná sada, nech sa oblasti obmieňajú
        dotazy: list[tuple[str, str, str]] = []
        for i, sk in enumerate(skupiny):
            dotazy.append((SABLONY_DEALOV[i % len(SABLONY_DEALOV)].format(s=sk), "deal", sk))
        for sk in skupiny[:max(2, config.WEB_HUNT_DOTAZOV_NA_BEH // 5)]:
            dotazy.append((random.choice(SABLONY_FREEBIES).format(s=sk), "freebie", sk))
        out: list[DealCandidate] = []
        videne: set[str] = set()
        for dotaz, typ, sk in dotazy[: config.WEB_HUNT_DOTAZOV_NA_BEH]:
            for url in brave_hladaj(dotaz, kluc, "pm" if typ == "deal" else "py"):
                if url in videne or len(videne) >= config.WEB_HUNT_MAX_NAVRHOV * 4:
                    continue
                videne.add(url)
                html = self._stiahni(url)
                c = over_stranku(url, html, typ, sk) if html else None
                if c:
                    out.append(c)
        logger.info("web-hunt (Brave): overených %d z %d stránok", len(out), len(videne))
        return out

    def _claude(self) -> list[DealCandidate]:
        navrhy = self._hladaj()
        logger.info("web-hunt: Claude navrhol %d ponúk", len(navrhy))
        out: list[DealCandidate] = []
        for n in navrhy[: config.WEB_HUNT_MAX_NAVRHOV]:
            html = self._stiahni(str(n.get("url") or ""))
            try:
                c = over_navrh(n, html) if html else None
            except Exception as e:
                logger.warning("web-hunt: overenie zlyhalo (%s)", e)
                continue
            if c:
                out.append(c)
            else:
                logger.info("web-hunt: nepotvrdené, zahadzujem: %s", str(n.get("url"))[:70])
        logger.info("web-hunt (Claude): overených %d z %d", len(out), len(navrhy))
        return out

    # ── siete a stav ─────────────────────────────────────────────────
    @staticmethod
    def _db():
        if config.DRY_RUN:
            return None
        try:
            import firestore_client
            return firestore_client.get_client()
        except Exception as e:
            logger.warning("web-hunt: databáza nedostupná (%s)", e)
            return None

    @staticmethod
    def _je_cas(db) -> bool:
        try:
            d = (db.document("admin_info/web_hunt").get().to_dict() or {}).get("posledny")
        except Exception:
            return True
        return not d or datetime.now(timezone.utc) - d >= timedelta(hours=config.WEB_HUNT_INTERVAL_HOURS)

    @staticmethod
    def _zapis_beh(db) -> None:
        try:
            db.document("admin_info/web_hunt").set({"posledny": datetime.now(timezone.utc)}, merge=True)
        except Exception as e:
            logger.warning("web-hunt: čas behu sa nepodarilo zapísať (%s)", e)

    def _hladaj(self) -> list[dict]:
        import anthropic

        client = anthropic.Anthropic()
        messages = [{"role": "user", "content": _prompt(config.WEB_HUNT_SKUPINY, config.WEB_HUNT_MAX_NAVRHOV)}]
        tools = [{
            "type": "web_search_20260209", "name": "web_search",
            "max_uses": config.WEB_HUNT_MAX_VYHLADAVANI,
            "user_location": {"type": "approximate", "country": "SK", "city": "Bratislava",
                              "region": "Bratislava", "timezone": "Europe/Bratislava"},
        }]
        try:
            for _ in range(6):   # server občas preruší (pause_turn) - pokračujeme
                with client.messages.stream(
                    model=config.WEB_HUNT_MODEL, max_tokens=16000, system=SYSTEM,
                    tools=tools, messages=messages,
                ) as stream:
                    odpoved = stream.get_final_message()
                if odpoved.stop_reason == "pause_turn":
                    messages.append({"role": "assistant", "content": odpoved.content})
                    continue
                if odpoved.stop_reason == "refusal":
                    logger.warning("web-hunt: model odmietol požiadavku")
                    return []
                break
        except Exception as e:
            logger.error("web-hunt: volanie Claude zlyhalo: %s", e)
            return []
        text = "".join(b.text for b in odpoved.content if getattr(b, "type", "") == "text")
        return vytiahni_json(text)
