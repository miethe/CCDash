import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';

export interface SmartScrollAnchorOptions {
    thresholdPx?: number;
    stickBehavior?: ScrollBehavior;
}

export interface SmartScrollAnchorResult {
    containerRef: RefObject<HTMLElement | null>;
    isNearBottom: boolean;
    pendingInserts: number;
    onItemsInserted: (insertedCount: number) => void;
    scrollToLatest: (behavior?: ScrollBehavior) => void;
    clearPendingInserts: () => void;
}

export const distanceFromBottom = (
    element: Pick<HTMLElement, 'scrollHeight' | 'scrollTop' | 'clientHeight'>,
): number => Math.max(0, element.scrollHeight - (element.scrollTop + element.clientHeight));

export const useSmartScrollAnchor = (
    options: SmartScrollAnchorOptions = {},
): SmartScrollAnchorResult => {
    const { thresholdPx = 120, stickBehavior = 'smooth' } = options;
    const containerRef = useRef<HTMLElement | null>(null);
    const [isNearBottom, setIsNearBottom] = useState(true);
    const [pendingInserts, setPendingInserts] = useState(0);

    const refreshAnchorState = useCallback(() => {
        const element = containerRef.current;
        if (!element) return;
        setIsNearBottom(distanceFromBottom(element) <= thresholdPx);
    }, [thresholdPx]);

    const scrollToLatest = useCallback((behavior?: ScrollBehavior) => {
        const element = containerRef.current;
        if (!element) return;
        element.scrollTo({ top: element.scrollHeight, behavior: behavior ?? stickBehavior });
        setPendingInserts(0);
    }, [stickBehavior]);

    const onItemsInserted = useCallback((insertedCount: number) => {
        if (insertedCount <= 0) return;
        if (isNearBottom) {
            if (typeof window !== 'undefined') {
                window.requestAnimationFrame(() => scrollToLatest('auto'));
            } else {
                scrollToLatest('auto');
            }
            return;
        }
        setPendingInserts(current => current + insertedCount);
    }, [isNearBottom, scrollToLatest]);

    const clearPendingInserts = useCallback(() => {
        setPendingInserts(0);
    }, []);

    useEffect(() => {
        const element = containerRef.current;
        if (!element) return;

        refreshAnchorState();
        const onScroll = () => refreshAnchorState();
        element.addEventListener('scroll', onScroll, { passive: true });
        return () => {
            element.removeEventListener('scroll', onScroll);
        };
    }, [refreshAnchorState]);

    useEffect(() => {
        if (!isNearBottom || pendingInserts <= 0) return;
        scrollToLatest('auto');
    }, [isNearBottom, pendingInserts, scrollToLatest]);

    return {
        containerRef,
        isNearBottom,
        pendingInserts,
        onItemsInserted,
        scrollToLatest,
        clearPendingInserts,
    };
};
