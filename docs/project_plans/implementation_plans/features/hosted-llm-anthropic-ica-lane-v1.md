---
it_schema: 1
feature_slug: hosted-llm-anthropic-ica-lane
title: "Anthropic/ICA lane + egress consent gating — implementation plan"
doc_type: implementation_plan
status: completed
tier: 2
priority: P1
points: 11
risk_level: high
context_class: C3
created: 2026-08-10
updated: 2026-08-10
prd_ref: null   # No PRD: the SPIKE findings doc below is the requirement record (913 lines,
                # status completed, with the config-surface table and exit criteria). A PRD would
                # restate it verbatim, which the doctrine forbids.
spike_ref: docs/project_plans/spikes/hosted-llm-provider-strategy.md
itt_node_id: node_01KZEXTPYXYB4TKGFE111ZRXPE
intenttree_tree: tree_01KVTH95F7P7CXK3QH9ZMECM5T
related_documents:
  - docs/project_plans/spikes/hosted-llm-provider-strategy-open-questions.md
  - docs/guides/redaction-tuning.md
  - docs/project_plans/adrs/adr-006-db-authoritative-project-registry.md
changelog_required: true
findings_doc_ref: null
deferred_items_spec_refs: []
acceptance_criteria:
  - "With CCDASH_LLM_EGRESS_CONSENT false, no egress adapter is constructed and the naming sweep no-ops with a log line."
  - "With global consent true and exactly one project's llm_egress_consent true, only that project's sessions egress."
  - "Every outbound prompt on an egress lane carries AGGREGATE or TRANSCRIPT_REDACTED provenance; a wrong-provenance envelope is rejected."
  - "projects.llm_egress_consent exists in BOTH sqlite and postgres DDL in one change set, with zero COLUMN_PARITY_DRIFT_ALLOWLIST entries."
  - "The anthropic adapter reaches ICA and Anthropic direct by base URL alone, sending bare model ids and anthropic-version: 2023-06-01."
  - "No provider credential appears in a URL query string, and no provider error body is logged."
open_questions:
  - "PARTIALLY ANSWERED 2026-08-11: the default ~/.dotfiles/ICA_CLAUDE key is confirmed working end-to-end through the shipped adapter for bare claude-haiku-4-5 (HTTP 200, msg_bdrk_ id). STILL OPEN: whether a named ICA_KEY block scopes models differently — that remains unprobed, so a deployment pinned to a named key is still an unverified configuration."
  - "Whether CCDASH_LLM_ANTHROPIC_MODEL should have a default at all. The SPIKE deliberately gives it none; a wrong default is a silent cost decision."
decisions:
  - decision: "Gate before lane: consent machinery lands and is proven against the EXISTING gemini egress lane in M2, before the anthropic adapter exists in M3."
    rationale: "The node's exit criteria are all provable against any egress lane. Landing the gate first means the safety property ships even if the new provider slips, and the new adapter is born into an already-gated world rather than being the thing that proves the gate."
    status: accepted
  - decision: "Fold the two still-open P2 defects (creds-in-URL + error-body logging; undeclared httpx) into M1 rather than treating them as external blockers."
    rationale: "Both sit on the exact files M3 extends. Adding a second credentialed egress adapter to a codebase that puts keys in query strings copies the defect into the new lane; fixing it first is the cheapest ordering. Nodes node_01KZEXSPEKDRCSY3FGEVZPEWMV and node_01KZEXSFSH4AGBFYGY5D5YTG9F are discharged by M1."
    status: accepted
  - decision: "No PRD; spike_ref carries the requirement record."
    rationale: "The SPIKE is complete and specifies the config surface, exit criteria, and three proposed ADRs. A PRD would duplicate 913 lines of settled spec."
    status: accepted
routing_constraints:
  - "Egress-boundary correctness (consent resolution, provenance enforcement, redaction seam) MUST stay claude-primary — never offloaded."
  - "The dual sqlite+postgres DDL change set MUST stay claude-primary: a half-applied migration crash-loops the node."
  - "Adapter transport plumbing and test scaffolding are offload-eligible."
  - "Capability bar: any leg touching the consent resolver or the DDL needs a model that can hold both migration files at once; adapter/test legs do not."
required_artifacts:
  - name: dev-execution
    type: skill
    status: available
  - name: artifact-tracking
    type: skill
    status: available
