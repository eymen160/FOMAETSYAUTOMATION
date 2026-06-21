# Ürün/SKU sınıflandırma motoru testleri.
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from lazer import urun_eslestirme as ue


@pytest.mark.parametrize("ad,beklenen", [
    ("Custom Glass Coffee Mug, Personalized", "Glass Cofe-Mug"),
    ("Personalized Ceramic Coffee Mug", "Coffee Mug"),
    ("Personalized 40oz Tumbler with Handle & Straw", "40 oz Tmblr"),
    ("Custom Laser Engraved Wine Tumbler", "Wine Tmblr"),
    ("Personalized Leather Tumbler", "20 oz  Lether Tmblr"),
    ("Custom Engraved Wine Glass with Name", "WineGlass"),
    ("Stemless Wine Glass Custom", "WineGlass-SL"),
    ("Personalized Beer Mug with Handle", "BeerMug"),
    ("Personalized Monogram Beer Glass, Pint Glass", "BeerMug"),
    ("Custom Lighter, Personalized Monogram Lighters", "Lighter"),
    ("Personalized Leather Toiletry Bag", "DoppKit T-Bag"),
    ("Personalized Wood Photo Frame", "Photo Frame"),
    ("Custom Damascus Steel Knife", "Damasc.Knife"),
    ("Personalized Checkbook Cover", "CheckBook"),
    ("Custom Can Cooler Holder", "CanCooler"),
    ("Personalized Cutting Board", "Cutting Board"),
    ("Custom Name Water Bottle", "Water Bottle"),
    ("Personalized Passport Holder", "Passp.Hold"),
    ("Custom Leather Wallet", "Wallet"),
])
def test_siniflandir_keyword(ad, beklenen):
    assert ue.siniflandir(ad, "", {}) == beklenen


def test_siniflandir_bilinmeyen():
    # Taksonomi dışı ürün → None (Diğer Ürün'e gider)
    assert ue.siniflandir("Unclassifiable Test Item ZZZ", "ZZZ1", {}) is None


def test_sku_sozlugu_oncelik():
    # Öğrenilmiş SKU sözlüğü keyword'den önce gelir
    m = {"XYZ9": "Wallet"}
    assert ue.siniflandir("Custom Beach Towel", "XYZ9", m) == "Wallet"


def test_kaydet_yukle_ogrenme(tmp_path):
    yol = str(tmp_path / "urun.json")
    ue.kaydet({"DSKP01": "Diğer Ürün"}, yol)
    ue.kaydet({"BBQ1": "Cutting Board"}, yol)
    v = ue.yukle(yol)
    assert v == {"DSKP01": "Diğer Ürün", "BBQ1": "Cutting Board"}


@pytest.fixture
def kalem_csv(tmp_path):
    alan = ["Order #", "Ship Date", "Store", "Item Name", "Item Quantity",
            "Item SKU"]
    satirlar = [
        ["1", "05/03/2026", "Shop A", "Custom Glass Coffee Mug", "2", "GCM1"],
        ["2", "05/04/2026", "Shop A", "Personalized 40oz Tumbler", "1", "T40"],
        ["3", "05/05/2026", "Shop A", "Unclassifiable Test Item ZZZ", "3", "ZZZ"],
        ["4", "04/30/2026", "Shop A", "Custom Lighter", "5", "LTR"],   # ay dışı
        ["5", "05/06/2026", "Shop B", "(3 Items)", "3", "(3 Items)"],  # gruplu→atla
        ["6", "05/07/2026", "Shop B", "Custom Wine Glass", "4", "WG1"],
    ]
    yol = tmp_path / "kalem.csv"
    with open(yol, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(alan)
        w.writerows(satirlar)
    return str(yol)


def test_kalem_format_mu(kalem_csv):
    assert ue.kalem_format_mu(kalem_csv) is True


def test_kalem_isle_siniflama(kalem_csv):
    s = ue.kalem_isle(kalem_csv, 5, 2026, {})
    a = s["magaza_urun"]["Shop A"]
    assert a["Glass Cofe-Mug"] == 2
    assert a["40 oz Tmblr"] == 1
    assert a[ue.DIGER] == 3          # sınıflanamayan test ürünü
    assert "Lighter" not in a        # ay dışı (04/30) hariç


def test_kalem_isle_gruplu_atlanir(kalem_csv):
    s = ue.kalem_isle(kalem_csv, 5, 2026, {})
    b = s["magaza_urun"]["Shop B"]
    assert b.get("WineGlass") == 4
    assert sum(b.values()) == 4      # "(3 Items)" satırı sayılmadı


def test_kalem_isle_kapsama(kalem_csv):
    s = ue.kalem_isle(kalem_csv, 5, 2026, {})
    # Mayıs içi: 2+1 (A bilinen) + 4 (B bilinen) = 7 sınıflanan; 3 diğer
    assert s["kapsama"]["siniflanan"] == 7
    assert s["kapsama"]["toplam"] == 10


def test_kalem_isle_bilinmeyen_listesi(kalem_csv):
    s = ue.kalem_isle(kalem_csv, 5, 2026, {})
    assert any("ZZZ" in k for k in s["bilinmeyen"])


def test_ogrenilmis_sku_kalemde(kalem_csv):
    # Bilinmeyen SKU'yu Diğer dışında bir kategoriye öğret → öyle sınıflanır
    s = ue.kalem_isle(kalem_csv, 5, 2026, {"ZZZ": "Coaster"})
    assert s["magaza_urun"]["Shop A"].get("Coaster") == 3


@pytest.fixture
def coklu_kalem_csv(tmp_path):
    alan = ["Order #", "Ship Date", "Store", "Item Name", "Item Quantity",
            "Item SKU"]
    satirlar = [
        # Çok-ürünlü sipariş (iki farklı kalem)
        ["100", "05/03/2026", "Shop A", "Custom Coffee Mug", "2", "M1"],
        ["100", "05/03/2026", "Shop A", "Custom Wine Glass", "3", "W1"],
        # Tekil sipariş
        ["101", "05/04/2026", "Shop A", "Custom Lighter", "1", "L1"],
        # Tek satır ama adet>1 → yine çok-ürünlü sayılır
        ["102", "05/05/2026", "Shop B", "Custom Tumbler", "5", "T1"],
    ]
    yol = tmp_path / "ck.csv"
    with open(yol, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(alan)
        w.writerows(satirlar)
    return str(yol)


def test_siparis_icerik_coklu(coklu_kalem_csv):
    s = ue.siparis_icerikleri(coklu_kalem_csv, 5, 2026)
    assert s["coklu"] == 2          # sipariş 100 (5 adet) + 102 (5 adet)
    assert s["tekil"] == 1          # sipariş 101
    g = s["icerik"]["100"]
    assert g["toplam_adet"] == 5
    assert len(g["items"]) == 2     # mug + wine glass
    adlar = {it["ad"] for it in g["items"]}
    assert "Custom Coffee Mug" in adlar and "Custom Wine Glass" in adlar


def test_siparis_icerik_tekil_haric(coklu_kalem_csv):
    s = ue.siparis_icerikleri(coklu_kalem_csv, 5, 2026)
    assert "101" not in s["icerik"]   # tekil sipariş listede değil
