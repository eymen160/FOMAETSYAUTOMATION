# İçeriğe dayalı dosya türü tanıma testleri (sentetik başlıklar).
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from lazer import dosya_tani as dt


def _yaz(tmp_path, ad, basliklar):
    yol = tmp_path / ad
    with open(yol, "w", newline="", encoding="utf-8") as f:
        f.write(",".join(f'"{b}"' for b in basliklar) + "\n")
        f.write(",".join("x" for _ in basliklar) + "\n")
    return str(yol)


CASES = {
    "ozet": ["Order - Number", "Date - Order Date", "Market - Store Name",
             "Amount - Order Subtotal", "Amount - Order Tax",
             "Amount - Order Total", "Amount - Shipping Cost"],
    "kalem": ["Shipment #", "Order #", "Store", "Item Name",
              "Item Quantity", "Item SKU"],
    "shipments": ["Shipment #", "Order #", "Tracking #", "Service", "Store"],
    "sku_katalog": ["SKU", "Name", "Weight", "Category", "CustomsValue",
                    "FillSku", "WarehouseLocation"],
    "orders": ["Order #", "Order Date", "Order Total", "Tax Paid",
               "Shipping Paid", "Quantity"],
    "etsy_orders": ["Sale Date", "Order ID", "Number of Items", "Order Value",
                    "Order Total", "Card Processing Fees", "Order Net"],
    "etsy_items": ["Sale Date", "Item Name", "Quantity", "Price",
                   "Transaction ID", "Listing ID", "Order ID", "SKU"],
    "etsy_payments": ["Payment ID", "Buyer Name", "Order ID", "Gross Amount",
                      "Fees", "Net Amount", "VAT Amount"],
    "etsy_listings": ["TITLE", "DESCRIPTION", "PRICE", "QUANTITY", "TAGS",
                      "MATERIALS", "SKU"],
    "reklam": ["Date", "Store", "Advertising", "Ad Spend", "Clicks"],
}


@pytest.mark.parametrize("beklenen,basliklar", list(CASES.items()))
def test_tani(tmp_path, beklenen, basliklar):
    yol = _yaz(tmp_path, f"{beklenen}.csv", basliklar)
    assert dt.tani(yol) == beklenen


def test_bilinmeyen(tmp_path):
    yol = _yaz(tmp_path, "x.csv", ["Foo", "Bar", "Baz"])
    assert dt.tani(yol) == "bilinmiyor"


def test_etsy_items_kalemden_ayrilir(tmp_path):
    # Etsy items'ta Store YOK → kalem değil etsy_items olmalı
    yol = _yaz(tmp_path, "x.csv",
               ["Item Name", "Quantity", "Transaction ID", "Order ID", "SKU"])
    assert dt.tani(yol) == "etsy_items"


def test_ozet_kalemden_once(tmp_path):
    # Hem Amount-Order Total hem Item Name olsa bile özet önceliklidir
    yol = _yaz(tmp_path, "x.csv",
               ["Market - Store Name", "Amount - Order Total", "Item Name",
                "Store", "Quantity"])
    assert dt.tani(yol) == "ozet"


def test_etiket_tum_turler_var():
    for tur in CASES:
        assert tur in dt.ETIKET
