/**
 * Canonical framer-motion animation presets for PlotLot.
 * MOTION_INTENSITY: 5 — professional, data-focused, no Disney bounce.
 * Import these rather than defining inline transitions.
 */

export const spring = {
  type: "spring" as const,
  stiffness: 400,
  damping: 30,
} satisfies object;

export const springGentle = {
  type: "spring" as const,
  stiffness: 200,
  damping: 25,
} satisfies object;

export const springBar = {
  type: "spring" as const,
  stiffness: 120,
  damping: 20,
} satisfies object;

/** Fade up from y:12 — standard item entrance */
export const fadeUp = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
};

/** Fade up from y:24 — for display headings */
export const fadeUpHero = {
  initial: { opacity: 0, y: 24 },
  animate: { opacity: 1, y: 0 },
};

/** Per-item stagger delay: use as spread in transition prop */
export const stagger = (i: number) => ({
  transition: { delay: i * 0.05 },
});

/** Standard card hover — professional lift */
export const cardHover = {
  whileHover: { y: -2, transition: spring },
  whileTap: { scale: 0.97 },
} satisfies object;

/** Variants for staggered container + children */
export const staggerContainer = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

export const staggerItem = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: "spring" as const, stiffness: 300, damping: 25 },
  },
};
