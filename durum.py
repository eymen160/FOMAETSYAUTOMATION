# Uygulama çalışma-zamanı durumu ve durum üzerinde çalışan yardımcılar.
#
# Tek kullanıcılı lokal uygulama: durum bellekte (DURUM) tutulur. Bu modül
# web katmanından (Flask) bağımsızdır — yalnız durumu sorgular/değiştirir ve
# rapor servisine DURUM'u bağlar; böylece blueprint'ler app.py'ye dönük
# döngüsel bağımlılık olmadan import edebilir. Yükleme hedefi tek kaynak
# olarak config.YUKLEME_KLASORU'ndan okunur.
import glob
import os

import config
from lazer import eslestirme, master, rapor_servis, shipstation_csv

# Tek kullanıcılı lokal uygulama: durum bellekte tutulur
DURUM = {
    "master_yolu": None,
    "orders_yolu": None,
    "ozet_yolu": None,     # sipariş özeti raporu (maliyet dahil, sipariş bazlı)
    "kalem_yolu": None,    # kalem-bazlı export (Store+Item Name+Qty+SKU → ürün)
    "shipments_yolu": None,
    "maliyet_csv_yolu": None,
    "sku_katalog_yolu": None,   # ShipStation ürün/SKU kataloğu (opsiyonel)
    # Etsy export'ları mağaza başına ayrı dosya gelir → her tür bir liste
    "etsy": {"etsy_orders": [], "etsy_items": [],
             "etsy_payments": [], "etsy_listings": []},
    "reklam_yollari": [],  # Etsy reklam / hesap özeti CSV'leri (mağaza başına)
    "analiz": None,        # son analiz sonucu (ay, yıl, kayıtlar, ss verisi…)
    "kargo": None,         # API/CSV'den mağaza bazında kargo maliyeti
    "son_rapor": None,
    "eslestirme_yolu": eslestirme.ESLESTIRME_DOSYASI,
    "demo": False,
    "mod": "form",          # "form" (master beyanı) | "formsuz" (ham veriden)
}

# Tanınan tür → tekil ShipStation DURUM slotu (üzerine yazılır)
_SS_SLOT = {
    "ozet": "ozet_yolu", "kalem": "kalem_yolu", "orders": "orders_yolu",
    "shipments": "shipments_yolu", "sku_katalog": "sku_katalog_yolu",
}
# Çok mağazalı Etsy türleri (her biri liste olarak biriktirilir)
_ETSY_TURLERI = ("etsy_orders", "etsy_items", "etsy_payments", "etsy_listings")


# ---- Durum sorgulama / algılama / sıfırlama -------------------------------
def master_bul():
    if DURUM["master_yolu"] and os.path.exists(DURUM["master_yolu"]):
        return DURUM["master_yolu"]
    adaylar = [y for y in glob.glob("*.xlsx")
               if not os.path.basename(y).startswith(("Lazer_Grubu_Rapor", "~$"))]
    return adaylar[0] if adaylar else None


def orders_bul():
    if DURUM["orders_yolu"] and os.path.exists(DURUM["orders_yolu"]):
        return DURUM["orders_yolu"]
    return None


def shipments_bul():
    if DURUM["shipments_yolu"] and os.path.exists(DURUM["shipments_yolu"]):
        return DURUM["shipments_yolu"]
    return None


def csv_otomatik_tani():
    """Klasördeki CSV'leri içeriğine göre orders/shipments olarak tanı."""
    if DURUM["demo"]:
        return  # demo modunda yalnızca paketlenmiş demo verisi kullanılır
    for yol in glob.glob("*.csv"):
        try:
            satirlar = shipstation_csv._csv_oku(yol)
        except shipstation_csv.CsvHata:
            continue
        basliklar = set(satirlar[0].keys())
        kalem = ("Item Name" in basliklar and "Store" in basliklar
                 and ("Item Quantity" in basliklar or "Quantity" in basliklar))
        if "Amount - Order Total" in basliklar and DURUM["ozet_yolu"] is None:
            DURUM["ozet_yolu"] = yol
        elif kalem and DURUM["kalem_yolu"] is None:
            DURUM["kalem_yolu"] = yol      # kalem detayı (ürün sınıflandırma)
        elif "Order Total" in basliklar and DURUM["orders_yolu"] is None:
            DURUM["orders_yolu"] = yol
        elif "Shipment #" in basliklar and "Order Total" not in basliklar \
                and DURUM["shipments_yolu"] is None:
            DURUM["shipments_yolu"] = yol


def demo_cik():
    """Elle dosya yükleme demo modundan çıkar (demo verisini bırakır)."""
    if not DURUM["demo"]:
        return
    DURUM["demo"] = False
    DURUM["eslestirme_yolu"] = eslestirme.ESLESTIRME_DOSYASI
    DURUM["ozet_yolu"] = None
    DURUM["master_yolu"] = None
    DURUM["kalem_yolu"] = None


