/**
 * Create Project Modal (KANBA-166 / KB-QA-05).
 *
 * Accessible modal dialog for creating a new Project via `POST /api/v1/projects`,
 * bootstrapping `X-CSRF-Token` from `/api/v1/auth/session` when needed and
 * navigating to `/projects/:identifier/issues`.
 */

import React, { useEffect, useRef, useState, type JSX, type SyntheticEvent } from 'react';
import { useNavigate } from 'react-router';
import { ensureSessionCsrfToken } from '../auth/useSessionGuard';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import './CreateProjectModal.css';

export interface CreatedProject {
  readonly id: string;
  readonly identifier: string;
  readonly name: string;
  readonly description_markdown?: string;
  readonly modules_enabled?: boolean;
  readonly skip_loaded_sequence_numbers?: boolean;
  readonly is_project_admin?: boolean;
  readonly capabilities?: readonly string[];
}

export interface CreateProjectModalProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onCreated?: (project: CreatedProject) => void;
}

export const PROJECT_IDENTIFIER_PATTERN = /^[A-Z][A-Z0-9]{1,9}$/;

/**
 * Derives a valid uppercase 2..10 char project identifier from a display name.
 */
export function suggestProjectIdentifier(name: string): string {
  const cleaned = name
    .toUpperCase()
    .replace(/[^A-Z0-9\s]+/g, ' ')
    .trim();
  if (!cleaned) {
    return '';
  }

  const words = cleaned.split(/\s+/).filter(Boolean);
  let candidate = '';
  if (words.length >= 2) {
    candidate = words
      .map((w) => w.slice(0, 2))
      .join('')
      .slice(0, 6);
  } else {
    /* v8 ignore next */
    candidate = (words[0] ?? '').slice(0, 5);
  }

  // Ensure leading character is A-Z
  candidate = candidate.replace(/^[^A-Z]+/, '');
  if (!candidate) {
    candidate = 'PRJ';
  }
  if (candidate.length < 2) {
    candidate = `${candidate}1`;
  }
  return candidate.slice(0, 10);
}

