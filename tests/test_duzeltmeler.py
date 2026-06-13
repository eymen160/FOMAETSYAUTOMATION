# DENETIM_RAPORU.md'deki 6 FAILED bulgunun regresyon testleri.
# Çalıştırma: python -m unittest tests.test_duzeltmeler -v
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lazer import shipstation_api, shipstation_csv

ORDERS_BASLIK = ["Order #", "Order Date", "Item SKU", "Item Name", "Quantity",
                 "Tax Paid", "Order Total", "Shipping Paid", "Amount Paid",
                 "Store", "Order Status"]


def orders_csv_yaz(yol, satirlar):
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(ORDERS_BASLIK)
        w.writerows(satirlar)


def label(lid, sid, order_no, cost, created, voided=False, store_id="ST1"):
    return {"label_id": lid, "shipment_id": sid, "order_number": order_no,
            "shipment_cost": {"amount": cost}, "insurance_cost": {"amount": 0},
            "created_at": created, "ship_date": created[:10], "voided": voided,
            "status": "voided" if voided else "completed",
            "tracking_number": "T-" + lid, "store_id": store_id}


class StubApi:
    def __init__(self, labels):
        self.labels = labels

    def ay_labellari(self, yil, ay, yenile=False):
        return self.labels

    def ay_shipmentlari(self, yil, ay, yenile=False):
        return []


class TempCwd(unittest.TestCase):
    """store_id_mapping.json gibi yan etkiler geçici klasörde kalsın."""

    def setUp(self):
        self.eski = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.eski)
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestFix1AySiniri(TempCwd):
    """FIX 1: Maliyet sipariş ayına yazılır, label ayına değil."""

    def _hesapla(self, labels, ay_siparisleri):
        order_store = {o: v["store"] for o, v in ay_siparisleri.items()}
        return shipstation_api.kargo_maliyeti_hesapla(
            StubApi(labels), 2026, 5, order_store,
            ay_siparisleri=ay_siparisleri)

    def test_ileri_sinir_mayis_siparisi_haziran_labeli_mayisa_yazilir(self):
        # Denetim kanıtı: 30 Mayıs siparişi (VW-1003), label 2 Haziran'da.
        labels = [label("L1", "S9", "VW-1003", 5.00, "2026-06-02T10:00:00Z")]
        sonuc = self._hesapla(labels, {"VW-1003": {"store": "Velvet", "ciro": 80.0}})
        self.assertAlmostEqual(sonuc["magaza_kargo"].get("Velvet", 0), 5.00)
        self.assertEqual(sonuc["istatistik"]["eslesen"], 1)

    def test_ters_sinir_nisan_siparisi_mayis_labeli_mayisa_yazilmaz(self):
        # Denetim kanıtı: 30 Nisan siparişi (PM-0420), label 2 Mayıs'ta.
        labels = [label("L1", "S7", "PM-0420", 6.00, "2026-05-02T11:00:00Z"),
                  label("L2", "S6", "PO-4002", 4.75, "2026-05-21T10:00:00Z")]
        ay_sip = {"PO-4002": {"store": "Pine & Oak", "ciro": 60.0}}  # yalnız Mayıs
        sonuc = self._hesapla(labels, ay_sip)
        self.assertAlmostEqual(sonuc["magaza_kargo"].get("Pine & Oak", 0), 4.75)
        self.assertEqual(sonuc["ay_disi_label"], 1)  # PM-0420 bu aya sayılmadı

    def test_genis_pencere_tarihleri(self):
        bas, son = shipstation_api._genis_pencere(2026, 5)
        self.assertEqual(bas, "2026-04-24T00:00:00Z")   # 1 Mayıs − 7 gün
        self.assertEqual(son, "2026-07-15T23:59:59Z")   # 31 Mayıs + 45 gün

    def test_order_no_normalizasyonu(self):
        self.assertEqual(shipstation_api.order_no_norm(" 12345.0 "), "12345")
        self.assertEqual(shipstation_api.order_no_norm("VW-1001"), "VW-1001")


