/**
 * Board Layout Switcher (KB-P3-34, S6.3, KAN-52).
 * Accessible radiogroup with 5 views (Issues, Board, Table, Calendar, Timeline) and responsive collapse.
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  type JSX,
  type KeyboardEvent,
} from 'react';
import { useSearchParams } from 'react-router';
import './LayoutSwitcher.css';

export type LayoutOption = 'list' | 'board' | 'table' | 'calendar' | 'timeline';

export interface LayoutConfig {
  readonly id: LayoutOption;
  readonly label: string;
}

export const LAYOUT_OPTIONS: readonly [LayoutConfig, ...LayoutConfig[]] = [
  { id: 'list', label: 'Issues' },
  { id: 'board', label: 'Board' },
  { id: 'table', label: 'Table' },
  { id: 'calendar', label: 'Calendar' },
  { id: 'timeline', label: 'Timeline' },
] as const;

const VALID_LAYOUTS: ReadonlySet<string> = new Set(
  LAYOUT_OPTIONS.map((o) => o.id),
);

export function normalizeLayout(value: string | null | undefined): LayoutOption {
  if (value && VALID_LAYOUTS.has(value.toLowerCase())) {
    return value.toLowerCase() as LayoutOption;
  }
  return 'list';
}

export interface LayoutSwitcherProps {
  value?: LayoutOption;
  onChange?: (layout: LayoutOption) => void;
  className?: string;
}

export function LayoutSwitcher({
  value: valueProp,
  onChange: onChangeProp,
  className,
}: LayoutSwitcherProps): JSX.Element {
  let searchParams: URLSearchParams | null = null;
  let setSearchParams: ((params: URLSearchParams) => void) | null = null;

  try {
    const [params, setParams] = useSearchParams();
    searchParams = params;
    setSearchParams = setParams;
  } catch {
    // Graceful fallback when rendered outside RouterProvider
  }

  const rawParam = searchParams?.get('layout');
  const activeLayout: LayoutOption =
    valueProp ?? normalizeLayout(rawParam);

  const [menuOpen, setMenuOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (!menuOpen) return;
    const handleOutsideClick = (e: MouseEvent): void => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    const handleEscape = (e: globalThis.KeyboardEvent): void => {
      if (e.key === 'Escape') {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [menuOpen]);

  const handleSelect = useCallback(
    (opt: LayoutOption) => {
      onChangeProp?.(opt);
      if (searchParams && setSearchParams) {
        const next = new URLSearchParams(searchParams);
        next.set('layout', opt);
        setSearchParams(next);
      }
      setMenuOpen(false);
    },
    [onChangeProp, searchParams, setSearchParams],
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number): void => {
    let nextIndex = index;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      nextIndex = (index + 1) % LAYOUT_OPTIONS.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      nextIndex = (index - 1 + LAYOUT_OPTIONS.length) % LAYOUT_OPTIONS.length;
    }

    if (nextIndex !== index) {
      const nextOpt = LAYOUT_OPTIONS[nextIndex];
      if (nextOpt) {
        handleSelect(nextOpt.id);
        buttonRefs.current[nextIndex]?.focus();
      }
    }
  };

  const activeConfig =
    LAYOUT_OPTIONS.find((o) => o.id === activeLayout) ?? LAYOUT_OPTIONS[0];

  return (
    <div
      ref={containerRef}
      className={`kb-layout-switcher ${className ?? ''}`}
    >
      {/* Desktop Segmented Control */}
      <div
        className="kb-layout-switcher-desktop"
        role="radiogroup"
        aria-label="Layout"
      >
        {LAYOUT_OPTIONS.map((opt, i) => {
          const isSelected = opt.id === activeLayout;
          return (
            <button
              key={opt.id}
              ref={(el) => {
                buttonRefs.current[i] = el;
              }}
              type="button"
              role="radio"
              aria-checked={isSelected}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => { handleSelect(opt.id); }}
              onKeyDown={(e) => { handleKeyDown(e, i); }}
              className={`kb-layout-switcher-btn ${isSelected ? 'kb-layout-switcher-btn--selected' : ''}`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      {/* Responsive Collapsed Dropdown (<= 1279px) */}
      <div className="kb-layout-switcher-mobile">
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-label={`Layout: ${activeConfig.label}`}
          onClick={() => { setMenuOpen(!menuOpen); }}
          className="kb-layout-switcher-mobile-btn"
        >
          <span className="kb-layout-switcher-mobile-label">
            <span className="kb-layout-switcher-prefix">Layout: </span>
            {activeConfig.label}
          </span>
          <span aria-hidden="true">▾</span>
        </button>

        {menuOpen && (
          <div
            role="menu"
            aria-label="Layout menu"
            className="kb-layout-switcher-menu"
          >
            {LAYOUT_OPTIONS.map((opt) => {
              const isSelected = opt.id === activeLayout;
              return (
                <button
                  key={opt.id}
                  type="button"
                  role="menuitemradio"
                  aria-checked={isSelected}
                  onClick={() => { handleSelect(opt.id); }}
                  className={`kb-layout-switcher-menu-item ${isSelected ? 'kb-layout-switcher-menu-item--selected' : ''}`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
