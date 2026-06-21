# Kargo maliyeti uç noktaları: ShipStation API, bağlantı testi ve maliyet CSV.
import os

from flask import Blueprint, jsonify, request

from durum import DURUM
from lazer import shipstation_api, shipstation_csv
from web.ortak import hata as _hata

kargo_bp = Blueprint("kargo", __name__)


@kargo_bp.route("/api/kargo/api", methods=["POST"])
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


@kargo_bp.route("/api/kargo/test", methods=["POST"])
def kargo_test():
    try:
        api = shipstation_api.ShipStationV2(os.environ.get("SHIPSTATION_API_KEY"))
        return jsonify(api.baglanti_testi())
    except shipstation_api.ApiHata as e:
        return _hata(str(e), 502)


@kargo_bp.route("/api/kargo/csv", methods=["POST"])
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
