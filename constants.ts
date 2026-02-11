
import { ProjectTask, AgentSession, AnalyticsMetric, AlertConfig, Notification, PlanDocument } from './types';

export const MOCK_TASKS: ProjectTask[] = [
  {
    id: 'T-101',
    title: 'Implement Vector Search',
    description: 'Add pgvector support to the backend and expose via search API.',
    status: 'done',
    owner: 'Nick Miethe',
    lastAgent: 'Claude 3.7 Sonnet',
    cost: 4.25,
    priority: 'high',
    projectType: 'Feature',
    projectLevel: 'Full',
    tags: ['backend', 'database', 'ai'],
    updatedAt: '2026-02-01T14:30:00Z',
    relatedFiles: [
      'docs/prd/vector-search.md', 
      'docs/arch/vector-search-plan.md',
      'docs/progress/phase-1-schema.md',
      'docs/progress/phase-2-api.md',
      'src/lib/db/schema.prisma', 
      'src/api/search.ts'
    ]
  },
  {
    id: 'T-102',
    title: 'Refactor Authentication',
    description: 'Migrate from custom JWT to Clerk authentication flow.',
    status: 'in-progress',
    owner: 'Nick Miethe',
    lastAgent: 'Claude 3.7 Sonnet',
    cost: 12.50,
    priority: 'high',
    projectType: 'Refactor',
    projectLevel: 'Full',
    tags: ['security', 'auth'],
    updatedAt: '2026-02-03T09:15:00Z',
    relatedFiles: [
      'docs/arch/auth-migration.md', 
      'docs/progress/auth-phase-1-cleanup.md',
      'src/components/AuthProvider.tsx', 
      'src/middleware.ts'
    ]
  },
  {
    id: 'T-103',
    title: 'Design Dashboard UI',
    description: 'Create responsive layout for the analytics dashboard using Tailwind.',
    status: 'review',
    owner: 'Nick Miethe',
    lastAgent: 'Claude 3.5 Haiku',
    cost: 0.85,
    priority: 'medium',
    projectType: 'Feature',
    projectLevel: 'Quick',
    tags: ['frontend', 'ui/ux'],
    updatedAt: '2026-02-02T16:45:00Z',
    relatedFiles: [
      'docs/design/dashboard.md', 
      'src/components/Dashboard.tsx'
    ]
  },
  {
    id: 'T-104',
    title: 'Optimize API Latency',
    description: 'Investigate slow endpoints in the reporting service.',
    status: 'todo',
    owner: 'Nick Miethe',
    lastAgent: 'n/a',
    cost: 0,
    priority: 'medium',
    projectType: 'Bugfix',
    projectLevel: 'Quick',
    tags: ['backend', 'perf'],
    updatedAt: '2026-02-03T10:00:00Z',
    relatedFiles: [
      'docs/reports/latency-analysis.md'
    ]
  },
];

