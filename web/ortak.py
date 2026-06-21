# Blueprint'ler arası paylaşılan küçük yardımcılar.
from flask import jsonify


def hata(mesaj, kod=400):
    """Tek biçimli JSON hata yanıtı — tüm uç noktalar bunu kullanır."""
    return jsonify({"hata": mesaj}), kod
