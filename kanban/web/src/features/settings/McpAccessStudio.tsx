// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useCallback, useContext, type JSX } from 'react';
import { useParams, useSearchParams, Link } from 'react-router';
import { useQuery, QueryClient, QueryClientContext } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import {
  fetchConnectedApps,
  revokeConnectedApp,
  fetchUnifiedMcpKeys,
  mintUnifiedMcpKey,
  revokeUnifiedMcpKey,
  type McpApiKeyItem,
  type OAuthConnectedApp,
  type ScopeTier,
  type OwnerKind,
  type MintMcpKeyRequest,
} from './settingsApi';
import { McpConfigSnippetModal } from './McpConfigSnippetModal';
import { ConnectOAuthAppModal } from './ConnectOAuthAppModal';
import { WorkloadFederationSection } from './McpUnifiedStudio';
import { SecondFactorStep } from '../auth/SecondFactorStep';
import type { MfaMethod } from '../auth/authApi';
import { ApiProblem } from '../../api/problem';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { useSystemStatus } from '../../app/useSystemStatus';
import { apiFetch } from '../../api/client';
import { NotFoundView } from '../../app/routes';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { AdminStudioSubnav } from '../admin/AdminStudioSubnav';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { AdvancedSection } from '../../ui/AdvancedSection';
import { copyToClipboard } from '../../utils/clipboard';
import './McpConfigSnippetModal.css';
import './McpAccessStudio.css';

export const SURFACE_TOOLS: Record<'agent' | 'docs' | 'admin', readonly string[]> = {
  agent: [
    'ping_agent',
    'search_tickets',
    'read_ticket',
    'create_ticket',
    'update_ticket',
    'begin_work',
    'transition_ticket',
    'complete_work',
    'add_comment',
    'link_objects',
  ],
  docs: [
    'ping_docs',
    'search_docs',
    'search_knowledge',
    'read_doc',
    'create_doc',
    'update_doc',
    'upsert_doc',
    'manage_stickies',
    'promote_sticky_to_doc',
    'link_knowledge',
  ],
  admin: [
    'manage_principals_and_groups',
    'manage_access_policies',
    'audit_links',
    'override_ticket_provenance',
    'audit_and_purge_object_links',
    'manage_ai_and_agent_runners',
    'destructive_lifecycle',
  ],
};

export const WRITE_MCP_TOOLS = new Set([
  'create_ticket',
  'update_ticket',
  'begin_work',
  'transition_ticket',
  'complete_work',
  'link_objects',
  'create_doc',
  'update_doc',
  'upsert_doc',
  'manage_stickies',
  'promote_sticky_to_doc',
  'link_knowledge',
  'manage_principals_and_groups',
  'manage_access_policies',
  'audit_links',
  'override_ticket_provenance',
  'audit_and_purge_object_links',
  'manage_ai_and_agent_runners',
  'destructive_lifecycle',
]);

export const CAPABILITY_BITS = [
  { bit: 1, name: 'VIEW', label: 'View (1)' },
  { bit: 2, name: 'COMMENT', label: 'Comment (2)' },
  { bit: 4, name: 'EDIT', label: 'Edit (4)' },
  { bit: 8, name: 'TRANSITION', label: 'Transition (8)' },
  { bit: 16, name: 'LINK', label: 'Link (16)' },
  { bit: 32, name: 'SHARE', label: 'Share (32)' },
  { bit: 64, name: 'ADMIN', label: 'Admin (64)' },
  { bit: 128, name: 'DELETE', label: 'Delete (128)' },
] as const;

function isValidIPv4Cidr(cidr: string): boolean {
  const parts = cidr.split('/');
  if (parts.length !== 2) return false;
  const ip = parts[0];
  const prefixStr = parts[1];
  if (!ip || !prefixStr || !/^\d+$/.test(prefixStr)) return false;
  const prefix = Number(prefixStr);
  if (prefix < 0 || prefix > 32) return false;
  const octets = ip.split('.');
  if (octets.length !== 4) return false;
  for (const oct of octets) {
    if (!/^\d+$/.test(oct)) return false;
    const n = Number(oct);
    if (n < 0 || n > 255) return false;
    if (oct.length > 1 && oct.startsWith('0')) return false;
  }
  return true;
}

function isValidIPv6Cidr(cidr: string): boolean {
  const parts = cidr.split('/');
  if (parts.length !== 2) return false;
  const ip = parts[0];
  const prefixStr = parts[1];
  if (!ip || !prefixStr || !/^\d+$/.test(prefixStr)) return false;
  const prefix = Number(prefixStr);
  if (prefix < 0 || prefix > 128) return false;
  if (!/^[0-9a-fA-F:]+$/.test(ip)) return false;
  if (ip.includes(':::')) return false;
  const doubleColonCount = (ip.match(/::/g) ?? []).length;
  if (doubleColonCount > 1) return false;
  const groups = ip.split(':');
  if (doubleColonCount === 0 && groups.length !== 8) return false;
  if (doubleColonCount === 1 && groups.length > 8) return false;
  for (const g of groups) {
    if (g.length > 4) return false;
    if (g.length > 0 && !/^[0-9a-fA-F]{1,4}$/.test(g)) return false;
  }
  return true;
}

export function validateCidrInput(rawInput: string): { valid: boolean; cidrs: string[]; error?: string } {
  const trimmed = rawInput.trim();
  if (!trimmed) {
    return { valid: true, cidrs: [] };
  }
  const parts = trimmed.split(/[\s,]+/).filter(Boolean);
  for (const part of parts) {
    if (!isValidIPv4Cidr(part) && !isValidIPv6Cidr(part)) {
      return {
        valid: false,
        cidrs: [],
        error: `Invalid CIDR format: "${part}". Must be valid IPv4 (e.g. 192.168.1.0/24) or IPv6 (e.g. 2001:db8::/32).`,
      };
    }
  }
  return { valid: true, cidrs: parts };
}

export function getCapabilityPresetName(mask: number): string {
  switch (mask) {
    case 1:
      return 'Read-Only Agent';
    case 3:
      return 'View + Comment';
    case 31:
      return 'Standard Developer Agent';
    case 255:
      return 'Full Project Agent';
    default:
      return `Custom (${String(mask)})`;
  }
}

export function formatMintKeySummary({
  label,
  ownerKind,
  scopeTier,
  project,
  surface,
  capabilityMask,
}: {
  label: string;
  ownerKind: OwnerKind;
  scopeTier: ScopeTier;
  project?: string | null | undefined;
  surface: 'agent' | 'docs' | 'admin';
  capabilityMask: number;
}): string {
  const trimmedLabel = label.trim();
  const displayLabel = trimmedLabel.length > 0 ? trimmedLabel : 'Untitled';
  const displayOwner = ownerKind === 'service_bot' ? 'Service Bot' : 'Personal User';
  let displayScope = 'This Workspace';
  if (scopeTier === 'project') {
    const trimmedProj = project?.trim();
    const proj = trimmedProj && trimmedProj.length > 0 ? trimmedProj : '(None)';
    displayScope = `Project ${proj}`;
  } else if (scopeTier === 'global') {
    displayScope = 'Entire Server';
  }
  const displaySurface = surface === 'agent' ? 'Agent' : surface === 'docs' ? 'Docs' : 'Admin';
  const displayPreset = getCapabilityPresetName(capabilityMask);

  return `Key "${displayLabel}" for ${displayOwner} can access ${displayScope} and use ${displaySurface} tools (${displayPreset}).`;
}

