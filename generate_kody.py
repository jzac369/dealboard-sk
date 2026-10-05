"""
Statické stránky zľavových kódov podľa obchodu.

PREČO VZNIKLI
"zľavový kód notino" je najčastejší typ dopytu v tejto oblasti. Na našej
stránke ho ale Google nenájde: Kódy sú len záložka, ktorá sa dopĺňa cez
JavaScript, a robot vidí prázdno. Pre každý obchod s aspoň dvoma platnými
kódmi preto vznikne vlastná stránka /kody/{obchod}/ ako obyčajné HTML.

Volá sa z generate_deal_pages.py, odkiaľ si berie aj spoločné pomôcky
(slugify, escape, affiliate_url). Samostatný súbor je to preto, že so
stránkami dealov nemá spoločné nič okrem nich.
"""

import json
import logging
import os
import shutil
from datetime import date

logger = logging.getLogger("kody")

KODY_ROOT = "kody"


def _g():
    """Spoločné pomôcky zo generate_deal_pages (import až tu, inak kruh)."""
    import generate_deal_pages as g
    return g


def _den(x):
    """Dátum z Firestore časovej pečiatky alebo z textu RRRR-MM-DD."""
    if x is None:
        return None
    if hasattr(x, "date"):
        try:
            return x.date()
        except Exception:
            return None
    try:
        return date.fromisoformat(str(x)[:10])
    except (ValueError, TypeError):
        return None


def kod_expirovany(k: dict) -> bool:
    d = _den(k.get("expiryISO") or k.get("expiryDate"))
    return bool(d and d < date.today())


def _sklonuj(n: int) -> str:
    return "kód" if n == 1 else ("kódy" if n < 5 else "kódov")


def render_obchod(obchod: str, kody: list, dealy: list) -> str:
    """Stránka so všetkými platnými kódmi jedného obchodu."""
    g = _g()
    esc, slug = g.escape, g.slugify(obchod)
    canonical = f"{g.SITE_URL}/{KODY_ROOT}/{slug}/"
    nadpis = f"Zľavové kódy {obchod}"
    popis = (f"Overené zľavové kódy a kupóny do {obchod} – {len(kody)} aktívnych "
             f"{_sklonuj(len(kody))} k {date.today().strftime('%d.%m.%Y')}. "
             f"Kód skopíruješ jedným klikom.")

    polozky, ponuky = [], []
    for k in kody:
        kod = esc(k.get("code") or "")
        zlava = esc(k.get("discount") or "Zľavový kód")
        kpopis = esc((k.get("description") or "").strip())
        plati = esc(k.get("expiryDate") or "")
        url = esc(g.affiliate_url(k.get("url") or g.SITE_URL))
        polozky.append(
            f'<li class="k"><div class="k-h"><b>{zlava}</b><code>{kod}</code></div>'
            + (f"<p>{kpopis}</p>" if kpopis else "")
            + f'<p class="k-m">' + (f"Platí do {plati} · " if plati else "")
            + f'<a href="{url}" target="_blank" rel="nofollow sponsored noopener">'
            f'Uplatniť v {esc(obchod)} →</a></p></li>'
        )
        platnost = _den(k.get("expiryISO") or k.get("expiryDate"))
        ponuky.append({
            "@type": "Offer",
            "name": k.get("discount") or f"Zľavový kód {obchod}",
            "description": (k.get("description") or "")[:200] or f"Zľavový kód do {obchod}.",
            "url": canonical,
            "seller": {"@type": "Organization", "name": obchod},
            **({"priceValidUntil": platnost.isoformat()} if platnost else {}),
        })

    dealy_html = ""
    if dealy:
        riadky = "".join(
            f'<li><a href="/{g.OUTPUT_ROOT}/{sid}/">{esc(d.get("title") or "")}</a>'
            + (f" – <strong>{g._cena(d)}</strong>" if g._cena(d) else "")
            + "</li>"
            for sid, d in dealy[:8]
        )
        dealy_html = f"<h2>Aktuálne zľavy v {esc(obchod)}</h2><ul class=\"dz\">{riadky}</ul>"

    ld_json = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": nadpis,
        "url": canonical,
        "numberOfItems": len(ponuky),
        "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": o}
                            for i, o in enumerate(ponuky)],
    }, ensure_ascii=False, indent=2)

    drobcek = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "HenKukaj.sk", "item": g.SITE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": "Zľavové kódy",
             "item": f"{g.SITE_URL}/{KODY_ROOT}/"},
            {"@type": "ListItem", "position": 3, "name": obchod, "item": canonical},
        ],
    }, ensure_ascii=False, indent=2)

    return f"""<!DOCTYPE html>
<html lang="sk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(nadpis)} – {len(kody)} aktívnych kupónov | HenKukaj.sk</title>
<meta name="description" content="{esc(popis)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="HenKukaj.sk">
<meta property="og:title" content="{esc(nadpis)}">
<meta property="og:description" content="{esc(popis)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{g.SITE_URL}/images/logo.png">
<meta property="og:locale" content="sk_SK">
<script type="application/ld+json">
{ld_json}
</script>
<script type="application/ld+json">
{drobcek}
</script>
{STYL}
</head>
<body>
  <div class="wrap">
    <div class="card">
      <p class="sub"><a class="home" href="{g.SITE_URL}/">HenKukaj.sk</a> ›
        <a class="home" href="/{KODY_ROOT}/">Zľavové kódy</a> › {esc(obchod)}</p>
      <h1>{esc(nadpis)}</h1>
      <p class="sub">{esc(popis)}</p>
      <ul>{"".join(polozky)}</ul>
      {dealy_html}
      <a class="btn" href="/{KODY_ROOT}/">Zľavové kódy ďalších e-shopov →</a>
      <p style="margin-top:20px;"><a class="home" href="{g.SITE_URL}/">← Späť na HenKukaj.sk</a></p>
    </div>
  </div>
</body>
</html>
"""


