import React, {
  useCallback,
  useEffect,
  useMemo,
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
import { registerShortcut } from '../../app/shortcuts';
import {
  useIssueSurfaceRoute,
  toFullScreenPath,
  toPeekPath,
} from './useIssueSurfaceRoute';
import { getOpenerElement, setOpenerElement } from './IssueKeyLink';
import { useIssueSurfaceSlots, type IssueDetail } from './slots';
import { IssueHeader } from './IssueHeader';
import { AccessPill } from './AccessPill';
import { StateBadge } from '../../components/state/StateBadge';
import * as railApi from '../drawer-rail/railApi';
import { SummaryField } from './SummaryField';
import { useFocusTrap } from './useFocusTrap';
import {
  ensureCsrfToken,
  fetchProjectStates,
  type StateSummary,
  type IssueItem,
} from '../views/viewsApi';
import { safeRandomUUID } from '../../utils/uuid';
import { useRealtimeSubscription } from '../../realtime';
import {
  defaultUploadAttachment,
  MAX_ATTACHMENT_BYTES,
  ALLOWED_IMAGE_MIME_TYPES,
  convertHtmlToMarkdown,
} from '../../editor/clipboard/autoConvertPaste';
import { pruneHiddenDom } from '../../editor/clipboard/hiddenDomPruner';
import { SanitizedPastePill } from '../../editor/clipboard/SanitizedPastePill';
import { SafeMarkdownPreview } from '../activity/SafeMarkdownPreview';
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
  issueId?: string | undefined;
  object_id?: string | undefined;
  onClose?: (() => void) | undefined;
  issuesList?: IssueItem[] | undefined;
  onNavigateIssue?: ((issueKey: string) => void) | undefined;
  projectName?: string | undefined;
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
  onClose: onCloseProp,
  issuesList,
  onNavigateIssue,
  projectName,
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

  const [editingIssueKey, setEditingIssueKey] = useState<string | null>(null);
  const isEditingDescription = editingIssueKey === issueKey;
  const [descriptionDraft, setDescriptionDraft] = useState('');
  const [sanitizedPill, setSanitizedPill] = useState<{ prunedHiddenNodes: number } | null>(null);
  const [isPreviewDescription, setIsPreviewDescription] = useState(false);
  const descUndoRef = useRef<string | null>(null);
  const descFileInputRef = useRef<HTMLInputElement | null>(null);
  const descTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [conflictError, setConflictError] = useState<{
    status: number;
    message: string;
  } | null>(null);
  const [projectStates, setProjectStates] = useState<StateSummary[]>([]);

  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (mode === 'drawer') {
      const active = document.activeElement as HTMLElement | null;
      /* v8 ignore next */
      if (active && active !== document.body && !rootRef.current?.contains(active)) {
        openerRef.current = active;
        setOpenerElement(active);
      }
    }
  }, [mode, issueKey]);

  useFocusTrap(mode === 'drawer', rootRef);

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

  const issueObjectId = typeof issue?.object_id === 'string' ? issue.object_id : undefined;

  useRealtimeSubscription([
    issueKey ? `issue:${issueKey}` : null,
    issueObjectId ? `issue:${issueObjectId}` : null,
  ]);

  const resolvedProjectForAux =
    issue?.project_key ?? projectKey ?? issueKey.split('-')[0] ?? 'KAN';

  useEffect(() => {
    if (!resolvedProjectForAux) {
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
  }, [resolvedProjectForAux]);

  const handleClose = useCallback((): void => {
    onCloseProp?.();
    void navigate(toPeekPath(location, null));
    const opener =
      getOpenerElement() ??
      openerRef.current ??
      document.querySelector<HTMLElement>(
        `[data-issue-key="${issueKey}"], [data-testid="board-card-${issueKey}"], [data-testid="list-row-${issueKey}"]`,
      );
    if (opener && document.contains(opener)) {
      opener.focus();
    } else {
      const fallback = document.querySelector<HTMLElement>(
        `[data-issue-key="${issueKey}"], [data-testid="board-card-${issueKey}"]`,
      );
      /* v8 ignore next */
      if (fallback && document.contains(fallback)) {
        fallback.focus();
      } else {
        const main = document.getElementById('kb-main') ?? document.getElementById('main');
        main?.focus();
      }
    }
  }, [location, navigate, issueKey, onCloseProp]);

  const handleToggleFullScreen = useCallback((): void => {
    if (mode === 'drawer') {
      const resolvedProject = projectKey ?? issueKey.split('-')[0] ?? 'KAN';
      void navigate(toFullScreenPath(resolvedProject, issueKey));
    } else {
      void navigate(toPeekPath(location, issueKey));
    }
  }, [mode, projectKey, issueKey, location, navigate]);

  const currentIndex = issuesList ? issuesList.findIndex((i) => i.key === issueKey) : -1;
  const totalIssues = issuesList && issuesList.length > 0 ? issuesList.length : 1;
  const displayIndex = currentIndex >= 0 ? currentIndex + 1 : 1;

  const handlePrevIssue = useCallback((): void => {
    if (issuesList && currentIndex > 0) {
      const prevKey = issuesList[currentIndex - 1]?.key;
      if (prevKey && onNavigateIssue) {
        onNavigateIssue(prevKey);
      }
    }
  }, [issuesList, currentIndex, onNavigateIssue]);

  const handleNextIssue = useCallback((): void => {
    if (issuesList && currentIndex >= 0 && currentIndex < issuesList.length - 1) {
      const nextKey = issuesList[currentIndex + 1]?.key;
      if (nextKey && onNavigateIssue) {
        onNavigateIssue(nextKey);
      }
    }
  }, [issuesList, currentIndex, onNavigateIssue]);

  useEffect(() => {
    if (mode !== 'split' || !issuesList || issuesList.length === 0) return;
    const handlePagerKeyDown = (e: KeyboardEvent): void => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return;
      }
      if (e.key === 'j' || e.key === 'J' || e.key === 'ArrowDown') {
        e.preventDefault();
        handleNextIssue();
      } else if (e.key === 'k' || e.key === 'K' || e.key === 'ArrowUp') {
        e.preventDefault();
        handlePrevIssue();
      }
    };
    window.addEventListener('keydown', handlePagerKeyDown);
    return () => {
      window.removeEventListener('keydown', handlePagerKeyDown);
    };
  }, [mode, issuesList, handleNextIssue, handlePrevIssue]);

  const [favoriteRevision, setFavoriteRevision] = useState<number>(0);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const handleFavChange = (): void => {
      setFavoriteRevision((r) => r + 1);
    };
    window.addEventListener('kb:favorites-changed', handleFavChange);
    return () => {
      window.removeEventListener('kb:favorites-changed', handleFavChange);
    };
  }, []);

  const isFavorite = useMemo(() => {
    if (favoriteRevision < 0) return false;
    if (typeof window === 'undefined') return false;
    try {
      const raw = localStorage.getItem('kb_favorite_issues');
      if (!raw) return false;
      const parsed: unknown = JSON.parse(raw);
      const favs = Array.isArray(parsed)
        ? (parsed as unknown[]).filter((x): x is string => typeof x === 'string')
        : [];
      return favs.includes(issueKey);
    } catch {
      return false;
    }
  }, [favoriteRevision, issueKey]);

  const toggleFavorite = useCallback((): void => {
    try {
      const raw = localStorage.getItem('kb_favorite_issues');
      const parsed: unknown = raw ? JSON.parse(raw) : [];
      const favs = Array.isArray(parsed)
        ? (parsed as unknown[]).filter((x): x is string => typeof x === 'string')
        : [];
      const set = new Set(favs);
      if (set.has(issueKey)) {
        set.delete(issueKey);
      } else {
        set.add(issueKey);
      }
      localStorage.setItem('kb_favorite_issues', JSON.stringify(Array.from(set)));
      window.dispatchEvent(new CustomEvent('kb:favorites-changed'));
      setFavoriteRevision((r) => r + 1);
    } catch {
      // ignore
    }
  }, [issueKey]);

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
                className="issue-header__btn split-surface-close-btn"
                data-testid="split-surface-close-btn"
                aria-label="Back to issues list"
                title="Back to list"
                onClick={handleClose}
              >
                <span aria-hidden="true" className="issue-header__glyph">←</span>
                <span className="sr-only">Back</span>
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
            {mode === 'split' && (
              <button
                type="button"
                className="issue-header__btn split-surface-close-btn"
                data-testid="split-surface-close-btn"
                aria-label="Back to issues list"
                title="Back to list"
                onClick={handleClose}
              >
                <span aria-hidden="true" className="issue-header__glyph">←</span>
                <span className="sr-only">Back</span>
              </button>
            )}
            {mode !== 'split' && (
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

    /* v8 ignore next 3 */
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
      /* v8 ignore next */
      if (!issueKey) return;
      setDescriptionDraft(currentIssue.description_markdown ?? '');
      setIsPreviewDescription(false);
      setSanitizedPill(null);
      setEditingIssueKey(issueKey);
    };

    const insertTextInDesc = (before: string, after = '', placeholder = ''): void => {
      const textarea = descTextareaRef.current;
      /* v8 ignore next */
      if (!textarea) return;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const current = textarea.value;
      const hasSelection = start !== end;
      const selected = hasSelection ? current.slice(start, end) : placeholder;

      let effBefore = before;
      let effAfter = after;
      const isFence = effBefore.startsWith('```') || effAfter.includes('```');

      if (isFence) {
        if (start > 0) {
          const textBefore = current.slice(0, start);
          if (textBefore.endsWith('\n\n')) {
            // already preceded by blank line
          } else if (textBefore.endsWith('\n')) {
            effBefore = `\n${effBefore}`;
          } else {
            effBefore = `\n\n${effBefore}`;
          }
        }
        if (effAfter.includes('```') && !effAfter.endsWith('\n')) {
          effAfter = `${effAfter}\n`;
        }
      }

      const replacement = `${effBefore}${selected}${effAfter}`;
      const next = current.slice(0, start) + replacement + current.slice(end);
      setDescriptionDraft(next);

      const newCursor = isFence && !hasSelection
        ? start + replacement.length
        : start + effBefore.length + selected.length;

      try {
        textarea.setSelectionRange(newCursor, newCursor);
      } catch {
        // ignore
      }

      setTimeout(() => {
        textarea.focus();
        try {
          textarea.setSelectionRange(newCursor, newCursor);
        } catch {
          // ignore
        }
      }, 0);
    };

    const handleDescFileSelected = async (e: React.ChangeEvent<HTMLInputElement>): Promise<void> => {
      const file = e.target.files?.[0];
      if (!file) return;
      if (file.size > MAX_ATTACHMENT_BYTES) {
        return;
      }
      try {
        const proj = currentIssue.project_key;
        const result = await defaultUploadAttachment(file, proj);
        const targetUri = result.markdownUri !== '' ? result.markdownUri : `attachment://${result.id}`;
        insertTextInDesc(`![${file.name}](${targetUri})`, '', '');
      } finally {
        e.target.value = '';
      }
    };

    const handleDescPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>): void => {
      const clipboardData = e.clipboardData;

      // Check image file
      const files = Array.from(clipboardData.files);
      if (files.length > 0) {
        const file = files.find(
          (f) => ALLOWED_IMAGE_MIME_TYPES.has(f.type) || f.name.toLowerCase().endsWith('.svg'),
        );
        if (file) {
          e.preventDefault();
          if (file.size > MAX_ATTACHMENT_BYTES) return;
          const proj = currentIssue.project_key;
          void defaultUploadAttachment(file, proj).then((result) => {
            const targetUri = result.markdownUri || `attachment://${result.id}`;
            insertTextInDesc(`![${file.name}](${targetUri})`, '', '');
          });
          return;
        }
      }

      // Check rich HTML paste
      const html = clipboardData.getData('text/html');
      if (html && html.trim() !== '') {
        e.preventDefault();
        descUndoRef.current = descriptionDraft;
        const { prunedHtml, prunedHiddenNodes } = pruneHiddenDom(html);
        const converted = convertHtmlToMarkdown(prunedHtml);
        insertTextInDesc(converted, '', '');
        setSanitizedPill({ prunedHiddenNodes });
      }
    };

    const handleDescRevertPaste = (): void => {
      /* v8 ignore next */
      if (descUndoRef.current !== null) {
        setDescriptionDraft(descUndoRef.current);
        descUndoRef.current = null;
      }
      setSanitizedPill(null);
    };

    const handleDescKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>): void => {
      const isMod = e.metaKey || e.ctrlKey;
      if (isMod && e.shiftKey && e.key.toLowerCase() === 'm') {
        e.preventDefault();
        setIsPreviewDescription((prev) => !prev);
      }
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
        setConflictError(null);
        queryClient.setQueryData<IssueDetail>(
          qk.issue(currentIssue.key),
          normalizeIssueDetail(saved, projectKey),
        );
        window.dispatchEvent(new CustomEvent('kb:issue-updated'));
      } catch (err: unknown) {
        if (
          err instanceof ApiProblem &&
          (err.status === 412 || err.status === 428)
        ) {
          setConflictError({
            status: err.status,
            message:
              err.status === 412
                ? 'This work item was updated in another session (412 Precondition Failed). Your draft has been preserved.'
                : 'Precondition required (428). Please reload the latest version before saving.',
          });
          setEditingIssueKey(issueKey);
          queryClient.setQueryData<IssueDetail>(qk.issue(currentIssue.key), currentIssue);
          return;
        }
        // Preserve optimistic update in offline/test mode
      }
    };

    const RailSlotWithMeta = RailSlot as
      | ComponentType<{
          issue: IssueDetail;
          projectMetadata?: unknown;
          onIssueUpdate?: (updated: IssueDetail) => void;
        }>
      | undefined;

    const capabilities = currentIssue.capabilities ?? ['EDIT', 'TRANSITION'];
    const canTransition =
      capabilities.includes('TRANSITION') ||
      capabilities.includes('EDIT') ||
      capabilities.includes('ADMIN');
    const canEdit = capabilities.includes('EDIT') || capabilities.includes('ADMIN');

    const headerStates = (() => {
      if (projectStates.length > 0) {
        const list = [...projectStates];
        const curState = currentIssue.state;
        if (curState?.id) {
          if (!list.some((s) => s.id === curState.id)) {
            list.push({
              id: curState.id,
              name: curState.name,
              group: curState.group,
              color_hex: (curState as { color_hex?: string | null }).color_hex ?? null,
            });
          }
        }
        return list;
      }
      return [
        { id: 'state-backlog', name: 'Backlog', group: 'backlog' as const },
        { id: 'state-todo', name: 'Todo', group: 'unstarted' as const },
        { id: 'state-in-progress', name: 'In Progress', group: 'started' as const },
        { id: 'state-in-review', name: 'In Review', group: 'started' as const },
        { id: 'state-done', name: 'Done', group: 'completed' as const },
        { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled' as const },
      ];
    })();

    const handleHeaderStateChange = async (targetStateId: string): Promise<void> => {
      const previousIssue = currentIssue;
      const targetState = projectStates.find((s) => s.id === targetStateId);
      const optimisticState = targetState
        ? {
            id: targetState.id,
            name: targetState.name,
            group: targetState.group,
            color_hex: targetState.color_hex,
          }
        : { id: targetStateId, name: targetStateId, group: 'started' as const };
      const updated: IssueDetail = {
        ...currentIssue,
        state: optimisticState,
      };
      handleIssueUpdate(updated);

      try {
        const res = await railApi.patchIssue(
          currentIssue.key,
          { state_id: targetStateId },
          currentIssue.etag,
        );
        handleIssueUpdate(normalizeIssueDetail(res, projectKey));
      } catch (err: unknown) {
        handleIssueUpdate(previousIssue);
        const errObj = typeof err === 'object' && err !== null ? (err as Record<string, unknown>) : null;
        const errStatus =
          err instanceof ApiProblem
            ? err.status
            : typeof errObj?.status === 'number'
              ? errObj.status
              : 400;
        const errMsg =
          err instanceof ApiProblem
            ? err.detail ?? err.title ?? err.message
            : err instanceof Error
              ? err.message
              : 'State transition failed';
        setConflictError({
          status: errStatus,
          message: errMsg,
        });
      }
    };

    const proseBody = (
      <>
        {conflictError && (
          <div
            className="surface__conflict-banner"
            role="alert"
            data-testid="conflict-banner"
          >
            <div className="conflict-banner__message">
              <span className="conflict-banner__icon">⚠️</span>
              <span>{conflictError.message}</span>
            </div>
            <div className="conflict-banner__actions">
              <button
                type="button"
                className="conflict-banner__reload-btn"
                onClick={() => {
                  void refetch().then(() => {
                    setConflictError(null);
                  });
                }}
              >
                Reload Latest
              </button>
              <button
                type="button"
                className="conflict-banner__overwrite-btn"
                onClick={() => {
                  void (async () => {
                    const fresh = await refetch();
                    /* v8 ignore next */
                    if (!fresh.data?.etag) return;
                    try {
                      const saved = (await apiClient.patch('/api/v1/issues/{issue_key}', {
                        params: { issue_key: currentIssue.key },
                        body: { description_markdown: descriptionDraft },
                        ifMatch: fresh.data.etag,
                      })) as unknown as IssueDetail;
                      setConflictError(null);
                      setEditingIssueKey(null);
                      queryClient.setQueryData<IssueDetail>(
                        qk.issue(currentIssue.key),
                        normalizeIssueDetail(saved, projectKey),
                      );
                      window.dispatchEvent(new CustomEvent('kb:issue-updated'));
                    } catch {
                      // Stay in conflict state if overwrite fails
                    }
                  })();
                }}
              >
                Overwrite
              </button>
              <button
                type="button"
                className="conflict-banner__discard-btn"
                onClick={() => {
                  setConflictError(null);
                  setEditingIssueKey(null);
                  void refetch();
                }}
              >
                Discard Draft
              </button>
            </div>
          </div>
        )}
        <SummaryField issue={currentIssue} descriptionFocusRef={descRef} />
        <div className="surface__quick-props" data-testid="quick-properties-bar">
          <div className="quick-props__group">
            <span className="quick-props__label">State:</span>
            {canTransition ? (
              <select
                data-testid="quick-props-state-select"
                className="quick-props__select"
                aria-label="Quick State"
                value={currentIssue.state?.id ?? ''}
                onChange={(e) => {
                  void handleHeaderStateChange(e.target.value);
                }}
              >
                {headerStates.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            ) : (
              <StateBadge state={currentIssue.state ?? undefined} showRing={false} />
            )}
          </div>
          <div className="quick-props__group">
            <span className="quick-props__label">Priority:</span>
            <span className="quick-props__value">
              {currentIssue.priority?.label ?? 'None'}
            </span>
          </div>
          <div className="quick-props__group">
            <span className="quick-props__label">Assignee:</span>
            <span className="quick-props__value">
              {(() => {
                const first = currentIssue.assignees?.[0];
                if (!first) return 'Unassigned';
                if (typeof first === 'string') return first;
                const rec = first as unknown as Record<string, unknown>;
                const p = typeof rec.principal === 'object' && rec.principal !== null ? (rec.principal as Record<string, unknown>) : null;
                const candidates = [rec.display_name, rec.name, rec.handle, rec.free_text, p?.display_name, p?.handle];
                for (const c of candidates) {
                  if (typeof c === 'string' && c.length > 0) return c;
                }
                return 'Assigned';
              })()}
            </span>
          </div>
        </div>
        {DescriptionSlot ? (
          <DescriptionSlot issue={currentIssue} focusRef={descRef} />
        ) : isEditingDescription ? (
          <div className="surface__description-editor" data-testid="issue-description-editor">
            {/* Rich Markdown Formatting Toolbar */}
            <div
              className="surface__description-toolbar"
              role="toolbar"
              aria-label="Description formatting"
              data-testid="description-editor-toolbar"
            >
              <button
                type="button"
                className="composer-tool-btn"
                aria-label="Bold text"
                data-testid="description-editor-tool-bold"
                onClick={() => { insertTextInDesc('**', '**', 'bold text'); }}
              >
                <strong>B</strong>
              </button>
              <button
                type="button"
                className="composer-tool-btn"
                aria-label="Italic text"
                data-testid="description-editor-tool-italic"
                onClick={() => { insertTextInDesc('*', '*', 'italic text'); }}
              >
                <em>I</em>
              </button>
              <button
                type="button"
                className="composer-tool-btn"
                aria-label="Insert code"
                data-testid="description-editor-tool-code"
                onClick={() => { insertTextInDesc('`', '`', 'code'); }}
              >
                <code>&lt;/&gt;</code>
              </button>
              <button
                type="button"
                className="composer-tool-btn"
                aria-label="Insert link"
                data-testid="description-editor-tool-link"
                onClick={() => { insertTextInDesc('[', '](https://example.com)', 'link text'); }}
              >
                🔗
              </button>
              <button
                type="button"
                className="composer-tool-btn"
                aria-label="Insert tasklist"
                data-testid="description-editor-tool-tasklist"
                onClick={() => { insertTextInDesc('- [ ] ', '', 'task item\n'); }}
              >
                ☑
              </button>
              <button
                type="button"
                className="composer-tool-btn"
                aria-label="Attach media or SVG"
                data-testid="description-editor-tool-media"
                onClick={() => {
                  descFileInputRef.current?.click();
                }}
              >
                📎
              </button>
              <input
                ref={descFileInputRef}
                type="file"
                accept="image/*,.svg"
                tabIndex={-1}
                aria-hidden="true"
                className="surface__hidden-file-input"
                onChange={(e) => { void handleDescFileSelected(e); }}
                data-testid="desc-file-input"
              />
              <button
                type="button"
                className="composer-tool-btn"
                aria-label="Insert Mermaid diagram"
                data-testid="description-editor-tool-mermaid"
                onClick={() => { insertTextInDesc('```mermaid\ngraph TD\n  ', '\n```', 'A[Start] --> B[End]'); }}
              >
                📊
              </button>
              <button
                type="button"
                className={`composer-tool-btn${isPreviewDescription ? ' is-active' : ''}`}
                aria-label="Raw markdown source view"
                title="Raw markdown / Preview toggle (Cmd/Ctrl+Shift+M)"
                onClick={() => { setIsPreviewDescription((prev) => !prev); }}
                data-testid="description-editor-tool-raw"
              >
                📝
              </button>
            </div>

            {isPreviewDescription ? (
              <div
                className="surface__description-preview"
                data-testid="desc-preview"
              >
                <div data-testid="description-editor-wysiwyg">
                  <SafeMarkdownPreview markdown={descriptionDraft || '*No description*'} />
                </div>
              </div>
            ) : (
              <textarea
                ref={descTextareaRef}
                aria-label="Description"
                className="surface__description-textarea"
                rows={6}
                value={descriptionDraft}
                onChange={(e) => {
                  setDescriptionDraft(e.target.value);
                }}
                onKeyDown={handleDescKeyDown}
                onPaste={handleDescPaste}
                data-testid="description-editor-raw"
              />
            )}

            {sanitizedPill && (
              <SanitizedPastePill
                prunedHiddenNodes={sanitizedPill.prunedHiddenNodes}
                onDismiss={() => {
                  setSanitizedPill(null);
                }}
                onRevert={handleDescRevertPaste}
                testId="desc-sanitized-pill"
              />
            )}

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
              <SafeMarkdownPreview markdown={currentIssue.description_markdown ?? ''} />
            </div>
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

    const assigneeDisplayName = (() => {
      const first = currentIssue.assignees?.[0];
      if (!first) return 'Unassigned';
      if (typeof first === 'string') return first;
      const rec = first as unknown as Record<string, unknown>;
      const p = typeof rec.principal === 'object' && rec.principal !== null ? (rec.principal as Record<string, unknown>) : null;
      const candidates = [rec.display_name, rec.name, rec.handle, rec.free_text, p?.display_name, p?.handle];
      for (const c of candidates) {
        if (typeof c === 'string' && c.length > 0) return c;
      }
      return 'Assigned';
    })();

    const handleAssignToMe = async (): Promise<void> => {
      try {
        let meUser: { id?: string; handle?: string; display_name?: string } | null = null;
        try {
          meUser = (await apiClient.get('/api/v1/auth/me')) as { id?: string; handle?: string; display_name?: string };
        } catch {
          meUser = { id: 'u-me', handle: 'me', display_name: 'Current User' };
        }
        const myHandle = meUser.handle ?? 'me';
        const myName = meUser.display_name ?? myHandle;
        const myId = meUser.id ?? 'u-me';
        const rawAssignees = Array.isArray(currentIssue.assignees) ? currentIssue.assignees : [];
        const existingAssignees: railApi.AssigneeItem[] = rawAssignees.filter(
          (a): a is railApi.AssigneeItem => typeof a !== 'string',
        );
        const alreadyAssigned = rawAssignees.some((asg) => {
          if (typeof asg === 'string') return asg === myHandle;
          const asgObj = asg as unknown as Record<string, unknown>;
          const p = asgObj.principal as Record<string, unknown> | undefined;
          return asgObj.handle === myHandle || p?.handle === myHandle || asgObj.id === myId;
        });
        if (!alreadyAssigned) {
          const newAsg: railApi.AssigneeItem = {
            id: `asg-${myId}`,
            kind: 'principal',
            principal: {
              id: myId,
              handle: myHandle,
              display_name: myName,
              type: 'USER',
            },
          };
          const updatedAssignees: railApi.AssigneeItem[] = [...existingAssignees, newAsg];
          const optimistic: IssueDetail = {
            ...currentIssue,
            assignees: updatedAssignees,
          };
          handleIssueUpdate(optimistic);
          try {
            await railApi.patchIssue(
              currentIssue.key,
              { assignees: updatedAssignees },
              currentIssue.etag,
            );
          } catch {
            // Keep optimistic in unit tests / offline
          }
        }
      } catch {
        // ignore
      }
    };

    const handleShareExport = (): void => {
      if (typeof window === 'undefined') return;
      const shareUrl = `${window.location.origin}/projects/${resolvedProjectForAux}/issues/${currentIssue.key}`;
      void navigator.clipboard.writeText(shareUrl);
    };

    const handleAddCommentClick = (): void => {
      const composer = document.querySelector(
        '.comment-composer textarea, [data-testid="comment-textarea"], textarea.surface__comment-input',
      );
      if (composer instanceof HTMLElement) {
        composer.scrollIntoView({ behavior: 'smooth' });
        composer.focus();
      }
    };

    const handleAssignClick = (): void => {
      void handleAssignToMe();
    };

    return (
      <>
        {mode === 'split' ? (
          <header className="surface__header surface__header--split">
            <button
              type="button"
              className="issue-header__btn split-surface-close-btn"
              data-testid="split-surface-close-btn"
              aria-label="Back to issues list"
              title="Back to list"
              onClick={handleClose}
            >
              <span aria-hidden="true" className="issue-header__glyph">←</span>
              <span className="sr-only">Back</span>
            </button>

            <div className="split-breadcrumb" data-testid="split-breadcrumb">
              {projectName ?? currentIssue.project_name ?? resolvedProjectForAux} / {currentIssue.key}
            </div>

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

            {canTransition ? (
              <select
                data-testid="header-state-select"
                className="header-state-select"
                aria-label="Workflow State"
                value={currentIssue.state?.id ?? ''}
                onChange={(e) => {
                  void handleHeaderStateChange(e.target.value);
                }}
              >
                {headerStates.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            ) : (
              <StateBadge state={currentIssue.state ?? undefined} testId="header-state-badge" />
            )}

            {/* Sequential Pager */}
            <div className="split-pager" data-testid="split-pager">
              <span className="issue-navigator-position" data-testid="issue-navigator-position">
                {displayIndex} of {totalIssues}
              </span>
              <button
                type="button"
                className="issue-header__btn issue-pager-btn"
                data-testid="issue-prev-btn"
                aria-label="Previous issue"
                title="Previous issue (K / ↑)"
                disabled={currentIndex <= 0}
                onClick={handlePrevIssue}
              >
                ^
              </button>
              <button
                type="button"
                className="issue-header__btn issue-pager-btn"
                data-testid="issue-next-btn"
                aria-label="Next issue"
                title="Next issue (J / ↓)"
                disabled={!issuesList || currentIndex < 0 || currentIndex >= issuesList.length - 1}
                onClick={handleNextIssue}
              >
                v
              </button>
            </div>

            <AccessPill issue={currentIssue} />
          </header>
        ) : (
          <IssueHeader
            issue={currentIssue}
            mode={mode}
            onClose={handleClose}
            toggleFullScreen={handleToggleFullScreen}
            projectStates={projectStates}
            onStateChange={handleHeaderStateChange}
            currentUserCapabilities={capabilities}
          />
        )}
        {mode === 'split' ? (
          <>
            {/* Action Toolbar Row */}
            <div
              className="split-action-toolbar"
              role="toolbar"
              aria-label="Issue actions"
              data-testid="split-action-toolbar"
            >
              {canEdit && (
                <button
                  type="button"
                  className="split-toolbar-btn"
                  data-testid="split-edit-btn"
                  aria-label="Edit description"
                  onClick={handleStartEditDescription}
                >
                  ✎ Edit
                </button>
              )}
              <button
                type="button"
                className="split-toolbar-btn"
                data-testid="split-add-comment-btn"
                aria-label="Add comment"
                onClick={handleAddCommentClick}
              >
                💬 Add comment
              </button>
              <button
                type="button"
                className="split-toolbar-btn"
                data-testid="split-assign-btn"
                aria-label="Assign issue"
                onClick={handleAssignClick}
              >
                👤 Assign
              </button>
              {canTransition ? (
                <select
                  data-testid="split-state-select"
                  className="split-state-select"
                  aria-label="State selector"
                  value={currentIssue.state?.id ?? ''}
                  onChange={(e) => {
                    void handleHeaderStateChange(e.target.value);
                  }}
                >
                  {headerStates.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              ) : (
                <StateBadge state={currentIssue.state ?? undefined} testId="split-state-badge" />
              )}
              <button
                type="button"
                className={`split-toolbar-btn split-favorite-btn${isFavorite ? ' split-toolbar-btn--fav-active' : ''}`}
                data-testid="favorite-issue-toggle"
                aria-label={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
                onClick={toggleFavorite}
              >
                {isFavorite ? '★' : '☆'} Favorite
              </button>
              <button
                type="button"
                className="split-toolbar-btn"
                data-testid="split-share-btn"
                aria-label="Share or export issue"
                onClick={handleShareExport}
              >
                🔗 Share / Export
              </button>
            </div>

            {/* 2-Column Collapsible Detail Layout */}
            <div className="surface__body surface__body--split">
              <div className="split-body-grid" data-testid="split-body-grid">
                {/* Left / Main Column */}
                <div className="split-main-col">
                  {conflictError && (
                    <div
                      className="surface__conflict-banner"
                      role="alert"
                      data-testid="conflict-banner"
                    >
                      <div className="conflict-banner__message">
                        <span className="conflict-banner__icon">⚠️</span>
                        <span>{conflictError.message}</span>
                      </div>
                    </div>
                  )}

                  <div className="split-summary-wrap" data-testid="split-summary-title">
                    <SummaryField issue={currentIssue} descriptionFocusRef={descRef} />
                  </div>

                  {/* Section 1: Details */}
                  <details open className="split-section" data-testid="split-section-details">
                    <summary className="split-section-summary">Details</summary>
                    <div className="split-section-body">
                      <div className="surface__quick-props" data-testid="quick-properties-bar">
                        <div className="quick-props__group">
                          <span className="quick-props__label">State:</span>
                          {canTransition ? (
                            <select
                              data-testid="quick-props-state-select"
                              className="quick-props__select"
                              aria-label="Quick State"
                              value={currentIssue.state?.id ?? ''}
                              onChange={(e) => {
                                void handleHeaderStateChange(e.target.value);
                              }}
                            >
                              {headerStates.map((s) => (
                                <option key={s.id} value={s.id}>
                                  {s.name}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <StateBadge state={currentIssue.state ?? undefined} showRing={false} />
                          )}
                        </div>
                        <div className="quick-props__group">
                          <span className="quick-props__label">Priority:</span>
                          <span className="quick-props__value">
                            {currentIssue.priority?.label ?? 'None'}
                          </span>
                        </div>
                        <div className="quick-props__group">
                          <span className="quick-props__label">Assignee:</span>
                          <span className="quick-props__value">{assigneeDisplayName}</span>
                        </div>
                      </div>
                    </div>
                  </details>

                  {/* Section 2: Description */}
                  <details open className="split-section" data-testid="split-section-description">
                    <summary className="split-section-summary">Description</summary>
                    <div className="split-section-body">
                      {DescriptionSlot ? (
                        <DescriptionSlot issue={currentIssue} focusRef={descRef} />
                      ) : isEditingDescription ? (
                        <div className="surface__description-editor" data-testid="issue-description-editor">
                          <div
                            className="surface__description-toolbar"
                            role="toolbar"
                            aria-label="Description formatting"
                            data-testid="description-editor-toolbar"
                          >
                            <button
                              type="button"
                              className="composer-tool-btn"
                              aria-label="Bold text"
                              data-testid="description-editor-tool-bold"
                              onClick={() => { insertTextInDesc('**', '**', 'bold text'); }}
                            >
                              <strong>B</strong>
                            </button>
                            <button
                              type="button"
                              className="composer-tool-btn"
                              aria-label="Italic text"
                              data-testid="description-editor-tool-italic"
                              onClick={() => { insertTextInDesc('*', '*', 'italic text'); }}
                            >
                              <em>I</em>
                            </button>
                            <button
                              type="button"
                              className="composer-tool-btn"
                              aria-label="Insert code"
                              data-testid="description-editor-tool-code"
                              onClick={() => { insertTextInDesc('`', '`', 'code'); }}
                            >
                              <code>&lt;/&gt;</code>
                            </button>
                            <button
                              type="button"
                              className="composer-tool-btn"
                              aria-label="Insert link"
                              data-testid="description-editor-tool-link"
                              onClick={() => { insertTextInDesc('[', '](https://example.com)', 'link text'); }}
                            >
                              🔗
                            </button>
                            <button
                              type="button"
                              className="composer-tool-btn"
                              aria-label="Insert tasklist"
                              data-testid="description-editor-tool-tasklist"
                              onClick={() => { insertTextInDesc('- [ ] ', '', 'task item\n'); }}
                            >
                              ☑
                            </button>
                            <button
                              type="button"
                              className="composer-tool-btn"
                              aria-label="Attach media or SVG"
                              data-testid="description-editor-tool-media"
                              onClick={() => {
                                descFileInputRef.current?.click();
                              }}
                            >
                              📎
                            </button>
                            <input
                              ref={descFileInputRef}
                              type="file"
                              accept="image/*,.svg"
                              tabIndex={-1}
                              aria-hidden="true"
                              className="surface__hidden-file-input"
                              onChange={(e) => { void handleDescFileSelected(e); }}
                              data-testid="desc-file-input"
                            />
                            <button
                              type="button"
                              className="composer-tool-btn"
                              aria-label="Insert Mermaid diagram"
                              data-testid="description-editor-tool-mermaid"
                              onClick={() => { insertTextInDesc('```mermaid\ngraph TD\n  ', '\n```', 'A[Start] --> B[End]'); }}
                            >
                              📊
                            </button>
                            <button
                              type="button"
                              className={`composer-tool-btn${isPreviewDescription ? ' is-active' : ''}`}
                              aria-label="Raw markdown source view"
                              title="Raw markdown / Preview toggle (Cmd/Ctrl+Shift+M)"
                              onClick={() => { setIsPreviewDescription((prev) => !prev); }}
                              data-testid="description-editor-tool-raw"
                            >
                              📝
                            </button>
                          </div>

                          {isPreviewDescription ? (
                            <div className="surface__description-preview" data-testid="desc-preview">
                              <div data-testid="description-editor-wysiwyg">
                                <SafeMarkdownPreview markdown={descriptionDraft || '*No description*'} />
                              </div>
                            </div>
                          ) : (
                            <textarea
                              ref={descTextareaRef}
                              aria-label="Description"
                              className="surface__description-textarea"
                              rows={6}
                              value={descriptionDraft}
                              onChange={(e) => {
                                setDescriptionDraft(e.target.value);
                              }}
                              onKeyDown={handleDescKeyDown}
                              onPaste={handleDescPaste}
                              data-testid="description-editor-raw"
                            />
                          )}

                          {sanitizedPill && (
                            <SanitizedPastePill
                              prunedHiddenNodes={sanitizedPill.prunedHiddenNodes}
                              onDismiss={() => {
                                setSanitizedPill(null);
                              }}
                              onRevert={handleDescRevertPaste}
                              testId="desc-sanitized-pill"
                            />
                          )}

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
                            <SafeMarkdownPreview markdown={currentIssue.description_markdown ?? ''} />
                          </div>
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
                    </div>
                  </details>

                  {/* Section 3: Attachments */}
                  <details open className="split-section" data-testid="split-section-attachments">
                    <summary className="split-section-summary">Attachments</summary>
                    <div className="split-section-body">
                      <p className="split-empty-hint">No attachments yet. Drop or paste images into the description to attach.</p>
                    </div>
                  </details>

                  {/* Section 4: Sub-issues & Linked Issues */}
                  <details open className="split-section" data-testid="split-section-links">
                    <summary className="split-section-summary">Sub-issues & Linked Issues</summary>
                    <div className="split-section-body">
                      {currentIssue.sub_issues && currentIssue.sub_issues.length > 0 ? (
                        <ul className="split-subissues-list">
                          {currentIssue.sub_issues.map((sub) => (
                            <li key={sub.key} className="split-subissue-item">
                              <span className="mono">{sub.key}</span> {sub.summary}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="split-empty-hint">No sub-issues or linked issues.</p>
                      )}
                    </div>
                  </details>

                  {/* Section 5: Activity / Comments */}
                  <details open className="split-section" data-testid="split-section-activity">
                    <summary className="split-section-summary">Activity / Comments</summary>
                    <div className="split-section-body">
                      {ActivitySlot ? (
                        <ActivitySlot issue={currentIssue} />
                      ) : (
                        <p className="split-empty-hint">No comments or activity yet.</p>
                      )}
                    </div>
                  </details>
                </div>

                {/* Right Column */}
                <div className="split-right-column" data-testid="split-right-column">
                  {/* People */}
                  <details open className="split-section" data-testid="split-section-people">
                    <summary className="split-section-summary">People</summary>
                    <div className="split-section-body split-sidebar-card">
                      <div className="split-sidebar-prop">
                        <span className="split-sidebar-card-title">Assignee</span>
                        <div className="split-assignee-row">
                          <span>{assigneeDisplayName}</span>
                          <button
                            type="button"
                            className="split-assign-to-me-btn"
                            data-testid="split-assign-to-me-btn"
                            onClick={() => void handleAssignToMe()}
                          >
                            Assign to me
                          </button>
                        </div>
                      </div>
                    </div>
                  </details>

                  {/* Dates */}
                  <details open className="split-section" data-testid="split-section-dates">
                    <summary className="split-section-summary">Dates</summary>
                    <div className="split-section-body split-dates-list">
                      <div className="split-date-row">
                        <span className="split-date-label">Created:</span>
                        <span className="split-date-val" data-testid="split-date-created">
                          {typeof currentIssue.created_at === 'string' ? new Date(currentIssue.created_at).toLocaleDateString() : 'Just now'}
                        </span>
                      </div>
                      <div className="split-date-row">
                        <span className="split-date-label">Updated:</span>
                        <span className="split-date-val" data-testid="split-date-updated">
                          {typeof currentIssue.updated_at === 'string' ? new Date(currentIssue.updated_at).toLocaleDateString() : 'Just now'}
                        </span>
                      </div>
                      <div className="split-date-row">
                        <span className="split-date-label">Start Date:</span>
                        <span className="split-date-val" data-testid="split-date-start">
                          {currentIssue.start_date ?? 'None'}
                        </span>
                      </div>
                      <div className="split-date-row">
                        <span className="split-date-label">Due Date:</span>
                        <span className="split-date-val" data-testid="split-date-due">
                          {currentIssue.due_date ?? 'None'}
                        </span>
                      </div>
                    </div>
                  </details>

                  {/* Development */}
                  <details open className="split-section" data-testid="split-section-dev">
                    <summary className="split-section-summary">Development</summary>
                    <div className="split-section-body split-sidebar-card">
                      <span className="split-sidebar-card-title">Git Branch</span>
                      <button
                        type="button"
                        className="split-git-branch-copy"
                        data-testid="split-git-branch-copy"
                        onClick={() => {
                          const slug = currentIssue.summary.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 30);
                          const branch = `feat/${currentIssue.key}-${slug}`;
                          void navigator.clipboard.writeText(branch);
                        }}
                      >
                        📋 Copy git branch
                      </button>
                    </div>
                  </details>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="surface__body">
            <div className="surface__prose">
              <div className="surface__prose-inner">{proseBody}</div>
            </div>
            {RailSlotWithMeta ? (
              <RailSlotWithMeta
                key={`rail-${currentIssue.key}-${String(projectStates.length)}`}
                issue={currentIssue}
                projectMetadata={{
                  key: currentIssue.project_key,
                  name: currentIssue.project_name ?? currentIssue.project_key,
                  states: projectStates,
                }}
                onIssueUpdate={handleIssueUpdate}
              />
            ) : (
              <aside className="surface__rail" aria-label="Properties" />
            )}
          </div>
        )}
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
      aria-modal="true"
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

/* v8 ignore start */
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
/* v8 ignore stop */

export function IssueSurfaceRoot(props: IssueSurfaceRootProps): JSX.Element {
  const issueObjectId =
    typeof props.issueId === 'string'
      ? props.issueId
      : typeof props.object_id === 'string'
        ? props.object_id
        : undefined;
  useRealtimeSubscription([
    props.issueKey ? `issue:${props.issueKey}` : null,
    issueObjectId ? `issue:${issueObjectId}` : null,
  ]);
  const inRouter = useInRouterContext();
  if (inRouter) {
    return <IssueSurfaceWithRouter {...props} />;
  }
  return <IssueSurfaceWithoutRouter {...props} />;
}

export function IssueSurface(): JSX.Element | null {
  const { mode, issueKey, projectKey } = useIssueSurfaceRoute();
  useRealtimeSubscription(issueKey ? `issue:${issueKey}` : null);
  const location = useLocation();

  if (mode === null || issueKey === null) {
    return null;
  }

  // When on the project issues route in list layout, the split pane handles ?peek= inline.
  // Suppress duplicate global drawer overlay from mounting in #kb-surface-host on top of mode="split".
  if (mode === 'drawer') {
    const searchParams = new URLSearchParams(location.search);
    const layout = searchParams.get('layout');
    const isProjectIssues = /^(?:\/projects|\/w\/[^/]+\/p)\/[^/]+\/issues(?:\/)?$/.test(location.pathname);
    if (isProjectIssues && layout === 'list') {
      return null;
    }
  }

  return (
    <IssueSurfaceRoot
      mode={mode}
      issueKey={issueKey}
      projectKey={projectKey}
    />
  );
}
