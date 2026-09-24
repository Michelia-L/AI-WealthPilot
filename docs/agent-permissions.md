# Client Assistant and Advisor Copilot (#79)

The assistant APIs share a stateless model loop, but have separate personas and
server-controlled tools. A prompt is not an authorization boundary. The existing
[session and assignment rules](api-access.md) apply to every tool execution.

## API contracts

| Endpoint | Caller | Body | Response |
| --- | --- | --- | --- |
| `POST /api/me/assistant` | Identity-linked client | `{"message":"Explain my published plan"}` | `{"answer":"…","demo":false}` |
| `POST /api/advisor/copilot` | Workspace advisor or admin | `{"message":"Review my assigned clients"}` | `{"answer":"…","demo":false}` |

Both require bearer sessions. Messages are limited to 8,000 characters. The body
does not accept role, persona, organization, client IDs, model settings, tools or
message history. `X-Locale: en|zh` selects the answer language and error copy.
The client endpoint ignores workspace selectors and derives its single Client
from the login identity. The copilot uses the existing `X-Organization-ID` workspace
selection rules. This change adds no frontend UI.

## Tool registry

`api/agent_tools.py` declares each tool's persona, allowed roles, scope and strict
argument schema. The model sees only permitted definitions. The dispatcher checks
the same restrictions independently, so inventing a hidden tool name cannot call
it. Extra identity or configuration arguments return a redacted 422.

| Persona | Tools | Scope |
| --- | --- | --- |
| Client | `read_own_profile`, `read_own_portfolio`, `read_own_goals` | No arguments; same allowlisted DTOs as `/api/me` |
| Client | `list_own_reports`, `read_own_report` | Only published/acknowledged snapshots belonging to the signed-in Client; detail accepts a report version ID |
| Advisor | `list_clients`, `read_client_profile` | Assigned profiles; admins see profiles in their own workspace |
| Advisor | `list_ips`, `read_ips` | Indexed IPS ownership, including staff research and machine review content |
| Advisor | `list_advisor_reports`, `read_advisor_report` | Indexed advisory report ownership |

Lists return at most 50 items. No tool can change settings, execute arbitrary SQL,
read arbitrary files, run organization monitoring, publish documents or execute
trades. The initial copilot supports read-only research within advisor workflows;
existing calculation and publication APIs remain separate.

Each invocation opens a fresh database session and rechecks session expiry/revocation,
account status, current membership, Client link and assignment. A run binds its
identity and workspace at entry. Relinking a client or changing a staff role cannot
silently switch the run's context. Previously read resources are checked again
before later provider requests and before returning the final answer. Revocation
stops further use of that context; it cannot retract data already sent to a provider.

## Model and response boundaries

The runtime resolves endpoint, model and API key through
`src/agents/llm_config.py`. Live mode needs a configured, function-calling-capable
OpenAI-compatible chat model. No live provider is exercised by the authorization
tests. Each run starts with server instructions and a single user message; there is
no cross-user conversation store or client-supplied system/tool message replay.
Only requested, authorized tool results are sent to the provider. Client tools
share `api/client_views.py` with the Client API and omit advisor notes, draft content,
machine reviews, approval actors and model configuration.

The loop permits at most 6 model requests and 12 tool calls, with a 120,000-character
aggregate internal-context limit and a separate 20,000-character final-answer limit.
For the official DeepSeek endpoint or a model whose final path segment starts with
`deepseek-`, each request explicitly sends `thinking: {type: disabled}` through
the SDK's `extra_body` and uses 4,096 output tokens. DeepSeek enables thinking by
default, so a small shared reasoning/answer budget can end before an answer or tool
call completes; see the official [thinking-mode controls](https://api-docs.deepseek.com/guides/thinking_mode/).
Other compatible models receive a 16,384-token output budget without DeepSeek-specific
parameters. Gateways using DeepSeek model names must support its thinking toggle.
These assistant settings do not change the long-form report/IPS generation policy.

Only `finish_reason=tool_calls` permits tool execution, and only `stop` permits a
final answer. A response containing tool calls alongside `length`, `content_filter`,
`insufficient_system_resource`, `aborted` or any other reason executes no tools;
see the official [completion termination states](https://api-docs.deepseek.com/api/create-chat-completion/).
Budget exhaustion, malformed/truncated provider responses and provider failures
return a generic localized 502. Missing
configuration returns 503. Authorization failures retain 401/403/404/409 semantics;
missing and inaccessible resources share 404. Responses use `Cache-Control: no-store`.

## Request admission and time budgets

Both live endpoints share process-wide admission in `api/assistant_limits.py`:

| Boundary | Limit |
| --- | --- |
| Authenticated user | 6 admitted requests per rolling 60 seconds; 1 active run |
| Authorized organization | 30 admitted requests per rolling 60 seconds; 2 active runs |
| API process | 4 active assistant runs, enforced by a nonblocking semaphore |

Rate exhaustion returns localized 429 with `Retry-After`. Busy capacity returns
localized 503 with `Retry-After: 1`. Admission never waits for a slot while holding
a FastAPI worker. User keys persist across sessions and both personas; organization
keys come from authorization, never directly from a caller header. Failed admitted
requests consume rate quota; every exit releases concurrency, including provider
errors and authorization revocation. Expired quota keys are removed. Demo responses
do not consume LLM admission because they make no provider request.

Assistant calls use zero SDK retries and a 30-second HTTP I/O timeout, with
5-second connect/pool timeouts. A 90-second elapsed run budget is checked before
provider/tool calls and after provider responses; each request timeout is reduced
to the remaining budget. Late answers and tool calls are rejected. HTTP timeouts
measure I/O inactivity, so this is not a hard cancellation deadline for an active
response that keeps sending bytes. The semaphore remains held until the call exits.

Limits are in memory within one API process, matching the supplied single-worker
Docker command. Restarts reset them; multiple workers or replicas multiply them.
Deployments using multiple processes must enforce shared user/organization quotas
and overall provider concurrency at a gateway or shared admission service. This
guard covers these two assistant endpoints, not other LLM workflows.

## Private context and demo behavior

Only the final text and demo flag are returned. Reasoning fields, raw tool calls,
tool results, provider metadata and exception payloads are not response fields or
logged by this layer. When a provider returns `reasoning_content`, it is replayed
only inside that run's model conversation, as required by reasoning-capable
[DeepSeek tool calls](https://api-docs.deepseek.com/guides/thinking_mode/).
User-authored document text is still untrusted content; the
permission checks prevent access expansion, not hallucinations or misleading prose.

With `DEMO_MODE=1`, both endpoints exercise the scoped dispatcher and return a
deterministic, explicitly labeled demonstration response without contacting an LLM.
This is not a claim about live model quality or global network isolation.

## Verification

`tests/test_assistant_permissions.py` exercises real bearer sessions with synthetic
model responses: unauthorized and invented tools, forged identities/history,
cross-client and cross-tenant reads, unpublished reports, injected document text,
mid-run logout/deactivation/reassignment, context isolation, error redaction,
localization, truncated tool-call rejection, DeepSeek SDK request serialization,
zero retries, run budgets, shared quotas, concurrent rejection and demo behavior.
`tests/test_assistant_limits.py` covers simultaneous admissions, quota expiry and
slot cleanup. Existing Client API and session tests cover the
shared projection and authentication helpers.
