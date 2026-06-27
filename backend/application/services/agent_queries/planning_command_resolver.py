"""Shared planning command resolution for command-center surfaces."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from backend.application.services.agent_queries.models import (
    PlanningCommandAlternativeDTO,
    PlanningCommandCapabilityDTO,
    PlanningCommandResolutionDTO,
    PlanningCommandRuleId,
    PlanningCommandTargetArtifactDTO,
)
from backend.models import Feature, FeaturePhase, LinkedDocument


_ACTIVE_PHASE_STATUSES = {"active", "in-progress", "in_progress", "review"}
_TERMINAL_PHASE_STATUSES = {"done", "completed", "complete", "deferred", "cancelled", "canceled"}
_REVIEW_READY_FEATURE_STATUSES = {"review", "review-ready", "review_ready"}


@dataclass(frozen=True)
class _Artifact:
    path: str = ""
    doc_type: str = ""
    title: str = ""
    artifact_id: str = ""


@dataclass(frozen=True)
class _CommandCandidate:
    rule_id: PlanningCommandRuleId
    command: str
    confidence: float
    rationale: str
    target_artifact: PlanningCommandTargetArtifactDTO | None = None
    phase: int | None = None
    warnings: list[str] = field(default_factory=list)
    required_capabilities: list[PlanningCommandCapabilityDTO] = field(default_factory=list)
    alternatives: list[PlanningCommandAlternativeDTO] = field(default_factory=list)


class PlanningCommandResolver:
    """Resolve deterministic next commands for planning work items.

    The resolver is transport-neutral so REST, CLI, MCP, and future aggregate
    query services can share the same PCC-CMD-* rule semantics.
    """

    def __init__(
        self,
        *,
        execute_contract_supported: bool = False,
    ) -> None:
        self._execute_contract_supported = execute_contract_supported

    def resolve(
        self,
        feature: Feature,
        documents: Sequence[LinkedDocument | Any] | None = None,
        *,
        tier: int | str | None = None,
        execute_contract_supported: bool | None = None,
    ) -> PlanningCommandResolutionDTO:
        """Return the primary command recommendation and explainable alternatives."""

        docs = self._normalize_documents(documents if documents is not None else feature.linkedDocs)
        plan_doc = self._first_doc(docs, self._is_plan_doc)
        seed_doc = self._planning_seed_doc(docs)
        spike_doc = self._first_doc(docs, self._is_spike_doc)
        exploration_doc = self._first_doc(docs, self._is_exploration_doc)
        contract_doc = self._first_doc(docs, self._is_contract_doc)
        feature_id = str(feature.id or "").strip()

        candidates: list[_CommandCandidate] = []

        if spike_doc is not None or self._feature_signals(feature, {"spike-needed", "spike_needed", "spike"}):
            target = self._target_for(spike_doc)
            command_arg = target.path if target is not None and target.path else feature_id
            warnings = [] if spike_doc is not None else ["Spike work is signaled, but no linked spike charter was found."]
            candidates.append(
                self._candidate(
                    "PCC-CMD-001",
                    f"/plan:spike {command_arg}",
                    0.94 if spike_doc is not None else 0.72,
                    "A spike charter or spike-needed signal is present, so run the spike workflow first.",
                    target,
                    warnings=warnings,
                    capabilities=[self._capability("workflow:/plan:spike")],
                )
            )

        if exploration_doc is not None or self._feature_signals(feature, {"explore-needed", "explore_needed", "exploration"}):
            target = self._target_for(exploration_doc)
            command_arg = target.path if target is not None and target.path else feature_id
            warnings = [] if exploration_doc is not None else ["Exploration is signaled, but no linked exploration charter was found."]
            candidates.append(
                self._candidate(
                    "PCC-CMD-002",
                    f"/plan:explore {command_arg}",
                    0.92 if exploration_doc is not None else 0.7,
                    "An exploration charter or feasibility signal recommends more exploration.",
                    target,
                    warnings=warnings,
                    capabilities=[self._capability("workflow:/plan:explore")],
                )
            )

        if plan_doc is None and seed_doc is not None:
            target = self._target_for(seed_doc)
            candidates.append(
                self._candidate(
                    "PCC-CMD-003",
                    f"/plan:plan-feature {target.path if target is not None else feature_id}",
                    0.96,
                    "A planning seed artifact exists but no implementation plan was found.",
                    target,
                    capabilities=[self._capability("workflow:/plan:plan-feature")],
                )
            )

        if contract_doc is not None and (plan_doc is None or self._is_tier_one(feature, tier)):
            candidates.append(
                self._contract_candidate(
                    feature_id,
                    contract_doc,
                    plan_doc,
                    supported=(
                        self._execute_contract_supported
                        if execute_contract_supported is None
                        else execute_contract_supported
                    ),
                )
            )

        phase_rows = self._phase_rows(feature.phases)
        active_phase = self._active_phase(phase_rows)
        next_phase = self._next_available_phase(phase_rows)
        completed_phase_count = sum(1 for _number, phase in phase_rows if self._phase_is_complete(phase))
        all_phases_terminal = bool(phase_rows) and all(self._phase_is_terminal(phase) for _number, phase in phase_rows)
        feature_status = self._normalized_status(getattr(feature, "status", ""))

        if all_phases_terminal or (
            feature_status in _REVIEW_READY_FEATURE_STATUSES and active_phase is None
        ):
            candidates.append(
                self._candidate(
                    "PCC-CMD-008",
                    f"/dev:complete-user-story {feature_id}",
                    0.9 if all_phases_terminal else 0.84,
                    "All phases are complete or the feature is review-ready.",
                    None,
                    capabilities=[self._capability("workflow:/dev:complete-user-story")],
                )
            )

        if plan_doc is not None and active_phase is not None:
            target = self._target_for(plan_doc)
            candidates.append(
                self._candidate(
                    "PCC-CMD-006",
                    f"/dev:execute-phase {active_phase} {target.path if target is not None else feature_id}",
                    0.9,
                    "A phase is active or in review, so resume that phase.",
                    target,
                    phase=active_phase,
                    capabilities=[self._capability("workflow:/dev:execute-phase")],
                )
            )

        if plan_doc is not None and next_phase is not None:
            target = self._target_for(plan_doc)
            candidates.append(
                self._candidate(
                    "PCC-CMD-007",
                    f"/dev:execute-phase {next_phase} {target.path if target is not None else feature_id}",
                    0.9,
                    "A completed phase was found and the next phase is available.",
                    target,
                    phase=next_phase,
                    capabilities=[self._capability("workflow:/dev:execute-phase")],
                )
            )

        if plan_doc is not None and completed_phase_count == 0:
            target = self._target_for(plan_doc)
            candidates.append(
                self._candidate(
                    "PCC-CMD-005",
                    f"/dev:execute-phase 1 {target.path if target is not None else feature_id}",
                    0.92,
                    "An implementation plan exists and no completed phases were detected.",
                    target,
                    phase=1,
                    capabilities=[self._capability("workflow:/dev:execute-phase")],
                )
            )

        candidates.append(
            self._candidate(
                "PCC-CMD-009",
                f"/dev:quick-feature {feature_id}",
                0.48 if not docs else 0.62,
                "No higher-confidence planning command could be resolved.",
                None,
                warnings=["No planning artifact found. Use quick-feature fallback."] if not docs else [],
                capabilities=[self._capability("workflow:/dev:quick-feature")],
            )
        )

        return self._finalize(candidates)

    def _contract_candidate(
        self,
        feature_id: str,
        contract_doc: _Artifact,
        plan_doc: _Artifact | None,
        *,
        supported: bool,
    ) -> _CommandCandidate:
        target = self._target_for(contract_doc)
        target_path = target.path if target is not None else feature_id
        unsupported_command = f"/dev:execute-contract {target_path}"
        if supported:
            return self._candidate(
                "PCC-CMD-004",
                unsupported_command,
                0.88,
                "A Tier 1 feature contract is ready and contract execution is supported.",
                target,
                capabilities=[self._capability("workflow:/dev:execute-contract")],
            )

        fallback_target = self._target_for(plan_doc)
        fallback_command = (
            f"/dev:execute-phase 1 {fallback_target.path}"
            if fallback_target is not None and fallback_target.path
            else f"/dev:quick-feature {feature_id}"
        )
        unsupported_warning = "/dev:execute-contract is not present in the current command mappings."
        unsupported_capability = self._capability(
            "workflow:/dev:execute-contract",
            supported=False,
            warning=unsupported_warning,
            fallback_command=fallback_command,
        )
        fallback_capability = self._capability(
            "workflow:/dev:execute-phase" if fallback_target is not None else "workflow:/dev:quick-feature"
        )
        unsupported_alt = PlanningCommandAlternativeDTO(
            rule_id="PCC-CMD-004",
            command=unsupported_command,
            confidence=0.58,
            rationale="Contract execution is capability-gated until command support is confirmed.",
            target_artifact_path=target.path if target is not None else "",
            target_artifact_doc_type=target.doc_type if target is not None else "",
            warnings=[unsupported_warning],
            required_capabilities=[unsupported_capability],
        )
        return self._candidate(
            "PCC-CMD-004",
            fallback_command,
            0.78,
            "A Tier 1 contract is ready, but contract execution is unsupported; using the existing execution fallback.",
            fallback_target or target,
            phase=1 if fallback_target is not None else None,
            warnings=[unsupported_warning],
            capabilities=[unsupported_capability, fallback_capability],
            alternatives=[unsupported_alt],
        )

    def _candidate(
        self,
        rule_id: PlanningCommandRuleId,
        command: str,
        confidence: float,
        rationale: str,
        target_artifact: PlanningCommandTargetArtifactDTO | None,
        *,
        phase: int | None = None,
        warnings: list[str] | None = None,
        capabilities: list[PlanningCommandCapabilityDTO] | None = None,
        alternatives: list[PlanningCommandAlternativeDTO] | None = None,
    ) -> _CommandCandidate:
        return _CommandCandidate(
            rule_id=rule_id,
            command=command,
            confidence=confidence,
            rationale=rationale,
            target_artifact=target_artifact,
            phase=phase,
            warnings=list(warnings or []),
            required_capabilities=list(capabilities or []),
            alternatives=list(alternatives or []),
        )

    def _finalize(self, candidates: Sequence[_CommandCandidate]) -> PlanningCommandResolutionDTO:
        primary = candidates[0]
        alternatives: list[PlanningCommandAlternativeDTO] = []
        seen_commands = {primary.command}
        for explicit in primary.alternatives:
            if explicit.command in seen_commands:
                continue
            alternatives.append(explicit)
            seen_commands.add(explicit.command)
        for candidate in candidates[1:]:
            if candidate.command in seen_commands:
                continue
            alternatives.append(self._alternative_for(candidate))
            seen_commands.add(candidate.command)

        target = primary.target_artifact
        return PlanningCommandResolutionDTO(
            command=primary.command,
            rule_id=primary.rule_id,
            confidence=primary.confidence,
            rationale=primary.rationale,
            target_artifact_path=target.path if target is not None else "",
            target_artifact_doc_type=target.doc_type if target is not None else "",
            target_artifact=target,
            phase=primary.phase,
            warnings=primary.warnings,
            alternatives=alternatives,
            required_capabilities=primary.required_capabilities,
        )

    def _alternative_for(self, candidate: _CommandCandidate) -> PlanningCommandAlternativeDTO:
        target = candidate.target_artifact
        return PlanningCommandAlternativeDTO(
            rule_id=candidate.rule_id,
            command=candidate.command,
            confidence=candidate.confidence,
            rationale=candidate.rationale,
            target_artifact_path=target.path if target is not None else "",
            target_artifact_doc_type=target.doc_type if target is not None else "",
            phase=candidate.phase,
            warnings=candidate.warnings,
            required_capabilities=candidate.required_capabilities,
        )

    def _capability(
        self,
        name: str,
        *,
        supported: bool = True,
        required: bool = True,
        warning: str = "",
        fallback_command: str = "",
    ) -> PlanningCommandCapabilityDTO:
        return PlanningCommandCapabilityDTO(
            name=name,
            supported=supported,
            required=required,
            warning=warning,
            fallback_command=fallback_command,
        )

    def _target_for(self, doc: _Artifact | None) -> PlanningCommandTargetArtifactDTO | None:
        if doc is None:
            return None
        return PlanningCommandTargetArtifactDTO(
            path=doc.path,
            doc_type=doc.doc_type,
            title=doc.title,
            source_ref=doc.artifact_id or doc.path,
        )

    def _normalize_documents(self, documents: Iterable[LinkedDocument | Any]) -> list[_Artifact]:
        artifacts: list[_Artifact] = []
        for doc in documents:
            path = str(
                getattr(doc, "filePath", "")
                or getattr(doc, "file_path", "")
                or getattr(doc, "path", "")
                or ""
            ).strip()
            doc_type = self._normalize_doc_type(
                getattr(doc, "docType", "") or getattr(doc, "doc_type", "") or ""
            )
            title = str(getattr(doc, "title", "") or path or "").strip()
            artifact_id = str(
                getattr(doc, "id", "")
                or getattr(doc, "artifact_id", "")
                or getattr(doc, "source_ref", "")
                or path
                or title
            ).strip()
            if not any((path, doc_type, title, artifact_id)):
                continue
            artifacts.append(_Artifact(path=path, doc_type=doc_type, title=title, artifact_id=artifact_id))
        return artifacts

    def _first_doc(self, docs: Sequence[_Artifact], predicate: Any) -> _Artifact | None:
        matches = [doc for doc in docs if predicate(doc)]
        if not matches:
            return None
        return sorted(matches, key=lambda doc: (not bool(doc.path), doc.path, doc.title))[0]

    def _planning_seed_doc(self, docs: Sequence[_Artifact]) -> _Artifact | None:
        priority = {"prd": 0, "spec": 1, "design_spec": 1, "design_doc": 1, "report": 2}
        matches = [doc for doc in docs if doc.doc_type in priority]
        if not matches:
            return None
        return sorted(matches, key=lambda doc: (priority[doc.doc_type], doc.path, doc.title))[0]

    def _is_plan_doc(self, doc: _Artifact) -> bool:
        return doc.doc_type == "implementation_plan" or "/implementation_plans/" in doc.path.lower()

    def _is_spike_doc(self, doc: _Artifact) -> bool:
        haystack = f"{doc.doc_type} {doc.path} {doc.title}".lower()
        return doc.doc_type == "spike" or "/spikes/" in haystack or "spike charter" in haystack

    def _is_exploration_doc(self, doc: _Artifact) -> bool:
        haystack = f"{doc.doc_type} {doc.path} {doc.title}".lower()
        return (
            doc.doc_type in {"exploration", "exploration_charter", "feasibility", "feasibility_brief"}
            or "exploration-charter" in haystack
            or "feasibility" in haystack
        )

    def _is_contract_doc(self, doc: _Artifact) -> bool:
        haystack = f"{doc.doc_type} {doc.path} {doc.title}".lower()
        return (
            doc.doc_type in {"contract", "feature_contract", "feature-contract"}
            or "/feature_contracts/" in haystack
            or "feature contract" in haystack
        )

    def _normalize_doc_type(self, value: str) -> str:
        return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

    def _feature_signals(self, feature: Feature, signals: set[str]) -> bool:
        tokens = {
            self._normalize_signal(str(tag))
            for tag in getattr(feature, "tags", [])
            if str(tag or "").strip()
        }
        for value in (
            getattr(feature, "status", ""),
            getattr(feature, "executionReadiness", ""),
            getattr(feature, "summary", ""),
            getattr(feature, "description", ""),
        ):
            normalized = self._normalize_signal(str(value or ""))
            if normalized in signals:
                return True
            tokens.add(normalized)
        return bool(tokens & signals)

    def _normalize_signal(self, value: str) -> str:
        return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")

    def _is_tier_one(self, feature: Feature, tier: int | str | None) -> bool:
        if tier is not None:
            token = str(tier).strip().lower().replace("tier", "").replace("-", "").replace("_", "").strip()
            return token in {"1", "one"}
        tags = {self._normalize_signal(str(tag)) for tag in getattr(feature, "tags", [])}
        return bool(tags & {"tier-1", "tier-one", "tier:1"})

    def _phase_rows(self, phases: Sequence[FeaturePhase]) -> list[tuple[int, FeaturePhase]]:
        rows: list[tuple[int, FeaturePhase]] = []
        for phase in phases:
            number = self._phase_number(phase)
            if number is not None:
                rows.append((number, phase))
        return sorted(rows, key=lambda row: row[0])

    def _phase_number(self, phase: FeaturePhase) -> int | None:
        token = str(getattr(phase, "phase", "") or "").strip().lower()
        if token.startswith("phase"):
            token = token.replace("phase", "", 1).strip()
        if token.isdigit():
            return int(token)
        return None

    def _phase_status(self, phase: FeaturePhase) -> str:
        planning_status = getattr(phase, "planningStatus", None)
        effective = getattr(planning_status, "effectiveStatus", "") if planning_status is not None else ""
        return self._normalized_status(effective or getattr(phase, "status", ""))

    def _normalized_status(self, value: str) -> str:
        return str(value or "").strip().lower().replace(" ", "_")

    def _phase_is_complete(self, phase: FeaturePhase) -> bool:
        status = self._phase_status(phase)
        if status in _TERMINAL_PHASE_STATUSES:
            return True
        total = int(getattr(phase, "totalTasks", 0) or 0)
        completed = int(getattr(phase, "completedTasks", 0) or 0)
        progress = int(getattr(phase, "progress", 0) or 0)
        return total > 0 and completed >= total or progress >= 100

    def _phase_is_terminal(self, phase: FeaturePhase) -> bool:
        return self._phase_status(phase) in _TERMINAL_PHASE_STATUSES or self._phase_is_complete(phase)

    def _active_phase(self, phase_rows: Sequence[tuple[int, FeaturePhase]]) -> int | None:
        for number, phase in phase_rows:
            if self._phase_status(phase) in _ACTIVE_PHASE_STATUSES:
                return number
        return None

    def _next_available_phase(self, phase_rows: Sequence[tuple[int, FeaturePhase]]) -> int | None:
        completed = [number for number, phase in phase_rows if self._phase_is_complete(phase)]
        if not completed:
            return None
        next_number = max(completed) + 1
        for number, phase in phase_rows:
            if number == next_number and not self._phase_is_terminal(phase):
                return number
        return None
