# Master'ın CSV (Google Form dışa aktarımı) olarak okunabildiğini doğrular —
# gerçek formdaki uzun başlıklar ('Yıl (örnek:2024)' vb.) ve Türkçe para
# biçimi ('$23.295,00') dahil. .xlsx yolu değişmedi (diğer testler kanıtlar).
import csv
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lazer import master as M

# Gerçek formdaki başlık varyantları (prefix eşleştirmeyle çözülmeli)
HEADERS = ["Zaman damgası", "Mağaza1", "Dönem", "Yıl (örnek:2024)",
           "Ciro (örnek: 14601 Küsürat yazmayın)",
           "Vergi (örnek: 14601 Küsürat yazmayın)",
           "Reklam (örnek: 14601 Küsürat yazmayın)",
           "Müşteri Kargo Ödemesi  (örnek: 14601-küsürat yazmayın)",
           "Kargo Harcaması (Sigorta gideri de eklenecek-küsüratı yazmayın)",
           "Toplam Satış Adedi", "Upgrade Satışı",
           "Ek ödeme ve açıklaması(ör: 12$ Adobe, 15$ Eğitim)",
           "Kalan Gelir", "Diğer konular", "Mağaza"]


def write_form_csv(path, encoding="utf-8-sig"):
    rows = [
        ["01.05.2026 10:00:00", "EskiAd", "Mayıs", "2026", "$23.295,00",
         "$1.148,00", "$1.351,00", "$1.924,00", "$3.955,00", "315", "5",
         "12$ Adobe", "$4.627,00", "", "VelvetWhiskeyDesign"],
        ["01.05.2026 11:00:00", "", "Mayıs", "2026", "$343,00", "$10,00",
         "$5,00", "$8,00", "$249,00", "12", "0", "", "$100,00", "",
         "CuteArtCustomDesign"],
        ["01.04.2026 09:00:00", "", "Nisan", "2026", "$1.000,00", "$50,00",
         "$20,00", "$30,00", "$40,00", "10", "0", "", "", "", "Eski Dönem"],
    ]
    with open(path, "w", newline="", encoding=encoding) as f:
        w = csv.writer(f)
        w.writerow(HEADERS)
        w.writerows(rows)


class TestMasterCsv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.csv = os.path.join(self.tmp, "form.csv")
        write_form_csv(self.csv)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_csv_columns_resolve(self):
        df, kmap = M.master_oku(self.csv)
        for k in M.ZORUNLU:
            self.assertIsNotNone(kmap[k], f"{k} çözülemedi")
        self.assertIsNotNone(kmap["magaza_yeni"])

    def test_csv_may2026_records_and_turkish_numbers(self):
        df, kmap = M.master_oku(self.csv)
        kayitlar, bozuk, _ = M.ay_kayitlari(df, kmap, "Mayıs", 2026)
        self.assertEqual(len(kayitlar), 2)  # Nisan kaydı hariç
        velvet = next(k for k in kayitlar if k["magaza"] == "VelvetWhiskeyDesign")
        self.assertAlmostEqual(velvet["ciro"], 23295.0)      # $23.295,00
        self.assertAlmostEqual(velvet["kargo"], 3955.0)
        self.assertAlmostEqual(velvet["ek_odeme"], 12.0)     # 12$ Adobe
        self.assertEqual(int(velvet["adet"]), 315)

    def test_csv_uses_new_store_column_over_old(self):
        df, kmap = M.master_oku(self.csv)
        kayitlar, _, _ = M.ay_kayitlari(df, kmap, "Mayıs", 2026)
        # 'Mağaza' (yeni) 'Mağaza1' (eski) yerine kullanılır
        self.assertIn("VelvetWhiskeyDesign", [k["magaza"] for k in kayitlar])
        self.assertNotIn("EskiAd", [k["magaza"] for k in kayitlar])

    def test_wrong_csv_clear_error(self):
        p = os.path.join(self.tmp, "wrong.csv")
        with open(p, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([["Foo", "Bar"], ["1", "2"]])
        with self.assertRaises(M.MasterHata):
            M.master_oku(p)


if __name__ == "__main__":
    unittest.main()
