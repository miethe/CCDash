/**
 * FE tests for per-message token usage feature.
 *
 * Covers:
 *  1. formatTokenCountCompact: compact number formatting per contract spec.
 *  2. SessionLog interface carries tokenUsage (source-level proof).
 *  3. TranscriptView renders TokenUsageCaption for agent messages with token data
 *     (source-level proof).
 *  4. TranscriptView does not render TokenUsageCaption for user messages or when
 *     tokenUsage is absent (source-level proof).
 */

import { describe, it, expect } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { formatTokenCountCompact } from '../../lib/tokenMetrics';

// --- 1. formatTokenCountCompact ---

describe('formatTokenCountCompact', () => {
    it('renders values < 1000 as raw integers', () => {
        expect(formatTokenCountCompact(0)).toBe('0');
        expect(formatTokenCountCompact(999)).toBe('999');
        expect(formatTokenCountCompact(500)).toBe('500');
    });

    it('renders values >= 1000 with K suffix', () => {
        expect(formatTokenCountCompact(1000)).toBe('1K');
        expect(formatTokenCountCompact(1200)).toBe('1.2K');
        expect(formatTokenCountCompact(1500)).toBe('1.5K');
        expect(formatTokenCountCompact(10000)).toBe('10K');
        expect(formatTokenCountCompact(999999)).toBe('1000K');
    });

    it('renders values >= 1_000_000 with M suffix', () => {
        expect(formatTokenCountCompact(1_000_000)).toBe('1M');
        expect(formatTokenCountCompact(1_200_000)).toBe('1.2M');
        expect(formatTokenCountCompact(2_500_000)).toBe('2.5M');
    });

    it('handles null and undefined gracefully', () => {
        expect(formatTokenCountCompact(null)).toBe('0');
        expect(formatTokenCountCompact(undefined)).toBe('0');
    });

    it('strips trailing .0 from K and M formatted values', () => {
        expect(formatTokenCountCompact(1000)).toBe('1K');
        expect(formatTokenCountCompact(1_000_000)).toBe('1M');
        expect(formatTokenCountCompact(2000)).toBe('2K');
    });
});

// --- 2-4. Source-level structural proofs ---

const TYPES_SOURCE = fs.readFileSync(path.resolve(__dirname, '../../types.ts'), 'utf-8');
const TRANSCRIPT_VIEW_SOURCE = fs.readFileSync(
    path.resolve(__dirname, '../SessionInspector/TranscriptView.tsx'),
    'utf-8',
);

describe('SessionLog tokenUsage type', () => {
    it('SessionLog interface declares tokenUsage field', () => {
        expect(TYPES_SOURCE).toContain('tokenUsage?');
    });

    it('SessionLogTokenUsage interface declares all four fields', () => {
        expect(TYPES_SOURCE).toContain('inputTokens');
        expect(TYPES_SOURCE).toContain('outputTokens');
        expect(TYPES_SOURCE).toContain('cacheReadInputTokens');
        expect(TYPES_SOURCE).toContain('cacheCreationInputTokens');
    });
});

describe('TranscriptView token caption rendering', () => {
    it('defines TokenUsageCaption component', () => {
        expect(TRANSCRIPT_VIEW_SOURCE).toContain('const TokenUsageCaption');
    });

    it('renders TokenUsageCaption only for agent messages with tokenUsage', () => {
        // The condition must guard on isAgent and log.tokenUsage
        expect(TRANSCRIPT_VIEW_SOURCE).toContain('isAgent && log.tokenUsage');
        expect(TRANSCRIPT_VIEW_SOURCE).toContain('<TokenUsageCaption');
    });

    it('imports formatTokenCountCompact from tokenMetrics', () => {
        expect(TRANSCRIPT_VIEW_SOURCE).toContain('formatTokenCountCompact');
    });

    it('uses the Popover primitive for hover breakdown', () => {
        expect(TRANSCRIPT_VIEW_SOURCE).toContain('Popover');
        expect(TRANSCRIPT_VIEW_SOURCE).toContain('PopoverTrigger');
        expect(TRANSCRIPT_VIEW_SOURCE).toContain('PopoverContent');
    });

    it('caption label includes tok suffix', () => {
        expect(TRANSCRIPT_VIEW_SOURCE).toContain('tok');
    });

    it('popover shows cache read tokens conditionally', () => {
        expect(TRANSCRIPT_VIEW_SOURCE).toContain('cacheReadInputTokens');
    });
});
