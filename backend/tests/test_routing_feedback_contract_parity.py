"""Digest-parity + flag-default contract test for the Proof -> Routing
Feedback Loop producer surface (BP-6, T1-005).

Enforces this feature's Phase 1 exit criteria mechanically rather than by
inspection:

1. **Digest parity** -- the vendored ``routing_task_map_v1.json`` (T1-001)
   file's raw-byte SHA-256 must equal ``routing_feedback_contract.MAPPING_DIGEST``
   (T1-002), normalized against that constant's literal ``sha256:`` prefix. Any
   byte-level drift in the vendored mapping (hand-edit, re-indentation,
   line-ending change) fails this test immediately, per the phase's own
   "byte-for-byte means byte-for-byte" gotcha.
2. **Flag default** -- ``backend.config.CCDASH_ROUTING_FEEDBACK_ENABLED``
   (T1-004) must read ``False`` when ``CCDASH_ROUTING_FEEDBACK_ENABLED`` is
   unset in the environment -- this feature is opt-in (default-OFF), the
   *inverse* polarity of the AAR-review autonomous worker's default-True
   (opt-out) flag (decisions block D6).

Phase 6's T6-002 later extends this module into the full no-LLM /
envelope-completeness / determinism test battery -- this phase's test is
deliberately narrow (the two assertions above only), per
``phase-1-contract-envelope-foundations.md``.

T6-002 (Phase 6) adds
``MappingDigestParityTests.test_corrupted_mapping_fixture_fails_the_digest_parity_assertion``
below: a deliberately-corrupted, test-local copy of the vendored mapping's
bytes (never the real file on disk) proves the digest-parity assertion above
is load-bearing rather than vacuously true -- i.e. that it would actually
fail CI on real byte-level drift, not just pass because the comparison can
never disagree. This is the R-P3 seam-task hardening required by
``phase-6-validation-guards-docs.md`` (AC-2, PRD SS11).

Run as a named module (full collection can hang -- see
``docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md`` and the
repo-wide pytest-collection caveat):
    backend/.venv/bin/python -m pytest backend/tests/test_routing_feedback_contract_parity.py -v
"""
from __future__ import annotations

import hashlib
import importlib
import os
import unittest

from backend import config as _config
from backend.application.services.agent_queries import routing_feedback_contract

_FLAG_NAME = "CCDASH_ROUTING_FEEDBACK_ENABLED"


def _sha256_prefixed(data: bytes) -> str:
    """Hash *data* and return it with the contract's literal ``sha256:``
    prefix, matching ``MAPPING_DIGEST``'s own prefix convention (T1-002's
    normalization note: pick one side to prepend/strip and stay consistent --
    this module prepends the prefix to the computed digest rather than
    stripping it from the constant, and this convention is reused verbatim by
    Phase 3/6's own digest comparisons).
    """
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


