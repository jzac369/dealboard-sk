"""
Generátor statických SEO stránok pre jednotlivé dealy.

Prečo toto existuje: henkukaj.sk je single-page app (SPA) - jednotlivé dealy
sa doteraz zobrazovali len cez ?deal=ID query parameter v rámci jednej
index.html stránky. Vyhľadávače majú problém indexovať takýto obsah ako
samostatné stránky.

Toto riešenie vygeneruje pre KAŽDÝ schválený deal samostatný statický
súbor na ceste /deal/{slug}-{id}/index.html s vlastným title, meta
description, Open Graph tagmi a JSON-LD structured data - to Google
indexuje oveľa spoľahlivejšie.

Stránka zároveň obsahuje odkaz na plnú interaktívnu verziu (hlasovanie,
komentáre) na hlavnej SPA stránke (/?deal=ID).

Spúšťa sa pravidelne cez GitHub Actions (.github/workflows/generate-deal-pages.yml).
Nepotrebuje Selenium ani žiadny scraping - len číta z vlastnej Firestore DB,
takže nehrozí žiadna blokácia na úrovni IP adries.
"""

import json
import os
import re
from datetime import date
import html
import unicodedata
import logging

from google.cloud import firestore
from google.oauth2 import service_account

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_deal_pages")

FIRESTORE_PROJECT_ID = os.environ.get("FIRESTORE_PROJECT_ID", "dealboard-e60bf")
FIREBASE_CREDENTIALS_PATH = os.environ.get(
    "FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json"
)
SITE_URL = "https://henkukaj.sk"
OUTPUT_ROOT = "deal"  # -> /deal/{slug}/index.html

CURRENCY_MAP = {"€": "EUR", "Kč": "CZK", "EUR": "EUR", "CZK": "CZK"}


def get_client() -> firestore.Client:
    credentials = service_account.Credentials.from_service_account_file(
        FIREBASE_CREDENTIALS_PATH
    )
    return firestore.Client(project=FIRESTORE_PROJECT_ID, credentials=credentials)


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60].strip("-") or "deal"


def escape(s) -> str:
    return html.escape(str(s or ""), quote=True)


# Nastavenia affiliate (settings/affiliate). Načítajú sa raz v main().
AFFILIATE: dict = {}


def affiliate_url(url: str) -> str:
    """
    Rovnaké pravidlá ako affiliateUrl v index.html - musia sa zhodovať,
    inak by odkaz z Facebooku (vedie sem) zarábal inak než ten istý deal
    na hlavnej stránke. Obal len pri zapnutom affiliate, schválenej
    doméne, známom kanáli a odkaze, ktorý ešte nevedie cez preklikávač.
    """
    from urllib.parse import quote, urlparse

    a = AFFILIATE
    if not a.get("enabled") or not url or not url.startswith("http"):
        return url
    host = (urlparse(url).hostname or "").lower()
    if host in ("go.dognet.com", "go.dognet.sk") or host.endswith((".go.dognet.com", ".go.dognet.sk")):
        return url
    domeny = a.get("domains") or []
    if not any(host == d or host.endswith("." + d) for d in domeny):
        return url
    chid = a.get("chid")
    if not chid:
        return url
    return f"https://go.dognet.com/?chid={quote(chid, safe='')}&url={quote(url, safe='')}"


def _datum_dealu(d: dict):
    """Dátum dealu (timestamp z Firestore) alebo None."""
    ts = d.get("timestamp")
    try:
        return ts.date() if ts else None
    except AttributeError:
        return None


def je_expirovany(d: dict) -> bool:
    if d.get("expired"):
        return True
    platnost = d.get("validUntilISO")
    return bool(platnost) and platnost < date.today().isoformat()


