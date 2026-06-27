/**
 * T0-009 — scope-persistence regression guard
 *
 * Asserts that an explicit is_active=true selection for a non-seed project B
 * PERSISTS across a refreshProjects() cycle. The default-active logic must NOT
 * override a valid explicit active selection.
 *
 * Tests the exported pure `resolveScopeOutcome` helper, which is the single
 * authoritative decision point inside refreshProjects().
 */
import { describe, expect, it } from 'vitest';
import type { Project } from '../../types';
import { resolveScopeOutcome, type ScopeResolutionOutcome } from '../AppSessionContext';

// ── fixtures ─────────────────────────────────────────────────────────────────

const baseProject = (overrides: Partial<Project> = {}): Project => ({
  id: 'proj-a',
  name: 'Project A',
  path: '/home/user/proj-a',
  description: '',
  repoUrl: '',
  agentPlatforms: [],
  planDocsPath: '',
  sessionsPath: '',
  progressPath: '',
  pathConfig: {
    root: { field: 'root', sourceKind: 'project_root', displayValue: '', filesystemPath: '', relativePath: '' },
    planDocs: { field: 'plan_docs', sourceKind: 'project_root', displayValue: '', filesystemPath: '', relativePath: '' },
    sessions: { field: 'sessions', sourceKind: 'project_root', displayValue: '', filesystemPath: '', relativePath: '' },
    progress: { field: 'progress', sourceKind: 'project_root', displayValue: '', filesystemPath: '', relativePath: '' },
  },
  testConfig: {
    flags: {
      testVisualizerEnabled: false,
      integritySignalsEnabled: false,
      liveTestUpdatesEnabled: false,
      semanticMappingEnabled: false,
    },
    platforms: [],
    autoSyncOnStartup: false,
    maxFilesPerScan: 0,
    maxParseConcurrency: 0,
    instructionProfile: '',
    instructionNotes: '',
  },
  skillMeat: {
    enabled: false,
    baseUrl: '',
    webBaseUrl: '',
    projectId: '',
    collectionId: '',
    aaaEnabled: false,
    apiKey: '',
    requestTimeoutSeconds: 30,
    featureFlags: {
      stackRecommendationsEnabled: false,
      workflowAnalyticsEnabled: false,
      usageAttributionEnabled: false,
      sessionBlockInsightsEnabled: false,
    },
  },
  ...overrides,
});

const projectA = baseProject({ id: 'proj-a', is_active: false, is_seed: true });
const projectB = baseProject({ id: 'proj-b', name: 'Project B', is_active: true, is_seed: false });

// ── core invariant ────────────────────────────────────────────────────────────

describe('resolveScopeOutcome — scope-persistence invariant (T0-009)', () => {
  it('returns "keep" when the scoped project is explicitly active (non-seed project B)', () => {
    // This is the critical regression test: projectB is is_active=true and is the
    // stored scope. refreshProjects() must retain it and must NOT call getActiveProject().
    const outcome: ScopeResolutionOutcome = resolveScopeOutcome(projectB, [projectA, projectB]);
    expect(outcome).toBe('keep');
  });

  it('returns "keep" when scoped project is active even if it is the only project', () => {
    const outcome = resolveScopeOutcome(projectB, [projectB]);
    expect(outcome).toBe('keep');
  });

  it('returns "keep" regardless of other projects having different is_active states', () => {
    // Multiple projects with mixed is_active — the scoped project is active, so keep it.
    const projectC = baseProject({ id: 'proj-c', is_active: false });
    const projectD = baseProject({ id: 'proj-d', is_active: null });
    const outcome = resolveScopeOutcome(projectB, [projectA, projectB, projectC, projectD]);
    expect(outcome).toBe('keep');
  });
});

// ── stale-scope clearing ──────────────────────────────────────────────────────

describe('resolveScopeOutcome — stale scope clearing', () => {
  it('returns "clear" when scoped project is inactive but another project is active', () => {
    // projectA is_active=false; projectB is_active=true in the registry.
    // The stored scope (projectA) is stale → clear it.
    const outcome = resolveScopeOutcome(projectA, [projectA, projectB]);
    expect(outcome).toBe('clear');
  });

  it('returns "clear" when scoped project has is_active=false explicitly', () => {
    const inactiveScoped = baseProject({ id: 'proj-x', is_active: false });
    const activeOther = baseProject({ id: 'proj-y', is_active: true });
    expect(resolveScopeOutcome(inactiveScoped, [inactiveScoped, activeOther])).toBe('clear');
  });
});

// ── legacy / no active ────────────────────────────────────────────────────────

describe('resolveScopeOutcome — legacy backend (no is_active field)', () => {
  it('returns "keep-legacy" when scoped project is inactive and no project has is_active=true', () => {
    // Older backend scenario: scoped project has is_active=false but no other
    // project declares is_active=true (possibly all null/undefined).
    const legacyScoped = baseProject({ id: 'proj-legacy', is_active: false });
    const legacyOther = baseProject({ id: 'proj-other', is_active: null });
    const outcome = resolveScopeOutcome(legacyScoped, [legacyScoped, legacyOther]);
    expect(outcome).toBe('keep-legacy');
  });

  it('returns "keep-legacy" when scoped project has is_active=false and registry is empty aside from it', () => {
    const legacyScoped = baseProject({ id: 'proj-legacy', is_active: false });
    const outcome = resolveScopeOutcome(legacyScoped, [legacyScoped]);
    expect(outcome).toBe('keep-legacy');
  });
});

// ── no stored scope ───────────────────────────────────────────────────────────

describe('resolveScopeOutcome — no stored scope', () => {
  it('returns "query" when scopedProject is null (no localStorage scope)', () => {
    const outcome = resolveScopeOutcome(null, [projectA, projectB]);
    expect(outcome).toBe('query');
  });

  it('returns "query" when scopedProject is undefined', () => {
    const outcome = resolveScopeOutcome(undefined, [projectA, projectB]);
    expect(outcome).toBe('query');
  });
});
