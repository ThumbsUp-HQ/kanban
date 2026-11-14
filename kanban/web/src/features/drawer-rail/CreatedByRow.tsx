import React, { useState, type JSX } from 'react';
import type { CreatorSummary, IssueDetail } from '../drawer/slots';
import { EmojiHint } from '../../components/emoji/EmojiHint';

export interface CreatedByRowProps {
  issue: IssueDetail;
  isAdmin: boolean;
  onOverrideCreator: (payload: { created_by: string; reason: string }) => Promise<void>;
}

function formatPrincipal(p?: CreatorSummary | string | null): string {
  if (!p) return 'Unknown';
  if (typeof p === 'string') {
    return p.startsWith('@') ? p : `@${p}`;
  }
  if (p.redacted) {
    return p.label ?? '1 External Collaborator';
  }
  return p.handle ? `@${p.handle}` : 'Unknown';
}

export function CreatedByRow({
  issue,
  isAdmin,
  onOverrideCreator,
}: CreatedByRowProps): JSX.Element {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newCreator, setNewCreator] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const prov = issue.provenance;
  const isOverridden = prov?.overridden ?? false;

  const currentCreatorStr = formatPrincipal(prov?.created_by);
  const origCreatorStr = formatPrincipal(prov?.original_created_by ?? prov?.created_by);
  const modifierStr = formatPrincipal(prov?.creator_modified_by);
  const modifiedAt = prov?.creator_modified_at ?? '';
  const overrideReason = prov?.reason ?? '';

  const popoverContent = isOverridden
    ? `Originally created by ${origCreatorStr} - overridden to ${currentCreatorStr} by ${modifierStr} on ${modifiedAt}. Reason: ${overrideReason}`
    : '';

  const handleSubmit = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();
    const trimmedUser = newCreator.trim().replace(/^@/, '');
    const trimmedReason = reason.trim();

    if (!trimmedUser) {
      setError('Please provide a valid user handle or UUID.');
      return;
    }
    if (trimmedReason.length < 10) {
      setError('Reason must be at least 10 characters.');
      return;
    }
    if (trimmedReason.length > 500) {
      setError('Reason cannot exceed 500 characters.');
      return;
    }

    setError(null);
    setIsSubmitting(true);
    try {
      await onOverrideCreator({ created_by: trimmedUser, reason: trimmedReason });
      setIsModalOpen(false);
      setNewCreator('');
      setReason('');
    } catch (err: unknown) {
      if (
        typeof err === 'object' &&
        err !== null &&
        (('code' in err && (err as { code: string }).code === 'AAL2_REQUIRED') ||
          ('status' in err && (err as { status: number }).status === 403))
      ) {
        setError('AAL2 second-factor authentication is required to override issue creator.');
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to override creator.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="prop-row" data-prop="created-by">
      <span className="prop-row__label">Created by</span>
      <div className="prop-row__value">
        <div className="creator-row__container">
          <span className="creator-name" data-testid="creator-handle">
            {currentCreatorStr}
          </span>

          {isOverridden ? (
            <EmojiHint
              kind="creatorOverride"
              content={popoverContent}
              label="Creator overridden"
            />
          ) : null}

          {isAdmin ? (
            <button
              type="button"
              className="creator-row__change-btn"
              onClick={() => { setIsModalOpen(true); }}
            >
              Change...
            </button>
          ) : null}
        </div>

        {isModalOpen ? (
          <div className="override-modal-backdrop" role="dialog" aria-modal="true">
            <div className="override-modal">
              <h3 className="override-modal__title">Override Issue Creator</h3>
              <form onSubmit={(e) => { void handleSubmit(e); }} className="override-modal__form">
                <div>
                  <label
                    htmlFor="override-creator-input"
                    className="override-modal__label"
                  >
                    New Creator (@handle or UUID)
                  </label>
                  <input
                    id="override-creator-input"
                    type="text"
                    className="prop-row__input override-modal__input"
                    placeholder="e.g. maya"
                    value={newCreator}
                    onChange={(e) => { setNewCreator(e.target.value); }}
                    required
                  />
                </div>

                <div>
                  <label
                    htmlFor="override-reason-input"
                    className="override-modal__label"
                  >
                    Administrative Reason (10-500 characters)
                  </label>
                  <textarea
                    id="override-reason-input"
                    className="override-modal__textarea"
                    placeholder="Provide reason for creator reassignment..."
                    value={reason}
                    onChange={(e) => { setReason(e.target.value); }}
                    required
                  />
                </div>

                {error ? (
                  <div className="prop-row__alert" role="alert">
                    {error}
                  </div>
                ) : null}

                <div className="override-modal__actions">
                  <button
                    type="button"
                    className="override-modal__cancel-btn"
                    onClick={() => { setIsModalOpen(false); }}
                    disabled={isSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="override-modal__submit-btn"
                    disabled={isSubmitting}
                  >
                    {isSubmitting ? 'Saving...' : 'Override'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
