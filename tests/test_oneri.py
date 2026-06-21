# Öğrenen kategori önericisi testleri.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lazer import oneri


def test_tokenize_stop_ve_kisa_eler():
    t = oneri.tokenize("Personalized Custom Wine Glass for Dad")
    assert "wine" in t and "glass" in t
    assert "personalized" not in t and "custom" not in t  # STOP
    assert "for" not in t and "dad" not in t              # STOP
    assert all(len(x) > 2 for x in t)


def test_model_ve_oner_temel():
    ciftler = [
        ("Custom Wine Glass with Name", "WineGlass"),
        ("Engraved Wine Glass Gift", "WineGlass"),
        ("Personalized Beer Mug Handle", "BeerMug"),
        ("Beer Mug Stein Gift", "BeerMug"),
    ]
    model = oneri.model_kur(ciftler)
    assert oneri.oner("A new wine glass", model, 1)[0][0] == "WineGlass"
    assert oneri.oner("Cool beer mug", model, 1)[0][0] == "BeerMug"


def test_oner_bos_sinyalsiz():
    model = oneri.model_kur([("Wine Glass", "WineGlass")])
    assert oneri.oner("", model) == []
    assert oneri.oner("Zzzz Qqqq", model) == []   # bilinmeyen token → öneri yok


def test_agirlik_etkisi():
    # Aynı token iki kategoriye gidiyor; ağırlık baskın kategoriyi öne çeker.
    ciftler = [
        ("custom tumbler travel", "20 oz Tmblr", 100),
        ("custom tumbler wine", "Wine Tmblr", 1),
    ]
    model = oneri.model_kur(ciftler)
    # "tumbler" token'ı her ikisinde; "travel" yalnız ilkinde → ilk öne çıkar
    assert oneri.oner("custom tumbler travel mug", model, 1)[0][0] == "20 oz Tmblr"


def test_model_katalogdan_kategori_oncelik():
    katalog = {
        "S1": {"ornek_ad": "Custom Wine Glass", "kategori": "Wallet",
               "auto_kategori": "WineGlass", "adet": 5},
        "S2": {"ornek_ad": "Beer Mug Stein", "kategori": None,
               "auto_kategori": "BeerMug", "adet": 3},
    }
    model = oneri.model_katalogdan(katalog)
    # S1 öğrenilmiş kategori 'Wallet' kullanılmalı (auto 'WineGlass' değil)
    assert "Wallet" in model["kat_top"]
    assert "WineGlass" not in model["kat_top"]
    assert "BeerMug" in model["kat_top"]
