# Rapor uç noktaları: Excel rapor üretimi, ekran tablosu/CEO özeti ve indirme.
import os

from flask import Blueprint, jsonify, request, send_file

import config
import durum as durum_state
from durum import DURUM
from lazer import rapor, shipstation_csv, urun_eslestirme
from web.ortak import hata as _hata

rapor_bp = Blueprint("rapor", __name__)


@rapor_bp.route("/api/rapor", methods=["POST"])
def rapor_uret_endpoint():
    a = DURUM["analiz"]
    if not a:
        return _hata("Önce analiz çalıştırın.")
    veri = request.get_json(silent=True) or {}
    kaynaklar = veri.get("kaynaklar") or {}
    ciro_kaynagi = veri.get("ciro_kaynagi") or durum_state.kaynak_varsayilan(a)
    urun_kaynagi = veri.get("urun_kaynagi") or "form"
    satirlar, _, amazon_liste, urun_basliklari, _ = durum_state.rapor_satirlari(
        kaynaklar, ciro_kaynagi, urun_kaynagi)

    eslesmeyen = DURUM["kargo"]["eslesmeyen"] if DURUM["kargo"] else None
    # Çok-ürünlü sipariş içerikleri (kalem detayı varsa) → Excel 2. sayfa
    siparis_icerik = None
    if DURUM["kalem_yolu"] and os.path.exists(DURUM["kalem_yolu"]):
        try:
            siparis_icerik = urun_eslestirme.siparis_icerikleri(
                DURUM["kalem_yolu"], a["ay"], a["yil"])["icerik"]
        except shipstation_csv.CsvHata:
            siparis_icerik = None
    dosya_adi = f"Lazer_Grubu_Rapor_{a['yil']}_{a['ay_adi'].upper()}.xlsx"
    yol = os.path.join(config.CIKTI_KLASORU, dosya_adi)
    try:
        rapor.rapor_uret(yol, a["ay_adi"], a["yil"], satirlar,
                         amazon_satirlari=amazon_liste,
                         eslesmeyen_maliyet=eslesmeyen,
                         urun_basliklari=urun_basliklari,
                         siparis_icerik=siparis_icerik)
    except PermissionError:
        return _hata(f"'{dosya_adi}' başka bir programda açık görünüyor; "
                     "kapatıp tekrar deneyin.")
    DURUM["son_rapor"] = yol
    return jsonify({"tamam": True, "dosya": dosya_adi})


@rapor_bp.route("/api/sonuc", methods=["POST"])
def sonuc():
    """Ekran için: nihai rapor tablosu (A→Q sayısal) + CEO özet kartları."""
    a = DURUM["analiz"]
    if not a:
        return _hata("Önce analiz çalıştırın.")
    veri = request.get_json(silent=True) or {}
    kaynaklar = veri.get("kaynaklar") or {}
    ciro_kaynagi = veri.get("ciro_kaynagi") or durum_state.kaynak_varsayilan(a)
    urun_kaynagi = veri.get("urun_kaynagi") or "form"
    satirlar, ss_veri, amazon_liste, urun_basliklari, kaynak_kullanim = \
        durum_state.rapor_satirlari(kaynaklar, ciro_kaynagi, urun_kaynagi)

    # Ekran tablosu: finansal kolonları sayısal hesapla (Excel ile birebir)
    tablo, toplam = [], {"ciro": 0.0, "vergi": 0.0, "reklam": 0.0,
                         "kargo_musteri": 0.0, "kargo": 0.0, "adet": 0,
                         "ilave_odeme": 0.0, "kalan": 0.0, "upgrade": 0}
    for s in satirlar:
        ciro = s["ciro"] or 0.0
        adet = s["adet"] or 0
        kalan = ciro - (s["vergi"] or 0) - (s["reklam"] or 0) - (s["kargo"] or 0)
        satir = {
            "magaza": s["magaza"], "ciro": ciro,
            "pb_ciro": ciro / adet if adet else None,
            "vergi": s["vergi"] or 0, "reklam": s["reklam"] or 0,
            "kargo_musteri": s["kargo_musteri"] or 0,
            "kargo_pb_odenen": (s["kargo_musteri"] or 0) / adet if adet else None,
            "kargo_pb_kalan": ((s["kargo_musteri"] or 0) - (s["kargo"] or 0)) / adet if adet else None,
            "kargo": s["kargo"] or 0, "adet": adet,
            "ilave_odeme": s["ilave_odeme"] or 0, "kalan": kalan,
            "yuzde_reklam": (s["reklam"] or 0) / ciro if ciro else None,
            "yuzde_vergi": (s["vergi"] or 0) / ciro if ciro else None,
            "pb_kalan": kalan / adet if adet else None,
            "upgrade": s["upgrade"] or 0,
        }
        tablo.append(satir)
        for k in ("ciro", "vergi", "reklam", "kargo_musteri", "kargo",
                  "ilave_odeme", "upgrade"):
            toplam[k] += s[k] or 0
        toplam["adet"] += adet
        toplam["kalan"] += kalan

    # CEO özet kartları
    ozet = a.get("ozet")
    islenen_siparis = 0
    if ozet:
        islenen_siparis = sum(v["siparis_sayisi"] for v in ozet["magazalar"].values())
    toplam_magaza = len(tablo)
    if a.get("mod") == "formsuz":
        eslesen = toplam_magaza   # satırlar zaten ham veriden geliyor
    else:
        eslesen = len([s for s in tablo if (ss_veri.get(s["magaza"]) or {})])
    # Otomatik (ShipStation'dan) vs manuel kolon sayısı
    finansal_alanlar = ["ciro", "vergi", "kargo_musteri", "kargo", "adet"]
    oto = sum(1 for f in finansal_alanlar if kaynak_kullanim.get(f) == "shipstation")
    manuel = len(finansal_alanlar) - oto + 2  # +REKLAM +İLAVE ÖDEME
    ceo = {
        "islenen_siparis": islenen_siparis,
        "toplam_ciro": round(toplam["ciro"]),
        "toplam_kargo": round(toplam["kargo"]),
        "toplam_kalan": round(toplam["kalan"]),
        "eslesen_magaza": eslesen,
        "toplam_magaza": toplam_magaza,
        "match_rate": round(100 * eslesen / toplam_magaza) if toplam_magaza else 0,
        "otomatik_kolon": oto,
        "manuel_kolon": manuel,
        "amazon_siparis": sum(x.get("siparis", 0) for x in amazon_liste),
        "zaman_tasarrufu": "~20 saat/ay manuel iş → dakikalar",
    }
    return jsonify({
        "ay": a["ay_adi"], "yil": a["yil"],
        "tablo": tablo, "toplam": {**toplam,
            "yuzde_reklam": toplam["reklam"] / toplam["ciro"] if toplam["ciro"] else None,
            "yuzde_vergi": toplam["vergi"] / toplam["ciro"] if toplam["ciro"] else None},
        "ceo": ceo,
        "urun_basliklari": urun_basliklari,
        "amazon": amazon_liste,
    })


@rapor_bp.route("/api/rapor/indir")
def rapor_indir():
    yol = DURUM.get("son_rapor")
    if not yol or not os.path.exists(yol):
        return _hata("Henüz rapor üretilmedi.", 404)
    return send_file(os.path.abspath(yol), as_attachment=True,
                     download_name=os.path.basename(yol))
