"""P4 -- one-shot bounded CLI for the empirical larger-model naming test.

hosted-llm-provider-strategy SPIKE, phase P4
(``docs/project_plans/spikes/hosted-llm-provider-strategy.md``, experiment
design lines ~615-696, decision rule line ~658, phase description
~745-754).

Runs ONE bounded pass over a frozen sample of session-naming candidates
through one or more arms (local Ollama / Anthropic-ICA), scoring each arm
mechanically (M1 validity, M2 discriminability, M3 keyword grounding,
latency, failure rate) and applying the pre-registered decision rule. This
is deliberately a single bounded script invocation -- "no ad hoc loop" --
so a re-run is `python -m backend.scripts.p4_naming_eval [...]`, never a
hand-rolled REPL loop.

Reuses the SAME prompt-building/output-validation/adapter code the shipped
naming lanes use (``session_naming_prompt.build_prompt_text``/
``sanitize_title``, ``backend.adapters.llm.{ollama,anthropic}``,
``application.ports.llm``) so the experiment measures the real pipeline,
not a re-implementation of it. It deliberately does NOT go through
``LocalOllamaNamingBackend``/``AnthropicNamingBackend`` directly, because
both persist to ``sessions.session_name`` on success -- this script must
never mutate product state (per the SPIKE's own design: "results written
to a scratch table or NDJSON, not to sessions.session_name").

M4 (blind pairwise human preference) is OUT OF SCOPE for this script by
design -- it is a bounded HUMAN step (40 judgments, one sitting) that no
unattended run can substitute for. ``evaluate_decision_rule`` below applies
the pre-registered rule's short-circuit: if gate 1 (M1) or gate 3 (cost)
already fails, the verdict is "keep local" without needing M4 at all; only
when gates 1 and 3 both pass does the rule need M4, and this script reports
that case as ``inconclusive_pending_m4`` rather than fabricating a result.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.adapters.llm.anthropic import AnthropicTextCompletionAdapter
from backend.adapters.llm.ollama import OllamaTextCompletionAdapter
from backend.application.ports.llm import (
    PromptEnvelope,
    PromptProvenance,
    envelope_from_redacted_transcript,
)
from backend.services.session_naming_prompt import build_prompt_text, sanitize_title

# Identical to LocalOllamaNamingBackend.derive_name / AnthropicNamingBackend.derive_name's
# instruction template (session_naming_local_backend.py) -- the SPIKE design requires the
# prompt held constant across arms; copied verbatim rather than imported because both
# backends inline it as a local string, not an exported constant.
_INSTRUCTION_TEMPLATE = (
    "You generate short titles for software development session "
    "transcripts. Read the excerpt below and respond with ONLY a "
    "concise title (3-8 words, no quotation marks, no trailing "
    "punctuation, no explanation) describing what the session was "
    "about.\n\n"
    "Transcript excerpt:\n{prompt_text}\n\nTitle:"
)

# Degenerate-generic stop-list (M2, per the SPIKE's scoring rubric table).
_DEGENERATE_TITLES = {
    "session",
    "debugging",
    "code changes",
    "bug fix",
    "untitled",
    "chat session",
}

# ~4.7 chars/token, per the SPIKE's own measured conversion (hosted-llm-provider-strategy.md,
# "Cost model" section) -- used only to give an illustrative $ figure from text actually sent/
# received in THIS run; never a substitute for a provider-reported usage count.
_CHARS_PER_TOKEN = 4.7


@dataclass
class FrozenCase:
    """One frozen-sample case: synthetic-but-code-realistic transcript + ground truth."""

    id: str
    transcript_items: list[dict[str, Any]]
    keywords: list[str]


@dataclass
class ArmSpec:
    id: str
    kind: str  # "ollama" | "anthropic"
    model: str
    base_url: str | None = None
    api_key: str | None = None
    rate_in_per_mtok: float = 0.0
    rate_out_per_mtok: float = 0.0


@dataclass
class CallResult:
    arm_id: str
    case_id: str
    title: str | None
    raw: str | None
    latency_s: float
    error: str | None
    input_chars: int
    output_chars: int


def build_frozen_sample() -> list[FrozenCase]:
    """The frozen sample this run evaluates against.

    SPIKE design calls for N=200 real production sessions. This leg has no
    credentialed access to a live session corpus (sandboxed execution; see
    the P4 report), so this is a SMALLER, synthetic-but-code-realistic
    substitute sample -- topics and file/branch references modeled on real
    CCDash session shapes, not drawn from production. This is a disclosed
    deviation, not a silent substitution (see report `assumptions`).
    """
    topics: list[tuple[str, list[str], list[str]]] = [
        (
            "fix-null-pointer-session-detail",
            ["backend/application/services/agent_queries/session_detail.py"],
            ["Fix a null-pointer bug", "raised when a session bundle's transcript field was None"],
        ),
        (
            "add-anthropic-adapter",
            ["backend/adapters/llm/anthropic.py"],
            ["Add an Anthropic Messages API adapter", "wire it to the ICA gateway"],
        ),
        (
            "refactor-session-repo-queries",
            ["backend/db/repositories/sessions.py"],
            ["Refactor the session repository's pagination queries", "for readability"],
        ),
        (
            "write-tests-naming-prompt",
            ["backend/tests/test_session_naming_local_backend.py"],
            ["Write unit tests", "for the session naming prompt builder"],
        ),
        (
            "tune-ollama-timeout-config",
            ["backend/config.py"],
            ["Investigate why the Ollama naming sweep times out", "tune CCDASH_OLLAMA_TIMEOUT_SECONDS"],
        ),
        (
            "migrate-projects-consent-column",
            ["backend/db/sqlite_migrations.py", "backend/db/postgres_migrations.py"],
            ["Add a per-project egress consent column", "dual SQLite and Postgres migration"],
        ),
        (
            "debug-watcher-hot-reload-loop",
            ["backend/db/file_watcher.py"],
            ["Debug the file watcher re-triggering syncs", "on its own writes"],
        ),
        (
            "improve-redaction-tool-aware-fields",
            ["backend/application/services/agent_queries/redaction.py"],
            ["Extend redaction to be tool-name aware", "for structured fields"],
        ),
        (
            "frontend-planning-board-branch-links",
            ["components/Planning/PlanningAgentSessionBoard.tsx"],
            ["Add per-phase session links", "to the planning agent session board"],
        ),
        (
            "cli-offline-mode-projects-json",
            ["backend/cli/offline.py"],
            ["Implement offline CLI mode", "seeding a local cache DB from raw JSONL"],
        ),
        (
            "perf-investigate-slow-sync-tick",
            ["backend/db/sync_engine.py"],
            ["Investigate a slow sync tick", "profile the entity-link rebuild path"],
        ),
        (
            "docs-update-external-api-guide",
            ["docs/guides/external-api-lan-deployment.md"],
            ["Update the external API deployment guide", "document the new capability flag"],
        ),
        (
            "fix-worktree-cwd-resolution",
            ["backend/parsers/platforms/claude_code/parser.py"],
            ["Fix worktree cwd resolution", "so child projects attribute to the right parent repo"],
        ),
        (
            "add-provider-pricing-catalog-entry",
            ["backend/services/provider_pricing.py"],
            ["Add a new model to the pricing catalog", "parse the published rate table"],
        ),
        (
            "review-egress-consent-gate-tests",
            ["backend/tests/test_session_naming_local_backend.py"],
            ["Review the egress consent gate's test coverage", "for the anthropic naming lane"],
        ),
        (
            "hotfix-ica-spend-attribution-null",
            ["backend/parsers/ica_spend.py"],
            ["Hotfix a null ICA spend attribution", "when readings are incomplete"],
        ),
    ]
    cases: list[FrozenCase] = []
    for slug, paths, lines in topics:
        items = [
            {"speaker": "user", "content": lines[0] + ". " + lines[1] + "."},
            {"speaker": "assistant", "content": f"Looked at {paths[0]}."},
            {"speaker": "user", "content": "Yes, go ahead and make that change."},
            {"speaker": "assistant", "content": f"Updated {', '.join(paths)}; tests pass."},
        ]
        keywords = [Path(p).stem.replace("_", "-") for p in paths] + [
            w.lower() for line in lines for w in line.split() if len(w) > 4
        ]
        cases.append(FrozenCase(id=slug, transcript_items=items, keywords=keywords))
    return cases


async def _run_one(arm: ArmSpec, case: FrozenCase) -> CallResult:
    prompt_text = build_prompt_text(case.transcript_items)
    instruction = _INSTRUCTION_TEMPLATE.format(prompt_text=prompt_text)

    if arm.kind == "ollama":
        adapter: Any = OllamaTextCompletionAdapter(
            base_url=arm.base_url or "http://localhost:11434",
            model=arm.model,
            timeout_seconds=60,
        )
        envelope = PromptEnvelope(
            text=instruction,
            provenance=PromptProvenance.TRANSCRIPT_REDACTED,
            redaction_events=0,
        )
    elif arm.kind == "anthropic":
        adapter = AnthropicTextCompletionAdapter(
            api_key=arm.api_key,
            model=arm.model,
            timeout_seconds=30,
            base_url=arm.base_url or "https://api.nextgen-beta.ica.ibm.com/ica",
        )
        envelope = envelope_from_redacted_transcript(instruction, redaction_events=0)
    else:
        raise ValueError(f"unknown arm kind: {arm.kind!r}")

    start = time.monotonic()
    raw: str | None = None
    error: str | None = None
    try:
        raw = await adapter.complete(envelope)
    except Exception as exc:  # noqa: BLE001 -- experiment harness records, never crashes the run
        error = f"{type(exc).__name__}: {exc}"
    latency = time.monotonic() - start

    title = sanitize_title(raw) if error is None else None
    return CallResult(
        arm_id=arm.id,
        case_id=case.id,
        title=title,
        raw=raw,
        latency_s=latency,
        error=error,
        input_chars=len(instruction),
        output_chars=len(raw or ""),
    )


@dataclass
class ArmMetrics:
    arm_id: str
    n: int
    n_failed: int
    m1_validity_rate: float
    m2_discriminability: float
    m3_keyword_grounding: float
    p50_latency_s: float
    p95_latency_s: float
    est_cost_usd: float


def score_arm(arm: ArmSpec, results: list[CallResult], cases_by_id: dict[str, FrozenCase]) -> ArmMetrics:
    n = len(results)
    failed = [r for r in results if r.error is not None]
    valid = [r for r in results if r.title is not None]
    m1 = len(valid) / n if n else 0.0

    lowered_titles = [(r.title or "").strip().lower() for r in valid]
    unique = len(set(lowered_titles))
    degenerate = sum(1 for t in lowered_titles if t in _DEGENERATE_TITLES)
    m2 = max(0.0, (unique - degenerate) / len(valid)) if valid else 0.0

    grounded = 0
    for r in valid:
        case = cases_by_id[r.case_id]
        title_tokens = {w.strip(".,!?").lower() for w in (r.title or "").split()}
        kw_tokens: set[str] = set()
        for kw in case.keywords:
            kw_tokens.update(w.lower() for w in kw.replace("-", " ").replace("/", " ").split())
        if title_tokens & kw_tokens:
            grounded += 1
    m3 = grounded / len(valid) if valid else 0.0

    latencies = sorted(r.latency_s for r in results)
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95_idx = min(len(latencies) - 1, int(len(latencies) * 0.95)) if latencies else 0
    p95 = latencies[p95_idx] if latencies else 0.0

    est_cost = 0.0
    for r in results:
        in_tok = r.input_chars / _CHARS_PER_TOKEN
        out_tok = r.output_chars / _CHARS_PER_TOKEN
        est_cost += (in_tok / 1e6) * arm.rate_in_per_mtok + (out_tok / 1e6) * arm.rate_out_per_mtok

    return ArmMetrics(
        arm_id=arm.id,
        n=n,
        n_failed=len(failed),
        m1_validity_rate=m1,
        m2_discriminability=m2,
        m3_keyword_grounding=m3,
        p50_latency_s=p50,
        p95_latency_s=p95,
        est_cost_usd=est_cost,
    )


def evaluate_decision_rule(
    *,
    local: ArmMetrics,
    hosted: ArmMetrics,
    cost_ceiling_usd: float | None,
    m4_win_rate: float | None,
) -> dict[str, Any]:
    """Apply the SPIKE's pre-registered decision rule (verbatim structure).

    Promote ``hosted`` over ``local`` only if all three hold:
      1. M1 >= local + 5pp, OR M1 already >= 95% on both arms.
      2. M4 win rate >= 60% in blind pairwise preference.
      3. Cost is $0 (free tier) or under an operator-set ceiling.

    Any early gate failure is a definitive "keep local" -- the rule is a
    conjunction, so gate 1 or gate 3 failing alone settles it without M4.
    Only when gates 1 and 3 both pass and M4 is unavailable does this
    return ``inconclusive_pending_m4``.
    """
    gate1 = (hosted.m1_validity_rate >= local.m1_validity_rate + 0.05) or (
        local.m1_validity_rate >= 0.95 and hosted.m1_validity_rate >= 0.95
    )
    gate3 = cost_ceiling_usd is None or hosted.est_cost_usd <= cost_ceiling_usd

    if not gate1:
        return {"verdict": "keep_local", "reason": "gate1_m1_failed", "gate1": gate1, "gate2": None, "gate3": gate3}
    if not gate3:
        return {"verdict": "keep_local", "reason": "gate3_cost_failed", "gate1": gate1, "gate2": None, "gate3": gate3}
    if m4_win_rate is None:
        return {
            "verdict": "inconclusive_pending_m4",
            "reason": "gates_1_and_3_passed_m4_not_run",
            "gate1": gate1,
            "gate2": None,
            "gate3": gate3,
        }
    gate2 = m4_win_rate >= 0.60
    verdict = "promote_hosted" if gate2 else "keep_local"
    return {
        "verdict": verdict,
        "reason": "full_rule_evaluated",
        "gate1": gate1,
        "gate2": gate2,
        "gate3": gate3,
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    cases = build_frozen_sample()
    if args.n is not None:
        cases = cases[: args.n]
    cases_by_id = {c.id: c for c in cases}

    arms: list[ArmSpec] = []
    for spec in args.arm:
        # "|"-separated, not ":" -- a bare Ollama model id (e.g. "qwen2.5:14b")
        # already contains a colon, so ":" cannot double as the field separator.
        parts = spec.split("|")
        if len(parts) < 3:
            raise ValueError(f"--arm must be id|kind|model[|rate_in|rate_out] -- got {spec!r}")
        arm_id, kind, model = parts[0], parts[1], parts[2]
        rate_in = float(parts[3]) if len(parts) > 3 else 0.0
        rate_out = float(parts[4]) if len(parts) > 4 else 0.0
        api_key = None
        if kind == "anthropic":
            import os

            api_key = os.environ.get("CCDASH_LLM_ANTHROPIC_API_KEY") or None
        arms.append(ArmSpec(id=arm_id, kind=kind, model=model, rate_in_per_mtok=rate_in, rate_out_per_mtok=rate_out, api_key=api_key))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, list[CallResult]] = {}
    with out_path.open("w", encoding="utf-8") as fh:
        for arm in arms:
            arm_results: list[CallResult] = []
            for case in cases:
                result = await _run_one(arm, case)
                arm_results.append(result)
                fh.write(json.dumps({
                    "arm": result.arm_id,
                    "case": result.case_id,
                    "title": result.title,
                    "raw": result.raw,
                    "latency_s": round(result.latency_s, 3),
                    "error": result.error,
                }) + "\n")
            all_results[arm.id] = arm_results

    metrics = {arm.id: score_arm(arm, all_results[arm.id], cases_by_id) for arm in arms}
    return {"arms": arms, "metrics": metrics, "n_cases": len(cases), "results_path": str(out_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--arm",
        action="append",
        required=True,
        help="id|kind|model[|rate_in_per_mtok|rate_out_per_mtok], e.g. 'local|ollama|qwen2.5:14b' or 'haiku|anthropic|claude-haiku-4-5|1|5'",
    )
    parser.add_argument("--n", type=int, default=None, help="cap the frozen sample to N cases")
    parser.add_argument("--out", default="docs/project_plans/spikes/results/p4-naming-eval/p4-results.ndjson")
    args = parser.parse_args()

    summary = asyncio.run(run(args))
    for arm in summary["arms"]:
        m = summary["metrics"][arm.id]
        print(
            f"{arm.id:>10} | n={m.n:3d} failed={m.n_failed:2d} "
            f"M1={m.m1_validity_rate:.2f} M2={m.m2_discriminability:.2f} M3={m.m3_keyword_grounding:.2f} "
            f"p50={m.p50_latency_s:.2f}s p95={m.p95_latency_s:.2f}s est_cost=${m.est_cost_usd:.5f}"
        )
    print(f"results written to {summary['results_path']}")


if __name__ == "__main__":
    main()