wave_plan:
  waves: [["M1"], ["M2"], ["M3"]]
  phases:
    - id: M1
      title: "The egress path is safe to extend"
      depends_on: []
      exit_criteria:
        - "httpx is declared in backend/requirements.txt"
        - "No provider credential is passed in a URL query string; no provider error body reaches a log"
      gate_lens: [security]
      gate_lens_reason: authz-boundary
    - id: M2
      title: "Consent gates egress, with no new provider added"
      depends_on: ["M1"]
      exit_criteria:
        - "Consent false => no egress adapter constructs, sweep no-ops with a log line"
        - "Per-project consent narrows egress to consented projects only, proven against the existing gemini lane"
        - "Dual-backend DDL parity holds with zero allowlist entries"
      gate_lens: [security, validator]
      gate_lens_reason: irreversible-outward
    - id: M3
      title: "The Anthropic/ICA lane serves a session name"
      depends_on: ["M2"]
      exit_criteria:
        - "The anthropic adapter completes a real prompt against ICA with bare model ids"
        - "CCDASH_LLM_* surface resolves, with documented fallbacks to the legacy vars"
      gate_lens: [security]
      gate_lens_reason: irreversible-outward
source_artifact_id: srcart_01KZP8ZDFQ4XWVPBH5N1PRQC4D
---

# Implementation Plan — Anthropic/ICA lane + egress consent gating

CCDash today has a `TextCompletionPort` seam (shipped in P1, `70f6e36`) with `ollama` and `gemini`
adapters, and a `PromptProvenance` vocabulary whose fail-closed factory already refuses to build a
transcript envelope when redaction is off. What it does not have is any way for an operator to say
"yes, this project's sessions may leave the box" — or a second hosted provider worth asking about.
When this is done, egress is a consented act per project, and the Anthropic wire format reaches
either ICA or Anthropic direct by base URL alone.

## Scope boundary

**In:** `backend/adapters/llm/`, `backend/application/ports/llm.py`, `backend/config.py`,
`backend/services/session_naming_*`, `backend/adapters/jobs/session_naming_sweep_job.py`,
`projects` DDL in both migration modules, `backend/observability/otel.py`.

**Out (stated, not silently dropped):** the 20k historical backfill (SPIKE P4 does not authorize it;
needs its own `--limit` CLI with cost confirmation); the empirical larger-model test
(`node_01KZEXTW9NZ3MQT5EFRJSJFHK8`, runs after this); embeddings (CCDash never computes a vector,
RQ-1 settled); ADR-016 (belongs to the shipped P1 seam — M3 discharges only ADR-017/018); setting
`CCDASH_API_TOKEN` on the node (`node_01KZP34GGMAQG584QTV7R88NV2` — deployment act, not code).

## Rubric — what "good" looks like

Consent must be **structurally** unable to fail open. The house pattern already exists and should be
copied rather than invented: `resolve_naming_backend` returns `None` — a deliberate no-op, never a
silent fallback to another lane — when hosted naming is requested but redaction is off. A reviewer
should read the resolver and see that false consent cannot produce a constructed egress adapter,
without tracing call sites to be sure.

Two asymmetries to respect. The per-project check must be evaluated **per sweep tick**, not captured
at construction: the sweep re-reads the whole registry each tick, so consent revoked at 14:00 must
bite at 14:30 without a restart. And **ICA is not a validation lane** — it returns 200 on unknown
top-level fields where Anthropic direct returns 400, so a green ICA call proves reachability, not
request correctness.

## Named risks

- **A silent fail-open is the whole risk of this plan.** Every other failure is visible. Prefer a
  structural no-op over a conditional at the call site, and assert the negative case in a test that
  fails if an egress adapter is ever constructed under false consent.
- **Half-applied migration crash-loops the node.** Two migration modules must move in one change set;
  the node runs api+worker migrations concurrently and a drifted column has crashed both before.
  Schema-qualify, mirror exactly, and expect zero allowlist entries.
- **`[1m]` model ids 403 against the raw gateway.** The suffix is a Claude-Code-layer convention, not
  an endpoint one. The adapter sends bare ids; a test should pin that.
- **The config fallback pattern does not exist yet in this repo.** `config.py` reads every var once,
  standalone — there is no `os.getenv(new) or os.getenv(old)` precedent. Write one helper and use it
  for all fallbacks rather than open-coding the chain per var.

## References

- Seam + provenance: `backend/application/ports/llm.py:32-121` (`PromptProvenance`,
  `envelope_from_redacted_transcript` fail-closed at `:105-118`)
