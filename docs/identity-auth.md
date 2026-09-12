# Identity foundation (#72)

The API can persist users, authenticate passwords, issue revocable bearer sessions, and resolve a current principal. This implements [issue #72](https://github.com/Michelia-L/AI-WealthPilot/issues/72).

## Scope

Only `GET /api/auth/me` and `POST /api/auth/logout` require authentication in this increment. Existing profile, IPS, monitoring, settings, portfolio, and other business APIs retain their existing behavior. The Web workstation does not yet have a login page or forward these sessions. This foundation does **not** make the application a protected multi-user deployment.

The principal contains `user_id`, `email`, and `is_demo`. It has no implied role, organization, membership, client ownership, or advisor assignment. Those belong to #73 and #74; securing existing routes belongs to #75. An email is a case-insensitive login identifier and is not verified by email delivery.

## Local setup

From the repository root with the Python environment active:

```bash
python -m api.create_user
```

For Compose, use an interactive terminal:

```bash
docker compose exec api python -m api.create_user
```

The command prompts for email, password, and password confirmation. Passwords must contain 15–1024 characters; spaces and Unicode are preserved. Password entry fails if the terminal cannot hide it. Credentials are not accepted as command-line arguments, printed on success, or included in controlled error messages. Duplicate normalized emails are rejected. There is no default password, public registration endpoint, email verification, password-reset workflow, MFA, or SSO integration.

Provisioning and the API use the same configured `AIWP_DB_URL`, defaulting to `data/wealthpilot.db`. Use the same configuration for both. Application startup adds `users` and `auth_sessions` tables via the existing idempotent initialization; it does not alter or assign existing profiles. Startup does not provision a local user automatically.

## API contract

| Method and path | Input | Result |
| --- | --- | --- |
| `POST /api/auth/login` | JSON `email`, `password` | `access_token`, `token_type: "bearer"`, UTC `expires_at` |
| `POST /api/auth/demo` | No credentials; requires `DEMO_MODE=1` | Same session response for the shared demo identity |
| `GET /api/auth/me` | `Authorization: Bearer <access_token>` | Server-resolved `user_id`, `email`, `is_demo` |
| `POST /api/auth/logout` | Same bearer header | HTTP 204; revokes this session only |

Missing, malformed, unknown, expired, revoked, or disabled-user credentials return HTTP 401 with `WWW-Authenticate: Bearer`. Bad login credentials, unavailable accounts, and temporary login cooldowns share the same generic 401 response. Invalid login bodies return a sanitized 422 response without echoing submitted values. `X-Locale: en` or `zh` selects API error text, defaulting to English.

When both password-hashing slots are occupied, password login immediately returns a localized HTTP 503 with `Retry-After: 1`. Capacity rejection does not count as a failed password attempt or issue a session. Clients should back off before retrying.

Bearer tokens must be sent in the `Authorization` header; cookies, query parameters, user IDs, and role headers do not authenticate requests. Successful identity responses and authentication/validation errors use `Cache-Control: no-store`. The API stores no browser session cookie.

The following local example keeps credentials and the bearer token in process memory and prints only response status codes:

```python
import getpass
import requests

origin = "http://127.0.0.1:8000"
with requests.Session() as client:
    response = client.post(
        f"{origin}/api/auth/login",
        json={"email": input("Email: "), "password": getpass.getpass()},
        timeout=30,
    )
    response.raise_for_status()
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    print(client.get(f"{origin}/api/auth/me", timeout=30).status_code)  # 200
    print(client.post(f"{origin}/api/auth/logout", timeout=30).status_code)  # 204
    print(client.get(f"{origin}/api/auth/me", timeout=30).status_code)  # 401
```

## Session and password behavior

- Sessions expire 12 hours after issuance, without sliding renewal. Each login issues an independent random 256-bit token. Only its SHA-256 digest, user ID, creation time, and expiry are persisted. Expired session rows are removed when a new session is issued.
- Sessions survive API restarts. Logout permanently deletes the presented session from SQLite; other sessions remain valid. Every protected request rechecks user existence and active status. `is_active=False` is a **temporary authentication pause**, not session revocation: rows remain stored, and re-enabling the user restores unexpired, non-logged-out sessions. Removing a user prevents lookup of that identity. This increment has no administrative disable/re-enable or revoke-all endpoint.
- Passwords use independently salted scrypt hashes (`N=2^17`, `r=8`, `p=1`), with a versioned storage format. These parameters follow the [OWASP scrypt baseline](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt). When capacity is available, unknown users still incur password-hash work; hash comparison uses constant-time comparison. Concurrent hashing is bounded to two operations per API process. Slot acquisition is nonblocking: excess requests receive 503 instead of occupying shared FastAPI/AnyIO workers while waiting. Slots are released even if hashing raises an exception.
- Five consecutive failed password attempts lock that user out of new password logins for five minutes. A successful login resets the counter; after a cooldown the next failed attempt starts a new counter. State is persisted and increments are atomic. This does not revoke existing sessions and is not a deployment-wide request limiter. Network-level rate limiting and HTTPS are still required before exposing authentication beyond localhost, alongside the unfinished business authorization controls.

An attacker who knows an email can repeatedly trigger the account-only lockout and deny that user new logins. The current cooldown is not sufficient protection for external deployments. [KI-004](known-issues.md#ki-004--认证对外部署前的限流与撤销边界) tracks combined account/source rate limiting or bounded progressive backoff, plus permanent all-session revocation for security-sensitive account disablement. Future administrative disablement must explicitly revoke sessions (for example, via transactional deletion or session versioning); flipping `is_active` alone does not provide that guarantee.

## Demo strategy

With `DEMO_MODE=1`, callers explicitly request `POST /api/auth/demo`. On first use it creates one persisted, passwordless, fictional identity (`demo@wealthpilot.invalid`). Subsequent demo logins reuse that identity and issue independent ordinary bearer sessions. Local provisioning reserves this identifier.

Demo mode does not automatically authenticate anonymous requests. Demo sessions pass through the same database lookup, expiry, active-user checks, principal dependency, and logout behavior as password sessions. The demo endpoint returns 404 when demo mode is disabled, and existing demo sessions are rejected while it is disabled. Password-based local identities continue to use their normal login flow in either mode. No demo identity is automatically attached to an existing client profile.

Turning demo mode back on restores any demo sessions that have neither expired nor been logged out. Mode changes pause authentication and do not permanently revoke tokens. This behavior is covered by regression tests and shares the revocation follow-up in KI-004.

## Route integration and validation

Future protected routes use `principal: Principal = Depends(get_current_principal)` from `api.auth` and `api.schemas`. Identity alone does not authorize access to a requested client or resource. Do not trust submitted user IDs or roles as a substitute for this dependency or future object-access checks.

Run the targeted tests with:

```bash
python -m pytest -q tests/test_api_auth.py tests/test_api_profiles.py tests/test_api_demo_mode.py tests/test_api_i18n.py
ruff check
ruff format --check
```

The authentication tests use generated temporary credentials and temporary SQLite databases. They exercise actual password hashing, restart persistence, expiry, revocation, account disablement, login cooldowns, demo gating, input redaction, locale errors, OpenAPI security declarations, local provisioning, and additive compatibility with a pre-identity profile table.
