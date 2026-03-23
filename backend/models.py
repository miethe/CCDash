"""Pydantic models matching the frontend TypeScript types."""
from __future__ import annotations

from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int


class DateValue(BaseModel):
    value: str = ""
    confidence: Literal["high", "medium", "low"] = "low"
    source: str = ""
    reason: str = ""


class EntityDates(BaseModel):
    createdAt: Optional[DateValue] = None
    updatedAt: Optional[DateValue] = None
    completedAt: Optional[DateValue] = None
    plannedAt: Optional[DateValue] = None
    startedAt: Optional[DateValue] = None
    endedAt: Optional[DateValue] = None
    lastActivityAt: Optional[DateValue] = None


class TimelineEvent(BaseModel):
    id: str
    timestamp: str
    label: str
    kind: str = ""
    confidence: Literal["high", "medium", "low"] = "low"
    source: str = ""
    description: str = ""


# ── Session-related models ──────────────────────────────────────────

class ToolCallInfo(BaseModel):
    id: Optional[str] = None
    name: str = ""
    args: str = ""
    output: Optional[str] = None
    status: str = "success"
    isError: bool = False


class SkillDetails(BaseModel):
    name: str = ""
    description: str = ""
    version: str = "1.0"


class SessionLog(BaseModel):
    id: str
    timestamp: str
    speaker: str  # "user" | "agent" | "system"
    type: str  # "message" | "tool" | "skill" | "thought" | "system" | "command" | "subagent_start"
    content: str = ""
    agentName: Optional[str] = None
    linkedSessionId: Optional[str] = None
    relatedToolCallId: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    toolCall: Optional[ToolCallInfo] = None
    skillDetails: Optional[SkillDetails] = None
    subagentThread: Optional[list[SessionLog]] = None


class SessionFileUpdate(BaseModel):
    filePath: str
    additions: int = 0
    deletions: int = 0
    commits: list[str] = Field(default_factory=list)
    agentName: str = ""
    action: str = "update"
    fileType: str = "Other"
    timestamp: str = ""
    sourceLogId: Optional[str] = None
    sourceToolName: Optional[str] = None
    threadSessionId: Optional[str] = None
    rootSessionId: Optional[str] = None


class SessionArtifact(BaseModel):
    id: str
    title: str
    type: str = "document"
    description: str = ""
    source: str = ""
    url: Optional[str] = None
    sourceLogId: Optional[str] = None
    sourceToolName: Optional[str] = None


class ToolUsage(BaseModel):
    name: str
    count: int = 0
    successRate: float = 1.0
    totalMs: int = 0


class SessionModelInfo(BaseModel):
    raw: str = ""
    modelDisplayName: str = ""
    modelProvider: str = ""
    modelFamily: str = ""
    modelVersion: str = ""


class SessionPlatformTransition(BaseModel):
    timestamp: str = ""
    fromVersion: str = ""
    toVersion: str = ""
    sourceLogId: Optional[str] = None


class ImpactPoint(BaseModel):
    timestamp: str
    label: str = ""
    type: str = "info"  # "info" | "warning" | "error" | "success"
    locAdded: int = 0
    locDeleted: int = 0
    fileCount: int = 0
    testPassCount: int = 0
    testFailCount: int = 0


class SessionMetadataField(BaseModel):
    id: str
    label: str
    value: str


class SessionMetadata(BaseModel):
    sessionTypeId: str = ""
    sessionTypeLabel: str = ""
    mappingId: str = ""
    relatedCommand: str = ""
    relatedPhases: list[str] = Field(default_factory=list)
    relatedFilePath: str = ""
    fields: list[SessionMetadataField] = Field(default_factory=list)


class AgentSession(BaseModel):
    id: str
    title: str = ""
    taskId: str = ""
    status: str = "completed"
    model: str = ""
    modelDisplayName: str = ""
    modelProvider: str = ""
    modelFamily: str = ""
    modelVersion: str = ""
    modelsUsed: list[SessionModelInfo] = Field(default_factory=list)
    platformType: str = "Claude Code"
    platformVersion: str = ""
    platformVersions: list[str] = Field(default_factory=list)
    platformVersionTransitions: list[SessionPlatformTransition] = Field(default_factory=list)
    agentsUsed: list[str] = Field(default_factory=list)
    skillsUsed: list[str] = Field(default_factory=list)
    toolSummary: list[str] = Field(default_factory=list)
    sessionType: str = ""
    parentSessionId: Optional[str] = None
    rootSessionId: str = ""
    agentId: Optional[str] = None
    threadKind: str = ""
    conversationFamilyId: str = ""
    contextInheritance: str = ""
    forkParentSessionId: Optional[str] = None
    forkPointLogId: Optional[str] = None
    forkPointEntryUuid: Optional[str] = None
    forkPointParentEntryUuid: Optional[str] = None
    forkDepth: int = 0
    forkCount: int = 0
    durationSeconds: int = 0
    tokensIn: int = 0
    tokensOut: int = 0
    modelIOTokens: int = 0
    cacheCreationInputTokens: int = 0
    cacheReadInputTokens: int = 0
    cacheInputTokens: int = 0
    observedTokens: int = 0
    toolReportedTokens: int = 0
    toolResultInputTokens: int = 0
    toolResultOutputTokens: int = 0
    toolResultCacheCreationInputTokens: int = 0
    toolResultCacheReadInputTokens: int = 0
    cacheShare: float = 0.0
    outputShare: float = 0.0
    currentContextTokens: int = 0
    contextWindowSize: int = 0
    contextUtilizationPct: float = 0.0
    contextMeasurementSource: str = ""
    contextMeasuredAt: str = ""
    totalCost: float = 0.0
    reportedCostUsd: Optional[float] = None
    recalculatedCostUsd: Optional[float] = None
    displayCostUsd: Optional[float] = None
    costProvenance: Literal["reported", "recalculated", "estimated", "unknown"] = "unknown"
    costConfidence: float = 0.0
    costMismatchPct: Optional[float] = None
    pricingModelSource: str = ""
    startedAt: str = ""
    endedAt: str = ""
    createdAt: str = ""
    updatedAt: str = ""
    qualityRating: int = 0
    frictionRating: int = 0
    gitCommitHash: Optional[str] = None
    gitCommitHashes: list[str] = Field(default_factory=list)
    gitAuthor: Optional[str] = None
    gitBranch: Optional[str] = None
    updatedFiles: list[SessionFileUpdate] = Field(default_factory=list)
    linkedArtifacts: list[SessionArtifact] = Field(default_factory=list)
    toolsUsed: list[ToolUsage] = Field(default_factory=list)
    impactHistory: list[ImpactPoint] = Field(default_factory=list)
    logs: list[SessionLog] = Field(default_factory=list)
    sessionMetadata: Optional[SessionMetadata] = None
    thinkingLevel: str = ""
    sessionForensics: dict[str, Any] = Field(default_factory=dict)
    forks: list[dict[str, Any]] = Field(default_factory=list)
    sessionRelationships: list[dict[str, Any]] = Field(default_factory=list)
    derivedSessions: list[dict[str, Any]] = Field(default_factory=list)
    usageEvents: list["SessionUsageEvent"] = Field(default_factory=list)
    usageAttributions: list["SessionUsageAttribution"] = Field(default_factory=list)
    usageAttributionSummary: Optional["SessionUsageAggregateResponse"] = None
    usageAttributionCalibration: Optional["SessionUsageCalibrationSummary"] = None
    dates: EntityDates = Field(default_factory=EntityDates)
    timeline: list[TimelineEvent] = Field(default_factory=list)


SessionUsageTokenFamily = Literal[
    "model_input",
    "model_output",
    "cache_creation_input",
    "cache_read_input",
    "tool_result_input",
    "tool_result_output",
    "tool_result_cache_creation_input",
    "tool_result_cache_read_input",
    "tool_reported_total",
    "relay_mirror_input",
    "relay_mirror_output",
    "relay_mirror_cache_creation_input",
    "relay_mirror_cache_read_input",
]

SessionUsageEntityType = Literal["skill", "agent", "subthread", "command", "artifact", "workflow", "feature"]
SessionUsageAttributionRole = Literal["primary", "supporting"]
SessionUsageAttributionMethod = Literal[
    "explicit_skill_invocation",
    "explicit_subthread_ownership",
    "explicit_agent_ownership",
    "explicit_command_context",
    "explicit_artifact_link",
    "skill_window",
    "artifact_window",
    "workflow_membership",
    "feature_inheritance",
]


