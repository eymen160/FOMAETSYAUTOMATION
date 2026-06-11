# Lazer Grubu ay sonu raporu otomasyonu — Flask uygulaması
# Çalıştırma: python app.py  →  http://127.0.0.1:5000
import glob
import os
import traceback

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file

from lazer import denetim, eslestirme, master, rapor, shipstation_api, shipstation_csv
from lazer.yardimci import AYLAR, ay_no, tr_kucuk

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

YUKLEME_KLASORU = "yuklenen"
CIKTI_KLASORU = "cikti"
os.makedirs(YUKLEME_KLASORU, exist_ok=True)
os.makedirs(CIKTI_KLASORU, exist_ok=True)

# Tek kullanıcılı lokal uygulama: durum bellekte tutulur
DURUM = {
    "master_yolu": None,
    "orders_yolu": None,
    "shipments_yolu": None,
    "maliyet_csv_yolu": None,
    "analiz": None,        # son analiz sonucu (ay, yıl, kayıtlar, ss verisi…)
    "kargo": None,         # API/CSV'den mağaza bazında kargo maliyeti
    "son_rapor": None,
}


def _hata(mesaj, kod=400):
    return jsonify({"hata": mesaj}), kod


def _master_bul():
    if DURUM["master_yolu"] and os.path.exists(DURUM["master_yolu"]):
        return DURUM["master_yolu"]
    adaylar = [y for y in glob.glob("*.xlsx")
               if not os.path.basename(y).startswith(("Lazer_Grubu_Rapor", "~$"))]
    return adaylar[0] if adaylar else None


def _orders_bul():
    if DURUM["orders_yolu"] and os.path.exists(DURUM["orders_yolu"]):
        return DURUM["orders_yolu"]
    return None


def _shipments_bul():
    if DURUM["shipments_yolu"] and os.path.exists(DURUM["shipments_yolu"]):
        return DURUM["shipments_yolu"]
    return None


def _csv_otomatik_tani():
    """Klasördeki CSV'leri içeriğine göre orders/shipments olarak tanı."""
    for yol in glob.glob("*.csv"):
        try:
            satirlar = shipstation_csv._csv_oku(yol)
        except shipstation_csv.CsvHata:
            continue
        basliklar = set(satirlar[0].keys())
        if "Order Total" in basliklar and DURUM["orders_yolu"] is None:
            DURUM["orders_yolu"] = yol
        elif "Shipment #" in basliklar and "Order Total" not in basliklar \
                and DURUM["shipments_yolu"] is None:
            DURUM["shipments_yolu"] = yol


@app.route("/")
def anasayfa():
    return render_template("index.html")


@app.route("/api/durum")
def durum():
    _csv_otomatik_tani()
    m = _master_bul()
    donem_listesi = []
    if m:
        try:
            df, kmap = master.master_oku(m)
            donem_listesi = [{"donem": d, "yil": y} for d, y in master.donemler(df, kmap)]
        except master.MasterHata as e:
            return jsonify({"master": m, "master_hata": str(e)})
    return jsonify({
        "master": m,
        "orders": _orders_bul(),
        "shipments": _shipments_bul(),
        "maliyet_csv": DURUM["maliyet_csv_yolu"],
        "api_anahtari_var": bool(os.environ.get("SHIPSTATION_API_KEY")),
        "donemler": donem_listesi,
        "aylar": AYLAR,
        "kargo_hazir": DURUM["kargo"] is not None,
    })


@app.route("/api/yukle/<tip>", methods=["POST"])
def yukle(tip):
    if tip not in ("master", "orders", "shipments", "maliyet"):
        return _hata("Bilinmeyen dosya tipi.")
    f = request.files.get("dosya")
    if not f or not f.filename:
        return _hata("Dosya seçilmedi.")
    uzanti = os.path.splitext(f.filename)[1].lower()
    if tip == "master" and uzanti != ".xlsx":
        return _hata("Master dosyası .xlsx olmalı.")
    if tip != "master" and uzanti != ".csv":
        return _hata("Bu alana .csv dosyası yükleyin.")
    yol = os.path.join(YUKLEME_KLASORU, f"{tip}{uzanti}")
    f.save(yol)
    # İçerik doğrulaması
    try:
        if tip == "master":
            master.master_oku(yol)
            DURUM["master_yolu"] = yol
        elif tip == "orders":
            shipstation_csv.orders_dogrula(yol)
            DURUM["orders_yolu"] = yol
        elif tip == "shipments":
            shipstation_csv.shipments_isle(yol)
            DURUM["shipments_yolu"] = yol
        else:
            DURUM["maliyet_csv_yolu"] = yol
    except (master.MasterHata, shipstation_csv.CsvHata) as e:
        return _hata(str(e))
    DURUM["analiz"] = None  # veri değişti, analiz bayatladı
    return jsonify({"tamam": True, "yol": yol})


