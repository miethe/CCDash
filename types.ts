
export type TaskStatus = 'todo' | 'in-progress' | 'review' | 'done';

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

export type LogType = 'message' | 'tool' | 'subagent' | 'skill';

export interface SessionLog {
  id: string;
  timestamp: string;
  speaker: 'user' | 'agent' | 'system';
  type: LogType;
  agentName?: string;
  content: string;
  toolCall?: {
    name: string;
    args: string;
    status: 'success' | 'error';
    output?: string;
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

export interface SessionFileUpdate {
  filePath: string;
  commits: string[];
  additions: number;
  deletions: number;
  agentName: string;
  timestamp: string;
}

export interface SessionArtifact {
  id: string;
  type: 'memory' | 'request_log' | 'knowledge_base' | 'external_link';
  title: string;
  source: string; // e.g., "SkillMeat", "MeatyCapture"
  description?: string;
  url?: string;
  preview?: string;
}

export interface AgentSession {
  id: string;
  taskId: string;
  status: 'active' | 'completed';
  model: string;
  durationSeconds: number;
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
  // Git Integration
  gitCommitHash?: string;
  gitAuthor?: string;
  gitBranch?: string;
}

export interface PlanDocument {
  id: string;
  title: string;
  filePath: string;
  status: 'draft' | 'active' | 'archived' | 'deprecated' | 'completed';
  lastModified: string;
  author: string;
  content?: string; // Raw markdown content
  frontmatter: {
    tags: string[];
    linkedFeatures?: string[]; // IDs like T-101
    linkedSessions?: string[]; // IDs like S-8821
    relatedFiles?: string[];
    version?: string;
    commits?: string[];
    prs?: string[];
  };
}

export interface AnalyticsMetric {
  date: string;
  cost: number;
  featuresShipped: number;
  avgQuality: number;
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
  docType: 'prd' | 'implementation_plan' | 'report' | 'phase_plan' | 'spec';
}

export interface FeaturePhase {
  phase: string;
  title: string;
  status: string;
  progress: number;
  totalTasks: number;
  completedTasks: number;
  tasks: ProjectTask[];
}

export interface Feature {
  id: string;
  name: string;
  status: string;
  totalTasks: number;
  completedTasks: number;
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
