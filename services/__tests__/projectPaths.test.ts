import { describe, expect, it } from 'vitest';

import {
  applyProjectPathConfigToLegacyFields,
  createDefaultPathConfig,
  normalizeProjectPathConfig,
  setProjectPathSourceKind,
  updateProjectPathReference,
} from '../projectPaths';

describe('project path helpers', () => {
  it('builds local-first defaults', () => {
    const config = createDefaultPathConfig();

    expect(config.root.sourceKind).toBe('filesystem');
    expect(config.planDocs.sourceKind).toBe('project_root');
    expect(config.progress.relativePath).toBe('progress');
  });

  it('normalizes legacy project fields into typed references', () => {
    const config = normalizeProjectPathConfig({
      path: '/tmp/workspace',
      planDocsPath: 'docs/project_plans',
      sessionsPath: '/tmp/sessions',
      progressPath: '.claude/progress',
      pathConfig: undefined as any,
    });

    expect(config.root.filesystemPath).toBe('/tmp/workspace');
    expect(config.planDocs.relativePath).toBe('docs/project_plans');
    expect(config.sessions.filesystemPath).toBe('/tmp/sessions');
  });

  it('keeps legacy display fields in sync after source changes', () => {
    const baseProject: any = {
      id: 'project-1',
      name: 'Project 1',
      path: '/tmp/workspace',
      planDocsPath: 'docs/project_plans',
      sessionsPath: '/tmp/sessions',
      progressPath: 'progress',
      pathConfig: createDefaultPathConfig(),
    };

    const githubConfig = updateProjectPathReference(
      setProjectPathSourceKind(baseProject.pathConfig, 'root', 'github_repo'),
      'root',
      reference => ({
        ...reference,
        displayValue: 'https://github.com/acme/repo',
        repoRef: {
          provider: 'github',
          repoUrl: 'https://github.com/acme/repo',
          repoSlug: 'acme/repo',
          branch: 'main',
          repoSubpath: '',
          writeEnabled: true,
        },
      }),
    );

    const project = applyProjectPathConfigToLegacyFields(baseProject, githubConfig);

    expect(project.path).toBe('https://github.com/acme/repo');
    expect(project.pathConfig.root.repoRef?.repoSlug).toBe('acme/repo');
  });
});
