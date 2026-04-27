/**
 * memory-profile.mjs — Tab memory load-test harness (FE-107)
 *
 * Launches a headless Chromium tab, samples `performance.memory.usedJSHeapSize`
 * at a configurable interval, and writes a JSON time-series to artifacts/.
 *
 * Usage:
 *   npm run profile:memory -- [options]
 *   node ./scripts/memory-profile.mjs [options]
 *
 * Options:
 *   --url          Base URL to load (default: http://localhost:3000)
 *   --duration-ms  Total sampling duration in ms (default: 3600000 = 60 min)
 *   --interval-ms  Sampling interval in ms (default: 60000 = 1 min)
 *   --headed       Disable headless mode (shows the browser window)
 *   --out-dir      Output directory (default: artifacts)
 *
 * Examples:
 *   # Full 60-min idle run
 *   npm run profile:memory -- --url http://localhost:3000 --duration-ms 3600000 --interval-ms 60000
 *
 *   # Quick 1-min smoke run
 *   npm run profile:memory -- --url http://localhost:3000 --duration-ms 60000 --interval-ms 10000
 *
 *   # 5-second sanity check against about:blank
 *   node ./scripts/memory-profile.mjs --url about:blank --duration-ms 5000 --interval-ms 1000
 */

import { mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------

/**
 * Parse CLI args of the form --key value or --flag.
 * Exported so a Vitest test can exercise it independently.
 */
export function parseArgs(argv) {
  const args = {
    url: 'http://localhost:3000',
    durationMs: 3_600_000,
    intervalMs: 60_000,
    headed: false,
    outDir: 'artifacts',
  };

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--url') args.url = argv[++i];
    else if (arg === '--duration-ms') args.durationMs = Number(argv[++i]);
    else if (arg === '--interval-ms') args.intervalMs = Number(argv[++i]);
    else if (arg === '--headed') args.headed = true;
    else if (arg === '--out-dir') args.outDir = argv[++i];
    else if (arg.startsWith('--url=')) args.url = arg.slice(6);
    else if (arg.startsWith('--duration-ms=')) args.durationMs = Number(arg.slice(14));
    else if (arg.startsWith('--interval-ms=')) args.intervalMs = Number(arg.slice(14));
    else if (arg.startsWith('--out-dir=')) args.outDir = arg.slice(10);
  }

  if (!Number.isFinite(args.durationMs) || args.durationMs <= 0)
    throw new Error(`Invalid --duration-ms: ${args.durationMs}`);
  if (!Number.isFinite(args.intervalMs) || args.intervalMs <= 0)
    throw new Error(`Invalid --interval-ms: ${args.intervalMs}`);

  return args;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const args = parseArgs(process.argv.slice(2));

  console.log('[memory-profile] Starting with config:');
  console.log(`  url         : ${args.url}`);
  console.log(`  duration    : ${args.durationMs} ms (${(args.durationMs / 60_000).toFixed(1)} min)`);
  console.log(`  interval    : ${args.intervalMs} ms`);
  console.log(`  headed      : ${args.headed}`);
  console.log(`  output dir  : ${args.outDir}`);

  // Dynamically import puppeteer so the module parses even if it isn't installed
  // (lets arg-parse tests run without the full browser dep).
  let puppeteer;
  try {
    puppeteer = (await import('puppeteer')).default;
  } catch {
    console.error(
      '[memory-profile] ERROR: puppeteer is not installed.\n' +
        '  Run: pnpm add -D puppeteer\n' +
        '  Then retry.'
    );
    process.exit(1);
  }

  const browser = await puppeteer.launch({
    headless: !args.headed,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });

  // Best-effort navigation — about:blank is always fine; dev server might 404
  try {
    await page.goto(args.url, { waitUntil: 'networkidle2', timeout: 30_000 });
  } catch (err) {
    console.warn(`[memory-profile] Navigation warning (continuing): ${err.message}`);
  }

  const userAgent = await page.evaluate(() => navigator.userAgent);
  const viewport = page.viewport();
  const startedAt = new Date().toISOString();
  const samples = [];

  console.log(`\n[memory-profile] Sampling started at ${startedAt}`);
  console.log('  Press Ctrl-C to stop early and flush results.\n');

  let done = false;

  // Collect a single sample
  const takeSample = async (tMs) => {
    try {
      const result = await page.evaluate(() => {
        const mem = performance.memory;
        if (!mem) return null;
        return {
          usedJSHeapSize: mem.usedJSHeapSize,
          totalJSHeapSize: mem.totalJSHeapSize,
        };
      });

      const usedJSHeapMB = result ? +(result.usedJSHeapSize / 1_048_576).toFixed(3) : null;
      const totalJSHeapMB = result ? +(result.totalJSHeapSize / 1_048_576).toFixed(3) : null;
      samples.push({ tMs, usedJSHeapMB, totalJSHeapMB });
      console.log(
        `  t=${String(tMs).padStart(8)} ms  used=${usedJSHeapMB !== null ? usedJSHeapMB + ' MB' : 'n/a (no performance.memory)'}`
      );
    } catch (err) {
      console.warn(`  t=${tMs} ms  sample error: ${err.message}`);
      samples.push({ tMs, usedJSHeapMB: null, totalJSHeapMB: null, error: err.message });
    }
  };

  // Flush results to disk
  const flush = async () => {
    const outDir = resolve(ROOT, args.outDir);
    if (!existsSync(outDir)) await mkdir(outDir, { recursive: true });

    const ts = startedAt.replace(/[:.]/g, '-').replace('T', '_').slice(0, 19);
    const outFile = resolve(outDir, `memory-profile-${ts}.json`);

    const payload = {
      url: args.url,
      startedAt,
      intervalMs: args.intervalMs,
      durationMs: args.durationMs,
      samples,
      metadata: { userAgent, viewport },
    };

    await writeFile(outFile, JSON.stringify(payload, null, 2));
    console.log(`\n[memory-profile] Results written to: ${outFile}`);
    return { outFile, payload };
  };

  // Summary printer
  const printSummary = (samples) => {
    const valid = samples.filter((s) => s.usedJSHeapMB !== null);
    if (valid.length === 0) {
      console.log('[memory-profile] No valid samples (performance.memory may be unavailable).');
      return;
    }
    const values = valid.map((s) => s.usedJSHeapMB);
    const baseline = values[0];
    const peak = Math.max(...values);
    const final = values[values.length - 1];
    const delta = +(final - baseline).toFixed(3);

    console.log('\n[memory-profile] Summary:');
    console.log(`  samples  : ${valid.length}`);
    console.log(`  baseline : ${baseline} MB`);
    console.log(`  peak     : ${peak} MB`);
    console.log(`  final    : ${final} MB`);
    console.log(`  delta    : ${delta > 0 ? '+' : ''}${delta} MB`);
  };

  // SIGINT handler — flush partial data
  const sigintHandler = async () => {
    if (done) return;
    done = true;
    console.log('\n[memory-profile] Interrupted — flushing partial results...');
    try {
      const { outFile } = await flush();
      printSummary(samples);
      console.log('[memory-profile] Partial results flushed to', outFile);
    } catch (err) {
      console.error('[memory-profile] Flush error:', err.message);
    }
    await browser.close().catch(() => {});
    process.exit(0);
  };

  process.on('SIGINT', sigintHandler);

  // Sampling loop
  const startTime = Date.now();
  await takeSample(0);

  await new Promise((resolveLoop) => {
    const intervalHandle = setInterval(async () => {
      if (done) return;
      const tMs = Date.now() - startTime;
      await takeSample(tMs);

      if (tMs >= args.durationMs - args.intervalMs / 2) {
        clearInterval(intervalHandle);
        resolveLoop();
      }
    }, args.intervalMs);

    // Safety timeout to avoid running forever if interval math drifts
    setTimeout(() => {
      clearInterval(intervalHandle);
      resolveLoop();
    }, args.durationMs + args.intervalMs);
  });

  done = true;
  process.off('SIGINT', sigintHandler);

  const { outFile } = await flush();
  printSummary(samples);
  console.log(`[memory-profile] Done. Output: ${outFile}`);

  await browser.close();
}

main().catch((err) => {
  console.error('[memory-profile] Fatal error:', err);
  process.exit(1);
});