class SessionUsageEvent(BaseModel):
    id: str
    projectId: str
    sessionId: str
    rootSessionId: str
    linkedSessionId: str = ""
    sourceLogId: str = ""
    capturedAt: str
    eventKind: str
    model: str = ""
    toolName: str = ""
    agentName: str = ""
    tokenFamily: SessionUsageTokenFamily
    deltaTokens: int = 0
    costUsdModelIO: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionUsageAttribution(BaseModel):
    eventId: str
    entityType: SessionUsageEntityType
    entityId: str
    attributionRole: SessionUsageAttributionRole
    weight: float = 1.0
    method: SessionUsageAttributionMethod
    confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionUsageAggregateRow(BaseModel):
    entityType: SessionUsageEntityType
    entityId: str
    entityLabel: str = ""
    exclusiveTokens: int = 0
    supportingTokens: int = 0
    exclusiveModelIOTokens: int = 0
    exclusiveCacheInputTokens: int = 0
    supportingModelIOTokens: int = 0
    supportingCacheInputTokens: int = 0
    exclusiveCostUsdModelIO: float = 0.0
    supportingCostUsdModelIO: float = 0.0
    eventCount: int = 0
    primaryEventCount: int = 0
    supportingEventCount: int = 0
    sessionCount: int = 0
    averageConfidence: float = 0.0
    methods: list[dict[str, Any]] = Field(default_factory=list)


class SessionUsageAggregateSummary(BaseModel):
    entityCount: int = 0
    sessionCount: int = 0
    eventCount: int = 0
    totalExclusiveTokens: int = 0
    totalSupportingTokens: int = 0
    totalExclusiveModelIOTokens: int = 0
    totalExclusiveCacheInputTokens: int = 0
    totalExclusiveCostUsdModelIO: float = 0.0
    averageConfidence: float = 0.0


class SessionUsageAggregateResponse(BaseModel):
    generatedAt: str = ""
    total: int = 0
    offset: int = 0
    limit: int = 0
    rows: list[SessionUsageAggregateRow] = Field(default_factory=list)
    summary: SessionUsageAggregateSummary = Field(default_factory=SessionUsageAggregateSummary)


class SessionUsageDrilldownRow(BaseModel):
    eventId: str
    sessionId: str
    rootSessionId: str = ""
    linkedSessionId: str = ""
    sessionType: str = ""
    parentSessionId: str = ""
    sourceLogId: str = ""
    capturedAt: str = ""
    eventKind: str = ""
    tokenFamily: SessionUsageTokenFamily
    deltaTokens: int = 0
    costUsdModelIO: float = 0.0
    model: str = ""
    toolName: str = ""
    agentName: str = ""
    entityType: SessionUsageEntityType
    entityId: str
    entityLabel: str = ""
    attributionRole: SessionUsageAttributionRole
    weight: float = 1.0
    method: SessionUsageAttributionMethod
    confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionUsageDrilldownResponse(BaseModel):
    generatedAt: str = ""
    total: int = 0
    offset: int = 0
    limit: int = 0
    items: list[SessionUsageDrilldownRow] = Field(default_factory=list)
    summary: SessionUsageAggregateSummary = Field(default_factory=SessionUsageAggregateSummary)


class SessionUsageCalibrationSummary(BaseModel):
    projectId: str = ""
    sessionCount: int = 0
    eventCount: int = 0
    attributedEventCount: int = 0
    primaryAttributedEventCount: int = 0
    ambiguousEventCount: int = 0
    unattributedEventCount: int = 0
    primaryCoverage: float = 0.0
    supportingCoverage: float = 0.0
    sessionModelIOTokens: int = 0
    exclusiveModelIOTokens: int = 0
    modelIOGap: int = 0
    sessionCacheInputTokens: int = 0
    exclusiveCacheInputTokens: int = 0
    cacheGap: int = 0
    averageConfidence: float = 0.0
    confidenceBands: list[dict[str, Any]] = Field(default_factory=list)
    methodMix: list[dict[str, Any]] = Field(default_factory=list)
    generatedAt: str = ""


class PricingCatalogEntry(BaseModel):
    projectId: str = ""
    platformType: str = ""
    modelId: str = ""
    displayLabel: str = ""
    entryKind: str = "model"
    familyId: str = ""
    contextWindowSize: Optional[int] = None
    inputCostPerMillion: Optional[float] = None
    outputCostPerMillion: Optional[float] = None
    cacheCreationCostPerMillion: Optional[float] = None
    cacheReadCostPerMillion: Optional[float] = None
    speedMultiplierFast: Optional[float] = None
    sourceType: str = "bundled"
    sourceUpdatedAt: str = ""
    overrideLocked: bool = False
    syncStatus: str = "never"
    syncError: str = ""
    derivedFrom: str = ""
    isPersisted: bool = False
    isDetected: bool = False
    isRequiredDefault: bool = False
    canDelete: bool = False
    createdAt: str = ""
    updatedAt: str = ""


class PricingCatalogUpsertRequest(BaseModel):
    platformType: str
    modelId: str = ""
    contextWindowSize: Optional[int] = None
    inputCostPerMillion: Optional[float] = None
    outputCostPerMillion: Optional[float] = None
    cacheCreationCostPerMillion: Optional[float] = None
    cacheReadCostPerMillion: Optional[float] = None
    speedMultiplierFast: Optional[float] = None
    sourceType: str = "manual"
    sourceUpdatedAt: str = ""
    overrideLocked: bool = False
    syncStatus: str = "manual"
    syncError: str = ""


class PricingCatalogSyncResponse(BaseModel):
    projectId: str = ""
    platformType: str = ""
    syncedAt: str = ""
    updatedEntries: int = 0
    warnings: list[str] = Field(default_factory=list)
    entries: list[PricingCatalogEntry] = Field(default_factory=list)


class SessionCostCalibrationProvenanceCount(BaseModel):
    provenance: str = "unknown"
    count: int = 0
    displayCostUsd: float = 0.0


class SessionCostCalibrationMismatchBand(BaseModel):
    band: str = "unknown"
    count: int = 0


class SessionCostCalibrationGroup(BaseModel):
    label: str = ""
    sessionCount: int = 0
    comparableSessionCount: int = 0
    avgMismatchPct: float = 0.0
    maxMismatchPct: float = 0.0
    avgConfidence: float = 0.0
    displayCostUsd: float = 0.0
    reportedCostUsd: float = 0.0
    recalculatedCostUsd: float = 0.0
    provenanceCounts: list[SessionCostCalibrationProvenanceCount] = Field(default_factory=list)


class SessionCostCalibrationSummary(BaseModel):
    projectId: str = ""
    sessionCount: int = 0
    comparableSessionCount: int = 0
    reportedSessionCount: int = 0
    recalculatedSessionCount: int = 0
    mismatchSessionCount: int = 0
    comparableCoveragePct: float = 0.0
    avgCostConfidence: float = 0.0
    avgMismatchPct: float = 0.0
    maxMismatchPct: float = 0.0
    totalDisplayCostUsd: float = 0.0
    totalReportedCostUsd: float = 0.0
    totalRecalculatedCostUsd: float = 0.0
    provenanceCounts: list[SessionCostCalibrationProvenanceCount] = Field(default_factory=list)
    mismatchBands: list[SessionCostCalibrationMismatchBand] = Field(default_factory=list)
    byModel: list[SessionCostCalibrationGroup] = Field(default_factory=list)
    byModelVersion: list[SessionCostCalibrationGroup] = Field(default_factory=list)
    byPlatformVersion: list[SessionCostCalibrationGroup] = Field(default_factory=list)
    generatedAt: str = ""


# ── Document-related models ────────────────────────────────────────

class DocumentFrontmatter(BaseModel):
    tags: list[str] = Field(default_factory=list)
    linkedFeatures: list[str] = Field(default_factory=list)
    linkedFeatureRefs: list["LinkedFeatureRef"] = Field(default_factory=list)
    blockedBy: list[str] = Field(default_factory=list)
    sequenceOrder: Optional[int] = None
    linkedSessions: list[str] = Field(default_factory=list)
    linkedTasks: list[str] = Field(default_factory=list)
    lineageFamily: str = ""
    lineageParent: str = ""
    lineageChildren: list[str] = Field(default_factory=list)
    lineageType: str = ""
    version: Optional[str] = None
    commits: list[str] = Field(default_factory=list)
    prs: list[str] = Field(default_factory=list)
    requestLogIds: list[str] = Field(default_factory=list)
    commitRefs: list[str] = Field(default_factory=list)
    prRefs: list[str] = Field(default_factory=list)
    relatedRefs: list[str] = Field(default_factory=list)
    pathRefs: list[str] = Field(default_factory=list)
    slugRefs: list[str] = Field(default_factory=list)
    prd: str = ""
    prdRefs: list[str] = Field(default_factory=list)
    sourceDocuments: list[str] = Field(default_factory=list)
    filesAffected: list[str] = Field(default_factory=list)
    filesModified: list[str] = Field(default_factory=list)
    contextFiles: list[str] = Field(default_factory=list)
    integritySignalRefs: list[str] = Field(default_factory=list)
    fieldKeys: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class DocumentTaskCounts(BaseModel):
    total: int = 0
    completed: int = 0
    inProgress: int = 0
    blocked: int = 0