@app.route("/api/analiz", methods=["POST"])
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

    m_yol = _master_bul()
    if not m_yol:
        return _hata("Master Excel bulunamadı. Lütfen dosyayı yükleyin.")
    try:
        df, kmap = master.master_oku(m_yol)
        kayitlar, bozuk, form_uyarilari = master.ay_kayitlari(df, kmap, ay_adi, yil)
    except master.MasterHata as e:
        return _hata(str(e))
    if not kayitlar:
        return _hata(f"Master'da {ay_adi} {yil} dönemi için form yanıtı bulunamadı.")

    _csv_otomatik_tani()
    uyarilar = list(form_uyarilari)
    orders_sonuc, shipments_sonuc = None, None
    o_yol, s_yol = _orders_bul(), _shipments_bul()
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
    else:
        uyarilar.append("Orders CSV yüklenmedi: ShipStation gelir verisi "
                        "(Ciro/Vergi/Kargo Müşteri/Parça Adedi) hesaplanamayacak.")
    if s_yol:
        try:
            shipments_sonuc = shipstation_csv.shipments_isle(s_yol, ay, yil)
            if shipments_sonuc["coklu_store"]:
                uyarilar.append(
                    "Shipments CSV'de aynı Order # birden fazla Store ile görünüyor: "
                    + ", ".join(shipments_sonuc["coklu_store"][:20]))
        except shipstation_csv.CsvHata as e:
            uyarilar.append(f"Shipments CSV işlenemedi: {e}")

    # Mağaza eşleştirme önerileri
    ss_adlari = set()
    if orders_sonuc:
        ss_adlari |= set(orders_sonuc["magazalar"].keys())
    if shipments_sonuc:
        ss_adlari |= set(shipments_sonuc["gonderi_sayisi"].keys())
    master_adlari = [k["magaza"] for k in kayitlar]
    mevcut_eslesme = eslestirme.yukle()
    oneriler = eslestirme.oneri_uret(ss_adlari, master_adlari, mevcut_eslesme)

    DURUM["analiz"] = {
        "ay": ay, "ay_adi": ay_adi.capitalize(), "yil": yil,
        "kayitlar": kayitlar, "bozuk": bozuk,
        "orders": orders_sonuc, "shipments": shipments_sonuc,
        "master_yolu": m_yol,
    }
    return jsonify({
        "ay": ay_adi.capitalize(), "yil": yil,
        "form_magaza_sayisi": len(kayitlar),
        "magazalar": master_adlari,
        "bozuk_satirlar": bozuk,
        "uyarilar": uyarilar,
        "eslestirme": oneriler,
        "iptal_iade": orders_sonuc["iptal_iade"] if orders_sonuc else [],
        "kapsama": orders_sonuc["kapsama"] if orders_sonuc else None,
        "orders_var": orders_sonuc is not None,
        "shipments_var": shipments_sonuc is not None,
    })


@app.route("/api/eslestirme/kaydet", methods=["POST"])
def eslestirme_kaydet():
    veri = request.get_json(silent=True) or {}
    eslesmeler = veri.get("eslesmeler") or {}
    if not isinstance(eslesmeler, dict):
        return _hata("Geçersiz eşleştirme verisi.")
    eslestirme.kaydet(eslesmeler)
    return jsonify({"tamam": True, "kayitli": len(eslesmeler)})