def kratka_cena(d: dict, currency_symbol: str) -> str:
    """Cena pre kartičku súvisiaceho dealu - kratšia verzia price_html."""
    if d.get("zadarmo"):
        return "Zadarmo"
    deal_price = d.get("dealPrice")
    if deal_price:
        return f"{deal_price:.2f} {currency_symbol}"
    if d.get("discountPercent"):
        return f"Zľava {round(d['discountPercent'])} %"
    return ""


def najdi_suvisiace(deal_id: str, d: dict, vsetky: list, limit: int = 6) -> list:
    """Iné aktívne dealy z rovnakého obchodu, doplnené z rovnakej kategórie.

    Len na vyplnenie - stránka dealu má dnes v priemere len pár stoviek
    znakov textu, čo Google pri AdSense recenzii označil ako "low-value
    content". Súvisiace dealy pridávajú originálny, pravdivý obsah (nie
    vymyslený text) a zároveň držia návštevníka na stránke dlhšie.
    """
    store = (d.get("store") or "").strip().lower()
    category = d.get("category") or ""
    rovnaky_obchod, rovnaka_kategoria = [], []
    for iid, idata, islug in vsetky:
        if iid == deal_id or je_expirovany(idata):
            continue
        cieľ = rovnaky_obchod if store and (idata.get("store") or "").strip().lower() == store \
            else rovnaka_kategoria if category and idata.get("category") == category else None
        if cieľ is not None:
            cieľ.append((iid, idata, islug))
    return (rovnaky_obchod + rovnaka_kategoria)[:limit]


def suvisiace_html(suvisiace: list) -> str:
    if not suvisiace:
        return ""
    karty = []
    for iid, idata, islug in suvisiace:
        titul = idata.get("title") or "Deal"
        obr = idata.get("imageUrl") or f"{SITE_URL}/images/logo.png"
        cena = kratka_cena(idata, idata.get("currency") or "€")
        odkaz = f"{SITE_URL}/{OUTPUT_ROOT}/{islug}-{iid}/"
        karty.append(f"""<a class="rel-card" href="{odkaz}">
      <img src="{escape(obr)}" alt="" loading="lazy">
      <span class="rel-t">{escape(titul)}</span>
      {f'<span class="rel-p">{escape(cena)}</span>' if cena else ''}
    </a>""")
    return f"""
    <div class="rel-wrap">
      <h2 class="rel-h">Súvisiace dealy</h2>
      <div class="rel-row">{''.join(karty)}</div>
    </div>"""


def structured_data(d: dict, title: str, store: str, image_url: str, description: str,
                    target_url: str, currency_code: str) -> str:
    """
    JSON-LD pre Google (Product + Offer). Skladá sa ako slovník a cez
    json.dumps - predtým to bol Python repr() s apostrofmi, čo nie je
    platný JSON a Google ho celý ignoroval.
    """
    data = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": title,
        "image": image_url,
        "description": description,
    }
    if store:
        data["brand"] = {"@type": "Brand", "name": store}
    cena = d.get("dealPrice")
    if cena or d.get("zadarmo"):
        offer = {
            "@type": "Offer",
            "price": "0.00" if d.get("zadarmo") else f"{float(cena):.2f}",
            "priceCurrency": currency_code,
            "url": target_url,
            "availability": "https://schema.org/Discontinued" if je_expirovany(d) else "https://schema.org/InStock",
        }
        if d.get("validUntilISO"):
            offer["priceValidUntil"] = d["validUntilISO"]
        if store:
            offer["seller"] = {"@type": "Organization", "name": store}
        data["offers"] = offer
    # "</" by v <script> mohlo predčasne ukončiť blok.
    return json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")


