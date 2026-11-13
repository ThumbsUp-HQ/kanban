/**
 * Modal dialog for justifying Hard WIP limit overrides (KB-P3-37, S6.4).
 */

import { useState, type ReactElement } from 'react';
import type { BoardWorkflowState } from './boardApi.ts';

export interface HardWipOverrideModalProps {
  isOpen: boolean;
  state: BoardWorkflowState;
  count: number;
  onCancel: () => void;
  onSubmit: (reason: string) => void;
}

export const MIN_REASON_LENGTH = 10;
export const MAX_REASON_LENGTH = 500;

export function HardWipOverrideModal(props: HardWipOverrideModalProps): ReactElement | null {
  const { isOpen, state, count, onCancel, onSubmit } = props;
  const [reason, setReason] = useState('');

  if (!isOpen) {
    return null;
  }

  const trimmed = reason.trim();
  const isValid = trimmed.length >= MIN_REASON_LENGTH && trimmed.length <= MAX_REASON_LENGTH;
  const isTooShort = trimmed.length > 0 && trimmed.length < MIN_REASON_LENGTH;

  const handleSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (isValid) {
      onSubmit(trimmed);
      setReason('');
    }
  };

  return (
    <div className="hard-wip-modal-overlay" onClick={onCancel} role="presentation">
      <div
        className="hard-wip-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="hard-wip-modal-title"
        onClick={(e) => { e.stopPropagation(); }}
      >
        <h2 id="hard-wip-modal-title" className="hard-wip-modal-title">
          Hard WIP Limit Exceeded
        </h2>
        <p className="hard-wip-modal-desc">
          Column <strong>{state.name}</strong> is at or exceeds its hard WIP limit (
          {count} / {state.wip_hard_limit}). Moving this card requires administrative
          justification.
        </p>

        <form onSubmit={handleSubmit} className="hard-wip-form">
          <label htmlFor="wip-override-reason" className="hard-wip-hint">
            Override justification reason (minimum 10 characters):
          </label>
          <textarea
            id="wip-override-reason"
            className="hard-wip-textarea"
            placeholder="Document why this limit must be overridden..."
            value={reason}
            onChange={(e) => { setReason(e.target.value); }}
            maxLength={MAX_REASON_LENGTH}
            autoFocus
          />

          <div
            className={`hard-wip-hint ${isTooShort ? 'hard-wip-hint--error' : ''}`}
            aria-live="polite"
          >
            {trimmed.length} / {MAX_REASON_LENGTH} characters
            {isTooShort && ` (requires at least ${String(MIN_REASON_LENGTH)} characters)`}
          </div>

          <div className="hard-wip-actions">
            <button
              type="button"
              className="hard-wip-btn hard-wip-btn--cancel"
              onClick={() => {
                setReason('');
                onCancel();
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="hard-wip-btn hard-wip-btn--submit"
              disabled={!isValid}
            >
              Override &amp; move
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