class DocumentMetadata(BaseModel):
    phase: str = ""
    phaseNumber: Optional[int] = None
    overallProgress: Optional[float] = None
    completionEstimate: str = ""
    description: str = ""
    summary: str = ""
    priority: str = ""
    riskLevel: str = ""
    complexity: str = ""
    track: str = ""
    timelineEstimate: str = ""
    targetRelease: str = ""
    milestone: str = ""
    decisionStatus: str = ""
    executionReadiness: str = ""
    testImpact: str = ""
    primaryDocRole: str = ""
    featureSlug: str = ""
    featureFamily: str = ""
    blockedBy: list[str] = Field(default_factory=list)
    sequenceOrder: Optional[int] = None
    featureVersion: str = ""
    planRef: str = ""
    implementationPlanRef: str = ""
    taskCounts: DocumentTaskCounts = Field(default_factory=DocumentTaskCounts)
    owners: list[str] = Field(default_factory=list)
    contributors: list[str] = Field(default_factory=list)
    reviewers: list[str] = Field(default_factory=list)
    approvers: list[str] = Field(default_factory=list)
    audience: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    linkedTasks: list[str] = Field(default_factory=list)
    requestLogIds: list[str] = Field(default_factory=list)
    commitRefs: list[str] = Field(default_factory=list)
    prRefs: list[str] = Field(default_factory=list)
    sourceDocuments: list[str] = Field(default_factory=list)
    filesAffected: list[str] = Field(default_factory=list)
    filesModified: list[str] = Field(default_factory=list)
    contextFiles: list[str] = Field(default_factory=list)
    integritySignalRefs: list[str] = Field(default_factory=list)
    executionEntrypoints: list[dict[str, Any]] = Field(default_factory=list)
    linkedFeatureRefs: list["LinkedFeatureRef"] = Field(default_factory=list)
    docTypeFields: dict[str, Any] = Field(default_factory=dict)
    featureSlugHint: str = ""
    canonicalPath: str = ""


class DocumentLinkCounts(BaseModel):
    features: int = 0
    tasks: int = 0
    sessions: int = 0
    documents: int = 0


class PlanDocument(BaseModel):
    id: str
    title: str
    filePath: str
    status: str = "active"
    createdAt: str = ""
    updatedAt: str = ""
    completedAt: str = ""
    lastModified: str = ""
    author: str = ""
    docType: str = ""
    category: str = ""
    docSubtype: str = ""
    rootKind: Literal["project_plans", "progress", "document"] = "project_plans"
    canonicalPath: str = ""
    hasFrontmatter: bool = False
    frontmatterType: str = ""
    statusNormalized: str = ""
    featureSlugHint: str = ""
    featureSlugCanonical: str = ""
    prdRef: str = ""
    phaseToken: str = ""
    phaseNumber: Optional[int] = None
    overallProgress: Optional[float] = None
    completionEstimate: str = ""
    description: str = ""
    summary: str = ""
    priority: str = ""
    riskLevel: str = ""
    complexity: str = ""
    track: str = ""
    timelineEstimate: str = ""
    targetRelease: str = ""
    milestone: str = ""
    decisionStatus: str = ""
    executionReadiness: str = ""
    testImpact: str = ""
    primaryDocRole: str = ""
    featureSlug: str = ""
    featureFamily: str = ""
    blockedBy: list[str] = Field(default_factory=list)
    sequenceOrder: Optional[int] = None
    featureVersion: str = ""
    planRef: str = ""
    implementationPlanRef: str = ""
    totalTasks: int = 0
    completedTasks: int = 0
    inProgressTasks: int = 0
    blockedTasks: int = 0
    pathSegments: list[str] = Field(default_factory=list)
    featureCandidates: list[str] = Field(default_factory=list)
    frontmatter: DocumentFrontmatter = Field(default_factory=DocumentFrontmatter)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    linkCounts: DocumentLinkCounts = Field(default_factory=DocumentLinkCounts)
    dates: EntityDates = Field(default_factory=EntityDates)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    content: Optional[str] = None  # markdown body, loaded on demand


# ── Task-related models ────────────────────────────────────────────

class ProjectTask(BaseModel):
    id: str
    title: str
    description: str = ""
    status: str = "backlog"  # backlog | in-progress | review | done | deferred
    owner: str = ""
    lastAgent: str = ""
    cost: float = 0.0
    priority: str = "medium"
    projectType: str = ""
    projectLevel: str = ""
    tags: list[str] = Field(default_factory=list)
    updatedAt: str = ""
    relatedFiles: list[str] = Field(default_factory=list)
    sourceFile: str = ""       # relative path to the progress file this task was parsed from
    sessionId: str = ""        # linked session ID (from frontmatter)
    commitHash: str = ""       # linked git commit hash (from frontmatter)
    featureId: Optional[str] = None
    phaseId: Optional[str] = None


# ── Analytics models ───────────────────────────────────────────────

class AnalyticsMetric(BaseModel):
    name: str
    value: float
    unit: str = ""
    trend: str = "stable"  # "up" | "down" | "stable"


class AlertConfig(BaseModel):
    id: str
    name: str
    metric: str = "total_tokens"  # 'total_tokens' | 'avg_quality' | 'cost_threshold'
    operator: str = ">"  # '>' | '<'
    threshold: float = 0.0
    isActive: bool = True
    scope: str = "session"  # 'session' | 'weekly'


class Notification(BaseModel):
    id: str
    alertId: str = ""
    message: str
    timestamp: str = ""
    isRead: bool = False


# ── Project test config models ─────────────────────────────────────

TestPlatformId = Literal[
    "pytest",
    "jest",
    "playwright",
    "coverage",
    "benchmark",
    "lighthouse",
    "locust",
    "triage",
]


class ProjectTestFlags(BaseModel):
    testVisualizerEnabled: bool = True
    integritySignalsEnabled: bool = True
    liveTestUpdatesEnabled: bool = True
    semanticMappingEnabled: bool = True


class ProjectTestPlatformConfig(BaseModel):
    id: TestPlatformId
    enabled: bool = False
    resultsDir: str = ""
    watch: bool = False
    patterns: list[str] = Field(default_factory=list)


def _default_project_test_platforms() -> list["ProjectTestPlatformConfig"]:
    return [
        ProjectTestPlatformConfig(
            id="pytest",
            enabled=True,
            resultsDir="test-results",
            watch=True,
            patterns=["**/*.xml", "**/junit*.xml", "**/pytest*.xml"],
        ),
        ProjectTestPlatformConfig(
            id="jest",
            enabled=False,
            resultsDir="skillmeat/web",
            watch=True,
            patterns=["**/jest-results*.json", "**/coverage/coverage-final.json"],
        ),
        ProjectTestPlatformConfig(
            id="playwright",
            enabled=False,
            resultsDir="skillmeat/web/test-results",
            watch=True,
            patterns=["**/results.json"],
        ),
        ProjectTestPlatformConfig(
            id="coverage",
            enabled=False,
            resultsDir=".",
            watch=False,
            patterns=["**/coverage.xml", "**/coverage.json", "**/lcov.info", "**/coverage-final.json"],
        ),
        ProjectTestPlatformConfig(
            id="benchmark",
            enabled=False,
            resultsDir=".",
            watch=False,
            patterns=["**/benchmark*_results.json", "**/benchmark*.json"],
        ),
        ProjectTestPlatformConfig(
            id="lighthouse",
            enabled=False,
            resultsDir="skillmeat/web/lighthouse-reports",
            watch=False,
            patterns=["**/*.json", "**/*.html"],
        ),
        ProjectTestPlatformConfig(
            id="locust",
            enabled=False,
            resultsDir=".",
            watch=False,
            patterns=["**/locust_report.html", "**/locust_results*.csv"],
        ),
        ProjectTestPlatformConfig(
            id="triage",
            enabled=False,
            resultsDir=".",
            watch=False,
            patterns=["**/test-failures.json", "**/test-failures-summary.txt", "**/test-failures.md"],
        ),
    ]


class ProjectTestConfig(BaseModel):
    flags: ProjectTestFlags = Field(default_factory=ProjectTestFlags)
    platforms: list[ProjectTestPlatformConfig] = Field(default_factory=_default_project_test_platforms)
    autoSyncOnStartup: bool = True
    maxFilesPerScan: int = 500
    maxParseConcurrency: int = 4
    instructionProfile: str = "skillmeat"
    instructionNotes: str = ""


class SkillMeatFeatureFlags(BaseModel):
    stackRecommendationsEnabled: bool = True
    workflowAnalyticsEnabled: bool = True
    usageAttributionEnabled: bool = True
    sessionBlockInsightsEnabled: bool = True