class TestFix2BosOrderNo(TempCwd):
    """FIX 2: Order # boş satırlar dedupe'a girmez, ciro düşmez."""

    def test_iki_bos_orderin_cirosu_da_sayilir(self):
        yol = os.path.join(self.tmp, "orders.csv")
        orders_csv_yaz(yol, [
            ["", "05/09/2026", "S1", "Item", 1, 2, 35, 1, 35, "Misc Shop", "shipped"],
            ["", "05/09/2026", "S2", "Item", 1, 3, 45, 2, 45, "Misc Shop", "shipped"],
        ])
        sonuc = shipstation_csv.orders_isle(yol, 5, 2026)
        m = sonuc["magazalar"]["Misc Shop"]
        self.assertAlmostEqual(m["ciro_order_total"], 80.0)  # eski kod 35 sayıyordu
        self.assertEqual(m["siparis_sayisi"], 2)
        b = sonuc["bos_order_no"]["Misc Shop"]
        self.assertEqual(b["satir"], 2)
        self.assertAlmostEqual(b["ciro"], 80.0)

    def test_bos_orderlar_ay_kumesine_girmez(self):
        yol = os.path.join(self.tmp, "orders.csv")
        orders_csv_yaz(yol, [
            ["", "05/09/2026", "S1", "Item", 1, 0, 35, 0, 35, "Misc Shop", "shipped"],
            ["A-1", "05/10/2026", "S2", "Item", 1, 0, 50, 0, 50, "Misc Shop", "shipped"],
        ])
        sonuc = shipstation_csv.orders_isle(yol, 5, 2026)
        self.assertEqual(set(sonuc["siparisler"]), {"A-1"})

    def test_negatif_bos_satir_diger_bos_satirlari_dusurmez(self):
        yol = os.path.join(self.tmp, "orders.csv")
        orders_csv_yaz(yol, [
            ["", "05/09/2026", "S1", "Item", 1, 0, -10, 0, -10, "Misc Shop", "shipped"],
            ["", "05/09/2026", "S2", "Item", 1, 0, 45, 0, 45, "Misc Shop", "shipped"],
        ])
        sonuc = shipstation_csv.orders_isle(yol, 5, 2026)
        self.assertAlmostEqual(
            sonuc["magazalar"]["Misc Shop"]["ciro_order_total"], 45.0)
        self.assertEqual(len(sonuc["iptal_iade"]), 1)


class TestFix4Fix5EslesmeVeKargolanmamis(TempCwd):
    """FIX 4: eşleşme oranı + sınıflandırma; FIX 5: kargolanmamış listesi."""

    def _sonuc(self):
        labels = [label("L1", "S1", "A-1", 8.0, "2026-05-02T10:00:00Z")]
        ay_sip = {
            "A-1": {"store": "Store X", "ciro": 100.0},   # eşleşir
            "A-2": {"store": "Store X", "ciro": 150.0},   # kargolanmamış
            "A-3": {"store": "Store Y", "ciro": 60.0},    # gönderi var, label yok
            "a 4": {"store": "Store Y", "ciro": 40.0},    # format anomalisi (label 'A-4')
        }
        labels.append(label("L2", "S2", "A-4", 3.0, "2026-05-03T10:00:00Z"))
        order_store = {o: v["store"] for o, v in ay_sip.items()}
        return shipstation_api.kargo_maliyeti_hesapla(
            StubApi(labels), 2026, 5, order_store, ay_siparisleri=ay_sip,
            iptal_orderlar=["C-9"], shipments_orderlari={"A-1", "A-3"})

    def test_eslesme_orani_ve_dusuk_uyarisi(self):
        ist = self._sonuc()["istatistik"]
        self.assertEqual(ist["toplam_siparis"], 4)
        self.assertEqual(ist["eslesen"], 1)
        self.assertAlmostEqual(ist["oran"], 0.25)
        self.assertTrue(ist["dusuk"])  # %97 altı kırmızı

    def test_siniflandirma(self):
        s = self._sonuc()["istatistik"]["siniflar"]
        self.assertEqual(s["kargolanmamis"], ["A-2"])
        self.assertEqual(s["aciklanamayan"], ["A-3"])
        self.assertEqual(s["format_anomalisi"], ["a 4"])
        self.assertEqual(s["iptal_iade"], ["C-9"])

    def test_kargolanmamis_magaza_listesi(self):
        km = self._sonuc()["kargolanmamis"]
        self.assertEqual(km["Store X"], {"adet": 1, "ciro": 150.0})


