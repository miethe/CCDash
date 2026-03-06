import React from 'react';
import { motion } from 'framer-motion';
import { getMotionPreset } from './motionPresets';
import { useReducedMotionPreference } from './useReducedMotionPreference';

const DOT_DELAYS = [0, 0.14, 0.28];

interface TypingIndicatorProps {
    className?: string;
    dotClassName?: string;
    label?: string;
}

export const TypingIndicator: React.FC<TypingIndicatorProps> = ({
    className,
    dotClassName,
    label = 'Agent is typing',
}) => {
    const prefersReducedMotion = useReducedMotionPreference();
    const preset = getMotionPreset('typingPulse', prefersReducedMotion);
    const containerClassName = className || 'inline-flex items-center gap-1';
    const dotClass = dotClassName || 'h-1.5 w-1.5 rounded-full bg-emerald-300/90';

    return (
        <div className={containerClassName} role="status" aria-live="polite" aria-label={label}>
            {DOT_DELAYS.map(delay => (
                <motion.span
                    key={delay}
                    className={dotClass}
                    initial={preset.initial}
                    animate={preset.animate}
                    transition={{
                        ...(preset.transition || {}),
                        delay,
                    }}
                />
            ))}
        </div>
    );
};

