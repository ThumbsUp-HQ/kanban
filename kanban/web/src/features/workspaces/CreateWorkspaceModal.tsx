/**
 * Create Workspace Modal (KB-UX-05, S1.1, S3.3, KANBA-175).
 *
 * Accessible modal dialog for creating a new Workspace via `POST /api/v1/workspaces`,
 * with CSRF token protection and instant workspace switching/navigation.
 */

import React, { useEffect, useRef, useState, type JSX, type SyntheticEvent } from 'react';
import { ensureSessionCsrfToken } from '../auth/useSessionGuard';
import './CreateWorkspaceModal.css';

export interface CreatedWorkspace {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
}

export interface CreateWorkspaceModalProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onCreated?: (workspace: CreatedWorkspace) => void;
}

export const WORKSPACE_SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/;

/**
 * Derives a valid lowercase kebab-case slug from a display name.
 */
export function suggestWorkspaceSlug(name: string): string {
  const cleaned = name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

  if (!cleaned) {
    return '';
  }
  if (cleaned.length === 1) {
    return `${cleaned}-ws`;
  }
  return cleaned.slice(0, 64);
}

export function CreateWorkspaceModal({
  isOpen,
  onClose,
  onCreated,
}: CreateWorkspaceModalProps): JSX.Element | null {
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const nameInputRef = useRef<HTMLInputElement | null>(null);

  const resetForm = (): void => {
    setName('');
    setSlug('');
    setSlugTouched(false);
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
      clearTimeout(timer);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  const handleNameChange = (value: string): void => {
    setName(value);
    if (!slugTouched) {
      setSlug(suggestWorkspaceSlug(value));
    }
    if (errorMessage) {
      setErrorMessage(null);
    }
  };

  const handleSlugChange = (value: string): void => {
    setSlugTouched(true);
    setSlug(
      value
        .toLowerCase()
        .replace(/[^a-z0-9-]/g, '')
        .slice(0, 64),
    );
    if (errorMessage) {
      setErrorMessage(null);
    }
  };

  const handleSubmit = async (e: SyntheticEvent): Promise<void> => {
    e.preventDefault();
    const trimmedName = name.trim();
    const cleanSlug = slug.trim().toLowerCase();

    if (!trimmedName) {
      setErrorMessage('Workspace name is required.');
      return;
    }
    if (!WORKSPACE_SLUG_PATTERN.test(cleanSlug)) {
      setErrorMessage(
        'Workspace slug must be 3-64 lowercase alphanumeric characters or hyphens, starting and ending with alphanumeric characters.',
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

      const res = await fetch('/api/v1/workspaces', {
        method: 'POST',
        headers,
        credentials: 'same-origin',
        body: JSON.stringify({
          name: trimmedName,
          slug: cleanSlug,
        }),
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
              : `Server returned ${String(res.status)}`;
        setErrorMessage(msg);
        setIsSubmitting(false);
        return;
      }

      const created = (await res.json()) as CreatedWorkspace;
      resetForm();
      onCreated?.(created);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Network error creating workspace';
      setErrorMessage(msg);
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <div
        className="kb-create-workspace-scrim"
        onClick={handleClose}
        data-testid="create-workspace-scrim"
      />
      <div
        className="kb-create-workspace-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="kb-create-workspace-title"
      >
        <div className="kb-create-workspace-header">
          <h2 id="kb-create-workspace-title" className="kb-create-workspace-title">
            Create New Workspace
          </h2>
          <button
            type="button"
            className="kb-create-workspace-close"
            onClick={handleClose}
            aria-label="Close dialog"
          >
            ✕
          </button>
        </div>

        <form
          onSubmit={(e) => {
            void handleSubmit(e);
          }}
          className="kb-create-workspace-form"
        >
          {errorMessage && (
            <div
              className="kb-create-workspace-error"
              role="alert"
              data-testid="create-workspace-error"
            >
              {errorMessage}
            </div>
          )}

          <div className="kb-create-workspace-field">
            <label htmlFor="kb-workspace-name" className="kb-create-workspace-label">
              Workspace Name <span className="kb-create-workspace-req">*</span>
            </label>
            <input
              ref={nameInputRef}
              id="kb-workspace-name"
              type="text"
              className="kb-create-workspace-input"
              value={name}
              onChange={(e) => {
                handleNameChange(e.target.value);
              }}
              placeholder="e.g. Acme Corp, Engineering"
              maxLength={128}
              autoComplete="off"
              disabled={isSubmitting}
            />
          </div>

          <div className="kb-create-workspace-field">
            <label htmlFor="kb-workspace-slug" className="kb-create-workspace-label">
              Slug <span className="kb-create-workspace-req">*</span>
            </label>
            <input
              id="kb-workspace-slug"
              type="text"
              className="kb-create-workspace-input kb-create-workspace-slug"
              value={slug}
              onChange={(e) => {
                handleSlugChange(e.target.value);
              }}
              placeholder="e.g. acme-corp"
              maxLength={64}
              autoComplete="off"
              disabled={isSubmitting}
            />
            <span className="kb-create-workspace-hint">
              Unique URL identifier (lowercase letters, numbers, and hyphens).
            </span>
          </div>

          <div className="kb-create-workspace-actions">
            <button
              type="button"
              className="kb-create-workspace-cancel-btn"
              onClick={handleClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="kb-create-workspace-submit-btn"
              disabled={isSubmitting || !name.trim() || !slug.trim()}
            >
              {isSubmitting ? 'Creating...' : 'Create Workspace'}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
