/**
 * Spacious Editorial Page Pane (KB-P3-50, S6.1, S8.1).
 * Features breadcrumbs, version pill, access hint, inline 1..500 char title,
 * MarkdownEditor surface="doc", 800ms debounced autosave with ETag, and 412 conflict guard.
 */

import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  type JSX,
} from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { fetchPage, updatePage, type PageResponse } from './docsApi';
import { ApiProblem } from '../../api/problem';
import { MarkdownEditor } from '../../editor/MarkdownEditor';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import './DocsWorkspaceView.css';

export interface PageEditorPaneProps {
  pageId: string;
  projectKey: string;
  readOnly?: boolean | undefined;
  onToggleRail?: (() => void) | undefined;
  onOpenHistory?: (() => void) | undefined;
  isRailOpen?: boolean | undefined;
  onAnnounce?: ((message: string) => void) | undefined;
  onMarkdownChange?: ((markdown: string) => void) | undefined;
}

interface InnerEditorFormProps {
  page: PageResponse;
  pageId: string;
  projectKey: string;
  readOnly?: boolean | undefined;
  onToggleRail?: (() => void) | undefined;
  onOpenHistory?: (() => void) | undefined;
  isRailOpen?: boolean | undefined;
  onAnnounce?: ((message: string) => void) | undefined;
  onMarkdownChange?: ((markdown: string) => void) | undefined;
  refetch: () => Promise<unknown>;
}

