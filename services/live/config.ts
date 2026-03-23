const readBooleanEnv = (value: unknown, defaultValue: boolean): boolean => {
  if (typeof value !== 'string' || !value.trim()) return defaultValue;
  const normalized = value.trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].includes(normalized)) return true;
  if (['0', 'false', 'no', 'off'].includes(normalized)) return false;
  return defaultValue;
};

export const isExecutionLiveUpdatesEnabled = (): boolean => (
  readBooleanEnv(import.meta.env.VITE_CCDASH_LIVE_EXECUTION_ENABLED, true)
);

export const isSessionLiveUpdatesEnabled = (): boolean => (
  readBooleanEnv(import.meta.env.VITE_CCDASH_LIVE_SESSIONS_ENABLED, true)
);

export const isSessionTranscriptAppendEnabled = (): boolean => (
  readBooleanEnv(import.meta.env.VITE_CCDASH_LIVE_SESSION_TRANSCRIPT_APPEND_ENABLED, false)
);

export const isFeatureLiveUpdatesEnabled = (): boolean => (
  readBooleanEnv(import.meta.env.VITE_CCDASH_LIVE_FEATURES_ENABLED, false)
);

export const isTestLiveUpdatesEnabled = (): boolean => (
  readBooleanEnv(import.meta.env.VITE_CCDASH_LIVE_TESTS_ENABLED, false)
);

export const isOpsLiveUpdatesEnabled = (): boolean => (
  readBooleanEnv(import.meta.env.VITE_CCDASH_LIVE_OPS_ENABLED, false)
);
