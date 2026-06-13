# Yazılabilir durum dosyalarının kök dizini.
#
# DATA_DIR ortam değişkeni ayarlıysa (örn. Render'da /data kalıcı diski) tüm
# yazılabilir durum (store_mapping.json, store_id_mapping.json, cache/,
# yüklenen dosyalar, üretilen raporlar) oraya yazılır. Ayarlı değilse mevcut
# davranış korunur: dosyalar çalışma dizinine göreli olarak oluşturulur —
# böylece `python app.py` ile lokal çalışma hiç değişmez.
import os

DATA_DIR = (os.environ.get("DATA_DIR") or "").strip()

if DATA_DIR:
    os.makedirs(DATA_DIR, exist_ok=True)


def veri_yolu(*parcalar):
    """DATA_DIR altında yol üretir; DATA_DIR boşsa çalışma dizinine göreli."""
    return os.path.join(DATA_DIR, *parcalar) if DATA_DIR else os.path.join(*parcalar)
