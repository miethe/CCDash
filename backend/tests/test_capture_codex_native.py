"""Synthetic native lifecycle metadata through the actual Codex consumer."""
import ast
import importlib.util
import json
import os
import urllib.request
from pathlib import Path

import pytest

from backend.parsers.platforms.codex.parser import parse_session_file as parse_codex_session_file
from backend.parsers.platforms.codex.capture import read_session_metadata_id

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("native_capture_hook", ROOT / "scripts/hooks/ccdash_capture_session_start.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
SID = "12345678-1234-1234-1234-123456789abc"
CHILD = "87654321-4321-4321-4321-abcdefabcdef"


@pytest.fixture(autouse=True)
def forbid_personal_and_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("native capture must not read Claude settings or probe ICA")
    monkeypatch.setattr(hook, "_settings_effort_level", forbidden)
    monkeypatch.setattr(hook, "_probe_key_spend", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)


def rollout(tmp_path, sid=SID, extra=()):
    path = tmp_path / f"rollout-2026-10-02T12-00-00-{sid}.jsonl"
    entries = [{"type": "session_meta", "timestamp": "2026-10-02T12:00:00Z", "payload": {"id": sid, "cwd": str(tmp_path), "cli_version": "0.159.2"}}, *extra]
    path.write_text("\n".join(json.dumps(e) for e in entries))
    return path


def payload(path, event="SessionStart", **metadata):
    return {"session_id": SID, "transcript_path": str(path), "cwd": str(path.parent), "platformType": "Codex", "hook_event_name": event, **metadata}


def capture(path, **metadata):
    observed_labels = {"launcher":"codex", "launcherSource":"codex_payload_launcher", "profile":"native", "profileSource":"codex_payload_profile"}
    out = hook.write_capture_sidecar(payload(path, **observed_labels, **metadata), {"CCDASH_LAUNCHER": "codex", "CCDASH_LAUNCH_PROFILE": "native", "CCDASH_LAUNCH_MODEL": "stale-claude", "CCDASH_LAUNCH_EFFORT": "stale-high", "CCDASH_LAUNCH_ICA_KEY": "CC-test"})
    assert out == path.with_name(f"{SID}.capture.json")
    return out, json.loads(out.read_text())


@pytest.mark.parametrize("effort_meta,source", [({"effort": "medium"}, "codex_payload_effort"), ({"collaboration_mode": {"settings": {"reasoning_effort": "high"}}}, "codex_collaboration_mode")])
def test_observed_native_writer_parser_join(tmp_path, effort_meta, source):
    path = rollout(tmp_path)
    _, data = capture(path, model="gpt-6-luna", **effort_meta)
    assert data["effortTierSource"] == source
    assert data["modelVariant"] == "gpt-6-luna"
    assert data["modelVariantSource"] == "codex_payload_model"
    assert all(data[k] is None for k in ("icaKey", "icaSpendStart", "icaSpendEnd"))
    session = parse_codex_session_file(path)
    assert session.id == f"S-{path.stem}"  # no DB ID migration
    assert session.sessionForensics["rawSessionId"] == SID
    assert session.sessionForensics["nativeSessionIdSource"] == "codex.session_meta.id"
    assert session.profile == "native" and session.launcher == "codex"
    assert session.modelVariant == "gpt-6-luna"
    assert session.effortTier == data["effortTier"]
    assert session.effortTierSource == source


def test_unknown_native_metadata_is_null_despite_stale_env(tmp_path):
    path = rollout(tmp_path)
    _, data = capture(path)
    assert all(data[k] is None for k in ("effortTier", "effortTierSource", "modelVariant", "modelVariantSource"))
    session = parse_codex_session_file(path)
    assert session.modelVariant is None and session.effortTier is None
    _, named = capture(path, model="gpt-6-high")
    assert named["effortTier"] is None and named["effortTierSource"] is None


def test_native_end_preserves_start_and_last(tmp_path):
    path = rollout(tmp_path)
    sidecar, before = capture(path, model="gpt-6-luna", effort="medium")
    hook.update_effort_tier_last(payload(path, "UserPromptSubmit", effort="high"), {})
    hook.write_capture_sidecar(payload(path, "SessionEnd", model="other", effort="low"), {})
    after = json.loads(sidecar.read_text())
    for key in ("launcher", "profile", "modelVariant", "modelVariantSource", "effortTier", "effortTierSource", "capturedAt"):
        assert after[key] == before[key]
    assert after["effortTierLast"] == "high"


def test_end_does_not_backfill_unknown_start(tmp_path):
    path = rollout(tmp_path)
    sidecar, _ = capture(path)
    hook.write_capture_sidecar(payload(path, "SessionEnd", model="later", effort="high"), {})
    after = json.loads(sidecar.read_text())
    assert after["modelVariant"] is None and after["effortTier"] is None


@pytest.mark.parametrize("mutation", [{"sessionId": CHILD}, {"sessionId": None}, {"platformType": "Claude Code"}, {"schemaVersion": 999}])
def test_native_consumer_withholds_wrong_identity_platform_schema(tmp_path, mutation):
    path = rollout(tmp_path)
    sidecar, data = capture(path, model="gpt-6-luna", effort="medium")
    data.update(mutation); sidecar.write_text(json.dumps(data))
    session = parse_codex_session_file(path)
    assert session.modelVariant is None and session.profile is None
    assert session.effortTier is None and not session.sessionForensics["captureSidecarJoined"]


def test_harness_observations_take_precedence_over_capture(tmp_path):
    path = rollout(tmp_path, extra=[{"type":"turn_context", "payload":{"model":"realized", "effort":"xhigh"}}])
    capture(path, model="start", effort="medium")
    session = parse_codex_session_file(path)
    assert session.model == "realized" and session.modelVariant == "start"
    assert session.effortTier == "xhigh"
    assert session.sessionForensics["captureEffortTier"] == "medium"


def _freshness_function():
    # Exact production consumer function, loaded without unrelated runtime setup.
    src = ROOT / "backend/db/sync_engine.py"
    tree = ast.parse(src.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_session_input_mtime")
    ns = {"Path": Path}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(src), "exec"), ns)
    return ns["_session_input_mtime"]


