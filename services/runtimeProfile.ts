import type {
  RuntimeHealthResponse,
  RuntimeProbeActivityResponse,
  RuntimeProbeContractResponse,
  RuntimeProbeReasonResponse,
  RuntimeProbeSectionResponse,
} from './apiClient';

export interface RuntimeProbeReason {
  code: string;
  category: string;
  severity: string;
  message: string;
  detail: string;
  source: string;
}

export interface RuntimeProbeActivity {
  name: string;
  state: string;
  status: string;
  detail: string;
  code: string;
  severity: string;
}

export interface RuntimeProbeSection {
  state: string;
  status: string;
  summary: string;
  detail: string;
  reasons: RuntimeProbeReason[];
  activities: RuntimeProbeActivity[];
}

export interface RuntimeProbeContract {
  schemaVersion: string;
  live: RuntimeProbeSection;
  ready: RuntimeProbeSection;
  detail: RuntimeProbeSection;
  probeReadyState: string;
  probeReadyStatus: string;
  probeDegraded: boolean | null;
  degradedReasons: RuntimeProbeReason[];
  degradedReasonCodes: string[];
}

export interface RuntimeStatus {
  health: string;
  database: string;
  watcher: string;
  profile: string;
  schemaVersion: string;
  probeReadyState: string;
  probeReadyStatus: string;
  probeDegraded: boolean | null;
  degradedReasons: RuntimeProbeReason[];
  degradedReasonCodes: string[];
  probeContract: RuntimeProbeContract;
  startupSync: string;
  analyticsSnapshots: string;
  telemetryExports: string;
  jobsEnabled: boolean | null;
  storageMode: string;
  storageProfile: string;
  storageBackend: string;
  recommendedStorageProfile: string;
  supportedStorageProfiles: string[];
  filesystemSourceOfTruth: boolean | null;
  sharedPostgresEnabled: boolean | null;
  storageIsolationMode: string;
  supportedStorageIsolationModes: string[];
  storageCanonicalStore: string;
  storageSchema: string;
  canonicalSessionStore: string;
}

function normalizeText(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback;
  const clean = value.trim();
  return clean || fallback;
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map(item => (typeof item === 'string' ? item.trim() : ''))
    .filter(Boolean);
}

function normalizeBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function normalizeObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function inferJobsEnabled(profile: string): boolean | null {
  if (profile === 'local' || profile === 'worker') return true;
  if (profile === 'api' || profile === 'test') return false;
  return null;
}

function inferProbeReadyState(status: string): string {
  const normalized = normalizeText(status, 'unknown').toLowerCase();
  if (['ok', 'healthy', 'ready', 'live', 'up'].includes(normalized)) return 'ready';
  if (['degraded', 'warning', 'partial'].includes(normalized)) return 'degraded';
  if (['not_ready', 'unready', 'starting', 'booting', 'initializing'].includes(normalized)) return 'not_ready';
  return normalized || 'unknown';
}

function normalizeProbeReason(value: unknown): RuntimeProbeReason {
  if (typeof value === 'string') {
    const clean = value.trim();
    return {
      code: clean || 'unknown',
      category: 'unknown',
      severity: 'unknown',
      message: clean || 'unknown',
      detail: clean || 'n/a',
      source: 'unknown',
    };
  }

  const reason = normalizeObject(value) as RuntimeProbeReasonResponse;
  const code = normalizeText(reason.code, 'unknown');
  const message = normalizeText(reason.message ?? reason.detail ?? reason.code, code);
  return {
    code,
    category: normalizeText(reason.category, 'unknown'),
    severity: normalizeText(reason.severity, 'unknown'),
    message,
    detail: normalizeText(reason.detail ?? reason.message, 'n/a'),
    source: normalizeText(reason.source, 'unknown'),
  };
}

function normalizeProbeActivity(value: unknown): RuntimeProbeActivity {
  const activity = normalizeObject(value) as RuntimeProbeActivityResponse;
  return {
    name: normalizeText(activity.name, 'unknown'),
    state: normalizeText(activity.state, 'unknown'),
    status: normalizeText(activity.status, 'unknown'),
    detail: normalizeText(activity.detail, 'n/a'),
    code: normalizeText(activity.code, 'unknown'),
    severity: normalizeText(activity.severity, 'unknown'),
  };
}

function normalizeProbeReasons(value: unknown): RuntimeProbeReason[] {
  if (!Array.isArray(value)) return [];
  return value.map(item => normalizeProbeReason(item));
}