def render_deal_page(deal_id: str, d: dict, suvisiace: list | None = None) -> str:
    title = d.get("title") or "Deal"
    store = d.get("store") or ""
    category = d.get("category") or ""
    description = d.get("description") or f"{title} v obchode {store}."
    image_url = d.get("imageUrl") or f"{SITE_URL}/images/logo.png"
    deal_price = d.get("dealPrice")
    original_price = d.get("originalPrice")
    currency_symbol = d.get("currency") or "€"
    currency_code = CURRENCY_MAP.get(currency_symbol, "EUR")
    target_url = affiliate_url(d.get("url") or SITE_URL)
    slug = slugify(title)
    page_path = f"{slug}-{deal_id}"
    canonical_url = f"{SITE_URL}/{OUTPUT_ROOT}/{page_path}/"
    spa_url = f"{SITE_URL}/?deal={deal_id}"

    price_html = ""
    if d.get("zadarmo"):
        price_html = '<span style="font-size:1.4rem;font-weight:800;color:#2E8B3D;">Zadarmo</span>'
    elif deal_price:
        price_html = f'<span style="font-size:1.4rem;font-weight:800;color:#2E8B3D;">{deal_price:.2f} {currency_symbol}</span>'
        if original_price and original_price > deal_price:
            price_html += f' <span style="text-decoration:line-through;color:#707070;font-size:0.9rem;">{original_price:.2f} {currency_symbol}</span>'
    elif d.get("discountPercent"):
        # Deal bez konkrétnej ceny - ukážeme len zľavu, nie "0,00 €".
        price_html = f'<span style="font-size:1.4rem;font-weight:800;color:#2E8B3D;">Zľava {round(d["discountPercent"])} %</span>'

    meta_description = (description[:155] + "…") if len(description) > 158 else description
    ld_json = structured_data(d, title, store, image_url, meta_description, target_url, currency_code)
    # Expirovaný deal dostane noindex hneď, nie až po čase - Google tieto
    # tenké, neaktuálne stránky inak počíta do "low-value content" (nahlásené
    # pri AdSense recenzii). Stránka ostáva prístupná, len sa neindexuje.
    robots = '<meta name="robots" content="noindex, follow">\n' if je_expirovany(d) else ""

    return f"""<!DOCTYPE html>
<html lang="sk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)} – HenKukaj.sk</title>
<meta name="description" content="{escape(meta_description)}">
<link rel="canonical" href="{canonical_url}">
{robots}
<meta property="og:type" content="product">
<meta property="og:site_name" content="HenKukaj.sk">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(meta_description)}">
<meta property="og:url" content="{canonical_url}">
<meta property="og:image" content="{escape(image_url)}">
<meta property="og:locale" content="sk_SK">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{escape(title)}">
<meta name="twitter:description" content="{escape(meta_description)}">
<meta name="twitter:image" content="{escape(image_url)}">

<script type="application/ld+json">
{ld_json}
</script>

<style>
  body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background:#EDEDED; color:#1A1A1A; margin:0; padding:24px 16px; }}
  .card {{ max-width:640px; margin:0 auto; background:#fff; border-radius:8px; border:1px solid #E2E2E2; overflow:hidden; }}
  .card img {{ width:100%; max-height:360px; object-fit:contain; background:#f5f5f5; display:block; }}
  .body {{ padding:20px; }}
  .meta {{ font-size:.8rem; color:#707070; margin-bottom:6px; }}
  h1 {{ font-size:1.3rem; margin:0 0 10px; }}
  p {{ line-height:1.6; color:#333; }}
  .btn {{ display:inline-block; background:#C44C0A; color:#fff; text-decoration:none; font-weight:700;
    padding:12px 22px; border-radius:22px; margin-top:16px; margin-right:10px; }}
  .btn.secondary {{ background:#2E8B3D; }}
  a.home {{ color:#707070; font-size:.85rem; }}
  .rel-wrap {{ max-width:640px; margin:14px auto 0; }}
  .rel-h {{ font-size:1rem; margin:0 0 10px; color:#1A1A1A; }}
  .rel-row {{ display:flex; gap:10px; overflow-x:auto; padding-bottom:4px; }}
  .rel-card {{ flex:0 0 140px; background:#fff; border:1px solid #E2E2E2; border-radius:12px; overflow:hidden;
    text-decoration:none; color:#1A1A1A; display:flex; flex-direction:column; }}
  .rel-card img {{ width:100%; height:90px; object-fit:contain; background:#f5f5f5; display:block; }}
  .rel-t {{ font-size:.76rem; line-height:1.3; padding:8px 8px 2px; flex:1; }}
  .rel-p {{ font-size:.82rem; font-weight:700; color:#C44C0A; padding:0 8px 8px; }}
</style>
</head>
<body>
  <div class="card">
    <img src="{escape(image_url)}" alt="{escape(title)}" loading="lazy">
    <div class="body">
      <div class="meta">{escape(store)} · {escape(category)}</div>
      <h1>{escape(title)}</h1>
      {'<p style="background:#FFF4E5;color:#7A4300;border-radius:8px;padding:10px 14px;font-weight:600;">Táto akcia už skončila. Aktuálne ponuky nájdeš na <a href="' + SITE_URL + '/" style="color:inherit;">HenKukaj.sk</a>.</p>' if je_expirovany(d) else ''}
      <p>{price_html}</p>
      <p>{escape(description)}</p>
      <a class="btn" href="{escape(target_url)}" target="_blank" rel="nofollow sponsored noopener">Zobraziť ponuku v e-shope →</a>
      <a class="btn secondary" href="{spa_url}">Hlasovať / komentovať na HenKukaj.sk</a>
      <p style="margin-top:24px;"><a class="home" href="{SITE_URL}/">← Späť na HenKukaj.sk</a></p>
    </div>
  </div>
  {suvisiace_html(suvisiace or [])}
  <script>
  /* Prenesieme UTM znacky na hlavnu stranku. Tato stranka merania
     nema - je to staticky sublist pre vyhladavace a nahlady odkazov.
     Keby sa znacky nepreniesli, navsteva z Facebooku by sa v prehlade
     kampani objavila ako "priamo" a cely bod 4 by bol na nic. */
  (function () {{
    var q = location.search;
    if (!q || q.indexOf('utm_') === -1) return;
    document.querySelectorAll('a[href^="{SITE_URL}/"]').forEach(function (a) {{
      a.href += (a.href.indexOf('?') === -1 ? '?' : '&') + q.slice(1);
    }});
  }})();
  </script>
</body>
</html>
"""


