# ShipStation CSV exportları: Orders (gelir) ve Shipments (Order# ↔ Store)
import csv
import calendar
from datetime import datetime

from .yardimci import kolon_bul, sayi, tr_kucuk


class CsvHata(Exception):
    pass


ORDERS_KOLONLARI = {
    "order_no": ["Order #", "Order Number", "Order"],
    "order_date": ["Order Date"],
    "sku": ["Item SKU", "SKU"],
    "item_name": ["Item Name"],
    "quantity": ["Quantity", "Qty"],
    "tax_paid": ["Tax Paid", "Tax"],
    "order_total": ["Order Total", "Total"],
    "shipping_paid": ["Shipping Paid"],
    "amount_paid": ["Amount Paid"],
    "store": ["Store"],
    "rate": ["Rate"],
    "status": ["Order Status", "Status"],
}
ORDERS_ZORUNLU = ["order_no", "order_date", "quantity", "order_total", "store"]

SHIPMENTS_KOLONLARI = {
    "shipment_no": ["Shipment #", "Shipment Number"],
    "order_no": ["Order #", "Order Number"],
    "tracking": ["Tracking #", "Tracking Number"],
    "ship_date": ["Ship Date"],
    "store": ["Store"],
}


def _csv_oku(yol):
    for kodlama in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(yol, newline="", encoding=kodlama) as f:
                satirlar = list(csv.DictReader(f))
            if satirlar:
                return satirlar
        except UnicodeDecodeError:
            continue
    raise CsvHata("CSV dosyası okunamadı (kodlama sorunu veya dosya boş).")


def _tarih(s):
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # '05/14/2026 10:30 AM' gibi varyantlar için ilk parçayı dene
    ilk = s.split(" ")[0]
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(ilk, fmt)
        except ValueError:
            continue
    return None


def orders_dogrula(yol):
    """Orders CSV'yi açar, kolonları çözer. Shipments dosyası yanlışlıkla
    yüklendiyse anlaşılır hata verir. Dönüş: (satirlar, kolon_map)."""
    satirlar = _csv_oku(yol)
    basliklar = list(satirlar[0].keys())
    kmap = {k: kolon_bul(basliklar, v, prefix=False) for k, v in ORDERS_KOLONLARI.items()}
    if kmap["order_total"] is None and kolon_bul(basliklar, ["Shipment #"], prefix=False):
        raise CsvHata(
            "Bu dosya bir Shipments export'una benziyor (Order Total kolonu yok). "
            "Lütfen ShipStation'dan Orders export'unu yükleyin "
            "(Order Total, Tax Paid, Shipping Paid, Quantity kolonlarını içermeli).")
    eksik = [ORDERS_KOLONLARI[k][0] for k in ORDERS_ZORUNLU if kmap[k] is None]
    if eksik:
        raise CsvHata(
            "Orders CSV'de şu kritik kolonlar bulunamadı: " + ", ".join(eksik)
            + ". Dosyadaki kolonlar: " + ", ".join(basliklar))
    return satirlar, kmap


def orders_isle(yol, ay, yil):
    """Orders CSV'yi mağaza bazında işler.

    Dönüş sözlüğü:
      magazalar: {store: {ciro_order_total, ciro_amount_paid, vergi,
                          kargo_musteri, adet, siparis_sayisi}}
      iptal_iade: negatif tutarlı / iptal statülü siparişler listesi
      coklu_store: aynı Order # birden fazla Store ile görünenler
      kapsama: {ilk_tarih, son_tarih, ay_tam_mi, uyarı}
      ay_disi_satir: filtre dışı kalan satır sayısı
    """
    satirlar, kmap = orders_dogrula(yol)

    def alan(r, k):
        kol = kmap.get(k)
        return r.get(kol) if kol else None

    tum_tarihler = []
    ay_satirlari = []
    for r in satirlar:
        t = _tarih(alan(r, "order_date"))
        if t:
            tum_tarihler.append(t)
        if t and t.year == yil and t.month == ay:
            ay_satirlari.append((r, t))

    # 1. geçiş: iptal/negatif siparişleri sipariş bazında tespit et
    iptal_orderlar = set()
    iptal_iade = []
    for r, t in ay_satirlari:
        ono = (alan(r, "order_no") or "").strip()
        if ono in iptal_orderlar:
            continue
        ot = sayi(alan(r, "order_total"), 0.0)
        ap = sayi(alan(r, "amount_paid"), 0.0)
        durum = (alan(r, "status") or "").strip().lower()
        if ot < 0 or ap < 0 or durum in ("cancelled", "canceled", "iptal"):
            iptal_orderlar.add(ono)
            iptal_iade.append({
                "order_no": ono, "store": (alan(r, "store") or "").strip(),
                "tarih": t.strftime("%d.%m.%Y"),
                "order_total": ot, "durum": durum or "negatif tutar"})

    # 2. geçiş: toplama (iptaller tamamen hariç; sipariş alanları dedupe'lu)
    magazalar = {}
    siparis_gorulen = {}   # order_no -> store (dedupe + çoklu store tespiti)
    coklu_store = set()
    for r, t in ay_satirlari:
        store = (alan(r, "store") or "").strip()
        ono = (alan(r, "order_no") or "").strip()
        if ono in iptal_orderlar:
            continue
        m = magazalar.setdefault(store, {
            "ciro_order_total": 0.0, "ciro_amount_paid": 0.0, "vergi": 0.0,
            "kargo_musteri": 0.0, "adet": 0.0, "siparis_sayisi": 0})
        m["adet"] += sayi(alan(r, "quantity"), 0.0)

        onceki = siparis_gorulen.get(ono)
        if onceki is not None:
            if onceki != store:
                coklu_store.add(ono)
            continue  # sipariş bazlı alanlar yalnızca ilk satırda sayılır
        siparis_gorulen[ono] = store
        m["ciro_order_total"] += sayi(alan(r, "order_total"), 0.0)
        m["ciro_amount_paid"] += sayi(alan(r, "amount_paid"), 0.0)
        m["vergi"] += sayi(alan(r, "tax_paid"), 0.0)
        m["kargo_musteri"] += sayi(alan(r, "shipping_paid"), 0.0)
        m["siparis_sayisi"] += 1

    kapsama = {"ilk": None, "son": None, "uyari": None}
    if tum_tarihler:
        ilk, son = min(tum_tarihler), max(tum_tarihler)
        kapsama["ilk"] = ilk.strftime("%d.%m.%Y")
        kapsama["son"] = son.strftime("%d.%m.%Y")
        son_gun = calendar.monthrange(yil, ay)[1]
        ay_ilk = datetime(yil, ay, 1)
        ay_son = datetime(yil, ay, son_gun)
        if ilk > ay_ilk or son < ay_son:
            kapsama["uyari"] = (
                f"Orders export'u {ilk.strftime('%d.%m.%Y')} – {son.strftime('%d.%m.%Y')} "
                f"aralığını kapsıyor; seçilen ay ({ay:02d}/{yil}) tam kapsanmıyor olabilir. "
                "Export'u tarih filtresiyle yeniden almayı değerlendirin.")
    return {
        "magazalar": magazalar,
        "iptal_iade": iptal_iade,
        "coklu_store": sorted(coklu_store),
        "kapsama": kapsama,
        "ay_satir_sayisi": len(ay_satirlari),
        "toplam_satir": len(satirlar),
    }