def _ss_master_bazinda():
    """Orders + kargo verisini master mağaza adına çevirip birleştirir."""
    a = DURUM["analiz"]
    eslesme = eslestirme.yukle()
    ss_veri = {}
    amazon = {}
    eslesmeyen_ss = []
    if a.get("orders"):
        for ss_ad, v in a["orders"]["magazalar"].items():
            hedef = eslesme.get(ss_ad.strip())
            if hedef is None and shipstation_csv.amazon_mu(ss_ad):
                hedef = eslestirme.AMAZON_ETIKETI
            if hedef == eslestirme.AMAZON_ETIKETI:
                am = amazon.setdefault(ss_ad.strip(), {"siparis": 0, "kargo": 0.0})
                am["siparis"] += v["siparis_sayisi"]
                continue
            if hedef is None or hedef == "-":
                eslesmeyen_ss.append(ss_ad.strip())
                continue
            h = ss_veri.setdefault(hedef, {
                "ciro_order_total": 0.0, "ciro_amount_paid": 0.0, "vergi": 0.0,
                "kargo_musteri": 0.0, "adet": 0.0, "kargo_api": None})
            for alan in ("ciro_order_total", "ciro_amount_paid", "vergi",
                         "kargo_musteri", "adet"):
                h[alan] += v[alan]
    if DURUM["kargo"]:
        for ss_ad, tutar in DURUM["kargo"]["magaza_kargo"].items():
            hedef = eslesme.get(ss_ad.strip())
            if hedef is None and shipstation_csv.amazon_mu(ss_ad):
                hedef = eslestirme.AMAZON_ETIKETI
            if hedef == eslestirme.AMAZON_ETIKETI:
                am = amazon.setdefault(ss_ad.strip(), {"siparis": 0, "kargo": 0.0})
                am["kargo"] += tutar
                continue
            if hedef is None or hedef == "-":
                continue
            h = ss_veri.setdefault(hedef, {
                "ciro_order_total": 0.0, "ciro_amount_paid": 0.0, "vergi": 0.0,
                "kargo_musteri": 0.0, "adet": 0.0, "kargo_api": None})
            h["kargo_api"] = (h["kargo_api"] or 0.0) + tutar
    # Amazon gönderi sayıları (shipments CSV'den, sipariş sayısı yoksa)
    if a.get("shipments"):
        for ss_ad, adet in a["shipments"]["gonderi_sayisi"].items():
            if shipstation_csv.amazon_mu(ss_ad):
                am = amazon.setdefault(ss_ad.strip(), {"siparis": 0, "kargo": 0.0})
                am["siparis"] = max(am["siparis"], adet)
    amazon_liste = [{"magaza": k, **v} for k, v in sorted(amazon.items())]
    return ss_veri, amazon_liste, sorted(set(eslesmeyen_ss))


@app.route("/api/kargo/api", methods=["POST"])
def kargo_api():
    a = DURUM["analiz"]
    if not a:
        return _hata("Önce analiz çalıştırın (ay + yıl seçip Analiz Et).")
    veri = request.get_json(silent=True) or {}
    yenile = bool(veri.get("yenile"))
    order_store = {}
    if a.get("shipments"):
        order_store.update(a["shipments"]["order_store"])
    # Orders CSV'deki Order# → Store da eşleşmeye katkı verir
    try:
        api = shipstation_api.ShipStationV2(os.environ.get("SHIPSTATION_API_KEY"))
        sonuc = shipstation_api.kargo_maliyeti_hesapla(
            api, a["yil"], a["ay"], order_store, yenile=yenile)
    except shipstation_api.ApiHata as e:
        return _hata(str(e), 502)
    DURUM["kargo"] = sonuc
    return jsonify({"tamam": True, "kaynak": "api", **sonuc})


@app.route("/api/kargo/test", methods=["POST"])
def kargo_test():
    try:
        api = shipstation_api.ShipStationV2(os.environ.get("SHIPSTATION_API_KEY"))
        return jsonify(api.baglanti_testi())
    except shipstation_api.ApiHata as e:
        return _hata(str(e), 502)


