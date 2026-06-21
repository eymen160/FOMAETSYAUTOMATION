# Birleşik SKU kataloğu testleri.
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from lazer import sku_katalog as sk


def _yaz(yol, basliklar, satirlar):
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(basliklar)
        w.writerows(satirlar)
    return str(yol)


@pytest.fixture
def ss_kalem(tmp_path):
    # ShipStation kalem formatı (Store + Item Name + Item Quantity + Item SKU)
    return _yaz(tmp_path / "ss.csv",
               ["Order #", "Store", "Item Name", "Item Quantity", "Item SKU"],
               [["1", "Shop A", "Custom Glass Coffee Mug", "2", "GCM1"],
                ["2", "Shop B", "Custom Glass Coffee Mug", "1", "GCM1"],
                ["3", "Shop A", "Personalized Beach Towel", "3", "TWL"],
                ["4", "Shop A", "(3 Items)", "3", "(3 Items)"],   # gruplu→atla
                ["5", "Shop A", "Mystery Zorblax Widget", "4", "ZRB"]])


@pytest.fixture
def etsy_item(tmp_path):
    # Etsy item formatı (Store yok, SKU + Item Name + Quantity)
    return _yaz(tmp_path / "etsy.csv",
               ["Order ID", "Item Name", "Quantity", "SKU"],
               [["10", "Custom Glass Coffee Mug", "5", "GCM1"],
                ["11", "Personalized Cutting Board", "2", "CB9"]])


def test_topla_temel(ss_kalem):
    k = sk.katalog_topla([ss_kalem], mapping={})
    assert set(k) == {"GCM1", "TWL", "ZRB"}          # gruplu satır atlandı
    assert k["GCM1"]["adet"] == 3                      # 2 + 1
    assert k["GCM1"]["magazalar"] == {"Shop A", "Shop B"}
    assert k["GCM1"]["auto_kategori"] == "Glass Cofe-Mug"
    assert k["TWL"]["auto_kategori"] == "Beach Towel"
    assert k["ZRB"]["auto_kategori"] is None          # taksonomi dışı


def test_topla_cok_kaynak_birlesir(ss_kalem, etsy_item):
    k = sk.katalog_topla([ss_kalem, etsy_item], mapping={})
    # GCM1 iki dosyada da var → adet birleşir (3 + 5), kaynak sayısı 2
    assert k["GCM1"]["adet"] == 8
    assert len(k["GCM1"]["kaynaklar"]) == 2
    assert k["CB9"]["auto_kategori"] == "Cutting Board"


def test_ogrenilmis_kategori_haritadan(ss_kalem):
    k = sk.katalog_topla([ss_kalem], mapping={"ZRB": "Coaster"})
    assert k["ZRB"]["kategori"] == "Coaster"
    assert sk.durum(k["ZRB"]) == "öğrenildi"
    assert sk.durum(k["GCM1"]) == "auto"               # haritada yok ama keyword var


def test_ogretilecekler_sirali(ss_kalem):
    # ZRB tek bilinmeyen (auto yok, öğrenilmiş yok)
    kuyruk = sk.ogretilecekler(sk.katalog_topla([ss_kalem], mapping={}))
    assert [k["sku"] for k in kuyruk] == ["ZRB"]


def test_ozet_matematik(ss_kalem):
    o = sk.ozet(sk.katalog_topla([ss_kalem], mapping={}))
    assert o["sku_sayisi"] == 3
    assert o["bilinmeyen_sku"] == 1                     # ZRB
    assert o["cozulen_sku"] == 2
    assert o["adet"] == 10                              # 3 + 3 + 4


def test_yaz_oku_roundtrip(ss_kalem, tmp_path):
    k = sk.katalog_topla([ss_kalem], mapping={"ZRB": "Coaster"})
    yol = str(tmp_path / "kat.json")
    sk.katalog_yaz(k, yol)
    okunan = sk.katalog_oku(yol)
    assert okunan["GCM1"]["adet"] == 3
    assert okunan["ZRB"]["durum"] == "öğrenildi"
    # set'ler JSON'da listeye dönüşmüş olmalı
    assert isinstance(okunan["GCM1"]["kaynaklar"], list)
    # hacme göre azalan sıralı yazılmalı (GCM1=3, TWL=3, ZRB=4 → ZRB ilk)
    assert list(okunan)[0] == "ZRB"


def test_sku_yoksa_ad_ile_gruplanir(tmp_path):
    yol = _yaz(tmp_path / "nosku.csv",
               ["Store", "Item Name", "Item Quantity", "Item SKU"],
               [["Shop A", "Custom Coaster", "2", ""],
                ["Shop B", "Custom Coaster", "1", ""]])
    k = sk.katalog_topla([yol], mapping={})
    anahtar = next(iter(k))
    assert anahtar.startswith("(SKU yok)")
    assert k[anahtar]["adet"] == 3
    assert k[anahtar]["auto_kategori"] == "Coaster"
