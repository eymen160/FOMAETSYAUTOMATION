# Ürün/denetim uç noktaları: form↔ShipStation denetimi, ürün adet denetimi,
# sipariş içeriği listesi ve SKU öğretme kuyruğu/kaydı.
import os

from flask import Blueprint, jsonify, request

import durum as durum_state
from durum import DURUM
from lazer import denetim, oneri, shipstation_csv, sku_katalog, urun_eslestirme
from lazer.yardimci import tr_kucuk
from web.ortak import hata as _hata

urun_bp = Blueprint("urun", __name__)


@urun_bp.route("/api/denetim", methods=["POST"])
def denetim_gor():
    a = DURUM["analiz"]
    if not a:
        return _hata("Önce analiz çalıştırın.")
    veri = request.get_json(silent=True) or {}
    ciro_kaynagi = veri.get("ciro_kaynagi") or (
        "subtotal_shipping" if a.get("ozet") else "order_total")
    ss_veri, amazon_liste, eslesmeyen_ss = durum_state.ss_master_bazinda()
    tablo = denetim.denetim_tablosu(a["kayitlar"], ss_veri, ciro_kaynagi)
    kalibrasyon = denetim.ciro_kalibrasyonu(a["kayitlar"], ss_veri)
    form_var = {k["magaza"] for k in a["kayitlar"]}
    ss_var_form_yok = sorted(set(ss_veri) - form_var)
    form_var_ss_yok = sorted(form_var - set(ss_veri)) if ss_veri else []
    return jsonify({
        "tablo": tablo,
        "kalibrasyon": kalibrasyon,
        "amazon": amazon_liste,
        "eslesmeyen_shipstation": eslesmeyen_ss,
        "ss_var_form_yok": ss_var_form_yok,
        "form_var_ss_yok": form_var_ss_yok,
        "kargo_hazir": DURUM["kargo"] is not None or a.get("ozet") is not None,
    })


@urun_bp.route("/api/urun/denetim", methods=["POST"])
def urun_denetim():
    """Ürün adetleri: form beyanı vs ShipStation otomatik sınıflandırma,
    master mağaza + kategori bazında, sapma renklendirmeli."""
    a = DURUM["analiz"]
    if not a:
        return _hata("Önce analiz çalıştırın.")
    if not a.get("kalem"):
        return _hata("Ürün denetimi için kalem detayı (Item Name'li export) "
                     "yükleyin.")
    basliklar = list(a.get("urun_basliklari") or [])
    if urun_eslestirme.DIGER not in basliklar:
        basliklar.append(urun_eslestirme.DIGER)
    form_map = a.get("urun_adetleri") or {}
    oto_map = durum_state.urun_master_bazinda()
    tablo = []
    for magaza in sorted(set(form_map) | set(oto_map), key=tr_kucuk):
        f = form_map.get(magaza, {})
        o = oto_map.get(magaza, {})
        f_top = sum(f.get(k, 0) for k in basliklar)
        o_top = sum(o.get(k, 0) for k in basliklar)
        taban = max(f_top, o_top)
        sapma = abs(f_top - o_top) / taban if taban else 0
        tablo.append({
            "magaza": magaza, "form_toplam": f_top, "oto_toplam": o_top,
            "sapma": round(sapma, 3), "renk": denetim.renk(sapma),
            "kategoriler": {k: {"form": f.get(k, 0), "oto": o.get(k, 0)}
                            for k in basliklar
                            if f.get(k, 0) or o.get(k, 0)},
        })
    return jsonify({
        "tablo": tablo, "basliklar": basliklar,
        "kapsama": a["kalem"]["kapsama"],
        "bilinmeyen": list(a["kalem"]["bilinmeyen"].items())[:30],
        "kategoriler": urun_eslestirme.KATEGORILER,
    })


