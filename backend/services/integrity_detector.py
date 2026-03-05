"""Integrity signal detection for Test Visualizer."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from typing import Any

from backend import config
from backend.db.factory import (
    get_test_definition_repository,
    get_test_integrity_repository,
    get_test_result_repository,
    get_test_run_repository,
)
from backend.models import TestIntegritySignalDTO


logger = logging.getLogger("ccdash.test_visualizer.integrity")

_FAILED_STATUSES = {"failed", "error", "xpassed"}
_PASSING_STATUSES = {"passed"}
_ASSERTION_TOKENS = (
    "assert ",
    "assertequal",
    "assertraises",
    "asserttrue",
    "assertfalse",
    "assert_called",
)
_SKIP_TOKENS = ("pytest.skip(", "@pytest.mark.skip", "unittest.skip(", "@skip(")
_XFAIL_TOKENS = ("@pytest.mark.xfail", "pytest.xfail(")
_BROAD_EXCEPTION_PATTERNS = (
    re.compile(r"except\s+Exception\s*:"),
    re.compile(r"except\s+BaseException\s*:"),
    re.compile(r"except\s*:"),
)
_DEF_TEST_PATTERN = re.compile(r"^\s*def\s+test_[A-Za-z0-9_]*\s*\(")
_DEF_ANY_PATTERN = re.compile(r"^\s*def\s+[A-Za-z0-9_]*\s*\(")


def _norm(value: str) -> str:
    return str(value or "").strip().lower()


class IntegrityDetector:
    """Async integrity detector. Runs after test ingestion."""

    SIGNAL_TYPES = [
        "assertion_removed",
        "skip_introduced",
        "xfail_added",
        "broad_exception",
        "edited_before_green",
    ]

    def __init__(self, db: Any, git_repo_path: str | None = None):
        self.db = db
        self.git_path = (
            str(git_repo_path or "").strip()
            or str(config.CCDASH_PROJECT_ROOT or "").strip()
            or os.getcwd()
        )
        self.integrity_repo = get_test_integrity_repository(db)
        self.definition_repo = get_test_definition_repository(db)
        self.result_repo = get_test_result_repository(db)
        self.run_repo = get_test_run_repository(db)

    async def check_run(
        self,
        run_id: str,
        git_sha: str,
        project_id: str,
    ) -> list[TestIntegritySignalDTO]:
        if not run_id or not git_sha or not project_id:
            return []

        if not self.git_path or not self._git_available():
            logger.info("Git not available; skipping integrity check for run %s", run_id)
            return []

        run_row = await self.run_repo.get_by_id(run_id)
        if run_row is None:
            return []

        diff_text = await self._get_git_diff(git_sha)
        if not diff_text:
            return []

        changes = self._extract_test_file_changes(diff_text)
        if not changes:
            return []

        definitions = await self._list_test_definitions(project_id)
        created: list[TestIntegritySignalDTO] = []
        for file_path, change_data in changes.items():
            created.extend(
                await self._analyze_file_changes(
                    run_id=run_id,
                    project_id=project_id,
                    git_sha=git_sha,
                    file_path=file_path,
                    change_data=change_data,
                    definitions=definitions,
                    agent_session_id=str(run_row.get("agent_session_id") or ""),
                )
            )
        return created

    async def _analyze_file_changes(
        self,
        *,
        run_id: str,
        project_id: str,
        git_sha: str,
        file_path: str,
        change_data: dict[str, Any],
        definitions: list[dict[str, Any]],
        agent_session_id: str,
    ) -> list[TestIntegritySignalDTO]:
        added_lines = change_data.get("added", [])
        removed_lines = change_data.get("removed", [])
        hunk_lines = change_data.get("hunk", [])

        test_ids = self._match_test_ids_for_path(file_path=file_path, definitions=definitions)
        created: list[TestIntegritySignalDTO] = []

        if self._has_assertion_removed(removed_lines):
            created.extend(
                await self._create_signals(
                    signal_type="assertion_removed",
                    run_id=run_id,
                    project_id=project_id,
                    git_sha=git_sha,
                    file_path=file_path,
                    test_ids=test_ids,
                    agent_session_id=agent_session_id,
                    details={"removed_assertions": removed_lines[:8]},
                )
            )

        if self._has_token(added_lines, _SKIP_TOKENS):
            created.extend(
                await self._create_signals(
                    signal_type="skip_introduced",
                    run_id=run_id,
                    project_id=project_id,
                    git_sha=git_sha,
                    file_path=file_path,
                    test_ids=test_ids,
                    agent_session_id=agent_session_id,
                    details={"added_skip_lines": added_lines[:8]},
                )
            )

        if self._has_token(added_lines, _XFAIL_TOKENS):
            created.extend(
                await self._create_signals(
                    signal_type="xfail_added",
                    run_id=run_id,
                    project_id=project_id,
                    git_sha=git_sha,
                    file_path=file_path,
                    test_ids=test_ids,
                    agent_session_id=agent_session_id,
                    details={"added_xfail_lines": added_lines[:8]},
                )
            )

        if self._has_broad_exception(hunk_lines):
            created.extend(
                await self._create_signals(
                    signal_type="broad_exception",
                    run_id=run_id,
                    project_id=project_id,
                    git_sha=git_sha,
                    file_path=file_path,
                    test_ids=test_ids,
                    agent_session_id=agent_session_id,
                    details={"broad_exception_context": hunk_lines[:15]},
                )
            )

        for test_id in test_ids:
            if await self._went_green_in_run(test_id=test_id, run_id=run_id):
                created.extend(
                    await self._create_signals(
                        signal_type="edited_before_green",
                        run_id=run_id,
                        project_id=project_id,
                        git_sha=git_sha,
                        file_path=file_path,
                        test_ids=[test_id],
                        agent_session_id=agent_session_id,
                        details={"reason": "Test transitioned from failing to passing in this run."},
                    )
                )
        return created

    async def _create_signals(
        self,
        *,
        signal_type: str,
        run_id: str,
        project_id: str,
        git_sha: str,
        file_path: str,
        test_ids: list[str],
        agent_session_id: str,
        details: dict[str, Any],
    ) -> list[TestIntegritySignalDTO]:
        targets = test_ids or [""]
        rows: list[TestIntegritySignalDTO] = []
        created_at = datetime.now(timezone.utc).isoformat()
        for test_id in targets:
            signal_id = self._build_signal_id(
                signal_type=signal_type,
                run_id=run_id,
                test_id=test_id,
                file_path=file_path,
            )
            dto = TestIntegritySignalDTO(
                signal_id=signal_id,
                project_id=project_id,
                git_sha=git_sha,
                file_path=file_path,
                test_id=test_id or None,
                signal_type=signal_type,
                severity=self._severity_for(signal_type),
                details=details,
                linked_run_ids=[run_id],
                agent_session_id=agent_session_id,
                created_at=created_at,
            )
            await self.integrity_repo.upsert(dto.model_dump(), project_id=project_id)
            rows.append(dto)
        return rows

    async def _list_test_definitions(self, project_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        limit = 200
        while True:
            page = await self.definition_repo.list_by_project(project_id=project_id, limit=limit, offset=offset)
            if not page:
                break
            rows.extend(page)
            if len(page) < limit:
                break
            offset += len(page)
        return rows

    async def _went_green_in_run(self, *, test_id: str, run_id: str) -> bool:
        history = await self.result_repo.get_history_for_test(test_id=test_id, limit=20)
        for index, row in enumerate(history):
            if str(row.get("run_id") or "").strip() != run_id:
                continue
            status = _norm(str(row.get("status") or ""))
            if status not in _PASSING_STATUSES:
                return False
            if index + 1 >= len(history):
                return False
            previous_status = _norm(str(history[index + 1].get("status") or ""))
            return previous_status in _FAILED_STATUSES
        return False

    def _match_test_ids_for_path(self, *, file_path: str, definitions: list[dict[str, Any]]) -> list[str]:
        normalized = file_path.replace("\\", "/").strip()
        if not normalized:
            return []
        matches: list[str] = []
        for definition in definitions:
            test_id = str(definition.get("test_id") or "").strip()
            path = str(definition.get("path") or "").replace("\\", "/").strip()
            if not test_id or not path:
                continue
            if path == normalized or path.endswith(normalized) or normalized.endswith(path):
                matches.append(test_id)
        return sorted(set(matches))

    def _has_assertion_removed(self, removed_lines: list[str]) -> bool:
        for line in removed_lines:
            token = line.lower()
            if any(match in token for match in _ASSERTION_TOKENS):
                return True
        return False

    def _has_token(self, lines: list[str], tokens: tuple[str, ...]) -> bool:
        lowered = [line.lower() for line in lines]
        for line in lowered:
            if any(token in line for token in tokens):
                return True
        return False

    def _has_broad_exception(self, hunk_lines: list[str]) -> bool:
        in_test_function = False
        for item in hunk_lines:
            if not isinstance(item, str) or not item:
                continue
            prefix = item[:1]
            text = item[1:] if len(item) > 1 else ""
            stripped = text.strip()
            if _DEF_TEST_PATTERN.match(stripped):
                in_test_function = True
            elif _DEF_ANY_PATTERN.match(stripped):
                in_test_function = False

            if prefix == "+" and in_test_function:
                if any(pattern.search(stripped) for pattern in _BROAD_EXCEPTION_PATTERNS):
                    return True
        return False

    def _extract_test_file_changes(self, diff_text: str) -> dict[str, dict[str, Any]]:
        changes: dict[str, dict[str, Any]] = {}
        current_file = ""
        for line in diff_text.splitlines():
            if line.startswith("diff --git "):
                current_file = ""
                parts = line.split(" ")
                if len(parts) >= 4:
                    candidate = parts[3]
                    if candidate.startswith("b/"):
                        candidate = candidate[2:]
                    if self._is_test_file(candidate):
                        current_file = candidate
                        changes.setdefault(
                            current_file,
                            {"added": [], "removed": [], "hunk": []},
                        )
                continue

            if not current_file:
                continue
            if line.startswith("+++ ") or line.startswith("--- "):
                continue
            if line.startswith("@@ "):
                continue

            bucket = changes[current_file]
            if line.startswith("+"):
                bucket["added"].append(line[1:].strip())
                bucket["hunk"].append(line)
            elif line.startswith("-"):
                bucket["removed"].append(line[1:].strip())
                bucket["hunk"].append(line)
            elif line.startswith(" "):
                bucket["hunk"].append(line)

        # Keep only files with meaningful changes.
        return {
            path: payload
            for path, payload in changes.items()
            if payload["added"] or payload["removed"]
        }

    def _is_test_file(self, file_path: str) -> bool:
        normalized = str(file_path or "").strip().replace("\\", "/")
        if not normalized:
            return False
        filename = normalized.split("/")[-1]
        return (
            "/tests/" in f"/{normalized}"
            or filename.startswith("test_")
            or filename.endswith("_test.py")
        )

    def _severity_for(self, signal_type: str) -> str:
        if signal_type in {"assertion_removed", "skip_introduced", "edited_before_green"}:
            return "high"
        return "medium"

    def _build_signal_id(self, *, signal_type: str, run_id: str, test_id: str, file_path: str) -> str:
        raw = f"{signal_type}::{run_id}::{test_id}::{file_path}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"sig_{digest}"

    def _git_available(self) -> bool:
        if shutil.which("git") is None:
            return False
        return os.path.isdir(self.git_path)

    async def _get_git_diff(self, git_sha: str) -> str:
        try:
            result = await asyncio.create_subprocess_exec(
                "git",
                "diff",
                f"{git_sha}^",
                git_sha,
                cwd=self.git_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()
            if result.returncode != 0:
                logger.warning("git diff failed: %s", stderr.decode("utf-8", errors="ignore"))
                return ""
            return stdout.decode("utf-8", errors="ignore")
        except FileNotFoundError:
            logger.warning("git command not found; integrity detection disabled")
            return ""
        except Exception as exc:
            logger.warning("Failed to run git diff for %s: %s", git_sha, exc)
            return ""
