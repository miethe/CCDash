import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { StatusChip } from '../StatusChip';

describe('StatusChip', () => {
  it('renders the label text', () => {
    const html = renderToStaticMarkup(<StatusChip label="pending" />);
    expect(html).toContain('pending');
  });

  it('applies neutral classes by default', () => {
    const html = renderToStaticMarkup(<StatusChip label="neutral-test" />);
    expect(html).toContain('bg-slate-700/60');
    expect(html).toContain('text-slate-300');
  });

  it('applies ok classes for variant=ok', () => {
    const html = renderToStaticMarkup(<StatusChip label="done" variant="ok" />);
    expect(html).toContain('bg-emerald-600/20');
    expect(html).toContain('text-emerald-400');
  });

  it('applies warn classes for variant=warn', () => {
    const html = renderToStaticMarkup(<StatusChip label="waiting" variant="warn" />);
    expect(html).toContain('bg-amber-600/20');
    expect(html).toContain('text-amber-400');
  });

  it('applies error classes for variant=error', () => {
    const html = renderToStaticMarkup(<StatusChip label="blocked" variant="error" />);
    expect(html).toContain('bg-rose-600/20');
    expect(html).toContain('text-rose-400');
  });

  it('applies info classes for variant=info', () => {
    const html = renderToStaticMarkup(<StatusChip label="info-label" variant="info" />);
    expect(html).toContain('bg-blue-600/20');
    expect(html).toContain('text-blue-400');
  });

  it('renders tooltip as title attribute when provided', () => {
    const html = renderToStaticMarkup(
      <StatusChip label="some-status" tooltip="This is the reason" />,
    );
    expect(html).toContain('title="This is the reason"');
  });

  it('renders the base structural classes', () => {
    const html = renderToStaticMarkup(<StatusChip label="x" />);
    expect(html).toContain('inline-flex');
    expect(html).toContain('rounded');
    expect(html).toContain('text-xs');
    expect(html).toContain('font-medium');
  });
});
