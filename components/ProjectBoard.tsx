
import React, { useState, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { MOCK_TASKS, MOCK_SESSIONS, MOCK_DOCUMENTS } from '../constants';
import { ProjectTask, TaskStatus, AgentSession, PlanDocument } from '../types';
import { MoreHorizontal, Tag, User, CircleDollarSign, X, FileText, Calendar, Terminal, GitCommit, GitBranch, ExternalLink, LayoutTemplate, FileJson, FileCode, Clock, Database, ChevronRight, GitPullRequest, LayoutGrid, List, Search, Filter, ArrowUpDown, Bot, PenTool, CheckCircle2, Circle, Workflow, Layers, Box, FileType } from 'lucide-react';
import { Link } from 'react-router-dom';

// --- Mock Content Generator for File Viewer ---
const getMockFileContent = (filename: string): string => {
  if (filename.endsWith('.md')) {
    return `# ${filename.split('/').pop()}\n\n## Overview\nThis document outlines the architectural decisions for the feature.\n\n- **Status**: Draft\n- **Author**: Agent 007\n\n## Implementation Steps\n1. Define schema\n2. Create API endpoints\n3. Update frontend components\n\n> Note: Ensure strictly typed interfaces.`;
  }
  if (filename.endsWith('.json') || filename.endsWith('.prisma')) {
    return `{\n  "name": "${filename}",\n  "version": "1.0.0",\n  "dependencies": {\n    "react": "^18.2.0",\n    "lucide-react": "^0.2.0"\n  }\n}`;
  }
  if (filename.endsWith('.tsx') || filename.endsWith('.ts')) {
    return `import React from 'react';\n\nexport const Component = () => {\n  // TODO: Implement logic for ${filename}\n  return (\n    <div className="p-4">\n      <h1>Hello World</h1>\n    </div>\n  );\n};`;
  }
  return `// Binary or unknown file content for ${filename}`;
};

const FileIcon = ({ filename }: { filename: string }) => {
  if (filename.endsWith('.json')) return <FileJson size={16} />;
  if (filename.endsWith('.tsx') || filename.endsWith('.ts')) return <FileCode size={16} />;
  return <FileText size={16} />;
};

// --- Helper Components for List View ---

const OverflowList = ({ 
  items, 
  icon: Icon, 
  colorClass, 
  emptyText,
  renderItem 
}: { 
  items: string[]; 
  icon: any; 
  colorClass: string; 
  emptyText: string;
  renderItem?: (item: string) => React.ReactNode;
}) => {
  const DISPLAY_LIMIT = 2;
  const overflowCount = items.length - DISPLAY_LIMIT;

  if (items.length === 0) return null;

  return (
    <div className="flex items-center gap-2">
      {items.slice(0, DISPLAY_LIMIT).map((item, idx) => (
        <div key={idx} className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs border ${colorClass}`}>
          <Icon size={12} />
          <span className="truncate max-w-[100px]">{renderItem ? renderItem(item) : item}</span>
        </div>
      ))}
      
      {overflowCount > 0 && (
        <div className="group relative">
           <div className={`cursor-help flex items-center gap-1 px-2 py-1 rounded text-xs border ${colorClass} hover:bg-slate-800 transition-colors`}>
             <span>+{overflowCount} more</span>
           </div>
           {/* Tooltip */}
           <div className="hidden group-hover:block absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 bg-slate-950 border border-slate-800 rounded-lg shadow-xl p-2 z-50 animate-in fade-in zoom-in-95 duration-200">
             <div className="text-[10px] uppercase text-slate-500 font-bold mb-1 px-1">Full List</div>
             <div className="flex flex-col gap-1">
                {items.slice(DISPLAY_LIMIT).map(item => (
                  <div key={item} className="text-xs text-slate-300 px-1 py-0.5 rounded hover:bg-slate-900 truncate">
                    {item}
                  </div>
                ))}
             </div>
           </div>
        </div>
      )}
    </div>
  );
};

// --- Sub-Components ---

const ProjectStructureTree = ({ task, onOpenFile }: { task: ProjectTask; onOpenFile: (path: string) => void }) => {
    // Categorize files
    const { prds, plans, phases, context } = useMemo(() => {
        const result = {
            prds: [] as { path: string; doc?: PlanDocument }[],
            plans: [] as { path: string; doc?: PlanDocument }[],
            phases: [] as { path: string; doc?: PlanDocument }[],
            context: [] as { path: string; doc?: PlanDocument }[]
        };

        (task.relatedFiles || []).forEach(file => {
            const doc = MOCK_DOCUMENTS.find(d => d.filePath === file);
            const lowerPath = file.toLowerCase();

            if (lowerPath.includes('/prd/') || lowerPath.includes('spec')) {
                result.prds.push({ path: file, doc });
            } else if (lowerPath.includes('/arch/') || lowerPath.includes('/plans/') || lowerPath.includes('plan')) {
                result.plans.push({ path: file, doc });
            } else if (lowerPath.includes('/progress/') || lowerPath.includes('phase')) {
                result.phases.push({ path: file, doc });
            } else {
                result.context.push({ path: file, doc });
            }
        });
        return result;
    }, [task.relatedFiles]);

    // Calculate statuses
    const getStatusIcon = (doc?: PlanDocument) => {
        if (!doc) return <Circle size={12} className="text-slate-600" />;
        if (doc.status === 'completed' || doc.status === 'archived') return <CheckCircle2 size={12} className="text-emerald-500" />;
        if (doc.status === 'active') return <div className="w-2.5 h-2.5 rounded-full bg-indigo-500 animate-pulse" />;
        if (doc.status === 'draft') return <div className="w-2.5 h-2.5 rounded-full border border-slate-500" />;
        return <Circle size={12} className="text-slate-600" />;
    };

    const isPhaseComplete = phases.length > 0 && phases.every(p => p.doc?.status === 'completed' || p.doc?.status === 'archived');

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <div className="p-3 bg-slate-950/50 border-b border-slate-800 flex justify-between items-center">
                <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
                    <Layers size={14} /> Project Structure
                </h3>
                <div className="flex gap-2">
                    <span className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${task.projectLevel === 'Full' ? 'bg-purple-500/10 text-purple-400' : 'bg-blue-500/10 text-blue-400'}`}>
                        {task.projectLevel}
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded font-bold uppercase bg-slate-800 text-slate-400">
                        {task.projectType}
                    </span>
                </div>
            </div>

            <div className="p-4 space-y-4">
                {/* 1. Definition Layer */}
                {task.projectLevel === 'Full' && (
                    <div className="relative pl-4 border-l border-slate-800">
                        <div className="absolute -left-[5px] top-0 w-2.5 h-2.5 rounded-full bg-slate-800 border-2 border-slate-700"></div>
                        <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2">Definition</h4>
                        <div className="space-y-1">
                            {prds.map(f => (
                                <div 
                                    key={f.path} 
                                    onClick={() => onOpenFile(f.path)}
                                    className="flex items-center gap-2 text-sm text-slate-300 p-2 hover:bg-slate-800 rounded cursor-pointer group"
                                >
                                    {getStatusIcon(f.doc)}
                                    <FileText size={14} className="text-indigo-400" />
                                    <span className="truncate group-hover:text-white transition-colors">
                                        {f.doc?.title || f.path.split('/').pop()}
                                    </span>
                                </div>
                            ))}
                            {prds.length === 0 && <div className="text-xs text-slate-600 italic pl-2">No PRD linked</div>}
                        </div>
                    </div>
                )}

                {/* 2. Planning Layer */}
                <div className="relative pl-4 border-l border-slate-800">
                    <div className="absolute -left-[5px] top-0 w-2.5 h-2.5 rounded-full bg-slate-800 border-2 border-slate-700"></div>
                    <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2">Architecture & Plan</h4>
                    <div className="space-y-1">
                        {plans.map(f => (
                            <div 
                                key={f.path} 
                                onClick={() => onOpenFile(f.path)}
                                className="flex items-center gap-2 text-sm text-slate-300 p-2 hover:bg-slate-800 rounded cursor-pointer group"
                            >
                                {getStatusIcon(f.doc)}
                                <Workflow size={14} className="text-amber-400" />
                                <span className="truncate group-hover:text-white transition-colors">
                                    {f.doc?.title || f.path.split('/').pop()}
                                </span>
                            </div>
                        ))}
                         {plans.length === 0 && <div className="text-xs text-slate-600 italic pl-2">No Plan linked</div>}
                    </div>
                </div>

                {/* 3. Execution Layer */}
                <div className="relative pl-4 border-l border-slate-800">
                    <div className={`absolute -left-[5px] top-0 w-2.5 h-2.5 rounded-full border-2 ${isPhaseComplete ? 'bg-emerald-500 border-emerald-600' : 'bg-slate-800 border-slate-700'}`}></div>
                    <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2 flex justify-between items-center">
                        Execution Phases
                        {isPhaseComplete && <span className="text-[9px] text-emerald-500 bg-emerald-500/10 px-1.5 rounded font-bold">COMPLETE</span>}
                    </h4>
                    <div className="space-y-1">
                         {phases.map(f => (
                            <div 
                                key={f.path} 
                                onClick={() => onOpenFile(f.path)}
                                className="flex items-center gap-2 text-sm text-slate-300 p-2 hover:bg-slate-800 rounded cursor-pointer group"
                            >
                                {getStatusIcon(f.doc)}
                                <FileType size={14} className="text-emerald-400" />
                                <span className="truncate group-hover:text-white transition-colors">
                                    {f.doc?.title || f.path.split('/').pop()}
                                </span>
                            </div>
                        ))}
                        {phases.length === 0 && <div className="text-xs text-slate-600 italic pl-2">No Phases tracked</div>}
                    </div>
                </div>
            </div>
        </div>
    );
}

const OverviewTab = ({ task, onOpenFile }: { task: ProjectTask; onOpenFile: (path: string) => void }) => (
  <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
    <div className="lg:col-span-2 space-y-8">
      <section>
        <h3 className="text-sm font-semibold text-slate-400 mb-3 uppercase tracking-wider">Description</h3>
        <p className="text-slate-300 leading-relaxed text-sm bg-slate-900/50 p-4 rounded-lg border border-slate-800">
          {task.description}
        </p>
      </section>

      {/* Project Structure Tree Injection */}
      <section>
          <ProjectStructureTree task={task} onOpenFile={onOpenFile} />
      </section>

      <section>
        <h3 className="text-sm font-semibold text-slate-400 mb-3 uppercase tracking-wider">Quick Stats</h3>
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
            <div className="text-slate-500 text-xs mb-1">Total Cost</div>
            <div className="text-emerald-400 font-mono font-bold">${task.cost.toFixed(2)}</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
            <div className="text-slate-500 text-xs mb-1">Priority</div>
            <div className={`font-bold capitalize ${
              task.priority === 'high' ? 'text-rose-400' : 'text-blue-400'
            }`}>{task.priority}</div>
          </div>
          <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
            <div className="text-slate-500 text-xs mb-1">Last Agent</div>
            <div className="text-slate-300 text-sm truncate">{task.lastAgent}</div>
          </div>
        </div>
      </section>
    </div>

    <div className="space-y-6">
      <div className="bg-slate-950/50 rounded-xl border border-slate-800 p-5 space-y-4">
        <h3 className="text-sm font-semibold text-slate-200">Metadata</h3>
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-500 flex items-center gap-2"><User size={14} /> Owner</span>
          <span className="text-sm text-slate-300">{task.owner}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-xs text-slate-500 flex items-center gap-2"><Calendar size={14} /> Updated</span>
          <span className="text-xs text-slate-300 font-mono">{new Date(task.updatedAt).toLocaleDateString()}</span>
        </div>
        <div className="flex justify-between items-center">
             <span className="text-xs text-slate-500 flex items-center gap-2"><Box size={14} /> Type</span>
             <span className="text-xs text-slate-300">{task.projectType}</span>
        </div>
        <div>
          <span className="text-xs text-slate-500 block mb-2">Tags</span>
          <div className="flex flex-wrap gap-2">
            {task.tags.map(tag => (
              <span key={tag} className="text-[10px] bg-slate-800 text-slate-400 px-2 py-1 rounded-full border border-slate-700">
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  </div>
);

const ContextTab = ({ task, initialFile }: { task: ProjectTask; initialFile?: string | null }) => {
  const [selectedFile, setSelectedFile] = useState<string | null>(initialFile || task.relatedFiles?.[0] || null);
  
  // Update internal state if initialFile prop changes (usually from parent navigating)
  React.useEffect(() => {
      if (initialFile) setSelectedFile(initialFile);
  }, [initialFile]);
  
  return (
    <div className="flex h-full gap-4 min-h-[400px]">
      {/* File List */}
      <div className="w-1/3 border-r border-slate-800 pr-4 flex flex-col gap-2">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Artifacts & Context</h3>
        {task.relatedFiles?.map(file => (
          <button
            key={file}
            onClick={() => setSelectedFile(file)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors text-left truncate ${
              selectedFile === file 
                ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' 
                : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200 border border-transparent'
            }`}
          >
            <div className="shrink-0"><FileIcon filename={file} /></div>
            <span className="truncate font-mono text-xs">{file.split('/').pop()}</span>
          </button>
        ))}
        {(!task.relatedFiles || task.relatedFiles.length === 0) && (
           <div className="text-slate-600 text-sm italic p-2">No context files linked.</div>
        )}
      </div>

      {/* File Viewer */}
      <div className="flex-1 flex flex-col bg-slate-950 rounded-lg border border-slate-800 overflow-hidden">
        {selectedFile ? (
          <>
            <div className="bg-slate-900 border-b border-slate-800 px-4 py-2 flex justify-between items-center">
              <span className="font-mono text-xs text-slate-400">{selectedFile}</span>
              <div className="flex gap-1">
                 <div className="w-2 h-2 rounded-full bg-rose-500/20"></div>
                 <div className="w-2 h-2 rounded-full bg-amber-500/20"></div>
                 <div className="w-2 h-2 rounded-full bg-emerald-500/20"></div>
              </div>
            </div>
            <div className="p-4 overflow-y-auto max-h-[400px]">
              <pre className="font-mono text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                {getMockFileContent(selectedFile)}
              </pre>
            </div>
          </>
        ) : (
          <div className="h-full flex items-center justify-center text-slate-600">
            Select a file to preview
          </div>
        )}
      </div>
    </div>
  );
};

const SessionsTab = ({ sessions }: { sessions: AgentSession[] }) => (
  <div className="space-y-4">
    {sessions.length > 0 ? sessions.map(session => (
      <Link to={`/sessions`} key={session.id} className="block group bg-slate-900/50 border border-slate-800 rounded-xl p-4 hover:border-indigo-500/50 transition-all hover:bg-slate-900">
        <div className="flex justify-between items-center mb-3">
          <div className="flex items-center gap-3">
            <div className="bg-indigo-500/10 p-2 rounded text-indigo-400">
              <Terminal size={16} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm text-indigo-400 font-bold">{session.id}</span>
                <span className="text-xs text-slate-500 bg-slate-800 px-1.5 rounded">{session.model}</span>
              </div>
              <div className="text-xs text-slate-500 flex items-center gap-2 mt-0.5">
                {new Date(session.startedAt).toLocaleString()}
              </div>
            </div>
          </div>
          <div className="text-right">
             <div className="text-emerald-400 font-mono font-bold text-sm">${session.totalCost.toFixed(2)}</div>
             <div className="flex gap-1 mt-1 justify-end">
                {[...Array(5)].map((_, i) => (
                    <div key={i} className={`w-1 h-1 rounded-full ${i < (session.qualityRating || 0) ? 'bg-indigo-500' : 'bg-slate-700'}`} />
                ))}
             </div>
          </div>
        </div>
        
        <div className="grid grid-cols-3 gap-4 border-t border-slate-800/50 pt-3">
           <div className="flex items-center gap-2 text-xs text-slate-400">
              <Clock size={12} /> {Math.floor(session.durationSeconds / 60)}m {session.durationSeconds % 60}s
           </div>
           <div className="flex items-center gap-2 text-xs text-slate-400">
              <Database size={12} /> {session.tokensIn + session.tokensOut} tokens
           </div>
           <div className="flex items-center gap-2 text-xs text-slate-400 justify-end group-hover:text-indigo-400 transition-colors">
              View Log <ChevronRight size={12} />
           </div>
        </div>
      </Link>
    )) : (
      <div className="text-center py-12 text-slate-500 border border-dashed border-slate-800 rounded-xl">
        <Terminal size={32} className="mx-auto mb-3 opacity-50" />
        <p>No agent sessions recorded for this task yet.</p>
      </div>
    )}
  </div>
);

const GitTab = ({ sessions }: { sessions: AgentSession[] }) => {
    const commits = sessions.filter(s => s.gitCommitHash);
    
    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between bg-slate-900 border border-slate-800 p-4 rounded-lg">
                <div className="flex items-center gap-3">
                    <div className="bg-purple-500/10 p-2 rounded text-purple-400">
                        <GitBranch size={18} />
                    </div>
                    <div>
                        <div className="text-xs text-slate-500">Active Branch</div>
                        <div className="text-slate-200 font-mono text-sm">{commits[0]?.gitBranch || 'main'}</div>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <div className="bg-blue-500/10 p-2 rounded text-blue-400">
                        <GitPullRequest size={18} />
                    </div>
                    <div>
                        <div className="text-xs text-slate-500">Open PR</div>
                        <div className="text-slate-200 font-mono text-sm">#{Math.floor(Math.random() * 1000)}</div>
                    </div>
                </div>
            </div>

            <div className="relative border-l border-slate-800 ml-3 space-y-6">
                {commits.length > 0 ? commits.map((session, idx) => (
                    <div key={idx} className="relative pl-8">
                        {/* Timeline Dot */}
                        <div className="absolute -left-[5px] top-1.5 w-2.5 h-2.5 rounded-full bg-slate-950 border-2 border-indigo-500"></div>
                        
                        <div className="bg-slate-900/30 border border-slate-800 rounded-lg p-4">
                            <div className="flex justify-between items-start mb-2">
                                <div className="flex items-center gap-2">
                                    <GitCommit size={14} className="text-slate-500" />
                                    <span className="font-mono text-sm text-indigo-400">{session.gitCommitHash}</span>
                                </div>
                                <span className="text-xs text-slate-500">{new Date(session.startedAt).toLocaleDateString()}</span>
                            </div>
                            <p className="text-slate-300 text-sm mb-3">Implemented changes via {session.model}</p>
                            
                            <div className="flex items-center gap-3 text-xs text-slate-500">
                                <span className="flex items-center gap-1"><User size={10} /> {session.gitAuthor}</span>
                                <span className="text-slate-700">|</span>
                                <span className="flex items-center gap-1 text-emerald-500/80">+124</span>
                                <span className="flex items-center gap-1 text-rose-500/80">-45</span>
                            </div>
                        </div>
                    </div>
                )) : (
                    <div className="pl-8 text-slate-500 text-sm">No linked commits found.</div>
                )}
            </div>
        </div>
    );
}

const TaskModal = ({ task, onClose }: { task: ProjectTask; onClose: () => void }) => {
  const linkedSessions = MOCK_SESSIONS.filter(s => s.taskId === task.id);
  const [activeTab, setActiveTab] = useState<'overview' | 'context' | 'sessions' | 'git'>('overview');
  const [contextFile, setContextFile] = useState<string | null>(null);

  const tabs = [
    { id: 'overview', label: 'Overview', icon: LayoutTemplate },
    { id: 'context', label: 'Context & Artifacts', icon: FileText },
    { id: 'sessions', label: 'Agent Sessions', icon: Terminal },
    { id: 'git', label: 'Git History', icon: GitBranch },
  ];

  const handleOpenContextFile = (path: string) => {
      setContextFile(path);
      setActiveTab('context');
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-5xl h-[85vh] flex flex-col shadow-2xl overflow-hidden">
        
        {/* Header */}
        <div className="p-6 border-b border-slate-800 flex justify-between items-start bg-slate-900">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="font-mono text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">{task.id}</span>
              <span className={`text-xs font-bold uppercase px-2 py-0.5 rounded ${
                task.status === 'done' ? 'bg-emerald-500/10 text-emerald-500' :
                task.status === 'in-progress' ? 'bg-indigo-500/10 text-indigo-500' :
                task.status === 'review' ? 'bg-amber-500/10 text-amber-500' :
                'bg-slate-500/10 text-slate-500'
              }`}>
                {task.status.replace('-', ' ')}
              </span>
            </div>
            <h2 className="text-2xl font-bold text-slate-100">{task.title}</h2>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-200 transition-colors p-1 hover:bg-slate-800 rounded">
            <X size={24} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="px-6 border-b border-slate-800 bg-slate-900/50 flex gap-6">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 py-4 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id 
                  ? 'border-indigo-500 text-indigo-400' 
                  : 'border-transparent text-slate-500 hover:text-slate-300 hover:border-slate-700'
              }`}
            >
              <tab.icon size={16} />
              {tab.label}
              {tab.id === 'sessions' && (
                <span className="bg-slate-800 text-slate-400 text-[10px] px-1.5 py-0.5 rounded-full">{linkedSessions.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* Scrollable Content Area */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-950/30">
          {activeTab === 'overview' && <OverviewTab task={task} onOpenFile={handleOpenContextFile} />}
          {activeTab === 'context' && <ContextTab task={task} initialFile={contextFile} />}
          {activeTab === 'sessions' && <SessionsTab sessions={linkedSessions} />}
          {activeTab === 'git' && <GitTab sessions={linkedSessions} />}
        </div>
      </div>
    </div>
  );
};

const StatusColumn = ({ 
  title, 
  tasks, 
  status,
  onMove,
  onTaskClick,
  onDropTask
}: { 
  title: string; 
  tasks: ProjectTask[]; 
  status: TaskStatus;
  onMove: (id: string, status: TaskStatus) => void;
  onTaskClick: (task: ProjectTask) => void;
  onDropTask: (e: React.DragEvent, status: TaskStatus) => void;
}) => {
  
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  return (
    <div 
        className="flex flex-col gap-4 min-w-[300px] w-full lg:w-1/4"
        onDragOver={handleDragOver}
        onDrop={(e) => onDropTask(e, status)}
    >
      <div className="flex items-center justify-between px-2">
        <h3 className="font-semibold text-slate-300 text-sm uppercase tracking-wider flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${
            status === 'done' ? 'bg-emerald-500' : 
            status === 'in-progress' ? 'bg-indigo-500' :
            status === 'review' ? 'bg-amber-500' : 'bg-slate-500'
          }`}></span>
          {title}
        </h3>
        <span className="text-slate-600 text-xs font-mono bg-slate-900 px-2 py-1 rounded">{tasks.length}</span>
      </div>
      
      <div className="flex flex-col gap-3 min-h-[200px] rounded-lg bg-slate-900/30 p-2 border border-slate-800/30 transition-colors hover:bg-slate-900/50 hover:border-slate-800/50">
        {tasks.map((task) => (
          <div 
            key={task.id} 
            draggable
            onDragStart={(e) => {
                e.dataTransfer.setData('taskId', task.id);
                e.dataTransfer.effectAllowed = 'move';
            }}
            onClick={() => onTaskClick(task)}
            className="bg-slate-900 border border-slate-800 p-4 rounded-lg shadow-sm hover:border-indigo-500/50 transition-all group cursor-pointer active:cursor-grabbing hover:shadow-lg hover:-translate-y-0.5"
          >
            <div className="flex justify-between items-start mb-2">
              <span className="text-xs font-mono text-slate-500">{task.id}</span>
              <button className="text-slate-600 hover:text-slate-300">
                <MoreHorizontal size={16} />
              </button>
            </div>
            
            <h4 className="font-medium text-slate-200 mb-2">{task.title}</h4>
            <p className="text-sm text-slate-400 mb-4 line-clamp-2">{task.description}</p>
            
            <div className="flex flex-wrap gap-2 mb-4">
              {task.tags.map(tag => (
                <span key={tag} className="flex items-center gap-1 text-[10px] bg-slate-800 text-slate-400 px-2 py-1 rounded-full border border-slate-700">
                  <Tag size={10} /> {tag}
                </span>
              ))}
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-slate-800">
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <User size={12} />
                <span>{task.owner}</span>
              </div>
              <div className="flex items-center gap-1 text-xs text-emerald-500/80 font-mono">
                <CircleDollarSign size={12} />
                <span>{task.cost.toFixed(2)}</span>
              </div>
            </div>
          </div>
        ))}
        {tasks.length === 0 && (
            <div className="h-full flex items-center justify-center text-slate-700 text-sm border-2 border-dashed border-slate-800 rounded-lg p-4">
                Drop here
            </div>
        )}
      </div>
    </div>
  );
};

const ListViewCard: React.FC<{ task: ProjectTask; onClick: () => void }> = ({ task, onClick }) => {
  // Aggregate data from sessions
  const linkedSessions = MOCK_SESSIONS.filter(s => s.taskId === task.id);
  
  const uniqueAgents = Array.from(new Set(linkedSessions.map(s => s.model)));
  const uniqueTools = Array.from(new Set(linkedSessions.flatMap(s => s.toolsUsed.map(t => t.name))));
  // Mock PR derivation from branches
  const uniquePRs = Array.from(new Set(linkedSessions.map(s => s.gitBranch).filter(Boolean)));

  return (
    <div 
      onClick={onClick}
      className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-indigo-500/50 transition-all cursor-pointer group shadow-sm hover:shadow-md"
    >
      {/* Header Row */}
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="flex items-center gap-3 mb-1">
             <span className="font-mono text-xs text-slate-500 border border-slate-800 px-1.5 py-0.5 rounded">{task.id}</span>
             <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                task.status === 'done' ? 'bg-emerald-500/10 text-emerald-500' :
                task.status === 'in-progress' ? 'bg-indigo-500/10 text-indigo-500' :
                task.status === 'review' ? 'bg-amber-500/10 text-amber-500' :
                'bg-slate-500/10 text-slate-500'
              }`}>
                {task.status}
              </span>
              <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                  {task.projectType}
              </span>
          </div>
          <h3 className="font-bold text-slate-200 text-lg group-hover:text-indigo-400 transition-colors">{task.title}</h3>
        </div>
        <div className="text-right">
           <div className="text-emerald-400 font-mono font-bold text-sm">${task.cost.toFixed(2)}</div>
           <div className="text-[10px] text-slate-500">{new Date(task.updatedAt).toLocaleDateString()}</div>
        </div>
      </div>

      {/* Description */}
      <p className="text-sm text-slate-400 mb-5 line-clamp-2">{task.description}</p>

      {/* Detailed Meta Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
         
         {/* Agents */}
         <div className="space-y-1">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Agents</span>
            <OverflowList 
               items={uniqueAgents.length ? uniqueAgents : ['No agents yet']} 
               icon={Bot} 
               colorClass="border-indigo-500/20 text-indigo-400 bg-indigo-500/5"
               emptyText="No agents"
            />
         </div>

         {/* Tools */}
         <div className="space-y-1">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Tools Used</span>
            <OverflowList 
               items={uniqueTools.length ? uniqueTools : ['No tools used']} 
               icon={PenTool} 
               colorClass="border-amber-500/20 text-amber-400 bg-amber-500/5"
               emptyText="No tools"
            />
         </div>

      </div>

      {/* Footer / Tags & PRs */}
      <div className="pt-3 border-t border-slate-800 flex items-center justify-between">
         <div className="flex gap-2">
            {task.tags.map(tag => (
                <span key={tag} className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full border border-slate-700 flex items-center gap-1">
                   <Tag size={10} /> {tag}
                </span>
            ))}
         </div>
         
         {uniquePRs.length > 0 && (
            <div className="flex items-center gap-1 text-xs text-slate-400">
               <GitPullRequest size={12} />
               <span>{uniquePRs.length} PR{uniquePRs.length !== 1 ? 's' : ''}</span>
            </div>
         )}
      </div>
    </div>
  );
};

export const ProjectBoard: React.FC = () => {
  const [viewMode, setViewMode] = useState<'board' | 'list'>('board');
  const [tasks, setTasks] = useState<ProjectTask[]>(MOCK_TASKS);
  const [selectedTask, setSelectedTask] = useState<ProjectTask | null>(null);

  // Filter States
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all');
  const [sortBy, setSortBy] = useState<'date' | 'cost'>('date');

  // Filter Logic
  const filteredTasks = useMemo(() => {
    let result = tasks;

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(t => 
        t.title.toLowerCase().includes(q) || 
        t.description.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q)
      );
    }

    if (statusFilter !== 'all') {
      result = result.filter(t => t.status === statusFilter);
    }

    return result.sort((a, b) => {
      if (sortBy === 'cost') return b.cost - a.cost;
      return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
    });
  }, [tasks, searchQuery, statusFilter, sortBy]);

  const moveTask = (id: string, newStatus: TaskStatus) => {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, status: newStatus } : t));
  };

  const handleDropTask = (e: React.DragEvent, status: TaskStatus) => {
    const taskId = e.dataTransfer.getData('taskId');
    if (taskId) {
        moveTask(taskId, status);
    }
  };

  // Portal Element for Sidebar Filters
  const sidebarPortal = document.getElementById('sidebar-portal');

  return (
    <div className="h-full flex flex-col relative">
      
      {/* Sidebar Filter Injection */}
      {sidebarPortal && createPortal(
        <div className="space-y-6 animate-in slide-in-from-left-4 duration-300">
          <div>
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
              <Filter size={12} /> Filters
            </h3>
            <div className="space-y-3">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input 
                  type="text" 
                  placeholder="Search tasks..." 
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none transition-colors"
                />
              </div>
              
              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">Status</label>
                <select 
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as any)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="all">All Statuses</option>
                  <option value="todo">To Do</option>
                  <option value="in-progress">In Progress</option>
                  <option value="review">Review</option>
                  <option value="done">Done</option>
                </select>
              </div>
            </div>
          </div>

          <div>
             <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
              <ArrowUpDown size={12} /> Sort
            </h3>
            <div className="flex gap-2">
               <button 
                  onClick={() => setSortBy('date')}
                  className={`flex-1 py-1.5 px-2 text-xs rounded border transition-colors ${sortBy === 'date' ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400' : 'bg-slate-900 border-slate-800 text-slate-400'}`}
               >
                 Recent
               </button>
               <button 
                  onClick={() => setSortBy('cost')}
                  className={`flex-1 py-1.5 px-2 text-xs rounded border transition-colors ${sortBy === 'cost' ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400' : 'bg-slate-900 border-slate-800 text-slate-400'}`}
               >
                 Cost
               </button>
            </div>
          </div>
        </div>,
        sidebarPortal
      )}

      {/* Page Header */}
      <div className="mb-6 flex justify-between items-center">
        <div>
           <h2 className="text-2xl font-bold text-slate-100">Feature Board</h2>
           <p className="text-slate-400 text-sm">Synchronized with local Markdown frontmatter.</p>
        </div>
        <div className="flex gap-3">
            {/* View Switcher */}
            <div className="bg-slate-900 border border-slate-800 p-1 rounded-lg flex gap-1">
              <button 
                onClick={() => setViewMode('board')}
                className={`p-1.5 rounded-md transition-all ${viewMode === 'board' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
                title="Kanban View"
              >
                <LayoutGrid size={18} />
              </button>
              <button 
                onClick={() => setViewMode('list')}
                className={`p-1.5 rounded-md transition-all ${viewMode === 'list' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
                title="List View"
              >
                <List size={18} />
              </button>
            </div>

            <button className="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors">
                New Feature
            </button>
        </div>
      </div>
      
      {/* Content Area */}
      <div className="flex-1 overflow-x-auto">
        {viewMode === 'board' ? (
          <div className="flex gap-6 min-w-[1200px] h-full pb-4">
            <StatusColumn 
              title="To Do" 
              status="todo"
              tasks={filteredTasks.filter(t => t.status === 'todo')} 
              onMove={moveTask}
              onTaskClick={setSelectedTask}
              onDropTask={handleDropTask}
            />
            <StatusColumn 
              title="In Progress" 
              status="in-progress"
              tasks={filteredTasks.filter(t => t.status === 'in-progress')} 
              onMove={moveTask}
              onTaskClick={setSelectedTask}
              onDropTask={handleDropTask}
            />
            <StatusColumn 
              title="Review" 
              status="review"
              tasks={filteredTasks.filter(t => t.status === 'review')} 
              onMove={moveTask}
              onTaskClick={setSelectedTask}
              onDropTask={handleDropTask}
            />
            <StatusColumn 
              title="Done" 
              status="done"
              tasks={filteredTasks.filter(t => t.status === 'done')} 
              onMove={moveTask}
              onTaskClick={setSelectedTask}
              onDropTask={handleDropTask}
            />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 gap-6 pb-6">
            {filteredTasks.map(task => (
              <ListViewCard 
                key={task.id} 
                task={task} 
                onClick={() => setSelectedTask(task)} 
              />
            ))}
            {filteredTasks.length === 0 && (
               <div className="col-span-full py-12 text-center text-slate-500 border border-dashed border-slate-800 rounded-xl">
                  No tasks match your filters.
               </div>
            )}
          </div>
        )}
      </div>

      {selectedTask && (
        <TaskModal 
            task={selectedTask} 
            onClose={() => setSelectedTask(null)} 
        />
      )}
    </div>
  );
};
