/**
 * Guardrail: No hand-rolled Map+TTL caches in TQ migration output files.
 *
 * Pattern copied from components/__tests__/ProjectBoardEagerLoop.test.tsx
 * (source-read assertion style).
 *
 * DESIGN: These tests are written to PASS during P0 (before any domain
 * migration has occurred) and will catch regressions in later phases:
 *
 *   - In P0: services/queries/ does not exist yet, so the file-scan tests
 *     are vacuously green (the directory has zero files to scan).
 *   - In P1–P2: each new hook file added to services/queries/ is automatically
 *     scanned; any hand-rolled Map+TTL pattern will cause a failure.
 *
 * Existing pre-migration files (featureSurfaceCache.ts, AppEntityDataContext.tsx)
 * intentionally contain Map+TTL patterns that WILL be removed as part of P1–P2
 * migration. Those files are NOT scanned here — this test only guards NEW code.
 *
 * Banned patterns (in new hook files):
 *   - new Map() combined with TTL / expiry / timestamp fields in the same file
 *
 * Permitted:
 *   - Imports from @tanstack/react-query (the authorised caching layer)
 *   - Plain Maps without expiry (lookup tables, WeakMaps, etc.)
 *
 * Additional source-level assertions (always run):
 *   - queryKeys.ts must not contain inline string keys
 *   - queryClient.ts must import from @tanstack/react-query
 *   - App.tsx must mount QueryClientProvider above DataProvider
 */

import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve, join, extname } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));

// ── helpers ───────────────────────────────────────────────────────────────────

function collectFiles(dir: string, extensions: string[]): string[] {
  if (!existsSync(dir)) return [];

  const results: string[] = [];

  function walk(current: string) {
    let entries: string[];
    try {
      entries = readdirSync(current);
    } catch {
      return;
    }
    for (const entry of entries) {
      const fullPath = join(current, entry);
      let stat;
      try {
        stat = statSync(fullPath);
      } catch {
        continue;
      }
      if (stat.isDirectory()) {
        if (entry === '__tests__' || entry === 'node_modules') continue;
        walk(fullPath);
      } else if (extensions.includes(extname(entry))) {
        results.push(fullPath);
      }
    }
  }

  walk(dir);
  return results;
}

/**
 * Returns true if the source contains a hand-rolled TTL cache pattern:
 * a `new Map()` combined with expiry/TTL/timestamp tracking.
 */
function hasHandRolledTTLCache(source: string): boolean {
  const hasNewMap = /new Map\s*\(/.test(source);
  if (!hasNewMap) return false;

  const ttlMarkers = [
    /[Ee]xpir/,
    /[Tt][Tt][Ll]/,
    /[Tt]imestamp/,
    /Date\.now\(\)/,
    /maxAge/,
    /cacheTime/,
  ];

  return ttlMarkers.some((pattern) => pattern.test(source));
}

// ── scan scope ────────────────────────────────────────────────────────────────

// Only scan services/queries/ — this is where all TQ migration output lives.
// Pre-migration files (featureSurfaceCache.ts, AppEntityDataContext.tsx, etc.)
// already contain Map+TTL patterns that are targeted for removal in P1–P2;
// scanning them here would produce pre-existing failures that mask new regressions.
const queriesDir = resolve(root, 'services', 'queries');
const queryFiles = collectFiles(queriesDir, ['.ts', '.tsx']);

// ── tests ─────────────────────────────────────────────────────────────────────

describe('noHandRolledCache — services/queries/ (TQ migration output)', () => {
  it('services/queries/ directory check (passes vacuously if directory absent in P0)', () => {
    // In P0 the directory does not exist yet — this is expected and not a failure.
    // The test will start enforcing once P1 hook files are created.
    if (!existsSync(queriesDir)) {
      expect(queryFiles).toHaveLength(0);
      return;
    }
    // If the directory exists it should contain .ts files
    // (once any hook is written). We just verify the list is accessible.
    expect(Array.isArray(queryFiles)).toBe(true);
  });

  for (const filePath of queryFiles) {
    it(`${filePath.replace(root, '')} — no new Map() + TTL pattern`, () => {
      const source = readFileSync(filePath, 'utf-8');
      const hasTTLCache = hasHandRolledTTLCache(source);
      expect(
        hasTTLCache,
        `${filePath.replace(root, '')} contains a hand-rolled Map+TTL cache pattern. ` +
          'Use @tanstack/react-query for server-state caching instead.',
      ).toBe(false);
    });
  }
});

describe('noHandRolledCache — @tanstack/react-query is the authorised cache layer', () => {
  it('queryKeys.ts uses array key factories, no inline string keys in useQuery calls', () => {
    const queryKeysPath = resolve(root, 'services', 'queryKeys.ts');
    const source = readFileSync(queryKeysPath, 'utf-8');

    // Must not use inline string key literals directly in useQuery / useInfiniteQuery calls
    expect(source).not.toMatch(/useQuery\(\s*['"`]/);
    expect(source).not.toMatch(/useInfiniteQuery\(\s*['"`]/);
  });

  it('queryClient.ts imports QueryClient from @tanstack/react-query', () => {
    const queryClientPath = resolve(root, 'lib', 'queryClient.ts');
    const source = readFileSync(queryClientPath, 'utf-8');
    expect(source).toContain("from '@tanstack/react-query'");
    expect(source).toContain('QueryClient');
  });

  it('App.tsx mounts QueryClientProvider above DataProvider', () => {
    const appPath = resolve(root, 'App.tsx');
    const source = readFileSync(appPath, 'utf-8');

    const qcpIndex = source.indexOf('<QueryClientProvider');
    const dpIndex = source.indexOf('<DataProvider');

    expect(qcpIndex).toBeGreaterThan(-1);
    expect(dpIndex).toBeGreaterThan(-1);
    expect(qcpIndex).toBeLessThan(dpIndex);
  });
});

// T2-008: tasks + features must be paginated — the unbounded limit=5000 fetch
// pattern must not reappear anywhere in services/ or contexts/ live code.
const LIMIT_5000_PATTERN = /limit\s*[=:]\s*5000/;

describe('noHandRolledCache — limit=5000 unbounded fetch is banned', () => {
  const scanDirs = [resolve(root, 'services'), resolve(root, 'contexts')];
  const sourceFiles = scanDirs.flatMap((dir) => collectFiles(dir, ['.ts', '.tsx']));

  it('finds source files to scan in services/ and contexts/', () => {
    expect(sourceFiles.length).toBeGreaterThan(0);
  });

  for (const filePath of sourceFiles) {
    it(`${filePath.replace(root, '')} — no limit=5000 / limit: 5000`, () => {
      const source = readFileSync(filePath, 'utf-8');
      expect(
        LIMIT_5000_PATTERN.test(source),
        `${filePath.replace(root, '')} contains an unbounded limit=5000 fetch. ` +
          'Use paginated TanStack Query hooks instead.',
      ).toBe(false);
    });
  }
});