class TestFix6StoreIdOgrenme(TempCwd):
    """FIX 6: store_id eşlemesi ≥3 sipariş kanıtı ister, çelişkide ezmez."""

    def _hesapla(self, labels, ay_sip):
        order_store = {o: v["store"] for o, v in ay_sip.items()}
        return shipstation_api.kargo_maliyeti_hesapla(
            StubApi(labels), 2026, 5, order_store, ay_siparisleri=ay_sip)

    def test_tek_siparis_kaliciLasmaz_dusuk_guven(self):
        labels = [label("L1", "S1", "A-1", 5.0, "2026-05-02T10:00:00Z", store_id="77")]
        sonuc = self._hesapla(labels, {"A-1": {"store": "Store X", "ciro": 10}})
        self.assertFalse(os.path.exists("store_id_mapping.json"))
        self.assertEqual(sonuc["store_id_dusuk_guven"]["77"],
                         {"magaza": "Store X", "siparis_sayisi": 1})

    def test_uc_siparis_kalicilasir(self):
        labels = [label(f"L{i}", f"S{i}", f"A-{i}", 5.0,
                        "2026-05-02T10:00:00Z", store_id="77") for i in range(3)]
        ay_sip = {f"A-{i}": {"store": "Store X", "ciro": 10} for i in range(3)}
        sonuc = self._hesapla(labels, ay_sip)
        self.assertEqual(sonuc["yeni_store_id_eslesme"], {"77": "Store X"})
        with open("store_id_mapping.json", encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"77": "Store X"})

    def test_celiskide_mevcut_kayit_ezilmez(self):
        shipstation_api.store_id_sozlugu_kaydet({"77": "Eski Mağaza"})
        labels = [label(f"L{i}", f"S{i}", f"A-{i}", 5.0,
                        "2026-05-02T10:00:00Z", store_id="77") for i in range(3)]
        ay_sip = {f"A-{i}": {"store": "Yeni Mağaza", "ciro": 10} for i in range(3)}
        sonuc = self._hesapla(labels, ay_sip)
        with open("store_id_mapping.json", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["77"], "Eski Mağaza")  # ezilmedi
        self.assertTrue(any("YAZILMADI" in c for c in sonuc["store_id_celiski"]))

    def test_ayni_idye_iki_magaza_kaniti_celiski(self):
        labels = [label(f"L{i}", f"S{i}", f"A-{i}", 5.0,
                        "2026-05-02T10:00:00Z", store_id="77") for i in range(4)]
        ay_sip = {f"A-{i}": {"store": "Mağaza 1" if i < 2 else "Mağaza 2",
                             "ciro": 10} for i in range(4)}
        sonuc = self._hesapla(labels, ay_sip)
        self.assertFalse(os.path.exists("store_id_mapping.json"))
        self.assertTrue(any("birden fazla mağaza" in c
                            for c in sonuc["store_id_celiski"]))


class TestFix3OrdersCsvKatkisi(TempCwd):
    """FIX 3: Orders CSV'nin Order#→Store eşlemesi maliyet join'ine katılır."""

    def test_shipments_olmadan_orders_csv_ile_eslesir(self):
        # Shipments CSV hiç yok; eski kodda order_store boş kalır, label
        # eşleşemezdi. Yeni akışta Orders CSV'den gelen eşleme yeterli.
        labels = [label("L1", "S1", "A-1", 7.5, "2026-05-02T10:00:00Z")]
        ay_sip = {"A-1": {"store": "Store X", "ciro": 100.0}}
        order_store = {o: v["store"] for o, v in ay_sip.items()}  # app._kargo_girdileri
        sonuc = shipstation_api.kargo_maliyeti_hesapla(
            StubApi(labels), 2026, 5, order_store, ay_siparisleri=ay_sip)
        self.assertAlmostEqual(sonuc["magaza_kargo"]["Store X"], 7.5)
        self.assertEqual(sonuc["eslesmeyen"]["adet"], 0)

    def test_app_kaynak_celiskisi_uyari_uretir(self):
        # app._kargo_girdileri: Orders 'Store X' / Shipments 'Store Y' çelişkisi
        import app as APP
        APP.DURUM["analiz"] = {
            "ay": 5, "yil": 2026,
            "orders": {"siparisler": {"A-1": {"store": "Store X", "ciro": 1}},
                       "iptal_iade": []},
            "shipments": {"order_store": {"A-1": "Store Y", "B-2": "Store Z"}},
            "ozet": None,
        }
        order_store, ay_sip, iptal, ship_set, uyarilar = APP._kargo_girdileri()
        self.assertEqual(order_store["A-1"], "Store X")   # sessizce ezilmedi
        self.assertEqual(order_store["B-2"], "Store Z")   # birleşim çalışıyor
        self.assertTrue(any("çelişiyor" in u for u in uyarilar))
        self.assertEqual(ship_set, {"A-1", "B-2"})
        APP.DURUM["analiz"] = None


if __name__ == "__main__":
    unittest.main()
