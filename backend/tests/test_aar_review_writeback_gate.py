"""Phase 6-B (T6-005/T6-007/T6-008) gated escalation/writeback seam tests.

Covers:

- T6-005 (Guard 3): the per-project, rolling-window escalation-quota gate --
  pure-function unit coverage plus the ``check_escalation_quota`` refusal
  path (over-quota -> ``EscalationQuotaExceededError``, never a handoff).
- T6-007 (AC-P6.1): the gated writeback seam itself -- ``assert_run_approved``
  refuses on missing/pending/rejected/unknown status; only an EXACT
  ``status == "approved"`` reference reaches the handoff.
- T6-008 (AC-P6.1 + AC-P6.3): integration coverage proving a REJECTED,
  PENDING, or MISSING run reference never reaches
  ``log_aar_review_candidate`` (the existing emit contract) across every
  call path this module exposes, plus the quota gate's over-quota refusal,
  plus a gate-ORDER regression test (a rejected + over-quota run must still
  fail on the approval gate, not the quota gate).
- A static-import-boundary audit mirroring
  ``test_aar_review_no_llm_imports.py``'s precedent: the P6-A worker
  (``aar_review_sweep_job.py``) never imports this seam module, and this
  seam module itself never imports anything resembling a swarm/ARC
  dispatcher or subprocess/network transport.

HARD INVARIANT: zero LLM/model calls anywhere on this path -- every fixture
below is a plain dataclass/mock; no model/agent client is imported.

Run as a named module (full collection can hang):
    backend/.venv/bin/python -m pytest backend/tests/test_aar_review_writeback_gate.py -v
"""
from __future__ import annotations

import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend.application.services.agent_queries.aar_review_writeback import (
    ApprovedRunReference,
    AARReviewWritebackResult,
    EscalationQuotaExceededError,
    EscalationRecord,
    RunNotApprovedError,
    assert_run_approved,
    check_escalation_quota,
    count_recent_approved_escalations,
    emit_aar_review_writeback,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WRITEBACK_MODULE_PATH = (
    _REPO_ROOT / "backend/application/services/agent_queries/aar_review_writeback.py"
)
_SWEEP_JOB_MODULE_PATH = _REPO_ROOT / "backend/adapters/jobs/aar_review_sweep_job.py"

_NOW = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)

_LOG_TARGET = "backend.application.services.agent_queries.aar_review_writeback.log_aar_review_candidate"


def _approved(project_id: str = "proj-1", run_id: str = "run-1") -> ApprovedRunReference:
    return ApprovedRunReference(run_id=run_id, status="approved", project_id=project_id)


def _pending(project_id: str = "proj-1", run_id: str = "run-1") -> ApprovedRunReference:
    return ApprovedRunReference(run_id=run_id, status="pending", project_id=project_id)


def _rejected(project_id: str = "proj-1", run_id: str = "run-1") -> ApprovedRunReference:
    return ApprovedRunReference(run_id=run_id, status="rejected", project_id=project_id)


def _unknown(project_id: str = "proj-1", run_id: str = "run-1") -> ApprovedRunReference:
    return ApprovedRunReference(run_id=run_id, status="frobnicated", project_id=project_id)


# ── 1. assert_run_approved: the approval gate, in isolation ─────────────────


class AssertRunApprovedTests(unittest.TestCase):
    def test_approved_run_passes_through(self) -> None:
        run = _approved()
        self.assertIs(assert_run_approved(run), run)

    def test_pending_run_refused(self) -> None:
        with self.assertRaises(RunNotApprovedError):
            assert_run_approved(_pending())

    def test_rejected_run_refused(self) -> None:
        with self.assertRaises(RunNotApprovedError):
            assert_run_approved(_rejected())

    def test_missing_run_refused(self) -> None:
        with self.assertRaises(RunNotApprovedError):
            assert_run_approved(None)

    def test_unknown_status_run_refused(self) -> None:
        with self.assertRaises(RunNotApprovedError):
            assert_run_approved(_unknown())

    def test_status_match_is_exact_case_sensitive(self) -> None:
        # "Approved" (capitalized) must NOT satisfy the gate -- fail-closed,
        # exact-match only.
        run = ApprovedRunReference(run_id="run-1", status="Approved", project_id="proj-1")
        with self.assertRaises(RunNotApprovedError):
            assert_run_approved(run)


# ── 2. Guard 3: escalation-quota pure functions ──────────────────────────────


