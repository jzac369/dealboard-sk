"""
Poistky proti opakovanému spúšťaniu a zaplavenému Telegramu.

Všetky tri sa prejavia len vtedy, keď Firestore odpovedá chybou - preto
to tu simulujeme. Presne tento stav 5. 10. 2026 nikto netestoval a agent
navrhol za deň vyše 230 tých istých dealov.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import planovac
import telegram_bot


class RozbitaDatabaza:
    """Čokoľvek sa z nej pokúsime prečítať, skončí ako vyčerpaná kvóta."""

    def document(self, _cesta):
        return self

    def get(self):
        raise RuntimeError("429 Quota exceeded.")


def test_nedostupny_rozvrh_nespusti_nic(monkeypatch):
    poslane = []
    monkeypatch.setattr(planovac.poplach, "nahlas",
                        lambda kod, *a, **k: poslane.append(kod))

    rozvrh = planovac.nacitaj(RozbitaDatabaza())
    assert rozvrh["nedoveryhodny"] is True
    # Bez záznamu o poslednom behu by sa ranný termín tváril ako
    # neodbavený a plánovač by úlohu spúšťal každých päť minút.
    teraz = datetime(2026, 10, 5, 12, 0, tzinfo=ZoneInfo("Europe/Bratislava"))
    assert planovac.co_spustit(rozvrh, teraz) == []
    # A nezlyhá to potichu - o poruche sa dozvieme.
    assert "kvota" in poslane


class Hotovo:
    returncode = 0
    stdout = ""
    stderr = ""


def test_poistka_zastavi_opakovane_spustanie(monkeypatch):
    """Ani pri zlyhanom zápise sa jedna úloha nespustí viac než STROP_SPUSTENI."""
    planovac.POCET_SPUSTENI.clear()
    planovac.SPUSTENE_V_BEHU.clear()
    spustene = []
    poplachy = []
    monkeypatch.setattr(planovac.subprocess, "run",
                        lambda prikaz, **k: spustene.append(prikaz[-1]) or Hotovo())
    # Zápis do databázy zlyháva - to je prípad z 5. 10. 2026.
    monkeypatch.setattr(planovac, "zapis_beh",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429 Quota exceeded.")))
    monkeypatch.setattr(planovac.poplach, "nahlas",
                        lambda kod, *a, **k: poplachy.append(kod))

    # Plánovač sa dožaduje tej istej úlohy dvadsaťkrát za sebou.
    for _ in range(20):
        planovac.spusti_ulohy(None, [("agent", None, True)], nasucho=False)

    assert len(spustene) == planovac.STROP_SPUSTENI
    assert "slucka" in poplachy
    planovac.POCET_SPUSTENI.clear()
    planovac.SPUSTENE_V_BEHU.clear()


def test_telegram_neposle_viac_nez_strop(monkeypatch):
    monkeypatch.setattr(telegram_bot, "_POSLANE_NAVRHY", 0)
    monkeypatch.setattr(telegram_bot, "is_configured", lambda: True)
    monkeypatch.setattr(telegram_bot, "_call", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(telegram_bot, "_format_caption", lambda d: "x")

    deal = {"title": "x", "price": 1}
    poslanych = sum(telegram_bot.send_deal_for_approval(f"d{i}", deal)
                    for i in range(telegram_bot.MAX_NAVRHOV_ZA_BEH + 10))
    assert poslanych == telegram_bot.MAX_NAVRHOV_ZA_BEH


# ── denný žiar: starým dealom sa hlasy nepridávajú ───────────────────

def test_ziar_obide_stare_dealy():
    from datetime import datetime, timedelta, timezone
    import denny_ziar

    teraz = datetime.now(timezone.utc)
    hranica = teraz - timedelta(days=30)

    assert denny_ziar.je_stary({"zverejnene": teraz - timedelta(days=31)}, hranica)
    assert not denny_ziar.je_stary({"zverejnene": teraz - timedelta(days=29)}, hranica)
    # Staršie dealy "zverejnene" nemajú, rozhoduje čas schválenia.
    assert denny_ziar.je_stary({"timestamp": teraz - timedelta(days=40)}, hranica)
    assert not denny_ziar.je_stary({"timestamp": teraz - timedelta(days=1)}, hranica)
    # Bez času radšej nepridávame nič.
    assert denny_ziar.je_stary({}, hranica)


# ── adresy feedov sa nesmú dostať do verejného logu ──────────────────

def test_tajna_adresa_v_logu():
    import http_client
    url = "https://feeds.example.sk/export/dognet654abc.xml?token=TAJNE123&secret=XYZ"
    http_client.tajne(url)
    assert http_client.ukaz(url) == "feeds.example.sk/…"
    # requests vkladá adresu do textu výnimky - aj odtiaľ musí zmiznúť.
    chyba = ("HTTPSConnectionPool(host='feeds.example.sk', port=443): Max retries "
             "exceeded with url: /export/dognet654abc.xml?token=TAJNE123&secret=XYZ")
    vystup = http_client.ukaz_chybu(chyba, url)
    assert "TAJNE123" not in vystup and "dognet654abc" not in vystup
    # Bežné adresy produktov sa vypisujú celé, kvôli ladeniu.
    assert http_client.ukaz("https://www.alza.sk/produkt") == "https://www.alza.sk/produkt"
