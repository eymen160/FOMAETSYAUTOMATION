# Analiz uç noktaları: formlu (master beyanı) ve formsuz (ham veriden) mod,
# elle girdiler ve mağaza eşleştirme kaydı.
import os

from flask import Blueprint, jsonify, request

import durum as durum_state
from durum import DURUM
from lazer import eslestirme, formsuz, master, shipstation_csv, urun_eslestirme
from lazer.yardimci import ay_no
from web.ortak import hata as _hata

analiz_bp = Blueprint("analiz", __name__)


def _formsuz_analiz(ay, ay_adi, yil):
    """Formsuz mod: rapor satırlarını ShipStation ham verisinden üretir.
    Master/form gerektirmez; mağazalar verinin kendisinden gelir."""
    durum_state.csv_otomatik_tani()
    z_yol = DURUM["ozet_yolu"] if DURUM["ozet_yolu"] and os.path.exists(DURUM["ozet_yolu"]) else None
    if not z_yol:
        return _hata("Formsuz rapor için ShipStation sipariş özeti (Amount-Order "
                     "Total kolonlu) yükleyin.")
    uyarilar = []
    try:
        ozet_sonuc = shipstation_csv.ozet_isle(z_yol, ay, yil)
    except shipstation_csv.CsvHata as e:
        return _hata(str(e))
    if ozet_sonuc["ay_satir_sayisi"] == 0:
        return _hata(f"Sipariş özetinde {ay_adi} {yil} dönemine ait satır yok.")
    if ozet_sonuc["kapsama"].get("uyari"):
        uyarilar.append(ozet_sonuc["kapsama"]["uyari"])

    kalem_sonuc = None
    k_yol = DURUM["kalem_yolu"] if DURUM["kalem_yolu"] and os.path.exists(DURUM["kalem_yolu"]) else None
    if k_yol:
        try:
            kalem_sonuc = urun_eslestirme.kalem_isle(k_yol, ay, yil)
            kap = kalem_sonuc["kapsama"]
            uyarilar.append(f"Ürün sınıflandırma: {kap['toplam']} adetin "
                            f"%{kap['oran']*100:.0f}'i kategoriye eşlendi.")
        except shipstation_csv.CsvHata as e:
            uyarilar.append(f"Kalem detayı işlenemedi: {e}")
    else:
        uyarilar.append("Kalem detayı yok: ürün kolonları ve sipariş içeriği "
                        "boş kalır (Item Name'li export yükleyin).")

    eslesme = eslestirme.yukle(DURUM["eslestirme_yolu"])
    elle = formsuz.elle_yukle().get(formsuz.donem_anahtari(yil, ay), {})
    # Etsy zenginleştirme (komisyon/net/iade + reklam) — ShipStation ile
    # aynı döneme (ay/yıl) filtreli
    etsy_finansal, reklam_magaza, etsy_meta = durum_state.etsy_enrichment(ay, yil)
    if etsy_meta:
        uyarilar.append(
            f"Etsy birleştirme: {etsy_meta['eslesen']} sipariş eşleşti, "
            f"{etsy_meta['magaza_sayisi']} mağazaya komisyon/net işlendi"
            + (f"; {etsy_meta['iade_sayisi']} iade "
               f"(${etsy_meta['iade_toplam']:,.2f})"
               if etsy_meta['iade_sayisi'] else "")
            + (f"; reklam ${etsy_meta['reklam_toplam']:,.2f}"
               if etsy_meta['reklam_toplam'] else "") + ".")
    DURUM["mod"] = "formsuz"
    DURUM["analiz"] = {
        "ay": ay, "ay_adi": ay_adi.capitalize(), "yil": yil,
        "ozet": ozet_sonuc, "kalem": kalem_sonuc, "elle": elle,
        "etsy_finansal": etsy_finansal, "reklam_magaza": reklam_magaza,
        "etsy_meta": etsy_meta, "mod": "formsuz",
    }
    # Rapor satırlarını üret (mağaza listesi + Amazon)
    satirlar, amazon_liste, _ = formsuz.rapor_satirlari(
        ozet_sonuc, kalem_sonuc, elle, eslesme, "subtotal_shipping",
        etsy_finansal=etsy_finansal, reklam_magaza=reklam_magaza)
    magazalar = [s["magaza"] for s in satirlar]
    if not magazalar:
        uyarilar.append("Hiç (Amazon dışı) mağaza bulunamadı.")
    return jsonify({
        "mod": "formsuz", "ay": ay_adi.capitalize(), "yil": yil,
        "magazalar": magazalar,
        "magaza_sayisi": len(magazalar),
        "uyarilar": uyarilar,
        "iptal_iade": ozet_sonuc["iptal_iade"],
        "kapsama": ozet_sonuc["kapsama"],
        "amazon": amazon_liste,
        "kalem_var": kalem_sonuc is not None,
        "etsy": etsy_meta,
        "elle": elle,
        "elle_alanlar": formsuz.ELLE_ALANLAR,
    })