class SkillMeatProjectConfig(BaseModel):
    enabled: bool = False
    baseUrl: str = ""
    webBaseUrl: str = ""
    projectId: str = ""
    collectionId: str = ""
    aaaEnabled: bool = False
    apiKey: str = ""
    requestTimeoutSeconds: float = 5.0
    featureFlags: SkillMeatFeatureFlags = Field(default_factory=SkillMeatFeatureFlags)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_workspace_id(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        collection_id = str(migrated.get("collectionId") or "").strip()
        legacy_workspace_id = str(migrated.get("workspaceId") or "").strip()
        if not collection_id and legacy_workspace_id:
            migrated["collectionId"] = legacy_workspace_id
        migrated.pop("workspaceId", None)
        return migrated


PathSourceKind = Literal["project_root", "github_repo", "filesystem"]
ProjectPathField = Literal["root", "plan_docs", "sessions", "progress"]


class GitRepoRef(BaseModel):
    provider: Literal["github"] = "github"
    repoUrl: str = ""
    repoSlug: str = ""
    branch: str = ""
    repoSubpath: str = ""
    writeEnabled: bool = False


class ProjectPathReference(BaseModel):
    field: ProjectPathField
    sourceKind: PathSourceKind = "filesystem"
    displayValue: str = ""
    filesystemPath: str = ""
    relativePath: str = ""
    repoRef: Optional[GitRepoRef] = None

    @model_validator(mode="after")
    def _validate_source_shape(self) -> "ProjectPathReference":
        if self.field == "root" and self.sourceKind == "project_root":
            raise ValueError("The root path cannot inherit from project_root.")

        if self.sourceKind == "project_root":
            if self.repoRef is not None:
                raise ValueError("project_root references cannot include repoRef.")
            if self.filesystemPath.strip():
                raise ValueError("project_root references cannot include filesystemPath.")
            if self.field != "root" and not self.relativePath.strip():
                raise ValueError("project_root references require relativePath.")
        elif self.sourceKind == "filesystem":
            if self.repoRef is not None:
                raise ValueError("filesystem references cannot include repoRef.")
        elif self.sourceKind == "github_repo":
            if self.repoRef is None:
                raise ValueError("github_repo references require repoRef.")
            if self.filesystemPath.strip():
                raise ValueError("github_repo references cannot include filesystemPath.")

        return self


class ProjectPathConfig(BaseModel):
    root: ProjectPathReference = Field(
        default_factory=lambda: ProjectPathReference(field="root", sourceKind="filesystem")
    )
    planDocs: ProjectPathReference = Field(
        default_factory=lambda: ProjectPathReference(
            field="plan_docs",
            sourceKind="project_root",
            relativePath="docs/project_plans/",
            displayValue="docs/project_plans/",
        )
    )
    sessions: ProjectPathReference = Field(
        default_factory=lambda: ProjectPathReference(field="sessions", sourceKind="filesystem")
    )
    progress: ProjectPathReference = Field(
        default_factory=lambda: ProjectPathReference(
            field="progress",
            sourceKind="project_root",
            relativePath="progress",
            displayValue="progress",
        )
    )

    @model_validator(mode="after")
    def _validate_fields(self) -> "ProjectPathConfig":
        if self.root.field != "root":
            raise ValueError("pathConfig.root must target the root field.")
        if self.planDocs.field != "plan_docs":
            raise ValueError("pathConfig.planDocs must target the plan_docs field.")
        if self.sessions.field != "sessions":
            raise ValueError("pathConfig.sessions must target the sessions field.")
        if self.progress.field != "progress":
            raise ValueError("pathConfig.progress must target the progress field.")
        return self


class GitHubIntegrationSettings(BaseModel):
    enabled: bool = False
    provider: Literal["github"] = "github"
    baseUrl: str = "https://github.com"
    username: str = "git"
    token: str = ""
    cacheRoot: str = ""
    writeEnabled: bool = False


class GitHubIntegrationSettingsUpdateRequest(BaseModel):
    enabled: bool = False
    baseUrl: str = "https://github.com"
    username: str = "git"
    token: str = ""
    cacheRoot: str = ""
    writeEnabled: bool = False


class GitHubIntegrationSettingsResponse(BaseModel):
    enabled: bool = False
    provider: Literal["github"] = "github"
    baseUrl: str = "https://github.com"
    username: str = "git"
    tokenConfigured: bool = False
    maskedToken: str = ""
    cacheRoot: str = ""
    writeEnabled: bool = False


class GitHubProbeResult(BaseModel):
    state: Literal["idle", "success", "warning", "error"] = "idle"
    message: str = ""
    checkedAt: str = ""
    path: str = ""


class GitHubCredentialValidationRequest(BaseModel):
    projectId: str = ""
    settings: Optional[GitHubIntegrationSettingsUpdateRequest] = None


class GitHubCredentialValidationResponse(BaseModel):
    auth: GitHubProbeResult = Field(default_factory=GitHubProbeResult)
    repoAccess: GitHubProbeResult = Field(default_factory=GitHubProbeResult)


class GitHubPathValidationRequest(BaseModel):
    projectId: str = ""
    reference: ProjectPathReference
    rootReference: Optional[ProjectPathReference] = None


class GitHubPathValidationResponse(BaseModel):
    reference: ProjectPathReference
    status: GitHubProbeResult = Field(default_factory=GitHubProbeResult)
    resolvedLocalPath: str = ""


class GitHubWorkspaceRefreshRequest(BaseModel):
    projectId: str = ""
    reference: Optional[ProjectPathReference] = None
    force: bool = False


class GitHubWorkspaceRefreshResponse(BaseModel):
    projectId: str = ""
    status: GitHubProbeResult = Field(default_factory=GitHubProbeResult)
    resolvedLocalPath: str = ""


class GitHubWriteCapabilityRequest(BaseModel):
    projectId: str = ""
    reference: Optional[ProjectPathReference] = None


class GitHubWriteCapabilityResponse(BaseModel):
    projectId: str = ""
    canWrite: bool = False
    status: GitHubProbeResult = Field(default_factory=GitHubProbeResult)


class ProjectResolvedPathDTO(BaseModel):
    field: ProjectPathField
    sourceKind: PathSourceKind
    path: str = ""
    diagnostic: str = ""


class ProjectResolvedPathsDTO(BaseModel):
    projectId: str = ""
    root: ProjectResolvedPathDTO
    planDocs: ProjectResolvedPathDTO
    sessions: ProjectResolvedPathDTO
    progress: ProjectResolvedPathDTO


# ── Project model ──────────────────────────────────────────────────

class Project(BaseModel):
    id: str
    name: str
    path: str
    description: str = ""
    repoUrl: str = ""
    agentPlatforms: list[str] = Field(default_factory=lambda: ["Claude Code"])
    planDocsPath: str = "docs/project_plans/"
    sessionsPath: str = ""       # absolute path to session JSONL files (e.g. ~/.claude/projects/<hash>/)
    progressPath: str = "progress"  # relative to project root
    pathConfig: ProjectPathConfig = Field(default_factory=ProjectPathConfig)
    testConfig: ProjectTestConfig = Field(default_factory=ProjectTestConfig)
    skillMeat: SkillMeatProjectConfig = Field(default_factory=SkillMeatProjectConfig)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_path_config(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        migrated = dict(value)
        if isinstance(migrated.get("pathConfig"), dict):
            return migrated

        root_path = str(migrated.get("path") or "").strip()
        plan_docs_path = str(migrated.get("planDocsPath") or "docs/project_plans/").strip() or "docs/project_plans/"
        sessions_path = str(migrated.get("sessionsPath") or "").strip()
        progress_path = str(migrated.get("progressPath") or "progress").strip() or "progress"

        migrated["pathConfig"] = {
            "root": {
                "field": "root",
                "sourceKind": "filesystem",
                "displayValue": root_path,
                "filesystemPath": root_path,
            },
            "planDocs": {
                "field": "plan_docs",
                "sourceKind": "project_root",
                "displayValue": plan_docs_path,
                "relativePath": plan_docs_path,
            },
            "sessions": {
                "field": "sessions",
                "sourceKind": "filesystem",
                "displayValue": sessions_path,
                "filesystemPath": sessions_path,
            },
            "progress": {
                "field": "progress",
                "sourceKind": "project_root",
                "displayValue": progress_path,
                "relativePath": progress_path,
            },
        }
        return migrated

    @model_validator(mode="after")
    def _derive_legacy_fields(self) -> "Project":
        root_ref = self.pathConfig.root
        if root_ref.sourceKind == "filesystem" and root_ref.filesystemPath.strip():
            self.path = root_ref.filesystemPath.strip()
        elif not self.path.strip():
            self.path = root_ref.displayValue.strip() or self.path

        self.planDocsPath = self._derive_legacy_path(
            self.pathConfig.planDocs,
            fallback=self.planDocsPath,
        )
        self.sessionsPath = self._derive_legacy_path(
            self.pathConfig.sessions,
            fallback=self.sessionsPath,
        )
        self.progressPath = self._derive_legacy_path(
            self.pathConfig.progress,
            fallback=self.progressPath,
        )
        return self

    @staticmethod
    def _derive_legacy_path(reference: ProjectPathReference, *, fallback: str) -> str:
        if reference.sourceKind == "project_root":
            value = reference.relativePath.strip()
            return value or fallback
        if reference.sourceKind == "filesystem":
            value = reference.filesystemPath.strip() or reference.displayValue.strip()
            return value or fallback
        repo_ref = reference.repoRef
        if repo_ref is not None:
            return repo_ref.repoUrl.strip() or reference.displayValue.strip() or fallback
        return reference.displayValue.strip() or fallback


# ── Feature models ─────────────────────────────────────────────────

class LinkedFeatureRef(BaseModel):
    feature: str
    type: str = ""
    source: str = ""
    confidence: Optional[float] = None
    notes: str = ""
    evidence: list[str] = Field(default_factory=list)


class LinkedDocument(BaseModel):
    id: str
    title: str
    filePath: str
    docType: str  # "prd" | "implementation_plan" | "report" | "phase_plan" | "progress" | "design_doc" | "spec"
    category: str = ""
    slug: str = ""
    canonicalSlug: str = ""
    featureFamily: str = ""
    primaryDocRole: str = ""
    blockedBy: list[str] = Field(default_factory=list)
    sequenceOrder: Optional[int] = None
    frontmatterKeys: list[str] = Field(default_factory=list)
    relatedRefs: list[str] = Field(default_factory=list)
    prdRef: str = ""
    lineageFamily: str = ""
    lineageParent: str = ""
    lineageChildren: list[str] = Field(default_factory=list)
    lineageType: str = ""
    linkedFeatures: list[LinkedFeatureRef] = Field(default_factory=list)
    dates: EntityDates = Field(default_factory=EntityDates)
    timeline: list[TimelineEvent] = Field(default_factory=list)


class FeaturePhase(BaseModel):
    id: Optional[str] = None
    phase: str  # "1", "2", "all"
    title: str = ""
    status: str = "backlog"  # backlog | in-progress | review | done | deferred
    progress: int = 0  # 0-100
    totalTasks: int = 0
    completedTasks: int = 0
    deferredTasks: int = 0
    tasks: list[ProjectTask] = Field(default_factory=list)


class FeaturePrimaryDocuments(BaseModel):
    prd: Optional[LinkedDocument] = None
    implementationPlan: Optional[LinkedDocument] = None
    phasePlans: list[LinkedDocument] = Field(default_factory=list)
    progressDocs: list[LinkedDocument] = Field(default_factory=list)
    supportingDocs: list[LinkedDocument] = Field(default_factory=list)


class FeatureDocumentCoverage(BaseModel):
    present: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    countsByType: dict[str, int] = Field(default_factory=dict)
    coverageScore: float = 0.0


class FeatureQualitySignals(BaseModel):
    blockerCount: int = 0
    atRiskTaskCount: int = 0
    integritySignalRefs: list[str] = Field(default_factory=list)
    reportFindingsBySeverity: dict[str, int] = Field(default_factory=dict)
    testImpact: str = ""
    hasBlockingSignals: bool = False


class FeatureDependencyEvidence(BaseModel):
    dependencyFeatureId: str = ""
    dependencyFeatureName: str = ""
    dependencyStatus: str = ""
    dependencyCompletionEvidence: list[str] = Field(default_factory=list)
    blockingDocumentIds: list[str] = Field(default_factory=list)
    blockingReason: str = ""
    resolved: bool = False
    state: Literal["complete", "blocked", "blocked_unknown"] = "blocked_unknown"


class FeatureDependencyState(BaseModel):
    state: Literal["unblocked", "blocked", "blocked_unknown", "ready_after_dependencies"] = "unblocked"
    dependencyCount: int = 0
    resolvedDependencyCount: int = 0
    blockedDependencyCount: int = 0
    unknownDependencyCount: int = 0
    blockingFeatureIds: list[str] = Field(default_factory=list)
    blockingDocumentIds: list[str] = Field(default_factory=list)
    firstBlockingDependencyId: str = ""
    blockingReason: str = ""
    completionEvidence: list[str] = Field(default_factory=list)
    dependencies: list[FeatureDependencyEvidence] = Field(default_factory=list)


class FeatureFamilyItem(BaseModel):
    featureId: str
    featureName: str = ""
    featureStatus: str = ""
    featureFamily: str = ""
    sequenceOrder: Optional[int] = None
    familyIndex: int = 0
    totalFamilyItems: int = 0
    isCurrent: bool = False
    isSequenced: bool = True
    isBlocked: bool = False
    isBlockedUnknown: bool = False
    isExecutable: bool = False
    dependencyState: FeatureDependencyState = Field(default_factory=FeatureDependencyState)
    primaryDocId: str = ""
    primaryDocPath: str = ""


class FeatureFamilyPosition(BaseModel):
    familyKey: str = ""
    currentIndex: int = 0
    sequencedIndex: int = 0
    totalItems: int = 0
    sequencedItems: int = 0
    unsequencedItems: int = 0
    display: str = ""
    currentItemId: str = ""
    nextItemId: str = ""
    nextItemLabel: str = ""


class FeatureFamilySummary(BaseModel):
    featureFamily: str = ""
    totalItems: int = 0
    sequencedItems: int = 0
    unsequencedItems: int = 0
    currentFeatureId: str = ""
    currentFeatureName: str = ""
    currentPosition: int = 0
    currentSequencedPosition: int = 0
    nextRecommendedFeatureId: str = ""
    nextRecommendedFamilyItem: Optional[FeatureFamilyItem] = None
    items: list[FeatureFamilyItem] = Field(default_factory=list)


class ExecutionGateState(BaseModel):
    state: Literal[
        "ready",
        "blocked_dependency",
        "waiting_on_family_predecessor",
        "unknown_dependency_state",
    ] = "ready"
    blockingDependencyId: str = ""
    firstExecutableFamilyItemId: str = ""
    recommendedFamilyItemId: str = ""
    familyPosition: Optional[FeatureFamilyPosition] = None
    dependencyState: FeatureDependencyState = Field(default_factory=FeatureDependencyState)
    familySummary: FeatureFamilySummary = Field(default_factory=FeatureFamilySummary)
    reason: str = ""
    waitingOnFamilyPredecessor: bool = False
    isReady: bool = True


class FeatureExecutionDerivedState(BaseModel):
    dependencyState: FeatureDependencyState = Field(default_factory=FeatureDependencyState)
    familySummary: FeatureFamilySummary = Field(default_factory=FeatureFamilySummary)
    familyPosition: FeatureFamilyPosition = Field(default_factory=FeatureFamilyPosition)
    executionGate: ExecutionGateState = Field(default_factory=ExecutionGateState)
    recommendedFamilyItem: Optional[FeatureFamilyItem] = None


class Feature(BaseModel):
    id: str  # slug, e.g. "discovery-import-fixes-v1"
    name: str
    status: str = "backlog"  # overall: done | deferred | in-progress | review | backlog
    totalTasks: int = 0
    completedTasks: int = 0
    deferredTasks: int = 0
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    summary: str = ""
    priority: str = ""
    riskLevel: str = ""
    complexity: str = ""
    track: str = ""
    timelineEstimate: str = ""
    targetRelease: str = ""
    milestone: str = ""
    owners: list[str] = Field(default_factory=list)
    contributors: list[str] = Field(default_factory=list)
    requestLogIds: list[str] = Field(default_factory=list)
    commitRefs: list[str] = Field(default_factory=list)
    prRefs: list[str] = Field(default_factory=list)
    executionReadiness: str = ""
    testImpact: str = ""
    featureFamily: str = ""
    updatedAt: str = ""
    plannedAt: str = ""
    startedAt: str = ""
    completedAt: str = ""
    linkedDocs: list[LinkedDocument] = Field(default_factory=list)
    linkedFeatures: list[LinkedFeatureRef] = Field(default_factory=list)
    primaryDocuments: FeaturePrimaryDocuments = Field(default_factory=FeaturePrimaryDocuments)
    documentCoverage: FeatureDocumentCoverage = Field(default_factory=FeatureDocumentCoverage)
    qualitySignals: FeatureQualitySignals = Field(default_factory=FeatureQualitySignals)
    dependencyState: Optional[FeatureDependencyState] = None
    blockingFeatures: list[FeatureDependencyEvidence] = Field(default_factory=list)
    familySummary: Optional[FeatureFamilySummary] = None
    familyPosition: Optional[FeatureFamilyPosition] = None
    executionGate: Optional[ExecutionGateState] = None
    nextRecommendedFamilyItem: Optional[FeatureFamilyItem] = None
    phases: list[FeaturePhase] = Field(default_factory=list)
    relatedFeatures: list[str] = Field(default_factory=list)
    dates: EntityDates = Field(default_factory=EntityDates)
    timeline: list[TimelineEvent] = Field(default_factory=list)


SkillMeatDefinitionType = Literal["artifact", "workflow", "context_module", "bundle"]
StackComponentType = Literal["workflow", "agent", "skill", "context_module", "command", "model_policy", "artifact"]
StackComponentStatus = Literal["explicit", "inferred", "resolved", "unresolved"]
DefinitionReferenceStatus = Literal["resolved", "cached", "unresolved"]


class ExecutionRecommendationEvidence(BaseModel):
    id: str
    label: str = ""
    value: str = ""
    sourceType: str = ""
    sourcePath: str = ""


class ExecutionRecommendationOption(BaseModel):
    command: str
    ruleId: str
    confidence: float = 0.0
    explanation: str = ""
    evidenceRefs: list[str] = Field(default_factory=list)


class ExecutionRecommendation(BaseModel):
    primary: ExecutionRecommendationOption
    alternatives: list[ExecutionRecommendationOption] = Field(default_factory=list)
    ruleId: str
    confidence: float = 0.0
    explanation: str = ""
    evidenceRefs: list[str] = Field(default_factory=list)
    evidence: list[ExecutionRecommendationEvidence] = Field(default_factory=list)


class FeatureExecutionWarning(BaseModel):
    section: str
    message: str
    recoverable: bool = True


class FeatureExecutionAnalyticsSummary(BaseModel):
    sessionCount: int = 0
    primarySessionCount: int = 0
    totalSessionCost: float = 0.0
    artifactEventCount: int = 0
    commandEventCount: int = 0
    lastEventAt: str = ""
    modelCount: int = 0


class RecommendedStackDefinitionRef(BaseModel):
    definitionType: str = ""
    externalId: str = ""
    displayName: str = ""
    version: str = ""
    sourceUrl: str = ""
    status: DefinitionReferenceStatus = "unresolved"


class ExecutionArtifactReference(BaseModel):
    key: str = ""
    label: str = ""
    kind: str = ""
    status: str = "unresolved"
    definitionType: str = ""
    externalId: str = ""
    sourceUrl: str = ""
    sourceAttribution: str = ""
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecommendedStackComponent(BaseModel):
    componentType: StackComponentType
    componentKey: str = ""
    label: str = ""
    status: StackComponentStatus = "explicit"
    confidence: float = 0.0
    sourceAttribution: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    definition: Optional[RecommendedStackDefinitionRef] = None
    artifactRef: Optional[ExecutionArtifactReference] = None


class SimilarWorkExample(BaseModel):
    sessionId: str
    featureId: str = ""
    title: str = ""
    workflowRef: str = ""
    similarityScore: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    matchedComponents: list[str] = Field(default_factory=list)
    startedAt: str = ""
    endedAt: str = ""
    totalCost: float = 0.0
    durationSeconds: int = 0
    successScore: float = 0.0
    efficiencyScore: float = 0.0
    qualityScore: float = 0.0
    riskScore: float = 0.0


class StackRecommendationEvidence(BaseModel):
    id: str
    label: str = ""
    summary: str = ""
    sourceType: str = ""
    sourceId: str = ""
    sourcePath: str = ""
    confidence: float = 0.0
    metrics: dict[str, Any] = Field(default_factory=dict)
    similarWork: list[SimilarWorkExample] = Field(default_factory=list)


class RecommendedStack(BaseModel):
    id: str
    label: str = ""
    workflowRef: str = ""
    commandAlignment: str = ""
    confidence: float = 0.0
    sampleSize: int = 0
    successScore: float = 0.0
    efficiencyScore: float = 0.0
    qualityScore: float = 0.0
    riskScore: float = 0.0
    sourceSessionId: str = ""
    sourceFeatureId: str = ""
    explanation: str = ""
    components: list[RecommendedStackComponent] = Field(default_factory=list)


class FeatureExecutionContext(BaseModel):
    feature: Feature
    documents: list[LinkedDocument] = Field(default_factory=list)
    sessions: list[dict[str, Any]] = Field(default_factory=list)
    analytics: FeatureExecutionAnalyticsSummary = Field(default_factory=FeatureExecutionAnalyticsSummary)
    recommendations: ExecutionRecommendation
    dependencyState: Optional[FeatureDependencyState] = None
    familySummary: Optional[FeatureFamilySummary] = None
    familyPosition: Optional[FeatureFamilyPosition] = None
    executionGate: Optional[ExecutionGateState] = None
    recommendedFamilyItem: Optional[FeatureFamilyItem] = None
    warnings: list[FeatureExecutionWarning] = Field(default_factory=list)
    recommendedStack: Optional[RecommendedStack] = None
    stackAlternatives: list[RecommendedStack] = Field(default_factory=list)
    stackEvidence: list[StackRecommendationEvidence] = Field(default_factory=list)
    definitionResolutionWarnings: list[FeatureExecutionWarning] = Field(default_factory=list)
    generatedAt: str = ""

class SkillMeatDefinitionSource(BaseModel):
    id: Optional[int] = None
    projectId: str
    sourceKind: str = "skillmeat"
    enabled: bool = False
    baseUrl: str = ""
    projectMapping: dict[str, Any] = Field(default_factory=dict)
    featureFlags: SkillMeatFeatureFlags = Field(default_factory=SkillMeatFeatureFlags)
    lastSyncedAt: str = ""
    lastSyncStatus: str = "never"
    lastSyncError: str = ""
    createdAt: str = ""
    updatedAt: str = ""


class SkillMeatDefinition(BaseModel):
    id: Optional[int] = None
    projectId: str
    sourceId: Optional[int] = None
    definitionType: SkillMeatDefinitionType
    externalId: str
    displayName: str = ""
    version: str = ""
    sourceUrl: str = ""
    resolutionMetadata: dict[str, Any] = Field(default_factory=dict)
    rawSnapshot: dict[str, Any] = Field(default_factory=dict)
    fetchedAt: str = ""
    createdAt: str = ""
    updatedAt: str = ""


class SkillMeatSyncWarning(BaseModel):
    section: str
    message: str
    recoverable: bool = True


SkillMeatProbeState = Literal["idle", "success", "warning", "error"]


class SkillMeatProbeResult(BaseModel):
    state: SkillMeatProbeState = "idle"
    message: str = ""
    checkedAt: str = ""
    httpStatus: Optional[int] = None


class SkillMeatConfigValidationRequest(BaseModel):
    baseUrl: str = ""
    projectId: str = ""
    aaaEnabled: bool = False
    apiKey: str = ""
    requestTimeoutSeconds: float = 5.0


class SkillMeatConfigValidationResponse(BaseModel):
    baseUrl: SkillMeatProbeResult = Field(default_factory=SkillMeatProbeResult)
    projectMapping: SkillMeatProbeResult = Field(default_factory=SkillMeatProbeResult)
    auth: SkillMeatProbeResult = Field(default_factory=SkillMeatProbeResult)


class SkillMeatSyncRequest(BaseModel):
    projectId: str = ""


class SkillMeatDefinitionSyncResponse(BaseModel):
    projectId: str
    source: SkillMeatDefinitionSource
    totalDefinitions: int = 0
    countsByType: dict[str, int] = Field(default_factory=dict)
    fetchedAt: str = ""
    warnings: list[SkillMeatSyncWarning] = Field(default_factory=list)


class SessionStackComponent(BaseModel):
    id: Optional[int] = None
    observationId: Optional[int] = None
    projectId: str
    componentType: StackComponentType
    componentKey: str = ""
    status: StackComponentStatus = "explicit"
    confidence: float = 0.0
    externalDefinitionId: Optional[int] = None
    externalDefinitionType: str = ""
    externalDefinitionExternalId: str = ""
    sourceAttribution: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    createdAt: str = ""
    updatedAt: str = ""


class SessionStackObservation(BaseModel):
    id: Optional[int] = None
    projectId: str
    sessionId: str
    featureId: str = ""
    workflowRef: str = ""
    confidence: float = 0.0
    source: str = "backfill"
    evidence: dict[str, Any] = Field(default_factory=dict)
    components: list[SessionStackComponent] = Field(default_factory=list)
    createdAt: str = ""
    updatedAt: str = ""


class SkillMeatObservationBackfillRequest(BaseModel):
    projectId: str = ""
    limit: int = Field(default=200, ge=1, le=5000)
    forceRecompute: bool = False


class SkillMeatObservationBackfillResponse(BaseModel):
    projectId: str
    sessionsProcessed: int = 0
    observationsStored: int = 0
    skippedSessions: int = 0
    resolvedComponents: int = 0
    unresolvedComponents: int = 0
    generatedAt: str = ""
    warnings: list[SkillMeatSyncWarning] = Field(default_factory=list)


class SkillMeatRefreshResponse(BaseModel):
    projectId: str
    sync: SkillMeatDefinitionSyncResponse
    backfill: SkillMeatObservationBackfillResponse | None = None


EffectivenessScopeType = Literal["workflow", "effective_workflow", "agent", "skill", "context_module", "bundle", "stack"]


class EffectivenessMetricDefinition(BaseModel):
    id: Literal["successScore", "efficiencyScore", "qualityScore", "riskScore"]
    label: str = ""
    description: str = ""
    formula: str = ""
    inputs: list[str] = Field(default_factory=list)


class WorkflowEffectivenessRollup(BaseModel):
    id: Optional[int] = None
    projectId: str
    scopeType: EffectivenessScopeType
    scopeId: str
    scopeLabel: str = ""
    period: str = "all"
    sampleSize: int = 0
    successScore: float = 0.0
    efficiencyScore: float = 0.0
    qualityScore: float = 0.0
    riskScore: float = 0.0
    attributedTokens: int = 0
    supportingAttributionTokens: int = 0
    attributedCostUsdModelIO: float = 0.0
    averageAttributionConfidence: float = 0.0
    attributionCoverage: float = 0.0
    attributionCacheShare: float = 0.0
    evidenceSummary: dict[str, Any] = Field(default_factory=dict)
    scopeRef: Optional[ExecutionArtifactReference] = None
    relatedRefs: list[ExecutionArtifactReference] = Field(default_factory=list)
    generatedAt: str = ""
    createdAt: str = ""
    updatedAt: str = ""


class WorkflowEffectivenessResponse(BaseModel):
    projectId: str
    period: str = "all"
    metricDefinitions: list[EffectivenessMetricDefinition] = Field(default_factory=list)
    items: list[WorkflowEffectivenessRollup] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 0
    generatedAt: str = ""


WorkflowRegistryCorrelationState = Literal["strong", "hybrid", "weak", "unresolved"]
WorkflowRegistryResolutionKind = Literal["workflow_definition", "command_artifact", "dual_backed", "none"]
WorkflowRegistryIssueSeverity = Literal["info", "warning", "error"]
WorkflowRegistryActionTarget = Literal["external", "internal"]


class WorkflowRegistryIssue(BaseModel):
    code: str
    severity: WorkflowRegistryIssueSeverity = "info"
    title: str = ""
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowRegistryIdentity(BaseModel):
    registryId: str
    observedWorkflowFamilyRef: str = ""
    observedAliases: list[str] = Field(default_factory=list)
    displayLabel: str = ""
    resolvedWorkflowId: str = ""
    resolvedWorkflowLabel: str = ""
    resolvedWorkflowSourceUrl: str = ""
    resolvedCommandArtifactId: str = ""
    resolvedCommandArtifactLabel: str = ""
    resolvedCommandArtifactSourceUrl: str = ""
    resolutionKind: WorkflowRegistryResolutionKind = "none"
    correlationState: WorkflowRegistryCorrelationState = "unresolved"


class WorkflowRegistryBundleAlignment(BaseModel):
    bundleId: str = ""
    bundleName: str = ""
    matchScore: float = 0.0
    matchedRefs: list[str] = Field(default_factory=list)
    sourceUrl: str = ""


class WorkflowRegistryContextModule(BaseModel):
    contextRef: str = ""
    moduleId: str = ""
    moduleName: str = ""
    status: str = ""
    sourceUrl: str = ""
    previewTokens: int = 0


class WorkflowRegistryCompositionSummary(BaseModel):
    artifactRefs: list[str] = Field(default_factory=list)
    contextRefs: list[str] = Field(default_factory=list)
    resolvedContextModules: list[WorkflowRegistryContextModule] = Field(default_factory=list)
    planSummary: dict[str, Any] = Field(default_factory=dict)
    stageOrder: list[str] = Field(default_factory=list)
    gateCount: int = 0
    fanOutCount: int = 0
    bundleAlignment: Optional[WorkflowRegistryBundleAlignment] = None


class WorkflowRegistryEffectivenessSummary(BaseModel):
    scopeType: str = ""
    scopeId: str = ""
    scopeLabel: str = ""
    sampleSize: int = 0
    successScore: float = 0.0
    efficiencyScore: float = 0.0
    qualityScore: float = 0.0
    riskScore: float = 0.0
    attributionCoverage: float = 0.0
    averageAttributionConfidence: float = 0.0
    evidenceSummary: dict[str, Any] = Field(default_factory=dict)


class WorkflowRegistryAction(BaseModel):
    id: str
    label: str
    target: WorkflowRegistryActionTarget = "external"
    href: str = ""
    disabled: bool = False
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowRegistrySessionEvidence(BaseModel):
    sessionId: str
    featureId: str = ""
    title: str = ""
    status: str = ""
    workflowRef: str = ""
    startedAt: str = ""
    endedAt: str = ""
    href: str = ""


class WorkflowRegistryExecutionEvidence(BaseModel):
    executionId: str = ""
    status: str = ""
    startedAt: str = ""
    sourceUrl: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class WorkflowRegistryItem(BaseModel):
    id: str
    identity: WorkflowRegistryIdentity
    correlationState: WorkflowRegistryCorrelationState = "unresolved"
    issueCount: int = 0
    issues: list[WorkflowRegistryIssue] = Field(default_factory=list)
    effectiveness: Optional[WorkflowRegistryEffectivenessSummary] = None
    observedCommandCount: int = 0
    representativeCommands: list[str] = Field(default_factory=list)
    sampleSize: int = 0
    lastObservedAt: str = ""


class WorkflowRegistryDetail(WorkflowRegistryItem):
    composition: WorkflowRegistryCompositionSummary = Field(default_factory=WorkflowRegistryCompositionSummary)
    representativeSessions: list[WorkflowRegistrySessionEvidence] = Field(default_factory=list)
    recentExecutions: list[WorkflowRegistryExecutionEvidence] = Field(default_factory=list)
    actions: list[WorkflowRegistryAction] = Field(default_factory=list)


class WorkflowRegistryListResponse(BaseModel):
    projectId: str
    items: list[WorkflowRegistryItem] = Field(default_factory=list)
    correlationCounts: dict[WorkflowRegistryCorrelationState, int] = Field(
        default_factory=lambda: {
            "strong": 0,
            "hybrid": 0,
            "weak": 0,
            "unresolved": 0,
        }
    )
    total: int = 0
    offset: int = 0
    limit: int = 0
    generatedAt: str = ""


class WorkflowRegistryDetailResponse(BaseModel):
    projectId: str
    item: WorkflowRegistryDetail
    generatedAt: str = ""


class FailurePatternRecord(BaseModel):
    id: str
    patternType: str
    title: str
    scopeType: str = ""
    scopeId: str = ""
    severity: Literal["low", "medium", "high"] = "medium"
    confidence: float = 0.0
    occurrenceCount: int = 0
    averageSuccessScore: float = 0.0
    averageRiskScore: float = 0.0
    evidenceSummary: dict[str, Any] = Field(default_factory=dict)
    sessionIds: list[str] = Field(default_factory=list)


class FailurePatternResponse(BaseModel):
    projectId: str
    items: list[FailurePatternRecord] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 0
    generatedAt: str = ""


ExecutionPolicyVerdict = Literal["allow", "requires_approval", "deny"]
ExecutionRunStatus = Literal["queued", "running", "succeeded", "failed", "canceled", "blocked"]
ExecutionRiskLevel = Literal["low", "medium", "high"]
ExecutionApprovalDecision = Literal["pending", "approved", "denied"]
ExecutionEventStream = Literal["stdout", "stderr", "system"]


class ExecutionPolicyResultDTO(BaseModel):
    verdict: ExecutionPolicyVerdict
    riskLevel: ExecutionRiskLevel
    requiresApproval: bool = False
    normalizedCommand: str = ""
    commandTokens: list[str] = Field(default_factory=list)
    resolvedCwd: str = ""
    reasonCodes: list[str] = Field(default_factory=list)


class ExecutionPolicyCheckRequest(BaseModel):
    command: str
    cwd: str = "."
    envProfile: str = "default"


class ExecutionRunCreateRequest(BaseModel):
    command: str
    cwd: str = "."
    envProfile: str = "default"
    featureId: str = ""
    recommendationRuleId: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionRunDTO(BaseModel):
    id: str
    projectId: str
    featureId: str = ""
    provider: str = "local"
    sourceCommand: str
    normalizedCommand: str
    cwd: str
    envProfile: str = "default"
    recommendationRuleId: str = ""
    riskLevel: ExecutionRiskLevel = "medium"
    policyVerdict: ExecutionPolicyVerdict = "allow"
    requiresApproval: bool = False
    approvedBy: str = ""
    approvedAt: str = ""
    status: ExecutionRunStatus = "queued"
    exitCode: Optional[int] = None
    startedAt: str = ""
    endedAt: str = ""
    retryOfRunId: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    createdAt: str = ""
    updatedAt: str = ""


class ExecutionRunEventDTO(BaseModel):
    id: Optional[int] = None
    runId: str
    sequenceNo: int
    stream: ExecutionEventStream = "system"
    eventType: str = "status"
    payloadText: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    occurredAt: str = ""


class ExecutionRunEventPageDTO(BaseModel):
    runId: str
    items: list[ExecutionRunEventDTO] = Field(default_factory=list)
    nextSequence: int = 0


class ExecutionApprovalDTO(BaseModel):
    id: Optional[int] = None
    runId: str
    decision: ExecutionApprovalDecision = "pending"
    reason: str = ""
    requestedAt: str = ""
    resolvedAt: str = ""
    requestedBy: str = ""
    resolvedBy: str = ""


class ExecutionApprovalRequest(BaseModel):
    decision: Literal["approved", "denied"]
    reason: str = ""
    actor: str = "user"


class ExecutionCancelRequest(BaseModel):
    reason: str = ""
    actor: str = "user"


class ExecutionRetryRequest(BaseModel):
    acknowledgeFailure: bool = False
    actor: str = "user"
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Test Visualizer DTOs ───────────────────────────────────────────

class TestRunDTO(BaseModel):
    run_id: str
    project_id: str
    timestamp: str
    git_sha: str = ""
    branch: str = ""
    agent_session_id: str = ""
    env_fingerprint: str = ""
    trigger: str = "local"
    status: str = "complete"
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    duration_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class TestDefinitionDTO(BaseModel):
    test_id: str
    project_id: str
    path: str
    name: str
    framework: str = "pytest"
    tags: list[str] = Field(default_factory=list)
    owner: str = ""
    created_at: str = ""
    updated_at: str = ""


class TestResultDTO(BaseModel):
    run_id: str
    test_id: str
    status: str
    duration_ms: int = 0
    error_fingerprint: str = ""
    error_message: str = ""
    artifact_refs: list[str] = Field(default_factory=list)
    stdout_ref: str = ""
    stderr_ref: str = ""
    created_at: str = ""


class TestDomainDTO(BaseModel):
    domain_id: str
    project_id: str
    name: str
    parent_id: Optional[str] = None
    description: str = ""
    tier: str = "core"
    sort_order: int = 0
    created_at: str = ""
    updated_at: str = ""


class TestFeatureMappingDTO(BaseModel):
    mapping_id: int
    project_id: str
    test_id: str
    feature_id: str
    domain_id: Optional[str] = None
    provider_source: str
    confidence: float = 0.5
    version: int = 1
    snapshot_hash: str = ""
    is_primary: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class TestIntegritySignalDTO(BaseModel):
    signal_id: str
    project_id: str
    git_sha: str
    file_path: str
    test_id: Optional[str] = None
    signal_type: str
    severity: str = "medium"
    details: dict[str, Any] = Field(default_factory=dict)
    linked_run_ids: list[str] = Field(default_factory=list)
    agent_session_id: str = ""
    created_at: str = ""


class DomainHealthRollupDTO(BaseModel):
    domain_id: str
    domain_name: str
    tier: str = "core"
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    pass_rate: float = 0.0
    integrity_score: float = 1.0
    confidence_score: float = 0.0
    last_run_at: Optional[str] = None
    children: list["DomainHealthRollupDTO"] = Field(default_factory=list)


class FeatureTestHealthDTO(BaseModel):
    feature_id: str
    feature_name: str
    domain_id: Optional[str] = None
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    pass_rate: float = 0.0
    integrity_score: float = 1.0
    confidence_score: float = 0.0
    last_run_at: Optional[str] = None
    open_signals: int = 0


class CursorPaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    next_cursor: Optional[str] = None


class TestResultHistoryDTO(BaseModel):
    run_id: str
    test_id: str
    status: str
    duration_ms: int = 0
    error_fingerprint: str = ""
    error_message: str = ""
    artifact_refs: list[str] = Field(default_factory=list)
    stdout_ref: str = ""
    stderr_ref: str = ""
    created_at: str = ""
    run_timestamp: str = ""
    git_sha: str = ""
    agent_session_id: str = ""


class TestRunDetailDTO(BaseModel):
    run: TestRunDTO
    results: list[TestResultDTO] = Field(default_factory=list)
    definitions: dict[str, TestDefinitionDTO] = Field(default_factory=dict)
    integrity_signals: list[TestIntegritySignalDTO] = Field(default_factory=list)


class RunResultPageDTO(BaseModel):
    items: list[TestResultDTO] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    next_cursor: Optional[str] = None
    definitions: dict[str, TestDefinitionDTO] = Field(default_factory=dict)


class FeatureTimelinePointDTO(BaseModel):
    date: str
    pass_rate: float = 0.0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    run_ids: list[str] = Field(default_factory=list)
    signals: list[TestIntegritySignalDTO] = Field(default_factory=list)


class FeatureTimelineResponseDTO(BaseModel):
    feature_id: str
    feature_name: str = ""
    timeline: list[FeatureTimelinePointDTO] = Field(default_factory=list)
    first_green: Optional[str] = None
    last_red: Optional[str] = None
    last_known_good: Optional[str] = None


class TestCorrelationResponseDTO(BaseModel):
    run: TestRunDTO
    agent_session: Optional[AgentSession] = None
    commit_correlation: Optional[dict[str, Any]] = None
    features: list[FeatureTestHealthDTO] = Field(default_factory=list)
    integrity_signals: list[TestIntegritySignalDTO] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)


class IngestRunRequest(BaseModel):
    run_id: str
    project_id: str
    timestamp: str
    git_sha: str = ""
    branch: str = ""
    agent_session_id: str = ""
    env_fingerprint: str = ""
    trigger: str = "local"
    test_definitions: list[dict[str, Any]] = Field(default_factory=list)
    test_results: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestRunResponse(BaseModel):
    run_id: str
    status: str  # created | updated | skipped
    test_definitions_upserted: int = 0
    test_results_inserted: int = 0
    test_results_skipped: int = 0
    mapping_trigger_queued: bool = False
    integrity_check_queued: bool = False
    errors: list[str] = Field(default_factory=list)


class EffectiveTestFlagsDTO(BaseModel):
    testVisualizerEnabled: bool = False
    integritySignalsEnabled: bool = False
    liveTestUpdatesEnabled: bool = False
    semanticMappingEnabled: bool = False


class TestSourceStatusDTO(BaseModel):
    platformId: str
    enabled: bool = False
    watch: bool = False
    resultsDir: str = ""
    resolvedDir: str = ""
    patterns: list[str] = Field(default_factory=list)
    exists: bool = False
    readable: bool = False
    matchedFiles: int = 0
    sampleFiles: list[str] = Field(default_factory=list)
    lastError: str = ""
    lastSyncedAt: str = ""


class TestVisualizerConfigDTO(BaseModel):
    projectId: str
    flags: ProjectTestFlags = Field(default_factory=ProjectTestFlags)
    effectiveFlags: EffectiveTestFlagsDTO = Field(default_factory=EffectiveTestFlagsDTO)
    autoSyncOnStartup: bool = True
    maxFilesPerScan: int = 500
    maxParseConcurrency: int = 4
    instructionProfile: str = "skillmeat"
    instructionNotes: str = ""
    parserHealth: dict[str, bool] = Field(default_factory=dict)
    sources: list[TestSourceStatusDTO] = Field(default_factory=list)


class SyncTestsRequest(BaseModel):
    project_id: str
    platforms: list[TestPlatformId] = Field(default_factory=list)
    force: bool = False


class SyncTestsResponse(BaseModel):
    project_id: str
    stats: dict[str, Any] = Field(default_factory=dict)
    sources: list[TestSourceStatusDTO] = Field(default_factory=list)


class BackfillTestMappingsRequest(BaseModel):
    project_id: str
    run_limit: int = Field(default=100, ge=1, le=5000)
    force_recompute: bool = False
    provider_sources: list[str] = Field(default_factory=list)
    source: str = "backfill"


class BackfillTestMappingsResponse(BaseModel):
    project_id: str
    run_limit: int
    runs_processed: int = 0
    tests_considered: int = 0
    tests_resolved: int = 0
    tests_reused_cached: int = 0
    mappings_stored: int = 0
    primary_mappings: int = 0
    resolver_version: str = ""
    cache_state: dict[str, Any] = Field(default_factory=dict)
    total_errors: int = 0
    errors: list[str] = Field(default_factory=list)


class MappingResolverRunDetailDTO(BaseModel):
    run_id: str
    timestamp: str = ""
    branch: str = ""
    git_sha: str = ""
    agent_session_id: str = ""
    total_results: int = 0
    mapped_primary_tests: int = 0
    unmapped_tests: int = 0
    coverage: float = 0.0


class MappingResolverDetailResponseDTO(BaseModel):
    project_id: str
    run_limit: int
    generated_at: str = ""
    runs: list[MappingResolverRunDetailDTO] = Field(default_factory=list)


class TestMetricSummaryDTO(BaseModel):
    project_id: str
    total_metrics: int = 0
    by_platform: dict[str, int] = Field(default_factory=dict)
    by_metric_type: dict[str, int] = Field(default_factory=dict)
    latest_collected_at: str = ""
