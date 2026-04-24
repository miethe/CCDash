/**
 * P5-004: Architecture Guardrail — No Eager Linked-Sessions Imports
 *
 * Lint-style test that scans the frontend production source tree (test files
 * excluded) and fails if any file outside the explicitly-allowed set imports or
 * calls the /api/features/{id}/linked-sessions endpoint in a way that would
 * cause an eager fan-out on render.
 *
 * Two classes of violations are detected:
 *
 *   CLASS A — getLegacyFeatureLinkedSessions import
 *     Any production file that imports `getLegacyFeatureLinkedSessions` from
 *     `featureSurface` must be on the ALLOWED_LEGACY_IMPORTERS allowlist.
 *     New consumers must use `getFeatureLinkedSessionPage` instead.
 *
 *   CLASS B — Raw fetch to /api/features/{id}/linked-sessions
 *     Any production file that contains an actual fetch call or template-literal
 *     URL directly targeting the linked-sessions path is forbidden — including
 *     files on the allowlist. The featureSurface.ts definition site is the sole
 *     permitted location.
 *
 * Allowlist rationale:
 *   - `services/featureSurface.ts` — definition + export site only; P5-006
 *     completed: ProjectBoard.tsx migrated to getFeatureLinkedSessionPage
 *
 * Pattern inspired by themeFoundationGuardrails.test.ts and the other
 * architecture-guardrail tests under lib/__tests__/.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { basename, extname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// ─────────────────────────────────────────────────────────────────────────────
// Root resolution
// ─────────────────────────────────────────────────────────────────────────────

const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)));

// ─────────────────────────────────────────────────────────────────────────────
// Allowlists
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Production files allowed to import getLegacyFeatureLinkedSessions.
 * Each entry is a path relative to the repo root.
 *
 * P5-006 (completed): ProjectBoard.tsx migrated to getFeatureLinkedSessionPage.
 * Only the definition site itself remains — it is the export location, not a
 * production consumer.  The set is intentionally kept for future allowance if
 * any new justified legacy consumer needs to be documented.
 */
const ALLOWED_LEGACY_IMPORTERS = new Set([
  'services/featureSurface.ts',         // definition site — exports the deprecated symbol
]);

/**
 * Production files allowed to contain the raw /linked-sessions fetch call.
 * This MUST be kept to a minimum — ideally only featureSurface.ts which owns
 * the network layer abstraction.
 */
const ALLOWED_RAW_FETCH_FILES = new Set([
  'services/featureSurface.ts',         // owns the network abstraction; both fns call it
]);

/**
 * Directories to skip entirely during the scan.
 */
const SKIP_DIRS = new Set([
  'node_modules',
  'dist',
  '.claude',
  '.git',
  'backend',
  'packages',
  'examples',
  'src',           // compiled output
]);

/**
 * File extensions to include in the scan.
 */
const SCAN_EXTENSIONS = new Set(['.ts', '.tsx']);

// ─────────────────────────────────────────────────────────────────────────────
// Scanner — production files only (excludes test files)
// ─────────────────────────────────────────────────────────────────────────────

function isTestFile(entry: string): boolean {
  return (
    entry.endsWith('.test.ts') ||
    entry.endsWith('.test.tsx') ||
    entry.endsWith('.spec.ts') ||
    entry.endsWith('.spec.tsx')
  );
}

function isInTestDir(absPath: string): boolean {
  return absPath.includes('__tests__') || absPath.includes('/__tests/');
}

function collectProductionSourceFiles(dir: string, files: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir) as string[];
  } catch {
    return files;
  }

  for (const entry of entries) {
    if (SKIP_DIRS.has(entry)) continue;
    // Skip __tests__ directories entirely
    if (entry === '__tests__') continue;

    const fullPath = join(dir, entry);
    let stat: ReturnType<typeof statSync>;
    try {
      stat = statSync(fullPath);
    } catch {
      continue;
    }

    if (stat.isDirectory()) {
      collectProductionSourceFiles(fullPath, files);
    } else if (SCAN_EXTENSIONS.has(extname(entry)) && !isTestFile(entry)) {
      files.push(fullPath);
    }
  }
  return files;
}

