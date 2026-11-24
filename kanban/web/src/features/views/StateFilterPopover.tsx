/**
 * Searchable Multi-Select Workflow State Checkboxes Popover (KAN-308 Problem 2).
 *
 * Security & Accessibility Invariants:
 * - Zero inline `style=` attributes and zero `dangerouslySetInnerHTML` (strict CSP Section 5.4).
 * - Checkbox search input enforces `maxLength={128}`, strips ASCII control characters and lone
 *   UTF-16 surrogates, and uses literal case-insensitive `.toLowerCase().includes(...)` (never `new RegExp`).
 * - Grouped under Actionable (`backlog`, `unstarted`, `started`, and custom non-terminal states)
 *   and Closed (`completed`, `cancelled`), ordered by `sort_order`.
 * - Full keyboard navigation (`Escape` closes & restores focus to trigger, `ArrowDown`/`ArrowUp`
 *   cycles search input and checkboxes, outside `pointerdown` closes) and notifies parent via `onOpenChange`
 *   so `useIssueKeyboardMap` suppresses single-key shortcuts while open.
 */

import React, {
  useState,
  useMemo,
  useRef,
  useEffect,
  useCallback,
  type JSX,
} from 'react';
import { StateBadge } from '../../components/state/StateBadge';
import {
  classifyStateFilterPreset,
  createActionableStateFilterPreference,
  createAllStatesFilterPreference,
  createNoStatesFilterPreference,
  isIssueStateVisible,
  stripControlAndSurrogates,
  toggleStateInPreference,
  type ProjectStateFilterPreference,
} from './issueFilterCookie';
import { normalizeStateKey, type IssueItem, type StateSummary } from './viewsApi';

export const MAX_STATE_SEARCH_LENGTH = 128;

export const DEFAULT_WORKFLOW_STATES: readonly StateSummary[] = Object.freeze([
  Object.freeze({ id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 10 }),
  Object.freeze({ id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 20 }),
  Object.freeze({ id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 30 }),
  Object.freeze({ id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 40 }),
  Object.freeze({ id: 'state-done', name: 'Done', group: 'completed', sort_order: 50 }),
  Object.freeze({ id: 'state-cancelled', name: 'Cancelled', group: 'cancelled', sort_order: 60 }),
]);

export interface StateFilterPopoverProps {
  projectStates?: readonly StateSummary[] | undefined;
  issues?: readonly IssueItem[] | undefined;
  value: ProjectStateFilterPreference;
  onChange: (next: ProjectStateFilterPreference) => void;
  onOpenChange?: ((open: boolean) => void) | undefined;
}

export function resolveEffectiveProjectStates(
  projectStates: readonly StateSummary[] = [],
): StateSummary[] {
  const source = projectStates.length > 0 ? projectStates : DEFAULT_WORKFLOW_STATES;
  return [...source].sort((a, b) => {
    const orderA = a.sort_order ?? 999;
    const orderB = b.sort_order ?? 999;
    if (orderA !== orderB) {
      return orderA - orderB;
    }
    return a.name.localeCompare(b.name);
  });
}

export function sanitizeStateSearchQuery(raw: string): string {
  const stripped = stripControlAndSurrogates(raw, false);
  return stripped.length > MAX_STATE_SEARCH_LENGTH
    ? stripped.slice(0, MAX_STATE_SEARCH_LENGTH)
    : stripped;
}

