# Rapor orkestrasyon servisi: analiz sonucu + eşleştirme + kargo verisinden
# rapor satırlarını üretir. Web katmanından (app.py) ayrıktır ve DURUM
# global'ine dokunmaz — tüm girdiler parametre olarak gelir, böylece Flask
# istemcisi olmadan doğrudan birim test edilebilir.
import os

from . import eslestirme, etsy, formsuz, shipstation_csv, urun_eslestirme
from .yardimci import tr_kucuk


def kaynak_varsayilan(analiz):
    """Ciro kaynağı varsayılanı: sipariş özeti raporu varsa subtotal+shipping,
    yoksa order_total."""
    return "subtotal_shipping" if analiz.get("ozet") else "order_total"


def ss_master_bazinda(analiz, eslesme, kargo):
    """ShipStation verilerini master mağaza adına çevirip birleştirir.

    Öncelik: gelir + kargo maliyeti sipariş özeti raporundan; PARÇA ADEDİ
    item bazlı Orders CSV'sinden; kargo maliyeti özet yoksa API/CSV'den.
    Dönüş: (ss_veri {master: {...}}, amazon_liste, eslesmeyen_ss)."""
    ss_veri = {}
    amazon = {}
    eslesmeyen_ss = []

    def hedef_bul(ss_ad):
        hedef = eslesme.get(ss_ad.strip())
        if hedef is None and shipstation_csv.amazon_mu(ss_ad):
            hedef = eslestirme.AMAZON_ETIKETI
        return hedef

    def hucre(hedef):
        return ss_veri.setdefault(hedef, {
            "ciro_order_total": None, "ciro_amount_paid": None,
            "ciro_subtotal_shipping": None, "vergi": None,
            "kargo_musteri": None, "adet": None, "kargo_api": None})

    def ekle(h, alan, deger):
        if deger is not None:
            h[alan] = (h[alan] or 0.0) + deger

    ozet = analiz.get("ozet")
    if ozet:
        for ss_ad, v in ozet["magazalar"].items():
            hedef = hedef_bul(ss_ad)
            if hedef == eslestirme.AMAZON_ETIKETI:
                am = amazon.setdefault(ss_ad.strip(), {"siparis": 0, "kargo": 0.0})
                am["siparis"] += v["siparis_sayisi"]
                am["kargo"] += v["kargo_maliyet"]
                continue
            if hedef is None or hedef == "-":
                eslesmeyen_ss.append(ss_ad.strip())
                continue
            h = hucre(hedef)
            for alan in ("ciro_order_total", "ciro_amount_paid",
                         "ciro_subtotal_shipping", "vergi", "kargo_musteri"):
                ekle(h, alan, v[alan])
            ekle(h, "kargo_api", v["kargo_maliyet"])
    if analiz.get("orders"):
        for ss_ad, v in analiz["orders"]["magazalar"].items():
            hedef = hedef_bul(ss_ad)
            if hedef == eslestirme.AMAZON_ETIKETI:
                if not ozet:
                    am = amazon.setdefault(ss_ad.strip(), {"siparis": 0, "kargo": 0.0})
                    am["siparis"] += v["siparis_sayisi"]
                continue
            if hedef is None or hedef == "-":
                eslesmeyen_ss.append(ss_ad.strip())
                continue
            h = hucre(hedef)
            ekle(h, "adet", v["adet"])  # adet yalnızca item bazlı export'ta doğru
            if not ozet:  # gelir alanlarında özet raporu önceliklidir
                for alan in ("ciro_order_total", "ciro_amount_paid", "vergi",
                             "kargo_musteri"):
                    ekle(h, alan, v[alan])
    if kargo and not ozet:
        for ss_ad, tutar in kargo["magaza_kargo"].items():
            hedef = hedef_bul(ss_ad)
            if hedef == eslestirme.AMAZON_ETIKETI:
                am = amazon.setdefault(ss_ad.strip(), {"siparis": 0, "kargo": 0.0})
                am["kargo"] += tutar
                continue
            if hedef is None or hedef == "-":
                continue
            ekle(hucre(hedef), "kargo_api", tutar)
    # Amazon gönderi sayıları (shipments CSV'den, sipariş sayısı yoksa)
    if analiz.get("shipments"):
        for ss_ad, adet in analiz["shipments"]["gonderi_sayisi"].items():
            if shipstation_csv.amazon_mu(ss_ad):
                am = amazon.setdefault(ss_ad.strip(), {"siparis": 0, "kargo": 0.0})
                am["siparis"] = max(am["siparis"], adet)
    amazon_liste = [{"magaza": k, **v} for k, v in sorted(amazon.items())]
    return ss_veri, amazon_liste, sorted(set(eslesmeyen_ss))


def urun_master_bazinda(analiz, eslesme):
    """Kalem-bazlı otomatik ürün adetlerini master mağaza adına çevirir.
    Dönüş: {master_magaza: {kategori: adet}}  (Amazon ve eşleşmeyen hariç)."""
    kalem = analiz.get("kalem")
    if not kalem:
        return {}
    sonuc = {}
    for ss_ad, urunler in kalem["magaza_urun"].items():
        hedef = eslesme.get(ss_ad.strip())
        if hedef is None and shipstation_csv.amazon_mu(ss_ad):
            continue  # Amazon rapora girmez
        if hedef is None or hedef in ("-", eslestirme.AMAZON_ETIKETI):
            continue
        d = sonuc.setdefault(hedef, {})
        for kat, adet in urunler.items():
            d[kat] = d.get(kat, 0) + adet
    return sonuc


