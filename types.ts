
export type TaskStatus = 'todo' | 'backlog' | 'in-progress' | 'review' | 'done' | 'deferred';

export interface ProjectTask {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  owner: string;
  lastAgent: string;
  cost: number;
  priority: 'low' | 'medium' | 'high';
  // New fields for Project Structure
  projectType: 'Feature' | 'Enhancement' | 'Refactor' | 'Bugfix';
  projectLevel: 'Quick' | 'Full';
  tags: string[];
  updatedAt: string;
  relatedFiles?: string[];
  sourceFile?: string;
  sessionId?: string;
  commitHash?: string;
}

export interface ToolUsage {
  name: string;
  count: number;
  successRate: number;
  category: 'search' | 'edit' | 'test' | 'system';
}

export type LogType = 'message' | 'tool' | 'subagent' | 'skill' | 'thought' | 'system' | 'command' | 'subagent_start';

export interface SessionLog {
  id: string;
  timestamp: string;
  speaker: 'user' | 'agent' | 'system';
  type: LogType;
  agentName?: string;
  content: string;
  linkedSessionId?: string;
  relatedToolCallId?: string;
  metadata?: Record<string, any>;
  toolCall?: {
    id?: string;
    name: string;
    args: string;
    status: 'success' | 'error';
    output?: string;
    isError?: boolean;
  };
  subagentThread?: SessionLog[]; // For subagent conversation recursion
  skillDetails?: {
    name: string;
    version: string;
    description: string;
  };
}

export interface SessionImpactPoint {
  timestamp: string; // ISO timestamp or relative time (e.g., "00:05")
  locAdded: number;
  locDeleted: number;
  fileCount: number;
  testPassCount: number;
  testFailCount: number;
}

export interface SessionMetadataField {
  id: string;
  label: string;
  value: string;
}

export interface SessionMetadata {
  sessionTypeId: string;
  sessionTypeLabel: string;
  mappingId: string;
  relatedCommand: string;
  relatedPhases: string[];
  relatedFilePath?: string;
  fields: SessionMetadataField[];
}

export interface SessionFileUpdate {
  filePath: string;
  commits: string[];
  additions: number;
  deletions: number;
  agentName: string;
  action: 'read' | 'create' | 'update' | 'delete' | string;
  fileType: string;
  timestamp: string;
  sourceLogId?: string;
  sourceToolName?: string;
  threadSessionId?: string;
  rootSessionId?: string;
}

export interface SessionArtifact {
  id: string;
  type: 'memory' | 'request_log' | 'knowledge_base' | 'external_link' | 'command' | 'skill' | 'agent' | 'manifest' | string;
  title: string;
  source: string; // e.g., "SkillMeat", "MeatyCapture"
  description?: string;
  url?: string;
  preview?: string;
  sourceLogId?: string;
  sourceToolName?: string;
}

export interface AgentSession {
  id: string;
  title?: string;
  taskId: string;
  status: 'active' | 'completed';
  model: string;
  modelDisplayName?: string;
  modelProvider?: string;
  modelFamily?: string;
  modelVersion?: string;
  durationSeconds: number;
  rootSessionId?: string;
  agentId?: string;
  tokensIn: number;
  tokensOut: number;
  totalCost: number;
  startedAt: string;
  qualityRating?: number; // 1-5
  frictionRating?: number; // 1-5
  toolsUsed: ToolUsage[];
  logs: SessionLog[];
  impactHistory?: SessionImpactPoint[];
  updatedFiles?: SessionFileUpdate[];
  linkedArtifacts?: SessionArtifact[];
  sessionMetadata?: SessionMetadata | null;
  // Git Integration
  gitCommitHash?: string;
  gitCommitHashes?: string[];
  gitAuthor?: string;
  gitBranch?: string;
}