@app.route("/api/kargo/csv", methods=["POST"])
def kargo_csv():
    a = DURUM["analiz"]
    if not a:
        return _hata("Önce analiz çalıştırın.")
    yol = DURUM["maliyet_csv_yolu"]
    if not yol or not os.path.exists(yol):
        return _hata("Önce maliyet CSV'sini yükleyin (Cost/Shipment Cost kolonlu rapor).")
    order_store = a["shipments"]["order_store"] if a.get("shipments") else {}
    try:
        sonuc = shipstation_csv.maliyet_csv_isle(yol, order_store, a["ay"], a["yil"])
    except shipstation_csv.CsvHata as e:
        return _hata(str(e))
    DURUM["kargo"] = {"magaza_kargo": sonuc["magaza_kargo"],
                      "eslesmeyen": sonuc["eslesmeyen"], "voided": 0,
                      "label_sayisi": None, "bilinmeyen_store_idler": {}}
    return jsonify({"tamam": True, "kaynak": "csv", **sonuc})


@app.route("/api/denetim", methods=["POST"])
def denetim_gor():
    a = DURUM["analiz"]
    if not a:
        return _hata("Önce analiz çalıştırın.")
    veri = request.get_json(silent=True) or {}
    ciro_kaynagi = veri.get("ciro_kaynagi") or "order_total"
    ss_veri, amazon_liste, eslesmeyen_ss = _ss_master_bazinda()
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
        "kargo_hazir": DURUM["kargo"] is not None,
    })


@app.route("/api/rapor", methods=["POST"])
def rapor_uret_endpoint():
    a = DURUM["analiz"]
    if not a:
        return _hata("Önce analiz çalıştırın.")
    veri = request.get_json(silent=True) or {}
    kaynaklar = veri.get("kaynaklar") or {}
    ciro_kaynagi = veri.get("ciro_kaynagi") or "order_total"
    ss_veri, amazon_liste, _ = _ss_master_bazinda()

    satirlar = []
    for kayit in sorted(a["kayitlar"], key=lambda k: tr_kucuk(k["magaza"])):
        ss = ss_veri.get(kayit["magaza"]) or {}
        ss_degerler = {
            "ciro": ss.get("ciro_amount_paid" if ciro_kaynagi == "amount_paid"
                           else "ciro_order_total"),
            "vergi": ss.get("vergi"),
            "kargo_musteri": ss.get("kargo_musteri"),
            "adet": ss.get("adet"),
            "kargo": ss.get("kargo_api"),
        }
        satir = {"magaza": kayit["magaza"],
                 "reklam": kayit["reklam"],            # her zaman formdan
                 "ilave_odeme": kayit["ek_odeme"],     # her zaman formdan
                 "upgrade": kayit["upgrade"]}
        for alan in ("ciro", "vergi", "kargo_musteri", "kargo", "adet"):
            secim = kaynaklar.get(alan, "shipstation")
            ss_d = ss_degerler.get(alan)
            satir[alan] = kayit[alan] if (secim == "form" or ss_d is None) else ss_d
        satir["adet"] = int(round(satir["adet"] or 0))
        satirlar.append(satir)

    eslesmeyen = DURUM["kargo"]["eslesmeyen"] if DURUM["kargo"] else None
    dosya_adi = f"Lazer_Grubu_Rapor_{a['yil']}_{a['ay_adi'].upper()}.xlsx"
    yol = os.path.join(CIKTI_KLASORU, dosya_adi)
    try:
        rapor.rapor_uret(yol, a["ay_adi"], a["yil"], satirlar,
                         amazon_satirlari=amazon_liste,
                         eslesmeyen_maliyet=eslesmeyen)
    except PermissionError:
        return _hata(f"'{dosya_adi}' başka bir programda açık görünüyor; "
                     "kapatıp tekrar deneyin.")
    DURUM["son_rapor"] = yol
    return jsonify({"tamam": True, "dosya": dosya_adi})


@app.route("/api/rapor/indir")
def rapor_indir():
    yol = DURUM.get("son_rapor")
    if not yol or not os.path.exists(yol):
        return _hata("Henüz rapor üretilmedi.", 404)
    return send_file(os.path.abspath(yol), as_attachment=True,
                     download_name=os.path.basename(yol))


@app.errorhandler(Exception)
def genel_hata(e):
    # Stack trace kullanıcıya gösterilmez; terminale yazılır
    traceback.print_exc()
    return _hata("Beklenmeyen bir hata oluştu. Ayrıntı için terminali kontrol edin.", 500)


if __name__ == "__main__":
    print("Lazer Grubu Rapor Otomasyonu → http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
