# Flask uygulama fabrikası: blueprint'leri toplar, oturum korumasını ve global
# hata yakalayıcıyı bağlar. app.py yalnız create_app()'i çağırır.
#
# Şablon/statik klasörleri proje köküne sabitlenir: fabrika web/ paketinin
# içinde olduğundan Flask'in varsayılan (paket-içi) yolları yanlış olur.
import os
import traceback

from flask import Flask

import config
from web.analiz import analiz_bp
from web.auth import auth_bp, oturum_kontrol
from web.kargo import kargo_bp
from web.ortak import hata
from web.rapor import rapor_bp
from web.urun import urun_bp
from web.yukleme import yukleme_bp

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app():
    """Uygulamayı kurup yapılandırılmış Flask örneğini döndürür."""
    app = Flask(__name__,
                template_folder=os.path.join(_KOK, "templates"),
                static_folder=os.path.join(_KOK, "static"))
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.secret_key = config.gizli_anahtar()
    os.makedirs(config.YUKLEME_KLASORU, exist_ok=True)
    os.makedirs(config.CIKTI_KLASORU, exist_ok=True)

    app.before_request(oturum_kontrol)
    for bp in (auth_bp, yukleme_bp, analiz_bp, kargo_bp, urun_bp, rapor_bp):
        app.register_blueprint(bp)

    @app.errorhandler(Exception)
    def genel_hata(e):
        # Stack trace kullanıcıya gösterilmez; terminale yazılır
        traceback.print_exc()
        return hata("Beklenmeyen bir hata oluştu. Ayrıntı için terminali "
                    "kontrol edin.", 500)

    return app
