#!/usr/bin/env node

/**
 * Link Validator
 * Checks that all relative links and image references in README.md resolve to existing files.
 *
 * Usage:
 *   node scripts/validate-links.js [--root <path>] [--check-external]
 */

import { readFileSync, existsSync } from 'fs';
import { resolve, join, dirname } from 'path';

const args = process.argv.slice(2);
const rootIdx = args.indexOf('--root');
const rootDir = rootIdx !== -1 ? resolve(args[rootIdx + 1]) : resolve(import.meta.dirname, '..');
const checkExternal = args.includes('--check-external');
const projectRoot = resolve(rootDir, '..', '..');
const readmePath = join(projectRoot, 'README.md');

if (!existsSync(readmePath)) {
  console.error(`README.md not found at ${readmePath}`);
  process.exit(1);
}

const content = readFileSync(readmePath, 'utf-8');

// Match markdown links: [text](url) and images: ![alt](url)
const linkPattern = /!?\[([^\]]*)\]\(([^)]+)\)/g;
const errors = [];
let match;

while ((match = linkPattern.exec(content)) !== null) {
  const [full, , url] = match;
  // Skip external URLs, anchors, and mailto
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('#') || url.startsWith('mailto:')) {
    if (checkExternal && (url.startsWith('http://') || url.startsWith('https://'))) {
      // External check would go here (not implemented for offline use)
    }
    continue;
  }

  // Strip anchor from relative paths
  const cleanUrl = url.split('#')[0];
  if (!cleanUrl) continue;

  const targetPath = resolve(dirname(readmePath), cleanUrl);
  if (!existsSync(targetPath)) {
    errors.push({ link: full, target: cleanUrl, resolved: targetPath });
  }
}

if (errors.length > 0) {
  console.error(`Found ${errors.length} broken link(s) in README.md:\n`);
  for (const err of errors) {
    console.error(`  - ${err.target}`);
    console.error(`    Resolved to: ${err.resolved}`);
    console.error(`    In: ${err.link}\n`);
  }
  process.exit(1);
} else {
  console.log(`All links in README.md are valid.`);
  process.exit(0);
}
