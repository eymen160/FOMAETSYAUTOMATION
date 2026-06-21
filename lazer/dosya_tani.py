# İçeriğe dayalı dosya türü tanıma: bir CSV'nin BAŞLIK satırına bakarak hangi
# kaynak olduğunu belirler. Böylece kullanıcı her dosyanın türünü elle seçmek
# zorunda kalmaz — "dosyaları bırak, uygulama eşleştirsin".
#
# Tanınan türler (ETIKET anahtarları):
#   ozet         ShipStation Sipariş Özeti/Insights (Amount - Order Total ...)
#   kalem        ShipStation Kalem Detayı (Store + Item Name + Quantity + SKU)
#   orders       ShipStation Orders (Order # + Order Total)
#   shipments    ShipStation Shipments (Shipment # + Store, kalem yok)
#   sku_katalog  ShipStation Ürün/SKU kataloğu (SKU + Name + Category ...)
#   etsy_orders  Etsy Satılan Siparişler (Order ID + Number of Items)
#   etsy_items   Etsy Sipariş Kalemleri (Order ID + Item Name + Transaction ID)
#   etsy_payments  Etsy Ödeme Hesabı (Payment ID + Net Amount + Order ID)
#   etsy_listings  Etsy İlanlar (TITLE + TAGS + MATERIALS)
#   reklam       Etsy Reklam / hesap özeti (reklam gideri içeren beyan)
#   bilinmiyor   Tanınamadı
import csv

from .shipstation_csv import CsvHata
from .yardimci import normalize_baslik

ETIKET = {
    "ozet": "ShipStation Sipariş Özeti (gelir + kargo maliyeti)",
    "kalem": "ShipStation Kalem Detayı (ürün / SKU)",
    "orders": "ShipStation Orders (sipariş)",
    "shipments": "ShipStation Shipments (gönderi)",
    "sku_katalog": "ShipStation Ürün/SKU Kataloğu",
    "etsy_orders": "Etsy Satılan Siparişler",
    "etsy_items": "Etsy Sipariş Kalemleri",
    "etsy_payments": "Etsy Ödeme Hesabı (komisyon / net)",
    "etsy_listings": "Etsy İlanlar",
    "reklam": "Etsy Reklam / Hesap Özeti (reklam gideri)",
    "bilinmiyor": "Tanınamadı",
}

# Hangi türlerin rapor hattında bir yere yönlendirildiği (UI ipucu)
RAPOR_KAYNAGI = {"ozet", "kalem", "orders", "shipments",
                 "etsy_orders", "etsy_items", "etsy_payments", "reklam"}


def basliklar_oku(yol):
    """Yalnızca başlık satırını oku (büyük dosyalarda hızlı). BOM toleranslı."""
    for kodlama in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(yol, newline="", encoding=kodlama) as f:
                ilk = next(csv.reader(f), [])
            if ilk:
                return [h.strip() for h in ilk]
        except (UnicodeDecodeError, StopIteration):
            continue
    raise CsvHata("Dosya başlığı okunamadı (kodlama sorunu veya boş dosya).")


def tani(yol):
    """CSV dosyasının türünü döndür (ETIKET anahtarlarından biri)."""
    try:
        basliklar = basliklar_oku(yol)
    except CsvHata:
        return "bilinmiyor"
    nset = {normalize_baslik(b) for b in basliklar}

    def var(*adaylar):
        return any(normalize_baslik(a) in nset for a in adaylar)

    item_name = var("Item Name")
    store = var("Store")
    order_id = var("Order ID")
    order_no = var("Order #", "Order Number")
    qty = var("Item Quantity", "Quantity")
    sku = var("Item SKU", "SKU")

    # --- Etsy (Order ID kullanır; ShipStation 'Order #' kullanır) ---
    if var("TITLE") and var("TAGS") and var("MATERIALS"):
        return "etsy_listings"
    if var("Payment ID") and var("Net Amount", "Gross Amount"):
        return "etsy_payments"
    if order_id and var("Number of Items"):
        return "etsy_orders"
    if order_id and item_name and var("Transaction ID", "Listing ID"):
        return "etsy_items"

    # --- Reklam / hesap özeti (reklam gideri içeren beyan) ---
    if var("Advertising", "Etsy Ads", "Ad Spend", "Marketing", "Reklam",
           "Advertising Cost", "Etsy Ads Cost"):
        return "reklam"

    # --- ShipStation ---
    if var("Amount - Order Total"):
        return "ozet"
    if var("Name") and var("Category") and sku and \
            var("CustomsValue", "WarehouseLocation", "FillSku"):
        return "sku_katalog"
    if item_name and store and qty:
        return "kalem"
    if var("Order Total") and (order_no or order_id):
        return "orders"
    if var("Shipment #") and store and not item_name:
        return "shipments"
    return "bilinmiyor"
