/**
 * Effective Access Inspector Popover (KB-P3-49, S3.4).
 * Transparent object access inspector: Users, Groups, Agents with Kill Switch, Deny Overrides & Redaction.
 */

import React, {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  type KeyboardEvent,
} from 'react';
import { useQuery } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { positionHint } from '../../components/emoji/positionHint';
import { AgentKillSwitchControl } from './AgentKillSwitchControl';
import { useFocusTrap } from '../drawer/useFocusTrap';
import type {
  AccessManifest,
  ManifestAgent,
  ManifestGroup,
  ManifestUser,
} from './types';
import './AccessInspectorPopover.css';

export interface AccessInspectorPopoverProps {
  objectId: string;
  anchorEl?: HTMLElement | null | undefined;
  onClose: () => void;
}

function getEffectiveCapabilityBadge(caps: string[]): { label: string; modifier: string } {
  if (caps.includes('ADMIN')) {
    return { label: 'Admin', modifier: 'admin' };
  }
  if (caps.includes('EDIT')) {
    return { label: 'Edit', modifier: 'edit' };
  }
  if (caps.includes('COMMENT')) {
    return { label: 'Comment', modifier: 'comment' };
  }
  return { label: 'View', modifier: 'view' };
}

function formatProvenance(src?: string): string {
  if (!src) {
    return '[Direct Share]';
  }
  switch (src) {
    case 'project_owner':
      return '[Project Owner]';
    case 'project_role':
      return '[Project Role]';
    case 'workspace_role':
    case 'workspace_admin':
      return '[Workspace Admin]';
    case 'direct_share':
      return '[Direct Share]';
    default:
      return src.startsWith('[') ? src : `[${src}]`;
  }
}

function formatScopeSummary(scope?: string): string {
  if (!scope) {
    return '[Project Scoped]';
  }
  return scope.startsWith('[') ? scope : `[${scope}]`;
}

function formatRedactedLabel(count?: number, label?: string): string {
  if (label) {
    return label;
  }
  const n = count && count > 0 ? count : 1;
  return `${String(n)} External Collaborator${n === 1 ? '' : 's'}`;
}

function getAgentRole(agent: ManifestAgent): string {
  if (agent.role) {
    return agent.role;
  }
  return agent.capabilities.includes('TRANSITION') ? 'Gate' : 'Read';
}

