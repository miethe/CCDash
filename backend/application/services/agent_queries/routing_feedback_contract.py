"""Frozen contract/taxonomy/mapping identity constants for the Proof -> Routing
Feedback Loop producer surface (BP-6, T1-002).

This module is the **single source of truth** for the `aos.routing.feedback` v1
cross-repo contract's identity, versioning, and digest values. Every downstream
phase of this feature (Data Layer, Rollup Compute Service, Worker Sweep Job,
Transport Surfaces, Validation/Guards/Docs) MUST import these constants rather
than re-declaring or hardcoding any of them elsewhere in the codebase.

Pinned contract source (informational only — never fetched live at runtime):
    agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback.md
    agentic_meta_dev/docs/agentic-operator/contracts/routing-feedback-task-map.v1.json

Design intent:
    - These are frozen contract-identity constants, not runtime configuration.
      They are plain Python literals with no environment-variable overrides and
      no dynamic computation at import time.
    - Runtime behavior toggles (CCDASH_ROUTING_FEEDBACK_ENABLED and its
      companion tunables) live in `backend.config`, deliberately kept separate
      so contract identity and environment-configurable behavior are never
      conflated.
    - Digest *verification* (comparing MAPPING_DIGEST against the vendored
      JSON's actual SHA-256) happens in
      `backend/tests/test_routing_feedback_contract_parity.py` (T1-005), not in
      this module.

See also: docs/project_plans/PRDs/infrastructure/proof-to-routing-loop-v1.md,
docs/project_plans/implementation_plans/infrastructure/proof-to-routing-loop-v1/phase-1-contract-envelope-foundations.md
"""

from __future__ import annotations

from pathlib import Path

# --- Contract identity -------------------------------------------------------

CONTRACT_ID = "aos.routing.feedback"
CONTRACT_VERSION = "1.0.0"

# --- Taxonomy identity (aos.routing.task_class vocabulary) --------------------

TAXONOMY_ID = "aos.routing.task_class"
TAXONOMY_VERSION = "1.0.0"
TAXONOMY_DIGEST = "sha256:d96a0819b0a3a42d14eccc1421d3146b8364253d975d9d54f4f264d4b6adeaca"

# --- Mapping identity (CCDash's pinned skill_name -> task_class mapping) -----

MAPPING_ID = "ccdash.skill_name_to_aos.routing.task_class"
MAPPING_VERSION = "1.2.0"
MAPPING_DIGEST = "sha256:4d62b43a14fb083d146354a8fa08749042c2fa88214738b483053faddc0e81ab"

# --- Producer + capability identity ------------------------------------------

PRODUCER = "ccdash"
CAPABILITY_STRING = "routing:feedback"

# --- Vendored mapping artifact path (T1-001) ---------------------------------

MAPPING_JSON_PATH = Path(__file__).resolve().parent / "routing_task_map_v1.json"
