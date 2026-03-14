import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { delimiter, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const venvPython = process.platform === 'win32'
  ? resolve(root, 'backend/.venv/Scripts/python.exe')
  : resolve(root, 'backend/.venv/bin/python');

const candidateExecutables = [
  process.env.CCDASH_PYTHON || '',
  venvPython,
  process.platform === 'win32' ? 'py' : 'python3',
  'python',
].filter(Boolean);

const choosePythonExecutable = () => {
  const visited = new Set();
  for (const candidate of candidateExecutables) {
    if (visited.has(candidate)) continue;
    visited.add(candidate);
    const isPath = candidate.includes('/') || candidate.includes('\\');
    if (isPath && !existsSync(candidate)) {
      continue;
    }
    const probeArgs = candidate === 'py' ? ['-3', '-c', 'import sys'] : ['-c', 'import sys'];
    const probe = spawnSync(candidate, probeArgs, { cwd: root, stdio: 'ignore' });
    if (probe.status === 0) {
      return candidate;
    }
  }
  return null;
};

const pythonExec = choosePythonExecutable();
if (!pythonExec) {
  console.error('[worker] no Python interpreter found. Run `npm run setup` first.');
  process.exit(1);
}

const pythonPrefix = pythonExec === 'py' ? ['-3'] : [];
const workerEnv = {
  ...process.env,
  PYTHONPATH: process.env.PYTHONPATH ? `${root}${delimiter}${process.env.PYTHONPATH}` : root,
};

console.log(`[worker] Python: ${pythonExec}`);
console.log('[worker] Starting background worker');

const worker = spawn(pythonExec, [...pythonPrefix, '-m', 'backend.worker'], {
  cwd: root,
  env: workerEnv,
  stdio: 'inherit',
});

const shutdown = () => {
  if (!worker.killed && worker.exitCode === null) {
    try {
      worker.kill('SIGTERM');
    } catch {
      // ignore
    }
  }
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

worker.on('exit', (code, signal) => {
  if (signal === 'SIGTERM') {
    process.exit(0);
    return;
  }
  process.exit(code ?? 1);
});
