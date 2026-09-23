# GolemOS Beta 0 — 8 GB Dell specification

Status: first development increment, 2026-09-22. Not an installed service or a
release. Development branch: `beta0-dell-8gb`.

## Verified foundation

The upstream is **https://github.com/use-agent-os/agent-os**, not another project
with the AgentOS name. Its Pilot Router, provider adapters and shared gateway
match the foundation described in the project discussion.

- Default branch: `main`.
- Fork baseline: `5271f3c61a65703df5bb982976add79f90dd34d4`.
- Latest published release: `v2026.9.22.post1` (GitHub releases API checked;
  published 2026-09-22 at 07:00:18 UTC, neither draft nor prerelease). Package
  version: `2026.9.22.post1`. The fork starts from inspected main, not the tag.
- License: Apache-2.0. Preserve `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`,
  embedded notices and the packaging license-file list. AgentOS credits
  OpenSquilla and other third parties; those credits remain intact.
- New GolemOS code is Apache-2.0. Any future edits to upstream files must carry
  a prominent downstream modification notice. Model weights retain their own
  licenses; Apache-2.0 does not relicense Gemma or bundled third-party assets.

Code inspection, rather than the earlier conversation's maturity estimates, is
the baseline for this fork. Upstream currently markets agentic trading; trading
integrations are outside GolemOS Beta 0 and must not be enabled by its profile.

## Existing architecture and the actual gap

Python 3.12+ and a React/Vite control UI sit over a Starlette gateway. The gateway
owns sessions, approvals and scheduling. Every client converges on `TurnRunner`
in `src/agentos/engine/runtime.py`. Pipeline steps resolve a model and apply
Pilot Router decisions before the shared agent loop dispatches tools.

Relevant source seams:

| Source | Existing responsibility |
| --- | --- |
| `agentos_router/pilot/` | Local MiniLM/ONNX classification into capability tiers |
| `agentos_router/llm_judge.py` | Optional LLM-based classification, not task completion |
| `engine/steps/agentos_router.py` | Apply routing, thinking and prompt policy |
| `provider/selector.py` | Build provider adapters and handle fallback chains |
| `provider/ollama.py` | Real local model inference through Ollama |
| `provider/openai.py`, `openai_responses.py`, `anthropic.py` | Cloud adapters |
| `session/`, `persistence/`, `memory/` | SQLite sessions, memory and retrieval |
| `safety/`, `sandbox/`, `tools/` | Permission checks and tool dispatch |

Local inference already exists. A local classifier selecting a cheap model is
not a resident executive: it cannot finish a task itself. Simply placing Gemma
in a cheap tier also does not give Gemma an explicit answer-or-escalate contract.

## Target design

```text
Windows local UI / CLI
  -> gateway: task identity, user preferences, permission policy
  -> resident local executive (Gemma candidate)
       -> complete simple text locally
       -> request cloud escalation -> permission + provider preference
            -> OpenAI / Anthropic / optional Gemini
  -> shared tool dispatcher -> permission checks -> files / Playwright
  -> SQLite: sessions, task state, preferences, audit events
```

Windows-first proof of concept on the existing 8 GB Dell. No Linux install,
partition changes, Docker requirement, startup service or network exposure in
this increment. Linux migration is eligible only after Beta 0 acceptance.

First resident candidate: **Gemma 3 4B Instruct Q4**, preferably a verified
Q4_K_M text-only artifact. Record model source, digest, quantization and terms
before download. Ollama is the first adapter; llama.cpp is a later alternative.
A model name alone does not prove quantization. Do not load a vision projector.
Benchmark before claiming Gemma fits or remains responsive on this Dell.

Start with one loaded model, one inference at a time, one browser context and
one active task. Target a 2,048-token runtime context and at most 512 output
tokens initially; measure actual peak working set, available physical memory,
page faults, first-token latency and end-to-end latency. Character limits in
the first code change are only an input bound, not a tokenizer-aware context
budget. Runtime context size and model keep-alive must be configured and tested
before gateway integration. If sustained paging or UI stalls occur, reduce
context or test a 1–2B fallback. Do not silently download or substitute models.
"Resident" means an available local executive service; permanent weight
residency on an 8 GB machine is a benchmark decision, not a guarantee.

## User-controlled provider preferences

The host, not model-generated text, selects provider credentials and endpoints.
Model IDs remain user-configurable and must be validated against the configured
provider; do not freeze speculative cloud model names into code.

| Task category | Initial preference |
| --- | --- |
| Simple text and private/offline tasks | Local Gemma candidate |
| Creative writing | OpenAI |
| GitHub/repository editing | OpenAI |
| Website building | Anthropic |
| Spreadsheets and office work | Anthropic |
| Other hard tasks | User-selected default; Gemini is optional |

