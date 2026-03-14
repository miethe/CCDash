#!/usr/bin/env node

/**
 * Version Updater
 * Updates data/version.json with a new version string and today's date.
 *
 * Usage:
 *   node scripts/update-version.js --version <semver> [--root <path>]
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { resolve, join } from 'path';

const args = process.argv.slice(2);
const rootIdx = args.indexOf('--root');
const rootDir = rootIdx !== -1 ? resolve(args[rootIdx + 1]) : resolve(import.meta.dirname, '..');
const versionIdx = args.indexOf('--version');

if (versionIdx === -1 || !args[versionIdx + 1]) {
  console.error('Usage: update-version.js --version <semver>');
  process.exit(1);
}

const newVersion = args[versionIdx + 1];
const versionPath = join(rootDir, 'data', 'version.json');

if (!existsSync(versionPath)) {
  console.error(`version.json not found at ${versionPath}`);
  process.exit(1);
}

const data = JSON.parse(readFileSync(versionPath, 'utf-8'));
const previous = { version: data.current, releaseDate: data.releaseDate };

data.current = newVersion;
data.releaseDate = new Date().toISOString().split('T')[0];

if (!data.previousVersions) data.previousVersions = [];
data.previousVersions.unshift(previous);

writeFileSync(versionPath, JSON.stringify(data, null, 2) + '\n', 'utf-8');
console.log(`Updated version: ${previous.version} -> ${newVersion} (${data.releaseDate})`);
