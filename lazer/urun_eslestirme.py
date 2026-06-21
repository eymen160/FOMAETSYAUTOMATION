# Ürün/SKU eşleştirme: ShipStation kalem-bazlı satışından ürün adetlerini
# rapordaki kategori kolonlarına sınıflandırır. Öğrenen SKU sözlüğü +
# keyword kuralları. Denetlenmiş finansal motora dokunmaz (ayrı modül).
import json
import os
import re

from .yardimci import tr_kucuk, sayi
from .shipstation_csv import _csv_oku, _tarih, CsvHata
from .yardimci import kolon_bul

URUN_MAPPING_DOSYASI = "urun_mapping.json"
DIGER = "Diğer Ürün"

# Rapor ürün kolonları (form başlıklarıyla aynı sırada) + ek kategoriler.
# Sınıflandırma Item Name metninden; sıra önemlidir (spesifik → genel).
KURALLAR = [
    ("Damasc.Knife", [r"damascus"]),
    ("Olive Wood Knife", [r"olive\s*wood.*knife"]),
    ("Multi Knife", [r"multi.?tool|multi.?function|pocket knife|folding knife|"
                     r"hunting knife|utility knife|edc knife"]),
    ("Photo Frame", [r"photo frame|picture frame"]),
    # --- yüksek hacimli ek kategoriler (2026-06 ham veri analizinden) ---
    ("Cooling Towel", [r"cooling towel"]),
    ("Beach Towel", [r"beach towel|pool towel|swim towel|bachelorette towel|"
                     r"bridal.*towel|bride.*towel|team towel|sport.*towel|"
                     r"monogram.*towel|custom.*towel|personali[sz]ed.*towel|"
                     r"stripe.*towel|\btowel\b"]),
    ("Blanket", [r"blanket|throw blanket|fleece blanket|sherpa"]),
    ("Puzzle", [r"puzzle|jigsaw"]),
    ("Name Plate", [r"name\s*plate|nameplate|desk\s*name|desk\s*plate|"
                    r"name\s*wedge|desk\s*wedge"]),
    ("T-Shirt", [r"\bt-?shirts?\b|\btees?\b|\bshirts?\b|sweat ?shirt|hoodie"]),
    ("Luggage Tag", [r"luggage tag|bag tag|suitcase tag"]),
    ("Card & Dice Set", [r"card\s*&?\s*dice|dice set"]),
    ("BBQ Set", [r"\bbbq\b|barbecue|grill (set|tool|kit)|grilling (set|tool)"]),
    ("Shot Glass", [r"shot glass"]),
    ("Phone Stand", [r"phone stand|phone holder|phone dock|phone cradle"]),
    ("Cord Case", [r"cord case|cable case|cord organizer|cable organizer|"
                   r"cord keeper|cord roll"]),
    ("Photo Clip", [r"photo clip|visor clip|car visor"]),
    ("Keychain", [r"keychain|key chain|key ?ring|key fob|keyfob"]),
    # --- ikinci tur: kalan yüksek hacimli kategoriler ---
    ("Hat", [r"\bhat\b|\bcap\b|trucker|snapback|beanie|baseball cap|dad hat|"
             r"leather patch hat"]),
    ("Desk Organizer", [r"desk organi[sz]er|office organi[sz]er|"
                        r"pen organi[sz]er|stationery organi[sz]er|desk caddy|"
                        r"office desk accessor|wood desk organi[sz]er"]),
    ("Whiskey Stones", [r"whiskey stones?|whisky stones?|chilling stones?|"
                        r"ice stones?|whiskey rocks?|whisky rocks?"]),
    ("Pen Set", [r"pen set|pen holder|wood pen|wooden pen|engraved pen|"
                 r"fountain pen|\bpen\b"]),
    ("Mouse Pad", [r"mouse ?pad|desk pad|desk mat"]),
    ("Rug", [r"\brug\b|area rug|floor mat|door ?mat|chenille|step rug"]),
    ("Crossbody Bag", [r"crossbody|cross body|sling bag|phone pouch|"
                       r"phone bag|phone crossbody|leather sling|half moon bag|"
                       r"crescent.*bag"]),
    ("Cooler Bag", [r"cooler bag|cooler backpack|insulated bag|lunch bag|"
                    r"cooler tote|insulated cooler"]),
    ("Beer Can Glass", [r"can glass|beer can glass"]),
    ("Grooming Set", [r"manicure set|manicure kit|nail care|nail clipper|"
                      r"grooming kit|grooming set"]),
    ("Ammo Can", [r"ammo can|ammunition can|ammo box"]),
    ("Cigar Case", [r"cigar case|cigar box|cigar holder|cigar ashtray|"
                    r"cigar humidor|\bhumidor\b|cigar travel"]),
    ("Pizza Board", [r"pizza board|pizza paddle|pizza peel"]),
    ("Fabric", [r"\bfabric\b|quilting cotton|by the yard|fat quarter|"
                r"fleece velvet|sewing fabric"]),
    ("Pet Bowl", [r"pet bowl|dog bowl|cat bowl|dog cat bowl|pet feeder|"
                  r"food bowl"]),
    ("Cribbage Set", [r"cribbage"]),
    ("Apron", [r"\bapron\b"]),
    ("Tapestry", [r"tapestry|woven throw|woven wall|wall hanging"]),
    ("Clipboard", [r"clipboard"]),
    ("Ring Dish", [r"ring dish|jewelry dish|trinket dish|ring holder"]),
    ("Christmas Stocking", [r"christmas stocking|holiday stocking|"
                            r"\bstocking\b"]),
    ("Engraving Upgrade", [r"engraving upgrade|engrave upgrade|express cargo|"
                           r"new upgrade|two side engrave|\bupgrade\b"]),
    ("Shipping Upgrade", [r"shipping fee|shipping price|shipping cost|"
                          r"shipping service|day shipping|express shipping|"
                          r"expedited|\bups\b|\bfedex\b|\bdhl\b|priority mail|"
                          r"rush order|\breship\b|shipping price"]),
    ("Pocket Mirror", [r"pocket mirror|compact mirror"]),
    ("Cake Pan", [r"cake pan"]),
    ("Cutting Board", [r"cutting board|charcuterie|chopping board"]),
    ("BakingDish", [r"baking dish|casserole dish"]),
    ("Coaster", [r"coaster"]),
    ("LedLamp", [r"led lamp|night light|moon lamp|led light|desk lamp|\blamp\b"]),
    ("Flower Pot", [r"flower pot|planter|plant pot|succulent pot"]),
    ("Passp.Hold", [r"passport"]),
    ("CanCooler", [r"can cooler|can holder|beverage holder|beer holder|koozie|"
                   r"drink holder|bottle holder|can sleeve"]),
    ("CheckBook", [r"checkbook|check book"]),
    ("PocketWatch", [r"pocket watch"]),
    ("Zipper Portfolio", [r"zipper.*portfolio|zippered portfolio|zip portfolio"]),
    ("Portfolio", [r"portfolio|padfolio"]),
    ("JewTravl Case", [r"jewelry (box|case|travel|roll|organizer)|ring box|"
                       r"watch box|watch case"]),
    ("Wallet", [r"wallet|card holder|cardholder|money clip|card case"]),
    ("Journal", [r"journal|notebook|diary|composition book"]),
    ("SnapUpTray", [r"valet tray|catchall|catch all|catch-all|snap tray|"
                    r"leather tray|nightstand tray|dump tray|\btray\b"]),
    ("DoppKit T-Bag", [r"toiletry|dopp kit|\bdopp\b|shaving bag|wash bag|"
                       r"\bt-?bag\b|cosmetic bag"]),
    ("Flask", [r"\bflask\b|hip flask"]),
    ("WhiskeyGlass", [r"whiskey glass|whisky glass|rocks glass|bourbon glass|"
                      r"scotch glass|old fashioned glass"]),
    ("ChampaFlute", [r"champagne|\bflute\b"]),
    ("WineGlass-SL", [r"stemless wine|stemless glass"]),
    ("WineGlass", [r"wine glass"]),
    ("BeerMug", [r"beer mug|beer stein|pint glass|beer glass|\bstein\b"]),
    ("Glass Cofe-Mug", [r"glass coffee mug|glass mug|glass latte|glass cofe"]),
    ("Coffee Mug", [r"coffee mug|ceramic mug|latte mug|camp mug|enamel mug|"
                    r"\bmug\b"]),
    ("Wine Tmblr", [r"wine tumbler"]),
    ("Simple Modern Tumbler", [r"simple modern"]),
    ("20 oz  Lether Tmblr", [r"leather.{0,8}tumbler|leatherette tumbler"]),
    ("22oz Skin Tmblr", [r"22\s?oz|skinny tumbler"]),
    ("40 oz Tmblr", [r"40\s?oz"]),
    ("20 oz Tmblr", [r"20\s?oz|30\s?oz|tumbler with handle|insulated tumbler|"
                     r"travel tumbler|\btumbler\b|\btmblr\b"]),
    ("Bottle Opener", [r"bottle opener"]),
    ("Water Bottle", [r"water bottle|sports bottle|insulated bottle|"
                      r"names? bottle|\bbottle\b"]),
    ("Lighter", [r"lighter"]),
    ("Ornoment", [r"ornament|ornoment"]),
    ("Coffee Mug", [r"\bcup\b"]),  # son çare: jenerik "cup"
]
_DERLI = [(k, [re.compile(p, re.I) for p in ps]) for k, ps in KURALLAR]

