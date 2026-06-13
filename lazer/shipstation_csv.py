# ShipStation CSV exportları: Orders (gelir) ve Shipments (Order# ↔ Store)
import csv
import calendar
import re
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


def _magaza_temizle(ad):
    """Mağaza adı normalizasyonu: baştaki/sondaki boşlukları at, içteki
    tekrarlı boşlukları teke indir ('  A  B ' → 'A B')."""
    return re.sub(r"\s+", " ", (ad or "").strip())


def _tarih(s):
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m/%d/%Y %H:%M",
                "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p"):
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


# --- Sipariş Export'u (maliyet dahil, sipariş bazlı ShipStation export) ------
# Sipariş bazlıdır ve kargo MALİYETİNİ de içerir. Tekrarlı Order # satırları
# iki türlüdür: (a) GERÇEK kopya = aynı kargo maliyeti (yeniden içe aktarım),
# (b) ÇOK GÖNDERİLİ = farklı kargo maliyeti (ayrı etiketler). Bu yüzden:
#   • Gelir (Order Total/Tax/Order Shipping/Paid/Item) → sipariş başına BİR kez
#     (drop_duplicates).
#   • Kargo (Shipping Cost) → sipariş içindeki FARKLI maliyet değerlerinin
#     toplamı, sonra mağaza bazında toplanır (gerçek kopyalar çift sayılmaz).
#   • Aynı siparişin satırları farklı tarih taşıyorsa ay ataması için EN ERKEN
#     tarih kullanılır.
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
    """Dosya sipariş export'u mu? Başlıkta 'Order - Number' + 'Amount -
    Shipping Cost' (ya da en azından 'Amount - Order Total') varsa evet."""
    try:
        satirlar = _csv_oku(yol)
    except CsvHata:
        return False
    basliklar = list(satirlar[0].keys())
    return kolon_bul(basliklar, ["Amount - Order Total"], prefix=False) is not None


def _amazon_pazar_mi(marketplace, store):
    """Pazar yeri AUTHORITATIVE: 'amazon'→True, 'etsy'→False; boş/bilinmiyorsa
    mağaza adı sezgisine (fallback) düşülür."""
    mp = tr_kucuk(marketplace)
    if "amazon" in mp:
        return True
    if "etsy" in mp:
        return False
    return amazon_mu(store)


