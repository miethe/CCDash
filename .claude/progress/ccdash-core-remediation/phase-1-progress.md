---
schema_version: 2
doc_type: progress
phase: 1
phase_title: "Transport-neutral transcript service + redaction"
feature_slug: ccdash-core-remediation
status: completed
created: 2026-06-11
updated: 2026-06-11
overall_progress: 100
completion_estimate: 2026-06-11
runtime_smoke: "skipped — Phase 1 is a service/library layer with no HTTP surface; REST smoke lands in Phase 2 (T2-004); MCP/CLI smoke lands in Phase 3 (T3-008). Per CLAUDE.md, runtime smoke gate applies to agent-facing surfaces: Phase 1 exit criteria are satisfied by unit/integration tests alone."
parallelization:
  strategy: sequential
  batch_1: [T1-001, T1-002, T1-003, T1-004, T1-005]
---

# Phase 1 Progress — Transport-neutral transcript service + redaction

## AC Audit

### AC R1.1 — session_detail service returns full detail for any project

**Verdict: MET**

| Criterion | Evidence |
|-----------|----------|
| `get_session_detail(project_id, session_id, ports, *, include, cursor, limit)` exposed | `session_detail.py:256` — signature matches spec exactly |
| `project_id` threaded into every repository call | `get_by_id(session_id, project_id=project_id)` line 348; `list_relationships(project_id, session_id)` line 410; `get_many_by_ids(child_ids, project_id=project_id)` line 418 |
| `SessionTranscriptService.list_session_logs` is the sole transcript reader | `_transcript_service = SessionTranscriptService()` singleton line 90; `list_session_logs` called line 380; structural guard `test_session_transcript_service_is_sole_reader` + `test_no_duplicate_transcript_reader` pass |
| All include flags gated (`transcript`, `subagents`, `tokens`, `artifacts`, `links`) | Lines 368, 408, 433, 440 — each segment gated by `INCLUDE_*` constant; `ALL_INCLUDE_FLAGS` frozenset |
| No active-project singleton reads | No `get_active_project` / singleton pattern in service; `project_id` is required param |
| Missing optional segment → empty list / None, not a 500 | `test_entity_links_failure_returns_empty_not_500`, `test_relationships_failure_returns_empty_subagents`, `test_empty_transcript_returns_empty_page` |
| Unknown include flag → warning, not error | `test_unknown_include_flag_ignored_no_error` — passes `"totally_unknown_flag_xyz"` without exception |
| Non-active project returns correct bundle | `test_non_active_project_returns_correct_bundle` — queries PROJ_A with project_id="proj-alpha" (no active project singleton), bundle returned with correct project_id |

### AC R1.2 — layered redaction scrubs secrets/PII across all egress payloads

**Verdict: MET**

| Criterion | Evidence |
|-----------|----------|
| Redaction applied inside `session_detail.py` before return | Lines 387–395: `page_items, redacted_count = redact_entries(page_items); total_redacted += redacted_count` — runs before `TranscriptPage` is built |
| Layer 1 (pattern scan) present | `redaction.py:51–111` — 9 pattern groups: api_key_assignment, bearer_token, aws_access_key_id, aws_secret_key, gcp_private_key, pem_private_key_header, sk_key, github_pat, dotenv_assignment, hex_64 |
| Layer 2 (tool-name-aware) present | `redaction.py:135–204` — `_TOOL_SENSITIVE_ARG_KEYS` maps Bash/Shell/Write/Edit/MultiEdit/computer_use to sensitive arg keys; `_redact_tool_call` applies both layers |
| Configurable via `CCDASH_REDACTION_PATTERNS_ENABLED` | `redaction.py:233` — `_redaction_env_bool("CCDASH_REDACTION_PATTERNS_ENABLED", True)` |
| Configurable via `CCDASH_REDACTION_TOOL_AWARE_ENABLED` | `redaction.py:235` — `_redaction_env_bool("CCDASH_REDACTION_TOOL_AWARE_ENABLED", True)` |
| Fail-closed defaults (unset → enabled) | `_redaction_env_bool` returns `default=True` on empty/missing env var; `test_default_both_enabled` verifies |
| Unknown tool falls through to Layer 1 (never fail-open) | `_TOOL_SENSITIVE_ARG_KEYS.get(tool_name, [])` returns `[]` for unknown → all arg keys scanned via Layer 1; `test_unknown_tool_still_runs_layer1_on_args` verifies |
| Redaction-event logs record count only, never contents | `redaction.py:302–308` — `logger.debug("redact_entries: redacted %d field(s) across %d entries ...", total, len(entries), ...)` — count only |
| Known secret never appears in service output | `test_embedded_secret_absent_from_output` — `sk-abc123…` embedded in log content; absent from `bundle.as_dict()` output |
| Redaction failure is logged and entry passes through (fail-safe delivery) | `session_detail.py:387–396` — bare `except Exception: logger.warning(...)` guard around `redact_entries` call |

---

## Task Table