function InnerEditorForm({
  page,
  pageId,
  projectKey,
  readOnly = false,
  onToggleRail,
  onOpenHistory,
  isRailOpen = true,
  onAnnounce,
  onMarkdownChange,
  refetch,
}: InnerEditorFormProps): JSX.Element {
  const queryClient = useQueryClient();

  const [title, setTitle] = useState(page.title);
  const [markdown, setMarkdown] = useState(page.body_markdown);
  const [dirty, setDirty] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [conflictRemoteVersion, setConflictRemoteVersion] = useState<number | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [copyFeedback, setCopyFeedback] = useState(false);
  const [copiedMarkdown, setCopiedMarkdown] = useState(false);

  const titleInputRef = useRef<HTMLTextAreaElement | null>(null);
  const editorContainerRef = useRef<HTMLDivElement | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: async ({
      nextTitle,
      nextMarkdown,
      etag,
    }: {
      nextTitle: string;
      nextMarkdown: string;
      etag: string;
    }) => {
      return updatePage(
        pageId,
        {
          title: nextTitle,
          body_markdown: nextMarkdown,
        },
        etag,
      );
    },
    onSuccess: (updatedPage) => {
      setSaveStatus('saved');
      setDirty(false);
      setConflictRemoteVersion(null);
      setValidationError(null);
      void queryClient.setQueryData(qk.page(pageId), updatedPage);
      void queryClient.invalidateQueries({ queryKey: qk.docsTree(projectKey) });
      onAnnounce?.(`Saved v${String(updatedPage.version_seq)}`);
    },
    onError: (err: unknown) => {
      setSaveStatus('error');
      if (err instanceof ApiProblem && err.status === 412) {
        const remoteSeq = (err.data.current_version_seq as number | undefined) ?? page.version_seq + 1;
        setConflictRemoteVersion(remoteSeq);
        onAnnounce?.('Conflict: Page was updated elsewhere');
      } else {
        const msg = err instanceof Error ? err.message : 'Save failed';
        setValidationError(msg);
      }
    },
  });

  const performSave = useCallback(
    (newTitle?: string, newMarkdown?: string) => {
      const activeTitle = (newTitle ?? title).trim();
      const activeMarkdown = newMarkdown ?? markdown;

      if (!activeTitle) {
        setValidationError('Title cannot be empty');
        return;
      }
      if (Array.from(activeTitle).length > 500) {
        setValidationError('Title cannot exceed 500 characters');
        return;
      }

      setValidationError(null);
      setSaveStatus('saving');

      // Use body_sha256 hex as ETag
      const currentEtag = page.body_sha256 ? `"${page.body_sha256}"` : '*';
      saveMutation.mutate({
        nextTitle: activeTitle,
        nextMarkdown: activeMarkdown,
        etag: currentEtag,
      });
    },
    [title, markdown, page, saveMutation],
  );

  // Debounce autosave
  const triggerDebouncedSave = useCallback(
    (newTitle?: string, newMarkdown?: string) => {
      setDirty(true);
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = setTimeout(() => {
        performSave(newTitle, newMarkdown);
      }, 800);
    },
    [performSave],
  );

  const handleTitleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    // Strip control characters (except newline)
    const cleaned = e.target.value.replace(/[\x00-\x09\x0B-\x1F\x7F]/g, '');
    setTitle(cleaned);
    const codePointCount = Array.from(cleaned.trim()).length;
    if (codePointCount > 500) {
      setValidationError('Title cannot exceed 500 characters');
    } else if (codePointCount === 0) {
      setValidationError('Title cannot be empty');
    } else {
      setValidationError(null);
    }
    triggerDebouncedSave(cleaned, undefined);
  };

  const handleTitleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      // Focus MarkdownEditor
      const editorProseMirror = editorContainerRef.current?.querySelector('.ProseMirror') as HTMLElement | null;
      editorProseMirror?.focus();
    }
  };

  const handleMarkdownChange = (nextMarkdown: string) => {
    setMarkdown(nextMarkdown);
    onMarkdownChange?.(nextMarkdown);
    triggerDebouncedSave(undefined, nextMarkdown);
  };

  const handleBlur = () => {
    if (dirty && !conflictRemoteVersion) {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      performSave();
    }
  };

  // Keyboard shortcut Cmd+S / Ctrl+S
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        if (debounceTimerRef.current) {
          clearTimeout(debounceTimerRef.current);
        }
        performSave();
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => {
      window.removeEventListener('keydown', handleGlobalKeyDown);
    };
  }, [performSave]);

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  const handleCopyDraft = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopyFeedback(true);
      setTimeout(() => {
        setCopyFeedback(false);
      }, 2000);
    } catch {
      // Fallback
    }
  };

  const handleReloadLatest = async () => {
    setConflictRemoteVersion(null);
    setValidationError(null);
    await refetch();
  };

  const handleCopyMarkdown = () => {
    try {
      void navigator.clipboard.writeText(markdown);
      setCopiedMarkdown(true);
      setTimeout(() => {
        setCopiedMarkdown(false);
      }, 2000);
      onAnnounce?.('Markdown copied to clipboard');
    } catch {
      // Fallback
    }
  };

  const handleAccessPillClick = () => {
    window.dispatchEvent(
      new CustomEvent('kb:open-access-inspector', {
        detail: { objectId: page.id, object_id: page.id },
      }),
    );
  };

  const breadcrumbs = page.breadcrumbs;

  return (
    <main className="docs-center-pane" aria-label="Page Editor" onBlur={handleBlur}>
      {/* Top Metadata Bar */}
      <header className="docs-metadata-bar">
        <nav aria-label="Breadcrumb" className="docs-breadcrumbs">
          <ol className="docs-breadcrumbs__list">
            {breadcrumbs.map((crumb, idx) => (
              <li key={crumb.id ?? String(idx)} className="docs-breadcrumbs__item">
                {idx > 0 && <span className="docs-breadcrumbs__separator">/</span>}
                <span className="docs-breadcrumbs__label" title={crumb.title ?? (crumb.slug ?? '')}>
                  {crumb.restricted ? '🔒 Restricted Page' : (crumb.title ?? (crumb.slug ?? 'Doc'))}
                </span>
              </li>
            ))}
          </ol>
        </nav>

        <div className="docs-metadata-bar__actions">
          <button
            type="button"
            className="docs-copy-markdown-btn"
            data-testid="copy-doc-markdown-btn"
            onClick={handleCopyMarkdown}
            title="Copy Markdown content to clipboard"
          >
            📋 {copiedMarkdown ? 'Copied!' : 'Copy Markdown'}
          </button>

          <button
            type="button"
            className="docs-version-pill mono docs-version-pill-btn"
            data-testid="page-version-pill"
            onClick={onOpenHistory}
            title="View version history"
            aria-label={`Version ${String(page.version_seq)} - view history`}
          >
            v{page.version_seq}
          </button>

          <span
            className="docs-access-pill-wrapper"
            data-testid="page-access-pill"
            onClick={handleAccessPillClick}
          >
            <EmojiHint
              kind="access"
              variant="interactive"
              label="Access visibility"
              onActivate={handleAccessPillClick}
            />
          </span>

          {onToggleRail && (
            <button
              type="button"
              className={`docs-rail-toggle-btn ${isRailOpen ? 'docs-rail-toggle-btn--active' : ''}`}
              onClick={onToggleRail}
              aria-label={isRailOpen ? 'Hide outline & history' : 'Show outline & history'}
              data-testid="rail-toggle-btn"
            >
              📑
            </button>
          )}
        </div>
      </header>

      {/* 412 Conflict Alert Banner */}
      {conflictRemoteVersion !== null && (
        <div
          className="docs-conflict-banner"
          role="alert"
          aria-live="assertive"
          data-testid="docs-conflict-alert"
        >
          <div className="docs-conflict-banner__message">
            Page was updated elsewhere (v{conflictRemoteVersion}). Copy your draft or reload latest.
          </div>
          <div className="docs-conflict-banner__actions">
            <button
              type="button"
              className="docs-conflict-btn"
              onClick={() => {
                void handleCopyDraft();
              }}
              data-testid="copy-my-draft-btn"
            >
              {copyFeedback ? 'Copied!' : 'Copy My Draft'}
            </button>
            <button
              type="button"
              className="docs-conflict-btn docs-conflict-btn--primary"
              onClick={() => {
                void handleReloadLatest();
              }}
              data-testid="reload-latest-btn"
            >
              Reload Latest
            </button>
          </div>
        </div>
      )}

      {/* Validation Error Banner */}
      {validationError && (
        <div className="docs-validation-alert" role="alert" data-testid="page-validation-alert">
          {validationError}
        </div>
      )}

      {/* Spacious Editorial Area (.docs-prose) */}
      <div className="docs-prose" data-testid="docs-prose">
        {/* Inline Title */}
        {readOnly ? (
          <h1 className="docs-title-static" data-testid="page-title-static">
            {title}
          </h1>
        ) : (
          <textarea
            ref={titleInputRef}
            className="docs-title-input"
            value={title}
            onChange={handleTitleChange}
            onKeyDown={handleTitleKeyDown}
            placeholder="Untitled page"
            rows={1}
            maxLength={501}
            aria-label="Document Title"
            data-testid="page-title-input"
          />
        )}

        {/* ProseMirror Markdown Editor */}
        <div ref={editorContainerRef} className="docs-editor-container">
          <MarkdownEditor
            surface="doc"
            value={markdown}
            onChange={handleMarkdownChange}
            onBlur={handleBlur}
            readOnly={readOnly}
            maxBytes={1048576}
            ariaLabel={`Content for ${title}`}
            testId="page-markdown-editor"
            projectId={projectKey}
            objectId={page.id}
          />
        </div>

        {saveStatus === 'saving' && (
          <div className="docs-autosave-status mono" aria-live="polite">
            Saving...
          </div>
        )}
      </div>
    </main>
  );
}