function normalizeProbeActivities(value: unknown): RuntimeProbeActivity[] {
  if (!Array.isArray(value)) return [];
  return value.map(item => normalizeProbeActivity(item));
}

function normalizeProbeSection(value: unknown): RuntimeProbeSection {
  const section = normalizeObject(value) as RuntimeProbeSectionResponse;
  const reasons = normalizeProbeReasons(section.reasons);
  return {
    state: normalizeText(section.state, 'unknown'),
    status: normalizeText(section.status, 'unknown'),
    summary: normalizeText(section.summary, 'n/a'),
    detail: normalizeText(section.detail, 'n/a'),
    reasons,
    activities: normalizeProbeActivities(section.activities),
  };
}

function normalizeProbeContract(health: RuntimeHealthResponse): RuntimeProbeContract {
  const contract = normalizeObject(health.probeContract) as RuntimeProbeContractResponse;
  const live = normalizeProbeSection(contract.live);
  const ready = normalizeProbeSection(contract.ready);
  const detail = normalizeProbeSection(contract.detail);
  const degradedReasons = normalizeProbeReasons(contract.degradedReasons ?? health.degradedReasons ?? ready.reasons ?? detail.reasons);
  const degradedReasonCodes = normalizeStringArray(contract.degradedReasonCodes ?? health.degradedReasonCodes ?? degradedReasons.map(reason => reason.code));
  const fallbackStatus = normalizeText(health.status, 'unknown');

  return {
    schemaVersion: normalizeText(contract.schemaVersion ?? health.schemaVersion, 'legacy'),
    live,
    ready: {
      ...ready,
      reasons: ready.reasons.length > 0 ? ready.reasons : degradedReasons,
    },
    detail: {
      ...detail,
      reasons: detail.reasons.length > 0 ? detail.reasons : degradedReasons,
    },
    probeReadyState: normalizeText(
      contract.probeReadyState ?? health.probeReadyState ?? ready.state,
      inferProbeReadyState(fallbackStatus),
    ),
    probeReadyStatus: normalizeText(
      contract.probeReadyStatus ?? health.probeReadyStatus ?? ready.status,
      fallbackStatus,
    ),
    probeDegraded: normalizeBoolean(contract.probeDegraded ?? health.probeDegraded),
    degradedReasons,
    degradedReasonCodes,
  };
}

export function normalizeRuntimeStatus(health: RuntimeHealthResponse): RuntimeStatus {
  const profile = normalizeText(health.profile, 'local');
  const jobsEnabled = normalizeBoolean(health.jobsEnabled) ?? inferJobsEnabled(profile);
  const telemetryExports = normalizeText(
    health.telemetryExports,
    profile === 'worker' ? 'unknown' : 'not_applicable',
  );
  const probeContract = normalizeProbeContract(health);

  return {
    health: normalizeText(health.status, 'unknown'),
    database: normalizeText(health.db, 'unknown'),
    watcher: normalizeText(health.watcher, 'unknown'),
    profile,
    schemaVersion: probeContract.schemaVersion,
    probeReadyState: probeContract.probeReadyState,
    probeReadyStatus: probeContract.probeReadyStatus,
    probeDegraded: probeContract.probeDegraded,
    degradedReasons: probeContract.degradedReasons,
    degradedReasonCodes: probeContract.degradedReasonCodes,
    probeContract,
    startupSync: normalizeText(health.startupSync, 'idle'),
    analyticsSnapshots: normalizeText(health.analyticsSnapshots, 'idle'),
    telemetryExports,
    jobsEnabled,
    storageMode: normalizeText(health.storageMode, 'unknown'),
    storageProfile: normalizeText(health.storageProfile, 'unknown'),
    storageBackend: normalizeText(health.storageBackend, 'unknown'),
    recommendedStorageProfile: normalizeText(health.recommendedStorageProfile, 'unknown'),
    supportedStorageProfiles: normalizeStringArray(health.supportedStorageProfiles),
    filesystemSourceOfTruth: normalizeBoolean(health.filesystemSourceOfTruth),
    sharedPostgresEnabled: normalizeBoolean(health.sharedPostgresEnabled),
    storageIsolationMode: normalizeText(health.storageIsolationMode, 'unknown'),
    supportedStorageIsolationModes: normalizeStringArray(health.supportedStorageIsolationModes),
    storageCanonicalStore: normalizeText(health.storageCanonicalStore, 'unknown'),
    storageSchema: normalizeText(health.storageSchema, 'n/a'),
    canonicalSessionStore: normalizeText(health.canonicalSessionStore, 'unknown'),
  };
}
