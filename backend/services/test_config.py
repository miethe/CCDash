"""Project-scoped test configuration helpers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from backend import config
from backend.models import (
    EffectiveTestFlagsDTO,
    Project,
    ProjectTestConfig,
    ProjectTestPlatformConfig,
    TestPlatformId,
)


@dataclass(frozen=True)
class ResolvedTestSource:
    platform_id: TestPlatformId
    enabled: bool
    watch: bool
    results_dir: str
    resolved_dir: Path
    patterns: list[str]


_PLATFORM_ORDER: tuple[TestPlatformId, ...] = (
    "pytest",
    "jest",
    "playwright",
    "coverage",
    "benchmark",
    "lighthouse",
    "locust",
    "triage",
)

_DEFAULT_PLATFORM_CONFIG: dict[TestPlatformId, ProjectTestPlatformConfig] = {
    cfg.id: cfg for cfg in ProjectTestConfig().platforms
}


def _copy_platform(cfg: ProjectTestPlatformConfig) -> ProjectTestPlatformConfig:
    return ProjectTestPlatformConfig(
        id=cfg.id,
        enabled=bool(cfg.enabled),
        resultsDir=str(cfg.resultsDir or ""),
        watch=bool(cfg.watch),
        patterns=[str(item).strip() for item in cfg.patterns if str(item).strip()],
    )


def normalize_project_test_config(
    project: Project,
    *,
    legacy_test_results_dir: str = "",
) -> ProjectTestConfig:
    """Merge partial configs with defaults and ensure stable platform ordering."""
    configured = project.testConfig if isinstance(project.testConfig, ProjectTestConfig) else ProjectTestConfig()
    by_id: dict[TestPlatformId, ProjectTestPlatformConfig] = {}
    for item in configured.platforms:
        if item.id in _DEFAULT_PLATFORM_CONFIG:
            by_id[item.id] = _copy_platform(item)

    normalized: list[ProjectTestPlatformConfig] = []
    for platform_id in _PLATFORM_ORDER:
        default_cfg = _copy_platform(_DEFAULT_PLATFORM_CONFIG[platform_id])
        current = by_id.get(platform_id)
        if current is None:
            normalized.append(default_cfg)
            continue
        normalized.append(
            ProjectTestPlatformConfig(
                id=platform_id,
                enabled=current.enabled,
                resultsDir=current.resultsDir or default_cfg.resultsDir,
                watch=current.watch,
                patterns=current.patterns or default_cfg.patterns,
            )
        )

    if legacy_test_results_dir.strip():
        for item in normalized:
            if item.id == "pytest" and item.resultsDir.strip() in {"", "test-results"}:
                item.resultsDir = legacy_test_results_dir.strip()
                break

    merged = ProjectTestConfig(
        flags=configured.flags,
        platforms=normalized,
        autoSyncOnStartup=bool(configured.autoSyncOnStartup),
        maxFilesPerScan=max(10, int(configured.maxFilesPerScan or 500)),
        maxParseConcurrency=max(1, int(configured.maxParseConcurrency or 4)),
        instructionProfile=str(configured.instructionProfile or "skillmeat").strip() or "skillmeat",
        instructionNotes=str(configured.instructionNotes or ""),
    )
    project.testConfig = merged
    return merged


def effective_test_flags(project: Project | None) -> EffectiveTestFlagsDTO:
    if project is None:
        return EffectiveTestFlagsDTO()
    cfg = normalize_project_test_config(project, legacy_test_results_dir=config.TEST_RESULTS_DIR)
    return EffectiveTestFlagsDTO(
        testVisualizerEnabled=bool(config.CCDASH_TEST_VISUALIZER_ENABLED and cfg.flags.testVisualizerEnabled),
        integritySignalsEnabled=bool(config.CCDASH_INTEGRITY_SIGNALS_ENABLED and cfg.flags.integritySignalsEnabled),
        liveTestUpdatesEnabled=bool(config.CCDASH_LIVE_TEST_UPDATES_ENABLED and cfg.flags.liveTestUpdatesEnabled),
        semanticMappingEnabled=bool(config.CCDASH_SEMANTIC_MAPPING_ENABLED and cfg.flags.semanticMappingEnabled),
    )


def _resolve_dir(project: Project, configured_dir: str) -> Path:
    value = str(configured_dir or "").strip() or "."
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return (Path(project.path) / candidate).resolve()


def resolve_test_sources(
    project: Project,
    *,
    include_disabled: bool = False,
    platform_filter: Iterable[str] | None = None,
) -> list[ResolvedTestSource]:
    cfg = normalize_project_test_config(project, legacy_test_results_dir=config.TEST_RESULTS_DIR)
    allowed = {str(item).strip() for item in (platform_filter or []) if str(item).strip()}

    sources: list[ResolvedTestSource] = []
    for item in cfg.platforms:
        if allowed and item.id not in allowed:
            continue
        if not include_disabled and not item.enabled:
            continue
        sources.append(
            ResolvedTestSource(
                platform_id=item.id,
                enabled=bool(item.enabled),
                watch=bool(item.watch),
                results_dir=item.resultsDir,
                resolved_dir=_resolve_dir(project, item.resultsDir),
                patterns=[str(pattern).strip() for pattern in item.patterns if str(pattern).strip()],
            )
        )
    return sources


def parser_health_map() -> dict[str, bool]:
    return {
        "pytest": True,
        "jest": True,
        "playwright": True,
        "coverage": True,
        "benchmark": True,
        "lighthouse": True,
        "locust": True,
        "triage": True,
    }