def test_late_uuid_sidecar_invalidates_actual_freshness_cache(tmp_path):
    path = rollout(tmp_path)
    os.utime(path, (100, 100))
    freshness = _freshness_function()
    before = freshness(path)
    assert parse_codex_session_file(path).profile is None
    sidecar, _ = capture(path, effort="medium")
    os.utime(sidecar, (200, 200))
    assert freshness(path) == 200 > before
    assert parse_codex_session_file(path).profile == "native"
    assert freshness(path) == 200  # storing this key converges


def test_metadata_header_is_bounded_and_ambiguous_identity_withheld(tmp_path):
    path = rollout(tmp_path, extra=[{"type":"session_meta", "payload":{"id":CHILD}}])
    capture(path, effort="medium")
    assert read_session_metadata_id(path) == ""
    assert parse_codex_session_file(path).profile is None
    path.write_bytes(b"x" * (64 * 1024 + 1))
    assert read_session_metadata_id(path) == ""


@pytest.mark.parametrize("alias", ["collaborationspawn_agent", "collaboration.spawn_agent", "spawn_agent"])
@pytest.mark.parametrize("child_exists", [True, False])
def test_native_spawn_arguments_and_confirmed_child_correlation(tmp_path, alias, child_exists):
    if child_exists:
        child = rollout(tmp_path, sid=CHILD)
    path = rollout(tmp_path, extra=[
        {"type":"response_item", "timestamp":"2026-10-02T12:00:01Z", "payload":{"type":"function_call", "name":alias, "call_id":"call-native", "arguments":json.dumps({"message":"READY only", "task_name":"ready_probe", "model":"gpt-6-luna", "reasoning_effort":"medium"})}},
        {"type":"response_item", "timestamp":"2026-10-02T12:00:02Z", "payload":{"type":"function_call_output", "call_id":"call-native", "output":json.dumps({"agent_id":CHILD})}},
    ])
    session = parse_codex_session_file(path)
    tool = next(log for log in session.logs if log.type == "tool")
    assert tool.metadata["taskName"] == "ready_probe"
    assert tool.metadata["taskPromptLength"] == len("READY only")
    assert tool.metadata["taskRequestedReasoningEffort"] == "medium"
    assert tool.metadata["taskModelProvenance"] == "request_intent"
    assert tool.metadata["nativeChildSessionId"] == CHILD
    assert "taskRunInBackground" not in tool.metadata
    assert tool.linkedSessionId == (f"S-{child.stem}" if child_exists else None)
    starts = [log for log in session.logs if log.type == "subagent_start"]
    assert len(starts) == 1
    assert starts[0].linkedSessionId == tool.linkedSessionId
    assert tool.metadata["nativeChildCorrelation"] == ("same_source_session_meta" if child_exists else "unresolved")


