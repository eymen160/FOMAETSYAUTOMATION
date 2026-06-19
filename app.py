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
DEMO_KLASORU = "demo"
DEMO_MASTER = os.path.join(DEMO_KLASORU, "demo_master_form.xlsx")
DEMO_OZET = os.path.join(DEMO_KLASORU, "demo_siparis_ozeti.csv")
DEMO_ESLESTIRME = os.path.join(DEMO_KLASORU, "store_mapping.json")
DEMO_AY, DEMO_YIL = "Mayıs", 2026
os.makedirs(YUKLEME_KLASORU, exist_ok=True)
os.makedirs(CIKTI_KLASORU, exist_ok=True)

# Tek kullanıcılı lokal uygulama: durum bellekte tutulur
DURUM = {
    "master_yolu": None,
    "orders_yolu": None,
    "ozet_yolu": None,     # sipariş özeti raporu (maliyet dahil, sipariş bazlı)
    "shipments_yolu": None,
    "maliyet_csv_yolu": None,
    "analiz": None,        # son analiz sonucu (ay, yıl, kayıtlar, ss verisi…)
    "kargo": None,         # API/CSV'den mağaza bazında kargo maliyeti
    "son_rapor": None,
    "eslestirme_yolu": eslestirme.ESLESTIRME_DOSYASI,
    "demo": False,
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
    if DURUM["demo"]:
        return  # demo modunda yalnızca paketlenmiş demo verisi kullanılır
    for yol in glob.glob("*.csv"):
        try:
            satirlar = shipstation_csv._csv_oku(yol)
        except shipstation_csv.CsvHata:
            continue
        basliklar = set(satirlar[0].keys())
        if "Amount - Order Total" in basliklar and DURUM["ozet_yolu"] is None:
            DURUM["ozet_yolu"] = yol
        elif "Order Total" in basliklar and DURUM["orders_yolu"] is None:
            DURUM["orders_yolu"] = yol
        elif "Shipment #" in basliklar and "Order Total" not in basliklar \
                and DURUM["shipments_yolu"] is None:
            DURUM["shipments_yolu"] = yol


@app.route("/")
def anasayfa():
    return render_template("index.html")


@app.route("/api/demo", methods=["POST"])
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
        "orders_yolu": None, "shipments_yolu": None, "maliyet_csv_yolu": None,
        "kargo": None, "analiz": None, "son_rapor": None,
        "eslestirme_yolu": DEMO_ESLESTIRME if os.path.exists(DEMO_ESLESTIRME)
        else eslestirme.ESLESTIRME_DOSYASI,
        "demo": True,
    })
    return jsonify({"tamam": True, "ay": DEMO_AY, "yil": DEMO_YIL,
                    "master": DEMO_MASTER, "ozet": DEMO_OZET})


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
        "orders": _orders_bul() or DURUM["ozet_yolu"],
        "shipments": _shipments_bul(),
        "maliyet_csv": DURUM["maliyet_csv_yolu"],
        "api_anahtari_var": bool(os.environ.get("SHIPSTATION_API_KEY")),
        "donemler": donem_listesi,
        "aylar": AYLAR,
        "kargo_hazir": DURUM["kargo"] is not None,
        "demo": DURUM["demo"],
        "demo_var": os.path.exists(DEMO_MASTER) and os.path.exists(DEMO_OZET),
        "demo_ay": DEMO_AY, "demo_yil": DEMO_YIL,
    })


@app.route("/api/yukle/<tip>", methods=["POST"])
def yukle(tip):
    if tip not in ("master", "orders", "shipments", "maliyet"):
        return _hata("Bilinmeyen dosya tipi.")
    f = request.files.get("dosya")
    if not f or not f.filename:
        return _hata("Dosya seçilmedi.")
    if DURUM["demo"]:  # elle dosya yükleme demo modundan çıkar
        DURUM["demo"] = False
        DURUM["eslestirme_yolu"] = eslestirme.ESLESTIRME_DOSYASI
        DURUM["ozet_yolu"] = None
        DURUM["master_yolu"] = None
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
        urun_basliklari, urun_adetleri = master.urun_adetleri(df, kmap, ay_adi, yil)
    except master.MasterHata as e:
        return _hata(str(e))
    if not kayitlar:
        return _hata(f"Master'da {ay_adi} {yil} dönemi için form yanıtı bulunamadı.")

    _csv_otomatik_tani()
    uyarilar = list(form_uyarilari)
    orders_sonuc, shipments_sonuc, ozet_sonuc = None, None, None
    o_yol, s_yol = _orders_bul(), _shipments_bul()
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

    # Mağaza eşleştirme önerileri
    ss_adlari = set()
    if orders_sonuc:
        ss_adlari |= set(orders_sonuc["magazalar"].keys())
    if ozet_sonuc:
        ss_adlari |= set(ozet_sonuc["magazalar"].keys())
    if shipments_sonuc:
        ss_adlari |= set(shipments_sonuc["gonderi_sayisi"].keys())
    master_adlari = [k["magaza"] for k in kayitlar]
    mevcut_eslesme = eslestirme.yukle(DURUM["eslestirme_yolu"])
    oneriler = eslestirme.oneri_uret(ss_adlari, master_adlari, mevcut_eslesme)

    DURUM["analiz"] = {
        "ay": ay, "ay_adi": ay_adi.capitalize(), "yil": yil,
        "kayitlar": kayitlar, "bozuk": bozuk,
        "orders": orders_sonuc, "shipments": shipments_sonuc,
        "ozet": ozet_sonuc,
        "urun_basliklari": urun_basliklari,
        "urun_adetleri": urun_adetleri,
        "master_yolu": m_yol,
    }
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
    })


