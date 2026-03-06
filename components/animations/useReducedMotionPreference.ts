import { useReducedMotion } from 'framer-motion';

export const useReducedMotionPreference = (): boolean => {
    const prefersReducedMotion = useReducedMotion();
    return Boolean(prefersReducedMotion);
};

