# Denetlenmiş motorun davranış kilidi (regresyon koruması).
# Finansal hesap kuralları, sipariş işleme, eşleştirme ve denetim mantığı.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv

import pytest

from lazer import denetim, eslestirme
from lazer.shipstation_csv import orders_isle, ozet_isle, amazon_mu
from lazer.yardimci import sayi, ay_no, tr_kucuk, ek_odeme_coz, normalize_baslik


# ---------------------------------------------------------------- sayı/ay
@pytest.mark.parametrize("ham,beklenen", [
    ("1.234,56", 1234.56), ("1,234.56", 1234.56), ("$123", 123.0),
    ("14601", 14601.0), ("", None), ("-", None), ("0", 0.0),
    ("12,5", 12.5), ("1.234.567,89", 1234567.89), (None, None), (42, 42.0),
])
def test_sayi_ayristirma(ham, beklenen):
    assert sayi(ham) == beklenen


@pytest.mark.parametrize("ad,no", [
    ("Ocak", 1), ("Mayıs", 5), ("mayıs", 5), ("MAYIS", 5),
    ("Aralık", 12), ("Haziran", 6), ("bilinmeyen", None),
])
def test_ay_no(ad, no):
    assert ay_no(ad) == no


def test_tr_kucuk_turkce():
    assert tr_kucuk("İSTANBUL") == "istanbul"
    assert tr_kucuk("MAYIS") == "mayıs"


@pytest.mark.parametrize("metin,tutar", [
    ("12$ Adobe, 15$ Eğitim", 27.0), ("$25 Adobe", 25.0),
    ("0", 0.0), ("", 0.0), (None, 0.0),
])
def test_ek_odeme_dolar(metin, tutar):
    deger, _ = ek_odeme_coz(metin)
    assert deger == tutar


def test_ek_odeme_tl_uyari():
    deger, uyari = ek_odeme_coz("ADOBE: ₺956,40")
    assert deger == 0.0 and uyari is not None


def test_normalize_baslik_bosluk_aksan():
    assert normalize_baslik(" Order  Total ") == normalize_baslik("order total")


# ---------------------------------------------------------- orders dedupe
@pytest.fixture
def orders_csv(tmp_path):
    satirlar = [
        # Çok ürünlü sipariş — sipariş alanları tekrarlanır (1 kez sayılmalı)
        {"Order #": "1001", "Order Date": "05/03/2026", "Item SKU": "A",
         "Item Name": "Mug", "Quantity": "2", "Tax Paid": "5.00",
         "Order Total": "100.00", "Shipping Paid": "8.00",
         "Amount Paid": "100.28", "Store": "Test Store"},
        {"Order #": "1001", "Order Date": "05/03/2026", "Item SKU": "B",
         "Item Name": "Tumbler", "Quantity": "1", "Tax Paid": "5.00",
         "Order Total": "100.00", "Shipping Paid": "8.00",
         "Amount Paid": "100.28", "Store": "Test Store"},
        # İptal / negatif
        {"Order #": "1002", "Order Date": "05/10/2026", "Item SKU": "C",
         "Item Name": "X", "Quantity": "1", "Tax Paid": "0",
         "Order Total": "-50.00", "Shipping Paid": "0",
         "Amount Paid": "-50.00", "Store": "Test Store"},
        # Aynı order farklı store (veri hatası)
        {"Order #": "1001", "Order Date": "05/03/2026", "Item SKU": "D",
         "Item Name": "Y", "Quantity": "1", "Tax Paid": "5.00",
         "Order Total": "100.00", "Shipping Paid": "8.00",
         "Amount Paid": "100.28", "Store": "Baska Store"},
        # Ay dışı
        {"Order #": "1003", "Order Date": "04/28/2026", "Item SKU": "E",
         "Item Name": "Z", "Quantity": "3", "Tax Paid": "1",
         "Order Total": "30", "Shipping Paid": "2", "Amount Paid": "30",
         "Store": "Test Store"},
        # İkinci normal sipariş
        {"Order #": "1004", "Order Date": "05/20/2026", "Item SKU": "F",
         "Item Name": "W", "Quantity": "4", "Tax Paid": "10.00",
         "Order Total": "200.00", "Shipping Paid": "12.00",
         "Amount Paid": "199.50", "Store": "Test Store"},
    ]
    yol = tmp_path / "orders.csv"
    with open(yol, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=satirlar[0].keys())
        w.writeheader()
        w.writerows(satirlar)
    return str(yol)


