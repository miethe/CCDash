import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { EffectiveStatusChips } from '../EffectiveStatusChips';

describe('EffectiveStatusChips', () => {
  it('always renders the raw status chip', () => {
    const html = renderToStaticMarkup(
      <EffectiveStatusChips rawStatus="pending" />,
    );
    expect(html).toContain('raw: pending');
  });

  it('does not render the eff: chip when effectiveStatus equals rawStatus', () => {
    const html = renderToStaticMarkup(
      <EffectiveStatusChips rawStatus="done" effectiveStatus="done" />,
    );
    expect(html).not.toContain('eff:');
  });

  it('renders the eff: chip when effectiveStatus differs from rawStatus', () => {
    const html = renderToStaticMarkup(
      <EffectiveStatusChips rawStatus="pending" effectiveStatus="blocked" />,
    );
    expect(html).toContain('eff: blocked');
  });

  it('hides eff: chip when effectiveStatus is undefined', () => {
    const html = renderToStaticMarkup(
      <EffectiveStatusChips rawStatus="pending" />,
    );
    expect(html).not.toContain('eff:');
  });

  it('applies warn variant to eff: chip when isMismatch is true', () => {
    const html = renderToStaticMarkup(
      <EffectiveStatusChips
        rawStatus="done"
        effectiveStatus="blocked"
        isMismatch={true}
      />,
    );
    // warn variant uses amber classes
    expect(html).toContain('eff: blocked');
    expect(html).toContain('bg-amber-600/20');
    expect(html).toContain('text-amber-400');
  });

  it('renders provenance tooltip content in the hover panel', () => {
    const html = renderToStaticMarkup(
      <EffectiveStatusChips
        rawStatus="in_progress"
        provenance={{
          source: 'derived',
          reason: 'Status inferred from progress document',
          evidence: [],
        }}
      />,
    );
    expect(html).toContain('Provenance');
    expect(html).toContain('Source: derived');
    expect(html).toContain('Status inferred from progress document');
  });

  it('does not render provenance panel when provenance is absent', () => {
    const html = renderToStaticMarkup(
      <EffectiveStatusChips rawStatus="done" />,
    );
    expect(html).not.toContain('Provenance');
  });
});
