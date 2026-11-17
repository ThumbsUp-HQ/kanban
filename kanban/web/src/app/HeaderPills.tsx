/**
 * Topbar Semantic Header Emoji Pills (KB-P3-34, S6.2).
 * Renders Warning, Air-Gap, and Access EmojiHints with full hover elaboration.
 */

import React, { useState, type JSX } from 'react';
import { useQuery } from '@tanstack/react-query';
import { EmojiHint } from '../components/emoji/EmojiHint';
import { qk } from '../api/queryKeys';
import { useSystemStatus, type SystemStatus } from './useSystemStatus';
import { useShellPanels } from './shellPanels';

export interface AccessManifestData {
  pill_label?: string;
  explicit_grant_count?: number;
  inherited_scope?: {
    kind?: string;
    scope_label?: string;
    workspace_name?: string;
    project_key?: string | null;
    project_name?: string | null;
    project_id?: string | null;
  };
  users?: unknown[];
  groups?: unknown[];
  agents?: unknown[];
  deny_overrides?: unknown[];
  redacted_count?: number;
}

export interface HeaderPillsProps {
  systemStatus?: SystemStatus | null | undefined;
  accessManifest?: AccessManifestData | null | undefined;
  projectId?: string | undefined;
  projectName?: string | undefined;
}

export const STANDALONE_DISMISS_KEY = 'kb_dismiss_standalone_warning';

export function HeaderPills({
  systemStatus: statusOverride,
  accessManifest: accessOverride,
  projectId,
  projectName,
}: HeaderPillsProps): JSX.Element {
  const { openPanel } = useShellPanels();
  const queryStatus = useSystemStatus();
  const status = statusOverride !== undefined ? statusOverride : queryStatus.data;

  const [isDismissed, setIsDismissed] = useState<boolean>(() => {
    try {
      return typeof sessionStorage !== 'undefined' && sessionStorage.getItem(STANDALONE_DISMISS_KEY) === 'true';
    } catch {
      return false;
    }
  });

  const handleDismissStandalone = (e: React.MouseEvent<HTMLButtonElement>): void => {
    e.stopPropagation();
    setIsDismissed(true);
    try {
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.setItem(STANDALONE_DISMISS_KEY, 'true');
      }
    } catch {
      // Ignore storage errors
    }
  };

  const accessQuery = useQuery({
    queryKey: qk.access(projectId ?? 'current'),
    queryFn: async ({ signal }) => {
      const res = await fetch(`/api/v1/objects/${projectId ?? 'project'}/access`, {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
        signal,
      });
      if (!res.ok) {
        return null;
      }
      return (await res.json()) as AccessManifestData;
    },
    enabled: accessOverride === undefined && Boolean(projectId),
    staleTime: 60000,
  });

  const manifest = accessOverride !== undefined ? accessOverride : accessQuery.data;

  const isStandalone =
    status?.deployment_mode === 'standalone_embedded_pg' ||
    status?.deployment_mode === 'standalone';

  const showStorageWarning = isStandalone && !status.persistent_volume && !isDismissed;

  const isAirGap = status?.air_gap_mode === true;

  const usersCount = manifest?.users?.length ?? 0;
  const groupsCount = manifest?.groups?.length ?? 0;
  const agentsCount = manifest?.agents?.length ?? 0;
  const denyCount = manifest?.deny_overrides?.length ?? 0;
  const redactedCount = manifest?.redacted_count ?? 0;

  const usersStr = String(usersCount);
  const groupsStr = String(groupsCount);
  const agentsStr = String(agentsCount);
  const denyStr = String(denyCount);
  const redactedStr = String(redactedCount);

  const resolvedProjectName =
    projectName ??
    manifest?.inherited_scope?.project_name ??
    'Platform Core';

  const scopeLabel =
    manifest?.pill_label ??
    manifest?.inherited_scope?.scope_label ??
    'Project';

  return (
    <div className="kb-header-pills">
      {/* 1. Standalone warning pill (ephemeral storage only) */}
      {showStorageWarning && (
        <span className="kb-standalone-pill-group">
          <EmojiHint
            kind="warning"
            variant="interactive"
            label="Standalone mode warning"
            activateLabel="Open standalone status"
            onAction={() => { openPanel('standalone'); }}
            onActivate={() => { openPanel('standalone'); }}
            content={
              <div className="kb-pill-content">
                <div>
                  Standalone Single-Container Mode (Not Recommended for Production) - Click for volume status, encrypted backup, & 1-click docker-compose.yml export
                </div>
                <div>
                  Ephemeral Storage: Mount -v kanban_data:/var/lib/kanban/data to persist data across container removal
                </div>
              </div>
            }
          />
          <button
            type="button"
            className="kb-pill-dismiss-btn"
            aria-label="Dismiss standalone warning"
            data-testid="standalone-dismiss-btn"
            onClick={handleDismissStandalone}
          >
            ✕
          </button>
        </span>
      )}

      {/* 2. Air-gap mode pill */}
      {isAirGap && (
        <EmojiHint
          kind="airGap"
          variant="tooltip"
          label="Air-gap local-only mode"
          content={
            <div className="kb-pill-content">
              <div>
                Air-Gap Local-Only Mode: external LLM and media egress are disabled at the socket level.
              </div>
              <div>
                Local model endpoint:{' '}
                {status.local_llm_endpoint_host ?? 'visible to server admins only'}
              </div>
            </div>
          }
        />
      )}

      {/* 3. Access transparency pill */}
      {manifest && (
        <EmojiHint
          kind="access"
          variant="interactive"
          label={`Access: ${scopeLabel}`}
          activateLabel="Open Access Inspector"
          onActivate={() => { openPanel('access', projectId); }}
          content={
            <div className="kb-pill-content">
              <div>Project: {resolvedProjectName}</div>
              <div>
                {`${usersStr} users, ${groupsStr} groups, ${agentsStr} 🤖 agents, ${denyStr} 🔒 deny rules`}
              </div>
              {redactedCount > 0 && (
                <div>{`${redactedStr} external collaborator(s)`}</div>
              )}
            </div>
          }
        />
      )}
    </div>
  );
}
