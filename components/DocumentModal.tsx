import React from 'react';
import { PlanDocument } from '../types';
import {
   ArrowLeft,
   FileText,
   FolderTree,
   Link2,
   ListTodo,
   Terminal,
   User,
   X,
} from 'lucide-react';
import { useData } from '../contexts/DataContext';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getFeatureStatusStyle } from './featureStatus';
import { updateDocument as saveDocument } from '../services/documents';

export const getFileContent = (doc: PlanDocument): string => {
   if (doc.content) return doc.content;
   return `# ${doc.title}

> **Status**: ${doc.status.toUpperCase()}
> **Path**: ${doc.filePath}

_Content preview not available for this document yet._`;
};

interface DocumentLinkFeature {
   id: string;
   name: string;
   status: string;
   category: string;
}

interface DocumentLinkTask {
   id: string;
   title: string;
   status: string;
   sourceFile: string;
   sessionId?: string;
   featureId?: string;
   phaseId?: string;
}

interface DocumentLinkSession {
   id: string;
   status: string;
   model: string;
   startedAt: string;
   totalCost: number;
}

interface DocumentLinkDocument {
   id: string;
   title: string;
   filePath: string;
   canonicalPath: string;
   docType: string;
   docSubtype: string;
}

interface DocumentLinksResponse {
   documentId: string;
   features: DocumentLinkFeature[];
   tasks: DocumentLinkTask[];
   sessions: DocumentLinkSession[];
   documents: DocumentLinkDocument[];
}

interface DocumentModalProps {
   doc: PlanDocument;
   onClose: () => void;
   onBack?: () => void;
   backLabel?: string;
   zIndexClassName?: string;
}

