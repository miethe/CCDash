import { describe, expect, it } from 'vitest';

import {
  buildApiUrl,
  normalizeApiBaseUrl,
  resolveApiBaseUrl,
  resolveLiveStreamBaseUrl,
} from '../runtimeBase';

describe('runtimeBase', () => {
  it('defaults to the same-origin API path', () => {
    expect(resolveApiBaseUrl({})).toBe('/api');
    expect(buildApiUrl('/health', {})).toBe('/api/health');
    expect(resolveLiveStreamBaseUrl({})).toBe('/api/live/stream');
  });

  it('normalizes relative configured base paths', () => {
    expect(normalizeApiBaseUrl('api/')).toBe('/api');
    expect(buildApiUrl('/health', { VITE_CCDASH_API_BASE_URL: 'api/' })).toBe('/api/health');
  });

  it('preserves absolute hosted API base URLs', () => {
    const env = { VITE_CCDASH_API_BASE_URL: 'https://api.example.com/api/' };
    expect(resolveApiBaseUrl(env)).toBe('https://api.example.com/api');
    expect(buildApiUrl('/health/detail', env)).toBe('https://api.example.com/api/health/detail');
    expect(resolveLiveStreamBaseUrl(env)).toBe('https://api.example.com/api/live/stream');
  });
});
