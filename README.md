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

## Sale invoice profile command

An administrator can generate a signed invoice-profile token through
`POST /invoice-profile/generate`. Send a JSON body containing `shop_name`,
`address`, and `phone_numbers` and authorize with the configured
`AIPOS_LICENSE_ADMIN_TOKEN` bearer token. The response's `hash` is a compact
base64url payload and Ed25519 signature, signed with the configured
`AIPOS_LICENSE_PRIVATE_KEY_FILE` (or `AIPOS_LICENSE_PRIVATE_KEY`) and
`AIPOS_LICENSE_KEY_ID`.

Paste this hash into **Inventory → Settings → Sale invoice profile → Command
box** in the Native app and press **Run**. The app verifies the signature
against its trusted license public keys, then stores the exact token in the
SQLite `app_settings` row with key `invoice`. Add a new public key to the
Native app's trusted key map before generating tokens with a new key ID.

Example request:

```sh
curl -X POST "https://YOUR_API/invoice-profile/generate" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"shop_name":"Khubaib Auto","address":"Auto Market, Lahore","phone_numbers":["0303 5971463","0300 9563285"]}'
```

Copy the `hash` string from the JSON response (not the surrounding JSON object)
into the Native app's command box.

## Offline Licensing

The POS verifies licenses locally and does not need the API to import or use an installed license. Creating or editing sales and purchases, saving drafts, and finalizing transactions require a valid, unexpired device license; transaction history remains available for viewing when the license is invalid or expired. Android and iOS device keys are stored in Expo SecureStore (Android Keystore-backed encryption and iOS Keychain). Electron Windows/macOS keeps the private key in the main process and stores it using Electron `safeStorage`. Browser-only web builds do not support device registration because they lack protected key storage.

### Signing keys

From this directory, generate a signing key pair once on the administrator's secure machine:

```sh
python license_tool.py keygen --private-key license-private.pem --public-key license-public.pem
```

Back up the private key securely. It is ignored by Git under the default filename and must never be copied into `Native/`. Configure the backend with `AIPOS_LICENSE_PRIVATE_KEY_FILE` pointing to the private PEM, `AIPOS_LICENSE_KEY_ID` (default `2026-01`), and `AIPOS_LICENSE_ADMIN_TOKEN`. Keep the admin token secret and do not expose admin endpoints to untrusted networks.

Add the raw public key printed by `keygen` to `Native/src/services/licenseTrust.ts` under the matching key ID:

```ts
export const trustedLicensePublicKeys: Record<string, string> = {
	'2026-01': 'BASE64_RAW_ED25519_PUBLIC_KEY',
};
```

Only public keys belong in the app. Add a new key ID and public key before rotating signing keys so existing licenses continue to verify; remove retired keys only after every license they signed has expired.

### Account registration, activation, and renewal

Configure the backend service and run its Alembic migrations. The migration renames `license_customers` to `clients` without discarding existing client/device/license records, then adds account, session, and entitlement fields.

In the POS, open **License** and create an account with a name, email, and password. The backend stores the user in Postgres with a salted PBKDF2 password hash and creates a client account. New accounts are pending and cannot register devices until an administrator grants an entitlement. Account bearer tokens expire after 30 days and are stored using the platform's protected local storage.

Use the `customer_id` returned by account registration to activate the client account. Set the expiry date and, optionally, a maximum number of active devices. A newly created account with no `max_devices` value has no device-count limit; when updating an existing entitlement, omitted `max_devices` and `features` values are preserved. Set `"max_devices": null` explicitly to remove an existing limit:

```sh
curl -X PUT "https://YOUR_API/admin/clients/CLIENT_ID/entitlement" \
  -H "Authorization: Bearer $AIPOS_LICENSE_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"expires":"2027-09-30","max_devices":5,"features":["sales","inventory","reports"]}'
```

Once activated, the user signs in on each POS and selects **Register This Device**. Each installation creates its own Ed25519 key pair, proves possession of its private key, and sends only the public key and proof. The backend associates each device with the shared client entitlement and returns a separately signed, device-bound license. The POS verifies and installs the license locally; it does not need the API for normal use.

Administrators can list client accounts, their entitlement details, and registered/active device and user counts:

```sh
curl "https://YOUR_API/admin/clients" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

After the administrator extends an account entitlement, each POS selects **Get / Renew License** while online. The backend signs a replacement license for that device with the same server signing key. The account screen lists registered devices and can deactivate other devices to free an activation slot. Deactivation prevents future renewal, but an offline device can continue using its already-installed license until it expires.

The existing command-line tools remain available for administrator-managed offline issuance:

```sh
python license_tool.py generate --customer-id CUSTOMER-001 --device-id POS-ABC123 --expires 2027-09-30 --output customer-device.license
python license_tool.py inspect customer-device.license
python license_tool.py verify customer-device.license --public-key license-public.pem
```

The generated file can be delivered by USB or another offline method and imported from **License**. The POS verifies its signature, key ID, device binding, dates, and current expiry before replacing the installed license. `--status REVOKED` signs a revocation payload, which takes effect only after that file is delivered and imported; an offline installation cannot learn about a remote revocation on its own. The previous token-based `/devices/register` endpoint remains for compatibility with existing installations and still requires `AIPOS_DEVICE_REGISTRATION_TOKEN`; the admin `/licenses/generate` endpoint also remains. New POS account activation uses `/account/*`.

### Signed bytes

The `payload` object is serialized as canonical UTF-8 JSON: object keys are recursively sorted by UTF-8 bytes, strings use JSON/`JSON.stringify` escaping, arrays retain their order, and insignificant whitespace is omitted. Floats and unsupported values are rejected. The signature covers the exact bytes `AIPOS-LICENSE-V1\n` followed by that canonical JSON, using Ed25519; `signature` is unpadded base64url. The envelope itself is not signed. Device registration proofs use the separate `AIPOS-DEVICE-REG-V1\n` context followed by canonical JSON, also signed with Ed25519 and encoded as unpadded base64url. The Python canonicalization implementation is in `app/infrastructure/licensing/canonical.py`; the POS must use the same rules.

Expo SecureStore protects the mobile seed at rest but returns it to JavaScript for Noble Ed25519 signing; this is not a non-exportable Secure Enclave/Android Keystore signing key. For hardware-bound, non-exportable device keys, a native cryptographic module and platform-specific implementation are a separate requirement. The Electron implementation keeps key material inside the main process.