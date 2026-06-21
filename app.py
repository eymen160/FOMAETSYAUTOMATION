# Lazer Grubu ay sonu raporu otomasyonu — Flask giriş noktası.
# Çalıştırma: python app.py  →  http://127.0.0.1:5000
#
# İş mantığı katmanlara ayrıştırıldı:
#   config  → ayarlar / kimlik doğrulama sabitleri
#   durum   → çalışma-zamanı durumu (DURUM) ve durum yardımcıları
#   lazer/  → alan servisleri (CSV/Excel işleme, eşleştirme, rapor üretimi)
#   web/    → Flask blueprint'leri + create_app() fabrikası
# Bu dosya yalnız uygulamayı kurar. Testler app.app / app.DURUM / app.config'e
# baktığı için bu adlar burada modül düzeyinde görünür kalır.
import os

import config  # noqa: F401  (testler flask_app.config'i config modülü olarak yamar)
from durum import DURUM  # noqa: F401  (testler flask_app.DURUM'a bakar)
from web import create_app

app = create_app()


if __name__ == "__main__":
    # Port meşgulse PORT ortam değişkeniyle değiştirilebilir:
    #   PORT=5001 python3 app.py
    # macOS'te 5000 genelde AirPlay Receiver tarafından kullanılır.
    port = int(os.environ.get("PORT", "5000"))
    print(f"Lazer Grubu Rapor Otomasyonu → http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