# ---- Yükleme yönlendirme (tanınan dosyayı doğru slota yerleştir) ----------
def coklu_yonlendir(tur, gecici, ad):
    """Tanınan `tur`'ü uygun DURUM slotuna yerleştir; kalıcı yolu döndür.

    Tekil ShipStation türleri sabit ada (üzerine yazma) kaydedilir; çok
    mağazalı Etsy/reklam türleri sıralı benzersiz ada eklenir. Tanınmayan
    dosya reddedilir (geçici silinir, None döner)."""
    uzanti = os.path.splitext(ad)[1].lower() or ".csv"
    if tur in _SS_SLOT:
        kalici = os.path.join(config.YUKLEME_KLASORU, f"{tur}{uzanti}")
        os.replace(gecici, kalici)
        DURUM[_SS_SLOT[tur]] = kalici
        return kalici
    if tur in _ETSY_TURLERI:
        liste = DURUM["etsy"][tur]
        kalici = os.path.join(config.YUKLEME_KLASORU,
                              f"{tur}_{len(liste) + 1}_{ad}")
        os.replace(gecici, kalici)
        liste.append(kalici)
        return kalici
    if tur == "reklam":
        n = len(DURUM["reklam_yollari"]) + 1
        kalici = os.path.join(config.YUKLEME_KLASORU, f"reklam_{n}_{ad}")
        os.replace(gecici, kalici)
        DURUM["reklam_yollari"].append(kalici)
        return kalici
    if os.path.exists(gecici):
        os.remove(gecici)
    return None


def xlsx_yonlendir(gecici, ad):
    """.xlsx → master beyanı mı? Doğrulayıp slota koy, türü döndür."""
    try:
        master.master_oku(gecici)
    except master.MasterHata:
        if os.path.exists(gecici):
            os.remove(gecici)
        return "bilinmiyor", None
    kalici = os.path.join(config.YUKLEME_KLASORU, "master.xlsx")
    os.replace(gecici, kalici)
    DURUM["master_yolu"] = kalici
    return "master", kalici


def yukleme_ozeti():
    """Slot bazında yükleme durumu (UI rozet/teyit için)."""
    return {
        "master": bool(DURUM["master_yolu"]),
        "ozet": bool(DURUM["ozet_yolu"]),
        "kalem": bool(DURUM["kalem_yolu"]),
        "orders": bool(DURUM["orders_yolu"]),
        "shipments": bool(DURUM["shipments_yolu"]),
        "sku_katalog": bool(DURUM["sku_katalog_yolu"]),
        "etsy_orders": len(DURUM["etsy"]["etsy_orders"]),
        "etsy_items": len(DURUM["etsy"]["etsy_items"]),
        "etsy_payments": len(DURUM["etsy"]["etsy_payments"]),
        "etsy_listings": len(DURUM["etsy"]["etsy_listings"]),
        "reklam": len(DURUM["reklam_yollari"]),
    }


# ---- Rapor servisini DURUM'a bağlayan adaptörler --------------------------
def kaynak_varsayilan(a):
    return rapor_servis.kaynak_varsayilan(a)


def etsy_enrichment(ay=None, yil=None):
    """DURUM slotlarını toplayıp Etsy finansal zenginleştirme servisine verir
    (formsuz mod). Dönüş: (etsy_finansal, reklam_magaza, meta)."""
    ss_yollari = [DURUM.get(k) for k in
                  ("ozet_yolu", "kalem_yolu", "orders_yolu", "shipments_yolu")]
    return rapor_servis.etsy_enrichment(
        DURUM.get("etsy") or {}, DURUM.get("reklam_yollari") or [],
        ss_yollari, ay, yil)


def ss_master_bazinda():
    """ShipStation verisini master mağaza adına çevirir (servise delege)."""
    return rapor_servis.ss_master_bazinda(
        DURUM["analiz"], eslestirme.yukle(DURUM["eslestirme_yolu"]),
        DURUM["kargo"])


def urun_master_bazinda():
    """Kalem-bazlı otomatik ürün adetlerini master mağaza adına çevirir
    (servise delege)."""
    return rapor_servis.urun_master_bazinda(
        DURUM["analiz"], eslestirme.yukle(DURUM["eslestirme_yolu"]))


def rapor_satirlari(kaynaklar, ciro_kaynagi, urun_kaynagi="form"):
    """Rapor + ekran tablosu için ortak satır üretimi (servise delege).
    Dönüş: (satirlar, ss_veri, amazon_liste, urun_basliklari,
    kaynak_kullanim)."""
    return rapor_servis.rapor_satirlari(
        DURUM["analiz"], eslestirme.yukle(DURUM["eslestirme_yolu"]),
        DURUM["kargo"], kaynaklar, ciro_kaynagi, urun_kaynagi)
