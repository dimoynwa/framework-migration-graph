# Agent Prompt — Generate Insomnia Collection for paysafe-wallet-switch Top-22 Endpoints

## Goal

Generate a valid **Insomnia Export v4 JSON file** named `paysafe-wallet-switch-top22.insomnia.json` containing the 22 highest-traffic endpoints of the `paysafe-wallet-switch` service, ready to import into Insomnia via `File → Import`.

## Insomnia export format reference

The file must follow Insomnia's v4 export schema:

```json
{
  "_type": "export",
  "__export_format": 4,
  "__export_date": "2026-07-12T00:00:00.000Z",
  "__export_source": "insomnia.desktop",
  "resources": [ ... ]
}
```

Every item in `resources` is a JSON object with `_type` being one of: `workspace`, `request_group` (folder), `request`, `environment`. Each has a unique `_id` (prefixed `wrk_`, `fld_`, `req_`, `env_` respectively) and a `parentId` that wires the tree together. Requests inside a folder have `parentId` = that folder's `_id`. Folders inside the workspace have `parentId` = the workspace's `_id`.

## Workspace & environment setup

### Workspace
- `_type`: `workspace`
- `_id`: `wrk_wallet_switch_top22`
- `name`: `Paysafe Wallet Switch — Top 22`
- `scope`: `collection`

### Base environment (attached to workspace)
- `_type`: `environment`
- `_id`: `env_base`
- `parentId`: `wrk_wallet_switch_top22`
- `name`: `Base Environment`
- `data`:
```json
{
  "local-paysafe-wallet-switch": "http://localhost:8118",
  "access_token": ""
}
```

### Authentication

All requests must include header `Authorization: Bearer {{ _.access_token }}`.

The collection includes a dedicated **"🔑 Fetch Token"** request in an **Auth** folder. Here are the full details:

- **Method:** `POST`
- **URL:** `https://paysafe-op-gateway.services.external.eu-west-1.dev.sandbox.dw-cloud.net/mobile/v3/auth`
- **Headers:**
  - `Content-Type: application/x-www-form-urlencoded`
  - `User-Agent: insomnia/12.5.0`
  - `X-TMX-Session-ID: 0uvn4jp075iir6muasu46xvrxz6y47p9`
  - `deviceId: test@threatmetrix.com`
  - `x-forwarded-deviceid: 4c5d0e33-60f9-4ed0-ac80-f9d585bad67c`
  - `x-internal-brand: Skrill`
  - `x-mobile-os-name: iOS`
- **Body** (`application/x-www-form-urlencoded`):
  - `grant_type` = `password`
  - `username` = `mohamed.salah@sun-fish.com`
  - `password` = `mohamed.salah@sun-fish.com1`
  - `client_id` = `d7bfe349e9351965db6c46165e3277e465970a45`
  - `client_secret` = `99d5f9d8d7558a36e7d021e10556185d5848f528cc4955a82bc7bc4f0a11015`
- **After-response script** (extracts `access_token` and stores it in the environment):
```javascript
const body = JSON.parse(insomnia.response.body());
insomnia.environment.set("access_token", body.access_token);
```

### Default headers (on every request)

Every request in the collection must include these headers directly (Insomnia does not have collection-level header inheritance):

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {{ _.access_token }}` |
| `x-internal-brand` | `Skrill` |
| `Accept` | `application/json` |

---

## Folder structure

Create these `request_group` resources with `parentId` = `wrk_wallet_switch_top22`:

| `_id` | Folder name |
|-------|-------------|
| `fld_auth` | Auth |
| `fld_telemetry` | Telemetry & Monitoring |
| `fld_preflight` | Preflight & Bootstrap |
| `fld_transactions` | Transaction History & Analytics |
| `fld_profile` | User Profile & Settings |
| `fld_currencies` | Currencies & Deals |
| `fld_merchant` | Merchant & Referral |
| `fld_deposit` | Deposit |

---

## Requests to include

### Folder: Auth

**0. POST 🔑 Fetch Token** — Fetches OAuth2 token
- URL: `https://paysafe-op-gateway.services.external.eu-west-1.dev.sandbox.dw-cloud.net/mobile/v3/auth`
- Headers:
  - `Content-Type: application/x-www-form-urlencoded`
  - `User-Agent: insomnia/12.5.0`
  - `X-TMX-Session-ID: 0uvn4jp075iir6muasu46xvrxz6y47p9`
  - `deviceId: test@threatmetrix.com`
  - `x-forwarded-deviceid: 4c5d0e33-60f9-4ed0-ac80-f9d585bad67c`
  - `x-internal-brand: Skrill`
  - `x-mobile-os-name: iOS`
