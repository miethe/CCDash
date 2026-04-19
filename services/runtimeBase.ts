export interface FrontendRuntimeEnv {
  readonly VITE_CCDASH_API_BASE_URL?: string;
}

export const DEFAULT_API_BASE_URL = '/api';

const ABSOLUTE_URL_PATTERN = /^[a-zA-Z][a-zA-Z\d+\-.]*:\/\//;

const trimTrailingSlash = (value: string): string => {
  if (value === '/') {
    return value;
  }
  return value.replace(/\/+$/, '');
};

export const normalizeApiBaseUrl = (rawValue: string | null | undefined): string => {
  const trimmed = rawValue?.trim();
  if (!trimmed) {
    return DEFAULT_API_BASE_URL;
  }
  if (ABSOLUTE_URL_PATTERN.test(trimmed) || trimmed.startsWith('//')) {
    return trimTrailingSlash(trimmed);
  }
  const normalizedPath = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
  return trimTrailingSlash(normalizedPath) || DEFAULT_API_BASE_URL;
};

const joinRuntimeBase = (baseUrl: string, path: string): string => {
  if (!path) {
    return baseUrl;
  }
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${trimTrailingSlash(baseUrl)}${normalizedPath}`;
};

export const resolveApiBaseUrl = (env: FrontendRuntimeEnv = import.meta.env as FrontendRuntimeEnv): string =>
  normalizeApiBaseUrl(env.VITE_CCDASH_API_BASE_URL);

export const buildApiUrl = (path: string, env?: FrontendRuntimeEnv): string =>
  joinRuntimeBase(resolveApiBaseUrl(env), path);

export const resolveLiveStreamBaseUrl = (env?: FrontendRuntimeEnv): string =>
  buildApiUrl('/live/stream', env);
