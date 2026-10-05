"""Pamäť agenta: lehoty, orezanie a denný strop.

Po 5. 10. 2026, keď agent za deň navrhol vyše 230 duplicitných dealov.
"""
from datetime import date

import firestore_client as fc


def test_zapis_a_rozobratie():
    assert fc._rozober("abc|739000") == ("abc", 739000)
    assert fc._rozober("abc") == ("abc", None)
    # Kľúč môže sám obsahovať zvislú čiaru - rozhoduje posledná.
    assert fc._rozober("a|b|739000") == ("a|b", 739000)
    kluc = fc._kluc_s_datumom("x")
    assert fc._rozober(kluc) == ("x", date.today().toordinal())


def test_stare_zaznamy_uz_neblokuju():
    dnes = fc._dnes_cislo()
    zaznamy = [fc._kluc_s_datumom("nove", dnes),
               fc._kluc_s_datumom("stare", dnes - 30),
               "bez_datumu"]
    hranica = dnes - 10
    aktivne = {k for k, d in map(fc._rozober, zaznamy) if d is not None and d >= hranica}
    assert aktivne == {"nove"}
