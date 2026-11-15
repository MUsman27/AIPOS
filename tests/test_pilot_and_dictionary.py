from pathlib import Path
from decimal import Decimal
from fastapi.testclient import TestClient

from app.server import app
from app.pdf_import.dictionary import (
    get_item_by_code,
    translate_urdu_to_english,
    normalize_urdu,
    clean_urdu_display,
)
from app.pdf_import.read import read_price_list
from app.pdf_import.parse import classify_price_list, manufacturer_name


def test_helper_dictionary_lookup_by_code():
    item = get_item_by_code("01001001")
    assert item is not None
    assert "AIR FILTER" in item["description_en"]
    assert item["manufacturer"] == "RP Parts"

    item_cp = get_item_by_code("36-0103-K0")
    assert item_cp is not None
    assert "AIR FILTER" in item_cp["description_en"]
    assert item_cp["manufacturer"] == "C.P"


def test_helper_dictionary_translates_urdu_to_english():
    # Translation from code
    assert "AIR FILTER" in translate_urdu_to_english("", code="01001001")

    # Translation from known phrase
    en = translate_urdu_to_english("ائیر فلٹر", model="CD70")
    assert "Air Filter" in en
    assert "CD70" in en

    # Translation of parts terms
    assert "Spark Plug Cap" in translate_urdu_to_english("پلک کیپ 125/70")
    assert "Nut" in translate_urdu_to_english("نٹ پیٹل", model="CG125")
    assert "Chain" in translate_urdu_to_english("چین اولڈ")
    assert "Petrol Pipe" in translate_urdu_to_english("پٹرول پائپ")


def test_classify_pilot_price_list():
    name, kind = classify_price_list("pilot price updated 49026 (1).pdf", "Pilot\n04-09-2026\nCell: 0333-1313513")
    assert name == "Pilot"
    assert kind == "pilot"


def test_read_pilot_price_list_end_to_end():
    pilot_pdf = Path(r"D:\Ivote\fff\AA\AIPOS\AIPOS\Itemlisting\pilot price updated 49026 (1).pdf")
    if not pilot_pdf.exists():
        return

    name, items = read_price_list(pilot_pdf)
    assert name == "Pilot"
    assert len(items) == 137

    # Check first item (Plug Cap)
    first = items[0]
    assert first.item_code == "1"
    assert first.purchase_price == Decimal("620.00")
    assert first.description_en  # Must not be empty

    # Check sample items have prices matching the list
    by_code = {it.item_code: it for it in items}
    assert by_code["1"].purchase_price == Decimal("620.00")
    assert by_code["2"].purchase_price == Decimal("480.00")
    assert by_code["3"].purchase_price == Decimal("140.00")
    assert by_code["37"].purchase_price == Decimal("1220.00")
    assert by_code["39"].purchase_price == Decimal("290.00")
    assert by_code["46"].purchase_price == Decimal("311.00")
    assert by_code["47"].purchase_price == Decimal("325.00")
    assert by_code["63"].purchase_price == Decimal("295.00")
    assert by_code["136"].purchase_price == Decimal("80.00")


def test_api_parse_pdf_with_pilot_file():
    pilot_pdf = Path(r"D:\Ivote\fff\AA\AIPOS\AIPOS\Itemlisting\pilot price updated 49026 (1).pdf")
    if not pilot_pdf.exists():
        return

    client = TestClient(app)
    with open(pilot_pdf, "rb") as f:
        response = client.post(
            "/api/pdf/parse",
            files={"file": (pilot_pdf.name, f.read(), "application/pdf")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["manufacturer_name"] == "Pilot"
    assert payload["total_items"] == 137
    assert len(payload["items"]) == 137

    # Ensure all items have an English name (not empty or unreadable copy)
    items = payload["items"]
    for it in items:
        assert it["description_en"], f"Item {it['item_code']} has empty description_en"
        assert it["purchase_price"] >= 0
