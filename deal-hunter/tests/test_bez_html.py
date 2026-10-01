from firestore_client import bez_html


def test_bez_html_feed_dyson():
    vstup = "<p><strong>Vysoký sací výkon</strong><br />Technológia&nbsp;HyperForce</p><p>Druhý odsek &amp; viac</p>"
    assert bez_html(vstup) == "Vysoký sací výkon\nTechnológia HyperForce\nDruhý odsek & viac"


def test_bez_html_zoznam_a_skript():
    vstup = "<ul><li>Jeden</li><li>Dva</li></ul><script>alert(1)</script>"
    assert bez_html(vstup) == "• Jeden\n• Dva"


def test_bez_html_obycajny_text_nezmeni():
    assert bez_html("Cena 5 < 10 eur") == "Cena 5 < 10 eur"
    assert bez_html(None) is None
    assert bez_html("Bez značiek") == "Bez značiek"
