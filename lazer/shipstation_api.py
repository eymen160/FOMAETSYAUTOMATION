# ShipStation V2 API istemcisi: kargo MALİYETİ (label bazlı) + store_id eşleme
import calendar
import json
import os
import time

import requests

BASE = "https://api.shipstation.com/v2"
CACHE_KLASORU = "cache"
STORE_ID_DOSYASI = "store_id_mapping.json"


class ApiHata(Exception):
    """Kullanıcıya gösterilecek anlaşılır Türkçe mesaj taşır."""


class ShipStationV2:
    def __init__(self, api_key):
        if not api_key:
            raise ApiHata(
                "SHIPSTATION_API_KEY bulunamadı. Proje klasöründeki .env dosyasına "
                "SHIPSTATION_API_KEY=... satırını ekleyin.")
        self.api_key = api_key
        os.makedirs(CACHE_KLASORU, exist_ok=True)

    # ---- HTTP katmanı -------------------------------------------------
    def _get(self, yol, params=None, deneme=0):
        try:
            r = requests.get(BASE + yol, params=params, timeout=60,
                             headers={"API-Key": self.api_key,
                                      "Accept": "application/json"})
        except requests.RequestException as e:
            raise ApiHata(
                "ShipStation API'ye ulaşılamadı (ağ hatası). İnternet bağlantınızı "
                f"kontrol edin veya CSV moduna geçin. Ayrıntı: {type(e).__name__}")
        if r.status_code == 401:
            raise ApiHata("API anahtarı geçersiz, .env dosyasını kontrol edin.")
        if r.status_code == 403:
            raise ApiHata(
                "ShipStation API erişimi reddedildi (403). API anahtarının V2 "
                "yetkisi olduğundan ve ağ/güvenlik duvarı ayarlarından emin olun.")
        if r.status_code == 429:
            if deneme >= 5:
                raise ApiHata("ShipStation API hız sınırı (429) aşıldı, daha sonra deneyin.")
            bekle = 2 ** (deneme + 1)
            time.sleep(bekle)
            return self._get(yol, params, deneme + 1)
        if r.status_code >= 400:
            raise ApiHata(f"ShipStation API hatası (HTTP {r.status_code}). "
                          "Daha sonra tekrar deneyin veya CSV moduna geçin.")
        try:
            return r.json()
        except ValueError:
            raise ApiHata("ShipStation API beklenmeyen bir yanıt döndürdü (JSON değil).")

    def baglanti_testi(self):
        """page_size=1 ile auth + alan adlarını teyit eder."""
        veri = self._get("/labels", {"page_size": 1})
        ornek = (veri.get("labels") or [{}])[0]
        return {"ok": True, "alanlar": sorted(ornek.keys()),
                "toplam": veri.get("total")}

    # ---- Sayfalı çekimler (cache'li) ----------------------------------
    def _sayfali_cek(self, yol, liste_anahtari, params):
        ogeler, sayfa = [], 1
        while True:
            p = dict(params, page=sayfa, page_size=100)
            veri = self._get(yol, p)
            parca = veri.get(liste_anahtari) or []
            ogeler.extend(parca)
            toplam_sayfa = veri.get("pages") or 1
            if sayfa >= toplam_sayfa or not parca:
                return ogeler
            sayfa += 1

    def _cache_yolu(self, ad, yil, ay):
        return os.path.join(CACHE_KLASORU, f"{ad}_{yil}_{ay:02d}.json")

    def _cacheli(self, ad, yil, ay, uretici, yenile=False):
        yol = self._cache_yolu(ad, yil, ay)
        if not yenile and os.path.exists(yol):
            with open(yol, encoding="utf-8") as f:
                return json.load(f)
        veri = uretici()
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(veri, f)
        return veri

    def ay_labellari(self, yil, ay, yenile=False):
        son_gun = calendar.monthrange(yil, ay)[1]
        params = {"created_at_start": f"{yil}-{ay:02d}-01T00:00:00Z",
                  "created_at_end": f"{yil}-{ay:02d}-{son_gun}T23:59:59Z"}
        return self._cacheli("labels", yil, ay, yenile=yenile,
                             uretici=lambda: self._sayfali_cek("/labels", "labels", params))

    def ay_shipmentlari(self, yil, ay, yenile=False):
        son_gun = calendar.monthrange(yil, ay)[1]
        params = {"created_at_start": f"{yil}-{ay:02d}-01T00:00:00Z",
                  "created_at_end": f"{yil}-{ay:02d}-{son_gun}T23:59:59Z"}
        return self._cacheli("shipments", yil, ay, yenile=yenile,
                             uretici=lambda: self._sayfali_cek("/shipments", "shipments", params))

    def shipment_detay(self, shipment_id):
        return self._get(f"/shipments/{shipment_id}")


# ---- Label işleme ------------------------------------------------------

