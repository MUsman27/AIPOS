"""FastAPI REST Service for AIPOS PDF Import & Database Operations."""

from __future__ import annotations

import logging
import base64
import json
import os
import re
import secrets
import tempfile
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.products.service import ProductService
from app.infrastructure.database.models import (
    IssuedLicense,
    LicenseCustomer,
    LicensedDevice,
    Manufacturer,
    Product,
)
from app.infrastructure.database.session import get_session, init_db
from app.licensing import (
    DEVICE_CHALLENGE_CONTEXT,
    LicenseError,
    b64url_decode,
    build_payload,
    load_private_key,
    signing_bytes,
    sign_payload,
)
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from app.pdf_import.load import import_file, upsert_items
from app.pdf_import.read import read_price_list

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("aipos.server")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


_MODEL_TOKENS = re.compile(
    r"(?i)(?:\b(?:CD|CG|JH|UD|CP|DYL|MB|GS|LF|EURO|UNITED|DELUXE|UNIVERSAL|YAMAHA|QINGQI|SOHRAB|STAR|HERO)\s*[-/ ]?\d{2,3}\b|\b(?:CD|CG|JH|UD|CP|DYL|MB|GS|LF|EURO|UNITED|DELUXE|UNIVERSAL|YAMAHA|QINGQI|SOHRAB|STAR|HERO)\b)"
)


