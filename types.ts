
export type TaskStatus = 'todo' | 'backlog' | 'in-progress' | 'review' | 'done' | 'deferred';

export type DateConfidence = 'high' | 'medium' | 'low';

export interface DateValue {
  value: string;
  confidence: DateConfidence;
  source: string;
  reason?: string;
}

export interface EntityDates {
  createdAt?: DateValue;
  updatedAt?: DateValue;
  completedAt?: DateValue;
  plannedAt?: DateValue;
  startedAt?: DateValue;
  endedAt?: DateValue;
  lastActivityAt?: DateValue;
}

export interface TimelineEvent {
  id: string;
  timestamp: string;
  label: string;
  kind?: string;
  confidence: DateConfidence;
  source: string;
  description?: string;
}

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
  category?: 'search' | 'edit' | 'test' | 'system';
  totalMs?: number;
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

export interface SessionModelInfo {
  raw: string;
  modelDisplayName?: string;
  modelProvider?: string;
  modelFamily?: string;
  modelVersion?: string;
}

export interface SessionPlatformTransition {
  timestamp: string;
  fromVersion: string;
  toVersion: string;
  sourceLogId?: string;
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
  modelsUsed?: SessionModelInfo[];
  platformType?: string;
  platformVersion?: string;
  platformVersions?: string[];
  platformVersionTransitions?: SessionPlatformTransition[];
  agentsUsed?: string[];
  skillsUsed?: string[];
  toolSummary?: string[];
  durationSeconds: number;
  sessionType?: string;
  parentSessionId?: string | null;
  rootSessionId?: string;
  agentId?: string;
  tokensIn: number;
  tokensOut: number;
  totalCost: number;
  startedAt: string;
  endedAt?: string;
  createdAt?: string;
  updatedAt?: string;
  qualityRating?: number; // 1-5
  frictionRating?: number; // 1-5
  toolsUsed: ToolUsage[];
  logs: SessionLog[];
  impactHistory?: SessionImpactPoint[];
  updatedFiles?: SessionFileUpdate[];
  linkedArtifacts?: SessionArtifact[];
  sessionMetadata?: SessionMetadata | null;
  thinkingLevel?: 'low' | 'medium' | 'high' | string;
  sessionForensics?: Record<string, any>;
  // Git Integration
  gitCommitHash?: string;
  gitCommitHashes?: string[];
  gitAuthor?: string;
  gitBranch?: string;
  dates?: EntityDates;
  timeline?: TimelineEvent[];
}

export interface SessionActivityItem {
  id: string;
  kind: 'log' | 'file' | 'artifact' | string;
  timestamp: string;
  sourceLogId?: string;
  sessionId: string;
  threadName?: string;
  label: string;
  detail?: string;
  action?: 'read' | 'create' | 'update' | 'delete' | string;
  filePath?: string;
  fileType?: string;
  artifactType?: string;
  artifactUrl?: string;
  linkedSessionId?: string;
  localPath?: string;
  documentId?: string;
  githubUrl?: string;
  additions?: number;
  deletions?: number;
}

export interface SessionFileAggregateRow {
  key: string;
  fileName: string;
  filePath: string;
  actions: Array<'read' | 'create' | 'update' | 'delete' | string>;
  touchCount: number;
  uniqueSessions: number;
  uniqueAgents: number;
  lastTouchedAt: string;
  netDiff: number;
  additions: number;
  deletions: number;
  sourceLogIds: string[];
  localPath: string;
  documentId?: string;
  fileType?: string;
}

export interface CodebaseFeatureInvolvement {
  featureId: string;
  featureName: string;
  featureStatus?: string;
  featureCategory?: string;
  score: number;
  confidence: number;
  involvementLevel: 'primary' | 'supporting' | 'peripheral';
  sessionCount: number;
  actions: string[];
}