- Adapters: `backend/adapters/llm/gemini.py:49` (credential in query string — M1 fixes this),
  `backend/adapters/llm/ollama.py:19-43`
- Lane selector / no-op precedent: `backend/services/session_naming_local_backend.py:309-395`
- Sweep fan-out (consent check belongs inside this loop):
  `backend/adapters/jobs/session_naming_sweep_job.py:185,197-241`
- Dual-DDL exemplar (v51 `ica_key`): `backend/db/sqlite_migrations.py:276-280,3194-3196` +
  `backend/db/postgres_migrations.py:4159-4163`; `SCHEMA_VERSION` at `sqlite_migrations.py:85` /
  `postgres_migrations.py:61`; parity allowlist `backend/db/migration_governance.py:462`
- Per-project boolean read path to copy: `is_active` in `backend/db/repositories/projects.py:185`,
  `backend/models.py:1874`
- Observability pattern: `backend/observability/otel.py:340-377` + call site
  `backend/services/integrations/telemetry_exporter.py:433-450`
- Config surface table + Empirical Addendum: `spike_ref` §Config surface, §Empirical Addendum

## Milestones

### M1 — The egress path is safe to extend

`httpx` is a declared dependency. No provider credential travels in a URL query string, and no
provider error body reaches a log. This discharges the two open P2 defect nodes; it is deliberately
first, because M3 adds a second credentialed adapter that would otherwise inherit the pattern.

**AC:** `httpx` in `backend/requirements.txt`; gemini adapter sends its key as a header; a test
asserts no provider error body is logged; existing naming/insight tests pass unmodified.

### M2 — Consent gates egress, with no new provider added

Egress is a consented act. `CCDASH_LLM_EGRESS_CONSENT` is the global switch and
`projects.llm_egress_consent` the per-project one; the resolver returns `None` under false consent,
and the sweep skips non-consenting projects each tick. All of it is proven against the **existing**
gemini lane — no new provider yet. **Touches a schema migration: Mode-D, halts for human approval.**

**AC:** consent false => no egress adapter constructs and the sweep logs a no-op line (asserted by a
no-construction test in the style of `test_aar_review_no_llm_imports.py`); global true + one project
consented => only that project's sessions egress; column present in both backends' `CREATE TABLE`
and `_ensure_column` paths with `SCHEMA_VERSION` bumped to 53 (planned as 52; renumbered on merge
because a concurrently-landed feature had already taken 52 — see the close-out ledger) and zero
allowlist entries; a
wrong-provenance envelope is rejected by any `egress=True` adapter; per-tick egress log line carries
lane, model id served, and project id.

### M3 — The Anthropic/ICA lane serves a session name

An `anthropic` adapter reaches ICA or Anthropic direct by base URL alone, and the `CCDASH_LLM_*`
surface selects it with documented fallbacks to the legacy `CCDASH_SESSION_NAMING_BACKEND` /
`CCDASH_GEMINI_API_KEY` vars. ADR-017 and ADR-018 move from `proposed` to `accepted`.

**AC:** adapter POSTs `{base}/v1/messages` with `anthropic-version: 2023-06-01` and a **bare** model
id (test pins that a `[1m]`-suffixed id is never sent); `CCDASH_LLM_SESSION_NAMING_LANE` resolves and
falls back to the legacy var; absent key or unreachable provider degrades per the established
`{disabled:true}` / `None` contract rather than failing the surface; CHANGELOG `[Unreleased]` entry;
ADR-017 + ADR-018 accepted.

> **Two claims here, and only one of them is done. Do not conflate them.**
>
> 1. **"The adapter completes a real prompt against ICA with bare model ids" — DONE, verified live
>    2026-08-11.** See the evidence table below (`HTTP 200`, `msg_bdrk_01Cy81qtPXAFRRMC9NjnrdpY`,
>    bare `claude-haiku-4-5` echoed; `[1m]` → `403` reproduced 3×). This is the frontmatter AC, and
>    it is closed.
> 2. **"A real ICA call NAMES ONE SESSION end-to-end" — still NOT done, and deliberately not an
>    acceptance criterion.** It appeared in this plan's original draft but is absent from the
>    frontmatter `acceptance_criteria` (the machine-readable contract). The live verification above
>    exercised the adapter directly with a SYNTHETIC AGGREGATE-provenance prompt, precisely so that
>    no session content egressed and no session name was mutated. Running the full worker sweep is
>    now *feasible* — the per-project consent write path landed in `13f8c23` — but it is a separate,
>    data-mutating act that nobody has asked for.

