/**
 * Text Selection to Linked Issue Floating Toolbar & Modal (KB-P3-50, S8.1).
 * Detects selections strictly inside .docs-prose, computes position using positionHint,
 * and creates linked tickets with VERIFIED_BY_DOC or RELATES_TO backlink.
 */

import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  type JSX,
  type SyntheticEvent,
} from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { positionHint } from '../../components/emoji/positionHint';
import { createIssue, createLink } from './docsApi';
import './DocsWorkspaceView.css';

export interface SelectionToIssueToolbarProps {
  pageId: string;
  projectKey: string;
  pageTitle: string;
  onAnnounce?: ((message: string) => void) | undefined;
}

export function SelectionToIssueToolbar({
  pageId,
  projectKey,
  pageTitle,
  onAnnounce,
}: SelectionToIssueToolbarProps): JSX.Element {
  const queryClient = useQueryClient();

  const [selectionRange, setSelectionRange] = useState<Range | null>(null);
  const [selectedText, setSelectedText] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [summary, setSummary] = useState('');
  const [description, setDescription] = useState('');
  const [createdIssueKey, setCreatedIssueKey] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const floatingBtnRef = useRef<HTMLButtonElement | null>(null);

  // Position floating trigger button using positionHint
  const updatePosition = useCallback(() => {
    if (!selectionRange || !floatingBtnRef.current) return;

    const rangeRect = selectionRange.getBoundingClientRect();
    if (rangeRect.width === 0 && rangeRect.height === 0) return;

    const viewport = {
      width: window.innerWidth,
      height: window.innerHeight,
    };

    const pos = positionHint(
      rangeRect,
      { width: 180, height: 36 },
      viewport,
    );

    floatingBtnRef.current.style.top = `${String(pos.top)}px`;
    floatingBtnRef.current.style.left = `${String(pos.left)}px`;
    floatingBtnRef.current.dataset.placement = pos.placement;
  }, [selectionRange]);

  // Monitor selectionchange
  useEffect(() => {
    const handleSelectionChange = () => {
      if (isModalOpen) return;

      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || sel.rangeCount === 0) {
        setSelectionRange(null);
        setSelectedText('');
        return;
      }

      const range = sel.getRangeAt(0);
      const text = sel.toString();
      const codePointsCount = Array.from(text.trim()).length;

      if (codePointsCount < 3) {
        setSelectionRange(null);
        setSelectedText('');
        return;
      }

      // Check strictly inside .docs-prose
      let container: Node | null = range.commonAncestorContainer;
      if (container.nodeType === Node.TEXT_NODE) {
        container = container.parentNode;
      }

      const proseEl = (container as Element | null)?.closest('.docs-prose');
      if (!proseEl) {
        // Selection is outside .docs-prose - ignore
        setSelectionRange(null);
        setSelectedText('');
        return;
      }

      setSelectionRange(range);
      setSelectedText(text.trim());
    };

    document.addEventListener('selectionchange', handleSelectionChange);
    return () => {
      document.removeEventListener('selectionchange', handleSelectionChange);
    };
  }, [isModalOpen]);

  useEffect(() => {
    updatePosition();
    window.addEventListener('resize', updatePosition, { passive: true });
    window.addEventListener('scroll', updatePosition, { capture: true, passive: true });
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, { capture: true });
    };
  }, [updatePosition]);

  // Dismiss on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isModalOpen) {
          setIsModalOpen(false);
        } else {
          setSelectionRange(null);
          setSelectedText('');
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isModalOpen]);

  // Open modal and pre-fill fields
  const handleOpenModal = () => {
    const lines = selectedText.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const firstLine = lines[0] ?? '';
    const initialSummary = Array.from(firstLine).slice(0, 120).join('');

    // Blockquote selected text (capped at 4000 chars)
    const cappedText = selectedText.slice(0, 4000);
    const quote = cappedText
      .split(/\r?\n/)
      .map((l) => `> ${l}`)
      .join('\n');
    const sourceLink = `\n\nSource: [${pageTitle}](/projects/${projectKey}/docs/${pageId})`;

    setSummary(initialSummary);
    setDescription(`${quote}${sourceLink}`);
    setErrorMessage(null);
    setCreatedIssueKey(null);
    setIsModalOpen(true);
  };

  // Issue creation mutation
  const createIssueMutation = useMutation({
    mutationFn: async () => {
      const issue = await createIssue(projectKey, {
        title: summary.trim(),
        description: description.trim(),
      });

      // Link to document
      try {
        await createLink({
          source_id: issue.id,
          target_id: pageId,
          link_type: 'VERIFIED_BY_DOC',
        });
      } catch {
        // Fallback to RELATES_TO
        await createLink({
          source_id: issue.id,
          target_id: pageId,
          link_type: 'RELATES_TO',
        });
      }

      return issue;
    },
    onSuccess: (issue) => {
      const keyOrId = issue.key ?? issue.id;
      setCreatedIssueKey(keyOrId);
      void queryClient.invalidateQueries({ queryKey: qk.page(pageId) });
      onAnnounce?.(`Created linked issue ${keyOrId}`);
    },
    onError: (err: unknown) => {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to create issue');
    },
  });

  const handleSubmitModal = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!summary.trim()) {
      setErrorMessage('Summary cannot be empty');
      return;
    }
    createIssueMutation.mutate();
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectionRange(null);
    setSelectedText('');
    setCreatedIssueKey(null);
  };

  return (
    <>
      {/* Floating Action Button */}
      {selectionRange && !isModalOpen && (
        <button
          ref={floatingBtnRef}
          type="button"
          className="docs-floating-action-btn"
          onClick={handleOpenModal}
          data-testid="create-linked-issue-floating-btn"
          aria-label="Create Linked Issue from Selection"
        >
          ➕ Create Linked Issue
        </button>
      )}

      {/* Modal Dialog */}
      {isModalOpen && (
        <div
          className="docs-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Create linked issue"
        >
          <div className="docs-modal">
            <h3 className="docs-modal__title">Create Linked Issue</h3>

            {errorMessage && (
              <div className="docs-modal__error" role="alert">
                {errorMessage}
              </div>
            )}

            {createdIssueKey ? (
              <div className="docs-modal__success" data-testid="issue-created-announcement">
                <p>Created linked issue <strong>{createdIssueKey}</strong>.</p>
                <div className="docs-modal__actions">
                  <a
                    href={`/projects/${projectKey}/issues/${createdIssueKey}`}
                    className="docs-tree-btn docs-tree-btn--primary"
                    data-testid="view-created-issue-link"
                  >
                    View Issue
                  </a>
                  <button
                    type="button"
                    className="docs-tree-btn"
                    onClick={() => {
                      handleCloseModal();
                    }}
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmitModal}>
                <label htmlFor="issue-summary-input" className="docs-modal__label">
                  Summary
                </label>
                <input
                  id="issue-summary-input"
                  type="text"
                  className="docs-modal__input"
                  value={summary}
                  onChange={(e) => {
                    setSummary(e.target.value);
                  }}
                  maxLength={500}
                  required
                  data-testid="issue-summary-input"
                />

                <label htmlFor="issue-description-input" className="docs-modal__label">
                  Description
                </label>
                <textarea
                  id="issue-description-input"
                  className="docs-modal__textarea"
                  value={description}
                  onChange={(e) => {
                    setDescription(e.target.value);
                  }}
                  rows={6}
                  data-testid="issue-description-input"
                />

                <div className="docs-modal__actions">
                  <button
                    type="button"
                    className="docs-tree-btn"
                    onClick={() => {
                      handleCloseModal();
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="docs-tree-btn docs-tree-btn--primary"
                    disabled={createIssueMutation.isPending}
                    data-testid="submit-issue-create-btn"
                  >
                    {createIssueMutation.isPending ? 'Creating...' : 'Create & Link'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
