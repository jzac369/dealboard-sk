"""
Obchod, ktorý nás začne blokovať (napr. HTTP 403 na každú stránku), sa
nemá skúšať donekonečna - 9. 11. 2026 takto benulekaren.sk zablokoval
celú vzorku 40 stránok a beh na ňom zbytočne strávil takmer 3 minúty.

Scraper má po niekoľkých zlyhaniach za sebou obchod vzdať a ísť na
ďalší, no nemá si mýliť "stránka zlyhala" (blokovanie) so "stránka sa
stiahla, len na nej nie je zľava" (bežný stav u väčšiny obchodov).
"""
import scrapers.sitemap_hunt as sh

URLS = [f"https://test.sk/p{i}" for i in range(40)]


def _scraper(monkeypatch, odpovede, over_najde=lambda html: html == "<html>discount</html>"):
    """odpovede: {url: "blocked" | "nodiscount" | "discount"}. "blocked" = http_client.get vráti None
    (stránka sa nestiahla), ostatné = stránka sa stiahla (over_stranku rozhoduje, či je na nej zľava)."""
    volania = []

    def fake_get(url, check_robots=True):
        volania.append(url)
        r = odpovede[url]
        return None if r == "blocked" else f"<html>{r}</html>"

    monkeypatch.setattr(sh.http_client, "get", fake_get)
    monkeypatch.setattr(sh, "over_stranku", lambda url, html, typ, extra: object() if over_najde(html) else None)
    monkeypatch.setattr(sh, "vyber_vzorku", lambda urls, n, rng=None: urls[:n])
    scraper = sh.SitemapHuntScraper()
    monkeypatch.setattr(scraper, "_stiahni_sitemapu", lambda url, hlbka=0: URLS)
    return scraper, volania


def test_blokujuci_obchod_sa_vzda_po_par_pokusoch(monkeypatch):
    odpovede = {u: "blocked" for u in URLS}
    scraper, volania = _scraper(monkeypatch, odpovede)
    najdene = scraper._obchod({"domena": "test.sk", "sitemapy": ["https://test.sk/sitemap.xml"], "strana": 40})
    # Nemá skúsiť všetkých 40 stránok - prestane presne po prahu zo sitemap_hunt.BLOKOVANY_PO_ZA_SEBOU.
    assert len(volania) == sh.BLOKOVANY_PO_ZA_SEBOU
    assert najdene == []


def test_bezny_obchod_bez_zliav_sa_neoznaci_za_blokovany(monkeypatch):
    # Žiadna stránka nemá zľavu (bežný stav), ale všetky sa dajú stiahnuť - to NIE JE blokovanie.
    odpovede = {u: "nodiscount" for u in URLS}
    scraper, volania = _scraper(monkeypatch, odpovede)
    najdene = scraper._obchod({"domena": "test.sk", "sitemapy": ["https://test.sk/sitemap.xml"], "strana": 40})
    assert len(volania) == 40
    assert najdene == []


def test_niekolko_zlyhani_pod_prahom_nezastavi_obchod(monkeypatch):
    odpovede = {u: "nodiscount" for u in URLS}
    for u in URLS[:4]:          # 4 zlyhania za sebou, prah je 5
        odpovede[u] = "blocked"
    scraper, volania = _scraper(monkeypatch, odpovede)
    scraper._obchod({"domena": "test.sk", "sitemapy": ["https://test.sk/sitemap.xml"], "strana": 40})
    assert len(volania) == 40


def test_zlyhania_sa_pocitaju_len_za_sebou_nie_spolu(monkeypatch):
    # Zlyhanie, potom úspech, potom znova 4 zlyhania - počítadlo sa po úspechu vynuluje,
    # takže sa to (správne) nemá vzdať.
    odpovede = {u: "nodiscount" for u in URLS}
    odpovede[URLS[0]] = "blocked"
    for u in URLS[5:9]:
        odpovede[u] = "blocked"
    scraper, volania = _scraper(monkeypatch, odpovede)
    scraper._obchod({"domena": "test.sk", "sitemapy": ["https://test.sk/sitemap.xml"], "strana": 40})
    assert len(volania) == 40


def test_vynimka_pri_spracovani_sa_pocita_ako_zlyhanie(monkeypatch):
    """Výnimka (napr. pri rozobratí stránky) sa má správať rovnako ako zlyhané
    stiahnutie - nespadne celý beh a započíta sa do poistky proti blokovaniu."""
    volania = []

    def fake_get(url, check_robots=True):
        volania.append(url)
        if url in URLS[:5]:
            raise RuntimeError("boom")
        return "<html>nodiscount</html>"

    monkeypatch.setattr(sh.http_client, "get", fake_get)
    monkeypatch.setattr(sh, "over_stranku", lambda *a: None)
    monkeypatch.setattr(sh, "vyber_vzorku", lambda urls, n, rng=None: urls[:n])
    scraper = sh.SitemapHuntScraper()
    monkeypatch.setattr(scraper, "_stiahni_sitemapu", lambda url, hlbka=0: URLS)
    najdene = scraper._obchod({"domena": "test.sk", "sitemapy": ["https://test.sk/sitemap.xml"], "strana": 40})
    # 5 výnimiek za sebou = tiež poistka, nie pád celého behu.
    assert len(volania) == sh.BLOKOVANY_PO_ZA_SEBOU
    assert najdene == []
