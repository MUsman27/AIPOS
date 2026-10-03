# AIPOS

## Dockerized FastAPI backend

The backend container includes Linux Tesseract and the English/Urdu trained
data from `.tessdata/`. Build it from this directory, which is the Docker build
context:

```sh
docker build -f Dockerfile.vercel -t aipos-api .
```

For a local run, configure `DATABASE_URL` for Supabase Postgres and any other
backend secrets in an ignored `.env` file, then run:

```sh
docker run --rm -p 8000:8000 --env-file .env aipos-api
```

The API is available at `http://localhost:8000`; `/health` is a simple
readiness check. The container runs Alembic migrations during startup, so it
must be able to connect to the configured database.

For Vercel, deploy this directory as a **Services** project. The
`vercel.json` routes requests to the `Dockerfile.vercel` container service.
Configure `DATABASE_URL` and all required backend secrets as Vercel environment
variables; never put secret values in the Dockerfile or commit them. The
container is stateless, so persist application data in Supabase or other
external storage, not in its filesystem. Set the frontend's
`EXPO_PUBLIC_API_BASE_URL` to this API deployment's URL and redeploy the
frontend.

## Offline Licensing

The POS verifies licenses locally and does not need the API to import or use an installed license. Android and iOS device keys are stored in Expo SecureStore (Android Keystore-backed encryption and iOS Keychain). Electron Windows/macOS keeps the private key in the main process and stores it using Electron `safeStorage`. Browser-only web builds do not support device registration because they lack protected key storage.

### Signing keys

From this directory, generate a signing key pair once on the administrator's secure machine:

```sh
python license_tool.py keygen --private-key license-private.pem --public-key license-public.pem
```

Back up the private key securely. It is ignored by Git under the default filename and must never be copied into `Native/`. Configure the backend with `AIPOS_LICENSE_PRIVATE_KEY_FILE` pointing to the private PEM, `AIPOS_LICENSE_KEY_ID` (default `2026-01`), `AIPOS_DEVICE_REGISTRATION_TOKEN`, and `AIPOS_LICENSE_ADMIN_TOKEN`. Keep both tokens secret. Do not expose the license-generation API directly to untrusted networks.

Add the raw public key printed by `keygen` to `Native/src/services/licenseTrust.ts` under the matching key ID:

```ts
export const trustedLicensePublicKeys: Record<string, string> = {
	'2026-01': 'BASE64_RAW_ED25519_PUBLIC_KEY',
};
```

Only public keys belong in the app. Add a new key ID and public key before rotating signing keys so existing licenses continue to verify; remove retired keys only after every license they signed has expired.

### Device activation and renewal

Configure the backend service and run its Alembic migrations. In the POS, open **License**, enter the reachable backend URL, customer ID/name, and the device registration token. Registration sends the public key and an Ed25519 proof; the device private key is never sent. The administrator can then create a license with the API or CLI:

```sh
python license_tool.py generate --customer-id CUSTOMER-001 --device-id POS-ABC123 --expires 2027-09-30 --output customer-device.license
python license_tool.py inspect customer-device.license
python license_tool.py verify customer-device.license --public-key license-public.pem
```

The generated file can be delivered by USB or another offline method and imported from **License**. The POS verifies its signature, key ID, device binding, dates, and current expiry before replacing the installed license. `--status REVOKED` signs a revocation payload, which takes effect only after that file is delivered and imported; an offline installation cannot learn about a remote revocation on its own.

### Signed bytes

The `payload` object is serialized as canonical UTF-8 JSON: object keys are recursively sorted by UTF-8 bytes, strings use JSON/`JSON.stringify` escaping, arrays retain their order, and insignificant whitespace is omitted. Floats and unsupported values are rejected. The signature covers the exact bytes `AIPOS-LICENSE-V1\n` followed by that canonical JSON, using Ed25519; `signature` is unpadded base64url. The envelope itself is not signed. Device registration proofs use the separate `AIPOS-DEVICE-REG-V1\n` context followed by canonical JSON, also signed with Ed25519 and encoded as unpadded base64url. The Python canonicalization implementation is in `app/infrastructure/licensing/canonical.py`; the POS must use the same rules.

Expo SecureStore protects the mobile seed at rest but returns it to JavaScript for Noble Ed25519 signing; this is not a non-exportable Secure Enclave/Android Keystore signing key. For hardware-bound, non-exportable device keys, a native cryptographic module and platform-specific implementation are a separate requirement. The Electron implementation keeps key material inside the main process.