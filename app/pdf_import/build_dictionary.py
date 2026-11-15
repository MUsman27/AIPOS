import json
import os
import re
import sqlite3
from pathlib import Path
import pymupdf

from app.pdf_import.read import read_price_list

def clean_text(s: str) -> str:
    if not s:
        return ""
    # remove control chars
    s = re.sub(r'[\u200e\u200f\u200b\u200c\u200d\u202a-\u202e]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def normalize_urdu(text: str) -> str:
    if not text:
        return ""
    text = clean_text(text)
    # Remove diacritics / aerab
    text = re.sub(r'[\u064b-\u065f\u0670]', '', text)
    # Normalize characters
    text = text.replace('ي', 'ی').replace('ى', 'ی')
    text = text.replace('ك', 'ک')
    text = text.replace('ة', 'ہ').replace('ھ', 'ہ')
    text = text.replace('ٹ', 'ٹ').replace('ڈ', 'ڈ').replace('ڑ', 'ڑ')
    # Arabic/Persian digits to English
    for a, e in zip('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'):
        text = text.replace(a, e)
    return text.strip()

def build_dictionary():
    itemlisting_dir = Path(r'D:\Ivote\fff\AA\AIPOS\AIPOS\Itemlisting')
    db_path = Path(r'D:\Ivote\fff\AA\AIPOS\AIPOS\pos.db')

    code_to_item = {}
    phrase_dict = {}
    word_dict = {}

    # Standard motorcycle parts vocabulary (Urdu -> English)
    domain_vocab = {
        # Core parts
        "فلٹر": "Filter",
        "ائیر": "Air",
        "ایئر": "Air",
        "ائل": "Oil",
        "آئل": "Oil",
        "پٹرول": "Petrol",
        "پیٹل": "Petrol Cock",
        "پک کیپ": "Spark Plug Cap",
        "پلگ کیپ": "Spark Plug Cap",
        "پلک کیپ": "Spark Plug Cap",
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
        "چین": "Drive Chain",
        "گراری": "Sprocket",
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
        "ڈاگ": "Dog / Pawl",
        "کتا": "Pawl",
        "گولی": "Ball Bearing",
        "سپروکیٹ": "Sprocket",
    }
    for ur, en in domain_vocab.items():
        norm = normalize_urdu(ur)
        word_dict[norm] = en
        phrase_dict[norm] = en

    # Harvest from PDFs in Itemlisting
    for pdf_name in [
        'Price List Rp Parts 01-7-2026.pdf',
        'C.P LIST (29-Aug-2026).pdf',
        'UPDATE LIST.pdf',
        'updated price list 20-6-2026.pdf',
    ]:
        pdf_path = itemlisting_dir / pdf_name
        if not pdf_path.exists():
            continue
        try:
            mfg, items = read_price_list(pdf_path)
            for it in items:
                en = clean_text(it.description_en)
                ur = clean_text(it.description_ur)
                code = clean_text(it.item_code)
                model = clean_text(it.model)

                if code and en:
                    code_to_item[code] = {
                        "description_en": en,
                        "description_ur": ur,
                        "model": model,
                        "manufacturer": mfg,
                    }
                if ur and en and ur.lower() != en.lower():
                    norm_ur = normalize_urdu(ur)
                    if norm_ur:
                        phrase_dict[norm_ur] = en
                        # If phrase is 1-2 words, also add to word_dict
                        ur_words = norm_ur.split()
                        en_words = en.split()
                        if len(ur_words) == 1 and len(en_words) == 1:
                            word_dict[ur_words[0]] = en_words[0]
        except Exception as exc:
            print(f"Error harvesting {pdf_name}: {exc}")

    # Harvest from pos.db
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            for tbl in ('products_copy1', 'products'):
                try:
                    rows = cur.execute(f"SELECT sku, name, description_ur, model FROM [{tbl}] WHERE name IS NOT NULL;").fetchall()
                    for sku, name, desc_ur, mdl in rows:
                        s_sku = clean_text(sku)
                        s_name = clean_text(name)
                        s_ur = clean_text(desc_ur)
                        s_mdl = clean_text(mdl)
                        if s_sku and s_name:
                            code_to_item.setdefault(s_sku, {
                                "description_en": s_name,
                                "description_ur": s_ur,
                                "model": s_mdl,
                                "manufacturer": "Database",
                            })
                        if s_ur and s_name and s_ur.lower() != s_name.lower():
                            norm_ur = normalize_urdu(s_ur)
                            if norm_ur:
                                phrase_dict.setdefault(norm_ur, s_name)
                except Exception:
                    pass
            conn.close()
        except Exception as e:
            print(f"Error accessing pos.db: {e}")

    # Build output payload
    output = {
        "codes": code_to_item,
        "phrases": phrase_dict,
        "words": word_dict,
    }

    out_path = Path(__file__).resolve().parent / "itemlisting_dictionary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved helper dictionary to {out_path}")
    print(f"  Codes: {len(code_to_item)}")
    print(f"  Phrases: {len(phrase_dict)}")
    print(f"  Words: {len(word_dict)}")

if __name__ == "__main__":
    build_dictionary()
