/**
 * SegmentedControl tests — a11y structure (role="group", aria-pressed,
 * aria-disabled) and onChange invocation.
 *
 * SegmentedControl has no internal hooks, so it is safe to invoke directly
 * as a plain function to inspect the returned element tree and call its
 * button `onClick` props — no DOM/jsdom required, consistent with this
 * repo's renderToStaticMarkup-based test methodology (no @testing-library
 * dependency is installed).
 */
import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { SegmentedControl, type SegmentedControlOption, type SegmentedControlProps } from '../SegmentedControl';

interface GroupDivProps {
  role: string;
  'aria-label': string;
  children: ButtonElement | ButtonElement[];
}

interface ButtonProps {
  onClick?: () => void;
  disabled: boolean;
  'aria-pressed': boolean;
  'aria-disabled': boolean;
}

type GroupElement = ReactElement<GroupDivProps>;
type ButtonElement = ReactElement<ButtonProps>;

const OPTIONS: SegmentedControlOption[] = [
  { id: 'a', label: 'Alpha' },
  { id: 'b', label: 'Beta' },
  { id: 'c', label: 'Gamma', disabled: true },
];

function renderGroup(props: SegmentedControlProps): GroupElement {
  return (SegmentedControl as unknown as (p: SegmentedControlProps) => GroupElement)(props);
}

function buttons(props: SegmentedControlProps): ButtonElement[] {
  const group = renderGroup(props);
  const children = group.props.children;
  return Array.isArray(children) ? children : [children];
}

describe('SegmentedControl — structural a11y', () => {
  it('renders role=group and aria-label on the wrapper', () => {
    const group = renderGroup({ options: OPTIONS, value: 'a', onChange: vi.fn(), ariaLabel: 'Test switcher' });
    expect(group.props.role).toBe('group');
    expect(group.props['aria-label']).toBe('Test switcher');
  });

  it('renders one button per option with the option label', () => {
    const html = renderToStaticMarkup(
      <SegmentedControl options={OPTIONS} value="a" onChange={() => {}} ariaLabel="Test switcher" />,
    );
    expect(html).toContain('role="group"');
    expect(html).toContain('aria-label="Test switcher"');
    expect(html).toContain('Alpha');
    expect(html).toContain('Beta');
    expect(html).toContain('Gamma');
  });

  it('sets aria-pressed=true only on the active option, false on the rest', () => {
    const items = buttons({ options: OPTIONS, value: 'b', onChange: vi.fn(), ariaLabel: 'x' });
    expect(items[0].props['aria-pressed']).toBe(false); // a
    expect(items[1].props['aria-pressed']).toBe(true); // b (active)
    expect(items[2].props['aria-pressed']).toBe(false); // c (disabled, inactive)
  });

  it('marks a disabled option aria-disabled + disabled, and never active', () => {
    const items = buttons({ options: OPTIONS, value: 'c', onChange: vi.fn(), ariaLabel: 'x' });
    // Even if `value` points at a disabled option, aria-pressed reflects the
    // literal value match — the component does not silently reinterpret it.
    expect(items[2].props['aria-disabled']).toBe(true);
    expect(items[2].props.disabled).toBe(true);
  });
});

describe('SegmentedControl — onChange', () => {
  it('invokes onChange with the clicked option id', () => {
    const onChange = vi.fn();
    const items = buttons({ options: OPTIONS, value: 'a', onChange, ariaLabel: 'x' });

    expect(items[1].props.onClick).toBeTypeOf('function');
    items[1].props.onClick();

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('b');
  });

  it('does not attach an onClick handler for disabled options', () => {
    const onChange = vi.fn();
    const items = buttons({ options: OPTIONS, value: 'a', onChange, ariaLabel: 'x' });

    expect(items[2].props.onClick).toBeUndefined();
  });
});
