
import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useData } from '../contexts/DataContext';
import { Feature, FeaturePhase, LinkedDocument, ProjectTask, AgentSession } from '../types';
import {
  X, FileText, Calendar, ChevronRight, ChevronDown, LayoutGrid, List,
  Search, Filter, ArrowUpDown, CheckCircle2, Circle, Layers, Box,
  FolderOpen, ExternalLink, Tag, ClipboardList, BarChart3, RefreshCw,
  Terminal, GitCommit,
} from 'lucide-react';

// ── Status helpers ─────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  'done': { label: 'Done', color: 'bg-emerald-500/10 text-emerald-500', dot: 'bg-emerald-500' },
  'in-progress': { label: 'In Progress', color: 'bg-indigo-500/10 text-indigo-500', dot: 'bg-indigo-500' },
  'review': { label: 'Review', color: 'bg-amber-500/10 text-amber-500', dot: 'bg-amber-500' },
  'backlog': { label: 'Backlog', color: 'bg-slate-500/10 text-slate-500', dot: 'bg-slate-500' },
};

const STATUS_OPTIONS = ['backlog', 'in-progress', 'review', 'done'] as const;

const getStatusStyle = (status: string) => STATUS_CONFIG[status] || STATUS_CONFIG['backlog'];

const ProgressBar = ({ completed, total }: { completed: number; total: number }) => {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${pct === 100 ? 'bg-emerald-500' : pct > 0 ? 'bg-indigo-500' : 'bg-slate-700'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] text-slate-500 font-mono min-w-[40px] text-right">
        {completed}/{total}
      </span>
    </div>
  );
};

const DocTypeIcon = ({ docType }: { docType: string }) => {
  switch (docType) {
    case 'prd': return <ClipboardList size={12} className="text-purple-400" />;
    case 'implementation_plan': return <Layers size={12} className="text-blue-400" />;
    case 'phase_plan': return <FileText size={12} className="text-amber-400" />;
    case 'report': return <BarChart3 size={12} className="text-emerald-400" />;
    default: return <FileText size={12} className="text-slate-400" />;
  }
};

const DocTypeBadge = ({ docType }: { docType: string }) => {
  const labels: Record<string, string> = {
    prd: 'PRD',
    implementation_plan: 'Plan',
    phase_plan: 'Phase',
    report: 'Report',
    spec: 'Spec',
  };
  return <span className="text-[9px] uppercase font-bold">{labels[docType] || docType}</span>;
};

// ── Status Dropdown ────────────────────────────────────────────────

const StatusDropdown = ({
  status,
  onStatusChange,
  size = 'sm',
}: {
  status: string;
  onStatusChange: (newStatus: string) => void;
  size?: 'sm' | 'xs';
}) => {
  const style = getStatusStyle(status);
  const sizeClasses = size === 'xs' ? 'text-[10px] px-1.5 py-0.5' : 'text-xs px-2 py-1';

  return (
    <select
      value={status}
      onChange={(e) => {
        e.stopPropagation();
        onStatusChange(e.target.value);
      }}
      onClick={(e) => e.stopPropagation()}
      className={`font-bold uppercase rounded cursor-pointer border-0 appearance-none ${sizeClasses} ${style.color} bg-transparent hover:ring-1 hover:ring-slate-600 focus:ring-1 focus:ring-indigo-500 focus:outline-none transition-all`}
      style={{ WebkitAppearance: 'none' }}
    >
      {STATUS_OPTIONS.map(s => (
        <option key={s} value={s} className="bg-slate-900 text-slate-300">
          {getStatusStyle(s).label}
        </option>
      ))}
    </select>
  );
};

// ── Task Source Dialog ─────────────────────────────────────────────

