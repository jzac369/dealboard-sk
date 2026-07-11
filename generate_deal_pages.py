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

import os
import re
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


def render_deal_page(deal_id: str, d: dict) -> str:
    title = d.get("title") or "Deal"
    store = d.get("store") or ""
    category = d.get("category") or ""
    description = d.get("description") or f"{title} v obchode {store}."
    image_url = d.get("imageUrl") or f"{SITE_URL}/images/logo.png"
    deal_price = d.get("dealPrice")
    original_price = d.get("originalPrice")
    currency_symbol = d.get("currency") or "€"
    currency_code = CURRENCY_MAP.get(currency_symbol, "EUR")
    target_url = d.get("url") or SITE_URL
    slug = slugify(title)
    page_path = f"{slug}-{deal_id}"
    canonical_url = f"{SITE_URL}/{OUTPUT_ROOT}/{page_path}/"
    spa_url = f"{SITE_URL}/?deal={deal_id}"

    price_html = ""
    if deal_price:
        price_html = f'<span style="font-size:1.4rem;font-weight:800;color:#2E8B3D;">{deal_price:.2f} {currency_symbol}</span>'
        if original_price and original_price > deal_price:
            price_html += f' <span style="text-decoration:line-through;color:#707070;font-size:0.9rem;">{original_price:.2f} {currency_symbol}</span>'

    offers_json = ""
    if deal_price:
        offers_json = f"""
  "offers": {{
    "@type": "Offer",
    "price": "{deal_price:.2f}",
    "priceCurrency": "{currency_code}",
    "url": "{escape(target_url)}",
    "availability": "https://schema.org/InStock"
  }},"""

    meta_description = (description[:155] + "…") if len(description) > 158 else description

    return f"""<!DOCTYPE html>
<html lang="sk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)} – HenKukaj.sk</title>
<meta name="description" content="{escape(meta_description)}">
<link rel="canonical" href="{canonical_url}">

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
{{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": {repr(title)},
  "image": {repr(image_url)},
  "description": {repr(meta_description)},{offers_json}
  "brand": {{"@type": "Brand", "name": {repr(store)}}}
}}
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
</style>
</head>
<body>
  <div class="card">
    <img src="{escape(image_url)}" alt="{escape(title)}" loading="lazy">
    <div class="body">
      <div class="meta">{escape(store)} · {escape(category)}</div>
      <h1>{escape(title)}</h1>
      <p>{price_html}</p>
      <p>{escape(description)}</p>
      <a class="btn" href="{escape(target_url)}" target="_blank" rel="noopener">Zobraziť ponuku v e-shope →</a>
      <a class="btn secondary" href="{spa_url}">Hlasovať / komentovať na HenKukaj.sk</a>
      <p style="margin-top:24px;"><a class="home" href="{SITE_URL}/">← Späť na HenKukaj.sk</a></p>
    </div>
  </div>
</body>
</html>
"""


def build_sitemap(deal_urls: list[str]) -> str:
    urls = [f"  <url>\n    <loc>{SITE_URL}/</loc>\n    <changefreq>daily</changefreq>\n    <priority>1.0</priority>\n  </url>"]
    for u in deal_urls:
        urls.append(
            f"  <url>\n    <loc>{u}</loc>\n    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n  </url>"
        )
    body = "\n".join(urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n'


def main():
    logger.info("=== Generovanie statických SEO stránok pre dealy ===")
    db = get_client()

    docs = db.collection("deals").where("status", "==", "approved").stream()

    deal_urls = []
    generated = 0
    for doc in docs:
        deal_id = doc.id
        d = doc.to_dict()

        slug = slugify(d.get("title") or "deal")
        page_dir = os.path.join(OUTPUT_ROOT, f"{slug}-{deal_id}")
        os.makedirs(page_dir, exist_ok=True)

        html_content = render_deal_page(deal_id, d)
        with open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html_content)

        deal_urls.append(f"{SITE_URL}/{OUTPUT_ROOT}/{slug}-{deal_id}/")
        generated += 1

    logger.info("Vygenerovaných %d stránok dealov", generated)

    sitemap_xml = build_sitemap(deal_urls)
    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    logger.info("sitemap.xml aktualizovaný (%d URL spolu)", len(deal_urls) + 1)


if __name__ == "__main__":
    main()
