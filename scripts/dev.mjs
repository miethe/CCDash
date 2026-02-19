import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);

const backendHost = process.env.CCDASH_BACKEND_HOST || '127.0.0.1';
const backendPort = Number.parseInt(process.env.CCDASH_BACKEND_PORT || '8000', 10);
const backendWaitHost = process.env.CCDASH_BACKEND_WAIT_HOST || (backendHost === '0.0.0.0' ? '127.0.0.1' : backendHost);

if (!Number.isInteger(backendPort) || backendPort < 1 || backendPort > 65535) {
  console.error(`[dev] invalid CCDASH_BACKEND_PORT value: ${process.env.CCDASH_BACKEND_PORT}`);
  process.exit(1);
}

const sleep = (ms) => new Promise((resolveSleep) => setTimeout(resolveSleep, ms));

const isBackendHealthy = async () => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 600);
  try {
    const response = await fetch(`http://${backendWaitHost}:${backendPort}/api/health`, {
      method: 'GET',
      signal: controller.signal,
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
};

const waitForBackendHealth = async (timeoutMs, isBackendProcessAlive) => {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await isBackendHealthy()) {
      return true;
    }
    if (!isBackendProcessAlive()) {
      return false;
    }
    await sleep(250);
  }
  return false;
};

const run = async () => {
  const children = [];
  let shuttingDown = false;
  let backend = null;
  let backendSpawnedByDev = false;

  const viteBin = resolve(root, 'node_modules/vite/bin/vite.js');
  const viteCommand = existsSync(viteBin) ? process.execPath : 'vite';
  const viteArgs = existsSync(viteBin) ? [viteBin, ...args] : args;

  if (await isBackendHealthy()) {
    console.log(`[dev] backend already healthy on ${backendWaitHost}:${backendPort}, reusing it`);
  } else {
    console.log('[dev] starting backend');
    backendSpawnedByDev = true;
    backend = spawn(
      process.execPath,
      [
        resolve(root, 'scripts/backend.mjs'),
        '--reload',
        '--host',
        backendHost,
        '--port',
        String(backendPort),
      ],
      {
        cwd: root,
        env: process.env,
        stdio: 'inherit',
      },
    );
    children.push(backend);

    const backendReady = await waitForBackendHealth(30000, () => backend && backend.exitCode === null);
    if (!backendReady) {
      console.error('[dev] backend did not become healthy within 30 seconds');
      if (backend && backend.exitCode === null) {
        backend.kill('SIGTERM');
      }
      process.exit(1);
    }
    console.log(`[dev] backend healthy at http://${backendWaitHost}:${backendPort}/api/health`);
  }

  console.log('[dev] starting frontend');
  const frontend = spawn(viteCommand, viteArgs, {
    cwd: root,
    env: process.env,
    stdio: 'inherit',
  });
  children.push(frontend);

  const shutdown = (exitCode) => {
    if (shuttingDown) return;
    shuttingDown = true;
    for (const child of children) {
      if (!child || child.killed) continue;
      try {
        child.kill('SIGTERM');
      } catch {
        // ignore
      }
    }
    setTimeout(() => process.exit(exitCode), 250);
  };

  process.on('SIGINT', () => shutdown(130));
  process.on('SIGTERM', () => shutdown(0));

  frontend.on('exit', (code) => {
    shutdown(code ?? 0);
  });

  if (backendSpawnedByDev && backend) {
    backend.on('exit', (code, signal) => {
      if (shuttingDown) return;
      if (signal === 'SIGTERM' || code === 0) return;
      console.error(`[dev] backend exited unexpectedly (code=${code ?? 'n/a'} signal=${signal ?? 'n/a'})`);
      shutdown(1);
    });
  }
};

run().catch((error) => {
  console.error('[dev] failed to start dev environment');
  console.error(error);
  process.exit(1);
});