export function CreateProjectModal({
  isOpen,
  onClose,
  onCreated,
}: CreateProjectModalProps): JSX.Element | null {
  const [name, setName] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [identifierTouched, setIdentifierTouched] = useState(false);
  const [description, setDescription] = useState('');
  const [modulesEnabled, setModulesEnabled] = useState(true);
  const [skipLoadedSeq, setSkipLoadedSeq] = useState(false);
  const [skipLoadedSeqTouched, setSkipLoadedSeqTouched] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const nameInputRef = useRef<HTMLInputElement | null>(null);

  let navigateFn: ((to: string) => void) | null = null;
  try {
    const nav = useNavigate();
    navigateFn = (to: string) => {
      void nav(to);
    };
  } catch {
    // Rendered outside Router context
  }

  const resetForm = (): void => {
    setName('');
    setIdentifier('');
    setIdentifierTouched(false);
    setDescription('');
    setModulesEnabled(true);
    setSkipLoadedSeq(false);
    setSkipLoadedSeqTouched(false);
    setErrorMessage(null);
    setIsSubmitting(false);
  };

  const handleClose = (): void => {
    resetForm();
    onClose();
  };

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const isMounted = { current: true };
    void (async () => {
      try {
        const res = await fetch('/api/v1/admin/workspace-settings', {
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
        });
        if (res.ok && isMounted.current) {
          const data = (await res.json()) as { default_skip_loaded_sequence_numbers?: boolean };
          if (typeof data.default_skip_loaded_sequence_numbers === 'boolean') {
            setSkipLoadedSeq(data.default_skip_loaded_sequence_numbers);
          }
        }
      } catch {
        // Inherits default gracefully on submit
      }
    })();

    const timer = setTimeout(() => {
      nameInputRef.current?.focus();
    }, 0);

    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        resetForm();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      isMounted.current = false;
      clearTimeout(timer);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  const handleNameChange = (value: string): void => {
    setName(value);
    if (!identifierTouched) {
      setIdentifier(suggestProjectIdentifier(value));
    }
    if (errorMessage) {
      setErrorMessage(null);
    }
  };

  const handleIdentifierChange = (value: string): void => {
    setIdentifierTouched(true);
    setIdentifier(value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10));
    if (errorMessage) {
      setErrorMessage(null);
    }
  };

  const handleSubmit = async (e: SyntheticEvent): Promise<void> => {
    e.preventDefault();
    const trimmedName = name.trim();
    const cleanId = identifier.trim().toUpperCase();

    if (!trimmedName) {
      setErrorMessage('Project name is required.');
      return;
    }
    if (!PROJECT_IDENTIFIER_PATTERN.test(cleanId)) {
      setErrorMessage(
        'Identifier must be 2-10 uppercase characters starting with a letter (A-Z, 0-9).',
      );
      return;
    }

    setErrorMessage(null);
    setIsSubmitting(true);

    try {
      const csrfToken = await ensureSessionCsrfToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      };
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
      }

      const createPayload: Record<string, unknown> = {
        name: trimmedName,
        identifier: cleanId,
        description_markdown: description.trim(),
        modules_enabled: modulesEnabled,
      };
      if (skipLoadedSeqTouched) {
        createPayload.skip_loaded_sequence_numbers = skipLoadedSeq;
      }

      const res = await fetch('/api/v1/projects', {
        method: 'POST',
        headers,
        credentials: 'same-origin',
        body: JSON.stringify(createPayload),
      });

      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as {
          detail?: string | { detail?: string };
        };
        const detail = body.detail;
        const msg =
          typeof detail === 'string'
            ? detail
            : typeof detail === 'object' && 'detail' in detail && typeof detail.detail === 'string'
              ? detail.detail
              : `Failed to create project (HTTP ${String(res.status)})`;
        throw new Error(msg);
      }

      const created = (await res.json()) as CreatedProject;
      /* v8 ignore next 5 */
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('kb:project-created', { detail: created }),
        );
      }
      onCreated?.(created);
      resetForm();
      onClose();
      navigateFn?.(`/projects/${created.identifier}/issues`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not create project.';
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="kb-palette-scrim kb-create-project-scrim"
      data-testid="create-project-scrim"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          handleClose();
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Create project"
        data-testid="create-project-modal"
        className="kb-create-project-dialog"
      >
        <div className="kb-create-project-header">
          <h2 className="kb-create-project-title">Create Project</h2>
          <button
            type="button"
            aria-label="Close create project modal"
            className="kb-create-project-close"
            onClick={handleClose}
          >
            ✕
          </button>
        </div>

        <form
          onSubmit={(e) => {
            void handleSubmit(e);
          }}
          className="kb-create-project-form"
        >
          <div className="kb-create-project-field">
            <label
              htmlFor="create-project-name"
              className="kb-create-project-label"
            >
              Project Name
            </label>
            <input
              ref={nameInputRef}
              id="create-project-name"
              type="text"
              required
              maxLength={120}
              placeholder="e.g. Platform Security"
              value={name}
              onChange={(e) => {
                handleNameChange(e.target.value);
              }}
              className="kb-create-project-input"
            />
          </div>

          <div className="kb-create-project-field">
            <label
              htmlFor="create-project-identifier"
              className="kb-create-project-label"
            >
              Identifier (Key)
            </label>
            <input
              id="create-project-identifier"
              type="text"
              required
              maxLength={10}
              placeholder="e.g. SEC"
              value={identifier}
              onChange={(e) => {
                handleIdentifierChange(e.target.value);
              }}
              className="kb-create-project-input kb-create-project-input-mono"
            />
            <span className="kb-create-project-hint">
              2-10 uppercase characters starting with a letter (used for issue keys like {identifier || 'SEC'}-1).
            </span>
          </div>

          <div className="kb-create-project-field">
            <label
              htmlFor="create-project-description"
              className="kb-create-project-label"
            >
              Description (Markdown)
            </label>
            <textarea
              id="create-project-description"
              rows={3}
              placeholder="Project goals, scope, and notes..."
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
              }}
              className="kb-create-project-textarea"
            />
          </div>

          <label
            htmlFor="create-project-modules"
            className="kb-create-project-checkbox-row"
          >
            <input
              id="create-project-modules"
              type="checkbox"
              checked={modulesEnabled}
              onChange={(e) => {
                setModulesEnabled(e.target.checked);
              }}
            />
            <span>Enable project modules</span>
          </label>

          <div className="kb-create-project-checkbox-row-wrap">
            <label
              htmlFor="create-project-skip-loaded-seq"
              className="kb-create-project-checkbox-row"
            >
              <input
                id="create-project-skip-loaded-seq"
                data-testid="create-project-skip-loaded-seq"
                type="checkbox"
                checked={skipLoadedSeq}
                onChange={(e) => {
                  setSkipLoadedSeqTouched(true);
                  setSkipLoadedSeq(e.target.checked);
                }}
              />
              <span>Agent-Safe Sequence Numbering (skip 13, 69, 88, 404, 420, 666, 1337, 1488)</span>
            </label>
            <EmojiHint kind="agentSafeNumbering" />
          </div>

          {errorMessage && (
            <div
              role="alert"
              data-testid="create-project-error"
              className="kb-create-project-error"
            >
              {errorMessage}
            </div>
          )}

          <div className="kb-create-project-actions">
            <button
              type="button"
              className="kb-create-project-cancel-btn"
              onClick={handleClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              data-testid="create-project-submit"
              className="kb-create-project-submit-btn"
            >
              {isSubmitting ? 'Creating...' : 'Create Project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
