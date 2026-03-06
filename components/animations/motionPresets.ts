import type { MotionPresetKey } from '@/types';
import type { Target, Transition } from 'framer-motion';
import { motionTokens } from './motionTokens';

export interface MotionPresetDefinition {
    initial: Target;
    animate: Target;
    exit?: Target;
    transition?: Transition;
    layout?: boolean | 'position' | 'size';
}

export const MOTION_PRESET_KEYS: MotionPresetKey[] = ['listInsertTop', 'messageFlyIn', 'typingPulse'];

export const motionPresets: Record<MotionPresetKey, MotionPresetDefinition> = {
    listInsertTop: {
        initial: { opacity: 0, y: -motionTokens.distance.listInsert, scale: 0.99 },
        animate: { opacity: 1, y: 0, scale: 1 },
        exit: { opacity: 0, y: -motionTokens.distance.listInsert / 2, scale: 0.99 },
        transition: {
            duration: motionTokens.duration.standard,
            ease: motionTokens.easing.standard,
        },
        layout: 'position',
    },
    messageFlyIn: {
        initial: { opacity: 0, y: motionTokens.distance.messageFlyIn, scale: 0.995 },
        animate: { opacity: 1, y: 0, scale: 1 },
        exit: { opacity: 0, y: motionTokens.distance.messageFlyIn / 2 },
        transition: {
            ...motionTokens.spring.messageFlyIn,
        },
        layout: 'position',
    },
    typingPulse: {
        initial: { opacity: 0.45, y: 0, scale: 0.95 },
        animate: { opacity: [0.45, 1, 0.45], y: [0, -2, 0], scale: [0.95, 1, 0.95] },
        transition: {
            duration: 1,
            ease: motionTokens.easing.standard,
            repeat: Infinity,
        },
    },
};

export const reducedMotionPresets: Record<MotionPresetKey, MotionPresetDefinition> = {
    listInsertTop: {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: {
            duration: motionTokens.duration.instant,
            ease: motionTokens.easing.decelerate,
        },
        layout: 'position',
    },
    messageFlyIn: {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: {
            duration: motionTokens.duration.fast,
            ease: motionTokens.easing.decelerate,
        },
        layout: 'position',
    },
    typingPulse: {
        initial: { opacity: 0.55 },
        animate: { opacity: [0.55, 0.9, 0.55] },
        transition: {
            duration: 1.2,
            ease: motionTokens.easing.standard,
            repeat: Infinity,
        },
    },
};

export const getMotionPreset = (
    key: MotionPresetKey,
    prefersReducedMotion = false,
): MotionPresetDefinition => (prefersReducedMotion ? reducedMotionPresets[key] : motionPresets[key]);