const TaskSourceDialog = ({ task, onClose }: { task: ProjectTask; onClose: () => void }) => {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!task.sourceFile) {
      setError('No source file linked to this task.');
      setLoading(false);
      return;
    }
    fetch(`/api/features/task-source?file=${encodeURIComponent(task.sourceFile)}`)
      .then(r => {
        if (!r.ok) throw new Error(`Failed to load (${r.status})`);
        return r.json();
      })
      .then(data => { setContent(data.content); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [task.sourceFile]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-3xl h-[70vh] flex flex-col shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-950">
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2 truncate">
              <FileText size={16} className="text-indigo-400 flex-shrink-0" />
              {task.title}
            </h3>
            <div className="flex items-center gap-3 mt-1">
              <span className="font-mono text-[10px] text-slate-500">{task.id}</span>
              {task.sourceFile && (
                <span className="text-[10px] text-slate-600 font-mono truncate flex items-center gap-1">
                  <FolderOpen size={10} />
                  {task.sourceFile}
                </span>
              )}
            </div>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors p-1">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 bg-slate-950/30">
          {loading && (
            <div className="flex items-center justify-center h-full text-slate-500">
              <RefreshCw size={20} className="animate-spin mr-2" /> Loading source file…
            </div>
          )}
          {error && (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
              <FileText size={32} className="mb-3 opacity-30" />
              <p className="text-sm">{error}</p>
            </div>
          )}
          {content && (
            <pre className="text-sm text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">{content}</pre>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Feature Detail Modal ───────────────────────────────────────────

const FeatureModal = ({
  feature,
  onClose,
  onFeatureUpdated,
}: {
  feature: Feature;
  onClose: () => void;
  onFeatureUpdated?: (updated: Feature) => void;
}) => {
  const navigate = useNavigate();
  const { updateFeatureStatus, updatePhaseStatus, updateTaskStatus, sessions } = useData();
  const [activeTab, setActiveTab] = useState<'overview' | 'phases' | 'docs' | 'sessions'>('overview');
  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set());
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [viewingTask, setViewingTask] = useState<ProjectTask | null>(null);

  const togglePhase = (phaseKey: string) => {
    setExpandedPhases(prev => {
      const next = new Set(prev);
      if (next.has(phaseKey)) next.delete(phaseKey);
      else next.add(phaseKey);
      return next;
    });
  };

  const statusStyle = getStatusStyle(feature.status);
  const pct = feature.totalTasks > 0 ? Math.round((feature.completedTasks / feature.totalTasks) * 100) : 0;

  // Fetch full detail (with tasks) on open
  const [fullFeature, setFullFeature] = useState<Feature | null>(null);
  useEffect(() => {
    fetch(`/api/features/${feature.id}`)
      .then(r => r.json())
      .then(setFullFeature)
      .catch(() => setFullFeature(null));
  }, [feature.id]);

  const phases = fullFeature?.phases || feature.phases;
  const linkedDocs = fullFeature?.linkedDocs || feature.linkedDocs;

  const handleFeatureStatusChange = async (newStatus: string) => {
    setUpdatingStatus(true);
    try {
      await updateFeatureStatus(feature.id, newStatus);
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handlePhaseStatusChange = async (phaseId: string, newStatus: string) => {
    setUpdatingStatus(true);
    try {
      await updatePhaseStatus(feature.id, phaseId, newStatus);
      // Refresh the detail
      const res = await fetch(`/api/features/${feature.id}`);
      setFullFeature(await res.json());
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleTaskStatusChange = async (phaseId: string, taskId: string, newStatus: string) => {
    setUpdatingStatus(true);
    try {
      await updateTaskStatus(feature.id, phaseId, taskId, newStatus);
      const res = await fetch(`/api/features/${feature.id}`);
      setFullFeature(await res.json());
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleDocClick = (doc: LinkedDocument) => {
    // Navigate to Documents tab and pre-select this doc
    const docId = `DOC-${doc.filePath.replace(/\//g, '-').replace('.md', '')}`;
    onClose();
    navigate(`/plans?doc=${encodeURIComponent(docId)}`);
  };

  // Compute linked sessions from task sessionIds
  const linkedSessionIds = useMemo(() => {
    const ids = new Set<string>();
    phases.forEach(p => p.tasks.forEach(t => { if (t.sessionId) ids.add(t.sessionId); }));
    return ids;
  }, [phases]);

  const linkedSessions = useMemo(() =>
    sessions.filter(s => linkedSessionIds.has(s.id)),
    [sessions, linkedSessionIds]
  );

  const tabs = [
    { id: 'overview', label: 'Overview', icon: Box },
    { id: 'phases', label: `Phases (${phases.length})`, icon: Layers },
    { id: 'docs', label: `Documents (${linkedDocs.length})`, icon: FileText },
    { id: 'sessions', label: `Sessions (${linkedSessions.length})`, icon: Terminal },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-4xl h-[80vh] flex flex-col shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="p-6 border-b border-slate-800 bg-slate-900">
          <div className="flex justify-between items-start">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-2">
                <span className="font-mono text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded border border-slate-700 truncate max-w-[200px]">{feature.id}</span>
                <StatusDropdown status={feature.status} onStatusChange={handleFeatureStatusChange} />
                {updatingStatus && <RefreshCw size={14} className="text-indigo-400 animate-spin" />}
                {feature.category && (
                  <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                    {feature.category}
                  </span>
                )}
              </div>
              <h2 className="text-xl font-bold text-slate-100 truncate">{feature.name}</h2>
              <div className="mt-2 flex items-center gap-4 text-xs text-slate-500">
                <span>{pct}% complete</span>
                <span>{feature.completedTasks}/{feature.totalTasks} tasks</span>
                {feature.updatedAt && feature.updatedAt !== 'None' && (
                  <span className="flex items-center gap-1">
                    <Calendar size={12} />
                    {feature.updatedAt}
                  </span>
                )}
              </div>
            </div>
            <button onClick={onClose} className="text-slate-500 hover:text-slate-200 transition-colors p-1 hover:bg-slate-800 rounded ml-4">
              <X size={24} />
            </button>
          </div>
          <div className="mt-3">
            <ProgressBar completed={feature.completedTasks} total={feature.totalTasks} />
          </div>
        </div>

        {/* Tab Nav */}
        <div className="px-6 border-b border-slate-800 bg-slate-900/50 flex gap-6">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === tab.id
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-500 hover:text-slate-300 hover:border-slate-700'
                }`}
            >
              <tab.icon size={16} />
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-950/30">

          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Stats Grid */}
              <div className="grid grid-cols-4 gap-4">
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                  <div className="text-slate-500 text-xs mb-1">Total Tasks</div>
                  <div className="text-slate-100 font-bold text-2xl">{feature.totalTasks}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                  <div className="text-slate-500 text-xs mb-1">Completed</div>
                  <div className="text-emerald-400 font-bold text-2xl">{feature.completedTasks}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                  <div className="text-slate-500 text-xs mb-1">Phases</div>
                  <div className="text-indigo-400 font-bold text-2xl">{phases.length}</div>
                </div>
                <div className="bg-slate-900 border border-slate-800 p-4 rounded-lg">
                  <div className="text-slate-500 text-xs mb-1">Documents</div>
                  <div className="text-purple-400 font-bold text-2xl">{linkedDocs.length}</div>
                </div>
              </div>

              {/* Linked Documents — clickable */}
              {linkedDocs.length > 0 && (
                <div>
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-3">Linked Documents</h3>
                  <div className="space-y-2">
                    {linkedDocs.map(doc => (
                      <button
                        key={doc.id}
                        onClick={() => handleDocClick(doc)}
                        className="w-full flex items-center gap-3 bg-slate-900 border border-slate-800 rounded-lg p-3 hover:border-indigo-500/50 hover:bg-slate-800/50 transition-all text-left group"
                      >
                        <DocTypeIcon docType={doc.docType} />
                        <span className="text-sm text-slate-300 flex-1 truncate group-hover:text-indigo-400 transition-colors">{doc.title}</span>
                        <DocTypeBadge docType={doc.docType} />
                        <ExternalLink size={12} className="text-slate-600 group-hover:text-indigo-400 transition-colors" />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Related Features */}
              {feature.relatedFeatures.length > 0 && (
                <div>
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-3">Related Features</h3>
                  <div className="flex flex-wrap gap-2">
                    {feature.relatedFeatures.map(rel => (
                      <span key={rel} className="text-xs bg-slate-800 text-indigo-400 px-2 py-1 rounded border border-slate-700">
                        {rel}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Tags */}
              {feature.tags.length > 0 && (
                <div>
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-3">Tags</h3>
                  <div className="flex flex-wrap gap-2">
                    {feature.tags.map(tag => (
                      <span key={tag} className="text-[10px] bg-slate-800 text-slate-400 px-2 py-1 rounded-full border border-slate-700 flex items-center gap-1">
                        <Tag size={10} />{tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Phases Tab */}
          {activeTab === 'phases' && (
            <div className="space-y-3">
              {phases.length === 0 && (
                <div className="text-center py-12 text-slate-500 border border-dashed border-slate-800 rounded-xl">
                  <Layers size={32} className="mx-auto mb-3 opacity-50" />
                  <p>No phases tracked for this feature.</p>
                </div>
              )}
              {phases.map(phase => {
                const phaseStatus = getStatusStyle(phase.status);
                const phaseKey = phase.id || phase.phase;
                const isExpanded = expandedPhases.has(phaseKey);
                return (
                  <div key={phaseKey} className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
                    <div className="flex items-center gap-3 p-4 hover:bg-slate-800/50 transition-colors">
                      <button
                        onClick={() => togglePhase(phaseKey)}
                        className="flex items-center gap-3 flex-1 min-w-0 text-left"
                      >
                        {isExpanded ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
                        <div className={`w-2 h-2 rounded-full ${phaseStatus.dot}`} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-slate-200">Phase {phase.phase}</span>
                            {phase.title && (
                              <span className="text-sm text-slate-400 truncate">— {phase.title}</span>
                            )}
                          </div>
                          <div className="mt-1">
                            <ProgressBar completed={phase.completedTasks} total={phase.totalTasks} />
                          </div>
                        </div>
                      </button>
                      <StatusDropdown
                        status={phase.status}
                        onStatusChange={(s) => handlePhaseStatusChange(phase.phase, s)}
                        size="xs"
                      />
                    </div>

                    {/* Expanded task list */}
                    {isExpanded && phase.tasks.length > 0 && (
                      <div className="border-t border-slate-800 px-4 py-3 space-y-1.5 bg-slate-950/30">
                        {phase.tasks.map(task => {
                          const taskDone = task.status === 'done';
                          const nextStatus = taskDone ? 'backlog' : 'done';
                          return (
                            <div key={task.id} className="flex items-center gap-3 py-1.5 px-2 rounded hover:bg-slate-900 transition-colors">
                              <button
                                onClick={() => handleTaskStatusChange(phase.phase, task.id, nextStatus)}
                                className="flex-shrink-0 hover:scale-110 transition-transform"
                                title={taskDone ? 'Mark incomplete' : 'Mark done'}
                              >
                                {taskDone ? (
                                  <CheckCircle2 size={14} className="text-emerald-500" />
                                ) : (
                                  <Circle size={14} className="text-slate-600 hover:text-indigo-400" />
                                )}
                              </button>
                              <button
                                onClick={() => setViewingTask(task)}
                                className="font-mono text-[10px] text-slate-500 w-16 flex-shrink-0 hover:text-indigo-400 transition-colors cursor-pointer text-left"
                                title="View source file"
                              >
                                {task.id}
                              </button>
                              <button
                                onClick={() => setViewingTask(task)}
                                className={`text-sm flex-1 truncate text-left hover:text-indigo-400 transition-colors ${taskDone ? 'text-slate-500 line-through' : 'text-slate-300'}`}
                                title="View source file"
                              >
                                {task.title}
                              </button>
                              {task.commitHash && (
                                <span className="flex items-center gap-1 text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700 font-mono flex-shrink-0" title={`Commit: ${task.commitHash}`}>
                                  <GitCommit size={10} />
                                  {task.commitHash.slice(0, 7)}
                                </span>
                              )}
                              {task.sessionId && (
                                <button
                                  onClick={(e) => { e.stopPropagation(); onClose(); navigate(`/sessions?session=${encodeURIComponent(task.sessionId!)}`); }}
                                  className="flex items-center gap-1 text-[10px] bg-indigo-500/10 text-indigo-400 px-1.5 py-0.5 rounded border border-indigo-500/30 font-mono hover:bg-indigo-500/20 transition-colors flex-shrink-0"
                                  title="Go to session"
                                >
                                  <Terminal size={10} />
                                  {task.sessionId}
                                </button>
                              )}
                              {task.owner && (
                                <span className="text-[10px] text-slate-600 truncate max-w-[100px] flex-shrink-0">{task.owner}</span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {isExpanded && phase.tasks.length === 0 && (
                      <div className="border-t border-slate-800 px-4 py-3 text-xs text-slate-600 italic">
                        No task details available for this phase.
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Documents Tab — clickable */}
          {activeTab === 'docs' && (
            <div className="space-y-3">
              {linkedDocs.length === 0 && (
                <div className="text-center py-12 text-slate-500 border border-dashed border-slate-800 rounded-xl">
                  <FileText size={32} className="mx-auto mb-3 opacity-50" />
                  <p>No documents linked to this feature.</p>
                </div>
              )}
              {linkedDocs.map(doc => (
                <button
                  key={doc.id}
                  onClick={() => handleDocClick(doc)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg p-4 hover:border-indigo-500/50 hover:bg-slate-800/50 transition-all text-left group"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <DocTypeIcon docType={doc.docType} />
                      <span className="text-sm font-medium text-slate-200 group-hover:text-indigo-400 transition-colors">{doc.title}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${doc.docType === 'prd' ? 'bg-purple-500/10 text-purple-400' : 'bg-blue-500/10 text-blue-400'}`}>
                        <DocTypeBadge docType={doc.docType} />
                      </span>
                      <ExternalLink size={12} className="text-slate-600 group-hover:text-indigo-400 transition-colors" />
                    </div>
                  </div>
                  <div className="text-xs text-slate-500 font-mono truncate flex items-center gap-1.5">
                    <FolderOpen size={12} />
                    {doc.filePath}
                  </div>
                </button>
              ))}
            </div>
          )}
          {/* Sessions Tab */}
          {activeTab === 'sessions' && (
            <div className="space-y-3">
              {linkedSessions.length === 0 && (
                <div className="text-center py-12 text-slate-500 border border-dashed border-slate-800 rounded-xl">
                  <Terminal size={32} className="mx-auto mb-3 opacity-50" />
                  <p>No sessions linked to this feature.</p>
                  <p className="text-xs mt-1 text-slate-600">Sessions are linked when tasks have session IDs in their progress files.</p>
                </div>
              )}
              {linkedSessions.map(session => {
                // Find which phases/tasks link to this session
                const relatedTasks = phases.flatMap(p =>
                  p.tasks.filter(t => t.sessionId === session.id).map(t => ({ phase: p, task: t }))
                );

                return (
                  <div key={session.id} className="bg-slate-900 border border-slate-800 rounded-lg p-4 hover:border-slate-700 transition-colors">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg ${session.status === 'active' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-slate-800 text-slate-400'}`}>
                          <Terminal size={16} />
                        </div>
                        <div>
                          <button
                            onClick={() => { onClose(); navigate(`/sessions?session=${encodeURIComponent(session.id)}`); }}
                            className="font-mono text-sm font-bold text-slate-200 hover:text-indigo-400 transition-colors"
                          >
                            {session.id}
                          </button>
                          <div className="flex items-center gap-3 mt-0.5">
                            <span className="text-[10px] text-slate-500 flex items-center gap-1">
                              <Calendar size={10} />
                              {new Date(session.startedAt).toLocaleDateString()}
                            </span>
                            <span className="text-[10px] text-slate-500 font-mono">{session.model}</span>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-right">
                        <div>
                          <div className="text-[9px] text-slate-600 uppercase">Cost</div>
                          <div className="text-xs font-mono text-emerald-400">${session.totalCost.toFixed(2)}</div>
                        </div>
                        <div>
                          <div className="text-[9px] text-slate-600 uppercase">Duration</div>
                          <div className="text-xs font-mono text-slate-400">{Math.round(session.durationSeconds / 60)}m</div>
                        </div>
                        {session.gitCommitHash && (
                          <span className="flex items-center gap-1 text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700 font-mono">
                            <GitCommit size={10} />
                            {session.gitCommitHash.slice(0, 7)}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Related tasks */}
                    {relatedTasks.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-slate-800/60">
                        <div className="text-[10px] text-slate-600 uppercase font-bold mb-2">Linked Tasks</div>
                        <div className="space-y-1">
                          {relatedTasks.map(({ phase, task }) => (
                            <div key={task.id} className="flex items-center gap-2 text-xs">
                              <span className="text-slate-600">Phase {phase.phase}</span>
                              <span className="text-slate-700">→</span>
                              <span className="font-mono text-slate-500">{task.id}</span>
                              <span className="text-slate-400 truncate">{task.title}</span>
                              <span className={`text-[9px] uppercase font-bold ml-auto ${getStatusStyle(task.status).color}`}>
                                {getStatusStyle(task.status).label}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Task Source Dialog */}
        {viewingTask && <TaskSourceDialog task={viewingTask} onClose={() => setViewingTask(null)} />}
      </div>
    </div>
  );
};

// ── Feature Card ───────────────────────────────────────────────────

const FeatureCard = ({
  feature,
  onClick,
  onStatusChange,
}: {
  feature: Feature;
  onClick: () => void;
  onStatusChange: (newStatus: string) => void;
}) => {
  const statusStyle = getStatusStyle(feature.status);
  const prdDoc = feature.linkedDocs.find(d => d.docType === 'prd');
  const planDoc = feature.linkedDocs.find(d => d.docType === 'implementation_plan');

  return (
    <div
      onClick={onClick}
      className="bg-slate-900 border border-slate-800 p-4 rounded-lg shadow-sm hover:border-indigo-500/50 transition-all group cursor-pointer hover:shadow-lg hover:-translate-y-0.5"
    >
      {/* Header */}
      <div className="flex justify-between items-start mb-2">
        <span className="font-mono text-[10px] text-slate-500 truncate max-w-[180px]">{feature.id}</span>
        <StatusDropdown status={feature.status} onStatusChange={onStatusChange} size="xs" />
      </div>

      <h4 className="font-medium text-slate-200 mb-2 line-clamp-2 group-hover:text-indigo-400 transition-colors text-sm">{feature.name}</h4>

      {/* Progress */}
      <div className="mb-3">
        <ProgressBar completed={feature.completedTasks} total={feature.totalTasks} />
      </div>

      {/* Linked Doc chips */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {prdDoc && (
          <span className="text-[9px] flex items-center gap-1 bg-purple-500/10 text-purple-400 px-1.5 py-0.5 rounded border border-purple-500/20">
            <ClipboardList size={10} /> PRD
          </span>
        )}
        {planDoc && (
          <span className="text-[9px] flex items-center gap-1 bg-blue-500/10 text-blue-400 px-1.5 py-0.5 rounded border border-blue-500/20">
            <Layers size={10} /> Plan
          </span>
        )}
        {feature.phases.length > 0 && (
          <span className="text-[9px] flex items-center gap-1 bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700">
            {feature.phases.length} phase{feature.phases.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-800">
        {feature.category ? (
          <span className="text-[10px] text-slate-500 truncate capitalize">{feature.category}</span>
        ) : <span />}
        <span className="text-[10px] text-slate-600 flex items-center gap-1 group-hover:text-indigo-400 transition-colors">
          Details <ChevronRight size={10} />
        </span>
      </div>
    </div>
  );
};

// ── List View Card ─────────────────────────────────────────────────

const FeatureListCard = ({
  feature,
  onClick,
  onStatusChange,
}: {
  feature: Feature;
  onClick: () => void;
  onStatusChange: (newStatus: string) => void;
}) => {
  const statusStyle = getStatusStyle(feature.status);

  return (
    <div
      onClick={onClick}
      className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-indigo-500/50 transition-all cursor-pointer group shadow-sm hover:shadow-md"
    >
      <div className="flex justify-between items-start mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1">
            <span className="font-mono text-xs text-slate-500 border border-slate-800 px-1.5 py-0.5 rounded truncate max-w-[200px]">{feature.id}</span>
            <StatusDropdown status={feature.status} onStatusChange={onStatusChange} size="xs" />
            {feature.category && (
              <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400 capitalize">{feature.category}</span>
            )}
          </div>
          <h3 className="font-bold text-slate-200 text-lg group-hover:text-indigo-400 transition-colors truncate">{feature.name}</h3>
        </div>
        <div className="text-right ml-4 flex-shrink-0">
          <div className="text-indigo-400 font-mono font-bold text-sm">{feature.completedTasks}/{feature.totalTasks}</div>
          {feature.updatedAt && feature.updatedAt !== 'None' && (
            <div className="text-[10px] text-slate-500">{feature.updatedAt}</div>
          )}
        </div>
      </div>

      <div className="mb-3">
        <ProgressBar completed={feature.completedTasks} total={feature.totalTasks} />
      </div>

      <div className="pt-3 border-t border-slate-800 flex items-center justify-between">
        <div className="flex gap-2">
          {feature.linkedDocs.map(doc => (
            <span key={doc.id} className="text-[10px] flex items-center gap-1 bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700">
              <DocTypeIcon docType={doc.docType} />
              <DocTypeBadge docType={doc.docType} />
            </span>
          ))}
        </div>
        {feature.phases.length > 0 && (
          <span className="text-xs text-slate-500">{feature.phases.length} phase{feature.phases.length !== 1 ? 's' : ''}</span>
        )}
      </div>
    </div>
  );
};

// ── Status Column (Board View) ─────────────────────────────────────

const StatusColumn = ({
  title,
  status,
  features,
  onFeatureClick,
  onStatusChange,
}: {
  title: string;
  status: string;
  features: Feature[];
  onFeatureClick: (f: Feature) => void;
  onStatusChange: (featureId: string, newStatus: string) => void;
}) => {
  const style = getStatusStyle(status);

  return (
    <div className="flex flex-col gap-4 min-w-[300px] w-full lg:w-1/4">
      <div className="flex items-center justify-between px-2">
        <h3 className="font-semibold text-slate-300 text-sm uppercase tracking-wider flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${style.dot}`} />
          {title}
        </h3>
        <span className="text-slate-600 text-xs font-mono bg-slate-900 px-2 py-1 rounded">{features.length}</span>
      </div>

      <div className="flex flex-col gap-3 min-h-[200px] rounded-lg bg-slate-900/30 p-2 border border-slate-800/30 overflow-y-auto max-h-[calc(100vh-280px)]">
        {features.map(f => (
          <FeatureCard
            key={f.id}
            feature={f}
            onClick={() => onFeatureClick(f)}
            onStatusChange={(newStatus) => onStatusChange(f.id, newStatus)}
          />
        ))}
        {features.length === 0 && (
          <div className="h-full flex items-center justify-center text-slate-700 text-sm border-2 border-dashed border-slate-800 rounded-lg p-4">
            No features
          </div>
        )}
      </div>
    </div>
  );
};

// ── Main Component ─────────────────────────────────────────────────

export const ProjectBoard: React.FC = () => {
  const { features: apiFeatures, updateFeatureStatus } = useData();
  const [searchParams, setSearchParams] = useSearchParams();
  const [viewMode, setViewMode] = useState<'board' | 'list'>('board');
  const [selectedFeature, setSelectedFeature] = useState<Feature | null>(null);

  // Auto-select feature from URL search params
  useEffect(() => {
    const featureId = searchParams.get('feature');
    if (featureId && apiFeatures.length > 0) {
      const feat = apiFeatures.find(f => f.id === featureId);
      if (feat) {
        setSelectedFeature(feat);
        // Clear param to avoid re-triggering, or keep it for sharable URLs?
        // Let's clear it to keep URL clean after opening, similar to PlanCatalog
        setSearchParams({}, { replace: true });
      }
    }
  }, [searchParams, apiFeatures, setSearchParams]);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'date' | 'progress' | 'tasks'>('date');

  // Derive unique categories
  const categories = useMemo(() => {
    const cats = new Set(apiFeatures.map(f => f.category).filter(Boolean));
    return Array.from(cats).sort();
  }, [apiFeatures]);

  const filteredFeatures = useMemo(() => {
    let result = apiFeatures;

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter(f =>
        f.name.toLowerCase().includes(q) ||
        f.id.toLowerCase().includes(q) ||
        f.tags.some(t => t.toLowerCase().includes(q))
      );
    }

    if (statusFilter !== 'all') {
      result = result.filter(f => f.status === statusFilter);
    }

    if (categoryFilter !== 'all') {
      result = result.filter(f => f.category === categoryFilter);
    }

    return result.sort((a, b) => {
      if (sortBy === 'progress') {
        const pctA = a.totalTasks > 0 ? a.completedTasks / a.totalTasks : 0;
        const pctB = b.totalTasks > 0 ? b.completedTasks / b.totalTasks : 0;
        return pctB - pctA;
      }
      if (sortBy === 'tasks') return b.totalTasks - a.totalTasks;
      // date sort (default)
      return (b.updatedAt || '').localeCompare(a.updatedAt || '');
    });
  }, [apiFeatures, searchQuery, statusFilter, categoryFilter, sortBy]);

  const handleStatusChange = async (featureId: string, newStatus: string) => {
    await updateFeatureStatus(featureId, newStatus);
  };

  // Keep selected feature in sync with API data
  useEffect(() => {
    if (selectedFeature) {
      const updated = apiFeatures.find(f => f.id === selectedFeature.id);
      if (updated) {
        setSelectedFeature(updated);
      }
    }
  }, [apiFeatures]);

  const sidebarPortal = document.getElementById('sidebar-portal');

  return (
    <div className="h-full flex flex-col relative">

      {/* Sidebar Filters */}
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
                  placeholder="Search features..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none transition-colors"
                />
              </div>

              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">Status</label>
                <select
                  value={statusFilter}
                  onChange={e => setStatusFilter(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="all">All Statuses</option>
                  <option value="backlog">Backlog</option>
                  <option value="in-progress">In Progress</option>
                  <option value="review">Review</option>
                  <option value="done">Done</option>
                </select>
              </div>

              <div>
                <label className="text-[10px] text-slate-500 mb-1 block">Category</label>
                <select
                  value={categoryFilter}
                  onChange={e => setCategoryFilter(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="all">All Categories</option>
                  {categories.map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
              <ArrowUpDown size={12} /> Sort
            </h3>
            <div className="flex flex-col gap-1.5">
              {[
                { key: 'date', label: 'Recent' },
                { key: 'progress', label: 'Progress' },
                { key: 'tasks', label: 'Task Count' },
              ].map(s => (
                <button
                  key={s.key}
                  onClick={() => setSortBy(s.key as any)}
                  className={`py-1.5 px-3 text-xs rounded border text-left transition-colors ${sortBy === s.key ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-400' : 'bg-slate-900 border-slate-800 text-slate-400'}`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        </div>,
        sidebarPortal,
      )}

      {/* Page Header */}
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">Feature Board</h2>
          <p className="text-slate-400 text-sm">
            {filteredFeatures.length} features · Synced from project plans &amp; progress files
          </p>
        </div>
        <div className="flex gap-3">
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
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-x-auto">
        {viewMode === 'board' ? (
          <div className="flex gap-6 min-w-[1200px] h-full pb-4">
            <StatusColumn
              title="Backlog"
              status="backlog"
              features={filteredFeatures.filter(f => f.status === 'backlog')}
              onFeatureClick={setSelectedFeature}
              onStatusChange={handleStatusChange}
            />
            <StatusColumn
              title="In Progress"
              status="in-progress"
              features={filteredFeatures.filter(f => f.status === 'in-progress')}
              onFeatureClick={setSelectedFeature}
              onStatusChange={handleStatusChange}
            />
            <StatusColumn
              title="Review"
              status="review"
              features={filteredFeatures.filter(f => f.status === 'review')}
              onFeatureClick={setSelectedFeature}
              onStatusChange={handleStatusChange}
            />
            <StatusColumn
              title="Done"
              status="done"
              features={filteredFeatures.filter(f => f.status === 'done')}
              onFeatureClick={setSelectedFeature}
              onStatusChange={handleStatusChange}
            />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-6">
            {filteredFeatures.map(f => (
              <FeatureListCard
                key={f.id}
                feature={f}
                onClick={() => setSelectedFeature(f)}
                onStatusChange={(newStatus) => handleStatusChange(f.id, newStatus)}
              />
            ))}
            {filteredFeatures.length === 0 && (
              <div className="col-span-full py-12 text-center text-slate-500 border border-dashed border-slate-800 rounded-xl">
                No features match your filters.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Feature Detail Modal */}
      {selectedFeature && (
        <FeatureModal
          feature={selectedFeature}
          onClose={() => setSelectedFeature(null)}
        />
      )}
    </div>
  );
};