# Rapor kolon başlıkları (master ürün başlıklarıyla eşleşen kanonik liste)
KATEGORILER = []
for _k, _ in KURALLAR:
    if _k not in KATEGORILER:
        KATEGORILER.append(_k)


def yukle(yol=URUN_MAPPING_DOSYASI):
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    return {}


def kaydet(eslesmeler, yol=URUN_MAPPING_DOSYASI):
    mevcut = yukle(yol)
    mevcut.update({str(k).strip(): v for k, v in eslesmeler.items()})
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(mevcut, f, ensure_ascii=False, indent=2, sort_keys=True)
    return mevcut


def siniflandir(item_name, sku, mapping=None):
    """SKU sözlüğü (öğrenilmiş) önce; sonra keyword kuralları; yoksa None.
    None = 'Diğer Ürün' kovasına gider ama öğrenilebilir olarak işaretlenir."""
    mapping = mapping or {}
    sku_k = (sku or "").strip()
    if sku_k and sku_k in mapping:
        return mapping[sku_k]
    ad = item_name or ""
    for kategori, desenler in _DERLI:
        for d in desenler:
            if d.search(ad):
                return kategori
    return None


KALEM_KOLONLARI = {
    "store": ["Store"],
    "item_name": ["Item Name"],
    "qty": ["Item Quantity", "Quantity", "Qty"],
    "sku": ["Item SKU", "SKU"],
    "ship_date": ["Ship Date", "Order Date"],
    "order_no": ["Order #", "Order Number"],
}


