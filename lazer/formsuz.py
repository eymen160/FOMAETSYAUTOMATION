# Formsuz rapor modu: rapor satırlarını doğrudan ShipStation + Etsy ham
# verisinden üretir (master form gerektirmez). Mağazalar verinin kendisinden
# gelir. Reklam/İlave ödeme/Upgrade elle girilir; Etsy Ads özeti varsa reklam
# oradan otomatik gelir.
import json
import os

from . import eslestirme
from .shipstation_csv import amazon_mu
from .urun_eslestirme import DIGER
from .yardimci import tr_kucuk

ELLE_DOSYASI = "elle_girdi.json"

# Elle girilen / dış kaynaklı alanlar (formsuz modda ham veride yok)
ELLE_ALANLAR = ["reklam", "ilave_odeme", "upgrade"]


def elle_yukle(yol=ELLE_DOSYASI):
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    return {}


def elle_kaydet(donem_anahtari, girdiler, yol=ELLE_DOSYASI):
    """girdiler: {magaza: {reklam, ilave_odeme, upgrade}} — dönem bazında saklanır."""
    veri = elle_yukle(yol)
    blok = veri.setdefault(donem_anahtari, {})
    for magaza, alanlar in girdiler.items():
        hedef = blok.setdefault(magaza, {})
        for k, v in alanlar.items():
            if k in ELLE_ALANLAR:
                hedef[k] = v
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2, sort_keys=True)
    return veri


def donem_anahtari(yil, ay):
    return f"{yil}-{ay:02d}"


def _kanonik(ss_ad, eslesme):
    """ShipStation mağaza adını kanonik (rapor) adına çevirir. Eşleştirme
    sözlüğünde varsa onu, yoksa adın kendisini (strip'li) kullanır."""
    ss = ss_ad.strip()
    hedef = eslesme.get(ss)
    if hedef and hedef not in ("-", eslestirme.AMAZON_ETIKETI):
        return hedef
    return ss