class EscalationQuotaPureFunctionTests(unittest.TestCase):
    def test_counts_only_records_within_window(self) -> None:
        history = [
            EscalationRecord(project_id="proj-1", approved_at=_NOW - timedelta(hours=1)),
            EscalationRecord(project_id="proj-1", approved_at=_NOW - timedelta(hours=23)),
            EscalationRecord(project_id="proj-1", approved_at=_NOW - timedelta(hours=25)),  # outside 24h window
        ]
        count = count_recent_approved_escalations("proj-1", history, window_hours=24, now=_NOW)
        self.assertEqual(count, 2)

    def test_counts_are_scoped_per_project_never_global(self) -> None:
        history = [
            EscalationRecord(project_id="proj-1", approved_at=_NOW - timedelta(hours=1)),
            EscalationRecord(project_id="proj-2", approved_at=_NOW - timedelta(hours=1)),
            EscalationRecord(project_id="proj-2", approved_at=_NOW - timedelta(hours=1)),
        ]
        self.assertEqual(count_recent_approved_escalations("proj-1", history, window_hours=24, now=_NOW), 1)
        self.assertEqual(count_recent_approved_escalations("proj-2", history, window_hours=24, now=_NOW), 2)

    def test_naive_datetime_treated_as_utc(self) -> None:
        naive_recent = _NOW.replace(tzinfo=None) - timedelta(hours=1)
        history = [EscalationRecord(project_id="proj-1", approved_at=naive_recent)]
        self.assertEqual(count_recent_approved_escalations("proj-1", history, window_hours=24, now=_NOW), 1)

    def test_check_escalation_quota_passes_under_quota(self) -> None:
        history = [
            EscalationRecord(project_id="proj-1", approved_at=_NOW - timedelta(hours=1))
            for _ in range(4)
        ]
        count = check_escalation_quota("proj-1", history, quota=5, window_hours=24, now=_NOW)
        self.assertEqual(count, 4)

    def test_check_escalation_quota_refuses_at_quota(self) -> None:
        history = [
            EscalationRecord(project_id="proj-1", approved_at=_NOW - timedelta(hours=1))
            for _ in range(5)
        ]
        with self.assertRaises(EscalationQuotaExceededError):
            check_escalation_quota("proj-1", history, quota=5, window_hours=24, now=_NOW)

    def test_check_escalation_quota_refuses_over_quota(self) -> None:
        history = [
            EscalationRecord(project_id="proj-1", approved_at=_NOW - timedelta(hours=1))
            for _ in range(9)
        ]
        with self.assertRaises(EscalationQuotaExceededError):
            check_escalation_quota("proj-1", history, quota=5, window_hours=24, now=_NOW)

    def test_check_escalation_quota_uses_config_defaults_when_unspecified(self) -> None:
        # Default quota is 5, default window is 24h (config.py) -- 5 in-window
        # records with no explicit quota/window override must still refuse.
        history = [
            EscalationRecord(project_id="proj-1", approved_at=_NOW - timedelta(hours=1))
            for _ in range(5)
        ]
        with self.assertRaises(EscalationQuotaExceededError):
            check_escalation_quota("proj-1", history, now=_NOW)

    def test_over_quota_project_never_starves_another_project(self) -> None:
        history = [
            EscalationRecord(project_id="proj-1", approved_at=_NOW - timedelta(hours=1))
            for _ in range(9)
        ]
        # proj-2 has zero recorded escalations -- its own quota check must pass
        # even though proj-1 (a different, noisy project) is deep over quota.
        count = check_escalation_quota("proj-2", history, quota=5, window_hours=24, now=_NOW)
        self.assertEqual(count, 0)


# ── 3. emit_aar_review_writeback: T6-007/T6-008 integration coverage ────────