def kalem_format_mu(yol):
    """Dosya kalem-bazlı (Store + Item Name + Quantity) bir export mı?"""
    try:
        satirlar = _csv_oku(yol)
    except CsvHata:
        return False
    b = list(satirlar[0].keys())
    return (kolon_bul(b, ["Item Name"], prefix=False) is not None
            and kolon_bul(b, ["Store"], prefix=False) is not None
            and kolon_bul(b, ["Item Quantity", "Quantity"], prefix=False) is not None)


def kalem_isle(yol, ay=None, yil=None, mapping=None):
    """Kalem-bazlı satışı ShipStation mağaza adı bazında ürün kategorisine
    sınıflandırır.

    Dönüş:
      magaza_urun: {store: {kategori: adet}}  ('Diğer Ürün' dahil)
      bilinmeyen: {(sku, kisa_ad): adet}  — kategoriye girmemiş, öğrenilebilir
      kapsama: {toplam_adet, siniflanan_adet, oran}
    """
    mapping = mapping or yukle()
    satirlar = _csv_oku(yol)
    b = list(satirlar[0].keys())
    kmap = {k: kolon_bul(b, v, prefix=False) for k, v in KALEM_KOLONLARI.items()}
    if kmap["item_name"] is None or kmap["store"] is None or kmap["qty"] is None:
        raise CsvHata(
            "Kalem detayı dosyasında 'Store', 'Item Name' ve 'Quantity' "
            "kolonları gerekli. Bulunan kolonlar: " + ", ".join(b))

    magaza_urun = {}
    bilinmeyen = {}
    toplam = 0
    siniflanan = 0
    for r in satirlar:
        if ay and yil and kmap["ship_date"]:
            t = _tarih(r.get(kmap["ship_date"]))
            if t and (t.year != yil or t.month != ay):
                continue
        ad = (r.get(kmap["item_name"]) or "").strip()
        if not ad or ad.startswith("("):   # "(3 Items)" gibi gruplu satır
            continue
        store = (r.get(kmap["store"]) or "").strip()
        sku = (r.get(kmap["sku"]) or "").strip() if kmap["sku"] else ""
        q = int(sayi(r.get(kmap["qty"]), 1) or 1)
        toplam += q
        kategori = siniflandir(ad, sku, mapping)
        m = magaza_urun.setdefault(store, {})
        if kategori is None:
            m[DIGER] = m.get(DIGER, 0) + q
            anahtar = f"{sku} | {ad[:40]}" if sku else ad[:50]
            bilinmeyen[anahtar] = bilinmeyen.get(anahtar, 0) + q
        else:
            m[kategori] = m.get(kategori, 0) + q
            siniflanan += q
    return {
        "magaza_urun": magaza_urun,
        "bilinmeyen": dict(sorted(bilinmeyen.items(), key=lambda x: -x[1])),
        "kapsama": {"toplam": toplam, "siniflanan": siniflanan,
                    "oran": round(siniflanan / toplam, 3) if toplam else 0},
    }


