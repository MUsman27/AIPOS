import base64
import json
from datetime import datetime, timezone

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database.models import Base
from app.infrastructure.database.session import get_session
from app.licensing import (
    DEVICE_CHALLENGE_CONTEXT,
    LicenseError,
    b64url_encode,
    build_payload,
    signing_bytes,
    sign_payload,
    validate_license,
)
from app.server import app


def _license(private_key: Ed25519PrivateKey, *, expires: str = "2030-12-31"):
    payload = build_payload(
        customer_id="CUSTOMER-001",
        device_id="POS-ABC123",
        expires=expires,
        key_id="2026-01",
        issued_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    return sign_payload(payload, private_key)


def test_license_signature_and_payload_tampering() -> None:
    private_key = Ed25519PrivateKey.generate()
    document = _license(private_key)
    trusted = {"2026-01": private_key.public_key()}

    result = validate_license(
        document,
        trusted,
        device_id="POS-ABC123",
        now=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )

    assert result["valid"] is True
    assert result["status"] == "ACTIVE"
    assert result["licenseId"] == document["payload"]["license_id"]

    modified = json.loads(json.dumps(document))
    modified["payload"]["features"].append("payroll")
    with pytest.raises(LicenseError, match="Invalid signature"):
        validate_license(modified, trusted, device_id="POS-ABC123")


def test_license_rejects_wrong_device_expiry_rollback_and_clock_rollback() -> None:
    private_key = Ed25519PrivateKey.generate()
    document = _license(private_key)
    trusted = {"2026-01": private_key.public_key()}
    with pytest.raises(LicenseError, match="another device"):
        validate_license(document, trusted, device_id="POS-OTHER")
    with pytest.raises(LicenseError, match="roll back"):
        validate_license(
            document,
            trusted,
            device_id="POS-ABC123",
            current_expires_at=datetime(2031, 1, 1, tzinfo=timezone.utc),
        )
    with pytest.raises(LicenseError, match="backwards"):
        validate_license(
            document,
            trusted,
            device_id="POS-ABC123",
            now=datetime(2026, 8, 1, tzinfo=timezone.utc),
            last_seen_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )


def test_license_reports_expired_and_revoked_states() -> None:
    private_key = Ed25519PrivateKey.generate()
    trusted = {"2026-01": private_key.public_key()}
    expired = _license(private_key, expires="2026-01-01")
    expired_result = validate_license(
        expired,
        trusted,
        device_id="POS-ABC123",
        now=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )
    assert expired_result["valid"] is False
    assert expired_result["status"] == "EXPIRED"

    revoked_payload = build_payload(
        customer_id="CUSTOMER-001",
        device_id="POS-ABC123",
        expires="2030-12-31",
        key_id="2026-01",
        status="REVOKED",
    )
    revoked = sign_payload(revoked_payload, private_key)
    revoked_result = validate_license(
        revoked,
        trusted,
        device_id="POS-ABC123",
        now=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )
    assert revoked_result["valid"] is False
    assert revoked_result["status"] == "REVOKED"


def test_registration_and_generation_api_require_proofs_and_admin_token(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setenv("AIPOS_DEVICE_REGISTRATION_TOKEN", "registration-secret")
    monkeypatch.setenv("AIPOS_LICENSE_ADMIN_TOKEN", "admin-secret")
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    monkeypatch.setenv("AIPOS_LICENSE_PRIVATE_KEY", private_pem)

    client = TestClient(app)
    device_id = "POS-API-001"
    customer_id = "CUSTOMER-API-001"
    raw_public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    public_key_text = base64.b64encode(raw_public_key).decode("ascii")
    proof_payload = {
        "customer_id": customer_id,
        "device_id": device_id,
        "device_public_key": public_key_text,
    }
    proof = b64url_encode(
        private_key.sign(signing_bytes(proof_payload, context=DEVICE_CHALLENGE_CONTEXT))
    )

    try:
        unauthenticated = client.post("/devices/register", json=proof_payload | {"proof": proof})
        assert unauthenticated.status_code == 401
        registered = client.post(
            "/devices/register",
            headers={"Authorization": "Bearer registration-secret"},
            json=proof_payload | {"proof": proof, "customer_name": "API Customer"},
        )
        assert registered.status_code == 201

        generated = client.post(
            "/licenses/generate",
            headers={"Authorization": "Bearer admin-secret"},
            json={
                "customer_id": customer_id,
                "device_id": device_id,
                "expires": "2030-12-31",
            },
        )
        assert generated.status_code == 201, generated.text
        stored = client.get(f"/licenses/{generated.json()['payload']['license_id']}")
        assert stored.status_code == 200
        assert stored.json() == generated.json()
    finally:
        app.dependency_overrides.pop(get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()