import { describe, expect, it } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';

import { deriveEffortTimelineLabel, deriveTranscriptIntelligenceTitle } from '../SessionCard';

const TRANSCRIPT_VIEW_SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../SessionInspector/TranscriptView.tsx'),
  'utf-8',
);
const SESSION_INSPECTOR_PANELS_SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../SessionInspector/SessionInspectorPanels.tsx'),
  'utf-8',
);
const TYPES_SOURCE = fs.readFileSync(path.resolve(__dirname, '../../types.ts'), 'utf-8');

describe('transcript intelligence title and effort helpers', () => {
  it('uses transcript title only when the feature flag path enables it', () => {
    expect(
      deriveTranscriptIntelligenceTitle(
        'session-raw-123',
        'Raw session title',
        null,
        'Resolved transcript title',
        true,
      ),
    ).toBe('Resolved transcript title');

    expect(
      deriveTranscriptIntelligenceTitle(
        'session-raw-123',
        'Raw session title',
        null,
        'Resolved transcript title',
        false,
      ),
    ).toBe('Raw session title');
  });

  it('falls back to the raw session id when no title source exists', () => {
    expect(deriveTranscriptIntelligenceTitle('session-raw-123', '', null, '', true)).toBe('session-raw-123');
  });

  it('formats effort transitions as Ultracode -> High', () => {
    expect(
      deriveEffortTimelineLabel([
        { effortTier: 'ultracode' },
        { effortTier: 'high' },
      ]),
    ).toBe('Ultracode -> High');
  });

  it('quietly returns no effort label when data is unknown', () => {
    expect(deriveEffortTimelineLabel([], null)).toBe('');
  });
});

describe('SessionSummaryCard transcript intelligence integration', () => {
  it('keeps title and effort display behind the transcript intelligence flag', () => {
    expect(SESSION_INSPECTOR_PANELS_SOURCE).toContain('isTranscriptIntelligenceEnabled()');
    expect(SESSION_INSPECTOR_PANELS_SOURCE).toContain('deriveTranscriptIntelligenceTitle(');
    expect(SESSION_INSPECTOR_PANELS_SOURCE).toContain('session.transcriptIntelligence?.title?.displayTitle');
    expect(SESSION_INSPECTOR_PANELS_SOURCE).toContain('deriveEffortTimelineLabel(session.transcriptIntelligence?.effortTimeline, session.effortTier)');
    expect(SESSION_INSPECTOR_PANELS_SOURCE).toContain('Effort {effortLabel}');
  });
});

describe('TranscriptView transcript intelligence structure', () => {
  it('declares the AgentSession transcriptIntelligence DTO field', () => {
    expect(TYPES_SOURCE).toContain('transcriptIntelligence?: TranscriptIntelligence | null');
    expect(TYPES_SOURCE).toContain('export interface TranscriptTokenCoverage');
  });

  it('renders a keyboard-accessible minimap marker list when markers exist', () => {
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('const TranscriptMarkersMinimap');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('aria-label="Transcript intelligence markers"');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('role="list"');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('role="listitem"');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('Open transcript marker');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('Transcript minimap mode');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('viewportIndicator');
  });

  it('renders sidepane sections for registers, plan links, and token coverage', () => {
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('Task Register');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('Workflow Register');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('Plan Links');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('Token Coverage');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('getCoverageRows');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('known row tokens');
  });

  it('collapses adjacent TaskCreate and TaskUpdate rows into an expandable transcript group', () => {
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('const buildTranscriptDisplayItems');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('TaskMutationGroupRow');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('taskMutationGroup');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('Grouped adjacent task mutation rows');
  });

  it('shows token rail only from row-level tokenUsage', () => {
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('data-token-rail="row-level"');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('Boolean(showTokenRail && item.log.tokenUsage)');
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('showTokenRail = Boolean(transcriptIntelligence && hasRowLevelTokenUsage)');
  });

  it('shows aggregate-only coverage notice without implying fake row segments', () => {
    expect(TRANSCRIPT_VIEW_SOURCE).toContain(
      'Aggregate token coverage available; row token rail is hidden until row-level tokenUsage is present.',
    );
    expect(TRANSCRIPT_VIEW_SOURCE).toContain("coverage?.sourceGranularity === 'aggregate'");
    expect(TRANSCRIPT_VIEW_SOURCE).toContain('coverage.rowLevelKnownTokens');
  });
});
