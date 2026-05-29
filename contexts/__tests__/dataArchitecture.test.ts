import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const dataContextPath = resolve(root, 'contexts', 'DataContext.tsx');
const apiClientPath = resolve(root, 'services', 'apiClient.ts');
const appPath = resolve(root, 'App.tsx');
const appRuntimePath = resolve(root, 'contexts', 'AppRuntimeContext.tsx');

describe('data architecture guardrails', () => {
  it('keeps DataContext as a composition facade (T4-007)', () => {
    const source = readFileSync(dataContextPath, 'utf-8');

    // Required providers still present
    expect(source).toContain('<DataClientProvider>');
    expect(source).toContain('<AuthSessionProvider>');
    expect(source).toContain('<AppSessionProvider>');
    expect(source).toContain('<AppRuntimeProvider>');

    // T4-005: AppEntityDataProvider is deleted
    expect(source).not.toContain('<AppEntityDataProvider>');

    // T4-007: DataContext must not hold server-state arrays in createContext()
    // DataContext no longer calls createContext() — it is a pure function shim
    expect(source).not.toContain('createContext(');

    // T4-007: No direct fetch() for domain data in DataContext
    // (fetch for health is in the health query hook, not DataContext)
    expect(source).not.toContain('useEffect(');
    expect(source).not.toContain('useState<AgentSession');
    expect(source).not.toContain('useState<PlanDocument');
    expect(source).not.toContain('useState<ProjectTask');
    expect(source).not.toContain('useState<Feature');
  });

  it('AppDataProviderGate still gates inner providers (T4-007)', () => {
    const source = readFileSync(dataContextPath, 'utf-8');

    expect(source).toContain('AppDataProviderGate');
    expect(source).toContain('shouldMountAppDataProviders');
    // Gate must conditionally render the inner provider tree
    expect(source).toContain('AppSessionProvider');
    expect(source).toContain('AppRuntimeProvider');
  });

  it('DataContext has no createContext() holding server arrays (T4-007)', () => {
    const source = readFileSync(dataContextPath, 'utf-8');
    // The useData() shim is a plain function — it does not need a React context
    expect(source).not.toContain('createContext(');
  });

  it('AppEntityDataContext.tsx is deleted (T4-005)', () => {
    const { existsSync } = require('node:fs');
    const appEntityPath = resolve(root, 'contexts', 'AppEntityDataContext.tsx');
    expect(existsSync(appEntityPath)).toBe(false);
  });

  it('keeps fetch logic in the typed API client layer', () => {
    const source = readFileSync(apiClientPath, 'utf-8');

    expect(source).toContain('export function createApiClient()');
    expect(source).toContain('credentials: init?.credentials ?? \'same-origin\'');
    expect(source).toContain('fetch(url, requestInit)');
  });
});

describe('TanStack Query provider order guardrails (T0-004)', () => {
  it('App.tsx imports QueryClientProvider from @tanstack/react-query', () => {
    const source = readFileSync(appPath, 'utf-8');
    expect(source).toContain("from '@tanstack/react-query'");
    expect(source).toContain('QueryClientProvider');
  });

  it('QueryClientProvider appears above DataProvider in App.tsx source', () => {
    const source = readFileSync(appPath, 'utf-8');

    const qcpIndex = source.indexOf('<QueryClientProvider');
    const dpIndex = source.indexOf('<DataProvider');

    // Both must be present
    expect(qcpIndex).toBeGreaterThan(-1);
    expect(dpIndex).toBeGreaterThan(-1);

    // QueryClientProvider must open before DataProvider opens
    expect(qcpIndex).toBeLessThan(dpIndex);
  });

  it('QueryClientProvider closing tag appears after DataProvider closing tag in App.tsx source', () => {
    const source = readFileSync(appPath, 'utf-8');

    const qcpCloseIndex = source.lastIndexOf('</QueryClientProvider>');
    const dpCloseIndex = source.lastIndexOf('</DataProvider>');

    expect(qcpCloseIndex).toBeGreaterThan(-1);
    expect(dpCloseIndex).toBeGreaterThan(-1);

    // QueryClientProvider must close after DataProvider closes (i.e., it is the outer wrapper)
    expect(qcpCloseIndex).toBeGreaterThan(dpCloseIndex);
  });

  it('App.tsx mounts ReactQueryDevtools conditional on env flag (T0-005)', () => {
    const source = readFileSync(appPath, 'utf-8');
    expect(source).toContain('VITE_CCDASH_QUERY_DEVTOOLS');
    expect(source).toContain('@tanstack/react-query-devtools');
  });
});

describe('AppRuntimeContext client-state-only guardrails (T4-006)', () => {
  it('AppRuntimeContext has no setInterval for polling (T4-002)', () => {
    const source = readFileSync(appRuntimePath, 'utf-8');
    expect(source).not.toContain('setInterval(');
  });

  it('AppRuntimeContext has no domain data fetch (T4-006)', () => {
    const source = readFileSync(appRuntimePath, 'utf-8');
    // No entity refresh calls
    expect(source).not.toContain('refreshSessions');
    expect(source).not.toContain('refreshDocuments');
    expect(source).not.toContain('refreshTasks');
    expect(source).not.toContain('refreshAlerts');
    expect(source).not.toContain('refreshNotifications');
    expect(source).not.toContain('refreshFeatures');
  });

  it('AppRuntimeContext uses useHealthQuery for health polling (T4-001)', () => {
    const source = readFileSync(appRuntimePath, 'utf-8');
    expect(source).toContain('useHealthQuery');
    expect(source).toContain('refetchInterval');
  });

  it('AppRuntimeContext removes polling management refs (T4-006)', () => {
    const source = readFileSync(appRuntimePath, 'utf-8');
    expect(source).not.toContain('refreshAllInFlightRef');
    expect(source).not.toContain('pollingActiveRef');
    // healthPollRef and featurePollRef (setInterval-based) must be absent
    expect(source).not.toContain('healthPollRef');
    expect(source).not.toContain('featurePollRef');
  });
});
