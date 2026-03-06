export type CubicBezier = [number, number, number, number];

export const motionTokens = {
    duration: {
        instant: 0.12,
        fast: 0.18,
        standard: 0.24,
        slow: 0.32,
    },
    easing: {
        standard: [0.22, 1, 0.36, 1] as CubicBezier,
        decelerate: [0, 0, 0.2, 1] as CubicBezier,
        accelerate: [0.4, 0, 1, 1] as CubicBezier,
    },
    spring: {
        listPush: {
            type: 'spring' as const,
            stiffness: 420,
            damping: 34,
            mass: 0.78,
        },
        messageFlyIn: {
            type: 'spring' as const,
            stiffness: 360,
            damping: 30,
            mass: 0.72,
        },
        typingPulse: {
            type: 'spring' as const,
            stiffness: 280,
            damping: 22,
            mass: 0.6,
        },
    },
    distance: {
        listInsert: 10,
        messageFlyIn: 16,
    },
};

