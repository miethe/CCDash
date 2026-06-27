#!/usr/bin/env python3
"""IntentTree / LAN agent example client for CCDash /api/v1.

Demonstrates:
  1. Capability discovery — checks which capabilities the server advertises.
  2. Session list        — paginates the first page of sessions.
  3. Session search      — text search across transcripts.
  4. Session detail      — pulls full detail for one session in a named project.

Usage:
    # Dry run (no live server needed — uses mocked responses):
    python examples/intenttree-client/client.py --dry

    # Live run against a running CCDash instance:
    python examples/intenttree-client/client.py \
        --base-url http://localhost:8000 \
        --project-id <your-project-id>

    # With a bearer token (when CCDASH_API_TOKEN is set on the server):
    python examples/intenttree-client/client.py \
        --base-url http://192.168.1.50:8000 \
        --project-id <your-project-id> \
        --token my-secret-token

Run ``python examples/intenttree-client/client.py --help`` for all options.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from typing import Any


# ---------------------------------------------------------------------------
# Low-level HTTP helpers (stdlib-only, no requests dependency)
# ---------------------------------------------------------------------------


def _http_get(url: str, *, token: str = "", timeout: int = 30) -> dict[str, Any]:
    """Perform a GET request and return the JSON body as a dict.

    Raises ``SystemExit`` on HTTP errors so that the script fails clearly
    rather than with a traceback.
    """
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"[ERROR] HTTP {exc.code} {exc.reason} → {url}", file=sys.stderr)
        print(f"        {body[:400]}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"[ERROR] Cannot reach {url}: {exc.reason}", file=sys.stderr)
        print("        Is CCDash running? Try --dry for an offline smoke-test.", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Dry-run mock responses
# ---------------------------------------------------------------------------

_DRY_CAPABILITY = {
    "status": "ok",
    "data": {
        "api_version": "1",
        "capabilities": ["sessions:cross-project", "sessions:detail"],
        "instance_id": "dry-run-instance",
        "server_time": "2026-01-01T00:00:00Z",
    },
    "meta": {"generated_at": "2026-01-01T00:00:00Z", "instance_id": "dry-run-instance", "request_id": "dry"},
}

_DRY_SESSIONS = {
    "status": "ok",
    "data": [],  # empty list — valid per contract (database may be empty)
    "meta": {"total": 0, "limit": 5, "offset": 0, "has_more": False, "generated_at": "2026-01-01T00:00:00Z"},
}

_DRY_SEARCH = {
    "status": "ok",
    "data": {"items": [], "total": 0, "query": "intenttree"},
    "meta": {"generated_at": "2026-01-01T00:00:00Z"},
}

_DRY_DETAIL = {
    "status": "ok",
    "data": {
        "sessionId": "dry-session-001",
        "projectId": "dry-project",
        "session": {"id": "dry-session-001", "title": "Dry-run session"},
        "transcript": None,   # not requested in this call
        "subagents": None,
        "tokens": None,
        "artifacts": None,
        "links": None,
        "redactedFieldCount": 0,
    },
    "meta": {},
}


# ---------------------------------------------------------------------------
# Client logic
# ---------------------------------------------------------------------------


def _check_capability(body: dict, name: str) -> bool:
    """Return True if ``name`` appears in data.capabilities."""
    caps = body.get("data", {}).get("capabilities", [])
    return name in caps


def run(
    *,
    base_url: str,
    project_id: str,
    token: str,
    dry: bool,
    limit: int,
    search_query: str,
) -> None:
    """Run the capability-discover → list → search → detail flow."""

    def get(path: str, dry_response: dict) -> dict[str, Any]:
        if dry:
            print(f"  [DRY] GET {path}")
            return dry_response
        return _http_get(f"{base_url}{path}", token=token)

    # ------------------------------------------------------------------
    # 1. Capability discovery
    # ------------------------------------------------------------------
    print("== Step 1: Capability discovery ==")
    cap_body = get("/api/v1/capabilities", _DRY_CAPABILITY)
    print(f"  api_version  : {cap_body.get('data', {}).get('api_version')}")
    print(f"  capabilities : {cap_body.get('data', {}).get('capabilities')}")

    has_cross_project = _check_capability(cap_body, "sessions:cross-project")
    has_detail = _check_capability(cap_body, "sessions:detail")
    if not has_cross_project:
        print("  [WARN] server does not advertise sessions:cross-project — detail endpoint may not be available")
    if not has_detail:
        print("  [WARN] server does not advertise sessions:detail — transcript bundle unavailable")

    # ------------------------------------------------------------------
    # 2. Session list (paginated, first page)
    # ------------------------------------------------------------------
    print(f"\n== Step 2: Session list (limit={limit}) ==")
    list_body = get(f"/api/v1/sessions?limit={limit}&offset=0", _DRY_SESSIONS)
    items = list_body.get("data", [])
    meta = list_body.get("meta", {})
    print(f"  total   : {meta.get('total', 0)}")
    print(f"  has_more: {meta.get('has_more', False)}")
    print(f"  items   : {len(items)} returned")
    if items:
        first = items[0]
        _fid = first.get('sessionId') or first.get('session_id') or first.get('id') or ''
        print(f"  first   : {_fid} — {first.get('title', '')[:60]}")

    # ------------------------------------------------------------------
    # 3. Search
    # ------------------------------------------------------------------
    print(f'\n== Step 3: Session search (q="{search_query}") ==')
    search_body = get(
        f"/api/v1/sessions/search?q={urllib.parse.quote(search_query)}&limit=5",
        _DRY_SEARCH,
    )
    search_items = search_body.get("data", {}).get("items", [])
    print(f"  matches : {len(search_items)}")

    # ------------------------------------------------------------------
    # 4. Session detail — only when a session_id is available
    # ------------------------------------------------------------------
    print(f"\n== Step 4: Session detail (project_id={project_id or '<none>'}) ==")
    # Prefer a session_id from the list; fall back to dry-run placeholder.
    session_id = (
        (items[0].get("sessionId") or items[0].get("session_id") or items[0].get("id"))
        if items else None
    ) or "dry-session-001"
    effective_project_id = project_id or "dry-project"

    if not has_detail:
        print("  [SKIP] sessions:detail capability not advertised; skipping.")
    elif not project_id and not dry:
        print("  [SKIP] --project-id is required for the detail endpoint in live mode.")
    else:
        detail_body = get(
            f"/api/v1/sessions/{session_id}/detail?project_id={effective_project_id}",
            _DRY_DETAIL,
        )
        data = detail_body.get("data", {})
        print(f"  sessionId        : {data.get('sessionId')}")
        print(f"  projectId        : {data.get('projectId')}")
        print(f"  redactedFields   : {data.get('redactedFieldCount', 0)}")
        transcript = data.get("transcript")
        if transcript is None:
            print("  transcript       : not included (expected — not requested in this call)")
        else:
            print(f"  transcript.items : {len(transcript.get('items', []))}")
            print(f"  transcript.next  : {transcript.get('nextCursor')}")

    print("\nDone.")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CCDash /api/v1 example client for IntentTree and LAN agents.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="CCDash server base URL (default: http://localhost:8000).",
    )
    parser.add_argument(
        "--project-id",
        default="",
        help="Project ID for cross-project detail/transcript requests (required in live mode).",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Bearer token when CCDASH_API_TOKEN is set on the server.",
    )
    parser.add_argument(
        "--dry",
        action="store_true",
        default=False,
        help="Dry-run mode: use mocked responses instead of hitting a live server.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Page size for the session list (default: 5).",
    )
    parser.add_argument(
        "--search",
        default="authentication",
        dest="search_query",
        help='Search query string (default: "authentication").',
    )
    return parser.parse_args()


if __name__ == "__main__":
    # Late import so `--help` works without urllib.parse being imported at module level
    import urllib.parse  # noqa: PLC0415

    args = _parse_args()
    run(
        base_url=args.base_url.rstrip("/"),
        project_id=args.project_id,
        token=args.token,
        dry=args.dry,
        limit=args.limit,
        search_query=args.search_query,
    )
