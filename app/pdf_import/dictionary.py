"""Helper dictionary for Urdu-to-English motorcycle parts translation and code lookup."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("aipos.dictionary")

_DICT_FILE = Path(__file__).resolve().parent / "itemlisting_dictionary.json"

# Core built-in vocabulary for motorcycle spare parts (Urdu -> English)
_DEFAULT_VOCABULARY: dict[str, str] = {
    # Core components
    "فلٹر": "Filter",
    "فلیر": "Filter",
    "ائیر": "Air",
    "ایئر": "Air",
    "ائل": "Oil",
    "آئل": "Oil",
    "پٹرول": "Petrol",
    "پیٹل": "Petrol Cock",
    "پک کیپ": "Spark Plug Cap",
    "پلگ کیپ": "Spark Plug Cap",
    "پلک کیپ": "Spark Plug Cap",
    "پگ کیپ": "Spark Plug Cap",
    "کیپ": "Cap",
    "پلگ": "Plug",
    "نٹ": "Nut",
    "بولٹ": "Bolt",
    "واشر": "Washer",
    "بش": "Bush",
    "بیرنگ": "Bearing",
    "کیبل": "Cable",
    "کلچ": "Clutch",
    "بریک": "Brake",
    "میٹر": "Speedometer",
    "ریس": "Throttle",
    "چوک": "Choke",
    "لیور": "Lever",
    "ہینڈل": "Handlebar",
    "گریپ": "Grip",
    "چمٹا": "Swing Arm",
    "ڈرم": "Drum",
    "ہب": "Hub",
    "اکسل": "Axle",
    "ایکسل": "Axle",
    "سنٹر": "Center",
    "شاک": "Shock Absorber",
    "سپرنگ": "Spring",
    "چین": "Chain",
    "گراری": "Sprocket",
    "سپروکیٹ": "Sprocket",
    "سیٹ": "Set",
    "سلنڈر": "Cylinder",
    "پسٹن": "Piston",
    "رنگ": "Ring",
    "والو": "Valve",
    "راکر": "Rocker",
    "کیم": "Cam",
    "شافٹ": "Shaft",
    "پن": "Pin",
    "روڈ": "Rod",
    "کاربوریٹر": "Carburetor",
    "کک": "Kick Starter",
    "گول": "Round",
    "پیکنگ": "Gasket",
    "پیک": "Packing",
    "گاسکٹ": "Gasket",
    "سیل": "Oil Seal",
    "ربڑ": "Rubber",
    "ربر": "Rubber",
    "پلیٹ": "Plate",
    "پریشر": "Pressure",
    "شو": "Shoe",
    "پیڈ": "Pad",
    "اشارہ": "Turn Signal",
    "لائٹ": "Light",
    "ہیڈ": "Head",
    "بیک": "Back",
    "ہارن": "Horn",
    "سوئچ": "Switch",
    "لاک": "Lock",
    "چابی": "Key",
    "جالی": "Mesh",
    "بوتل": "Bottle",
    "پائپ": "Pipe",
    "وائرنگ": "Wiring Harness",
    "کوائل": "Coil",
    "میگنٹ": "Magnet",
    "سی ڈی آئی": "CDI",
    "ریگولیٹر": "Regulator",
    "بیٹری": "Battery",
    "ٹائر": "Tyre",
    "ٹیوب": "Tube",
    "رم": "Rim",
    "سپوک": "Spoke",
    "مڈگارڈ": "Mudguard",
    "فٹ بار": "Footrest Bar",
    "فٹ ریسٹ": "Footrest",
    "سٹینڈ": "Stand",
    "اٹینڈ": "Stand",
    "سائیڈ": "Side",
    "مین": "Main",
    "ٹینک": "Fuel Tank",
    "ٹینکی": "Fuel Tank",
    "ٹاپہ": "Side Cover",
    "سائلنسر": "Silencer",
    "مفلر": "Muffler",
    "مکمل": "Complete",
    "نیو": "New Model",
    "اولڈ": "Old Model",
    "اولڑ": "Old Model",
    "پرانا": "Old Model",
    "بمعہ": "With",
    "بمع": "With",
    "ڈبل": "Double",
    "سنگل": "Single",
    "فرنٹ": "Front",
    "پچھلی": "Rear",
    "اگلی": "Front",
    "چھوٹی": "Small",
    "بڑی": "Big",
    "اٹل": "Atal",
    "رولر": "Roller",
    "ڈاگ": "Pawl / Dog",
    "کتا": "Pawl",
    "گولی": "Ball Bearing",
}

_MODEL_NORMALIZATIONS: dict[str, str] = {
    "70": "CD70",
    "125": "CG125",
    "100": "CD100",
    "110": "CD110",
    "150": "GS150",
    "70K": "CD70",
    "70CC": "CD70",
    "125CC": "CG125",
    "EURO2": "EURO-2",
    "EURO 2": "EURO-2",
}

_cached_dictionary: dict[str, Any] | None = None


def normalize_urdu(text: str | None) -> str:
    """Normalize Urdu text for robust matching across OCR and typing variants."""
    if not text:
        return ""
    # Strip invisible Unicode control tokens
    s = re.sub(r"[\u200e\u200f\u200b\u200c\u200d\u202a-\u202e]", "", text)
    # Strip diacritics / aerab
    s = re.sub(r"[\u064b-\u065f\u0670]", "", s)
    # Unify letters
    s = s.replace("ي", "ی").replace("ى", "ی")
    s = s.replace("ك", "ک")
    s = s.replace("ة", "ہ").replace("ھ", "ہ")
    s = s.replace("ڑ", "ڑ").replace("ٹ", "ٹ").replace("ڈ", "ڈ")
    # Convert Eastern digits to Western digits
    for a, e in zip("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"):
        s = s.replace(a, e)
    # Strip noisy symbols
    s = re.sub(r"[{}\[\]<>«»|~_+=]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def clean_urdu_display(text: str | None) -> str:
    """Clean Urdu text for UI display, keeping proper letters and numbers."""
    if not text:
        return ""
    s = re.sub(r"[\u200e\u200f\u200b\u200c\u200d\u202a-\u202e]", "", text)
    s = re.sub(r"[|_=~\[\]{}<>«»]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .:-;,'\"()[]{}")


def load_helper_dictionary() -> dict[str, Any]:
    """Load or reload the harvested itemlisting dictionary."""
    global _cached_dictionary
    if _cached_dictionary is not None:
        return _cached_dictionary

    codes: dict[str, dict[str, str]] = {}
    phrases: dict[str, str] = {}
    words: dict[str, str] = dict(_DEFAULT_VOCABULARY)

    if _DICT_FILE.is_file():
        try:
            with open(_DICT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                codes.update(data.get("codes", {}))
                phrases.update(data.get("phrases", {}))
                words.update(data.get("words", {}))
        except Exception as exc:
            logger.warning("Failed to read %s: %s", _DICT_FILE, exc)

    # Re-apply defaults to ensure core words are always present
    words.update(_DEFAULT_VOCABULARY)

    # Normalize keys in phrases and words
    normalized_phrases = {normalize_urdu(k): v for k, v in phrases.items() if k}
    normalized_words = {normalize_urdu(k): v for k, v in words.items() if k}

    _cached_dictionary = {
        "codes": codes,
        "phrases": normalized_phrases,
        "words": normalized_words,
    }
    return _cached_dictionary


def get_item_by_code(code: str | None) -> dict[str, str] | None:
    """Look up an item by its SKU/item code from the dictionary."""
    if not code:
        return None
    cleaned = code.strip()
    data = load_helper_dictionary()
    codes = data.get("codes", {})
    return codes.get(cleaned)


def translate_urdu_to_english(
    text: str | None,
    code: str | None = None,
    model: str | None = None,
) -> str:
    """Translate an Urdu product description into a proper English name.

    1. Checks code in the helper dictionary.
    2. Checks full Urdu phrase in the dictionary.
    3. Translates token by token using motorcycle spare parts dictionary.
    4. Combines with model specifications.
    """
    # 1. Code match
    if code:
        item = get_item_by_code(code)
        if item and item.get("description_en"):
            en = item["description_en"].strip()
            item_model = item.get("model") or model
            if item_model and item_model not in en:
                return f"{en} {item_model}".strip()
            return en

    if not text:
        if model:
            return f"Item {model}".strip()
        return "Unknown item"

    norm = normalize_urdu(text)
    if not norm:
        if model:
            return f"Item {model}".strip()
        return "Unknown item"

    data = load_helper_dictionary()
    phrases = data.get("phrases", {})
    words_map = data.get("words", {})

    # 2. Exact phrase match
    if norm in phrases:
        result = phrases[norm]
        if model and model.upper() not in result.upper():
            return f"{result} {model}".strip()
        return result

    # 3. Token-by-token translation using vocabulary and models
    raw_tokens = norm.split()
    translated_tokens: list[str] = []
    found_models: list[str] = []

    model_regex = re.compile(
        r"(?i)\b(CD[- ]?70|CG[- ]?125|CD[- ]?100|GS[- ]?150|YBR[- ]?125|EURO[- ]?2|DELUXE|70|125|100|150)\b"
    )

    skip_next = False
    for i, token in enumerate(raw_tokens):
        if skip_next:
            skip_next = False
            continue

        clean_token = token.strip(" .:-;,'\"()[]{}")
        if not clean_token:
            continue

        # Check 2-word combinations
        if i + 1 < len(raw_tokens):
            two_word = f"{clean_token} {raw_tokens[i+1].strip(' .:-;,\'\"()[]{}')}"
            if two_word in phrases:
                translated_tokens.append(phrases[two_word])
                skip_next = True
                continue
            if two_word in words_map:
                translated_tokens.append(words_map[two_word])
                skip_next = True
                continue

        # Check 1-word translation
        if clean_token in words_map:
            translated_tokens.append(words_map[clean_token])
            continue

        # Check model tokens
        m_match = model_regex.fullmatch(clean_token)
        if m_match:
            val = m_match.group(1).upper()
            mapped = _MODEL_NORMALIZATIONS.get(val, val)
            if mapped not in found_models:
                found_models.append(mapped)
            continue

        # If token is Latin characters (e.g. OEM, KOK, 2RS, SET)
        if re.fullmatch(r"[A-Za-z0-9/_-]+", clean_token) and len(clean_token) >= 2:
            translated_tokens.append(clean_token.upper())
            continue

    # Clean and order tokens
    if model:
        m_val = model.upper()
        if m_val not in found_models:
            found_models.append(m_val)

    # De-duplicate translated tokens while preserving order
    seen: set[str] = set()
    ordered_tokens: list[str] = []
    for tok in translated_tokens:
        tok_clean = tok.strip()
        if tok_clean and tok_clean.casefold() not in seen:
            seen.add(tok_clean.casefold())
            ordered_tokens.append(tok_clean)

    if ordered_tokens:
        base_name = " ".join(ordered_tokens)
        if found_models:
            models_str = " ".join(found_models)
            if models_str not in base_name:
                return f"{base_name} {models_str}".strip()
        return base_name.strip()

    if found_models:
        return f"Spare Part {' '.join(found_models)}".strip()

    # Fallback to Latin characters in raw text if present
    latin_chars = re.sub(r"[^\x20-\x7E]+", " ", text).strip()
    latin_clean = re.sub(r"\s+", " ", latin_chars).strip(" .:-;,'\"()[]{}")
    if latin_clean and len(latin_clean) >= 3:
        return latin_clean

    return "Motorcycle Spare Part"