export interface CodebaseTreeNode {
  path: string;
  name: string;
  nodeType: 'folder' | 'file';
  depth: number;
  parentPath: string;
  touchCount: number;
  isTouched: boolean;
  sessionCount: number;
  featureCount: number;
  lastTouchedAt: string;
  actions: string[];
  hasChildren: boolean;
  sizeBytes?: number;
  exists?: boolean;
  children?: CodebaseTreeNode[];
}

export interface CodebaseFileSummary {
  filePath: string;
  fileName: string;
  directory: string;
  exists: boolean;
  sizeBytes: number;
  lastModified: string;
  actions: string[];
  touchCount: number;
  sessionCount: number;
  agentCount: number;
  lastTouchedAt: string;
  additions: number;
  deletions: number;
  netDiff: number;
  actionCounts: Record<string, number>;
  featureCount: number;
  features: CodebaseFeatureInvolvement[];
  sourceLogIds: string[];
}

export interface CodebaseFileSessionSummary {
  sessionId: string;
  rootSessionId: string;
  parentSessionId?: string;
  status: string;
  startedAt: string;
  endedAt: string;
  totalCost: number;
  touchCount: number;
  actions: string[];
  lastTouchedAt: string;
  agentNames: string[];
}

export interface CodebaseLinkedDocument {
  documentId: string;
  title: string;
  filePath: string;
  docType?: string;
  category?: string;
  status?: string;
  relation: 'source' | 'reference' | string;
}

export interface CodebaseFileActivityEntry {
  id: string;
  kind: string;
  timestamp: string;
  action?: string;
  filePath?: string;
  fileType?: string;
  sessionId?: string;
  rootSessionId?: string;
  sourceLogId?: string;
  sourceToolName?: string;
  additions?: number;
  deletions?: number;
  agentName?: string;
  logType?: string;
  logContent?: string;
  linkedSessionId?: string;
  artifactCount?: number;
  artifactIds?: string[];
}

export interface CodebaseFileDetail extends CodebaseFileSummary {
  absolutePath: string;
  sessions: CodebaseFileSessionSummary[];
  documents: CodebaseLinkedDocument[];
  activity: CodebaseFileActivityEntry[];
}