def shipments_isle(yol, ay=None, yil=None):
    """Shipments CSV: Order# → Store sözlüğü + mağaza bazında gönderi sayısı."""
    satirlar = _csv_oku(yol)
    basliklar = list(satirlar[0].keys())
    kmap = {k: kolon_bul(basliklar, v, prefix=False) for k, v in SHIPMENTS_KOLONLARI.items()}
    if kmap["order_no"] is None or kmap["store"] is None:
        raise CsvHata(
            "Shipments CSV'de 'Order #' veya 'Store' kolonu bulunamadı. "
            "Dosyadaki kolonlar: " + ", ".join(basliklar))
    order_store = {}
    gonderi_sayisi = {}
    coklu = set()
    for r in satirlar:
        if ay and yil and kmap["ship_date"]:
            t = _tarih(r.get(kmap["ship_date"]))
            if t and (t.year != yil or t.month != ay):
                continue
        ono = (r.get(kmap["order_no"]) or "").strip()
        store = (r.get(kmap["store"]) or "").strip()
        if not ono or not store:
            continue
        if ono in order_store and order_store[ono] != store:
            coklu.add(ono)
        order_store[ono] = store
        gonderi_sayisi[store] = gonderi_sayisi.get(store, 0) + 1
    return {"order_store": order_store, "gonderi_sayisi": gonderi_sayisi,
            "coklu_store": sorted(coklu), "satir_sayisi": len(satirlar)}


def amazon_mu(store_adi):
    return "amazon" in tr_kucuk(store_adi)


MALIYET_KOLONLARI = {
    "order_no": ["Order #", "Order Number"],
    "tracking": ["Tracking #", "Tracking Number"],
    "maliyet": ["Cost", "Shipment Cost", "Label Cost", "Rate", "Postage Cost"],
    "sigorta": ["Insurance Cost", "Insurance"],
    "store": ["Store"],
    "ship_date": ["Ship Date"],
}


def maliyet_csv_isle(yol, order_store, ay=None, yil=None):
    """API fallback'i: maliyet kolonu içeren ShipStation raporu.
    Mağaza bazında kargo maliyeti döndürür."""
    satirlar = _csv_oku(yol)
    basliklar = list(satirlar[0].keys())
    kmap = {k: kolon_bul(basliklar, v, prefix=False) for k, v in MALIYET_KOLONLARI.items()}
    if kmap["maliyet"] is None:
        raise CsvHata(
            "Bu dosyada maliyet kolonu (Cost / Shipment Cost / Rate) bulunamadı. "
            "Dosyadaki kolonlar: " + ", ".join(basliklar))
    magaza_kargo = {}
    eslesmeyen = {"maliyet": 0.0, "adet": 0}
    for r in satirlar:
        if ay and yil and kmap["ship_date"]:
            t = _tarih(r.get(kmap["ship_date"]))
            if t and (t.year != yil or t.month != ay):
                continue
        tutar = sayi(r.get(kmap["maliyet"]), 0.0)
        if kmap["sigorta"]:
            tutar += sayi(r.get(kmap["sigorta"]), 0.0)
        store = (r.get(kmap["store"]) or "").strip() if kmap["store"] else ""
        if not store and kmap["order_no"]:
            store = order_store.get((r.get(kmap["order_no"]) or "").strip(), "")
        if store:
            magaza_kargo[store] = magaza_kargo.get(store, 0.0) + tutar
        else:
            eslesmeyen["maliyet"] += tutar
            eslesmeyen["adet"] += 1
    return {"magaza_kargo": {k: round(v, 2) for k, v in magaza_kargo.items()},
            "eslesmeyen": {"maliyet": round(eslesmeyen["maliyet"], 2),
                           "adet": eslesmeyen["adet"]}}
