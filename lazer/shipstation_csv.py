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

    # 1. geçiş: iptal/negatif siparişleri sipariş bazında tespit et.
    # Order # boş satırlar sipariş bazında değil SATIR bazında işaretlenir;
    # aksi halde tek bir negatif boş satır tüm boş satırları düşürür.
    iptal_orderlar = set()
    iptal_bos_satirlar = set()
    iptal_iade = []
    for i, (r, t) in enumerate(ay_satirlari):
        ono = (alan(r, "order_no") or "").strip()
        if ono and ono in iptal_orderlar:
            continue
        ot = sayi(alan(r, "order_total"), 0.0)
        ap = sayi(alan(r, "amount_paid"), 0.0)
        durum = (alan(r, "status") or "").strip().lower()
        if ot < 0 or ap < 0 or durum in ("cancelled", "canceled", "iptal"):
            if ono:
                iptal_orderlar.add(ono)
            else:
                iptal_bos_satirlar.add(i)
            iptal_iade.append({
                "order_no": ono, "store": (alan(r, "store") or "").strip(),
                "tarih": t.strftime("%d.%m.%Y"),
                "order_total": ot, "durum": durum or "negatif tutar"})

    # 2. geçiş: toplama (iptaller tamamen hariç; sipariş alanları dedupe'lu).
    # Order # boş satırlar dedupe'a SOKULMAZ: iki boş satır aynı sipariş
    # değildir; her biri ayrı sipariş gibi sayılır ve bos_order_no ile
    # validasyona raporlanır (ciro düşmesin diye).
    magazalar = {}
    siparis_gorulen = {}   # order_no -> store (dedupe + çoklu store tespiti)
    siparisler = {}        # order_no -> {store, ciro, tarih} (ay sipariş kümesi)
    coklu_store = set()
    bos_order_no = {}      # store -> {satir, ciro}
    for i, (r, t) in enumerate(ay_satirlari):
        store = (alan(r, "store") or "").strip()
        ono = (alan(r, "order_no") or "").strip()
        if (ono and ono in iptal_orderlar) or i in iptal_bos_satirlar:
            continue
        m = magazalar.setdefault(store, {
            "ciro_order_total": 0.0, "ciro_amount_paid": 0.0, "vergi": 0.0,
            "kargo_musteri": 0.0, "adet": 0.0, "siparis_sayisi": 0})
        m["adet"] += sayi(alan(r, "quantity"), 0.0)

        if not ono:
            b = bos_order_no.setdefault(store, {"satir": 0, "ciro": 0.0})
            b["satir"] += 1
            b["ciro"] += sayi(alan(r, "order_total"), 0.0)
        else:
            onceki = siparis_gorulen.get(ono)
            if onceki is not None:
                if onceki != store:
                    coklu_store.add(ono)
                continue  # sipariş bazlı alanlar yalnızca ilk satırda sayılır
            siparis_gorulen[ono] = store
            siparisler[ono] = {"store": store,
                               "ciro": sayi(alan(r, "order_total"), 0.0),
                               "tarih": t.strftime("%d.%m.%Y")}
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
        "siparisler": siparisler,
        "bos_order_no": bos_order_no,
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


# --- Sipariş Özeti raporu (ShipStation Insights/Reports export'u) -----------
# Sipariş bazlıdır ve kargo MALİYETİNİ de içerir. Tekrarlı Order # satırları
# bölünmüş gönderilerdir ve tutarları farklıdır → toplanır (dedupe edilmez).
OZET_KOLONLARI = {
    "order_no": ["Order - Number"],
    "order_date": ["Date - Order Date"],
    "store": ["Market - Store Name"],
    "marketplace": ["Market - Markeplace Name", "Market - Marketplace Name"],
    "kargo_maliyet": ["Amount - Shipping Cost"],
    "kargo_musteri": ["Amount - Order Shipping"],
    "paid": ["Amount - Paid by Customer"],
    "subtotal": ["Amount - Order Subtotal"],
    "tax": ["Amount - Order Tax"],
    "total": ["Amount - Order Total"],
    "item_sayisi": ["Count - Number of Items"],
}
OZET_ZORUNLU = ["order_no", "order_date", "store", "subtotal", "total"]


