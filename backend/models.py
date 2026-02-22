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


class ImpactPoint(BaseModel):
    timestamp: str
    label: str
    type: str = "info"  # "info" | "warning" | "error" | "success"


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
    agentsUsed: list[str] = Field(default_factory=list)
    skillsUsed: list[str] = Field(default_factory=list)
    toolSummary: list[str] = Field(default_factory=list)
    sessionType: str = ""
    parentSessionId: Optional[str] = None
    rootSessionId: str = ""
    agentId: Optional[str] = None
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
    dates: EntityDates = Field(default_factory=EntityDates)
    timeline: list[TimelineEvent] = Field(default_factory=list)


# ── Document-related models ────────────────────────────────────────

class DocumentFrontmatter(BaseModel):
    tags: list[str] = Field(default_factory=list)
    linkedFeatures: list[str] = Field(default_factory=list)
    linkedSessions: list[str] = Field(default_factory=list)
    lineageFamily: str = ""
    lineageParent: str = ""
    lineageChildren: list[str] = Field(default_factory=list)
    lineageType: str = ""
    version: Optional[str] = None
    commits: list[str] = Field(default_factory=list)
    prs: list[str] = Field(default_factory=list)
    relatedRefs: list[str] = Field(default_factory=list)
    pathRefs: list[str] = Field(default_factory=list)
    slugRefs: list[str] = Field(default_factory=list)
    prd: str = ""
    prdRefs: list[str] = Field(default_factory=list)
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
    taskCounts: DocumentTaskCounts = Field(default_factory=DocumentTaskCounts)
    owners: list[str] = Field(default_factory=list)
    contributors: list[str] = Field(default_factory=list)
    requestLogIds: list[str] = Field(default_factory=list)
    commitRefs: list[str] = Field(default_factory=list)
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


# ── Feature models ─────────────────────────────────────────────────

class LinkedDocument(BaseModel):
    id: str
    title: str
    filePath: str
    docType: str  # "prd" | "implementation_plan" | "report" | "phase_plan" | "progress" | "spec"
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


class Feature(BaseModel):
    id: str  # slug, e.g. "discovery-import-fixes-v1"
    name: str
    status: str = "backlog"  # overall: done | deferred | in-progress | review | backlog
    totalTasks: int = 0
    completedTasks: int = 0
    deferredTasks: int = 0
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    updatedAt: str = ""
    plannedAt: str = ""
    startedAt: str = ""
    completedAt: str = ""
    linkedDocs: list[LinkedDocument] = Field(default_factory=list)
    phases: list[FeaturePhase] = Field(default_factory=list)
    relatedFeatures: list[str] = Field(default_factory=list)
    dates: EntityDates = Field(default_factory=EntityDates)
    timeline: list[TimelineEvent] = Field(default_factory=list)