/** Also collect all files (including tests) for the coverage sanity check. */
function collectAllSourceFiles(dir: string, files: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir) as string[];
  } catch {
    return files;
  }

  for (const entry of entries) {
    if (SKIP_DIRS.has(entry)) continue;

    const fullPath = join(dir, entry);
    let stat: ReturnType<typeof statSync>;
    try {
      stat = statSync(fullPath);
    } catch {
      continue;
    }

    if (stat.isDirectory()) {
      collectAllSourceFiles(fullPath, files);
    } else if (SCAN_EXTENSIONS.has(extname(entry))) {
      files.push(fullPath);
    }
  }
  return files;
}

function readSource(absPath: string): string {
  return readFileSync(absPath, 'utf-8');
}

// ─────────────────────────────────────────────────────────────────────────────
// Violation types
// ─────────────────────────────────────────────────────────────────────────────

interface Violation {
  file: string;
  lineNo: number;
  text: string;
  reason: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// CLASS A detector
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Detect production files that import getLegacyFeatureLinkedSessions without
 * being on the allowlist.
 */
function detectClassAViolations(files: string[]): Violation[] {
  const violations: Violation[] = [];

  for (const absPath of files) {
    const relPath = relative(ROOT, absPath);
    if (ALLOWED_LEGACY_IMPORTERS.has(relPath)) continue;

    const source = readSource(absPath);
    const lines = source.split('\n');

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (!line.includes('getLegacyFeatureLinkedSessions')) continue;
      if (!(line.includes('import') || line.includes('from'))) continue;

      const trimmed = line.trimStart();
      if (trimmed.startsWith('//') || trimmed.startsWith('*')) continue;

      violations.push({
        file: relPath,
        lineNo: i + 1,
        text: trimmed.slice(0, 120),
        reason:
          'Imports getLegacyFeatureLinkedSessions. Use getFeatureLinkedSessionPage instead. ' +
          'Add to ALLOWED_LEGACY_IMPORTERS only if the call is gated behind a non-initial-render handler.',
      });
    }
  }

  return violations;
}

