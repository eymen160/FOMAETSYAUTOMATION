# Yükleme + durum uç noktaları: ana sayfa, demo verisi, dosya yükleme (tekil
# ve içeriğe göre otomatik yönlendiren çoklu) ve genel durum sorgusu.
import os

from flask import Blueprint, jsonify, render_template, request
from werkzeug.utils import secure_filename

import config
import durum as durum_state
from config import (DEMO_AY, DEMO_ESLESTIRME, DEMO_KALEM, DEMO_KLASORU,
                    DEMO_MASTER, DEMO_OZET, DEMO_YIL)
from durum import DURUM
from lazer import dosya_tani, eslestirme, master, shipstation_csv, urun_eslestirme
from lazer.yardimci import AYLAR
from web.ortak import hata as _hata

yukleme_bp = Blueprint("yukleme", __name__)


@yukleme_bp.route("/")
def anasayfa():
    return render_template("index.html")


@yukleme_bp.route("/api/demo", methods=["POST"])
def demo_yukle():
    """Demo verisini tek tıkla yükler: paketlenmiş master + sipariş özeti +
    9 mağaza için hazır eşleştirme (FTM bilerek inceleme vakası)."""
    if not (os.path.exists(DEMO_MASTER) and os.path.exists(DEMO_OZET)):
        return _hata("Demo verisi bulunamadı. 'demo/' klasöründe "
                     "demo_master_form.xlsx ve demo_siparis_ozeti.csv olmalı.")
    # Eşleştirmeyi temiz baseline'a sıfırla (prova tekrarlanabilir olsun:
    # FTM her zaman inceleme vakası olarak başlar)
    baseline = os.path.join(DEMO_KLASORU, "store_mapping_baseline.json")
    if os.path.exists(baseline):
        import shutil
        shutil.copyfile(baseline, DEMO_ESLESTIRME)
    # Temiz başlangıç (önceki yüklemeler demo'yu etkilemesin)
    DURUM.update({
        "master_yolu": DEMO_MASTER, "ozet_yolu": DEMO_OZET,
        "kalem_yolu": DEMO_KALEM if os.path.exists(DEMO_KALEM) else None,
        "orders_yolu": None, "shipments_yolu": None, "maliyet_csv_yolu": None,
        "kargo": None, "analiz": None, "son_rapor": None,
        "eslestirme_yolu": DEMO_ESLESTIRME if os.path.exists(DEMO_ESLESTIRME)
        else eslestirme.ESLESTIRME_DOSYASI,
        "demo": True,
    })
    return jsonify({"tamam": True, "ay": DEMO_AY, "yil": DEMO_YIL,
                    "master": DEMO_MASTER, "ozet": DEMO_OZET})


@yukleme_bp.route("/api/durum")
def durum():
    durum_state.csv_otomatik_tani()
    m = durum_state.master_bul()
    donem_listesi = []
    if m:
        try:
            df, kmap = master.master_oku(m)
            donem_listesi = [{"donem": d, "yil": y} for d, y in master.donemler(df, kmap)]
        except master.MasterHata as e:
            return jsonify({"master": m, "master_hata": str(e)})
    return jsonify({
        "master": m,
        "orders": durum_state.orders_bul() or DURUM["ozet_yolu"],
        "kalem": DURUM["kalem_yolu"],
        "shipments": durum_state.shipments_bul(),
        "maliyet_csv": DURUM["maliyet_csv_yolu"],
        "api_anahtari_var": bool(os.environ.get("SHIPSTATION_API_KEY")),
        "donemler": donem_listesi,
        "aylar": AYLAR,
        "kargo_hazir": DURUM["kargo"] is not None,
        "demo": DURUM["demo"],
        "demo_var": os.path.exists(DEMO_MASTER) and os.path.exists(DEMO_OZET),
        "demo_ay": DEMO_AY, "demo_yil": DEMO_YIL,
        "yukleme": durum_state.yukleme_ozeti(),
    })