def test_orders_ciro_dedupe(orders_csv):
    s = orders_isle(orders_csv, 5, 2026)
    ts = s["magazalar"]["Test Store"]
    assert ts["ciro_order_total"] == 300.0      # 100 (bir kez) + 200
    assert ts["ciro_amount_paid"] == 299.78


def test_orders_vergi_kargo_dedupe(orders_csv):
    ts = orders_isle(orders_csv, 5, 2026)["magazalar"]["Test Store"]
    assert ts["vergi"] == 15.0
    assert ts["kargo_musteri"] == 20.0


def test_orders_adet_item_bazli(orders_csv):
    # 2+1 (1001) + 4 (1004); iptal 1002 ve ay-dışı 1003 hariç
    ts = orders_isle(orders_csv, 5, 2026)["magazalar"]["Test Store"]
    assert ts["adet"] == 7.0


def test_orders_iptal_ayri_raporlanir(orders_csv):
    s = orders_isle(orders_csv, 5, 2026)
    assert len(s["iptal_iade"]) == 1
    assert s["iptal_iade"][0]["order_no"] == "1002"


def test_orders_coklu_store_uyarisi(orders_csv):
    assert orders_isle(orders_csv, 5, 2026)["coklu_store"] == ["1001"]


def test_orders_tarih_kapsama_uyarisi(orders_csv):
    # 28.04–20.05 aralığı Mayıs'ı tam kapsamaz
    assert orders_isle(orders_csv, 5, 2026)["kapsama"]["uyari"]


def test_orders_siparis_sayisi(orders_csv):
    ts = orders_isle(orders_csv, 5, 2026)["magazalar"]["Test Store"]
    assert ts["siparis_sayisi"] == 2


