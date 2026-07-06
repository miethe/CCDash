"""Derived AOS correlation helpers.

This module intentionally treats AOS correlation as an additive read/ingest
projection. It extracts IDs and aliases only; prompt and response bodies from
sidecar events are never retained in returned payloads.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

AOS_KINDS: tuple[str, ...] = (
    "turn",
    "session",
    "run",
    "feature",
    "artifact",
    "app",
    "service",
    "trace",
)

UUID_PATTERN = (
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
AOS_URN_RE = re.compile(
    rf"\burn:aos:(?P<kind>{'|'.join(AOS_KINDS)}):(?P<uuid>{UUID_PATTERN})\b",
    re.IGNORECASE,
)
AOS_FOOTER_RE = re.compile(
    rf"(?:^|\n)\s*AOS-ID:\s*(?P<urn>urn:aos:turn:{UUID_PATTERN})\s*(?:\n|$)",
    re.IGNORECASE,
)
UUID_RE = re.compile(rf"\b(?P<uuid>{UUID_PATTERN})\b")

_PRIVATE_BODY_KEYS = {
    "body",
    "completion",
    "content",
    "input",
    "message",
    "messages",
    "output",
    "prompt",
    "prompts",
    "request",
    "response",
    "responses",
    "text",
    "transcript",
}

_SESSION_ALIAS_KEY_MARKERS = (
    "ccdash_session_id",
    "claude_session_id",
    "codex_session_id",
    "codex_thread_id",
    "harness_session_id",
    "ica_session_id",
    "session_id",
    "thread_id",
)


def normalize_aos_urn(kind: str, uuid_value: str) -> str:
    return f"urn:aos:{kind.lower()}:{uuid_value.lower()}"


def parse_aos_reference(value: Any) -> dict[str, str] | None:
    """Return ``{kind, uuid, urn}`` for an AOS URN or bare UUID string."""
    raw = str(value or "").strip()
    if not raw:
        return None
    urn_match = AOS_URN_RE.search(raw)
    if urn_match:
        kind = urn_match.group("kind").lower()
        uuid_value = urn_match.group("uuid").lower()
        return {"kind": kind, "uuid": uuid_value, "urn": normalize_aos_urn(kind, uuid_value)}
    uuid_match = UUID_RE.search(raw)
    if uuid_match:
        return {"kind": "", "uuid": uuid_match.group("uuid").lower(), "urn": ""}
    return None


def extract_aos_footers_from_logs(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract visible final-turn AOS footers from log content."""
    footers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, log in enumerate(logs):
        if not isinstance(log, dict):
            continue
        content = str(log.get("content") or "")
        for match in AOS_FOOTER_RE.finditer(content):
            parsed = parse_aos_reference(match.group("urn"))
            if not parsed or parsed["urn"] in seen:
                continue
            seen.add(parsed["urn"])
            footers.append(
                {
                    "kind": "turn",
                    "uuid": parsed["uuid"],
                    "urn": parsed["urn"],
                    "source": "transcript_footer",
                    "sourceLogId": str(log.get("id") or log.get("source_log_id") or ""),
                    "messageIndex": int(log.get("message_index") or log.get("messageIndex") or index),
                    "timestamp": str(log.get("timestamp") or log.get("event_timestamp") or ""),
                }
            )
    return footers