@app.route("/api/eslestirme/kaydet", methods=["POST"])
def eslestirme_kaydet():
    veri = request.get_json(silent=True) or {}
    eslesmeler = veri.get("eslesmeler") or {}
    if not isinstance(eslesmeler, dict):
        return _hata("Geçersiz eşleştirme verisi.")
    eslestirme.kaydet(eslesmeler, DURUM["eslestirme_yolu"])
    return jsonify({"tamam": True, "kayitli": len(eslesmeler)})


def _ss_master_bazinda():
    """ShipStation verilerini master mağaza adına çevirip birleştirir.

    Öncelik: gelir + kargo maliyeti sipariş özeti raporundan; PARÇA ADEDİ
    item bazlı Orders CSV'sinden; kargo maliyeti özet yoksa API/CSV'den."""
    a = DURUM["analiz"]
    eslesme = eslestirme.yukle(DURUM["eslestirme_yolu"])
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

    ozet = a.get("ozet")
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
    if a.get("orders"):
        for ss_ad, v in a["orders"]["magazalar"].items():
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
    if DURUM["kargo"] and not ozet:
        for ss_ad, tutar in DURUM["kargo"]["magaza_kargo"].items():
            hedef = hedef_bul(ss_ad)
            if hedef == eslestirme.AMAZON_ETIKETI:
                am = amazon.setdefault(ss_ad.strip(), {"siparis": 0, "kargo": 0.0})
                am["kargo"] += tutar
                continue
            if hedef is None or hedef == "-":
                continue
            ekle(hucre(hedef), "kargo_api", tutar)
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
    ciro_kaynagi = veri.get("ciro_kaynagi") or (
        "subtotal_shipping" if a.get("ozet") else "order_total")
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
        "kargo_hazir": DURUM["kargo"] is not None or a.get("ozet") is not None,
    })


def _kaynak_varsayilan(a):
    return "subtotal_shipping" if a.get("ozet") else "order_total"


def _rapor_satirlari(kaynaklar, ciro_kaynagi):
    """Rapor + ekran tablosu için ortak satır üretimi. Kaynak seçimini ve
    ürün adetlerini (form beyanından) uygular. Dönüş: (satirlar, ss_veri,
    amazon_liste, urun_basliklari, kaynak_kullanim)."""
    a = DURUM["analiz"]
    ss_veri, amazon_liste, _ = _ss_master_bazinda()
    urun_basliklari = a.get("urun_basliklari") or []
    urun_map = a.get("urun_adetleri") or {}
    kaynak_kullanim = {}
    satirlar = []
    for kayit in sorted(a["kayitlar"], key=lambda k: tr_kucuk(k["magaza"])):
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


@app.route("/api/rapor", methods=["POST"])
def rapor_uret_endpoint():
    a = DURUM["analiz"]
    if not a:
        return _hata("Önce analiz çalıştırın.")
    veri = request.get_json(silent=True) or {}
    kaynaklar = veri.get("kaynaklar") or {}
    ciro_kaynagi = veri.get("ciro_kaynagi") or _kaynak_varsayilan(a)
    satirlar, _, amazon_liste, urun_basliklari, _ = _rapor_satirlari(
        kaynaklar, ciro_kaynagi)

    eslesmeyen = DURUM["kargo"]["eslesmeyen"] if DURUM["kargo"] else None
    dosya_adi = f"Lazer_Grubu_Rapor_{a['yil']}_{a['ay_adi'].upper()}.xlsx"
    yol = os.path.join(CIKTI_KLASORU, dosya_adi)
    try:
        rapor.rapor_uret(yol, a["ay_adi"], a["yil"], satirlar,
                         amazon_satirlari=amazon_liste,
                         eslesmeyen_maliyet=eslesmeyen,
                         urun_basliklari=urun_basliklari)
    except PermissionError:
        return _hata(f"'{dosya_adi}' başka bir programda açık görünüyor; "
                     "kapatıp tekrar deneyin.")
    DURUM["son_rapor"] = yol
    return jsonify({"tamam": True, "dosya": dosya_adi})


@app.route("/api/sonuc", methods=["POST"])
def sonuc():
    """Ekran için: nihai rapor tablosu (A→Q sayısal) + CEO özet kartları."""
    a = DURUM["analiz"]
    if not a:
        return _hata("Önce analiz çalıştırın.")
    veri = request.get_json(silent=True) or {}
    kaynaklar = veri.get("kaynaklar") or {}
    ciro_kaynagi = veri.get("ciro_kaynagi") or _kaynak_varsayilan(a)
    satirlar, ss_veri, amazon_liste, urun_basliklari, kaynak_kullanim = \
        _rapor_satirlari(kaynaklar, ciro_kaynagi)

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
    eslesen = len([s for s in tablo if (ss_veri.get(s["magaza"]) or {})])
    toplam_magaza = len(tablo)
    # Otomatik (ShipStation'dan) vs manuel (formdan) kolon sayısı
    finansal_alanlar = ["ciro", "vergi", "kargo_musteri", "kargo", "adet"]
    oto = sum(1 for f in finansal_alanlar if kaynak_kullanim.get(f) == "shipstation")
    manuel = len(finansal_alanlar) - oto + 2  # +REKLAM +İLAVE ÖDEME (hep form)
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
