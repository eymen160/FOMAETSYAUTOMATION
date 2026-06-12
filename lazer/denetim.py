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
        ss_ciro = ss.get(f"ciro_{ciro_kaynagi}", ss.get("ciro_order_total"))
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


CIRO_ADAYLARI = ["subtotal_shipping", "order_total", "amount_paid"]


def ciro_kalibrasyonu(form_kayitlari, ss_magaza_verisi):
    """Hangi tutar 'Ciro' tanımına oturuyor? (Subtotal+Shipping, Order Total,
    Amount Paid) Her aday için form beyanlarına ortalama mutlak sapmayı ölçer."""
    sapmalar = {a: [] for a in CIRO_ADAYLARI}
    detay = []
    for kayit in form_kayitlari:
        ss = ss_magaza_verisi.get(kayit["magaza"])
        if not ss or not kayit.get("ciro"):
            continue
        f = kayit["ciro"]
        d = {"magaza": kayit["magaza"], "form": round(f, 2)}
        for aday in CIRO_ADAYLARI:
            v = ss.get(f"ciro_{aday}")
            if v is not None:
                sapmalar[aday].append(abs(f - v) / max(f, 1))
                d[aday] = round(v, 2)
        detay.append(d)
    n = len(detay)

    def medyan(liste):
        if not liste:
            return None
        s = sorted(liste)
        return round(s[len(s) // 2], 4)

    # Tek bir aşırı sapan mağaza ortalamayı bozmasın diye medyanla karşılaştır
    medyanlar = {a: medyan(v) for a, v in sapmalar.items()}
    adaylar = [(m, a) for a, m in medyanlar.items() if m is not None]
    oneri, net = None, False
    if adaylar:
        adaylar.sort()
        oneri = adaylar[0][1]
        net = len(adaylar) == 1 or adaylar[0][0] + 0.01 < adaylar[1][0]
    return {"detay": detay, "magaza_sayisi": n,
            "medyan_sapmalar": medyanlar,
            "oneri": oneri, "net": net}
