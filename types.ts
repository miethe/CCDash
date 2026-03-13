
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
  // Event-style fields captured by current parser pipelines.
  label?: string;
  type?: 'info' | 'warning' | 'error' | 'success' | string;
  // Legacy/derived numeric impact fields (optional).
  locAdded?: number;
  locDeleted?: number;
  fileCount?: number;
  testPassCount?: number;
  testFailCount?: number;
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

export interface SessionModelFacet {
  raw: string;
  modelDisplayName: string;
  modelProvider: string;
  modelFamily: string;
  modelVersion: string;
  count: number;
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

export interface SessionRelationship {
  id?: string;
  relationshipType: string;
  parentSessionId: string;
  childSessionId: string;
  contextInheritance?: string;
  sourcePlatform?: string;
  parentEntryUuid?: string;
  childEntryUuid?: string;
  sourceLogId?: string;
  metadata?: Record<string, any>;
}

export interface SessionForkSummary {
  sessionId: string;
  label?: string;
  forkPointTimestamp?: string;
  forkPointPreview?: string;
  entryCount?: number;
  contextInheritance?: string;
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
  threadKind?: 'root' | 'fork' | 'subagent' | string;
  conversationFamilyId?: string;
  contextInheritance?: 'fresh' | 'full' | string;
  forkParentSessionId?: string | null;
  forkPointLogId?: string | null;
  forkPointEntryUuid?: string | null;
  forkPointParentEntryUuid?: string | null;
  forkDepth?: number;
  forkCount?: number;
  tokensIn: number;
  tokensOut: number;
  modelIOTokens?: number;
  cacheCreationInputTokens?: number;
  cacheReadInputTokens?: number;
  cacheInputTokens?: number;
  observedTokens?: number;
  toolReportedTokens?: number;
  toolResultInputTokens?: number;
  toolResultOutputTokens?: number;
  toolResultCacheCreationInputTokens?: number;
  toolResultCacheReadInputTokens?: number;
  cacheShare?: number;
  outputShare?: number;
  currentContextTokens?: number;
  contextWindowSize?: number;
  contextUtilizationPct?: number;
  contextMeasurementSource?: string;
  contextMeasuredAt?: string;
  totalCost: number;
  reportedCostUsd?: number | null;
  recalculatedCostUsd?: number | null;
  displayCostUsd?: number | null;
  costProvenance?: 'reported' | 'recalculated' | 'estimated' | 'unknown';
  costConfidence?: number;
  costMismatchPct?: number | null;
  pricingModelSource?: string;
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
  forks?: SessionForkSummary[];
  sessionRelationships?: SessionRelationship[];
  usageEvents?: SessionUsageEvent[];
  usageAttributions?: SessionUsageAttribution[];
  usageAttributionSummary?: SessionUsageAggregateResponse | null;
  usageAttributionCalibration?: SessionUsageCalibrationSummary | null;
  // Git Integration
  gitCommitHash?: string;
  gitCommitHashes?: string[];
  gitAuthor?: string;
  gitBranch?: string;
  dates?: EntityDates;
  timeline?: TimelineEvent[];
}

export type SessionUsageTokenFamily =
  | 'model_input'
  | 'model_output'
  | 'cache_creation_input'
  | 'cache_read_input'
  | 'tool_result_input'
  | 'tool_result_output'
  | 'tool_result_cache_creation_input'
  | 'tool_result_cache_read_input'
  | 'tool_reported_total'
  | 'relay_mirror_input'
  | 'relay_mirror_output'
  | 'relay_mirror_cache_creation_input'
  | 'relay_mirror_cache_read_input';

export type SessionUsageEntityType =
  | 'skill'
  | 'agent'
  | 'subthread'
  | 'command'
  | 'artifact'
  | 'workflow'
  | 'feature';

export type SessionUsageAttributionRole = 'primary' | 'supporting';

export type SessionUsageAttributionMethod =
  | 'explicit_skill_invocation'
  | 'explicit_subthread_ownership'
  | 'explicit_agent_ownership'
  | 'explicit_command_context'
  | 'explicit_artifact_link'
  | 'skill_window'
  | 'artifact_window'
  | 'workflow_membership'
  | 'feature_inheritance';

export interface SessionUsageEvent {
  id: string;
  projectId: string;
  sessionId: string;
  rootSessionId: string;
  linkedSessionId: string;
  sourceLogId: string;
  capturedAt: string;
  eventKind: string;
  model: string;
  toolName: string;
  agentName: string;
  tokenFamily: SessionUsageTokenFamily;
  deltaTokens: number;
  costUsdModelIO: number;
  metadata: Record<string, unknown>;
}

export interface SessionUsageAttribution {
  eventId: string;
  entityType: SessionUsageEntityType;
  entityId: string;
  attributionRole: SessionUsageAttributionRole;
  weight: number;
  method: SessionUsageAttributionMethod;
  confidence: number;
  metadata: Record<string, unknown>;
}

export interface SessionUsageAggregateRow {
  entityType: SessionUsageEntityType;
  entityId: string;
  entityLabel?: string;
  exclusiveTokens: number;
  supportingTokens: number;
  exclusiveModelIOTokens?: number;
  exclusiveCacheInputTokens?: number;
  supportingModelIOTokens?: number;
  supportingCacheInputTokens?: number;
  exclusiveCostUsdModelIO: number;
  supportingCostUsdModelIO?: number;
  eventCount: number;
  primaryEventCount: number;
  supportingEventCount: number;
  sessionCount?: number;
  averageConfidence: number;
  methods: Array<Record<string, unknown>>;
}

export interface SessionUsageAggregateSummary {
  entityCount: number;
  sessionCount: number;
  eventCount: number;
  totalExclusiveTokens: number;
  totalSupportingTokens: number;
  totalExclusiveModelIOTokens: number;
  totalExclusiveCacheInputTokens: number;
  totalExclusiveCostUsdModelIO: number;
  averageConfidence: number;
}

export interface SessionUsageAggregateResponse {
  generatedAt: string;
  total: number;
  offset: number;
  limit: number;
  rows: SessionUsageAggregateRow[];
  summary: SessionUsageAggregateSummary;
}

export interface SessionUsageDrilldownRow {
  eventId: string;
  sessionId: string;
  rootSessionId?: string;
  linkedSessionId?: string;
  sessionType?: string;
  parentSessionId?: string;
  sourceLogId?: string;
  capturedAt: string;
  eventKind: string;
  tokenFamily: SessionUsageTokenFamily;
  deltaTokens: number;
  costUsdModelIO: number;
  model?: string;
  toolName?: string;
  agentName?: string;
  entityType: SessionUsageEntityType;
  entityId: string;
  entityLabel?: string;
  attributionRole: SessionUsageAttributionRole;
  weight: number;
  method: SessionUsageAttributionMethod;
  confidence: number;
  metadata: Record<string, unknown>;
}

export interface SessionUsageDrilldownResponse {
  generatedAt: string;
  total: number;
  offset: number;
  limit: number;
  items: SessionUsageDrilldownRow[];
  summary: SessionUsageAggregateSummary;
}

export interface SessionUsageCalibrationSummary {
  projectId: string;
  sessionCount: number;
  eventCount: number;
  attributedEventCount: number;
  primaryAttributedEventCount: number;
  ambiguousEventCount: number;
  unattributedEventCount: number;
  primaryCoverage: number;
  supportingCoverage: number;
  sessionModelIOTokens: number;
  exclusiveModelIOTokens: number;
  modelIOGap: number;
  sessionCacheInputTokens: number;
  exclusiveCacheInputTokens: number;
  cacheGap: number;
  averageConfidence: number;
  confidenceBands: Array<Record<string, unknown>>;
  methodMix: Array<Record<string, unknown>>;
  generatedAt: string;
}

export type MotionPresetKey = 'listInsertTop' | 'messageFlyIn' | 'typingPulse';

export interface LiveAgentActivity {
  agentName: string;
  sessionId?: string;
  threadSessionId?: string;
  lastSeenAt: string;
  status: 'active' | 'idle';
}

export interface LiveInsertMeta {
  insertedIds: string[];
  removedIds: string[];
  movedIds: string[];
  isHydrated: boolean;
}

export interface LiveTranscriptState {
  isLive: boolean;
  pendingMessageCount: number;
  autoStickToLatest: boolean;
  activeAgents: LiveAgentActivity[];
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
  completionEstimate?: string;
  description?: string;
  summary?: string;
  priority?: string;
  riskLevel?: string;
  complexity?: string;
  track?: string;
  timelineEstimate?: string;
  targetRelease?: string;
  milestone?: string;
  decisionStatus?: string;
  executionReadiness?: string;
  testImpact?: string;
  primaryDocRole?: string;
  featureSlug?: string;
  featureFamily?: string;
  featureVersion?: string;
  planRef?: string;
  implementationPlanRef?: string;
  totalTasks?: number;
  completedTasks?: number;
  inProgressTasks?: number;
  blockedTasks?: number;
  frontmatter: {
    tags: string[];
    linkedFeatures?: string[]; // IDs like T-101
    linkedFeatureRefs?: LinkedFeatureRef[];
    linkedSessions?: string[]; // IDs like S-8821
    linkedTasks?: string[];
    lineageFamily?: string;
    lineageParent?: string;
    lineageChildren?: string[];
    lineageType?: string;
    relatedFiles?: string[];
    version?: string;
    commits?: string[];
    prs?: string[];
    requestLogIds?: string[];
    commitRefs?: string[];
    prRefs?: string[];
    relatedRefs?: string[];
    pathRefs?: string[];
    slugRefs?: string[];
    prd?: string;
    prdRefs?: string[];
    sourceDocuments?: string[];
    filesAffected?: string[];
    filesModified?: string[];
    contextFiles?: string[];
    integritySignalRefs?: string[];
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
    completionEstimate?: string;
    description?: string;
    summary?: string;
    priority?: string;
    riskLevel?: string;
    complexity?: string;
    track?: string;
    timelineEstimate?: string;
    targetRelease?: string;
    milestone?: string;
    decisionStatus?: string;
    executionReadiness?: string;
    testImpact?: string;
    primaryDocRole?: string;
    featureSlug?: string;
    featureFamily?: string;
    featureVersion?: string;
    planRef?: string;
    implementationPlanRef?: string;
    taskCounts?: {
      total: number;
      completed: number;
      inProgress: number;
      blocked: number;
    };
    owners?: string[];
    contributors?: string[];
    reviewers?: string[];
    approvers?: string[];
    audience?: string[];
    labels?: string[];
    linkedTasks?: string[];
    requestLogIds?: string[];
    commitRefs?: string[];
    prRefs?: string[];
    sourceDocuments?: string[];
    filesAffected?: string[];
    filesModified?: string[];
    contextFiles?: string[];
    integritySignalRefs?: string[];
    executionEntrypoints?: Array<Record<string, any>>;
    linkedFeatureRefs?: LinkedFeatureRef[];
    docTypeFields?: Record<string, any>;
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

export interface DocumentUpdateRequest {
  content: string;
  commitMessage?: string;
}

export interface DocumentUpdateResponse {
  document: PlanDocument;
  writeMode: 'local' | 'github_repo';
  commitHash: string;
  message: string;
}

export interface LinkedFeatureRef {
  feature: string;
  type?: string;
  source?: string;
  confidence?: number;
  notes?: string;
  evidence?: string[];
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
    modelIOTokens?: number;
    cacheInputTokens?: number;
    observedTokens?: number;
    toolReportedTokens?: number;
    contextSessionCount?: number;
    avgContextUtilizationPct?: number;
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
  modelVersion?: string;
  status: string;
  startedAt: string;
  endedAt: string;
  rootSessionId?: string;
  parentSessionId?: string;
  sessionType?: string;
  platformVersion?: string;
  durationSeconds?: number;
  tokenInput?: number;
  tokenOutput?: number;
  modelIOTokens?: number;
  cacheCreationInputTokens?: number;
  cacheReadInputTokens?: number;
  cacheInputTokens?: number;
  observedTokens?: number;
  toolReportedTokens?: number;
  currentContextTokens?: number;
  contextWindowSize?: number;
  contextUtilizationPct?: number;
  contextMeasurementSource?: string;
  contextMeasuredAt?: string;
  cacheShare?: number;
  outputShare?: number;
  totalTokens?: number;
  totalCost?: number;
  reportedCostUsd?: number | null;
  recalculatedCostUsd?: number | null;
  displayCostUsd?: number | null;
  costProvenance?: 'reported' | 'recalculated' | 'estimated' | 'unknown';
  costConfidence?: number;
  costMismatchPct?: number | null;
  pricingModelSource?: string;
  linkedFeatureCount?: number;
  isSubagent?: boolean;
}

export interface SessionCostCalibrationProvenanceCount {
  provenance: string;
  count: number;
  displayCostUsd: number;
}

export interface SessionCostCalibrationMismatchBand {
  band: string;
  count: number;
}

export interface SessionCostCalibrationGroup {
  label: string;
  sessionCount: number;
  comparableSessionCount: number;
  avgMismatchPct: number;
  maxMismatchPct: number;
  avgConfidence: number;
  displayCostUsd: number;
  reportedCostUsd: number;
  recalculatedCostUsd: number;
  provenanceCounts: SessionCostCalibrationProvenanceCount[];
}

export interface SessionCostCalibrationSummary {
  projectId: string;
  sessionCount: number;
  comparableSessionCount: number;
  reportedSessionCount: number;
  recalculatedSessionCount: number;
  mismatchSessionCount: number;
  comparableCoveragePct: number;
  avgCostConfidence: number;
  avgMismatchPct: number;
  maxMismatchPct: number;
  totalDisplayCostUsd: number;
  totalReportedCostUsd: number;
  totalRecalculatedCostUsd: number;
  provenanceCounts: SessionCostCalibrationProvenanceCount[];
  mismatchBands: SessionCostCalibrationMismatchBand[];
  byModel: SessionCostCalibrationGroup[];
  byModelVersion: SessionCostCalibrationGroup[];
  byPlatformVersion: SessionCostCalibrationGroup[];
  generatedAt: string;
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

export type EffectivenessScopeType = 'workflow' | 'effective_workflow' | 'agent' | 'skill' | 'context_module' | 'bundle' | 'stack';

export interface EffectivenessMetricDefinition {
  id: 'successScore' | 'efficiencyScore' | 'qualityScore' | 'riskScore';
  label: string;
  description: string;
  formula: string;
  inputs: string[];
}

export interface WorkflowEffectivenessRollup {
  id?: number | null;
  projectId: string;
  scopeType: EffectivenessScopeType;
  scopeId: string;
  scopeLabel: string;
  period: string;
  sampleSize: number;
  successScore: number;
  efficiencyScore: number;
  qualityScore: number;
  riskScore: number;
  attributedTokens?: number;
  supportingAttributionTokens?: number;
  attributedCostUsdModelIO?: number;
  averageAttributionConfidence?: number;
  attributionCoverage?: number;
  attributionCacheShare?: number;
  evidenceSummary: Record<string, unknown>;
  scopeRef?: ExecutionArtifactReference | null;
  relatedRefs?: ExecutionArtifactReference[];
  generatedAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowEffectivenessResponse {
  projectId: string;
  period: string;
  metricDefinitions: EffectivenessMetricDefinition[];
  items: WorkflowEffectivenessRollup[];
  total: number;
  offset: number;
  limit: number;
  generatedAt: string;
}

export interface FailurePatternRecord {
  id: string;
  patternType: string;
  title: string;
  scopeType: string;
  scopeId: string;
  severity: 'low' | 'medium' | 'high';
  confidence: number;
  occurrenceCount: number;
  averageSuccessScore: number;
  averageRiskScore: number;
  evidenceSummary: Record<string, unknown>;
  sessionIds: string[];
}

export interface FailurePatternResponse {
  projectId: string;
  items: FailurePatternRecord[];
  total: number;
  offset: number;
  limit: number;
  generatedAt: string;
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

export type TestPlatformId =
  | 'pytest'
  | 'jest'
  | 'playwright'
  | 'coverage'
  | 'benchmark'
  | 'lighthouse'
  | 'locust'
  | 'triage';

export interface ProjectTestFlags {
  testVisualizerEnabled: boolean;
  integritySignalsEnabled: boolean;
  liveTestUpdatesEnabled: boolean;
  semanticMappingEnabled: boolean;
}

export interface ProjectTestPlatformConfig {
  id: TestPlatformId;
  enabled: boolean;
  resultsDir: string;
  watch: boolean;
  patterns: string[];
}

export interface ProjectTestConfig {
  flags: ProjectTestFlags;
  platforms: ProjectTestPlatformConfig[];
  autoSyncOnStartup: boolean;
  maxFilesPerScan: number;
  maxParseConcurrency: number;
  instructionProfile: string;
  instructionNotes: string;
}

export interface SkillMeatFeatureFlags {
  stackRecommendationsEnabled: boolean;
  workflowAnalyticsEnabled: boolean;
  usageAttributionEnabled: boolean;
  sessionBlockInsightsEnabled: boolean;
}

export interface SkillMeatProjectConfig {
  enabled: boolean;
  baseUrl: string;
  webBaseUrl: string;
  projectId: string;
  collectionId: string;
  aaaEnabled: boolean;
  apiKey: string;
  requestTimeoutSeconds: number;
  featureFlags: SkillMeatFeatureFlags;
}

export type SkillMeatProbeState = 'idle' | 'success' | 'warning' | 'error';

export interface SkillMeatProbeResult {
  state: SkillMeatProbeState;
  message: string;
  checkedAt: string;
  httpStatus?: number | null;
}

export interface SkillMeatConfigValidationResponse {
  baseUrl: SkillMeatProbeResult;
  projectMapping: SkillMeatProbeResult;
  auth: SkillMeatProbeResult;
}

export interface SkillMeatSyncWarning {
  section: string;
  message: string;
  recoverable: boolean;
}

export interface SkillMeatDefinitionSyncResponse {
  projectId: string;
  totalDefinitions: number;
  countsByType: Record<string, number>;
  fetchedAt: string;
  warnings: SkillMeatSyncWarning[];
}

export interface SkillMeatObservationBackfillResponse {
  projectId: string;
  sessionsProcessed: number;
  observationsStored: number;
  skippedSessions: number;
  resolvedComponents: number;
  unresolvedComponents: number;
  generatedAt: string;
  warnings: SkillMeatSyncWarning[];
}

export interface SkillMeatRefreshResponse {
  projectId: string;
  sync: SkillMeatDefinitionSyncResponse;
  backfill: SkillMeatObservationBackfillResponse | null;
}

export interface PricingCatalogEntry {
  projectId: string;
  platformType: string;
  modelId: string;
  displayLabel: string;
  entryKind: string;
  familyId: string;
  contextWindowSize?: number | null;
  inputCostPerMillion?: number | null;
  outputCostPerMillion?: number | null;
  cacheCreationCostPerMillion?: number | null;
  cacheReadCostPerMillion?: number | null;
  speedMultiplierFast?: number | null;
  sourceType: string;
  sourceUpdatedAt: string;
  overrideLocked: boolean;
  syncStatus: string;
  syncError: string;
  derivedFrom: string;
  isPersisted: boolean;
  isDetected: boolean;
  isRequiredDefault: boolean;
  canDelete: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface PricingCatalogUpsertRequest {
  platformType: string;
  modelId?: string;
  contextWindowSize?: number | null;
  inputCostPerMillion?: number | null;
  outputCostPerMillion?: number | null;
  cacheCreationCostPerMillion?: number | null;
  cacheReadCostPerMillion?: number | null;
  speedMultiplierFast?: number | null;
  sourceType?: string;
  sourceUpdatedAt?: string;
  overrideLocked?: boolean;
  syncStatus?: string;
  syncError?: string;
}

export interface PricingCatalogSyncResponse {
  projectId: string;
  platformType: string;
  syncedAt: string;
  updatedEntries: number;
  warnings: string[];
  entries: PricingCatalogEntry[];
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
  pathConfig: ProjectPathConfig;
  testConfig: ProjectTestConfig;
  skillMeat: SkillMeatProjectConfig;
}

export type PathSourceKind = 'project_root' | 'github_repo' | 'filesystem';
export type ProjectPathField = 'root' | 'plan_docs' | 'sessions' | 'progress';

export interface GitRepoRef {
  provider: 'github';
  repoUrl: string;
  repoSlug: string;
  branch: string;
  repoSubpath: string;
  writeEnabled: boolean;
}

export interface ProjectPathReference {
  field: ProjectPathField;
  sourceKind: PathSourceKind;
  displayValue: string;
  filesystemPath: string;
  relativePath: string;
  repoRef?: GitRepoRef | null;
}

export interface ProjectPathConfig {
  root: ProjectPathReference;
  planDocs: ProjectPathReference;
  sessions: ProjectPathReference;
  progress: ProjectPathReference;
}

export interface GitHubIntegrationSettings {
  enabled: boolean;
  provider: 'github';
  baseUrl: string;
  username: string;
  token: string;
  cacheRoot: string;
  writeEnabled: boolean;
}

export interface GitHubIntegrationSettingsUpdateRequest {
  enabled: boolean;
  baseUrl: string;
  username: string;
  token: string;
  cacheRoot: string;
  writeEnabled: boolean;
}

export interface GitHubIntegrationSettingsResponse {
  enabled: boolean;
  provider: 'github';
  baseUrl: string;
  username: string;
  tokenConfigured: boolean;
  maskedToken: string;
  cacheRoot: string;
  writeEnabled: boolean;
}

export interface GitHubProbeResult {
  state: 'idle' | 'success' | 'warning' | 'error';
  message: string;
  checkedAt: string;
  path: string;
}

export interface GitHubCredentialValidationRequest {
  projectId: string;
  settings?: GitHubIntegrationSettingsUpdateRequest | null;
}

export interface GitHubCredentialValidationResponse {
  auth: GitHubProbeResult;
  repoAccess: GitHubProbeResult;
}

export interface GitHubPathValidationRequest {
  projectId: string;
  reference: ProjectPathReference;
  rootReference?: ProjectPathReference | null;
}

export interface GitHubPathValidationResponse {
  reference: ProjectPathReference;
  status: GitHubProbeResult;
  resolvedLocalPath: string;
}

export interface GitHubWorkspaceRefreshRequest {
  projectId: string;
  reference?: ProjectPathReference | null;
  force: boolean;
}

export interface GitHubWorkspaceRefreshResponse {
  projectId: string;
  status: GitHubProbeResult;
  resolvedLocalPath: string;
}

export interface GitHubWriteCapabilityRequest {
  projectId: string;
  reference?: ProjectPathReference | null;
}

export interface GitHubWriteCapabilityResponse {
  projectId: string;
  canWrite: boolean;
  status: GitHubProbeResult;
}

export interface ProjectResolvedPathDTO {
  field: ProjectPathField;
  sourceKind: PathSourceKind;
  path: string;
  diagnostic: string;
}

export interface ProjectResolvedPathsDTO {
  projectId: string;
  root: ProjectResolvedPathDTO;
  planDocs: ProjectResolvedPathDTO;
  sessions: ProjectResolvedPathDTO;
  progress: ProjectResolvedPathDTO;
}

export interface LinkedDocument {
  id: string;
  title: string;
  filePath: string;
  docType: 'prd' | 'implementation_plan' | 'report' | 'phase_plan' | 'progress' | 'design_doc' | 'spec' | string;
  category?: string;
  slug?: string;
  canonicalSlug?: string;
  frontmatterKeys?: string[];
  relatedRefs?: string[];
  prdRef?: string;
  lineageFamily?: string;
  lineageParent?: string;
  lineageChildren?: string[];
  lineageType?: string;
  linkedFeatures?: LinkedFeatureRef[];
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
  description?: string;
  summary?: string;
  priority?: string;
  riskLevel?: string;
  complexity?: string;
  track?: string;
  timelineEstimate?: string;
  targetRelease?: string;
  milestone?: string;
  owners?: string[];
  contributors?: string[];
  requestLogIds?: string[];
  commitRefs?: string[];
  prRefs?: string[];
  executionReadiness?: string;
  testImpact?: string;
  updatedAt: string;
  plannedAt?: string;
  startedAt?: string;
  completedAt?: string;
  linkedDocs: LinkedDocument[];
  linkedFeatures?: LinkedFeatureRef[];
  primaryDocuments?: FeaturePrimaryDocuments;
  documentCoverage?: FeatureDocumentCoverage;
  qualitySignals?: FeatureQualitySignals;
  phases: FeaturePhase[];
  relatedFeatures: string[];
  dates?: EntityDates;
  timeline?: TimelineEvent[];
}

export interface FeaturePrimaryDocuments {
  prd?: LinkedDocument | null;
  implementationPlan?: LinkedDocument | null;
  phasePlans: LinkedDocument[];
  progressDocs: LinkedDocument[];
  supportingDocs: LinkedDocument[];
}

export interface FeatureDocumentCoverage {
  present: string[];
  missing: string[];
  countsByType: Record<string, number>;
  coverageScore: number;
}

export interface FeatureQualitySignals {
  blockerCount: number;
  atRiskTaskCount: number;
  integritySignalRefs: string[];
  reportFindingsBySeverity: Record<string, number>;
  testImpact: string;
  hasBlockingSignals: boolean;
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

export type DefinitionReferenceStatus = 'resolved' | 'cached' | 'unresolved';

export interface RecommendedStackDefinitionRef {
  definitionType: string;
  externalId: string;
  displayName: string;
  version: string;
  sourceUrl: string;
  status: DefinitionReferenceStatus;
}

export interface ExecutionArtifactReference {
  key: string;
  label: string;
  kind: string;
  status: string;
  definitionType: string;
  externalId: string;
  sourceUrl: string;
  sourceAttribution: string;
  description: string;
  metadata: Record<string, unknown>;
}

export interface RecommendedStackComponent {
  componentType: 'workflow' | 'agent' | 'skill' | 'context_module' | 'command' | 'model_policy' | 'artifact';
  componentKey: string;
  label: string;
  status: 'explicit' | 'inferred' | 'resolved' | 'unresolved';
  confidence: number;
  sourceAttribution: string;
  payload: Record<string, unknown>;
  definition?: RecommendedStackDefinitionRef | null;
  artifactRef?: ExecutionArtifactReference | null;
}

export interface SimilarWorkExample {
  sessionId: string;
  featureId: string;
  title: string;
  workflowRef: string;
  similarityScore: number;
  reasons: string[];
  matchedComponents: string[];
  startedAt: string;
  endedAt: string;
  totalCost: number;
  durationSeconds: number;
  successScore: number;
  efficiencyScore: number;
  qualityScore: number;
  riskScore: number;
}

export interface StackRecommendationEvidence {
  id: string;
  label: string;
  summary: string;
  sourceType: string;
  sourceId: string;
  sourcePath: string;
  confidence: number;
  metrics: Record<string, unknown>;
  similarWork: SimilarWorkExample[];
}

export interface RecommendedStack {
  id: string;
  label: string;
  workflowRef: string;
  commandAlignment: string;
  confidence: number;
  sampleSize: number;
  successScore: number;
  efficiencyScore: number;
  qualityScore: number;
  riskScore: number;
  sourceSessionId: string;
  sourceFeatureId: string;
  explanation: string;
  components: RecommendedStackComponent[];
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
  tokensIn?: number;
  tokensOut?: number;
  modelIOTokens?: number;
  cacheCreationInputTokens?: number;
  cacheReadInputTokens?: number;
  cacheInputTokens?: number;
  observedTokens?: number;
  toolReportedTokens?: number;
  currentContextTokens?: number;
  contextWindowSize?: number;
  contextUtilizationPct?: number;
  contextMeasurementSource?: string;
  contextMeasuredAt?: string;
  cacheShare?: number;
  outputShare?: number;
  reportedCostUsd?: number | null;
  recalculatedCostUsd?: number | null;
  displayCostUsd?: number | null;
  costProvenance?: 'reported' | 'recalculated' | 'estimated' | 'unknown';
  costConfidence?: number;
  costMismatchPct?: number | null;
  pricingModelSource?: string;
  gitCommitHash?: string;
  gitCommitHashes?: string[];
  gitBranch?: string;
  pullRequests?: Array<{
    prNumber?: string;
    prUrl?: string;
    prRepository?: string;
  }>;
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
    prLinks?: Array<{
      prNumber?: string;
      prUrl?: string;
      prRepository?: string;
    }>;
    commitCorrelations?: Array<{
      commitHash?: string;
      windowStart?: string;
      windowEnd?: string;
      eventCount?: number;
      toolCallCount?: number;
      commandCount?: number;
      artifactCount?: number;
      tokenInput?: number;
      tokenOutput?: number;
      fileCount?: number;
      additions?: number;
      deletions?: number;
      costUsd?: number;
      featureIds?: string[];
      phases?: string[];
      taskIds?: string[];
      filePaths?: string[];
      provisional?: boolean;
    }>;
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
  recommendedStack?: RecommendedStack | null;
  stackAlternatives: RecommendedStack[];
  stackEvidence: StackRecommendationEvidence[];
  definitionResolutionWarnings: FeatureExecutionWarning[];
  generatedAt: string;
}

export type ExecutionPolicyVerdict = 'allow' | 'requires_approval' | 'deny';
export type ExecutionRunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled' | 'blocked';
export type ExecutionRiskLevel = 'low' | 'medium' | 'high';
export type ExecutionApprovalDecision = 'pending' | 'approved' | 'denied';
export type ExecutionEventStream = 'stdout' | 'stderr' | 'system';

export interface ExecutionPolicyResult {
  verdict: ExecutionPolicyVerdict;
  riskLevel: ExecutionRiskLevel;
  requiresApproval: boolean;
  normalizedCommand: string;
  commandTokens: string[];
  resolvedCwd: string;
  reasonCodes: string[];
}

export interface ExecutionRun {
  id: string;
  projectId: string;
  featureId: string;
  provider: string;
  sourceCommand: string;
  normalizedCommand: string;
  cwd: string;
  envProfile: string;
  recommendationRuleId: string;
  riskLevel: ExecutionRiskLevel;
  policyVerdict: ExecutionPolicyVerdict;
  requiresApproval: boolean;
  approvedBy: string;
  approvedAt: string;
  status: ExecutionRunStatus;
  exitCode: number | null;
  startedAt: string;
  endedAt: string;
  retryOfRunId: string;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface ExecutionRunEvent {
  id: number | null;
  runId: string;
  sequenceNo: number;
  stream: ExecutionEventStream;
  eventType: string;
  payloadText: string;
  payload: Record<string, unknown>;
  occurredAt: string;
}

export interface ExecutionRunEventPage {
  runId: string;
  items: ExecutionRunEvent[];
  nextSequence: number;
}

export interface ExecutionApproval {
  id: number | null;
  runId: string;
  decision: ExecutionApprovalDecision;
  reason: string;
  requestedAt: string;
  resolvedAt: string;
  requestedBy: string;
  resolvedBy: string;
}

// ── Test Visualizer Types ──────────────────────────────────────────

export type TestStatus =
  | 'passed'
  | 'failed'
  | 'skipped'
  | 'error'
  | 'xfailed'
  | 'xpassed'
  | 'unknown'
  | 'running';

export type TestRunStatus = 'running' | 'complete' | 'failed';

export interface TestRun {
  runId: string;
  projectId: string;
  timestamp: string;
  gitSha: string;
  branch: string;
  agentSessionId: string;
  envFingerprint: string;
  trigger: 'local' | 'ci' | string;
  status: TestRunStatus;
  totalTests: number;
  passedTests: number;
  failedTests: number;
  skippedTests: number;
  durationMs: number;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface TestDefinition {
  testId: string;
  projectId: string;
  path: string;
  name: string;
  framework: string;
  tags: string[];
  owner: string;
  createdAt: string;
  updatedAt: string;
}

export interface TestResult {
  runId: string;
  testId: string;
  status: TestStatus;
  durationMs: number;
  errorFingerprint: string;
  errorMessage: string;
  artifactRefs: string[];
  stdoutRef: string;
  stderrRef: string;
  createdAt: string;
}

export interface TestDomain {
  domainId: string;
  projectId: string;
  name: string;
  parentId: string | null;
  description: string;
  tier: 'core' | 'extras' | 'nonfunc' | string;
  sortOrder: number;
}

export interface TestFeatureMapping {
  mappingId: number;
  projectId: string;
  testId: string;
  featureId: string;
  domainId: string | null;
  providerSource: string;
  confidence: number;
  isPrimary: boolean;
  createdAt: string;
}

export interface TestIntegritySignal {
  signalId: string;
  projectId: string;
  gitSha: string;
  filePath: string;
  testId: string | null;
  signalType:
    | 'assertion_removed'
    | 'skip_introduced'
    | 'xfail_added'
    | 'broad_exception'
    | 'edited_before_green'
    | string;
  severity: 'low' | 'medium' | 'high' | string;
  details: Record<string, unknown>;
  linkedRunIds: string[];
  agentSessionId: string;
  createdAt: string;
}

export interface DomainHealthRollup {
  domainId: string;
  domainName: string;
  tier: 'core' | 'extras' | 'nonfunc' | string;
  totalTests: number;
  passed: number;
  failed: number;
  skipped: number;
  passRate: number;
  integrityScore: number;
  confidenceScore?: number;
  lastRunAt: string | null;
  children: DomainHealthRollup[];
}

export interface FeatureTestHealth {
  featureId: string;
  featureName: string;
  domainId: string | null;
  totalTests: number;
  passed: number;
  failed: number;
  skipped: number;
  passRate: number;
  integrityScore: number;
  confidenceScore?: number;
  lastRunAt: string | null;
  openSignals: number;
}

export interface TestTimelinePoint {
  date: string;
  passRate: number;
  passed: number;
  failed: number;
  skipped: number;
  runIds: string[];
  signals: TestIntegritySignal[];
}

export interface FeatureTestTimeline {
  featureId: string;
  featureName: string;
  timeline: TestTimelinePoint[];
  firstGreen: string | null;
  lastRed: string | null;
  lastKnownGood: string | null;
}

export interface TestRunDetail {
  run: TestRun;
  results: TestResult[];
  definitions: Record<string, TestDefinition>;
  integritySignals: TestIntegritySignal[];
}

export interface CorrelatedTestRun {
  run: TestRun;
  agentSession: AgentSession | null;
  features: FeatureTestHealth[];
  integritySignals: TestIntegritySignal[];
  links: Record<string, string>;
}

export interface TestSourceStatus {
  platformId: string;
  enabled: boolean;
  watch: boolean;
  resultsDir: string;
  resolvedDir: string;
  patterns: string[];
  exists: boolean;
  readable: boolean;
  matchedFiles: number;
  sampleFiles: string[];
  lastError: string;
  lastSyncedAt: string;
}

export interface EffectiveTestFlags {
  testVisualizerEnabled: boolean;
  integritySignalsEnabled: boolean;
  liveTestUpdatesEnabled: boolean;
  semanticMappingEnabled: boolean;
}

export interface TestVisualizerConfig {
  projectId: string;
  flags: ProjectTestFlags;
  effectiveFlags: EffectiveTestFlags;
  autoSyncOnStartup: boolean;
  maxFilesPerScan: number;
  maxParseConcurrency: number;
  instructionProfile: string;
  instructionNotes: string;
  parserHealth: Record<string, boolean>;
  sources: TestSourceStatus[];
}

export interface TestSyncResponse {
  projectId: string;
  stats: Record<string, unknown>;
  sources: TestSourceStatus[];
}

export interface TestMetricSummary {
  projectId: string;
  totalMetrics: number;
  byPlatform: Record<string, number>;
  byMetricType: Record<string, number>;
  latestCollectedAt: string;
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