def _tutar(obj):
    if isinstance(obj, dict):
        return float(obj.get("amount") or 0)
    return float(obj or 0)


def _gecerli_label(lab):
    if lab.get("voided"):
        return False
    return (lab.get("status") or "").lower() not in ("voided", "cancelled", "canceled")


def labellari_isle(labels):
    """Voided'ları at; aynı shipment için en güncel geçerli label'ı tut.

    Dönüş: {shipment_id: {maliyet, ship_date, tracking, order_no?}}, voided_sayisi
    """
    voided = 0
    secilen = {}
    for lab in labels:
        if not _gecerli_label(lab):
            voided += 1
            continue
        sid = lab.get("shipment_id") or lab.get("label_id")
        olusturma = lab.get("created_at") or ""
        if sid in secilen and secilen[sid]["created_at"] >= olusturma:
            continue
        secilen[sid] = {
            "created_at": olusturma,
            "maliyet": _tutar(lab.get("shipment_cost")) + _tutar(lab.get("insurance_cost")),
            "ship_date": lab.get("ship_date"),
            "tracking": lab.get("tracking_number"),
            "order_no": (lab.get("external_order_id") or lab.get("order_number")
                         or lab.get("external_shipment_id")),
            "store_id": lab.get("store_id"),
        }
    return secilen, voided


def store_id_sozlugu_yukle(yol=STORE_ID_DOSYASI):
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    return {}


def store_id_sozlugu_kaydet(sozluk, yol=STORE_ID_DOSYASI):
    mevcut = store_id_sozlugu_yukle(yol)
    mevcut.update({str(k): v for k, v in sozluk.items()})
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(mevcut, f, ensure_ascii=False, indent=2, sort_keys=True)
    return mevcut


def kargo_maliyeti_hesapla(api, yil, ay, order_store, yenile=False):
    """API'den ay label'larını çekip ShipStation mağaza adı bazında kargo
    maliyetini hesaplar.

    order_store: Order # → ShipStation Store adı (CSV'lerden).
    Dönüş: {magaza_kargo, eslesmeyen_maliyet, voided, label_sayisi,
            store_id_eslesme: {store_id: store_adi}, bilinmeyen_store_idler}
    """
    labels = api.ay_labellari(yil, ay, yenile=yenile)
    secilen, voided = labellari_isle(labels)

    # store_id → mağaza adı sözlüğü (kalıcı) + shipment üzerinden tamamlama
    id_sozluk = store_id_sozlugu_yukle()
    shipment_store = {}
    eksik_order = any(not v.get("order_no") for v in secilen.values())
    eksik_store_id = any(not v.get("store_id") for v in secilen.values())
    if eksik_order or eksik_store_id:
        try:
            for sh in api.ay_shipmentlari(yil, ay, yenile=yenile):
                shipment_store[sh.get("shipment_id")] = {
                    "store_id": sh.get("store_id"),
                    "order_no": (sh.get("external_order_id")
                                 or sh.get("order_number")
                                 or sh.get("external_shipment_id")),
                }
        except ApiHata:
            shipment_store = {}  # shipments listesi alınamazsa label verisiyle devam

    magaza_kargo = {}
    eslesmeyen = {"maliyet": 0.0, "adet": 0}
    yeni_id_eslesme = {}
    bilinmeyen_idler = {}
    for sid, v in secilen.items():
        ek = shipment_store.get(sid, {})
        order_no = str(v.get("order_no") or ek.get("order_no") or "").strip()
        store_id = str(v.get("store_id") or ek.get("store_id") or "")
        magaza = order_store.get(order_no)
        if magaza is None and store_id and store_id in id_sozluk:
            magaza = id_sozluk[store_id]
        if magaza is None:
            eslesmeyen["maliyet"] += v["maliyet"]
            eslesmeyen["adet"] += 1
            if store_id:
                b = bilinmeyen_idler.setdefault(store_id, {"adet": 0, "maliyet": 0.0})
                b["adet"] += 1
                b["maliyet"] += v["maliyet"]
            continue
        if store_id and store_id not in id_sozluk:
            yeni_id_eslesme[store_id] = magaza
        magaza_kargo[magaza] = magaza_kargo.get(magaza, 0.0) + v["maliyet"]
    if yeni_id_eslesme:
        store_id_sozlugu_kaydet(yeni_id_eslesme)
    return {
        "magaza_kargo": {k: round(v, 2) for k, v in magaza_kargo.items()},
        "eslesmeyen": {"maliyet": round(eslesmeyen["maliyet"], 2),
                       "adet": eslesmeyen["adet"]},
        "voided": voided,
        "label_sayisi": len(secilen),
        "yeni_store_id_eslesme": yeni_id_eslesme,
        "bilinmeyen_store_idler": bilinmeyen_idler,
    }