def ozet_format_mu(yol):
    """Dosya sipariş özeti raporu mu? (başlığa bakarak hızlı kontrol)"""
    try:
        satirlar = _csv_oku(yol)
    except CsvHata:
        return False
    basliklar = list(satirlar[0].keys())
    return kolon_bul(basliklar, ["Amount - Order Total"], prefix=False) is not None


def ozet_isle(yol, ay, yil):
    """Sipariş özeti raporunu mağaza bazında işler.

    Dönüş: magazalar {store: {ciro_subtotal_shipping, ciro_order_total,
           ciro_amount_paid, vergi, kargo_musteri, kargo_maliyet,
           siparis_sayisi}}, iptal_iade, kapsama, ay_satir_sayisi
    """
    satirlar = _csv_oku(yol)
    basliklar = list(satirlar[0].keys())
    kmap = {k: kolon_bul(basliklar, v, prefix=False) for k, v in OZET_KOLONLARI.items()}
    eksik = [OZET_KOLONLARI[k][0] for k in OZET_ZORUNLU if kmap[k] is None]
    if eksik:
        raise CsvHata("Sipariş özeti raporunda şu kolonlar bulunamadı: "
                      + ", ".join(eksik))

    def alan(r, k, vars=0.0):
        kol = kmap.get(k)
        return sayi(r.get(kol), vars) if kol else vars

    tum_tarihler, ay_satirlari = [], []
    for r in satirlar:
        t = _tarih(r.get(kmap["order_date"]))
        if t:
            tum_tarihler.append(t)
        if t and t.year == yil and t.month == ay:
            ay_satirlari.append((r, t))

    magazalar = {}
    iptal_iade = []
    siparisler = {}  # order_no -> {store, ciro} (ay sipariş kümesi)
    for r, t in ay_satirlari:
        store = (r.get(kmap["store"]) or "").strip()
        total = alan(r, "total")
        paid = alan(r, "paid")
        if total < 0 or paid < 0:
            iptal_iade.append({
                "order_no": (r.get(kmap["order_no"]) or "").strip(),
                "store": store, "tarih": t.strftime("%d.%m.%Y"),
                "order_total": total, "durum": "negatif tutar"})
            continue
        m = magazalar.setdefault(store, {
            "ciro_subtotal_shipping": 0.0, "ciro_order_total": 0.0,
            "ciro_amount_paid": 0.0, "vergi": 0.0, "kargo_musteri": 0.0,
            "kargo_maliyet": 0.0, "adet": None, "siparis_sayisi": 0})
        sub = alan(r, "subtotal")
        shp = alan(r, "kargo_musteri")
        m["ciro_subtotal_shipping"] += sub + shp
        m["ciro_order_total"] += total
        m["ciro_amount_paid"] += paid
        m["vergi"] += alan(r, "tax")
        m["kargo_musteri"] += shp
        m["kargo_maliyet"] += alan(r, "kargo_maliyet")
        m["siparis_sayisi"] += 1
        ono = (r.get(kmap["order_no"]) or "").strip()
        if ono:  # tekrarlı Order # = bölünmüş gönderi → ciro toplanır
            sp = siparisler.setdefault(ono, {"store": store, "ciro": 0.0,
                                             "tarih": t.strftime("%d.%m.%Y")})
            sp["ciro"] += total

    kapsama = {"ilk": None, "son": None, "uyari": None}
    if tum_tarihler:
        ilk, son = min(tum_tarihler), max(tum_tarihler)
        kapsama["ilk"] = ilk.strftime("%d.%m.%Y")
        kapsama["son"] = son.strftime("%d.%m.%Y")
        son_gun = calendar.monthrange(yil, ay)[1]
        if ilk > datetime(yil, ay, 1) or son < datetime(yil, ay, son_gun):
            kapsama["uyari"] = (
                f"Sipariş özeti raporu {ilk.strftime('%d.%m.%Y')} – "
                f"{son.strftime('%d.%m.%Y')} aralığını kapsıyor; seçilen ay "
                f"({ay:02d}/{yil}) tam kapsanmıyor olabilir.")
    return {"magazalar": magazalar, "siparisler": siparisler,
            "iptal_iade": iptal_iade,
            "kapsama": kapsama, "ay_satir_sayisi": len(ay_satirlari),
            "toplam_satir": len(satirlar)}


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
