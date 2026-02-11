import React, { useState, useMemo } from 'react';
import { useData } from '../contexts/DataContext';
import { AgentSession, SessionLog, LogType, SessionFileUpdate, SessionArtifact, PlanDocument } from '../types';
import { Clock, Database, Terminal, CheckCircle2, XCircle, Search, Edit3, GitCommit, GitBranch, ArrowLeft, Bot, Activity, Archive, PlayCircle, Cpu, Zap, Box, ChevronRight, MessageSquare, Code, ChevronDown, Calendar, BarChart2, PieChart as PieChartIcon, Users, TrendingUp, FileDiff, ShieldAlert, Check, FileText, ExternalLink, Link as LinkIcon, HardDrive, Scroll, Maximize2, X, MoreHorizontal, Layers } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, LineChart, Line, Legend, ComposedChart, Scatter, ReferenceLine } from 'recharts';
import { DocumentModal } from './DocumentModal';

// --- Sub-Components ---

const LogItemBlurb: React.FC<{
    log: SessionLog;
    isSelected: boolean;
    onClick: () => void;
}> = ({ log, isSelected, onClick }) => {
    const isAgent = log.speaker === 'agent';
    const isUser = log.speaker === 'user';

    if (log.type === 'message') {
        return (
            <div
                onClick={onClick}
                className={`group cursor-pointer flex gap-4 mb-4 px-2 py-1 rounded-xl transition-all ${isUser ? 'flex-row-reverse' : 'flex-row'} ${isSelected ? 'bg-indigo-500/10 ring-1 ring-indigo-500/30' : 'hover:bg-slate-800/30'
                    }`}
            >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 border transition-colors ${isSelected
                    ? 'border-indigo-500 bg-indigo-500/20 text-indigo-400'
                    : isUser
                        ? 'bg-slate-800 border-slate-700 text-slate-400'
                        : 'bg-indigo-500/10 border-indigo-500/20 text-indigo-400'
                    }`}>
                    {isUser ? <span className="text-xs font-bold">U</span> : <Bot size={16} />}
                </div>

                <div className={`flex flex-col max-w-[85%] ${isUser ? 'items-end' : 'items-start'}`}>
                    {isAgent && log.agentName && (
                        <span className={`text-[10px] font-mono mb-1 px-1.5 py-0.5 rounded transition-colors ${isSelected ? 'text-indigo-300 bg-indigo-500/20' : 'text-indigo-400 bg-indigo-500/5'}`}>
                            {log.agentName}
                        </span>
                    )}
                    <div className={`p-3 rounded-xl text-sm transition-all border ${isSelected
                        ? 'bg-transparent border-transparent text-indigo-100'
                        : isUser
                            ? 'bg-slate-800 border-slate-700 text-slate-300'
                            : 'bg-slate-900 border-slate-800 text-slate-300'
                        }`}>
                        <p className="line-clamp-3 leading-relaxed">{log.content}</p>
                    </div>
                </div>
            </div>
        );
    }

    const icons = {
        tool: <Terminal size={12} className="text-amber-500" />,
        subagent: <Zap size={12} className="text-purple-400" />,
        skill: <Cpu size={12} className="text-blue-400" />,
    };

    const label = log.type === 'tool' ? `Used Tool: ${log.toolCall?.name}` :
        log.type === 'subagent' ? `Spawned Agent: ${log.agentName || 'Subagent'}` :
            `Loaded Skill: ${log.skillDetails?.name}`;

    return (
        <div
            onClick={onClick}
            className={`cursor-pointer mb-2 ml-12 p-2 rounded-lg border transition-all flex items-center justify-between group ${isSelected
                ? 'bg-indigo-500/20 border-indigo-500/50 ring-1 ring-indigo-500/20'
                : 'bg-slate-950 border-slate-900 hover:border-slate-800'
                }`}
        >
            <div className="flex items-center gap-2 overflow-hidden">
                {icons[log.type as keyof typeof icons] || <Box size={12} />}
                <span className={`text-[11px] font-mono truncate transition-colors ${isSelected ? 'text-indigo-300' : 'text-slate-400'}`}>
                    {label}
                </span>
            </div>
            <ChevronRight size={12} className={`text-slate-600 transition-transform ${isSelected ? 'rotate-90 text-indigo-400' : 'group-hover:translate-x-0.5'}`} />
        </div>
    );
};

const DetailPane: React.FC<{ log: SessionLog }> = ({ log }) => {
    const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());

    const toggleSection = (id: string) => {
        const next = new Set(expandedSections);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        setExpandedSections(next);
    };

    return (
        <div className="flex flex-col h-full animate-in fade-in slide-in-from-right-2 duration-300">
            <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-lg shadow-inner">
                        {log.type === 'message' ? <MessageSquare size={16} /> : log.type === 'tool' ? <Terminal size={16} /> : <Zap size={16} />}
                    </div>
                    <div>
                        <h4 className="text-sm font-bold text-slate-100 uppercase tracking-tight">
                            {log.type === 'subagent' ? 'Subagent Thread' : log.type === 'tool' ? 'Tool Execution' : 'Log Details'}
                        </h4>
                        <p className="text-[10px] text-slate-500 font-mono">{log.timestamp}</p>
                    </div>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* TOOL DETAILS WITH INLINE EXPANSION */}
                {log.type === 'tool' && log.toolCall && (
                    <div className="space-y-4">
                        <div className="bg-slate-950 rounded-xl border border-slate-800 overflow-hidden">
                            <div className="px-4 py-3 bg-slate-900 border-b border-slate-800 flex justify-between items-center">
                                <span className="text-xs font-mono text-amber-500 flex items-center gap-2">
                                    <Terminal size={14} /> {log.toolCall.name}
                                </span>
                                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${log.toolCall.status === 'success' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'}`}>
                                    {log.toolCall.status.toUpperCase()}
                                </span>
                            </div>

                            {/* Arguments Section */}
                            <div className="p-4 border-b border-slate-800">
                                <button
                                    onClick={() => toggleSection('args')}
                                    className="w-full flex justify-between items-center text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-2 hover:text-slate-300 transition-colors"
                                >
                                    <span>Arguments</span>
                                    {expandedSections.has('args') ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                </button>
                                {expandedSections.has('args') && (
                                    <pre className="text-xs font-mono text-slate-300 bg-slate-900/50 p-3 rounded border border-slate-800 overflow-x-auto animate-in slide-in-from-top-1 duration-200">
                                        {log.toolCall.args}
                                    </pre>
                                )}
                            </div>

                            {/* Output Section */}
                            {log.toolCall.output && (
                                <div className="p-4 bg-slate-900/20">
                                    <button
                                        onClick={() => toggleSection('output')}
                                        className="w-full flex justify-between items-center text-[10px] text-slate-500 uppercase font-bold tracking-wider mb-2 hover:text-slate-300 transition-colors"
                                    >
                                        <span>Output</span>
                                        {expandedSections.has('output') ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    </button>
                                    {expandedSections.has('output') && (
                                        <pre className="text-xs font-mono text-slate-400 overflow-x-auto whitespace-pre-wrap animate-in slide-in-from-top-1 duration-200">
                                            {log.toolCall.output}
                                        </pre>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* SUBAGENT THREAD DETAILS */}
                {log.type === 'subagent' && log.subagentThread && (
                    <div className="space-y-4">
                        <div className="border-l-2 border-indigo-500/30 pl-4 space-y-4">
                            {log.subagentThread.map((sl, idx) => (
                                <div
                                    key={sl.id}
                                    onClick={() => toggleSection(`sub-${sl.id}`)}
                                    className="bg-slate-900/50 rounded-lg p-3 border border-slate-800 cursor-pointer hover:border-slate-700 transition-all"
                                >
                                    <div className="flex justify-between items-center mb-2">
                                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${sl.speaker === 'user' ? 'bg-slate-800 text-slate-400' : 'bg-indigo-500/10 text-indigo-400'}`}>
                                            {sl.speaker.toUpperCase()}
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <span className="text-[9px] text-slate-600 font-mono">{sl.timestamp}</span>
                                            {expandedSections.has(`sub-${sl.id}`) ? <ChevronDown size={12} className="text-slate-500" /> : <ChevronRight size={12} className="text-slate-500" />}
                                        </div>
                                    </div>
                                    <p className={`text-xs text-slate-300 ${expandedSections.has(`sub-${sl.id}`) ? '' : 'line-clamp-2'}`}>{sl.content}</p>
                                    {expandedSections.has(`sub-${sl.id}`) && sl.toolCall && (
                                        <div className="mt-3 text-[10px] font-mono text-amber-500 bg-amber-500/5 p-2 rounded border border-amber-500/10 animate-in fade-in duration-200">
                                            <div className="mb-1 flex justify-between">
                                                <span>{'>'} {sl.toolCall.name}</span>
                                                <span className="opacity-50">{sl.toolCall.status}</span>
                                            </div>
                                            <div className="text-slate-500 truncate">{sl.toolCall.args}</div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* FALLBACK FOR REGULAR MESSAGES */}
                {log.type === 'message' && (
                    <div className="bg-slate-900/30 border border-slate-800 rounded-xl p-5">
                        <p className="text-slate-300 leading-relaxed whitespace-pre-wrap text-sm">{log.content}</p>
                    </div>
                )}

                {/* SKILLS */}
                {log.type === 'skill' && log.skillDetails && (
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                        <div className="flex items-center gap-2 text-blue-400 font-mono text-sm mb-3">
                            <Cpu size={16} /> {log.skillDetails.name}
                        </div>
                        <p className="text-slate-400 text-xs mb-4 leading-relaxed">{log.skillDetails.description}</p>
                        <div className="flex items-center justify-between text-[10px] border-t border-slate-800 pt-3">
                            <span className="text-slate-500">Version</span>
                            <span className="font-mono text-slate-300">{log.skillDetails.version}</span>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

// --- View Components ---

const TranscriptView: React.FC<{
    session: AgentSession;
    selectedLogId: string | null;
    setSelectedLogId: (id: string | null) => void;
    filterAgent?: string | null;
}> = ({ session, selectedLogId, setSelectedLogId, filterAgent }) => {

    const logs = filterAgent
        ? session.logs.filter(l => l.agentName === filterAgent || l.speaker === 'user')
        : session.logs;

    const selectedLog = logs.find(l => l.id === selectedLogId);

    return (
        <div className="flex-1 flex gap-6 min-h-0 min-w-full h-full">
            {/* Pane 1: Chat Transcript (Left) */}
            <div
                className={`flex flex-col bg-slate-900/50 border border-slate-800 rounded-2xl overflow-hidden transition-all duration-500 ease-out min-w-[450px] ${selectedLogId ? 'basis-[70%]' : 'flex-1'
                    }`}
            >
                <div className="p-4 border-b border-slate-800 bg-slate-950/50 flex items-center justify-between">
                    <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                        <MessageSquare size={14} className="text-indigo-400" /> {filterAgent ? `Transcript: ${filterAgent}` : 'Full Transcript'}
                    </h3>
                    <div className="text-[10px] text-slate-600 font-mono">{logs.length} Steps</div>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-2 custom-scrollbar">
                    {logs.map(log => (
                        <LogItemBlurb
                            key={log.id}
                            log={log}
                            isSelected={selectedLogId === log.id}
                            onClick={() => setSelectedLogId(log.id === selectedLogId ? null : log.id)}
                        />
                    ))}
                    {logs.length === 0 && <div className="p-8 text-center text-slate-500 italic">No logs found for this view.</div>}
                </div>
            </div>

            {/* Pane 2: Expanded Details (Middle) - Dynamic visibility */}
            {selectedLogId && (
                <div className="basis-[30%] min-w-[320px] flex flex-col bg-slate-900 border border-indigo-500/20 rounded-2xl overflow-hidden shadow-2xl animate-in fade-in slide-in-from-right-4 duration-300">
                    {selectedLog && <DetailPane log={selectedLog} />}
                </div>
            )}

            {/* Pane 3: Metadata Details (Far Right) - Smaller fixed-ish width */}
            <div className="w-[280px] min-w-[240px] max-w-[320px] flex flex-col gap-5 overflow-y-auto pb-4 shrink-0">
                {/* Performance Summary */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Forensics</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs text-slate-400"><Clock size={14} /> Duration</div>
                            <span className="text-xs font-mono text-slate-200">{session.durationSeconds}s</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs text-slate-400"><Database size={14} /> Tokens</div>
                            <span className="text-xs font-mono text-slate-200">{(session.tokensIn + session.tokensOut).toLocaleString()}</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-xs text-slate-400"><Code size={14} /> Base Model</div>
                            <span className="text-[10px] font-mono text-indigo-400 truncate max-w-[120px]" title={session.model}>{session.model.split('-').slice(0, 2).join(' ')}</span>
                        </div>
                    </div>
                </div>

                {/* Git Context */}
                {session.gitCommitHash && (
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
                        <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Version Control</h3>
                        <div className="space-y-4">
                            <div className="group">
                                <div className="text-[9px] text-slate-600 uppercase font-bold mb-1 group-hover:text-slate-400 transition-colors">Commit Hash</div>
                                <div className="flex items-center gap-2 text-xs font-mono text-indigo-400 bg-indigo-500/5 p-1.5 rounded border border-indigo-500/10">
                                    <GitCommit size={14} /> {session.gitCommitHash}
                                </div>
                            </div>
                            <div className="group">
                                <div className="text-[9px] text-slate-600 uppercase font-bold mb-1">Branch</div>
                                <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
                                    <GitBranch size={14} className="text-slate-500" /> {session.gitBranch}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Tool Breakdown */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex-1 shadow-sm">
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Tool Efficiency</h3>
                    <div className="space-y-5">
                        {session.toolsUsed.map(tool => (
                            <div key={tool.name} className="space-y-1.5">
                                <div className="flex justify-between items-center text-[11px] font-mono">
                                    <span className="text-slate-400">{tool.name}</span>
                                    <span className="text-slate-300 font-bold">{tool.count}</span>
                                </div>
                                <div className="w-full bg-slate-950 h-1.5 rounded-full overflow-hidden border border-slate-800/50">
                                    <div
                                        className={`h-full transition-all duration-1000 ${tool.successRate > 0.9 ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.3)]' : 'bg-amber-500'}`}
                                        style={{ width: `${tool.successRate * 100}%` }}
                                    />
                                </div>
                                <div className="flex justify-end">
                                    <span className="text-[9px] text-slate-600 font-mono">{(tool.successRate * 100).toFixed(0)}% SR</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};

const FilesView: React.FC<{ session: AgentSession; onOpenDoc: (doc: PlanDocument) => void }> = ({ session, onOpenDoc }) => {
    const { documents } = useData();
    if (!session.updatedFiles || session.updatedFiles.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
                <FileText size={48} className="mb-4 opacity-20" />
                <p>No file updates recorded for this session.</p>
            </div>
        );
    }

    const handleFileClick = (file: SessionFileUpdate) => {
        const doc = documents.find(d => d.filePath === file.filePath);
        if (doc) {
            onOpenDoc(doc);
        } else {
            console.log(`Opening external file: ${file.filePath}`);
            alert(`Opening ${file.filePath} in local IDE...`);
        }
    };

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="grid grid-cols-12 gap-4 p-4 border-b border-slate-800 bg-slate-950/50 text-xs font-bold text-slate-500 uppercase tracking-wider">
                <div className="col-span-4">File Path</div>
                <div className="col-span-2">Stats</div>
                <div className="col-span-3">Commits</div>
                <div className="col-span-2">Agent</div>
                <div className="col-span-1 text-right">Action</div>
            </div>
            <div className="divide-y divide-slate-800">
                {session.updatedFiles.map((file, idx) => (
                    <div key={idx} className="grid grid-cols-12 gap-4 p-4 hover:bg-slate-800/30 transition-colors items-center group">
                        <div className="col-span-4 flex items-center gap-3">
                            <FileText size={16} className="text-indigo-400" />
                            <span className="text-sm font-mono text-slate-300 truncate" title={file.filePath}>{file.filePath}</span>
                        </div>
                        <div className="col-span-2 flex items-center gap-3 text-xs font-mono">
                            <span className="text-emerald-400">+{file.additions}</span>
                            <span className="text-rose-400">-{file.deletions}</span>
                        </div>
                        <div className="col-span-3 flex flex-wrap gap-1">
                            {file.commits.map(commit => (
                                <span key={commit} className="flex items-center gap-1 text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700 font-mono">
                                    <GitCommit size={10} /> {commit}
                                </span>
                            ))}
                        </div>
                        <div className="col-span-2 text-sm text-slate-400">{file.agentName}</div>
                        <div className="col-span-1 text-right">
                            <button
                                onClick={() => handleFileClick(file)}
                                className="p-1.5 hover:bg-indigo-500/10 text-slate-500 hover:text-indigo-400 rounded transition-colors"
                                title={documents.find(d => d.filePath === file.filePath) ? "View Document" : "Open in IDE"}
                            >
                                {documents.find(d => d.filePath === file.filePath) ? <Maximize2 size={16} /> : <ExternalLink size={16} />}
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

const ArtifactsView: React.FC<{ session: AgentSession }> = ({ session }) => {
    if (!session.linkedArtifacts || session.linkedArtifacts.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
                <LinkIcon size={48} className="mb-4 opacity-20" />
                <p>No linked artifacts found.</p>
            </div>
        );
    }

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {session.linkedArtifacts.map(artifact => (
                <div key={artifact.id} className="bg-slate-900 border border-slate-800 rounded-xl p-6 hover:border-indigo-500/50 transition-all group">
                    <div className="flex justify-between items-start mb-4">
                        <div className={`p-2 rounded-lg ${artifact.type === 'memory' ? 'bg-purple-500/10 text-purple-400' :
                            artifact.type === 'request_log' ? 'bg-amber-500/10 text-amber-400' :
                                'bg-blue-500/10 text-blue-400'
                            }`}>
                            {artifact.type === 'memory' ? <HardDrive size={20} /> :
                                artifact.type === 'request_log' ? <Scroll size={20} /> :
                                    <Database size={20} />}
                        </div>
                        <span className="text-[10px] bg-slate-800 text-slate-500 px-2 py-0.5 rounded uppercase font-bold tracking-wider">
                            {artifact.source}
                        </span>
                    </div>

                    <h3 className="font-bold text-slate-200 mb-2 group-hover:text-indigo-400 transition-colors">{artifact.title}</h3>
                    <p className="text-sm text-slate-400 mb-4 line-clamp-3">{artifact.description}</p>

                    <div className="pt-4 border-t border-slate-800 flex justify-between items-center">
                        <span className="text-xs font-mono text-slate-500">{artifact.id}</span>
                        <button className="text-xs flex items-center gap-1 text-indigo-400 hover:text-indigo-300">
                            View Details <ChevronRight size={12} />
                        </button>
                    </div>
                </div>
            ))}
        </div>
    );
};

// --- Analytics Sub-Components ---

const AnalyticsDetailsModal: React.FC<{
    title: string;
    data: any;
    onClose: () => void;
    onViewTranscript: (agentName?: string) => void;
}> = ({ title, data, onClose, onViewTranscript }) => {
    if (!data) return null;

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
            <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-lg shadow-2xl overflow-hidden flex flex-col">
                <div className="p-5 border-b border-slate-800 flex justify-between items-center bg-slate-950">
                    <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                        <Activity size={18} className="text-indigo-500" />
                        {title}: {data.name}
                    </h3>
                    <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
                        <X size={20} />
                    </button>
                </div>
                <div className="p-6 space-y-6">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700/50">
                            <div className="text-xs text-slate-500 uppercase font-bold mb-1">Total Interactions</div>
                            <div className="text-2xl font-mono text-white">{data.value || 0}</div>
                        </div>
                        <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700/50">
                            <div className="text-xs text-slate-500 uppercase font-bold mb-1">Estimated Cost</div>
                            <div className="text-2xl font-mono text-emerald-400">${(data.cost || 0).toFixed(4)}</div>
                        </div>
                    </div>

                    <div className="space-y-2">
                        <div className="flex justify-between text-sm border-b border-slate-800 pb-2">
                            <span className="text-slate-400">Tokens Consumed</span>
                            <span className="font-mono text-slate-200">{(data.tokens || 0).toLocaleString()}</span>
                        </div>
                        <div className="flex justify-between text-sm border-b border-slate-800 pb-2">
                            <span className="text-slate-400">Tools Called</span>
                            <span className="font-mono text-slate-200">{data.toolCount || 0}</span>
                        </div>
                    </div>

                    <button
                        onClick={() => onViewTranscript(data.type === 'agent' ? data.name : undefined)}
                        className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
                    >
                        <MessageSquare size={16} /> Filter Transcript
                    </button>
                </div>
            </div>
        </div>
    );
};

const TokenTimeline: React.FC<{ session: AgentSession }> = ({ session }) => {
    // Transform logs into cumulative timeline data
    const timelineData = useMemo(() => {
        let cumulativeTokens = 0;
        return session.logs.map((log, index) => {
            // Mock token estimation per step
            const stepTokens = (log.content.length / 4) + (log.toolCall ? 100 : 0);
            cumulativeTokens += stepTokens;

            // Map file edits to this timestamp if they exist
            const fileUpdates = session.updatedFiles?.filter(f => {
                // Approximate matching by index or timestamp string would be better in real app
                // For mock, we'll just check if speaker is agent and index matches roughly
                return log.speaker === 'agent' && Math.random() > 0.9;
            });

            return {
                index,
                time: log.timestamp,
                tokens: Math.round(cumulativeTokens),
                stepTokens: Math.round(stepTokens),
                agent: log.agentName,
                tool: log.toolCall ? log.toolCall.name : null,
                fileCount: fileUpdates?.length || 0,
                speaker: log.speaker
            };
        });
    }, [session]);

    return (
        <div className="h-80 w-full relative">
            <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={timelineData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                    <defs>
                        <linearGradient id="colorTokens" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="time" stroke="#475569" tick={{ fontSize: 10 }} interval={Math.floor(timelineData.length / 5)} />
                    <YAxis stroke="#475569" tick={{ fontSize: 10 }} label={{ value: 'Tokens', angle: -90, position: 'insideLeft', fill: '#64748b' }} />
                    <Tooltip
                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }}
                        itemStyle={{ color: '#e2e8f0' }}
                        labelStyle={{ color: '#94a3b8' }}
                    />

                    {/* Token Area */}
                    <Area type="monotone" dataKey="tokens" stroke="#3b82f6" fillOpacity={1} fill="url(#colorTokens)" name="Cumulative Tokens" />

                    {/* Tool Usage Scatter */}
                    <Scatter name="Tool Used" dataKey="tool" fill="#f59e0b" shape="circle" />

                    {/* File Edit Scatter (Using dummy value 1 for y-placement normalization, but ideally should be on timeline) */}
                    {/* Note: Recharts scatter on composed chart is tricky with categorical data, simulating via customized dots on line if needed, 
                        but for now relying on toolTip to show details */}
                </ComposedChart>
            </ResponsiveContainer>

            {/* Overlay Event Markers (Custom HTML overlay for better control than SVG scatter sometimes) */}
            <div className="absolute top-0 left-0 w-full h-full pointer-events-none overflow-hidden">
                {timelineData.filter(d => d.tool).map((d, i) => (
                    <div key={`tool-${i}`} className="absolute bottom-2" style={{ left: `${(i / timelineData.length) * 100}%` }}>
                        <div className="w-1.5 h-1.5 rounded-full bg-amber-500" title={`Tool: ${d.tool}`} />
                    </div>
                ))}
            </div>
        </div>
    );
};


const AnalyticsView: React.FC<{
    session: AgentSession;
    goToTranscript: (agentName?: string) => void;
}> = ({ session, goToTranscript }) => {
    const [modalData, setModalData] = useState<{ title: string; data: any } | null>(null);
    const [tokenViewMode, setTokenViewMode] = useState<'summary' | 'timeline'>('summary');

    const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'];

    // --- Data Aggregation ---

    // 1. Tool Data
    const toolData = session.toolsUsed.map(t => ({
        name: t.name,
        value: t.count,
        type: 'tool',
        cost: session.totalCost * 0.1, // Mock portion
        tokens: Math.round(session.tokensIn * 0.1) // Mock portion
    }));

    // 2. Agent Data
    const agentStats = useMemo(() => {
        const stats: Record<string, { count: number, tokens: number, tools: number }> = {};
        session.logs.forEach(log => {
            if (log.speaker === 'agent') {
                const name = log.agentName || 'Main';
                if (!stats[name]) stats[name] = { count: 0, tokens: 0, tools: 0 };
                stats[name].count += 1;
                stats[name].tokens += log.content.length / 4; // Approx
                if (log.type === 'tool') stats[name].tools += 1;
            }
        });
        return Object.entries(stats).map(([name, stat]) => ({
            name,
            value: stat.count,
            tokens: Math.round(stat.tokens),
            toolCount: stat.tools,
            cost: (stat.tokens / 1000000) * 15, // Mock pricing
            type: 'agent'
        }));
    }, [session]);

    // 3. Model Data
    const modelData = useMemo(() => {
        // Mocking: assuming Agents use different models or the session model is primary
        // In a real app, logs would have `modelId`
        return [{
            name: session.model,
            value: session.logs.length,
            tokens: session.tokensIn + session.tokensOut,
            toolCount: session.toolsUsed.reduce((acc, t) => acc + t.count, 0),
            cost: session.totalCost,
            type: 'model'
        }];
    }, [session]);

    return (
        <div className="h-full overflow-y-auto pb-6 relative">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">

                {/* 1. AGENTS CHART */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-sm font-bold text-slate-300 mb-6 flex items-center gap-2"><Users size={16} /> Active Agents</h3>
                    <div className="h-64 cursor-pointer">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={agentStats} onClick={(data: any) => data && data.activePayload && setModalData({ title: 'Agent Details', data: data.activePayload[0].payload })}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                <XAxis dataKey="name" stroke="#475569" tick={{ fontSize: 12 }} />
                                <YAxis stroke="#475569" tick={{ fontSize: 12 }} />
                                <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                                <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} name="Interactions" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 2. TOOLS CHART */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-sm font-bold text-slate-300 mb-6 flex items-center gap-2"><PieChartIcon size={16} /> Tool Usage</h3>
                    <div className="h-64 cursor-pointer">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={toolData}
                                    innerRadius={60}
                                    outerRadius={80}
                                    paddingAngle={5}
                                    dataKey="value"
                                    onClick={(data) => setModalData({ title: 'Tool Details', data: data })}
                                >
                                    {toolData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                    ))}
                                </Pie>
                                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f1f5f9' }} itemStyle={{ color: '#e2e8f0' }} />
                                <Legend verticalAlign="bottom" height={36} wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 3. MODELS CHART */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-sm font-bold text-slate-300 mb-6 flex items-center gap-2"><Cpu size={16} /> Model Allocation</h3>
                    <div className="h-64 cursor-pointer">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart layout="vertical" data={modelData} onClick={(data: any) => data && data.activePayload && setModalData({ title: 'Model Details', data: data.activePayload[0].payload })}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                                <XAxis type="number" stroke="#475569" tick={{ fontSize: 12 }} />
                                <YAxis dataKey="name" type="category" stroke="#94a3b8" tick={{ fontSize: 10 }} width={100} />
                                <Tooltip cursor={{ fill: '#1e293b' }} contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                                <Bar dataKey="value" fill="#10b981" radius={[0, 4, 4, 0]} barSize={24} name="Steps Executed" />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* 4. TOKEN CONSUMPTION (Toggleable) */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <div className="flex justify-between items-center mb-6">
                        <h3 className="text-sm font-bold text-slate-300 flex items-center gap-2"><BarChart2 size={16} /> Token Consumption</h3>
                        <div className="flex bg-slate-950 rounded-lg p-0.5 border border-slate-800">
                            <button
                                onClick={() => setTokenViewMode('summary')}
                                className={`px-2 py-1 text-[10px] font-bold rounded ${tokenViewMode === 'summary' ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                            >
                                Summary
                            </button>
                            <button
                                onClick={() => setTokenViewMode('timeline')}
                                className={`px-2 py-1 text-[10px] font-bold rounded ${tokenViewMode === 'timeline' ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:text-slate-300'}`}
                            >
                                Timeline
                            </button>
                        </div>
                    </div>

                    <div className="h-64">
                        {tokenViewMode === 'summary' ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={[
                                    { name: 'Input', tokens: session.tokensIn, fill: '#3b82f6' },
                                    { name: 'Output', tokens: session.tokensOut, fill: '#10b981' }
                                ]} layout="vertical">
                                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                                    <XAxis type="number" stroke="#475569" tick={{ fontSize: 12 }} />
                                    <YAxis dataKey="name" type="category" stroke="#94a3b8" tick={{ fontSize: 12 }} />
                                    <Tooltip cursor={{ fill: 'transparent' }} contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                                    <Bar dataKey="tokens" radius={[0, 4, 4, 0]} barSize={32} />
                                </BarChart>
                            </ResponsiveContainer>
                        ) : (
                            <TokenTimeline session={session} />
                        )}
                    </div>
                </div>

                {/* 5. MASTER TIMELINE VIEW (Full Width) */}
                <div className="md:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-sm font-bold text-slate-300 mb-2 flex items-center gap-2"><Layers size={16} /> Session Master Timeline</h3>
                    <p className="text-xs text-slate-500 mb-6">Correlated view of token usage, tool executions, and file edits over the session lifecycle.</p>
                    <TokenTimeline session={session} />
                    <div className="mt-4 flex gap-4 justify-center">
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                            <div className="w-3 h-3 bg-blue-500/50 border border-blue-500 rounded-sm"></div> Token Volume
                        </div>
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                            <div className="w-2 h-2 rounded-full bg-amber-500"></div> Tool Execution
                        </div>
                    </div>
                </div>

            </div>

            {/* COST SUMMARY */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <h3 className="text-sm font-bold text-slate-300 mb-2">Cost Analysis</h3>
                <div className="flex items-center gap-8">
                    <div className="flex-1 bg-slate-950 rounded-lg p-4 border border-slate-800">
                        <div className="text-xs text-slate-500 mb-1">Total Cost</div>
                        <div className="text-3xl font-mono text-emerald-400 font-bold">${session.totalCost.toFixed(4)}</div>
                    </div>
                    <div className="flex-1 bg-slate-950 rounded-lg p-4 border border-slate-800">
                        <div className="text-xs text-slate-500 mb-1">Cost / Step</div>
                        <div className="text-3xl font-mono text-indigo-400 font-bold">${(session.totalCost / session.logs.length).toFixed(4)}</div>
                    </div>
                    <div className="flex-1 bg-slate-950 rounded-lg p-4 border border-slate-800">
                        <div className="text-xs text-slate-500 mb-1">Tokens / Step</div>
                        <div className="text-3xl font-mono text-blue-400 font-bold">{Math.round((session.tokensIn + session.tokensOut) / session.logs.length)}</div>
                    </div>
                </div>
            </div>

            {/* DETAIL MODAL */}
            {modalData && (
                <AnalyticsDetailsModal
                    title={modalData.title}
                    data={modalData.data}
                    onClose={() => setModalData(null)}
                    onViewTranscript={(agent) => {
                        goToTranscript(agent);
                        setModalData(null);
                    }}
                />
            )}
        </div>
    );
};

const AgentsView: React.FC<{
    session: AgentSession;
    onSelectAgent: (agentName: string) => void;
}> = ({ session, onSelectAgent }) => {
    // Extract unique agents
    const agents = Array.from(new Set(session.logs.filter(l => l.speaker === 'agent').map(l => l.agentName || 'Main Agent')));

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {agents.map(agent => {
                const agentLogs = session.logs.filter(l => l.agentName === agent || (agent === 'Main Agent' && !l.agentName && l.speaker === 'agent'));
                const toolsUsed = new Set(agentLogs.filter(l => l.type === 'tool').map(l => l.toolCall?.name));

                return (
                    <div
                        key={agent}
                        onClick={() => onSelectAgent(agent === 'Main Agent' ? '' : agent)}
                        className="bg-slate-900 border border-slate-800 rounded-xl p-6 hover:border-indigo-500/50 hover:shadow-lg transition-all cursor-pointer group"
                    >
                        <div className="flex items-center gap-4 mb-4">
                            <div className="w-12 h-12 rounded-full bg-slate-800 border-2 border-slate-700 flex items-center justify-center text-xl font-bold text-indigo-400 group-hover:border-indigo-500 transition-colors">
                                {agent[0]}
                            </div>
                            <div>
                                <h3 className="font-bold text-slate-200 group-hover:text-indigo-400 transition-colors">{agent}</h3>
                                <p className="text-xs text-slate-500 font-mono">{agentLogs.length} interactions</p>
                            </div>
                        </div>

                        <div className="space-y-3 mb-4">
                            <div className="flex justify-between text-xs">
                                <span className="text-slate-500">Tools Accessed</span>
                                <span className="text-slate-300 font-mono">{toolsUsed.size}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                                <span className="text-slate-500">Avg. Response Time</span>
                                <span className="text-slate-300 font-mono">~1.2s</span>
                            </div>
                        </div>

                        <div className="pt-4 border-t border-slate-800">
                            <button className="text-xs font-bold text-indigo-400 flex items-center gap-1 group-hover:translate-x-1 transition-transform">
                                View Transcript <ArrowLeft size={12} className="rotate-180" />
                            </button>
                        </div>
                    </div>
                );
            })}
        </div>
    );
};

const ImpactView: React.FC<{ session: AgentSession }> = ({ session }) => {
    if (!session.impactHistory || session.impactHistory.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
                <Activity size={48} className="mb-4 opacity-20" />
                <p>No app impact metrics recorded for this session.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6 h-full overflow-y-auto pb-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <h3 className="text-sm font-bold text-slate-300 mb-6 flex items-center gap-2"><TrendingUp size={16} /> Codebase Impact Over Time</h3>
                <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={session.impactHistory}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis dataKey="timestamp" stroke="#475569" tick={{ fontSize: 12 }} />
                            <YAxis stroke="#475569" tick={{ fontSize: 12 }} />
                            <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                            <Legend />
                            <Line type="monotone" dataKey="locAdded" stroke="#10b981" strokeWidth={2} name="LOC Added" dot={false} />
                            <Line type="monotone" dataKey="locDeleted" stroke="#f43f5e" strokeWidth={2} name="LOC Removed" dot={false} />
                            <Line type="monotone" dataKey="fileCount" stroke="#3b82f6" strokeWidth={2} name="Files Touched" dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-sm font-bold text-slate-300 mb-6 flex items-center gap-2"><ShieldAlert size={16} /> Test Stability</h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={session.impactHistory}>
                                <defs>
                                    <linearGradient id="colorPass" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="colorFail" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                                <XAxis dataKey="timestamp" stroke="#475569" tick={{ fontSize: 12 }} />
                                <YAxis stroke="#475569" tick={{ fontSize: 12 }} />
                                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                                <Area type="monotone" dataKey="testPassCount" stackId="1" stroke="#10b981" fill="url(#colorPass)" name="Tests Passed" />
                                <Area type="monotone" dataKey="testFailCount" stackId="1" stroke="#f43f5e" fill="url(#colorFail)" name="Tests Failed" />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 flex flex-col justify-center">
                    <h3 className="text-sm font-bold text-slate-300 mb-4">Final Session Impact</h3>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between p-3 bg-emerald-500/10 rounded-lg border border-emerald-500/20">
                            <div className="flex items-center gap-3">
                                <FileDiff className="text-emerald-500" size={20} />
                                <span className="text-sm text-slate-300">Net Code Growth</span>
                            </div>
                            <span className="font-mono font-bold text-emerald-400">+{session.impactHistory[session.impactHistory.length - 1].locAdded - session.impactHistory[session.impactHistory.length - 1].locDeleted} LOC</span>
                        </div>
                        <div className="flex items-center justify-between p-3 bg-blue-500/10 rounded-lg border border-blue-500/20">
                            <div className="flex items-center gap-3">
                                <Check className="text-blue-500" size={20} />
                                <span className="text-sm text-slate-300">Tests Passing</span>
                            </div>
                            <span className="font-mono font-bold text-blue-400">{session.impactHistory[session.impactHistory.length - 1].testPassCount}</span>
                        </div>
                        <div className="flex items-center justify-between p-3 bg-rose-500/10 rounded-lg border border-rose-500/20">
                            <div className="flex items-center gap-3">
                                <ShieldAlert className="text-rose-500" size={20} />
                                <span className="text-sm text-slate-300">New Regressions</span>
                            </div>
                            <span className="font-mono font-bold text-rose-400">{session.impactHistory[session.impactHistory.length - 1].testFailCount}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

// --- Main Container ---

const SessionDetail: React.FC<{ session: AgentSession; onBack: () => void }> = ({ session, onBack }) => {
    const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'transcript' | 'analytics' | 'agents' | 'impact' | 'files' | 'artifacts'>('transcript');
    const [filterAgent, setFilterAgent] = useState<string | null>(null);
    const [viewingDoc, setViewingDoc] = useState<PlanDocument | null>(null);

    const handleSelectAgent = (agent: string) => {
        setFilterAgent(agent || null); // Empty string resets filter
        setActiveTab('transcript');
    };

    const handleJumpToTranscript = (agentName?: string) => {
        if (agentName) setFilterAgent(agentName);
        else setFilterAgent(null);
        setActiveTab('transcript');
    }

    return (
        <div className="h-full flex flex-col animate-in fade-in slide-in-from-bottom-4 duration-500 relative">
            {/* Header */}
            <div className="flex justify-between items-center mb-4 px-2">
                <div className="flex items-center gap-4">
                    <button onClick={onBack} className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-all group">
                        <ArrowLeft size={18} className="group-hover:-translate-x-1 transition-transform" />
                    </button>
                    <div>
                        <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
                            {session.id}
                            <span className="text-slate-700 font-mono text-xs">/</span>
                            <span className="text-slate-500 font-mono text-xs tracking-wider">{session.taskId}</span>
                        </h2>
                        <div className="flex items-center gap-3 mt-0.5">
                            <span className="text-xs text-slate-500 flex items-center gap-1.5"><Calendar size={12} /> {new Date(session.startedAt).toLocaleString()}</span>
                            <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${session.status === 'active' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-slate-800 text-slate-500'}`}>
                                {session.status}
                            </span>
                        </div>
                    </div>
                </div>

                {/* Tabs */}
                <div className="flex items-center bg-slate-900 rounded-lg p-1 border border-slate-800 overflow-x-auto">
                    {[
                        { id: 'transcript', icon: MessageSquare, label: 'Transcript' },
                        { id: 'files', icon: FileText, label: 'Files' },
                        { id: 'artifacts', icon: LinkIcon, label: 'Artifacts' },
                        { id: 'impact', icon: TrendingUp, label: 'App Impact' },
                        { id: 'analytics', icon: BarChart2, label: 'Analytics' },
                        { id: 'agents', icon: Users, label: 'Agents' },
                    ].map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id as any)}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all whitespace-nowrap ${activeTab === tab.id
                                ? 'bg-indigo-600 text-white shadow'
                                : 'text-slate-400 hover:text-slate-200'
                                }`}
                        >
                            <tab.icon size={14} />
                            {tab.label}
                        </button>
                    ))}
                </div>

                <div className="flex items-center gap-6">
                    <div className="text-right">
                        <div className="text-[10px] text-slate-500 uppercase font-bold tracking-widest mb-1">Session Cost</div>
                        <div className="text-emerald-400 font-mono font-bold text-lg">${session.totalCost.toFixed(2)}</div>
                    </div>
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 min-h-0 min-w-full">
                {activeTab === 'transcript' && (
                    <TranscriptView
                        session={session}
                        selectedLogId={selectedLogId}
                        setSelectedLogId={setSelectedLogId}
                        filterAgent={filterAgent}
                    />
                )}
                {activeTab === 'files' && <FilesView session={session} onOpenDoc={setViewingDoc} />}
                {activeTab === 'artifacts' && <ArtifactsView session={session} />}
                {activeTab === 'analytics' && <AnalyticsView session={session} goToTranscript={handleJumpToTranscript} />}
                {activeTab === 'agents' && <AgentsView session={session} onSelectAgent={handleSelectAgent} />}
                {activeTab === 'impact' && <ImpactView session={session} />}
            </div>

            {viewingDoc && <DocumentModal doc={viewingDoc} onClose={() => setViewingDoc(null)} />}
        </div>
    );
};

export const SessionInspector: React.FC = () => {
    const { sessions } = useData();
    const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

    const activeSessions = sessions.filter(s => s.status === 'active');
    const pastSessions = sessions.filter(s => s.status !== 'active');

    if (selectedSessionId) {
        const session = sessions.find(s => s.id === selectedSessionId);
        if (session) {
            return <SessionDetail session={session} onBack={() => setSelectedSessionId(null)} />;
        }
    }

    return (
        <div className="h-full flex flex-col gap-8 animate-in fade-in duration-500">
            <div>
                <h2 className="text-3xl font-bold text-slate-100 mb-2 font-mono tracking-tighter">Session Forensics</h2>
                <p className="text-slate-400 max-w-2xl">Examine agent behavior, tool call chains, and multi-agent orchestration logs with millisecond-precision timestamps.</p>
            </div>

            <div className="space-y-10">
                {/* Active Sessions Section */}
                <div className="space-y-4">
                    <h3 className="text-xs font-bold text-emerald-500 uppercase tracking-[0.2em] flex items-center gap-2">
                        <Activity size={16} /> Live In-Flight
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                        {activeSessions.map(session => (
                            <SessionSummaryCard key={session.id} session={session} onClick={() => setSelectedSessionId(session.id)} />
                        ))}
                        {activeSessions.length === 0 && (
                            <div className="col-span-full border border-dashed border-slate-800 rounded-2xl p-10 text-center text-slate-600 bg-slate-900/10">
                                <Zap size={32} className="mx-auto mb-3 opacity-10" />
                                <p className="text-sm">No live sessions detected on local system.</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Past Sessions Section */}
                <div className="space-y-4">
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-[0.2em] flex items-center gap-2">
                        <Archive size={16} /> Historical Index
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                        {pastSessions.map(session => (
                            <SessionSummaryCard key={session.id} session={session} onClick={() => setSelectedSessionId(session.id)} />
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};

const SessionSummaryCard: React.FC<{ session: AgentSession; onClick: () => void }> = ({ session, onClick }) => (
    <div
        onClick={onClick}
        className="group bg-slate-900 border border-slate-800 rounded-2xl p-6 hover:border-indigo-500/50 hover:shadow-2xl hover:shadow-indigo-500/5 transition-all cursor-pointer relative overflow-hidden"
    >
        {session.status === 'active' && (
            <div className="absolute top-0 right-0 p-3">
                <span className="flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                </span>
            </div>
        )}

        <div className="flex justify-between items-start mb-5">
            <div className="flex items-center gap-3">
                <div className={`p-2.5 rounded-xl ${session.status === 'active' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-slate-800 text-slate-400'}`}>
                    {session.status === 'active' ? <PlayCircle size={22} /> : <Archive size={22} />}
                </div>
                <div>
                    <h3 className="font-mono text-sm font-bold text-slate-200 group-hover:text-indigo-400 transition-colors tracking-tight">{session.id}</h3>
                    <p className="text-[10px] text-slate-600 font-mono tracking-wider">{session.taskId}</p>
                </div>
            </div>
            <div className="text-right">
                <div className="text-emerald-400 font-mono font-bold text-sm">${session.totalCost.toFixed(2)}</div>
            </div>
        </div>

        <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="space-y-1">
                <div className="text-[9px] uppercase tracking-wider text-slate-500 font-bold">Model</div>
                <div className="text-xs text-slate-300 font-mono truncate">{session.model.split('-').slice(0, 2).join(' ')}</div>
            </div>
            <div className="space-y-1 text-right">
                <div className="text-[9px] uppercase tracking-wider text-slate-500 font-bold">Logs</div>
                <div className="text-xs text-slate-300 font-mono">{session.logs.length} pts</div>
            </div>
        </div>

        <div className="pt-4 border-t border-slate-800/60 flex items-center justify-between">
            <div className="flex -space-x-2">
                {Array.from(new Set(session.logs.filter(l => l.speaker === 'agent').map(l => l.agentName || 'Agent'))).slice(0, 3).map((agent, i) => (
                    <div key={i} className="w-7 h-7 rounded-full bg-slate-800 border-2 border-slate-900 flex items-center justify-center text-[10px] text-indigo-400 font-bold group-hover:border-slate-700 transition-colors" title={agent}>
                        {agent[0]}
                    </div>
                ))}
            </div>
            <div className="flex gap-1.5">
                {[...Array(5)].map((_, i) => (
                    <div key={i} className={`w-1.5 h-1.5 rounded-full ${i < (session.qualityRating || 0) ? 'bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.6)]' : 'bg-slate-800'}`} />
                ))}
            </div>
        </div>
    </div>
);