import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const requirementsPath = resolve(root, 'backend/requirements.txt');
const venvPython = process.platform === 'win32'
  ? resolve(root, 'backend/.venv/Scripts/python.exe')
  : resolve(root, 'backend/.venv/bin/python');

const run = (cmd, args, label) => {
  console.log(`[setup] ${label}`);
  const result = spawnSync(cmd, args, {
    cwd: root,
    stdio: 'inherit',
    env: process.env,
  });
  if (result.status !== 0) {
    throw new Error(`step failed: ${cmd} ${args.join(' ')}`);
  }
};

const chooseBootstrapPython = () => {
  const candidates = [
    process.env.CCDASH_PYTHON || '',
    process.platform === 'win32' ? 'py' : 'python3',
    'python',
  ].filter(Boolean);
  const visited = new Set();
  for (const candidate of candidates) {
    if (visited.has(candidate)) continue;
    visited.add(candidate);
    const probeArgs = candidate === 'py' ? ['-3', '-c', 'import sys'] : ['-c', 'import sys'];
    const probe = spawnSync(candidate, probeArgs, { cwd: root, stdio: 'ignore' });
    if (probe.status === 0) {
      return candidate;
    }
  }
  return null;
};

try {
  if (!existsSync(requirementsPath)) {
    throw new Error(`missing backend requirements file at ${requirementsPath}`);
  }

  if (!existsSync(venvPython)) {
    const bootstrapPython = chooseBootstrapPython();
    if (!bootstrapPython) {
      throw new Error('no Python interpreter found (python3/python).');
    }
    const bootstrapArgs = bootstrapPython === 'py' ? ['-3', '-m', 'venv', 'backend/.venv'] : ['-m', 'venv', 'backend/.venv'];
    run(bootstrapPython, bootstrapArgs, 'Creating backend virtual environment');
  } else {
    console.log('[setup] backend virtual environment already exists');
  }

  run(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip'], 'Upgrading pip in backend virtual environment');
  run(venvPython, ['-m', 'pip', 'install', '-r', 'backend/requirements.txt'], 'Installing backend dependencies');

  console.log('[setup] complete');
  console.log('[setup] Next: run `npm run dev`');
} catch (error) {
  console.error('[setup] failed');
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
}