def rapor_satirlari(analiz, eslesme, kargo, kaynaklar, ciro_kaynagi,
                    urun_kaynagi="form"):
    """Rapor + ekran tablosu için ortak satır üretimi. Kaynak seçimini ve
    ürün adetlerini uygular. urun_kaynagi: 'form' (beyan) veya 'shipstation'
    (kalem-bazlı otomatik sınıflandırma). Dönüş: (satirlar, ss_veri,
    amazon_liste, urun_basliklari, kaynak_kullanim)."""
    if analiz.get("mod") == "formsuz":
        satirlar, amazon_liste, urun_basliklari = formsuz.rapor_satirlari(
            analiz.get("ozet"), analiz.get("kalem"), analiz.get("elle"),
            eslesme, ciro_kaynagi,
            etsy_finansal=analiz.get("etsy_finansal"),
            reklam_magaza=analiz.get("reklam_magaza"))
        # Formsuz modda finansal kolonlar her zaman ham veriden gelir
        kaynak_kullanim = {al: "shipstation" for al in
                           ("ciro", "vergi", "kargo_musteri", "kargo", "adet")}
        return satirlar, {}, amazon_liste, urun_basliklari, kaynak_kullanim
    ss_veri, amazon_liste, _ = ss_master_bazinda(analiz, eslesme, kargo)
    urun_basliklari = list(analiz.get("urun_basliklari") or [])
    urun_map = analiz.get("urun_adetleri") or {}
    # ShipStation otomatik ürün adetleri (kalem-bazlı), seçilirse kullan
    if urun_kaynagi == "shipstation" and analiz.get("kalem"):
        oto = urun_master_bazinda(analiz, eslesme)
        urun_map = {m: {k: d.get(k, 0) for k in urun_basliklari}
                    for m, d in oto.items()}
        if urun_eslestirme.DIGER not in urun_basliklari:
            urun_basliklari.append(urun_eslestirme.DIGER)
        for m, d in oto.items():
            urun_map.setdefault(m, {})[urun_eslestirme.DIGER] = d.get(
                urun_eslestirme.DIGER, 0)
    kaynak_kullanim = {}
    satirlar = []
    for kayit in sorted(analiz["kayitlar"], key=lambda k: tr_kucuk(k["magaza"])):
        ss = ss_veri.get(kayit["magaza"]) or {}
        ss_degerler = {
            "ciro": ss.get(f"ciro_{ciro_kaynagi}", ss.get("ciro_order_total")),
            "vergi": ss.get("vergi"),
            "kargo_musteri": ss.get("kargo_musteri"),
            "adet": ss.get("adet"),
            "kargo": ss.get("kargo_api"),
        }
        satir = {"magaza": kayit["magaza"],
                 "reklam": kayit["reklam"],            # her zaman formdan
                 "ilave_odeme": kayit["ek_odeme"],     # her zaman formdan
                 "upgrade": kayit["upgrade"],
                 "urunler": urun_map.get(kayit["magaza"], {})}
        for alan in ("ciro", "vergi", "kargo_musteri", "kargo", "adet"):
            secim = kaynaklar.get(alan, "shipstation")
            ss_d = ss_degerler.get(alan)
            kullanilan = "form" if (secim == "form" or ss_d is None) else "shipstation"
            satir[alan] = kayit[alan] if kullanilan == "form" else ss_d
            kaynak_kullanim.setdefault(alan, kullanilan)
        satir["adet"] = int(round(satir["adet"] or 0))
        satirlar.append(satir)
    return satirlar, ss_veri, amazon_liste, urun_basliklari, kaynak_kullanim


def etsy_enrichment(etsy_slot, reklam_yollari, ss_yollari, ay=None, yil=None):
    """Etsy finansal zenginleştirmesini kur (formsuz mod).

    Etsy komisyon/net/iade'yi Order# → Store haritası üzerinden mağazalara
    dağıtır; reklam giderini ayrı hesap özetinden toplar. ay/yil verilirse
    Etsy verisi ShipStation ciro'su ile aynı döneme filtrelenir.
    Dönüş: (etsy_finansal {ss_store: {...}}, reklam_magaza {ss_store: tutar},
            meta) — Etsy/reklam verisi yoksa (None, None, None)."""
    slot = etsy_slot or {}
    pay = slot.get("etsy_payments") or []
    ords = slot.get("etsy_orders") or []
    reklam_yollari = reklam_yollari or []
    if not (pay or ords or reklam_yollari):
        return None, None, None
    ss_yollari = [y for y in (ss_yollari or []) if y and os.path.exists(y)]
    harita = etsy.magaza_haritasi(ss_yollari)
    fin = etsy.siparis_finansal(pay, ords, ay, yil)
    mf = etsy.magaza_finansal(harita, fin)
    rk = etsy.reklam_topla(reklam_yollari, ay, yil)
    meta = {
        "magaza_sayisi": len(mf["magazalar"]),
        "eslesen": mf["eslesen"], "eslesmeyen": mf["eslesmeyen"],
        "iade_sayisi": len(mf["iade_kalemleri"]),
        "iade_toplam": round(sum(i["iade"] for i in mf["iade_kalemleri"]), 2),
        "iade_kalemleri": mf["iade_kalemleri"][:100],
        "reklam_toplam": rk["toplam"],
        "reklam_magaza_bazli": bool(rk["magaza"]),
    }
    return mf["magazalar"], rk["magaza"], meta