class MappingDigestParityTests(unittest.TestCase):
    """AC-2 / AC-8 -- vendored mapping bytes must match the pinned digest."""

    def test_vendored_mapping_sha256_matches_pinned_mapping_digest(self) -> None:
        actual_bytes = routing_feedback_contract.MAPPING_JSON_PATH.read_bytes()
        actual_digest = _sha256_prefixed(actual_bytes)

        self.assertEqual(
            actual_digest,
            routing_feedback_contract.MAPPING_DIGEST,
            "Vendored routing_task_map_v1.json bytes no longer match the pinned "
            f"MAPPING_DIGEST constant. Expected {routing_feedback_contract.MAPPING_DIGEST!r}, "
            f"computed {actual_digest!r}. Either the vendored file drifted from the "
            "normative cross-repo contract copy, or MAPPING_DIGEST was edited without "
            "re-vendoring -- both require a deliberate mapping_version/mapping_digest "
            "bump together, never a silent one-sided edit.",
        )

    def test_mapping_digest_constant_carries_the_sha256_prefix_convention(self) -> None:
        # Guards the normalization assumption itself: if a future edit drops
        # the "sha256:" prefix from MAPPING_DIGEST, the parity test above
        # would start comparing a prefixed computed digest against an
        # unprefixed constant and fail in a confusing way -- fail loudly and
        # explain here instead of relying on that test's message alone.
        self.assertTrue(
            routing_feedback_contract.MAPPING_DIGEST.startswith("sha256:"),
            "MAPPING_DIGEST must carry the literal 'sha256:' prefix per the "
            "contract's own convention (T1-002); this test's normalization "
            "logic assumes that prefix is present.",
        )

    def test_corrupted_mapping_fixture_fails_the_digest_parity_assertion(self) -> None:
        """T6-002 (AC-2, bullet 2) -- prove the digest-parity assertion above
        is load-bearing, not vacuously true, by running the exact same
        ``assertEqual`` comparison against a deliberately corrupted,
        test-local copy of the vendored mapping's bytes and confirming it
        raises. This never writes to, nor mutates, the real vendored file on
        disk -- the corruption exists only as an in-memory ``bytes`` object
        for the duration of this test.
        """
        real_bytes = routing_feedback_contract.MAPPING_JSON_PATH.read_bytes()
        corrupted_bytes = real_bytes.replace(
            b'"mapping_version": "1.1.0"', b'"mapping_version": "1.1.1"', 1
        )

        # Sanity: the targeted replace must have actually changed something,
        # or this test would "pass" for the wrong reason -- asserting a
        # failure that can never occur because the "corruption" was a no-op
        # (e.g. because mapping_version was bumped and the literal above no
        # longer appears in the vendored file). If this fires, update the
        # corruption target to match the current vendored content.
        self.assertNotEqual(
            corrupted_bytes,
            real_bytes,
            "test setup bug: the corrupted fixture is byte-identical to the "
            "real vendored file -- the targeted 'mapping_version: 1.1.0' "
            "substring no longer exists in routing_task_map_v1.json.",
        )

        with self.assertRaises(
            AssertionError,
            msg=(
                "a deliberately corrupted copy of the vendored mapping "
                "produced the SAME digest as the pinned MAPPING_DIGEST "
                "constant -- the digest-parity assertion above is vacuously "
                "true and could never catch real byte-level drift, which "
                "defeats this seam task's purpose (AC-2)."
            ),
        ):
            self.assertEqual(
                _sha256_prefixed(corrupted_bytes),
                routing_feedback_contract.MAPPING_DIGEST,
            )


class RoutingFeedbackFlagDefaultTests(unittest.TestCase):
    """AC-4 / D6 -- CCDASH_ROUTING_FEEDBACK_ENABLED must default to False."""

    def setUp(self) -> None:
        self._original_env_value = os.environ.get(_FLAG_NAME)

    def tearDown(self) -> None:
        if self._original_env_value is None:
            os.environ.pop(_FLAG_NAME, None)
        else:
            os.environ[_FLAG_NAME] = self._original_env_value
        importlib.reload(_config)

    def test_flag_defaults_false_when_env_var_is_unset(self) -> None:
        os.environ.pop(_FLAG_NAME, None)
        importlib.reload(_config)

        self.assertIs(
            _config.CCDASH_ROUTING_FEEDBACK_ENABLED,
            False,
            "CCDASH_ROUTING_FEEDBACK_ENABLED must default to False (opt-in) when "
            "unset -- this is the inverse polarity of "
            "CCDASH_AAR_REVIEW_AUTONOMOUS_WORKER_ENABLED's default-True (opt-out) "
            "flag; do not copy that precedent's default.",
        )

    def test_flag_reads_true_when_env_var_is_explicitly_set(self) -> None:
        # Sanity check that the flag is genuinely environment-driven (not a
        # hardcoded False literal) -- without this, the default-false
        # assertion above could pass trivially even if the `_env_bool` wiring
        # were silently broken.
        os.environ[_FLAG_NAME] = "true"
        importlib.reload(_config)

        self.assertIs(_config.CCDASH_ROUTING_FEEDBACK_ENABLED, True)


if __name__ == "__main__":
    unittest.main()
