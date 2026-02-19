import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { delimiter, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);

const readArg = (flag, fallback) => {
  const index = args.indexOf(flag);
  if (index === -1 || index + 1 >= args.length) return fallback;
  return args[index + 1];
};

const hasFlag = (flag) => args.includes(flag);

const host = readArg('--host', process.env.CCDASH_BACKEND_HOST || '127.0.0.1');
const port = Number.parseInt(readArg('--port', process.env.CCDASH_BACKEND_PORT || process.env.PORT || '8000'), 10);
const reload = hasFlag('--reload');

if (!Number.isInteger(port) || port < 1 || port > 65535) {
  console.error(`[backend] invalid backend port: ${readArg('--port', process.env.CCDASH_BACKEND_PORT || process.env.PORT)}`);
  process.exit(1);
}

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
  console.error('[backend] no Python interpreter found. Run `npm run setup` first.');
  process.exit(1);
}

const pythonPrefix = pythonExec === 'py' ? ['-3'] : [];

const uvicornCheck = spawnSync(pythonExec, [...pythonPrefix, '-c', 'import uvicorn'], {
  cwd: root,
  stdio: 'ignore',
});
if (uvicornCheck.status !== 0) {
  console.error('[backend] uvicorn is not installed in the selected Python environment.');
  console.error('[backend] Run `npm run setup` to install backend dependencies.');
  process.exit(1);
}

const backendEnv = {
  ...process.env,
  PYTHONPATH: process.env.PYTHONPATH ? `${root}${delimiter}${process.env.PYTHONPATH}` : root,
};

const uvicornArgs = [
  ...pythonPrefix,
  '-m',
  'uvicorn',
  'backend.main:app',
  '--host',
  host,
  '--port',
  String(port),
];
if (reload) {
  uvicornArgs.push('--reload');
}

console.log(`[backend] Python: ${pythonExec}`);
console.log(`[backend] Starting backend at http://${host}:${port}${reload ? ' (reload)' : ''}`);

const backend = spawn(pythonExec, uvicornArgs, {
  cwd: root,
  env: backendEnv,
  stdio: 'inherit',
});

const shutdown = () => {
  if (!backend.killed && backend.exitCode === null) {
    try {
      backend.kill('SIGTERM');
    } catch {
      // ignore
    }
  }
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

backend.on('exit', (code, signal) => {
  if (signal === 'SIGTERM') {
    process.exit(0);
    return;
  }
  process.exit(code ?? 1);
});
