import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));

const readSource = (path: string): string =>
  readFileSync(resolve(root, path), 'utf-8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|\s)\/\/.*$/gm, '');

describe('permission-aware UI affordance guardrails', () => {
  it('keeps hosted navigation affordances scoped by auth permissions', () => {
    const source = readSource('components/Layout.tsx');

    expect(source).toContain("auth.hasPermission({ scopes: ['execution:read']");
    expect(source).toContain("auth.hasPermission({ scopes: ['codebase:read_tree', 'codebase:file_read', 'codebase:activity_read']");
    expect(source).toContain("auth.hasPermission({ scopes: ['session_mapping:read', 'session_mapping:diagnose']");
    expect(source).toContain("auth.hasPermission({ scopes: ['cache:read_status', 'cache.operation:read']");
    expect(source).toContain('Permission hint only; backend authorization remains authoritative.');
    expect(source).toMatch(/<NavItem[\s\S]*label="Execution"[\s\S]*restricted=\{!canAccessExecution\}/);
    expect(source).toMatch(/<NavItem[\s\S]*label="Codebase Explorer"[\s\S]*restricted=\{!canAccessCodebase\}/);
  });

  it('keeps operation mutations gated before invoking protected transports', () => {
    const source = readSource('components/OpsPanel.tsx');

    expect(source).toContain("auth.hasPermission({ scopes: ['cache.sync:trigger']");
    expect(source).toContain("auth.hasPermission({ scopes: ['cache.links:rebuild']");
    expect(source).toContain("auth.hasPermission({ scopes: ['test.sync:trigger', 'test.run:ingest']");
    expect(source).toMatch(/const runSync[\s\S]*if \(!canTriggerCacheSync\)[\s\S]*return;[\s\S]*apiRequestJson/);
    expect(source).toMatch(/const runRebuildLinks[\s\S]*if \(!canRebuildLinks\)[\s\S]*return;[\s\S]*apiRequestJson/);
    expect(source).toContain('Permission hint only; backend authorization remains authoritative.');
  });

  it('keeps execution controls permission-hinted while backend authorization stays authoritative', () => {
    const source = readSource('components/FeatureExecutionWorkbench.tsx');

    expect(source).toContain("auth.hasPermission({ scopes: ['execution.run:create']");
    expect(source).toContain("auth.hasPermission({ scopes: ['execution.run:cancel']");
    expect(source).toContain("auth.hasPermission({ scopes: ['execution.run:retry']");
    expect(source).toContain("auth.hasPermission({ scopes: ['execution.run:approve']");
    expect(source).toContain('Permission hint only; backend authorization remains authoritative.');
    expect(source).toContain('title={!canCreateExecutionRun ? protectedActionHint : undefined}');
  });
});
