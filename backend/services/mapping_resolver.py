"""Domain mapping resolver for Test Visualizer."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from backend import config
from backend.db.factory import (
    get_feature_repository,
    get_test_definition_repository,
    get_test_domain_repository,
    get_test_mapping_repository,
    get_test_result_repository,
    get_test_run_repository,
)


logger = logging.getLogger("ccdash.test_visualizer.mapping")

_FEATURE_MARKER_PATTERN = re.compile(r'@pytest\.mark\.feature\(["\']([^"\']+)["\']\)')
_DOMAIN_MARKER_PATTERN = re.compile(r'@pytest\.mark\.domain\(["\']([^"\']+)["\']\)')
_GENERIC_MARKER_PATTERN = re.compile(r"@pytest\.mark\.([A-Za-z_][A-Za-z0-9_]*)")
_TEST_FUNC_PATTERN = re.compile(r"\btest[_\-.]([A-Za-z0-9_\-.]+)")


def _slug(value: str) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    token = re.sub(r"[^a-z0-9]+", "-", token)
    return token.strip("-")


def _clamp_confidence(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except Exception:
        return default
    if numeric < 0.0:
        return 0.0
    if numeric > 1.0:
        return 1.0
    return round(numeric, 4)


@runtime_checkable
class MappingProvider(Protocol):
    """Protocol for domain/feature mapping providers."""

    @property
    def name(self) -> str:
        ...

    @property
    def priority(self) -> int:
        ...

    async def resolve(
        self,
        test_definitions: list[dict[str, Any]],
        project_id: str,
        context: dict[str, Any],
    ) -> list["MappingCandidate"]:
        ...


@dataclass
class MappingCandidate:
    test_id: str
    feature_id: str
    domain_id: str | None
    confidence: float
    provider_source: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MappingResolutionResult:
    run_id: str = ""
    project_id: str = ""
    provider_count: int = 0
    candidate_count: int = 0
    stored_count: int = 0
    primary_count: int = 0
    errors: list[str] = field(default_factory=list)


class RepoHeuristicsProvider:
    name = "repo_heuristics"
    priority = 50

    def __init__(self, db: Any):
        self.db = db
        self.feature_repo = get_feature_repository(db)
        self.domain_repo = get_test_domain_repository(db)

    async def resolve(
        self,
        test_definitions: list[dict[str, Any]],
        project_id: str,
        context: dict[str, Any],
    ) -> list[MappingCandidate]:
        features = await self.feature_repo.list_all(project_id)
        candidates: list[MappingCandidate] = []

        for row in test_definitions:
            test_id = str(row.get("test_id") or "").strip()
            if not test_id:
                continue
            path = str(row.get("path") or "").strip()
            name = str(row.get("name") or "").strip()

            feature_hint = self._extract_feature_hint(path=path, test_name=name)
            if not feature_hint:
                continue
            matched_feature_id, confidence = self._match_feature_hint(feature_hint, features)
            if not matched_feature_id or confidence <= 0.3:
                continue

            domain_id = None
            domain_hint = self._extract_domain_hint(path)
            if domain_hint:
                domain = await self.domain_repo.get_or_create_by_name(project_id, domain_hint)
                domain_id = str(domain.get("domain_id") or "").strip() or None

            candidates.append(
                MappingCandidate(
                    test_id=test_id,
                    feature_id=matched_feature_id,
                    domain_id=domain_id,
                    confidence=confidence,
                    provider_source=self.name,
                    metadata={
                        "feature_hint": feature_hint,
                        "domain_hint": domain_hint,
                    },
                )
            )
        return candidates

    def _extract_domain_hint(self, test_path: str) -> str:
        path = str(test_path or "").strip().replace("\\", "/")
        if not path:
            return ""
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            return ""
        if segments[0] == "tests":
            segments = segments[1:]
        if not segments:
            return ""
        if segments[0] in {"unit", "integration", "e2e", "functional"} and len(segments) > 1:
            return _slug(segments[1])
        return _slug(segments[0])

    def _extract_feature_hint(self, *, path: str, test_name: str) -> str:
        filename = Path(path).name
        stem = Path(filename).stem
        if stem.startswith("test_"):
            hint = _slug(stem[len("test_"):])
            if hint:
                return hint

        match = _TEST_FUNC_PATTERN.search(test_name)
        if match:
            return _slug(match.group(1))
        return ""

    def _match_feature_hint(
        self,
        hint: str,
        features: list[dict[str, Any]],
    ) -> tuple[str | None, float]:
        best_feature = None
        best_confidence = 0.0
        normalized_hint = _slug(hint)
        if not normalized_hint:
            return None, 0.0

        for feature in features:
            feature_id = str(feature.get("id") or "").strip()
            feature_name = str(feature.get("name") or "").strip()
            id_slug = _slug(feature_id)
            name_slug = _slug(feature_name)

            score = 0.0
            if normalized_hint in {feature_id.lower(), feature_name.lower(), id_slug, name_slug}:
                score = 0.9
            elif id_slug.startswith(normalized_hint) or name_slug.startswith(normalized_hint):
                score = 0.5
            else:
                ratio = max(
                    SequenceMatcher(None, normalized_hint, id_slug).ratio(),
                    SequenceMatcher(None, normalized_hint, name_slug).ratio(),
                )
                if ratio >= 0.8:
                    score = 0.7

            if score > best_confidence and feature_id:
                best_confidence = score
                best_feature = feature_id

        return best_feature, best_confidence


class TestMetadataProvider:
    name = "test_metadata"
    priority = 30

    def __init__(self, db: Any):
        self.db = db
        self.feature_repo = get_feature_repository(db)
        self.domain_repo = get_test_domain_repository(db)

    async def resolve(
        self,
        test_definitions: list[dict[str, Any]],
        project_id: str,
        context: dict[str, Any],
    ) -> list[MappingCandidate]:
        features = await self.feature_repo.list_all(project_id)
        feature_lookup: dict[str, str] = {}
        for feature in features:
            feature_id = str(feature.get("id") or "").strip()
            if not feature_id:
                continue
            feature_lookup[_slug(feature_id)] = feature_id
            feature_lookup[_slug(str(feature.get("name") or ""))] = feature_id

        candidates: list[MappingCandidate] = []
        for row in test_definitions:
            test_id = str(row.get("test_id") or "").strip()
            if not test_id:
                continue
            markers = self._extract_markers(row=row, context=context)
            if not markers["features"] and not markers["feature_tags"]:
                continue

            domain_id = None
            if markers["domains"]:
                domain = await self.domain_repo.get_or_create_by_name(project_id, markers["domains"][0])
                domain_id = str(domain.get("domain_id") or "").strip() or None

            for token in markers["features"]:
                feature_id = feature_lookup.get(_slug(token))
                if not feature_id:
                    continue
                candidates.append(
                    MappingCandidate(
                        test_id=test_id,
                        feature_id=feature_id,
                        domain_id=domain_id,
                        confidence=0.9,
                        provider_source=self.name,
                        metadata={"source": "feature_marker", "token": token},
                    )
                )

            for token in markers["feature_tags"]:
                feature_id = feature_lookup.get(_slug(token))
                if not feature_id:
                    continue
                candidates.append(
                    MappingCandidate(
                        test_id=test_id,
                        feature_id=feature_id,
                        domain_id=domain_id,
                        confidence=0.8,
                        provider_source=self.name,
                        metadata={"source": "tag", "token": token},
                    )
                )
        return candidates

    def _extract_markers(self, *, row: dict[str, Any], context: dict[str, Any]) -> dict[str, list[str]]:
        feature_markers: list[str] = []
        domain_markers: list[str] = []
        feature_tags: list[str] = []

        path = str(row.get("path") or "").strip()
        source = self._read_source(path=path, context=context)
        if source:
            feature_markers.extend(_FEATURE_MARKER_PATTERN.findall(source))
            domain_markers.extend(_DOMAIN_MARKER_PATTERN.findall(source))

            # Keep explicit feature()/domain() markers out of generic marker parsing.
            generic = [
                marker for marker in _GENERIC_MARKER_PATTERN.findall(source)
                if marker not in {"feature", "domain", "parametrize"}
            ]
            feature_tags.extend(generic)

        for tag in row.get("tags") or []:
            token = str(tag).strip()
            if not token:
                continue
            lower = token.lower()
            if lower.startswith("feature:"):
                feature_markers.append(token.split(":", 1)[1].strip())
                continue
            if lower.startswith("domain:"):
                domain_markers.append(token.split(":", 1)[1].strip())
                continue
            feature_tags.append(token)

        return {
            "features": [value for value in feature_markers if value],
            "domains": [_slug(value) for value in domain_markers if _slug(value)],
            "feature_tags": [value for value in feature_tags if value],
        }

    def _read_source(self, *, path: str, context: dict[str, Any]) -> str:
        if not path:
            return ""
        roots = [
            str(context.get("project_root") or "").strip(),
            str(config.CCDASH_PROJECT_ROOT or "").strip(),
            os.getenv("CCDASH_PROJECT_ROOT", "").strip(),
        ]
        normalized = path.replace("\\", "/")
        for root in roots:
            if not root:
                continue
            candidate = Path(root) / normalized
            if candidate.exists() and candidate.is_file():
                try:
                    return candidate.read_text(encoding="utf-8")
                except Exception:
                    return ""
        return ""


class SemanticLLMProvider:
    name = "semantic_llm"
    priority = 20

    def __init__(self, mapping_data: dict[str, Any]):
        self.mapping_data = mapping_data

    async def resolve(
        self,
        test_definitions: list[dict[str, Any]],
        project_id: str,
        context: dict[str, Any],
    ) -> list[MappingCandidate]:
        _ = project_id
        _ = context
        entries = self.mapping_data.get("mappings", [])
        if not isinstance(entries, list):
            return []

        by_test_id: dict[str, dict[str, Any]] = {}
        by_path_name: dict[tuple[str, str], dict[str, Any]] = {}
        for row in test_definitions:
            test_id = str(row.get("test_id") or "").strip()
            path = str(row.get("path") or "").strip()
            name = str(row.get("name") or "").strip()
            if test_id:
                by_test_id[test_id] = row
            if path and name:
                by_path_name[(path, name)] = row

        generated_by = str(self.mapping_data.get("generated_by") or "").strip()
        generated_at = str(self.mapping_data.get("generated_at") or "").strip()
        candidates: list[MappingCandidate] = []

        for item in entries:
            if not isinstance(item, dict):
                continue
            feature_id = str(item.get("feature_id") or "").strip()
            if not feature_id:
                continue

            mapped_test_id = str(item.get("test_id") or "").strip()
            if not mapped_test_id:
                mapped = by_path_name.get(
                    (str(item.get("test_path") or "").strip(), str(item.get("test_name") or "").strip())
                )
                mapped_test_id = str((mapped or {}).get("test_id") or "").strip()
            if not mapped_test_id:
                continue

            candidates.append(
                MappingCandidate(
                    test_id=mapped_test_id,
                    feature_id=feature_id,
                    domain_id=str(item.get("domain_id") or "").strip() or None,
                    confidence=_clamp_confidence(item.get("confidence"), default=0.7),
                    provider_source=self.name,
                    metadata={
                        "rationale": str(item.get("rationale") or "").strip(),
                        "generated_by": generated_by,
                        "generated_at": generated_at,
                    },
                )
            )
        return candidates


class MappingResolver:
    """Orchestrates providers, resolves conflicts, and stores mapping snapshots."""

    def __init__(self, db: Any, providers: list[MappingProvider] | None = None):
        self.db = db
        self.run_repo = get_test_run_repository(db)
        self.result_repo = get_test_result_repository(db)
        self.definition_repo = get_test_definition_repository(db)
        self.mapping_repo = get_test_mapping_repository(db)
        self.providers = providers or self._default_providers()

    def _default_providers(self) -> list[MappingProvider]:
        return [
            TestMetadataProvider(self.db),
            RepoHeuristicsProvider(self.db),
        ]

    async def resolve_for_run(self, run_id: str, project_id: str) -> MappingResolutionResult:
        run = await self.run_repo.get_by_id(run_id)
        resolved_project = project_id or str((run or {}).get("project_id") or "").strip()
        if not resolved_project:
            return MappingResolutionResult(
                run_id=run_id,
                project_id="",
                provider_count=len(self.providers),
                errors=["Missing project_id for mapping resolution."],
            )

        run_results = await self.result_repo.get_by_run(run_id)
        definitions: dict[str, dict[str, Any]] = {}
        for row in run_results:
            test_id = str(row.get("test_id") or "").strip()
            if not test_id:
                continue
            definition = await self.definition_repo.get_by_id(test_id)
            if definition is not None:
                definitions[test_id] = definition
                continue

            # Fall back to result row fields for partial payloads.
            definitions[test_id] = {
                "test_id": test_id,
                "project_id": resolved_project,
                "path": str(row.get("path") or "").strip(),
                "name": str(row.get("name") or "").strip(),
                "framework": str(row.get("framework") or "pytest").strip() or "pytest",
                "tags": row.get("tags") if isinstance(row.get("tags"), list) else [],
                "owner": str(row.get("owner") or "").strip(),
            }

        result = await self.resolve(
            project_id=resolved_project,
            test_definitions=list(definitions.values()),
            context={
                "run_id": run_id,
                "git_sha": str((run or {}).get("git_sha") or "").strip(),
                "version": 1,
                "project_root": str(config.CCDASH_PROJECT_ROOT or "").strip(),
            },
        )
        result.run_id = run_id
        return result

    async def resolve(
        self,
        *,
        project_id: str,
        test_definitions: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> MappingResolutionResult:
        context = dict(context or {})
        providers = sorted(self.providers, key=lambda provider: int(getattr(provider, "priority", 100)))
        provider_priority = {
            str(provider.name): int(getattr(provider, "priority", 100))
            for provider in providers
        }

        errors: list[str] = []
        all_candidates: list[MappingCandidate] = []
        for provider in providers:
            if not isinstance(provider, MappingProvider):
                errors.append(f"Provider {provider!r} does not satisfy MappingProvider protocol.")
                continue
            try:
                rows = await provider.resolve(test_definitions, project_id, context)
                all_candidates.extend(
                    self._sanitize_candidate(
                        row,
                        fallback_provider=str(provider.name),
                    )
                    for row in rows
                )
            except Exception as exc:
                logger.warning("Mapping provider failed: %s", provider.name, exc)
                errors.append(f"{provider.name}: {exc}")

        cleaned = [candidate for candidate in all_candidates if candidate is not None]
        merged = self._merge_candidates(cleaned, provider_priority)
        stored_count, primary_count = await self._store_candidates(
            project_id=project_id,
            candidates=merged,
            context=context,
        )
        return MappingResolutionResult(
            run_id=str(context.get("run_id") or ""),
            project_id=project_id,
            provider_count=len(providers),
            candidate_count=len(merged),
            stored_count=stored_count,
            primary_count=primary_count,
            errors=errors,
        )

    def _sanitize_candidate(
        self,
        row: MappingCandidate | dict[str, Any] | None,
        *,
        fallback_provider: str,
    ) -> MappingCandidate | None:
        if row is None:
            return None

        if isinstance(row, MappingCandidate):
            test_id = str(row.test_id or "").strip()
            feature_id = str(row.feature_id or "").strip()
            provider = str(row.provider_source or fallback_provider).strip()
            if not test_id or not feature_id:
                return None
            return MappingCandidate(
                test_id=test_id,
                feature_id=feature_id,
                domain_id=str(row.domain_id or "").strip() or None,
                confidence=_clamp_confidence(row.confidence, default=0.0),
                provider_source=provider,
                metadata=dict(row.metadata or {}),
            )

        if not isinstance(row, dict):
            return None
        test_id = str(row.get("test_id") or "").strip()
        feature_id = str(row.get("feature_id") or "").strip()
        if not test_id or not feature_id:
            return None
        return MappingCandidate(
            test_id=test_id,
            feature_id=feature_id,
            domain_id=str(row.get("domain_id") or "").strip() or None,
            confidence=_clamp_confidence(row.get("confidence"), default=0.0),
            provider_source=str(row.get("provider_source") or fallback_provider).strip(),
            metadata=dict(row.get("metadata") or {}),
        )

    def _merge_candidates(
        self,
        all_candidates: list[MappingCandidate],
        provider_priority: dict[str, int],
    ) -> list[MappingCandidate]:
        if not all_candidates:
            return []

        # Rule 1: if providers agree on (test_id, feature_id), average confidence.
        by_pair: dict[tuple[str, str], list[MappingCandidate]] = {}
        for candidate in all_candidates:
            key = (candidate.test_id, candidate.feature_id)
            by_pair.setdefault(key, []).append(candidate)

        averaged: list[MappingCandidate] = []
        for (test_id, feature_id), group in by_pair.items():
            avg_confidence = round(sum(item.confidence for item in group) / len(group), 4)
            for item in group:
                metadata = dict(item.metadata)
                metadata["agreeing_providers"] = sorted({row.provider_source for row in group})
                metadata["provider_count_for_feature"] = len(group)
                averaged.append(
                    MappingCandidate(
                        test_id=test_id,
                        feature_id=feature_id,
                        domain_id=item.domain_id,
                        confidence=avg_confidence,
                        provider_source=item.provider_source,
                        metadata=metadata,
                    )
                )

        # Rules 2-4: disagreement resolution and primary selection.
        by_test: dict[str, list[MappingCandidate]] = {}
        for candidate in averaged:
            by_test.setdefault(candidate.test_id, []).append(candidate)

        resolved: list[MappingCandidate] = []
        for test_id, candidates in by_test.items():
            primary_key: tuple[str, str, str] | None = None
            eligible = [row for row in candidates if row.confidence >= 0.5]
            if eligible:
                eligible.sort(
                    key=lambda row: (
                        -row.confidence,
                        provider_priority.get(row.provider_source, 100),
                        row.feature_id,
                        row.provider_source,
                    )
                )
                selected = eligible[0]
                primary_key = (selected.test_id, selected.feature_id, selected.provider_source)

            for row in candidates:
                metadata = dict(row.metadata)
                metadata["is_primary"] = bool(
                    primary_key is not None
                    and (row.test_id, row.feature_id, row.provider_source) == primary_key
                )
                metadata["provider_priority"] = provider_priority.get(row.provider_source, 100)
                resolved.append(
                    MappingCandidate(
                        test_id=test_id,
                        feature_id=row.feature_id,
                        domain_id=row.domain_id,
                        confidence=row.confidence,
                        provider_source=row.provider_source,
                        metadata=metadata,
                    )
                )
        return resolved

    async def _store_candidates(
        self,
        *,
        project_id: str,
        candidates: list[MappingCandidate],
        context: dict[str, Any],
    ) -> tuple[int, int]:
        if not candidates:
            return 0, 0

        version = int(context.get("version") or 1)
        snapshot_hash = self._snapshot_hash(
            candidates=candidates,
            run_id=str(context.get("run_id") or ""),
            version=version,
        )

        stored = 0
        primary = 0
        for row in candidates:
            is_primary = bool(row.metadata.get("is_primary"))
            if is_primary:
                primary += 1
            await self.mapping_repo.upsert(
                {
                    "project_id": project_id,
                    "test_id": row.test_id,
                    "feature_id": row.feature_id,
                    "domain_id": row.domain_id,
                    "provider_source": row.provider_source,
                    "confidence": row.confidence,
                    "version": version,
                    "snapshot_hash": snapshot_hash,
                    "is_primary": 1 if is_primary else 0,
                    "metadata": row.metadata,
                },
                project_id=project_id,
            )
            stored += 1

        return stored, primary

    def _snapshot_hash(
        self,
        *,
        candidates: list[MappingCandidate],
        run_id: str,
        version: int,
    ) -> str:
        payload = [
            {
                "test_id": row.test_id,
                "feature_id": row.feature_id,
                "domain_id": row.domain_id,
                "confidence": row.confidence,
                "provider_source": row.provider_source,
            }
            for row in sorted(
                candidates,
                key=lambda item: (item.test_id, item.feature_id, item.provider_source),
            )
        ]
        encoded = json.dumps(
            {"run_id": run_id, "version": version, "mappings": payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]


def validate_semantic_mapping_file(mapping_file: dict[str, Any]) -> tuple[bool, str]:
    """Validate SemanticLLMProvider import payload shape."""
    if not isinstance(mapping_file, dict):
        return False, "mapping_file must be an object."
    mappings = mapping_file.get("mappings")
    if not isinstance(mappings, list):
        return False, "mapping_file.mappings must be an array."
    for index, row in enumerate(mappings):
        if not isinstance(row, dict):
            return False, f"mapping_file.mappings[{index}] must be an object."
        if not str(row.get("feature_id") or "").strip():
            return False, f"mapping_file.mappings[{index}].feature_id is required."
        if not str(row.get("test_id") or "").strip():
            has_path = str(row.get("test_path") or "").strip()
            has_name = str(row.get("test_name") or "").strip()
            if not (has_path and has_name):
                return (
                    False,
                    f"mapping_file.mappings[{index}] requires test_id or (test_path + test_name).",
                )
    return True, ""
