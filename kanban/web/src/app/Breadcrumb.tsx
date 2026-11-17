/**
 * Topbar Breadcrumb Navigation (KB-P3-34, S6.3).
 * Semantic accessible breadcrumb with workspace context, project icon, section label,
 * count badge, and mobile back button. Zero inline styles.
 */

import React, { type JSX } from 'react';
import { Link, useNavigate } from 'react-router';
import './Breadcrumb.css';

export interface BreadcrumbProps {
  workspaceName?: string | undefined;
  projectKey?: string | undefined;
  projectName?: string | undefined;
  projectIcon?: string | undefined;
  currentSection?: string | undefined;
  issueCount?: number | null | undefined;
  onBack?: (() => void) | undefined;
  className?: string | undefined;
}

export function Breadcrumb({
  workspaceName = 'kanban',
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
        {workspaceName && (
          <>
            <li className="kb-breadcrumb-item">
              <span className="kb-breadcrumb-workspace" data-testid="breadcrumb-workspace">
                {workspaceName}
              </span>
            </li>
            <li aria-hidden="true" className="kb-breadcrumb-separator">
              /
            </li>
          </>
        )}

        <li className="kb-breadcrumb-item">
          <span aria-hidden="true">{projectIcon}</span>
          <Link
            to={`/projects/${projectKey}/overview`}
            className="kb-breadcrumb-link"
          >
            {projectName}
          </Link>
        </li>

        <li aria-hidden="true" className="kb-breadcrumb-separator">
          /
        </li>

        <li aria-current="page" className="kb-breadcrumb-current">
          <span data-testid="breadcrumb-current-section">{currentSection}</span>
          {issueCount !== undefined && issueCount !== null && (
            <span className="kb-breadcrumb-count">
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
          className="kb-breadcrumb-back-btn"
        >
          ‹
        </button>
        <span className="kb-breadcrumb-current">
          {currentSection}
          {issueCount !== undefined && issueCount !== null && ` (${String(issueCount)})`}
        </span>
      </div>
    </nav>
  );
}
