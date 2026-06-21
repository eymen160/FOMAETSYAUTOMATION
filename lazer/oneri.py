# Öğrenen kategori önericisi (hafif "ML"): sınıflandırılmış ürün adlarından
# token→kategori istatistiği çıkarır ve bilinmeyen bir ürün adı için en olası
# kategorileri önerir. Harici bağımlılık yok (token-oyu / Naive-Bayes benzeri).
#
# Amaç: SKU'lar mağazadan mağazaya farklı olduğunda bile ürün ADI betimleyici
# olduğu için ortak öğrenilebilir. Keyword motoru bir adı çözemediğinde, bu
# öneri motoru öğretme (teach) ekranına "akıllı tahmin" sunar. Korpus büyüdükçe
# (daha çok SKU öğrenildikçe) öneriler kendiliğinden iyileşir.
import re
from collections import defaultdict

# Ayırt edici olmayan, her üründe geçen kelimeler (öneriye katkısı zararlı).
STOP = set((
    "the a an and or for with of to in on by your you our this that it is are "
    "personalized personalize personalised custom customized engraved engrave "
    "engraving monogram monogrammed gift gifts set sets name names laser wooden "
    "wood leather stainless steel metal oz personal new best first great cute "
    "funny men women mens womens man woman him her his their dad mom mommy daddy "
    "father mother son daughter husband wife boyfriend girlfriend family kids "
    "day wedding birthday christmas anniversary valentine graduation groomsmen "
    "groomsman bridesmaid bride groom party holiday keepsake matching couple "
    "him her gift custom design designs item product quality premium handmade "
    "unique special perfect love mr mrs ships next"
).split())

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(ad):
    """Ürün adından ayırt edici küçük-harf token kümesi (>2 harf, STOP hariç)."""
    return [t for t in _TOKEN.findall((ad or "").lower())
            if len(t) > 2 and t not in STOP]


def model_kur(ciftler):
    """ciftler: iterable[(ad, kategori)] veya [(ad, kategori, agirlik)].
    Dönüş: {token_kat: {token: {kat: agirlik}}, kat_top: {kat: agirlik}}."""
    token_kat = defaultdict(lambda: defaultdict(float))
    kat_top = defaultdict(float)
    for cift in ciftler:
        ad, kat = cift[0], cift[1]
        agirlik = float(cift[2]) if len(cift) > 2 and cift[2] else 1.0
        if not kat:
            continue
        kat_top[kat] += agirlik
        for t in set(tokenize(ad)):
            token_kat[t][kat] += agirlik
    return {"token_kat": {t: dict(d) for t, d in token_kat.items()},
            "kat_top": dict(kat_top)}


def model_katalogdan(katalog):
    """sku_katalog.katalog_topla() çıktısından öneri modeli kurar.
    Öğrenilmiş kategori (kategori) varsa onu, yoksa auto_kategori'yi kullanır."""
    ciftler = []
    for k in katalog.values():
        kat = k.get("kategori") or k.get("auto_kategori")
        if kat:
            ciftler.append((k.get("ornek_ad", ""), kat, k.get("adet", 1)))
    return model_kur(ciftler)


def oner(ad, model, n=3):
    """ad için [(kategori, skor)] (en olası ilk). Token başına kategori
    dağılımının normalize toplamı; eşit ad token'ları ayırt ediciliğe göre."""
    tokens = set(tokenize(ad))
    tk = model.get("token_kat") or {}
    if not tokens or not tk:
        return []
    skor = defaultdict(float)
    for t in tokens:
        dagilim = tk.get(t)
        if not dagilim:
            continue
        toplam = sum(dagilim.values()) or 1.0
        for kat, w in dagilim.items():
            skor[kat] += w / toplam       # token'ın o kategoriye ait olma oranı
    if not skor:
        return []
    sirali = sorted(skor.items(), key=lambda x: (-x[1], x[0]))
    return [(k, round(s, 3)) for k, s in sirali[:n]]