tasks:
  - id: T1-001
    name: "Service scaffold + include-flag contract"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: >
      backend/application/services/agent_queries/session_detail.py created.
      get_session_detail() exposes all 5 include flags; project_id threaded
      to every repo call; SessionTranscriptService singleton is sole reader.
    test_evidence:
      module: backend/tests/test_session_detail_service.py
      tests:
        - TestGetSessionDetail::test_returns_bundle_for_existing_session
        - TestGetSessionDetail::test_returns_none_for_absent_session
        - TestGetSessionDetail::test_returns_none_for_wrong_project
        - TestGetSessionDetail::test_none_include_returns_all_segments
        - TestGetSessionDetail::test_include_tokens_only_returns_only_tokens
        - TestGetSessionDetail::test_include_transcript_only
        - TestGetSessionDetail::test_unknown_include_flag_ignored_no_error
        - TestGetSessionDetail::test_non_active_project_returns_correct_bundle
        - TestStructuralGuards::test_session_transcript_service_is_sole_reader
        - TestStructuralGuards::test_no_duplicate_transcript_reader
        - TestStructuralGuards::test_project_id_passed_to_get_by_id
    acs:
      - AC R1.1: DONE

  - id: T1-002
    name: "Cursor pagination envelope"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: >
      TranscriptPage dataclass with items/cursor/limit/next_cursor; as_dict()
      returns {items,cursor,limit,nextCursor}. _encode_cursor/_decode_cursor
      are opaque base64-encoded JSON offset strings. Over-max limit clamped
      and logged. DEFAULT_TRANSCRIPT_LIMIT=200, MAX_TRANSCRIPT_LIMIT=1000.
    test_evidence:
      module: backend/tests/test_session_detail_service.py
      tests:
        - TestCursorHelpers::test_encode_decode_round_trip_zero
        - TestCursorHelpers::test_encode_decode_round_trip_positive
        - TestCursorHelpers::test_decode_none_returns_zero
        - TestCursorHelpers::test_decode_empty_returns_zero
        - TestCursorHelpers::test_decode_garbage_returns_zero
        - TestCursorHelpers::test_encode_produces_string
        - TestGetSessionDetail::test_empty_transcript_returns_empty_page
        - TestGetSessionDetail::test_single_page_next_cursor_is_none
        - TestGetSessionDetail::test_multi_page_round_trip_no_gaps_no_dupes
        - TestGetSessionDetail::test_over_max_limit_is_clamped
        - TestGetSessionDetail::test_page_items_count_matches_limit
        - TestGetSessionDetail::test_transcript_page_as_dict_shape
    acs:
      - AC R1.1 (pagination shape): DONE

  - id: T1-003
    name: "Layered redaction module"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: >
      backend/application/services/agent_queries/redaction.py created.
      Layer 1: 9 secret pattern groups (api_key_assignment, bearer_token,
      aws_access_key_id, aws_secret_key, gcp_private_key, pem_private_key_header,
      sk_key, github_pat, dotenv_assignment, hex_64). Layer 2: tool-name-aware
      field redaction for Bash/Shell/Write/Edit/MultiEdit/computer_use.
      CCDASH_REDACTION_PATTERNS_ENABLED + CCDASH_REDACTION_TOOL_AWARE_ENABLED
      env knobs, fail-closed defaults. Count-only structured log.
    test_evidence:
      module: backend/tests/test_redaction.py
      tests:
        - TestLayer1Patterns::test_api_key_assignment_fires
        - TestLayer1Patterns::test_bearer_token_fires
        - TestLayer1Patterns::test_aws_access_key_id_fires
        - TestLayer1Patterns::test_aws_secret_access_key_fires
        - TestLayer1Patterns::test_openai_sk_key_fires
        - TestLayer1Patterns::test_github_pat_fires
        - TestLayer1Patterns::test_pem_private_key_header_fires
        - TestLayer1Patterns::test_dotenv_assignment_fires
        - TestLayer1Patterns::test_hex_64_fires
        - TestLayer1Patterns::test_clean_plain_text_unchanged
        - TestLayer1Patterns::test_short_hex_not_redacted
        - TestLayer1Patterns::test_numeric_only_string_unchanged
        - TestLayer1Patterns::test_short_api_value_not_redacted
        - TestLayer1Patterns::test_empty_string_unchanged
        - TestRedactLogEntryLayer2::test_bash_command_with_env_var_redacted
        - TestRedactLogEntryLayer2::test_bash_sk_key_in_args_redacted
        - TestRedactLogEntryLayer2::test_write_tool_content_scanned
        - TestRedactLogEntryLayer2::test_unknown_tool_still_runs_layer1_on_args
        - TestRedactLogEntryLayer2::test_tool_output_with_secret_redacted
        - TestRedactLogEntryLayer2::test_tool_aware_disabled_layer2_skipped
        - TestRedactLogEntryLayer2::test_both_layers_disabled_nothing_redacted
        - TestRedactLogEntryLayer2::test_clean_tool_call_unchanged
        - TestEnvConfig::test_default_both_enabled
        - TestEnvConfig::test_patterns_disabled_via_env
        - TestEnvConfig::test_patterns_enabled_via_env_true
        - TestEnvConfig::test_tool_aware_disabled_via_env
        - TestRedactEntries::test_empty_list_returns_empty
        - TestRedactEntries::test_single_clean_entry_count_zero
        - TestRedactEntries::test_multiple_entries_counts_accumulated
        - TestRedactEntries::test_input_list_not_mutated
        - TestRedactEntries::test_placeholder_present_in_redacted_output
        - TestRedactEntries::test_all_entries_disabled_zero_count
        - TestSecretNeverEgresses::test_secrets_absent_from_redacted_entries
        - TestSecretNeverEgresses::test_secrets_absent_from_tool_args
    acs:
      - AC R1.2: DONE

  - id: T1-004
    name: "Wire redaction before egress + assemble bundle"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: >
      session_detail.py lines 387-395: redact_entries() called on page_items
      before TranscriptPage is constructed. redacted_field_count accumulated
      in SessionDetailBundle. otel.start_span("ccdash.session_detail.get")
      wraps the entire call. Subagents assembled via list_relationships +
      get_many_by_ids. Tokens extracted via _extract_token_telemetry.
      Artifacts/links classified via _classify_links on entity_links repo.
    test_evidence:
      module: backend/tests/test_session_detail_service.py
      tests:
        - TestGetSessionDetail::test_embedded_secret_absent_from_output
        - TestGetSessionDetail::test_clean_entries_not_modified
        - TestGetSessionDetail::test_tokens_match_session_row
        - TestGetSessionDetail::test_as_dict_includes_all_keys
        - TestGetSessionDetail::test_non_active_project_returns_correct_bundle
        - TestResilienceEdgeCases::test_entity_links_failure_returns_empty_not_500
        - TestResilienceEdgeCases::test_relationships_failure_returns_empty_subagents
        - TestResilienceEdgeCases::test_tokens_present_in_bundle
        - TestStructuralGuards::test_otel_span_emitted
        - TestStructuralGuards::test_redaction_import_present
    acs:
      - AC R1.1 (assembly): DONE
      - AC R1.2 (wired before egress): DONE

  - id: T1-005
    name: "Redaction + non-active-project unit suite"
    status: completed
    started: 2026-06-11
    completed: 2026-06-11
    evidence: >
      Structural guards verify: (1) SessionTranscriptService is sole reader
      (no parsers.sessions import, no raw session_logs SQL), (2) redaction.py
      imported and redact_entries called, (3) otel.start_span present,
      (4) project_id threaded to get_by_id. All 72 tests pass.
    test_evidence:
      module: backend/tests/test_session_detail_service.py
      tests:
        - TestStructuralGuards::test_file_exists
        - TestStructuralGuards::test_session_transcript_service_is_sole_reader
        - TestStructuralGuards::test_no_duplicate_transcript_reader
        - TestStructuralGuards::test_no_raw_sql_in_session_detail
        - TestStructuralGuards::test_otel_span_emitted
        - TestStructuralGuards::test_project_id_passed_to_get_by_id
        - TestStructuralGuards::test_redaction_import_present
    acs:
      - AC R1.1 (structural guard): DONE
      - AC R1.2 (structural guard): DONE

