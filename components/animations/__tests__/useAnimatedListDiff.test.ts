import { describe, expect, it } from 'vitest';
import { reconcileAnimatedList } from '../useAnimatedListDiff';

interface Row {
    id: string;
    label: string;
    rank: number;
}

const getId = (row: Row): string => row.id;

describe('reconcileAnimatedList', () => {
    it('keeps object identity for unchanged rows', () => {
        const previous: Row[] = [
            { id: 'a', label: 'Alpha', rank: 1 },
            { id: 'b', label: 'Beta', rank: 2 },
        ];

        const incoming: Row[] = [
            { id: 'a', label: 'Alpha', rank: 1 },
            { id: 'b', label: 'Beta+', rank: 2 },
        ];

        const result = reconcileAnimatedList(previous, incoming, {
            getId,
            isHydrated: true,
        });

        expect(result.items[0]).toBe(previous[0]);
        expect(result.items[1]).not.toBe(previous[1]);
    });

    it('computes inserted, removed, and moved ids', () => {
        const previous: Row[] = [
            { id: 'a', label: 'A', rank: 1 },
            { id: 'b', label: 'B', rank: 2 },
            { id: 'c', label: 'C', rank: 3 },
        ];

        const incoming: Row[] = [
            { id: 'c', label: 'C', rank: 1 },
            { id: 'b', label: 'B', rank: 2 },
            { id: 'd', label: 'D', rank: 3 },
        ];

        const result = reconcileAnimatedList(previous, incoming, {
            getId,
            isHydrated: true,
        });

        expect([...result.insertedIds]).toEqual(['d']);
        expect([...result.removedIds]).toEqual(['a']);
        expect([...result.movedIds]).toEqual(['c']);
    });

    it('suppresses first-render insert animations when hydration guard is enabled', () => {
        const result = reconcileAnimatedList<Row>([], [{ id: 'a', label: 'A', rank: 1 }], {
            getId,
            isHydrated: false,
            suppressInitialInsertAnimation: true,
        });

        expect(result.isHydrated).toBe(false);
        expect(result.insertedIds.size).toBe(0);
    });
});

