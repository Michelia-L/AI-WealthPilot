# Client access and advisor assignments (#74)

The API provides shared authorization primitives for [issue #74](https://github.com/Michelia-L/AI-WealthPilot/issues/74), using the [identity layer](identity-auth.md) and [organization/client ownership model](client-ownership.md).

## Permission rules

Every operation takes an explicit `organization_id`. That value selects a scope to check; it never grants membership. A user with memberships in several organizations is evaluated only in the requested organization. Roles, client links, and assignments are read from the database on each check, rather than taken from the principal, headers, request bodies, or cached role decisions.

| Membership role in the selected organization | Accessible Clients |
| --- | --- |
| `client` | Only Clients in that organization whose optional `user_id` equals the authenticated user's ID. A login link without membership grants no access. |
| `advisor` | Only Clients in that organization with an explicit assignment to this advisor. A link to the advisor's own business Client does not substitute for an assignment. |
| `admin` | All Clients in that organization, including Clients without login identities. There is no deployment-wide admin bypass. |
| No membership | None. |

`require_client`, `require_advisor`, and `require_org_admin` check exact organization roles. Passing a role guard alone does not authorize access to a particular Client. `get_authorized_client` applies the role-specific object rule and returns the authorized Client. An admin in organization A with a client membership in B has only client privileges in B.

The principal must come from `api.auth.get_current_principal`. The authorization service also checks that the identity still exists, is active, and is allowed by demo mode, but does not itself validate a bearer token. Passing a fabricated `Principal(user_id=...)` from untrusted request data defeats the caller's authentication boundary and is never a supported integration.

## HTTP behavior

| Situation | Result |
| --- | --- |
| Missing/invalid/expired/revoked bearer session | `401`, through the existing identity dependency, with `WWW-Authenticate: Bearer`. |
| Missing, disabled, or currently disallowed demo identity | `401`. |
| Wrong or absent membership for a role-only operation | Generic `403`, including a nonexistent organization scope. |
| Missing Client, wrong organization, absent membership, wrong owner, or missing advisor assignment | Identical generic `404`: `Client not found.` |
| Admin attempts to assign an absent, inactive, or non-advisor identity in their organization | Generic `422`. |

These errors use `api/i18n.py` (`X-Locale: en/zh`) and `Cache-Control: no-store`. They do not echo user IDs, client IDs, organization IDs, profiles, or credentials. Object denial and absence share the same response to avoid exposing whether an inaccessible Client exists; this is not a constant-time guarantee.

## Assignment persistence and lifecycle

`advisor_client_assignments` stores UUID `id`, required `organization_id`, `advisor_user_id`, `client_id`, and `created_at`. The organization/advisor/client tuple is unique. Composite foreign keys require the advisor to be a member of that same organization and the Client to belong to it. SQLite rejects cross-organization assignments, duplicates, and dangling references even for direct SQL writes. Advisor and client lookup columns are indexed.

`assign_advisor` and `unassign_advisor` both require an authenticated admin of the selected organization. Assignment creation also verifies the target's current advisor role and active identity. Repeated creation preserves the assignment ID and timestamp; repeated revocation is a no-op. Both services leave commit and rollback to their caller and share the caller's database transaction. The database verifies membership existence; current role eligibility is enforced by the service and checked again at access time.

An assignment is not a role grant. Demoting an advisor immediately changes the rules applied to that identity, even if assignment rows remain. Re-promoting the identity can restore access through those retained assignments; use `unassign_advisor` for permanent revocation. It works for demoted or inactive advisors too. Removing an assigned membership or moving/deleting an assigned Client is rejected by foreign keys until the assignments are explicitly removed. No implicit cascading deletion or cross-organization reassignment is configured.

Explicit demo login grants admin membership in the dedicated `demo` organization. It grants no access to `local` or other organizations; demo identities follow the same object checks. Disabling demo mode rejects those identities through the existing authentication policy.

## Upgrade from #73

`init_db()` creates the assignment table and ensures the composite unique parent index on `clients(organization_id, id)` exists, including on an existing #73 database. This index enables the composite SQLite foreign key without rewriting Client records. Initialization runs in the existing `BEGIN IMMEDIATE` transaction and can be repeated. Existing users, memberships, Clients, and profiles are preserved; no assignments or permissions are inferred from legacy data. The existing profile migration and constraint checks continue to run.

## Route integration boundary

Existing routes now enforce authentication and scoped authorization; the [route audit](api-access.md) records each group and its object checks. Assignment management remains an internal service with no public management endpoint. The [resource ownership inventory and migration](resource-ownership.md) extend these checks to file artifacts, task replay, holdings and deployment settings.

Additional routes can use the helpers with an explicit scope and the real identity dependency:

```python
from fastapi import Depends
from sqlmodel import Session

from api.auth import get_current_principal
from api.authorization import get_authorized_client
from api.db import get_session
from api.i18n import get_request_locale
from api.schemas import Principal


@router.get("/organizations/{organization_id}/clients/{client_id}")
def client_detail(
    organization_id: str,
    client_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
    locale: str = Depends(get_request_locale),
):
    client = get_authorized_client(
        session, principal, organization_id, client_id, locale=locale
    )
    return {"id": client.id}
```

This example demonstrates the Client check only. Routes returning profiles, reports, tasks, or other records must also bind every subsequent query to that authorized Client and organization, rather than trusting another submitted ID. Existing routes use `api/access.py` to bind profiles, artifacts, and tasks to authorized Clients.

## Validation

```bash
python -m pytest -q tests/test_authorization.py tests/test_ownership.py tests/test_api_auth.py tests/test_api_i18n.py
ruff check
ruff format --check
```

The tests cover the client/advisor/admin access matrix, multiple memberships, role and assignment changes, assignment service permissions and rollback, database tenant constraints, upgrading a #73 database, and test-only routes using real bearer sessions. The HTTP integration checks anonymous access, forged user/role headers, indistinguishable missing/forbidden responses, Chinese localization, and logout revocation.
