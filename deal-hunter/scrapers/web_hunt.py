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

Potrebuje ANTHROPIC_API_KEY (GitHub secret). Bez kľúča sa zdroj preskočí.
Beh sa platí, preto ide najviac raz za WEB_HUNT_INTERVAL_HOURS.
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


class WebHuntScraper(BaseScraper):
    source_name = "web-hunt"

    def fetch_candidates(self) -> list[DealCandidate]:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.info("web-hunt: chýba ANTHROPIC_API_KEY, preskakujem.")
            return []
        db = self._db()
        if db is not None and not self._je_cas(db):
            logger.info("web-hunt: bežal pred menej než %d h, preskakujem.", config.WEB_HUNT_INTERVAL_HOURS)
            return []

        navrhy = self._hladaj()
        logger.info("web-hunt: Claude navrhol %d ponúk", len(navrhy))
        out: list[DealCandidate] = []
        for n in navrhy[: config.WEB_HUNT_MAX_NAVRHOV]:
            try:
                html = http_client.get(str(n.get("url") or ""), check_robots=True)
                c = over_navrh(n, html) if html else None
            except Exception as e:
                logger.warning("web-hunt: overenie zlyhalo (%s)", e)
                continue
            if c:
                out.append(c)
            else:
                logger.info("web-hunt: nepotvrdené, zahadzujem: %s", str(n.get("url"))[:70])
        logger.info("web-hunt: overených %d z %d", len(out), len(navrhy))
        if db is not None:
            self._zapis_beh(db)
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
