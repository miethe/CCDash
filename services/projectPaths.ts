import { GitRepoRef, Project, ProjectPathConfig, ProjectPathReference } from '../types';

export type ProjectPathConfigKey = keyof ProjectPathConfig;

export interface ProjectPathFieldDefinition {
  key: ProjectPathConfigKey;
  field: ProjectPathReference['field'];
  label: string;
  description: string;
  helperText: string;
}

const DEFAULT_GITHUB_REF: GitRepoRef = {
  provider: 'github',
  repoUrl: '',
  repoSlug: '',
  branch: '',
  repoSubpath: '',
  writeEnabled: false,
};

export const PROJECT_PATH_FIELDS: ProjectPathFieldDefinition[] = [
  {
    key: 'root',
    field: 'root',
    label: 'Project Root',
    description: 'The root workspace CCDash resolves everything else from.',
    helperText: 'Use a local filesystem path or a managed GitHub workspace.',
  },
  {
    key: 'planDocs',
    field: 'plan_docs',
    label: 'Plan Documents',
    description: 'PRDs, implementation plans, and related docs.',
    helperText: 'Project-root sources stay relative to the resolved root path.',
  },
  {
    key: 'sessions',
    field: 'sessions',
    label: 'Sessions',
    description: 'Directory containing Claude session JSONL exports.',
    helperText: 'This is usually a local filesystem path, even for repo-backed projects.',
  },
  {
    key: 'progress',
    field: 'progress',
    label: 'Progress / Tasks',
    description: 'Progress trackers and execution task files.',
    helperText: 'Project-root sources inherit from the resolved project root.',
  },
];

const DEFAULT_PATH_REFERENCES: Record<ProjectPathConfigKey, ProjectPathReference> = {
  root: {
    field: 'root',
    sourceKind: 'filesystem',
    displayValue: '',
    filesystemPath: '',
    relativePath: '',
    repoRef: null,
  },
  planDocs: {
    field: 'plan_docs',
    sourceKind: 'project_root',
    displayValue: 'docs/project_plans/',
    filesystemPath: '',
    relativePath: 'docs/project_plans/',
    repoRef: null,
  },
  sessions: {
    field: 'sessions',
    sourceKind: 'filesystem',
    displayValue: '',
    filesystemPath: '',
    relativePath: '',
    repoRef: null,
  },
  progress: {
    field: 'progress',
    sourceKind: 'project_root',
    displayValue: 'progress',
    filesystemPath: '',
    relativePath: 'progress',
    repoRef: null,
  },
};

const joinPreviewPath = (basePath: string, childPath: string): string => {
  const base = String(basePath || '').replace(/\\/g, '/').trim().replace(/\/+$/, '');
  const child = String(childPath || '').replace(/\\/g, '/').trim().replace(/^\/+/, '');
  if (!base) return child;
  if (!child) return base;
  return `${base}/${child}`;
};

const cloneRepoRef = (value?: GitRepoRef | null): GitRepoRef => ({
  ...DEFAULT_GITHUB_REF,
  ...(value || {}),
});

const cloneReference = (reference: ProjectPathReference): ProjectPathReference => ({
  ...reference,
  repoRef: reference.repoRef ? cloneRepoRef(reference.repoRef) : null,
});

export const createDefaultPathConfig = (): ProjectPathConfig => ({
  root: cloneReference(DEFAULT_PATH_REFERENCES.root),
  planDocs: cloneReference(DEFAULT_PATH_REFERENCES.planDocs),
  sessions: cloneReference(DEFAULT_PATH_REFERENCES.sessions),
  progress: cloneReference(DEFAULT_PATH_REFERENCES.progress),
});