def siparis_icerikleri(yol, ay=None, yil=None):
    """Çok-ürünlü siparişlerin içeriğini çözer ('5 item' → gerçek ürünler).
    Mağaza sahibinin Etsy'e manuel bakma ihtiyacını ortadan kaldırır.

    Dönüş:
      icerik: {order_no: {"store":.., "items":[{ad,sku,adet,kategori}],
                          "toplam_adet":..}}  — yalnızca çok-ürünlü siparişler
      tekil: tekil (1 ürünlü) sipariş sayısı
    """
    mapping = yukle()
    satirlar = _csv_oku(yol)
    b = list(satirlar[0].keys())
    kmap = {k: kolon_bul(b, v, prefix=False) for k, v in KALEM_KOLONLARI.items()}
    if kmap["order_no"] is None or kmap["item_name"] is None:
        raise CsvHata("Sipariş içeriği için 'Order #' ve 'Item Name' kolonları "
                      "gerekli. Bulunan: " + ", ".join(b))
    gruplu = {}
    for r in satirlar:
        if ay and yil and kmap["ship_date"]:
            t = _tarih(r.get(kmap["ship_date"]))
            if t and (t.year != yil or t.month != ay):
                continue
        ad = (r.get(kmap["item_name"]) or "").strip()
        if not ad or ad.startswith("("):
            continue
        ono = (r.get(kmap["order_no"]) or "").strip()
        if not ono:
            continue
        sku = (r.get(kmap["sku"]) or "").strip() if kmap["sku"] else ""
        q = int(sayi(r.get(kmap["qty"]), 1) or 1)
        g = gruplu.setdefault(ono, {"store": (r.get(kmap["store"]) or "").strip(),
                                    "items": [], "toplam_adet": 0})
        g["items"].append({"ad": ad, "sku": sku, "adet": q,
                           "kategori": siniflandir(ad, sku, mapping) or DIGER})
        g["toplam_adet"] += q
    icerik = {o: g for o, g in gruplu.items() if g["toplam_adet"] > 1}
    tekil = sum(1 for g in gruplu.values() if g["toplam_adet"] == 1)
    return {"icerik": icerik, "tekil": tekil,
            "coklu": len(icerik), "toplam_siparis": len(gruplu)}

