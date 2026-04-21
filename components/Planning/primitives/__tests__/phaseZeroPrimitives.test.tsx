import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import {
  ArtifactChip,
  Chip,
  Dot,
  ExecBtn,
  MetricTile,
  Panel,
  Spark,
  StatusPill,
  Tile,
} from '../PhaseZeroPrimitives';

describe('PhaseZeroPrimitives — StatusPill', () => {
  it('renders labels for every planning status token', () => {
    const statuses = [
      ['idea', 'idea'],
      ['shaping', 'shaping'],
      ['ready', 'ready'],
      ['draft', 'draft'],
      ['approved', 'approved'],
      ['in-progress', 'in-progress'],
      ['in_progress', 'in-progress'],
      ['blocked', 'blocked'],
      ['completed', 'completed'],
      ['superseded', 'superseded'],
      ['future', 'future'],
      ['deprecated', 'deprecated'],
    ] as const;

    const html = renderToStaticMarkup(
      <div>
        {statuses.map(([status]) => (
          <StatusPill key={status} status={status} />
        ))}
      </div>,
    );

    for (const [, label] of statuses) {
      expect(html).toContain(label);
    }
    expect(html).toContain('planning-pill');
  });

  it('keeps unknown statuses visible instead of dropping the token', () => {
    const html = renderToStaticMarkup(<StatusPill status="needs-review" size="md" />);

    expect(html).toContain('needs-review');
    expect(html).toContain('padding:3px 8px');
  });
});

describe('PhaseZeroPrimitives — ArtifactChip', () => {
  it('renders every artifact token with its short label and count', () => {
    const kinds = [
      ['spec', 'SPEC'],
      ['spike', 'SPIKE'],
      ['prd', 'PRD'],
      ['implementation_plan', 'PLAN'],
      ['plan', 'PLAN'],
      ['progress', 'PROG'],
      ['context', 'CTX'],
      ['tracker', 'TRK'],
      ['report', 'REP'],
    ] as const;

    const html = renderToStaticMarkup(
      <div>
        {kinds.map(([kind], index) => (
          <ArtifactChip key={kind} kind={kind} count={index + 1} />
        ))}
      </div>,
    );

    for (const [, label] of kinds) {
      expect(html).toContain(label);
    }
    expect(html).toContain('9');
  });

  it('uses button markup when clickable and span markup otherwise', () => {
    const buttonHtml = renderToStaticMarkup(
      <ArtifactChip kind="prd" count={2} onClick={() => {}} aria-label="Open PRDs" />,
    );
    const spanHtml = renderToStaticMarkup(<ArtifactChip kind="prd" count={0} />);

    expect(buttonHtml).toContain('<button');
    expect(buttonHtml).toContain('aria-label="Open PRDs"');
    expect(spanHtml).toContain('<span');
    expect(spanHtml).not.toContain('<button');
  });
});

describe('PhaseZeroPrimitives — layout and metric helpers', () => {
  it('renders MetricTile label, value, subtext, and large sizing', () => {
    const html = renderToStaticMarkup(
      <MetricTile label="Tokens" value="12.4k" sub="linked sessions" accent="var(--ok)" big />,
    );

    expect(html).toContain('Tokens');
    expect(html).toContain('12.4k');
    expect(html).toContain('linked sessions');
    expect(html).toContain('font-size:34px');
    expect(html).toContain('color:var(--ok)');
  });

  it('renders Spark as hidden decorative SVG with stable points for multi and single values', () => {
    const html = renderToStaticMarkup(
      <div>
        <Spark data={[0, 10, 5]} color="red" width={90} height={30} />
        <Spark data={[7]} />
      </div>,
    );

    expect(html).toContain('<svg');
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain('stroke="red"');
    expect(html).not.toContain('NaN');
    expect(html).not.toContain('Infinity');
  });

  it('renders ExecBtn with run icon and respects compact mode', () => {
    const regularHtml = renderToStaticMarkup(<ExecBtn label="Launch" />);
    const compactHtml = renderToStaticMarkup(<ExecBtn label="Launch" compact aria-label="Launch task" />);

    expect(regularHtml).toContain('<button');
    expect(regularHtml).toContain('Launch');
    expect(compactHtml).toContain('aria-label="Launch task"');
    expect(compactHtml).not.toContain('<span>Launch</span>');
  });

  it('preserves structural classes for Dot, Chip, Panel, and Tile', () => {
    const html = renderToStaticMarkup(
      <Panel className="panel-extra">
        <Tile className="tile-extra">
          <Chip className="chip-extra">Ready</Chip>
          <Dot tone="var(--ok)" className="dot-extra" />
        </Tile>
      </Panel>,
    );

    expect(html).toContain('planning-panel');
    expect(html).toContain('panel-extra');
    expect(html).toContain('planning-tile');
    expect(html).toContain('tile-extra');
    expect(html).toContain('planning-chip');
    expect(html).toContain('chip-extra');
    expect(html).toContain('planning-dot');
    expect(html).toContain('dot-extra');
    expect(html).toContain('background:var(--ok)');
  });
});