export const normalizeProjectPathConfig = (
  project?: Pick<Project, 'path' | 'planDocsPath' | 'sessionsPath' | 'progressPath' | 'pathConfig'> | null,
): ProjectPathConfig => {
  const defaults = createDefaultPathConfig();
  const config = project?.pathConfig;
  if (config) {
    return {
      root: cloneReference({ ...defaults.root, ...(config.root || {}) }),
      planDocs: cloneReference({ ...defaults.planDocs, ...(config.planDocs || {}) }),
      sessions: cloneReference({ ...defaults.sessions, ...(config.sessions || {}) }),
      progress: cloneReference({ ...defaults.progress, ...(config.progress || {}) }),
    };
  }

  return {
    root: cloneReference({
      ...defaults.root,
      displayValue: project?.path || '',
      filesystemPath: project?.path || '',
    }),
    planDocs: cloneReference({
      ...defaults.planDocs,
      displayValue: project?.planDocsPath || defaults.planDocs.displayValue,
      relativePath: project?.planDocsPath || defaults.planDocs.relativePath,
    }),
    sessions: cloneReference({
      ...defaults.sessions,
      displayValue: project?.sessionsPath || '',
      filesystemPath: project?.sessionsPath || '',
    }),
    progress: cloneReference({
      ...defaults.progress,
      displayValue: project?.progressPath || defaults.progress.displayValue,
      relativePath: project?.progressPath || defaults.progress.relativePath,
    }),
  };
};

export const updateProjectPathReference = (
  config: ProjectPathConfig,
  key: ProjectPathConfigKey,
  updater: (reference: ProjectPathReference) => ProjectPathReference,
): ProjectPathConfig => ({
  ...config,
  [key]: cloneReference(updater(cloneReference(config[key]))),
});

export const setProjectPathSourceKind = (
  config: ProjectPathConfig,
  key: ProjectPathConfigKey,
  sourceKind: ProjectPathReference['sourceKind'],
): ProjectPathConfig => updateProjectPathReference(config, key, (reference) => {
  if (sourceKind === 'project_root') {
    return {
      ...reference,
      sourceKind,
      displayValue: reference.relativePath || reference.displayValue,
      filesystemPath: '',
      repoRef: null,
    };
  }
  if (sourceKind === 'filesystem') {
    return {
      ...reference,
      sourceKind,
      displayValue: reference.filesystemPath || reference.displayValue,
      relativePath: '',
      repoRef: null,
    };
  }
  return {
    ...reference,
    sourceKind,
    displayValue: reference.displayValue || reference.repoRef?.repoUrl || '',
    filesystemPath: '',
    relativePath: '',
    repoRef: cloneRepoRef(reference.repoRef),
  };
});

export const getProjectPathInputValue = (reference: ProjectPathReference): string => {
  if (reference.sourceKind === 'project_root') return reference.relativePath || reference.displayValue || '';
  if (reference.sourceKind === 'filesystem') return reference.filesystemPath || reference.displayValue || '';
  return reference.repoRef?.repoUrl || reference.displayValue || '';
};

export const deriveProjectPathPreview = (
  config: ProjectPathConfig,
  key: ProjectPathConfigKey,
  resolvedRootPath: string,
  githubResolvedPath?: string,
): string => {
  const reference = config[key];
  if (reference.sourceKind === 'project_root') {
    return joinPreviewPath(resolvedRootPath, reference.relativePath || reference.displayValue);
  }
  if (reference.sourceKind === 'filesystem') {
    return reference.filesystemPath || reference.displayValue || '';
  }
  return githubResolvedPath || reference.repoRef?.repoUrl || reference.displayValue || '';
};

export const pathReferenceUsesGitHub = (reference: ProjectPathReference): boolean => (
  reference.sourceKind === 'github_repo'
);

const deriveLegacyValue = (reference: ProjectPathReference): string => {
  if (reference.sourceKind === 'project_root') {
    return reference.relativePath || reference.displayValue || '';
  }
  if (reference.sourceKind === 'filesystem') {
    return reference.filesystemPath || reference.displayValue || '';
  }
  return reference.repoRef?.repoUrl || reference.displayValue || '';
};

export const applyProjectPathConfigToLegacyFields = (
  project: Project,
  pathConfig: ProjectPathConfig,
): Project => ({
  ...project,
  pathConfig,
  path: deriveLegacyValue(pathConfig.root),
  planDocsPath: deriveLegacyValue(pathConfig.planDocs),
  sessionsPath: deriveLegacyValue(pathConfig.sessions),
  progressPath: deriveLegacyValue(pathConfig.progress),
});