export function AccessInspectorPopover({
  objectId,
  anchorEl,
  onClose,
}: AccessInspectorPopoverProps): React.JSX.Element {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const openerRef = useRef<HTMLElement | null>(anchorEl ?? (document.activeElement as HTMLElement | null));
  const titleId = useId();

  const { data: manifest, isLoading, isError } = useQuery<AccessManifest>({
    queryKey: qk.access(objectId),
    queryFn: async ({ signal }) => {
      const res = await fetch(`/api/v1/objects/${objectId}/access`, {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
        signal,
      });
      if (!res.ok) {
        throw new Error(`Failed to load access manifest: ${String(res.status)}`);
      }
      return (await res.json()) as AccessManifest;
    },
    enabled: Boolean(objectId),
  });

  // Restore focus to invoking element on unmount
  useEffect(() => {
    if (!openerRef.current || openerRef.current === document.body) {
      const active = document.activeElement as HTMLElement | null;
      if (active && active !== document.body && !dialogRef.current?.contains(active)) {
        openerRef.current = active;
      }
    }
    return () => {
      const opener = openerRef.current;
      if (opener && document.contains(opener)) {
        opener.focus();
      }
    };
  }, []);

  useFocusTrap(true, dialogRef);

  const handleClose = (): void => {
    const opener = openerRef.current;
    onClose();
    if (opener && document.contains(opener)) {
      opener.focus();
    }
  };

  // Strict CSP CSSOM positioning with positionHint
  useLayoutEffect(() => {
    const el = dialogRef.current;
    /* v8 ignore next 3 */
    if (!el || window.innerWidth <= 767) {
      return;
    }

    const popupSize = {
      width: el.offsetWidth || 520,
      height: el.offsetHeight || 420,
    };
    const viewport = {
      width: window.innerWidth,
      height: window.innerHeight,
    };

    if (anchorEl) {
      const triggerRect = anchorEl.getBoundingClientRect();
      const pos = positionHint(triggerRect, popupSize, viewport);
      el.style.top = `${String(pos.top)}px`;
      el.style.left = `${String(pos.left)}px`;
    } else {
      const top = Math.max(16, (viewport.height - popupSize.height) / 2);
      const left = Math.max(16, (viewport.width - popupSize.width) / 2);
      el.style.top = `${String(Math.round(top))}px`;
      el.style.left = `${String(Math.round(left))}px`;
    }
  }, [anchorEl, manifest, isLoading, isError]);

  // Initial focus and focus trapping
  useEffect(() => {
    const el = dialogRef.current;
    /* v8 ignore next 3 */
    if (!el) {
      return;
    }
    const focusable = el.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    /* v8 ignore start */
    if (focusable.length === 0) {
      el.focus();
      return;
    }
    /* v8 ignore stop */
    focusable[0]?.focus();
  }, [isLoading, isError]);

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      e.preventDefault();
      handleClose();
    }
  };

  const handleManageAccess = (): void => {
    window.dispatchEvent(
      new CustomEvent('kb:open-manage-access', {
        detail: { objectId },
      }),
    );
  };

  const renderScopeText = (): string => {
    if (!manifest?.inherited_scope) {
      return 'Inherited from Project';
    }
    const scope = manifest.inherited_scope;
    if (scope.kind === 'private') {
      return 'Private';
    }
    if (scope.kind === 'project') {
      const pName = (scope.project_name && scope.project_name.length > 0)
        ? scope.project_name
        : ((scope.project_key && scope.project_key.length > 0) ? scope.project_key : 'Project');
      const wsName = (scope.workspace_name && scope.workspace_name.length > 0)
        ? scope.workspace_name
        : 'Default';
      return `📂 Project "${pName}" (Workspace: ${wsName})`;
    }
    const wsName = (scope.workspace_name && scope.workspace_name.length > 0)
      ? scope.workspace_name
      : 'Default';
    return `Workspace: ${wsName}`;
  };

  const canonicalKey = (manifest?.canonical_key && manifest.canonical_key.length > 0)
    ? manifest.canonical_key
    : 'KAN-142';
  const objectType = ((manifest?.object_type && manifest.object_type.length > 0)
    ? manifest.object_type
    : 'ISSUE').toUpperCase();
  const callerCaps = manifest?.caller_capabilities ?? [];
  const canManage = callerCaps.some((c) => c === 'SHARE' || c === 'ADMIN');
  const canAdmin = callerCaps.includes('ADMIN');
  const hasRedacted = (manifest?.redacted_entries?.length ?? 0) > 0 || (manifest?.redacted_count ?? 0) > 0;
  const hasRedactedEntries = (manifest?.redacted_entries?.length ?? 0) > 0;

  return (
    <>
      <div
        className="access-inspector-backdrop"
        onClick={handleClose}
        aria-hidden="true"
      />
      <div
        ref={dialogRef}
        className="access-inspector"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
      >
        <header className="access-inspector__header">
          <h2 id={titleId} className="access-inspector__title">
            EFFECTIVE ACCESS FOR {objectType}{' '}
            <span className="mono">{canonicalKey}</span>
          </h2>
          <div className="access-inspector__header-actions">
            {canManage && (
              <button
                type="button"
                className="access-inspector__btn access-inspector__btn--secondary"
                onClick={handleManageAccess}
              >
                [Manage Access...]
              </button>
            )}
            <button
              type="button"
              className="access-inspector__close-btn"
              onClick={handleClose}
              aria-label="Close Access Inspector"
            >
              ✕
            </button>
          </div>
        </header>

        {isLoading && (
          <div className="access-inspector__loading">
            Loading effective access manifest...
          </div>
        )}

        {isError && (
          <div className="access-inspector__error" role="alert">
            Object was not found or you do not have access.
          </div>
        )}

        {!isLoading && !isError && manifest && (
          <>
            <div className="access-inspector__scope-banner">
              <span className="access-inspector__scope-label">Inherited Scope:</span>
              <span className="access-inspector__scope-badge">{renderScopeText()}</span>
            </div>

            <div className="access-inspector__body">
              {/* 1. USERS */}
              <section className="access-inspector__section">
                <div className="access-inspector__section-header">
                  <span className="access-inspector__section-title">
                    👤 USERS ({String(manifest.users.length)} Direct)
                  </span>
                </div>
                {manifest.users.length === 0 ? (
                  <div className="access-inspector__empty">None</div>
                ) : (
                  manifest.users.map((user: ManifestUser) => {
                    const badge = getEffectiveCapabilityBadge(user.capabilities);
                    return (
                      <div key={user.principal_id} className="access-inspector__row">
                        <div className="access-inspector__row-left">
                          <span>{user.display_name}</span>
                          <span className="mono">{user.handle}</span>
                        </div>
                        <div className="access-inspector__row-right">
                          <span
                            className={`access-inspector__badge access-inspector__badge--${badge.modifier}`}
                          >
                            {badge.label}
                          </span>
                          <span className="access-inspector__tag">
                            {formatProvenance(user.grant_source)}
                          </span>
                        </div>
                      </div>
                    );
                  })
                )}
              </section>

              {/* 2. GROUPS */}
              <section className="access-inspector__section">
                <div className="access-inspector__section-header">
                  <span className="access-inspector__section-title">
                    👥 GROUPS ({String(manifest.groups.length)})
                  </span>
                </div>
                {manifest.groups.length === 0 ? (
                  <div className="access-inspector__empty">None</div>
                ) : (
                  manifest.groups.map((group: ManifestGroup) => {
                    const badge = getEffectiveCapabilityBadge(group.capabilities);
                    let originStr = `(${String(group.member_count)} members)`;
                    if (group.external_source === 'LDAP') {
                      originStr = `(${String(group.member_count)} members, LDAPS synced)`;
                    } else if (group.external_source === 'OIDC') {
                      originStr = `(${String(group.member_count)} members, OIDC)`;
                    }
                    return (
                      <div key={group.principal_id} className="access-inspector__row">
                        <div className="access-inspector__row-left">
                          <span>{group.name}</span>
                          <span className="access-inspector__tag">{originStr}</span>
                        </div>
                        <div className="access-inspector__row-right">
                          <span
                            className={`access-inspector__badge access-inspector__badge--${badge.modifier}`}
                          >
                            {badge.label}
                          </span>
                          <span className="access-inspector__tag">
                            {formatProvenance(group.grant_source)}
                          </span>
                        </div>
                      </div>
                    );
                  })
                )}
              </section>

              {/* 3. AGENTS & WORKFLOW RUNNERS */}
              <section className="access-inspector__section">
                <div className="access-inspector__section-header">
                  <span className="access-inspector__section-title">
                    🤖 AGENTS & WORKFLOW RUNNERS ({String(manifest.agents.length)} Active)
                  </span>
                  {canAdmin && manifest.agents.length > 0 && (
                    <AgentKillSwitchControl
                      objectId={objectId}
                      canonicalKey={canonicalKey}
                      agentsCount={manifest.agents.length}
                    />
                  )}
                </div>
                {manifest.agents.length === 0 ? (
                  <div className="access-inspector__empty">None</div>
                ) : (
                  manifest.agents.map((agent: ManifestAgent) => {
                    const role = getAgentRole(agent);
                    const scopeStr = formatScopeSummary(agent.scope_summary);
                    return (
                      <div key={agent.principal_id} className="access-inspector__row">
                        <div className="access-inspector__row-left">
                          <EmojiHint
                            kind="agent"
                            label={agent.display_name}
                            content={`Agent harness: ${agent.provider_badge ?? 'Autonomous runner'} - Effective permissions: ${agent.capabilities.join(', ')}`}
                          />
                          <span>{agent.display_name}</span>
                          {agent.provider_badge && (
                            <span className="mono access-inspector__tag">
                              ({agent.provider_badge})
                            </span>
                          )}
                        </div>
                        <div className="access-inspector__row-right">
                          <span className="access-inspector__badge">
                            {role}
                          </span>
                          <span className="access-inspector__tag">
                            {scopeStr}
                          </span>
                        </div>
                      </div>
                    );
                  })
                )}
              </section>

              {/* 4. RESTRICTED OVERRIDES */}
              <section className="access-inspector__section">
                <div className="access-inspector__section-header">
                  <span className="access-inspector__section-title">
                    🔒 RESTRICTED OVERRIDES ({String(manifest.deny_overrides.length)})
                  </span>
                </div>
                {manifest.deny_overrides.length === 0 ? (
                  <div className="access-inspector__empty">None</div>
                ) : (
                  manifest.deny_overrides.map((override, idx) => (
                    <div key={override.principal_id ?? `deny-${String(idx)}`} className="access-inspector__row">
                      <div className="access-inspector__row-left">
                        <EmojiHint kind="restricted" label="Restricted Override" />
                        <span>{override.display_name}</span>
                      </div>
                      <div className="access-inspector__row-right">
                        <span className="access-inspector__deny-pill">
                          Explicit DENY
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </section>

              {/* Anti-Enumeration Redacted Principals (Defense-in-depth) */}
              {hasRedacted && (
                <section className="access-inspector__section">
                  {hasRedactedEntries ? (
                    (manifest.redacted_entries ?? []).map((entry, idx) => (
                      <div key={`redacted-${String(idx)}`} className="access-inspector__row access-inspector__row--redacted">
                        <span className="access-inspector__redacted-label">
                          {formatRedactedLabel(manifest.redacted_count, entry.label)} - outside your visibility boundary
                        </span>
                      </div>
                    ))
                  ) : (
                    <div className="access-inspector__row access-inspector__row--redacted">
                      <span className="access-inspector__redacted-label">
                        {formatRedactedLabel(manifest.redacted_count)} - outside your visibility boundary
                      </span>
                    </div>
                  )}
                </section>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
