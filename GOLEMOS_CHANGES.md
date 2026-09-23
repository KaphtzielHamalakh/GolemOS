# GolemOS downstream changes

Copyright 2026 GolemOS contributors. New code is licensed under Apache-2.0.

Based on https://github.com/use-agent-os/agent-os at
`5271f3c61a65703df5bb982976add79f90dd34d4` (main, 2026-09-22).

The first increment adds `src/agentos/agentos_router/resident.py`, its offline
tests, and `docs/GOLEMOS_BETA0.md`. Existing upstream source and all upstream
licensing/attribution files are preserved unchanged. The resident module is
opt-in, text-only and not yet connected to the gateway.

See the specification for the intended system and the explicitly deferred work.
No deployment, model download, service installation or OS migration is included.

## Validation of this increment

Validated on Windows with the locked dependencies and Python 3.12.14:

- Executive regression tests: **24 passed**, including the real Ollama adapter
  with a mocked HTTP transport. No live inference or credentials were used.
- Production Control UI build, asset budgets and license generation: passed.
- Frontend checks (TypeScript, ESLint, Prettier, Vitest): passed; **2,081 tests**
  across 99 files. The initial sandboxed Vitest launch failed on parent-directory
  access; the complete rerun with the necessary filesystem access passed.
- `ruff check src tests`: passed.
- `mypy src/agentos --show-error-codes`: passed, **630 source files**.
- Wheel build: passed. Verified the new module is included and the packaged
  LICENSE, NOTICE and THIRD_PARTY_NOTICES.md match the source byte for byte.

The broader Python run used `--maxfail=10` and excluded live/costly/browser/slow
markers. It stopped at **3,192 passed, 10 failed, 15 skipped, 21 deselected**;
the full Python suite is **not green and did not run to completion**.
All ten exact failures reproduce against an independently extracted, unchanged
upstream baseline at the pinned commit (baseline source import path verified):

- Two Pilot encoder tests: Git LFS model pointers, rather than the ONNX payload,
  are present. LFS assets were intentionally not downloaded for this text-only
  prototype. A successful wheel build does not make this checkout a usable
  packaged model distribution.
- Five CI changed-file tests: `sed` is absent from the shell environment used by
  those tests.
- Three existing router guard tests: cost-aware routing picks `c2` while the
  tests expect `c1`; reproduced with the baseline and unavailable live pricing.

These baseline/environment failures block claiming a clean upstream release
gate. They are not fixed in this deliberately small development increment.
The locked npm installation also reports 10 existing dependency advisories
(5 moderate, 5 high); dependency upgrades are outside this patch.

Remaining product work: benchmark a verified Gemma Q4 artifact on the Dell;
connect the executive to TurnRunner and its audit/session lifecycle; implement
persisted routing preferences and permission UI; add scoped tools and
Playwright; then consider remote access and Linux migration. This callable
prototype is not a deployed or always-running GolemOS environment.