- Body (`application/x-www-form-urlencoded`):
  - `grant_type` = `password`
  - `username` = `mohamed.salah@sun-fish.com`
  - `password` = `mohamed.salah@sun-fish.com1`
  - `client_id` = `d7bfe349e9351965db6c46165e3277e465970a45`
  - `client_secret` = `99d5f9d8d7558a36e7d021e10556185d5848f528cc4955a82bc7bc4f0a11015`
- After-response script:
```javascript
const body = JSON.parse(insomnia.response.body());
insomnia.environment.set("access_token", body.access_token);
```
- Description: "Run this first to populate access_token. The token is extracted from the `access_token` field in the JSON response."
- Do NOT include the `Authorization: Bearer` header on this request (it's the one that fetches the token)

### Folder: Telemetry & Monitoring

**1. POST /api/wallet/v1/usage/event** — Logs usage event data
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/v1/usage/event`
- Headers (in addition to default three):
  - `Content-Type: application/json`
  - `User-Agent: InsomniaSmoke/1.0`
  - `X-Forwarded-For: 127.0.0.1`
  - `CLIENT-INSTANCE-ID: insomnia-test-instance`
  - `CLIENT-SESSION-ID: 1000000001`
- Body (raw JSON):
```json
{
  "name": "smoke_test_event",
  "type": "page_view",
  "properties": {
    "page": "dashboard",
    "source": "insomnia"
  }
}
```
- Expected status: `200`

**2. PUT /api/wallet/monitor/event** — Logs monitoring event
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/monitor/event`
- Headers: default three + `Content-Type: application/json`
- Body:
```json
{
  "name": "insomnia_smoke_test",
  "type": "INFO",
  "uid": "insomnia-uid-001",
  "payload": {
    "action": "smoke_test",
    "timestamp": "2025-01-01T00:00:00Z"
  }
}
```
- Note: `type` must be one of: `INFO`, `WARN`, `ERROR`, `DEBUG`
- Expected status: `200`

### Folder: Preflight & Bootstrap

**3. GET /api/wallet/preflight** — Bootstrap preflight response
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/preflight`
- No query params, no body
- Expected status: `200`

**4. GET /api/wallet/scaRegistrationStatus** — SCA registration status
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/scaRegistrationStatus`
- No query params, no body
- Expected status: `200`

**5. GET /api/wallet/v2/verification-progress/extended** — Verification progress
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/v2/verification-progress/extended`
- Note: The actual controller path includes `/extended`. Traffic log shows the shorter path — use the full controller path.
- No query params, no body
- Expected status: `200`

### Folder: Transaction History & Analytics

**6. GET /api/wallet/v3/transaction-history** — Transaction history v3
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/v3/transaction-history`
- No required query params
- Expected status: `200`

**7. GET /api/wallet/v1/analytics/CASHFLOW/EUR** — Analytics cashflow (EUR)
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/v1/analytics/CASHFLOW/EUR`
- Query params:
  - `period` = `MONTH` (required)
  - `language` = `en` (required)
- Expected status: `200`

**8. GET /api/wallet/v1/analytics/CASHFLOW/USD** — Analytics cashflow (USD)
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/v1/analytics/CASHFLOW/USD`
- Query params:
  - `period` = `MONTH`
  - `language` = `en`
- Expected status: `200`

### Folder: User Profile & Settings

**9. GET /api/wallet/user/restrictions** — User restrictions
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/user/restrictions`
- Query params (optional):
  - `filterByPriority` = `false`
- Expected status: `200`

**10. GET /api/wallet/ads-info** — User ads info
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/ads-info`
- No required query params
- Expected status: `200`

**11. GET /api/wallet/v1/cmpl-announcement** — Compliance announcement
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/v1/cmpl-announcement`
- No required query params
- Expected status: `200`

**12. GET /api/wallet/profile-settings** — Profile settings
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/profile-settings`
- No query params, no body
- Expected status: `200`

**13. GET /api/wallet/verifications/kyc/info** — KYC info
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/verifications/kyc/info`
- No query params, no body
- Expected status: `200`

### Folder: Currencies & Deals

**14. GET /api/wallet/v2/currencies** — Currencies v2 (with tickers)
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/v2/currencies`
- No query params, no body
- Expected status: `200`

**15. GET /api/wallet/deals/eligibility** — Deals eligibility
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/deals/eligibility`
- No query params, no body
- Expected status: `200`

### Folder: Merchant & Referral

**16. GET /api/wallet/merchant/v3/pay-online-merchants** — Pay-online merchants v3
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/merchant/v3/pay-online-merchants`
- No query params, no body
- Expected status: `200`

**17. GET /api/wallet/raf/v1/program-info** — Refer-a-friend program info
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/raf/v1/program-info`
- Headers (in addition to default three):
  - `brand` = `Skrill`
- No required query params
- Expected status: `200`

### Folder: Deposit

**18. GET /api/wallet/deposit/payment-options** — Deposit payment options (v1)
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/deposit/payment-options`
- Query params (all optional):
  - `language` = `en`
- Expected status: `200`

**19. GET /api/wallet/deposit/v3/payment-options** — Deposit payment options (v3)
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/deposit/v3/payment-options`
- Query params (all optional):
  - `language` = `en`
- Expected status: `200`

**20. GET /api/wallet/deposit/v3/payment-options/google-pay** — Google Pay deposit options
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/deposit/v3/payment-options/google-pay`
- No required query params
- Expected status: `204` (No Content — this is the expected success status)

**21. GET /api/wallet/deposit/v2/last-successful** — Last successful deposit (v2)
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/deposit/v2/last-successful`
- Note: Traffic log shows `/api/wallet/deposit/v2/last-successful` but API reference documents `/api/wallet/deposit/last-successful`. Use the v2 path from traffic.
- Query params:
  - `includeBankwire` = `true` (required)
- Expected status: `200`

**22. GET /api/wallet/deposit/limits** — Deposit limits
- URL: `{{ _.local-paysafe-wallet-switch }}/api/wallet/deposit/limits`
- Query params (all required):
  - `fromCurrency` = `EUR`
  - `toCurrency` = `USD`
  - `maxAmount` = `10000`
  - `minAmount` = `10`
- Expected status: `200`

---

## Output requirements

1. Produce a single valid **Insomnia v4 export JSON file**.
2. All requests must use `{{ _.local-paysafe-wallet-switch }}` as the host — never a hardcoded URL.
3. `Authorization`, `x-internal-brand`, and `Accept` headers must appear on **every request** (except `Authorization` on the token-fetch request). Insomnia has no collection-level header inheritance — put them explicitly on each request.
4. Each request must have a descriptive `name` (e.g., "GET Preflight Bootstrap", "POST Usage Event") and a `description` field.
5. Include **after-response scripts** on each request (except the token-fetch) that assert:
   - The expected HTTP status code
   - Response time < 5000ms
   - Example script:
   ```javascript
   const status = insomnia.response.status();
   if (status !== EXPECTED_STATUS) {
     throw new Error(`Expected ${EXPECTED_STATUS}, got ${status}`);
   }
   ```
6. Group requests into the folders defined above using `parentId` references.
7. The token-fetch request must use the exact URL, headers, and form fields specified in the Auth section above — no placeholders.
8. Every `request` resource must include: `_id`, `_type`, `parentId`, `name`, `description`, `method`, `url`, `headers` (array of `{name, value}`), `body` (if applicable), `parameters` (query params as array of `{name, value}`), `authentication` (set to `{}`).

## Format

Output a single file: `paysafe-wallet-switch-top22.insomnia.json`

Do NOT output explanations — just the JSON file. If anything is ambiguous, prefer a working collection with placeholder comments over asking questions.