export const MOCK_SESSIONS: AgentSession[] = [
  {
    id: 'S-8821',
    taskId: 'T-101',
    status: 'completed',
    model: 'claude-3-7-sonnet-20260201',
    durationSeconds: 345,
    tokensIn: 15000,
    tokensOut: 4020,
    totalCost: 1.25,
    startedAt: '2026-02-01T14:00:00Z',
    qualityRating: 5,
    frictionRating: 1,
    gitCommitHash: 'a1b2c3d',
    gitAuthor: 'Nick Miethe',
    gitBranch: 'feature/vector-search',
    updatedFiles: [
      { filePath: 'src/lib/db/schema.prisma', commits: ['a1b2c3d'], additions: 45, deletions: 2, agentName: 'Architect', timestamp: '14:00:15' },
      { filePath: 'src/api/search.ts', commits: ['a1b2c3d', 'f9g8h7j'], additions: 120, deletions: 0, agentName: 'Coder', timestamp: '14:02:10' },
      { filePath: 'docs/prd/vector-search.md', commits: ['d4e5f6g'], additions: 15, deletions: 5, agentName: 'Planner', timestamp: '14:04:30' }
    ],
    linkedArtifacts: [
      { id: 'MEM-101', type: 'memory', title: 'Preferred DB Schema Style', source: 'SkillMeat', description: 'User prefers snake_case for DB columns and strictly typed interfaces.' },
      { id: 'LOG-552', type: 'request_log', title: 'Capture-8821-A', source: 'MeatyCapture', description: 'Full HTTP request/response cycle for the initial failed search implementation.' },
      { id: 'KB-003', type: 'knowledge_base', title: 'PGVector Best Practices', source: 'SkillMeat', description: 'Cached embeddings strategy context loaded.' }
    ],
    toolsUsed: [
      { name: 'read_file', count: 12, successRate: 1.0, category: 'system' },
      { name: 'edit_file', count: 3, successRate: 1.0, category: 'edit' },
      { name: 'run_terminal', count: 5, successRate: 0.8, category: 'test' },
    ],
    impactHistory: [
      { timestamp: '00:00', locAdded: 0, locDeleted: 0, fileCount: 42, testPassCount: 120, testFailCount: 0 },
      { timestamp: '01:30', locAdded: 50, locDeleted: 10, fileCount: 43, testPassCount: 120, testFailCount: 2 },
      { timestamp: '03:15', locAdded: 120, locDeleted: 20, fileCount: 43, testPassCount: 122, testFailCount: 0 },
      { timestamp: '05:45', locAdded: 120, locDeleted: 20, fileCount: 43, testPassCount: 135, testFailCount: 0 },
    ],
    logs: [
      { id: 'l1', timestamp: '14:00:01', speaker: 'user', type: 'message', content: 'Please implement the vector search using pgvector. Ensure the schema is updated first.' },
      { id: 'l2', timestamp: '14:00:05', speaker: 'agent', type: 'skill', agentName: 'Architect', content: 'Loading Skill: DatabaseSchemaManager', skillDetails: { name: 'DatabaseSchemaManager', version: 'v2.1', description: 'Handles Prisma and SQL schema migrations safely.' } },
      { id: 'l3', timestamp: '14:00:10', speaker: 'agent', type: 'tool', agentName: 'Architect', content: 'Reading schema.prisma to identify vector extension requirements.', toolCall: { name: 'read_file', args: 'schema.prisma', status: 'success', output: 'datasource db {\n  provider = "postgresql"\n  url      = env("DATABASE_URL")\n}' } },
      { id: 'l4', timestamp: '14:01:20', speaker: 'agent', type: 'subagent', agentName: 'Orchestrator', content: 'Spawning Coder subagent to handle the npm installations and file edits.', subagentThread: [
        { id: 'sl1', timestamp: '14:01:21', speaker: 'user', type: 'message', content: 'Install pgvector and update the schema.' },
        { id: 'sl2', timestamp: '14:01:25', speaker: 'agent', type: 'tool', agentName: 'Coder', content: 'Running installation', toolCall: { name: 'run_terminal', args: 'npm install pgvector', status: 'success', output: 'added 1 package, and audited 402 packages in 2s' } },
        { id: 'sl3', timestamp: '14:02:00', speaker: 'agent', type: 'message', content: 'Installation complete. Now editing the schema file.' }
      ] },
      { id: 'l5', timestamp: '14:05:00', speaker: 'agent', type: 'message', agentName: 'Architect', content: 'Vector search implementation is complete. I have updated the schema and the search API. Ready for testing.' },
    ],
  },
  {
    id: 'S-8822',
    taskId: 'T-102',
    status: 'active',
    model: 'claude-3-7-sonnet-20260201',
    durationSeconds: 820,
    tokensIn: 45000,
    tokensOut: 8000,
    totalCost: 3.50,
    startedAt: '2026-02-03T08:00:00Z',
    qualityRating: undefined,
    frictionRating: 4,
    gitCommitHash: 'e4f5g6h',
    gitAuthor: 'Nick Miethe',
    gitBranch: 'refactor/auth-flow',
    updatedFiles: [
      { filePath: 'src/components/AuthProvider.tsx', commits: ['e4f5g6h'], additions: 200, deletions: 150, agentName: 'Coder', timestamp: '08:16:00' },
      { filePath: 'src/middleware.ts', commits: ['e4f5g6h'], additions: 25, deletions: 40, agentName: 'Coder', timestamp: '08:18:22' },
      { filePath: 'docs/arch/auth-migration.md', commits: ['h8i9j0k'], additions: 50, deletions: 10, agentName: 'Planner', timestamp: '08:05:15' }
    ],
    linkedArtifacts: [
       { id: 'MEM-105', type: 'memory', title: 'Clerk.dev API Keys', source: 'SkillMeat', description: 'Keys retrieved from secure vault skill.' },
    ],
    toolsUsed: [
      { name: 'grep_search', count: 25, successRate: 0.9, category: 'search' },
      { name: 'edit_file', count: 8, successRate: 0.7, category: 'edit' },
    ],
    impactHistory: [
        { timestamp: '00:00', locAdded: 0, locDeleted: 0, fileCount: 150, testPassCount: 450, testFailCount: 0 },
        { timestamp: '05:00', locAdded: 200, locDeleted: 150, fileCount: 152, testPassCount: 400, testFailCount: 50 },
        { timestamp: '10:00', locAdded: 350, locDeleted: 300, fileCount: 155, testPassCount: 420, testFailCount: 30 },
        { timestamp: '13:40', locAdded: 400, locDeleted: 350, fileCount: 155, testPassCount: 450, testFailCount: 5 },
    ],
    logs: [
       { id: 'l21', timestamp: '08:00:01', speaker: 'user', type: 'message', content: 'Begin auth refactor. Move from custom JWT to Clerk. Scan for all "jsonwebtoken" usages.' },
       { id: 'l22', timestamp: '08:00:15', speaker: 'agent', type: 'tool', agentName: 'Planner', content: 'Searching for JWT dependencies', toolCall: { name: 'grep_search', args: 'jsonwebtoken', status: 'success', output: 'src/lib/auth.ts:12:import jwt from "jsonwebtoken";' } },
       { id: 'l23', timestamp: '08:15:22', speaker: 'agent', type: 'message', agentName: 'Coder', content: 'I found 3 locations. Starting migration of the main provider.' },
    ],
  },
  {
    id: 'S-8823',
    taskId: 'T-104',
    status: 'active',
    model: 'claude-3-5-haiku',
    durationSeconds: 120,
    tokensIn: 5000,
    tokensOut: 1200,
    totalCost: 0.45,
    startedAt: '2026-02-03T10:00:00Z',
    toolsUsed: [],
    impactHistory: [
        { timestamp: '00:00', locAdded: 0, locDeleted: 0, fileCount: 155, testPassCount: 450, testFailCount: 0 },
        { timestamp: '01:00', locAdded: 0, locDeleted: 0, fileCount: 155, testPassCount: 450, testFailCount: 0 },
        { timestamp: '02:00', locAdded: 5, locDeleted: 0, fileCount: 155, testPassCount: 450, testFailCount: 0 },
    ],
    logs: [
        { id: 'l31', timestamp: '10:00:01', speaker: 'user', type: 'message', content: 'Check latency on endpoint /api/reports' },
        { id: 'l32', timestamp: '10:00:05', speaker: 'agent', type: 'message', agentName: 'Debugger', content: 'Checking application logs for performance bottlenecks...' }
    ]
  }
];