// ─────────────────────────────────────────────────────────────────────────────
// CLASS B detector
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Patterns that identify an actual fetch call / URL construction targeting
 * the linked-sessions endpoint. These are tight enough to avoid matching
 * test description strings or comments.
 *
 * Specifically detected:
 *   - fetch(... /linked-sessions ...)  ← actual fetch() call
 *   - legacyFetch(... linked-sessions ...)  ← internal helper in featureSurface
 *   - template literal url with ${featureId}/linked-sessions
 *     where the context is a function call argument (starts with `)
 */
const CLASS_B_PATTERNS: RegExp[] = [
  // Actual fetch() call containing linked-sessions in the URL argument
  /\bfetch\s*\(\s*[`'"][^`'"]*\/linked-sessions/,
  // legacyFetch helper (used only inside featureSurface.ts — allowlisted)
  /\blegacyFetch\s*\(\s*[`'"][^`'"]*\/linked-sessions/,
  // Template literal URL construction passed as a call argument: `.../${id}/linked-sessions`
  /`[^`]*\/\$\{[^`}]+\}\/linked-sessions[^`]*`/,
];

function detectClassBViolations(files: string[]): Violation[] {
  const violations: Violation[] = [];

  for (const absPath of files) {
    const relPath = relative(ROOT, absPath);
    if (ALLOWED_RAW_FETCH_FILES.has(relPath)) continue;

    const source = readSource(absPath);
    const lines = source.split('\n');

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trimStart();
      // Skip comment lines
      if (trimmed.startsWith('//') || trimmed.startsWith('*')) continue;

      for (const pattern of CLASS_B_PATTERNS) {
        if (pattern.test(line)) {
          violations.push({
            file: relPath,
            lineNo: i + 1,
            text: trimmed.slice(0, 120),
            reason:
              'Raw URL construction or fetch call to /linked-sessions in production code. ' +
              'All linked-sessions access must be encapsulated in services/featureSurface.ts.',
          });
          break; // one violation per line
        }
      }
    }
  }

  return violations;
}

// ─────────────────────────────────────────────────────────────────────────────
// CLASS C detector — zero production callers (P5-006 completed)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * P5-006 (completed): ProjectBoard.tsx has been migrated to getFeatureLinkedSessionPage.
 * The CLASS C gate check is replaced with a hard assertion that no production file
 * imports getLegacyFeatureLinkedSessions outside the definition site.
 *
 * This function is retained as a named entry point so the test suite structure
 * is unchanged (CLASS A / B / C labelling). It now verifies the zero-importer
 * invariant rather than the lazy-sessions gate.
 */
function detectGateMissing(): Violation[] {
  // Collect all production importers except the definition site itself.
  const violations: Violation[] = [];

  for (const absPath of productionFiles) {
    const relPath = relative(ROOT, absPath);
    // The definition site is allowed — it exports the symbol.
    if (relPath === 'services/featureSurface.ts') continue;

    const source = readSource(absPath);
    const lines = source.split('\n');

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (!line.includes('getLegacyFeatureLinkedSessions')) continue;
      // Must be an import statement, not a comment or test description string.
      if (!(line.includes('import') || line.includes('from'))) continue;
      const trimmed = line.trimStart();
      if (trimmed.startsWith('//') || trimmed.startsWith('*')) continue;

      violations.push({
        file: relPath,
        lineNo: i + 1,
        text: trimmed.slice(0, 120),
        reason:
          'P5-006 completed: no production file may import getLegacyFeatureLinkedSessions. ' +
          'Use getFeatureLinkedSessionPage instead.',
      });
    }
  }

  return violations;
}

// ─────────────────────────────────────────────────────────────────────────────
// File sets
// ─────────────────────────────────────────────────────────────────────────────

const productionFiles = collectProductionSourceFiles(ROOT);
// Kept available for future coverage-sanity tests that scan tests too.
void collectAllSourceFiles;

function formatViolations(violations: Violation[]): string {
  if (violations.length === 0) return '  (none)';
  return violations
    .map(v => `  ${v.file}:${v.lineNo}\n    ${v.text}\n    → ${v.reason}`)
    .join('\n\n');
}

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

describe('Architecture guardrail: no eager linked-sessions imports (P5-004)', () => {
  it('CLASS A — no new production files import getLegacyFeatureLinkedSessions without allowlist approval', () => {
    const violations = detectClassAViolations(productionFiles);
    expect(
      violations,
      `Unapproved getLegacyFeatureLinkedSessions imports found:\n\n${formatViolations(violations)}\n`,
    ).toHaveLength(0);
  });

  it('CLASS B — no production file constructs a raw URL to /linked-sessions outside featureSurface.ts', () => {
    const violations = detectClassBViolations(productionFiles);
    expect(
      violations,
      `Raw URL construction to /linked-sessions found:\n\n${formatViolations(violations)}\n`,
    ).toHaveLength(0);
  });

  it('CLASS C — zero production files import getLegacyFeatureLinkedSessions (P5-006 hard gate)', () => {
    const violations = detectGateMissing();
    expect(
      violations,
      `Unapproved getLegacyFeatureLinkedSessions production importer found after P5-006 retirement:\n\n${formatViolations(violations)}\n`,
    ).toHaveLength(0);
  });

  it('scan covers at least the known consumer production files', () => {
    const knownFiles = [
      'components/ProjectBoard.tsx',
      'components/SessionInspector.tsx',
      'components/FeatureExecutionWorkbench.tsx',
      'components/Dashboard.tsx',
      'components/BlockingFeatureList.tsx',
      'services/featureSurface.ts',
      'services/useFeatureModalData.ts',
    ];

    const relPaths = productionFiles.map(f => relative(ROOT, f));
    for (const known of knownFiles) {
      expect(relPaths, `Expected ${known} to be in the production scan set`).toContain(known);
    }
  });

  it('allowlist files each exist on disk', () => {
    for (const relPath of ALLOWED_LEGACY_IMPORTERS) {
      const absPath = resolve(ROOT, relPath);
      let exists = false;
      try {
        statSync(absPath);
        exists = true;
      } catch {
        exists = false;
      }
      expect(
        exists,
        `Allowlisted file ${relPath} does not exist — remove it from ALLOWED_LEGACY_IMPORTERS`,
      ).toBe(true);
    }
  });

  it('production scan excludes test files', () => {
    const testFilesInScan = productionFiles.filter(f => isTestFile(basename(f)) || isInTestDir(f));
    expect(
      testFilesInScan,
      `Test files should not be in the production scan:\n${testFilesInScan.map(f => '  ' + relative(ROOT, f)).join('\n')}`,
    ).toHaveLength(0);
  });
});