@urun_bp.route("/api/siparis_icerik", methods=["POST"])
def siparis_icerik_gor():
    """Çok-ürünlü siparişlerin ('5 item') içeriğini listeler — Etsy'e manuel
    bakma ihtiyacını giderir. İsteğe bağlı 'ara' ile filtreler."""
    a = DURUM["analiz"]
    if not a:
        return _hata("Önce analiz çalıştırın.")
    if not (DURUM["kalem_yolu"] and os.path.exists(DURUM["kalem_yolu"])):
        return _hata("Sipariş içeriği için kalem detayı (Item Name'li export) "
                     "yükleyin.")
    veri = request.get_json(silent=True) or {}
    ara = (veri.get("ara") or "").strip().lower()
    try:
        s = urun_eslestirme.siparis_icerikleri(DURUM["kalem_yolu"], a["ay"], a["yil"])
    except shipstation_csv.CsvHata as e:
        return _hata(str(e))
    kayitlar = []
    for ono, g in s["icerik"].items():
        if ara and ara not in ono.lower() and ara not in g["store"].lower() \
                and not any(ara in it["ad"].lower() for it in g["items"]):
            continue
        kayitlar.append({"order_no": ono, "store": g["store"],
                         "toplam_adet": g["toplam_adet"], "items": g["items"]})
    kayitlar.sort(key=lambda x: -x["toplam_adet"])
    return jsonify({"kayitlar": kayitlar[:300], "coklu": s["coklu"],
                    "tekil": s["tekil"], "toplam_siparis": s["toplam_siparis"]})


@urun_bp.route("/api/urun/ogret", methods=["POST"])
def urun_ogret():
    """Bilinmeyen SKU'yu bir kategoriye öğret (urun_mapping.json'a yazılır,
    sonraki sınıflandırmalarda otomatik kullanılır)."""
    veri = request.get_json(silent=True) or {}
    eslesmeler = veri.get("eslesmeler") or {}
    if not isinstance(eslesmeler, dict) or not eslesmeler:
        return _hata("Geçersiz veya boş eşleştirme.")
    urun_eslestirme.kaydet(eslesmeler)
    # Kalem'i yeni sözlükle yeniden sınıflandır
    a = DURUM["analiz"]
    if a and DURUM["kalem_yolu"]:
        a["kalem"] = urun_eslestirme.kalem_isle(
            DURUM["kalem_yolu"], a["ay"], a["yil"])
    return jsonify({"tamam": True, "ogretilen": len(eslesmeler)})


@urun_bp.route("/api/urun/ogretilecekler", methods=["POST"])
def urun_ogretilecekler():
    """Öğretme kuyruğu: keyword motorunun çözemediği SKU'lar + her biri için
    öğrenen modelden (oneri) akıllı kategori önerisi. Ekip tek tıkla onaylar;
    onay urun_mapping.json'a /api/urun/ogret ile yazılır. Korpus büyüdükçe
    öneriler iyileşir."""
    yol = DURUM.get("kalem_yolu")
    if not (yol and os.path.exists(yol)):
        return _hata("Öğretme kuyruğu için kalem detayı (Item Name'li export) "
                     "yükleyin.")
    try:
        katalog = sku_katalog.katalog_topla([yol])
    except shipstation_csv.CsvHata as e:
        return _hata(str(e))
    model = oneri.model_katalogdan(katalog)
    kuyruk = []
    for k in sku_katalog.ogretilecekler(katalog):
        if not k["sku"]:
            continue  # SKU'suz satır SKU sözlüğüne öğretilemez
        oneriler = oneri.oner(k["ornek_ad"], model, 3)
        kuyruk.append({
            "sku": k["sku"], "ad": k["ornek_ad"], "adet": k["adet"],
            "magaza_sayisi": len(k["magazalar"]),
            "oneriler": [{"kategori": c, "skor": s} for c, s in oneriler],
        })
    return jsonify({
        "kuyruk": kuyruk[:300],
        "ozet": sku_katalog.ozet(katalog),
        "kategoriler": urun_eslestirme.KATEGORILER,
    })
