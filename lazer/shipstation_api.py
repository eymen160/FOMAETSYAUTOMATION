# ShipStation V2 API istemcisi: kargo MALİYETİ (label bazlı) + store_id eşleme
import calendar
import json
import os
import re
import time
from datetime import datetime, timedelta

import requests

from .config import veri_yolu

BASE = "https://api.shipstation.com/v2"
CACHE_KLASORU = veri_yolu("cache")
STORE_ID_DOSYASI = veri_yolu("store_id_mapping.json")


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
        # Maliyet SİPARİŞ ayına yazılır; ay sonu siparişlerinin label'ı sonraki
        # ayda kesilebildiğinden geniş pencereyle çekilir (ay başı −7 gün,
        # ay sonu +45 gün) ve Order # üzerinden ay kümesine bağlanır.
        bas, son = _genis_pencere(yil, ay)
        params = {"created_at_start": bas, "created_at_end": son}
        return self._cacheli("labels_genis", yil, ay, yenile=yenile,
                             uretici=lambda: self._sayfali_cek("/labels", "labels", params))

    def ay_shipmentlari(self, yil, ay, yenile=False):
        bas, son = _genis_pencere(yil, ay)
        params = {"created_at_start": bas, "created_at_end": son}
        return self._cacheli("shipments_genis", yil, ay, yenile=yenile,
                             uretici=lambda: self._sayfali_cek("/shipments", "shipments", params))

    def shipment_detay(self, shipment_id):
        return self._get(f"/shipments/{shipment_id}")


# ---- Label işleme ------------------------------------------------------

def _genis_pencere(yil, ay):
    bas = datetime(yil, ay, 1) - timedelta(days=7)
    son = datetime(yil, ay, calendar.monthrange(yil, ay)[1]) + timedelta(days=45)
    return (bas.strftime("%Y-%m-%dT00:00:00Z"), son.strftime("%Y-%m-%dT23:59:59Z"))


def order_no_norm(o):
    """Order # karşılaştırma anahtarı: boşluk + Excel'in '12345.0' bozması."""
    s = str(o or "").strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _order_no_gevsek(o):
    """Format anomalisi taraması için gevşek anahtar (büyük/küçük, -, boşluk)."""
    return re.sub(r"[\s\-_#]+", "", order_no_norm(o)).casefold()


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


STORE_ID_MIN_KANIT = 3  # store_id eşlemesi kalıcılaşmadan önce gereken sipariş