def test_native_filename_candidate_is_not_identity_evidence(tmp_path):
    fake = rollout(tmp_path, sid=CHILD)
    fake.write_text(json.dumps({"type":"session_meta","payload":{"id":"different-id"}}))
    from backend.parsers.platforms.codex.capture import resolve_child_session
    assert resolve_child_session(fake.with_name("parent.jsonl"), CHILD) is None


@pytest.mark.parametrize("platform", ["Other", "", None])
def test_unknown_explicit_platform_has_zero_sidecar_settings_transport_calls(tmp_path, platform, monkeypatch):
    path = rollout(tmp_path)
    sidecar, _ = capture(path, model="start", effort="medium")
    before = sidecar.read_bytes()
    p = payload(path, model="unobserved", effort="high"); p["platformType"] = platform
    calls = []
    def forbidden(*args, **kwargs):
        calls.append("side_effect")
        raise AssertionError("unknown platform side effect")
    with monkeypatch.context() as scoped:
        for name in ("_resolve_sidecar_path", "_load_existing_sidecar", "_settings_effort_level", "_probe_key_spend"):
            scoped.setattr(hook, name, forbidden)
        scoped.setattr(hook.Path, "write_text", forbidden)
        scoped.setattr(hook.Path, "mkdir", forbidden)
        assert hook.write_capture_sidecar(p, {"CCDASH_LAUNCH_ICA_KEY":"stale"}, fallback_base=tmp_path) is None
        assert hook.update_effort_tier_last(p, {}, fallback_base=tmp_path) is None
        assert calls == []
    assert sidecar.read_bytes() == before


def test_native_end_without_valid_start_does_not_originate_or_convert(tmp_path):
    path = rollout(tmp_path)
    p = payload(path, "SessionEnd", model="end-model", effort="high")
    assert hook.write_capture_sidecar(p, {}) is None
    sidecar = path.with_name(f"{SID}.capture.json")
    stale = {"schemaVersion":4,"sessionId":SID,"effortTier":"high","effortTierSource":"claude_settings","modelVariant":"claude"}
    sidecar.write_text(json.dumps(stale))
    assert hook.write_capture_sidecar(p, {}) is None
    assert json.loads(sidecar.read_text()) == stale
    assert hook.update_effort_tier_last(payload(path, "UserPromptSubmit", effort="low"), {}) is None


def test_stale_claude_sidecar_cannot_supply_native_effort_or_model(tmp_path):
    path = rollout(tmp_path)
    sidecar, data = capture(path, model="gpt-6-luna", effort="medium")
    data["effortTierSource"] = "claude_settings"
    data["modelVariantSource"] = "launch_env"
    sidecar.write_text(json.dumps(data))
    session = parse_codex_session_file(path)
    assert session.effortTier is None and session.modelVariant is None


@pytest.mark.parametrize("sid", ["..", "../escape", "bad\\path"])
def test_native_writer_rejects_noncomponent_identity(tmp_path, sid):
    p = payload(rollout(tmp_path)); p["session_id"] = sid
    assert hook.write_capture_sidecar(p, {}) is None


def test_native_uuid_sidecar_watcher_routes_to_confirmed_rollout(tmp_path):
    from watchfiles import Change
    from backend.db.file_watcher import FileWatcher
    path = rollout(tmp_path)
    sidecar, _ = capture(path, effort="medium")
    watcher = FileWatcher()
    changes = {(Change.modified, str(sidecar))}
    assert watcher._classify_changes(changes, sessions_dir=tmp_path) == [("modified", path)]
    assert watcher._classify_changes(changes, sessions_dir=tmp_path / "unrelated") == []
    assert watcher._classify_changes({(Change.deleted, str(sidecar))}, sessions_dir=tmp_path) == []
    path.write_text(json.dumps({"type":"session_meta","payload":{"id":CHILD}}))
    assert watcher._classify_changes(changes, sessions_dir=tmp_path) == []


