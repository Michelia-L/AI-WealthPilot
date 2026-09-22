# Resource ownership and migration (#76)

Authentication and role checks are described in [API access](api-access.md). This document records the persistence boundary: selecting a workspace never grants access to another organization's resources, and a file name, display name or numeric profile ID cannot establish ownership.

## Resource inventory

| Resource | Scope | Persistence and access |
| --- | --- | --- |
| User / authentication session | User | `users` / `auth_sessions`; sessions belong to a login identity, not a workspace role |
| Membership / advisor assignment | Organization | Organization/user membership and organization/client assignment constraints |
| Client profile | Client | `client_profiles.client_id → clients.organization_id`; API queries use the shared authorized-client subquery |
| IPS, embedded audit trail, AI-generated IPS content | Client | JSON payload plus authoritative `artifacts` index: kind, ID, filename, organization, Client UUID and nullable creator |
| Published document versions | Client | SQLite `document_versions` stores immutable submitted content, version identity and human workflow history; only published/acknowledged versions appear through `/me/reports` ([publication lifecycle](client-publication.md)) |
| Saved advisor report / generated deliverable | Client | Same index with kind `report`; ownership is queried before opening payload files, including exports/deletes |
| Background task and persisted SSE events | Client, or user within an organization | Indexed `background_tasks.organization_id`, `client_id`, `created_by`; profile-bound tasks follow Client access, otherwise only the creator can replay them in the selected organization |
| Portfolio recommendation / optimization | Request, or task scope | Synchronous results are not persisted separately. Async optimization results live in their scoped task event log; saved IPS allocations inherit IPS ownership |
| Retirement analysis | Request | Simulations use submitted inputs and have no separate persisted analysis record. Profile-based suggestions authorize that profile before reading it |
| Actual holdings / monitoring history | Client | `holding_snapshots` stores organization, Client UUID and creator alongside document ID. Reads constrain organization and require the snapshot's Client to match the indexed IPS owner |
| Monitoring results / AI rebalance advice | Request; cache scoped to caller and organization | Results and advice are not separately persisted. Fleet cache keys include organization, user, date and locale; inputs are authorized document IDs and scoped snapshots |
| LLM settings | Deployment-global | `app_settings.scope = 'deployment'` is enforced by a DB check. Only non-demo local-workspace admins can change configuration; all tenants share the resulting provider settings |
| CME files, market/rate/price caches, quantitative backtest cache | Global shared research data | CME files and parameter-keyed market/quantitative caches contain no profile ownership, saved report or account identity. They are not customer records |
| Standalone profile JSON / unindexed standalone IPS and reports | Local operator files, not API-visible resources | Profile import creates a destination-scoped Client. Artifact adoption requires the validated process below; arbitrary standalone files do not grant API access |
| HTML/PDF/Markdown exports | Source artifact scope | Generated on demand after source authorization; temporary API export files are removed. Downloads retained outside the service are outside its access boundary |

New artifact, task and holdings writes derive ownership from the authenticated request or persisted task, never from client-submitted owner fields. Composite foreign keys reject a Client UUID from another organization. Historical creator identities remain null when unknown; migration does not invent them. Artifact index `created_at` records registration time; original generation timestamps remain in the unchanged payload. Profiles continue to use the existing Client relationship rather than duplicating organization IDs.

The artifact SQL index is authoritative. API lists stream authorized index rows in descending filename order, load and validate each payload once, and stop at the requested number of valid matching summaries (50 by default). Missing/corrupt files and report-name filters can require scanning further. Fleet calculations reuse those validated IPS payloads. Existing JSON formats remain compatible with standalone domain tools. An unindexed file returns 404 through the API, including a newly written standalone file. A payload that conflicts with its indexed owner is rejected. File symlinks are not adopted or served. Missing payload files remain inaccessible; the ownership index is retained so a later restore cannot silently reassign an ID.

## Automatic upgrade

On startup, `init_db()` runs under SQLite `BEGIN IMMEDIATE`:

1. Create missing tables and apply the existing profile ownership migration.
2. Rebuild the recognized pre-#76 task, holdings and settings tables with ownership columns and constraints, preserving IDs, timestamps, raw JSON and setting values.
3. Index existing IPS/report files only when their stored stable Client UUID resolves to a Client. Derive the organization from that Client and reject conflicting stored organization metadata.
4. Promote valid #75 task ownership metadata into dedicated columns. Unknown or conflicting ownership stays null and cannot be accessed through task endpoints.
5. Backfill legacy holdings ownership from the indexed IPS, never from a client name or numeric profile ID.

Partially upgraded tables with missing required constraints are rejected. The database changes commit together or roll back together, including DDL. Running initialization again is safe. Artifact payload files are neither rewritten nor deleted. If different files share an ID that had no authoritative index before this scan, migration aborts and rolls back the entire batch; directory order never chooses the owner. If the ID was already indexed, that ownership is preserved and extra conflicting files count as unresolved. Resolve duplicate legacy IDs in an operator-reviewed copy before retrying. Malformed, missing-owner and dangling-owner files remain unindexed; ownership indexes already present are never reassigned. Keep the SQLite database and artifact directories together in backups and restores.

## Explicit legacy adoption

Stop API writers and back up the database and artifact directories before an operator migration. Use the same `AIWP_DB_URL` and data directories as the service. Review ownership outside the application; a name match alone is insufficient evidence.

Create a JSON mapping with exact filenames and existing organization/Client IDs:

```json
[
  {
    "kind": "ips",
    "filename": "ips_legacy_example.json",
    "organization_id": "existing-organization-id",
    "client_id": "existing-client-uuid"
  }
]
```

Use `kind: "report"` for a saved advisor report. Each entry must contain exactly those four fields. Paths outside the artifact directory, symlinks, missing files, conflicting ownership and duplicate mappings are rejected. Profile IDs and client names are not mapping keys.

```bash
# Validate and show aggregate counts; roll back all DB changes by default.
python -m api.migrate_resources --mapping ownership-map.json

# Apply the same reviewed mapping in one transaction.
python -m api.migrate_resources --mapping ownership-map.json --apply
```

With no mapping, the CLI audits/adopts only the same stable-UUID resources recognized by startup. It reports counts, not customer content or secrets. A failure rolls back the entire batch. Explicitly adopting an IPS also scopes its previously unowned holdings history. Existing indexed ownership cannot be changed by rerunning the mapping.

Legacy tasks without trustworthy #75 ownership remain inaccessible; there is no task-ID adoption shortcut. Regenerate the analysis under an authorized session if needed. No migration grants a login, membership or advisor assignment.

## Verification and limits

`tests/test_resource_ownership.py` covers stable-UUID migration, unknown/conflicting owners, explicit adoption, dry runs, idempotency, payload preservation, unsafe paths, DB constraints and rollback after DDL. API tests cover cross-client/organization access, assignment changes, authorization before file loading, task metadata tampering, restored SSE events and mismatched snapshot ownership. Browser tests exercise generated IPS, reports, task flows and holdings through authenticated proxies.

A JSON file write and SQLite commit are not one filesystem transaction. API completion is reported only after the ownership index is committed; an interrupted save can leave an unindexed file. Startup can recover it only if it carries a valid stable Client UUID. Do not change that UUID to transfer resources between clients.

This issue does not add publication/versioning rules (#78), client-specific DTOs (#77), or a Client Portal (#80). As with #75, access is checked on each request or stream reconnect; already-open streams are not forcibly terminated on a subsequent assignment change.