class EmitWritebackGateIntegrationTests(unittest.TestCase):
    """T6-008: assert rejected/pending/missing/unknown NEVER reach the emit contract."""

    def test_rejected_run_never_emits(self) -> None:
        with patch(_LOG_TARGET) as mock_log:
            with self.assertRaises(RunNotApprovedError):
                emit_aar_review_writeback(
                    _rejected(), document_id="doc-1", session_refs=["s-1"], verdict="deep_review_recommended",
                )
            mock_log.assert_not_called()

    def test_pending_run_never_emits(self) -> None:
        with patch(_LOG_TARGET) as mock_log:
            with self.assertRaises(RunNotApprovedError):
                emit_aar_review_writeback(
                    _pending(), document_id="doc-1", session_refs=["s-1"], verdict="deep_review_recommended",
                )
            mock_log.assert_not_called()

    def test_missing_run_never_emits(self) -> None:
        with patch(_LOG_TARGET) as mock_log:
            with self.assertRaises(RunNotApprovedError):
                emit_aar_review_writeback(
                    None, document_id="doc-1", session_refs=["s-1"], verdict="deep_review_recommended",
                )
            mock_log.assert_not_called()

    def test_unknown_status_run_never_emits(self) -> None:
        with patch(_LOG_TARGET) as mock_log:
            with self.assertRaises(RunNotApprovedError):
                emit_aar_review_writeback(
                    _unknown(), document_id="doc-1", session_refs=["s-1"], verdict="deep_review_recommended",
                )
            mock_log.assert_not_called()

    def test_over_quota_approved_run_never_emits(self) -> None:
        history = [
            EscalationRecord(project_id="proj-1", approved_at=_NOW - timedelta(hours=1))
            for _ in range(5)
        ]
        with patch(_LOG_TARGET) as mock_log:
            with self.assertRaises(EscalationQuotaExceededError):
                emit_aar_review_writeback(
                    _approved(),
                    document_id="doc-1",
                    session_refs=["s-1"],
                    verdict="deep_review_recommended",
                    escalation_history=history,
                    quota=5,
                    window_hours=24,
                    now=_NOW,
                )
            mock_log.assert_not_called()

    def test_approved_run_under_quota_emits_exactly_once(self) -> None:
        with patch(_LOG_TARGET) as mock_log:
            result = emit_aar_review_writeback(
                _approved(),
                document_id="doc-1",
                session_refs=["s-1"],
                verdict="deep_review_recommended",
                triggered_flags=["context_ballooning"],
                escalation_history=[],
                quota=5,
                window_hours=24,
                now=_NOW,
            )
            mock_log.assert_called_once_with(
                document_id="doc-1",
                session_refs=["s-1"],
                verdict="deep_review_recommended",
                triggered_flags=["context_ballooning"],
            )
        self.assertIsInstance(result, AARReviewWritebackResult)
        self.assertTrue(result.accepted)
        self.assertEqual(result.run_id, "run-1")
        self.assertEqual(result.project_id, "proj-1")
        self.assertEqual(result.escalation_count_in_window, 0)

    def test_gate_order_rejected_and_over_quota_fails_on_approval_gate_first(self) -> None:
        """Regression: approval gate must be checked BEFORE the quota gate.

        A rejected run whose project is ALSO deep over quota must fail with
        ``RunNotApprovedError`` (the approval gate), never
        ``EscalationQuotaExceededError`` -- proving a rejected run can never
        "sneak through" by virtue of being under quota, and that quota
        history is never even consulted for a non-approved run.
        """
        over_quota_history = [
            EscalationRecord(project_id="proj-1", approved_at=_NOW - timedelta(hours=1))
            for _ in range(99)
        ]
        with patch(_LOG_TARGET) as mock_log:
            with self.assertRaises(RunNotApprovedError):
                emit_aar_review_writeback(
                    _rejected(),
                    document_id="doc-1",
                    session_refs=["s-1"],
                    verdict="deep_review_recommended",
                    escalation_history=over_quota_history,
                    quota=5,
                    window_hours=24,
                    now=_NOW,
                )
            mock_log.assert_not_called()

    def test_missing_run_with_no_other_args_fails_before_touching_quota(self) -> None:
        # Even with defaults for every quota kwarg (i.e. config-driven), a
        # missing run must refuse -- proving the approval gate is unconditional.
        with patch(_LOG_TARGET) as mock_log:
            with self.assertRaises(RunNotApprovedError):
                emit_aar_review_writeback(None, document_id="doc-1")
            mock_log.assert_not_called()


# ── 4. Static import-boundary audit (mirrors test_aar_review_no_llm_imports.py) ──


class WritebackSeamImportBoundaryTests(unittest.TestCase):
    """No autonomous path may import this seam; this seam may never import a dispatcher."""

    def test_sweep_job_never_imports_the_writeback_seam(self) -> None:
        source = _SWEEP_JOB_MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(_SWEEP_JOB_MODULE_PATH))
        imported_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.append(node.module)
                imported_names.extend(f"{node.module}.{alias.name}" for alias in node.names)

        self.assertFalse(
            any("aar_review_writeback" in name for name in imported_names),
            "AARReviewSweepJob (P6-A, autonomous worker) must NEVER import the "
            "gated writeback seam -- the worker has no code path to an "
            "ApprovedRunReference and must not gain one via a stray import.",
        )
        # Sanity: the source text itself (not just parsed imports) must not
        # reference the seam module/symbols either -- catches e.g. a
        # `getattr`/string-based dynamic import that the AST walk would miss.
        self.assertNotIn("aar_review_writeback", source)

    def test_writeback_seam_has_no_dispatch_or_transport_import(self) -> None:
        source = _WRITEBACK_MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(_WRITEBACK_MODULE_PATH))
        imported_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.append(node.module)

        banned_substrings = (
            "subprocess", "socket", "requests", "httpx", "aiohttp", "urllib",
            "swarm", "arc", "skillmeat",
        )
        offending = [
            name for name in imported_names
            if any(banned in name.lower() for banned in banned_substrings)
        ]
        self.assertEqual(
            offending, [],
            f"aar_review_writeback.py must never import a network/subprocess/"
            f"dispatch-shaped module (Hard Invariant #2: CCDash emits only); "
            f"found: {offending}",
        )

    def test_writeback_seam_only_emits_via_the_existing_log_contract(self) -> None:
        source = _WRITEBACK_MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("log_aar_review_candidate", source)
        # No dispatch-shaped helper name anywhere in this module's source.
        for banned_symbol in ("spawn_agent", "dispatch_agent", "invoke_agent", "run_subagent"):
            self.assertNotIn(banned_symbol, source)


if __name__ == "__main__":
    unittest.main()
