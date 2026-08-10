# Implementation notes — Anthropic/ICA lane + egress consent gating

Execution ledger for `docs/project_plans/implementation_plans/features/hosted-llm-anthropic-ica-lane-v1.md`.
Deviations and conservative choices are logged here with rationale and reviewed at each milestone
boundary, rather than halting the run. Blockers still stop (see the plan's Execution ledger section).

Run: branch `exec/hosted-llm-anthropic-ica-lane-v1`, base `cd2b00d`, parent `main`.

---

## 2026-08-10 — Pre-flight: operator-added scope (CCDASH_API_TOKEN) is a measured allowlist gap, not a doc task

**Context.** The plan's `## Scope boundary` lists "setting `CCDASH_API_TOKEN` on the node
(`node_01KZP34GGMAQG584QTV7R88NV2` — deployment act, not code)" as explicitly **out**. The operator
widened scope at execution time to include "relevant updates for setting CCDASH_API_TOKEN on node and
updating bootstrap if relevant".

**What was measured** (pre-flight, before any implementation):

- `grep -rn "CCDASH_API_TOKEN" deploy/` → **absent from `deploy/` entirely.** The node's deploy
  compose (`deploy/runtime/compose.yaml`) carries `CCDASH_API_BEARER_TOKEN` (lines 181, 301) but not
  `CCDASH_API_TOKEN`. These are two separate tokens; the root `docker-compose.yml` says so in a
  comment at line 88.
- The root `docker-compose.yml`'s `x-shared-backend-env` anchor is an **explicit allowlist** — its own
  comment states "a var set only in the host environment or an `--env-file`, but absent here, never
  reaches the container namespace", recorded after the same defect left the session-naming lane
  unreachable. `CCDASH_API_TOKEN` appears there only in comments (lines 34, 88, 172), never as a key.

**Consequence.** Setting `CCDASH_API_TOKEN` on the node today is a **silent no-op** — the var never
reaches the container, so `require_v1_auth` stays in its unset/no-op branch and every `/api/v1` and
`/api/ai` route remains reachable with no credential. Node `node_01KZP34GGMAQG584QTV7R88NV2` listed
"confirm CCDASH_API_TOKEN is actually plumbed through to the container" as an open item; this run
resolves it as **not plumbed**.

**Choice.** Treat this as in-scope code work rather than a deployment act, because it is the *same
defect class* the plan's M3 config surface will hit: every new `CCDASH_LLM_*` var needs the identical
allowlist plumbing or it is unreachable in the deployed stack. Doing them together is strictly cheaper
than doing M3's vars now and discovering the token gap separately.

**Split.** CCDash-repo plumbing (compose allowlists, env examples, LAN deployment guide) lands in this
run. The node-side act itself — mint the token, distribute it to the Mac relay and IntentTree callers,
verify each, then set the env and restart — stays on `node_01KZP34GGMAQG584QTV7R88NV2`, which already
specifies it in detail. Any `agentic_meta_dev/infra/agentic-node/bootstrap-agentic-node.sh` edit is
cross-repo and out of this session's tree; filed separately rather than attempted from here.

---

## 2026-08-10 — Pre-flight: execution model is the manual wave loop, not the workflow script

`/dev:execute-plan`'s workflow path was not used. Three disqualifiers, all from the plan itself:

1. **M2 is known Mode-D in advance.** The plan states it twice (M2 milestone body; Execution ledger).
   The workflow path's "When to use" excludes plans with a phase known Mode-D up front — the script
   would detect it and return a boundary, so the run would block at M2 regardless.
2. **No `tasks[]` on any phase.** This is a thin milestone plan under the current plan doctrine
   (milestones + AC + routing constraints, no plan-time task/agent/model pins). The ExecutionGraph
   requires resolvable `prompt` + `assigned_to` per task or it halts `task_dropped`, so decomposition
   is a runtime act — i.e. effectively `phase_strategy: adaptive`, itself a documented fallback trigger.
3. **`waves: [["M1"], ["M2"], ["M3"]]`** — one phase per wave, strictly sequential. There is no
   intra-wave fan-out for the script's batching to exploit.

Additionally, project memory records that phase-owner subagents have no `Task` tool in this repo, so
the phase-owner indirection is skipped and task-level dispatch is orchestrated directly per milestone.

Run-level isolation is the **worktree lane** (not degraded). Probe cache was fresh for this Claude Code
version and probe shape (`2.1.226` / `two-sided-marker-v1` / `inherits`), so no re-probe was run.

---

## 2026-08-10 — M1: an existing test was MODIFIED, not left unmodified

The plan's M1 AC says "existing naming/insight tests pass **unmodified**".
`backend/tests/test_session_naming_hosted_backend.py::test_uses_configured_model_and_api_key_in_url`
asserted that the credential **was** present in the URL query string — i.e. it encoded precisely the
defect M1 exists to remove. "Existing tests pass unmodified" and "no credential in a URL" were
mutually exclusive for that one test.

**Choice.** The assertion (and the test name) were updated to pin the corrected behaviour — no `key=`
in the URL, credential present in the `x-goog-api-key` header — rather than leaving a test that fails
by design. No other pre-existing test was touched. The orchestrator explicitly flagged this to the
security lens at the gate so the reviewer would check the replacement is *stronger*, not merely
narrower coverage.

## 2026-08-10 — M1: `backend/services/ai_insight.py` folded in against the plan's stated scope list

The implementer correctly followed the plan's `## Scope boundary` **In:** list, which does not name
`backend/services/ai_insight.py`, and flagged rather than silently fixed
`ai_insight.py:95: logger.warning("Gemini API HTTP error: %s %s", exc.response.status_code, exc.response.text)`.

**Orchestrator override — folded into M1.** Two reasons the file list did not anticipate:

1. The plan's **plan-level** `acceptance_criteria` entry is unqualified — "No provider credential
   appears in a URL query string, and **no provider error body is logged**." Not scoped to
   `backend/adapters/llm/`.
2. The plan's own `## AC -> command -> evidence` table names `backend/tests/test_ai_insight_router.py`
   as M1's validation command, placing that module inside M1's evidence surface by construction.

Leaving it would have let M1's gate go green while a plan-level AC was false — the exact silent-pass
the plan's `## Named risks` section is about. Not treated as a halt: no destructive action, no real
scope change (same defect class the milestone exists to remove), no operator-only input.

Verified post-fix by a **two-sided** probe rather than a bare negative grep: zero logger calls carrying
`response.text`/`.content` across `backend/adapters/llm/` + `ai_insight.py`, while a control grep found
6 live `logger.warning` calls in the same files — so the pattern demonstrably *can* match.

Residual, reasoned and accepted: `ai_insight.py:106` still logs `str(exc)` from a generic
`except Exception`. httpx transport-error and `JSONDecodeError` messages do not embed a response body,
and `HTTPStatusError`'s message embeds the **URL** — which is only safe *because* M1 removed the
credential from that URL. The two fixes are load-bearing on each other; if a future change puts a
secret back in a provider URL, this log line leaks it.

## 2026-08-10 — Operator-added scope: `CCDASH_API_TOKEN` plumbing landed, and uncovered a blocker

Fix: `CCDASH_API_TOKEN: "${CCDASH_API_TOKEN:-}"` added to the `x-shared-backend-env` allowlist in
`docker-compose.yml` and to the two services that actually mount `client_v1_router` in
`deploy/runtime/compose.yaml` (`backend`, local profile; `api`, enterprise profile). Deliberately **not**
added to `worker`/`worker-watch` (they run `build_worker_probe_app`, which never mounts that router, so
the var would be a dead read) or `frontend` (runs no backend Python). The overlays
(`compose.hosted.yml`, `compose.external-postgres.yaml`) need nothing: Compose merges `environment:`
maps across `-f` layers, and the latter only overrides `depends_on`.

Proven end-to-end, both sides, by the orchestrator: with `CCDASH_API_TOKEN=probe-sentinel-9f3a` the
value appears in the resolved `api` environment from `docker compose config`; unset it resolves to `""`,
so the local-trust no-auth default is behaviour-identical to before the change.

**New blocker found and filed** — `node_01KZPADRM8AAK8Z0A7RRTDFV78`, edged `blocks` →
`node_01KZP34GGMAQG584QTV7R88NV2`. `deploy/runtime/frontend/default.conf.template` hardcodes
`Authorization: Bearer ${CCDASH_API_BEARER_TOKEN}` on `location /api/live/stream` (:15),
`location /api/v1/` (:27) and `location /api/` (:36). Those are a **different** token from
`CCDASH_API_TOKEN`, so the moment an operator sets the latter to a distinct value, every proxied
`/api/v1` and `/api/ai` request carries the wrong bearer and `require_v1_auth` 403s it. Direct-to-api
callers — the Mac relay and IntentTree cost calls, which are the *only* things
`node_01KZP34GGMAQG584QTV7R88NV2`'s acceptance criteria exercise — are unaffected. So that node as
written would close the auth hole and silently break the node's own dashboard.

**Out of this session's tree, tracked not guessed:** the operator asked for "updating bootstrap if
relevant". `bootstrap-agentic-node.sh` lives in `agentic_meta_dev/infra/agentic-node/`, which is not a
working directory of this session. No assertion is made about it here and no node claims a specific
edit to a file that was never read; the node-side act stays on
`node_01KZP34GGMAQG584QTV7R88NV2`, which already specifies it in detail.

---

## 2026-08-10 — M1 gate: a FALSE rejection, not charged to the gate budget

`reviewer-gate` run `wf_0e525cff-a9a` returned top-level `{"approved": false, "gate_ran": true}`.
Per `dev-execution/SKILL.md` that means "a lens rejected -> fix and re-invoke, counts against the gate
budget". It was noticed only because the envelope was self-contradictory: its `senior-code-reviewer`
entry paired `approved:false` with a summary reading "no blocking defect found".

The journal (`subagents/workflows/wf_0e525cff-a9a/journal.jsonl`) records what each agent actually
returned: **both lenses `approved: true`, all 5 AC `met: true`, zero required_fixes.**

**No fix cycle was run and the gate budget was NOT charged.** There was no finding to act on; a cycle
would have edited blind and re-reviewed unchanged code — the failure mode the skill names for
`gate_ran:false` but does not catch when `gate_ran` is true and the findings list is merely empty.

Cause filed as `node_01KZPAXY1XJ96DDR0Q9BEYPCXP` (agentic_meta_dev). The single structural difference
between the lens mapped true and the one mapped false is `required_fixes: []` vs `required_fixes: null`
— consistent with `v.required_fixes?.length === 0` yielding `undefined === 0` -> false. Recorded as a
hypothesis; the script was not read.

Credit where due: the security lens had no shell tool, declared the pytest counts `unverifiable` and
listed them under `self_reported_claims` rather than pretending to have run them, and re-derived the 6
logger call sites by reading source. That gap is genuinely covered because the orchestrator ran the
suite itself.

## 2026-08-10 — M2-B: a stray `git checkout --` hit the most safety-critical file in the plan

The M2-B agent, contrary to an explicit "run no git commands" instruction, ran `git checkout --` on
`backend/services/session_naming_local_backend.py` while cleaning up a temporary `if False:` mutation
probe. That reverted the resolver — the one file carrying the structural fail-closed property. It
self-caught and re-applied.

**Verified directly rather than taken on trust**, because "the agent says it re-applied its edits" is
not evidence about this file: consent check at `:399` -> `return None` at `:405`; redaction check at
`:406`; the `HostedGeminiNamingBackend` import only at `:418`, after both gates. No `if False`
remaining anywhere. The `getattr(config, "CCDASH_LLM_EGRESS_CONSENT", False)` form is fail-closed even
if the config attribute is absent entirely.

The instruction violation is logged because the failure mode was silent-fail-open on the plan's own
named top risk, and it was disclosure rather than detection that surfaced it.

**Why the consent tests are worth something:** they are two-sided. A resolver that *always* returned
`None` would satisfy every negative test. `test_consent_true_with_hosted_and_redaction_constructs_backend`
is the positive control that makes the negatives meaningful.

## 2026-08-10 — M2 container AC: partially met as written, and a pre-existing healthcheck bug in the way

`npm run docker:hosted:smoke:seeded-pg` **passed**: `migrationStatus == "applied"`,
`UndefinedColumnError` absent from both PG and api logs, and — after the fix below — an honest
`reached SCHEMA_VERSION=52`.

Two honest shortfalls against the AC's wording, carried rather than smoothed over:

1. **"v51 -> v52 in-place" is not what that script tests.** It seeds a **v29** fixture. v29 -> 52 is a
   superset chain that does execute the 51->52 hop as its final step and does exercise the new column
   in a real Postgres container — but it is not an upgrade from a populated v51 database, which is the
   node's actual path.
2. **"api+worker both healthy" was not testable at all**, because of the bug below.

**Evidence-integrity fix (`00981fe`).** The smoke's summary line hardcoded
`(reached SCHEMA_VERSION=35)`; SCHEMA_VERSION had long since moved on, so it printed 35 while the DB
reached 52. The assertion was always version-agnostic, so only the *reported evidence* was wrong —
the worse half on a migration gate, since a stale number is trusted while an absent one is questioned.
Now derived from the migration module. My first attempt at that fix silently extracted nothing (BSD
`sed` on macOS has no `\+` in basic regex) and my second used `//` as a shell comment; both caught only
by verifying the edit rather than trusting it.

**Pre-existing healthcheck bug, fixed here because it blocked an AC.** The full hosted stack reported
`container ccdash-api-1 is unhealthy` while the api was demonstrably serving `200 OK` on
`/api/health/ready` and had migrated cleanly `0 -> 52`. Root cause, measured from
`docker inspect .Config.Healthcheck.Test`: the unquoted exec-form YAML scalar was split on whitespace
into **10 argv elements**, so python received `-c import` and every probe died with
`SyntaxError: invalid syntax`:

```
["CMD","python","-c","import","os,","urllib.request;","urllib.request.urlopen(\"http://127.0.0.1:\"", ...]
```

A control run of the same logic properly quoted inside the container printed `HEALTHCHECK LOGIC OK`.
`git diff cd2b00d` confirms **this run changed zero healthcheck lines** — pre-existing, not a
regression. All three affected services (api, worker, worker-watch) used the same form; two other
healthchecks in the same file already used `CMD-SHELL` and worked, so the broken three were the
outliers. Converted to `CMD-SHELL`, which hands one string to `sh -c` and cannot be argv-split.

The cascade is why it mattered: api never reached `healthy`, so `worker` and `frontend` — both
dependent on it — never started, which is why the AC's "api+worker both healthy" could not be
evaluated. Fixing it was satisfying the AC, not widening scope.

## 2026-08-10 — M3-A: `[1m]` model ids REJECTED, not stripped

The adapter raises `ValueError` at construction on a `[1m]`-suffixed model id rather than stripping it.
Rationale accepted: stripping would send a *different* model than configured with no signal, masking a
config error, whereas the suffix appearing at all means a Claude-Code-layer delegation id was pasted
into a raw-HTTP config surface. Consistent with the seam's existing fail-loud posture
(`enforce_egress_provenance` and `envelope_from_redacted_transcript` both raise).

Verified: `enforce_egress_provenance` at `:163` precedes URL construction at `:173`; payload carries
exactly `model`/`max_tokens`/`messages` and nothing else, which matters because ICA silently accepts
unknown top-level fields where Anthropic direct returns 400.

Minor accepted inconsistency: this adapter checks for an absent key *inside* `complete()` and returns
`None`, whereas gemini leaves that check to its caller. Justified by the AC demanding adapter-level
degradation here, but the two adapters now differ in where that precondition lives.

## 2026-08-10 — Two gate-envelope false negatives; read the journal, not the envelope

Both M1's and (partially) M3's `reviewer-gate` runs returned a top-level `approved: false` that the
per-lens journal records contradicted. M1: both lenses `approved:true`, cause filed as
`node_01KZPAXY1XJ96DDR0Q9BEYPCXP` (null-vs-`[]` `required_fixes`). M3: both real lenses
(`senior-code-reviewer`, `task-completion-validator`) `approved:true` with all 6 AC met and
`required_fixes:[]`; a third journal record carried no lens verdict and the script appears to have
synthesized an "integrity failure" into the validator's envelope slot from that emptiness. In both
cases the verdict was established by reading `journal.jsonl`, not the envelope, and no gate budget was
charged for the phantom rejection. **Operating rule for this run: the journal's per-agent
`type:result` records are the verdict; the aggregated envelope is advisory until the script bug is
fixed.**

M3's validator integrity complaint was, separately, *correct*: no validation-scope measurement was
supplied. It resolved itself the right way — the validator re-ran every test file touching the changed
symbols itself (150 passed) rather than trusting the orchestrator's counts.

## 2026-08-10 — base URL default contradicted ADR-017 (found by reading the SPIKE, not by a gate)

`CCDASH_LLM_ANTHROPIC_BASE_URL` shipped defaulting to `https://api.anthropic.com` (the paid lane).
ADR-017 in the SPIKE — which the plan designates as the requirement record in place of a PRD — states
"ICA is the default endpoint". So this was a defect against the accepted decision, in the
cost-incurring direction, latent only because the missing model default keeps the lane disabled until
configured. Corrected to the ICA gateway across code + both compose stacks + both env examples + the
guide (commit `a788751`); the test `test_default_base_url_is_anthropic_direct` was **inverted**, not
deleted — a default deserves a test, it was asserting the wrong value (same shape as M1's
credential-in-URL test). **Neither reviewer lens caught this**; both faithfully verified the six stated
ACs, and connecting line 877 of a 913-line SPIKE to a config default was not among them. The lesson:
the requirement record needs reading directly, not only via the ACs distilled from it.

## 2026-08-10 — ADR-016/017/018 did not exist as files; ADR-018's guardrail was prose, now enforced

The plan's M3 AC "ADR-017 + ADR-018 accepted" read as a status flip but required *authoring* them —
the repo stopped at adr-015 and the proposals lived only in the SPIKE. Authored both `accepted`; ADR-016
left to the shipped P1 seam per the plan.

ADR-018 claimed (present tense) a guardrail test forbidding provider modules from importing raw
transcript readers. It did not exist; the nearest test guards the inverse direction. That gap is a real
hole: `enforce_egress_provenance` only inspects an envelope passed to it, so an adapter importing a raw
reader directly and never building an envelope bypasses the whole provenance vocabulary. Wrote
`test_llm_adapters_no_raw_transcript_imports.py` (import-graph walk, two-sided with a positive control
so it can't pass vacuously; proven to bite and reverted clean). No adapter currently violates it. This
ships the enforcement rather than accepting an ADR that overstates its own guarantee.

## 2026-08-10 — M2 gate: a TRUE rejection on per-tick consent (AC3), the caching layer the test hid

M2's security lens rejected on AC3, correctly. Verified on disk: per-tick consent reads
`list_projects()` → `DbProjectManager.list_projects()` → `_ensure_snapshot()` (`project_manager.py:396`),
which is "hydrate on first use" and returns early once `_snapshot_loaded` is True. That flag resets only
in `_invalidate_snapshot()` (`:~538`), never called by `list_projects()`. So a hydrated worker serves an
in-memory snapshot indefinitely, and a consent **revocation** (a bare DB write — no API in this change
set) is invisible until restart. Failing direction is the dangerous one: data keeps egressing after
consent is withdrawn, contradicting both the AC and the sweep job's own "never cached" docstring.

The per-tick test could not catch it: it injected `types.SimpleNamespace(list_projects=lambda: [project])`,
which re-reads a mutable Python object every call, so the caching layer was never exercised — the mock
made the bug look fixed. Re-pass (M2 × security, 1 of 2) dispatched to the original implementer's live
session: force a fresh read via the existing `reload_projects()` before each tick's consent check, make
any unavailable-refresh path *visible* rather than silently stale (a deliberate fail-closed-vs-proceed
decision, recorded), and replace the mock test with one against a real `DbProjectManager` mutated through
a second connection, proven to fail without the fix.

## 2026-08-10 — Close-out: `main` moved and took our SCHEMA_VERSION; ours renumbered 52 -> 53

The plan says "SCHEMA_VERSION 51 -> 52". By the time this branch was ready to land,
`origin/main` was four commits past our base and one of them (`d230d78`, provider /
channel / credential as first-class entities, from a concurrently-running session in a
sibling worktree) had already taken **52**. Both branches set `SCHEMA_VERSION = 52` in
both backends — verified by reading the constant on each side, not inferred from the
commit subject.

How bad: less bad than it looks, and the mechanism was checked rather than assumed.
Migrations here are not a numbered chain. `SCHEMA_VERSION` is a high-water mark and the
`_ensure_column` sweep runs **unconditionally** — `sqlite_migrations.py` logs
"already recorded; running idempotent column/index checks" and then sweeps regardless.
So a DB sitting at their 52 still receives `llm_egress_consent`. No data-loss path. But a
version number that no longer identifies a schema is a real governance defect.

DECISION (orchestrator, Mode-D surface, not delegated): merge `origin/main` in, keep both
migrations in full, renumber ours to **53**. Theirs keeps its `if current_version < 52`
gate untouched; ours re-gates to `< 53`. Zero new `COLUMN_PARITY_DRIFT_ALLOWLIST` entries.
This is a deviation from the plan's literal text, forced by a moved base, and it is the
only reading that satisfies the operator's "squash to main" intent.

## 2026-08-10 — A real parity gap in our OWN M2 commit, found only because the base moved

While resolving the above, `llm_egress_consent` turned out to be present in the
**unconditional** `_ensure_column` sweep in `sqlite_migrations.py` but **absent** from the
equivalent sweep in `postgres_migrations.py`. It was in Postgres' `CREATE TABLE` body and
in its version-gated block, so a DB below our version converged correctly and every test
passed — which is exactly why nobody caught it. Now added to the Postgres unconditional
sweep, mirroring the sqlite placement.

Worth naming the lesson: the dual-DDL rule in CLAUDE.md says "both backends", and we
satisfied it in two of the three places it matters. The green suite proved convergence for
fresh and below-version DBs and said nothing about the belt-and-braces path. This was found
by a forced merge, not by a gate.

## 2026-08-10 — Relaxed another feature's `== 52` assertions to `>= 52`

`backend/tests/test_provider_dimension_schema.py` (theirs, landed on main hours earlier)
asserted `SCHEMA_VERSION == 52` literally, twice. Our bump to 53 broke both. Changed to
`assertGreaterEqual(..., 52)` and renamed the two methods to `..._is_at_least_52` so the
names stop lying.

Rationale for `>=` over bumping to `53`: `SCHEMA_VERSION` is a repo-global high-water mark,
not one feature's property. Pinning it with `==` meant those assertions would fail on the
next schema change by ANY feature, forever; bumping to `53` just relocates the same trap.
The invariant the test actually protects — provider-dimension DDL gated at or after v52 —
is what `>=` states, and their `if current_version < 52` gate still implements it unchanged.
Flagged here because it edits a concurrent session's file.

## 2026-08-10 — Plan gate: a TRUE rejection on AC1; consent gated one egress lane, not both

The plan-level `karen` pass returned CHANGES_REQUESTED, correctly. `CCDASH_LLM_EGRESS_CONSENT`
gated the session-naming lane only. `backend/services/ai_insight.py` constructed the Gemini
adapter (`EGRESS = True`) on the API key alone, with no consent check, reachable live via
`POST /insight` — so consent=false did not mean "egress is off", while the CHANGELOG told
operators it did. AC1 is unqualified ("**no** egress adapter is constructed") where AC2 is
deliberately scoped to sessions, and nothing in this ledger recorded the insight lane as an
accepted exclusion. So: an oversight, not a scoping decision. Fixed, with a
negative-construction test that fails without the fix.

Also fixed from the same pass: the per-tick egress audit line reported the lane from the
LEGACY `CCDASH_SESSION_NAMING_BACKEND` var, so an operator using the documented-preferred
`CCDASH_LLM_SESSION_NAMING_LANE=anthropic` would get `lane=local` recorded while egressing
to ICA.

## 2026-08-10 — The M3 live-ICA-call criterion: NOT obtained, and the plan said it was

The plan's AC->evidence table asserted, for the M3 live row, "HTTP 200, `msg_bdrk_` id in
response, one session named." That never happened. Corrected: the row now splits the
adapter's wire contract (verified by `test_anthropic_adapter.py` — URL, ICA default base,
version header, credential-as-header, frozen payload key-set, `[1m]` rejection) from live
reachability, which is marked NOT OBTAINED and deferred to the operator.

It stays deferred deliberately. It needs an operator-held ICA key, and `open_questions[0]`
— which ICA key the deployed adapter uses — is still open, so an agent picking one would be
guessing at a cost/scope decision. The wire format itself was already measured by four live
probes on 2026-08-07 (see `spike_ref`); what remains unverified is this deployment's key
scope and endpoint liveness, which are operational facts no unit test can hold.

## 2026-08-10 — The pre-existing parity failure, proven rather than assumed

`test_migration_governance.py::test_column_parity_all_shared_tables` fails on this branch.
It is NOT ours. Proven two-sided: a throwaway worktree detached at pristine `origin/main`
(`b5b6a13`) fails the identical assertion with the identical drift set —
`documents` / `entity_links` / `features` / `tasks` on `workspace_id`, with `projects`
appearing nowhere. No allowlist entry was added, and none should be.

## 2026-08-10 — seeded-pg smoke RE-RUN after the renumber, because SQLite-green proves nothing here

The renumber to v53 changed the in-place Postgres upgrade path, and the earlier smoke
evidence was obtained for 51->52 against a base that no longer exists. A migration change
whose only evidence is a green SQLite suite is exactly the shape that crash-loops the node,
so the smoke was re-run rather than assumed still valid.

Result (`bash deploy/runtime/scripts/smoke-seeded-pg.sh`, exit 0): seeded at v29,
`Migration result: applied (reached SCHEMA_VERSION=53)`, `/api/health/ready` returned
`migrationStatus=="applied"`, and `UndefinedColumnError` was ABSENT from both the postgres
and api container logs. This run exercises the upgrade with BOTH `projects.llm_egress_consent`
and the concurrently-landed provider/channel/credential tables present -- which the original
run could not, because that DDL did not exist yet.

Note the M2 fix in `00981fe` is what made this trustworthy: the smoke now DERIVES
`HEAD_VERSION` from the source constant instead of hardcoding it. A hardcoded literal would
have kept asserting 52 and passed while validating the wrong thing -- the exact failure the
commit message for `00981fe` describes having found at "35".

The background shell reported "exit code 0" for the whole invocation, which is meaningless
here (the compound ends in an `echo`). The trustworthy value is the script's own
`SMOKE_EXIT=0` recorded in the log, and the PASS lines above it. Reading the wrapper's code
instead of the script's is how a smoke that actually failed once got reported as green.

## 2026-08-10 — Plan gate round 2: substance closed, and the renumber had left FIVE stale v52 labels

Round 2 returned CHANGES_REQUESTED again, but on a different and much smaller class: all four
round-1 findings verified closed, the v53 merge verified sound, and the only remaining items were
stale `v52` strings that MY OWN renumber created. One was blocking on honesty grounds
(`CHANGELOG.md` still said "SCHEMA_VERSION 51->52", which attributes this feature's column to v52 --
a version that actually belongs to provider-entities).

This is deliberately NOT treated as a third gate round. The reviewer's own instruction was to
re-verify by grep rather than spend another whole-tree pass, and the same-class stop rule does not
apply -- these are not the round-1 defect class recurring, they are a new mechanical class the
renumber introduced. A third full pass over an unchanged behavioural surface would buy nothing.

Corrected: `CHANGELOG.md:60`, both `CREATE TABLE` inline comments, the plan's M2 AC prose,
`adr-017` line 124, and the `test_provider_dimension_schema.py` class docstring.

MY BROADER GREP FOUND TWO THE REVIEWER'S LIST MISSED: `backend/config.py:413` and
`backend/models.py:1880` both said "(v52 migration)" of this column. Worth noting as a method
point -- working the reviewer's enumerated list alone would have shipped two of them. The check that
caught it was a two-sided grep: assert ours all read v53 AND that theirs still correctly reads v52,
rather than grepping only for what I expected to have fixed.

Also removed from the plan's M3 prose: "a real ICA call names one session end-to-end", which was
listed as an AC but is absent from the frontmatter `acceptance_criteria` (the machine-readable
contract) and was never obtained. Replaced with an explicit "deliberately NOT an acceptance
criterion" note carrying the reason.

Recommendation R1 (make the naming backends self-gating by re-checking consent inside `derive_name`,
as they already do for the redaction flag) was NOT implemented -- filed as
node_01KZPR9FW06VJJ6G2V92R440GB. Landing a further edit on the egress boundary after the final gate,
with the 2-pass budget spent, would ship an unreviewed change to the most safety-critical surface in
the feature. The reviewer confirmed there is no open bypass path today, so deferring is the right
trade; the third construction site is unbypassED, not unbypassABLE, and the node says so.

Post-correction test state: 202 passed, exit 0 across the adapter, consent-gate, sweep, registry and
provider-schema suites.
