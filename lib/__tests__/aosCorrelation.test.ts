import { describe, expect, it } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

import type { AOSCorrelation } from '../../types';
import { buildAOSCorrelationView, getAOSClipboardText } from '../aosCorrelation';

const TYPES_SOURCE = fs.readFileSync(path.resolve(__dirname, '../../types.ts'), 'utf-8');
const SESSION_INSPECTOR_SOURCE = fs.readFileSync(path.resolve(__dirname, '../../components/SessionInspector.tsx'), 'utf-8');

const TURN_UUID = '11111111-1111-4111-8111-111111111111';
const RUN_UUID = '22222222-2222-4222-8222-222222222222';
const ARTIFACT_UUID = '33333333-3333-4333-8333-333333333333';

describe('AOS correlation session detail contract', () => {
  it('declares the optional AgentSession.aosCorrelation API-client field', () => {
    expect(TYPES_SOURCE).toContain('export interface AOSCorrelation');
    expect(TYPES_SOURCE).toContain('aosCorrelation?: AOSCorrelation | null');
  });

  it('copies only the leaf AOS-ID footer while retaining parent aliases for visible details', () => {
    const correlation: AOSCorrelation = {
      footer: `AOS-ID: urn:aos:turn:${TURN_UUID}`,
      parentRun: {
        kind: 'run',
        urn: `urn:aos:run:${RUN_UUID}`,
        href: '/execution?run=op_run_20260706_120000_example',
        aliases: {
          op_run_id: 'op_run_20260706_120000_example',
        },
      },
      parentFeature: {
        kind: 'feature',
        featureId: 'FEAT-AOS-CORRELATION',
        aliases: {
          prd_slug: 'aos-correlation-indexing-v1',
        },
      },
      parentArtifact: {
        kind: 'artifact',
        urn: `urn:aos:artifact:${ARTIFACT_UUID}`,
        artifactType: 'implementation_plan',
        path: 'docs/project_plans/implementation_plans/aos-correlation-indexing-v1-handoff.md',
        aliases: {
          path: 'docs/project_plans/implementation_plans/aos-correlation-indexing-v1-handoff.md',
        },
      },
    };

    const view = buildAOSCorrelationView(correlation);
    const clipboard = getAOSClipboardText(correlation);

    expect(view?.footer).toBe(`AOS-ID: urn:aos:turn:${TURN_UUID}`);
    expect(clipboard).toBe(`AOS-ID: urn:aos:turn:${TURN_UUID}`);
    expect(clipboard).not.toContain('op_run_20260706_120000_example');
    expect(clipboard).not.toContain('FEAT-AOS-CORRELATION');
    expect(clipboard).not.toContain('aos-correlation-indexing-v1-handoff.md');

    const runParent = view?.parents.find(parent => parent.kind === 'run');
    const featureParent = view?.parents.find(parent => parent.kind === 'feature');
    const artifactParent = view?.parents.find(parent => parent.kind === 'artifact');

    expect(runParent?.href).toBe('/execution?run=op_run_20260706_120000_example');
    expect(runParent?.aliases).toContainEqual({ key: 'op_run_id', value: 'op_run_20260706_120000_example' });
    expect(featureParent?.href).toBe('/board?feature=FEAT-AOS-CORRELATION&tab=overview');
    expect(featureParent?.aliases).toContainEqual({ key: 'prd_slug', value: 'aos-correlation-indexing-v1' });
    expect(artifactParent?.href).toBe(
      '/planning/artifacts/implementation-plans?path=docs%2Fproject_plans%2Fimplementation_plans%2Faos-correlation-indexing-v1-handoff.md',
    );
    expect(artifactParent?.aliases).toContainEqual({
      key: 'path',
      value: 'docs/project_plans/implementation_plans/aos-correlation-indexing-v1-handoff.md',
    });
  });

  it('normalizes backend snake_case turn fields and keeps unresolved states non-copyable', () => {
    const snakeCaseView = buildAOSCorrelationView({
      aos_turn_uuid: TURN_UUID,
    } as unknown as AOSCorrelation);
    expect(snakeCaseView?.footer).toBe(`AOS-ID: urn:aos:turn:${TURN_UUID}`);
    expect(buildAOSCorrelationView({} as AOSCorrelation)).toBeNull();

    const unresolved = buildAOSCorrelationView({
      status: 'unresolved',
      parent_run: {
        kind: 'run',
        aliases: {
          op_run_id: 'op_run_missing_sidecar',
        },
      },
    } as unknown as AOSCorrelation);

    expect(unresolved?.status).toBe('unresolved');
    expect(unresolved?.footer).toBeNull();
    expect(getAOSClipboardText({ status: 'unresolved' } as AOSCorrelation)).toBeNull();
  });

  it('resolves parent links from backend-style list aliases', () => {
    const view = buildAOSCorrelationView({
      footer: `AOS-ID: urn:aos:turn:${TURN_UUID}`,
      parentFeature: {
        kind: 'feature',
        urn: `urn:aos:feature:${RUN_UUID}`,
        aliases: {
          feature_id: ['FEAT-AOS'],
        },
      } as unknown as AOSCorrelation['parentFeature'],
      parentArtifact: {
        kind: 'artifact',
        urn: `urn:aos:artifact:${ARTIFACT_UUID}`,
        aliases: {
          artifact_type: ['implementation_plan'],
          path: ['docs/project_plans/implementation_plans/aos-correlation-indexing-v1-handoff.md'],
        },
      } as unknown as AOSCorrelation['parentArtifact'],
    });

    const featureParent = view?.parents.find(parent => parent.kind === 'feature');
    const artifactParent = view?.parents.find(parent => parent.kind === 'artifact');

    expect(featureParent?.href).toBe('/board?feature=FEAT-AOS&tab=overview');
    expect(featureParent?.aliases).toContainEqual({ key: 'feature_id', value: 'FEAT-AOS' });
    expect(artifactParent?.href).toBe(
      '/planning/artifacts/implementation-plans?path=docs%2Fproject_plans%2Fimplementation_plans%2Faos-correlation-indexing-v1-handoff.md',
    );
  });

  it('wires SessionInspector display and clipboard behavior to the leaf footer only', () => {
    expect(SESSION_INSPECTOR_SOURCE).toContain('buildAOSCorrelationView(correlation)');
    expect(SESSION_INSPECTOR_SOURCE).toContain('navigator.clipboard.writeText(aosView.footer)');
    expect(SESSION_INSPECTOR_SOURCE).toContain('data-copy-value={aosView.footer}');
    expect(SESSION_INSPECTOR_SOURCE).toContain('Copy leaf AOS-ID footer');
    expect(SESSION_INSPECTOR_SOURCE).toContain('Parent Aliases');
    expect(SESSION_INSPECTOR_SOURCE).toContain('correlation={effectiveSession.aosCorrelation}');
  });
});
