# Master Excel (Google Form yanıtları) okuma
import pandas as pd

from .yardimci import kolon_bul, sayi, tr_kucuk, ek_odeme_coz

SHEET_ADI = "Form Yanıtları 1"

KOLON_ADAYLARI = {
    "magaza_yeni": ["Mağaza"],
    "magaza_eski": ["Mağaza1"],
    "donem": ["Dönem"],
    "yil": ["Yıl"],
    "ciro": ["Ciro"],
    "vergi": ["Vergi"],
    "reklam": ["Reklam"],
    "kargo_musteri": ["Müşteri Kargo Ödemesi", "Müşteri Kargo"],
    "kargo": ["Kargo Harcaması"],
    "adet": ["Toplam Satış Adedi"],
    "upgrade": ["Upgrade Satışı", "Upgrade"],
    "ek_odeme": ["Ek ödeme"],
    "kalan_form": ["Kalan Gelir"],
    "hatali_urun": ["Hatalı ürün"],
    "diger": ["Diğer konular"],
    "zaman": ["Zaman damgası"],
}

ZORUNLU = ["donem", "yil", "ciro", "vergi", "reklam", "kargo_musteri", "kargo", "adet"]


class MasterHata(Exception):
    pass


def master_oku(yol):
    """Master Excel'i okuyup kolonları çözümler. Dönüş: (DataFrame, kolon_map)."""
    try:
        df = pd.read_excel(yol, sheet_name=SHEET_ADI)
    except ValueError:
        raise MasterHata(
            f"Master Excel'de '{SHEET_ADI}' sayfası bulunamadı. "
            "Doğru dosyayı yüklediğinizden emin olun.")
    basliklar = list(df.columns)
    kmap = {anahtar: kolon_bul(basliklar, adaylar)
            for anahtar, adaylar in KOLON_ADAYLARI.items()}
    if kmap["magaza_yeni"] is None and kmap["magaza_eski"] is None:
        raise MasterHata("Master Excel'de 'Mağaza' kolonu bulunamadı.")
    eksik = [k for k in ZORUNLU if kmap[k] is None]
    if eksik:
        raise MasterHata(
            "Master Excel'de şu kolonlar bulunamadı: "
            + ", ".join(KOLON_ADAYLARI[k][0] for k in eksik))
    return df, kmap


def _hucre(satir, kmap, anahtar):
    kol = kmap.get(anahtar)
    if kol is None:
        return None
    v = satir.get(kol)
    if pd.isna(v):
        return None
    return v


def ay_kayitlari(df, kmap, ay_adi, yil):
    """Seçilen dönem+yıl için mağaza kayıtlarını ve bozuk satırları döndürür."""
    kayitlar, bozuk, uyarilar = [], [], []
    hedef_donem = tr_kucuk(ay_adi)
    gorulen = {}
    for idx, satir in df.iterrows():
        donem = tr_kucuk(_hucre(satir, kmap, "donem"))
        yil_v = sayi(_hucre(satir, kmap, "yil"))
        if donem != hedef_donem or yil_v != float(yil):
            continue
        magaza = _hucre(satir, kmap, "magaza_yeni") or _hucre(satir, kmap, "magaza_eski")
        magaza = str(magaza).strip() if magaza is not None else ""
        satir_no = idx + 2  # Excel satır numarası (başlık + 1-index)
        if not magaza:
            bozuk.append({"satir": satir_no, "sorun": "Mağaza adı boş"})
            continue
        kayit = {"magaza": magaza, "satir": satir_no}
        sorunlu = []
        for alan in ["ciro", "vergi", "reklam", "kargo_musteri", "kargo", "adet", "upgrade"]:
            ham = _hucre(satir, kmap, alan)
            deger = sayi(ham)
            if deger is None:
                if ham is not None and str(ham).strip():
                    sorunlu.append(f"{alan} sayıya çevrilemedi: '{ham}'")
                deger = 0.0
            kayit[alan] = deger
        ek_ham = _hucre(satir, kmap, "ek_odeme")
        kayit["ek_odeme"], ek_uyari = ek_odeme_coz(ek_ham)
        kayit["ek_odeme_metin"] = "" if ek_ham is None else str(ek_ham)
        if ek_uyari:
            uyarilar.append(f"{magaza}: {ek_uyari}")
        kayit["hatali_urun"] = str(_hucre(satir, kmap, "hatali_urun") or "")
        kayit["diger"] = str(_hucre(satir, kmap, "diger") or "")
        kayit["kalan_form"] = sayi(_hucre(satir, kmap, "kalan_form"))
        if sorunlu:
            bozuk.append({"satir": satir_no, "magaza": magaza, "sorun": "; ".join(sorunlu)})
        if magaza in gorulen:
            uyarilar.append(
                f"'{magaza}' için {ay_adi} {yil} döneminde birden fazla form yanıtı var "
                f"(satır {gorulen[magaza]} ve {satir_no}); en son gönderilen kullanıldı.")
            kayitlar = [k for k in kayitlar if k["magaza"] != magaza]
        gorulen[magaza] = satir_no
        kayitlar.append(kayit)
    return kayitlar, bozuk, uyarilar


def donemler(df, kmap):
    """Master'daki mevcut (dönem, yıl) kombinasyonları."""
    sonuc = set()
    for _, satir in df.iterrows():
        d = _hucre(satir, kmap, "donem")
        y = sayi(_hucre(satir, kmap, "yil"))
        if d and y:
            sonuc.add((str(d).strip().capitalize(), int(y)))
    return sorted(sonuc, key=lambda t: (t[1], t[0]))
