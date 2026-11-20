import React, { useState, useRef, useLayoutEffect, useEffect, useMemo, type JSX } from 'react';
import type { IssueItem } from './viewsApi';
import './filterBulk.css';

export type QuickFieldType =
  | 'state'
  | 'priority'
  | 'assignee'
  | 'labels'
  | 'module'
  | 'due_date';

export interface QuickFieldPopoverProps {
  isOpen: boolean;
  field: QuickFieldType | null;
  anchorRect: DOMRect | null;
  issue: IssueItem | null | undefined;
  onClose: () => void;
  onSelect: (field: QuickFieldType, value: unknown) => void;
  modulesEnabled?: boolean | undefined;
  states?: { id: string; name: string; group?: string; color_hex?: string | null }[] | undefined;
}

interface OptionItem {
  id: string;
  label: string;
  emoji?: string;
  value: unknown;
}

export function QuickFieldPopover({
  isOpen,
  field,
  anchorRect,
  issue,
  onClose,
  onSelect,
  modulesEnabled = true,
  states,
}: QuickFieldPopoverProps): JSX.Element | null {
  const popoverRef = useRef<HTMLDivElement>(null);
  const [focusedIndex, setFocusedIndex] = useState(0);

  // Compute whether popover should be active
  const isEligible =
    isOpen &&
    field !== null &&
    issue != null &&
    !(field === 'module' && !modulesEnabled);

  // Define options per field
  const { title, options } = useMemo<{ title: string; options: OptionItem[] }>(() => {
    let t = 'Select Option';
    let opts: OptionItem[] = [];

    if (field === 'priority') {
      t = 'Priority';
      opts = [
        { id: 'urgent', label: 'Urgent', emoji: '🔥', value: 'urgent' },
        { id: 'high', label: 'High', emoji: '⚡', value: 'high' },
        { id: 'medium', label: 'Medium', emoji: '🔹', value: 'medium' },
        { id: 'low', label: 'Low', emoji: '💤', value: 'low' },
        { id: 'none', label: 'None', value: 'none' },
      ];
    } else if (field === 'state') {
      t = 'State';
      if (states && states.length > 0) {
        opts = states.map((s) => ({
          id: s.id,
          label: s.name,
          value: s.id,
        }));
      } else {
        opts = [
          { id: 'backlog', label: 'Backlog', value: 'state-backlog' },
          { id: 'todo', label: 'Todo', value: 'state-todo' },
          { id: 'in-progress', label: 'In Progress', value: 'state-in-progress' },
          { id: 'in-review', label: 'In Review', value: 'state-in-review' },
          { id: 'done', label: 'Done', value: 'state-done' },
          { id: 'cancelled', label: 'Cancelled', value: 'state-cancelled' },
        ];
      }
    } else if (field === 'assignee') {
      t = 'Assignee';
      opts = [
        { id: 'alice', label: 'Alice Cooper', value: 'alice' },
        { id: 'adam', label: 'Adam Outler', value: 'adam' },
        { id: 'unassigned', label: 'Unassigned', value: 'unassigned' },
      ];
    } else if (field === 'labels') {
      t = 'Labels';
      opts = [
        { id: 'lbl-sec', label: 'Security', value: 'lbl-sec' },
        { id: 'lbl-auth', label: 'Auth', value: 'lbl-auth' },
        { id: 'lbl-db', label: 'Database', value: 'lbl-db' },
      ];
    } else if (field === 'module') {
      t = 'Module';
      opts = [
        { id: 'mod-1', label: 'Auth Core', value: 'mod-1' },
        { id: 'mod-2', label: 'Kanban Board', value: 'mod-2' },
        { id: 'none', label: 'No Module', value: 'none' },
      ];
    } else {
      t = 'Due Date';
      opts = [
        { id: 'today', label: 'Due Today', value: 'today' },
        { id: 'next_week', label: 'Due Next Week', value: 'next_week' },
        { id: 'clear', label: 'Clear Due Date', value: null },
      ];
    }

    return { title: t, options: opts };
  }, [field, states]);

  // Anchor popover position strictly via CSS custom properties on element ref (Strict CSP)
  useLayoutEffect(() => {
    if (!isEligible) return;
    if (popoverRef.current) {
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const top = Math.min(
        viewportHeight - 250,
        Math.max(10, anchorRect ? anchorRect.bottom + 6 : 10)
      );
      const left = Math.min(
        viewportWidth - 240,
        Math.max(10, anchorRect ? anchorRect.left : 10)
      );
      popoverRef.current.style.setProperty('--popover-top', `${String(top)}px`);
      popoverRef.current.style.setProperty('--popover-left', `${String(left)}px`);
    }
  }, [isEligible, anchorRect]);

  // Handle keyboard navigation inside the popover
  useEffect(() => {
    if (!isEligible || options.length === 0) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setFocusedIndex((prev) => (prev + 1) % options.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setFocusedIndex((prev) => (prev - 1 + options.length) % options.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const selected = options[focusedIndex];
        /* v8 ignore next */
        if (selected) {
          onSelect(field, selected.value);
        }
        onClose();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => { window.removeEventListener('keydown', handleKeyDown); };
  }, [isEligible, options, focusedIndex, field, onSelect, onClose]);

  if (!isEligible) {
    return null;
  }

  return (
    <>
      <div
        className="quick-field-backdrop"
        data-testid="quick-field-backdrop"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={popoverRef}
        className="quick-field-popover"
        role="dialog"
        aria-label={`Quick ${title} Picker`}
        data-testid="quick-field-popover"
      >
        <div className="quick-field-popover-title">{title}</div>
        <div className="quick-field-options" role="listbox">
          {options.map((opt, index) => (
            <button
              key={opt.id}
              type="button"
              role="option"
              aria-selected={index === focusedIndex}
              className={`quick-field-option ${index === focusedIndex ? 'quick-field-option--focused' : ''}`}
              onClick={() => {
                onSelect(field, opt.value);
                onClose();
              }}
            >
              {opt.emoji ? <span>{opt.emoji} </span> : null}
              <span>{opt.label}</span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
