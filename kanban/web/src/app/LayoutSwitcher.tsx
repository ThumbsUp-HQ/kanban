/**
 * Board Layout Switcher (KB-P3-34, S6.3).
 * Accessible radiogroup with 5 views (List, Board, Table, Calendar, Timeline) and responsive collapse.
 */

import React, {
  useCallback,
  useRef,
  useState,
  type JSX,
  type KeyboardEvent,
} from 'react';
import { useSearchParams } from 'react-router';

export type LayoutOption = 'list' | 'board' | 'table' | 'calendar' | 'timeline';

export interface LayoutConfig {
  readonly id: LayoutOption;
  readonly label: string;
}

export const LAYOUT_OPTIONS: readonly LayoutConfig[] = [
  { id: 'list', label: 'List' },
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
      }
      buttonRefs.current[nextIndex]?.focus();
    }
  };

  const activeConfig =
    LAYOUT_OPTIONS.find((o) => o.id === activeLayout) ??
    (LAYOUT_OPTIONS[0] ?? { id: 'list', label: 'List' });

  return (
    <div
      ref={containerRef}
      className={`kb-layout-switcher ${className ?? ''}`}
      style={{ display: 'inline-flex', alignItems: 'center' }}
    >
      {/* Desktop Segmented Control */}
      <div
        className="kb-layout-switcher-desktop"
        role="radiogroup"
        aria-label="Layout"
        style={{
          display: 'flex',
          background: 'var(--bg-surface-raised, #24272f)',
          borderRadius: 'var(--radius-md, 6px)',
          padding: '2px',
          gap: '2px',
          border: '1px solid var(--border-subtle, #333842)',
        }}
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
              style={{
                background: isSelected ? 'var(--bg-hover, #2c313a)' : 'transparent',
                color: isSelected
                  ? 'var(--fg-primary, #f8fafc)'
                  : 'var(--fg-muted, #94a3b8)',
                padding: 'var(--space-1, 4px) var(--space-3, 12px)',
                borderRadius: 'var(--radius-sm, 4px)',
                border: 'none',
                cursor: 'pointer',
                fontSize: '13px',
                fontWeight: isSelected ? 600 : 400,
                outline: 'none',
                transition: 'background 120ms ease, color 120ms ease',
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      {/* Responsive Collapsed Dropdown (<= 1279px) */}
      <div className="kb-layout-switcher-mobile" style={{ position: 'relative' }}>
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-label={`Layout: ${activeConfig.label}`}
          onClick={() => { setMenuOpen(!menuOpen); }}
          style={{
            background: 'var(--bg-surface-raised, #24272f)',
            color: 'var(--fg-primary, #f8fafc)',
            border: '1px solid var(--border-subtle, #333842)',
            borderRadius: 'var(--radius-md, 6px)',
            padding: 'var(--space-1, 4px) var(--space-3, 12px)',
            cursor: 'pointer',
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span>Layout: {activeConfig.label}</span>
          <span aria-hidden="true">▾</span>
        </button>

        {menuOpen && (
          <div
            role="menu"
            aria-label="Layout menu"
            style={{
              position: 'absolute',
              top: 'calc(100% + 4px)',
              right: 0,
              background: 'var(--bg-surface-raised, #24272f)',
              border: '1px solid var(--border-subtle, #333842)',
              borderRadius: 'var(--radius-md, 6px)',
              boxShadow: 'var(--shadow-lg, 0 10px 15px -3px rgba(0, 0, 0, 0.5))',
              zIndex: 100,
              minWidth: '140px',
              padding: '4px',
            }}
          >
            {LAYOUT_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                role="menuitemradio"
                aria-checked={opt.id === activeLayout}
                onClick={() => { handleSelect(opt.id); }}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  background:
                    opt.id === activeLayout
                      ? 'var(--bg-hover, #2c313a)'
                      : 'transparent',
                  color:
                    opt.id === activeLayout
                      ? 'var(--fg-primary, #f8fafc)'
                      : 'var(--fg-secondary, #cbd5e1)',
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-sm, 4px)',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '13px',
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
