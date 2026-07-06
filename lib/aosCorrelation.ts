import type { AOSCorrelation } from '../types';
import { planningArtifactsHref, planningFeatureModalHref } from '../services/planningRoutes';

const AOS_TURN_URN_RE = /^urn:aos:turn:[0-9a-fA-F-]{36}$/;
const AOS_FOOTER_RE = /^AOS-ID:\s+(urn:aos:turn:[0-9a-fA-F-]{36})$/;
const AOS_URN_RE = /^urn:aos:([^:]+):(.+)$/;

export type AOSParentLinkKind = 'run' | 'feature' | 'artifact';

export interface AOSAliasRow {
  key: string;
  value: string;
}

export interface AOSParentLinkView {
  kind: AOSParentLinkKind;
  label: string;
  urn: string | null;
  uuid: string | null;
  nativeId: string | null;
  href: string | null;
  aliases: AOSAliasRow[];
}

export interface AOSCorrelationView {
  status: string;
  footer: string | null;
  turnUrn: string | null;
  turnUuid: string | null;
  parents: AOSParentLinkView[];
}

const asRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
);

const takeString = (...values: unknown[]): string | null => {
  for (const value of values) {
    if (Array.isArray(value)) {
      for (const item of value) {
        const normalized = takeString(item);
        if (normalized) return normalized;
      }
      continue;
    }
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (trimmed) return trimmed;
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      const stringValue = String(value).trim();
      if (stringValue) return stringValue;
    }
  }
  return null;
};

const toAliasRows = (...records: unknown[]): AOSAliasRow[] => {
  const rows: AOSAliasRow[] = [];
  const seen = new Set<string>();

  records.forEach(recordValue => {
    const record = asRecord(recordValue);
    Object.entries(record).forEach(([key, value]) => {
      const normalizedKey = key.trim();
      if (Array.isArray(value)) {
        value.forEach(item => {
          const normalizedValue = takeString(item);
          if (!normalizedKey || !normalizedValue) return;
          const dedupeKey = `${normalizedKey}:${normalizedValue}`;
          if (seen.has(dedupeKey)) return;
          seen.add(dedupeKey);
          rows.push({ key: normalizedKey, value: normalizedValue });
        });
        return;
      }
      const normalizedValue = takeString(value);
      if (!normalizedKey || !normalizedValue) return;
      const dedupeKey = `${normalizedKey}:${normalizedValue}`;
      if (seen.has(dedupeKey)) return;
      seen.add(dedupeKey);
      rows.push({ key: normalizedKey, value: normalizedValue });
    });
  });

  return rows;
};

const parseUrn = (urn: string | null): { kind: string; uuid: string } | null => {
  if (!urn) return null;
  const match = urn.match(AOS_URN_RE);
  if (!match) return null;
  return { kind: match[1], uuid: match[2] };
};

const normalizeFooter = (correlation: Record<string, unknown>): { footer: string | null; turnUrn: string | null; turnUuid: string | null } => {
  const turn = asRecord(correlation.turn ?? correlation.leafTurn ?? correlation.leaf_turn);
  const footer = takeString(correlation.footer, correlation.aosFooter, correlation.aos_footer);
  const footerMatch = footer?.match(AOS_FOOTER_RE);
  const footerUrn = footerMatch?.[1] ?? null;
  const urn = takeString(
    footerUrn,
    correlation.turnUrn,
    correlation.turnURN,
    correlation.aosTurnUrn,
    correlation.aos_turn_urn,
    turn.urn,
  );
  const uuid = takeString(
    correlation.turnUuid,
    correlation.turnUUID,
    correlation.aosTurnUuid,
    correlation.aos_turn_uuid,
    turn.uuid,
  );
  const normalizedUrn = urn && AOS_TURN_URN_RE.test(urn)
    ? urn
    : uuid
      ? `urn:aos:turn:${uuid}`
      : null;

  if (!normalizedUrn || !AOS_TURN_URN_RE.test(normalizedUrn)) {
    return { footer: null, turnUrn: null, turnUuid: uuid };
  }

  return {
    footer: `AOS-ID: ${normalizedUrn}`,
    turnUrn: normalizedUrn,
    turnUuid: parseUrn(normalizedUrn)?.uuid ?? uuid,
  };
};

const normalizeArtifactType = (value: string | null): string | null => {
  if (!value) return null;
  const normalized = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  if (['design_spec', 'design_specs', 'design_doc', 'design_docs'].includes(normalized)) return 'design-specs';
  if (['prd', 'prds'].includes(normalized)) return 'prds';
  if (['implementation_plan', 'implementation_plans', 'impl_plan', 'impl_plans'].includes(normalized)) return 'implementation-plans';
  if (['context', 'contexts', 'context_file', 'context_files', 'worknotes'].includes(normalized)) return 'contexts';
  if (['report', 'reports'].includes(normalized)) return 'reports';
  return null;
};

