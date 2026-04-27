
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

export interface SessionTranscriptAppendPayload {
  sessionId: string;
  entryId: string;
  sequenceNo: number;
  kind: LogType | string;
  createdAt: string;
  payload: Pick<SessionLog, 'id' | 'timestamp' | 'speaker' | 'type' | 'agentName' | 'content' | 'linkedSessionId' | 'relatedToolCallId' | 'metadata' | 'toolCall'>;
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
  intelligenceSummary?: SessionIntelligenceSessionRollup | null;
  // Git Integration
  gitCommitHash?: string;
  gitCommitHashes?: string[];
  gitAuthor?: string;
  gitBranch?: string;
  dates?: EntityDates;
  timeline?: TimelineEvent[];
  // P15-001: Agent classification & planning correlation
  subagentType?: string | null;
  displayAgentType?: string | null;
  linkedFeatureIds?: string[];
  phaseHints?: string[];
  taskHints?: string[];
  transcriptTruncated?: { droppedCount: number; firstRetainedTimestamp?: string };
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

export type SessionIntelligenceConcern = 'sentiment' | 'churn' | 'scope_drift';

export interface SessionIntelligenceCapability {
  supported: boolean;
  authoritative: boolean;
  storageProfile: string;
  searchMode: string;
  detail: string;
}

export interface SessionSemanticSearchMatch {
  sessionId: string;
  featureId: string;
  rootSessionId: string;
  threadSessionId: string;
  blockKind: string;
  blockIndex: number;
  eventTimestamp: string;
  score: number;
  matchedTerms: string[];
  messageIds: string[];
  sourceLogIds: string[];
  content: string;
  snippet: string;
}

export interface SessionSemanticSearchResponse {
  version: string;
  query: string;
  total: number;
  offset: number;
  limit: number;
  capability: SessionIntelligenceCapability;
  items: SessionSemanticSearchMatch[];
}

export interface SessionIntelligenceConcernSummary {
  label: string;
  score: number;
  confidence: number;
  factCount: number;
  flaggedCount: number;
}

export interface SessionIntelligenceSessionRollup {
  sessionId: string;
  featureId: string;
  rootSessionId: string;
  startedAt: string;
  endedAt: string;
  sentiment: SessionIntelligenceConcernSummary;
  churn: SessionIntelligenceConcernSummary;
  scopeDrift: SessionIntelligenceConcernSummary;
}

export interface SessionIntelligenceListResponse {
  version: string;
  generatedAt: string;
  total: number;
  offset: number;
  limit: number;
  items: SessionIntelligenceSessionRollup[];
}

export interface SessionSentimentFact {
  sessionId: string;
  featureId: string;
  rootSessionId: string;
  threadSessionId: string;
  sourceMessageId: string;
  sourceLogId: string;
  messageIndex: number;
  sentimentLabel: string;
  sentimentScore: number;
  confidence: number;
  heuristicVersion: string;
  evidence: Record<string, unknown>;
}

export interface SessionCodeChurnFact {
  sessionId: string;
  featureId: string;
  rootSessionId: string;
  threadSessionId: string;
  filePath: string;
  firstSourceLogId: string;
  lastSourceLogId: string;
  firstMessageIndex: number;
  lastMessageIndex: number;
  touchCount: number;
  distinctEditTurnCount: number;
  repeatTouchCount: number;
  rewritePassCount: number;
  additionsTotal: number;
  deletionsTotal: number;
  netDiffTotal: number;
  churnScore: number;
  progressScore: number;
  lowProgressLoop: boolean;
  confidence: number;
  heuristicVersion: string;
  evidence: Record<string, unknown>;
}

export interface SessionScopeDriftFact {
  sessionId: string;
  featureId: string;
  rootSessionId: string;
  threadSessionId: string;
  plannedPathCount: number;
  actualPathCount: number;
  matchedPathCount: number;
  outOfScopePathCount: number;
  driftRatio: number;
  adherenceScore: number;
  confidence: number;
  heuristicVersion: string;
  evidence: Record<string, unknown>;
}

export interface SessionIntelligenceDetailResponse {
  version: string;
  sessionId: string;
  featureId: string;
  rootSessionId: string;
  summary?: SessionIntelligenceSessionRollup | null;
  sentimentFacts: SessionSentimentFact[];
  churnFacts: SessionCodeChurnFact[];
  scopeDriftFacts: SessionScopeDriftFact[];
}

export interface SessionIntelligenceDrilldownItem {
  concern: SessionIntelligenceConcern;
  sessionId: string;
  featureId: string;
  rootSessionId: string;
  startedAt: string;
  endedAt: string;
  label: string;
  score: number;
  confidence: number;
  messageIndex: number;
  sourceMessageId: string;
  sourceLogId: string;
  filePath: string;
  evidence: Record<string, unknown>;
}

export interface SessionIntelligenceDrilldownResponse {
  version: string;
  concern: SessionIntelligenceConcern;
  generatedAt: string;
  total: number;
  offset: number;
  limit: number;
  items: SessionIntelligenceDrilldownItem[];
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
  blockedBy?: string[];
  sequenceOrder?: number | null;
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
    blockedBy?: string[];
    sequenceOrder?: number | null;
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
    blockedBy?: string[];
    sequenceOrder?: number | null;
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

export type WorkflowRegistryCorrelationState = 'strong' | 'hybrid' | 'weak' | 'unresolved';
export type WorkflowRegistryResolutionKind = 'workflow_definition' | 'command_artifact' | 'dual_backed' | 'none';
export type WorkflowRegistryIssueSeverity = 'info' | 'warning' | 'error';
export type WorkflowRegistryActionTarget = 'external' | 'internal';

export interface WorkflowRegistryIssue {
  code: string;
  severity: WorkflowRegistryIssueSeverity;
  title: string;
  message: string;
  metadata: Record<string, unknown>;
}

export interface WorkflowRegistryIdentity {
  registryId: string;
  observedWorkflowFamilyRef: string;
  observedAliases: string[];
  displayLabel: string;
  resolvedWorkflowId: string;
  resolvedWorkflowLabel: string;
  resolvedWorkflowSourceUrl: string;
  resolvedCommandArtifactId: string;
  resolvedCommandArtifactLabel: string;
  resolvedCommandArtifactSourceUrl: string;
  resolutionKind: WorkflowRegistryResolutionKind;
  correlationState: WorkflowRegistryCorrelationState;
}

export interface WorkflowRegistryBundleAlignment {
  bundleId: string;
  bundleName: string;
  matchScore: number;
  matchedRefs: string[];
  sourceUrl: string;
}

export interface WorkflowRegistryContextModule {
  contextRef: string;
  moduleId: string;
  moduleName: string;
  status: string;
  sourceUrl: string;
  previewTokens: number;
}

export interface WorkflowRegistryCompositionSummary {
  artifactRefs: string[];
  contextRefs: string[];
  resolvedContextModules: WorkflowRegistryContextModule[];
  planSummary: Record<string, unknown>;
  stageOrder: string[];
  gateCount: number;
  fanOutCount: number;
  bundleAlignment?: WorkflowRegistryBundleAlignment | null;
}

export interface WorkflowRegistryEffectivenessSummary {
  scopeType: string;
  scopeId: string;
  scopeLabel: string;
  sampleSize: number;
  successScore: number;
  efficiencyScore: number;
  qualityScore: number;
  riskScore: number;
  attributionCoverage: number;
  averageAttributionConfidence: number;
  evidenceSummary: Record<string, unknown>;
}

export interface WorkflowRegistryAction {
  id: string;
  label: string;
  target: WorkflowRegistryActionTarget;
  href: string;
  disabled: boolean;
  reason: string;
  metadata: Record<string, unknown>;
}

export interface WorkflowRegistrySessionEvidence {
  sessionId: string;
  featureId: string;
  title: string;
  status: string;
  workflowRef: string;
  startedAt: string;
  endedAt: string;
  href: string;
}

export interface WorkflowRegistryExecutionEvidence {
  executionId: string;
  status: string;
  startedAt: string;
  sourceUrl: string;
  parameters: Record<string, unknown>;
}

export interface WorkflowRegistryItem {
  id: string;
  identity: WorkflowRegistryIdentity;
  correlationState: WorkflowRegistryCorrelationState;
  issueCount: number;
  issues: WorkflowRegistryIssue[];
  effectiveness?: WorkflowRegistryEffectivenessSummary | null;
  observedCommandCount: number;
  representativeCommands: string[];
  sampleSize: number;
  lastObservedAt: string;
}

export interface WorkflowRegistryDetail extends WorkflowRegistryItem {
  composition: WorkflowRegistryCompositionSummary;
  representativeSessions: WorkflowRegistrySessionEvidence[];
  recentExecutions: WorkflowRegistryExecutionEvidence[];
  actions: WorkflowRegistryAction[];
}

export interface WorkflowRegistryListResponse {
  projectId: string;
  items: WorkflowRegistryItem[];
  correlationCounts: Record<WorkflowRegistryCorrelationState, number>;
  total: number;
  offset: number;
  limit: number;
  generatedAt: string;
}

export interface WorkflowRegistryDetailResponse {
  projectId: string;
  item: WorkflowRegistryDetail;
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

export type SessionMemoryDraftStatus = 'draft' | 'approved' | 'rejected' | 'published';
export type SessionMemoryDraftType = 'decision' | 'constraint' | 'gotcha' | 'style_rule' | 'learning';

export interface SessionMemoryDraft {
  id?: number | null;
  projectId: string;
  sessionId: string;
  featureId: string;
  rootSessionId: string;
  threadSessionId: string;
  workflowRef: string;
  title: string;
  memoryType: SessionMemoryDraftType;
  status: SessionMemoryDraftStatus;
  moduleName: string;
  moduleDescription: string;
  content: string;
  confidence: number;
  sourceMessageId: string;
  sourceLogId: string;
  sourceMessageIndex: number;
  contentHash: string;
  evidence: Record<string, unknown>;
  publishAttempts: number;
  publishedModuleId: string;
  publishedMemoryId: string;
  reviewedBy: string;
  reviewNotes: string;
  reviewedAt: string;
  publishedAt: string;
  lastPublishError: string;
  createdAt: string;
  updatedAt: string;
}

export interface SessionMemoryDraftListResponse {
  generatedAt: string;
  total: number;
  offset: number;
  limit: number;
  items: SessionMemoryDraft[];
}

export interface SessionMemoryDraftGenerateResponse {
  projectId: string;
  generatedAt: string;
  sessionsConsidered: number;
  draftsCreated: number;
  draftsUpdated: number;
  draftsSkipped: number;
  items: SessionMemoryDraft[];
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

export interface TelemetryQueueStats {
  pending: number;
  synced: number;
  failed: number;
  abandoned: number;
  total: number;
}

export interface TelemetryExportSettingsUpdateRequest {
  enabled: boolean;
}

export interface TelemetryExportStatus {
  enabled: boolean;
  configured: boolean;
  samEndpointMasked: string;
  queueStats: TelemetryQueueStats;
  lastPushTimestamp: string;
  eventsPushed24h: number;
  lastError: string;
  errorSeverity: 'info' | 'warning' | 'error' | '';
  envLocked: boolean;
  persistedEnabled: boolean;
}

export interface TelemetryPushNowResponse {
  success: boolean;
  batchSize: number;
  durationMs: number;
  error: string;
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
  featureFamily?: string;
  primaryDocRole?: string;
  blockedBy?: string[];
  sequenceOrder?: number | null;
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

export type PlanningNodeType =
  | 'design_spec'
  | 'prd'
  | 'implementation_plan'
  | 'progress'
  | 'context'
  | 'tracker'
  | 'report';

export type PlanningEdgeRelationType =
  | 'promotes_to'
  | 'implements'
  | 'phase_of'
  | 'informs'
  | 'blocked_by'
  | 'family_member_of'
  | 'tracked_by'
  | 'executed_by';

export type PlanningStatusProvenanceSource = 'raw' | 'derived' | 'inferred_complete' | 'unknown';

export type PlanningMismatchStateValue =
  | 'aligned'
  | 'derived'
  | 'mismatched'
  | 'blocked'
  | 'stale'
  | 'reversed'
  | 'unresolved'
  | 'unknown';

export type PlanningPhaseBatchReadinessState = 'ready' | 'blocked' | 'waiting' | 'unknown';

export interface PlanningStatusEvidence {
  id: string;
  label: string;
  detail: string;
  sourceType: string;
  sourceId: string;
  sourcePath: string;
}

export interface PlanningStatusProvenance {
  source: PlanningStatusProvenanceSource;
  reason: string;
  evidence: PlanningStatusEvidence[];
}

export interface PlanningMismatchState {
  state: PlanningMismatchStateValue;
  reason: string;
  isMismatch: boolean;
  evidence: PlanningStatusEvidence[];
}

export interface PlanningEffectiveStatus {
  rawStatus: string;
  effectiveStatus: string;
  provenance: PlanningStatusProvenance;
  mismatchState: PlanningMismatchState;
}

export interface PlanningNode {
  id: string;
  type: PlanningNodeType;
  path: string;
  title: string;
  featureSlug: string;
  rawStatus: string;
  effectiveStatus: string;
  mismatchState: PlanningMismatchState;
  updatedAt: string;
  statusDetail?: PlanningEffectiveStatus | null;
}

/**
 * Per-model token breakdown within a FeatureTokenRollup.
 * Delivered by T7-004 (PlanningQueryService / FeatureForensicsQueryService).
 */
export interface FeatureModelTokens {
  /** Normalized model identity key: "opus" | "sonnet" | "haiku" */
  model: 'opus' | 'sonnet' | 'haiku' | string;
  totalTokens: number;
  tokenInput?: number;
  tokenOutput?: number;
}

/**
 * Feature-level token + story-point rollup, added to ProjectPlanningGraph by T7-004.
 * The backend attaches this per featureSlug; frontend reads it as server truth only.
 */
export interface FeatureTokenRollup {
  featureSlug: string;
  /** Aggregated story-point estimate from progress files. 0 when unavailable. */
  storyPoints: number;
  /** Sum of all session tokens linked to this feature. 0 when no sessions linked. */
  totalTokens: number;
  /** Per-model breakdown. Empty array when no sessions linked. */
  byModel: FeatureModelTokens[];
}

export interface PlanningArtifactRef {
  artifactId: string;
  title: string;
  filePath: string;
  canonicalPath: string;
  docType: string;
  status: string;
  updatedAt: string;
  sourceRef: string;
}

export interface PlanningSpikeItem {
  spikeId: string;
  title: string;
  status: string;
  filePath: string;
  sourceRef: string;
}

export interface PlanningOpenQuestionItem {
  oqId: string;
  question: string;
  severity: string;
  answerText: string;
  resolved: boolean;
  pendingSync: boolean;
  sourceDocumentId: string;
  sourceDocumentPath: string;
  updatedAt: string;
}

export interface PlanningTokenUsageByModel {
  opus: number;
  sonnet: number;
  haiku: number;
  other: number;
  total: number;
}

export interface PlanningEdge {
  sourceId: string;
  targetId: string;
  relationType: PlanningEdgeRelationType;
}

export interface PlanningPhaseBatchReadiness {
  state: PlanningPhaseBatchReadinessState;
  reason: string;
  blockingNodeIds: string[];
  blockingTaskIds: string[];
  evidence: PlanningStatusEvidence[];
  isReady: boolean;
}

export interface PlanningPhaseBatch {
  featureSlug: string;
  phase: string;
  batchId: string;
  taskIds: string[];
  assignedAgents: string[];
  fileScopeHints: string[];
  readinessState: PlanningPhaseBatchReadinessState;
  readiness: PlanningPhaseBatchReadiness;
}

export interface PlanningGraph {
  nodes: PlanningNode[];
  edges: PlanningEdge[];
  phaseBatches: PlanningPhaseBatch[];
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
  planningStatus?: PlanningEffectiveStatus | null;
  phaseBatches?: PlanningPhaseBatch[];
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
  featureFamily?: string;
  updatedAt: string;
  plannedAt?: string;
  startedAt?: string;
  completedAt?: string;
  linkedDocs: LinkedDocument[];
  linkedFeatures?: LinkedFeatureRef[];
  primaryDocuments?: FeaturePrimaryDocuments;
  documentCoverage?: FeatureDocumentCoverage;
  qualitySignals?: FeatureQualitySignals;
  dependencyState?: FeatureDependencyState | null;
  blockingFeatures?: FeatureDependencyEvidence[];
  familySummary?: FeatureFamilySummary | null;
  familyPosition?: FeatureFamilyPosition | null;
  executionGate?: ExecutionGateState | null;
  nextRecommendedFamilyItem?: FeatureFamilyItem | null;
  phases: FeaturePhase[];
  relatedFeatures: string[];
  planningStatus?: PlanningEffectiveStatus | null;
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

export type FeatureDependencyResolutionState = 'complete' | 'blocked' | 'blocked_unknown';
export type FeatureDependencyStateValue = 'unblocked' | 'blocked' | 'blocked_unknown' | 'ready_after_dependencies';
export type ExecutionGateStateValue =
  | 'ready'
  | 'blocked_dependency'
  | 'waiting_on_family_predecessor'
  | 'unknown_dependency_state';

export interface FeatureDependencyEvidence {
  dependencyFeatureId: string;
  dependencyFeatureName: string;
  dependencyStatus: string;
  dependencyCompletionEvidence: string[];
  blockingDocumentIds: string[];
  blockingReason: string;
  resolved: boolean;
  state: FeatureDependencyResolutionState;
}

export interface FeatureDependencyState {
  state: FeatureDependencyStateValue;
  dependencyCount: number;
  resolvedDependencyCount: number;
  blockedDependencyCount: number;
  unknownDependencyCount: number;
  blockingFeatureIds: string[];
  blockingDocumentIds: string[];
  firstBlockingDependencyId: string;
  blockingReason: string;
  completionEvidence: string[];
  dependencies: FeatureDependencyEvidence[];
}

export interface FeatureFamilyItem {
  featureId: string;
  featureName: string;
  featureStatus: string;
  featureFamily: string;
  sequenceOrder?: number | null;
  familyIndex: number;
  totalFamilyItems: number;
  isCurrent: boolean;
  isSequenced: boolean;
  isBlocked: boolean;
  isBlockedUnknown: boolean;
  isExecutable: boolean;
  dependencyState: FeatureDependencyState;
  primaryDocId: string;
  primaryDocPath: string;
}

export interface FeatureFamilyPosition {
  familyKey: string;
  currentIndex: number;
  sequencedIndex: number;
  totalItems: number;
  sequencedItems: number;
  unsequencedItems: number;
  display: string;
  currentItemId: string;
  nextItemId: string;
  nextItemLabel: string;
}

export interface FeatureFamilySummary {
  featureFamily: string;
  totalItems: number;
  sequencedItems: number;
  unsequencedItems: number;
  currentFeatureId: string;
  currentFeatureName: string;
  currentPosition: number;
  currentSequencedPosition: number;
  nextRecommendedFeatureId: string;
  nextRecommendedFamilyItem?: FeatureFamilyItem | null;
  items: FeatureFamilyItem[];
}

export interface ExecutionGateState {
  state: ExecutionGateStateValue;
  blockingDependencyId: string;
  firstExecutableFamilyItemId: string;
  recommendedFamilyItemId: string;
  familyPosition?: FeatureFamilyPosition | null;
  dependencyState: FeatureDependencyState;
  familySummary: FeatureFamilySummary;
  reason: string;
  waitingOnFamilyPredecessor: boolean;
  isReady: boolean;
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
  dependencyState?: FeatureDependencyState | null;
  familySummary?: FeatureFamilySummary | null;
  familyPosition?: FeatureFamilyPosition | null;
  executionGate?: ExecutionGateState | null;
  recommendedFamilyItem?: FeatureFamilyItem | null;
  warnings: FeatureExecutionWarning[];
  recommendedStack?: RecommendedStack | null;
  stackAlternatives: RecommendedStack[];
  stackEvidence: StackRecommendationEvidence[];
  definitionResolutionWarnings: FeatureExecutionWarning[];
  planningGraph?: PlanningGraph | null;
  generatedAt: string;
}

// ── Planning Launch Preparation (PCP-504) ────────────────────────────────────

export type LaunchBatchReadinessState = 'ready' | 'blocked' | 'partial' | 'unknown';
export type LaunchApprovalRequirement = 'none' | 'optional' | 'required';
export type LaunchRiskLevel = 'low' | 'medium' | 'high';
export type WorktreeContextStatus = 'draft' | 'ready' | 'in_use' | 'archived' | 'error';

export interface LaunchProviderCapability {
  provider: string;
  label: string;
  supported: boolean;
  supportsWorktrees: boolean;
  supportsModelSelection: boolean;
  defaultModel: string;
  availableModels: string[];
  requiresApproval: boolean;
  unsupportedReason: string;
  metadata: Record<string, unknown>;
}

export interface LaunchBatchTaskSummary {
  taskId: string;
  title: string;
  status: string;
  assignees: string[];
  blockers: string[];
}

export interface LaunchBatchSummary {
  batchId: string;
  phaseNumber: number;
  featureId: string;
  featureName: string;
  phaseTitle: string;
  readinessState: LaunchBatchReadinessState;
  isReady: boolean;
  blockedReason: string;
  taskIds: string[];
  tasks: LaunchBatchTaskSummary[];
  owners: string[];
  dependencies: string[];
}

export interface LaunchWorktreeSelection {
  worktreeContextId: string;
  createIfMissing: boolean;
  branch: string;
  worktreePath: string;
  baseBranch: string;
  notes: string;
}

export interface LaunchApprovalRequirementDetail {
  requirement: LaunchApprovalRequirement;
  reasonCodes: string[];
  riskLevel: LaunchRiskLevel;
}

export interface WorktreeContext {
  id: string;
  projectId: string;
  featureId: string;
  phaseNumber: number | null;
  batchId: string;
  branch: string;
  worktreePath: string;
  baseBranch: string;
  baseCommitSha: string;
  status: WorktreeContextStatus;
  lastRunId: string;
  provider: string;
  notes: string;
  metadata: Record<string, unknown>;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface LaunchPreparationRequest {
  projectId: string;
  featureId: string;
  phaseNumber: number;
  batchId: string;
  providerPreference?: string;
  modelPreference?: string;
  worktreeContextId?: string;
}

export interface LaunchPreparation {
  projectId: string;
  featureId: string;
  phaseNumber: number;
  batchId: string;
  batch: LaunchBatchSummary;
  providers: LaunchProviderCapability[];
  selectedProvider: string;
  selectedModel: string;
  worktreeCandidates: WorktreeContext[];
  worktreeSelection: LaunchWorktreeSelection;
  approval: LaunchApprovalRequirementDetail;
  warnings: string[];
  generatedAt: string;
}

export interface LaunchStartRequest {
  projectId: string;
  featureId: string;
  phaseNumber: number;
  batchId: string;
  provider: string;
  model?: string;
  worktree: LaunchWorktreeSelection;
  commandOverride?: string;
  envProfile?: string;
  approvalDecision?: 'approved' | '';
  actor?: string;
  metadata?: Record<string, unknown>;
}

export interface LaunchStartResponse {
  runId: string;
  worktreeContextId: string;
  status: string;
  requiresApproval: boolean;
  warnings: string[];
}

// ─────────────────────────────────────────────────────────────────────────────

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
  liveUpdates?: {
    active_subscribers: number;
    buffered_topics: number;
    active_topic_subscriptions: number;
    published_events: number;
    dropped_events: number;
    buffer_evictions: number;
    replay_gaps: number;
    subscription_opens: number;
    subscription_closes: number;
  } | null;
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

// ── Planning Control Plane types (PCP-204) ────────────────────────────────────
// Wire format is snake_case (backend publishes no camelCase aliases).
// services/planning.ts adapts to camelCase on ingestion; these types reflect
// the adapted (camelCase) shape that the rest of the frontend consumes.

/** Common envelope fields present on every agent-query planning response. */
export interface AgentQueryEnvelope {
  /** Query resolution status: "ok" | "partial" | "error" */
  status: 'ok' | 'partial' | 'error';
  /** ISO-8601 timestamp indicating when the underlying data was last synced. */
  dataFreshness: string;
  /** ISO-8601 timestamp of when this response was generated. */
  generatedAt: string;
  /** Stable identifiers for the primary data sources consulted. */
  sourceRefs: string[];
}

/** Counts of PlanningNode instances bucketed by node type. */
export interface PlanningNodeCountsByType {
  prd: number;
  designSpec: number;
  implementationPlan: number;
  progress: number;
  context: number;
  tracker: number;
  report: number;
}

/** Lightweight per-feature summary used in project-level planning views. */
export interface FeatureSummaryItem {
  featureId: string;
  featureName: string;
  rawStatus: string;
  effectiveStatus: string;
  isMismatch: boolean;
  mismatchState: string;
  hasBlockedPhases: boolean;
  phaseCount: number;
  blockedPhaseCount: number;
  nodeCount: number;
}

export interface PlanningStatusCounts {
  shaping: number;
  planned: number;
  active: number;
  blocked: number;
  review: number;
  completed: number;
  deferred: number;
  staleOrMismatched: number;
}

export interface PlanningCtxPerPhase {
  contextCount: number;
  phaseCount: number;
  ratio: number | null;
  source: 'backend' | 'unavailable';
}

export interface PlanningTokenTelemetryEntry {
  modelFamily: string;
  totalTokens: number;
}

export interface PlanningTokenTelemetry {
  totalTokens: number | null;
  byModelFamily: PlanningTokenTelemetryEntry[];
  source: 'session_attribution' | 'unavailable';
}

/** Project-level planning health summary (PCP-201 query 1). */
export interface ProjectPlanningSummary extends AgentQueryEnvelope {
  projectId: string;
  projectName: string;
  totalFeatureCount: number;
  activeFeatureCount: number;
  staleFeatureCount: number;
  blockedFeatureCount: number;
  mismatchCount: number;
  reversalCount: number;
  staleFeatureIds: string[];
  reversalFeatureIds: string[];
  blockedFeatureIds: string[];
  nodeCountsByType: PlanningNodeCountsByType;
  featureSummaries: FeatureSummaryItem[];
  statusCounts?: PlanningStatusCounts;
  ctxPerPhase?: PlanningCtxPerPhase | null;
  tokenTelemetry?: PlanningTokenTelemetry | null;
}

/** Aggregated planning graph for a project or feature seed (PCP-201 query 2). */
export interface ProjectPlanningGraph extends AgentQueryEnvelope {
  projectId: string;
  featureId: string | null;
  depth: number | null;
  nodes: PlanningNode[];
  edges: PlanningEdge[];
  phaseBatches: PlanningPhaseBatch[];
  nodeCount: number;
  edgeCount: number;
  /**
   * Per-feature token + story-point rollups, keyed by featureSlug.
   * Present when the backend delivers T7-004 data; absent (undefined) otherwise.
   * UI must fall back to empty-state rendering when undefined or entry missing.
   */
  featureTokenRollups?: Record<string, FeatureTokenRollup>;
}

/** One phase's planning context inside FeaturePlanningContext. */
export interface PhaseContextItem {
  phaseId: string;
  phaseNumber?: number | null;
  phaseToken: string;
  phaseTitle: string;
  rawStatus: string;
  effectiveStatus: string;
  isMismatch: boolean;
  mismatchState: string;
  /** Serialised PlanningEffectiveStatus dict from the backend. */
  planningStatus: Record<string, unknown>;
  /** Serialised PlanningPhaseBatch dicts. */
  batches: PlanningPhaseBatch[];
  blockedBatchIds: string[];
  totalTasks: number;
  completedTasks: number;
  deferredTasks: number;
}

/** Single-feature planning context including graph, status, and phases (PCP-201 query 3). */
export interface FeaturePlanningContext extends AgentQueryEnvelope {
  featureId: string;
  featureName: string;
  rawStatus: string;
  effectiveStatus: string;
  mismatchState: string;
  /** Serialised PlanningEffectiveStatus dict from the backend. */
  planningStatus: Record<string, unknown>;
  /** Serialised subgraph as a PlanningGraph-compatible object. */
  graph: PlanningGraph;
  phases: PhaseContextItem[];
  blockedBatchIds: string[];
  linkedArtifactRefs: string[];
  specs?: PlanningArtifactRef[];
  prds?: PlanningArtifactRef[];
  plans?: PlanningArtifactRef[];
  ctxs?: PlanningArtifactRef[];
  reports?: PlanningArtifactRef[];
  spikes?: PlanningSpikeItem[];
  openQuestions?: PlanningOpenQuestionItem[];
  readyToPromote?: boolean;
  isStale?: boolean;
  totalTokens?: number;
  tokenUsageByModel?: PlanningTokenUsageByModel;
  category?: string;
  slug?: string;
  complexity?: string;
  tags?: string[];
}

/** Task summary within a phase operations response. */
export interface PhaseTaskItem {
  taskId: string;
  title: string;
  status: string;
  assignees: string[];
  blockers: string[];
  batchId: string;
}

/** Operational detail for a single phase (PCP-201 query 4). */
export interface PhaseOperations extends AgentQueryEnvelope {
  featureId: string;
  phaseNumber: number;
  phaseToken: string;
  phaseTitle: string;
  rawStatus: string;
  effectiveStatus: string;
  isReady: boolean;
  readinessState: string;
  phaseBatches: PlanningPhaseBatch[];
  blockedBatchIds: string[];
  tasks: PhaseTaskItem[];
  /** Serialised dependency resolution summary from the backend. */
  dependencyResolution: Record<string, unknown>;
  progressEvidence: string[];
}

// ── Planning Agent Session Board ──────────────────────────────────────────────

/** Evidence item explaining why a session was correlated to a planning artifact. */
export interface SessionCorrelationEvidence {
  /** How the correlation was detected: "explicit_link" | "phase_hint" | "task_hint" | "command_token" | "lineage" | "feature_ref" */
  sourceType: string;
  /** ID of the source artifact that produced this evidence, if applicable. */
  sourceId?: string;
  /** Human-readable label for the evidence source. */
  sourceLabel: string;
  /** Confidence tier of this evidence item. */
  confidence: 'high' | 'medium' | 'low' | 'unknown';
  /** Additional detail about how the evidence was derived. */
  detail?: string;
}

/** Planning-artifact correlation for a single agent session. */
export interface SessionCorrelation {
  featureId?: string;
  featureName?: string;
  phaseNumber?: number;
  phaseTitle?: string;
  batchId?: string;
  taskId?: string;
  taskTitle?: string;
  /** Aggregate confidence across all evidence items. */
  confidence: 'high' | 'medium' | 'low' | 'unknown';
  evidence: SessionCorrelationEvidence[];
}

/** A directed relationship from one session to another in a session tree. */
export interface BoardSessionRelationship {
  relatedSessionId: string;
  relationType: 'parent' | 'root' | 'sibling' | 'child';
  agentName?: string;
  state?: string;
}

/** A notable moment in a session timeline rendered as a board card marker. */
export interface SessionActivityMarker {
  markerType: 'tool_call' | 'file_edit' | 'command' | 'error' | 'completion';
  label: string;
  timestamp?: string;
  detail?: string;
}

/** Summarised token usage for a single session. */
export interface SessionTokenSummary {
  tokensIn: number;
  tokensOut: number;
  totalTokens: number;
  /** Fraction of the model context window consumed (0–1). */
  contextWindowPct?: number;
  model?: string;
}

/** A single card on the Planning Agent Session Board representing one agent session. */
export interface PlanningAgentSessionCard {
  sessionId: string;
  agentName?: string;
  agentType?: string;
  state: 'running' | 'thinking' | 'completed' | 'failed' | 'cancelled' | 'unknown';
  model?: string;
  /** Best-effort correlation to a planning feature / phase / task. */
  correlation?: SessionCorrelation;
  /** Deep-link to the session transcript view. */
  transcriptHref?: string;
  /** Deep-link to the planning page for the correlated feature. */
  planningHref?: string;
  /** Deep-link to the correlated phase detail. */
  phaseHref?: string;
  parentSessionId?: string;
  rootSessionId?: string;
  startedAt?: string;
  lastActivityAt?: string;
  durationSeconds?: number;
  tokenSummary?: SessionTokenSummary;
  relationships: BoardSessionRelationship[];
  activityMarkers: SessionActivityMarker[];
}

/** A column of cards on the Planning Agent Session Board, keyed by the active grouping. */
export interface PlanningBoardGroup {
  groupKey: string;
  groupLabel: string;
  groupType: 'state' | 'feature' | 'phase' | 'agent' | 'model';
  cards: PlanningAgentSessionCard[];
  cardCount: number;
}

/** The dimension by which board cards are grouped into columns. */
export type PlanningBoardGroupingMode = 'state' | 'feature' | 'phase' | 'agent' | 'model';

/** Top-level board payload returned by the agent-session-board query. */
export interface PlanningAgentSessionBoard {
  projectId: string;
  /** When set, the board is scoped to sessions correlated to this feature. */
  featureId?: string;
  grouping: PlanningBoardGroupingMode;
  groups: PlanningBoardGroup[];
  totalCardCount: number;
  activeCount: number;
  completedCount: number;
  /** ISO-8601 timestamp of the oldest data row contributing to this board. */
  dataFreshness?: string;
  /** ISO-8601 timestamp when this payload was assembled by the backend. */
  generatedAt?: string;
}

/** A reference to a context artifact (session, phase, task, etc.) used in next-run scaffolding. */
export interface NextRunContextRef {
  refType: 'session' | 'phase' | 'task' | 'artifact' | 'transcript';
  refId: string;
  refLabel: string;
  refPath?: string;
}

/** Context selection payload for the POST next-run-preview endpoint. */
export interface PromptContextSelection {
  sessionIds: string[];
  phaseRefs: string[];
  taskRefs: string[];
  artifactRefs: string[];
  transcriptRefs: string[];
}

/** Scaffolded preview of the command and context that would be used to continue planning work. */
export interface PlanningNextRunPreview {
  featureId: string;
  featureName?: string;
  phaseNumber?: number;
  /** CLI command that would launch the next planning session. */
  command: string;
  /** Template prompt with placeholders showing what context would be injected. */
  promptSkeleton: string;
  contextRefs: NextRunContextRef[];
  /** Advisory warnings about missing context, stale data, or blocked predecessors. */
  warnings: string[];
  /** ISO-8601 timestamp of the oldest data row used to build this preview. */
  dataFreshness?: string;
  /** ISO-8601 timestamp when this payload was assembled by the backend. */
  generatedAt?: string;
}