export function StateFilterPopover({
  projectStates = [],
  issues = [],
  value,
  onChange,
  onOpenChange,
}: StateFilterPopoverProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false);
  const [stateSearch, setStateSearch] = useState('');
  const containerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const effectiveStates = useMemo(
    () => resolveEffectiveProjectStates(projectStates),
    [projectStates],
  );

  const classification = useMemo(
    () => classifyStateFilterPreset(value, effectiveStates),
    [value, effectiveStates],
  );

  // Derive unfiltered issue counts per workflow state
  const stateIssueCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const st of effectiveStates) {
      counts.set(st.id, 0);
    }
    for (const issue of issues) {
      const iState = (issue as { state?: StateSummary }).state;
      const explicitId = (issue as { state_id?: string }).state_id ?? iState?.id ?? '';
      const iNameNorm = iState?.name ? normalizeStateKey(iState.name) : '';
      const matched =
        effectiveStates.find((st) => st.id === explicitId) ??
        (iNameNorm
          ? effectiveStates.find((st) => normalizeStateKey(st.name) === iNameNorm)
          : undefined);
      if (matched) {
        counts.set(matched.id, (counts.get(matched.id) ?? 0) + 1);
      }
    }
    return counts;
  }, [effectiveStates, issues]);

  const setOpenState = useCallback(
    (nextOpen: boolean, restoreFocus = false) => {
      setIsOpen(nextOpen);
      if (!nextOpen) {
        setStateSearch('');
      }
      onOpenChange?.(nextOpen);
      if (!nextOpen && restoreFocus) {
        queueMicrotask(() => {
          triggerRef.current?.focus();
        });
      }
    },
    [onOpenChange],
  );

  // Auto-focus search input on popover open
  useEffect(() => {
    if (!isOpen) return;
    const handle = setTimeout(() => {
      searchInputRef.current?.focus();
    }, 0);
    return () => {
      clearTimeout(handle);
    };
  }, [isOpen]);

  // Close on outside pointerdown
  useEffect(() => {
    if (!isOpen) return;
    const handlePointerDown = (e: PointerEvent | MouseEvent): void => {
      const target = e.target as Node | null;
      if (containerRef.current && target && !containerRef.current.contains(target)) {
        setOpenState(false, false);
      }
    };
    document.addEventListener('pointerdown', handlePointerDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [isOpen, setOpenState]);

  const filteredStates = useMemo(() => {
    const q = stateSearch.trim().toLowerCase();
    if (!q) return effectiveStates;
    return effectiveStates.filter(
      (st) =>
        st.name.toLowerCase().includes(q) ||
        st.group.toLowerCase().includes(q),
    );
  }, [effectiveStates, stateSearch]);

  const actionableGroupStates = useMemo(
    () =>
      filteredStates.filter((st) => {
        const g = st.group.toLowerCase();
        return g !== 'completed' && g !== 'cancelled';
      }),
    [filteredStates],
  );

  const closedGroupStates = useMemo(
    () =>
      filteredStates.filter((st) => {
        const g = st.group.toLowerCase();
        return g === 'completed' || g === 'cancelled';
      }),
    [filteredStates],
  );

  const handleToggleCheckbox = useCallback(
    (st: StateSummary, checked: boolean) => {
      const next = toggleStateInPreference(value, st, checked, effectiveStates);
      onChange(next);
    },
    [value, effectiveStates, onChange],
  );

  const handleSelectPreset = useCallback(
    (preset: 'actionable' | 'all' | 'none') => {
      if (preset === 'actionable') {
        onChange(createActionableStateFilterPreference());
      } else if (preset === 'all') {
        onChange(createAllStatesFilterPreference());
      } else {
        onChange(createNoStatesFilterPreference(effectiveStates));
      }
    },
    [effectiveStates, onChange],
  );

  const handlePopoverKeyDown = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      setOpenState(false, true);
      return;
    }

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const root = containerRef.current;
      if (!root) return;
      const focusables = Array.from(
        root.querySelectorAll<HTMLElement>(
          '[data-testid="state-filter-search-input"], input.state-filter-checkbox',
        ),
      );
      const activeEl = document.activeElement as HTMLElement | null;
      const curIdx = activeEl ? Math.max(focusables.indexOf(activeEl), 0) : 0;
      const step = e.key === 'ArrowDown' ? 1 : -1;
      const nextIdx = (curIdx + step + focusables.length) % focusables.length;
      focusables[nextIdx]?.focus();
    }
  };

  const renderStateRow = (st: StateSummary): JSX.Element => {
    const checked = isIssueStateVisible(st, value);
    const count = stateIssueCounts.get(st.id) ?? 0;
    const normKey = normalizeStateKey(st.name);

    return (
      <label
        key={st.id}
        className={`state-filter-option ${checked ? 'state-filter-option--checked' : ''}`}
      >
        <span className="state-filter-option-left">
          <input
            type="checkbox"
            className="state-filter-checkbox"
            data-testid={`state-checkbox-${st.id}`}
            data-state-key={normKey}
            data-state-group={st.group}
            checked={checked}
            onChange={(e) => {
              handleToggleCheckbox(st, e.target.checked);
            }}
          />
          <StateBadge state={st} showEmoji showRing showLabel />
        </span>
        <span
          className="state-filter-count mono"
          data-testid={`state-count-${st.id}`}
        >
          {count}
        </span>
      </label>
    );
  };

  return (
    <div className="state-filter-popover-wrap" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        id="state-filter-trigger"
        className={`navigator-state-trigger state-filter-trigger ${isOpen ? 'navigator-state-trigger--open' : ''}`}
        data-testid="navigator-filter-state"
        data-state-preset={classification.preset}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        aria-controls="navigator-state-popover"
        aria-label="Filter by state"
        onClick={() => {
          setOpenState(!isOpen, false);
        }}
      >
        <span className="navigator-state-trigger-label">{classification.label}</span>
        <span className="navigator-state-trigger-chevron" aria-hidden="true">
          {isOpen ? '▲' : '▼'}
        </span>
      </button>

      {isOpen && (
        <div
          id="navigator-state-popover"
          data-testid="navigator-state-popover"
          className="navigator-state-popover"
          role="dialog"
          aria-label="Filter workflow states"
          onKeyDown={handlePopoverKeyDown}
        >
          {/* Quick Presets Row */}
          <div
            className="state-filter-presets"
            role="group"
            aria-label="State filter presets"
          >
            <button
              type="button"
              className={`state-filter-preset-btn ${
                classification.preset === 'actionable' ? 'state-filter-preset-btn--active' : ''
              }`}
              data-testid="state-preset-actionable"
              aria-pressed={classification.preset === 'actionable'}
              onClick={() => {
                handleSelectPreset('actionable');
              }}
            >
              Actionable
            </button>
            <button
              type="button"
              className={`state-filter-preset-btn ${
                classification.preset === 'all' ? 'state-filter-preset-btn--active' : ''
              }`}
              data-testid="state-preset-all"
              aria-pressed={classification.preset === 'all'}
              onClick={() => {
                handleSelectPreset('all');
              }}
            >
              All
            </button>
            <button
              type="button"
              className={`state-filter-preset-btn ${
                classification.preset === 'none' ? 'state-filter-preset-btn--active' : ''
              }`}
              data-testid="state-preset-none"
              aria-pressed={classification.preset === 'none'}
              onClick={() => {
                handleSelectPreset('none');
              }}
            >
              None
            </button>
          </div>

          {/* Search Input */}
          <div className="state-filter-search-wrap">
            <input
              ref={searchInputRef}
              type="search"
              className="state-filter-search-input"
              data-testid="state-filter-search-input"
              maxLength={MAX_STATE_SEARCH_LENGTH}
              placeholder="Filter workflow states..."
              aria-label="Search workflow states"
              value={stateSearch}
              onChange={(e) => {
                setStateSearch(sanitizeStateSearchQuery(e.target.value));
              }}
            />
          </div>

          {/* Grouped Checkboxes List */}
          <div className="state-filter-groups" data-testid="state-filter-groups">
            {filteredStates.length === 0 ? (
              <div className="state-filter-empty" data-testid="state-filter-empty">
                No matching workflow states
              </div>
            ) : (
              <>
                {actionableGroupStates.length > 0 && (
                  <div
                    className="state-filter-group"
                    data-testid="state-filter-group-actionable"
                  >
                    <div className="state-filter-group-header">Actionable</div>
                    <div className="state-filter-group-list">
                      {actionableGroupStates.map(renderStateRow)}
                    </div>
                  </div>
                )}

                {closedGroupStates.length > 0 && (
                  <div
                    className="state-filter-group"
                    data-testid="state-filter-group-closed"
                  >
                    <div className="state-filter-group-header">Closed</div>
                    <div className="state-filter-group-list">
                      {closedGroupStates.map(renderStateRow)}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
