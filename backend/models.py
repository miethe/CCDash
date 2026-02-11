"""Pydantic models matching the frontend TypeScript types."""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


# ── Session-related models ──────────────────────────────────────────

class ToolCallInfo(BaseModel):
    name: str = ""
    args: str = ""
    output: Optional[str] = None
    status: str = "success"


class SkillDetails(BaseModel):
    name: str = ""
    description: str = ""
    version: str = "1.0"


class SessionLog(BaseModel):
    id: str
    timestamp: str
    speaker: str  # "user" | "agent"
    type: str  # "message" | "tool" | "subagent" | "skill"
    content: str = ""
    agentName: Optional[str] = None
    toolCall: Optional[ToolCallInfo] = None
    skillDetails: Optional[SkillDetails] = None
    subagentThread: Optional[list[SessionLog]] = None


class SessionFileUpdate(BaseModel):
    filePath: str
    additions: int = 0
    deletions: int = 0
    commits: list[str] = Field(default_factory=list)
    agentName: str = ""


class SessionArtifact(BaseModel):
    id: str
    title: str
    type: str = "document"
    description: str = ""
    source: str = ""


class ToolUsage(BaseModel):
    name: str
    count: int = 0
    successRate: float = 1.0


class ImpactPoint(BaseModel):
    timestamp: str
    label: str
    type: str = "info"  # "info" | "warning" | "error" | "success"


class AgentSession(BaseModel):
    id: str
    taskId: str = ""
    status: str = "completed"
    model: str = ""
    durationSeconds: int = 0
    tokensIn: int = 0
    tokensOut: int = 0
    totalCost: float = 0.0
    startedAt: str = ""
    qualityRating: int = 0
    frictionRating: int = 0
    gitCommitHash: Optional[str] = None
    gitAuthor: Optional[str] = None
    gitBranch: Optional[str] = None
    updatedFiles: list[SessionFileUpdate] = Field(default_factory=list)
    linkedArtifacts: list[SessionArtifact] = Field(default_factory=list)
    toolsUsed: list[ToolUsage] = Field(default_factory=list)
    impactHistory: list[ImpactPoint] = Field(default_factory=list)
    logs: list[SessionLog] = Field(default_factory=list)


# ── Document-related models ────────────────────────────────────────

class DocumentFrontmatter(BaseModel):
    tags: list[str] = Field(default_factory=list)
    linkedFeatures: list[str] = Field(default_factory=list)
    linkedSessions: list[str] = Field(default_factory=list)
    version: Optional[str] = None
    commits: list[str] = Field(default_factory=list)
    prs: list[str] = Field(default_factory=list)


class PlanDocument(BaseModel):
    id: str
    title: str
    filePath: str
    status: str = "active"
    lastModified: str = ""
    author: str = ""
    frontmatter: DocumentFrontmatter = Field(default_factory=DocumentFrontmatter)
    content: Optional[str] = None  # markdown body, loaded on demand


# ── Task-related models ────────────────────────────────────────────

class ProjectTask(BaseModel):
    id: str
    title: str
    description: str = ""
    status: str = "backlog"  # backlog | in-progress | review | done
    owner: str = ""
    lastAgent: str = ""
    cost: float = 0.0
    priority: str = "medium"
    projectType: str = ""
    projectLevel: str = ""
    tags: list[str] = Field(default_factory=list)
    updatedAt: str = ""
    relatedFiles: list[str] = Field(default_factory=list)


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
