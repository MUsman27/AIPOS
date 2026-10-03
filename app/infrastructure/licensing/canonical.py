"""Canonical encoding + Ed25519 signing for AIPOS licenses.

This module is the single source of truth for the wire format. The React Native
app implements the same rules in ``Native/src/services/license/canonical.ts``
and both sides are pinned against ``tests/data/license_vectors.json``.

FORMAT (v1)
-----------
A license file is JSON with exactly two members::

    {"payload": {...}, "signature": "<base64url, no padding>"}

The signature is an Ed25519 signature over these exact bytes::

    b"AIPOS-LICENSE-V1\n" + canonical_json(payload)

``canonical_json`` is an RFC 8785-style canonical JSON encoding:

* Object keys are sorted by their UTF-8 bytes (recursively). Because UTF-8
  preserves code-point order this matches a plain code-point sort.
* No insignificant whitespace; members separated by ``,`` and key/value by ``:``.
* Strings are escaped exactly like ``JSON.stringify`` (see ``_encode_string``)
  and emitted as raw UTF-8 (``U+2028``/``U+2029`` are NOT escaped).
* ``features`` arrays keep their order.
* Only ``str``, ``bool``, ``int``, ``list``, ``dict`` and ``None`` are allowed.
  ``float`` is rejected outright so two languages can never disagree on the
  rendering of a number.
* Duplicate keys, non-string keys and lone surrogate code points are rejected.

Together these rules make the signed byte string reproducible on Python and JS.
"""

from __future__ import annotations

import base64
from typing import Any, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

#: Only payload shape version 1 is understood by this build.
LICENSE_VERSION = 1

#: Payload versions this build will accept.
SUPPORTED_LICENSE_VERSIONS: frozenset[int] = frozenset({1})

#: Domain-separation prefix so a signature can never be replayed as generic JSON.
SIGNATURE_CONTEXT = b"AIPOS-LICENSE-V1\n"

#: Domain-separation prefix for device registration proofs of possession.
DEVICE_CHALLENGE_CONTEXT = b"AIPOS-DEVICE-REG-V1\n"

#: Payload members that must be present and well-formed.
REQUIRED_LICENSE_FIELDS: tuple[str, ...] = (
    "version",
    "key_id",
    "license_id",
    "customer_id",
    "device_id",
    "issued_at",
    "expires_at",
    "features",
)

_ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
}


class LicenseFormatError(ValueError):
    """Raised when a payload cannot be canonicalized or is structurally invalid."""


def b64url_encode(data: bytes) -> str:
    """Base64url without padding (the padding-free form used in license files)."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    """Decode base64url with or without padding; raises ``LicenseFormatError``."""
    if not isinstance(value, str):
        raise LicenseFormatError("expected a base64url string")
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, base64.binascii.Error) as exc:
        raise LicenseFormatError(f"invalid base64url value: {exc}") from exc


def _encode_string(value: str) -> str:
    """Escape a string exactly like ``JSON.stringify`` and wrap it in quotes."""
    out: list[str] = ['"']
    for char in value:
        code = ord(char)
        if 0xD7FF < code < 0xE000:
            raise LicenseFormatError("lone surrogate code points are not encodable")
        if char in ('"', "\\"):
            out.append("\\" + char)
        elif code in _ESCAPES:
            out.append(_ESCAPES[code])
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def canonicalize(value: Any) -> str:
    """Return the canonical JSON text for ``value``.

    Raises:
        LicenseFormatError: on floats, duplicate/non-string keys, lone
            surrogates or unsupported member types.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        raise LicenseFormatError("floats are not allowed in a canonical payload")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, Mapping):
        keys: list[str] = []
        seen: set[bytes] = set()
        for key in value:
            if not isinstance(key, str):
                raise LicenseFormatError("canonical object keys must be strings")
            raw = key.encode("utf-8")
            if raw in seen:
                raise LicenseFormatError(f"duplicate canonical object key: {key!r}")
            seen.add(raw)
            keys.append(key)
        keys.sort(key=lambda item: item.encode("utf-8"))
        members = ",".join(f"{_encode_string(k)}:{canonicalize(value[k])}" for k in keys)
        return "{" + members + "}"
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return "[" + ",".join(canonicalize(item) for item in value) + "]"
    if isinstance(value, (bytes, bytearray)):
        raise LicenseFormatError("byte strings must be base64url encoded first")
    raise LicenseFormatError(f"unsupported canonical member type: {type(value).__name__}")


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    """Return the exact UTF-8 bytes that are signed for ``payload``."""
    return canonicalize(payload).encode("utf-8")


