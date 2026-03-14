#!/usr/bin/env node

/**
 * Screenshot Checker
 * Verifies that screenshot files referenced in data/screenshots.json exist on disk.
 *
 * Usage:
 *   node scripts/check-screenshots.js [--root <path>] [--required-only]
 */

import { readFileSync, existsSync } from 'fs';
import { resolve, join } from 'path';

const args = process.argv.slice(2);
const rootIdx = args.indexOf('--root');
const rootDir = rootIdx !== -1 ? resolve(args[rootIdx + 1]) : resolve(import.meta.dirname, '..');
const requiredOnly = args.includes('--required-only');
const projectRoot = resolve(rootDir, '..', '..');

const screenshotsPath = join(rootDir, 'data', 'screenshots.json');
if (!existsSync(screenshotsPath)) {
  console.log('No screenshots.json found — skipping.');
  process.exit(0);
}

let data;
try {
  data = JSON.parse(readFileSync(screenshotsPath, 'utf-8'));
} catch (e) {
  console.error(`Error parsing screenshots.json: ${e.message}`);
  process.exit(1);
}

const items = [...(data.screenshots || []), ...(data.gifs || [])];
const errors = [];
const warnings = [];

for (const item of items) {
  if (requiredOnly && item.status === 'pending') continue;

  if (item.status === 'captured') {
    const filePath = resolve(projectRoot, item.file);
    if (!existsSync(filePath)) {
      errors.push({ id: item.id, file: item.file, resolved: filePath });
    }
  }

  if (item.status === 'outdated') {
    warnings.push({ id: item.id, file: item.file, notes: item.notes });
  }
}

if (warnings.length > 0) {
  console.warn(`${warnings.length} outdated screenshot(s):`);
  for (const w of warnings) {
    console.warn(`  - ${w.id}: ${w.file} (${w.notes || 'needs refresh'})`);
  }
  console.warn('');
}

if (errors.length > 0) {
  console.error(`${errors.length} missing screenshot file(s):\n`);
  for (const err of errors) {
    console.error(`  - ${err.id}: ${err.file}`);
    console.error(`    Expected at: ${err.resolved}\n`);
  }
  process.exit(1);
} else {
  const total = items.filter(i => i.status === 'captured').length;
  console.log(`All ${total} captured screenshot(s) found.`);
  process.exit(0);
}
