import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const dataContextPath = resolve(root, 'contexts', 'DataContext.tsx');
const apiClientPath = resolve(root, 'services', 'apiClient.ts');

describe('data architecture guardrails', () => {
  it('keeps DataContext as a composition facade', () => {
    const source = readFileSync(dataContextPath, 'utf-8');

    expect(source).toContain('<DataClientProvider>');
    expect(source).toContain('<AppSessionProvider>');
    expect(source).toContain('<AppEntityDataProvider>');
    expect(source).toContain('<AppRuntimeProvider>');
    expect(source).not.toContain('createContext(');
    expect(source).not.toContain('fetch(');
  });

  it('keeps fetch logic in the typed API client layer', () => {
    const source = readFileSync(apiClientPath, 'utf-8');

    expect(source).toContain('export function createApiClient()');
    expect(source).toContain('fetch(`${API_BASE}${path}`');
  });
});
