# Etsy zenginleştirme testleri: Order# join, komisyon/net/iade, reklam.
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lazer import etsy


def _yaz(tmp_path, ad, basliklar, satirlar):
    yol = tmp_path / ad
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(basliklar)
        for s in satirlar:
            w.writerow(s)
    return str(yol)


def test_magaza_haritasi_shipstation(tmp_path):
    # Kalem (Order # + Store) ve ozet (Order - Number + Market - Store Name)
    kalem = _yaz(tmp_path, "kalem.csv",
                 ["Order #", "Store", "Item Name"],
                 [["100", "Shop A", "X"], ["101", "Shop B", "Y"]])
    ozet = _yaz(tmp_path, "ozet.csv",
                ["Order - Number", "Market - Store Name", "Amount - Order Total"],
                [["102", "Shop C", "9"]])
    h = etsy.magaza_haritasi([kalem, ozet])
    assert h == {"100": "Shop A", "101": "Shop B", "102": "Shop C"}


def test_magaza_haritasi_ilk_kazanir(tmp_path):
    a = _yaz(tmp_path, "a.csv", ["Order #", "Store"], [["1", "First"]])
    b = _yaz(tmp_path, "b.csv", ["Order #", "Store"], [["1", "Second"]])
    assert etsy.magaza_haritasi([a, b])["1"] == "First"


def test_payments_topla_toplar(tmp_path):
    p = _yaz(tmp_path, "pay.csv",
             ["Order ID", "Gross Amount", "Fees", "Net Amount",
              "VAT Amount", "Refund Amount"],
             [["1", "21.06", "0.92", "20.14", "0.00", "22.46"],
              ["2", "99.20", "3.42", "95.78", "0.00", "0.00"]])
    v = etsy.payments_topla([p])
    assert round(v["1"]["komisyon"], 2) == 0.92
    assert round(v["1"]["iade"], 2) == 22.46
    assert round(v["2"]["net"], 2) == 95.78
    assert v["2"]["iade"] == 0.0
    assert v["1"]["kaynak"] == "payment"


def test_siparis_finansal_orders_yalniz_bosluk(tmp_path):
    # Order#1 hem ödemede hem siparişte → ödeme kazanır (üzerine yazılmaz);
    # Order#2 yalnız siparişte → sipariş kaydından gelir.
    pay = _yaz(tmp_path, "pay.csv",
               ["Order ID", "Fees", "Net Amount"],
               [["1", "1.00", "10.00"]])
    ords = _yaz(tmp_path, "ord.csv",
                ["Order ID", "Card Processing Fees", "Order Net", "Order Total"],
                [["1", "9.99", "999"], ["2", "2.00", "20.00", "22.00"]])
    fin = etsy.siparis_finansal([pay], [ords])
    assert fin["1"]["komisyon"] == 1.00      # ödeme kazandı
    assert fin["1"]["kaynak"] == "payment"
    assert fin["2"]["komisyon"] == 2.00      # siparişten doldu
    assert fin["2"]["kaynak"] == "order"


def test_magaza_finansal_join_ve_iade(tmp_path):
    harita = {"1": "Shop A", "2": "Shop A", "3": "Shop B"}
    fin = {
        "1": {"brut": 100.0, "komisyon": 4.0, "net": 96.0, "kdv": 0.0,
              "iade": 0.0, "kaynak": "payment"},
        "2": {"brut": 50.0, "komisyon": 2.0, "net": 48.0, "kdv": 0.0,
              "iade": 50.0, "kaynak": "payment"},
        "3": {"brut": 30.0, "komisyon": 1.0, "net": 29.0, "kdv": 0.0,
              "iade": 0.0, "kaynak": "payment"},
        "999": {"brut": 9.0, "komisyon": 1.0, "net": 8.0, "kdv": 0.0,
                "iade": 0.0, "kaynak": "payment"},  # ShipStation'da yok
    }
    mf = etsy.magaza_finansal(harita, fin)
    assert mf["eslesen"] == 3 and mf["eslesmeyen"] == 1
    a = mf["magazalar"]["Shop A"]
    assert a["komisyon"] == 6.0 and a["net"] == 144.0 and a["siparis"] == 2
    assert a["iade"] == 50.0 and a["iade_sayisi"] == 1
    assert "999" not in [i["order"] for i in mf["iade_kalemleri"]]
    assert mf["iade_kalemleri"][0]["order"] == "2"   # tek iade


def test_reklam_topla_tip_filtreler(tmp_path):
    # "Type" kolonu varsa yalnız pazarlama/reklam satırları sayılır
    r = _yaz(tmp_path, "stmt.csv",
             ["Date", "Type", "Store", "Amount"],
             [["1/2", "Marketing", "Shop A", "-12.50"],
              ["1/3", "Sale", "Shop A", "100.00"],
              ["1/4", "Etsy Ads", "Shop B", "8.00"],
              ["1/5", "Fee", "Shop B", "3.00"]])
    out = etsy.reklam_topla([r])
    assert out["toplam"] == 20.50          # 12.50 + 8.00 (işaret yok sayılır)
    assert out["magaza"] == {"Shop A": 12.50, "Shop B": 8.00}
    assert out["kayit"] == 2


def test_reklam_topla_tutar_kolonu_yoksa_atlar(tmp_path):
    r = _yaz(tmp_path, "x.csv", ["Date", "Clicks"], [["1/2", "5"]])
    assert etsy.reklam_topla([r]) == {"toplam": 0.0, "magaza": {}, "kayit": 0}


def test_payments_donem_filtresi(tmp_path):
    # Order Date'e göre yalnız Mayıs 2026 sayılır (4 haneli yıl biçimi)
    p = _yaz(tmp_path, "pay.csv",
             ["Order ID", "Order Date", "Fees", "Net Amount"],
             [["1", "05/14/2026", "1.00", "10.00"],
              ["2", "04/30/2026", "9.00", "90.00"],
              ["3", "06/01/2026", "5.00", "50.00"]])
    v = etsy.payments_topla([p], ay=5, yil=2026)
    assert set(v) == {"1"}
    # filtresiz hepsi gelir
    assert set(etsy.payments_topla([p])) == {"1", "2", "3"}


def test_orders_donem_filtresi_2haneli_yil(tmp_path):
    # SoldOrders 'Sale Date' 2 haneli yıl (MM/DD/YY) biçimini de çözer
    o = _yaz(tmp_path, "ord.csv",
             ["Order ID", "Sale Date", "Card Processing Fees", "Order Net"],
             [["10", "05/02/26", "2.00", "20.00"],
              ["11", "06/18/26", "3.00", "30.00"]])
    v = {}
    etsy.orders_birlestir(v, [o], ay=5, yil=2026)
    assert set(v) == {"10"}


def test_donem_filtresi_tarih_kolonu_yoksa_uygulanmaz(tmp_path):
    # Tarih kolonu hiç yoksa filtre atlanır (tüm satırlar gelir)
    p = _yaz(tmp_path, "pay.csv", ["Order ID", "Fees"], [["1", "1.00"]])
    assert set(etsy.payments_topla([p], ay=5, yil=2026)) == {"1"}