def rapor_satirlari(ozet_sonuc, kalem_sonuc=None, elle_girdiler=None,
                    eslesme=None, ciro_kaynagi="subtotal_shipping",
                    etsy_finansal=None, reklam_magaza=None):
    """ShipStation verisinden formsuz rapor satırları üretir.

    ozet_sonuc: shipstation_csv.ozet_isle çıktısı (gelir + kargo maliyeti)
    kalem_sonuc: urun_eslestirme.kalem_isle çıktısı (ürün + adet) — opsiyonel
    elle_girdiler: {kanonik_magaza: {reklam, ilave_odeme, upgrade}}
    etsy_finansal: {ss_store: {komisyon, net, brut, kdv, iade, iade_sayisi}}
        — Etsy Order# join'inden (etsy.magaza_finansal); satıra komisyon/net/
        iade ekler
    reklam_magaza: {ss_store|kanonik: reklam_tutari} — Etsy Ads hesap özetinden
        otomatik reklam (elle girdi varsa o önceliklidir)
    Dönüş: (satirlar, amazon_liste, urun_basliklari)
    """
    eslesme = eslesme or {}
    elle_girdiler = elle_girdiler or {}
    magazalar = {}        # kanonik → birikmiş finansal alanlar
    urun = {}             # kanonik → {kategori: adet}
    amazon = {}

    ciro_alan = f"ciro_{ciro_kaynagi}"
    for ss_ad, v in (ozet_sonuc or {}).get("magazalar", {}).items():
        if amazon_mu(ss_ad):
            am = amazon.setdefault(ss_ad.strip(), {"siparis": 0, "kargo": 0.0})
            am["siparis"] += v.get("siparis_sayisi", 0)
            am["kargo"] += v.get("kargo_maliyet", 0.0)
            continue
        if eslesme.get(ss_ad.strip()) in ("-", eslestirme.AMAZON_ETIKETI):
            if eslesme.get(ss_ad.strip()) == eslestirme.AMAZON_ETIKETI:
                am = amazon.setdefault(ss_ad.strip(), {"siparis": 0, "kargo": 0.0})
                am["siparis"] += v.get("siparis_sayisi", 0)
                am["kargo"] += v.get("kargo_maliyet", 0.0)
            continue
        kanon = _kanonik(ss_ad, eslesme)
        m = magazalar.setdefault(kanon, {"ciro": 0.0, "vergi": 0.0,
                                         "kargo_musteri": 0.0, "kargo": 0.0,
                                         "siparis": 0, "adet": 0})
        m["ciro"] += v.get(ciro_alan, v.get("ciro_subtotal_shipping", 0.0)) or 0.0
        m["vergi"] += v.get("vergi", 0.0)
        m["kargo_musteri"] += v.get("kargo_musteri", 0.0)
        m["kargo"] += v.get("kargo_maliyet", 0.0)
        m["siparis"] += v.get("siparis_sayisi", 0)

    # Ürün + adet (kalem detayından)
    if kalem_sonuc:
        for ss_ad, urunler in kalem_sonuc.get("magaza_urun", {}).items():
            if amazon_mu(ss_ad) or eslesme.get(ss_ad.strip()) in (
                    "-", eslestirme.AMAZON_ETIKETI):
                continue
            kanon = _kanonik(ss_ad, eslesme)
            d = urun.setdefault(kanon, {})
            for kat, adet in urunler.items():
                d[kat] = d.get(kat, 0) + adet

    # Etsy finansal (komisyon/net/iade) — ss_store → kanonik topla
    etsy_kanon = {}
    for ss_ad, f in (etsy_finansal or {}).items():
        if amazon_mu(ss_ad) or eslesme.get(ss_ad.strip()) in (
                "-", eslestirme.AMAZON_ETIKETI):
            continue
        kanon = _kanonik(ss_ad, eslesme)
        d = etsy_kanon.setdefault(kanon, {"komisyon": 0.0, "net": 0.0,
            "brut": 0.0, "kdv": 0.0, "iade": 0.0, "iade_sayisi": 0})
        for k in ("komisyon", "net", "brut", "kdv", "iade"):
            d[k] += f.get(k, 0.0) or 0.0
        d["iade_sayisi"] += f.get("iade_sayisi", 0) or 0

    # Reklam (ss_store ya da kanonik anahtarlı) — kanonik topla
    reklam_kanon = {}
    for ad, tutar in (reklam_magaza or {}).items():
        kanon = _kanonik(ad, eslesme)
        reklam_kanon[kanon] = reklam_kanon.get(kanon, 0.0) + (tutar or 0.0)

    # Ürün başlıkları (görünen sıra: kategori listesi + Diğer)
    from .urun_eslestirme import KATEGORILER
    urun_basliklari = list(KATEGORILER)
    if any(DIGER in d for d in urun.values()):
        urun_basliklari.append(DIGER)

    satirlar = []
    for kanon in sorted(magazalar, key=tr_kucuk):
        m = magazalar[kanon]
        u = urun.get(kanon, {})
        adet = sum(u.values()) if u else m["siparis"]   # kalem yoksa sipariş sayısı
        el = elle_girdiler.get(kanon, {})
        ef = etsy_kanon.get(kanon, {})
        # Reklam: elle girdi öncelikli; yoksa Etsy Ads özetinden otomatik
        reklam_elle = el.get("reklam")
        reklam = (float(reklam_elle) if reklam_elle
                  else round(reklam_kanon.get(kanon, 0.0), 2))
        satirlar.append({
            "magaza": kanon,
            "ciro": round(m["ciro"], 2),
            "vergi": round(m["vergi"], 2),
            "kargo_musteri": round(m["kargo_musteri"], 2),
            "kargo": round(m["kargo"], 2),
            "adet": int(adet),
            "reklam": reklam,
            "ilave_odeme": float(el.get("ilave_odeme") or 0),
            "upgrade": float(el.get("upgrade") or 0),
            # Etsy zenginleştirme (yoksa 0)
            "komisyon": round(ef.get("komisyon", 0.0), 2),
            "net": round(ef.get("net", 0.0), 2),
            "etsy_brut": round(ef.get("brut", 0.0), 2),
            "etsy_kdv": round(ef.get("kdv", 0.0), 2),
            "iade": round(ef.get("iade", 0.0), 2),
            "iade_sayisi": int(ef.get("iade_sayisi", 0)),
            "urunler": u,
            "siparis": m["siparis"],
        })
    amazon_liste = [{"magaza": k, **v} for k, v in sorted(amazon.items())]
    return satirlar, amazon_liste, urun_basliklari
