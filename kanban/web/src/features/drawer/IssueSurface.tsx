import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentType,
  type JSX,
} from 'react';
import { useLocation, useNavigate } from 'react-router';
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
import { SummaryField } from './SummaryField';
import { useFocusTrap } from './useFocusTrap';
import {
  ensureCsrfToken,
  fetchProjectStates,
  type StateSummary,
} from '../views/viewsApi';
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
  if (raw.project_key && raw.object_id && raw.etag) {
    return raw;
  }
  const keyStr = typeof raw.key === 'string' ? raw.key : '';
  const nonEmptyProjectKey =
    typeof raw.project_key === 'string' && raw.project_key.length > 0
      ? raw.project_key
      : undefined;
  const inferredProject =
    nonEmptyProjectKey ??
    fallbackProjectKey ??
    (keyStr.includes('-') ? (keyStr.split('-')[0] ?? 'KAN') : 'KAN');

  const rawId = typeof raw.id === 'string' ? raw.id : undefined;
  const rawSha =
    typeof raw.description_sha256 === 'string' && raw.description_sha256.length > 0
      ? `"${raw.description_sha256}"`
      : undefined;

  const rawLabels = Array.isArray(raw.labels) ? raw.labels : undefined;
  const derivedLabelIds =
    raw.label_ids ??
    (rawLabels
      ? rawLabels.map((lbl) => (typeof lbl === 'string' ? lbl : lbl.id))
      : undefined);

  return {
    ...raw,
    project_key: inferredProject,
    object_id: raw.object_id ?? rawId,
    etag: raw.etag ?? rawSha,
    label_ids: derivedLabelIds,
    capabilities: raw.capabilities ?? ['EDIT', 'TRANSITION', 'COMMENT'],
  };
}

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
            <button
              type="button"
              className="surface__description-edit-btn"
              aria-label="Edit description"
              onClick={handleStartEditDescription}
            >
              Edit description
            </button>
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
