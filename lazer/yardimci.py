# Ortak yardımcılar: Türkçe ay adları, esnek kolon eşleştirme, sayı ayrıştırma
import re
import unicodedata

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def tr_kucuk(s):
    """Türkçe'ye duyarlı küçük harfe çevirme (I→ı, İ→i)."""
    if s is None:
        return ""
    return str(s).replace("I", "ı").replace("İ", "i").lower().strip()


def ay_no(donem):
    """Türkçe ay adından ay numarası (1-12); bulunamazsa None."""
    d = tr_kucuk(donem)
    for i, ay in enumerate(AYLAR, start=1):
        if tr_kucuk(ay) == d:
            return i
    return None


def normalize_baslik(s):
    """Kolon başlığını karşılaştırma için normalize et: küçük harf,
    aksan/boşluk/noktalama toleranslı."""
    s = tr_kucuk(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9ıöüçşğ#]+", " ", s).strip()


def kolon_bul(basliklar, adaylar, prefix=True):
    """Başlık listesinde adaylardan birine uyan ilk kolonu döndür.
    prefix=True ise normalize edilmiş başlığın aday ile BAŞLAMASI yeterli."""
    norm = {b: normalize_baslik(b) for b in basliklar}
    for aday in adaylar:
        na = normalize_baslik(aday)
        for b, nb in norm.items():
            if nb == na:
                return b
    if prefix:
        for aday in adaylar:
            na = normalize_baslik(aday)
            for b, nb in norm.items():
                if nb.startswith(na):
                    return b
    return None


def sayi(deger, varsayilan=None):
    """Esnek sayı ayrıştırma: '1.234,56', '1,234.56', '$123' vb. kabul eder."""
    if deger is None:
        return varsayilan
    if isinstance(deger, (int, float)):
        try:
            f = float(deger)
        except (TypeError, ValueError):
            return varsayilan
        return varsayilan if f != f else f  # NaN kontrolü
    s = str(deger).strip()
    if not s or s in ("-", "—"):
        return varsayilan
    s = re.sub(r"[^\d,.\-]", "", s)
    if not s or s in (".", ",", "-"):
        return varsayilan
    # Hem nokta hem virgül varsa: sondaki ayraç ondalıktır
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Tek virgül ve 1-2 ondalık hane ise ondalık say, aksi halde binlik
        parca = s.split(",")
        if len(parca) == 2 and len(parca[1]) in (1, 2):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return varsayilan


def ek_odeme_coz(metin):
    """'12$ Adobe, 15$ Eğitim' gibi serbest metinden toplam dolar tutarı çıkar.
    Dönüş: (toplam, uyarı_veya_None)."""
    if metin is None:
        return 0.0, None
    s = str(metin).strip()
    if not s or s in ("0", "-", "0.0"):
        return 0.0, None
    if "₺" in s or re.search(r"\bTL\b", s, re.IGNORECASE):
        return 0.0, f"Ek ödeme TL cinsinden beyan edilmiş, dolara çevrilemedi: '{s}'"
    tutarlar = re.findall(r"(\d+(?:[.,]\d+)?)\s*\$|\$\s*(\d+(?:[.,]\d+)?)", s)
    toplam = 0.0
    for a, b in tutarlar:
        v = sayi(a or b)
        if v:
            toplam += v
    if toplam == 0.0:
        # $ işareti yoksa yalın sayıları dene (ör. '25 Adobe')
        yalin = re.findall(r"\b(\d+(?:[.,]\d+)?)\b", s)
        if len(yalin) == 1:
            toplam = sayi(yalin[0], 0.0)
        elif yalin:
            return 0.0, f"Ek ödeme metni net ayrıştırılamadı, elle kontrol edin: '{s}'"
    return round(toplam, 2), None