# ── Dealy priamo v HTML úvodnej stránky ──────────────────────────────
# Robot Googlu nečaká, kým sa zoznam dotiahne z databázy - 5. 10. 2026
# videl na úvodnej stránke len "Načítavam dealy…" a žiadny produkt ani
# cenu. Preto sem vpíšeme najnovšie dealy ako obyčajný text s odkazmi.
# Návštevník ich uvidí tiež, len ich hneď nahradí JavaScript živou
# verziou s hlasovaním - preto je blok označený id="seo-dealy" a
# renderDealsList() ho prepíše.
POCET_V_HTML = 24

ZNACKA_OD = "<!-- SEO-DEALY-ZACIATOK -->"
ZNACKA_PO = "<!-- SEO-DEALY-KONIEC -->"


def _cena(d: dict) -> str:
    c, mena = d.get("dealPrice"), (d.get("currency") or "€")
    try:
        return f"{float(c):.2f} {mena}".replace(".", ",")
    except (TypeError, ValueError):
        return ""


def render_seo_dealy(dealy: list) -> str:
    """Zoznam dealov ako čitateľný HTML - pre vyhľadávače a prvé vykreslenie."""
    riadky = []
    for slug_id, d in dealy:
        nazov = escape(d.get("title") or "")
        obchod = escape(d.get("store") or "")
        cena = _cena(d)
        povodna = ""
        try:
            if d.get("originalPrice"):
                povodna = f' <s>{float(d["originalPrice"]):.2f} {escape(d.get("currency") or "€")}</s>'.replace(".", ",")
        except (TypeError, ValueError):
            pass
        zlava = d.get("discountPercent")
        zlava_txt = f" <b>−{int(zlava)} %</b>" if isinstance(zlava, (int, float)) and zlava else ""
        popis = escape((d.get("description") or "")[:160])
        riadky.append(
            f'<article class="seo-deal">'
            f'<h3><a href="/{OUTPUT_ROOT}/{slug_id}/">{nazov}</a></h3>'
            f'<p class="seo-deal-m">{obchod}{" · " if obchod and cena else ""}'
            f'<strong>{cena}</strong>{povodna}{zlava_txt}</p>'
            f'{f"<p>{popis}</p>" if popis else ""}'
            f'</article>'
        )
    if not riadky:
        return ""
    return (f'{ZNACKA_OD}\n<div id="seo-dealy">\n<h2>Najnovšie zľavy a akcie</h2>\n'
            + "\n".join(riadky) + f'\n</div>\n{ZNACKA_PO}')


