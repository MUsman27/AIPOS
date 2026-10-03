"""Tesseract OCR for price-list pages whose text layer is missing or encoded."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

from app.pdf_import.parse import Word

_TESSDATA = Path(
    os.environ.get("AIPOS_TESSDATA_DIR", Path(__file__).resolve().parents[3] / ".tessdata")
)
_TESSERACT = Path(
    os.environ.get("AIPOS_TESSERACT_EXE", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
)


def configure_tesseract() -> None:
    os.environ["TESSDATA_PREFIX"] = str(_TESSDATA)
    if _TESSERACT.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(_TESSERACT)
    elif shutil.which("tesseract") is None:
        raise RuntimeError(
            "Tesseract OCR is not installed. Install the UB Mannheim build "
            "and keep English and Urdu trained data in pos/.tessdata."
        )


def ocr_text(page, clip, *, lang: str = "urd+eng", psm: int = 4) -> str:
    """OCR a page region and return plain text."""
    configure_tesseract()
    zoom = 3.1
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    return pytesseract.image_to_string(
        image,
        lang=lang,
        config=f"--oem 1 --psm {psm}",
    )


def ocr_words(page, *, lang: str = "eng+urd") -> list[Word]:
    """OCR a whole PDF page. Coordinates are returned in PDF points."""
    return _recognize(page, clip=None, lang=lang)


def ocr_urdu_lines(page, clip) -> list[tuple[float, str]]:
    """OCR one column and return (pdf y, line text) in reading order."""
    words = _recognize(page, clip=clip, lang="urd+eng")
    if not words:
        return []
    grouped: dict[float, list[Word]] = {}
    for word in words:
        key = round(word.y0 / 6) * 6
        grouped.setdefault(key, []).append(word)
    lines: list[tuple[float, str]] = []
    for key in sorted(grouped):
        ordered = sorted(grouped[key], key=lambda word: -word.x0)
        text = " ".join(word.text for word in ordered)
        text = " ".join(text.split())
        if text:
            lines.append((key, text))
    return lines


def _recognize(page, *, clip, lang: str) -> list[Word]:
    configure_tesseract()
    zoom = 2.2
    matrix = pymupdf.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    data = pytesseract.image_to_data(
        image,
        lang=lang,
        config="--psm 6",
        output_type=pytesseract.Output.DICT,
    )
    origin_x = 0.0 if clip is None else float(clip.x0)
    origin_y = 0.0 if clip is None else float(clip.y0)
    words: list[Word] = []
    texts = data["text"]
    for index, raw in enumerate(texts):
        text = str(raw).strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1
        if confidence < 20:
            continue
        x0 = origin_x + float(data["left"][index]) / zoom
        y0 = origin_y + float(data["top"][index]) / zoom
        x1 = x0 + float(data["width"][index]) / zoom
        y1 = y0 + float(data["height"][index]) / zoom
        words.append(Word(text, x0, y0, x1, y1, "ocr"))
    return words
