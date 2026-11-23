// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useId, type JSX } from 'react';
import './AdvancedSection.css';

export interface AdvancedSectionProps {
  title?: string;
  summary?: string;
  defaultOpen?: boolean;
  isOpen?: boolean;
  onToggle?: (open: boolean) => void;
  activeOverridesCount?: number;
  activeOverrideCount?: number;
  badgeLabel?: string;
  hasErrors?: boolean;
  className?: string;
  id?: string;
  testId?: string;
  children: React.ReactNode;
}

/**
 * Reusable progressive disclosure accordion for power-user, cryptographic,
 * raw-JSON/DSL, and low-frequency configuration settings (KB-ADVANCED-DISCLOSURE, KAN-319).
 *
 * Defaults to collapsed, supports keyboard navigation (Enter/Space), aria-expanded,
 * auto-expand on errors, and renders an active overrides badge when custom settings are active.
 */
export function AdvancedSection({
  title = 'Advanced',
  summary,
  defaultOpen = false,
  isOpen,
  onToggle,
  activeOverridesCount,
  activeOverrideCount,
  badgeLabel,
  hasErrors = false,
  className = '',
  id,
  testId = 'advanced-section',
  children,
}: AdvancedSectionProps): JSX.Element {
  const generatedId = useId();
  const sectionId = id || `kb-adv-${generatedId}`;
  const contentId = `${sectionId}-content`;

  const [internalOpen, setInternalOpen] = useState<boolean>(defaultOpen);
  const isControlled = isOpen !== undefined;
  const open = isControlled ? isOpen : internalOpen;

  // Auto-expand if hasErrors is set to true so validation errors are immediately reachable
  useEffect(() => {
    if (hasErrors && !open) {
      if (!isControlled) {
        setInternalOpen(true);
      }
      onToggle?.(true);
    }
  }, [hasErrors, open, isControlled, onToggle]);

  const toggle = () => {
    const nextState = !open;
    if (!isControlled) {
      setInternalOpen(nextState);
    }
    onToggle?.(nextState);
  };

  const handleSummaryClick = (e: React.MouseEvent<HTMLElement>) => {
    e.preventDefault();
    toggle();
  };

  const handleSummaryKeyDown = (e: React.KeyboardEvent<HTMLElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggle();
    }
  };

  const count = activeOverridesCount ?? activeOverrideCount ?? 0;
  const badgeText =
    badgeLabel ||
    `${count} custom ${count === 1 ? 'setting' : 'settings'} active`;

  return (
    <details
      id={sectionId}
      className={`kb-advanced-section ${open ? 'kb-advanced-section--open' : ''} ${className}`.trim()}
      open={open}
      data-testid={testId}
    >
      <summary
        className="kb-advanced-summary"
        role="button"
        aria-expanded={open}
        aria-controls={contentId}
        tabIndex={0}
        onClick={handleSummaryClick}
        onKeyDown={handleSummaryKeyDown}
        data-testid={`${testId}-toggle`}
      >
        <span
          className={`kb-advanced-chevron ${open ? 'kb-advanced-chevron--open' : ''}`}
          aria-hidden="true"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M4 2l4 4-4 4" />
          </svg>
        </span>
        <span className="kb-advanced-header">
          <span className="kb-advanced-title">{title}</span>
          {summary ? <span className="kb-advanced-desc">{summary}</span> : null}
          {count > 0 ? (
            <span
              className="kb-advanced-badge"
              data-testid="advanced-active-badge"
              data-collapsed={!open}
            >
              {badgeText}
            </span>
          ) : null}
        </span>
      </summary>
      <div
        id={contentId}
        className="kb-advanced-content"
        role="region"
        aria-label={title}
      >
        {children}
      </div>
    </details>
  );
}

export default AdvancedSection;
