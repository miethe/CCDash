"""Service layer for Test Visualizer health, timeline, and correlation endpoints."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

from backend.db.factory import (
    get_feature_repository,
    get_session_repository,
    get_test_domain_repository,
    get_test_integrity_repository,
    get_test_mapping_repository,
    get_test_result_repository,
    get_test_run_repository,
)
from backend.models import (
    DomainHealthRollupDTO,
    FeatureTestHealthDTO,
    FeatureTimelinePointDTO,
    FeatureTimelineResponseDTO,
    TestCorrelationResponseDTO,
    TestIntegritySignalDTO,
    TestRunDTO,
)

_FAILED_STATUSES = {"failed", "error", "xpassed"}
_SKIPPED_STATUSES = {"skipped", "xfailed"}


def _parse_iso(value: str | None) -> datetime | None:
    token = str(value or "").strip()
    if not token:
        return None
    try:
        return datetime.fromisoformat(token.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_dto_run(row: dict[str, Any]) -> TestRunDTO:
    return TestRunDTO(
        run_id=str(row.get("run_id") or ""),
        project_id=str(row.get("project_id") or ""),
        timestamp=str(row.get("timestamp") or ""),
        git_sha=str(row.get("git_sha") or ""),
        branch=str(row.get("branch") or ""),
        agent_session_id=str(row.get("agent_session_id") or ""),
        env_fingerprint=str(row.get("env_fingerprint") or ""),
        trigger=str(row.get("trigger") or "local"),
        status=str(row.get("status") or "complete"),
        total_tests=int(row.get("total_tests") or 0),
        passed_tests=int(row.get("passed_tests") or 0),
        failed_tests=int(row.get("failed_tests") or 0),
        skipped_tests=int(row.get("skipped_tests") or 0),
        duration_ms=int(row.get("duration_ms") or 0),
        metadata=row.get("metadata_json", {}) if isinstance(row.get("metadata_json", {}), dict) else {},
        created_at=str(row.get("created_at") or ""),
    )


def _to_dto_signal(row: dict[str, Any]) -> TestIntegritySignalDTO:
    details = row.get("details_json", {}) if isinstance(row.get("details_json"), dict) else {}
    linked_run_ids = row.get("linked_run_ids_json", [])
    if not isinstance(linked_run_ids, list):
        linked_run_ids = []
    return TestIntegritySignalDTO(
        signal_id=str(row.get("signal_id") or ""),
        project_id=str(row.get("project_id") or ""),
        git_sha=str(row.get("git_sha") or ""),
        file_path=str(row.get("file_path") or ""),
        test_id=str(row.get("test_id") or "") or None,
        signal_type=str(row.get("signal_type") or ""),
        severity=str(row.get("severity") or "medium"),
        details=details,
        linked_run_ids=[str(item) for item in linked_run_ids if str(item).strip()],
        agent_session_id=str(row.get("agent_session_id") or ""),
        created_at=str(row.get("created_at") or ""),
    )


def _status_totals(rows: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    passed = 0
    failed = 0
    skipped = 0
    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        if status in _FAILED_STATUSES:
            failed += 1
        elif status in _SKIPPED_STATUSES:
            skipped += 1
        else:
            passed += 1
    total = passed + failed + skipped
    return total, passed, failed, skipped


def _pass_rate(*, passed: int, failed: int) -> float:
    denom = passed + failed
    if denom <= 0:
        return 0.0
    return round(float(passed) / float(denom), 4)


def _integrity_scores(open_signals: int) -> tuple[float, float]:
    integrity_score = max(0.0, round(1.0 - (0.1 * float(open_signals)), 4))
    return integrity_score, round(integrity_score, 4)


class TestHealthService:
    """Compute domain/feature health, timeline, and correlation payloads."""

    def __init__(self, db: Any):
        self.db = db
        self.run_repo = get_test_run_repository(db)
        self.result_repo = get_test_result_repository(db)
        self.mapping_repo = get_test_mapping_repository(db)
        self.domain_repo = get_test_domain_repository(db)
        self.integrity_repo = get_test_integrity_repository(db)
        self.feature_repo = get_feature_repository(db)
        self.session_repo = get_session_repository(db)

    async def _list_all_paginated(self, repo: Any, project_id: str, page_size: int = 200) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = await repo.list_paginated(offset=offset, limit=page_size, project_id=project_id)
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += len(page)
        return rows

    async def _filtered_runs(self, project_id: str, since: str | None = None) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        offset = 0
        page_size = 200
        while True:
            page = await self.run_repo.list_by_project(project_id=project_id, limit=page_size, offset=offset)
            if not page:
                break
            runs.extend(page)
            if len(page) < page_size:
                break
            offset += len(page)

        since_dt = _parse_iso(since)
        if since_dt is None:
            return runs
        filtered: list[dict[str, Any]] = []
        for run in runs:
            run_dt = _parse_iso(str(run.get("timestamp") or ""))
            if run_dt is not None and run_dt >= since_dt:
                filtered.append(run)
        return filtered

    async def _latest_results_by_test(
        self,
        project_id: str,
        since: str | None = None,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
        runs = await self._filtered_runs(project_id=project_id, since=since)
        runs_sorted = sorted(
            runs,
            key=lambda item: _parse_iso(str(item.get("timestamp") or "")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        run_by_id = {str(run.get("run_id") or ""): run for run in runs_sorted if str(run.get("run_id") or "")}
        latest_result: dict[str, dict[str, Any]] = {}
        latest_run_for_test: dict[str, dict[str, Any]] = {}

        for run in runs_sorted:
            run_id = str(run.get("run_id") or "")
            if not run_id:
                continue
            results = await self.result_repo.get_by_run(run_id)
            for row in results:
                test_id = str(row.get("test_id") or "")
                if test_id and test_id not in latest_result:
                    latest_result[test_id] = row
                    latest_run_for_test[test_id] = run
        return run_by_id, latest_result, latest_run_for_test, runs_sorted

    async def get_domain_rollups(
        self,
        project_id: str,
        since: str | None = None,
        include_children: bool = True,
    ) -> list[DomainHealthRollupDTO]:
        domains = await self._list_all_paginated(self.domain_repo, project_id=project_id)
        mappings = await self._list_all_paginated(self.mapping_repo, project_id=project_id)
        integrity_signals = await self.integrity_repo.list_by_project(project_id=project_id, limit=5000, offset=0)
        _, latest_result, latest_run_for_test, _ = await self._latest_results_by_test(project_id=project_id, since=since)

        primary_mappings = [
            row for row in mappings
            if int(row.get("is_primary") or 0) == 1 and str(row.get("domain_id") or "").strip()
        ]

        domain_to_tests: dict[str, set[str]] = defaultdict(set)
        for row in primary_mappings:
            domain_id = str(row.get("domain_id") or "").strip()
            test_id = str(row.get("test_id") or "").strip()
            if domain_id and test_id:
                domain_to_tests[domain_id].add(test_id)

        signal_counts: dict[str, int] = defaultdict(int)
        test_to_domain: dict[str, str] = {}
        for domain_id, test_ids in domain_to_tests.items():
            for test_id in test_ids:
                test_to_domain[test_id] = domain_id
        for signal in integrity_signals:
            test_id = str(signal.get("test_id") or "").strip()
            domain_id = test_to_domain.get(test_id)
            if domain_id:
                signal_counts[domain_id] += 1

        nodes: dict[str, DomainHealthRollupDTO] = {}
        for domain in domains:
            domain_id = str(domain.get("domain_id") or "")
            test_ids = domain_to_tests.get(domain_id, set())
            rows = [latest_result[test_id] for test_id in test_ids if test_id in latest_result]
            _, passed, failed, skipped = _status_totals(rows)
            pass_rate = _pass_rate(passed=passed, failed=failed)
            integrity_score, confidence_base = _integrity_scores(signal_counts.get(domain_id, 0))
            confidence_score = round(pass_rate * confidence_base, 4)
            last_run_at = None
            for test_id in test_ids:
                run = latest_run_for_test.get(test_id)
                if run is None:
                    continue
                ts = str(run.get("timestamp") or "")
                if ts and (last_run_at is None or ts > last_run_at):
                    last_run_at = ts

            nodes[domain_id] = DomainHealthRollupDTO(
                domain_id=domain_id,
                domain_name=str(domain.get("name") or ""),
                tier=str(domain.get("tier") or "core"),
                total_tests=len(rows),
                passed=passed,
                failed=failed,
                skipped=skipped,
                pass_rate=pass_rate,
                integrity_score=integrity_score,
                confidence_score=confidence_score,
                last_run_at=last_run_at,
                children=[],
            )

        roots: list[DomainHealthRollupDTO] = []
        for domain in domains:
            domain_id = str(domain.get("domain_id") or "")
            parent_id = str(domain.get("parent_id") or "").strip()
            node = nodes.get(domain_id)
            if node is None:
                continue
            if parent_id and parent_id in nodes and include_children:
                nodes[parent_id].children.append(node)
            else:
                roots.append(node)

        if not include_children:
            for node in nodes.values():
                node.children = []
        return roots

    async def get_feature_health(
        self,
        project_id: str,
        feature_id: str,
        since: str | None = None,
    ) -> FeatureTestHealthDTO | None:
        feature_rows, _ = await self.list_feature_health(
            project_id=project_id,
            domain_id=None,
            since=since,
            offset=0,
            limit=10000,
        )
        for row in feature_rows:
            if row.feature_id == feature_id:
                return row
        return None

    async def list_feature_health(
        self,
        project_id: str,
        domain_id: str | None = None,
        since: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[FeatureTestHealthDTO], int]:
        mappings = await self._list_all_paginated(self.mapping_repo, project_id=project_id)
        feature_rows = await self.feature_repo.list_all(project_id)
        feature_names = {str(row.get("id") or ""): str(row.get("name") or "") for row in feature_rows}
        integrity_signals = await self.integrity_repo.list_by_project(project_id=project_id, limit=5000, offset=0)
        _, latest_result, latest_run_for_test, _ = await self._latest_results_by_test(project_id=project_id, since=since)

        feature_to_tests: dict[str, set[str]] = defaultdict(set)
        feature_domain: dict[str, str | None] = {}

        for row in mappings:
            if int(row.get("is_primary") or 0) != 1:
                continue
            mapping_domain_id = str(row.get("domain_id") or "").strip() or None
            if domain_id and mapping_domain_id != domain_id:
                continue
            feature_id = str(row.get("feature_id") or "").strip()
            test_id = str(row.get("test_id") or "").strip()
            if not feature_id or not test_id:
                continue
            feature_to_tests[feature_id].add(test_id)
            if feature_id not in feature_domain:
                feature_domain[feature_id] = mapping_domain_id

        test_to_features: dict[str, set[str]] = defaultdict(set)
        for feature_id, test_ids in feature_to_tests.items():
            for test_id in test_ids:
                test_to_features[test_id].add(feature_id)

        signal_counts: dict[str, int] = defaultdict(int)
        for signal in integrity_signals:
            test_id = str(signal.get("test_id") or "").strip()
            for feature_id in test_to_features.get(test_id, set()):
                signal_counts[feature_id] += 1

        items: list[FeatureTestHealthDTO] = []
        for mapped_feature_id in sorted(feature_to_tests.keys()):
            test_ids = feature_to_tests[mapped_feature_id]
            rows = [latest_result[test_id] for test_id in test_ids if test_id in latest_result]
            _, passed, failed, skipped = _status_totals(rows)
            pass_rate = _pass_rate(passed=passed, failed=failed)
            open_signals = signal_counts.get(mapped_feature_id, 0)
            integrity_score, confidence_base = _integrity_scores(open_signals)
            confidence_score = round(pass_rate * confidence_base, 4)
            last_run_at = None
            for test_id in test_ids:
                run = latest_run_for_test.get(test_id)
                if run is None:
                    continue
                ts = str(run.get("timestamp") or "")
                if ts and (last_run_at is None or ts > last_run_at):
                    last_run_at = ts

            items.append(
                FeatureTestHealthDTO(
                    feature_id=mapped_feature_id,
                    feature_name=feature_names.get(mapped_feature_id, mapped_feature_id),
                    domain_id=feature_domain.get(mapped_feature_id),
                    total_tests=len(rows),
                    passed=passed,
                    failed=failed,
                    skipped=skipped,
                    pass_rate=pass_rate,
                    integrity_score=integrity_score,
                    confidence_score=confidence_score,
                    last_run_at=last_run_at,
                    open_signals=open_signals,
                )
            )

        total = len(items)
        return items[offset: offset + limit], total

    async def get_feature_timeline(
        self,
        project_id: str,
        feature_id: str,
        since: str | None,
        until: str | None,
        include_signals: bool,
    ) -> FeatureTimelineResponseDTO:
        effective_since = since
        if not effective_since:
            effective_since = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()

        mappings = await self.mapping_repo.list_by_feature(project_id, feature_id, is_primary_only=True)
        test_ids = {str(row.get("test_id") or "").strip() for row in mappings if str(row.get("test_id") or "").strip()}
        runs = await self._filtered_runs(project_id=project_id, since=effective_since)
        until_dt = _parse_iso(until)
        if until_dt is not None:
            runs = [
                run
                for run in runs
                if (_parse_iso(str(run.get("timestamp") or "")) or datetime.min.replace(tzinfo=timezone.utc)) <= until_dt
            ]

        feature_row = await self.feature_repo.get_by_id(feature_id)
        feature_name = str((feature_row or {}).get("name") or feature_id)

        by_day: dict[str, dict[str, Any]] = {}
        timeline_rows_for_good_red: list[tuple[str, int, int]] = []

        signals = []
        if include_signals:
            signals = await self.integrity_repo.list_by_project(project_id=project_id, limit=5000, offset=0)

        signals_by_run: dict[str, list[TestIntegritySignalDTO]] = defaultdict(list)
        if include_signals:
            for row in signals:
                linked = row.get("linked_run_ids_json", [])
                if not isinstance(linked, list):
                    linked = []
                signal_test_id = str(row.get("test_id") or "").strip()
                if signal_test_id and test_ids and signal_test_id not in test_ids:
                    continue
                for run_id in linked:
                    token = str(run_id).strip()
                    if token:
                        signals_by_run[token].append(_to_dto_signal(row))

        for run in runs:
            run_id = str(run.get("run_id") or "")
            if not run_id:
                continue
            run_ts = str(run.get("timestamp") or "")
            run_dt = _parse_iso(run_ts)
            if run_dt is None:
                continue
            day = run_dt.date().isoformat()
            results = await self.result_repo.get_by_run(run_id)
            if test_ids:
                results = [row for row in results if str(row.get("test_id") or "").strip() in test_ids]
            if not results:
                continue

            _, passed, failed, skipped = _status_totals(results)
            bucket = by_day.setdefault(
                day,
                {
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "run_ids": [],
                    "signals": [],
                    "max_ts": "",
                },
            )
            bucket["passed"] += passed
            bucket["failed"] += failed
            bucket["skipped"] += skipped
            if run_id not in bucket["run_ids"]:
                bucket["run_ids"].append(run_id)
            bucket["signals"].extend(signals_by_run.get(run_id, []))
            if run_ts > str(bucket.get("max_ts") or ""):
                bucket["max_ts"] = run_ts

        points: list[FeatureTimelinePointDTO] = []
        first_green: str | None = None
        last_red: str | None = None
        last_known_good: str | None = None

        for day in sorted(by_day.keys()):
            bucket = by_day[day]
            pass_rate = _pass_rate(passed=int(bucket["passed"]), failed=int(bucket["failed"]))
            point = FeatureTimelinePointDTO(
                date=day,
                pass_rate=pass_rate,
                passed=int(bucket["passed"]),
                failed=int(bucket["failed"]),
                skipped=int(bucket["skipped"]),
                run_ids=list(bucket["run_ids"]),
                signals=list(bucket["signals"]),
            )
            points.append(point)
            timeline_rows_for_good_red.append((str(bucket.get("max_ts") or ""), int(bucket["passed"]), int(bucket["failed"])))

        for ts, passed, failed in sorted(timeline_rows_for_good_red, key=lambda row: row[0]):
            if passed > 0 and failed == 0 and first_green is None:
                first_green = ts
            if failed > 0:
                last_red = ts
            if passed > 0 and failed == 0:
                last_known_good = ts

        return FeatureTimelineResponseDTO(
            feature_id=feature_id,
            feature_name=feature_name,
            timeline=points,
            first_green=first_green,
            last_red=last_red,
            last_known_good=last_known_good,
        )

    async def get_correlation(self, run_id: str, project_id: str) -> TestCorrelationResponseDTO | None:
        run = await self.run_repo.get_by_id(run_id)
        if not run or str(run.get("project_id") or "") != project_id:
            return None

        run_dto = _to_dto_run(run)
        session_row = None
        session_id = str(run.get("agent_session_id") or "").strip()
        if session_id:
            session_row = await self.session_repo.get_by_id(session_id)

        commit_correlation = await self._load_commit_correlation(project_id=project_id, git_sha=str(run.get("git_sha") or ""))

        mappings = await self._list_mappings_for_run(project_id=project_id, run_id=run_id)
        feature_ids = sorted(
            {
                str(row.get("feature_id") or "").strip()
                for row in mappings
                if int(row.get("is_primary") or 0) == 1 and str(row.get("feature_id") or "").strip()
            }
        )
        features: list[FeatureTestHealthDTO] = []
        for feature_id in feature_ids:
            health = await self.get_feature_health(project_id=project_id, feature_id=feature_id)
            if health is not None:
                features.append(health)

        signals: list[dict[str, Any]] = []
        git_sha = str(run.get("git_sha") or "").strip()
        if git_sha:
            signals = await self.integrity_repo.list_by_sha(project_id=project_id, git_sha=git_sha, limit=200)
        signal_dtos = [_to_dto_signal(row) for row in signals]

        links = {
            "session_url": f"/#/sessions?session_id={session_id}" if session_id else "",
            "feature_url": f"/#/execution?feature_id={feature_ids[0]}" if feature_ids else "",
            "testing_page_url": f"/#/tests?run_id={run_id}",
        }

        return TestCorrelationResponseDTO(
            run=run_dto,
            agent_session=session_row,
            commit_correlation=commit_correlation,
            features=features,
            integrity_signals=signal_dtos,
            links=links,
        )

    async def _list_mappings_for_run(self, project_id: str, run_id: str) -> list[dict[str, Any]]:
        results = await self.result_repo.get_by_run(run_id)
        mappings: list[dict[str, Any]] = []
        for row in results:
            test_id = str(row.get("test_id") or "").strip()
            if not test_id:
                continue
            rows = await self.mapping_repo.list_by_test(project_id, test_id)
            mappings.extend(rows)
        return mappings

    async def _load_commit_correlation(self, project_id: str, git_sha: str) -> dict[str, Any] | None:
        if not git_sha:
            return None

        if isinstance(self.db, aiosqlite.Connection):
            query = """
                SELECT *
                FROM commit_correlations
                WHERE project_id = ? AND commit_hash = ?
                ORDER BY window_end DESC
                LIMIT 1
            """
            async with self.db.execute(query, (project_id, git_sha)) as cur:
                row = await cur.fetchone()
                if row is None:
                    return None
                payload = dict(row)
        else:
            query = """
                SELECT *
                FROM commit_correlations
                WHERE project_id = $1 AND commit_hash = $2
                ORDER BY window_end DESC
                LIMIT 1
            """
            row = await self.db.fetchrow(query, project_id, git_sha)
            if row is None:
                return None
            payload = dict(row)

        raw_payload = payload.get("payload_json")
        if isinstance(raw_payload, str) and raw_payload.strip():
            try:
                payload["payload_json"] = json.loads(raw_payload)
            except Exception:
                payload["payload_json"] = {}
        elif not isinstance(raw_payload, dict):
            payload["payload_json"] = {}
        return payload
