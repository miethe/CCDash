import { describe, expect, it } from 'vitest';
import { distanceFromBottom, isWithinScrollThreshold } from '../useSmartScrollAnchor';

describe('useSmartScrollAnchor helpers', () => {
    it('computes distance from the bottom of a scroll container', () => {
        expect(distanceFromBottom({
            scrollHeight: 1200,
            scrollTop: 900,
            clientHeight: 200,
        })).toBe(100);
    });

    it('reports whether the user is close enough to auto-stick', () => {
        expect(isWithinScrollThreshold(80, 120)).toBe(true);
        expect(isWithinScrollThreshold(121, 120)).toBe(false);
    });
});
