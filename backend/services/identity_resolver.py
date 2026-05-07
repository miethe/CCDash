"""Artifact identity resolution for SkillMeat snapshot ingestion."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re
from typing import Iterable, Literal

from backend import config
from backend.db.repositories.base import ArtifactSnapshotRepository
from backend.models import SnapshotArtifact


MatchTier = Literal["tier-1", "tier-2", "unresolved"]


@dataclass(frozen=True)
class ArtifactIdentityResolution:
    project_id: str
    ccdash_name: str
    ccdash_type: str
    match_tier: MatchTier
    confidence: float | None
    skillmeat_uuid: str = ""
    content_hash: str = ""
    unresolved_reason: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.match_tier != "unresolved"


class ArtifactIdentityMapper:
    """Resolve observed CCDash artifact names against a SkillMeat snapshot."""

    def __init__(
        self,
        repository: ArtifactSnapshotRepository,
        *,
        fuzzy_threshold: float | None = None,
    ) -> None:
        self.repository = repository
        self.fuzzy_threshold = (
            config.CCDASH_IDENTITY_FUZZY_THRESHOLD if fuzzy_threshold is None else fuzzy_threshold
        )

    async def resolve_identity(
        self,
        *,
        project_id: str,
        observed_name: str,
        ccdash_type: str,
        snapshot_artifacts: Iterable[SnapshotArtifact],
        observed_uuid: str | None = None,
        content_hash: str | None = None,
    ) -> ArtifactIdentityResolution:
        artifacts = tuple(snapshot_artifacts)
        normalized_name = observed_name.strip()
        normalized_type = ccdash_type.strip()

        exact = self._find_exact_match(
            artifacts,
            observed_name=normalized_name,
            observed_uuid=observed_uuid,
            content_hash=content_hash,
        )
        if exact is not None:
            return await self._persist_result(
                self._matched_result(
                    project_id=project_id,
                    ccdash_name=normalized_name,
                    ccdash_type=normalized_type,
                    artifact=exact,
                    match_tier="tier-1",
                    confidence=1.0,
                )
            )

        fuzzy = self._find_fuzzy_match(normalized_name, artifacts)
        if fuzzy is not None:
            artifact, score, matched_alias = fuzzy
            if score >= self.fuzzy_threshold:
                return await self._persist_result(
                    self._matched_result(
                        project_id=project_id,
                        ccdash_name=normalized_name,
                        ccdash_type=normalized_type,
                        artifact=artifact,
                        match_tier="tier-2",
                        confidence=score,
                        matched_alias=matched_alias,
                    )
                )
            if score < 0.5:
                return await self._persist_result(
                    self._unresolved_result(
                        project_id=project_id,
                        ccdash_name=normalized_name,
                        ccdash_type=normalized_type,
                        unresolved_reason="not_in_snapshot",
                    )
                )
            return await self._persist_result(
                self._unresolved_result(
                    project_id=project_id,
                    ccdash_name=normalized_name,
                    ccdash_type=normalized_type,
                    unresolved_reason="below_threshold",
                    best_candidate=artifact,
                    best_confidence=score,
                    matched_alias=matched_alias,
                )
            )

        return await self._persist_result(
            self._unresolved_result(
                project_id=project_id,
                ccdash_name=normalized_name,
                ccdash_type=normalized_type,
                unresolved_reason="not_in_snapshot",
            )
        )

    async def resolve_many(
        self,
        *,
        project_id: str,
        observed_artifacts: Iterable[dict[str, str | None]],
        snapshot_artifacts: Iterable[SnapshotArtifact],
    ) -> list[ArtifactIdentityResolution]:
        artifacts = tuple(snapshot_artifacts)
        results: list[ArtifactIdentityResolution] = []
        for observed in observed_artifacts:
            results.append(
                await self.resolve_identity(
                    project_id=project_id,
                    observed_name=observed["observed_name"] or "",
                    ccdash_type=observed.get("ccdash_type") or "",
                    snapshot_artifacts=artifacts,
                    observed_uuid=observed.get("observed_uuid"),
                    content_hash=observed.get("content_hash"),
                )
            )
        return results

    def _find_exact_match(
        self,
        artifacts: Iterable[SnapshotArtifact],
        *,
        observed_name: str,
        observed_uuid: str | None,
        content_hash: str | None,
    ) -> SnapshotArtifact | None:
        uuid_key = (observed_uuid or "").strip()
        hash_key = (content_hash or "").strip()
        if not uuid_key and _looks_like_hash(observed_name):
            hash_key = observed_name.strip()

        for artifact in artifacts:
            if uuid_key and artifact.artifact_uuid == uuid_key:
                return artifact
            if hash_key and artifact.content_hash == hash_key:
                return artifact
        return None

    def _find_fuzzy_match(
        self,
        observed_name: str,
        artifacts: Iterable[SnapshotArtifact],
    ) -> tuple[SnapshotArtifact, float, str] | None:
        best: tuple[SnapshotArtifact, float, str] | None = None
        for artifact in artifacts:
            for alias in _artifact_aliases(artifact):
                score = _alias_score(observed_name, alias)
                if best is None or score > best[1]:
                    best = (artifact, score, alias)
        return best

    def _matched_result(
        self,
        *,
        project_id: str,
        ccdash_name: str,
        ccdash_type: str,
        artifact: SnapshotArtifact,
        match_tier: MatchTier,
        confidence: float,
        matched_alias: str | None = None,
    ) -> ArtifactIdentityResolution:
        metadata: dict[str, object] = {
            "artifact_status": artifact.status,
            "identity_reconciliation": {"recommended": False, "status": "resolved"},
        }
        if artifact.status == "disabled":
            metadata["ranking_status"] = "disabled"
        if matched_alias:
            metadata["matched_alias"] = matched_alias
        return ArtifactIdentityResolution(
            project_id=project_id,
            ccdash_name=ccdash_name,
            ccdash_type=ccdash_type,
            skillmeat_uuid=artifact.artifact_uuid,
            content_hash=artifact.content_hash,
            match_tier=match_tier,
            confidence=round(confidence, 4),
            metadata=metadata,
        )

    def _unresolved_result(
        self,
        *,
        project_id: str,
        ccdash_name: str,
        ccdash_type: str,
        unresolved_reason: str,
        best_candidate: SnapshotArtifact | None = None,
        best_confidence: float | None = None,
        matched_alias: str | None = None,
    ) -> ArtifactIdentityResolution:
        metadata: dict[str, object] = {
            "identity_reconciliation": {"recommended": True, "status": "pending"},
        }
        if best_candidate is not None:
            metadata["best_candidate_uuid"] = best_candidate.artifact_uuid
            metadata["best_candidate_name"] = best_candidate.display_name
        if best_confidence is not None:
            metadata["best_confidence"] = round(best_confidence, 4)
        if matched_alias:
            metadata["matched_alias"] = matched_alias
        return ArtifactIdentityResolution(
            project_id=project_id,
            ccdash_name=ccdash_name,
            ccdash_type=ccdash_type,
            match_tier="unresolved",
            confidence=None,
            unresolved_reason=unresolved_reason,
            metadata=metadata,
        )

    async def _persist_result(
        self,
        result: ArtifactIdentityResolution,
    ) -> ArtifactIdentityResolution:
        await self.repository.save_identity_mapping(
            {
                "project_id": result.project_id,
                "ccdash_name": result.ccdash_name,
                "ccdash_type": result.ccdash_type,
                "skillmeat_uuid": result.skillmeat_uuid,
                "content_hash": result.content_hash,
                "match_tier": result.match_tier,
                "confidence": result.confidence,
                "resolved_at": _iso_now() if result.resolved else "",
                "unresolved_reason": result.unresolved_reason,
            }
        )
        return result


def _artifact_aliases(artifact: SnapshotArtifact) -> tuple[str, ...]:
    aliases = [artifact.display_name, artifact.external_id]
    if ":" in artifact.external_id:
        aliases.append(artifact.external_id.rsplit(":", 1)[-1])
    aliases.extend(artifact.tags)
    return tuple(dict.fromkeys(alias.strip() for alias in aliases if alias.strip()))


def _alias_score(observed_name: str, alias: str) -> float:
    observed = _normalize_alias(observed_name)
    candidate = _normalize_alias(alias)
    if not observed or not candidate:
        return 0.0
    if observed == candidate:
        return 1.0

    shorter, longer = sorted((observed, candidate), key=len)
    ratio = SequenceMatcher(None, observed, candidate).ratio()
    if len(shorter) >= 5 and longer.startswith(shorter):
        return max(ratio, 0.9)
    return ratio


def _normalize_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _looks_like_hash(value: str) -> bool:
    stripped = value.strip().lower()
    if stripped.startswith("sha256:"):
        stripped = stripped.removeprefix("sha256:")
    return bool(re.fullmatch(r"[a-f0-9]{64}", stripped))


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
