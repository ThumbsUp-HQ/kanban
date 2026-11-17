import React, { type JSX } from 'react';
import type { AuthCard } from './authApi';
import { renderAuthIcon } from '../../components/icons/KanbanIcons';
import './auth.css';

function clampText(text: string | null | undefined, maxLen: number): string {
  if (!text) return '';
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}

export interface AuthCardButtonProps {
  card: AuthCard;
  isPrimary?: boolean;
  next?: string;
  isLdapExpanded?: boolean;
  onToggleLdap?: () => void;
  formId?: string;
}

export function AuthCardButton({
  card,
  isPrimary = false,
  next = '/',
  isLdapExpanded = false,
  onToggleLdap,
  formId,
}: AuthCardButtonProps): JSX.Element {
  const isLdap = card.provider_kind === 'LDAP';

  const accessibleName = isLdap
    ? `Sign in with ${card.display_name}`
    : `Continue with ${card.display_name}`;

  const clampedDisplayName = clampText(card.display_name, 80);
  const clampedSubtext = clampText(card.button_subtext, 120);

  const handleClick = () => {
    if (isLdap) {
      onToggleLdap?.();
    } else {
      const targetUrl = `/api/v1/auth/cards/${encodeURIComponent(card.slug)}/start?next=${encodeURIComponent(next)}`;
      window.location.assign(targetUrl);
    }
  };

  return (
    <button
      type="button"
      className="auth-card-button"
      onClick={handleClick}
      aria-label={accessibleName}
      aria-expanded={isLdap ? isLdapExpanded : undefined}
      aria-controls={isLdap && isLdapExpanded ? formId : undefined}
    >
      <div className="auth-card-main-content">
        <span className="auth-card-icon" aria-hidden="true">
          {renderAuthIcon(card.icon_preset, 20)}
        </span>
        <div className="auth-card-text-wrap">
          <span className="auth-card-display-name" title={card.display_name}>
            {clampedDisplayName}
          </span>
          {clampedSubtext ? (
            <span className="auth-card-subtext" title={card.button_subtext ?? undefined}>
              {clampedSubtext}
            </span>
          ) : null}
        </div>
      </div>
      <div className="auth-card-meta">
        {isPrimary ? <span className="auth-primary-badge">Primary</span> : null}
        {isLdap ? (
          <span className="auth-card-chevron" aria-hidden="true">
            {isLdapExpanded ? '▾' : '▸'}
          </span>
        ) : null}
      </div>
    </button>
  );
}
