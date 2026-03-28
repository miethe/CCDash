"""Standalone load test for telemetry exporter hardening."""
from __future__ import annotations

import argparse
import asyncio
import tempfile
import time
import tracemalloc
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiosqlite

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import TelemetryExporterConfig
from backend.db.repositories.telemetry_queue import SqliteTelemetryQueueRepository
from backend.db.sqlite_migrations import run_migrations
from backend.models import ExecutionOutcomePayload, TelemetryExportSettingsUpdateRequest
from backend.services.integrations.telemetry_exporter import TelemetryExportCoordinator
from backend.services.integrations.telemetry_settings_store import TelemetrySettingsStore


DEFAULT_QUEUE_SIZE = 1000
DEFAULT_RUNS = 10
DEFAULT_BATCH_SIZE = 50
DEFAULT_INTERVAL_SECONDS = 2.0
DEFAULT_CPU_TARGET_PCT = 2.0


@dataclass(slots=True)
class LoadTestResult:
    queue_seeded: int
    runs_completed: int
    batch_size: int
    processed_rows: int
    remaining_rows: int
    cpu_seconds: float
    wall_seconds: float
    cpu_share_pct: float
    peak_traced_kib: float
    cpu_target_pct: float

    @property
    def passed(self) -> bool:
        return self.cpu_share_pct <= self.cpu_target_pct


class _StubClient:
    async def push_batch(self, events: list[ExecutionOutcomePayload]) -> tuple[bool, str | None]:
        if not events:
            return True, None
        # Do a tiny bit of work so the benchmark exercises real serialization and loops.
        for event in events:
            _ = event.event_id, event.project_slug, event.session_id
        return True, None


def _build_payload(index: int) -> ExecutionOutcomePayload:
    return ExecutionOutcomePayload(
        event_id=uuid4(),
        project_slug="project-load-test",
        session_id=uuid4(),
        workflow_type="feature",
        model_family="Sonnet",
        token_input=200 + index,
        token_output=50 + (index % 25),
        token_cache_read=index % 11,
        token_cache_write=index % 7,
        cost_usd=0.01 + (index * 0.0001),
        tool_call_count=4 + (index % 3),
        tool_call_success_count=4 + (index % 2),
        duration_seconds=30 + (index % 90),
        message_count=6 + (index % 5),
        outcome_status="completed",
        test_pass_rate=0.8 + (index % 5) * 0.02,
        context_utilization_peak=min(0.95, 0.5 + (index % 20) * 0.02),
        feature_slug=f"feature-{index % 12}",
        timestamp=datetime.now(timezone.utc),
        ccdash_version="0.1.0",
    )


async def _seed_queue(
    repo: SqliteTelemetryQueueRepository,
    *,
    queue_size: int,
) -> None:
    for index in range(queue_size):
        payload = _build_payload(index)
        await repo.enqueue(
            session_id=str(payload.session_id),
            project_slug=payload.project_slug,
            payload=payload.event_dict(),
            queue_id=str(payload.event_id),
        )


async def _count_rows(repo: SqliteTelemetryQueueRepository) -> int:
    stats = await repo.get_queue_stats()
    return int(stats.get("pending", 0))


async def _run_load_test(
    *,
    queue_size: int,
    runs: int,
    batch_size: int,
    interval_seconds: float,
    cpu_target_pct: float,
) -> LoadTestResult:
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_store = TelemetrySettingsStore(Path(tmpdir) / "integrations.json")
        settings_store.save(TelemetryExportSettingsUpdateRequest(enabled=True))

        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await run_migrations(db)

        try:
            repo = SqliteTelemetryQueueRepository(db)
            runtime_config = TelemetryExporterConfig(
                enabled=True,
                sam_endpoint="https://sam.example.com/api/v1/analytics/execution-outcomes",
                sam_api_key="secret",
                interval_seconds=60,
                batch_size=batch_size,
                timeout_seconds=30,
                max_queue_size=max(queue_size * 2, 1000),
                queue_retention_days=30,
                allow_insecure=False,
                ccdash_version="0.1.0",
            )
            coordinator = TelemetryExportCoordinator(
                repository=repo,
                settings_store=settings_store,
                runtime_config=runtime_config,
            )
            coordinator._client = _StubClient()  # noqa: SLF001

            await _seed_queue(repo, queue_size=queue_size)

            start_wall = time.perf_counter()
            start_cpu = time.process_time()
            tracemalloc.start()

            runs_completed = 0
            processed_rows = 0
            for _ in range(runs):
                outcome = await coordinator.execute(trigger="load-test", raise_on_busy=False)
                runs_completed += 1
                processed_rows += int(outcome.batch_size)
                if interval_seconds > 0:
                    await asyncio.sleep(interval_seconds)

            current_traced, peak_traced = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            wall_seconds = max(0.0, time.perf_counter() - start_wall)
            cpu_seconds = max(0.0, time.process_time() - start_cpu)
            cpu_share_pct = (cpu_seconds / wall_seconds * 100.0) if wall_seconds > 0 else 0.0
            remaining_rows = await _count_rows(repo)
            return LoadTestResult(
                queue_seeded=queue_size,
                runs_completed=runs_completed,
                batch_size=batch_size,
                processed_rows=processed_rows,
                remaining_rows=remaining_rows,
                cpu_seconds=cpu_seconds,
                wall_seconds=wall_seconds,
                cpu_share_pct=cpu_share_pct,
                peak_traced_kib=peak_traced / 1024.0,
                cpu_target_pct=cpu_target_pct,
            )
        finally:
            await db.close()


def _format_result(result: LoadTestResult) -> str:
    status = "PASS" if result.passed else "FAIL"
    lines = [
        "Telemetry Exporter Load Test",
        f"Status: {status}",
        f"Seeded rows: {result.queue_seeded}",
        f"Runs completed: {result.runs_completed}",
        f"Batch size: {result.batch_size}",
        f"Processed rows: {result.processed_rows}",
        f"Remaining rows: {result.remaining_rows}",
        f"CPU time: {result.cpu_seconds:.4f}s",
        f"Wall time: {result.wall_seconds:.4f}s",
        f"CPU share: {result.cpu_share_pct:.2f}%",
        f"Peak traced memory: {result.peak_traced_kib:.1f} KiB",
        f"Target: <= {result.cpu_target_pct:.2f}%",
    ]
    if not result.passed:
        lines.append("Result: CPU share exceeded the hardening target.")
    else:
        lines.append("Result: CPU share met the hardening target.")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the telemetry exporter hardening load test.")
    parser.add_argument("--queue-size", type=int, default=DEFAULT_QUEUE_SIZE)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--cpu-target-pct", type=float, default=DEFAULT_CPU_TARGET_PCT)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    result = await _run_load_test(
        queue_size=max(1, int(args.queue_size)),
        runs=max(1, int(args.runs)),
        batch_size=max(1, int(args.batch_size)),
        interval_seconds=max(0.0, float(args.interval_seconds)),
        cpu_target_pct=max(0.0, float(args.cpu_target_pct)),
    )
    print(_format_result(result))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