def zapis_seo_dealy(html_blok: str) -> bool:
    """Vymení blok medzi značkami v index.html. Vráti, či sa niečo zmenilo."""
    with open("index.html", encoding="utf-8") as f:
        s = f.read()
    i, j = s.find(ZNACKA_OD), s.find(ZNACKA_PO)
    if i < 0 or j < 0:
        logger.warning("V index.html chýbajú značky pre SEO dealy - preskakujem.")
        return False
    novy = s[:i] + html_blok + s[j + len(ZNACKA_PO):]
    if novy == s:
        return False
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(novy)
    return True


def build_sitemap(deal_urls: list, kod_urls: list | None = None) -> str:
    """deal_urls: zoznam (url, dátum dealu alebo None, expirovaný?)."""
    N = chr(10)
    dnes = date.today().isoformat()
    urls = [f"  <url>\n    <loc>{SITE_URL}/</loc>\n    <lastmod>{dnes}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>1.0</priority>\n  </url>"]
    # Statické stránky - menia sa zriedka, ale patria do sitemap.
    for static_path in ("podmienky.html", "ochrana-udajov.html"):
        urls.append(
            f"  <url>\n    <loc>{SITE_URL}/{static_path}</loc>\n"
            f"    <changefreq>yearly</changefreq>\n    <priority>0.3</priority>\n  </url>"
        )
    for u, kedy, expirovany in deal_urls:
        lastmod = f"\n    <lastmod>{kedy.isoformat()}</lastmod>" if kedy else ""
        # Expirovaný deal je pre Google menej dôležitý ako platný.
        priorita = "0.3" if expirovany else "0.7"
        frekvencia = "monthly" if expirovany else "weekly"
        urls.append(
            f"  <url>\n    <loc>{u}</loc>{lastmod}\n    <changefreq>{frekvencia}</changefreq>\n    <priority>{priorita}</priority>\n  </url>"
        )
    # Stránky kódov sa menia pri každom novom kupóne a sú to naše
    # najlepšie ciele na vyhľadávanie - preto vysoká priorita.
    for u in (kod_urls or []):
        urls.append(
            f"  <url>" + N + f"    <loc>{u}</loc>" + N + f"    <lastmod>{dnes}</lastmod>" + N
            + "    <changefreq>daily</changefreq>" + N + "    <priority>0.8</priority>" + N + "  </url>"
        )
    body = "\n".join(urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n'


def main():
    logger.info("=== Generovanie statických SEO stránok pre dealy ===")
    db = get_client()

    global AFFILIATE
    try:
        AFFILIATE = db.document("settings/affiliate").get().to_dict() or {}
    except Exception as e:
        logger.warning("Nastavenia affiliate sa nepodarilo načítať (%s) - odkazy budú čisté", e)
        AFFILIATE = {}

    docs = db.collection("deals").where("status", "==", "approved").stream()

    # Prvý prechod: vytiahnuť fotky a poskladať zoznam všetkých dealov -
    # kým nemáme všetky, nevieme ku ktorému dealu sú súvisiace.
    vsetky = []
    for doc in docs:
        deal_id = doc.id
        d = doc.to_dict()
        slug = slugify(d.get("title") or "deal")
        page_dir = os.path.join(OUTPUT_ROOT, f"{slug}-{deal_id}")
        os.makedirs(page_dir, exist_ok=True)

        # Fotka nahraná alebo orezaná v admine je v databáze ako data: URL.
        # Facebook ani Google si ju z nej nevezmú - uložíme ju ako súbor
        # vedľa stránky dealu a do og:image dáme jeho adresu.
        obr = d.get("imageUrl") or ""
        if obr.startswith("data:image/"):
            import base64
            try:
                hlavicka, data = obr.split(",", 1)
                pripona = "webp" if "webp" in hlavicka else ("png" if "png" in hlavicka else "jpg")
                with open(os.path.join(page_dir, f"foto.{pripona}"), "wb") as f:
                    f.write(base64.b64decode(data))
                d = {**d, "imageUrl": f"{SITE_URL}/{OUTPUT_ROOT}/{slug}-{deal_id}/foto.{pripona}"}
            except Exception as e:
                logger.warning("Fotku dealu %s sa nepodarilo uložiť: %s", deal_id, e)
                d = {**d, "imageUrl": None}
        vsetky.append((deal_id, d, slug))

    deal_urls = []
    vygenerovane = []
    pre_uvod = []
    podla_obchodu = {}
    generated = 0
    for deal_id, d, slug in vsetky:
        page_dir = os.path.join(OUTPUT_ROOT, f"{slug}-{deal_id}")
        vygenerovane.append(f"{slug}-{deal_id}")

        suvisiace = najdi_suvisiace(deal_id, d, vsetky)
        html_content = render_deal_page(deal_id, d, suvisiace)
        with open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_content)

        # Expirované do sitemap nepatria (stránka má noindex).
        if not je_expirovany(d):
            deal_urls.append((f"{SITE_URL}/{OUTPUT_ROOT}/{slug}-{deal_id}/", _datum_dealu(d), je_expirovany(d)))
        if not je_expirovany(d):
            pre_uvod.append((f"{slug}-{deal_id}", d))
            podla_obchodu.setdefault((d.get("store") or "").strip().lower(), []).append((f"{slug}-{deal_id}", d))
        generated += 1

    logger.info("Vygenerovaných %d stránok dealov", generated)

    # Stránky dealov, ktoré už nie sú zverejnené (skryté, archivované,
    # vymazané), zmažeme - inak by ostali na webe aj v Google navždy.
    # Mažeme len priečinky, ktoré vyzerajú ako stránka dealu.
    import shutil
    aktualne = set(vygenerovane)
    zmazane = 0
    for meno in os.listdir(OUTPUT_ROOT):
        cesta = os.path.join(OUTPUT_ROOT, meno)
        if (os.path.isdir(cesta) and meno not in aktualne
                and os.path.isfile(os.path.join(cesta, "index.html"))
                and re.search(r"-[A-Za-z0-9]{20}$", meno)):
            shutil.rmtree(cesta)
            zmazane += 1
    if zmazane:
        logger.info("Zmazaných %d stránok dealov, ktoré už nie sú zverejnené", zmazane)

    # Najnovšie platné dealy do úvodnej stránky.
    pre_uvod.sort(key=lambda x: _datum_dealu(x[1]) or date.min, reverse=True)
    if zapis_seo_dealy(render_seo_dealy(pre_uvod[:POCET_V_HTML])):
        logger.info("index.html: %d dealov vpísaných do HTML pre vyhľadávače",
                    min(len(pre_uvod), POCET_V_HTML))

    # Stranky zlavovych kodov podla obchodu.
    import generate_kody
    kod_urls = generate_kody.generuj(db, podla_obchodu)

    sitemap_xml = build_sitemap(deal_urls, kod_urls)
    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    logger.info("sitemap.xml aktualizovaný (%d URL spolu)", len(deal_urls) + 1)


if __name__ == "__main__":
    main()