export interface PlanDocument {
  id: string;
  title: string;
  filePath: string;
  canonicalPath?: string;
  status: string;
  statusNormalized?: string;
  createdAt?: string;
  updatedAt?: string;
  completedAt?: string;
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
    lineageFamily?: string;
    lineageParent?: string;
    lineageChildren?: string[];
    lineageType?: string;
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
  dates?: EntityDates;
  timeline?: TimelineEvent[];
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

export interface AnalyticsOverview {
  kpis: {
    sessionCost: number;
    sessionTokens: number;
    sessionCount: number;
    sessionDurationAvg: number;
    taskVelocity: number;
    taskCompletionPct: number;
    featureProgress: number;
    toolCallCount: number;
    toolSuccessRate: number;
  };
  topModels: Array<{ name: string; usage: number }>;
  generatedAt: string;
  range: {
    start: string;
    end: string;
  };
}

export interface AnalyticsBreakdownItem {
  name: string;
  count: number;
  tokens?: number;
  cost?: number;
}

export interface AnalyticsCorrelationItem {
  sessionId: string;
  featureId: string;
  featureName: string;
  confidence: number;
  linkStrategy?: string;
  commitHash: string;
  model: string;
  modelRaw?: string;
  modelFamily?: string;
  status: string;
  startedAt: string;
  endedAt: string;
}

export interface AnalyticsArtifactTypePoint {
  artifactType: string;
  count: number;
}

export interface AnalyticsArtifactTypeBreakdownItem {
  artifactType: string;
  count: number;
  sessions: number;
  features: number;
  models: string[];
  tools: string[];
  sources: string[];
  tokenInput: number;
  tokenOutput: number;
  totalTokens: number;
  totalCost: number;
}

export interface AnalyticsArtifactSourceBreakdownItem {
  source: string;
  count: number;
  sessions: number;
  artifactTypes: string[];
}

export interface AnalyticsArtifactToolBreakdownItem {
  toolName: string;
  count: number;
  sessions: number;
  artifactTypes: string[];
  models: string[];
}

export interface AnalyticsArtifactSessionItem {
  sessionId: string;
  model: string;
  modelRaw?: string;
  modelFamily?: string;
  status: string;
  startedAt: string;
  artifactCount: number;
  artifactTypes: AnalyticsArtifactTypePoint[];
  toolNames: string[];
  sources: string[];
  featureIds: string[];
  featureNames: string[];
  tokenInput: number;
  tokenOutput: number;
  totalTokens: number;
  totalCost: number;
}

export interface AnalyticsArtifactFeatureItem {
  featureId: string;
  featureName: string;
  artifactCount: number;
  sessions: number;
  models: string[];
  tools: string[];
  artifactTypes: AnalyticsArtifactTypePoint[];
  tokenInput: number;
  tokenOutput: number;
  totalTokens: number;
  totalCost: number;
}

export interface AnalyticsModelArtifactItem {
  model: string;
  modelRaw?: string;
  modelFamily?: string;
  artifactType: string;
  count: number;
  sessions: number;
  tools: string[];
  tokenInput: number;
  tokenOutput: number;
  totalTokens: number;
  totalCost: number;
}

export interface AnalyticsArtifactToolRelationItem {
  artifactType: string;
  toolName: string;
  count: number;
  sessions: number;
  models: string[];
}

export interface AnalyticsModelArtifactToolItem {
  model: string;
  modelRaw?: string;
  modelFamily?: string;
  artifactType: string;
  toolName: string;
  count: number;
  sessions: number;
  tokenInput: number;
  tokenOutput: number;
  totalTokens: number;
  totalCost: number;
}

export interface AnalyticsArtifactsResponse {
  generatedAt: string;
  range: {
    start: string;
    end: string;
  };
  totals: {
    artifactCount: number;
    artifactTypes: number;
    sessions: number;
    features: number;
    models: number;
    modelFamilies: number;
    tools: number;
    sources: number;
    agents: number;
    skills: number;
    commands: number;
    kindTotals: {
      agents: number;
      skills: number;
      commands: number;
      manifests: number;
      requests: number;
    };
  };
  byType: AnalyticsArtifactTypeBreakdownItem[];
  bySource: AnalyticsArtifactSourceBreakdownItem[];
  byTool: AnalyticsArtifactToolBreakdownItem[];
  bySession: AnalyticsArtifactSessionItem[];
  byFeature: AnalyticsArtifactFeatureItem[];
  modelArtifact: AnalyticsModelArtifactItem[];
  modelFamilies: Array<{
    modelFamily: string;
    artifactCount: number;
    sessions: number;
    models: string[];
    artifactTypes: string[];
    tokenInput: number;
    tokenOutput: number;
    totalTokens: number;
    totalCost: number;
  }>;
  artifactTool: AnalyticsArtifactToolRelationItem[];
  modelArtifactTool: AnalyticsModelArtifactToolItem[];
  commandModel: Array<{
    command: string;
    model: string;
    modelRaw?: string;
    modelFamily?: string;
    count: number;
    sessions: number;
    tokenInput: number;
    tokenOutput: number;
    totalTokens: number;
    totalCost: number;
  }>;
  agentModel: Array<{
    agent: string;
    model: string;
    modelRaw?: string;
    modelFamily?: string;
    count: number;
    sessions: number;
    tokenInput: number;
    tokenOutput: number;
    totalTokens: number;
    totalCost: number;
  }>;
  tokenUsage: {
    byArtifactType: Array<{
      artifactType: string;
      tokenInput: number;
      tokenOutput: number;
      totalTokens: number;
      totalCost: number;
    }>;
    byModel: Array<{
      model: string;
      modelRaw?: string;
      modelFamily?: string;
      artifactCount: number;
      sessions: number;
      artifactTypes: string[];
      tokenInput: number;
      tokenOutput: number;
      totalTokens: number;
      totalCost: number;
    }>;
    byModelArtifact: AnalyticsModelArtifactItem[];
    byModelFamily: Array<{
      modelFamily: string;
      artifactCount: number;
      sessions: number;
      models: string[];
      artifactTypes: string[];
      tokenInput: number;
      tokenOutput: number;
      totalTokens: number;
      totalCost: number;
    }>;
  };
  detailLimit: number;
}

// Alert System
export type AlertMetric = 'total_tokens' | 'avg_quality' | 'cost_threshold' | string;
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
  dates?: EntityDates;
  timeline?: TimelineEvent[];
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
  plannedAt?: string;
  startedAt?: string;
  completedAt?: string;
  linkedDocs: LinkedDocument[];
  phases: FeaturePhase[];
  relatedFeatures: string[];
  dates?: EntityDates;
  timeline?: TimelineEvent[];
}