@analiz_bp.route("/api/formsuz/elle", methods=["POST"])
def formsuz_elle():
    """Reklam / İlave ödeme / Upgrade elle girdilerini kaydeder (dönem bazında)."""
    a = DURUM["analiz"]
    if not a or DURUM["mod"] != "formsuz":
        return _hata("Önce formsuz analiz çalıştırın.")
    veri = request.get_json(silent=True) or {}
    girdiler = veri.get("girdiler") or {}
    if not isinstance(girdiler, dict):
        return _hata("Geçersiz girdi.")
    dk = formsuz.donem_anahtari(a["yil"], a["ay"])
    formsuz.elle_kaydet(dk, girdiler)
    a["elle"] = formsuz.elle_yukle().get(dk, {})
    return jsonify({"tamam": True, "kayitli": len(girdiler)})


@analiz_bp.route("/api/analiz", methods=["POST"])
def analiz():
    veri = request.get_json(silent=True) or {}
    ay_adi = (veri.get("ay") or "").strip()
    ay = ay_no(ay_adi)
    try:
        yil = int(veri.get("yil"))
    except (TypeError, ValueError):
        return _hata("Geçerli bir yıl seçin.")
    if not ay:
        return _hata("Geçerli bir ay seçin (örn. Mayıs).")

    # Formsuz mod: master yok ya da kullanıcı 'ham veriden' seçti → rapor
    # doğrudan ShipStation verisinden üretilir.
    if veri.get("formsuz") or not durum_state.master_bul():
        return _formsuz_analiz(ay, ay_adi, yil)

    m_yol = durum_state.master_bul()
    if not m_yol:
        return _hata("Master Excel bulunamadı. Lütfen dosyayı yükleyin.")
    try:
        df, kmap = master.master_oku(m_yol)
        kayitlar, bozuk, form_uyarilari = master.ay_kayitlari(df, kmap, ay_adi, yil)
        urun_basliklari, urun_adetleri = master.urun_adetleri(df, kmap, ay_adi, yil)
    except master.MasterHata as e:
        return _hata(str(e))
    if not kayitlar:
        return _hata(f"Master'da {ay_adi} {yil} dönemi için form yanıtı bulunamadı.")

    durum_state.csv_otomatik_tani()
    uyarilar = list(form_uyarilari)
    orders_sonuc, shipments_sonuc, ozet_sonuc = None, None, None
    o_yol, s_yol = durum_state.orders_bul(), durum_state.shipments_bul()
    z_yol = DURUM["ozet_yolu"] if DURUM["ozet_yolu"] and os.path.exists(DURUM["ozet_yolu"]) else None
    if z_yol:
        try:
            ozet_sonuc = shipstation_csv.ozet_isle(z_yol, ay, yil)
            if ozet_sonuc["kapsama"].get("uyari"):
                uyarilar.append(ozet_sonuc["kapsama"]["uyari"])
            if ozet_sonuc["ay_satir_sayisi"] == 0:
                uyarilar.append(f"Sipariş özeti raporunda {ay_adi} {yil} dönemine "
                                "ait satır yok (tarih filtresini kontrol edin).")
            else:
                uyarilar.append(
                    "Sipariş özeti raporu kullanılıyor: Ciro/Kargo Müşteri/Kargo "
                    "maliyeti buradan hesaplanır. Bu raporda ürün adedi OLMADIĞI "
                    "için PARÇA ADEDİ form beyanından (veya item bazlı Orders "
                    "CSV'sinden) gelir. Form 'Vergi' beyanı Etsy kesintisidir; "
                    "ShipStation'daki Order Tax (pazar yeri satış vergisi) ile "
                    "birebir karşılaştırılamaz — VERGİ kolonu için kaynak olarak "
                    "'Form' önerilir.")
        except shipstation_csv.CsvHata as e:
            uyarilar.append(f"Sipariş özeti raporu işlenemedi: {e}")
    if o_yol:
        try:
            orders_sonuc = shipstation_csv.orders_isle(o_yol, ay, yil)
            if orders_sonuc["kapsama"].get("uyari"):
                uyarilar.append(orders_sonuc["kapsama"]["uyari"])
            if orders_sonuc["coklu_store"]:
                uyarilar.append(
                    "Aynı Order # birden fazla Store ile görünüyor (veri hatası): "
                    + ", ".join(orders_sonuc["coklu_store"][:20]))
            if orders_sonuc["ay_satir_sayisi"] == 0:
                uyarilar.append(
                    f"Orders CSV'de {ay_adi} {yil} dönemine ait satır yok "
                    "(tarih filtresini kontrol edin).")
        except shipstation_csv.CsvHata as e:
            uyarilar.append(f"Orders CSV işlenemedi: {e}")
    elif not ozet_sonuc:
        uyarilar.append("Orders CSV / sipariş özeti raporu yüklenmedi: ShipStation "
                        "gelir verisi (Ciro/Kargo Müşteri/Parça Adedi) hesaplanamayacak.")
    if s_yol:
        try:
            shipments_sonuc = shipstation_csv.shipments_isle(s_yol, ay, yil)
            if shipments_sonuc["coklu_store"]:
                uyarilar.append(
                    "Shipments CSV'de aynı Order # birden fazla Store ile görünüyor: "
                    + ", ".join(shipments_sonuc["coklu_store"][:20]))
        except shipstation_csv.CsvHata as e:
            uyarilar.append(f"Shipments CSV işlenemedi: {e}")

    # Ürün/SKU sınıflandırma (kalem-bazlı export'tan)
    kalem_sonuc = None
    k_yol = DURUM["kalem_yolu"] if DURUM["kalem_yolu"] and os.path.exists(DURUM["kalem_yolu"]) else None
    if k_yol:
        try:
            kalem_sonuc = urun_eslestirme.kalem_isle(k_yol, ay, yil)
            kap = kalem_sonuc["kapsama"]
            if kap["toplam"] == 0:
                uyarilar.append(f"Kalem detayında {ay_adi} {yil} dönemine ait satır "
                                "yok (tarih filtresini kontrol edin).")
            else:
                uyarilar.append(
                    f"Ürün/SKU sınıflandırma: {kap['toplam']} adetin "
                    f"%{kap['oran']*100:.0f}'i bilinen kategoriye eşlendi; "
                    "kalanı 'Diğer Ürün'. Bilinmeyen SKU'ları öğretebilirsiniz.")
        except shipstation_csv.CsvHata as e:
            uyarilar.append(f"Kalem detayı işlenemedi: {e}")

    # Mağaza eşleştirme önerileri
    ss_adlari = set()
    if orders_sonuc:
        ss_adlari |= set(orders_sonuc["magazalar"].keys())
    if ozet_sonuc:
        ss_adlari |= set(ozet_sonuc["magazalar"].keys())
    if shipments_sonuc:
        ss_adlari |= set(shipments_sonuc["gonderi_sayisi"].keys())
    if kalem_sonuc:
        ss_adlari |= set(kalem_sonuc["magaza_urun"].keys())
    master_adlari = [k["magaza"] for k in kayitlar]
    mevcut_eslesme = eslestirme.yukle(DURUM["eslestirme_yolu"])
    oneriler = eslestirme.oneri_uret(ss_adlari, master_adlari, mevcut_eslesme)

    DURUM["analiz"] = {
        "ay": ay, "ay_adi": ay_adi.capitalize(), "yil": yil,
        "kayitlar": kayitlar, "bozuk": bozuk,
        "orders": orders_sonuc, "shipments": shipments_sonuc,
        "ozet": ozet_sonuc, "kalem": kalem_sonuc,
        "urun_basliklari": urun_basliklari,
        "urun_adetleri": urun_adetleri,
        "master_yolu": m_yol, "mod": "form",
    }
    DURUM["mod"] = "form"
    iptal = list(orders_sonuc["iptal_iade"]) if orders_sonuc else []
    if ozet_sonuc:
        iptal += ozet_sonuc["iptal_iade"]
    return jsonify({
        "ay": ay_adi.capitalize(), "yil": yil,
        "form_magaza_sayisi": len(kayitlar),
        "magazalar": master_adlari,
        "bozuk_satirlar": bozuk,
        "uyarilar": uyarilar,
        "eslestirme": oneriler,
        "iptal_iade": iptal,
        "kapsama": (ozet_sonuc or orders_sonuc or {}).get("kapsama"),
        "orders_var": orders_sonuc is not None,
        "ozet_var": ozet_sonuc is not None,
        "shipments_var": shipments_sonuc is not None,
        "kalem_var": kalem_sonuc is not None,
    })


@analiz_bp.route("/api/eslestirme/kaydet", methods=["POST"])
def eslestirme_kaydet():
    veri = request.get_json(silent=True) or {}
    eslesmeler = veri.get("eslesmeler") or {}
    if not isinstance(eslesmeler, dict):
        return _hata("Geçersiz eşleştirme verisi.")
    eslestirme.kaydet(eslesmeler, DURUM["eslestirme_yolu"])
    return jsonify({"tamam": True, "kayitli": len(eslesmeler)})