export interface PlanDocument {
  id: string;
  title: string;
  filePath: string;
  canonicalPath?: string;
  status: string;
  statusNormalized?: string;
  lastModified: string;
  author: string;
  content?: string; // Raw markdown content
  docType?: string;
  docSubtype?: string;
  rootKind?: 'project_plans' | 'progress' | 'document';
  hasFrontmatter?: boolean;
  frontmatterType?: string;
  featureSlugHint?: string;
  featureSlugCanonical?: string;
  prdRef?: string;
  phaseToken?: string;
  phaseNumber?: number | null;
  overallProgress?: number | null;
  totalTasks?: number;
  completedTasks?: number;
  inProgressTasks?: number;
  blockedTasks?: number;
  frontmatter: {
    tags: string[];
    linkedFeatures?: string[]; // IDs like T-101
    linkedSessions?: string[]; // IDs like S-8821
    relatedFiles?: string[];
    version?: string;
    commits?: string[];
    prs?: string[];
    relatedRefs?: string[];
    pathRefs?: string[];
    slugRefs?: string[];
    prd?: string;
    prdRefs?: string[];
    fieldKeys?: string[];
    raw?: Record<string, any>;
  };
  category?: string;
  pathSegments?: string[];
  featureCandidates?: string[];
  metadata?: {
    phase?: string;
    phaseNumber?: number | null;
    overallProgress?: number | null;
    taskCounts?: {
      total: number;
      completed: number;
      inProgress: number;
      blocked: number;
    };
    owners?: string[];
    contributors?: string[];
    requestLogIds?: string[];
    commitRefs?: string[];
    featureSlugHint?: string;
    canonicalPath?: string;
  };
  linkCounts?: {
    features: number;
    tasks: number;
    sessions: number;
    documents: number;
  };
}

export interface AnalyticsMetric {
  name: string;
  value: number;
  unit: string;
}

export interface AnalyticsTrendPoint {
  captured_at: string;
  value: number;
  metadata?: any;
}

// Alert System
export type AlertMetric = 'total_tokens' | 'avg_quality' | 'cost_threshold';
export type AlertOperator = '>' | '<';

export interface AlertConfig {
  id: string;
  name: string;
  metric: AlertMetric;
  operator: AlertOperator;
  threshold: number;
  isActive: boolean;
  scope: 'session' | 'weekly';
}

export interface Notification {
  id: string;
  alertId: string;
  message: string;
  timestamp: string;
  isRead: boolean;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  description: string;
  repoUrl: string;
  agentPlatforms: string[];
  planDocsPath: string;
  sessionsPath: string;
  progressPath: string;
}

export interface LinkedDocument {
  id: string;
  title: string;
  filePath: string;
  docType: 'prd' | 'implementation_plan' | 'report' | 'phase_plan' | 'progress' | 'spec' | string;
  category?: string;
  slug?: string;
  canonicalSlug?: string;
  frontmatterKeys?: string[];
  relatedRefs?: string[];
  prdRef?: string;
}

export interface FeaturePhase {
  id?: string;
  phase: string;
  title: string;
  status: string;
  progress: number;
  totalTasks: number;
  completedTasks: number;
  deferredTasks?: number;
  tasks: ProjectTask[];
}

export interface Feature {
  id: string;
  name: string;
  status: string;
  totalTasks: number;
  completedTasks: number;
  deferredTasks?: number;
  category: string;
  tags: string[];
  updatedAt: string;
  linkedDocs: LinkedDocument[];
  phases: FeaturePhase[];
  relatedFeatures: string[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface SyncOperation {
  id: string;
  kind: string;
  projectId: string;
  trigger: string;
  status: 'running' | 'completed' | 'failed' | string;
  phase: string;
  message: string;
  startedAt: string;
  updatedAt: string;
  finishedAt: string;
  durationMs: number;
  progress: Record<string, any>;
  counters: Record<string, any>;
  stats: Record<string, any>;
  metadata: Record<string, any>;
  error: string;
}

export interface CacheStatusResponse {
  status: string;
  sync_engine: string;
  watcher: string;
  projectId: string;
  projectName?: string;
  activePaths?: {
    sessionsDir: string;
    docsDir: string;
    progressDir: string;
  };
  operations: {
    activeOperationCount: number;
    activeOperations: SyncOperation[];
    recentOperations: SyncOperation[];
    trackedOperationCount: number;
  };
}

export interface LinkAuditSuspect {
  feature_id: string;
  session_id: string;
  confidence: number;
  ambiguity_share: number;
  title: string;
  signal_type: string;
  signal_path: string;
  commands: string[];
  reason: string;
  fanout_count: number;
}

export interface LinkAuditResponse {
  status: string;
  project_id: string;
  feature_filter?: string | null;
  row_count: number;
  suspect_count: number;
  primary_floor: number;
  fanout_floor: number;
  generated_at?: string;
  suspects: LinkAuditSuspect[];
}