export interface ExecutionRecommendationEvidence {
  id: string;
  label: string;
  value: string;
  sourceType: string;
  sourcePath?: string;
}

export interface ExecutionRecommendationOption {
  command: string;
  ruleId: string;
  confidence: number;
  explanation: string;
  evidenceRefs: string[];
}

export interface ExecutionRecommendation {
  primary: ExecutionRecommendationOption;
  alternatives: ExecutionRecommendationOption[];
  ruleId: string;
  confidence: number;
  explanation: string;
  evidenceRefs: string[];
  evidence: ExecutionRecommendationEvidence[];
}

export interface FeatureExecutionWarning {
  section: string;
  message: string;
  recoverable: boolean;
}

export interface FeatureExecutionAnalyticsSummary {
  sessionCount: number;
  primarySessionCount: number;
  totalSessionCost: number;
  artifactEventCount: number;
  commandEventCount: number;
  lastEventAt: string;
  modelCount: number;
}

export interface FeatureExecutionSessionLink {
  sessionId: string;
  title?: string;
  titleSource?: string;
  titleConfidence?: number;
  confidence: number;
  reasons?: string[];
  commands: string[];
  commitHashes?: string[];
  startedAt?: string;
  endedAt?: string;
  createdAt?: string;
  updatedAt?: string;
  status?: string;
  model?: string;
  modelDisplayName?: string;
  modelProvider?: string;
  modelFamily?: string;
  modelVersion?: string;
  modelsUsed?: SessionModelInfo[];
  agentsUsed?: string[];
  skillsUsed?: string[];
  toolSummary?: string[];
  totalCost?: number;
  durationSeconds?: number;
  gitCommitHash?: string;
  gitCommitHashes?: string[];
  sessionType?: string;
  parentSessionId?: string | null;
  rootSessionId?: string;
  agentId?: string | null;
  isSubthread?: boolean;
  linkStrategy?: string;
  workflowType?: string;
  isPrimaryLink?: boolean;
  relatedPhases?: string[];
  relatedTasks?: Array<{
    taskId: string;
    taskTitle?: string;
    phaseId?: string;
    phase?: string;
    matchedBy?: string;
    linkedSessionId?: string;
  }>;
  sessionMetadata?: {
    sessionTypeId?: string;
    sessionTypeLabel?: string;
    mappingId?: string;
    relatedCommand?: string;
    relatedPhases?: string[];
    relatedFilePath?: string;
    fields?: Array<{
      id: string;
      label: string;
      value: string;
    }>;
  } | null;
}

export interface FeatureExecutionContext {
  feature: Feature;
  documents: LinkedDocument[];
  sessions: FeatureExecutionSessionLink[];
  analytics: FeatureExecutionAnalyticsSummary;
  recommendations: ExecutionRecommendation;
  warnings: FeatureExecutionWarning[];
  generatedAt: string;
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
