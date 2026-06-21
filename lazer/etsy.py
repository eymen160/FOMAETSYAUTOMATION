# Etsy export'larını ShipStation mağazalarıyla birleştirir (zenginleştirme).
#
# Etsy dosyalarında ShipStation "Store" kolonu YOKTUR; her dosya bir mağazaya
# aittir ama mağaza adı dosyanın içinde bulunmaz. Bu yüzden birleştirme
# anahtarı her yerde Order ID'dir (= ShipStation "Order #"). Etsy'nin
# komisyon / net / iade verisini ShipStation Order# → Store haritası üzerinden
# mağazalara dağıtırız.
#
# Üretilenler:
#   komisyon  Etsy ödeme komisyonu (DirectCheckoutPayments.Fees /
#             SoldOrders.Card Processing Fees) — gider, pozitif tutulur
#   net       Etsy net tutar (Net Amount / Order Net)
#   brut      Etsy brüt (Gross Amount / Order Total)
#   kdv       VAT Amount / Sales Tax (genelde 0 — Etsy pazaryeri vergisini
#             satıcıya yansıtmaz)
#   iade      Refund Amount > 0 olan ödemeler → "çöp"/iptal-iade kalemleri
#   reklam    Ayrı Etsy Ads / hesap özeti CSV'sinden (Etsy ÜRÜN dosyalarında
#             reklam gideri kolonu YOKTUR)
from .shipstation_csv import CsvHata, _csv_oku, _tarih
from .yardimci import kolon_bul, sayi

# Etsy birleştirme anahtarı (her dosyada bir biçimde Order ID bulunur)
_ORDER_ADAYLARI = ["Order ID", "Order #", "Order Number", "Order - Number",
                   "Order"]
_STORE_ADAYLARI = ["Store", "Market - Store Name", "Shop Name", "Shop"]
# Dönem (ay/yıl) filtresi için tarih kolonları
_PAY_TARIH = ["Order Date", "Date", "Funds Available"]
_ORD_TARIH = ["Sale Date", "Date Paid", "Order Date", "Date"]


def _kolonlar(satirlar):
    return list(satirlar[0].keys()) if satirlar else []


def _donemde_mi(deger, ay, yil):
    """ay/yil verilmişse satırın tarihini kontrol et. Tarih kolonu yoksa
    (deger None) filtre uygulanmaz → True. Tarih var ama çözülemez/dönem
    dışıysa False (çapraz-dönem bulaşmasını önler)."""
    if not ay or not yil:
        return True
    if deger is None:        # bu dosyada tarih kolonu yok → filtreleme
        return True
    dt = _tarih(deger)
    return bool(dt and dt.month == ay and dt.year == yil)


def magaza_haritasi(yollar):
    """ShipStation dosyalarından Order# → Store sözlüğü kur.

    Birden çok dosya verilebilir (ozet / kalem / orders / shipments). Aynı
    Order# birden çok dosyada görünürse ilk (boş olmayan) Store kazanır."""
    harita = {}
    for yol in yollar or []:
        try:
            satirlar = _csv_oku(yol)
        except CsvHata:
            continue
        b = _kolonlar(satirlar)
        c_ord = kolon_bul(b, _ORDER_ADAYLARI)
        c_store = kolon_bul(b, _STORE_ADAYLARI)
        if not (c_ord and c_store):
            continue
        for r in satirlar:
            no = (r.get(c_ord) or "").strip()
            store = (r.get(c_store) or "").strip()
            if no and store and no not in harita:
                harita[no] = store
    return harita


def _bos_fin():
    return {"brut": 0.0, "komisyon": 0.0, "net": 0.0,
            "kdv": 0.0, "iade": 0.0, "kaynak": None}


