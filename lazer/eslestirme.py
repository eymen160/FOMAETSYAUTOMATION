# ShipStation mağaza adı ↔ master mağaza adı eşleştirme (fuzzy + kalıcı sözlük)
import json
import os
import re

from rapidfuzz import fuzz

from .yardimci import tr_kucuk
from .shipstation_csv import amazon_mu
from .config import veri_yolu

ESLESTIRME_DOSYASI = veri_yolu("store_mapping.json")
AMAZON_ETIKETI = "Rapor Dışı (Amazon)"

# Mağaza adlarında ayırt edici olmayan kelimeler
_GENEL_KELIMELER = {"custom", "design", "designs", "store", "shop", "gift",
                    "gifts", "by", "the", "co", "studio"}


def _camel_ayir(s):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)


def normalize_magaza(ad):
    """Karşılaştırma anahtarı: camelCase ayır, küçült, genel kelimeleri at."""
    s = _camel_ayir(str(ad).strip())
    s = tr_kucuk(s)
    s = re.sub(r"[^a-z0-9ıöüçşğ ]+", " ", s)
    kelimeler = [k for k in s.split() if k not in _GENEL_KELIMELER]
    return " ".join(kelimeler) if kelimeler else s.strip()


def yukle(yol=ESLESTIRME_DOSYASI):
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    return {}


def kaydet(eslesmeler, yol=ESLESTIRME_DOSYASI):
    mevcut = yukle(yol)
    mevcut.update({k.strip(): v for k, v in eslesmeler.items()})
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(mevcut, f, ensure_ascii=False, indent=2, sort_keys=True)
    return mevcut


def oneri_uret(shipstation_adlari, master_adlari, mevcut=None):
    """Her ShipStation mağazası için durum + öneri listesi üretir.

    Dönüş listesi öğesi: {shipstation, durum: eslesik|amazon|oneri|bilinmiyor,
                          master, skor, adaylar}
    """
    mevcut = mevcut or {}
    sonuc = []
    master_norm = {m: normalize_magaza(m) for m in master_adlari}
    for ss_ham in sorted(set(shipstation_adlari), key=tr_kucuk):
        ss = ss_ham.strip()
        if ss in mevcut:
            sonuc.append({"shipstation": ss, "durum": "eslesik",
                          "master": mevcut[ss], "skor": 100, "adaylar": []})
            continue
        if amazon_mu(ss):
            sonuc.append({"shipstation": ss, "durum": "amazon",
                          "master": AMAZON_ETIKETI, "skor": 100, "adaylar": []})
            continue
        ss_n = normalize_magaza(ss)
        skorlar = []
        for m, m_n in master_norm.items():
            if ss_n == m_n:
                puan = 100  # normalize sonrası birebir eşleşme her zaman önde
            else:
                # token_set tek başına alt-küme eşleşmelerini (örn. 'art' ⊂
                # 'minimalist art') 100 sayar; token_sort ile ortalanır
                puan = min(99, round((fuzz.token_set_ratio(ss_n, m_n)
                                      + fuzz.token_sort_ratio(ss_n, m_n)) / 2))
            skorlar.append((puan, m))
        skorlar.sort(key=lambda t: t[0], reverse=True)
        adaylar = [{"master": m, "skor": p} for p, m in skorlar[:4] if p >= 45]
        if skorlar and skorlar[0][0] >= 90:  # <90 elle onay ister
            sonuc.append({"shipstation": ss, "durum": "oneri",
                          "master": skorlar[0][1], "skor": skorlar[0][0],
                          "adaylar": adaylar})
        else:
            sonuc.append({"shipstation": ss, "durum": "bilinmiyor",
                          "master": None, "skor": skorlar[0][0] if skorlar else 0,
                          "adaylar": adaylar})
    return sonuc
