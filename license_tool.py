"""Generate and inspect offline AIPOS license files."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.licensing import (
    LicenseError,
    build_payload,
    load_private_key,
    load_public_key,
    public_key_base64,
    sign_payload,
    validate_license,
)


def _private_key_argument(value: str | None):
    configured = value or os.environ.get("AIPOS_LICENSE_PRIVATE_KEY_FILE") or os.environ.get(
        "AIPOS_LICENSE_PRIVATE_KEY", ""
    )
    if not configured:
        raise LicenseError("Set AIPOS_LICENSE_PRIVATE_KEY_FILE or pass --private-key")
    return load_private_key(configured)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="license_tool.py")
    commands = parser.add_subparsers(dest="command", required=True)

    keygen = commands.add_parser("keygen", help="Create an Ed25519 signing key pair")
    keygen.add_argument("--private-key", default="license-private.pem")
    keygen.add_argument("--public-key", default="license-public.pem")
    keygen.add_argument("--force", action="store_true")

    generate = commands.add_parser("generate", help="Generate a signed .license file")
    generate.add_argument("--customer-id", required=True)
    generate.add_argument("--device-id", required=True)
    generate.add_argument("--expires", required=True, help="Expiry date YYYY-MM-DD")
    generate.add_argument("--output", required=True)
    generate.add_argument("--key-id", default=os.environ.get("AIPOS_LICENSE_KEY_ID", "2026-01"))
    generate.add_argument("--feature", action="append", dest="features")
    generate.add_argument("--status", choices=("ACTIVE", "REVOKED"), default="ACTIVE")
    generate.add_argument("--private-key")

    inspect = commands.add_parser("inspect", help="Display the payload in a license file")
    inspect.add_argument("license_file")

    verify = commands.add_parser("verify", help="Verify a license signature and expiry")
    verify.add_argument("license_file")
    verify.add_argument("--device-id")
    verify.add_argument("--public-key")

    return parser


def _read_document(path: str) -> dict:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LicenseError(f"Cannot read license file: {path}") from exc
    if not isinstance(document, dict):
        raise LicenseError("License document must be a JSON object")
    return document


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "keygen":
            private_path = Path(args.private_key)
            public_path = Path(args.public_key)
            if not args.force and (private_path.exists() or public_path.exists()):
                raise LicenseError("Key file already exists; pass --force to replace it")
            private_key = Ed25519PrivateKey.generate()
            private_bytes = private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            public_bytes = private_key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            private_path.write_bytes(private_bytes)
            public_path.write_bytes(public_bytes)
            try:
                private_path.chmod(0o600)
            except OSError:
                pass
            print(f"Wrote private signing key: {private_path}")
            print(f"Wrote public verification key: {public_path}")
            print(f"Raw public key (base64): {public_key_base64(private_key.public_key())}")
            return 0

        if args.command == "generate":
            key = _private_key_argument(args.private_key)
            payload = build_payload(
                customer_id=args.customer_id,
                device_id=args.device_id,
                expires=args.expires,
                key_id=args.key_id,
                features=args.features,
                status=args.status,
            )
            document = sign_payload(payload, key)
            output_path = Path(args.output)
            output_path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Wrote {payload['license_id']} to {output_path}")
            return 0

        document = _read_document(args.license_file)
        if args.command == "inspect":
            print(json.dumps(document.get("payload", {}), ensure_ascii=False, indent=2))
            return 0

        public_key_value = args.public_key or os.environ.get("AIPOS_LICENSE_PUBLIC_KEY")
        if public_key_value:
            public_key = load_public_key(public_key_value)
        else:
            public_key = _private_key_argument(None).public_key()
        payload = document.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("key_id"), str):
            raise LicenseError("License payload has no key_id")
        result = validate_license(
            document,
            {payload["key_id"]: public_key},
            device_id=args.device_id or payload.get("device_id", ""),
            now=datetime.now(timezone.utc),
        )
        print(json.dumps({key: value for key, value in result.items() if key != "payload"}, indent=2))
        return 0 if result["valid"] else 1
    except (LicenseError, OSError, ValueError) as exc:
        print(f"license_tool: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())