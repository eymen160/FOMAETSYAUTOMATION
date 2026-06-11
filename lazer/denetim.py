# Denetim: form beyanı vs ShipStation gerçeği karşılaştırması
SARI_ESIK = 0.05
KIRMIZI_ESIK = 0.15

# Karşılaştırılan alanlar: (alan_adi, form_anahtari, ss_anahtari)
ALANLAR = [
    ("ciro", "ciro", "ciro"),
    ("vergi", "vergi", "vergi"),
    ("kargo_musteri", "kargo_musteri", "kargo_musteri"),
    ("kargo", "kargo", "kargo_api"),
    ("adet", "adet", "adet"),
]


def _sapma(form, ss):
    if form is None or ss is None:
        return None
    taban = max(abs(form), abs(ss))
    if taban == 0:
        return 0.0
    return abs(form - ss) / taban


def renk(sapma):
    if sapma is None:
        return "yok"
    if sapma > KIRMIZI_ESIK:
        return "kirmizi"
    if sapma > SARI_ESIK:
        return "sari"
    return "yesil"


def denetim_tablosu(form_kayitlari, ss_magaza_verisi, ciro_kaynagi="order_total"):
    """form_kayitlari: master.ay_kayitlari çıktısı
    ss_magaza_verisi: {master_magaza: {ciro_order_total, ciro_amount_paid,
                       vergi, kargo_musteri, adet, kargo_api}}
    Dönüş: mağaza başına form/ss değerleri + sapma + renk."""
    tablo = []
    for kayit in sorted(form_kayitlari, key=lambda k: k["magaza"].lower()):
        m = kayit["magaza"]
        ss = ss_magaza_verisi.get(m) or {}
        ss_ciro = ss.get("ciro_amount_paid" if ciro_kaynagi == "amount_paid"
                         else "ciro_order_total")
        satir = {"magaza": m, "ss_var": bool(ss), "alanlar": {}}
        ss_degerler = {"ciro": ss_ciro, "vergi": ss.get("vergi"),
                       "kargo_musteri": ss.get("kargo_musteri"),
                       "adet": ss.get("adet"), "kargo": ss.get("kargo_api")}
        for alan, form_k, _ in ALANLAR:
            f = kayit.get(form_k)
            s = ss_degerler.get(alan)
            sp = _sapma(f, s)
            satir["alanlar"][alan] = {
                "form": None if f is None else round(f, 2),
                "shipstation": None if s is None else round(s, 2),
                "sapma": None if sp is None else round(sp, 4),
                "renk": renk(sp),
            }
        tablo.append(satir)
    return tablo


def ciro_kalibrasyonu(form_kayitlari, ss_magaza_verisi):
    """Order Total mı Amount Paid mi 'Ciro' tanımına oturuyor?
    Her aday için form beyanlarına ortalama mutlak sapmayı ölçer."""
    sonuc = {"order_total": [], "amount_paid": [], "magaza_sayisi": 0}
    detay = []
    for kayit in form_kayitlari:
        ss = ss_magaza_verisi.get(kayit["magaza"])
        if not ss or not kayit.get("ciro"):
            continue
        f = kayit["ciro"]
        ot, ap = ss.get("ciro_order_total"), ss.get("ciro_amount_paid")
        d = {"magaza": kayit["magaza"], "form": round(f, 2)}
        if ot is not None:
            sonuc["order_total"].append(abs(f - ot) / max(f, 1))
            d["order_total"] = round(ot, 2)
        if ap is not None:
            sonuc["amount_paid"].append(abs(f - ap) / max(f, 1))
            d["amount_paid"] = round(ap, 2)
        detay.append(d)
    n = len(detay)
    ort_ot = sum(sonuc["order_total"]) / n if n and sonuc["order_total"] else None
    ort_ap = sum(sonuc["amount_paid"]) / n if n and sonuc["amount_paid"] else None
    oneri, net = None, False
    if ort_ot is not None and ort_ap is not None:
        if abs(ort_ot - ort_ap) >= 0.01:  # %1'den fazla fark → net karar
            oneri = "order_total" if ort_ot < ort_ap else "amount_paid"
            net = True
        else:
            oneri = "order_total" if ort_ot <= ort_ap else "amount_paid"
    elif ort_ot is not None:
        oneri, net = "order_total", True
    elif ort_ap is not None:
        oneri, net = "amount_paid", True
    return {"detay": detay, "magaza_sayisi": n,
            "ort_sapma_order_total": None if ort_ot is None else round(ort_ot, 4),
            "ort_sapma_amount_paid": None if ort_ap is None else round(ort_ap, 4),
            "oneri": oneri, "net": net}
