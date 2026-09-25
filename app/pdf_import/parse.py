"""Turn price-list words into catalog rows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

_TWOPLACES = Decimal("0.01")
_CP_CODE = re.compile(r"^\d{2}-[0-9A-Z]{4}-[0-9A-Z]+$", re.IGNORECASE)
_RP_CODE = re.compile(r"^\d{5,8}$")
_AMOUNT = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$|^\d+(?:\.\d+)?$")
_MODEL_HINT = re.compile(
    r"^(CD|CG|JH|UD|DYL|MB|GS|LF|EURO|UNITED|DELUXE|UNIVERSAL|YAMAHA|QINGQI|SOHRAB|STAR|HERO|OEM)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    source: str = "text"

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass(slots=True)
class ParsedItem:
    description_en: str
    purchase_price: Decimal
    description_ur: str | None = None
    model: str | None = None
    item_code: str | None = None


def manufacturer_name(filename: str) -> str:
    """Brand printed on the list, or the file name when the page has no brand."""
    known = {
        "C.P LIST (29-Aug-2026).pdf": "C.P",
        "MGP_PriceList.pdf": "MGP",
        "perfect autos rate list.pdf": "Perfect Autos",
        "Power Ride price list.pdf": "Power Ride",
        "Price List Rp Parts 01-7-2026.pdf": "RP Parts",
        "UPDATE LIST.pdf": "Spider",
        "updated price list 20-6-2026.pdf": "Mitsuboshi",
        "Updated Rate List 01-05-2026.pdf": "Pilot",
    }
    if filename in known:
        return known[filename]
    stem = filename.rsplit(".", 1)[0].strip()
    return stem or filename


def template_for(filename: str) -> str:
    return {
        "C.P LIST (29-Aug-2026).pdf": "cp",
        "MGP_PriceList.pdf": "mgp",
        "perfect autos rate list.pdf": "bands",
        "Power Ride price list.pdf": "bands",
        "Price List Rp Parts 01-7-2026.pdf": "rp",
        "UPDATE LIST.pdf": "spider",
        "updated price list 20-6-2026.pdf": "mitsuboshi",
        "Updated Rate List 01-05-2026.pdf": "bands",
    }.get(filename, "sides")


def classify_price_list(filename: str, page_text: str) -> tuple[str, str]:
    """Manufacturer and layout for a price list, including a renamed upload."""
    if template_for(filename) != "sides":
        return manufacturer_name(filename), template_for(filename)
    text = page_text.upper()
    if "SPIDER" in text:
        return "Spider", "spider"
    if "MITSUBOSHI" in text:
        return "Mitsuboshi", "mitsuboshi"
    if "POWER RIDE" in text:
        return "Power Ride", "bands"
    if re.search(r"\bPILOT\b", text):
        return "Pilot", "bands"
    if "PERFECT" in text:
        return "Perfect Autos", "bands"
    if "T.P" in text and "CODE" in text:
        return "RP Parts", "rp"
    if "ITEM CODE" in text or re.search(r"\d{2}-\d{4}-[A-Z0-9]+", page_text):
        return "C.P", "cp"
    if "MGP" in text or "MGP" in filename.upper():
        return "MGP", "mgp"
    readable = sum(char.isascii() and char.isalpha() for char in page_text)
    kind = "mgp" if readable < 40 else "bands"
    return manufacturer_name(filename), kind


def parse_amount(text: str) -> Decimal | None:
    cleaned = text.strip().replace(" ", "")
    if not _AMOUNT.fullmatch(cleaned):
        return None
    value = Decimal(cleaned.replace(",", ""))
    if value <= 0 or value >= Decimal("10000000"):
        return None
    return value.quantize(_TWOPLACES)


def split_script(text: str) -> tuple[str, str]:
    english: list[str] = []
    urdu: list[str] = []
    for char in text:
        code = ord(char)
        if char.isspace():
            english.append(" ")
            urdu.append(" ")
        elif 0x0600 <= code <= 0x06FF or 0x0750 <= code <= 0x077F:
            urdu.append(char)
        elif char.isascii():
            english.append(char)
    return _squash("".join(english)), _squash("".join(urdu))


def parse_cp(words: list[Word]) -> list[ParsedItem]:
    anchors = [word for word in words if _CP_CODE.fullmatch(word.text)]
    return _rows_around(anchors, words, _cp_item, tolerance=11)


def parse_rp(
    words: list[Word],
    urdu_lines: list[tuple[float, str]] | None = None,
) -> list[ParsedItem]:
    anchors = [
        word
        for word in words
        if _RP_CODE.fullmatch(word.text) and 40 <= word.x0 <= 170
    ]
    return _rows_around(
        anchors,
        words,
        lambda anchor, row: _rp_item(anchor, row, urdu_lines or []),
        tolerance=8,
    )


def parse_spider(
    words: list[Word],
    urdu_lines: list[tuple[float, str]] | None = None,
) -> list[ParsedItem]:
    return _parse_serial_table(
        words,
        price_min_x=450,
        model_min_x=360,
        urdu_lines=urdu_lines,
    )


def parse_mitsuboshi(
    words: list[Word],
    urdu_lines: list[tuple[float, str]] | None = None,
) -> list[ParsedItem]:
    return _parse_serial_table(
        words,
        price_min_x=460,
        model_min_x=280,
        urdu_lines=urdu_lines,
    )


def parse_side_by_side(words: list[Word], page_width: float) -> list[ParsedItem]:
    midpoint = page_width / 2
    right = [word for word in words if word.center_x >= midpoint]
    left = [word for word in words if word.center_x < midpoint]
    items: list[ParsedItem] = []
    for group in (right, left):
        for row in _bucket_rows(group, bucket=8):
            item = _side_row(row)
            if item is not None:
                items.append(item)
    return items


_MODEL_PATTERN = re.compile(
    r"(?i)(?:cd|cg|jh|ud|cp)\s*-?\s*\d{2,3}"
    r"|\d{2,3}\s+(?:cd|cg|jh|ud)\b(?!\s*-\s*\d)"
    r"|\d{2,3}\s*/\s*\d{2,3}"
    r"|\b(?:united|deluxe|dyl|universal|yamaha|qingqi|sohrab|star|hero)\b"
)


def parse_ocr_text(text: str, *, price_at: str) -> list[ParsedItem]:
    """Parse Tesseract lines from a motorcycle price list."""
    items: list[ParsedItem] = []
    for raw_line in text.splitlines():
        item = _parse_ocr_line(raw_line, price_at=price_at)
        if item is not None:
            items.append(item)
    return items


def _parse_ocr_line(raw_line: str, *, price_at: str) -> ParsedItem | None:
    line = raw_line.replace("|", " ")
    line = re.sub(r"[\[\]{}<>«»=_~]+", " ", line)
    line = " ".join(line.split())
    if len(line) < 3 or _is_header(line):
        return None
    models = [ _normalize_model(match.group()) for match in _MODEL_PATTERN.finditer(line) ]
    body = _MODEL_PATTERN.sub(" ", line)
    amounts = _amounts_in(body)
    if not amounts:
        return None
    price = _choose_price(amounts, price_at)
    if price is None:
        return None
    body = _remove_amount(body, price)
    body = re.sub(r"\b\d{1,4}\b", " ", body)
    # These lists have one description column. Urdu and English share that
    # cell, so the whole cell is stored in the Urdu description.
    combined = _clip(body, 500)
    _latin, arabic = split_script(combined)
    if not arabic and not re.search(r"[A-Za-z]{3,}", _latin) and not models:
        return None
    if price_at == "start" and not _band_row_is_usable(price, arabic, models):
        return None
    return _make_item(
        english=[],
        model=models,
        urdu=combined or None,
        price=price,
        item_code=None,
        blank_english=True,
    )


def _band_row_is_usable(price: Decimal, arabic: str, models: list[str]) -> bool:
    if price < 15 or price > 4000:
        return False
    if models:
        return True
    arabic_letters = sum(1 for char in arabic if "\u0600" <= char <= "\u06FF")
    return arabic_letters >= 4


def _amounts_in(text: str) -> list[Decimal]:
    amounts: list[Decimal] = []
    for match in re.finditer(r"\d{1,3}(?:,\d{3})+|\d+", text):
        amount = parse_amount(match.group())
        if amount is not None and amount >= 8:
            amounts.append(amount)
    return amounts


def _choose_price(amounts: list[Decimal], price_at: str) -> Decimal | None:
    if price_at == "start":
        for big in amounts:
            for small in amounts:
                if big > small and 8 <= (big / small) <= 12:
                    return small
        return amounts[0]
    return amounts[-1]


def _remove_amount(text: str, price: Decimal) -> str:
    rendered = f"{price:.2f}"
    whole = str(int(price)) if price == price.to_integral_value() else rendered
    with_commas = f"{int(price):,}" if price == price.to_integral_value() else whole
    for token in (with_commas, whole):
        updated = re.sub(rf"\b{re.escape(token)}\b", " ", text, count=1)
        if updated != text:
            return updated
    return text


def _normalize_model(token: str) -> str:
    compact = " ".join(token.split())
    reversed_model = re.fullmatch(r"(?i)(\d{2,3})\s*-?\s*(cd|cg|jh|ud)", compact)
    if reversed_model:
        return f"{reversed_model.group(2).upper()}-{reversed_model.group(1)}"
    normal = re.fullmatch(r"(?i)(cd|cg|jh|ud|cp)\s*-?\s*(\d{2,3})", compact)
    if normal:
        brand = normal.group(1).upper()
        if brand == "CP":
            brand = "CD"
        return f"{brand}-{normal.group(2)}"
    if compact.isascii():
        return compact.upper()
    return compact


def dedupe_items(items: list[ParsedItem]) -> list[ParsedItem]:
    kept: dict[tuple[str, ...], ParsedItem] = {}
    for item in items:
        if item.item_code:
            key = ("code", item.item_code.casefold())
        else:
            key = (
                "name",
                item.description_en.casefold(),
                (item.model or "").casefold(),
                (item.description_ur or "").casefold(),
            )
        kept[key] = item
    return list(kept.values())


def _rows_around(anchors, words, build, tolerance: float) -> list[ParsedItem]:
    if not anchors:
        return []
    assigned: dict[int, list[Word]] = {id(anchor): [] for anchor in anchors}
    for word in words:
        nearest = min(anchors, key=lambda anchor: abs(anchor.y0 - word.y0))
        if abs(nearest.y0 - word.y0) <= tolerance:
            assigned[id(nearest)].append(word)
    items: list[ParsedItem] = []
    for anchor in anchors:
        item = build(anchor, assigned[id(anchor)])
        if item is not None:
            items.append(item)
    return items


def _cp_item(anchor: Word, row: list[Word]) -> ParsedItem | None:
    english: list[str] = []
    model: list[str] = []
    urdu_words: list[Word] = []
    price: Decimal | None = None
    price_distance = 999.0
    for word in row:
        if word is anchor:
            continue
        if 460 <= word.center_x <= 510:
            amount = parse_amount(word.text)
            if amount is not None:
                distance = abs(word.center_x - 482)
                if distance < price_distance:
                    price = amount
                    price_distance = distance
                continue
        if word.x0 < 34:
            continue
        latin, arabic = split_script(word.text)
        if arabic and word.x0 < 460:
            urdu_words.append(word)
        if not latin or parse_amount(latin) is not None:
            continue
        if 68 <= word.x0 < 108:
            model.append(latin)
        elif 108 <= word.x0 < 370:
            english.append(latin)
    return _make_item(
        english=english,
        model=model,
        urdu=_join_urdu_visual(urdu_words),
        price=price,
        item_code=anchor.text.upper(),
    )


def _rp_item(
    anchor: Word,
    row: list[Word],
    urdu_lines: list[tuple[float, str]],
) -> ParsedItem | None:
    english: list[str] = []
    model: list[str] = []
    price: Decimal | None = None
    for word in row:
        if word is anchor or word.x0 < 70:
            continue
        if word.x0 >= 525 or "+" in word.text:
            continue
        if 400 <= word.x0 <= 524:
            amount = _trailing_amount(word.text)
            if amount is not None:
                price = amount
                continue
        latin, _arabic = split_script(word.text)
        if not latin or parse_amount(latin) is not None:
            continue
        if word.x0 >= 320:
            model.append(latin)
        elif word.x0 >= 160:
            english.append(latin)
    urdu = _nearest_line(anchor.y0, urdu_lines)
    return _make_item(
        english=english,
        model=model,
        urdu=urdu,
        price=price,
        item_code=anchor.text,
    )


def _parse_serial_table(
    words: list[Word],
    *,
    price_min_x: float,
    model_min_x: float,
    urdu_lines: list[tuple[float, str]] | None,
) -> list[ParsedItem]:
    serials = [word for word in words if word.x0 < 110 and _is_serial(word.text)]
    items: list[ParsedItem] = []
    for serial in serials:
        row = [word for word in words if abs(word.y0 - serial.y0) <= 8]
        price: Decimal | None = None
        english: list[str] = []
        model: list[str] = []
        urdu_words: list[Word] = []
        for word in row:
            if word is serial:
                continue
            amount = parse_amount(word.text)
            if amount is not None and word.x0 >= price_min_x:
                price = amount
                continue
            latin, arabic = split_script(word.text)
            if arabic and word.x0 < price_min_x:
                urdu_words.append(word)
            if word.x0 < 100:
                continue
            token = latin or (word.text if amount is not None else "")
            if not token:
                continue
            if model_min_x <= word.x0 < price_min_x:
                model.append(token)
            elif amount is None:
                english.append(token)
        urdu = _nearest_line(serial.y0, urdu_lines or []) or _join_urdu_visual(
            urdu_words
        )
        item = _make_item(
            english=english,
            model=model,
            urdu=urdu,
            price=price,
            item_code=None,
        )
        if item is not None:
            items.append(item)
    return items


def _side_row(row: list[Word]) -> ParsedItem | None:
    numbers = [
        (word, amount)
        for word in row
        if (amount := parse_amount(word.text)) is not None
    ]
    described = [word for word in row if parse_amount(word.text) is None]
    if not numbers or not described:
        return None
    desc_right = max(word.x1 for word in described)
    desc_left = min(word.x0 for word in described)
    serials = [pair for pair in numbers if pair[0].x0 >= desc_right - 4]
    prices = [pair for pair in numbers if pair[0].x1 <= desc_left + 8]
    if not prices:
        prices = [pair for pair in numbers if pair not in serials]
    if not prices:
        return None
    price = max(prices, key=lambda pair: pair[0].x0)[1]
    model: list[str] = []
    description: list[str] = []
    for word in sorted(described, key=lambda item: item.x0):
        latin, arabic = split_script(word.text)
        if latin and not arabic and _looks_like_model(latin):
            model.append(latin)
            continue
        description.append(word.text)
    text = " ".join(word.text for word in described)
    if _is_header(text):
        return None
    return _make_item(
        english=[],
        model=model,
        urdu=_clip(" ".join(description), 500) or None,
        price=price,
        item_code=None,
        blank_english=True,
    )


def _make_item(
    *,
    english: list[str],
    model: list[str],
    urdu: str | None,
    price: Decimal | None,
    item_code: str | None,
    blank_english: bool = False,
) -> ParsedItem | None:
    if price is None:
        return None
    description_en = _clip(" ".join(_unique(english)), 500)
    description_ur = _clip(urdu or "", 500) or None
    model_text = _clip(" ".join(_unique(model)), 120) or None
    if _is_header(description_en) or _is_header(description_ur or ""):
        return None
    if blank_english:
        # One description column: keep English empty for a later translation.
        description_en = ""
        if not description_ur:
            return None
    elif not description_en:
        description_en = description_ur or model_text or ""
        if not description_en:
            return None
    return ParsedItem(
        description_en=description_en,
        purchase_price=price,
        description_ur=description_ur,
        model=model_text,
        item_code=_clip(item_code or "", 64) or None,
    )


def _bucket_rows(words: list[Word], bucket: float) -> list[list[Word]]:
    grouped: dict[float, list[Word]] = {}
    for word in words:
        key = round(word.y0 / bucket) * bucket
        grouped.setdefault(key, []).append(word)
    return [grouped[key] for key in sorted(grouped)]


def _join_urdu_visual(words: list[Word]) -> str | None:
    pieces: list[str] = []
    for word in sorted(words, key=lambda item: -item.x0):
        _latin, arabic = split_script(word.text)
        if arabic:
            pieces.append(arabic)
    return _clip(" ".join(pieces), 500) or None


def _nearest_line(y: float, lines: list[tuple[float, str]]) -> str | None:
    if not lines:
        return None
    line_y, text = min(lines, key=lambda line: abs(line[0] - y))
    if abs(line_y - y) > 10:
        return None
    cleaned = re.sub(r"\s+\d[\d,]*\s*$", "", text).strip(" |-_")
    return _clip(cleaned, 500) or None


def _trailing_amount(text: str) -> Decimal | None:
    direct = parse_amount(text)
    if direct is not None:
        return direct
    match = re.search(r"(\d{2,6})$", text.replace(",", ""))
    if match is None:
        return None
    return parse_amount(match.group(1))


def _is_serial(text: str) -> bool:
    amount = parse_amount(text)
    if amount is None or amount != amount.to_integral_value():
        return False
    return amount <= 5000


def _looks_like_model(token: str) -> bool:
    compact = token.strip()
    if not compact or compact.casefold() in {"oem", "matt", "black", "set", "with"}:
        return False
    if _MODEL_HINT.match(compact):
        return True
    if re.fullmatch(r"\d{2,5}[A-Z]{0,3}", compact, re.IGNORECASE):
        return True
    if re.search(r"\d", compact) and len(compact) <= 18:
        return True
    return False


def _is_header(text: str) -> bool:
    lowered = text.casefold()
    markers = (
        "price list",
        "item description",
        "s.no",
        "scheme",
        "customer",
        "نمبر شمار",
        "تفصیل",
        "فی تعداد",
    )
    return any(marker in lowered for marker in markers)


def _unique(parts: list[str]) -> list[str]:
    seen: list[str] = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return seen


def _squash(text: str) -> str:
    return " ".join(text.replace("|", " ").split())


def _clip(text: str | None, limit: int) -> str:
    cleaned = _squash(text or "")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip()
