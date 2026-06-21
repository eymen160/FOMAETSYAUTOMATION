# Formsuz rapor modu testleri (master form olmadan ham veriden üretim).
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lazer import formsuz


def _ozet():
    # shipstation_csv.ozet_isle çıktısı biçimi
    return {"magazalar": {
        "Etched Elegance Shop": {"ciro_subtotal_shipping": 1000.0,
                                 "ciro_order_total": 1100.0,
                                 "ciro_amount_paid": 1090.0, "vergi": 100.0,
                                 "kargo_musteri": 200.0, "kargo_maliyet": 150.0,
                                 "siparis_sayisi": 20},
        "Foma Amazon Store": {"ciro_subtotal_shipping": 5000.0,
                              "ciro_order_total": 5500.0, "ciro_amount_paid": 5400.0,
                              "vergi": 500.0, "kargo_musteri": 800.0,
                              "kargo_maliyet": 600.0, "siparis_sayisi": 100}}}


def _kalem():
    return {"magaza_urun": {
        "Etched Elegance Shop": {"Coffee Mug": 12, "Wine Tmblr": 8,
                                 "Diğer Ürün": 3}}}


def test_formsuz_magaza_ham_veriden():
    s, amazon, basliklar = formsuz.rapor_satirlari(_ozet(), _kalem(), {}, {})
    adlar = [r["magaza"] for r in s]
    assert "Etched Elegance Shop" in adlar
    assert all("Amazon" not in a for a in adlar)   # Amazon hariç


def test_formsuz_ciro_subtotal_shipping():
    s, _, _ = formsuz.rapor_satirlari(_ozet(), _kalem(), {}, {},
                                      "subtotal_shipping")
    r = next(x for x in s if x["magaza"] == "Etched Elegance Shop")
    assert r["ciro"] == 1000.0       # subtotal+shipping
    assert r["vergi"] == 100.0       # tax
    assert r["kargo"] == 150.0       # shipping cost
    assert r["kargo_musteri"] == 200.0


def test_formsuz_adet_kalemden():
    s, _, _ = formsuz.rapor_satirlari(_ozet(), _kalem(), {}, {})
    r = next(x for x in s if x["magaza"] == "Etched Elegance Shop")
    assert r["adet"] == 12 + 8 + 3   # kalem ürün adetleri toplamı


def test_formsuz_adet_kalem_yoksa_siparis():
    s, _, _ = formsuz.rapor_satirlari(_ozet(), None, {}, {})
    r = next(x for x in s if x["magaza"] == "Etched Elegance Shop")
    assert r["adet"] == 20           # kalem yok → sipariş sayısı


def test_formsuz_amazon_ayri():
    _, amazon, _ = formsuz.rapor_satirlari(_ozet(), _kalem(), {}, {})
    assert len(amazon) == 1
    assert amazon[0]["magaza"] == "Foma Amazon Store"
    assert amazon[0]["kargo"] == 600.0


def test_formsuz_elle_girdiler():
    elle = {"Etched Elegance Shop": {"reklam": 300, "ilave_odeme": 50,
                                     "upgrade": 5}}
    s, _, _ = formsuz.rapor_satirlari(_ozet(), _kalem(), elle, {})
    r = next(x for x in s if x["magaza"] == "Etched Elegance Shop")
    assert r["reklam"] == 300 and r["ilave_odeme"] == 50 and r["upgrade"] == 5


def test_formsuz_kanonik_yeniden_adlandirma():
    # store_mapping ile ShipStation adı kanonik ada çevrilir
    s, _, _ = formsuz.rapor_satirlari(
        _ozet(), _kalem(), {}, {"Etched Elegance Shop": "Etched Elegance"})
    assert any(r["magaza"] == "Etched Elegance" for r in s)


def test_elle_kaydet_yukle(tmp_path):
    yol = str(tmp_path / "elle.json")
    formsuz.elle_kaydet("2026-05", {"A": {"reklam": 10}}, yol)
    formsuz.elle_kaydet("2026-05", {"B": {"upgrade": 2}}, yol)
    v = formsuz.elle_yukle(yol)
    assert v["2026-05"]["A"]["reklam"] == 10
    assert v["2026-05"]["B"]["upgrade"] == 2


def test_formsuz_etsy_finansal_zenginlestirir():
    # Etsy komisyon/net/iade ss_store anahtarıyla satıra eklenmeli
    etsy_fin = {"Etched Elegance Shop": {"komisyon": 38.0, "net": 962.0,
                                         "brut": 1000.0, "kdv": 0.0,
                                         "iade": 25.0, "iade_sayisi": 1}}
    s, _, _ = formsuz.rapor_satirlari(_ozet(), _kalem(), {}, {},
                                      etsy_finansal=etsy_fin)
    r = next(x for x in s if x["magaza"] == "Etched Elegance Shop")
    assert r["komisyon"] == 38.0 and r["net"] == 962.0
    assert r["iade"] == 25.0 and r["iade_sayisi"] == 1


def test_formsuz_etsy_finansal_kanonik_eslesir():
    # Etsy ss_store adı, store_mapping ile kanonik ada toplanmalı
    etsy_fin = {"Etched Elegance Shop": {"komisyon": 10.0, "net": 90.0,
                                         "iade": 0.0, "iade_sayisi": 0}}
    s, _, _ = formsuz.rapor_satirlari(
        _ozet(), _kalem(), {}, {"Etched Elegance Shop": "Etched Elegance"},
        etsy_finansal=etsy_fin)
    r = next(x for x in s if x["magaza"] == "Etched Elegance")
    assert r["komisyon"] == 10.0 and r["net"] == 90.0


def test_formsuz_reklam_otomatik_ve_elle_oncelik():
    reklam = {"Etched Elegance Shop": 120.0}
    # Elle girdi yoksa otomatik reklam gelir
    s, _, _ = formsuz.rapor_satirlari(_ozet(), _kalem(), {}, {},
                                      reklam_magaza=reklam)
    r = next(x for x in s if x["magaza"] == "Etched Elegance Shop")
    assert r["reklam"] == 120.0
    # Elle girdi varsa o öncelikli (otomatiği ezer)
    elle = {"Etched Elegance Shop": {"reklam": 300}}
    s2, _, _ = formsuz.rapor_satirlari(_ozet(), _kalem(), elle, {},
                                       reklam_magaza=reklam)
    r2 = next(x for x in s2 if x["magaza"] == "Etched Elegance Shop")
    assert r2["reklam"] == 300


def test_donem_anahtari():
    assert formsuz.donem_anahtari(2026, 5) == "2026-05"
