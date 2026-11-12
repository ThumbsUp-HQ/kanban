import React, {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FocusEvent,
  type JSX,
  type KeyboardEvent,
  type RefObject,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { ApiProblem } from '../../api/problem';
import { qk } from '../../api/queryKeys';
import { useOptimisticMutation } from '../../api/optimistic';
import type { IssueDetail } from './slots';
import './SummaryField.css';

export interface SummaryFieldProps {
  issue: IssueDetail;
  descriptionFocusRef?: RefObject<HTMLElement | null>;
}

export function sanitizeSummary(val: string): string {
  // Replace newlines and C0/C1 control characters with a single space
  return val.replace(/[\r\n\u0000-\u001F\u007F-\u009F]+/g, ' ');
}

export function getCodePointLength(val: string): number {
  return Array.from(val.trim()).length;
}

export function SummaryField({ issue, descriptionFocusRef }: SummaryFieldProps): JSX.Element {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [draftText, setDraftText] = useState(issue.summary);
  const [prevSummary, setPrevSummary] = useState(issue.summary);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [conflictError, setConflictError] = useState(false);

  const editButtonRef = useRef<HTMLButtonElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Sync draftText when issue prop changes externally, unless currently editing
  if (!isEditing && issue.summary !== prevSummary) {
    setPrevSummary(issue.summary);
    setDraftText(issue.summary);
  }

  // Auto-focus and adjust height when entering edit mode
  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.setSelectionRange(
        textareaRef.current.value.length,
        textareaRef.current.value.length,
      );
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${String(textareaRef.current.scrollHeight)}px`;
    }
  }, [isEditing]);

  const mutation = useOptimisticMutation<{ summary: string }, IssueDetail, IssueDetail>({
    queryKey: qk.issue(issue.key),
    mutationFn: async ({ summary }) => {
      return (await apiClient.patch(
        '/api/v1/issues/{issue_key}',
        {
          ifMatch: issue.etag,
          params: { issue_key: issue.key },
          body: { summary },
        },
      )) as unknown as IssueDetail;
    },
    apply: (cache, { summary }) => {
      if (!cache) {
        return { ...issue, summary };
      }
      return { ...cache, summary };
    },
    onRollbackMessage: (err) => {
      if (err instanceof ApiProblem && err.status === 412) {
        return 'Summary update conflicted. Reloading latest version.';
      }
      return 'Failed to update summary.';
    },
  });

  const validate = (val: string): boolean => {
    const len = getCodePointLength(val);
    if (len === 0) {
      setErrorText('Summary cannot be empty.');
      return false;
    }
    if (len > 500) {
      setErrorText(`Summary must be 500 characters or fewer (currently ${String(len)}).`);
      return false;
    }
    setErrorText(null);
    return true;
  };

  const commitSummary = async (newVal: string): Promise<void> => {
    const trimmed = newVal.trim();
    if (trimmed === issue.summary) {
      setIsEditing(false);
      setErrorText(null);
      return;
    }

    try {
      await mutation.mutateAsync({ summary: trimmed });
      setIsEditing(false);
      setErrorText(null);
      setConflictError(false);
    } catch (err: unknown) {
      if (err instanceof ApiProblem && err.status === 412) {
        setConflictError(true);
        setDraftText(issue.summary);
        setIsEditing(false);
        setErrorText(null);
      }
    }
  };

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>): void => {
    const sanitized = sanitizeSummary(e.target.value);
    setDraftText(sanitized);
    validate(sanitized);

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${String(textareaRef.current.scrollHeight)}px`;
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (!validate(draftText)) {
        return;
      }
      void commitSummary(draftText);
      if (descriptionFocusRef?.current) {
        descriptionFocusRef.current.focus();
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setDraftText(issue.summary);
      setErrorText(null);
      setIsEditing(false);
      setTimeout(() => {
        editButtonRef.current?.focus();
      }, 0);
    }
  };

  const handleBlur = (e: FocusEvent<HTMLTextAreaElement>): void => {
    const related = e.relatedTarget as HTMLElement | null;
    if (related && (related.closest('.surface__header') || related.closest('.issue-header__btn'))) {
      return;
    }

    const len = getCodePointLength(draftText);
    if (len === 0 || len > 500) {
      return;
    }
    void commitSummary(draftText);
  };

  const handleReload = (): void => {
    void queryClient.invalidateQueries({ queryKey: qk.issue(issue.key) });
    setConflictError(false);
  };

  return (
    <div className={`summary-field${isEditing ? ' summary-field--editing' : ''}`}>
      {isEditing ? (
        <div className="summary-field__editor-container">
          <textarea
            ref={textareaRef}
            className="summary-field__textarea"
            aria-label="Summary"
            aria-describedby={errorText ? `summary-error-${issue.key}` : undefined}
            value={draftText}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            onBlur={handleBlur}
            rows={1}
          />
          {errorText && (
            <div
              id={`summary-error-${issue.key}`}
              role="alert"
              className="summary-field__error"
            >
              {errorText}
            </div>
          )}
        </div>
      ) : (
        <h1 id={`issue-summary-${issue.key}`} className="summary-field__heading">
          <span className="summary-field__display-text">{issue.summary}</span>
          <button
            ref={editButtonRef}
            type="button"
            className="summary__edit"
            aria-label="Edit summary"
            onClick={() => {
              setDraftText(issue.summary);
              setErrorText(null);
              setIsEditing(true);
            }}
          >
            <span aria-hidden="true" className="summary__edit-glyph">✎</span>
          </button>
        </h1>
      )}

      {conflictError && (
        <div role="alert" className="summary-field__conflict">
          <span className="summary-field__conflict-msg">
            This issue changed since you opened it. Reload to see the latest version.
          </span>
          <button
            type="button"
            className="summary-field__conflict-reload-btn"
            onClick={handleReload}
          >
            Reload
          </button>
        </div>
      )}
    </div>
  );
}
