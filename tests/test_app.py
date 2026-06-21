# Flask uç nokta testleri (öğretme kuyruğu + çoklu yükleme + oturum koruması).
import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import app as flask_app


@pytest.fixture
def client(tmp_path_factory, monkeypatch):
    flask_app.app.config["TESTING"] = True
    # Yüklemeler proje klasörünü kirletmesin → geçici klasöre yönlendir.
    # Yükleme yolu artık config'ten okunur (app.py ve durum.py aynı modülü
    # paylaşır), bu yüzden config.YUKLEME_KLASORU yamanır.
    up = tmp_path_factory.mktemp("yuklenen")
    monkeypatch.setattr(flask_app.config, "YUKLEME_KLASORU", str(up))
    c = flask_app.app.test_client()
    with c.session_transaction() as s:
        s["giris"] = True            # oturumu test için aç
    yield c
    # izolasyon: tüm yükleme slotlarını sıfırla
    flask_app.DURUM["kalem_yolu"] = None
    flask_app.DURUM["ozet_yolu"] = None
    flask_app.DURUM["orders_yolu"] = None
    flask_app.DURUM["shipments_yolu"] = None
    flask_app.DURUM["sku_katalog_yolu"] = None
    flask_app.DURUM["etsy"] = {"etsy_orders": [], "etsy_items": [],
                               "etsy_payments": [], "etsy_listings": []}
    flask_app.DURUM["reklam_yollari"] = []


def _csv_bytes(basliklar, satir=None):
    """Bellekte CSV üret (çoklu yükleme testleri için)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(basliklar)
    w.writerow(satir if satir is not None else ["x" for _ in basliklar])
    return buf.getvalue().encode("utf-8")


def _kalem(tmp_path):
    yol = tmp_path / "kalem.csv"
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Order #", "Store", "Item Name", "Item Quantity", "Item SKU"])
        w.writerow(["1", "Shop A", "Custom Engraved Wine Glass", "2", "WG1"])
        w.writerow(["2", "Shop A", "Mystery Zorblax Widget XYZ", "4", "ZRB"])
    return str(yol)


def test_oturum_gerekli_401():
    c = flask_app.app.test_client()        # oturumsuz
    r = c.post("/api/urun/ogretilecekler")
    assert r.status_code == 401
    assert r.get_json().get("giris_gerekli") is True


def test_ogretilecekler_kalemsiz_hata(client):
    flask_app.DURUM["kalem_yolu"] = None
    r = client.post("/api/urun/ogretilecekler")
    assert r.status_code == 400


def test_ogretilecekler_kuyruk_ve_oneri(client, tmp_path):
    flask_app.DURUM["kalem_yolu"] = _kalem(tmp_path)
    r = client.post("/api/urun/ogretilecekler")
    assert r.status_code == 200
    d = r.get_json()
    skus = [x["sku"] for x in d["kuyruk"]]
    assert "ZRB" in skus          # taksonomi dışı → kuyrukta
    assert "WG1" not in skus      # keyword'le çözülür → kuyrukta değil
    assert "WineGlass" in d["kategoriler"]
    assert d["ozet"]["sku_sayisi"] == 2
    # ZRB kaydı öneri alanı taşımalı (boş olabilir ama yapı olmalı)
    zrb = next(x for x in d["kuyruk"] if x["sku"] == "ZRB")
    assert "oneriler" in zrb and isinstance(zrb["oneriler"], list)


# ---- Çoklu (formsuz) yükleme: içeriğe göre otomatik yönlendirme -----------
def test_yukle_coklu_oturum_gerekli_401():
    c = flask_app.app.test_client()        # oturumsuz
    r = c.post("/api/yukle_coklu")
    assert r.status_code == 401


def test_yukle_coklu_dosyasiz_hata(client):
    r = client.post("/api/yukle_coklu", data={},
                    content_type="multipart/form-data")
    assert r.status_code == 400


def test_yukle_coklu_icerige_gore_yonlendirir(client):
    # ShipStation kalem + ShipStation özet + Etsy siparişleri + reklam +
    # tanınamayan bir dosya: hepsi tek istekte, doğru slota.
    kalem = _csv_bytes(["Order #", "Store", "Item Name",
                        "Item Quantity", "Item SKU"])
    ozet = _csv_bytes(["Order - Number", "Market - Store Name",
                       "Amount - Order Total", "Amount - Shipping Cost"])
    etsy_o = _csv_bytes(["Sale Date", "Order ID", "Number of Items",
                         "Order Total"])
    reklam = _csv_bytes(["Date", "Store", "Advertising", "Ad Spend"])
    cop = _csv_bytes(["Foo", "Bar", "Baz"])
    data = {"dosyalar": [
        (io.BytesIO(kalem), "magazaA_items.csv"),
        (io.BytesIO(ozet), "insights.csv"),
        (io.BytesIO(etsy_o), "EtsySoldOrders.csv"),
        (io.BytesIO(reklam), "etsy_stmt.csv"),
        (io.BytesIO(cop), "rastgele.csv"),
    ]}
    r = client.post("/api/yukle_coklu", data=data,
                    content_type="multipart/form-data")
    assert r.status_code == 200
    d = r.get_json()
    turler = {x["dosya"]: x["tur"] for x in d["dosyalar"]}
    assert turler["magazaA_items.csv"] == "kalem"
    assert turler["insights.csv"] == "ozet"
    assert turler["EtsySoldOrders.csv"] == "etsy_orders"
    assert turler["etsy_stmt.csv"] == "reklam"
    assert turler["rastgele.csv"] == "bilinmiyor"
    # tanınanlar kabul, çöp reddedilmeli
    kabul = {x["dosya"]: x["kabul"] for x in d["dosyalar"]}
    assert kabul["rastgele.csv"] is False
    assert all(kabul[k] for k in
               ("magazaA_items.csv", "insights.csv",
                "EtsySoldOrders.csv", "etsy_stmt.csv"))
    # slot özeti tutmalı
    o = d["ozet"]
    assert o["kalem"] is True and o["ozet"] is True
    assert o["etsy_orders"] == 1 and o["reklam"] == 1
    assert flask_app.DURUM["kalem_yolu"] is not None


def test_yukle_coklu_etsy_cok_magaza_biriktirir(client):
    # Aynı türden iki Etsy dosyası (iki mağaza) → liste birikmeli, ezilmemeli.
    a = _csv_bytes(["Sale Date", "Order ID", "Number of Items", "Order Total"])
    b = _csv_bytes(["Sale Date", "Order ID", "Number of Items", "Order Total"])
    data = {"dosyalar": [
        (io.BytesIO(a), "EtsySoldOrders.csv"),
        (io.BytesIO(b), "EtsySoldOrders.csv"),
    ]}
    r = client.post("/api/yukle_coklu", data=data,
                    content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.get_json()["ozet"]["etsy_orders"] == 2
    assert len(flask_app.DURUM["etsy"]["etsy_orders"]) == 2
