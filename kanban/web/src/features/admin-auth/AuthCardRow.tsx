import React, { type JSX } from 'react';
import type { AdminAuthCard } from './adminAuthApi';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { renderAuthIcon, LocalAdmin } from '../../components/icons/KanbanIcons';
import './adminAuth.css';

export interface AuthCardRowProps {
  card: AdminAuthCard;
  index: number;
  totalCards: number;
  isPrimary?: boolean;
  onMoveUp?: (card: AdminAuthCard) => void;
  onMoveDown?: (card: AdminAuthCard) => void;
  onToggleEnabled: (card: AdminAuthCard, enabled: boolean) => void;
  onTestHandshake: (card: AdminAuthCard) => void;
  onEdit: (card: AdminAuthCard) => void;
  onDelete: (card: AdminAuthCard) => void;
  onDragStart?: (e: React.DragEvent<HTMLLIElement>, index: number) => void;
  onDragOver?: (e: React.DragEvent<HTMLLIElement>, index: number) => void;
  onDrop?: (e: React.DragEvent<HTMLLIElement>, index: number) => void;
  isTestingHandshake?: boolean;
  isToggling?: boolean;
}

export function AuthCardRow({
  card,
  index,
  totalCards,
  isPrimary = false,
  onMoveUp,
  onMoveDown,
  onToggleEnabled,
  onTestHandshake,
  onEdit,
  onDelete,
  onDragStart,
  onDragOver,
  onDrop,
  isTestingHandshake = false,
  isToggling = false,
}: AuthCardRowProps): JSX.Element {
  const isPinned = card.provider_kind === 'LOCAL_ADMIN';

  const canMoveUp = !isPinned && index > 0;
  const canMoveDown = !isPinned && index < totalCards - 2; // Below non-pinned cards

  return (
    <li
      className={`auth-card-row ${isPinned ? 'auth-card-row--pinned' : ''}`}
      draggable={!isPinned}
      onDragStart={!isPinned && onDragStart ? (e) => { onDragStart(e, index); } : undefined}
      onDragOver={!isPinned && onDragOver ? (e) => { onDragOver(e, index); } : undefined}
      onDrop={!isPinned && onDrop ? (e) => { onDrop(e, index); } : undefined}
      data-testid={`auth-card-row-${card.slug}`}
      data-sort-rank={card.sort_rank}
    >
      <div className="auth-card-left">
        {!isPinned ? (
          <div
            className="auth-card-drag-handle"
            title="Drag to reorder"
            aria-hidden="true"
          >
            ⋮⋮
          </div>
        ) : null}

        <div className="auth-card-reorder-group">
          <button
            type="button"
            className="auth-reorder-btn"
            disabled={!canMoveUp}
            onClick={() => onMoveUp?.(card)}
            aria-label={
              isPinned
                ? 'Local Admin always appears in the break-glass disclosure'
                : `Move ${card.display_name} up`
            }
          >
            ▲
          </button>
          <button
            type="button"
            className="auth-reorder-btn"
            disabled={!canMoveDown}
            onClick={() => onMoveDown?.(card)}
            aria-label={
              isPinned
                ? 'Local Admin always appears in the break-glass disclosure'
                : `Move ${card.display_name} down`
            }
          >
            ▼
          </button>
        </div>

        <div className="auth-card-icon" aria-hidden="true">
          {isPinned ? <LocalAdmin size={20} /> : renderAuthIcon(card.icon_preset, 20)}
        </div>

        <div className="auth-card-info">
          <div className="auth-card-name-row">
            <span className="auth-card-title">{card.display_name}</span>
            <code className="auth-card-slug">{card.slug}</code>
            <span className="auth-card-kind-badge">{card.provider_kind}</span>
            {isPrimary ? (
              <span className="auth-badge-primary auth-badge--primary">Primary</span>
            ) : null}
          </div>
          {card.button_subtext ? (
            <p className="auth-card-subtext">{card.button_subtext}</p>
          ) : null}
        </div>
      </div>

      <div className="auth-card-right">
        {/* Health Status Chip */}
        {(() => {
          const statusStr = card.last_health_status.toUpperCase();
          const statusLower = statusStr.toLowerCase();
          return (
            <div
              className={`auth-health-chip auth-status-chip auth-health-chip--${statusLower} auth-status-chip--${statusLower}`}
              data-testid={`health-chip-${card.slug}`}
            >
              <span>
                {statusStr === 'HEALTHY' && card.latency_ms !== null && card.latency_ms !== undefined
                  ? `HEALTHY (${String(card.latency_ms)} ms)`
                  : statusStr}
              </span>
              {statusStr === 'FAILED' ? (
                <EmojiHint
                  kind="warning"
                  label="Health check failure"
                  content={
                    card.check_summary
                      ? `${card.check_summary}${
                          card.last_handshake_at ? ` (at ${card.last_handshake_at})` : ''
                        }`
                      : 'Connection failed'
                  }
                />
              ) : null}
            </div>
          );
        })()}

        {/* Test Handshake Button */}
        <button
          type="button"
          className="auth-btn-secondary"
          onClick={() => { onTestHandshake(card); }}
          disabled={isTestingHandshake}
          aria-busy={isTestingHandshake}
          data-testid={`test-handshake-${card.slug}`}
        >
          {isTestingHandshake ? 'Testing...' : 'Test handshake'}
        </button>

        {/* Enable / Disable Switch */}
        <label className="auth-toggle-switch auth-switch-label">
          <input
            type="checkbox"
            className="auth-toggle-input auth-switch-input"
            role="switch"
            checked={card.is_enabled}
            onChange={(e) => { onToggleEnabled(card, e.target.checked); }}
            aria-label={`Enable ${card.display_name}`}
            aria-checked={card.is_enabled}
            disabled={isToggling}
          />
          <span className="auth-toggle-track" aria-hidden="true" />
        </label>

        {/* Edit Button */}
        <button
          type="button"
          className="auth-btn-secondary"
          onClick={() => { onEdit(card); }}
        >
          Edit
        </button>

        {/* Delete Button (disabled on LOCAL_ADMIN) */}
        <button
          type="button"
          className="auth-btn-secondary auth-btn-danger"
          onClick={() => { onDelete(card); }}
          disabled={isPinned}
          aria-label={
            isPinned
              ? 'Local Admin cannot be deleted'
              : `Delete ${card.display_name}`
          }
        >
          Delete
        </button>
      </div>
    </li>
  );
}
