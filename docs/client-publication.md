# Client API and document publication (#77, #78)

Client Portal contracts are separate from the Advisor Workstation. They use the
same bearer sessions but do not accept a client, profile or organization selector.
The server joins the authenticated user to their Client and current `client`
organization membership. No matching link returns 404; multiple matching links
return 409 and require an operator to resolve the ambiguity. `X-Organization-ID`
and extra identity query parameters cannot change this scope. Staff continue to
use the workspace and assignment rules in [API access](api-access.md).

## Client endpoints

All paths below start with `/api/me` and use the `Client Portal` OpenAPI tag and
`client-scoped` access annotation.

| Method/path | Response |
| --- | --- |
| `GET /api/me` | Login identity and client role |
| `GET /profile` | Basic profile and financial summary; no advisor notes or questionnaire internals |
| `GET /portfolio` | Most recently published IPS target allocation and recommendation; not executed holdings |
| `GET /goals` | Recorded goals; per-goal progress is null because goal balances are not tracked |
| `GET /risk-profile` | Plain-language assessment using the domain model's lower-of-ability-and-willingness rule; explicit incomplete state |
| `GET /advisor` | Active, currently assigned advisors' contact emails |
| `GET /reports` | Published and acknowledged versions, with `limit` (1–100) and `offset` pagination |
| `GET /reports/{id}` | A published version's client-facing content |
| `POST /reports/{id}/acknowledge` | Record the linked client's acknowledgement; repeating it preserves the timestamp |

Actual portfolio performance is null, with a localized explanation. Backtests,
expected returns and synthetic data are not substituted for actual returns.
Profile access is read-only in this initial Client API. `/profiles/*` and `/ips/*`
are now staff endpoints, including their raw payloads and exports. A client cannot
bypass publication through those routes. Client responses exclude optimizer
settings, LLM configuration, machine review traces and staff approval metadata.
`X-Locale: en|zh` controls explanatory messages; stored document text retains the
language reviewed by the advisor. There is no Client Portal UI in this change.

## Publication workflow

`document_versions` stores each version's content in SQLite, separately from the
raw artifact files. It includes organization and Client UUIDs, a stable
`document_id` for the version series, a unique version `id`, integer `version`,
status, creator, reviewer, approver, publisher, acknowledging user and timestamps.
The route `{id}` is the version ID. Composite ownership foreign keys and unique `(document_id, version)` constraints
apply. Source-backed versions also enforce unique `(source_artifact_id, version)`,
so concurrent adoption cannot split one IPS into multiple logical series. Source
IDs are indexed for reimport lookup. Published rows require both a publication
timestamp and publisher identity. Back up the database to retain published
content and its approval history.

| Operation | Permission / transition |
| --- | --- |
| `POST /api/documents` | Assigned advisor or organization admin creates a draft from an authorized `profile_id`, `type` and client-facing `content` |
| `GET /api/documents` | Scoped versions; optional `profile_id`, `limit`, `offset` |
| `GET /api/documents/{id}` | Scoped content and staff workflow metadata |
| `PUT /api/documents/{id}` | Replace client-facing content while still `draft` |
| `POST /api/documents/{id}/submit` | Staff: `draft → in_review`; freezes content |
| `POST /api/documents/{id}/approve` | Organization admin: `in_review → approved`; records human reviewer/approver |
| `POST /api/documents/{id}/publish` | Staff: `approved → published` |
| `POST /api/documents/{id}/revisions` | Staff creates the next numbered draft; `{}` copies content or `{"content": ...}` replaces it |
| `POST /api/me/reports/{id}/acknowledge` | Owning client: `published → acknowledged` |

The existing organization admin role is the permitted reviewer. Advisors cannot
approve. An admin may also author a document; this implementation does not impose
a separate-author rule. Authorization reads current membership and assignment on
each request. Invalid transitions and edits to submitted versions return 409.
Conditional SQL updates prevent a stale draft edit from replacing submitted
content. Concurrent revision/adoption conflicts return 409 for retry. Concurrent
client acknowledgements are idempotent: once either request records the
acknowledgement, both observe the acknowledged version.

Published/acknowledged versions remain visible when a new draft is created.
Content is never overwritten in place after submission. Client reads use the
stored publication snapshot, so later file edits or deletion of the source IPS
do not change the approved version. Acknowledgement records receipt, not a trade
execution or acceptance of guaranteed results.

## IPS integration and existing data

New live and demo IPS generation validates the publication projection before
writing the raw artifact, then creates a publication draft in the same database
transaction as artifact registration before emitting the completed task event.
If that transaction fails, the newly written task artifact is removed so startup
migration cannot resurrect a failed generation. The projection selects narrative
sections and allocation targets; generated machine review results are not human
approval. IPS drafts may be incomplete while being prepared, but publication
requires a non-empty, normalized target allocation. The raw IPS and audit trail remain
available to authorized staff for research.

For an existing indexed IPS, `POST /api/ips/{artifact_id}/documents` creates a draft
from the authorized source. Reimporting the same artifact creates the next draft
version in its existing series. Startup creates the new table but does not publish
or invent approval history for legacy artifacts. Portfolio reviews and retirement
reports use the same typed document creation and lifecycle endpoints; their
existing calculation/generation routes do not automatically publish results.

The API permits only explicit client-facing content fields. Staff must review the
actual narrative before publication; schema allowlisting is not semantic
redaction of text an author deliberately enters.

## Verification

`tests/test_client_api.py` covers identity derivation, forged selectors, role
changes, missing/ambiguous links, DTO schemas, locale and raw-artifact denial.
`tests/test_documents.py` covers transitions, tenant/assignment authorization,
client visibility and acknowledgement, version preservation, source mutation,
stale edits, constraints and restart persistence. Existing IPS generation tests
exercise automatic draft integration.
