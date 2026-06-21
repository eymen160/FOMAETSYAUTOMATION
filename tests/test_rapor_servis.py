# Rapor orkestrasyon servisi testleri: app.py'den ayrılan iş mantığı artık
# Flask istemcisi olmadan doğrudan test edilir (kaynak seçimi, join, Amazon
# ayrımı, Etsy zenginleştirme kompozisyonu).
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lazer import rapor_servis


def _yaz(tmp_path, ad, basliklar, satirlar):
    yol = tmp_path / ad
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(basliklar)
        for s in satirlar:
            w.writerow(s)
    return str(yol)


def test_kaynak_varsayilan():
    assert rapor_servis.kaynak_varsayilan({"ozet": {"x": 1}}) == "subtotal_shipping"
    assert rapor_servis.kaynak_varsayilan({}) == "order_total"


def test_ss_master_bazinda_ozet_join_amazon_eslesmeyen():
    analiz = {"ozet": {"magazalar": {
        "Shop A": {"siparis_sayisi": 5, "kargo_maliyet": 10.0,
                   "ciro_order_total": 100.0, "ciro_amount_paid": 98.0,
                   "ciro_subtotal_shipping": 95.0, "vergi": 8.0,
                   "kargo_musteri": 12.0},
        "My Amazon Store": {"siparis_sayisi": 3, "kargo_maliyet": 7.0,
                            "ciro_order_total": 50.0, "ciro_amount_paid": 50.0,
                            "ciro_subtotal_shipping": 48.0, "vergi": 4.0,
                            "kargo_musteri": 6.0},
        "Unmapped Shop": {"siparis_sayisi": 1, "kargo_maliyet": 1.0,
                          "ciro_order_total": 10.0, "ciro_amount_paid": 10.0,
                          "ciro_subtotal_shipping": 9.0, "vergi": 1.0,
                          "kargo_musteri": 2.0}}}}
    eslesme = {"Shop A": "Mağaza A"}   # Amazon otomatik; Unmapped eşleşmeyen
    ss_veri, amazon, eslesmeyen = rapor_servis.ss_master_bazinda(
        analiz, eslesme, None)
    assert ss_veri["Mağaza A"]["ciro_subtotal_shipping"] == 95.0
    assert ss_veri["Mağaza A"]["kargo_api"] == 10.0   # özet → kargo maliyeti
    assert [a["magaza"] for a in amazon] == ["My Amazon Store"]
    assert eslesmeyen == ["Unmapped Shop"]


def test_ss_master_bazinda_orders_adet_ve_kargo_csv():
    # Özet yoksa: gelir + adet Orders'tan, kargo maliyeti kargo CSV'sinden.
    analiz = {"orders": {"magazalar": {
        "Shop A": {"siparis_sayisi": 4, "adet": 9, "ciro_order_total": 80.0,
                   "ciro_amount_paid": 78.0, "vergi": 6.0,
                   "kargo_musteri": 7.0}}}}
    eslesme = {"Shop A": "Mağaza A"}
    kargo = {"magaza_kargo": {"Shop A": 15.0}}
    ss_veri, _, _ = rapor_servis.ss_master_bazinda(analiz, eslesme, kargo)
    h = ss_veri["Mağaza A"]
    assert h["adet"] == 9
    assert h["ciro_order_total"] == 80.0   # özet yok → orders gelir doldurur
    assert h["kargo_api"] == 15.0          # kargo CSV'sinden


def test_urun_master_bazinda_amazon_ve_eslesmeyen_haric():
    analiz = {"kalem": {"magaza_urun": {
        "Shop A": {"WineGlass": 3, "Diğer Ürün": 1},
        "Amazon X": {"WineGlass": 5},
        "Unmapped": {"Mug": 2}}}}
    eslesme = {"Shop A": "Mağaza A"}
    out = rapor_servis.urun_master_bazinda(analiz, eslesme)
    assert out == {"Mağaza A": {"WineGlass": 3, "Diğer Ürün": 1}}


def test_rapor_satirlari_form_kaynak_secimi():
    # Alan bazında kaynak seçimi: ciro/adet ShipStation, vergi form; reklam
    # her zaman formdan.
    analiz = {
        "mod": "form",
        "kayitlar": [{"magaza": "Mağaza A", "reklam": 50.0, "ek_odeme": 5.0,
                      "upgrade": 2.0, "ciro": 1000.0, "vergi": 90.0,
                      "kargo_musteri": 100.0, "kargo": 70.0, "adet": 30}],
        "orders": {"magazalar": {
            "Shop A": {"siparis_sayisi": 30, "adet": 33,
                       "ciro_order_total": 1100.0, "ciro_amount_paid": 1080.0,
                       "vergi": 0.0, "kargo_musteri": 120.0}}},
    }
    eslesme = {"Shop A": "Mağaza A"}
    kaynaklar = {"ciro": "shipstation", "adet": "shipstation", "vergi": "form"}
    satirlar, ss_veri, amazon, basliklar, kullanim = \
        rapor_servis.rapor_satirlari(analiz, eslesme, None, kaynaklar,
                                     "order_total")
    r = satirlar[0]
    assert r["ciro"] == 1100.0      # ShipStation
    assert r["adet"] == 33          # ShipStation (item bazlı)
    assert r["vergi"] == 90.0       # form beyanı
    assert r["reklam"] == 50.0      # her zaman form
    assert kullanim["ciro"] == "shipstation" and kullanim["vergi"] == "form"


def test_rapor_satirlari_formsuz_bos_ssveri():
    analiz = {"mod": "formsuz",
              "ozet": {"magazalar": {"Shop A": {
                  "ciro_subtotal_shipping": 1000.0, "ciro_order_total": 1100.0,
                  "ciro_amount_paid": 1090.0, "vergi": 100.0,
                  "kargo_musteri": 200.0, "kargo_maliyet": 150.0,
                  "siparis_sayisi": 20}}},
              "kalem": None, "elle": {}, "etsy_finansal": None,
              "reklam_magaza": None}
    satirlar, ss_veri, amazon, basliklar, kullanim = \
        rapor_servis.rapor_satirlari(analiz, {}, None, {}, "subtotal_shipping")
    assert ss_veri == {}    # formsuz modda ss_veri kullanılmaz
    assert all(v == "shipstation" for v in kullanim.values())
    assert any(s["magaza"] == "Shop A" for s in satirlar)


def test_etsy_enrichment_veri_yoksa():
    assert rapor_servis.etsy_enrichment({}, [], []) == (None, None, None)


def test_etsy_enrichment_join_meta(tmp_path):
    # ShipStation Order# → Store haritası + Etsy ödeme → mağazaya komisyon.
    ss = _yaz(tmp_path, "ss.csv", ["Order #", "Store"], [["1", "Shop A"]])
    pay = _yaz(tmp_path, "pay.csv",
               ["Order ID", "Fees", "Net Amount", "Refund Amount"],
               [["1", "3.0", "97.0", "0"]])
    fin, reklam, meta = rapor_servis.etsy_enrichment(
        {"etsy_payments": [pay], "etsy_orders": []}, [], [ss])
    assert meta["eslesen"] == 1 and meta["eslesmeyen"] == 0
    assert round(fin["Shop A"]["komisyon"], 2) == 3.0