def payments_topla(yollar, ay=None, yil=None):
    """Etsy ödeme (DirectCheckoutPayments) dosyalarını Order ID bazında topla.
    ay/yil verilirse yalnız o döneme ait satırlar (Order Date) sayılır.

    Dönüş: {order_id: {brut, komisyon, net, kdv, iade, kaynak}}"""
    veri = {}
    for yol in yollar or []:
        try:
            satirlar = _csv_oku(yol)
        except CsvHata:
            continue
        b = _kolonlar(satirlar)
        c_ord = kolon_bul(b, _ORDER_ADAYLARI)
        if not c_ord:
            continue
        c_gross = kolon_bul(b, ["Gross Amount", "Gross"])
        c_fees = kolon_bul(b, ["Fees", "Card Processing Fees"])
        c_net = kolon_bul(b, ["Net Amount", "Net"])
        c_vat = kolon_bul(b, ["VAT Amount", "VAT"])
        c_ref = kolon_bul(b, ["Refund Amount", "Refund"])
        c_tar = kolon_bul(b, _PAY_TARIH)
        for r in satirlar:
            no = (r.get(c_ord) or "").strip()
            if not no:
                continue
            if not _donemde_mi(r.get(c_tar) if c_tar else None, ay, yil):
                continue
            d = veri.setdefault(no, _bos_fin())
            d["kaynak"] = "payment"
            d["brut"] += sayi(r.get(c_gross), 0.0) if c_gross else 0.0
            d["komisyon"] += sayi(r.get(c_fees), 0.0) if c_fees else 0.0
            d["net"] += sayi(r.get(c_net), 0.0) if c_net else 0.0
            d["kdv"] += sayi(r.get(c_vat), 0.0) if c_vat else 0.0
            d["iade"] += sayi(r.get(c_ref), 0.0) if c_ref else 0.0
    return veri


def orders_birlestir(veri, yollar, ay=None, yil=None):
    """SoldOrders dosyalarından, ödemede OLMAYAN siparişler için komisyon/net
    boşluğunu doldur (ödeme kaydı kanonik kabul edilir, üzerine yazılmaz).
    ay/yil verilirse yalnız o döneme ait satırlar (Sale Date) sayılır."""
    for yol in yollar or []:
        try:
            satirlar = _csv_oku(yol)
        except CsvHata:
            continue
        b = _kolonlar(satirlar)
        c_ord = kolon_bul(b, _ORDER_ADAYLARI)
        if not c_ord:
            continue
        c_total = kolon_bul(b, ["Order Total", "Order Value"])
        c_fees = kolon_bul(b, ["Card Processing Fees", "Fees"])
        c_net = kolon_bul(b, ["Order Net", "Net"])
        c_vat = kolon_bul(b, ["Sales Tax", "VAT Amount", "VAT"])
        c_tar = kolon_bul(b, _ORD_TARIH)
        for r in satirlar:
            no = (r.get(c_ord) or "").strip()
            if not no or no in veri:   # ödeme kaydı varsa dokunma
                continue
            if not _donemde_mi(r.get(c_tar) if c_tar else None, ay, yil):
                continue
            d = veri.setdefault(no, _bos_fin())
            d["kaynak"] = "order"
            d["brut"] += sayi(r.get(c_total), 0.0) if c_total else 0.0
            d["komisyon"] += sayi(r.get(c_fees), 0.0) if c_fees else 0.0
            d["net"] += sayi(r.get(c_net), 0.0) if c_net else 0.0
            d["kdv"] += sayi(r.get(c_vat), 0.0) if c_vat else 0.0
    return veri


def siparis_finansal(payment_yollari=None, order_yollari=None,
                     ay=None, yil=None):
    """Etsy sipariş bazında finansal veri: ödemeler + (boşlukta) siparişler.
    ay/yil verilirse her iki kaynak da o döneme filtrelenir (ShipStation
    ciro'su ile aynı ay olması için)."""
    veri = payments_topla(payment_yollari, ay, yil)
    orders_birlestir(veri, order_yollari, ay, yil)
    return veri