def _clean_display_value(value: str | None) -> str:
    if value is None:
        return ""
    cleaned = value
    for token in ("\u200e", "\u200f", "\u200c", "\u200d", "\u202a", "\u202b", "\u202c", "\u202d", "\u202e"):
        cleaned = cleaned.replace(token, "")
    cleaned = re.sub(r"[|_=~\[\]{}<>«»]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" .:-;,'\"()[]{}")
    return cleaned


def _strip_model_tokens(value: str | None, model: str | None = None) -> str:
    raw = _clean_display_value(value)
    if not raw:
        return ""
    model_text = _clean_display_value(model)
    candidate = raw
    for token in [model_text, *re.findall(r"(?i)(?:CD|CG|JH|UD|CP|DYL|MB|GS|LF|EURO|UNITED|DELUXE|UNIVERSAL|YAMAHA|QINGQI|SOHRAB|STAR|HERO)[- /]?\d{2,3}", raw)]:
        if not token:
            continue
        candidate = re.sub(rf"(?i)\b{re.escape(token)}\b", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate)
    candidate = re.sub(r"(?i)\b(?:CD|CG|JH|UD|CP|DYL|MB|GS|LF|EURO|UNITED|DELUXE|UNIVERSAL|YAMAHA|QINGQI|SOHRAB|STAR|HERO)\b", " ", candidate)
    candidate = re.sub(r"(?i)\b(?:CD|CG|JH|UD|CP|DYL|MB|GS|LF|EURO|UNITED|DELUXE|UNIVERSAL|YAMAHA|QINGQI|SOHRAB|STAR|HERO)\s*[-/ ]?\d{2,3}\b", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" .:-;,'\"()[]{}")
    return candidate


app = FastAPI(
    title="AIPOS Python Service",
    description="Backend microservice for PDF parsing, OCR, and DB operations",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for React Native / Electron frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null", "http://localhost:8084", "http://127.0.0.1:8084"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-AIPOS-Local-Token"],
)


@app.middleware("http")
async def authenticate_local_api(request: Request, call_next):
    expected = os.environ.get("AIPOS_LOCAL_API_TOKEN", "").strip()
    if expected and request.method != "OPTIONS":
        supplied = request.headers.get("x-aipos-local-token", "")
        if not secrets.compare_digest(supplied, expected):
            return JSONResponse(status_code=401, content={"detail": "Local API token required"})
    return await call_next(request)


class ProductCreate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    model: Optional[str] = None
    cost_price: Optional[float] = None
    unit_price: Optional[float] = None
    description_en: Optional[str] = None
    description_ur: Optional[str] = None
    manufacturer_name: Optional[str] = None
    manufacturer: Optional[str] = None

    @property
    def normalized_name(self) -> Optional[str]:
        return self.name or self.description_en


class DeviceRegistration(BaseModel):
    customer_id: str
    customer_name: Optional[str] = None
    device_id: str
    device_public_key: str
    proof: str


class LicenseGenerate(BaseModel):
    customer_id: str
    device_id: str
    expires: date
    features: list[str] = ["sales", "inventory", "reports"]
    status: str = "ACTIVE"


def _require_license_token(
    authorization: str | None,
    *,
    environment_variable: str,
) -> None:
    expected = os.environ.get(environment_variable, "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail=f"{environment_variable} is not configured")
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Valid bearer token required")


@app.post("/devices/register", status_code=201)
def register_device(
    item: DeviceRegistration,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_license_token(
        authorization, environment_variable="AIPOS_DEVICE_REGISTRATION_TOKEN"
    )
    try:
        public_bytes = base64.b64decode(item.device_public_key, validate=True)
        signature = b64url_decode(item.proof)
        if len(public_bytes) != 32:
            raise ValueError("Invalid Ed25519 public key length")
        public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
        proof_payload = {
            "customer_id": item.customer_id,
            "device_id": item.device_id,
            "device_public_key": item.device_public_key,
        }
        public_key.verify(
            signature,
            signing_bytes(proof_payload, context=DEVICE_CHALLENGE_CONTEXT),
        )
    except (ValueError, InvalidSignature) as exc:
        raise HTTPException(status_code=400, detail="Invalid device key proof") from exc

    existing = session.get(LicensedDevice, item.device_id)
    if existing:
        if existing.device_public_key != item.device_public_key or existing.customer_id != item.customer_id:
            raise HTTPException(status_code=409, detail="Device ID is already registered")
        return {"device_id": existing.device_id, "customer_id": existing.customer_id, "status": existing.status}

    customer = session.get(LicenseCustomer, item.customer_id)
    if customer is None:
        customer = LicenseCustomer(
            customer_id=item.customer_id,
            name=(item.customer_name or item.customer_id).strip(),
        )
        session.add(customer)
        session.flush()
    device = LicensedDevice(
        device_id=item.device_id,
        customer_id=item.customer_id,
        device_public_key=item.device_public_key,
        status="ACTIVE",
    )
    session.add(device)
    session.commit()
    return {"device_id": device.device_id, "customer_id": device.customer_id, "status": device.status}


@app.post("/licenses/generate", status_code=201)
def generate_license(
    item: LicenseGenerate,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_license_token(authorization, environment_variable="AIPOS_LICENSE_ADMIN_TOKEN")
    device = session.get(LicensedDevice, item.device_id)
    if device is None or device.customer_id != item.customer_id:
        raise HTTPException(status_code=404, detail="Registered device/customer not found")
    if device.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Device is not active")
    private_key_value = os.environ.get("AIPOS_LICENSE_PRIVATE_KEY_FILE") or os.environ.get(
        "AIPOS_LICENSE_PRIVATE_KEY", ""
    )
    if not private_key_value:
        raise HTTPException(status_code=503, detail="License signing key is not configured")
    key_id = os.environ.get("AIPOS_LICENSE_KEY_ID", "2026-01")
    try:
        payload = build_payload(
            customer_id=item.customer_id,
            device_id=item.device_id,
            expires=item.expires.isoformat(),
            key_id=key_id,
            features=item.features,
            status=item.status,
        )
        signed = sign_payload(payload, load_private_key(private_key_value))
    except LicenseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = IssuedLicense(
        license_id=payload["license_id"],
        device_id=device.device_id,
        payload=json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        signature=signed["signature"],
        expires_at=datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00")),
    )
    session.add(record)
    session.commit()
    return signed


@app.get("/devices/{device_id}")
def get_registered_device(
    device_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    device = session.get(LicensedDevice, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return {
        "device_id": device.device_id,
        "customer_id": device.customer_id,
        "device_public_key": device.device_public_key,
        "status": device.status,
        "created_at": device.created_at,
    }


@app.get("/licenses/{license_id}")
def get_issued_license(
    license_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    record = session.get(IssuedLicense, license_id)
    if record is None:
        raise HTTPException(status_code=404, detail="License not found")
    return {"payload": json.loads(record.payload), "signature": record.signature}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "AIPOS Python Backend"}


async def _parse_pdf_file(file: UploadFile) -> dict[str, Any]:
    """Shared logic for parsing uploaded price-list PDFs."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        manufacturer_name, items = read_price_list(tmp_path)
        items_json = []
        for item in items:
            model_text = _clean_display_value(item.model)
            description_ur = _strip_model_tokens(item.description_ur, model_text)
            description_en = _clean_display_value(item.description_en)
            if not description_en:
                description_en = description_ur or model_text or "Unknown item"
            description_en = _strip_model_tokens(description_en, model_text)
            if not description_en:
                description_en = "Unknown item"
            items_json.append(
                {
                    "item_code": item.item_code,
                    "description_en": description_en,
                    "description_ur": description_ur or _clean_display_value(item.description_ur),
                    "model": model_text,
                    "purchase_price": float(item.purchase_price) if item.purchase_price else 0.0,
                }
            )
        return {
            "status": "success",
            "filename": file.filename,
            "manufacturer_name": manufacturer_name,
            "total_items": len(items_json),
            "items": items_json,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {exc}") from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@app.post("/api/pdf/parse")
async def parse_pdf(file: UploadFile = File(...)) -> dict[str, Any]:
    """Parse a PDF file and return JSON items without saving to DB directly."""
    return await _parse_pdf_file(file)


@app.post("/api/pdf/read")
async def read_pdf_file(file: UploadFile = File(...)) -> dict[str, Any]:
    """Backward-compatible alias for the PDF parsing endpoint."""
    return await _parse_pdf_file(file)


@app.post("/api/pdf/import")
async def import_pdf_to_db(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Parse PDF file and directly upsert parsed items into DB."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        manufacturer_name, inserted, updated = import_file(session, tmp_path)
        return {
            "status": "success",
            "filename": file.filename,
            "manufacturer_name": manufacturer_name,
            "inserted": inserted,
            "updated": updated,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import PDF: {str(e)}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@app.get("/api/products")
def get_products(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Retrieve product catalog from DB as JSON."""
    products = session.scalars(select(Product).order_by(Product.id.desc())).all()
    result = []
    for p in products:
        result.append(
            {
                "id": p.id,
                "name": p.name,
                "sku": p.sku,
                "model": p.model,
                "cost_price": float(p.cost_price) if p.cost_price else None,
                "unit_price": float(p.unit_price) if p.unit_price else None,
                "description_ur": p.description_ur,
                "manufacturer": p.manufacturer.name if p.manufacturer else None,
                "is_active": p.is_active,
            }
        )
    return result


def _create_product_record(item: ProductCreate, session: Session) -> dict[str, Any]:
    m_name = item.manufacturer_name or item.manufacturer or "General"
    manufacturer = session.scalar(select(Manufacturer).where(Manufacturer.name == m_name))
    if not manufacturer:
        manufacturer = Manufacturer(name=m_name, source_file="API Manual Entry")
        session.add(manufacturer)
        session.flush()

    cost_dec = Decimal(str(item.cost_price)) if item.cost_price is not None else None
    unit_dec = Decimal(str(item.unit_price)) if item.unit_price is not None else None
    name = item.normalized_name or item.name or "Untitled Product"
    sku = item.sku.strip() if isinstance(item.sku, str) and item.sku.strip() else None
    barcode = item.barcode.strip() if isinstance(item.barcode, str) and item.barcode.strip() else None

    product: Product | None = None
    if sku:
        product = session.scalar(
            select(Product).where(
                Product.manufacturer_id == manufacturer.id,
                Product.sku == sku,
            )
        )
    if product is None and barcode:
        product = session.scalar(select(Product).where(Product.barcode == barcode))

    if product is None:
        product = Product(
            manufacturer=manufacturer,
            sku=sku,
            barcode=barcode,
            name=name,
            description_ur=item.description_ur,
            model=item.model,
            cost_price=cost_dec,
            unit_price=unit_dec,
            is_active=True,
        )
        session.add(product)
    else:
        product.manufacturer = manufacturer
        product.sku = sku or product.sku
        product.barcode = barcode or product.barcode
        product.name = name
        product.description_ur = item.description_ur or product.description_ur
        product.model = item.model or product.model
        product.cost_price = cost_dec if cost_dec is not None else product.cost_price
        product.unit_price = unit_dec if unit_dec is not None else product.unit_price
        product.is_active = True

    session.commit()
    session.refresh(product)

    return {
        "status": "success",
        "product": {
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
            "barcode": product.barcode,
            "model": product.model,
            "cost_price": float(product.cost_price) if product.cost_price else None,
            "unit_price": float(product.unit_price) if product.unit_price else None,
            "description_ur": product.description_ur,
            "manufacturer": manufacturer.name,
        },
    }


@app.post("/api/products")
def create_product(
    item: ProductCreate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create or save a product into DB from JSON sent by React Native."""
    return _create_product_record(item, session)


@app.post("/api/products/translate-missing-names")
def translate_missing_names(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Translate Urdu product descriptions into English names for blank-name records."""
    logger.info("POST /api/products/translate-missing-names called")
    service = ProductService(session)
    updated = service.translate_missing_names()
    logger.info("translate-missing-names completed: updated=%s", updated)
    return {
        "status": "success",
        "updated": updated,
    }


@app.post("/api/products/translate-selected-missing-names")
def translate_selected_missing_names(
    payload: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Translate a limited subset of missing-English products to avoid Google rate limits."""
    logger.info("POST /api/products/translate-selected-missing-names payload=%s", payload)
    product_ids = payload.get("product_ids")
    if not isinstance(product_ids, list):
        raise HTTPException(status_code=400, detail="product_ids must be a list of integers.")

    cleaned_ids: list[int] = []
    for value in product_ids:
        if isinstance(value, int):
            cleaned_ids.append(value)
        elif isinstance(value, str) and value.strip():
            try:
                cleaned_ids.append(int(value))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="product_ids must contain valid integers.") from exc

    logger.info("translate-selected-missing-names: requested ids=%s", cleaned_ids)
    service = ProductService(session)
    updated = service.translate_selected_missing_names(cleaned_ids, limit=10)
    logger.info("translate-selected-missing-names completed: updated=%s requested=%s", updated, len(cleaned_ids))
    return {
        "status": "success",
        "updated": updated,
        "requested": len(cleaned_ids),
        "limit": 10,
    }


@app.post("/api/items/save")
async def save_item(item_data: dict[str, Any]) -> dict[str, Any]:
    """Frontend-friendly save endpoint for a product payload from React/Electron."""
    if not isinstance(item_data, dict):
        raise HTTPException(status_code=400, detail="Item payload must be a JSON object.")

    normalized = dict(item_data)
    if "name" not in normalized:
        normalized["name"] = normalized.get("description_en") or normalized.get("item_name")
    if "manufacturer_name" not in normalized and "manufacturer" in normalized:
        normalized["manufacturer_name"] = normalized["manufacturer"]

    session = get_session()
    try:
        item = ProductCreate(**normalized)
        result = _create_product_record(item, session)
        return {"status": "saved", "item": result["product"]}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid item payload: {exc}") from exc
    finally:
        session.close()


@app.get("/api/manufacturers")
def get_manufacturers(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Retrieve list of manufacturers."""
    manufacturers = session.scalars(select(Manufacturer)).all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "source_file": m.source_file,
            "product_count": len(m.products),
        }
        for m in manufacturers
    ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.server:app", host="127.0.0.1", port=8000, reload=True)