export const MOCK_DOCUMENTS: PlanDocument[] = [
  {
    id: 'DOC-001',
    title: 'Vector Search PRD',
    filePath: 'docs/prd/vector-search.md',
    status: 'active',
    lastModified: '2026-02-01T10:00:00Z',
    author: 'Nick Miethe',
    frontmatter: {
      tags: ['feature', 'backend', 'ai'],
      linkedFeatures: ['T-101'],
      linkedSessions: ['S-8821'],
      version: '1.2',
      prs: ['PR-405']
    }
  },
  {
    id: 'DOC-001A',
    title: 'Vector Search Master Plan',
    filePath: 'docs/arch/vector-search-plan.md',
    status: 'active',
    lastModified: '2026-02-01T11:00:00Z',
    author: 'Architect',
    frontmatter: {
      tags: ['plan', 'backend'],
      linkedFeatures: ['T-101'],
      version: '1.0'
    }
  },
  {
    id: 'DOC-001B',
    title: 'Phase 1: DB Schema',
    filePath: 'docs/progress/phase-1-schema.md',
    status: 'completed',
    lastModified: '2026-02-02T09:00:00Z',
    author: 'Coder',
    frontmatter: {
      tags: ['progress', 'phase-1'],
      linkedFeatures: ['T-101']
    }
  },
  {
    id: 'DOC-001C',
    title: 'Phase 2: API Endpoints',
    filePath: 'docs/progress/phase-2-api.md',
    status: 'completed',
    lastModified: '2026-02-02T16:00:00Z',
    author: 'Coder',
    frontmatter: {
      tags: ['progress', 'phase-2'],
      linkedFeatures: ['T-101']
    }
  },
  {
    id: 'DOC-002',
    title: 'Auth Migration Arch',
    filePath: 'docs/arch/auth-migration.md',
    status: 'active',
    lastModified: '2026-02-03T08:00:00Z',
    author: 'Nick Miethe',
    frontmatter: {
      tags: ['architecture', 'security'],
      linkedFeatures: ['T-102'],
      relatedFiles: ['docs/arch/legacy-auth.md'],
      version: '0.9',
      commits: ['e4f5g6h']
    }
  },
  {
    id: 'DOC-002B',
    title: 'Phase 1: Cleanup',
    filePath: 'docs/progress/auth-phase-1-cleanup.md',
    status: 'active',
    lastModified: '2026-02-03T11:00:00Z',
    author: 'Coder',
    frontmatter: {
      tags: ['progress', 'phase-1'],
      linkedFeatures: ['T-102']
    }
  },
  {
    id: 'DOC-003',
    title: 'Dashboard Wireframes',
    filePath: 'docs/design/dashboard.md',
    status: 'draft',
    lastModified: '2026-01-25T15:30:00Z',
    author: 'DesignBot',
    frontmatter: {
      tags: ['design', 'ui'],
      linkedFeatures: ['T-103'],
      version: '0.1'
    }
  },
  {
    id: 'DOC-004',
    title: 'Latency Report Q1',
    filePath: 'docs/reports/latency-analysis.md',
    status: 'archived',
    lastModified: '2026-01-15T09:00:00Z',
    author: 'Nick Miethe',
    frontmatter: {
      tags: ['report', 'perf'],
      linkedFeatures: ['T-104'],
      linkedSessions: ['S-8823']
    }
  },
  {
    id: 'DOC-005',
    title: 'API Standards',
    filePath: 'docs/standards/api-guidelines.md',
    status: 'active',
    lastModified: '2025-12-10T11:00:00Z',
    author: 'Principal Eng',
    frontmatter: {
      tags: ['standards', 'api'],
      version: '2.0'
    }
  },
  {
    id: 'DOC-006',
    title: 'Database Schema v2',
    filePath: 'docs/arch/db-v2.md',
    status: 'deprecated',
    lastModified: '2025-11-01T10:00:00Z',
    author: 'Nick Miethe',
    frontmatter: {
      tags: ['database', 'legacy'],
      version: '1.0'
    }
  }
];