@yukleme_bp.route("/api/yukle/<tip>", methods=["POST"])
def yukle(tip):
    if tip not in ("master", "orders", "shipments", "maliyet", "kalem"):
        return _hata("Bilinmeyen dosya tipi.")
    f = request.files.get("dosya")
    if not f or not f.filename:
        return _hata("Dosya seçilmedi.")
    durum_state.demo_cik()  # elle dosya yükleme demo modundan çıkar
    uzanti = os.path.splitext(f.filename)[1].lower()
    if tip == "master" and uzanti != ".xlsx":
        return _hata("Master dosyası .xlsx olmalı.")
    if tip != "master" and uzanti != ".csv":
        return _hata("Bu alana .csv dosyası yükleyin.")
    yol = os.path.join(config.YUKLEME_KLASORU, f"{tip}{uzanti}")
    f.save(yol)
    # İçerik doğrulaması
    try:
        if tip == "master":
            master.master_oku(yol)
            DURUM["master_yolu"] = yol
        elif tip == "orders":
            # Orders alanı iki formatı da kabul eder: item bazlı Orders
            # export'u veya sipariş özeti raporu (maliyet kolonlu)
            if shipstation_csv.ozet_format_mu(yol):
                DURUM["ozet_yolu"] = yol
            else:
                shipstation_csv.orders_dogrula(yol)
                DURUM["orders_yolu"] = yol
        elif tip == "shipments":
            shipstation_csv.shipments_isle(yol)
            DURUM["shipments_yolu"] = yol
        elif tip == "kalem":
            if not urun_eslestirme.kalem_format_mu(yol):
                return _hata("Kalem detayı dosyası 'Store', 'Item Name' ve "
                             "'Quantity' kolonlarını içermeli.")
            DURUM["kalem_yolu"] = yol
        else:
            DURUM["maliyet_csv_yolu"] = yol
    except (master.MasterHata, shipstation_csv.CsvHata) as e:
        return _hata(str(e))
    DURUM["analiz"] = None  # veri değişti, analiz bayatladı
    return jsonify({"tamam": True, "yol": yol})


@yukleme_bp.route("/api/yukle_coklu", methods=["POST"])
def yukle_coklu():
    """Çoklu dosya yükleme: kullanıcı tüm dosyaları (ShipStation + Etsy, .csv
    ve master .xlsx) tek seferde bırakır; her dosya BAŞLIK satırından tanınıp
    doğru slota yönlendirilir. "Dosyaları bırak, uygulama eşleştirsin."

    Dönüş: her dosya için {dosya, tur, etiket, kabul} + slot bazında özet."""
    dosyalar = request.files.getlist("dosyalar")
    if not dosyalar:
        return _hata("Dosya seçilmedi.")
    durum_state.demo_cik()
    sonuc = []
    for f in dosyalar:
        if not f or not f.filename:
            continue
        ad = secure_filename(f.filename) or "dosya.csv"
        uzanti = os.path.splitext(ad)[1].lower()
        gecici = os.path.join(config.YUKLEME_KLASORU, f"_tmp_{ad}")
        f.save(gecici)
        try:
            if uzanti == ".xlsx":
                tur, kalici = durum_state.xlsx_yonlendir(gecici, ad)
            elif uzanti == ".csv":
                tur = dosya_tani.tani(gecici)
                kalici = durum_state.coklu_yonlendir(tur, gecici, ad)
            else:
                tur, kalici = "bilinmiyor", None
                if os.path.exists(gecici):
                    os.remove(gecici)
        except (master.MasterHata, shipstation_csv.CsvHata):
            tur, kalici = "bilinmiyor", None
            if os.path.exists(gecici):
                os.remove(gecici)
        sonuc.append({
            "dosya": f.filename,
            "tur": tur,
            "etiket": dosya_tani.ETIKET.get(tur, tur),
            "kabul": kalici is not None,
        })
    DURUM["analiz"] = None  # veri değişti, analiz bayatladı
    return jsonify({"dosyalar": sonuc, "ozet": durum_state.yukleme_ozeti()})
