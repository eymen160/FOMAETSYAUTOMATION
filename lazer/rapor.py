# Nihai Excel raporu (ekibin şablon görünümü, openpyxl)
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

BASLIKLAR = ["MAĞAZA", "CİRO", "Parça başı ciro", "VERGİ", "REKLAM",
             "KARGO MÜŞTERİ", "Kargo parça başı ort ödenen",
             "Kargo parça başı ort kalan", "Kargo", "P", "PARÇA ADEDİ",
             "İLAVE ÖDEME", "KALAN", "%REKLAM", "%VERGİ",
             "Parça başı kalan", "Upgrade"]

# Kolon harfleri (1 tabanlı): A MAĞAZA, B CİRO, C pb ciro, D VERGİ, E REKLAM,
# F KARGO MÜŞTERİ, G pb ödenen, H pb kalan, I Kargo, J P, K ADET, L İLAVE,
# M KALAN, N %REKLAM, O %VERGİ, P pb kalan, Q Upgrade
PARA_KOLONLARI = [2, 4, 5, 6, 9, 12, 13]
ONDALIK_KOLONLAR = [3, 7, 8, 16]
YUZDE_KOLONLARI = [14, 15]
SAYI_KOLONLARI = [11, 17]

TURUNCU = PatternFill("solid", fgColor="FF9900")
ACIK_GRI = PatternFill("solid", fgColor="F2F2F2")
BEYAZ_KALIN = Font(bold=True, color="FFFFFF", size=10)
KALIN = Font(bold=True)
INCE = Side(style="thin", color="BFBFBF")
KENARLIK = Border(left=INCE, right=INCE, top=INCE, bottom=INCE)

PARA_FMT = "#,##0"
ONDALIK_FMT = "#,##0.00"
YUZDE_FMT = "0.0%"


def _formul_bolme(pay_hucre, adet_hucre):
    """ADET 0/boşsa boş bırakan bölme formülü (#DIV/0! asla üretilmez)."""
    return f'=IF(N({adet_hucre})=0,"",{pay_hucre}/{adet_hucre})'


def _stil(ws, satir, kalin=False, dolgu=None):
    for k in range(1, len(BASLIKLAR) + 1):
        h = ws.cell(row=satir, column=k)
        h.border = KENARLIK
        if kalin:
            h.font = KALIN
        if dolgu:
            h.fill = dolgu
        if k in PARA_KOLONLARI:
            h.number_format = PARA_FMT
        elif k in ONDALIK_KOLONLAR:
            h.number_format = ONDALIK_FMT
        elif k in YUZDE_KOLONLARI:
            h.number_format = YUZDE_FMT
        elif k in SAYI_KOLONLARI:
            h.number_format = "#,##0"


