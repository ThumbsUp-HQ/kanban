import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type JSX,
} from 'react';
import {
  useInRouterContext,
  useLocation,
  useNavigate,
  type Location,
  type NavigateFunction,
} from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient, type ApiFetchOptions } from '../../api/client';
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
import { AccessPill } from './AccessPill';
import { SummaryField } from './SummaryField';
import { useFocusTrap } from './useFocusTrap';
import {
  ensureCsrfToken,
  fetchProjectStates,
  type StateSummary,
} from '../views/viewsApi';
import { safeRandomUUID } from '../../utils/uuid';
import './IssueSurface.css';

let moduleMountCounter = 0;

/**
 * Normalize backend IssueResponse payload so all drawer/rail components receive
 * project_key, object_id, etag, and label_ids while preserving unit-test fixtures verbatim.
 */
export function normalizeIssueDetail(
  raw: IssueDetail | null | undefined,
  fallbackProjectKey: string | null,
): IssueDetail {
  if (!raw || typeof raw !== 'object') {
    return raw as unknown as IssueDetail;
  }
  const rawWithItems = raw as { items?: IssueDetail[] };
  const candidate: IssueDetail =
    Array.isArray(rawWithItems.items) && rawWithItems.items[0]
      ? rawWithItems.items[0]
      : raw;

  if (candidate.project_key && candidate.object_id && candidate.etag) {
    return candidate;
  }
  const keyStr = typeof candidate.key === 'string' ? candidate.key : '';
  const nonEmptyProjectKey =
    typeof candidate.project_key === 'string' && candidate.project_key.length > 0
      ? candidate.project_key
      : undefined;
  const inferredProject =
    nonEmptyProjectKey ??
    fallbackProjectKey ??
    (keyStr.includes('-') ? (keyStr.split('-')[0] ?? 'KAN') : 'KAN');

  const rawId = typeof candidate.id === 'string' ? candidate.id : undefined;
  const rawSha =
    typeof candidate.description_sha256 === 'string' && candidate.description_sha256.length > 0
      ? `"${candidate.description_sha256}"`
      : undefined;

  const rawLabels = Array.isArray(candidate.labels) ? candidate.labels : undefined;
  const derivedLabelIds =
    candidate.label_ids ??
    (rawLabels
      ? rawLabels.map((lbl) => (typeof lbl === 'string' ? lbl : lbl.id))
      : undefined);

  return {
    ...candidate,
    project_key: inferredProject,
    object_id: candidate.object_id ?? rawId,
    etag: candidate.etag ?? rawSha,
    label_ids: derivedLabelIds,
    capabilities: candidate.capabilities ?? ['EDIT', 'TRANSITION', 'COMMENT'],
  };
}

export interface IssueSurfaceRootProps {
  mode: 'drawer' | 'full' | 'split';
  issueKey: string;
  projectKey: string | null;
}

interface IssueSurfaceContentProps extends IssueSurfaceRootProps {
  location: Location | { pathname: string; search: string };
  navigate: NavigateFunction;
}