STYL = """<style>
  body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background:#EDEDED;
    color:#1A1A1A; margin:0; padding:24px 16px; }
  .wrap { max-width:720px; margin:0 auto; }
  .card { background:#fff; border-radius:8px; border:1px solid #E2E2E2; padding:20px; }
  h1 { font-size:1.4rem; margin:0 0 6px; }
  h2 { font-size:1.05rem; margin:24px 0 8px; }
  .sub { color:#707070; font-size:.9rem; margin:0 0 18px; }
  ul { list-style:none; padding:0; margin:0; }
  .k { border:1px solid #E2E2E2; border-radius:8px; padding:12px 14px; margin-bottom:10px; }
  .k-h { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .k code { background:#FFF1E6; color:#B8460A; font-weight:700; padding:4px 12px; border-radius:6px; }
  .k p { margin:6px 0 0; font-size:.88rem; color:#444; line-height:1.5; }
  .k-m { color:#707070; font-size:.82rem; }
  .k-m a { color:#C44C0A; font-weight:600; }
  .dz li { padding:7px 0; border-bottom:1px solid #EEE; font-size:.9rem; }
  .dz li:last-child { border-bottom:none; }
  .dz a { color:#1A1A1A; }
  .zoz li { display:flex; justify-content:space-between; gap:10px; padding:10px 0;
    border-bottom:1px solid #EEE; }
  .zoz li:last-child { border-bottom:none; }
  .zoz a { color:#1A1A1A; font-weight:600; text-decoration:none; }
  .zoz a:hover { color:#C44C0A; }
  .zoz span { color:#707070; font-size:.85rem; white-space:nowrap; }
  .btn { display:inline-block; background:#C44C0A; color:#fff; text-decoration:none;
    font-weight:700; padding:12px 22px; border-radius:22px; margin-top:18px; }
  a.home { color:#707070; font-size:.85rem; }
</style>"""