export const MOCK_ANALYTICS: AnalyticsMetric[] = [
  { date: '2026-01-28', cost: 12.5, featuresShipped: 1, avgQuality: 4.2 },
  { date: '2026-01-29', cost: 18.2, featuresShipped: 2, avgQuality: 3.8 },
  { date: '2026-01-30', cost: 8.4, featuresShipped: 0, avgQuality: 4.5 },
  { date: '2026-01-31', cost: 22.1, featuresShipped: 3, avgQuality: 4.8 },
  { date: '2026-02-01', cost: 15.6, featuresShipped: 1, avgQuality: 4.0 },
  { date: '2026-02-02', cost: 9.3, featuresShipped: 2, avgQuality: 4.9 },
  { date: '2026-02-03', cost: 11.2, featuresShipped: 1, avgQuality: 4.5 },
];

export const MOCK_ALERTS: AlertConfig[] = [
  {
    id: 'A-1',
    name: 'Expensive Session Detector',
    metric: 'cost_threshold',
    operator: '>',
    threshold: 5.00,
    isActive: true,
    scope: 'session'
  },
  {
    id: 'A-2',
    name: 'Low Quality Warning',
    metric: 'avg_quality',
    operator: '<',
    threshold: 3.5,
    isActive: true,
    scope: 'weekly'
  },
  {
    id: 'A-3',
    name: 'Token Spike Alert',
    metric: 'total_tokens',
    operator: '>',
    threshold: 50000,
    isActive: false,
    scope: 'session'
  }
];

export const MOCK_NOTIFICATIONS: Notification[] = [
  {
    id: 'N-1',
    alertId: 'A-2',
    message: 'Weekly Average Quality dropped below 3.5 on Jan 29th.',
    timestamp: '2026-01-29T09:00:00Z',
    isRead: false
  },
  {
    id: 'N-2',
    alertId: 'A-1',
    message: 'Session S-8820 exceeded $5.00 cost threshold.',
    timestamp: '2026-01-28T16:30:00Z',
    isRead: true
  }
];
