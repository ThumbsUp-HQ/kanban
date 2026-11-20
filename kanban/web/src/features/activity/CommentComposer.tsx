/**
 * Comment Composer with formatting toolbar, @mention autocomplete, and 409 safe-mention warning (KB-P3-44, S7.1, S7.2 8k).
 */

import React, {
  useState,
  useRef,
  useEffect,
  type JSX,
  type KeyboardEvent,
  type ChangeEvent,
  type DragEvent,
  type ClipboardEvent,
} from 'react';
import {
  createComment,
  patchComment,
  fetchAssigneeSuggestions,
  type CommentResponse,
  type AssigneeSuggestion,
  type MentionAccessWarning,
} from './activityApi';
import { ApiProblem } from '../../api/problem';
import {
  defaultUploadAttachment,
  MAX_ATTACHMENT_BYTES,
  ALLOWED_IMAGE_MIME_TYPES,
  convertHtmlToMarkdown,
} from '../../editor/clipboard/autoConvertPaste';
import { pruneHiddenDom } from '../../editor/clipboard/hiddenDomPruner';
import { SanitizedPastePill } from '../../editor/clipboard/SanitizedPastePill';
import { SafeMarkdownPreview } from './SafeMarkdownPreview';

export const MAX_COMMENT_BYTES = 262144;

export interface CommentComposerProps {
  readonly issueKey: string;
  readonly projectKey: string;
  readonly parentCommentId?: string | null | undefined;
  readonly initialValue?: string | undefined;
  readonly commentId?: string | undefined;
  readonly etag?: string | undefined;
  readonly isEditing?: boolean | undefined;
  readonly onSuccess?: ((comment: CommentResponse) => void) | undefined;
  readonly onCancel?: (() => void) | undefined;
  readonly placeholder?: string | undefined;
}

export function getUtf8ByteLength(str: string): number {
  return new TextEncoder().encode(str).length;
}