def test_native_same_source_duplicate_and_candidate_limit_withhold(tmp_path):
    from backend.parsers.platforms.codex.capture import resolve_session_path
    path = rollout(tmp_path)
    assert resolve_session_path(tmp_path, SID) == path
    duplicate = tmp_path / f"duplicate-{SID}.jsonl"
    duplicate.write_text(path.read_text())
    assert resolve_session_path(tmp_path, SID) is None
    for i in range(17):
        (tmp_path / f"candidate{i}-{SID}.jsonl").write_text("{}")
    assert resolve_session_path(tmp_path, SID) is None


def test_native_capability_preflight_is_static_and_stdout_contract(tmp_path, monkeypatch):
    import subprocess
    import sys
    monkeypatch.setattr(sys, "argv", [str(ROOT / "scripts/hooks/ccdash_capture_session_start.py"), "--capabilities"])
    class NoRead:
        def read(self):
            raise AssertionError("capability preflight read stdin")
    monkeypatch.setattr(hook.sys, "stdin", NoRead())
    from contextlib import redirect_stdout
    from io import StringIO
    output = StringIO()
    with redirect_stdout(output):
        hook._main()
    document = json.loads(output.getvalue())
    assert document["capability"] == "ccdash.capture.native"
    assert document["contractVersion"] == 1
    assert document["platformType"] == "Codex" and document["schemaVersion"] == 4
    assert document["networkCalls"] == 0 and document["readsTranscript"] is False
    assert document["requiresCallerDeadlineSeconds"] == 1.8
    assert document["sessionEnd"] == "preserve_existing_start_or_skip"
    # Real standalone CLI must produce the same known JSON, no stdin or config.
    process = subprocess.run([sys.executable, str(ROOT / "scripts/hooks/ccdash_capture_session_start.py"), "--capabilities"], cwd=tmp_path, env={"HOME":str(tmp_path)}, capture_output=True, text=True, timeout=1.8)
    assert process.returncode == 0 and json.loads(process.stdout) == document
    assert list(tmp_path.iterdir()) == []


def test_native_missing_source_path_is_unavailable_without_fallback_store(tmp_path):
    p = {"session_id":SID,"platformType":"Codex","model":"gpt-6-luna","effort":"medium"}
    assert hook.write_capture_sidecar(p, {}, fallback_base=tmp_path) is None
    assert hook.update_effort_tier_last(p, {}, fallback_base=tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_child_symlink_outside_source_is_not_followed(tmp_path):
    from backend.parsers.platforms.codex.capture import resolve_session_path
    source = tmp_path / "source"; source.mkdir()
    other = tmp_path / "other"; other.mkdir()
    foreign = rollout(other, sid=CHILD)
    (source / foreign.name).symlink_to(foreign)
    assert resolve_session_path(source, CHILD) is None


@pytest.mark.parametrize("metadata", [{}, {"launcher":"ica-claude.sh","profile":"ica-delegate"}, {"launcher":"codex","launcherSource":"launch_env","profile":"native","profileSource":"claude_settings"}])
def test_stale_launcher_profile_env_cannot_label_native(tmp_path, metadata):
    path = rollout(tmp_path)
    out = hook.write_capture_sidecar(payload(path, **metadata), {"CCDASH_LAUNCHER":"ica-claude.sh","CCDASH_LAUNCH_PROFILE":"ica-delegate"})
    data = json.loads(out.read_text())
    assert data["launcher"] is None and data["profile"] is None
    assert data["launcherSource"] is None and data["profileSource"] is None
    session = parse_codex_session_file(path)
    assert session.launcher is None and session.profile is None


def test_native_consumer_withholds_labels_without_native_source(tmp_path):
    path = rollout(tmp_path)
    sidecar, data = capture(path)
    data["launcherSource"] = "launch_env"; data["profileSource"] = None
    sidecar.write_text(json.dumps(data))
    session = parse_codex_session_file(path)
    assert session.launcher is None and session.profile is None
