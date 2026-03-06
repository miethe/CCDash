import { describe, expect, it } from 'vitest';
import { MOTION_PRESET_KEYS, getMotionPreset, motionPresets, reducedMotionPresets } from '../motionPresets';

describe('motionPresets', () => {
    it('registers every expected preset key', () => {
        const presetKeys = Object.keys(motionPresets).sort();
        expect(presetKeys).toEqual([...MOTION_PRESET_KEYS].sort());
    });

    it('returns reduced-motion variants when requested', () => {
        MOTION_PRESET_KEYS.forEach(key => {
            expect(getMotionPreset(key, false)).toBe(motionPresets[key]);
            expect(getMotionPreset(key, true)).toBe(reducedMotionPresets[key]);
        });
    });

    it('uses shorter list insert timing in reduced-motion mode', () => {
        const standardDuration = Number(motionPresets.listInsertTop.transition?.duration || 0);
        const reducedDuration = Number(reducedMotionPresets.listInsertTop.transition?.duration || 0);
        expect(reducedDuration).toBeGreaterThan(0);
        expect(reducedDuration).toBeLessThan(standardDuration);
    });
});