def kargo_maliyeti_hesapla(api, yil, ay, order_store, ay_siparisleri=None,
                           iptal_orderlar=None, shipments_orderlari=None,
                           yenile=False):
    """API label'larından ShipStation mağaza adı bazında kargo maliyeti.

    order_store: Order # → ShipStation Store adı (Orders + Shipments CSV).
    ay_siparisleri: Order # → {store, ciro} — seçili ayın iptalsiz sipariş
      kümesi. Verilirse maliyet SİPARİŞ AYINA yazılır: yalnızca bu kümedeki
      Order #'larla eşleşen label'lar sayılır (label hangi ayda kesilmiş
      olursa olsun); eşleşme istatistiği, eşleşmeyen sipariş sınıflandırması
      ve mağaza bazında "henüz kargolanmamış" listesi de döner.
    iptal_orderlar: iptal/iade Order #'ları (sınıflandırma için).
    shipments_orderlari: Shipments CSV'de gönderi kaydı olan Order #'lar.

    Dönüş: {magaza_kargo, eslesmeyen, voided, label_sayisi, ay_disi_label,
            istatistik, kargolanmamis, store_id_dusuk_guven, store_id_celiski,
            yeni_store_id_eslesme, bilinmeyen_store_idler}
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

    os_norm = {order_no_norm(k): v for k, v in (order_store or {}).items()
               if order_no_norm(k)}
    ay_set = None
    if ay_siparisleri is not None:
        ay_set = {order_no_norm(k) for k in ay_siparisleri if order_no_norm(k)}

    magaza_kargo = {}
    eslesmeyen = {"maliyet": 0.0, "adet": 0}
    bilinmeyen_idler = {}
    kanit = {}            # store_id -> {magaza: {order_no}} (CSV kaynaklı kanıt)
    eslesen_orderlar = set()
    label_gevsek = set()  # format anomalisi taraması için gevşek anahtarlar
    ay_disi_label = 0
    sayilan = 0
    for sid, v in secilen.items():
        ek = shipment_store.get(sid, {})
        ono = order_no_norm(v.get("order_no") or ek.get("order_no") or "")
        store_id = str(v.get("store_id") or ek.get("store_id") or "")
        label_gevsek.add(_order_no_gevsek(ono))
        if ay_set is not None and ono not in ay_set:
            ay_disi_label += 1  # başka ayın siparişi: bu aya yazılmaz
            continue
        magaza = os_norm.get(ono)
        if magaza is not None and store_id:
            kanit.setdefault(store_id, {}).setdefault(magaza, set()).add(ono or sid)
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
        if ono:
            eslesen_orderlar.add(ono)
        magaza_kargo[magaza] = magaza_kargo.get(magaza, 0.0) + v["maliyet"]
        sayilan += 1

    # store_id öğrenme: tek siparişlik kanıt kalıcılaşmaz, çelişki ezilmez
    yeni_id_eslesme, dusuk_guven, celiskiler = {}, {}, []
    for sid_, magazalar_k in kanit.items():
        if len(magazalar_k) > 1:
            celiskiler.append(
                f"store_id {sid_} bu ay birden fazla mağazayla görüldü: "
                + ", ".join(f"'{m}' ({len(s)} sipariş)"
                            for m, s in sorted(magazalar_k.items()))
                + " — otomatik eşleme yapılmadı, elle kontrol edin.")
            continue
        magaza, orderlar = next(iter(magazalar_k.items()))
        if sid_ in id_sozluk:
            if id_sozluk[sid_] != magaza:
                celiskiler.append(
                    f"store_id {sid_} kayıtlı eşlemesi '{id_sozluk[sid_]}' ama bu ay "
                    f"{len(orderlar)} sipariş '{magaza}' gösteriyor — üzerine "
                    "YAZILMADI; doğruysa eşlemeyi elle onaylayın.")
            continue
        if len(orderlar) >= STORE_ID_MIN_KANIT:
            yeni_id_eslesme[sid_] = magaza
        else:
            dusuk_guven[sid_] = {"magaza": magaza, "siparis_sayisi": len(orderlar)}
    if yeni_id_eslesme:
        store_id_sozlugu_kaydet(yeni_id_eslesme)

    # Eşleşme istatistiği + eşleşmeyen sipariş sınıflandırması + kargolanmamış
    istatistik, kargolanmamis = None, {}
    if ay_set is not None:
        ham_map = {order_no_norm(k): k for k in ay_siparisleri}
        ship_set = {order_no_norm(o) for o in (shipments_orderlari or [])}
        siniflar = {"kargolanmamis": [], "format_anomalisi": [],
                    "aciklanamayan": [],
                    "iptal_iade": sorted({order_no_norm(o)
                                          for o in (iptal_orderlar or [])})}
        for ono in sorted(ay_set - eslesen_orderlar):
            if _order_no_gevsek(ono) in label_gevsek:
                siniflar["format_anomalisi"].append(ono)
            elif ono not in ship_set:
                siniflar["kargolanmamis"].append(ono)
            else:
                siniflar["aciklanamayan"].append(ono)
        for ono in siniflar["kargolanmamis"]:
            sp = ay_siparisleri.get(ham_map.get(ono, ono)) or {}
            k = kargolanmamis.setdefault(sp.get("store") or "(mağazasız)",
                                         {"adet": 0, "ciro": 0.0})
            k["adet"] += 1
            k["ciro"] += sp.get("ciro") or 0.0
        toplam = len(ay_set)
        eslesen = len(eslesen_orderlar & ay_set)
        oran = (eslesen / toplam) if toplam else 1.0
        istatistik = {"toplam_siparis": toplam, "eslesen": eslesen,
                      "oran": round(oran, 4), "dusuk": oran < 0.97,
                      "siniflar": siniflar}
        kargolanmamis = {k: {"adet": v["adet"], "ciro": round(v["ciro"], 2)}
                         for k, v in sorted(kargolanmamis.items())}

    return {
        "magaza_kargo": {k: round(v, 2) for k, v in magaza_kargo.items()},
        "eslesmeyen": {"maliyet": round(eslesmeyen["maliyet"], 2),
                       "adet": eslesmeyen["adet"]},
        "voided": voided,
        "label_sayisi": sayilan,
        "ay_disi_label": ay_disi_label,
        "istatistik": istatistik,
        "kargolanmamis": kargolanmamis,
        "yeni_store_id_eslesme": yeni_id_eslesme,
        "store_id_dusuk_guven": dusuk_guven,
        "store_id_celiski": celiskiler,
        "bilinmeyen_store_idler": bilinmeyen_idler,
    }