# ------------------------------------------------ sipariş özeti raporu
@pytest.fixture
def ozet_csv(tmp_path):
    alan = ["Order - Number", "Date - Order Date", "Market - Store Name",
            "Market - Markeplace Name", "Amount - Shipping Cost",
            "Amount - Order Shipping", "Amount - Paid by Customer",
            "Amount - Order Subtotal", "Amount - Order Tax",
            "Amount - Order Total", "Count - Number of Items"]
    satirlar = [
        # Bölünmüş gönderi: aynı order iki satır — TOPLANIR (dedupe edilmez)
        ["2001", "5/3/2026 1:00 AM", "Shop A", "Etsy", "5.00", "8.00",
         "50.00", "40.00", "3.00", "51.00", "1"],
        ["2001", "5/3/2026 1:00 AM", "Shop A", "Etsy", "4.00", "6.00",
         "30.00", "25.00", "2.00", "32.00", "1"],
        # Negatif → iptal
        ["2002", "5/5/2026 2:00 AM", "Shop A", "Etsy", "0", "0",
         "-20.00", "-18.00", "0", "-20.00", "1"],
    ]
    yol = tmp_path / "ozet.csv"
    with open(yol, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(alan)
        w.writerows(satirlar)
    return str(yol)


def test_ozet_bolunmus_gonderi_toplanir(ozet_csv):
    s = ozet_isle(ozet_csv, 5, 2026)
    a = s["magazalar"]["Shop A"]
    assert a["kargo_maliyet"] == 9.0          # 5 + 4 (her ikisi de sayılır)
    assert a["ciro_subtotal_shipping"] == 79.0  # (40+8)+(25+6)
    assert a["ciro_order_total"] == 83.0


def test_ozet_negatif_iptal(ozet_csv):
    s = ozet_isle(ozet_csv, 5, 2026)
    assert len(s["iptal_iade"]) == 1
    assert "Shop A" not in {} or s["magazalar"]["Shop A"]["siparis_sayisi"] == 1


# ----------------------------------------------------------- eşleştirme
def test_amazon_tespiti():
    assert amazon_mu("Foma Amazon Store")
    assert amazon_mu(" Alpha - Amazon Store ")
    assert not amazon_mu("Etched Elegance Shop")


@pytest.mark.parametrize("ss,master", [
    ("Etched Elegance Shop", "Etched Elegance"),
    ("Devran Custom Design", "Devran"),
    ("YemlihaDesign", "Yemliha"),
    ("SeraCustomDesign", "Sera"),
    ("CuteArtCustomDesign", "Cute Art"),
    ("Custom Gift by FTM", "Custom Gift By FTM"),
])
def test_fuzzy_eslestirme_ornekleri(ss, master):
    oneri = eslestirme.oneri_uret([ss], [master], {})[0]
    assert oneri["master"] == master
    assert oneri["durum"] in ("oneri", "eslesik")


def test_eslestirme_bosluk_normalize():
    oneri = eslestirme.oneri_uret([" Velvet Whiskey Design"],
                                  ["VelvetWhiskeyDesign"], {})[0]
    assert oneri["master"] == "VelvetWhiskeyDesign"


def test_eslestirme_amazon_rapor_disi():
    oneri = eslestirme.oneri_uret(["Foma Amazon Store"], ["Devran"], {})[0]
    assert oneri["durum"] == "amazon"
    assert oneri["master"] == eslestirme.AMAZON_ETIKETI


def test_eslestirme_kayitli_oncelik():
    oneri = eslestirme.oneri_uret(["Garip Ad"], ["Devran"],
                                  {"Garip Ad": "Devran"})[0]
    assert oneri["durum"] == "eslesik" and oneri["master"] == "Devran"


def test_eslestirme_kaydet_yukle(tmp_path):
    yol = str(tmp_path / "m.json")
    eslestirme.kaydet({"A Shop": "A"}, yol)
    eslestirme.kaydet({"B Shop": "B"}, yol)   # birleştirir, ezmez
    veri = eslestirme.yukle(yol)
    assert veri == {"A Shop": "A", "B Shop": "B"}


# -------------------------------------------------------------- denetim
def _ss(ciro=None, vergi=None, km=None, adet=None, kargo=None):
    return {"ciro_order_total": ciro, "ciro_amount_paid": ciro,
            "ciro_subtotal_shipping": ciro, "vergi": vergi,
            "kargo_musteri": km, "adet": adet, "kargo_api": kargo}


def test_denetim_renk_esikleri():
    kayitlar = [{"magaza": "X", "ciro": 1000, "vergi": 100,
                 "kargo_musteri": 100, "kargo": 100, "adet": 100}]
    # %3 sapma → yeşil; %10 → sarı; %20 → kırmızı
    assert denetim.renk(0.03) == "yesil"
    assert denetim.renk(0.10) == "sari"
    assert denetim.renk(0.20) == "kirmizi"
    assert denetim.renk(None) == "yok"


def test_denetim_tablosu_sapma():
    kayitlar = [{"magaza": "X", "ciro": 1000, "vergi": 100,
                 "kargo_musteri": 100, "kargo": 100, "adet": 100}]
    ssv = {"X": _ss(ciro=2000, vergi=100, km=100, adet=100, kargo=100)}
    t = denetim.denetim_tablosu(kayitlar, ssv, "order_total")[0]
    assert t["alanlar"]["ciro"]["renk"] == "kirmizi"   # 1000 vs 2000
    assert t["alanlar"]["vergi"]["renk"] == "yesil"


def test_kalibrasyon_secimi():
    kayitlar = [{"magaza": "X", "ciro": 1000}]
    ssv = {"X": {"ciro_order_total": 1200, "ciro_amount_paid": 1300,
                 "ciro_subtotal_shipping": 1010, "vergi": None,
                 "kargo_musteri": None, "adet": None, "kargo_api": None}}
    kal = denetim.ciro_kalibrasyonu(kayitlar, ssv)
    assert kal["oneri"] == "subtotal_shipping"   # en düşük sapma
    assert kal["net"] is True