const localHref = (value: string | null): string | null => {
  if (!value) return null;
  if (value.startsWith('/')) return value;
  if (value.startsWith('#/')) return value.slice(1);
  return null;
};

const aliasValue = (entity: Record<string, unknown>, ...keys: string[]): string | null => {
  const aliases = asRecord(entity.aliases);
  const native = asRecord(entity.native);
  for (const key of keys) {
    const value = takeString(entity[key], aliases[key], native[key]);
    if (value) return value;
  }
  return null;
};

const inferKind = (fallbackKind: AOSParentLinkKind, entity: Record<string, unknown>): AOSParentLinkKind | null => {
  const explicit = takeString(entity.kind, entity.type)?.toLowerCase();
  if (explicit === 'run' || explicit === 'feature' || explicit === 'artifact') return explicit;
  const urnKind = parseUrn(takeString(entity.urn))?.kind;
  if (urnKind === 'run' || urnKind === 'feature' || urnKind === 'artifact') return urnKind;
  return fallbackKind;
};

const parentHref = (kind: AOSParentLinkKind, entity: Record<string, unknown>, nativeId: string | null): string | null => {
  const explicit = localHref(takeString(entity.href, entity.route, entity.url));
  if (explicit) return explicit;

  if (kind === 'feature') {
    const featureId = aliasValue(entity, 'featureId', 'feature_id', 'id') ?? nativeId;
    return featureId ? planningFeatureModalHref(featureId, 'overview') : null;
  }

  if (kind === 'artifact') {
    const artifactType = normalizeArtifactType(aliasValue(entity, 'artifactType', 'artifact_type', 'docType', 'doc_type', 'type'));
    if (!artifactType) return null;
    const path = aliasValue(entity, 'path', 'filePath', 'file_path');
    const base = planningArtifactsHref(artifactType);
    return path ? `${base}?path=${encodeURIComponent(path)}` : base;
  }

  return null;
};

const parentFromEntity = (fallbackKind: AOSParentLinkKind, raw: unknown): AOSParentLinkView | null => {
  const entity = asRecord(raw);
  if (Object.keys(entity).length === 0) return null;
  const kind = inferKind(fallbackKind, entity);
  if (!kind) return null;

  const urn = takeString(entity.urn);
  const parsedUrn = parseUrn(urn);
  const uuid = takeString(entity.uuid, parsedUrn?.uuid);
  const nativeId = aliasValue(
    entity,
    'nativeId',
    'native_id',
    'featureId',
    'feature_id',
    'runId',
    'run_id',
    'artifactId',
    'artifact_id',
    'id',
  );
  const label = takeString(entity.label, entity.name, nativeId, urn, uuid, kind);

  return {
    kind,
    label: label ?? kind,
    urn,
    uuid,
    nativeId,
    href: parentHref(kind, entity, nativeId),
    aliases: toAliasRows(entity.aliases, entity.native),
  };
};

const collectParentLinks = (correlation: Record<string, unknown>): AOSParentLinkView[] => {
  const candidates: Array<[AOSParentLinkKind, unknown]> = [
    ['run', correlation.run],
    ['run', correlation.parentRun],
    ['run', correlation.parent_run],
    ['feature', correlation.feature],
    ['feature', correlation.parentFeature],
    ['feature', correlation.parent_feature],
    ['artifact', correlation.artifact],
    ['artifact', correlation.parentArtifact],
    ['artifact', correlation.parent_artifact],
  ];

  const listValues = [
    correlation.parents,
    correlation.parentLinks,
    correlation.parent_links,
    correlation.linkedParents,
    correlation.linked_parents,
  ];
  listValues.forEach(value => {
    if (!Array.isArray(value)) return;
    value.forEach(item => {
      const kind = inferKind('run', asRecord(item)) ?? 'run';
      candidates.push([kind, item]);
    });
  });

  const seen = new Set<string>();
  return candidates
    .map(([kind, entity]) => parentFromEntity(kind, entity))
    .filter((parent): parent is AOSParentLinkView => {
      if (!parent) return false;
      const dedupeKey = `${parent.kind}:${parent.urn ?? parent.nativeId ?? parent.uuid ?? parent.label}`;
      if (seen.has(dedupeKey)) return false;
      seen.add(dedupeKey);
      return true;
    });
};

export function buildAOSCorrelationView(value: AOSCorrelation | null | undefined): AOSCorrelationView | null {
  if (!value) return null;
  const correlation = asRecord(value);
  const footer = normalizeFooter(correlation);
  const explicitStatus = takeString(correlation.status);
  const parents = collectParentLinks(correlation);
  if (!footer.footer && parents.length === 0 && !explicitStatus) return null;
  const status = explicitStatus ?? (footer.footer ? 'resolved' : 'unresolved');

  return {
    status,
    footer: footer.footer,
    turnUrn: footer.turnUrn,
    turnUuid: footer.turnUuid,
    parents,
  };
}

export function getAOSClipboardText(value: AOSCorrelation | null | undefined): string | null {
  return buildAOSCorrelationView(value)?.footer ?? null;
}
