"""Price-list parsers, using word positions instead of PDF files."""

from decimal import Decimal

from app.pdf_import.parse import (
    Word,
    classify_price_list,
    manufacturer_name,
    parse_cp,
    parse_mitsuboshi,
    parse_ocr_text,
    parse_rp,
    parse_side_by_side,
    parse_spider,
)


def word(text: str, x: float, y: float, width: float = 20) -> Word:
    return Word(text, x, y, x + width, y + 8)


def test_cp_row_uses_cp_column_as_purchase_price() -> None:
    words = [
        word("1", 22, 99, 8),
        word("36-0103-K0", 36, 99, 40),
        word("CD70-EURO2", 72, 99, 36),
        word("AIR", 112, 99, 16),
        word("FILTER", 130, 99, 24),
        word("فلیر", 410, 99, 16),
        word("ائیر", 430, 100, 16),
        word("180", 440, 99, 16),
        word("85", 476, 99, 12),
        word("6,300", 501, 99, 24),
        word("180", 533, 99, 16),
        word("2", 565, 99, 8),
    ]
    items = parse_cp(words)
    assert len(items) == 1
    item = items[0]
    assert item.item_code == "36-0103-K0"
    assert item.model == "CD70-EURO2"
    assert item.description_en == "AIR FILTER"
    assert item.description_ur == "ائیر فلیر"
    assert item.purchase_price == Decimal("85.00")


def test_rp_price_is_trade_price_not_scheme() -> None:
    words = [
        word("1", 60, 120, 8),
        word("01001001", 78, 120, 40),
        word("AIR", 193, 120, 16),
        word("FILTER", 210, 120, 24),
        word("RP", 240, 120, 12),
        word("CD70", 339, 120, 20),
        word("CDI", 362, 120, 16),
        word("فل58", 430, 120, 24),
        word("29+1", 538, 124, 20),
    ]
    items = parse_rp(words, urdu_lines=[(120, "ایئر فلٹر 58")])
    assert len(items) == 1
    item = items[0]
    assert item.item_code == "01001001"
    assert item.description_en == "AIR FILTER RP"
    assert item.model == "CD70 CDI"
    assert item.description_ur == "ایئر فلٹر"
    assert item.purchase_price == Decimal("58.00")


def test_spider_and_mitsuboshi_keep_model_out_of_the_price() -> None:
    spider = parse_spider(
        [
            word("3", 66, 111, 8),
            word("BEARING", 152, 111, 36),
            word("6000", 396, 111, 20),
            word("2RS", 421, 111, 16),
            word("50", 478, 111, 12),
        ]
    )
    assert spider[0].description_en == "BEARING"
    assert spider[0].model == "6000 2RS"
    assert spider[0].purchase_price == Decimal("50.00")

    mitsuboshi = parse_mitsuboshi(
        [
            word("1", 61, 133, 8),
            word("Air", 150, 133, 16),
            word("Filter", 170, 133, 24),
            word("CD70", 302, 133, 20),
            word("Euro", 329, 133, 20),
            word("فلٹر", 416, 133, 18),
            word("ائير", 436, 133, 18),
            word("98", 493, 133, 12),
        ]
    )
    assert mitsuboshi[0].description_en == "Air Filter"
    assert mitsuboshi[0].model == "CD70 Euro"
    assert mitsuboshi[0].description_ur == "ائير فلٹر"
    assert mitsuboshi[0].purchase_price == Decimal("98.00")


def test_side_by_side_uses_the_rate_beside_the_description() -> None:
    words = [
        word("میرر", 430, 180, 24),
        word("CD-70", 390, 180, 28),
        word("148", 300, 180, 16),
        word("80", 250, 180, 14),
        word("1", 520, 180, 8),
        word("فیلٹر", 80, 180, 24),
        word("CG125", 40, 180, 28),
        word("390", 10, 180, 16),
    ]
    items = parse_side_by_side(words, page_width=600)
    by_price = {item.purchase_price: item for item in items}
    assert by_price[Decimal("148.00")].model == "CD-70"
    assert by_price[Decimal("148.00")].description_ur == "میرر"
    assert by_price[Decimal("148.00")].description_en == ""
    assert by_price[Decimal("390.00")].model == "CG125"


def test_ocr_lines_keep_purchase_price_and_model() -> None:
    mgp = parse_ocr_text("فٹ بار 70 CD 430", price_at="end")
    assert mgp[0].purchase_price == Decimal("430.00")
    assert mgp[0].model == "CD-70"
    assert mgp[0].description_ur == "فٹ بار"
    assert mgp[0].description_en == ""

    perfect = parse_ocr_text("306 CG-125 MATE BLACK 934", price_at="start")
    assert perfect[0].purchase_price == Decimal("306.00")
    assert perfect[0].model == "CG-125"
    assert perfect[0].description_ur == "MATE BLACK"
    assert perfect[0].description_en == ""

    mixed = parse_ocr_text("فٹ بار MATE BLACK 70 CD 430", price_at="end")
    assert mixed[0].model == "CD-70"
    assert mixed[0].description_ur == "فٹ بار MATE BLACK"
    assert mixed[0].description_en == ""

    pilot = parse_ocr_text("001 پک یپ 125/70 JF 58 580", price_at="start")
    assert pilot[0].purchase_price == Decimal("58.00")
    assert pilot[0].model == "125/70"
    assert parse_ocr_text("Sai coz 80", price_at="start") == []
    assert parse_ocr_text("3135 OEM", price_at="start") == []


def test_renamed_upload_matches_the_existing_manufacturer() -> None:
    name, kind = classify_price_list(
        "new cp list.pdf",
        "CUSTOMER PRICE LIST\nITEM CODE 36-0103-K0 CD70",
    )
    assert name == "C.P"
    assert kind == "cp"
    spider, spider_kind = classify_price_list(
        "rates.pdf",
        "SPIDER BRAND RATE LIST",
    )
    assert spider == "Spider"
    assert spider_kind == "spider"


def test_manufacturer_names_follow_the_printed_brand() -> None:
    assert manufacturer_name("UPDATE LIST.pdf") == "Spider"
    assert manufacturer_name("updated price list 20-6-2026.pdf") == "Mitsuboshi"
    assert manufacturer_name("Updated Rate List 01-05-2026.pdf") == "Pilot"
    assert manufacturer_name("C.P LIST (29-Aug-2026).pdf") == "C.P"
