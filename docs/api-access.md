# Existing API access (#75)

All business API requests require an active bearer session. OpenAPI records every operation's `x-access-scope` and bearer security requirement. `GET /api/health`, password login, and explicit demo login are public. `/docs`, `/redoc`, and `/openapi.json` expose API documentation, not customer data.

## Workspace selection and roles

For workstation routes, send `X-Organization-ID` with the session. Client Portal `/api/me/*` instead derives a unique linked Client from the session; see [Client API and publication](client-publication.md). The API infers the organization only when the caller has exactly one membership. Missing membership, an unknown scope, or ambiguous selection returns generic 403. A header selects a scope; it cannot grant membership or a role. Missing, invalid, expired, or revoked sessions return 401 with `WWW-Authenticate: Bearer`.

On workstation routes, advisors access explicitly assigned Clients and admins access all Clients in the selected organization. Client Portal routes independently resolve the caller’s own linked Client. Object lookups return the same localized 404 for absent and inaccessible objects. Lists filter by those rules before applying storage limits. All business responses use `Cache-Control: no-store`.

## Route audit

Paths below are relative to `/api`. “Staff” means advisor or admin in the selected organization; client-bound staff operations also apply the assignment/organization rule.

| Operations | OpenAPI scope | Access and data binding |
| --- | --- | --- |
| `GET /health`; `POST /auth/login`, `/auth/demo` | public | Health metadata or credential/demo validation only |
| `GET /auth/me`, `/auth/organizations`; `POST /auth/logout` | authenticated | Current session or its membership list; logout revokes that session |
| `GET /market/*` | shared | Any authenticated identity; shared market data, no customer lookup |
| `GET /profiles/questionnaire` | advisor-scoped | Staff; shared questionnaire |
| `GET /profiles`, `/profiles/{id}`; `PUT /profiles/{id}` | advisor-scoped | Staff; assigned or same-organization profiles |
| `POST /profiles`; `GET /profiles/compare`; `DELETE /profiles/{id}` | advisor-scoped | Staff; every compared/deleted profile checked. New profile belongs to the selected organization; an advisor creator receives an assignment to that new Client |
| `POST /profiles/import/upload` | admin-scoped | Import and deduplication confined to selected organization |
| `POST /profiles/import` | admin-scoped | Local organization admin, excluding demo identities; reads server-local legacy files |
| `GET /ips`, `/ips/{id}`, `/ips/{id}/pdf`, `/ips/{id}/export` | advisor-scoped | Staff; SQL artifact ownership checked before reading raw payload or audit trail |
| `POST /ips/generate`; `GET /ips/tasks/{id}/events` | advisor-scoped | Authorized profile before generation; persisted task ownership before live/replayed SSE |
| All `/advisor/*` | advisor-scoped | Staff; stream/save check profile, and report list/read/delete/export/PDF check indexed organization and Client ID |
| All `/monitoring/*` | advisor-scoped | Staff; IPS ownership before holdings, analysis, backtest, or advice. Optional advice profile is checked too. Fleet inputs are filtered and cache entries distinguish caller and organization |
| All `/portfolio/*` | advisor-scoped | Staff; any supplied profile is checked before recommendation or optimization. Task events check kind, organization and Client ID, or creator for a task with no profile |
| All `/retirement/*` | advisor-scoped | Staff; supplied profile checked before CME suggestion. Simulation uses submitted inputs only |
| All `/cme/*` | advisor-scoped | Staff; shared assumptions and cache refresh, no customer lookup |
| All `/settings/*` | admin-scoped | Deployment-global configuration is limited to local organization admins. Demo organization admins can read a synthetic settings status, but cannot change settings or probe model providers |

Client-facing reads and acknowledgements use `/me/*`; staff publication operations use `/documents/*` and `/ips/{id}/documents`. Their contracts and transitions are documented in [Client API and publication](client-publication.md).

## Stable artifacts and upgrade behavior

New IPS documents and advisor reports store the originating Client UUID and an authoritative SQL ownership index. Report saves require `profile_id`; the server resolves and stamps the Client and current profile name. Submitted client names or extra ownership fields do not determine access. New task records store organization, creator, and optional Client UUID; task kind must match the events endpoint.

Startup indexes artifacts with a valid stored Client UUID and migrates valid task ownership into dedicated columns. Unindexed IPS/reports and unowned tasks remain hidden and return 404. Matching a client name or an old numeric profile ID does not imply ownership. See [resource ownership and explicit legacy adoption](resource-ownership.md) for the full inventory, constraints and migration procedure. Payload files are not rewritten or deleted. Deleting/recreating a numeric profile cannot transfer access to its prior Client's artifacts.

## Web and local setup

The Web sign-in form uses the same backend sessions. `wp_session` is HttpOnly and SameSite=Lax, with Secure enabled on HTTPS. The workspace cookie is also HttpOnly; the organization selection endpoint validates membership. Server-rendered reads, JSON mutations, SSE, and downloads forward the session and workspace server-side. Browser-provided authorization or role headers are not used by these proxies. Unsafe same-origin API requests require an exact matching Origin, including sign-in and sign-out. Sign-out revokes the backend session before clearing cookies, then reloads the page and clears the active-client selection.

For local development, use the same database configuration as the backend:

```bash
python -m api.create_user --local-admin
# Compose:
docker compose exec api python -m api.create_user --local-admin
```

Without `--local-admin`, provisioning creates an identity without workspace access. Membership and assignment management remains an internal service; there is no self-service role grant. A login with no workspace shows an access message.

With `DEMO_MODE=1`, choose **Try demo**. Explicit demo login receives admin membership in the separate `demo` organization. It cannot read the `local` organization's existing data or change deployment settings. On an empty database, the fictional seed belongs to `demo`; startup never reassigns pre-existing profiles.

Authorization is checked when a request/stream is opened, including every SSE reconnect. An already open stream is not forcibly disconnected by logout or assignment changes. Production deployment still needs the authentication hardening tracked in [KI-004](known-issues.md#ki-004--认证对外部署前的限流与撤销边界); #75 does not claim those controls are complete.

## Verification

`tests/test_api_access.py` checks every existing operation's anonymous denial and scope declaration, plus real bearer sessions across roles, clients and organizations, assignment changes, exports, task replay, and demo isolation. Existing API tests use explicitly provisioned local admin sessions and owned fixture artifacts. Web tests cover session cookies, forwarding and origin checks; Playwright exercises sign-in/out and the existing demo workflows through the authenticated proxies.