export function isCursorInsideCode(text: string, cursorPos: number): boolean {
  const before = text.slice(0, cursorPos);
  // Check fenced code block: odd number of ``` before cursor means inside block
  const backtickTriples = (before.match(/```/g) ?? []).length;
  if (backtickTriples % 2 === 1) {
    return true;
  }
  // Check inline code: odd number of ` on the current line before cursor
  const currentLine = before.split('\n').pop() ?? '';
  const inlineTicks = (currentLine.match(/`/g) ?? []).length;
  return inlineTicks % 2 === 1;
}

export function extractMentionPrefix(text: string, cursorPos: number): string | null {
  if (isCursorInsideCode(text, cursorPos)) {
    return null;
  }
  const before = text.slice(0, cursorPos);
  const match = /(?:^|\s)@([a-zA-Z0-9_-]*)$/.exec(before);
  if (!match) {
    return null;
  }
  return match[1] ?? '';
}

export function formatMentionWarning(unauthorized: readonly { readonly handle: string }[]): string {
  const handles = unauthorized.map((m) => `@${m.handle.replace(/^@/, '')}`);
  if (handles.length === 1) {
    const handle = handles[0] ?? '';
    return `${handle} cannot view this issue. Posting will NOT grant access or send a notification to ${handle}.`;
  }
  return `${handles.join(', ')} cannot view this issue. Posting will NOT grant access or send notifications to them.`;
}

export function CommentComposer({
  issueKey,
  projectKey,
  parentCommentId = null,
  initialValue = '',
  commentId,
  etag,
  isEditing = false,
  onSuccess,
  onCancel,
  placeholder = 'Write a comment... (Markdown, HTML, Mermaid, SVG auto-clean)',
}: CommentComposerProps): JSX.Element {
  const [draft, setDraft] = useState(initialValue);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 409 safe-mention warning state
  const [mentionWarning, setMentionWarning] = useState<MentionAccessWarning | null>(null);
  // 412 conflict error
  const [conflictError, setConflictError] = useState(false);

  // @mention autocomplete state
  const [suggestions, setSuggestions] = useState<readonly AssigneeSuggestion[]>([]);
  const [suggestionPrefix, setSuggestionPrefix] = useState<string | null>(null);
  const [, setCursorPosition] = useState<number>(0);
  const [selectedSuggestionIdx, setSelectedSuggestionIdx] = useState(0);
  const [sanitizedPill, setSanitizedPill] = useState<{ prunedHiddenNodes: number } | null>(null);
  const [isPreview, setIsPreview] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const alertRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const undoDraftRef = useRef<string | null>(null);

  useEffect(() => {
    if (mentionWarning && alertRef.current) {
      alertRef.current.focus();
    }
  }, [mentionWarning]);

  const insertTextAtCursor = (beforeInsert: string, afterInsert = '', placeholderText = ''): void => {
    const textarea = textareaRef.current;
    /* v8 ignore next */
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const current = textarea.value;
    const hasSelection = start !== end;
    const selected = hasSelection ? current.slice(start, end) : placeholderText;

    let effBefore = beforeInsert;
    let effAfter = afterInsert;
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
    const nextDraft = current.slice(0, start) + replacement + current.slice(end);

    setDraft(nextDraft);
    setErrorText(null);

    const newCursor = isFence && !hasSelection
      ? start + replacement.length
      : start + effBefore.length + selected.length;

    // Set selection immediately on the DOM element if available
    try {
      textarea.setSelectionRange(newCursor, newCursor);
    } catch {
      // ignore
    }

    // Restore focus and selection
    setTimeout(() => {
      textarea.focus();
      try {
        textarea.setSelectionRange(newCursor, newCursor);
      } catch {
        // ignore
      }
    }, 0);
  };

  const handleTextChange = async (e: ChangeEvent<HTMLTextAreaElement>): Promise<void> => {
    const val = e.target.value;
    setDraft(val);
    setErrorText(null);
    setConflictError(false);

    // Check for @mention trigger
    const cursorPos = e.target.selectionStart;
    setCursorPosition(cursorPos);
    const prefix = extractMentionPrefix(val, cursorPos);
    setSuggestionPrefix(prefix);

    if (prefix !== null) {
      try {
        const resp = await fetchAssigneeSuggestions(projectKey, prefix);
        setSuggestions(resp.items);
        setSelectedSuggestionIdx(0);
      } catch {
        setSuggestions([]);
      }
    } else {
      setSuggestions([]);
    }
  };

  const applyMention = (handle: string): void => {
    const textarea = textareaRef.current;
    /* v8 ignore next */
    if (!textarea || suggestionPrefix === null) return;

    const cursorPos = textarea.selectionStart;
    const before = draft.slice(0, cursorPos);
    const after = draft.slice(cursorPos);

    // Replace @prefix with @handle + space
    const atIndex = before.lastIndexOf('@');
    /* v8 ignore next */
    if (atIndex !== -1) {
      const cleanHandle = handle.replace(/^@/, '');
      const newBefore = `${before.slice(0, atIndex)}@${cleanHandle} `;
      const next = newBefore + after;
      setDraft(next);
      setSuggestions([]);
      setSuggestionPrefix(null);

      setTimeout(() => {
        textarea.focus();
        textarea.setSelectionRange(newBefore.length, newBefore.length);
      }, 0);
    }
  };

  const handleSubmit = async (acknowledgedPrincipals?: readonly string[]): Promise<void> => {
    const trimmed = draft.trim();
    if (!trimmed) {
      setErrorText('Comment cannot be empty.');
      return;
    }

    const byteLen = getUtf8ByteLength(trimmed);
    if (byteLen > MAX_COMMENT_BYTES) {
      setErrorText('Comment exceeds maximum size of 262,144 bytes.');
      return;
    }

    setIsSubmitting(true);
    setErrorText(null);

    try {
      let result: CommentResponse;
      if (isEditing && commentId) {
        result = await patchComment(
          commentId,
          {
            body_markdown: trimmed,
            acknowledge_mentions: acknowledgedPrincipals,
          },
          etag,
        );
      } else {
        result = await createComment(issueKey, {
          body_markdown: trimmed,
          parent_comment_id: parentCommentId,
          acknowledge_mentions: acknowledgedPrincipals,
        });
      }

      setDraft('');
      setMentionWarning(null);
      setConflictError(false);
      onSuccess?.(result);
    } catch (err: unknown) {
      if (err instanceof ApiProblem) {
        const problemData = err.data as Record<string, unknown> | undefined;
        if (err.status === 409 && problemData?.code === 'MENTION_ACCESS_WARNING') {
          setMentionWarning(problemData as unknown as MentionAccessWarning);
        } else if (err.status === 412) {
          setConflictError(true);
        } else {
          setErrorText(err.message !== '' ? err.message : 'Failed to submit comment.');
        }
      } else {
        const errorObj = err as Error;
        setErrorText(errorObj.message !== '' ? errorObj.message : 'Failed to submit comment.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFileSelected = async (e: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_ATTACHMENT_BYTES) {
      setErrorText('Attachment exceeds 25 MB limit');
      return;
    }
    try {
      const result = await defaultUploadAttachment(file, projectKey);
      const targetUri = result.markdownUri !== '' ? result.markdownUri : `attachment://${result.id}`;
      insertTextAtCursor(`![${file.name}](${targetUri})`, '', '');
    } catch {
      setErrorText('Attachment upload failed');
    } finally {
      e.target.value = '';
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    if (files.length === 0) return;
    const file = files.find(
      (f) => ALLOWED_IMAGE_MIME_TYPES.has(f.type) || f.name.toLowerCase().endsWith('.svg'),
    );
    if (!file) return;
    if (file.size > MAX_ATTACHMENT_BYTES) {
      setErrorText('Attachment exceeds 25 MB limit');
      return;
    }
    void defaultUploadAttachment(file, projectKey)
      .then((result) => {
        const targetUri = result.markdownUri !== '' ? result.markdownUri : `attachment://${result.id}`;
        insertTextAtCursor(`![${file.name}](${targetUri})`, '', '');
      })
      .catch(() => {
        setErrorText('Attachment upload failed');
      });
  };

  const handlePaste = (e: ClipboardEvent<HTMLTextAreaElement>): void => {
    const clipboardData = e.clipboardData;

    // 1. Binary file paste
    const files = Array.from(clipboardData.files);
    if (files.length > 0) {
      const file = files.find(
        (f) => ALLOWED_IMAGE_MIME_TYPES.has(f.type) || f.name.toLowerCase().endsWith('.svg'),
      );
      if (file) {
        e.preventDefault();
        if (file.size > MAX_ATTACHMENT_BYTES) {
          setErrorText('Attachment exceeds 25 MB limit');
          return;
        }
        void defaultUploadAttachment(file, projectKey)
          .then((result) => {
            const targetUri = result.markdownUri !== '' ? result.markdownUri : `attachment://${result.id}`;
            insertTextAtCursor(`![${file.name}](${targetUri})`, '', '');
          })
          .catch(() => {
            setErrorText('Attachment upload failed');
          });
        return;
      }
    }

    // 2. Rich HTML paste
    const html = clipboardData.getData('text/html');
    if (html && html.trim() !== '') {
      e.preventDefault();
      /* v8 ignore next */
      undoDraftRef.current = textareaRef.current?.value ?? '';
      const { prunedHtml, prunedHiddenNodes } = pruneHiddenDom(html);
      const converted = convertHtmlToMarkdown(prunedHtml);
      insertTextAtCursor(converted, '', '');
      setSanitizedPill({ prunedHiddenNodes });
    }
  };

  const handleRevertPaste = (): void => {
    /* v8 ignore next */
    if (undoDraftRef.current !== null) {
      setDraft(undoDraftRef.current);
      undoDraftRef.current = null;
    }
    setSanitizedPill(null);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>): void => {
    const isMod = e.metaKey || e.ctrlKey;
    if (isMod && e.shiftKey && e.key.toLowerCase() === 'm') {
      e.preventDefault();
      setIsPreview((prev) => !prev);
      return;
    }
    // Autocomplete navigation
    if (suggestions.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedSuggestionIdx((prev) => (prev + 1) % suggestions.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedSuggestionIdx((prev) => (prev - 1 + suggestions.length) % suggestions.length);
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        const chosen = suggestions[selectedSuggestionIdx];
        /* v8 ignore next */
        if (chosen) {
          applyMention(chosen.handle);
        }
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setSuggestions([]);
        return;
      }
    }

    // Submit with Cmd+Enter or Ctrl+Enter
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  return (
    <div className={`comment-composer${isEditing ? ' comment-composer--editing' : ''}`}>
      {/* Toolbar */}
      <div className="comment-composer__toolbar" role="toolbar" aria-label="Comment formatting">
        <button
          type="button"
          className="composer-tool-btn"
          aria-label="Bold text"
          onClick={() => { insertTextAtCursor('**', '**', 'bold text'); }}
        >
          <strong>B</strong>
        </button>
        <button
          type="button"
          className="composer-tool-btn"
          aria-label="Italic text"
          onClick={() => { insertTextAtCursor('*', '*', 'italic text'); }}
        >
          <em>I</em>
        </button>
        <button
          type="button"
          className="composer-tool-btn"
          aria-label="Insert code"
          onClick={() => { insertTextAtCursor('```\n', '\n```', 'code'); }}
        >
          <code>&lt;/&gt;</code>
        </button>
        <button
          type="button"
          className="composer-tool-btn"
          aria-label="Insert link"
          onClick={() => { insertTextAtCursor('[', '](https://example.com)', 'link text'); }}
        >
          🔗
        </button>
        <button
          type="button"
          className="composer-tool-btn"
          aria-label="Insert tasklist"
          onClick={() => { insertTextAtCursor('- [ ] ', '', 'task item\n'); }}
        >
          ☑
        </button>
        <button
          type="button"
          className="composer-tool-btn"
          aria-label="Attach media or SVG"
          onClick={() => {
            insertTextAtCursor('![', '](https://example.com/media.png)', 'alt text');
            fileInputRef.current?.click();
          }}
        >
          📎
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,.svg"
          tabIndex={-1}
          aria-hidden="true"
          className="comment-composer__file-input"
          onChange={(e) => { void handleFileSelected(e); }}
          data-testid="comment-file-input"
        />
        <button
          type="button"
          className="composer-tool-btn"
          aria-label="Insert Mermaid diagram"
          onClick={() => { insertTextAtCursor('```mermaid\ngraph TD\n  ', '\n```', 'A[Start] --> B[End]'); }}
        >
          📊
        </button>
        <button
          type="button"
          className={`composer-tool-btn${isPreview ? ' is-active' : ''}`}
          aria-label="Raw markdown source view"
          title="Raw markdown source view (Cmd/Ctrl+Shift+M)"
          onClick={() => { setIsPreview((prev) => !prev); }}
          data-testid="comment-tool-raw"
        >
          📝
        </button>
      </div>

      {/* Editor Box */}
      <div
        className="comment-composer__input-wrapper"
        onDragOver={(e) => { e.preventDefault(); }}
        onDrop={handleDrop}
      >
        {isPreview ? (
          <div className="comment-composer__preview" data-testid="comment-preview">
            <SafeMarkdownPreview markdown={draft || '*No comment content*'} />
          </div>
        ) : (
          <textarea
            ref={textareaRef}
            className="comment-composer__textarea"
            aria-label="Write a comment"
            placeholder={placeholder}
            value={draft}
            onChange={(e) => { void handleTextChange(e); }}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            rows={3}
          />
        )}

        {/* @mention autocomplete listbox */}
        {suggestions.length > 0 && (
          <ul
            className="comment-composer__suggestions"
            role="listbox"
            aria-label="Mention suggestions"
          >
            {suggestions.map((item, idx) => (
              <li
                key={item.id}
                role="option"
                aria-selected={idx === selectedSuggestionIdx}
                className={`composer-suggestion${idx === selectedSuggestionIdx ? ' composer-suggestion--active' : ''}`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  applyMention(item.handle);
                }}
                onClick={() => {
                  applyMention(item.handle);
                }}
              >
                <span className="composer-suggestion__handle">
                  {item.is_agent ? '🤖 Agent ' : '👤 Member '}
                  @{item.handle.replace(/^@/, '')}
                </span>
                <span className="composer-suggestion__name">{item.display_name}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Floating Sanitized Paste Status Pill (🧼) */}
      {sanitizedPill && (
        <SanitizedPastePill
          prunedHiddenNodes={sanitizedPill.prunedHiddenNodes}
          onDismiss={() => {
            setSanitizedPill(null);
          }}
          onRevert={handleRevertPaste}
          testId="comment-sanitized-pill"
        />
      )}

      {/* 409 MENTION_ACCESS_WARNING Banner */}
      {mentionWarning && (
        <div
          ref={alertRef}
          tabIndex={-1}
          role="alert"
          className="comment-composer__warning-banner"
          aria-live="assertive"
        >
          <div className="warning-banner__text">
            {formatMentionWarning(mentionWarning.unauthorized_mentions)}
          </div>
          <div className="warning-banner__actions">
            <button
              type="button"
              className="warning-btn warning-btn--secondary"
              onClick={() => {
                setMentionWarning(null);
                textareaRef.current?.focus();
              }}
            >
              Edit comment
            </button>
            <button
              type="button"
              className="warning-btn warning-btn--primary"
              onClick={() => {
                const ids = mentionWarning.unauthorized_mentions.map((m) => m.principal_id);
                void handleSubmit(ids);
              }}
            >
              Post without granting access
            </button>
          </div>
        </div>
      )}

      {/* 412 Precondition Failed Conflict Alert */}
      {conflictError && (
        <div role="alert" className="comment-composer__conflict-banner">
          <span>This comment was edited elsewhere. Copy your changes and reload.</span>
        </div>
      )}

      {/* Standard Error Alert */}
      {errorText && (
        <div role="alert" className="comment-composer__error-alert">
          {errorText}
        </div>
      )}

      {/* Action Footer */}
      <div className="comment-composer__footer">
        {onCancel && (
          <button
            type="button"
            className="composer-cancel-btn"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            Cancel
          </button>
        )}
        <button
          type="button"
          className="composer-submit-btn"
          onClick={() => { void handleSubmit(); }}
          disabled={isSubmitting}
        >
          {isSubmitting ? 'Saving...' : isEditing ? 'Save Changes' : parentCommentId ? 'Reply' : 'Comment'}
        </button>
      </div>
    </div>
  );
}