const normalizeDoc = (raw: Partial<PlanDocument>, fallback: PlanDocument): PlanDocument => ({
   id: String(raw.id || fallback.id || ''),
   title: String(raw.title || fallback.title || ''),
   filePath: String(raw.filePath || fallback.filePath || ''),
   canonicalPath: String(raw.canonicalPath || fallback.canonicalPath || raw.filePath || fallback.filePath || ''),
   status: String(raw.status || fallback.status || 'active'),
   statusNormalized: String(raw.statusNormalized || fallback.statusNormalized || ''),
   createdAt: String(raw.createdAt || fallback.createdAt || ''),
   updatedAt: String(raw.updatedAt || fallback.updatedAt || ''),
   completedAt: String(raw.completedAt || fallback.completedAt || ''),
   lastModified: String(raw.lastModified || fallback.lastModified || ''),
   author: String(raw.author || fallback.author || ''),
   content: typeof raw.content === 'string' ? raw.content : fallback.content,
   docType: raw.docType || fallback.docType,
   docSubtype: raw.docSubtype || fallback.docSubtype,
   rootKind: raw.rootKind || fallback.rootKind,
   hasFrontmatter: typeof raw.hasFrontmatter === 'boolean' ? raw.hasFrontmatter : fallback.hasFrontmatter,
   frontmatterType: raw.frontmatterType || fallback.frontmatterType,
   featureSlugHint: raw.featureSlugHint || fallback.featureSlugHint,
   featureSlugCanonical: raw.featureSlugCanonical || fallback.featureSlugCanonical,
   prdRef: raw.prdRef || fallback.prdRef,
   phaseToken: raw.phaseToken || fallback.phaseToken,
   phaseNumber: raw.phaseNumber ?? fallback.phaseNumber,
   overallProgress: raw.overallProgress ?? fallback.overallProgress,
   completionEstimate: raw.completionEstimate ?? fallback.completionEstimate,
   description: raw.description ?? fallback.description,
   summary: raw.summary ?? fallback.summary,
   priority: raw.priority ?? fallback.priority,
   riskLevel: raw.riskLevel ?? fallback.riskLevel,
   complexity: raw.complexity ?? fallback.complexity,
   track: raw.track ?? fallback.track,
   timelineEstimate: raw.timelineEstimate ?? fallback.timelineEstimate,
   targetRelease: raw.targetRelease ?? fallback.targetRelease,
   milestone: raw.milestone ?? fallback.milestone,
   decisionStatus: raw.decisionStatus ?? fallback.decisionStatus,
   executionReadiness: raw.executionReadiness ?? fallback.executionReadiness,
   testImpact: raw.testImpact ?? fallback.testImpact,
   primaryDocRole: raw.primaryDocRole ?? fallback.primaryDocRole,
   featureSlug: raw.featureSlug ?? fallback.featureSlug,
   featureFamily: raw.featureFamily ?? fallback.featureFamily,
   featureVersion: raw.featureVersion ?? fallback.featureVersion,
   planRef: raw.planRef ?? fallback.planRef,
   implementationPlanRef: raw.implementationPlanRef ?? fallback.implementationPlanRef,
   totalTasks: raw.totalTasks ?? fallback.totalTasks ?? 0,
   completedTasks: raw.completedTasks ?? fallback.completedTasks ?? 0,
   inProgressTasks: raw.inProgressTasks ?? fallback.inProgressTasks ?? 0,
   blockedTasks: raw.blockedTasks ?? fallback.blockedTasks ?? 0,
   category: raw.category || fallback.category,
   pathSegments: Array.isArray(raw.pathSegments) ? raw.pathSegments : (fallback.pathSegments || []),
   featureCandidates: Array.isArray(raw.featureCandidates) ? raw.featureCandidates : (fallback.featureCandidates || []),
   metadata: {
      phase: raw.metadata?.phase ?? fallback.metadata?.phase ?? '',
      phaseNumber: raw.metadata?.phaseNumber ?? fallback.metadata?.phaseNumber,
      overallProgress: raw.metadata?.overallProgress ?? fallback.metadata?.overallProgress,
      taskCounts: raw.metadata?.taskCounts ?? fallback.metadata?.taskCounts ?? {
         total: raw.totalTasks ?? fallback.totalTasks ?? 0,
         completed: raw.completedTasks ?? fallback.completedTasks ?? 0,
         inProgress: raw.inProgressTasks ?? fallback.inProgressTasks ?? 0,
         blocked: raw.blockedTasks ?? fallback.blockedTasks ?? 0,
      },
      owners: raw.metadata?.owners ?? fallback.metadata?.owners ?? [],
      contributors: raw.metadata?.contributors ?? fallback.metadata?.contributors ?? [],
      reviewers: raw.metadata?.reviewers ?? fallback.metadata?.reviewers ?? [],
      approvers: raw.metadata?.approvers ?? fallback.metadata?.approvers ?? [],
      audience: raw.metadata?.audience ?? fallback.metadata?.audience ?? [],
      labels: raw.metadata?.labels ?? fallback.metadata?.labels ?? [],
      description: raw.metadata?.description ?? fallback.metadata?.description ?? '',
      summary: raw.metadata?.summary ?? fallback.metadata?.summary ?? '',
      priority: raw.metadata?.priority ?? fallback.metadata?.priority ?? '',
      riskLevel: raw.metadata?.riskLevel ?? fallback.metadata?.riskLevel ?? '',
      complexity: raw.metadata?.complexity ?? fallback.metadata?.complexity ?? '',
      track: raw.metadata?.track ?? fallback.metadata?.track ?? '',
      timelineEstimate: raw.metadata?.timelineEstimate ?? fallback.metadata?.timelineEstimate ?? '',
      targetRelease: raw.metadata?.targetRelease ?? fallback.metadata?.targetRelease ?? '',
      milestone: raw.metadata?.milestone ?? fallback.metadata?.milestone ?? '',
      decisionStatus: raw.metadata?.decisionStatus ?? fallback.metadata?.decisionStatus ?? '',
      executionReadiness: raw.metadata?.executionReadiness ?? fallback.metadata?.executionReadiness ?? '',
      testImpact: raw.metadata?.testImpact ?? fallback.metadata?.testImpact ?? '',
      planRef: raw.metadata?.planRef ?? fallback.metadata?.planRef ?? '',
      implementationPlanRef: raw.metadata?.implementationPlanRef ?? fallback.metadata?.implementationPlanRef ?? '',
      requestLogIds: raw.metadata?.requestLogIds ?? fallback.metadata?.requestLogIds ?? [],
      commitRefs: raw.metadata?.commitRefs ?? fallback.metadata?.commitRefs ?? [],
      prRefs: raw.metadata?.prRefs ?? fallback.metadata?.prRefs ?? [],
      sourceDocuments: raw.metadata?.sourceDocuments ?? fallback.metadata?.sourceDocuments ?? [],
      filesAffected: raw.metadata?.filesAffected ?? fallback.metadata?.filesAffected ?? [],
      filesModified: raw.metadata?.filesModified ?? fallback.metadata?.filesModified ?? [],
      contextFiles: raw.metadata?.contextFiles ?? fallback.metadata?.contextFiles ?? [],
      integritySignalRefs: raw.metadata?.integritySignalRefs ?? fallback.metadata?.integritySignalRefs ?? [],
      linkedTasks: raw.metadata?.linkedTasks ?? fallback.metadata?.linkedTasks ?? [],
      executionEntrypoints: raw.metadata?.executionEntrypoints ?? fallback.metadata?.executionEntrypoints ?? [],
      linkedFeatureRefs: raw.metadata?.linkedFeatureRefs ?? fallback.metadata?.linkedFeatureRefs ?? [],
      docTypeFields: raw.metadata?.docTypeFields ?? fallback.metadata?.docTypeFields ?? {},
      featureSlugHint: raw.metadata?.featureSlugHint ?? fallback.metadata?.featureSlugHint ?? '',
      canonicalPath: raw.metadata?.canonicalPath ?? fallback.metadata?.canonicalPath ?? '',
   },
   linkCounts: {
      features: raw.linkCounts?.features ?? fallback.linkCounts?.features ?? 0,
      tasks: raw.linkCounts?.tasks ?? fallback.linkCounts?.tasks ?? 0,
      sessions: raw.linkCounts?.sessions ?? fallback.linkCounts?.sessions ?? 0,
      documents: raw.linkCounts?.documents ?? fallback.linkCounts?.documents ?? 0,
   },
   dates: raw.dates ?? fallback.dates,
   timeline: Array.isArray(raw.timeline) ? raw.timeline : (fallback.timeline || []),
   frontmatter: {
      tags: Array.isArray(raw.frontmatter?.tags) ? raw.frontmatter.tags : (fallback.frontmatter?.tags || []),
      linkedFeatures: Array.isArray(raw.frontmatter?.linkedFeatures) ? raw.frontmatter.linkedFeatures : (fallback.frontmatter?.linkedFeatures || []),
      linkedFeatureRefs: Array.isArray(raw.frontmatter?.linkedFeatureRefs) ? raw.frontmatter.linkedFeatureRefs : (fallback.frontmatter?.linkedFeatureRefs || []),
      linkedSessions: Array.isArray(raw.frontmatter?.linkedSessions) ? raw.frontmatter.linkedSessions : (fallback.frontmatter?.linkedSessions || []),
      linkedTasks: Array.isArray(raw.frontmatter?.linkedTasks) ? raw.frontmatter.linkedTasks : (fallback.frontmatter?.linkedTasks || []),
      lineageFamily: raw.frontmatter?.lineageFamily ?? fallback.frontmatter?.lineageFamily,
      lineageParent: raw.frontmatter?.lineageParent ?? fallback.frontmatter?.lineageParent,
      lineageChildren: Array.isArray(raw.frontmatter?.lineageChildren) ? raw.frontmatter.lineageChildren : (fallback.frontmatter?.lineageChildren || []),
      lineageType: raw.frontmatter?.lineageType ?? fallback.frontmatter?.lineageType,
      relatedFiles: Array.isArray(raw.frontmatter?.relatedFiles) ? raw.frontmatter.relatedFiles : (fallback.frontmatter?.relatedFiles || []),
      version: raw.frontmatter?.version ?? fallback.frontmatter?.version,
      commits: Array.isArray(raw.frontmatter?.commits) ? raw.frontmatter.commits : (fallback.frontmatter?.commits || []),
      prs: Array.isArray(raw.frontmatter?.prs) ? raw.frontmatter.prs : (fallback.frontmatter?.prs || []),
      requestLogIds: Array.isArray(raw.frontmatter?.requestLogIds) ? raw.frontmatter.requestLogIds : (fallback.frontmatter?.requestLogIds || []),
      commitRefs: Array.isArray(raw.frontmatter?.commitRefs) ? raw.frontmatter.commitRefs : (fallback.frontmatter?.commitRefs || []),
      prRefs: Array.isArray(raw.frontmatter?.prRefs) ? raw.frontmatter.prRefs : (fallback.frontmatter?.prRefs || []),
      relatedRefs: Array.isArray(raw.frontmatter?.relatedRefs) ? raw.frontmatter.relatedRefs : (fallback.frontmatter?.relatedRefs || []),
      pathRefs: Array.isArray(raw.frontmatter?.pathRefs) ? raw.frontmatter.pathRefs : (fallback.frontmatter?.pathRefs || []),
      slugRefs: Array.isArray(raw.frontmatter?.slugRefs) ? raw.frontmatter.slugRefs : (fallback.frontmatter?.slugRefs || []),
      prd: raw.frontmatter?.prd ?? fallback.frontmatter?.prd,
      prdRefs: Array.isArray(raw.frontmatter?.prdRefs) ? raw.frontmatter.prdRefs : (fallback.frontmatter?.prdRefs || []),
      sourceDocuments: Array.isArray(raw.frontmatter?.sourceDocuments) ? raw.frontmatter.sourceDocuments : (fallback.frontmatter?.sourceDocuments || []),
      filesAffected: Array.isArray(raw.frontmatter?.filesAffected) ? raw.frontmatter.filesAffected : (fallback.frontmatter?.filesAffected || []),
      filesModified: Array.isArray(raw.frontmatter?.filesModified) ? raw.frontmatter.filesModified : (fallback.frontmatter?.filesModified || []),
      contextFiles: Array.isArray(raw.frontmatter?.contextFiles) ? raw.frontmatter.contextFiles : (fallback.frontmatter?.contextFiles || []),
      integritySignalRefs: Array.isArray(raw.frontmatter?.integritySignalRefs) ? raw.frontmatter.integritySignalRefs : (fallback.frontmatter?.integritySignalRefs || []),
      fieldKeys: Array.isArray(raw.frontmatter?.fieldKeys) ? raw.frontmatter.fieldKeys : (fallback.frontmatter?.fieldKeys || []),
      raw: raw.frontmatter?.raw ?? fallback.frontmatter?.raw,
   },
});