def ozet_isle(yol, ay, yil):
    """Maliyet dahil sipariş export'unu işler (onaylı dedupe + pazar yeri ayrımı).

    Dönüş:
      magazalar: {etsy_store: {ciro_subtotal_shipping, ciro_order_total,
        ciro_amount_paid, vergi, kargo_musteri, kargo_maliyet, adet,
        siparis_sayisi}}  (yalnızca Etsy — rapor gövdesi)
      amazon: {store: {siparis, kargo}}  (Rapor Dışı)
      siparisler, iptal_iade, iptal_magaza, bos_order_no, kapsama,
      kargo_distinct_toplam, kargo_naive_toplam (dedupe kanıtı),
      pazar_sayilari, benzersiz_siparis, ay_satir_sayisi, toplam_satir
    """
    satirlar = _csv_oku(yol)
    basliklar = list(satirlar[0].keys())
    kmap = {k: kolon_bul(basliklar, v, prefix=False) for k, v in OZET_KOLONLARI.items()}
    eksik = [OZET_KOLONLARI[k][0] for k in OZET_ZORUNLU if kmap[k] is None]
    if eksik:
        raise CsvHata("Sipariş export'unda şu kolonlar bulunamadı: "
                      + ", ".join(eksik))

    def alan(r, k, vars=0.0):
        kol = kmap.get(k)
        return sayi(r.get(kol), vars) if kol else vars

    # 1) Satırları Order # bazında grupla. Boş Order # satırları dedupe'a
    #    girmez: her biri ayrı sözde-sipariş (ciro kaybını önlemek için).
    gruplar = {}      # order_no -> [satır, ...]
    bos_anahtarlar = set()
    bos_i = 0
    for r in satirlar:
        ono = (r.get(kmap["order_no"]) or "").strip()
        if ono:
            gruplar.setdefault(ono, []).append(r)
        else:
            bos_i += 1
            anah = f"__bos__{bos_i}"
            gruplar[anah] = [r]
            bos_anahtarlar.add(anah)

    magazalar, amazon = {}, {}
    iptal_iade, iptal_magaza = [], {}
    siparisler, bos_order_no = {}, {}
    tum_tarihler = []
    kargo_distinct_toplam = kargo_naive_toplam = 0.0
    pazar_sayilari = {"etsy": 0, "amazon": 0}
    benzersiz_siparis = 0
    ay_siparis_sayisi = 0

    for ono, rows in gruplar.items():
        # Ay ataması: siparişin EN ERKEN tarihli satırı
        tarihli = [(r, _tarih(r.get(kmap["order_date"]))) for r in rows]
        tarihli = [(r, t) for r, t in tarihli if t]
        if not tarihli:
            continue
        for _, t in tarihli:
            tum_tarihler.append(t)
        rep, ilk_t = min(tarihli, key=lambda x: x[1])
        benzersiz_siparis += 1
        if ilk_t.year != yil or ilk_t.month != ay:
            continue
        ay_siparis_sayisi += 1

        store = _magaza_temizle(rep.get(kmap["store"]))
        total = alan(rep, "total")
        paid = alan(rep, "paid")
        # Kargo: sipariş içindeki FARKLI maliyet değerlerinin toplamı
        maliyetler = {round(sayi(r.get(kmap["kargo_maliyet"]), 0.0), 2) for r in rows}
        order_kargo = round(sum(maliyetler), 2)
        naive_kargo = round(sum(round(sayi(r.get(kmap["kargo_maliyet"]), 0.0), 2)
                                for r in rows), 2)

        # İptal/iade şüphesi: negatif veya sıfır Order Total → gelirden hariç
        if total < 0 or total == 0 or paid < 0:
            iptal_iade.append({
                "order_no": "" if ono in bos_anahtarlar else ono,
                "store": store, "tarih": ilk_t.strftime("%d.%m.%Y"),
                "order_total": total,
                "durum": "negatif tutar" if total < 0 or paid < 0 else "sıfır tutar"})
            iptal_magaza[store] = iptal_magaza.get(store, 0) + 1
            continue

        kargo_distinct_toplam += order_kargo
        kargo_naive_toplam += naive_kargo

        if _amazon_pazar_mi(rep.get(kmap["marketplace"]), store):
            pazar_sayilari["amazon"] += 1
            am = amazon.setdefault(store, {"siparis": 0, "kargo": 0.0})
            am["siparis"] += 1
            am["kargo"] += order_kargo
            continue

        pazar_sayilari["etsy"] += 1
        m = magazalar.setdefault(store, {
            "ciro_subtotal_shipping": 0.0, "ciro_order_total": 0.0,
            "ciro_amount_paid": 0.0, "vergi": 0.0, "kargo_musteri": 0.0,
            "kargo_maliyet": 0.0, "adet": 0.0, "siparis_sayisi": 0})
        sub = alan(rep, "subtotal")
        shp = alan(rep, "kargo_musteri")
        m["ciro_subtotal_shipping"] += sub + shp
        m["ciro_order_total"] += total
        m["ciro_amount_paid"] += paid
        m["vergi"] += alan(rep, "tax")
        m["kargo_musteri"] += shp
        m["kargo_maliyet"] += order_kargo
        m["adet"] += alan(rep, "item_sayisi")
        m["siparis_sayisi"] += 1
        if ono in bos_anahtarlar:
            b = bos_order_no.setdefault(store, {"satir": 0, "ciro": 0.0})
            b["satir"] += 1
            b["ciro"] += total
        else:
            siparisler[ono] = {"store": store, "ciro": total,
                               "tarih": ilk_t.strftime("%d.%m.%Y")}

    amazon = {k: {"siparis": v["siparis"], "kargo": round(v["kargo"], 2)}
              for k, v in amazon.items()}

    kapsama = {"ilk": None, "son": None, "uyari": None}
    if tum_tarihler:
        ilk, son = min(tum_tarihler), max(tum_tarihler)
        kapsama["ilk"] = ilk.strftime("%d.%m.%Y")
        kapsama["son"] = son.strftime("%d.%m.%Y")
        son_gun = calendar.monthrange(yil, ay)[1]
        if ilk > datetime(yil, ay, 1) or son < datetime(yil, ay, son_gun):
            kapsama["uyari"] = (
                f"Sipariş export'u {ilk.strftime('%d.%m.%Y')} – "
                f"{son.strftime('%d.%m.%Y')} aralığını kapsıyor; seçilen ay "
                f"({ay:02d}/{yil}) tam kapsanmıyor olabilir.")
    return {"magazalar": magazalar, "amazon": amazon, "siparisler": siparisler,
            "iptal_iade": iptal_iade, "iptal_magaza": iptal_magaza,
            "bos_order_no": bos_order_no, "kapsama": kapsama,
            "kargo_distinct_toplam": round(kargo_distinct_toplam, 2),
            "kargo_naive_toplam": round(kargo_naive_toplam, 2),
            "pazar_sayilari": pazar_sayilari,
            "benzersiz_siparis": benzersiz_siparis,
            "ay_satir_sayisi": ay_siparis_sayisi,
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