def signing_bytes(
    payload: Mapping[str, Any], context: bytes = SIGNATURE_CONTEXT
) -> bytes:
    """Prefix the canonical payload with its domain-separation context."""
    return context + canonical_json(payload)


def sign_payload(payload: Mapping[str, Any], private_key: Ed25519PrivateKey) -> str:
    """Sign ``payload`` and return the base64url Ed25519 signature."""
    return b64url_encode(private_key.sign(signing_bytes(payload)))


def verify_signature(
    payload: Mapping[str, Any],
    signature: str,
    public_key: Ed25519PublicKey,
    *,
    context: bytes = SIGNATURE_CONTEXT,
) -> bool:
    """Return ``True`` only when ``signature`` is valid for ``payload``."""
    try:
        public_key.verify(b64url_decode(signature), signing_bytes(payload, context))
    except (InvalidSignature, LicenseFormatError, ValueError):
        return False
    return True


def build_license_document(payload: Mapping[str, Any], signature: str) -> dict[str, Any]:
    """Wrap a payload + signature into the on-disk ``.license`` document."""
    return {"payload": dict(payload), "signature": signature}


def split_license_document(document: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """Extract ``(payload, signature)`` from a ``.license`` document."""
    if not isinstance(document, Mapping):
        raise LicenseFormatError("license document must be a JSON object")
    payload = document.get("payload")
    signature = document.get("signature")
    if not isinstance(payload, dict):
        raise LicenseFormatError("license document is missing an object 'payload'")
    if not isinstance(signature, str) or not signature:
        raise LicenseFormatError("license document is missing a 'signature' string")
    return payload, signature


def validate_payload_shape(payload: Mapping[str, Any]) -> list[str]:
    """Structural (non-cryptographic) checks; returns human-readable problems."""
    problems: list[str] = []
    for field in REQUIRED_LICENSE_FIELDS:
        if field not in payload:
            problems.append(f"missing required field '{field}'")

    version = payload.get("version")
    if version is not None and (isinstance(version, bool) or not isinstance(version, int)):
        problems.append("'version' must be an integer")
    elif isinstance(version, int) and version not in SUPPORTED_LICENSE_VERSIONS:
        problems.append(f"unsupported license version {version}")

    for field in ("key_id", "license_id", "customer_id", "device_id"):
        value = payload.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            problems.append(f"'{field}' must be a non-empty string")

    for field in ("issued_at", "expires_at"):
        value = payload.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            problems.append(f"'{field}' must be an RFC 3339 string")

    features = payload.get("features")
    if features is not None and (
        not isinstance(features, list)
        or any(not isinstance(item, str) or not item for item in features)
    ):
        problems.append("'features' must be an array of non-empty strings")

    fingerprint = payload.get("device_key_fingerprint")
    if fingerprint is not None and (
        not isinstance(fingerprint, str) or not fingerprint.strip()
    ):
        problems.append("'device_key_fingerprint' must be a non-empty string when present")

    grace = payload.get("grace_period_days")
    if grace is not None and (
        isinstance(grace, bool) or not isinstance(grace, int) or grace < 0 or grace > 90
    ):
        problems.append("'grace_period_days' must be an integer between 0 and 90")

    return problems

