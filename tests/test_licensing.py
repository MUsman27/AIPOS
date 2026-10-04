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

from app.infrastructure.database.models import Base, Client, LicenseUser, LicensedDevice
from app.infrastructure.database.session import get_session
from app.licensing import (
    DEVICE_CHALLENGE_CONTEXT,
    LicenseError,
    b64url_decode,
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


def test_invoice_profile_generation_returns_signed_profile_hash(monkeypatch) -> None:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    monkeypatch.setenv("AIPOS_LICENSE_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("AIPOS_LICENSE_PRIVATE_KEY", private_pem)
    monkeypatch.setenv("AIPOS_LICENSE_KEY_ID", "2026-01")
    client = TestClient(app)
    request = {
        "shop_name": "Khubaib Auto",
        "address": "Auto Market",
        "phone_numbers": ["0303 5971463", "0300 9563285"],
    }

    assert client.post("/invoice-profile/generate", json=request).status_code == 401
    response = client.post(
        "/invoice-profile/generate",
        headers={"Authorization": "Bearer admin-secret"},
        json=request,
    )
    assert response.status_code == 200, response.text

    token = response.json()["hash"]
    encoded_payload, encoded_signature = token.split(".")
    payload_bytes = b64url_decode(encoded_payload)
    signature = b64url_decode(encoded_signature)
    private_key.public_key().verify(
        signature,
        b"AIPOS-INVOICE-PROFILE-V1\n" + payload_bytes,
    )
    assert json.loads(payload_bytes) == {
        "address": "Auto Market",
        "key_id": "2026-01",
        "phone_numbers": ["0303 5971463", "0300 9563285"],
        "shop_name": "Khubaib Auto",
        "version": 1,
    }


def test_account_entitlement_is_shared_across_device_licenses(monkeypatch) -> None:
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
    monkeypatch.setenv("AIPOS_LICENSE_ADMIN_TOKEN", "admin-secret")
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    monkeypatch.setenv("AIPOS_LICENSE_PRIVATE_KEY", private_pem)
    client = TestClient(app)

    try:
        created = client.post(
            "/account/register",
            json={
                "full_name": "Account Owner",
                "email": "owner@example.com",
                "password": "long-enough-password",
                "phone": "+1-555-0100",
            },
        )
        assert created.status_code == 201, created.text
        response = created.json()
        token = response["access_token"]
        customer_id = response["account"]["client"]["customer_id"]
        assert response["account"]["client"]["license_expires_at"] is None
        assert client.post(
            "/account/login",
            json={"email": "owner@example.com", "password": "wrong-password"},
        ).status_code == 401

        activated = client.put(
            f"/admin/clients/{customer_id}/entitlement",
            headers={"Authorization": "Bearer admin-secret"},
            json={"expires": "2030-12-31", "max_devices": 1},
        )
        assert activated.status_code == 200, activated.text

        device_key = Ed25519PrivateKey.generate()
        device_id = "POS-ACCOUNT-001"
        raw_public_key = device_key.public_key().public_bytes(
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
            device_key.sign(signing_bytes(proof_payload, context=DEVICE_CHALLENGE_CONTEXT))
        )
        issued = client.post(
            "/account/devices/register",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "device_id": device_id,
                "device_public_key": public_key_text,
                "proof": proof,
            },
        )
        assert issued.status_code == 201, issued.text
        document = issued.json()
        assert document["payload"]["customer_id"] == customer_id
        assert validate_license(
            document,
            {"2026-01": private_key.public_key()},
            device_id=device_id,
        )["valid"] is True

        second_key = Ed25519PrivateKey.generate()
        second_device_id = "POS-ACCOUNT-002"
        second_public_text = base64.b64encode(
            second_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).decode("ascii")
        second_proof_payload = {
            "customer_id": customer_id,
            "device_id": second_device_id,
            "device_public_key": second_public_text,
        }
        second_proof = b64url_encode(
            second_key.sign(
                signing_bytes(second_proof_payload, context=DEVICE_CHALLENGE_CONTEXT)
            )
        )
        device_limit = client.post(
            "/account/devices/register",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "device_id": second_device_id,
                "device_public_key": second_public_text,
                "proof": second_proof,
            },
        )
        assert device_limit.status_code == 409

        expired = client.put(
            f"/admin/clients/{customer_id}/entitlement",
            headers={"Authorization": "Bearer admin-secret"},
            json={"expires": "2020-12-31"},
        )
        assert expired.status_code == 200, expired.text
        account = client.get(
            "/account/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert account.json()["client"]["max_devices"] == 1
        renewal = client.post(
            f"/account/devices/{device_id}/renew",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert renewal.status_code == 403
    finally:
        app.dependency_overrides.pop(get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_admin_can_list_clients(monkeypatch) -> None:
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
    monkeypatch.setenv("AIPOS_LICENSE_ADMIN_TOKEN", "admin-secret")
    with session_factory() as session:
        client_record = Client(
            customer_id="CLIENT-001",
            name="Example Shop",
            phone="555-0100",
            address="Market Street",
            license_features='["sales","inventory"]',
        )
        session.add(client_record)
        session.flush()
        session.add(
            LicenseUser(
                customer_id=client_record.customer_id,
                full_name="Shop Owner",
                email="owner@example.com",
                phone=None,
                password_hash="not-a-real-password-hash",
            )
        )
        session.add(
            LicensedDevice(
                device_id="POS-001",
                customer_id=client_record.customer_id,
                device_public_key="public-key",
                status="ACTIVE",
            )
        )
        session.commit()

    test_client = TestClient(app)
    try:
        unauthorized = test_client.get("/admin/clients")
        assert unauthorized.status_code == 401

        response = test_client.get(
            "/admin/clients",
            headers={"Authorization": "Bearer admin-secret"},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["total"] == 1
        listed_client = result["clients"][0]
        assert listed_client["created_at"] is not None
        assert {
            key: value for key, value in listed_client.items() if key != "created_at"
        } == {
            "customer_id": "CLIENT-001",
            "name": "Example Shop",
            "phone": "555-0100",
            "address": "Market Street",
            "is_active": True,
            "license_expires_at": None,
            "max_devices": None,
            "features": ["sales", "inventory"],
            "user_count": 1,
            "registered_devices": 1,
            "active_devices": 1,
        }
    finally:
        app.dependency_overrides.pop(get_session, None)
        Base.metadata.drop_all(engine)
        engine.dispose()