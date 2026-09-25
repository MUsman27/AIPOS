"""Read one price-list PDF into manufacturer name and item rows."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from app.pdf_import.ocr import ocr_text, ocr_urdu_lines
from app.pdf_import.parse import (
    ParsedItem,
    Word,
    classify_price_list,
    dedupe_items,
    parse_cp,
    parse_mitsuboshi,
    parse_ocr_text,
    parse_rp,
    parse_spider,
)


def read_price_list(path: Path) -> tuple[str, list[ParsedItem]]:
    document = pymupdf.open(path)
    items: list[ParsedItem] = []
    try:
        first_text = document[0].get_text("text") if document.page_count else ""
        name, kind = classify_price_list(path.name, first_text)
        for index, page in enumerate(document):
            print(f"  page {index + 1}/{document.page_count}", flush=True)
            items.extend(_read_page(page, kind))
    finally:
        document.close()
    return name, dedupe_items(items)


def _read_page(page, kind: str) -> list[ParsedItem]:
    if kind == "cp":
        return parse_cp(_text_words(page))
    if kind == "rp":
        clip = pymupdf.Rect(400, 90, 510, page.rect.height - 24)
        return parse_rp(_text_words(page), ocr_urdu_lines(page, clip))
    if kind == "spider":
        clip = pymupdf.Rect(250, 40, 390, page.rect.height - 24)
        return parse_spider(_text_words(page), ocr_urdu_lines(page, clip))
    if kind == "mitsuboshi":
        clip = pymupdf.Rect(400, 100, 485, page.rect.height - 24)
        return parse_mitsuboshi(_text_words(page), ocr_urdu_lines(page, clip))
    if kind == "mgp":
        return _ocr_halves(page, price_at="end", y0=70)
    if kind == "bands":
        return _ocr_bands(page)
    return []


def _ocr_halves(page, *, price_at: str, y0: float) -> list[ParsedItem]:
    width = float(page.rect.width)
    height = float(page.rect.height)
    midpoint = width / 2
    clips = (
        pymupdf.Rect(0, y0, midpoint + 8, height - 8),
        pymupdf.Rect(midpoint - 8, y0, width, height - 8),
    )
    items: list[ParsedItem] = []
    for clip in clips:
        items.extend(parse_ocr_text(ocr_text(page, clip), price_at=price_at))
    return items


def _ocr_bands(page) -> list[ParsedItem]:
    width = float(page.rect.width)
    height = float(page.rect.height)
    midpoint = width / 2
    items: list[ParsedItem] = []
    y = 110.0
    while y < height - 30:
        bottom = min(height - 6, y + 150)
        for x0, x1 in ((8, midpoint + 6), (midpoint - 6, width - 8)):
            clip = pymupdf.Rect(x0, y, x1, bottom)
            items.extend(parse_ocr_text(ocr_text(page, clip), price_at="start"))
        y += 120
    return items


def _text_words(page) -> list[Word]:
    return [
        Word(word[4], word[0], word[1], word[2], word[3], "text")
        for word in page.get_text("words")
    ]