export type ActiveScopeFilter = 'all' | 'project' | 'workspace' | 'server';
export type ActiveView = 'mine' | 'governance';

export interface McpAccessStudioProps {
  tier?: ('personal' | 'project' | 'workspace' | 'global') | undefined;
  allowUnlimitedKeys?: boolean | undefined;
  user?: {
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
    is_project_admin?: boolean;
    workspace_role?: string;
  } | null | undefined;
}

interface ProjectOption {
  id: string;
  identifier: string;
  name: string;
}

const fallbackQueryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

export function McpAccessStudio({
  tier,
  allowUnlimitedKeys,
  user: propUser,
}: McpAccessStudioProps): JSX.Element {
  const contextClient = useContext(QueryClientContext);
  const queryClient = contextClient ?? fallbackQueryClient;

  const [searchParams, setSearchParams] = useSearchParams();
  const routeParams = useParams<{ projectKey?: string; workspaceSlug?: string }>();

  // Determine initial scope filter from props or query
  const queryScope = searchParams.get('scope');
  const queryProject = searchParams.get('project');
  const queryView = searchParams.get('view');

  const resolvedInitialScope: ActiveScopeFilter = (() => {
    if (tier === 'global') return 'server';
    if (tier === 'workspace') return 'workspace';
    if (tier === 'project') return 'project';
    if (queryScope === 'server' || queryScope === 'global') return 'server';
    if (queryScope === 'workspace') return 'workspace';
    if (queryScope === 'project') return 'project';
    return 'all';
  })();

  const [activeScope, setActiveScope] = useState<ActiveScopeFilter>(resolvedInitialScope);
  const [selectedProject, setSelectedProject] = useState<string | null>(
    queryProject ?? routeParams.projectKey ?? null,
  );
  const [activeView, setActiveView] = useState<ActiveView>(
    queryView === 'governance' ? 'governance' : 'mine',
  );

  const [fetchedUser, setFetchedUser] = useState<{
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
    is_project_admin?: boolean;
    workspace_role?: string;
  } | null>(null);

  useEffect(() => {
    if (propUser !== undefined) return;
    const isMounted = { current: true };
    void (async () => {
      try {
        const u = (await apiFetch('GET', '/api/v1/auth/me')) as {
          is_server_admin?: boolean;
          is_workspace_admin?: boolean;
          is_project_admin?: boolean;
          workspace_role?: string;
        };
        if (isMounted.current) setFetchedUser(u);
      } catch {
        // Unmocked in unit test
      }
    })();
    return () => {
      isMounted.current = false;
    };
  }, [propUser]);

  const currentUser = propUser ?? fetchedUser;
  const isServerAdmin = currentUser?.is_server_admin === true;
  const isWorkspaceAdmin = currentUser?.is_workspace_admin === true || isServerAdmin;
  const isProjectAdmin = currentUser?.is_project_admin === true || isWorkspaceAdmin;
  const canAccessGovernance = isServerAdmin || isWorkspaceAdmin || isProjectAdmin;
  const isViewer =
    currentUser?.workspace_role === 'VIEWER' || currentUser?.workspace_role === 'WORKSPACE_GUEST';

  const isDenied =
    currentUser !== null &&
    ((tier === 'global' && !isServerAdmin) || (tier === 'workspace' && !isWorkspaceAdmin));

  const projectsQuery = useQuery<ProjectOption[]>(
    {
      queryKey: qk.projects(),
      queryFn: async () => {
        try {
          const res = await apiFetch('GET', '/api/v1/projects');
          const data = res as unknown as
            | { items?: { id: string; identifier?: string; key?: string; name?: string }[] }
            | { id: string; identifier?: string; key?: string; name?: string }[];
          const rawList = Array.isArray(data) ? data : (data.items ?? []);
          return rawList.map((p) => {
            const ident = p.identifier ?? p.key ?? '';
            return {
              id: p.id,
              identifier: ident,
              name: p.name ?? ident,
            };
          });
        } catch {
          return [];
        }
      },
      staleTime: 30000,
      enabled: !isDenied,
    },
    queryClient,
  );

  const workspacesQuery = useQuery<{ id: string; name: string; slug: string; is_current?: boolean }[]>(
    {
      queryKey: ['workspaces'],
      queryFn: async () => {
        try {
          const res = await apiFetch('GET', '/api/v1/workspaces');
          return Array.isArray(res) ? res : [];
        } catch {
          return [];
        }
      },
      staleTime: 60000,
      enabled: !isDenied,
    },
    queryClient,
  );

  const currentWorkspaceSlug =
    routeParams.workspaceSlug ??
    (/^\/w\/([^/]+)/.exec(typeof window !== 'undefined' ? window.location.pathname : '')?.[1]) ??
    workspacesQuery.data?.find((w) => w.is_current)?.slug ??
    workspacesQuery.data?.[0]?.slug ??
    'kanban';

  const systemStatusQuery = useSystemStatus();
  const allowUnlimited =
    allowUnlimitedKeys ?? systemStatusQuery.data?.allow_unlimited_mcp_keys ?? true;

  const [keys, setKeys] = useState<McpApiKeyItem[]>([]);

  const projects = React.useMemo<ProjectOption[]>(() => {
    if (projectsQuery.data && projectsQuery.data.length > 0) {
      return projectsQuery.data;
    }
    const fromKeys = Array.from(
      new Set(
        keys
          .flatMap((k) => k.allowed_projects ?? [])
          .filter((p): p is string => Boolean(p.trim())),
      ),
    );
    return fromKeys.map((p) => ({
      id: p,
      identifier: p,
      name: p,
    }));
  }, [projectsQuery.data, keys]);

  const effectiveProjectKey =
    selectedProject ??
    queryProject ??
    routeParams.projectKey ??
    projects[0]?.identifier ??
    '';
  const [connectedApps, setConnectedApps] = useState<OAuthConnectedApp[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [showConnectOAuthModal, setShowConnectOAuthModal] = useState<boolean>(false);

  // Mint modal state
  const [showMintModal, setShowMintModal] = useState<boolean>(false);
  const [newKeyLabel, setNewKeyLabel] = useState<string>('');
  const [newKeySurface, setNewKeySurface] = useState<'agent' | 'docs' | 'admin'>('agent');
  const [newKeyOwnerKind, setNewKeyOwnerKind] = useState<OwnerKind>('personal_user');
  const [newKeyScopeTier, setNewKeyScopeTier] = useState<ScopeTier>(
    activeScope === 'server' ? 'global' : activeScope === 'project' ? 'project' : 'workspace',
  );
  const [newKeyProject, setNewKeyProject] = useState<string>(effectiveProjectKey);
  const [newKeyExpiry, setNewKeyExpiry] = useState<number>(60);
  const [isUnlimited, setIsUnlimited] = useState<boolean>(false);
  const [confirmUnlimited, setConfirmUnlimited] = useState<boolean>(false);
  const [disabledTools, setDisabledTools] = useState<string[]>([]);
  const [capabilityMask, setCapabilityMask] = useState<number>(31);
  const [allowedCidrsInput, setAllowedCidrsInput] = useState<string>('');
  const [cidrError, setCidrError] = useState<string | null>(null);
  const [minting, setMinting] = useState<boolean>(false);
  const [mintError, setMintError] = useState<string | null>(null);
  const [studioError, setStudioError] = useState<string | null>(null);

  // Snippet modal state (ephemeral secret)
  const [activeSnippetKey, setActiveSnippetKey] = useState<string | undefined>(undefined);
  const [showSnippetModal, setShowSnippetModal] = useState<boolean>(false);

  // 2-step inline revocation confirmation states
  const [confirmRevokeKeyId, setConfirmRevokeKeyId] = useState<string | null>(null);
  const [confirmRevokeAppId, setConfirmRevokeAppId] = useState<string | null>(null);

  // Inline AAL2 challenge state
  const [aal2Challenge, setAal2Challenge] = useState<{
    challengeId: string;
    methods: MfaMethod[];
  } | null>(null);
  const [pendingAction, setPendingAction] = useState<(() => Promise<void>) | null>(null);

  const loadData = useCallback(async (): Promise<void> => {
    if (isDenied) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      if (activeView === 'governance') {
        const fetched = await fetchUnifiedMcpKeys({
          view: 'governance',
          scope_tier: activeScope !== 'all' ? activeScope : undefined,
          project_ref: activeScope === 'project' ? effectiveProjectKey : undefined,
        });
        setKeys(fetched);
        setConnectedApps([]);
      } else {
        const [fetchedKeys, fetchedApps] = await Promise.all([
          fetchUnifiedMcpKeys({
            view: 'mine',
            scope_tier: tier === 'global' ? 'global' : activeScope !== 'all' ? activeScope : undefined,
            project_ref: activeScope === 'project' ? effectiveProjectKey : undefined,
          }),
          fetchConnectedApps(),
        ]);
        setKeys(fetchedKeys);
        setConnectedApps(fetchedApps);
      }
    } catch (err: unknown) {
      if (err instanceof ApiProblem && (err.code === 'AAL2_REQUIRED' || err.code === 'AAL2_STALE')) {
        const data = err.data;
        const challengeId = typeof data.challenge_id === 'string' ? data.challenge_id : 'aal2-stepup';
        const methods = Array.isArray(data.methods)
          ? (data.methods as MfaMethod[])
          : (['webauthn', 'totp'] as MfaMethod[]);
        setAal2Challenge({ challengeId, methods });
        setPendingAction(() => async () => {
          await loadData();
        });
      }
    } finally {
      setLoading(false);
    }
  }, [activeView, activeScope, effectiveProjectKey, tier, isDenied]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleScopeFilterChange = (newScope: ActiveScopeFilter): void => {
    setActiveScope(newScope);
    setSearchParams((prev) => {
      const updated = new URLSearchParams(prev);
      if (newScope === 'all') {
        updated.delete('scope');
      } else {
        updated.set('scope', newScope);
      }
      return updated;
    });
  };

  const handleProjectSelectChange = (newProject: string): void => {
    setSelectedProject(newProject);
    setSearchParams((prev) => {
      const updated = new URLSearchParams(prev);
      updated.set('project', newProject);
      return updated;
    });
  };

  const handleViewToggle = (newView: ActiveView): void => {
    setActiveView(newView);
    setSearchParams((prev) => {
      const updated = new URLSearchParams(prev);
      if (newView === 'governance') {
        updated.set('view', 'governance');
      } else {
        updated.delete('view');
      }
      return updated;
    });
  };

  const handleOpenMintModal = (): void => {
    let initialTier: ScopeTier = 'workspace';
    let initialOwner: OwnerKind = 'personal_user';
    if (activeScope === 'server' || tier === 'global') {
      initialTier = 'global';
      initialOwner = 'service_bot';
    } else if (activeScope === 'project' || tier === 'project') {
      initialTier = 'project';
      initialOwner = 'personal_user';
    } else if (activeScope === 'workspace' || tier === 'workspace') {
      initialTier = 'workspace';
      initialOwner = 'personal_user';
    } else {
      initialTier = 'workspace';
      initialOwner = 'personal_user';
    }
    setNewKeyOwnerKind(initialOwner);
    setNewKeyScopeTier(initialTier);
    setNewKeyProject(effectiveProjectKey);
    setCapabilityMask(31);
    setShowMintModal(true);
  };

  const handleMintSubmit = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();
    if (!newKeyLabel.trim()) {
      return;
    }
    if (isUnlimited && !confirmUnlimited) {
      return;
    }
    setMinting(true);
    setMintError(null);

    const mintAction = async (): Promise<void> => {
      const parsedCidrs = validateCidrInput(allowedCidrsInput);
      if (!parsedCidrs.valid) {
        setMintError(parsedCidrs.error ?? 'Invalid CIDR format.');
        return;
      }

      const resolvedScopeTier: ScopeTier =
        tier === 'global'
          ? 'global'
          : tier === 'project'
          ? 'project'
          : newKeyScopeTier === 'global'
          ? 'global'
          : newKeyScopeTier === 'project'
          ? 'project'
          : 'workspace';

      const targetProject = newKeyProject.trim() || effectiveProjectKey;

      const payload: MintMcpKeyRequest = {
        label: newKeyLabel.trim(),
        surface: newKeySurface,
        scopes:
          capabilityMask === 1
            ? [`${newKeySurface}:read`]
            : [`${newKeySurface}:read`, `${newKeySurface}:write`],
        scope_tier: resolvedScopeTier,
        owner_kind: newKeyOwnerKind,
        capability_mask: capabilityMask,
        ...(parsedCidrs.cidrs.length > 0 ? { allowed_cidrs: parsedCidrs.cidrs } : {}),
        ...(resolvedScopeTier === 'project'
          ? {
              project_ref: targetProject,
              allowed_projects: targetProject ? [targetProject] : undefined,
            }
          : {}),
        ...(isUnlimited
          ? { unlimited: true, confirm_unlimited: confirmUnlimited }
          : { expires_in_days: newKeyExpiry }),
        ...(disabledTools.length > 0 ? { disabled_tools: disabledTools } : {}),
      };

      const minted = await mintUnifiedMcpKey(payload);

      await queryClient.invalidateQueries({ queryKey: ['mcp-keys'] });
      await queryClient.invalidateQueries({ queryKey: qk.projects() });

      setKeys((prev) => [minted, ...prev.filter((k) => k.id !== minted.id)]);
      setActiveSnippetKey(minted.raw_key);
      setShowMintModal(false);
      setShowSnippetModal(true);
      setNewKeyLabel('');
      setIsUnlimited(false);
      setConfirmUnlimited(false);
      setDisabledTools([]);
      setNewKeyExpiry(60);
      setCapabilityMask(31);
      setAllowedCidrsInput('');
      setCidrError(null);
      setMintError(null);
    };

    try {
      await mintAction();
    } catch (err: unknown) {
      if (err instanceof ApiProblem && (err.code === 'AAL2_REQUIRED' || err.code === 'AAL2_STALE')) {
        const data = err.data;
        const challengeId = typeof data.challenge_id === 'string' ? data.challenge_id : 'aal2-stepup';
        const methods = Array.isArray(data.methods)
          ? (data.methods as MfaMethod[])
          : (['webauthn', 'totp'] as MfaMethod[]);
        setAal2Challenge({ challengeId, methods });
        setPendingAction(() => async () => {
          await mintAction();
        });
        return;
      }
      if (err instanceof Error) {
        setMintError(err.message);
      } else {
        setMintError('Failed to mint MCP key.');
      }
    } finally {
      setMinting(false);
    }
  };

  const handleConfirmRevokeKey = async (keyId: string): Promise<void> => {
    setStudioError(null);
    const revokeAction = async (): Promise<void> => {
      await revokeUnifiedMcpKey(keyId);
      setKeys((prev) =>
        prev.map((k) => (k.id === keyId ? { ...k, revoked_at: new Date().toISOString() } : k)),
      );
    };

    try {
      await revokeAction();
    } catch (err: unknown) {
      if (err instanceof ApiProblem && (err.code === 'AAL2_REQUIRED' || err.code === 'AAL2_STALE')) {
        const data = err.data;
        const challengeId = typeof data.challenge_id === 'string' ? data.challenge_id : 'aal2-stepup';
        const methods = Array.isArray(data.methods)
          ? (data.methods as MfaMethod[])
          : (['webauthn', 'totp'] as MfaMethod[]);
        setAal2Challenge({ challengeId, methods });
        setPendingAction(() => async () => {
          await revokeAction();
        });
        return;
      }
      if (err instanceof Error) {
        setStudioError(err.message);
      } else {
        setStudioError('Failed to revoke MCP key.');
      }
    } finally {
      setConfirmRevokeKeyId(null);
    }
  };

  const handleConfirmRevokeApp = async (grantId: string): Promise<void> => {
    try {
      await revokeConnectedApp(grantId);
      setConnectedApps((prev) => prev.filter((app) => app.id !== grantId));
    } catch {
      // Handle error
    } finally {
      setConfirmRevokeAppId(null);
    }
  };

  const handleAal2Success = async (): Promise<void> => {
    const action = pendingAction;
    setAal2Challenge(null);
    setPendingAction(null);
    if (action) {
      await action();
    }
  };

  const getTierBadge = (
    keyTier: ScopeTier,
    allowedProjects?: string[] | null,
  ): JSX.Element => {
    if (keyTier === 'global') {
      return (
        <span className="kb-mcp-tier-badge kb-mcp-tier-global" data-testid="tier-badge-global">
          <EmojiHint kind="access" /> Global
        </span>
      );
    }
    if (keyTier === 'workspace') {
      return (
        <span className="kb-mcp-tier-badge kb-mcp-tier-workspace" data-testid="tier-badge-workspace">
          <EmojiHint kind="access" /> Workspace: {currentWorkspaceSlug}
        </span>
      );
    }
    if (keyTier === 'project') {
      const projLabel =
        allowedProjects && allowedProjects.length > 0
          ? allowedProjects.join(', ')
          : effectiveProjectKey;
      return (
        <span className="kb-mcp-tier-badge kb-mcp-tier-project" data-testid="tier-badge-project">
          <EmojiHint kind="access" /> Project: {projLabel}
        </span>
      );
    }
    return (
      <span className="kb-mcp-tier-badge kb-mcp-tier-personal" data-testid="tier-badge-personal">
        <EmojiHint kind="access" /> Personal
      </span>
    );
  };

  const titleForTier: Record<string, string> = {
    personal: 'Personal MCP Keys & Connected Apps',
    project: `Project (${effectiveProjectKey}) MCP Bot Keys`,
    workspace: 'Workspace MCP Bot Keys & Client Approvals',
    global: 'Global Cross-Workspace Bot Keys (meatloaf-bot)',
  };

  const displayedTitle =
    activeView === 'governance'
      ? 'MCP Key Governance (All Scoped Keys)'
      : (tier ? titleForTier[tier] : 'Personal MCP Keys & Connected Apps');

  // Filter keys for display based on activeScope when in 'mine' view
  const displayedKeys = keys.filter((k) => {
    if (activeView === 'governance') return true;
    if (activeScope === 'all') return true;
    if (activeScope === 'project') {
      if (k.scope_tier !== 'project') return false;
      if (effectiveProjectKey && k.allowed_projects && k.allowed_projects.length > 0) {
        return k.allowed_projects.includes(effectiveProjectKey);
      }
      return true;
    }
    if (activeScope === 'workspace') {
      return k.scope_tier === 'workspace';
    }
    return k.scope_tier === 'global';
  });

  if (currentUser !== null) {
    if (tier === 'global' && !isServerAdmin) {
      return <NotFoundView />;
    }
    if (tier === 'workspace' && !isWorkspaceAdmin) {
      return <NotFoundView />;
    }
  }

  return (
    <div className="kb-mcp-studio-container" data-testid="mcp-access-studio">
      <header className="kb-mcp-studio-header">
        <div>
          <h1 className="kb-mcp-studio-title" data-testid="studio-title">{displayedTitle}</h1>
          <p className="kb-mcp-studio-subtitle">
            Mint and manage Model Context Protocol API keys with explicit scope tiers and one-click revocation.
          </p>
        </div>
        <div className="kb-mcp-header-actions">
          <StudioDocLink
            href="/docs/three-surface-mcp-server-architecture"
            title="MCP Architecture & Tool Reference"
            testId="mcp-studio-doc-link"
          />
          <button
            type="button"
            className="kb-mcp-studio-mint-btn"
            data-testid="mint-key-button"
            onClick={handleOpenMintModal}
          >
            + Mint MCP Key
          </button>
        </div>
      </header>

      {studioError && (
        <div className="kb-mcp-mint-error kb-mcp-mint-error--banner" role="alert" data-testid="studio-error-banner">
          {studioError}
        </div>
      )}

      {/* Admin subnav for global tier */}
      {tier === 'global' && (
        <AdminStudioSubnav activeTab="mcp" isServerAdmin={isServerAdmin} />
      )}

      {/* Admin View Switch (My Keys vs Governance) */}
      {canAccessGovernance && (
        <div className="kb-mcp-view-toggle" data-testid="admin-view-toggle">
          <button
            type="button"
            className={`kb-mcp-view-btn ${activeView === 'mine' ? 'kb-mcp-view-btn-active' : ''}`}
            data-testid="view-mine-btn"
            onClick={() => {
              handleViewToggle('mine');
            }}
          >
            My Keys & Connected Apps
          </button>
          <button
            type="button"
            className={`kb-mcp-view-btn ${activeView === 'governance' ? 'kb-mcp-view-btn-active' : ''}`}
            data-testid="view-governance-btn"
            onClick={() => {
              handleViewToggle('governance');
            }}
          >
            Governance (All Scoped Keys)
          </button>
        </div>
      )}

      {/* Explanatory Architecture Card */}
      <div className="kb-mcp-explainer-card" data-testid="mcp-scope-explainer">
        <div className="kb-mcp-explainer-item">
          <strong>Personal Keys vs Service Bot Keys:</strong> Personal keys act on your behalf across permitted surfaces, while Service Bot keys provide dedicated automation identities tied to project, workspace, or server scopes.
        </div>
        <div className="kb-mcp-explainer-item">
          <strong>Scope Tiers:</strong> Project keys are confined to tickets and docs in designated projects. Workspace keys cover all projects in this workspace. Server keys have system-wide privileges for administrative orchestration.
        </div>
        <div className="kb-mcp-explainer-item" data-testid="mcp-credential-boundary-explainer">
          <strong>Monotonic Credential Boundary:</strong> Keys enforce downward capability narrowing via capability ceilings and allowed source CIDRs without privilege escalation. PostgreSQL FORCE RLS guarantees access constraints are enforced equally across /mcp/* and /api/v1/*.
        </div>
      </div>

      {/* Recommended Agent Skills & Onboarding Callout */}
      <div className="kb-mcp-llms-callout" data-testid="mcp-llms-txt-callout">
        <div className="kb-mcp-llms-callout-text">
          <span aria-hidden="true">🤖</span>{' '}
          <strong>Agent Onboarding &amp; Recommended Skills:</strong> Point your agent to{' '}
          <a href="/llms.txt" target="_blank" rel="noopener noreferrer">/llms.txt</a>{' '}
          to learn 👍kanban's ticket authoring rules, 3-surface MCP architecture, and start the 4-axis configuration interview.
        </div>
        <button
          type="button"
          className="kb-mcp-copy-prompt-btn"
          data-testid="mcp-copy-llms-prompt-btn"
          onClick={() => {
            const origin = typeof window !== 'undefined' ? window.location.origin : 'https://kanban.example.com';
            void copyToClipboard(
              `Read ${origin}/llms.txt, learn 👍kanban's ticket workflow, interview me on Execution Mode (Single-Thread, Teamwork, or Swarm), Model/Quota Strategy (Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra), and QA Rigor, and save my preferences to .agents/skills/ and AGENTS.md.`
            );
          }}
        >
          Copy Agent Skill Prompt
        </button>
      </div>

      {/* Scope Filter Pills & Project Selector */}
      <div className="kb-mcp-filter-bar" data-testid="mcp-filter-bar">
        <div className="kb-mcp-pills-group" data-testid="mcp-pills-group">
          <button
            type="button"
            className={`kb-mcp-filter-pill ${activeScope === 'all' ? 'kb-mcp-filter-pill-active' : ''}`}
            data-testid="scope-pill-all"
            onClick={() => {
              handleScopeFilterChange('all');
            }}
          >
            All
          </button>
          <button
            type="button"
            className={`kb-mcp-filter-pill ${activeScope === 'project' ? 'kb-mcp-filter-pill-active' : ''}`}
            data-testid="scope-pill-project"
            onClick={() => {
              handleScopeFilterChange('project');
            }}
          >
            Project
          </button>
          <button
            type="button"
            className={`kb-mcp-filter-pill ${activeScope === 'workspace' ? 'kb-mcp-filter-pill-active' : ''}`}
            data-testid="scope-pill-workspace"
            onClick={() => {
              handleScopeFilterChange('workspace');
            }}
          >
            Workspace
          </button>
          <button
            type="button"
            className={`kb-mcp-filter-pill ${activeScope === 'server' ? 'kb-mcp-filter-pill-active' : ''}`}
            data-testid="scope-pill-server"
            onClick={() => {
              handleScopeFilterChange('server');
            }}
          >
            Server
          </button>
        </div>

        {activeScope === 'project' && (
          <div className="kb-mcp-project-selector" data-testid="scope-project-container">
            <label htmlFor="scope-project-select">Target Project:</label>
            <select
              id="scope-project-select"
              className="kb-mcp-form-select"
              data-testid="scope-project-select"
              value={effectiveProjectKey}
              onChange={(e) => {
                handleProjectSelectChange(e.target.value);
              }}
            >
              {projects.map((p) => (
                <option key={p.id} value={p.identifier}>
                  {p.name && p.name !== p.identifier ? `${p.identifier} - ${p.name}` : p.identifier}
                </option>
              ))}
              {effectiveProjectKey && !projects.some((p) => p.identifier === effectiveProjectKey) && (
                <option value={effectiveProjectKey}>{effectiveProjectKey}</option>
              )}
            </select>
          </div>
        )}
      </div>

      {/* MCP Keys Table Section */}
      <section className="kb-mcp-studio-section" data-testid="mcp-keys-section">
        <h2 className="kb-mcp-section-title">
          <EmojiHint kind="agent" /> {activeView === 'governance' ? 'Governance Scoped Keys' : 'Active MCP Keys'}
        </h2>
        <div className="kb-mcp-table-wrap">
          <table className="kb-mcp-table" data-testid="mcp-keys-table">
            <thead>
              <tr>
                <th className="kb-mcp-th">Label</th>
                <th className="kb-mcp-th">Key Hint</th>
                <th className="kb-mcp-th">Scope Tier</th>
                <th className="kb-mcp-th">Surface</th>
                <th className="kb-mcp-th">Expires</th>
                <th className="kb-mcp-th">Status</th>
                <th className="kb-mcp-th">Actions</th>
              </tr>
            </thead>
            <tbody>
              {displayedKeys.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="kb-mcp-empty-state">
                    No active MCP keys configured. Click "+ Mint MCP Key" to create one.
                  </td>
                </tr>
              )}
              {displayedKeys.map((k) => {
                const isRevoked = Boolean(k.revoked_at);
                const isConfirming = confirmRevokeKeyId === k.id;
                const prefix = k.surface === 'agent' ? 'kb_agt_' : k.surface === 'docs' ? 'kb_doc_' : 'kb_adm_';

                return (
                  <tr key={k.id} className="kb-mcp-tr" data-testid={`key-row-${k.id}`}>
                    <td className="kb-mcp-td">
                      <span className={isRevoked ? 'kb-mcp-status-revoked' : ''}>{k.label}</span>
                    </td>
                    <td className="kb-mcp-td">
                      <code className="kb-mcp-key-hint" data-testid={`key-hint-${k.id}`}>
                        {prefix}...{k.display_hint}
                      </code>
                    </td>
                    <td className="kb-mcp-td">
                      <div>{getTierBadge(k.scope_tier, k.allowed_projects)}</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '4px' }}>
                        {k.capability_mask !== undefined && (
                          <span
                            className="kb-mcp-unlimited-pill"
                            data-testid={`key-cap-mask-${k.id}`}
                            title={`Capability Mask: ${String(k.capability_mask)}`}
                            style={{ fontSize: '0.75rem', padding: '2px 6px' }}
                          >
                            Mask: {k.capability_mask}
                          </span>
                        )}
                        {k.allowed_cidrs && k.allowed_cidrs.length > 0 && (
                          <span
                            className="kb-mcp-unlimited-pill"
                            data-testid={`key-cidr-badge-${k.id}`}
                            title={`Allowed CIDRs: ${k.allowed_cidrs.join(', ')}`}
                            style={{ fontSize: '0.75rem', padding: '2px 6px' }}
                          >
                            CIDR: {k.allowed_cidrs.join(', ')}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="kb-mcp-td">{k.surface.toUpperCase()}</td>
                    <td className="kb-mcp-td" data-testid={`key-expires-${k.id}`}>
                      {k.expires_at ? (
                        new Date(k.expires_at).toLocaleDateString()
                      ) : (
                        <span className="kb-mcp-unlimited-pill" data-testid={`key-unlimited-${k.id}`}>
                          Never (Unlimited)
                        </span>
                      )}
                    </td>
                    <td className="kb-mcp-td">
                      {isRevoked ? (
                        <span className="kb-mcp-status-revoked" data-testid="status-revoked">Revoked</span>
                      ) : (
                        <span>Active</span>
                      )}
                    </td>
                    <td className="kb-mcp-td">
                      {!isRevoked && (
                        <>
                          {isConfirming ? (
                            <div className="kb-mcp-confirm-bar" data-testid="confirm-revoke-bar">
                              <button
                                type="button"
                                className="kb-mcp-cancel-btn"
                                data-testid="cancel-revoke-btn"
                                autoFocus
                                onClick={() => {
                                  setConfirmRevokeKeyId(null);
                                }}
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                className="kb-mcp-confirm-revoke-btn"
                                data-testid="confirm-revoke-btn"
                                onClick={() => {
                                  void handleConfirmRevokeKey(k.id);
                                }}
                              >
                                Confirm Revoke
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className="kb-mcp-action-btn"
                              data-testid={`revoke-btn-${k.id}`}
                              onClick={() => {
                                setConfirmRevokeKeyId(k.id);
                              }}
                            >
                              Revoke
                            </button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Connected OAuth Apps Section (in mine view) */}
      {activeView === 'mine' && (
        <section className="kb-mcp-studio-section" data-testid="connected-apps-section">
          <div className="kb-mcp-section-header">
            <h2 className="kb-mcp-section-title">
              <EmojiHint kind="restricted" /> Connected OAuth Apps
            </h2>
            <div className="kb-mcp-header-actions">
              <button
                type="button"
                className="kb-mcp-connect-btn"
                data-testid="connect-oauth-app-btn"
                onClick={() => {
                  setShowConnectOAuthModal(true);
                }}
              >
                + Connect OAuth App
              </button>
              <Link
                to="/oauth/device"
                className="kb-mcp-enter-device-code-btn"
                data-testid="enter-device-code-btn"
              >
                Enter Device Code
              </Link>
            </div>
          </div>
          <div className="kb-mcp-table-wrap">
            <table className="kb-mcp-table" data-testid="connected-apps-table">
              <thead>
                <tr>
                  <th className="kb-mcp-th">Application</th>
                  <th className="kb-mcp-th">Client ID</th>
                  <th className="kb-mcp-th">Surface</th>
                  <th className="kb-mcp-th">Connected Date</th>
                  <th className="kb-mcp-th">Actions</th>
                </tr>
              </thead>
              <tbody>
                {connectedApps.length === 0 && !loading && (
                  <tr>
                    <td colSpan={5} className="kb-mcp-empty-state">
                      <div className="kb-mcp-empty-content">
                        <p>No external OAuth applications currently connected.</p>
                        <div className="kb-mcp-empty-actions">
                          <button
                            type="button"
                            className="kb-mcp-connect-btn"
                            data-testid="empty-connect-oauth-app-btn"
                            onClick={() => {
                              setShowConnectOAuthModal(true);
                            }}
                          >
                            + Connect OAuth App
                          </button>
                          <Link
                            to="/oauth/device"
                            className="kb-mcp-enter-device-code-btn"
                            data-testid="empty-enter-device-code-btn"
                          >
                            Enter Device Code
                          </Link>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
                {connectedApps.map((app) => {
                  const isConfirming = confirmRevokeAppId === app.id;

                  return (
                    <tr key={app.id} className="kb-mcp-tr" data-testid={`app-row-${app.id}`}>
                      <td className="kb-mcp-td" data-testid={`app-name-${app.id}`}>
                        {/* Render client_name strictly as text node against XSS */}
                        <span>{app.client_name ?? app.client_id}</span>
                      </td>
                      <td className="kb-mcp-td">
                        <code>{app.client_id}</code>
                      </td>
                      <td className="kb-mcp-td">{app.surface.toUpperCase()}</td>
                      <td className="kb-mcp-td">
                        {new Date(app.created_at).toLocaleDateString()}
                      </td>
                      <td className="kb-mcp-td">
                        {isConfirming ? (
                          <div className="kb-mcp-confirm-bar" data-testid="confirm-disconnect-bar">
                            <button
                              type="button"
                              className="kb-mcp-cancel-btn"
                              data-testid="cancel-disconnect-btn"
                              autoFocus
                              onClick={() => {
                                setConfirmRevokeAppId(null);
                              }}
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              className="kb-mcp-confirm-revoke-btn"
                              data-testid="confirm-disconnect-btn"
                              onClick={() => {
                                void handleConfirmRevokeApp(app.id);
                              }}
                            >
                              Confirm Disconnect
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            className="kb-mcp-action-btn"
                            data-testid={`disconnect-btn-${app.id}`}
                            onClick={() => {
                              setConfirmRevokeAppId(app.id);
                            }}
                          >
                            Disconnect
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Workload Identity Federation (RFC 8693) */}
      <WorkloadFederationSection isAdmin={isWorkspaceAdmin} />

      {/* Mint Key Modal */}
      {showMintModal && (
        <div
          className="kb-snippet-modal-backdrop"
          data-testid="mint-modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowMintModal(false);
            }
          }}
        >
          <div
            className="kb-snippet-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mint-modal-title"
            data-testid="mint-modal-card"
          >
            <div className="kb-snippet-modal-header">
              <h2 id="mint-modal-title" className="kb-snippet-modal-title">Mint New MCP Access Key</h2>
              <button
                type="button"
                className="kb-snippet-modal-close-btn"
                onClick={() => {
                  setShowMintModal(false);
                  setMintError(null);
                }}
              >
                x
              </button>
            </div>
            <form
              onSubmit={(e) => {
                void handleMintSubmit(e);
              }}
              className="kb-mcp-mint-form"
            >
              {mintError && (
                <div className="kb-mcp-mint-error" role="alert" id="mint-error-msg" data-testid="mint-error-banner">
                  {mintError}
                </div>
              )}
              {/* Question 1: Key Name */}
              <div className="kb-mcp-form-row">
                <label htmlFor="mint-label-input" className="kb-mcp-form-label">
                  <span className="kb-mcp-question-num">1.</span> What is the key name?
                </label>
                <input
                  id="mint-label-input"
                  type="text"
                  className="kb-mcp-form-input"
                  data-testid="mint-label-input"
                  placeholder="e.g. CI Agent Token"
                  value={newKeyLabel}
                  onChange={(e) => {
                    setNewKeyLabel(e.target.value);
                  }}
                  autoFocus
                  required
                  aria-invalid={Boolean(mintError)}
                  aria-describedby={mintError ? 'mint-error-msg' : undefined}
                />
              </div>

              {/* Question 2: Unified Key Type & Scope Tier Selector */}
              <div className="kb-mcp-form-row">
                <label htmlFor="mint-key-scope-type-select" className="kb-mcp-form-label">
                  <span className="kb-mcp-question-num">2.</span> Who is this key for & what can it access?
                  <FieldHelpHint
                    title="Key Type & Scope"
                    summary="Security boundary and ownership model governing whether this token belongs to your personal account or an automated service bot, and which workspace or project resources it can access."
                    validValues={[
                      { label: 'Personal - Entire Workspace', description: 'Inherits your user credentials across the entire workspace.' },
                      { label: 'Personal - Single Project', description: 'Inherits your user credentials scoped strictly to one project.' },
                      { label: 'Service Bot - Entire Workspace', description: 'Dedicated bot/automation token scoped to this workspace.' },
                      { label: 'Service Bot - Single Project', description: 'Dedicated bot/automation token restricted strictly to one project.' },
                      { label: 'Service Bot - Server / Global', description: 'Server admin automation key across all workspaces.' },
                    ]}
                    docHref="/docs/three-surface-mcp-server-architecture#scope-tiers"
                    testId="mint-scope-help"
                  />
                </label>
                <select
                  id="mint-key-scope-type-select"
                  className="kb-mcp-form-select"
                  data-testid="mint-key-scope-type-select"
                  value={`${newKeyOwnerKind}:${newKeyScopeTier}`}
                  onChange={(e) => {
                    const [ownerKind, scopeTier] = e.target.value.split(':') as [OwnerKind, ScopeTier];
                    setNewKeyOwnerKind(ownerKind);
                    setNewKeyScopeTier(scopeTier);
                  }}
                >
                  <optgroup label="For Me (Personal User)">
                    <option value="personal_user:project">Personal - Single Project</option>
                    <option value="personal_user:workspace">Personal - Entire Workspace</option>
                  </optgroup>
                  <optgroup label="For an Automated Bot / CI (Service Bot)">
                    <option value="service_bot:project">Service Bot - Single Project</option>
                    <option value="service_bot:workspace">Service Bot - Entire Workspace</option>
                    {isServerAdmin && (
                      <option value="service_bot:global">Service Bot - Server / Global</option>
                    )}
                  </optgroup>
                </select>
              </div>

              {newKeyScopeTier === 'project' && (
                <div className="kb-mcp-form-row">
                  <label htmlFor="mint-project-input" className="kb-mcp-form-label">
                    Allowed Project:
                  </label>
                  <input
                    id="mint-project-input"
                    type="text"
                    className="kb-mcp-form-input"
                    data-testid="mint-project-input"
                    list="mint-project-datalist"
                    value={newKeyProject}
                    onChange={(e) => {
                      setNewKeyProject(e.target.value);
                    }}
                    required
                  />
                  {projects.length > 0 && (
                    <datalist id="mint-project-datalist">
                      {projects.map((p) => (
                        <option key={p.id} value={p.identifier}>
                          {p.name && p.name !== p.identifier ? `${p.identifier} - ${p.name}` : p.identifier}
                        </option>
                      ))}
                    </datalist>
                  )}
                </div>
              )}

              {/* Question 3: Capabilities, Target Surface, Expiration & Advanced */}
              <div className="kb-mcp-form-question-heading">
                <span className="kb-mcp-question-num">3.</span> What can it do?
              </div>

              <div className="kb-mcp-form-row">
                <label htmlFor="mint-surface-select" className="kb-mcp-form-label">
                  Target Surface:
                </label>
                <select
                  id="mint-surface-select"
                  className="kb-mcp-form-select"
                  data-testid="mint-surface-select"
                  value={newKeySurface}
                  onChange={(e) => {
                    setNewKeySurface(e.target.value as 'agent' | 'docs' | 'admin');
                    setDisabledTools([]);
                  }}
                >
                  <option value="agent">/mcp/agent (Standard Tools)</option>
                  <option value="docs">/mcp/docs (Knowledge & Markdown)</option>
                  {isWorkspaceAdmin && (
                    <option value="admin">/mcp/admin (Administrative Ops)</option>
                  )}
                </select>
              </div>

              <div className="kb-mcp-form-row">
                <label htmlFor="mint-expiry-select" className="kb-mcp-form-label">
                  Expiration:
                  <FieldHelpHint
                    title="Token Expiration"
                    summary="Lifetime duration before newly minted MCP access key expires."
                    defaultValue="30 Days (Max: Workspace TTL)"
                    docHref="/docs/three-surface-mcp-server-architecture#scope-tiers"
                    testId="mcp-expiry-help"
                  />
                </label>
                <select
                  id="mint-expiry-select"
                  className="kb-mcp-form-select"
                  data-testid="mint-expiry-select"
                  value={isUnlimited ? 'unlimited' : newKeyExpiry}
                  onChange={(e) => {
                    if (e.target.value === 'unlimited') {
                      setIsUnlimited(true);
                    } else {
                      setIsUnlimited(false);
                      setNewKeyExpiry(Number(e.target.value));
                      setConfirmUnlimited(false);
                    }
                  }}
                >
                  <option value={30}>30 Days</option>
                  <option value={60}>60 Days</option>
                  <option value={90}>90 Days</option>
                  <option value={365}>1 Year</option>
                  {allowUnlimited && (
                    <option value="unlimited" data-testid="option-unlimited">
                      Unlimited (not recommended)
                    </option>
                  )}
                </select>
              </div>

              {isUnlimited && (
                <div
                  className="kb-mcp-unlimited-warning"
                  data-testid="unlimited-warning-box"
                  data-test-banner="unlimited-warning-banner"
                >
                  <p className="kb-mcp-warning-text">
                    ⚠️ <strong>Are you sure?</strong> Unlimited keys never expire. This poses a significant security risk if the token is leaked or compromised.
                  </p>
                  <label className="kb-mcp-confirm-unlimited-label" htmlFor="confirm-unlimited-checkbox">
                    <input
                      id="confirm-unlimited-checkbox"
                      type="checkbox"
                      data-testid="confirm-unlimited-checkbox"
                      aria-label="I understand the security risk and confirm creating an unlimited key"
                      checked={confirmUnlimited}
                      onChange={(e) => {
                        setConfirmUnlimited(e.target.checked);
                      }}
                    />
                    <span>I understand the security risk and confirm creating an unlimited key</span>
                  </label>
                </div>
              )}

              <AdvancedSection
                title="Advanced Capability & Network Restrictions"
                summary="Granular bitmask permissions, tool-level narrowing, and CIDR ingress restrictions"
                testId="advanced-capability-restrictions"
                hasErrors={Boolean(cidrError)}
                activeOverridesCount={
                  (allowedCidrsInput.trim() ? 1 : 0) +
                  (disabledTools.length > 0 ? 1 : 0) +
                  (capabilityMask !== 31 ? 1 : 0)
                }
              >
                <div className="kb-mcp-form-row">
                  <label htmlFor="capability-preset-select" className="kb-mcp-form-label">
                    Capability Ceiling:
                    <FieldHelpHint
                      title="Capability Ceiling"
                      summary="Maximum permission ceiling bitmask allocated to the client."
                      defaultValue="31 (Standard Developer Agent)"
                      docHref="/docs/three-surface-mcp-server-architecture#scope-tiers"
                      testId="mcp-capability-ceiling-help"
                    />
                  </label>
                  <select
                    id="capability-preset-select"
                    className="kb-mcp-form-select"
                    data-testid="capability-preset-select"
                    value={
                      [1, 3, 31, 255].includes(capabilityMask)
                        ? String(capabilityMask)
                        : 'custom'
                    }
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val !== 'custom') {
                        setCapabilityMask(Number(val));
                      }
                    }}
                  >
                    <option value="1">Read-Only Agent (1)</option>
                    <option value="3">View + Comment (3)</option>
                    <option value="31">Standard Developer Agent (31)</option>
                    <option value="255">Full Project Agent (255)</option>
                    {![1, 3, 31, 255].includes(capabilityMask) && (
                      <option value="custom">Custom ({capabilityMask})</option>
                    )}
                  </select>
                  <span className="kb-mcp-form-hint">
                    Sets the maximum permission ceiling. Keys narrow permissions downward without escalating privileges.
                  </span>
                </div>

                <div className="kb-mcp-form-row">
                  <label className="kb-mcp-form-label">
                    Granular Capability Bit Toggles:
                  </label>
                  <div className="kb-mcp-tools-grid" data-testid="capability-bits-grid">
                    {CAPABILITY_BITS.map(({ bit, name }) => {
                      const isChecked = (capabilityMask & bit) === bit;
                      return (
                        <label key={bit} className="kb-mcp-tool-checkbox-label" htmlFor={`cap-bit-${String(bit)}`}>
                          <input
                            id={`cap-bit-${String(bit)}`}
                            type="checkbox"
                            aria-label={`Capability bit ${name} (${String(bit)})`}
                            data-testid={`cap-bit-${String(bit)}`}
                            checked={isChecked}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setCapabilityMask((prev) => prev | bit);
                              } else {
                                setCapabilityMask((prev) => prev & ~bit);
                              }
                            }}
                          />
                          <span>{name} ({bit})</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <div className="kb-mcp-form-row">
                  <label htmlFor="mint-allowed-cidrs-input" className="kb-mcp-form-label">
                    Allowed CIDRs (Optional):
                  </label>
                  <input
                    id="mint-allowed-cidrs-input"
                    type="text"
                    className="kb-mcp-form-input"
                    data-testid="mint-allowed-cidrs-input"
                    placeholder="e.g. 192.168.1.0/24, 10.0.0.0/8"
                    value={allowedCidrsInput}
                    onChange={(e) => {
                      const val = e.target.value;
                      setAllowedCidrsInput(val);
                      const res = validateCidrInput(val);
                      setCidrError(res.error ?? null);
                    }}
                    aria-invalid={Boolean(cidrError)}
                    aria-describedby={cidrError ? 'cidr-error-message' : undefined}
                  />
                  {cidrError && (
                    <div
                      id="cidr-error-message"
                      className="kb-mcp-warning-text"
                      role="alert"
                      data-testid="cidr-error-message"
                      style={{ color: '#ef4444', marginTop: '4px' }}
                    >
                      {cidrError}
                    </div>
                  )}
                  <span className="kb-mcp-form-hint">
                    Optional comma-separated IPv4 or IPv6 CIDR blocks restricting source networks.
                  </span>
                </div>

                <div className="kb-mcp-form-row">
                  <label className="kb-mcp-form-label">
                    Narrow Tools (Disable specific capabilities):
                  </label>
                  <div className="kb-mcp-tools-grid" data-testid="tools-selection-grid">
                    {SURFACE_TOOLS[newKeySurface]
                      .filter((toolName) => !isViewer || !WRITE_MCP_TOOLS.has(toolName))
                      .map((toolName) => {
                      const isDisabled = disabledTools.includes(toolName);
                      return (
                        <label key={toolName} className="kb-mcp-tool-checkbox-label" htmlFor={`disable-tool-${toolName}`}>
                          <input
                            id={`disable-tool-${toolName}`}
                            type="checkbox"
                            aria-label={`Disable tool ${toolName}`}
                            data-testid={`disable-tool-${toolName}`}
                            checked={isDisabled}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setDisabledTools([...disabledTools, toolName]);
                              } else {
                                setDisabledTools(disabledTools.filter((t) => t !== toolName));
                              }
                            }}
                          />
                          <span><code>{toolName}</code> (disable)</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              </AdvancedSection>

              {/* Question 4: Live Plain-Language Key Summary */}
              <div className="kb-mcp-form-row kb-mcp-key-summary-row">
                <div className="kb-mcp-form-question-heading">
                  <span className="kb-mcp-question-num">4.</span> Key Summary
                </div>
                <div className="kb-mcp-key-summary" data-testid="mint-key-summary">
                  {formatMintKeySummary({
                    label: newKeyLabel,
                    ownerKind: newKeyOwnerKind,
                    scopeTier: newKeyScopeTier,
                    project: newKeyScopeTier === 'project' ? newKeyProject : undefined,
                    surface: newKeySurface,
                    capabilityMask,
                  })}
                </div>
              </div>

              <div className="kb-mcp-form-actions">
                <button
                  type="button"
                  className="kb-snippet-copy-btn"
                  onClick={() => {
                    setShowMintModal(false);
                    setMintError(null);
                    setIsUnlimited(false);
                    setConfirmUnlimited(false);
                    setDisabledTools([]);
                    setCapabilityMask(31);
                    setAllowedCidrsInput('');
                    setCidrError(null);
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kb-snippet-done-btn"
                  data-testid="mint-submit-btn"
                  disabled={
                    minting ||
                    !newKeyLabel.trim() ||
                    (isUnlimited && !confirmUnlimited) ||
                    Boolean(cidrError) ||
                    capabilityMask <= 0
                  }
                >
                  {minting ? 'Minting...' : 'Mint Key'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Snippet / Plaintext Key Modal */}
      {showSnippetModal && (
        <McpConfigSnippetModal
          rawKey={activeSnippetKey}
          surface={newKeySurface}
          workspaceSlug={currentWorkspaceSlug}
          projectKey={newKeyProject.trim() || effectiveProjectKey}
          onClose={() => {
            setActiveSnippetKey(undefined);
            setShowSnippetModal(false);
          }}
        />
      )}

      {/* Inline AAL2 Step-Up Modal */}
      {aal2Challenge && (
        <div className="kb-snippet-modal-backdrop" data-testid="aal2-modal-backdrop">
          <div
            className="kb-snippet-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="aal2-modal-title"
            data-testid="aal2-modal-card"
          >
            <div className="kb-snippet-modal-header">
              <h2 id="aal2-modal-title" className="kb-snippet-modal-title">
                Admin Verification Required (AAL2)
              </h2>
              <button
                type="button"
                className="kb-snippet-modal-close-btn"
                onClick={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
              >
                x
              </button>
            </div>
            <div className="kb-mcp-studio-section">
              <SecondFactorStep
                challengeId={aal2Challenge.challengeId}
                methods={aal2Challenge.methods}
                onSuccess={() => {
                  void handleAal2Success();
                }}
                onError={() => {
                  // Handled inside SecondFactorStep
                }}
                onSessionExpired={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
                onCancel={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
              />
            </div>
          </div>
        </div>
      )}
      {showConnectOAuthModal && (
        <ConnectOAuthAppModal
          user={propUser ?? fetchedUser}
          workspaceSlug={currentWorkspaceSlug}
          projectKey={effectiveProjectKey}
          scopeTier={activeScope === 'all' ? 'workspace' : activeScope}
          onClose={() => {
            setShowConnectOAuthModal(false);
          }}
        />
      )}
    </div>
  );
}
