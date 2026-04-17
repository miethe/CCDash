import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { BatchReadinessPill } from '../BatchReadinessPill';

describe('BatchReadinessPill', () => {
  it('renders the readiness state label', () => {
    const html = renderToStaticMarkup(
      <BatchReadinessPill readinessState="ready" />,
    );
    expect(html).toContain('ready');
  });

  it('uses ok (emerald) classes for ready state', () => {
    const html = renderToStaticMarkup(
      <BatchReadinessPill readinessState="ready" />,
    );
    expect(html).toContain('bg-emerald-600/20');
    expect(html).toContain('text-emerald-400');
  });

  it('uses error (rose) classes for blocked state', () => {
    const html = renderToStaticMarkup(
      <BatchReadinessPill readinessState="blocked" />,
    );
    expect(html).toContain('bg-rose-600/20');
    expect(html).toContain('text-rose-400');
  });

  it('uses warn (amber) classes for waiting state', () => {
    const html = renderToStaticMarkup(
      <BatchReadinessPill readinessState="waiting" />,
    );
    expect(html).toContain('bg-amber-600/20');
    expect(html).toContain('text-amber-400');
  });

  it('uses neutral (slate) classes for unknown state', () => {
    const html = renderToStaticMarkup(
      <BatchReadinessPill readinessState="unknown" />,
    );
    expect(html).toContain('bg-slate-700/60');
    expect(html).toContain('text-slate-300');
  });

  it('renders blocking node IDs when provided', () => {
    const html = renderToStaticMarkup(
      <BatchReadinessPill
        readinessState="blocked"
        blockingNodeIds={['node-1', 'node-2']}
      />,
    );
    expect(html).toContain('Blocking nodes: node-1, node-2');
  });

  it('renders blocking task IDs when provided', () => {
    const html = renderToStaticMarkup(
      <BatchReadinessPill
        readinessState="blocked"
        blockingTaskIds={['TASK-1.1', 'TASK-1.2']}
      />,
    );
    expect(html).toContain('Blocking tasks: TASK-1.1, TASK-1.2');
  });

  it('does not render blocker details when arrays are empty', () => {
    const html = renderToStaticMarkup(
      <BatchReadinessPill
        readinessState="ready"
        blockingNodeIds={[]}
        blockingTaskIds={[]}
      />,
    );
    expect(html).not.toContain('Blocking');
  });

  it('does not render blocker sections when arrays are absent', () => {
    const html = renderToStaticMarkup(
      <BatchReadinessPill readinessState="ready" />,
    );
    expect(html).not.toContain('Blocking');
  });
});
