import React, { useEffect, useState, type JSX } from 'react';

export interface WorkflowStateItem {
  id: string;
  name: string;
  group?: string | undefined;
  sort_order?: number | undefined;
}

export interface TouchReorderPopoverProps {
  isOpen: boolean;
  itemKey: string;
  itemSummary?: string | undefined;
  currentStateId?: string | undefined;
  states?: WorkflowStateItem[] | undefined;
  kind?: 'issue' | 'sticky' | undefined;
  onClose: () => void;
  onSelectState?: ((stateId: string) => void) | undefined;
  onSelectRank?: ((rankPosition: 'top' | 'bottom') => void) | undefined;
  onApplyMove?: ((stateId: string, rankPosition?: 'top' | 'bottom') => void) | undefined;
  onReorderSticky?: ((position: 'top' | 'bottom' | 'up' | 'down') => void) | undefined;
}

/**
 * Mobile touch action popover and bottom-sheet fallback for Board Cards and Stickies (KAN-342).
 *
 * Provides touch-accessible controls to select target workflow state and rank position
 * without relying on mouse drag events.
 */
export function TouchReorderPopover({
  isOpen,
  itemKey,
  itemSummary,
  currentStateId,
  states = [],
  kind = 'issue',
  onClose,
  onSelectState,
  onSelectRank,
  onApplyMove,
  onReorderSticky,
}: TouchReorderPopoverProps): JSX.Element | null {
  const [selectedStateId, setSelectedStateId] = useState<string>(
    currentStateId ?? states[0]?.id ?? '',
  );
  const [prevCurrentStateId, setPrevCurrentStateId] = useState<string | undefined>(currentStateId);
  const [selectedRank, setSelectedRank] = useState<'top' | 'bottom'>('bottom');

  if (currentStateId !== prevCurrentStateId) {
    setPrevCurrentStateId(currentStateId);
    setSelectedStateId(currentStateId ?? states[0]?.id ?? '');
  }

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  const handleStateClick = (stateId: string): void => {
    setSelectedStateId(stateId);
    onSelectState?.(stateId);
    onApplyMove?.(stateId, selectedRank);
  };

  const handleRankClick = (rank: 'top' | 'bottom'): void => {
    setSelectedRank(rank);
    onSelectRank?.(rank);
    if (kind === 'sticky') {
      onReorderSticky?.(rank);
    }
  };

  const handleApply = (): void => {
    if (kind === 'sticky') {
      onReorderSticky?.(selectedRank);
      onClose();
      return;
    }
    if (selectedStateId) {
      onApplyMove?.(selectedStateId, selectedRank);
      onSelectState?.(selectedStateId);
    }
    onClose();
  };

  return (
    <div
      className="touch-reorder-overlay"
      data-testid="touch-reorder-overlay"
    >
      <div
        className="touch-reorder-backdrop"
        data-testid="touch-reorder-backdrop"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="touch-reorder-title"
        className="touch-reorder-popover"
        data-testid="touch-reorder-popover"
      >
        <div className="touch-reorder-header">
          <div className="touch-reorder-title-wrap">
            <span className="touch-reorder-badge">{kind === 'sticky' ? 'Sticky Note' : 'Task'}</span>
            <h2 id="touch-reorder-title" className="touch-reorder-title" data-testid="touch-reorder-title">
              Move {itemKey}
            </h2>
            {itemSummary ? (
              <p className="touch-reorder-summary" title={itemSummary}>
                {itemSummary}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            className="touch-reorder-close-btn"
            data-testid="touch-reorder-close-btn"
            onClick={onClose}
            aria-label="Close reorder popover"
          >
            ✕
          </button>
        </div>

        <div className="touch-reorder-body">
          {kind === 'issue' && states.length > 0 && (
            <div className="touch-reorder-section">
              <label className="touch-reorder-section-label">Target Workflow State</label>
              <div className="touch-reorder-states-grid" role="radiogroup" aria-label="Target state">
                {states.map((st) => {
                  const isCurrent = st.id === currentStateId;
                  const isSelected = st.id === selectedStateId;
                  return (
                    <button
                      key={st.id}
                      type="button"
                      role="radio"
                      aria-checked={isSelected}
                      className={`touch-reorder-state-option ${isSelected ? 'touch-reorder-state-option--selected' : ''} ${isCurrent ? 'touch-reorder-state-option--current' : ''}`}
                      data-testid={`touch-state-option-${st.id}`}
                      onClick={() => { handleStateClick(st.id); }}
                    >
                      <span className="touch-reorder-state-glyph" aria-hidden="true">
                        {isSelected ? '●' : '○'}
                      </span>
                      <span className="touch-reorder-state-name">{st.name}</span>
                      {isCurrent && <span className="touch-reorder-current-tag">(Current)</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="touch-reorder-section">
            <label className="touch-reorder-section-label">Column Rank Position</label>
            <div className="touch-reorder-rank-options">
              <button
                type="button"
                className={`touch-reorder-rank-btn ${selectedRank === 'top' ? 'touch-reorder-rank-btn--active' : ''}`}
                data-testid="touch-rank-top"
                onClick={() => { handleRankClick('top'); }}
              >
                <span aria-hidden="true">⤒</span> Top of column
              </button>
              <button
                type="button"
                className={`touch-reorder-rank-btn ${selectedRank === 'bottom' ? 'touch-reorder-rank-btn--active' : ''}`}
                data-testid="touch-rank-bottom"
                onClick={() => { handleRankClick('bottom'); }}
              >
                <span aria-hidden="true">⤓</span> Bottom of column
              </button>
            </div>
          </div>
        </div>

        <div className="touch-reorder-actions">
          <button
            type="button"
            className="touch-reorder-cancel-btn"
            data-testid="touch-reorder-cancel-btn"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className="touch-reorder-apply-btn"
            data-testid="touch-reorder-apply-btn"
            onClick={handleApply}
          >
            Move Card
          </button>
        </div>
      </div>
    </div>
  );
}
