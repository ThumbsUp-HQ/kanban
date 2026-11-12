import { useEffect, useState } from 'react';

/**
 * Authoritative responsive breakpoint boundaries.
 *
 * Responsive Rule (S6.1):
 * S6.1 card padding (--card-pad: 16px 18px), row heights (--list-row-h: 46px, --prop-row-h: 38px),
 * and gaps (--card-gap: 12px, --board-col-gap: 20px) are NEVER reduced at any breakpoint.
 * Generous whitespace is preserved uniformly across all viewports; the only mobile exception
 * is board canvas padding 16px (applied by KB-P3-37).
 */
export const BP = {
  mobileMax: 767,
  tabletMax: 1279,
} as const;

export type Breakpoint = 'mobile' | 'tablet' | 'desktop';

/**
 * Pure helper evaluating current viewport against media queries.
 */
export function getBreakpoint(): Breakpoint {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return 'desktop';
  }
  if (window.matchMedia(`(max-width: ${String(BP.mobileMax)}px)`).matches) {
    return 'mobile';
  }
  if (window.matchMedia(`(max-width: ${String(BP.tabletMax)}px)`).matches) {
    return 'tablet';
  }
  return 'desktop';
}

/**
 * React hook observing viewport changes across mobile, tablet, and desktop breakpoints.
 */
export function useBreakpoint(): Breakpoint {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(getBreakpoint);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return;
    }

    const mobileMql = window.matchMedia(`(max-width: ${String(BP.mobileMax)}px)`);
    const tabletMql = window.matchMedia(`(max-width: ${String(BP.tabletMax)}px)`);

    const update = (): void => {
      setBreakpoint(getBreakpoint());
    };

    mobileMql.addEventListener('change', update);
    tabletMql.addEventListener('change', update);

    return () => {
      mobileMql.removeEventListener('change', update);
      tabletMql.removeEventListener('change', update);
    };
  }, []);

  return breakpoint;
}
