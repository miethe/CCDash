import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));

const readSource = (path: string): string =>
  readFileSync(resolve(root, path), 'utf-8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|\s)\/\/.*$/gm, '');

describe('protected request transport guardrails', () => {
  it.each([
    'services/execution.ts',
    'services/githubIntegrations.ts',
    'services/skillmeat.ts',
    'services/documents.ts',
    'services/codebase.ts',
    'services/testVisualizer.ts',
    'services/featureSurface.ts',
    'services/planning.ts',
    'components/OpsPanel.tsx',
    'components/CodebaseExplorer.tsx',
    'components/SessionMappings.tsx',
    'components/DocumentModal.tsx',
    'components/SessionInspector/TranscriptView.tsx',
  ])('%s does not use ad hoc raw fetch for protected paths', (path) => {
    const source = readSource(path);

    expect(source).not.toMatch(/\bfetch\s*\(/);
    expect(source).toMatch(/\b(apiFetch|apiRequestJson|getCodebase(Tree|FileDetail)|listCodebaseFiles)\b/);
  });

  it('keeps analytics alert mutation paths on the shared auth-aware helper', () => {
    const source = readSource('services/analytics.ts');

    expect(source).toContain('import { apiRequestJson }');
    expect(source).toMatch(/async createAlert[\s\S]*apiRequestJson<AlertConfig>\(`\$\{API_BASE\}\/alerts`/);
    expect(source).toMatch(/async updateAlert[\s\S]*apiRequestJson<AlertConfig>\(`\$\{API_BASE\}\/alerts\/\$\{alertId\}`/);
    expect(source).toMatch(/async deleteAlert[\s\S]*apiRequestJson<void>\(`\$\{API_BASE\}\/alerts\/\$\{alertId\}`/);
  });
});
