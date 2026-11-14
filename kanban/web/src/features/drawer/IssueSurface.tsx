import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  type JSX,
} from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { ApiProblem } from '../../api/problem';
import { qk } from '../../api/queryKeys';
import { useBreakpoint } from '../../styles/breakpoints';
import { registerShortcut } from '../../app/shortcuts';
import {
  useIssueSurfaceRoute,
  toFullScreenPath,
  toPeekPath,
} from './useIssueSurfaceRoute';
import { getOpenerElement } from './IssueKeyLink';
import { useIssueSurfaceSlots, type IssueDetail } from './slots';
import { IssueHeader } from './IssueHeader';
import { SummaryField } from './SummaryField';
import { useFocusTrap } from './useFocusTrap';
import './IssueSurface.css';

let moduleMountCounter = 0;

interface IssueSurfaceRootProps {
  mode: 'drawer' | 'full';
  issueKey: string;
  projectKey: string | null;
}

function IssueSurfaceRoot({
  mode,
  issueKey,
  projectKey,
}: IssueSurfaceRootProps): JSX.Element {
  const [mountId] = useState(() => crypto.randomUUID());
  const [mountSeq] = useState(() => {
    moduleMountCounter += 1;
    return moduleMountCounter;
  });

  const location = useLocation();
  const navigate = useNavigate();
  const rootRef = useRef<HTMLElement | null>(null);
  const descRef = useRef<HTMLElement | null>(null);

  const slots = useIssueSurfaceSlots();
  const bp = useBreakpoint();
  const isMobile = bp === 'mobile';

  useFocusTrap(isMobile && mode === 'drawer', rootRef);

  useEffect(() => {
    rootRef.current?.focus();
  }, [issueKey]);

  const {
    data: issue,
    error,
    isLoading,
    refetch,
  } = useQuery<IssueDetail>({
    queryKey: qk.issue(issueKey),
    queryFn: async () => {
      return (await apiClient.get(
        '/api/v1/issues/{issue_key}',
        { params: { issue_key: issueKey } },
      )) as unknown as IssueDetail;
    },
    staleTime: 60_000,
  });

  const handleClose = useCallback((): void => {
    void navigate(toPeekPath(location, null));
    const opener = getOpenerElement();
    if (opener) {
      opener.focus();
    } else {
      const main = document.getElementById('kb-main') ?? document.getElementById('main');
      main?.focus();
    }
  }, [location, navigate]);

  const handleToggleFullScreen = useCallback((): void => {
    if (mode === 'drawer') {
      const resolvedProject = projectKey ?? (issueKey.split('-')[0] ?? 'KAN');
      void navigate(toFullScreenPath(resolvedProject, issueKey));
    } else {
      void navigate(toPeekPath(location, issueKey));
    }
  }, [mode, projectKey, issueKey, location, navigate]);

  useEffect(() => {
    const unregister = registerShortcut(
      'mod+shift+f',
      (e) => {
        e.preventDefault();
        handleToggleFullScreen();
      },
      { allowInInputs: true },
    );
    return unregister;
  }, [handleToggleFullScreen]);

  useEffect(() => {
    const handleGlobalEscape = (e: KeyboardEvent): void => {
      if (e.key !== 'Escape') {
        return;
      }
      // If an open popup or dialog exists inside, it handles Escape first
      const hasOpenPopover = document.querySelector(
        '[data-hint-open="true"], [role="dialog"].kb-hint-popup',
      );
      if (hasOpenPopover) {
        return;
      }
      if (e.defaultPrevented) {
        return;
      }
      e.preventDefault();
      if (mode === 'full') {
        void navigate(toPeekPath(location, issueKey));
      } else {
        handleClose();
      }
    };
    window.addEventListener('keydown', handleGlobalEscape);
    return () => {
      window.removeEventListener('keydown', handleGlobalEscape);
    };
  }, [mode, issueKey, location, navigate, handleClose]);

  const DescriptionSlot = slots.description;
  const RailSlot = slots.rail;
  const ActivitySlot = slots.activity;

  const errorStatus =
    error instanceof ApiProblem
      ? error.status
      : (error as { status?: number } | undefined)?.status;
  const isNotFoundOrForbidden = errorStatus === 403 || errorStatus === 404;

  const renderContent = (): JSX.Element => {
    if (isLoading) {
      return (
        <>
          <div className="surface__header">
            <button
              type="button"
              className="issue-header__btn"
              aria-label="Close issue panel"
              onClick={handleClose}
            >
              <span aria-hidden="true" className="issue-header__glyph">→</span>
            </button>
            <span className="mono issue-header__key">{issueKey}</span>
          </div>
          <div className="surface__body">
            <div className="surface__prose">
              <div className="surface__skeleton">
                <div className="surface__skeleton-line surface__skeleton-line--title" />
                <div className="surface__skeleton-line surface__skeleton-line--body" />
              </div>
            </div>
            <aside className="surface__rail" aria-label="Properties" />
          </div>
        </>
      );
    }

    if (error) {
      return (
        <>
          <div className="surface__header">
            <button
              type="button"
              className="issue-header__btn"
              aria-label="Close issue panel"
              onClick={handleClose}
            >
              <span aria-hidden="true" className="issue-header__glyph">→</span>
            </button>
            <button
              type="button"
              className="issue-header__btn"
              aria-label={mode === 'full' ? 'Return to side panel' : 'Open in full screen'}
              aria-keyshortcuts="Meta+Shift+F Control+Shift+F"
              onClick={handleToggleFullScreen}
            >
              <span aria-hidden="true" className="issue-header__glyph">↗</span>
            </button>
            <span className="mono issue-header__key">{issueKey}</span>
          </div>
          <div className="surface__body">
            <div className="surface__prose">
              <div className="surface__error" role="alert">
                <p className="surface__error-message">
                  {isNotFoundOrForbidden
                    ? `Issue ${issueKey} was not found or you do not have access.`
                    : `Could not load ${issueKey}.`}
                </p>
                {!isNotFoundOrForbidden && (
                  <button
                    type="button"
                    className="surface__retry-btn"
                    onClick={() => void refetch()}
                  >
                    Retry
                  </button>
                )}
              </div>
            </div>
            <aside className="surface__rail" aria-label="Properties" />
          </div>
        </>
      );
    }

    if (!issue) {
      return <></>;
    }
    const currentIssue: IssueDetail = issue;

    const proseBody = (
      <>
        <SummaryField issue={currentIssue} descriptionFocusRef={descRef} />
        {DescriptionSlot ? (
          <DescriptionSlot issue={currentIssue} focusRef={descRef} />
        ) : (
          <div
            ref={descRef as React.RefObject<HTMLDivElement>}
            tabIndex={0}
            className="surface__description"
          >
            {currentIssue.description_markdown}
          </div>
        )}
        {ActivitySlot && <ActivitySlot issue={currentIssue} />}
      </>
    );

    return (
      <>
        <IssueHeader
          issue={currentIssue}
          mode={mode}
          onClose={handleClose}
          toggleFullScreen={handleToggleFullScreen}
        />
        <div className="surface__body">
          <div className="surface__prose">
            <div className="surface__prose-inner">{proseBody}</div>
          </div>
          <aside className="surface__rail" aria-label="Properties">
            {RailSlot ? <RailSlot issue={currentIssue} /> : null}
          </aside>
        </div>
      </>
    );
  };

  if (mode === 'full') {
    return (
      <section
        ref={rootRef}
        className="surface--full"
        aria-labelledby={`issue-summary-${issueKey}`}
        tabIndex={-1}
        data-mount-id={mountId}
        data-mount-seq={mountSeq}
      >
        {renderContent()}
      </section>
    );
  }

  return (
    <section
      ref={rootRef}
      className="surface--drawer"
      role="dialog"
      aria-modal={isMobile ? 'true' : 'false'}
      aria-labelledby={`issue-summary-${issueKey}`}
      tabIndex={-1}
      data-mount-id={mountId}
      data-mount-seq={mountSeq}
    >
      {renderContent()}
    </section>
  );
}

export function IssueSurface(): JSX.Element | null {
  const { mode, issueKey, projectKey } = useIssueSurfaceRoute();

  if (mode === null || issueKey === null) {
    return null;
  }

  return (
    <IssueSurfaceRoot
      mode={mode}
      issueKey={issueKey}
      projectKey={projectKey}
    />
  );
}
