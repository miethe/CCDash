import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Folder, FileText, FolderTree, Search, RefreshCw, ExternalLink, Clock, Users, GitBranch, Link as LinkIcon } from 'lucide-react';
import { useData } from '../contexts/DataContext';
import { CodebaseFileDetail, CodebaseFileSummary, CodebaseTreeNode } from '../types';

const normalizePath = (value: string): string =>
  (value || '').replace(/\\/g, '/').replace(/^\.\/+/, '').replace(/^\/+/, '').trim();

const toEpoch = (value?: string): number => {
  const parsed = Date.parse(value || '');
  return Number.isFinite(parsed) ? parsed : 0;
};

const actionBadge = (action: string): string => {
  const token = action.toLowerCase();
  if (token === 'read') return 'bg-blue-500/10 border-blue-500/30 text-blue-300';
  if (token === 'create') return 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300';
  if (token === 'update') return 'bg-amber-500/10 border-amber-500/30 text-amber-300';
  if (token === 'delete') return 'bg-rose-500/10 border-rose-500/30 text-rose-300';
  return 'bg-slate-700/30 border-slate-600 text-slate-300';
};

const formatAction = (action: string): string =>
  action ? `${action.charAt(0).toUpperCase()}${action.slice(1)}` : 'Unknown';

const TreeNodeItem: React.FC<{
  node: CodebaseTreeNode;
  selectedPath: string;
  onOpenPath: (path: string, nodeType: 'folder' | 'file') => void;
  depth?: number;
}> = ({ node, selectedPath, onOpenPath, depth = 0 }) => {
  const [open, setOpen] = useState(depth < 2);
  const isSelected = selectedPath === node.path;
  const hasChildren = !!node.children && node.children.length > 0;

  return (
    <div>
      <div
        className={`flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors ${
          isSelected ? 'bg-indigo-500/20 text-indigo-200' : 'text-slate-300 hover:bg-slate-800/60'
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={() => {
          if (node.nodeType === 'folder') {
            if (hasChildren) setOpen(prev => !prev);
            onOpenPath(node.path, 'folder');
            return;
          }
          onOpenPath(node.path, 'file');
        }}
      >
        {node.nodeType === 'folder' ? (
          <Folder size={14} className="text-slate-400" />
        ) : (
          <FileText size={14} className="text-slate-500" />
        )}
        <span className="truncate text-xs flex-1">{node.name}</span>
        {node.isTouched && <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />}
      </div>
      {open && hasChildren && node.children!.map(child => (
        <TreeNodeItem
          key={child.path}
          node={child}
          selectedPath={selectedPath}
          onOpenPath={onOpenPath}
          depth={depth + 1}
        />
      ))}
    </div>
  );
};

export const CodebaseExplorer: React.FC = () => {
  const { activeProject } = useData();
  const navigate = useNavigate();

  const [prefix, setPrefix] = useState('');
  const [search, setSearch] = useState('');
  const [includeUntouched, setIncludeUntouched] = useState(false);
  const [actionFilter, setActionFilter] = useState('');
  const [sortBy, setSortBy] = useState<'last_touched' | 'touches' | 'sessions' | 'agents' | 'net_diff' | 'path' | 'file_name'>('last_touched');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [offset, setOffset] = useState(0);
  const [limit] = useState(200);

  const [treeNodes, setTreeNodes] = useState<CodebaseTreeNode[]>([]);
  const [fileItems, setFileItems] = useState<CodebaseFileSummary[]>([]);
  const [totalFiles, setTotalFiles] = useState(0);
  const [selectedFilePath, setSelectedFilePath] = useState('');
  const [selectedDetail, setSelectedDetail] = useState<CodebaseFileDetail | null>(null);

  const [loadingTree, setLoadingTree] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const queryPrefix = normalizePath(prefix);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoadingTree(true);
      try {
        const params = new URLSearchParams({
          prefix: queryPrefix,
          depth: '12',
          include_untouched: includeUntouched ? 'true' : 'false',
          search,
        });
        const res = await fetch(`/api/codebase/tree?${params.toString()}`);
        if (!res.ok) throw new Error(`Tree load failed (${res.status})`);
        const data = await res.json();
        if (!cancelled) setTreeNodes(Array.isArray(data.nodes) ? data.nodes : []);
      } catch (error) {
        if (!cancelled) setTreeNodes([]);
        console.error(error);
      } finally {
        if (!cancelled) setLoadingTree(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [includeUntouched, queryPrefix, search]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoadingFiles(true);
      try {
        const params = new URLSearchParams({
          prefix: queryPrefix,
          search,
          include_untouched: includeUntouched ? 'true' : 'false',
          action: actionFilter,
          feature_id: '',
          sort_by: sortBy,
          sort_order: sortOrder,
          offset: String(offset),
          limit: String(limit),
        });
        const res = await fetch(`/api/codebase/files?${params.toString()}`);
        if (!res.ok) throw new Error(`File list load failed (${res.status})`);
        const data = await res.json();
        if (cancelled) return;
        setFileItems(Array.isArray(data.items) ? data.items : []);
        setTotalFiles(Number(data.total) || 0);
      } catch (error) {
        if (!cancelled) {
          setFileItems([]);
          setTotalFiles(0);
        }
        console.error(error);
      } finally {
        if (!cancelled) setLoadingFiles(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [actionFilter, includeUntouched, limit, offset, queryPrefix, search, sortBy, sortOrder]);

  useEffect(() => {
    let cancelled = false;
    const path = normalizePath(selectedFilePath);
    if (!path) {
      setSelectedDetail(null);
      return;
    }
    const load = async () => {
      setLoadingDetail(true);
      try {
        const encodedPath = path.split('/').map(encodeURIComponent).join('/');
        const res = await fetch(`/api/codebase/files/${encodedPath}?activity_limit=120`);
        if (!res.ok) throw new Error(`Detail load failed (${res.status})`);
        const data = await res.json();
        if (!cancelled) setSelectedDetail(data);
      } catch (error) {
        if (!cancelled) setSelectedDetail(null);
        console.error(error);
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedFilePath]);

  useEffect(() => {
    setOffset(0);
  }, [queryPrefix, search, includeUntouched, actionFilter, sortBy, sortOrder]);

  const breadcrumbs = useMemo(() => queryPrefix.split('/').filter(Boolean), [queryPrefix]);

  const openLocalFile = (path: string) => {
    const projectPath = activeProject?.path || '';
    const normalized = normalizePath(path);
    const localPath = normalized.startsWith('/') ? normalized : `${projectPath.replace(/\/+$/, '')}/${normalized}`;
    window.location.href = `vscode://file/${encodeURI(localPath)}`;
  };

  return (
    <div className="h-full flex flex-col">
      <div className="mb-6 flex items-center justify-between gap-6">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">Codebase Explorer</h2>
          <p className="text-sm text-slate-400">File-level activity intelligence across sessions, features, and documents.</p>
        </div>
        <div className="text-xs text-slate-500 font-mono">
          Root: {activeProject?.path || '(none)'}
        </div>
      </div>

      <div className="mb-4 grid grid-cols-1 lg:grid-cols-[1fr_auto_auto_auto_auto] gap-3">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder="Search files..."
            className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
          />
        </div>
        <select
          value={actionFilter}
          onChange={event => setActionFilter(event.target.value)}
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200"
        >
          <option value="">All actions</option>
          <option value="read">Read</option>
          <option value="create">Create</option>
          <option value="update">Update</option>
          <option value="delete">Delete</option>
        </select>
        <select
          value={sortBy}
          onChange={event => setSortBy(event.target.value as any)}
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200"
        >
          <option value="last_touched">Last touched</option>
          <option value="touches">Touches</option>
          <option value="sessions">Sessions</option>
          <option value="agents">Agents</option>
          <option value="net_diff">Net diff</option>
          <option value="path">Path</option>
          <option value="file_name">File name</option>
        </select>
        <button
          onClick={() => setSortOrder(prev => (prev === 'desc' ? 'asc' : 'desc'))}
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 hover:border-indigo-500"
        >
          {sortOrder.toUpperCase()}
        </button>
        <label className="inline-flex items-center gap-2 text-xs text-slate-300 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2">
          <input
            type="checkbox"
            checked={includeUntouched}
            onChange={event => setIncludeUntouched(event.target.checked)}
          />
          Include untouched
        </label>
      </div>

      <div className="h-full min-h-0 grid grid-cols-1 xl:grid-cols-[300px_1fr_420px] gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col min-h-0">
          <div className="px-3 py-2 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <FolderTree size={14} /> Tree
            </div>
            {loadingTree && <RefreshCw size={12} className="animate-spin text-slate-500" />}
          </div>
          <div className="px-2 py-2 border-b border-slate-800 flex items-center gap-1 text-[11px]">
            <button
              onClick={() => setPrefix('')}
              className="px-2 py-1 rounded border border-slate-700 text-slate-300 hover:border-indigo-500/40"
            >
              .
            </button>
            {breadcrumbs.map((segment, idx) => {
              const path = breadcrumbs.slice(0, idx + 1).join('/');
              return (
                <button
                  key={path}
                  onClick={() => setPrefix(path)}
                  className="px-2 py-1 rounded border border-slate-700 text-slate-300 hover:border-indigo-500/40"
                >
                  {segment}
                </button>
              );
            })}
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-1">
            {treeNodes.map(node => (
              <TreeNodeItem
                key={node.path}
                node={node}
                selectedPath={selectedFilePath}
                onOpenPath={(path, nodeType) => {
                  if (nodeType === 'folder') {
                    setPrefix(path);
                  } else {
                    setSelectedFilePath(path);
                  }
                }}
              />
            ))}
            {!loadingTree && treeNodes.length === 0 && (
              <div className="text-xs text-slate-500 px-2 py-4">No files match this view.</div>
            )}
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col min-h-0">
          <div className="px-3 py-2 border-b border-slate-800 flex items-center justify-between">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400">Files ({totalFiles})</div>
            {loadingFiles && <RefreshCw size={12} className="animate-spin text-slate-500" />}
          </div>
          <div className="grid grid-cols-[1.4fr_1fr_80px_80px_80px_130px_90px] gap-2 px-3 py-2 border-b border-slate-800 bg-slate-950/60 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            <div>File</div>
            <div>Actions</div>
            <div>Tch</div>
            <div>Ses</div>
            <div>Agt</div>
            <div>Last</div>
            <div>Diff</div>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto">
            {fileItems.map(item => (
              <button
                key={item.filePath}
                onClick={() => setSelectedFilePath(item.filePath)}
                className={`w-full text-left grid grid-cols-[1.4fr_1fr_80px_80px_80px_130px_90px] gap-2 px-3 py-2 border-b border-slate-800/70 text-xs hover:bg-slate-800/40 transition-colors ${
                  selectedFilePath === item.filePath ? 'bg-indigo-500/10' : ''
                }`}
              >
                <div className="truncate">
                  <div className="text-slate-200 font-medium truncate">{item.fileName}</div>
                  <div className="text-[10px] text-slate-500 font-mono truncate">{item.filePath}</div>
                </div>
                <div className="flex flex-wrap gap-1">
                  {item.actions.map(action => (
                    <span key={`${item.filePath}-${action}`} className={`inline-flex text-[10px] rounded border px-1.5 py-0.5 ${actionBadge(action)}`}>
                      {formatAction(action)}
                    </span>
                  ))}
                </div>
                <div className="text-slate-300">{item.touchCount}</div>
                <div className="text-slate-300">{item.sessionCount}</div>
                <div className="text-slate-300">{item.agentCount}</div>
                <div className="text-slate-400 text-[11px]">{item.lastTouchedAt ? new Date(item.lastTouchedAt).toLocaleString() : '—'}</div>
                <div className="font-mono text-[11px]">
                  <span className={item.netDiff >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                    {item.netDiff >= 0 ? '+' : ''}{item.netDiff}
                  </span>
                </div>
              </button>
            ))}
            {!loadingFiles && fileItems.length === 0 && (
              <div className="text-xs text-slate-500 px-4 py-6">No files in this scope.</div>
            )}
          </div>
          <div className="px-3 py-2 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
            <span>
              Showing {Math.min(offset + 1, totalFiles)}-{Math.min(offset + fileItems.length, totalFiles)} of {totalFiles}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setOffset(prev => Math.max(0, prev - limit))}
                disabled={offset === 0}
                className="px-2 py-1 rounded border border-slate-700 disabled:opacity-40"
              >
                Prev
              </button>
              <button
                onClick={() => setOffset(prev => prev + limit)}
                disabled={offset + limit >= totalFiles}
                className="px-2 py-1 rounded border border-slate-700 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden flex flex-col min-h-0">
          <div className="px-3 py-2 border-b border-slate-800 flex items-center justify-between">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400">Detail</div>
            {loadingDetail && <RefreshCw size={12} className="animate-spin text-slate-500" />}
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-4">
            {!selectedDetail && (
              <div className="text-xs text-slate-500">Select a file to view activity, sessions, features, and linked docs.</div>
            )}

            {selectedDetail && (
              <>
                <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                  <div className="text-sm text-slate-100 font-semibold">{selectedDetail.fileName}</div>
                  <div className="text-[11px] text-slate-500 font-mono mt-1 break-all">{selectedDetail.filePath}</div>
                  <div className="mt-2 flex items-center gap-2">
                    <button
                      onClick={() => openLocalFile(selectedDetail.filePath)}
                      className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-indigo-500/30 bg-indigo-500/10 text-indigo-300"
                    >
                      <ExternalLink size={12} /> Open
                    </button>
                    <span className="text-[11px] text-slate-500">{selectedDetail.touchCount} touches</span>
                  </div>
                </div>

                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
                    <GitBranch size={12} /> Features
                  </div>
                  <div className="space-y-2">
                    {selectedDetail.features.map(feature => (
                      <button
                        key={feature.featureId}
                        onClick={() => navigate(`/board?feature=${encodeURIComponent(feature.featureId)}`)}
                        className="w-full text-left rounded-lg border border-slate-800 bg-slate-950/60 p-2 hover:border-indigo-500/40"
                      >
                        <div className="text-xs text-slate-200">{feature.featureName}</div>
                        <div className="text-[10px] text-slate-500 mt-1">
                          {feature.involvementLevel} · score {feature.score.toFixed(2)}
                        </div>
                      </button>
                    ))}
                    {selectedDetail.features.length === 0 && <div className="text-xs text-slate-500">No feature links.</div>}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
                    <Users size={12} /> Sessions
                  </div>
                  <div className="space-y-2">
                    {selectedDetail.sessions.map(session => (
                      <button
                        key={session.sessionId}
                        onClick={() => navigate(`/sessions?session=${encodeURIComponent(session.sessionId)}`)}
                        className="w-full text-left rounded-lg border border-slate-800 bg-slate-950/60 p-2 hover:border-indigo-500/40"
                      >
                        <div className="text-xs text-indigo-300 font-mono">{session.sessionId}</div>
                        <div className="text-[10px] text-slate-500 mt-1">{session.touchCount} touches · {session.actions.join(', ')}</div>
                      </button>
                    ))}
                    {selectedDetail.sessions.length === 0 && <div className="text-xs text-slate-500">No session activity.</div>}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
                    <LinkIcon size={12} /> Documents
                  </div>
                  <div className="space-y-2">
                    {selectedDetail.documents.map(doc => (
                      <button
                        key={`${doc.documentId}:${doc.relation}`}
                        onClick={() => navigate(`/plans?doc=${encodeURIComponent(doc.documentId)}`)}
                        className="w-full text-left rounded-lg border border-slate-800 bg-slate-950/60 p-2 hover:border-indigo-500/40"
                      >
                        <div className="text-xs text-slate-200">{doc.title}</div>
                        <div className="text-[10px] text-slate-500 mt-1">{doc.relation} · {doc.docType || 'document'}</div>
                      </button>
                    ))}
                    {selectedDetail.documents.length === 0 && <div className="text-xs text-slate-500">No linked documents.</div>}
                  </div>
                </div>

                <div>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
                    <Clock size={12} /> Activity
                  </div>
                  <div className="space-y-2">
                    {selectedDetail.activity.map(entry => (
                      <div key={entry.id} className="rounded-lg border border-slate-800 bg-slate-950/60 p-2">
                        <div className="text-[11px] text-slate-200">
                          {formatAction(entry.action || '')} · {entry.sourceToolName || entry.logType || 'event'}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-1">
                          {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : '—'} · {entry.sessionId || ''}
                        </div>
                      </div>
                    ))}
                    {selectedDetail.activity.length === 0 && <div className="text-xs text-slate-500">No recent activity.</div>}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