def magaza_finansal(harita, siparis_fin):
    """Order# → Store haritası ile Etsy finansalını mağaza bazında topla.

    Dönüş: {
      "magazalar": {ss_store: {komisyon, net, brut, kdv, iade,
                               iade_sayisi, siparis}},
      "eslesen": n, "eslesmeyen": n, "iade_kalemleri": [...]
    }
    eslesmeyen: Order# ShipStation'da bulunamayan Etsy siparişleri (mağazaya
    atanamaz — Etsy/ShipStation dönem farkı ya da eksik dosya)."""
    magazalar = {}
    eslesen = eslesmeyen = 0
    iadeler = []
    for no, f in siparis_fin.items():
        store = harita.get(no)
        if not store:
            eslesmeyen += 1
            continue
        eslesen += 1
        m = magazalar.setdefault(store, {
            "komisyon": 0.0, "net": 0.0, "brut": 0.0,
            "kdv": 0.0, "iade": 0.0, "iade_sayisi": 0, "siparis": 0})
        m["komisyon"] += f["komisyon"]
        m["net"] += f["net"]
        m["brut"] += f["brut"]
        m["kdv"] += f["kdv"]
        m["siparis"] += 1
        if f["iade"] > 0:
            m["iade"] += f["iade"]
            m["iade_sayisi"] += 1
            iadeler.append({"order": no, "magaza": store,
                            "iade": round(f["iade"], 2)})
    for m in magazalar.values():
        for k in ("komisyon", "net", "brut", "kdv", "iade"):
            m[k] = round(m[k], 2)
    iadeler.sort(key=lambda x: x["iade"], reverse=True)
    return {"magazalar": magazalar, "eslesen": eslesen,
            "eslesmeyen": eslesmeyen, "iade_kalemleri": iadeler}


# --- Reklam / Etsy Ads hesap özeti -----------------------------------------
_REKLAM_TUTAR = ["Ad Spend", "Advertising Cost", "Etsy Ads Cost", "Amount",
                 "Net", "Spend", "Cost", "Fees & Taxes"]
_REKLAM_TIP = ["Type", "Title", "Description", "Activity"]
_REKLAM_ANAHTAR = ("marketing", "advertis", "etsy ads", "reklam", "offsite",
                   "onsite")


def reklam_topla(yollar, ay=None, yil=None):
    """Etsy Ads / hesap özeti CSV'lerinden reklam giderini topla.

    Etsy ÜRÜN dosyalarında reklam kolonu yoktur; reklam ayrı bir hesap özeti
    (Shop Manager → Finances) dosyasından gelir. Biçim mağazaya göre değişir;
    bu yüzden esnek davranırız: net bir tutar kolonu varsa onu toplarız, bir
    "Type" kolonu varsa yalnız pazarlama/reklam satırlarını sayarız.
    ay/yil verilirse (ve tarih kolonu varsa) yalnız o dönem sayılır.

    Dönüş: {"toplam": float, "magaza": {store: tutar}, "kayit": n}"""
    toplam = 0.0
    per_magaza = {}
    kayit = 0
    for yol in yollar or []:
        try:
            satirlar = _csv_oku(yol)
        except CsvHata:
            continue
        b = _kolonlar(satirlar)
        c_tutar = kolon_bul(b, _REKLAM_TUTAR)
        c_tip = kolon_bul(b, _REKLAM_TIP)
        c_store = kolon_bul(b, _STORE_ADAYLARI)
        c_tar = kolon_bul(b, ["Date", "Order Date", "Sale Date"])
        if not c_tutar:
            continue
        for r in satirlar:
            if not _donemde_mi(r.get(c_tar) if c_tar else None, ay, yil):
                continue
            if c_tip:
                tip = (r.get(c_tip) or "").lower()
                if not any(a in tip for a in _REKLAM_ANAHTAR):
                    continue
            tutar = sayi(r.get(c_tutar), 0.0) or 0.0
            tutar = abs(tutar)        # gider; işaret ne olursa olsun büyüklük
            if tutar == 0:
                continue
            toplam += tutar
            kayit += 1
            if c_store:
                st = (r.get(c_store) or "").strip()
                if st:
                    per_magaza[st] = round(per_magaza.get(st, 0.0) + tutar, 2)
    return {"toplam": round(toplam, 2), "magaza": per_magaza, "kayit": kayit}
