"""Pydantic models matching the frontend TypeScript types."""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Optional, Generic, TypeVar, Literal

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
    totalCost: float = 0.0
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
    dates: EntityDates = Field(default_factory=EntityDates)
    timeline: list[TimelineEvent] = Field(default_factory=list)


# ── Document-related models ────────────────────────────────────────

class DocumentFrontmatter(BaseModel):
    tags: list[str] = Field(default_factory=list)
    linkedFeatures: list[str] = Field(default_factory=list)
    linkedFeatureRefs: list["LinkedFeatureRef"] = Field(default_factory=list)
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


class SkillMeatProjectConfig(BaseModel):
    enabled: bool = False
    baseUrl: str = ""
    projectId: str = ""
    workspaceId: str = ""
    requestTimeoutSeconds: float = 5.0


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
    testConfig: ProjectTestConfig = Field(default_factory=ProjectTestConfig)
    skillMeat: SkillMeatProjectConfig = Field(default_factory=SkillMeatProjectConfig)


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
    updatedAt: str = ""
    plannedAt: str = ""
    startedAt: str = ""
    completedAt: str = ""
    linkedDocs: list[LinkedDocument] = Field(default_factory=list)
    linkedFeatures: list[LinkedFeatureRef] = Field(default_factory=list)
    primaryDocuments: FeaturePrimaryDocuments = Field(default_factory=FeaturePrimaryDocuments)
    documentCoverage: FeatureDocumentCoverage = Field(default_factory=FeatureDocumentCoverage)
    qualitySignals: FeatureQualitySignals = Field(default_factory=FeatureQualitySignals)
    phases: list[FeaturePhase] = Field(default_factory=list)
    relatedFeatures: list[str] = Field(default_factory=list)
    dates: EntityDates = Field(default_factory=EntityDates)
    timeline: list[TimelineEvent] = Field(default_factory=list)


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


class FeatureExecutionContext(BaseModel):
    feature: Feature
    documents: list[LinkedDocument] = Field(default_factory=list)
    sessions: list[dict[str, Any]] = Field(default_factory=list)
    analytics: FeatureExecutionAnalyticsSummary = Field(default_factory=FeatureExecutionAnalyticsSummary)
    recommendations: ExecutionRecommendation
    warnings: list[FeatureExecutionWarning] = Field(default_factory=list)
    generatedAt: str = ""


SkillMeatDefinitionType = Literal["artifact", "workflow", "context_module"]
StackComponentType = Literal["workflow", "agent", "skill", "context_module", "command", "model_policy", "artifact"]
StackComponentStatus = Literal["explicit", "inferred", "resolved", "unresolved"]


class SkillMeatDefinitionSource(BaseModel):
    id: Optional[int] = None
    projectId: str
    sourceKind: str = "skillmeat"
    enabled: bool = False
    baseUrl: str = ""
    projectMapping: dict[str, Any] = Field(default_factory=dict)
    featureFlags: dict[str, Any] = Field(default_factory=dict)
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