Planned precedence: private/local-only constraint, explicit per-task model
selection, user category preference, then capability/cost policy. Overrides
require a recorded reason and must never relax privacy or permission policy.
No cloud provider is implicitly authorized by a timeout, refusal, invalid JSON,
missing local model or failed local operation. A local-only task stops and
requests input when it cannot finish. Cloud authorization must cover the exact
task content and selected destination; a configured API key is not consent.

## Permission tiers and audit requirements

All models propose actions; deterministic host policy grants capabilities.

| Tier | Policy |
| --- | --- |
| Read | Read within an explicitly granted workspace; no arbitrary filesystem access |
| Reversible work | Scoped edits/tests in a task workspace, then report changes |
| Approval required | External messages, publishing/deployment, destructive operations, purchases, credential/security changes |
| Denied | Actions outside granted scope or prohibited by host policy |

Beta 0 begins with text only, then allowlisted read tools. No shell or write
tools until Windows path/symlink containment and approval tests pass. Upstream
does **not** provide the Linux/macOS OS-level sandbox on Windows. Application
checks must not be described as equivalent OS isolation. Do not weaken upstream
guards or run the executive as administrator to get around that limitation.

Reuse SQLite for durable sessions, tasks, routing preferences and a structured
audit log. Required events: task accepted, local completion, escalation request,
egress authorization/denial, selected provider/model, tool proposal, approval,
execution result, failure/cancellation and completion. Store correlation IDs,
timestamps, policy version and redacted metadata; avoid prompts, secrets and
full tool outputs by default. Apply retention/export rules. Local SQLite is
not a tamper-proof security ledger. This increment returns structured results;
durable executive audit integration is still pending.

## Browser, remote access and migration

Add Playwright through the existing tool registry/MCP boundary after the text
loop is proven. Start with an isolated browser profile, one context, explicit
navigation/read actions and bounded snapshots. Form submissions and external
writes pass through the same approval policy. Do not import signed-in personal
browser profiles by default. Website text is untrusted data, never permission.

Phone/remote access comes later: authenticated access over a private network or
secure tunnel, with session authorization and approval UX. Beta 0 initially
binds only to loopback; no public listener or port forwarding. Linux migration
comes after the Windows acceptance tests, followed by optional desktop shell
work. No OS replacement is part of this change.

## First small code change

`agentos_router/resident.py` adds an opt-in `ResidentExecutive` that reuses
AgentOS's `LLMProvider`, `Message`, `ChatConfig` and stream events. It calls a
trusted local adapter once, asks for a strict JSON answer or escalation, and
returns a finished local answer without invoking cloud. On explicit escalation,
it either returns `needs_cloud` or calls the caller's selected cloud adapter
once when `allow_cloud=True`. It sends only the original task, not the local
model's proposed instructions. Tools are never supplied or executed.

It rejects malformed output, incomplete streams, tool events, empty answers
and oversized output; local failures never auto-escalate. Cancellation is
propagated, inference has a deadline, and one instance serializes requests.
Permission defaults to false on every call. The trusted host must inject a
genuinely local adapter: the protocol itself does not enforce network locality.

This is a callable text proof of concept, **not yet wired into the gateway,
CLI, Pilot strategy registry or automatic startup**. That keeps the first
change independently testable without altering existing user routing or tool
permissions. Native Gemma tool-calling capability is not assumed.

After configuring and verifying a local Gemma artifact, an embedding host can
reuse the object as follows (no inference has been run by this development task):

```python
from agentos.agentos_router.resident import ResidentExecutive
from agentos.provider.ollama import OllamaProvider

# This local model alias must first be created/verified by the operator.
executive = ResidentExecutive(
    OllamaProvider(model="golemos-gemma3-4b-q4", base_url="http://127.0.0.1:11434")
)
result = await executive.run("Summarize: The meeting moved from Monday to Tuesday.")
```

Supply a configured OpenAI/Anthropic/Gemini adapter as `cloud` to exercise the
authorized escalation path. Provider selection and preferences are host inputs
in this increment; persistence/UI for editing preferences remains to build.

## Next acceptance gates

1. Verify Dell hardware and measure Gemma Q4 with short text tasks. Record JSON
   conformance, answer quality, escalation accuracy, latency and RAM headroom.
2. Connect this boundary to TurnRunner with opt-in configuration, explicit
   model overrides, SQLite audit events, restart-safe task state and egress
   approvals. Confirm local answers survive session replay without cloud calls.
3. Add read-only tools behind existing permission gates, then scoped reversible
   edits and Playwright. Prove approval denial prevents side effects.
4. Complete a bounded task in a disposable sample repository, test in browser,
   and stop for deployment approval. Do not test against existing user repos.
5. Consider phone access, then Linux, only after those gates pass.

Offline tests use fake providers and must never require credentials, downloads,
paid inference, or a running local model. Live Gemma and cloud integration tests
are separate opt-in benchmarks, not established by mock tests.
