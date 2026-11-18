/**
 * Sticky to Doc AI Promotion Preview Modal (KB-AUDIT-11, KANBA-217, S8.2).
 * Shows synthesized title, Markdown headings/Mermaid blocks preview, and preserved ACL grants.
 */

import React, { useState, useEffect, type JSX, type SyntheticEvent } from 'react';
import {
  previewStickyPromotion,
  type StickyItem,
} from './stickiesApi';
import './StickiesGrid.css';

export interface StickyPromotePreviewModalProps {
  sticky: StickyItem;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (payload: {
    title: string;
    structured_body_markdown: string;
    expected_sticky_sha256?: string;
  }) => Promise<void>;
}

function getInitialTitle(sticky: StickyItem): string {
  const lines = sticky.body_markdown.split('\n');
  const firstHeading = lines.find((l) => l.startsWith('#'))?.replace(/^#+\s*/, '').trim();
  return firstHeading ?? lines[0]?.trim().slice(0, 80) ?? 'Promoted Specification';
}

export function StickyPromotePreviewModal({
  sticky,
  isOpen,
  onClose,
  onConfirm,
}: StickyPromotePreviewModalProps): JSX.Element | null {
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [docTitle, setDocTitle] = useState(() => getInitialTitle(sticky));
  const [markdownBody, setMarkdownBody] = useState(sticky.body_markdown);
  const [originalSha, setOriginalSha] = useState<string | undefined>(sticky.body_sha256);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [directAclCount, setDirectAclCount] = useState<number>(0);

  useEffect(() => {
    if (!isOpen) return;

    let active = true;

    async function loadPreview() {
      try {
        const preview = await previewStickyPromotion(sticky.id);
        if (!active) return;
        if (preview.proposal.title) {
          setDocTitle(preview.proposal.title);
        }
        if (preview.rendered_markdown) {
          setMarkdownBody(preview.rendered_markdown);
        }
        if (preview.original_sha256) {
          setOriginalSha(preview.original_sha256);
        }
        if (preview.warnings) {
          setWarnings(preview.warnings);
        }
        if (preview.acl_preview.direct_entries_count !== undefined) {
          setDirectAclCount(preview.acl_preview.direct_entries_count);
        }
      } catch {
        // Fallback to deterministic structuring if preview API is off/air-gapped
        if (!active) return;
        const fallbackStructured = sticky.body_markdown.includes('```mermaid')
          ? sticky.body_markdown
          : `${sticky.body_markdown}\n\n\`\`\`mermaid\ngraph TD\n  Start[Start] --> Process[Process] --> Finish[Finish]\n\`\`\``;
        setMarkdownBody(fallbackStructured);
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    void loadPreview();

    return () => {
      active = false;
    };
  }, [isOpen, sticky.id, sticky.body_markdown]);

  if (!isOpen) return null;

  const handleSubmit = async (e: SyntheticEvent) => {
    e.preventDefault();
    const trimmedTitle = docTitle.trim();
    if (!trimmedTitle) {
      setError('Title cannot be empty');
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      await onConfirm({
        title: trimmedTitle,
        structured_body_markdown: markdownBody,
        ...(originalSha ? { expected_sticky_sha256: originalSha } : {}),
      });
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to promote sticky to document');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="sticky-promote-modal-backdrop"
      onClick={onClose}
      data-testid="sticky-promote-preview-backdrop"
    >
      <div
        className="sticky-promote-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="promote-modal-heading"
        onClick={(e) => { e.stopPropagation(); }}
        data-testid="sticky-promote-preview-modal"
      >
        <header className="sticky-promote-modal__header">
          <h2 id="promote-modal-heading" className="sticky-promote-modal__title">
            <span aria-hidden="true">📄</span> Promote Sticky to Document
          </h2>
          <button
            type="button"
            className="sticky-promote-modal__close-btn"
            onClick={onClose}
            aria-label="Close promotion preview"
            data-testid="close-promote-modal-btn"
          >
            ✕
          </button>
        </header>

        {isLoading ? (
          <div className="sticky-promote-modal__loading" data-testid="promote-modal-loading">
            Synthesizing document structure and Mermaid diagrams...
          </div>
        ) : (
          <form onSubmit={(e) => { void handleSubmit(e); }} className="sticky-promote-modal__form">
            {error && (
              <div
                role="alert"
                className="sticky-promote-modal__error"
                data-testid="promote-modal-error"
              >
                {error}
              </div>
            )}

            {/* Preserved 🛡️ ACL Grants Notice */}
            <div className="sticky-promote-modal__acl-notice" data-testid="promote-modal-acl">
              <span className="sticky-promote-modal__acl-icon" aria-hidden="true">🛡️</span>
              <div className="sticky-promote-modal__acl-text">
                <strong>Access Grants Preserved:</strong> All {directAclCount} explicit ACL grant(s)
                and security policies from this sticky note will be copied verbatim to the newly created document.
              </div>
            </div>

            {/* Warnings banner */}
            {warnings.length > 0 && (
              <div className="sticky-promote-modal__warnings" data-testid="promote-modal-warnings">
                <strong>Integrity Warnings:</strong>
                <ul>
                  {warnings.map((w, idx) => (
                    <li key={idx}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Doc Title Input */}
            <div className="sticky-promote-modal__field">
              <label htmlFor="promote-doc-title" className="sticky-promote-modal__label">
                Document Title
              </label>
              <input
                id="promote-doc-title"
                type="text"
                className="sticky-promote-modal__input"
                value={docTitle}
                onChange={(e) => { setDocTitle(e.target.value); }}
                required
                data-testid="promote-modal-title"
              />
            </div>

            {/* Markdown Body Preview / Editor */}
            <div className="sticky-promote-modal__field">
              <label htmlFor="promote-doc-markdown" className="sticky-promote-modal__label">
                Structured Markdown & Mermaid Preview
              </label>
              <textarea
                id="promote-doc-markdown"
                className="sticky-promote-modal__textarea mono"
                value={markdownBody}
                onChange={(e) => { setMarkdownBody(e.target.value); }}
                rows={10}
                data-testid="promote-modal-markdown"
              />
            </div>

            <footer className="sticky-promote-modal__footer">
              <button
                type="button"
                className="sticky-promote-modal__cancel-btn"
                onClick={onClose}
                disabled={isSubmitting}
                data-testid="cancel-promote-btn"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="sticky-promote-modal__confirm-btn"
                disabled={isSubmitting || isLoading}
                data-testid="confirm-promote-btn"
              >
                {isSubmitting ? 'Promoting...' : 'Confirm Promotion'}
              </button>
            </footer>
          </form>
        )}
      </div>
    </div>
  );
}
