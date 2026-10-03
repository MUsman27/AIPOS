"""Canonical license payload signing and verification."""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from app.infrastructure.licensing.canonical import (
    DEVICE_CHALLENGE_CONTEXT,
    LicenseFormatError,
    b64url_decode,
    b64url_encode,
    canonical_json as _canonical_json,
    sign_payload as _sign_canonical_payload,
    signing_bytes,
    validate_payload_shape,
    verify_signature,
)

KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
LICENSE_VERSION = 1
DEFAULT_FEATURES = ["sales", "inventory", "reports"]


class LicenseError(ValueError):
    """Raised when a license or signing key is malformed or untrusted."""


def canonical_json(value: dict[str, Any]) -> bytes:
    """Expose the shared canonical UTF-8 JSON representation."""
    return _canonical_json(value)


def _load_key_bytes(value: str | Path) -> bytes:
    text = str(value)
    path = Path(text)
    if "-----BEGIN" not in text and path.is_file():
        return path.read_bytes()
    return text.encode("utf-8")


def load_private_key(value: str | Path) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(_load_key_bytes(value), password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise LicenseError("Unable to load Ed25519 PEM private key") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise LicenseError("Signing key must be Ed25519")
    return key


def load_public_key(value: str | Path) -> Ed25519PublicKey:
    raw = _load_key_bytes(value)
    try:
        key = serialization.load_pem_public_key(raw)
    except ValueError:
        try:
            decoded = base64.b64decode(raw.strip(), validate=True)
            key = Ed25519PublicKey.from_public_bytes(decoded)
        except (ValueError, TypeError) as exc:
            raise LicenseError("Unable to load Ed25519 public key") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise LicenseError("Verification key must be Ed25519")
    return key


def public_key_base64(key: Ed25519PublicKey) -> str:
    raw = key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def public_key_map_from_environment() -> dict[str, Ed25519PublicKey]:
    configured = os.environ.get("AIPOS_LICENSE_PUBLIC_KEYS", "").strip()
    if not configured:
        public_key = os.environ.get("AIPOS_LICENSE_PUBLIC_KEY", "").strip()
        key_id = os.environ.get("AIPOS_LICENSE_KEY_ID", "2026-01")
        return {key_id: load_public_key(public_key)} if public_key else {}
    try:
        entries = json.loads(configured)
        if not isinstance(entries, dict):
            raise ValueError
        return {key_id: load_public_key(value) for key_id, value in entries.items()}
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise LicenseError("AIPOS_LICENSE_PUBLIC_KEYS must be a JSON key-id map") from exc


def build_payload(
    *,
    customer_id: str,
    device_id: str,
    expires: str,
    key_id: str,
    features: list[str] | None = None,
    status: str = "ACTIVE",
    license_id: str | None = None,
    issued_at: datetime | None = None,
) -> dict[str, Any]:
    if not KEY_ID_PATTERN.fullmatch(key_id):
        raise LicenseError("Invalid key_id")
    try:
        expiry_date = date.fromisoformat(expires)
    except ValueError as exc:
        raise LicenseError("Expiry must be an ISO date (YYYY-MM-DD)") from exc
    if not customer_id.strip() or not device_id.strip():
        raise LicenseError("customer_id and device_id are required")
    if status not in {"ACTIVE", "REVOKED"}:
        raise LicenseError("License status must be ACTIVE or REVOKED")
    resolved_features = sorted(set(features or DEFAULT_FEATURES))
    if not resolved_features or any(not item.strip() for item in resolved_features):
        raise LicenseError("At least one non-empty feature is required")
    issue_time = issued_at or datetime.now(timezone.utc)
    if issue_time.tzinfo is None:
        issue_time = issue_time.replace(tzinfo=timezone.utc)
    expires_at = datetime.combine(expiry_date, time(23, 59, 59), tzinfo=timezone.utc)
    return {
        "version": LICENSE_VERSION,
        "key_id": key_id,
        "license_id": license_id or f"LIC-{uuid4().hex[:12].upper()}",
        "customer_id": customer_id.strip(),
        "device_id": device_id.strip(),
        "issued_at": issue_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "features": resolved_features,
        "status": status,
    }


def sign_payload(payload: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    signature = _sign_canonical_payload(payload, private_key)
    return {
        "payload": payload,
        "signature": signature,
    }


def validate_license(
    document: Any,
    trusted_keys: dict[str, Ed25519PublicKey],
    *,
    device_id: str,
    now: datetime | None = None,
    current_expires_at: datetime | None = None,
    last_seen_at: datetime | None = None,
) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != {"payload", "signature"}:
        raise LicenseError("Invalid license envelope")
    payload = document["payload"]
    required = {
        "version", "key_id", "license_id", "customer_id", "device_id",
        "issued_at", "expires_at", "features",
    }
    if not isinstance(payload, dict) or not required.issubset(payload):
        raise LicenseError("License is missing required fields")
    shape_problems = validate_payload_shape(payload)
    if shape_problems:
        raise LicenseError("Invalid license payload: " + "; ".join(shape_problems))
    if payload["version"] != LICENSE_VERSION:
        raise LicenseError("Unsupported license version")
    key_id = payload["key_id"]
    if not isinstance(key_id, str) or not KEY_ID_PATTERN.fullmatch(key_id):
        raise LicenseError("Invalid key_id")
    public_key = trusted_keys.get(key_id)
    if public_key is None:
        raise LicenseError("Untrusted key_id")
    if any(not isinstance(payload[field], str) or not payload[field].strip() for field in (
        "license_id", "customer_id", "device_id", "issued_at", "expires_at"
    )):
        raise LicenseError("Invalid required license field")
    if payload["device_id"] != device_id:
        raise LicenseError("License belongs to another device")
    if not isinstance(payload["features"], list) or any(
        not isinstance(feature, str) or not feature.strip() for feature in payload["features"]
    ):
        raise LicenseError("Invalid features")
    if payload.get("status", "ACTIVE") not in {"ACTIVE", "REVOKED"}:
        raise LicenseError("Invalid license status")
    try:
        if not verify_signature(payload, document["signature"], public_key):
            raise LicenseError("Invalid signature")
        issued_at = datetime.fromisoformat(payload["issued_at"].replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    except (LicenseFormatError, ValueError, TypeError) as exc:
        raise LicenseError("Invalid signature or date") from exc
    if issued_at.tzinfo is None or expires_at.tzinfo is None:
        raise LicenseError("License timestamps must include a timezone")
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    expires_at = expires_at.astimezone(timezone.utc)
    if last_seen_at and current_time < last_seen_at.astimezone(timezone.utc):
        raise LicenseError("System clock moved backwards")
    if current_expires_at and expires_at < current_expires_at.astimezone(timezone.utc):
        raise LicenseError("Renewal would roll back the current expiry")
    days_remaining = (expires_at.date() - current_time.date()).days
    if payload.get("status", "ACTIVE") == "REVOKED":
        return {
            "valid": False,
            "status": "REVOKED",
            "licenseId": payload["license_id"],
            "expiresAt": payload["expires_at"],
            "daysRemaining": max(days_remaining, 0),
            "payload": payload,
        }
    return {
        "valid": expires_at >= current_time,
        "status": "EXPIRED" if expires_at < current_time else (
            "EXPIRING_SOON" if days_remaining <= 30 else "ACTIVE"
        ),
        "licenseId": payload["license_id"],
        "expiresAt": payload["expires_at"],
        "daysRemaining": max(days_remaining, 0),
        "payload": payload,
    }