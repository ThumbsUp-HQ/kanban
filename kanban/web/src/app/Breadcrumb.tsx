/**
 * Topbar Breadcrumb Navigation (KB-P3-34, S6.3).
 * Semantic accessible breadcrumb with project icon, section label, count badge, and mobile back button.
 */

import React, { type JSX } from 'react';
import { Link, useNavigate } from 'react-router';
import './Breadcrumb.css';

export interface BreadcrumbProps {
  projectKey?: string | undefined;
  projectName?: string | undefined;
  projectIcon?: string | undefined;
  currentSection?: string | undefined;
  issueCount?: number | null | undefined;
  onBack?: (() => void) | undefined;
  className?: string | undefined;
}

export function Breadcrumb({
  projectKey = 'KAN',
  projectName = 'kanban',
  projectIcon = '⚡',
  currentSection = 'Work Items',
  issueCount,
  onBack,
  className,
}: BreadcrumbProps): JSX.Element {
  const navigate = useNavigate();

  const handleBack = (): void => {
    if (onBack) {
      onBack();
    } else {
      void navigate(-1);
    }
  };

  return (
    <nav
      aria-label="Breadcrumb"
      className={`kb-breadcrumb ${className ?? ''}`}
    >
      {/* Desktop & Tablet Full Breadcrumb */}
      <ol className="kb-breadcrumb-desktop">
        <li style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span aria-hidden="true">{projectIcon}</span>
          <Link
            to={`/projects/${projectKey}/overview`}
            style={{
              color: 'var(--fg-secondary, #94a3b8)',
              textDecoration: 'none',
              fontWeight: 500,
            }}
          >
            {projectName}
          </Link>
        </li>

        <li aria-hidden="true" style={{ color: 'var(--fg-muted, #64748b)' }}>
          /
        </li>

        <li
          aria-current="page"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            color: 'var(--fg-primary, #f8fafc)',
            fontWeight: 600,
          }}
        >
          <span data-testid="breadcrumb-current-section">{currentSection}</span>
          {issueCount !== undefined && issueCount !== null && (
            <span
              className="kb-breadcrumb-count"
              style={{
                color: 'var(--fg-muted, #94a3b8)',
                fontWeight: 400,
                fontSize: '13px',
              }}
            >
              {`(${String(issueCount)})`}
            </span>
          )}
        </li>
      </ol>

      {/* Mobile Compact Breadcrumb with Back Button (<= 767px) */}
      <div className="kb-breadcrumb-mobile">
        <button
          type="button"
          aria-label="Back"
          onClick={handleBack}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--fg-secondary, #94a3b8)',
            cursor: 'pointer',
            padding: '4px 6px',
            display: 'flex',
            alignItems: 'center',
            fontSize: '16px',
          }}
        >
          ‹
        </button>
        <span
          style={{
            color: 'var(--fg-primary, #f8fafc)',
            fontWeight: 600,
            fontSize: '14px',
          }}
        >
          {currentSection}
          {issueCount !== undefined && issueCount !== null && ` (${String(issueCount)})`}
        </span>
      </div>
    </nav>
  );
}
