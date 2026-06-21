# Uygulama yapılandırması: yol/limit sabitleri, demo verisi konumları ve
# kimlik doğrulama ayarları tek yerde toplanır (web katmanından ayrık).
import os
import secrets

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

# ---- Yükleme / çıktı / demo yolları ---------------------------------------
YUKLEME_KLASORU = "yuklenen"
CIKTI_KLASORU = "cikti"
DEMO_KLASORU = "demo"
DEMO_MASTER = os.path.join(DEMO_KLASORU, "demo_master_form.xlsx")
DEMO_OZET = os.path.join(DEMO_KLASORU, "demo_siparis_ozeti.csv")
DEMO_KALEM = os.path.join(DEMO_KLASORU, "demo_kalem_detay.csv")
DEMO_ESLESTIRME = os.path.join(DEMO_KLASORU, "store_mapping.json")
DEMO_AY, DEMO_YIL = "Mayıs", 2026

# Yükleme boyutu üst sınırı (ShipStation/Etsy export'ları büyük olabilir)
MAX_CONTENT_LENGTH = 100 * 1024 * 1024

# ---- Kimlik doğrulama -----------------------------------------------------
# Giriş bilgileri .env'den gelir; şifre düz metin tutulmaz, import anında
# hash'lenir ve karşılaştırma hash üzerinden yapılır.
GIRIS_KULLANICI = os.environ.get("LAZER_KULLANICI", "admin")
GIRIS_SIFRE_HASH = generate_password_hash(
    os.environ.get("LAZER_SIFRE", "lazer2026"))

# Giriş ve statik dışındaki her endpoint oturum ister. Blueprint'e taşındıktan
# sonra endpoint adları "auth." ön ekiyle gelir (static app düzeyinde kalır).
ACIK_YOLLAR = {"auth.giris_sayfa", "auth.cikis", "static"}


def gizli_anahtar():
    """Kalıcı Flask secret key (oturumların restart sonrası korunması için).
    Önce LAZER_SECRET ortam değişkenine, yoksa .flask_secret dosyasına bakar;
    ikisi de yoksa üretip dosyaya (0600) yazar."""
    env = os.environ.get("LAZER_SECRET")
    if env:
        return env
    yol = ".flask_secret"
    if os.path.exists(yol):
        with open(yol) as f:
            return f.read().strip()
    anahtar = secrets.token_hex(32)
    try:
        with open(yol, "w") as f:
            f.write(anahtar)
        os.chmod(yol, 0o600)
    except OSError:
        pass
    return anahtar
