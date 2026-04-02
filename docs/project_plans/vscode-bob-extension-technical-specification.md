---
title: "VSCode/Bob Extension for CCDash Integration - Technical Specification"
type: "architecture"
status: "draft"
created: "2026-04-02"
updated: "2026-04-02"
version: "1.0"
authors: ["Bob (Planning Mode)"]
tags: ["vscode", "extension", "bob", "integration", "architecture"]
---

# VSCode/Bob Extension for CCDash Integration

## Executive Summary

This document provides a comprehensive technical specification for a VSCode extension that integrates CCDash capabilities directly into the IDE. The extension will evolve through three phases: **Pure Visualization** (Phase 1), **Project Detection & Context Awareness** (Phase 2), and **Workflow Execution Integration** (Phase 3). The extension will leverage CCDash's existing REST API, provide intelligent project detection, and enable workflow execution directly from the IDE.

**Target Users**: Developers using Bob (or other AI assistants) who want to visualize agent sessions, track project progress, and execute workflows without leaving their IDE.

**Key Value Propositions**:
- Seamless access to CCDash data within VSCode
- Context-aware navigation between code and agent sessions
- Workflow execution with real-time feedback
- Enhanced AI-assisted development experience

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Phase 1: Pure Visualization](#phase-1-pure-visualization)
3. [Phase 2: Project Detection & Context Awareness](#phase-2-project-detection--context-awareness)
4. [Phase 3: Workflow Execution Integration](#phase-3-workflow-execution-integration)
5. [Technical Implementation Details](#technical-implementation-details)
6. [API Requirements](#api-requirements)
7. [Bob Mode Integration](#bob-mode-integration)
8. [Data Models & Types](#data-models--types)
9. [Security & Performance](#security--performance)
10. [Testing Strategy](#testing-strategy)
11. [Implementation Roadmap](#implementation-roadmap)
12. [Appendices](#appendices)

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      VSCode Extension                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Extension Host (Node.js)                   │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │ │
│  │  │   Commands   │  │  Tree Views  │  │   Webviews   │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘ │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │         State Management Layer                    │ │ │
│  │  │  - Project Context  - Session Cache  - Settings  │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  │  ┌──────────────────────────────────────────────────┐ │ │
│  │  │            API Client Layer                       │ │ │
│  │  │  - REST Client  - WebSocket  - Cache Manager     │ │ │
│  │  └──────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTP/REST + WebSocket
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   CCDash Backend (FastAPI)                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  REST API (Port 8000)                                   │ │
│  │  - /api/sessions      - /api/features                   │ │
│  │  - /api/documents     - /api/execution                  │ │
│  │  - /api/projects      - /api/analytics                  │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Live Updates (WebSocket/SSE)                           │ │
│  │  - Session updates    - Execution events                │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Database (SQLite/PostgreSQL)                           │ │
│  │  - Cached session data  - Documents  - Features         │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Filesystem Watch
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Project Filesystem                        │
│  - Session JSONL logs    - Markdown documents                │
│  - Progress files        - projects.json                     │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. Extension Host (TypeScript/Node.js)
- **Commands**: VSCode command palette integration
- **Tree Views**: Sidebar panels for sessions, documents, tasks
- **Webviews**: Rich UI for session inspection, analytics
- **State Management**: Project context, caching, settings
- **API Client**: Communication with CCDash backend

#### 2. CCDash Backend Integration
- **REST API**: Primary data access method
- **WebSocket/SSE**: Real-time updates for live sessions
- **Database**: Cached data for performance

#### 3. Bob Mode Integration
- **Custom Bob Mode**: Specialized mode for CCDash operations
- **Tool Extensions**: New tools for CCDash interaction
- **Context Injection**: Automatic context from CCDash data

---

## Phase 1: Pure Visualization

### Objective
Display CCDash data (sessions, documents, tasks, features) in VSCode panels without requiring project detection or execution capabilities.

### Features

#### 1.1 Session Explorer Tree View

**Location**: VSCode Activity Bar (sidebar)

**Structure**:
```
CCDash Sessions
├─ 📊 Active Project: SkillMeat
├─ 🔄 Recent Sessions (10)
│  ├─ 📝 Session: Feature Implementation (2h ago)
│  │  ├─ 💬 Messages (45)
│  │  ├─ 🔧 Tools Used (12)
│  │  ├─ 📊 Token Usage: 15.2K
│  │  └─ 💰 Cost: $0.23
│  └─ 🐛 Session: Bug Fix (5h ago)
├─ 📚 Documents (25)
│  ├─ 📄 PRD: User Authentication
│  ├─ 📋 Plan: Database Migration
│  └─ 📊 Report: Performance Analysis
├─ ✨ Features (8)
│  ├─ 🚀 Feature: OAuth Integration (in-progress)
│  └─ ⏸️  Feature: Email Notifications (backlog)
└─ ✅ Tasks (15)
   ├─ 🔴 High: Fix login timeout (in-progress)
   └─ 🟡 Medium: Update docs (todo)
```

**Implementation**:
- [`TreeDataProvider`](https://code.visualstudio.com/api/extension-guides/tree-view) for each entity type
- Lazy loading with pagination
- Refresh on demand or periodic polling
- Icons using VSCode's built-in icon set or custom SVGs

**API Endpoints Used**:
- `GET /api/sessions?offset=0&limit=50`
- `GET /api/documents?offset=0&limit=50`
- `GET /api/features?offset=0&limit=50`
- `GET /api/tasks?offset=0&limit=50`
- `GET /api/projects` (for project switcher)

#### 1.2 Session Inspector Webview

**Trigger**: Click on a session in the tree view

**Features**:
- Full session transcript with syntax highlighting
- Tool usage timeline
- Token metrics and cost breakdown
- Model information and badges
- File changes visualization
- Export session data

**Implementation**:
- [`Webview`](https://code.visualstudio.com/api/extension-guides/webview) with React UI
- Reuse CCDash frontend components where possible
- Message passing between extension and webview
- Lazy loading of transcript entries

**API Endpoints Used**:
- `GET /api/sessions/{sessionId}`
- `GET /api/sessions/{sessionId}/transcript` (if available)

#### 1.3 Document Viewer Webview

**Trigger**: Click on a document in the tree view

**Features**:
- Markdown rendering with frontmatter display
- Linked entities (sessions, features, tasks)
- Document metadata and status
- Edit in VSCode button (opens file)

**Implementation**:
- Webview with markdown renderer
- Click handlers for entity links
- Integration with VSCode's markdown preview

**API Endpoints Used**:
- `GET /api/documents/{documentId}`

#### 1.4 Analytics Dashboard Webview

**Trigger**: Command palette or tree view button

**Features**:
- Token usage trends
- Cost analysis
- Tool usage statistics
- Session duration metrics
- Model comparison

**Implementation**:
- Webview with Chart.js or similar
- Reuse CCDash analytics components
- Date range selector
- Export to CSV

**API Endpoints Used**:
- `GET /api/analytics/sessions`
- `GET /api/analytics/tokens`
- `GET /api/analytics/tools`

#### 1.5 Project Switcher

**Location**: Status bar or tree view header

**Features**:
- Quick switch between CCDash projects
- Display active project name
- Refresh data on project switch

**Implementation**:
- Status bar item with click handler
- Quick pick menu for project selection
- Update all tree views on switch

**API Endpoints Used**:
- `GET /api/projects`
- `GET /api/projects/active`
- `POST /api/projects/switch`

### Phase 1 Deliverables

1. ✅ Extension scaffold with TypeScript
2. ✅ API client with authentication
3. ✅ Session explorer tree view
4. ✅ Session inspector webview
5. ✅ Document viewer webview
6. ✅ Analytics dashboard webview
7. ✅ Project switcher
8. ✅ Basic settings (API URL, polling interval)
9. ✅ Error handling and offline mode


---

## Phase 2: Project Detection & Context Awareness

### Objective
Automatically detect the active CCDash project based on open files and workspace, then provide intelligent navigation between code and CCDash entities.

### Features

#### 2.1 Automatic Project Detection

**Detection Strategy**:

1. **Workspace Root Matching**
   - Check if workspace root matches any project path in `projects.json`
   - Use filesystem path comparison (handle symlinks)

2. **Session Path Matching**
   - Check if workspace contains `.claude/` or other session directories
   - Match session paths from `projects.json`

3. **Git Repository Matching**
   - Extract git remote URL from workspace
   - Match against `repoUrl` in `projects.json`

4. **Heuristic Scoring**
   - Combine multiple signals with confidence scores
   - Select project with highest confidence

**Implementation**:
```typescript
interface ProjectDetectionResult {
  projectId: string;
  confidence: 'high' | 'medium' | 'low';
  matchedBy: 'workspace_path' | 'session_path' | 'git_remote' | 'heuristic';
  project: Project;
}

async function detectProject(
  workspace: vscode.WorkspaceFolder
): Promise<ProjectDetectionResult | null> {
  // 1. Try exact workspace path match
  // 2. Try session path match
  // 3. Try git remote match
  // 4. Try heuristic (file patterns, etc.)
  // 5. Return best match or null
}
```

**User Experience**:
- Automatic detection on workspace open
- Status bar indicator showing detected project
- Manual override option in settings
- Notification if detection is uncertain

#### 2.2 Context-Aware File Navigation

**Features**:

1. **Show Related Sessions for Open File**
   - Detect when user opens a file
   - Query sessions that modified this file
   - Display in tree view or inline

2. **Show Related Documents**
   - Find documents that reference the open file
   - Display in tree view with relevance score

3. **Show Related Features**
   - Find features that include this file in their scope
   - Display with status and progress

**Implementation**:
```typescript
interface FileContext {
  filePath: string;
  relatedSessions: AgentSession[];
  relatedDocuments: PlanDocument[];
  relatedFeatures: Feature[];
  lastModifiedBy: string; // Agent name
  lastModifiedAt: string;
}

async function getFileContext(
  filePath: string,
  projectId: string
): Promise<FileContext> {
  // Query backend for related entities
  // Use file path normalization
  // Return aggregated context
}
```

**API Endpoints Needed**:
- `GET /api/files/context?file_path={path}&project_id={id}`

#### 2.3 Code Lens Integration

**Features**:
- Show inline annotations above functions/classes
- Display last agent that modified the code
- Show related session link
- Click to open session inspector

**Implementation**:
```typescript
class CCDashCodeLensProvider implements vscode.CodeLensProvider {
  async provideCodeLenses(
    document: vscode.TextDocument
  ): Promise<vscode.CodeLens[]> {
    // Get file context
    // Find relevant code ranges
    // Create code lenses with commands
  }
}
```

**Example**:
```typescript
// 👤 Last modified by Claude (Session: abc123) - 2h ago
function authenticateUser(credentials: Credentials) {
  // ...
}
```

#### 2.4 Hover Provider

**Features**:
- Hover over a function/class to see CCDash context
- Display session summary, tool usage, cost
- Quick links to related entities

**Implementation**:
```typescript
class CCDashHoverProvider implements vscode.HoverProvider {
  async provideHover(
    document: vscode.TextDocument,
    position: vscode.Position
  ): Promise<vscode.Hover | null> {
    // Get symbol at position
    // Query file context
    // Build hover markdown
  }
}
```

#### 2.5 Smart Search

**Features**:
- Search across sessions, documents, features
- Filter by current file context
- Fuzzy matching with relevance scoring
- Quick navigation to results

**Implementation**:
- Command palette integration
- Custom quick pick with preview
- Search history

**API Endpoints Needed**:
- `GET /api/search?q={query}&project_id={id}&context_file={path}`

### Phase 2 Deliverables

1. ✅ Project detection algorithm
2. ✅ File context API integration
3. ✅ Context-aware tree view filtering
4. ✅ Code lens provider
5. ✅ Hover provider
6. ✅ Smart search command
7. ✅ Settings for context awareness

---

## Phase 3: Workflow Execution Integration

### Objective
Enable workflow execution directly from VSCode with real-time feedback and potential integration with Bob's tool system.

### Features

#### 3.1 Workflow Execution Panel

**Location**: Webview panel or tree view

**Features**:
- List available workflows/features
- Show execution recommendations
- Display execution status
- Real-time progress updates
- Execution history

**Implementation**:
```typescript
interface WorkflowExecution {
  id: string;
  featureId: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  command: string;
  cwd: string;
  startedAt: string;
  endedAt?: string;
  exitCode?: number;
  output: ExecutionEvent[];
}

interface ExecutionEvent {
  sequenceNo: number;
  stream: 'stdout' | 'stderr' | 'system';
  eventType: 'output' | 'status' | 'error';
  payloadText: string;
  occurredAt: string;
}
```

**API Endpoints Used**:
- `GET /api/features` (with execution context)
- `POST /api/execution/policy-check`
- `POST /api/execution/runs`
- `GET /api/execution/runs/{runId}`
- `GET /api/execution/runs/{runId}/events`

#### 3.2 Execution Recommendations

**Features**:
- Analyze current context (open files, git status)
- Suggest next development steps
- Display recommended commands
- Show risk level and approval requirements

**Implementation**:
```typescript
interface ExecutionRecommendation {
  id: string;
  featureId: string;
  title: string;
  description: string;
  command: string;
  riskLevel: 'low' | 'medium' | 'high';
  requiresApproval: boolean;
  evidence: string[];
  options: ExecutionOption[];
}
```

#### 3.3 Integrated Terminal Execution

**Features**:
- Execute commands in VSCode integrated terminal
- Stream output in real-time
- Capture exit codes and errors
- Link execution to CCDash run records

**Implementation**:
```typescript
async function executeWorkflow(
  recommendation: ExecutionRecommendation
): Promise<WorkflowExecution> {
  // 1. Check policy
  const policy = await checkExecutionPolicy(recommendation);
  
  // 2. Request approval if needed
  if (policy.requiresApproval) {
    const approved = await requestApproval(policy);
    if (!approved) return;
  }
  
  // 3. Create execution run
  const run = await createExecutionRun(recommendation);
  
  // 4. Execute in terminal
  const terminal = vscode.window.createTerminal({
    name: `CCDash: ${recommendation.title}`,
    cwd: recommendation.cwd,
  });
  terminal.show();
  terminal.sendText(recommendation.command);
  
  // 5. Monitor execution
  await monitorExecution(run.id, terminal);
  
  return run;
}
```

#### 3.4 Bob Tool Integration

**Concept**: Extend Bob's tool system to interact with CCDash

**New Bob Tools**:

1. **`ccdash_get_context`**
   - Get current project context
   - Returns related sessions, documents, features
   - Used by Bob to understand project state

2. **`ccdash_execute_workflow`**
   - Trigger workflow execution
   - Monitor progress
   - Return results to Bob

3. **`ccdash_search`**
   - Search CCDash entities
   - Filter by context
   - Return relevant information

**Implementation Approach**:

**Option A: MCP Server** (Model Context Protocol)
- Create CCDash MCP server
- Expose tools via MCP
- Bob connects to MCP server

**Option B: Bob Mode Extension**
- Create custom Bob mode for CCDash
- Add tools directly to mode
- Integrate with extension

**Option C: Hybrid** (Recommended)
- MCP server for core functionality
- Bob mode for UI integration

**Example Bob Tool Definition**:
```typescript
{
  name: "ccdash_get_context",
  description: "Get CCDash context for the current file or project",
  parameters: {
    type: "object",
    properties: {
      filePath: {
        type: "string",
        description: "File path to get context for (optional)"
      },
      includeRelated: {
        type: "boolean",
        description: "Include related sessions and documents"
      }
    }
  }
}
```

### Phase 3 Deliverables

1. ✅ Workflow execution panel
2. ✅ Execution recommendations UI
3. ✅ Integrated terminal execution
4. ✅ Real-time monitoring with WebSocket
5. ✅ Execution history view
6. ✅ Bob tool integration (MCP or mode)
7. ✅ Approval workflow UI
8. ✅ Error handling and retry logic

---

## Technical Implementation Details

### Extension Structure

```
vscode-ccdash-extension/
├── src/
│   ├── extension.ts              # Entry point
│   ├── commands/                 # Command handlers
│   │   ├── sessions.ts
│   │   ├── documents.ts
│   │   ├── features.ts
│   │   └── execution.ts
│   ├── providers/                # VSCode providers
│   │   ├── treeDataProvider.ts
│   │   ├── codeLensProvider.ts
│   │   ├── hoverProvider.ts
│   │   └── completionProvider.ts
│   ├── webviews/                 # Webview implementations
│   │   ├── sessionInspector/
│   │   ├── documentViewer/
│   │   ├── analytics/
│   │   └── execution/
│   ├── api/                      # API client
│   │   ├── client.ts
│   │   ├── types.ts
│   │   ├── websocket.ts
│   │   └── cache.ts
│   ├── state/                    # State management
│   │   ├── projectContext.ts
│   │   ├── sessionCache.ts
│   │   └── settings.ts
│   ├── utils/                    # Utilities
│   │   ├── projectDetection.ts
│   │   ├── fileContext.ts
│   │   └── formatting.ts
│   └── bob/                      # Bob integration
│       ├── mode.ts
│       ├── tools.ts
│       └── mcp-server.ts
├── webview-ui/                   # React UI for webviews
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   └── utils/
│   └── package.json
├── package.json                  # Extension manifest
├── tsconfig.json
└── README.md
```

### State Management

**Approach**: Centralized state with event-driven updates

```typescript
class ExtensionState {
  private _activeProject: Project | null = null;
  private _sessionCache: Map<string, AgentSession> = new Map();
  private _fileContext: Map<string, FileContext> = new Map();
  private _onDidChangeProject = new vscode.EventEmitter<Project>();
  
  get activeProject(): Project | null {
    return this._activeProject;
  }
  
  set activeProject(project: Project | null) {
    this._activeProject = project;
    this._onDidChangeProject.fire(project);
  }
  
  get onDidChangeProject(): vscode.Event<Project> {
    return this._onDidChangeProject.event;
  }
  
  // Cache management
  getSession(id: string): AgentSession | undefined {
    return this._sessionCache.get(id);
  }
  
  setSession(id: string, session: AgentSession): void {
    this._sessionCache.set(id, session);
  }
  
  clearCache(): void {
    this._sessionCache.clear();
    this._fileContext.clear();
  }
}
```

### API Client Implementation

**Features**:
- Automatic retry with exponential backoff
- Request caching with TTL
- Offline mode support
- Error handling and logging

```typescript
class CCDashApiClient {
  private baseUrl: string;
  private cache: Map<string, CacheEntry> = new Map();
  private ws: WebSocket | null = null;
  
  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }
  
  async getSessions(
    filters: SessionFilters,
    options?: RequestOptions
  ): Promise<PaginatedResponse<AgentSession>> {
    const cacheKey = `sessions:${JSON.stringify(filters)}`;
    
    // Check cache
    if (options?.useCache) {
      const cached = this.getFromCache(cacheKey);
      if (cached) return cached;
    }
    
    // Make request
    const response = await this.request<PaginatedResponse<AgentSession>>(
      '/api/sessions',
      { params: filters }
    );
    
    // Update cache
    this.setCache(cacheKey, response, options?.cacheTtl || 60000);
    
    return response;
  }
  
  async request<T>(
    path: string,
    options?: RequestOptions
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const maxRetries = options?.maxRetries || 3;
    let lastError: Error;
    
    for (let i = 0; i < maxRetries; i++) {
      try {
        const response = await fetch(url, {
          method: options?.method || 'GET',
          headers: {
            'Content-Type': 'application/json',
            ...options?.headers,
          },
          body: options?.body ? JSON.stringify(options.body) : undefined,
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return await response.json();
      } catch (error) {
        lastError = error as Error;
        if (i < maxRetries - 1) {
          await this.delay(Math.pow(2, i) * 1000);
        }
      }
    }
    
    throw lastError!;
  }
  
  connectWebSocket(onMessage: (data: any) => void): void {
    this.ws = new WebSocket(`${this.baseUrl.replace('http', 'ws')}/ws`);
    this.ws.onmessage = (event) => onMessage(JSON.parse(event.data));
    this.ws.onerror = (error) => console.error('WebSocket error:', error);
  }
  
  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}
```

---

## API Requirements

### Existing Endpoints (Available)

| Endpoint | Method | Purpose | Phase |
|----------|--------|---------|-------|
| `/api/health` | GET | Backend health check | 1 |
| `/api/sessions` | GET | List sessions with filters | 1 |
| `/api/sessions/{id}` | GET | Get session details | 1 |
| `/api/documents` | GET | List documents | 1 |
| `/api/documents/{id}` | GET | Get document details | 1 |
| `/api/features` | GET | List features | 1 |
| `/api/features/{id}` | GET | Get feature details | 1 |
| `/api/tasks` | GET | List tasks | 1 |
| `/api/projects` | GET | List projects | 1 |
| `/api/projects/active` | GET | Get active project | 1 |
| `/api/projects/switch` | POST | Switch active project | 1 |
| `/api/analytics/*` | GET | Analytics data | 1 |
| `/api/execution/policy-check` | POST | Check execution policy | 3 |
| `/api/execution/runs` | POST | Create execution run | 3 |
| `/api/execution/runs/{id}` | GET | Get run details | 3 |
| `/api/execution/runs/{id}/events` | GET | Get run events | 3 |

### New Endpoints Needed

#### Phase 2: Context Awareness

```typescript
// Get file context
GET /api/files/context
Query params:
  - file_path: string (required)
  - project_id: string (required)
  - include_sessions: boolean (default: true)
  - include_documents: boolean (default: true)
  - include_features: boolean (default: true)
Response: {
  filePath: string;
  relatedSessions: AgentSession[];
  relatedDocuments: PlanDocument[];
  relatedFeatures: Feature[];
  lastModifiedBy: string;
  lastModifiedAt: string;
}

// Search across entities
GET /api/search
Query params:
  - q: string (required)
  - project_id: string (required)
  - entity_types: string[] (optional: sessions, documents, features, tasks)
  - context_file: string (optional: boost results related to this file)
  - limit: number (default: 20)
Response: {
  results: SearchResult[];
  total: number;
}

interface SearchResult {
  entityType: 'session' | 'document' | 'feature' | 'task';
  entityId: string;
  title: string;
  snippet: string;
  relevanceScore: number;
  metadata: Record<string, any>;
}
```

#### Phase 3: Workflow Execution

```typescript
// Get workflow guidance
GET /api/features/{featureId}/workflow-guidance
Response: {
  featureId: string;
  current Step: number;
  totalSteps: number;
  steps: WorkflowStep[];
  blockers: string[];
  nextActions: string[];
}

// WebSocket for real-time execution updates
WS /api/execution/runs/{runId}/stream
Messages: {
  type: 'output' | 'status' | 'error' | 'complete';
  payload: ExecutionEvent;
}
```

### WebSocket/SSE Requirements

**Use Case**: Real-time updates for:
- Active session changes
- Execution progress
- Document updates
- Feature status changes

**Implementation**: WebSocket with SSE fallback

**Protocol**:
```typescript
// Client subscribes to topics
{
  type: 'subscribe',
  topics: ['sessions', 'execution', 'documents']
}

// Server sends updates
{
  type: 'update',
  topic: 'sessions',
  action: 'created' | 'updated' | 'deleted',
  payload: AgentSession
}
```

---

## Bob Mode Integration

### Approach: Custom Bob Mode + MCP Server

**Architecture**:
```
┌─────────────────────────────────────────────────────────────┐
│                      Bob (AI Assistant)                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              CCDash Mode (Custom Mode)                  │ │
│  │  - Context injection from CCDash                        │ │
│  │  - Specialized prompts for workflow execution           │ │
│  │  - Tool use patterns for CCDash operations              │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              MCP Client (Model Context Protocol)        │ │
│  │  - Connects to CCDash MCP Server                        │ │
│  │  - Exposes CCDash tools to Bob                          │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ MCP Protocol
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              CCDash MCP Server (Node.js)                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Tools:                                                 │ │
│  │  - ccdash_get_context                                   │ │
│  │  - ccdash_search                                        │ │
│  │  - ccdash_execute_workflow                              │ │
│  │  - ccdash_get_recommendations                           │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Resources:                                             │ │
│  │  - session://session-id                                 │ │
│  │  - document://document-id                               │ │
│  │  - feature://feature-id                                 │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ REST API
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   CCDash Backend (FastAPI)                   │
└─────────────────────────────────────────────────────────────┘
```

### CCDash Bob Mode Definition

**File**: `.bob/modes/ccdash.md`

```markdown
---
name: CCDash Workflow
slug: ccdash
description: Execute and monitor CCDash workflows with context awareness
---

# CCDash Workflow Mode

You are Bob in CCDash Workflow mode. Your goal is to help the user execute development workflows using CCDash context and recommendations.

## Capabilities

- Access CCDash project context (sessions, documents, features)
- Search across CCDash entities
- Execute recommended workflows
- Monitor execution progress
- Provide guidance on next steps

## Tools Available

- `ccdash_get_context`: Get context for current file or project
- `ccdash_search`: Search CCDash entities
- `ccdash_execute_workflow`: Execute a workflow
- `ccdash_get_recommendations`: Get execution recommendations

## Workflow

1. Understand user's intent
2. Get relevant CCDash context
3. Analyze recommendations
4. Propose workflow execution
5. Monitor and report progress
6. Suggest next steps

## Example Usage

User: "I need to implement the OAuth feature"

1. Use `ccdash_get_context` to find the OAuth feature
2. Use `ccdash_get_recommendations` to get execution steps
3. Present recommendations to user
4. Use `ccdash_execute_workflow` to execute approved steps
5. Monitor progress and report results
```

### Bob Tool Definitions

```typescript
const tools = [
  {
    name: 'ccdash_get_context',
    description: 'Get CCDash context for the current file or project, including related sessions, documents, and features',
    inputSchema: {
      type: 'object',
      properties: {
        filePath: {
          type: 'string',
          description: 'File path to get context for (optional, defaults to current file)',
        },
        includeRelated: {
          type: 'boolean',
          description: 'Include related sessions and documents (default: true)',
        },
      },
    },
  },
  {
    name: 'ccdash_search',
    description: 'Search across CCDash entities (sessions, documents, features, tasks)',
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Search query',
        },
        entityTypes: {
          type: 'array',
          items: { type: 'string' },
          description: 'Entity types to search (sessions, documents, features, tasks)',
        },
        contextFile: {
          type: 'string',
          description: 'File path to boost results related to this file',
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'ccdash_execute_workflow',
    description: 'Execute a CCDash workflow or feature',
    inputSchema: {
      type: 'object',
      properties: {
        featureId: {
          type: 'string',
          description: 'Feature ID to execute',
        },
        command: {
          type: 'string',
          description: 'Command to execute (optional, uses recommendation if not provided)',
        },
        approve: {
          type: 'boolean',
          description: 'Auto-approve execution (default: false)',
        },
      },
      required: ['featureId'],
    },
  },
  {
    name: 'ccdash_get_recommendations',
    description: 'Get execution recommendations for a feature',
    inputSchema: {
      type: 'object',
      properties: {
        featureId: {
          type: 'string',
          description: 'Feature ID to get recommendations for',
        },
      },
      required: ['featureId'],
    },
  },
];
```

---

## Security & Performance

### Security Considerations

1. **API Authentication**
   - Support for API keys or tokens
   - Secure storage in VSCode settings
   - HTTPS-only communication

2. **Command Execution**
   - Policy-based approval system
   - Risk level assessment
   - User confirmation for high-risk operations
   - Sandboxed execution environment

3. **Data Privacy**
   - Local caching with encryption
   - No sensitive data in logs
   - Configurable data retention

4. **Network Security**
   - Certificate validation
   - Request timeout limits
   - Rate limiting

### Performance Optimizations

1. **Caching Strategy**
   - Multi-level caching (memory, disk)
   - TTL-based cache invalidation
   - Selective cache warming

2. **Lazy Loading**
   - Paginated data loading
   - On-demand webview rendering
   - Progressive tree view expansion

3. **WebSocket Optimization**
   - Connection pooling
   - Message batching
   - Automatic reconnection

4. **Memory Management**
   - Weak references for cached data
   - Periodic garbage collection
   - Resource cleanup on extension deactivation

---

## Testing Strategy

### Unit Tests

**Framework**: Jest with TypeScript

**Coverage Areas**:
- API client functionality
- Project detection algorithms
- State management
- Utility functions

**Example**:
```typescript
describe('ProjectDetection', () => {
  it('should detect project by workspace path', async () => {
    const workspace = { uri: vscode.Uri.file('/path/to/project') };
    const result = await detectProject(workspace);
    
    expect(result).toBeDefined();
    expect(result.confidence).toBe('high');
    expect(result.matchedBy).toBe('workspace_path');
  });
});
```

### Integration Tests

**Framework**: VSCode Extension Test Runner

**Coverage Areas**:
- Extension activation/deactivation
- Command execution
- Tree view providers
- Webview communication

### End-to-End Tests

**Framework**: Playwright or similar

**Coverage Areas**:
- Full workflow execution
- UI interactions
- Real backend integration

### Performance Tests

**Tools**: VSCode Performance Profiler

**Metrics**:
- Extension activation time
- Memory usage
- API response times
- UI responsiveness

---

## Implementation Roadmap

### Phase 1: Pure Visualization (8-10 weeks)

**Week 1-2: Foundation**
- [ ] Extension scaffold and build system
- [ ] API client implementation
- [ ] Basic authentication and settings

**Week 3-4: Tree Views**
- [ ] Session explorer tree view
- [ ] Document tree view
- [ ] Feature and task tree views
- [ ] Project switcher

**Week 5-6: Webviews**
- [ ] Session inspector webview
- [ ] Document viewer webview
- [ ] React UI components

**Week 7-8: Analytics & Polish**
- [ ] Analytics dashboard webview
- [ ] Error handling and offline mode
- [ ] Performance optimization
- [ ] Testing and documentation

**Week 9-10: Release Preparation**
- [ ] Beta testing
- [ ] Bug fixes
- [ ] VSCode Marketplace preparation

### Phase 2: Context Awareness (6-8 weeks)

**Week 1-2: Project Detection**
- [ ] Project detection algorithms
- [ ] Workspace integration
- [ ] Settings and configuration

**Week 3-4: File Context**
- [ ] File context API integration
- [ ] Context-aware tree filtering
- [ ] Active file tracking

**Week 5-6: Code Integration**
- [ ] Code lens provider
- [ ] Hover provider
- [ ] Smart search functionality

**Week 7-8: Polish & Testing**
- [ ] Performance optimization
- [ ] User experience refinement
- [ ] Comprehensive testing

### Phase 3: Workflow Execution (10-12 weeks)

**Week 1-2: Execution Framework**
- [ ] Execution API integration
- [ ] Policy checking system
- [ ] Approval workflow UI

**Week 3-4: Terminal Integration**
- [ ] Integrated terminal execution
- [ ] Real-time monitoring
- [ ] WebSocket implementation

**Week 5-6: Bob Integration**
- [ ] MCP server implementation
- [ ] Bob mode definition
- [ ] Tool integration

**Week 7-8: Workflow Guidance**
- [ ] Recommendation system
- [ ] Step-by-step guidance
- [ ] Dependency checking

**Week 9-10: Advanced Features**
- [ ] Execution history
- [ ] Error handling and retry
- [ ] Performance monitoring

**Week 11-12: Release & Documentation**
- [ ] Final testing and bug fixes
- [ ] User documentation
- [ ] Release preparation

### Total Timeline: 24-30 weeks (6-7.5 months)

---

## Success Metrics

### Phase 1 Success Criteria
- [ ] Extension installs and activates without errors
- [ ] All CCDash entities display correctly in tree views
- [ ] Session inspector shows complete session data
- [ ] Analytics dashboard renders charts and metrics
- [ ] Project switching works seamlessly

### Phase 2 Success Criteria
- [ ] Project detection accuracy > 90%
- [ ] File context loads within 2 seconds
- [ ] Code lens annotations appear for modified files
- [ ] Search returns relevant results within 1 second
- [ ] Context-aware filtering improves user workflow

### Phase 3 Success Criteria
- [ ] Workflow execution completes successfully
- [ ] Real-time monitoring shows accurate progress
- [ ] Bob integration provides useful context
- [ ] Approval workflow prevents unauthorized execution
- [ ] User can complete development tasks without leaving VSCode

### Performance Targets
- Extension activation time: < 2 seconds
- API response time: < 1 second (95th percentile)
- Memory usage: < 100MB under normal load
- UI responsiveness: < 100ms for interactions

---

## Appendices

### Appendix A: VSCode Extension API Reference

**Key APIs Used**:
- [`TreeDataProvider`](https://code.visualstudio.com/api/references/vscode-api#TreeDataProvider)
- [`WebviewPanel`](https://code.visualstudio.com/api/references/vscode-api#WebviewPanel)
- [`CodeLensProvider`](https://code.visualstudio.com/api/references/vscode-api#CodeLensProvider)
- [`HoverProvider`](https://code.visualstudio.com/api/references/vscode-api#HoverProvider)
- [`Terminal`](https://code.visualstudio.com/api/references/vscode-api#Terminal)

### Appendix B: CCDash API Schema

**Base URL**: `http://localhost:8000/api`

**Authentication**: None (local development)

**Response Format**: JSON

**Error Handling**: HTTP status codes with error messages

### Appendix C: Bob Mode Integration Guide

**MCP Protocol**: [Model Context Protocol Specification](https://modelcontextprotocol.io/)

**Bob Mode Structure**: Custom mode definition with tools and resources

**Tool Registration**: MCP server exposes tools to Bob client

### Appendix D: Development Environment Setup

**Prerequisites**:
- Node.js 18+
- VSCode 1.80+
- CCDash backend running locally

**Development Commands**:
```bash
# Install dependencies
npm install

# Build extension
npm run build

# Run tests
npm test

# Package extension
npm run package
```

---

## Conclusion

This technical specification provides a comprehensive roadmap for building a VSCode extension that integrates CCDash capabilities directly into the IDE. The three-phase approach ensures incremental value delivery while building toward a fully integrated workflow execution system.

The extension will significantly enhance the developer experience by providing seamless access to CCDash data, intelligent context awareness, and the ability to execute workflows without leaving the IDE. The Bob integration will further enhance AI-assisted development by providing rich context and execution capabilities.

**Next Steps**:
1. Review and approve this specification
2. Set up development environment
3. Begin Phase 1 implementation
4. Establish regular review and feedback cycles
5. Plan beta testing with target users

**Success depends on**:
- Close collaboration with CCDash backend team
- Regular user feedback and iteration
- Robust testing at each phase
- Performance optimization throughout development
- Clear documentation and user onboarding