## AC -> command -> evidence

| AC | Command | Evidence of pass |
|---|---|---|
| M1 — no creds in URL, no error bodies logged | `backend/.venv/bin/python -m pytest backend/tests/test_ai_insight_router.py backend/tests/test_session_naming_hosted_backend.py -v` | Green; grep of `backend/adapters/llm/` shows no `?key=` construction |
| M2 — consent false constructs nothing | `backend/.venv/bin/python -m pytest backend/tests/test_session_naming_sweep_guards.py -v` | Negative-construction test green; sweep emits the no-op log line |
| M2 — per-project narrowing | `backend/.venv/bin/python -m pytest backend/tests/test_session_naming_sweep_job.py -v` | Two-project fixture: consented project egresses, other is skipped |
| M2 — dual DDL parity | `backend/.venv/bin/python -m pytest backend/tests/test_migration_governance.py -v` | Column in both backends; zero `COLUMN_PARITY_DRIFT_ALLOWLIST` entries |
| M2 — postgres migration actually applies | `npm run docker:hosted:smoke:seeded-pg` | Re-run 2026-08-10 AFTER the renumber to v53 (see the close-out ledger entry): seeded at v29, `Migration result: applied (reached SCHEMA_VERSION=53)`, `/api/health/ready` returned `migrationStatus=="applied"`, `UndefinedColumnError` ABSENT from both the postgres and api container logs, script exit 0. This is the run that matters — it exercises the in-place upgrade with BOTH this feature's `projects.llm_egress_consent` and the concurrently-landed provider/channel/credential tables present |
| M3 — provenance enforced on egress | `backend/.venv/bin/python -m pytest backend/tests/test_session_naming_read_path_no_model_client.py -v` | Guard green; wrong-provenance envelope raises |
| M3 — bare model ids, base-URL-only routing, version header | `backend/.venv/bin/python -m pytest backend/tests/test_anthropic_adapter.py -v` | Green. Pins the URL, the ICA default base, `anthropic-version: 2023-06-01`, credential-as-header (asserts no `key=` in the URL), the frozen payload key-set, and `[1m]`-id rejection before the wire |
| M3 — live reachability against ICA | Direct invocation of `AnthropicTextCompletionAdapter` against the ICA gateway with the default `~/.dotfiles/ICA_CLAUDE` key, plus a raw `POST {base}/v1/messages` on the same key to capture the response envelope | **OBTAINED 2026-08-11** (operator-authorized). Adapter returned `'ok'`. Raw probe: `HTTP 200`, id `msg_bdrk_01Cy81qtPXAFRRMC9NjnrdpY`, model echoed back as bare `claude-haiku-4-5`, `stop_reason end_turn`, 14 in / 4 out. Negative side 3/3: `claude-haiku-4-5[1m]` → `HTTP 403 team_model_access_denied`, each paired with a bare-id control at 200 (excludes a gateway outage). Adapter also raises `ValueError` on a `[1m]` id pre-network. Prompt was SYNTHETIC with AGGREGATE provenance — **zero session content egressed**. NOTE: the first suffixed-id attempt returned a transient `502`; re-probing 3× showed a stable `403`, so the SPIKE's recorded finding holds |

## Sequencing (load-bearing)

M1 -> M2 -> M3, and the reason is not house style. **M1 before M3** because M3 adds a second
credentialed adapter that would copy M1's defect if it landed first. **M2 before M3** because the
consent gate is the safety property; landing it against the existing gemini lane means the new
provider is born gated, and a slip in M3 does not also lose the gate. The M2 migration is a
serialization barrier — nothing in M3 may merge while the DDL is half-applied.

## Execution ledger

Deviations and conservative choices are logged with rationale to
`.claude/worknotes/hosted-llm-anthropic-ica-lane/implementation-notes.md` and reviewed at each
milestone boundary — rather than halting on them.

**Blockers still stop** (failing test on current work, unsatisfiable declared artifact, exhausted
recovery). Beyond those, mid-milestone halts are only for: destructive action, real scope change, or
input only the operator has.

**Mode-D boundaries are unchanged and non-negotiable** — **auth · payments/billing · schema
migrations · data deletion · secret rotation · infrastructure**. M2 contains a schema migration and
halts for explicit human approval before it applies.