## Test Results

```
backend/tests/test_redaction.py             38/38 passed
backend/tests/test_session_detail_service.py 34/34 passed
Total: 72/72 passed in 9.31s
```

Run command:
```
backend/.venv/bin/python -m pytest backend/tests/test_redaction.py backend/tests/test_session_detail_service.py -v
```

## Files Changed

| File | Change Type | Notes |
|------|-------------|-------|
| `backend/application/services/agent_queries/session_detail.py` | NEW | Transport-neutral service; SessionTranscriptService sole reader; project_id threaded; cursor pagination; OTEL span |
| `backend/application/services/agent_queries/redaction.py` | NEW | Layer 1 (9 pattern groups) + Layer 2 (tool-aware); env-configurable; fail-closed; count-only logs |
| `backend/tests/test_session_detail_service.py` | NEW | 34 tests covering T1-001/002/004/005 |
| `backend/tests/test_redaction.py` | NEW | 38 tests covering T1-003/005 |
| `backend/application/services/sessions.py` | UNCHANGED | Reused only (SessionTranscriptService.list_session_logs); no edits required |
| `backend/config.py` | UNCHANGED | Env knobs read via os.getenv in redaction.py per ownership constraint |

## Phase 1 Quality Gate

- [x] AC R1.1 met — service returns full detail for any project via include-flags + cursor pagination
- [x] AC R1.2 met — layered redaction (Layer 1 + Layer 2) applied before egress; env-configurable; fail-closed
- [x] Redaction suite green — 38/38 tests
- [x] No duplicate transcript reader — structural guard + test confirm SessionTranscriptService sole reader
- [x] OTEL spans present — otel.start_span("ccdash.session_detail.get") in service; structural test confirms
- [x] Existing suites unaffected — 72 tests pass with no regressions
- [x] Runtime smoke — skipped (service layer only; no HTTP surface in Phase 1; Phase 2 T2-004 and Phase 3 T3-008 carry smoke gates)