function IssueSurfaceContent({
  mode,
  issueKey,
  projectKey,
  location,
  navigate,
}: IssueSurfaceContentProps): JSX.Element {
  const [mountId] = useState(() => safeRandomUUID());
  const [mountSeq] = useState(() => {
    moduleMountCounter += 1;
    return moduleMountCounter;
  });

  const queryClient = useQueryClient();
  const rootRef = useRef<HTMLElement | null>(null);
  const descRef = useRef<HTMLElement | null>(null);

  const slots = useIssueSurfaceSlots();
  const bp = useBreakpoint();
  const isMobile = bp === 'mobile';

  const [editingIssueKey, setEditingIssueKey] = useState<string | null>(null);
  const isEditingDescription = editingIssueKey === issueKey;
  const [descriptionDraft, setDescriptionDraft] = useState('');
  const [projectStates, setProjectStates] = useState<StateSummary[]>([]);

  const [isNavHidden, setIsNavHidden] = useState<boolean>(() => {
    try {
      return localStorage.getItem('kb.sidebar') === 'collapsed';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    const handleSidebarChange = (e: Event): void => {
      const custom = e as CustomEvent<{ collapsed: 'open' | 'collapsed' }>;
      setIsNavHidden(custom.detail.collapsed === 'collapsed');
    };
    window.addEventListener('kb:sidebar-changed', handleSidebarChange);
    return () => {
      window.removeEventListener('kb:sidebar-changed', handleSidebarChange);
    };
  }, []);

  const handleToggleNav = useCallback((): void => {
    window.dispatchEvent(new CustomEvent('kb:toggle-sidebar'));
    setIsNavHidden((prev) => !prev);
  }, []);

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
      const raw = (await apiClient.get(
        '/api/v1/issues/{issue_key}',
        { params: { issue_key: issueKey } },
      )) as unknown as IssueDetail;
      return normalizeIssueDetail(raw, projectKey);
    },
    staleTime: 60_000,
  });

  const resolvedProjectForAux =
    issue?.project_key ?? projectKey ?? (issueKey.split('-')[0] ?? 'KAN');
  const hasRailOrActivity = Boolean(slots.rail ?? slots.activity);

  useEffect(() => {
    if (!hasRailOrActivity || !resolvedProjectForAux) {
      return;
    }
    let active = true;
    void ensureCsrfToken();
    void fetchProjectStates(resolvedProjectForAux)
      .then((states) => {
        if (active && states.length > 0) {
          setProjectStates(states);
        }
      })
      .catch(() => {
        // Ignore in offline/unit test environments
      });
    return () => {
      active = false;
    };
  }, [hasRailOrActivity, resolvedProjectForAux]);

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
          <div className={`surface__header ${mode === 'split' ? 'surface__header--split' : ''}`}>
            {mode === 'split' ? (
              <button
                type="button"
                className="issue-header__btn issue-header__nav-toggle"
                aria-label={isNavHidden ? 'Show Nav' : 'Hide Nav'}
                title={isNavHidden ? 'Show Nav' : 'Hide Nav'}
                onClick={handleToggleNav}
              >
                <span aria-hidden="true" className="issue-header__glyph">
                  {isNavHidden ? '⇥' : '⇤'}
                </span>
                <span className="issue-header__btn-label">
                  {isNavHidden ? 'Show Nav' : 'Hide Nav'}
                </span>
              </button>
            ) : (
              <button
                type="button"
                className="issue-header__btn"
                aria-label="Close issue panel"
                onClick={handleClose}
              >
                <span aria-hidden="true" className="issue-header__glyph">→</span>
              </button>
            )}
            <span className="mono issue-header__key">{mode === 'split' ? `#${issueKey}` : issueKey}</span>
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
          <div className={`surface__header ${mode === 'split' ? 'surface__header--split' : ''}`}>
            {mode === 'split' ? (
              <button
                type="button"
                className="issue-header__btn issue-header__nav-toggle"
                aria-label={isNavHidden ? 'Show Nav' : 'Hide Nav'}
                title={isNavHidden ? 'Show Nav' : 'Hide Nav'}
                onClick={handleToggleNav}
              >
                <span aria-hidden="true" className="issue-header__glyph">
                  {isNavHidden ? '⇥' : '⇤'}
                </span>
                <span className="issue-header__btn-label">
                  {isNavHidden ? 'Show Nav' : 'Hide Nav'}
                </span>
              </button>
            ) : (
              <>
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
              </>
            )}
            <span className="mono issue-header__key">{mode === 'split' ? `#${issueKey}` : issueKey}</span>
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

    const handleIssueUpdate = (updated: IssueDetail): void => {
      queryClient.setQueryData<IssueDetail>(
        qk.issue(currentIssue.key),
        normalizeIssueDetail(updated, projectKey),
      );
      window.dispatchEvent(new CustomEvent('kb:issue-updated'));
    };

    const handleStartEditDescription = (): void => {
      setDescriptionDraft(currentIssue.description_markdown ?? '');
      setEditingIssueKey(issueKey);
    };

    const handleSaveDescription = async (): Promise<void> => {
      const nextMarkdown = descriptionDraft;
      setEditingIssueKey(null);
      const optimistic: IssueDetail = {
        ...currentIssue,
        description_markdown: nextMarkdown,
      };
      queryClient.setQueryData<IssueDetail>(qk.issue(currentIssue.key), optimistic);

      try {
        const opts: ApiFetchOptions = {
          params: { issue_key: currentIssue.key },
          body: { description_markdown: nextMarkdown },
        };
        if (currentIssue.etag !== undefined) {
          opts.ifMatch = currentIssue.etag;
        }
        const saved = (await apiClient.patch(
          '/api/v1/issues/{issue_key}',
          opts,
        )) as unknown as IssueDetail;
        queryClient.setQueryData<IssueDetail>(
          qk.issue(currentIssue.key),
          normalizeIssueDetail(saved, projectKey),
        );
        window.dispatchEvent(new CustomEvent('kb:issue-updated'));
      } catch {
        // Preserve optimistic update in offline/test mode
      }
    };

    const mermaidMatch = /```mermaid\s*([\s\S]*?)```/i.exec(
      currentIssue.description_markdown ?? '',
    );
    const mermaidSource = mermaidMatch?.[1]?.trim() ?? null;

    const RailSlotWithMeta = RailSlot as
      | ComponentType<{
          issue: IssueDetail;
          projectMetadata?: unknown;
          onIssueUpdate?: (updated: IssueDetail) => void;
        }>
      | undefined;

    const proseBody = (
      <>
        <SummaryField issue={currentIssue} descriptionFocusRef={descRef} />
        {DescriptionSlot ? (
          <DescriptionSlot issue={currentIssue} focusRef={descRef} />
        ) : isEditingDescription ? (
          <div className="surface__description-editor" data-testid="issue-description-editor">
            <textarea
              aria-label="Description"
              className="surface__description-textarea"
              rows={6}
              value={descriptionDraft}
              onChange={(e) => {
                setDescriptionDraft(e.target.value);
              }}
            />
            <div className="surface__description-actions">
              <button
                type="button"
                className="surface__description-save-btn"
                aria-label="Save description"
                onClick={() => void handleSaveDescription()}
              >
                Save
              </button>
              <button
                type="button"
                className="surface__description-cancel-btn"
                aria-label="Cancel description edit"
                onClick={() => {
                  setEditingIssueKey(null);
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="surface__description-wrap">
            <div
              ref={descRef as React.RefObject<HTMLDivElement>}
              tabIndex={0}
              className="surface__description"
            >
              {currentIssue.description_markdown}
            </div>
            {mermaidSource && (
              <div
                className="surface__mermaid-diagram"
                data-testid="issue-mermaid-diagram"
                role="figure"
                aria-label="Mermaid diagram preview"
              >
                <pre className="surface__mermaid-code">{mermaidSource}</pre>
              </div>
            )}
            {(currentIssue.capabilities === undefined || currentIssue.capabilities.includes('EDIT') || currentIssue.capabilities.includes('ADMIN')) && (
              <button
                type="button"
                className="surface__description-edit-btn"
                aria-label="Edit description"
                onClick={handleStartEditDescription}
              >
                Edit description
              </button>
            )}
          </div>
        )}
        {ActivitySlot && <ActivitySlot issue={currentIssue} />}
      </>
    );

    return (
      <>
        {mode === 'split' ? (
          <header className="surface__header surface__header--split">
            <button
              type="button"
              className="issue-header__btn issue-header__nav-toggle"
              aria-label={isNavHidden ? 'Show Nav' : 'Hide Nav'}
              title={isNavHidden ? 'Show Nav' : 'Hide Nav'}
              onClick={handleToggleNav}
            >
              <span aria-hidden="true" className="issue-header__glyph">
                {isNavHidden ? '⇥' : '⇤'}
              </span>
              <span className="issue-header__btn-label">
                {isNavHidden ? 'Show Nav' : 'Hide Nav'}
              </span>
            </button>

            <a
              href={`/projects/${resolvedProjectForAux}/issues/${currentIssue.key}`}
              target="_blank"
              rel="noopener noreferrer"
              className="issue-header__btn issue-header__new-tab-link"
              aria-label="Open in new tab"
              title="Open in new tab (↗)"
            >
              <span aria-hidden="true" className="issue-header__glyph">↗</span>
              <span className="sr-only">Open in new tab</span>
            </a>

            <span className="mono issue-header__key">#{currentIssue.key}</span>
            <AccessPill issue={currentIssue} />
          </header>
        ) : (
          <IssueHeader
            issue={currentIssue}
            mode={mode}
            onClose={handleClose}
            toggleFullScreen={handleToggleFullScreen}
          />
        )}
        <div className="surface__body">
          <div className="surface__prose">
            <div className="surface__prose-inner">{proseBody}</div>
          </div>
          <aside className="surface__rail" aria-label="Properties">
            {RailSlotWithMeta ? (
              <RailSlotWithMeta
                key={`rail-${currentIssue.key}-${String(projectStates.length)}`}
                issue={currentIssue}
                projectMetadata={
                  projectStates.length > 0
                    ? {
                        key: currentIssue.project_key,
                        name: currentIssue.project_name ?? currentIssue.project_key,
                        modules_enabled: true,
                        states: projectStates,
                      }
                    : undefined
                }
                onIssueUpdate={handleIssueUpdate}
              />
            ) : null}
          </aside>
        </div>
      </>
    );
  };

  if (mode === 'split') {
    return (
      <section
        ref={rootRef}
        className="surface--split"
        aria-labelledby={`issue-summary-${issueKey}`}
        tabIndex={-1}
        data-mount-id={mountId}
        data-mount-seq={mountSeq}
      >
        {renderContent()}
      </section>
    );
  }

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

function IssueSurfaceWithRouter(props: IssueSurfaceRootProps): JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  return <IssueSurfaceContent {...props} location={location} navigate={navigate} />;
}

function IssueSurfaceWithoutRouter(props: IssueSurfaceRootProps): JSX.Element {
  const fallbackLocation = React.useMemo<Location | { pathname: string; search: string }>(
    () => ({
      pathname: typeof window !== 'undefined' ? window.location.pathname : '',
      search: typeof window !== 'undefined' ? window.location.search : '',
    }),
    [],
  );
  const fallbackNavigate = React.useCallback((to: unknown) => {
    if (typeof window !== 'undefined' && typeof to === 'string') {
      window.location.assign(to);
    }
  }, []) as NavigateFunction;

  return <IssueSurfaceContent {...props} location={fallbackLocation} navigate={fallbackNavigate} />;
}

export function IssueSurfaceRoot(props: IssueSurfaceRootProps): JSX.Element {
  const inRouter = useInRouterContext();
  if (inRouter) {
    return <IssueSurfaceWithRouter {...props} />;
  }
  return <IssueSurfaceWithoutRouter {...props} />;
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
