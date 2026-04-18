import path from 'path';
import type { ProxyOptions } from 'vite';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

const DEFAULT_FRONTEND_PORT = '3000';
const DEFAULT_BACKEND_PORT = '8000';
const DEFAULT_API_BASE_URL = '/api';

const trimTrailingSlash = (value: string): string => {
  if (value === '/') {
    return value;
  }
  return value.replace(/\/+$/, '');
};

const normalizeApiBaseUrl = (value: string | undefined): string => {
  const trimmed = value?.trim();
  if (!trimmed) {
    return DEFAULT_API_BASE_URL;
  }
  if (/^[a-zA-Z][a-zA-Z\d+\-.]*:\/\//.test(trimmed) || trimmed.startsWith('//')) {
    return trimTrailingSlash(trimmed);
  }
  return trimTrailingSlash(trimmed.startsWith('/') ? trimmed : `/${trimmed}`) || DEFAULT_API_BASE_URL;
};

const validateHostedApiBaseUrl = (apiBaseUrl: string): void => {
  if (apiBaseUrl === DEFAULT_API_BASE_URL) {
    return;
  }
  if (!apiBaseUrl.endsWith('/api')) {
    throw new Error(
      `[vite] VITE_CCDASH_API_BASE_URL must include the backend API base path and end with /api. Received: ${apiBaseUrl}`,
    );
  }
};

const resolveProxyTarget = (
  env: Record<string, string>,
  fallbackBackendPort: string,
  apiBaseUrl: string,
): string => {
  const configuredProxyTarget = env.CCDASH_API_PROXY_TARGET?.trim();
  if (configuredProxyTarget) {
    return trimTrailingSlash(configuredProxyTarget);
  }
  if (/^[a-zA-Z][a-zA-Z\d+\-.]*:\/\//.test(apiBaseUrl)) {
    return trimTrailingSlash(new URL(apiBaseUrl).origin);
  }
  return `http://127.0.0.1:${fallbackBackendPort}`;
};

const createApiProxy = (target: string): Record<string, string | ProxyOptions> => ({
  '/api': {
    target,
    changeOrigin: true,
  },
});

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const backendPort = env.CCDASH_BACKEND_PORT || DEFAULT_BACKEND_PORT;
  const apiBaseUrl = normalizeApiBaseUrl(env.VITE_CCDASH_API_BASE_URL);
  const proxyTarget = resolveProxyTarget(env, backendPort, apiBaseUrl);
  const proxy = createApiProxy(proxyTarget);

  validateHostedApiBaseUrl(apiBaseUrl);

  return {
    server: {
      port: Number.parseInt(env.VITE_PORT || DEFAULT_FRONTEND_PORT, 10),
      host: '0.0.0.0',
      proxy,
    },
    preview: {
      port: Number.parseInt(env.VITE_PORT || DEFAULT_FRONTEND_PORT, 10),
      host: '0.0.0.0',
      proxy,
    },
    plugins: [react()],
    define: {
      'process.env.API_KEY': JSON.stringify(env.GEMINI_API_KEY),
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      }
    },
  };
});