def render_rozcestnik(obchody: list) -> str:
    """Prehľad všetkých obchodov so zľavovými kódmi."""
    g = _g()
    esc = g.escape
    canonical = f"{g.SITE_URL}/{KODY_ROOT}/"
    spolu = sum(n for _, n in obchody)
    popis = (f"Overené zľavové kódy a kupóny do {len(obchody)} slovenských a českých "
             f"e-shopov – {spolu} aktívnych {_sklonuj(spolu)} k "
             f"{date.today().strftime('%d.%m.%Y')}.")
    polozky = "".join(
        f'<li><a href="/{KODY_ROOT}/{g.slugify(o)}/">Zľavové kódy {esc(o)}</a>'
        f'<span>{n} {_sklonuj(n)}</span></li>'
        for o, n in obchody
    )
    return f"""<!DOCTYPE html>
<html lang="sk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Zľavové kódy a kupóny – {spolu} aktívnych | HenKukaj.sk</title>
<meta name="description" content="{esc(popis)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="HenKukaj.sk">
<meta property="og:title" content="Zľavové kódy a kupóny">
<meta property="og:description" content="{esc(popis)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{g.SITE_URL}/images/logo.png">
<meta property="og:locale" content="sk_SK">
{STYL}
</head>
<body>
  <div class="wrap">
    <div class="card">
      <p class="sub"><a class="home" href="{g.SITE_URL}/">HenKukaj.sk</a> › Zľavové kódy</p>
      <h1>Zľavové kódy a kupóny</h1>
      <p class="sub">{esc(popis)}</p>
      <ul class="zoz">{polozky}</ul>
      <p style="margin-top:20px;"><a class="home" href="{g.SITE_URL}/">← Späť na HenKukaj.sk</a></p>
    </div>
  </div>
</body>
</html>
"""


def generuj(db, dealy_podla_obchodu: dict) -> list:
    """Vytvorí /kody/ a /kody/{obchod}/. Vráti adresy pre sitemap."""
    g = _g()
    try:
        kupony = [k.to_dict() or {} for k in db.collection("coupons").stream()]
    except Exception as e:
        logger.warning("Zľavové kódy sa nepodarilo načítať (%s) - stránky kódov preskakujem.", e)
        return []

    podla_obchodu: dict[str, list] = {}
    for k in kupony:
        if k.get("status") != "approved" or kod_expirovany(k):
            continue
        obchod = (k.get("store") or "").strip()
        if obchod:
            podla_obchodu.setdefault(obchod, []).append(k)

    # Obchod s jediným kódom vlastnú stránku nedostane - stránka s jednou
    # položkou je presne to, čo Google hodnotí ako slabý obsah.
    podla_obchodu = {o: ks for o, ks in podla_obchodu.items() if len(ks) >= 2}

    os.makedirs(KODY_ROOT, exist_ok=True)
    urls, prehlad, vygenerovane = [], [], set()
    for obchod, ks in sorted(podla_obchodu.items(), key=lambda x: (-len(x[1]), x[0].lower())):
        ks.sort(key=lambda k: -(k.get("votes") or 0))
        slug = g.slugify(obchod)
        vygenerovane.add(slug)
        priecinok = os.path.join(KODY_ROOT, slug)
        os.makedirs(priecinok, exist_ok=True)
        with open(os.path.join(priecinok, "index.html"), "w", encoding="utf-8") as f:
            f.write(render_obchod(obchod, ks, dealy_podla_obchodu.get(obchod.lower(), [])))
        urls.append(f"{g.SITE_URL}/{KODY_ROOT}/{slug}/")
        prehlad.append((obchod, len(ks)))

    if prehlad:
        with open(os.path.join(KODY_ROOT, "index.html"), "w", encoding="utf-8") as f:
            f.write(render_rozcestnik(prehlad))
        urls.insert(0, f"{g.SITE_URL}/{KODY_ROOT}/")

    # Obchody, ktorým kódy vypršali, nesmú na webe ostať navždy.
    zmazane = 0
    for meno in os.listdir(KODY_ROOT):
        cesta = os.path.join(KODY_ROOT, meno)
        if os.path.isdir(cesta) and meno not in vygenerovane:
            shutil.rmtree(cesta)
            zmazane += 1
    logger.info("Stránky kódov: %d obchodov, %d zmazaných", len(prehlad), zmazane)
    return urls
