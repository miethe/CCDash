import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { MismatchBadge } from '../MismatchBadge';

describe('MismatchBadge — banner variant (compact=false)', () => {
  it('renders the fixed title text', () => {
    const html = renderToStaticMarkup(
      <MismatchBadge state="mismatched" reason="Progress says done but PRD is pending" />,
    );
    expect(html).toContain('Status mismatch detected');
  });

  it('renders the reason text', () => {
    const html = renderToStaticMarkup(
      <MismatchBadge state="mismatched" reason="Reason text here" />,
    );
    expect(html).toContain('Reason text here');
  });

  it('renders evidence label chips', () => {
    const html = renderToStaticMarkup(
      <MismatchBadge
        state="stale"
        reason="Stale doc"
        evidenceLabels={['PRD-outdated', 'progress-diverged']}
      />,
    );
    expect(html).toContain('PRD-outdated');
    expect(html).toContain('progress-diverged');
  });

  it('does not render evidence chips when evidenceLabels is empty', () => {
    const html = renderToStaticMarkup(
      <MismatchBadge state="mismatched" reason="reason" evidenceLabels={[]} />,
    );
    expect(html).not.toContain('bg-amber-500/20');
  });

  it('uses amber border and bg classes', () => {
    const html = renderToStaticMarkup(
      <MismatchBadge state="mismatched" reason="x" />,
    );
    expect(html).toContain('border-amber-500/30');
    expect(html).toContain('bg-amber-500/10');
  });
});

describe('MismatchBadge — compact variant (compact=true)', () => {
  it('renders the state label inline', () => {
    const html = renderToStaticMarkup(
      <MismatchBadge state="reversed" reason="Reversed at feature level" compact />,
    );
    expect(html).toContain('reversed');
  });

  it('does not render the banner title in compact mode', () => {
    const html = renderToStaticMarkup(
      <MismatchBadge state="stale" reason="stale reason" compact />,
    );
    expect(html).not.toContain('Status mismatch detected');
  });

  it('sets reason as title attribute for tooltip', () => {
    const html = renderToStaticMarkup(
      <MismatchBadge state="stale" reason="hover explanation" compact />,
    );
    expect(html).toContain('title="hover explanation"');
  });

  it('uses amber chip classes', () => {
    const html = renderToStaticMarkup(
      <MismatchBadge state="blocked" reason="x" compact />,
    );
    expect(html).toContain('border-amber-500/30');
    expect(html).toContain('bg-amber-500/10');
    expect(html).toContain('text-amber-300');
  });
});
