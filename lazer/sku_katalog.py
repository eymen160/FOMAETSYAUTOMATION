# Birleşik SKU kataloğu: tüm kaynaklardan (ShipStation kalem, Etsy item,
# SKU katalog dosyaları) her SKU'yu tek envanterde toplar. Her SKU için:
# örnek ad, toplam adet, görüldüğü mağaza/kaynak sayısı, otomatik kategori
# (keyword motoru) ve öğrenilmiş kategori (urun_mapping.json).
#
# Bu katalog: (1) "tüm ürünlere/SKU'lara sahip miyiz?" sorusunun cevabı,
# (2) öğretme (teach) ekranının veri kaynağı, (3) raporun ürün dökümü için
# referans. urun_mapping.json'ı KİRLETMEZ — yalnızca okur. Yeniden
# üretilebilir; kural değişince tekrar çalıştırılır.
import json
import os

from . import urun_eslestirme as ue
from .shipstation_csv import _csv_oku, CsvHata
from .yardimci import kolon_bul, sayi

SKU_KATALOG_DOSYASI = "sku_katalog.json"

# Kaynaklar arası olası kolon adları (ShipStation + Etsy + katalog dosyaları)
_SKU_ADAYLARI = ["Item SKU", "SKU", "Sku"]
_AD_ADAYLARI = ["Item Name", "Product Name", "Listing Title", "Title", "Name"]
_QTY_ADAYLARI = ["Item Quantity", "Quantity", "Qty"]
_MAGAZA_ADAYLARI = ["Store", "Shop Name", "Shop", "Market - Store Name"]


def _dosya_tara(yol):
    """Tek CSV'den (sku, ad, adet, magaza) kayıtları üretir (jeneratör).
    Kalem/Etsy/katalog formatlarını kolon adından otomatik tanır."""
    try:
        satirlar = _csv_oku(yol)
    except CsvHata:
        return
    if not satirlar:
        return
    basliklar = list(satirlar[0].keys())
    sk = kolon_bul(basliklar, _SKU_ADAYLARI, prefix=False)
    adk = kolon_bul(basliklar, _AD_ADAYLARI, prefix=False)
    if not sk and not adk:
        return  # ürün dosyası değil (ör. saf sevkiyat/özet)
    qk = kolon_bul(basliklar, _QTY_ADAYLARI, prefix=False)
    stk = kolon_bul(basliklar, _MAGAZA_ADAYLARI, prefix=False)
    for r in satirlar:
        sku = (r.get(sk) or "").strip() if sk else ""
        ad = (r.get(adk) or "").strip() if adk else ""
        if not sku and not ad:
            continue
        if ad.startswith("("):   # "(3 Items)" gibi gruplu satır
            continue
        adet = int(sayi(r.get(qk), 1) or 1) if qk else 1
        magaza = (r.get(stk) or "").strip() if stk else ""
        yield sku, ad, adet, magaza


def katalog_topla(yollar, mapping=None):
    """Verilen CSV yollarından birleşik SKU kataloğu üretir.

    Dönüş: {anahtar: {sku, ornek_ad, adlar{ad:adet}, adet, magazalar(set),
                      kaynaklar(set), auto_kategori, kategori}}
    anahtar = SKU (varsa); SKU yoksa 'ad' ile gruplanır."""
    if mapping is None:
        mapping = ue.yukle()
    katalog = {}
    for yol in yollar:
        dosya = os.path.basename(yol)
        for sku, ad, adet, magaza in _dosya_tara(yol):
            anahtar = sku or f"(SKU yok) {ad[:48]}"
            k = katalog.get(anahtar)
            if k is None:
                k = katalog[anahtar] = {
                    "sku": sku, "adlar": {}, "adet": 0,
                    "magazalar": set(), "kaynaklar": set()}
            if ad:
                k["adlar"][ad] = k["adlar"].get(ad, 0) + adet
            k["adet"] += adet
            if magaza:
                k["magazalar"].add(magaza)
            k["kaynaklar"].add(dosya)
    for k in katalog.values():
        ornek = max(k["adlar"], key=k["adlar"].get) if k["adlar"] else ""
        k["ornek_ad"] = ornek
        # auto kategori: öğrenilmiş haritayı KULLANMADAN salt keyword sonucu
        k["auto_kategori"] = ue.siniflandir(ornek, k["sku"], {})
        k["kategori"] = mapping.get(k["sku"]) if k["sku"] else None
    return katalog


def durum(k):
    """Bir katalog kaydının sınıflandırma durumu."""
    if k.get("kategori"):
        return "öğrenildi"
    if k.get("auto_kategori"):
        return "auto"
    return "bilinmiyor"


def ogretilecekler(katalog):
    """Öğretme kuyruğu: ne keyword ne de öğrenilmiş haritanın çözebildiği
    SKU'lar, hacme (adet) göre azalan sıralı."""
    liste = [k for k in katalog.values() if durum(k) == "bilinmiyor"]
    return sorted(liste, key=lambda k: -k["adet"])


def ozet(katalog):
    """Kapsama özeti: SKU sayısı ve adet bazında auto/öğrenilmiş/bilinmeyen."""
    toplam_sku = len(katalog)
    toplam_adet = sum(k["adet"] for k in katalog.values())
    cozulen_sku = sum(1 for k in katalog.values() if durum(k) != "bilinmiyor")
    cozulen_adet = sum(k["adet"] for k in katalog.values()
                       if durum(k) != "bilinmiyor")
    return {
        "sku_sayisi": toplam_sku,
        "cozulen_sku": cozulen_sku,
        "bilinmeyen_sku": toplam_sku - cozulen_sku,
        "adet": toplam_adet,
        "cozulen_adet": cozulen_adet,
        "sku_oran": round(cozulen_sku / toplam_sku, 4) if toplam_sku else 0,
        "adet_oran": round(cozulen_adet / toplam_adet, 4) if toplam_adet else 0,
    }


def _json_kayit(k):
    """Tek kaydı JSON'a yazılabilir biçime çevir (set→liste, ad varyantları)."""
    adlar = sorted(k["adlar"].items(), key=lambda x: -x[1])
    return {
        "sku": k["sku"],
        "ornek_ad": k["ornek_ad"],
        "ad_varyantlari": [a for a, _ in adlar[:3]],
        "adet": k["adet"],
        "magaza_sayisi": len(k["magazalar"]),
        "kaynaklar": sorted(k["kaynaklar"]),
        "auto_kategori": k["auto_kategori"],
        "kategori": k["kategori"],
        "durum": durum(k),
    }


def katalog_yaz(katalog, yol=SKU_KATALOG_DOSYASI):
    """Kataloğu, hacme göre sıralı JSON olarak diske yazar."""
    sirali = sorted(katalog.items(), key=lambda kv: -kv[1]["adet"])
    out = {anahtar: _json_kayit(k) for anahtar, k in sirali}
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return yol


def katalog_oku(yol=SKU_KATALOG_DOSYASI):
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    return {}
