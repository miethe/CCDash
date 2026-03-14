#!/usr/bin/env node

/**
 * README Build Script
 * Compiles README.md from Handlebars templates, partials, and JSON data files.
 *
 * Usage:
 *   node scripts/build-readme.js [--dry-run] [--root <path>] [--verbose]
 */

import { readFileSync, writeFileSync, readdirSync, existsSync } from 'fs';
import { resolve, basename, extname, join } from 'path';
import Handlebars from 'handlebars';

// --- CLI args ---
const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');
const verbose = args.includes('--verbose');
const rootIdx = args.indexOf('--root');
const rootDir = rootIdx !== -1 ? resolve(args[rootIdx + 1]) : resolve(import.meta.dirname, '..');

const dataDir = join(rootDir, 'data');
const partialsDir = join(rootDir, 'partials');
const templatesDir = join(rootDir, 'templates');
const projectRoot = resolve(rootDir, '..', '..');
const outputPath = join(projectRoot, 'README.md');

// --- Register Handlebars helpers ---

Handlebars.registerHelper('formatDate', (dateStr, format) => {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  if (format === 'short') return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  return d.toLocaleDateString();
});

Handlebars.registerHelper('isoDate', () => new Date().toISOString());

Handlebars.registerHelper('eq', (a, b) => a === b);

Handlebars.registerHelper('count', (arr) => Array.isArray(arr) ? arr.length : 0);

Handlebars.registerHelper('join', (arr, sep) => Array.isArray(arr) ? arr.join(typeof sep === 'string' ? sep : ', ') : '');

Handlebars.registerHelper('isOdd', (n) => n % 2 === 1);

Handlebars.registerHelper('filter', function (items, key, value, options) {
  if (!Array.isArray(items)) return '';
  return items.filter(i => i[key] === value).map(i => options.fn(i)).join('');
});

Handlebars.registerHelper('highlightedFeatures', (categories) => {
  if (!Array.isArray(categories)) return [];
  return categories.flatMap(c => (c.items || []).filter(f => f.highlight));
});

Handlebars.registerHelper('screenshotsByCategory', (screenshots, category) => {
  if (!Array.isArray(screenshots)) return [];
  return screenshots.filter(s => s.category === category && s.status === 'captured');
});

Handlebars.registerHelper('totalFeatures', (categories) => {
  if (!Array.isArray(categories)) return 0;
  return categories.reduce((sum, c) => sum + (c.items || []).length, 0);
});

Handlebars.registerHelper('hasCliCommands', (categories) => {
  if (!Array.isArray(categories)) return false;
  return categories.some(c => (c.items || []).some(f => f.cliCommand));
});

Handlebars.registerHelper('cliCommands', (categories) => {
  if (!Array.isArray(categories)) return '';
  return categories
    .flatMap(c => (c.items || []).filter(f => f.cliCommand).map(f => f.cliCommand))
    .join(', ');
});

// --- Load data files ---
function loadData() {
  const data = {};
  if (!existsSync(dataDir)) return data;
  for (const file of readdirSync(dataDir)) {
    if (extname(file) !== '.json') continue;
    const key = basename(file, '.json');
    try {
      data[key] = JSON.parse(readFileSync(join(dataDir, file), 'utf-8'));
    } catch (e) {
      console.error(`Error parsing ${file}: ${e.message}`);
      process.exit(1);
    }
  }
  return data;
}

// --- Register partials ---
function registerPartials() {
  if (!existsSync(partialsDir)) return;
  for (const file of readdirSync(partialsDir)) {
    if (extname(file) !== '.md') continue;
    const name = basename(file, '.md');
    const content = readFileSync(join(partialsDir, file), 'utf-8');
    Handlebars.registerPartial(name, content);
    if (verbose) console.log(`  Registered partial: ${name}`);
  }
}

// --- Main ---
function main() {
  console.log(`Building README from ${rootDir}`);
  if (dryRun) console.log('  (dry-run mode — output to stdout)\n');

  // Load template
  const templatePath = join(templatesDir, 'README.hbs');
  if (!existsSync(templatePath)) {
    console.error(`Template not found: ${templatePath}`);
    process.exit(1);
  }
  const templateSource = readFileSync(templatePath, 'utf-8');

  // Load data and partials
  const data = loadData();
  registerPartials();

  if (verbose) {
    console.log(`  Data keys: ${Object.keys(data).join(', ')}`);
    console.log(`  Output: ${outputPath}\n`);
  }

  // Compile and render
  const template = Handlebars.compile(templateSource, { noEscape: true });
  const output = template(data);

  if (dryRun) {
    console.log(output);
  } else {
    writeFileSync(outputPath, output, 'utf-8');
    console.log(`\nGenerated: ${outputPath}`);
  }
}

main();
