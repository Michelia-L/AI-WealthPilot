# Client Portal (#80)

The existing Next.js application serves two product surfaces. Advisor and admin
memberships use the Advisor Console at `/`; a selected client membership uses
the Client Portal at `/client`. Opening a console URL as a client redirects to
`/client`. Opening `/client` as an advisor or admin redirects to the console.
Users with multiple memberships choose their workspace through the existing
session controls. The API independently authorizes every data request.

## Access and account links

The portal uses the existing sign-in form and HttpOnly session cookie. Access
requires both a `client` organization membership and a Client linked through
`clients.user_id`. Provisioning a login alone does not grant this access.
Membership and account linking remain operator tasks using the existing
[ownership services](client-ownership.md); this change adds no public signup or
account-management endpoints. An absent or ambiguous link shows an access error
with retry, workspace selection and sign-out controls. The portal never guesses
a customer from an email, name, query string or saved advisor selection.

**Try demo** continues to open the shared demo administrator's Advisor Console.
It does not impersonate a client. Portal E2E tests provision fictional client
identities only in the throwaway Playwright database.

## Pages and current data

| Route | Data and behavior |
| --- | --- |
| `/client` | Recorded financial summary, latest published target allocation, assessed risk, goals, recent publications and assigned advisor contacts |
| `/client/portfolio` | Latest published IPS target weights and recommendation, with a link to that exact document version |
| `/client/goals` | Recorded goals, manual or priority-weighted planning budgets, funding coverage, annual contributions, required returns and years to target at 0% return; actual goal balances are not tracked |
| `/client/risk-profile` | Plain-language risk explanation and basic profile context; incomplete assessments have an explicit state |
| `/client/documents` | Published and acknowledged versions, paginated in groups of 20 |
| `/client/documents/{id}` | The authorized version's reviewed content and persistent, idempotent read acknowledgement |
| `/client/ai` | One question at a time through the existing client assistant; demo answers are identified as demo responses |

Profile information is read-only. Financial amounts retain their recorded units;
the profile contract does not provide a currency code, so the portal does not
invent a currency symbol or apply conversion. Actual holdings, investment
performance, drawdown and benchmark comparisons are unavailable in the current
client contract. Suggested IPS targets are not shown as executed holdings.

Goal planning uses the shared `src/portfolio/goals.py` service. Advisors can set
manual asset and annual contribution budgets per goal in the profile editor.
These budgets reserve recorded investable assets and positive annual savings;
other evaluable goals share the remainder with priority weights high 3, medium 2,
low 1. Turning off a manual budget restores automatic allocation. Explicit zero
budgets remain zero; when all goals have manual budgets, unassigned funds stay
outside the goals. Saving and JSON import reject incomplete goals with manual
budgets and totals that exceed available assets or positive annual savings.
Each goal identifies its budget method and shows its planning budget
divided by its nominal target, the uncovered target amount and the annual return
needed with constant end-of-year contributions. Targets with a missing amount
or horizon remain visible without a calculation. Coverage above 100% retains
its numeric value while the bar stops at 100%.

Manual amounts are saved with their goals; automatic amounts are recalculated
from the profile. Neither represents persisted subaccounts or realized savings.
They require no market or LLM request and do not expose
unpublished advisor recommendations. Funding states distinguish coverage by
the current budget, coverage with savings at zero return, required investment
growth and an unsolved funding requirement. They are not success probabilities.
The zero-return timeline shows the first year-end reaching the target with
constant annual contributions, up to 80 years. An already covered target has
zero years; a target not reached within that range has an explicit unavailable
state. This scenario is not a market forecast. Inflation, tax and fees are
excluded. Actual goal balances, projected wealth,
success probability and what-if calculations remain follow-up work under
[#48](https://github.com/Michelia-L/AI-WealthPilot/issues/48). The frontend only
formats these API calculations.

Read acknowledgement records only that the client read that version. It does not
approve or execute transactions. Stored document content retains its publication
language when the interface switches languages. Each AI question is independent;
conversation history is not submitted. Live assistant requests use the existing
provider configuration and may send the caller's authorized client context to
that provider. The [assistant permission boundary](agent-permissions.md) applies.

## Implementation and verification

Advisor pages are grouped under `web/src/app/(advisor)/` without changing their
URLs. The root layout owns fonts, locale and the common session gate. The portal
has its own layout and responsive navigation, with no advisor client selector,
optimizer, raw artifact viewer or settings controls.

Server-rendered portal reads use the `/api/me/*` domain client in
`web/src/lib/api/client-portal-server.ts`, forwarding the session and explicit
locale with `cache: no-store`. The only browser mutations are same-origin
`POST /api/me/assistant` and `POST /api/me/reports/{id}/acknowledge`, which reuse
the existing proxy and origin checks. No backend authorization rules or
financial calculations are duplicated in the frontend.

`web/e2e/client-portal.spec.ts` exercises both product surfaces with actual
sessions and APIs, copied cross-client document links, hidden drafts, forged
selectors, read acknowledgement, role removal, ambiguous links, empty states,
English/Chinese switching, assistant responses and mobile navigation. Component
and transport tests cover pending and failure states and authenticated forwarding.
