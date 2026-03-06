import { useEffect, useMemo, useRef } from 'react';

export interface ListDiffMeta {
    insertedIds: Set<string>;
    removedIds: Set<string>;
    movedIds: Set<string>;
}

export interface AnimatedListResult<T> extends ListDiffMeta {
    items: T[];
    isHydrated: boolean;
}

export interface AnimatedListOptions<T> {
    getId: (item: T) => string;
    areItemsEqual?: (current: T, incoming: T) => boolean;
    suppressInitialInsertAnimation?: boolean;
}

const shallowEqualObject = (current: object, incoming: object): boolean => {
    if (current === incoming) return true;
    const currentRecord = current as Record<string, unknown>;
    const incomingRecord = incoming as Record<string, unknown>;
    const currentKeys = Object.keys(currentRecord);
    const incomingKeys = Object.keys(incomingRecord);
    if (currentKeys.length !== incomingKeys.length) return false;
    for (const key of currentKeys) {
        if (currentRecord[key] !== incomingRecord[key]) return false;
    }
    return true;
};

export const computeListDiff = (previousIds: string[], nextIds: string[]): ListDiffMeta => {
    const previousSet = new Set(previousIds);
    const nextSet = new Set(nextIds);
    const insertedIds = new Set(nextIds.filter(id => !previousSet.has(id)));
    const removedIds = new Set(previousIds.filter(id => !nextSet.has(id)));
    const previousIndexById = new Map(previousIds.map((id, index) => [id, index]));
    const movedIds = new Set<string>();

    nextIds.forEach((id, nextIndex) => {
        const previousIndex = previousIndexById.get(id);
        if (previousIndex === undefined) return;
        if (previousIndex !== nextIndex) movedIds.add(id);
    });

    return {
        insertedIds,
        removedIds,
        movedIds,
    };
};

export const reconcileAnimatedList = <T extends object>(
    previousItems: T[],
    incomingItems: T[],
    options: AnimatedListOptions<T> & { isHydrated: boolean },
): AnimatedListResult<T> => {
    const { getId, areItemsEqual, isHydrated } = options;
    const suppressInitialInsertAnimation = options.suppressInitialInsertAnimation !== false;
    const previousById = new Map(previousItems.map(item => [getId(item), item] as const));

    const items = incomingItems.map(item => {
        const previous = previousById.get(getId(item));
        if (!previous) return item;

        if (areItemsEqual) {
            return areItemsEqual(previous, item) ? previous : item;
        }
        return shallowEqualObject(previous, item) ? previous : item;
    });

    const previousIds = previousItems.map(getId);
    const nextIds = items.map(getId);
    const diff = computeListDiff(previousIds, nextIds);

    if (!isHydrated && suppressInitialInsertAnimation) {
        return {
            ...diff,
            insertedIds: new Set<string>(),
            items,
            isHydrated: false,
        };
    }

    return {
        ...diff,
        items,
        isHydrated,
    };
};

export const useAnimatedListDiff = <T extends object>(
    incomingItems: T[],
    options: AnimatedListOptions<T>,
): AnimatedListResult<T> => {
    const { getId, areItemsEqual, suppressInitialInsertAnimation } = options;
    const previousItemsRef = useRef<T[]>([]);
    const hydratedRef = useRef(false);

    const result = useMemo(() => (
        reconcileAnimatedList(previousItemsRef.current, incomingItems, {
            getId,
            areItemsEqual,
            isHydrated: hydratedRef.current,
            suppressInitialInsertAnimation,
        })
    ), [areItemsEqual, getId, incomingItems, suppressInitialInsertAnimation]);

    useEffect(() => {
        previousItemsRef.current = result.items;
        hydratedRef.current = true;
    }, [result.items]);

    return result;
};