export const DocumentModal = ({
   doc: initialDoc,
   onClose,
   onBack,
   backLabel = 'Back',
   zIndexClassName = 'z-50',
}: DocumentModalProps) => {
   const navigate = useNavigate();
   const { sessions, features, refreshDocuments } = useData();
   const [activeTab, setActiveTab] = React.useState<'summary' | 'delivery' | 'relationships' | 'content' | 'timeline' | 'raw'>('summary');
   const [fullDoc, setFullDoc] = React.useState<PlanDocument>(() => normalizeDoc(initialDoc, initialDoc));
   const [links, setLinks] = React.useState<DocumentLinksResponse | null>(null);
   const [isEditing, setIsEditing] = React.useState(false);
   const [draftContent, setDraftContent] = React.useState(() => getFileContent(initialDoc));
   const [commitMessage, setCommitMessage] = React.useState('');
   const [saveBusy, setSaveBusy] = React.useState(false);
   const [saveError, setSaveError] = React.useState<string | null>(null);
   const [saveMessage, setSaveMessage] = React.useState<string | null>(null);

   React.useEffect(() => {
      let cancelled = false;
      const docId = (initialDoc.id || '').trim();
      if (!docId) {
         setFullDoc(normalizeDoc(initialDoc, initialDoc));
         setLinks(null);
         return () => {
            cancelled = true;
         };
      }

      Promise.all([
         fetch(`/api/documents/${encodeURIComponent(docId)}`),
         fetch(`/api/documents/${encodeURIComponent(docId)}/links`),
      ])
         .then(async ([docRes, linksRes]) => {
            if (!docRes.ok) throw new Error(`Failed to fetch document (${docRes.status})`);
            const docPayload = await docRes.json();
            const linksPayload = linksRes.ok ? await linksRes.json() : null;
            if (cancelled) return;
            setFullDoc(normalizeDoc((docPayload || {}) as Partial<PlanDocument>, initialDoc));
            if (linksPayload && typeof linksPayload === 'object') {
               setLinks({
                  documentId: String(linksPayload.documentId || docId),
                  features: Array.isArray(linksPayload.features) ? linksPayload.features : [],
                  tasks: Array.isArray(linksPayload.tasks) ? linksPayload.tasks : [],
                  sessions: Array.isArray(linksPayload.sessions) ? linksPayload.sessions : [],
                  documents: Array.isArray(linksPayload.documents) ? linksPayload.documents : [],
               });
            } else {
               setLinks(null);
            }
         })
         .catch(() => {
            if (cancelled) return;
            setFullDoc(normalizeDoc(initialDoc, initialDoc));
            setLinks(null);
         });

      return () => {
         cancelled = true;
      };
   }, [initialDoc.id]);

   const doc = normalizeDoc(fullDoc || initialDoc, initialDoc);
   const canEditDocument = doc.rootKind === 'project_plans';
   const currentContent = getFileContent(doc);
   const hasUnsavedChanges = draftContent !== currentContent;
   const isProgressDoc = doc.rootKind === 'progress' || (doc.docSubtype || '').startsWith('progress_');

   React.useEffect(() => {
      if (isEditing) return;
      setDraftContent(currentContent);
   }, [currentContent, isEditing]);

   React.useEffect(() => {
      setIsEditing(false);
      setCommitMessage('');
      setSaveError(null);
      setSaveMessage(null);
   }, [doc.id]);

   const handleStartEdit = React.useCallback(() => {
      setActiveTab('content');
      setDraftContent(currentContent);
      setSaveError(null);
      setSaveMessage(null);
      setIsEditing(true);
   }, [currentContent]);

   const handleCancelEdit = React.useCallback(() => {
      setDraftContent(currentContent);
      setCommitMessage('');
      setSaveError(null);
      setIsEditing(false);
   }, [currentContent]);

   const handleSave = React.useCallback(async () => {
      setSaveBusy(true);
      setSaveError(null);
      setSaveMessage(null);
      try {
         const response = await saveDocument(doc.id, {
            content: draftContent,
            commitMessage,
         });
         const nextDoc = normalizeDoc(response.document, doc);
         setFullDoc(nextDoc);
         setDraftContent(getFileContent(nextDoc));
         setCommitMessage('');
         setSaveMessage(response.commitHash
            ? `${response.message} Commit ${response.commitHash}.`
            : response.message);
         setIsEditing(false);
         await refreshDocuments();
      } catch (error: any) {
         setSaveError(error?.message || 'Failed to save document');
      } finally {
         setSaveBusy(false);
      }
   }, [commitMessage, doc, draftContent, refreshDocuments]);
   const linkedFeatures = React.useMemo(() => {
      const featureById = new Map<string, { id: string; name: string; status: string; category: string }>();
      features.forEach(feature => {
         featureById.set(feature.id.toLowerCase(), {
            id: feature.id,
            name: feature.name,
            status: feature.status,
            category: feature.category,
         });
      });

      const merged = new Map<string, DocumentLinkFeature>();
      (links?.features || []).forEach(feature => {
         const matched = featureById.get((feature.id || '').toLowerCase());
         const resolvedId = matched?.id || feature.id;
         if (!resolvedId) return;
         merged.set(resolvedId, {
            id: resolvedId,
            name: feature.name || matched?.name || resolvedId,
            status: feature.status || matched?.status || 'backlog',
            category: feature.category || matched?.category || '',
         });
      });

      (doc.frontmatter.linkedFeatures || []).forEach(ref => {
         const matched = featureById.get((ref || '').toLowerCase());
         const resolvedId = matched?.id || ref;
         if (!resolvedId || merged.has(resolvedId)) return;
         merged.set(resolvedId, {
            id: resolvedId,
            name: matched?.name || resolvedId,
            status: matched?.status || 'backlog',
            category: matched?.category || '',
         });
      });

      return Array.from(merged.values());
   }, [features, links?.features, doc.frontmatter.linkedFeatures]);
   const linkedTasks = links?.tasks || [];
   const linkedSessions = React.useMemo(() => {
      if (links?.sessions && links.sessions.length > 0) return links.sessions;
      const fallbackIds = doc.frontmatter.linkedSessions || [];
      return fallbackIds
         .map(id => sessions.find(s => s.id === id))
         .filter(Boolean)
         .map(session => ({
            id: session!.id,
            status: session!.status,
            model: session!.model,
            startedAt: session!.startedAt,
            totalCost: session!.totalCost,
         }));
   }, [links?.sessions, doc.frontmatter.linkedSessions, sessions]);
   const linkedDocs = links?.documents || [];
   const taskCounts = doc.metadata?.taskCounts || {
      total: doc.totalTasks || 0,
      completed: doc.completedTasks || 0,
      inProgress: doc.inProgressTasks || 0,
      blocked: doc.blockedTasks || 0,
   };
   const formatDate = (value?: string): string => {
      if (!value) return '-';
      const parsed = Date.parse(value);
      if (Number.isNaN(parsed)) return value;
      return new Date(parsed).toLocaleDateString();
   };
   const dateChip = (key: keyof NonNullable<PlanDocument['dates']>) => {
      const value = doc.dates?.[key];
      if (!value?.value) return '';
      const confidence = value.confidence ? ` (${value.confidence})` : '';
      return `${formatDate(value.value)}${confidence}`;
   };
   const timelineEvents = React.useMemo(() => {
      const fromTimeline = Array.isArray(doc.timeline) ? doc.timeline : [];
      if (fromTimeline.length > 0) {
         return [...fromTimeline].sort((a, b) => Date.parse(b.timestamp || '') - Date.parse(a.timestamp || ''));
      }
      return [
         doc.dates?.updatedAt?.value ? {
            id: 'doc-updated',
            timestamp: doc.dates.updatedAt.value,
            label: 'Updated',
            kind: 'updated',
            confidence: doc.dates.updatedAt.confidence,
            source: doc.dates.updatedAt.source,
            description: doc.dates.updatedAt.reason,
         } : null,
         doc.dates?.createdAt?.value ? {
            id: 'doc-created',
            timestamp: doc.dates.createdAt.value,
            label: 'Created',
            kind: 'created',
            confidence: doc.dates.createdAt.confidence,
            source: doc.dates.createdAt.source,
            description: doc.dates.createdAt.reason,
         } : null,
         doc.dates?.completedAt?.value ? {
            id: 'doc-completed',
            timestamp: doc.dates.completedAt.value,
            label: 'Completed',
            kind: 'completed',
            confidence: doc.dates.completedAt.confidence,
            source: doc.dates.completedAt.source,
            description: doc.dates.completedAt.reason,
         } : null,
      ].filter(Boolean);
   }, [doc.timeline, doc.dates]);

   return (
      <div className={`fixed inset-0 ${zIndexClassName} flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200`} onClick={onClose}>
         <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-5xl h-[85vh] flex flex-col shadow-2xl overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="p-6 border-b border-slate-800 flex justify-between items-start bg-slate-900">
               <div className="flex items-start gap-3 min-w-0">
                  {onBack && (
                     <button
                        onClick={onBack}
                        className="mt-0.5 p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                        title={backLabel}
                        aria-label={backLabel}
                     >
                        <ArrowLeft size={16} />
                     </button>
                  )}
                  <div className="min-w-0">
                     <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <span className="font-mono text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">{doc.id}</span>
                        <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-300">{doc.status}</span>
                        {doc.docType && <span className="text-[10px] uppercase px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">{doc.docType}</span>}
                        {doc.docSubtype && <span className="text-[10px] uppercase px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20">{doc.docSubtype}</span>}
                        {doc.rootKind && <span className="text-[10px] uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">{doc.rootKind}</span>}
                        {linkedFeatures.slice(0, 3).map(feature => {
                           const style = getFeatureStatusStyle(feature.status);
                           return (
                              <button
                                 key={feature.id}
                                 type="button"
                                 onClick={() => { onClose(); navigate(`/board?feature=${encodeURIComponent(feature.id)}`); }}
                                 className={`text-[10px] font-semibold rounded-full border px-2 py-0.5 transition-colors ${style.badge}`}
                                 title={`Open Feature ${feature.id} (${style.label})`}
                              >
                                 {feature.id}
                              </button>
                           );
                        })}
                        {linkedFeatures.length > 3 && (
                           <span className="text-[10px] rounded-full border border-slate-700 bg-slate-800 px-2 py-0.5 text-slate-300">
                              +{linkedFeatures.length - 3} features
                           </span>
                        )}
                     </div>
                     <h2 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
                        <FileText className="text-slate-400" /> {doc.title}
                     </h2>
                     <p className="text-slate-400 font-mono text-xs mt-1">{doc.canonicalPath || doc.filePath}</p>
                  </div>
               </div>
               <div className="flex items-center gap-2">
                  {canEditDocument && !isEditing && (
                     <button
                        type="button"
                        onClick={handleStartEdit}
                        className="rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-3 py-2 text-xs font-semibold text-indigo-200 hover:bg-indigo-500/20"
                     >
                        Edit Markdown
                     </button>
                  )}
                  {canEditDocument && isEditing && (
                     <>
                        <button
                           type="button"
                           onClick={handleCancelEdit}
                           disabled={saveBusy}
                           className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200 hover:border-slate-600 disabled:opacity-50"
                        >
                           Cancel
                        </button>
                        <button
                           type="button"
                           onClick={() => { void handleSave(); }}
                           disabled={saveBusy || !hasUnsavedChanges}
                           className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
                        >
                           {saveBusy ? 'Saving...' : 'Save'}
                        </button>
                     </>
                  )}
                  <button onClick={onClose} className="text-slate-500 hover:text-slate-200 transition-colors p-1 hover:bg-slate-800 rounded">
                     <X size={24} />
                  </button>
               </div>
            </div>

            <div className="px-6 border-b border-slate-800 bg-slate-900/50 flex gap-6">
               {[
                  { id: 'summary', label: 'Summary' },
                  { id: 'delivery', label: 'Delivery' },
                  { id: 'relationships', label: 'Relationships', count: linkedFeatures.length + linkedTasks.length + linkedSessions.length + linkedDocs.length },
                  { id: 'content', label: 'Content' },
                  { id: 'timeline', label: 'Timeline', count: timelineEvents.length },
                  { id: 'raw', label: 'Raw' },
               ].map(tab => (
                  <button
                     key={tab.id}
                     onClick={() => setActiveTab(tab.id as typeof activeTab)}
                     className={`flex items-center gap-2 py-4 text-sm font-medium border-b-2 transition-colors ${
                        activeTab === tab.id
                           ? 'border-indigo-500 text-indigo-400'
                           : 'border-transparent text-slate-500 hover:text-slate-300 hover:border-slate-700'
                     }`}
                  >
                     {tab.label}
                     {tab.count !== undefined && tab.count > 0 && (
                        <span className="bg-slate-800 text-slate-400 text-[10px] px-1.5 py-0.5 rounded-full">{tab.count}</span>
                     )}
                  </button>
               ))}
            </div>

            <div className="flex-1 overflow-y-auto p-6 bg-slate-950/30">
               {saveMessage && (
                  <div className="mb-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
                     {saveMessage}
                  </div>
               )}
               {saveError && (
                  <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                     {saveError}
                  </div>
               )}

               {activeTab === 'summary' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                     <div className="space-y-4">
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                           <h3 className="text-sm font-semibold text-slate-200 mb-3">Identity & Lifecycle</h3>
                           <div className="space-y-2 text-sm">
                              <div className="flex justify-between text-slate-400"><span>Type</span><span className="text-slate-200">{doc.docType || '-'}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Subtype</span><span className="text-slate-200">{doc.docSubtype || '-'}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Status</span><span className="text-slate-200">{doc.statusNormalized || doc.status}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Created</span><span className="text-slate-200">{dateChip('createdAt') || formatDate(doc.createdAt)}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Updated</span><span className="text-slate-200">{dateChip('updatedAt') || formatDate(doc.updatedAt || doc.lastModified)}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Completed</span><span className="text-slate-200">{dateChip('completedAt') || formatDate(doc.completedAt)}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Canonical Path</span><span className="text-slate-200 font-mono text-xs">{doc.canonicalPath || doc.filePath}</span></div>
                           </div>
                        </div>
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                           <h3 className="text-sm font-semibold text-slate-200 mb-3">Summary</h3>
                           <p className="text-sm text-slate-300 whitespace-pre-wrap">{doc.description || doc.summary || 'No description provided.'}</p>
                           {doc.summary && doc.description && (
                              <p className="mt-2 text-xs text-slate-400 whitespace-pre-wrap">{doc.summary}</p>
                           )}
                        </div>
                     </div>
                     <div className="space-y-4">
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                           <h3 className="text-sm font-semibold text-slate-200 mb-3">Ownership & Classification</h3>
                           <div className="space-y-2 text-xs">
                              <div><div className="text-slate-500 uppercase mb-1">Owners</div><div className="text-slate-300">{(doc.metadata?.owners || []).join(', ') || '-'}</div></div>
                              <div><div className="text-slate-500 uppercase mb-1">Contributors</div><div className="text-slate-300">{(doc.metadata?.contributors || []).join(', ') || '-'}</div></div>
                              <div className="grid grid-cols-2 gap-2 pt-1">
                                 <div className="bg-slate-950 border border-slate-800 rounded p-2"><div className="text-slate-500 uppercase">Priority</div><div className="text-slate-200 mt-1">{doc.priority || doc.metadata?.priority || '-'}</div></div>
                                 <div className="bg-slate-950 border border-slate-800 rounded p-2"><div className="text-slate-500 uppercase">Risk</div><div className="text-slate-200 mt-1">{doc.riskLevel || doc.metadata?.riskLevel || '-'}</div></div>
                                 <div className="bg-slate-950 border border-slate-800 rounded p-2"><div className="text-slate-500 uppercase">Complexity</div><div className="text-slate-200 mt-1">{doc.complexity || doc.metadata?.complexity || '-'}</div></div>
                                 <div className="bg-slate-950 border border-slate-800 rounded p-2"><div className="text-slate-500 uppercase">Track</div><div className="text-slate-200 mt-1">{doc.track || doc.metadata?.track || '-'}</div></div>
                              </div>
                           </div>
                        </div>
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                           <h3 className="text-sm font-semibold text-slate-200 mb-3">Anchors</h3>
                           <div className="space-y-2 text-xs">
                              <div className="flex justify-between text-slate-400"><span>Feature</span><span className="text-slate-200 font-mono">{doc.featureSlugCanonical || doc.featureSlugHint || '-'}</span></div>
                              <div className="flex justify-between text-slate-400"><span>PRD Ref</span><span className="text-slate-200 font-mono">{doc.prdRef || doc.frontmatter.prd || '-'}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Plan Ref</span><span className="text-slate-200 font-mono">{doc.planRef || doc.metadata?.planRef || '-'}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Implementation Plan Ref</span><span className="text-slate-200 font-mono">{doc.implementationPlanRef || doc.metadata?.implementationPlanRef || '-'}</span></div>
                           </div>
                        </div>
                     </div>
                  </div>
               )}

               {activeTab === 'delivery' && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                     <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                        <h3 className="text-sm font-semibold text-slate-200 mb-3">Execution & Quality</h3>
                        <div className="space-y-2 text-xs">
                           <div className="flex justify-between text-slate-400"><span>Execution Readiness</span><span className="text-slate-200">{doc.executionReadiness || doc.metadata?.executionReadiness || '-'}</span></div>
                           <div className="flex justify-between text-slate-400"><span>Timeline Estimate</span><span className="text-slate-200">{doc.timelineEstimate || doc.metadata?.timelineEstimate || '-'}</span></div>
                           <div className="flex justify-between text-slate-400"><span>Test Impact</span><span className="text-slate-200">{doc.testImpact || doc.metadata?.testImpact || '-'}</span></div>
                           <div className="flex justify-between text-slate-400"><span>Completion Estimate</span><span className="text-slate-200">{doc.completionEstimate || doc.metadata?.completionEstimate || '-'}</span></div>
                           <div className="flex justify-between text-slate-400"><span>Overall Progress</span><span className="text-slate-200">{doc.overallProgress ?? doc.metadata?.overallProgress ?? '-'}%</span></div>
                        </div>
                     </div>
                     <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                        <h3 className="text-sm font-semibold text-slate-200 mb-3">Task Counters</h3>
                        <div className="grid grid-cols-2 gap-3 text-xs">
                           <div className="p-2 rounded bg-slate-950 border border-slate-800"><div className="text-slate-500 uppercase">Total</div><div className="text-slate-200 font-mono mt-1">{taskCounts.total}</div></div>
                           <div className="p-2 rounded bg-slate-950 border border-slate-800"><div className="text-slate-500 uppercase">Completed</div><div className="text-slate-200 font-mono mt-1">{taskCounts.completed}</div></div>
                           <div className="p-2 rounded bg-slate-950 border border-slate-800"><div className="text-slate-500 uppercase">In Progress</div><div className="text-slate-200 font-mono mt-1">{taskCounts.inProgress}</div></div>
                           <div className="p-2 rounded bg-slate-950 border border-slate-800"><div className="text-slate-500 uppercase">Blocked</div><div className="text-slate-200 font-mono mt-1">{taskCounts.blocked}</div></div>
                        </div>
                     </div>
                  </div>
               )}

               {activeTab === 'relationships' && (
                  <div className="space-y-4">
                     <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                           <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2"><User size={14} /> Features</h3>
                           <div className="flex flex-wrap gap-2">
                              {linkedFeatures.map(feature => {
                                 const style = getFeatureStatusStyle(feature.status);
                                 return (
                                    <button
                                       key={feature.id}
                                       onClick={() => { onClose(); navigate(`/board?feature=${encodeURIComponent(feature.id)}`); }}
                                       className={`text-[10px] font-semibold rounded-full border px-2 py-0.5 transition-colors ${style.badge}`}
                                    >
                                       {feature.id}
                                    </button>
                                 );
                              })}
                              {linkedFeatures.length === 0 && <span className="text-xs text-slate-500 italic">No linked features.</span>}
                           </div>
                        </div>
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                           <h3 className="text-sm font-semibold text-slate-200 mb-3">Lineage</h3>
                           <div className="space-y-2 text-xs">
                              <div className="flex justify-between text-slate-400"><span>Family</span><span className="text-slate-200 font-mono">{doc.frontmatter.lineageFamily || '-'}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Parent</span><span className="text-slate-200 font-mono">{doc.frontmatter.lineageParent || '-'}</span></div>
                              <div className="flex justify-between text-slate-400"><span>Type</span><span className="text-slate-200">{doc.frontmatter.lineageType || '-'}</span></div>
                              <div className="text-slate-400"><span className="mr-2">Children</span><span className="text-slate-200 font-mono">{(doc.frontmatter.lineageChildren || []).join(', ') || '-'}</span></div>
                           </div>
                        </div>
                     </div>
                     <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                        <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2"><FolderTree size={14} /> Documents</h3>
                        <div className="space-y-2">
                           {linkedDocs.map(linkedDoc => (
                              <div key={linkedDoc.id} className="flex items-center gap-3 p-2 bg-slate-950 border border-slate-800 rounded">
                                 <Link2 size={14} className="text-slate-500" />
                                 <div className="min-w-0">
                                    <div className="text-xs text-slate-200 truncate">{linkedDoc.title || linkedDoc.id}</div>
                                    <div className="text-[11px] text-slate-500 font-mono truncate">{linkedDoc.canonicalPath || linkedDoc.filePath}</div>
                                 </div>
                              </div>
                           ))}
                           {(doc.frontmatter.pathRefs || []).map(pathRef => (
                              <div key={pathRef} className="text-xs text-slate-300 font-mono p-2 bg-slate-950 border border-slate-800 rounded">{pathRef}</div>
                           ))}
                           {linkedDocs.length === 0 && (doc.frontmatter.pathRefs || []).length === 0 && <p className="text-xs text-slate-500 italic">No linked docs.</p>}
                        </div>
                     </div>
                     <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                           <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2"><ListTodo size={14} /> Tasks</h3>
                           <div className="space-y-2">
                              {linkedTasks.map(task => (
                                 <div key={task.id} className="p-2 bg-slate-950 border border-slate-800 rounded">
                                    <div className="text-xs font-mono text-slate-500">{task.id}</div>
                                    <div className="text-xs text-slate-200">{task.title}</div>
                                 </div>
                              ))}
                              {linkedTasks.length === 0 && <p className="text-xs text-slate-500 italic">No linked tasks.</p>}
                           </div>
                        </div>
                        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                           <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2"><Terminal size={14} /> Sessions</h3>
                           <div className="space-y-2">
                              {linkedSessions.map(session => (
                                 <button
                                    key={session.id}
                                    onClick={() => { onClose(); navigate(`/sessions/${encodeURIComponent(session.id)}`); }}
                                    className="w-full text-left p-2 bg-slate-950 border border-slate-800 rounded hover:border-indigo-500/40"
                                 >
                                    <div className="flex justify-between items-center">
                                       <span className="text-xs font-mono text-indigo-400">{session.id}</span>
                                       <span className="text-[10px] text-slate-500">{session.status}</span>
                                    </div>
                                 </button>
                              ))}
                              {linkedSessions.length === 0 && <p className="text-xs text-slate-500 italic">No linked sessions.</p>}
                           </div>
                        </div>
                     </div>
                  </div>
               )}

               {activeTab === 'content' && (
                  <div className="bg-slate-900 border border-slate-800 rounded-lg p-6">
                     {isEditing ? (
                        <div className="space-y-4">
                           <label className="block">
                              <span className="block text-xs uppercase tracking-wide text-slate-500 mb-2">Commit Message (optional)</span>
                              <input
                                 type="text"
                                 value={commitMessage}
                                 onChange={event => setCommitMessage(event.target.value)}
                                 className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                                 placeholder={`ccdash: update ${doc.title}`}
                              />
                           </label>
                           <textarea
                              value={draftContent}
                              onChange={event => setDraftContent(event.target.value)}
                              className="h-[52vh] w-full resize-y rounded-lg border border-slate-700 bg-slate-950 p-3 font-mono text-[13px] text-slate-200 focus:outline-none focus:border-indigo-500"
                           />
                        </div>
                     ) : (
                        <div className="prose prose-invert prose-sm max-w-none [&_h1]:text-slate-100 [&_h2]:text-slate-200 [&_h3]:text-slate-300 [&_p]:text-slate-400 [&_li]:text-slate-400 [&_code]:bg-slate-800 [&_code]:text-indigo-300 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_pre]:bg-slate-900 [&_pre]:border [&_pre]:border-slate-800 [&_a]:text-indigo-400 [&_a:hover]:text-indigo-300 [&_blockquote]:border-l-indigo-500 [&_blockquote]:text-slate-400">
                           <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {currentContent}
                           </ReactMarkdown>
                        </div>
                     )}
                  </div>
               )}

               {activeTab === 'timeline' && (
                  <div className="space-y-2">
                     {timelineEvents.map(event => (
                        <div key={event.id} className="bg-slate-900 border border-slate-800 rounded-lg p-3">
                           <div className="flex items-center justify-between gap-2">
                              <span className="text-sm text-slate-200">{event.label}</span>
                              <span className="text-xs text-slate-500">{formatDate(event.timestamp)}</span>
                           </div>
                           <div className="mt-1 text-[11px] text-slate-500 flex flex-wrap gap-2">
                              <span className="uppercase">{event.kind || 'event'}</span>
                              <span>{event.confidence || 'low'}</span>
                              {event.source && <span className="font-mono truncate">{event.source}</span>}
                           </div>
                           {event.description && <p className="mt-2 text-xs text-slate-400">{event.description}</p>}
                        </div>
                     ))}
                     {timelineEvents.length === 0 && <p className="text-sm text-slate-500 italic">No timeline events available.</p>}
                  </div>
               )}

               {activeTab === 'raw' && (
                  <div className="grid grid-cols-1 gap-4">
                     <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                        <h3 className="text-sm font-semibold text-slate-200 mb-2">Normalized Metadata</h3>
                        <pre className="text-[11px] text-slate-300 overflow-auto">{JSON.stringify({
                           id: doc.id,
                           title: doc.title,
                           status: doc.status,
                           docType: doc.docType,
                           docSubtype: doc.docSubtype,
                           metadata: doc.metadata,
                           dates: doc.dates,
                           timeline: doc.timeline,
                        }, null, 2)}</pre>
                     </div>
                     <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                        <h3 className="text-sm font-semibold text-slate-200 mb-2">Raw Frontmatter</h3>
                        <pre className="text-[11px] text-slate-300 overflow-auto">{JSON.stringify(doc.frontmatter?.raw || doc.frontmatter || {}, null, 2)}</pre>
                     </div>
                  </div>
               )}
            </div>
         </div>
      </div>
   );
};