def rapor_uret(yol, ay_adi, yil, satirlar, amazon_satirlari=None,
               eslesmeyen_maliyet=None):
    """satirlar: [{magaza, ciro, vergi, reklam, kargo_musteri, kargo,
                   adet, ilave_odeme, upgrade}]"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Rapor"

    # Başlık satırı (turuncu şablon)
    for k, ad in enumerate(BASLIKLAR, start=1):
        h = ws.cell(row=1, column=k, value=ad)
        h.fill = TURUNCU
        h.font = BEYAZ_KALIN
        h.alignment = Alignment(wrap_text=True, vertical="center",
                                horizontal="center" if k > 1 else "left")
        h.border = KENARLIK
    ws.row_dimensions[1].height = 42
    ws.freeze_panes = "B2"

    genislikler = [24, 11, 10, 10, 10, 12, 11, 11, 10, 4, 10, 10, 11, 9, 9, 11, 9]
    for k, g in enumerate(genislikler, start=1):
        ws.column_dimensions[get_column_letter(k)].width = g

    # Ay bloğu başlığı
    r = 2
    ay_h = ws.cell(row=r, column=1, value=f"{ay_adi.upper()} {yil}")
    ay_h.font = Font(bold=True, size=12)
    _stil(ws, r, dolgu=ACIK_GRI)
    ay_h.font = Font(bold=True, size=12)
    r += 1

    ilk_veri = r
    for s in satirlar:
        ws.cell(row=r, column=1, value=s["magaza"])
        ws.cell(row=r, column=2, value=round(s.get("ciro") or 0, 2))
        ws.cell(row=r, column=4, value=round(s.get("vergi") or 0, 2))
        ws.cell(row=r, column=5, value=round(s.get("reklam") or 0, 2))
        ws.cell(row=r, column=6, value=round(s.get("kargo_musteri") or 0, 2))
        ws.cell(row=r, column=9, value=round(s.get("kargo") or 0, 2))
        # J ("P") kolonu kararla boş bırakılıyor
        ws.cell(row=r, column=11, value=s.get("adet") or 0)
        ws.cell(row=r, column=12, value=round(s.get("ilave_odeme") or 0, 2))
        ws.cell(row=r, column=17, value=s.get("upgrade") or 0)
        # Formüller (ekip hücreye tıklayıp kontrol edebilsin)
        ws.cell(row=r, column=3, value=_formul_bolme(f"B{r}", f"K{r}"))
        ws.cell(row=r, column=7, value=_formul_bolme(f"F{r}", f"K{r}"))
        ws.cell(row=r, column=8, value=_formul_bolme(f"(F{r}-I{r})", f"K{r}"))
        ws.cell(row=r, column=13, value=f"=B{r}-D{r}-E{r}-I{r}")
        ws.cell(row=r, column=14, value=f'=IF(N(B{r})=0,"",E{r}/B{r})')
        ws.cell(row=r, column=15, value=f'=IF(N(B{r})=0,"",D{r}/B{r})')
        ws.cell(row=r, column=16, value=_formul_bolme(f"M{r}", f"K{r}"))
        _stil(ws, r)
        r += 1
    son_veri = r - 1

    # TOPLAM satırı
    if son_veri >= ilk_veri:
        ws.cell(row=r, column=1, value="TOPLAM")
        for k in [2, 4, 5, 6, 9, 11, 12, 13, 17]:
            harf = get_column_letter(k)
            ws.cell(row=r, column=k,
                    value=f"=SUM({harf}{ilk_veri}:{harf}{son_veri})")
        ws.cell(row=r, column=3, value=_formul_bolme(f"B{r}", f"K{r}"))
        ws.cell(row=r, column=7, value=_formul_bolme(f"F{r}", f"K{r}"))
        ws.cell(row=r, column=8, value=_formul_bolme(f"(F{r}-I{r})", f"K{r}"))
        # Yüzde kolonlarında toplam ciro üzerinden ağırlıklı değer
        ws.cell(row=r, column=14, value=f'=IF(N(B{r})=0,"",E{r}/B{r})')
        ws.cell(row=r, column=15, value=f'=IF(N(B{r})=0,"",D{r}/B{r})')
        ws.cell(row=r, column=16, value=_formul_bolme(f"M{r}", f"K{r}"))
        _stil(ws, r, kalin=True, dolgu=ACIK_GRI)
        r += 2

    # Rapor Dışı (Amazon) bölümü
    if amazon_satirlari:
        b = ws.cell(row=r, column=1, value="RAPOR DIŞI (AMAZON)")
        b.font = Font(bold=True, size=11)
        ws.cell(row=r, column=2, value="Sipariş/Gönderi")
        ws.cell(row=r, column=3, value="Kargo Harcaması")
        for k in (1, 2, 3):
            ws.cell(row=r, column=k).fill = ACIK_GRI
            ws.cell(row=r, column=k).border = KENARLIK
            ws.cell(row=r, column=k).font = KALIN
        r += 1
        for a in amazon_satirlari:
            ws.cell(row=r, column=1, value=a["magaza"]).border = KENARLIK
            ws.cell(row=r, column=2, value=a.get("siparis", 0)).border = KENARLIK
            m = ws.cell(row=r, column=3, value=round(a.get("kargo") or 0, 2))
            m.border = KENARLIK
            m.number_format = PARA_FMT
            r += 1
        r += 1

    if eslesmeyen_maliyet and eslesmeyen_maliyet.get("adet"):
        n = ws.cell(row=r, column=1, value=(
            f"Not: {eslesmeyen_maliyet['adet']} gönderinin mağazası "
            f"eşleştirilemedi (toplam {eslesmeyen_maliyet['maliyet']:.2f}$ kargo "
            "maliyeti rapora dahil edilmedi)."))
        n.font = Font(italic=True, color="990000")

    wb.save(yol)
    return yol