export function PageEditorPane({
  pageId,
  projectKey,
  readOnly = false,
  onToggleRail,
  onOpenHistory,
  isRailOpen = true,
  onAnnounce,
  onMarkdownChange,
}: PageEditorPaneProps): JSX.Element {
  const {
    data: page,
    isLoading,
    error,
    refetch,
  } = useQuery<PageResponse, ApiProblem | Error>({
    queryKey: qk.page(pageId),
    queryFn: () => fetchPage(pageId),
  });

  // 403 & 404 security handling
  if (error) {
    return (
      <main className="docs-center-pane" aria-label="Page Editor">
        <div className="docs-center-pane__not-found" role="alert" data-testid="page-not-found">
          Page was not found or you do not have access.
        </div>
      </main>
    );
  }

  if (isLoading || !page) {
    return (
      <main className="docs-center-pane" aria-label="Page Editor">
        <div className="docs-center-pane__loading" data-testid="page-loading">
          Loading page...
        </div>
      </main>
    );
  }

  return (
    <InnerEditorForm
      key={page.id}
      page={page}
      pageId={pageId}
      projectKey={projectKey}
      readOnly={readOnly}
      onToggleRail={onToggleRail}
      onOpenHistory={onOpenHistory}
      isRailOpen={isRailOpen}
      onAnnounce={onAnnounce}
      onMarkdownChange={onMarkdownChange}
      refetch={refetch}
    />
  );
}
