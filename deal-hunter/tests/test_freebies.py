"""Freebies: z odpovede Epic Games sa berú len hry s aktívnou akciou za 0 €."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.freebies import epic_freebies, steam_freebies  # noqa: E402


def _hra(nazov, povodna, zlavnena, koniec_o_hodin, slug="hra"):
    koniec = (datetime.now(timezone.utc) + timedelta(hours=koniec_o_hodin)).isoformat().replace("+00:00", "Z")
    return {
        "title": nazov, "productSlug": slug, "keyImages": [{"type": "Thumbnail", "url": "https://x/i.jpg"}],
        "price": {"totalPrice": {"originalPrice": povodna, "discountPrice": zlavnena}},
        "promotions": {"promotionalOffers": [{"promotionalOffers": [{"endDate": koniec}]}]},
    }


def _data(*hry):
    return {"data": {"Catalog": {"searchStore": {"elements": list(hry)}}}}


def test_epic_berie_len_aktivnu_hru_zadarmo():
    vysledok = epic_freebies(_data(
        _hra("Zadarmo", 2239, 0, 48, "zadarmo"),          # áno
        _hra("Len zlava", 1999, 799, 48, "zlava"),       # nie: nie je za 0 €
        _hra("Stale zadarmo", 0, 0, 48, "f2p"),          # nie: free-to-play nie je akcia
        _hra("Konci hned", 1000, 0, 1, "konci"),          # nie: skončí do 3 hodín
    ))
    assert [c.url for c in vysledok] == ["https://store.epicgames.com/sk/p/zadarmo"]
    c = vysledok[0]
    assert c.zadarmo and c.deal_price == 0 and c.original_price == 22.39
    assert c.valid_until and not c.is_already_expired


def test_steam_bez_hodnoteni_sa_nepouzije():
    blok = ('<a href="https://store.steampowered.com/app/1/Hra/?snr=1" class="search_result_row">'
            '<img src="https://x/c.jpg"><span class="title">Hra</span>{recenzie}'
            '<div class="discount_block" data-discount="100"><div class="discount_original_price">4,99€</div></div></a>')
    bez = {"results_html": blok.format(recenzie="")}
    s = {"results_html": blok.format(recenzie='<span class="search_review_summary positive"></span>')}
    assert steam_freebies(bez) == []
    vysledok = steam_freebies(s)
    assert len(vysledok) == 1 and vysledok[0].original_price == 4.99