def extract_aos_urns_from_logs(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract all supported AOS URNs from transcript rows.

    Only the URN, kind, UUID, and row provenance are returned. Transcript body
    content stays in the canonical transcript store.
    """
    aliases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, log in enumerate(logs):
        if not isinstance(log, dict):
            continue
        content = str(log.get("content") or "")
        for match in AOS_URN_RE.finditer(content):
            parsed = parse_aos_reference(match.group(0))
            if not parsed or not parsed["kind"] or parsed["urn"] in seen:
                continue
            seen.add(parsed["urn"])
            aliases.append(
                {
                    "kind": parsed["kind"],
                    "uuid": parsed["uuid"],
                    "urn": parsed["urn"],
                    "source": "transcript_urn",
                    "sourceLogId": str(log.get("id") or log.get("source_log_id") or ""),
                    "messageIndex": int(log.get("message_index") or log.get("messageIndex") or index),
                    "timestamp": str(log.get("timestamp") or log.get("event_timestamp") or ""),
                }
            )
    return aliases


def aos_sidecar_path(aos_id_home: str | Path | None = None) -> Path:
    home = str(aos_id_home or os.environ.get("AOS_ID_HOME") or "").strip()
    if home:
        return Path(home).expanduser() / "events.jsonl"
    return Path.home() / ".aos" / "correlation" / "events.jsonl"


def load_aos_sidecar_events(aos_id_home: str | Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read sanitized AOS sidecar events.

    Missing and malformed files degrade to diagnostics. The returned events
    contain IDs, aliases, links, timestamps, and native pointers only.
    """
    path = aos_sidecar_path(aos_id_home)
    diagnostics: list[dict[str, Any]] = []
    if not path.exists():
        diagnostics.append({"code": "sidecar_missing", "severity": "info"})
        return [], diagnostics

    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        diagnostics.append(
            {
                "code": "sidecar_unreadable",
                "severity": "warning",
                "message": str(exc),
            }
        )
        return [], diagnostics

    seen_signatures: dict[str, int] = {}
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            diagnostics.append(
                {
                    "code": "malformed_sidecar_line",
                    "severity": "warning",
                    "line": line_no,
                    "message": exc.msg,
                }
            )
            continue
        if not isinstance(raw, dict):
            diagnostics.append(
                {
                    "code": "malformed_sidecar_line",
                    "severity": "warning",
                    "line": line_no,
                    "message": "event is not a JSON object",
                }
            )
            continue
        event = _sanitize_sidecar_event(raw, line_no)
        if not _event_urns(event):
            diagnostics.append(
                {
                    "code": "unresolved_sidecar_row",
                    "severity": "warning",
                    "line": line_no,
                    "message": "event has no supported AOS IDs or links",
                }
            )
            continue
        signature = _event_signature(event)
        if signature in seen_signatures:
            diagnostics.append(
                {
                    "code": "duplicate_sidecar_row",
                    "severity": "warning",
                    "line": line_no,
                    "firstLine": seen_signatures[signature],
                    "message": "duplicate AOS sidecar event ignored",
                }
            )
            continue
        seen_signatures[signature] = line_no
        events.append(event)
    return events, diagnostics


def derive_aos_correlation(
    *,
    session_id: str = "",
    project_id: str = "",
    session_row: dict[str, Any] | None = None,
    logs: list[dict[str, Any]] | None = None,
    query: str | None = None,
    aos_id_home: str | Path | None = None,
) -> dict[str, Any]:
    """Build an additive AOS correlation payload for a session or UUID query."""
    safe_logs = logs if isinstance(logs, list) else []
    footers = extract_aos_footers_from_logs(safe_logs)
    transcript_aliases = extract_aos_urns_from_logs(safe_logs)
    sidecar_events, diagnostics = load_aos_sidecar_events(aos_id_home)
    index = _build_sidecar_index(sidecar_events)
    query_ref = parse_aos_reference(query)

    seed_urns: set[str] = {footer["urn"] for footer in footers}
    seed_urns.update(alias["urn"] for alias in transcript_aliases)
    seed_urns.update(_event_urns_for_session(index["events"], session_id))
    if query_ref:
        if query_ref["urn"]:
            seed_urns.add(query_ref["urn"])
        else:
            seed_urns.update(index["urns_by_uuid"].get(query_ref["uuid"], set()))

    related_urns = _expand_related_urns(index, seed_urns)
    related_events = _events_for_urns(index["events"], related_urns)

    ids_by_kind = _collect_ids_by_kind(related_urns)
    for alias in transcript_aliases:
        ids_by_kind[alias["kind"]].append(alias["uuid"])
    ids_by_kind = {kind: sorted(set(values)) for kind, values in ids_by_kind.items() if values}

    aliases = _collect_named_values(related_events, "aliases")
    native = _collect_named_values(related_events, "native")
    has_resolution = bool(footers or transcript_aliases or related_events)
    if not has_resolution and not query_ref:
        return {}
    session_ids = _collect_session_ids(
        related_events,
        session_id=session_id if has_resolution else "",
    )

    leaf_turn_id = ""
    if footers:
        leaf_turn_id = footers[-1]["urn"]
    elif ids_by_kind.get("turn"):
        leaf_turn_id = normalize_aos_urn("turn", ids_by_kind["turn"][-1])
    turn_uuid = parse_aos_reference(leaf_turn_id)["uuid"] if leaf_turn_id else ""

    sources: list[str] = []
    if footers:
        sources.append("transcript_footer")
    if transcript_aliases:
        sources.append("transcript_urn")
    if related_events:
        sources.append("sidecar_events")

    status = "resolved" if has_resolution else "unresolved"
    warning_diagnostics = [d for d in diagnostics if d.get("severity") == "warning"]
    if has_resolution and warning_diagnostics:
        status = "partial"
    if query_ref and not has_resolution:
        status = "unresolved"

    result: dict[str, Any] = {
        "version": "v1",
        "status": status,
        "projectId": project_id,
        "sessionId": session_id,
        "footer": f"AOS-ID: {leaf_turn_id}" if leaf_turn_id else "",
        "turnUrn": leaf_turn_id,
        "turnUuid": turn_uuid,
        "leafTurnId": leaf_turn_id,
        "footerIds": footers,
        "transcriptAliases": transcript_aliases,
        "ids": ids_by_kind,
        "urns": {
            kind: [normalize_aos_urn(kind, uuid_value) for uuid_value in values]
            for kind, values in ids_by_kind.items()
        },
        "sessionIds": sorted(set(session_ids)),
        "aliases": aliases,
        "native": native,
        "links": _collect_links(related_events),
        "sources": sources,
        "diagnostics": diagnostics,
    }
    for field_name, kind in (
        ("parentRun", "run"),
        ("parentFeature", "feature"),
        ("parentArtifact", "artifact"),
    ):
        entity = _parent_entity(kind, ids_by_kind, aliases, native)
        if entity:
            result[field_name] = entity
    if query_ref:
        result["query"] = query_ref
    if session_row:
        existing = _safe_dict(session_row.get("aosCorrelation")) or _session_forensics_correlation(session_row)
        if existing:
            result = _merge_existing_correlation(result, existing)
    return result


def resolve_aos_query(query: str, *, aos_id_home: str | Path | None = None) -> dict[str, Any]:
    """Resolve an AOS UUID/URN from sidecar events without reading transcripts."""
    return derive_aos_correlation(query=query, aos_id_home=aos_id_home)


def is_aos_query(value: str | None) -> bool:
    return parse_aos_reference(value) is not None


def aos_query_terms(value: str | None) -> list[str]:
    parsed = parse_aos_reference(value)
    if not parsed:
        return []
    terms: list[str] = [parsed["uuid"]]
    if parsed["urn"]:
        terms.append(parsed["urn"])
    terms.extend(normalize_aos_urn(kind, parsed["uuid"]) for kind in AOS_KINDS)
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            deduped.append(term)
    return deduped


def _sanitize_sidecar_event(raw: dict[str, Any], line_no: int) -> dict[str, Any]:
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in AOS_KINDS:
        parsed_urn = parse_aos_reference(raw.get("urn"))
        kind = parsed_urn["kind"] if parsed_urn and parsed_urn["kind"] else ""
    uuid_value = str(raw.get("uuid") or "").strip().lower()
    parsed_uuid = parse_aos_reference(uuid_value)
    if parsed_uuid and not parsed_uuid["kind"]:
        uuid_value = parsed_uuid["uuid"]

    urn = str(raw.get("urn") or "").strip()
    parsed_urn = parse_aos_reference(urn)
    if parsed_urn and parsed_urn["kind"]:
        kind = parsed_urn["kind"]
        uuid_value = parsed_urn["uuid"]
        urn = parsed_urn["urn"]
    elif kind and uuid_value:
        urn = normalize_aos_urn(kind, uuid_value)
    else:
        urn = ""

    ids: dict[str, set[str]] = defaultdict(set)
    if kind and uuid_value:
        ids[kind].add(uuid_value)
    for candidate_kind in AOS_KINDS:
        raw_uuid = raw.get(f"aos_{candidate_kind}_uuid")
        parsed = parse_aos_reference(raw_uuid)
        if parsed:
            ids[candidate_kind].add(parsed["uuid"])
        raw_urn = raw.get(f"aos_{candidate_kind}_urn")
        parsed_urn_value = parse_aos_reference(raw_urn)
        if parsed_urn_value and parsed_urn_value["kind"]:
            ids[parsed_urn_value["kind"]].add(parsed_urn_value["uuid"])

    source = _normalize_optional_urn(raw.get("source"))
    target = _normalize_optional_urn(raw.get("target"))
    for related_urn in (source, target):
        parsed = parse_aos_reference(related_urn)
        if parsed and parsed["kind"]:
            ids[parsed["kind"]].add(parsed["uuid"])

    return {
        "line": line_no,
        "schemaVersion": _safe_scalar(raw.get("schema_version") or raw.get("schemaVersion")),
        "eventType": _safe_scalar(raw.get("event_type") or raw.get("eventType")),
        "kind": kind,
        "uuid": uuid_value,
        "urn": urn,
        "createdAt": _safe_scalar(raw.get("created_at") or raw.get("createdAt")),
        "relation": _safe_scalar(raw.get("relation")),
        "source": source,
        "target": target,
        "aliases": _safe_mapping(raw.get("aliases")),
        "native": _safe_mapping(raw.get("native")),
        "ids": {k: sorted(v) for k, v in ids.items() if v},
    }


def _build_sidecar_index(events: list[dict[str, Any]]) -> dict[str, Any]:
    events_by_urn: dict[str, list[dict[str, Any]]] = defaultdict(list)
    links_by_urn: dict[str, set[str]] = defaultdict(set)
    urns_by_uuid: dict[str, set[str]] = defaultdict(set)
    for event in events:
        event_urns = _event_urns(event)
        for urn in event_urns:
            events_by_urn[urn].append(event)
            parsed = parse_aos_reference(urn)
            if parsed:
                urns_by_uuid[parsed["uuid"]].add(urn)
        source = str(event.get("source") or "")
        target = str(event.get("target") or "")
        if source and target:
            links_by_urn[source].add(target)
            links_by_urn[target].add(source)
        if len(event_urns) > 1:
            for urn in event_urns:
                links_by_urn[urn].update(other for other in event_urns if other != urn)
    return {
        "events": events,
        "events_by_urn": events_by_urn,
        "links_by_urn": links_by_urn,
        "urns_by_uuid": urns_by_uuid,
    }


def _event_signature(event: dict[str, Any]) -> str:
    payload = {
        "urns": sorted(_event_urns(event)),
        "eventType": event.get("eventType") or "",
        "relation": event.get("relation") or "",
        "source": event.get("source") or "",
        "target": event.get("target") or "",
        "aliases": event.get("aliases") or {},
        "native": event.get("native") or {},
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _expand_related_urns(index: dict[str, Any], seed_urns: set[str]) -> set[str]:
    related: set[str] = set()
    queue: deque[str] = deque()
    for urn in seed_urns:
        if urn:
            related.add(urn)
            queue.append(urn)
    while queue:
        urn = queue.popleft()
        event_urns: set[str] = set()
        for event in index["events_by_urn"].get(urn, []):
            event_urns.update(_event_urns(event))
        event_urns.update(index["links_by_urn"].get(urn, set()))
        for candidate in event_urns:
            if candidate and candidate not in related:
                related.add(candidate)
                queue.append(candidate)
    return related


def _events_for_urns(events: list[dict[str, Any]], urns: set[str]) -> list[dict[str, Any]]:
    if not urns:
        return []
    return [event for event in events if _event_urns(event) & urns]


def _event_urns(event: dict[str, Any]) -> set[str]:
    urns: set[str] = set()
    if str(event.get("urn") or ""):
        urns.add(str(event["urn"]))
    for key in ("source", "target"):
        if str(event.get(key) or ""):
            urns.add(str(event[key]))
    ids = event.get("ids")
    if isinstance(ids, dict):
        for kind, values in ids.items():
            if kind not in AOS_KINDS:
                continue
            if isinstance(values, list):
                for value in values:
                    parsed = parse_aos_reference(str(value))
                    if parsed:
                        urns.add(normalize_aos_urn(kind, parsed["uuid"]))
    return urns


def _event_urns_for_session(events: list[dict[str, Any]], session_id: str) -> set[str]:
    if not str(session_id or "").strip():
        return set()
    target_session_id = str(session_id).strip()
    return {
        urn
        for event in events
        if target_session_id in _event_session_ids(event)
        for urn in _event_urns(event)
    }


def _collect_ids_by_kind(urns: set[str]) -> dict[str, list[str]]:
    ids: dict[str, list[str]] = defaultdict(list)
    for urn in urns:
        parsed = parse_aos_reference(urn)
        if parsed and parsed["kind"]:
            ids[parsed["kind"]].append(parsed["uuid"])
    return ids


def _collect_named_values(events: list[dict[str, Any]], field: str) -> dict[str, list[str]]:
    collected: dict[str, set[str]] = defaultdict(set)
    for event in events:
        mapping = event.get(field)
        if not isinstance(mapping, dict):
            continue
        for key, value in mapping.items():
            if isinstance(value, list):
                values = [str(v).strip() for v in value if str(v).strip()]
            else:
                values = [str(value).strip()] if str(value or "").strip() else []
            for item in values:
                collected[str(key)].add(item)
    return {key: sorted(values) for key, values in sorted(collected.items())}


def _collect_session_ids(events: list[dict[str, Any]], *, session_id: str = "") -> list[str]:
    values: set[str] = set()
    if session_id:
        values.add(session_id)
    for event in events:
        values.update(_event_session_ids(event))
    return sorted(values)


def _event_session_ids(event: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for mapping_key in ("aliases", "native"):
        mapping = event.get(mapping_key)
        if not isinstance(mapping, dict):
            continue
        for key, value in mapping.items():
            key_l = str(key or "").strip().lower()
            if not any(marker in key_l for marker in _SESSION_ALIAS_KEY_MARKERS):
                continue
            if isinstance(value, list):
                for item in value:
                    raw = str(item or "").strip()
                    if raw:
                        values.add(raw)
            else:
                raw = str(value or "").strip()
                if raw:
                    values.add(raw)
    return values


def _collect_links(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for event in events:
        source = str(event.get("source") or "")
        target = str(event.get("target") or "")
        if not source or not target:
            continue
        relation = str(event.get("relation") or "related")
        key = (source, target, relation)
        if key in seen:
            continue
        seen.add(key)
        links.append({"source": source, "target": target, "relation": relation})
    return links


def _parent_entity(
    kind: str,
    ids_by_kind: dict[str, list[str]],
    aliases: dict[str, list[str]],
    native: dict[str, list[str]],
) -> dict[str, Any] | None:
    values = ids_by_kind.get(kind) or []
    if not values:
        return None
    uuid_value = values[0]
    return {
        "kind": kind,
        "uuid": uuid_value,
        "urn": normalize_aos_urn(kind, uuid_value),
        "aliases": aliases,
        "native": native,
    }


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, item in value.items():
        key_s = str(key or "").strip()
        if not key_s or _is_private_body_key(key_s):
            continue
        if isinstance(item, list):
            safe_items = [_safe_scalar(v) for v in item]
            safe[key_s] = [v for v in safe_items if v]
        else:
            scalar = _safe_scalar(item)
            if scalar:
                safe[key_s] = scalar
    return safe


def _safe_scalar(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip()
    return ""


def _is_private_body_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _PRIVATE_BODY_KEYS or any(part in _PRIVATE_BODY_KEYS for part in normalized.split("_"))


def _normalize_optional_urn(value: Any) -> str:
    parsed = parse_aos_reference(value)
    return parsed["urn"] if parsed and parsed["kind"] else ""


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _session_forensics_correlation(session_row: dict[str, Any]) -> dict[str, Any]:
    raw = session_row.get("session_forensics_json") or session_row.get("sessionForensics")
    payload: dict[str, Any] = {}
    if isinstance(raw, str) and raw.strip():
        try:
            decoded = json.loads(raw)
            payload = decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            payload = {}
    elif isinstance(raw, dict):
        payload = raw
    existing = payload.get("aosCorrelation")
    return existing if isinstance(existing, dict) else {}


def _merge_existing_correlation(current: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key in ("ids", "urns", "aliases", "native"):
        merged[key] = _merge_map_lists(_safe_dict(current.get(key)), _safe_dict(existing.get(key)))
    for key in ("sessionIds", "sources", "links", "footerIds", "transcriptAliases", "diagnostics"):
        merged[key] = _dedupe_list([*existing.get(key, []), *current.get(key, [])])
    if not merged.get("leafTurnId") and existing.get("leafTurnId"):
        merged["leafTurnId"] = existing["leafTurnId"]
    return merged


def _merge_map_lists(left: dict[str, Any], right: dict[str, Any]) -> dict[str, list[str]]:
    merged: dict[str, set[str]] = defaultdict(set)
    for source in (left, right):
        for key, values in source.items():
            if isinstance(values, list):
                merged[str(key)].update(str(v) for v in values if str(v).strip())
            elif str(values or "").strip():
                merged[str(key)].add(str(values))
    return {key: sorted(values) for key, values in sorted(merged.items())}


def _dedupe_list(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        marker = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result
