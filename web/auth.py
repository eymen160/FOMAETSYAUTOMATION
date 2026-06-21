# Oturum/giriş uç noktaları ve uygulama geneli oturum koruması.
from flask import (Blueprint, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash

from config import ACIK_YOLLAR, GIRIS_KULLANICI, GIRIS_SIFRE_HASH

auth_bp = Blueprint("auth", __name__)


def oturum_kontrol():
    """before_request kancası: giriş ve statik dışındaki her şey oturum ister.
    Fabrika tarafından app.before_request ile bağlanır."""
    if request.endpoint in ACIK_YOLLAR:
        return None
    if session.get("giris"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"hata": "Oturum gerekli. Lütfen tekrar giriş yapın.",
                        "giris_gerekli": True}), 401
    return redirect(url_for("auth.giris_sayfa"))


@auth_bp.route("/giris", methods=["GET", "POST"])
def giris_sayfa():
    if request.method == "POST":
        veri = request.get_json(silent=True) or request.form
        kul = (veri.get("kullanici") or "").strip()
        sif = veri.get("sifre") or ""
        if kul == GIRIS_KULLANICI and check_password_hash(GIRIS_SIFRE_HASH, sif):
            session["giris"] = True
            session["kullanici"] = kul
            session.permanent = True
            return jsonify({"tamam": True})
        return jsonify({"hata": "Kullanıcı adı veya şifre hatalı."}), 401
    if session.get("giris"):
        return redirect(url_for("yukleme.anasayfa"))
    return render_template("giris.html")


@auth_bp.route("/cikis")
def cikis():
    session.clear()
    return redirect(url_for("auth.giris_sayfa"))
