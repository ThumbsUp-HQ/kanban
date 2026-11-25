/**
 * Workspace Settings Studio (KANBA-202, KANBA-210).
 *
 * Dedicated management page for Workspace Administrators (WORKSPACE_ADMIN / SERVER_ADMIN).
 * Tabs:
 * 1. General & Policy: Workspace Name, Slug, Display Name, Default Visibility,
 *    Session Timeouts, Trash Retention, MCP Key Max TTL, and Air-Gap Mode.
 * 2. Workspace Members: Local user provisioning (+ Add User), inline role bindings,
 *    and member removal.
 * 3. Groups & Governance: Nested Groups and Group Membership CRUD with cycle rejection.
 * 4. Workspace MCP Keys: Link to /workspaces/settings/mcp.
 */

import React, { useEffect, useState, type JSX, type SyntheticEvent } from 'react';
import { Link, useLocation } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { apiFetch, isAal2StepUpCancelled } from '../../api/client';
import { ensureSessionCsrfToken } from '../auth/useSessionGuard';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { RbacPolicyBuilder } from '../rbac/RbacPolicyBuilder';
import { RoleLabelPicker } from '../rbac/RoleLabelPicker';
import { AdvancedSection } from '../../ui/AdvancedSection';
import { AiStudioPage } from '../admin-ai/AiStudioPage';
import { AgentStudioPage } from '../admin-agents/AgentStudioPage';
import './ProjectSettingsPage.css';
import './WorkspaceSettingsPage.css';

interface WorkspaceSettingsData {
  workspace_id?: string;
  id?: string;
  name?: string;
  slug?: string;
  display_name?: string | null;
  default_project_visibility?: 'private' | 'workspace';
  session_idle_timeout_min?: number;
  session_absolute_timeout_min?: number;
  trash_retention_days?: number;
  mcp_key_max_ttl_days?: number;
  air_gap_mode?: boolean;
  default_skip_loaded_sequence_numbers?: boolean;
  issue_export_enabled?: boolean;
  issue_import_enabled?: boolean;
  issue_export_allowed_roles?: string[];
  updated_at?: string;
}

export interface WorkspacePrincipal {
  id: string;
  display_name?: string | null;
  principal_type?: string | null;
  type?: string | null;
  handle?: string | null;
  principal?: string | null;
  email?: string | null;
  role?: string | null;
  role_name?: string | null;
}

export function formatHandle(handle?: string | null): string {
  if (!handle) return '';
  const clean = handle.replace(/^@+/, '');
  return clean ? `@${clean}` : '';
}

export type WorkspaceTab = 'general' | 'members' | 'groups' | 'roles' | 'ai' | 'agents' | 'trash';

export function parseTabFromHash(hash?: string | null): WorkspaceTab | null {
  if (!hash) return null;
  const clean = hash.trim().replace(/^#+/, '');
  if (clean === 'tab-general' || clean === 'general') return 'general';
  if (clean === 'tab-members' || clean === 'members') return 'members';
  if (clean === 'tab-groups' || clean === 'groups') return 'groups';
  if (clean === 'tab-roles' || clean === 'roles') return 'roles';
  if (clean === 'tab-ai' || clean === 'ai') return 'ai';
  if (clean === 'tab-agents' || clean === 'agents') return 'agents';
  if (clean === 'tab-trash' || clean === 'trash') return 'trash';
  return null;
}

export interface WorkspaceTrashedItem {
  id: string;
  kind: string;
  key?: string | null;
  title?: string | null;
  deleted_at: string;
  purge_after?: string;
  remaining_days: number;
  project_id?: string | null;
}

const TRASH_KIND_LABELS: Record<string, string> = {
  project: '📁 Project',
  issue: '📋 Issue',
  doc: '📄 Doc',
  page: '📃 Page',
  sticky: '🟨 Sticky',
  cycle: '🔄 Cycle',
  module: '🧩 Module',
  view: '👁️ View',
};

export const TRASH_FILTER_LABELS: Record<string, string> = {
  all: 'All Items',
  project: 'Projects',
  issue: 'Issues',
  doc: 'Docs',
  page: 'Pages',
  sticky: 'Stickies',
  cycle: 'Cycles',
  module: 'Modules',
  view: 'Views',
};

function getTrashError(err: unknown, fallback: string): string {
  const o = err as { detail?: string; message?: string } | undefined;
  return o?.detail ?? o?.message ?? fallback;
}

export function formatTrashKind(kind: string): string {
  return TRASH_KIND_LABELS[kind.toLowerCase()] ?? kind;
}

export function formatIdleDuration(minutes: number): string {
  if (minutes < 60) return `${String(minutes)} minutes`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${String(h)} hour${h > 1 ? 's' : ''}` : `${String(h)}h ${String(m)}m`;
}

export function formatAbsoluteDuration(minutes: number): string {
  if (minutes < 60) return `${String(minutes)} minutes`;
  if (minutes < 1440) {
    const h = (minutes / 60).toFixed(minutes % 60 === 0 ? 0 : 1);
    return `${h} hour${Number(h) > 1 ? 's' : ''}`;
  }
  const days = (minutes / 1440).toFixed(minutes % 1440 === 0 ? 0 : 1);
  const hours = Math.floor(minutes / 60);
  return `${days} day${Number(days) > 1 ? 's' : ''} (${String(hours)} hours)`;
}

export function WorkspaceSettingsPage(): JSX.Element {
  const location = useLocation();
  const queryClient = useQueryClient();
  const locationHash = location.hash;

  const [currentUser, setCurrentUser] = useState<{
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
    is_project_admin?: boolean;
  } | null>(null);

  const isWsOrServerAdmin = (currentUser?.is_server_admin === true) || (currentUser?.is_workspace_admin === true);
  const isProjectAdminOnly = Boolean(!isWsOrServerAdmin && currentUser?.is_project_admin);

  const [rawActiveTab, setActiveTab] = useState<WorkspaceTab>(() => {
    const rawHash = window.location.hash || locationHash;
    return parseTabFromHash(rawHash) ?? 'general';
  });

  const activeTab: WorkspaceTab = isProjectAdminOnly ? 'trash' : rawActiveTab;

  useEffect(() => {
    const syncFromHash = (): void => {
      const currentHash = window.location.hash;
      const clean = currentHash.replace(/^#+/, '').trim();
      if (!clean) {
        setActiveTab(isProjectAdminOnly ? 'trash' : 'general');
        return;
      }
      const parsed = parseTabFromHash(currentHash);
      if (parsed) {
        setActiveTab(isProjectAdminOnly ? 'trash' : parsed);
      }
    };

    window.addEventListener('hashchange', syncFromHash);
    return () => {
      window.removeEventListener('hashchange', syncFromHash);
    };
  }, [isProjectAdminOnly]);

  const handleTabChange = (tab: WorkspaceTab): void => {
    setActiveTab(tab);
    const targetHash = `#tab-${tab}`;
    if (window.location.hash !== targetHash) {
      window.location.hash = targetHash;
    }
  };
  const [settings, setSettings] = useState<WorkspaceSettingsData | null>(null);
  const [principals, setPrincipals] = useState<WorkspacePrincipal[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form Fields - General
  const [name, setName] = useState<string>('');
  const [slug, setSlug] = useState<string>('');
  const [displayName, setDisplayName] = useState<string>('');
  const [defaultVisibility, setDefaultVisibility] = useState<'private' | 'workspace'>('workspace');
  const [idleTimeout, setIdleTimeout] = useState<number>(120);
  const [absTimeout, setAbsTimeout] = useState<number>(1440);
  const [trashRetention, setTrashRetention] = useState<number>(30);
  const [mcpKeyMaxTtl, setMcpKeyMaxTtl] = useState<number>(90);
  const [airGapMode, setAirGapMode] = useState<boolean>(false);
  const [defaultSkipLoadedSeq, setDefaultSkipLoadedSeq] = useState<boolean>(false);
  const [issueExportEnabled, setIssueExportEnabled] = useState<boolean>(true);
  const [issueImportEnabled, setIssueImportEnabled] = useState<boolean>(true);
  const [issueExportAllowedRoles, setIssueExportAllowedRoles] = useState<string[]>([
    'workspace_admin',
    'project_admin',
    'member',
  ]);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // Form Fields - New User
  const [newHandle, setNewHandle] = useState<string>('');
  const [newDisplayName, setNewDisplayName] = useState<string>('');
  const [newEmail, setNewEmail] = useState<string>('');
  const [newPassword, setNewPassword] = useState<string>('');
  const [newRole, setNewRole] = useState<'WORKSPACE_MEMBER' | 'WORKSPACE_GUEST' | 'WORKSPACE_ADMIN'>('WORKSPACE_MEMBER');
  const [isCreatingUser, setIsCreatingUser] = useState<boolean>(false);

  // Form Fields - Groups
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [groupMembers, setGroupMembers] = useState<WorkspacePrincipal[]>([]);
  const [isLoadingGroupMembers, setIsLoadingGroupMembers] = useState<boolean>(false);
  const [newGroupName, setNewGroupName] = useState<string>('');
  const [newGroupHandle, setNewGroupHandle] = useState<string>('');
  const [isCreatingGroup, setIsCreatingGroup] = useState<boolean>(false);
  const [selectedAddMemberId, setSelectedAddMemberId] = useState<string>('');
  const [groupActionError, setGroupActionError] = useState<string | null>(null);

  // Form Fields - Trash & Retention
  const [trashedItems, setTrashedItems] = useState<WorkspaceTrashedItem[]>([]);
  const [trashKindFilter, setTrashKindFilter] = useState<string>('all');
  const [trashSearchQuery, setTrashSearchQuery] = useState<string>('');
  const [isLoadingTrash, setIsLoadingTrash] = useState<boolean>(false);
  const [trashActionError, setTrashActionError] = useState<string | null>(null);
  const [trashActionSuccess, setTrashActionSuccess] = useState<string | null>(null);

  // 2-stage permanent purge state (SERVER_ADMIN only)
  const [purgeTarget, setPurgeTarget] = useState<WorkspaceTrashedItem | null>(null);
  const [purgeConfirmationToken, setPurgeConfirmationToken] = useState<string | null>(null);
  const [purgeBlastHash, setPurgeBlastHash] = useState<string | null>(null);
  const [purgeConfirmPhrase, setPurgeConfirmPhrase] = useState<string | null>(null);
  const [typedConfirmPhrase, setTypedConfirmPhrase] = useState<string>('');
  const [purgeReason, setPurgeReason] = useState<string>('');
  const [isRequestingPurge, setIsRequestingPurge] = useState<boolean>(false);
  const [isExecutingPurge, setIsExecutingPurge] = useState<boolean>(false);

  const refreshPrincipals = async (): Promise<void> => {
    try {
      const pRes = (await apiFetch('GET', '/api/v1/admin/principals?limit=100' as never)) as
        | WorkspacePrincipal[]
        | { items?: WorkspacePrincipal[] };
      const raw = Array.isArray(pRes) ? pRes : (pRes.items ?? []);
      setPrincipals(raw);
    } catch {
      // Fallback
    }
  };

  const loadGroupMembers = async (groupId: string): Promise<void> => {
    setIsLoadingGroupMembers(true);
    setGroupActionError(null);
    try {
      const res = (await apiFetch('GET', `/api/v1/admin/groups/${groupId}/members` as never)) as
        | WorkspacePrincipal[]
        | { items?: WorkspacePrincipal[] };
      const raw = Array.isArray(res) ? res : ((res).items ?? []);
      setGroupMembers(raw);
    } catch (err: unknown) {
      /* v8 ignore next */
      if (isAal2StepUpCancelled(err)) return;
      const errObj = err as { message?: string; detail?: string };
      setGroupActionError(errObj.detail ?? errObj.message ?? 'Failed to load group members.');
    } finally {
      setIsLoadingGroupMembers(false);
    }
  };

  useEffect(() => {
    let active = true;
    async function init(): Promise<void> {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        // 0. Verify authorization
        try {
          const me = (await apiFetch('GET', '/api/v1/auth/me' as never)) as {
            is_server_admin?: boolean;
            is_workspace_admin?: boolean;
            is_project_admin?: boolean;
          };
          if (active) setCurrentUser(me);

          const isOpeningTrash = window.location.hash.includes('tab-trash') || (parseTabFromHash(window.location.hash) === 'trash');
          const isServerAdmin = Boolean(me.is_server_admin);
          const isWsAdmin = Boolean(me.is_workspace_admin);
          let isProjAdmin = Boolean(me.is_project_admin);

          if (!isServerAdmin && !isWsAdmin) {
            if (!isProjAdmin && isOpeningTrash) {
              try {
                const probeRes = (await apiFetch('GET', '/api/v1/admin/trash' as never)) as {
                  items?: unknown[];
                  retention_days?: number;
                };
                if (Array.isArray(probeRes.items) || probeRes.retention_days != null) {
                  isProjAdmin = true;
                  if (active) {
                    setCurrentUser({ ...me, is_project_admin: true });
                  }
                }
              } catch {
                isProjAdmin = false;
              }
            }

            if (!isProjAdmin) {
              if (active) setIsLoading(false);
              return;
            }

            // Project admin: lock to trash tab and skip workspace-level admin fetches
            if (active) {
              setActiveTab('trash');
              setIsLoading(false);
            }
            return;
          }
        } catch {
          // If auth/me failed because of network error or in offline unit tests, fall through to workspace-settings fetch
        }

        // 1. Fetch workspace settings
        const settingsRes = (await apiFetch('GET', '/api/v1/admin/workspace-settings' as never)) as WorkspaceSettingsData;
        if (active) {
          setSettings(settingsRes);
          setName(settingsRes.name ?? '');
          setSlug(settingsRes.slug ?? '');
          setDisplayName(settingsRes.display_name ?? '');
          setDefaultVisibility(settingsRes.default_project_visibility ?? 'workspace');
          setIdleTimeout(settingsRes.session_idle_timeout_min ?? 120);
          setAbsTimeout(settingsRes.session_absolute_timeout_min ?? 1440);
          setTrashRetention(settingsRes.trash_retention_days ?? 30);
          setMcpKeyMaxTtl(settingsRes.mcp_key_max_ttl_days ?? 90);
          setAirGapMode(Boolean(settingsRes.air_gap_mode));
          setDefaultSkipLoadedSeq(Boolean(settingsRes.default_skip_loaded_sequence_numbers));
          setIssueExportEnabled(settingsRes.issue_export_enabled !== false);
          setIssueImportEnabled(settingsRes.issue_import_enabled !== false);
          if (Array.isArray(settingsRes.issue_export_allowed_roles)) {
            setIssueExportAllowedRoles(settingsRes.issue_export_allowed_roles);
          }
        }

        // 2. Fetch workspace principals
        try {
          const pRes = (await apiFetch('GET', '/api/v1/admin/principals?limit=100' as never)) as
            | WorkspacePrincipal[]
            | { items?: WorkspacePrincipal[] };
          const raw = Array.isArray(pRes) ? pRes : (pRes.items ?? []);
          if (active) {
            setPrincipals(raw);
            const firstGroup = raw.find((p) => (p.principal_type ?? p.type) === 'GROUP');
            if (firstGroup) {
              setSelectedGroupId(firstGroup.id);
            }
          }
        } catch {
          // May be restricted or mock in tests
        }
      } catch (err: unknown) {
        /* v8 ignore next */
        if (!active || isAal2StepUpCancelled(err)) return;
        const errObj = err as { message?: string; detail?: string };
        setErrorMessage(errObj.detail ?? errObj.message ?? 'Failed to load workspace settings.');
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (selectedGroupId && activeTab === 'groups') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void loadGroupMembers(selectedGroupId);
    }
  }, [selectedGroupId, activeTab]);

  const loadWorkspaceTrash = async (
    kind: string = trashKindFilter,
    query: string = trashSearchQuery,
  ): Promise<void> => {
    setIsLoadingTrash(true);
    setTrashActionError(null);
    try {
      const params = new URLSearchParams();
      if (kind && kind !== 'all') params.set('kind', kind);
      if (query.trim()) params.set('q', query.trim());
      const queryStr = params.toString() ? `?${params.toString()}` : '';

      const res = (await apiFetch('GET', `/api/v1/admin/trash${queryStr}` as never)) as {
        items?: WorkspaceTrashedItem[];
        retention_days?: number;
        total?: number;
      };
      setTrashedItems(res.items ?? []);
      if (res.retention_days != null) {
        setTrashRetention(res.retention_days);
      }
    } catch (err: unknown) {
      /* v8 ignore next */
      if (isAal2StepUpCancelled(err)) return;
      setTrashActionError(getTrashError(err, 'Failed to load trashed items.'));
    } finally {
      setIsLoadingTrash(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'trash') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void loadWorkspaceTrash();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, trashKindFilter]);

  const handleRestoreItem = async (item: WorkspaceTrashedItem): Promise<void> => {
    setTrashActionError(null);
    setTrashActionSuccess(null);
    try {
      const csrf = await ensureSessionCsrfToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (csrf) headers['X-CSRF-Token'] = csrf;

      await apiFetch(
        'POST',
        `/api/v1/admin/trash/${item.id}:restore?reason=${encodeURIComponent('Restored from workspace trash studio')}` as never,
        { headers },
      );
      setTrashActionSuccess(`Restored ${(item.title ?? item.key) ?? item.kind} successfully.`);
      await loadWorkspaceTrash();
    } catch (err: unknown) {
      /* v8 ignore next */
      if (isAal2StepUpCancelled(err)) return;
      setTrashActionError(getTrashError(err, 'Failed to restore item.'));
    }
  };

  const handleRequestPurge = async (item: WorkspaceTrashedItem): Promise<void> => {
    setTrashActionError(null);
    setTrashActionSuccess(null);
    setPurgeTarget(item);
    setIsRequestingPurge(true);
    try {
      const csrf = await ensureSessionCsrfToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (csrf) headers['X-CSRF-Token'] = csrf;

      const body = {
        target_kind: item.kind,
        target: item.id,
        mode: 'permanent_purge',
      };
      const res = (await apiFetch('POST', '/api/v1/admin/destructive:request' as never, {
        headers,
        body: JSON.stringify(body),
      })) as { confirmation_token?: string; blast_hash?: string; confirm_phrase?: string };

      setPurgeConfirmationToken(res.confirmation_token ?? null);
      setPurgeBlastHash(res.blast_hash ?? null);
      setPurgeConfirmPhrase(res.confirm_phrase ?? null);
      setTypedConfirmPhrase('');
      setPurgeReason('');
    } catch (err: unknown) {
      /* v8 ignore next */
      if (isAal2StepUpCancelled(err)) return;
      setTrashActionError(getTrashError(err, 'Failed to request permanent purge.'));
      setPurgeTarget(null);
      setPurgeConfirmationToken(null);
      setPurgeBlastHash(null);
      setPurgeConfirmPhrase(null);
      setTypedConfirmPhrase('');
      setPurgeReason('');
    } finally {
      setIsRequestingPurge(false);
    }
  };

  const handleExecutePurge = async (): Promise<void> => {
    /* v8 ignore next */
    if (!purgeConfirmationToken || !purgeTarget) return;
    setIsExecutingPurge(true);
    setTrashActionError(null);
    setTrashActionSuccess(null);
    try {
      const csrf = await ensureSessionCsrfToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (csrf) headers['X-CSRF-Token'] = csrf;

      const expectedConfirmPhrase =
        purgeConfirmPhrase ??
        `PURGE ${purgeTarget.kind.toUpperCase()} ${(purgeTarget.key ?? purgeTarget.id)}`;

      const body = {
        target_kind: purgeTarget.kind,
        target: purgeTarget.id,
        mode: 'permanent_purge',
        confirmation_token: purgeConfirmationToken,
        confirm_phrase: expectedConfirmPhrase,
        reason: purgeReason.trim().slice(0, 500),
      };
      await apiFetch('POST', '/api/v1/admin/destructive:execute' as never, {
        headers,
        body: JSON.stringify(body),
      });

      setTrashActionSuccess(
        `Permanently purged ${(purgeTarget.title ?? purgeTarget.key) ?? purgeTarget.kind}.`,
      );
      setPurgeTarget(null);
      setPurgeConfirmationToken(null);
      setPurgeBlastHash(null);
      setPurgeConfirmPhrase(null);
      setTypedConfirmPhrase('');
      setPurgeReason('');
      await loadWorkspaceTrash();
    } catch (err: unknown) {
      /* v8 ignore next */
      if (isAal2StepUpCancelled(err)) return;
      setTrashActionError(getTrashError(err, 'Failed to execute permanent purge.'));
    } finally {
      setIsExecutingPurge(false);
    }
  };

  const handleCancelPurge = (): void => {
    setPurgeTarget(null);
    setPurgeConfirmationToken(null);
    setPurgeBlastHash(null);
    setPurgeConfirmPhrase(null);
    setTypedConfirmPhrase('');
    setPurgeReason('');
  };

  const handleSaveGeneral = (e: SyntheticEvent) => {
    e.preventDefault();
    void (async () => {
      setIsSaving(true);
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const payload = {
          name: name.trim(),
          slug: slug.trim(),
          display_name: displayName.trim(),
          default_project_visibility: defaultVisibility,
          session_idle_timeout_min: idleTimeout,
          session_absolute_timeout_min: absTimeout,
          trash_retention_days: trashRetention,
          mcp_key_max_ttl_days: mcpKeyMaxTtl,
          air_gap_mode: airGapMode,
          default_skip_loaded_sequence_numbers: defaultSkipLoadedSeq,
          issue_export_enabled: issueExportEnabled,
          issue_import_enabled: issueImportEnabled,
          issue_export_allowed_roles: issueExportAllowedRoles,
        };

        const updated = (await apiFetch('PATCH', '/api/v1/admin/workspace-settings' as never, {
          headers,
          body: JSON.stringify(payload),
        })) as WorkspaceSettingsData;

        setSettings(updated);
        setSuccessMessage('Workspace settings updated successfully.');
        // Invalidate system status queries
        void queryClient.invalidateQueries({ queryKey: ['system', 'status'] });
        // Notify topbar header pills of air-gap status update
        window.dispatchEvent(new CustomEvent('kb:system-status-changed'));
      } catch (err: unknown) {
        if (isAal2StepUpCancelled(err)) return;
        const errObj = err as { message?: string; detail?: string };
        setErrorMessage(errObj.detail ?? errObj.message ?? 'Failed to update workspace settings.');
      } finally {
        setIsSaving(false);
      }
    })();
  };

  const handleCreateUser = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!newHandle.trim() || !newDisplayName.trim()) return;
    const trimmedEmail = newEmail.trim();
    if (!trimmedEmail) {
      setErrorMessage('Email is required for user provisioning.');
      setSuccessMessage(null);
      return;
    }
    void (async () => {
      setIsCreatingUser(true);
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        // 1. Create principal/user
        const createdUser = (await apiFetch('POST', '/api/v1/admin/principals' as never, {
          headers,
          body: JSON.stringify({
            type: 'USER',
            handle: newHandle.startsWith('@') ? newHandle.trim() : `@${newHandle.trim()}`,
            display_name: newDisplayName.trim(),
            email: trimmedEmail,
            password: newPassword.length > 0 ? newPassword : undefined,
          }),
        })) as { id: string };

        // 2. Bind role if provided (sending both role and role_name to prevent 422)
        if (createdUser.id) {
          await apiFetch('POST', '/api/v1/admin/role-bindings' as never, {
            headers,
            body: JSON.stringify({
              principal_id: createdUser.id,
              role: newRole,
              role_name: newRole,
              scope_type: 'workspace',
            }),
          });
        }

        setNewHandle('');
        setNewDisplayName('');
        setNewEmail('');
        setNewPassword('');
        setSuccessMessage(`User ${newDisplayName} created successfully.`);
        await refreshPrincipals();
      } catch (err: unknown) {
        /* v8 ignore next */
        if (isAal2StepUpCancelled(err)) return;
        const errObj = err as { message?: string; detail?: string };
        setErrorMessage(errObj.detail ?? errObj.message ?? 'Failed to create workspace user.');
      } finally {
        setIsCreatingUser(false);
      }
    })();
  };

  const handleUpdateRole = async (principalId: string, role: string): Promise<void> => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const csrf = await ensureSessionCsrfToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (csrf) headers['X-CSRF-Token'] = csrf;

      await apiFetch('POST', '/api/v1/admin/role-bindings' as never, {
        headers,
        body: JSON.stringify({
          principal_id: principalId,
          role: role,
          role_name: role,
          scope_type: 'workspace',
        }),
      });
      setSuccessMessage('Member role updated.');
      setPrincipals((prev) =>
        prev.map((p) => (p.id === principalId ? { ...p, role, role_name: role } : p)),
      );
    } catch (err: unknown) {
      /* v8 ignore next */
      if (isAal2StepUpCancelled(err)) return;
      const errObj = err as { message?: string; detail?: string };
      setErrorMessage(errObj.detail ?? errObj.message ?? 'Failed to update member role.');
    }
  };

  const handleRemoveMember = async (principalId: string, role?: string): Promise<void> => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const csrf = await ensureSessionCsrfToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (csrf) headers['X-CSRF-Token'] = csrf;

      const member = principals.find((p) => p.id === principalId);
      const memberRole = role ?? member?.role ?? member?.role_name ?? 'WORKSPACE_MEMBER';

      await apiFetch('DELETE', '/api/v1/admin/role-bindings' as never, {
        headers,
        body: JSON.stringify({
          principal_id: principalId,
          role: memberRole,
          scope_type: 'workspace',
        }),
      });
      setSuccessMessage('Member removed from workspace.');
      setPrincipals((prev) => prev.filter((p) => p.id !== principalId));
    } catch (err: unknown) {
      /* v8 ignore next */
      if (isAal2StepUpCancelled(err)) return;
      const errObj = err as { message?: string; detail?: string };
      setErrorMessage(errObj.detail ?? errObj.message ?? 'Failed to remove workspace member.');
    }
  };

  const handleCreateGroup = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!newGroupName.trim() || !newGroupHandle.trim()) return;
    void (async () => {
      setIsCreatingGroup(true);
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const cleanHandle = newGroupHandle.startsWith('@')
          ? newGroupHandle.trim()
          : `@${newGroupHandle.trim()}`;

        const created = (await apiFetch('POST', '/api/v1/admin/principals' as never, {
          headers,
          body: JSON.stringify({
            type: 'GROUP',
            handle: cleanHandle,
            display_name: newGroupName.trim(),
          }),
        })) as { id: string };

        setNewGroupName('');
        setNewGroupHandle('');
        setSuccessMessage('Group created successfully.');
        if (created.id) {
          setSelectedGroupId(created.id);
        }
        await refreshPrincipals();
      } catch (err: unknown) {
        /* v8 ignore next */
        if (isAal2StepUpCancelled(err)) return;
        const errObj = err as { message?: string; detail?: string };
        setErrorMessage(errObj.detail ?? errObj.message ?? 'Failed to create group.');
      } finally {
        setIsCreatingGroup(false);
      }
    })();
  };

  const handleAddGroupMember = async (groupId: string, memberId: string): Promise<void> => {
    /* v8 ignore next */
    if (!memberId) return;
    setGroupActionError(null);
    try {
      const csrf = await ensureSessionCsrfToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (csrf) headers['X-CSRF-Token'] = csrf;

      await apiFetch('POST', `/api/v1/admin/groups/${groupId}/members/${memberId}` as never, {
        headers,
      });
      setSuccessMessage('Member added to group successfully.');
      setSelectedAddMemberId('');
      void loadGroupMembers(groupId);
    } catch (err: unknown) {
      /* v8 ignore next */
      if (isAal2StepUpCancelled(err)) return;
      const errObj = err as { message?: string; detail?: string; code?: string };
      const msg =
        errObj.detail ??
        errObj.message ??
        'Cannot nest group: would introduce a cyclic dependency.';
      setGroupActionError(msg);
    }
  };

  const handleRemoveGroupMember = async (groupId: string, memberId: string): Promise<void> => {
    setGroupActionError(null);
    try {
      const csrf = await ensureSessionCsrfToken();
      const headers: Record<string, string> = {};
      if (csrf) headers['X-CSRF-Token'] = csrf;

      await apiFetch('DELETE', `/api/v1/admin/groups/${groupId}/members/${memberId}` as never, {
        headers,
      });
      setSuccessMessage('Member removed from group.');
      void loadGroupMembers(groupId);
    } catch (err: unknown) {
      /* v8 ignore next */
      if (isAal2StepUpCancelled(err)) return;
      const errObj = err as { message?: string; detail?: string };
      setGroupActionError(errObj.detail ?? errObj.message ?? 'Failed to remove group member.');
    }
  };

  if (isLoading) {
    return (
      <div data-testid="workspace-settings-page" className="kb-settings-container">
        <div className="kb-settings-loading">Loading workspace settings...</div>
      </div>
    );
  }

  if (currentUser && !isWsOrServerAdmin && !isProjectAdminOnly) {
    return (
      <div data-testid="workspace-settings-page" className="kb-settings-container">
        <div data-testid="access-denied-message" className="kb-settings-alert kb-settings-alert-error" role="alert">
          <h2>Not found or no access</h2>
          <p>You do not have administrative privileges to manage this workspace.</p>
        </div>
      </div>
    );
  }

  const groupsList = principals.filter(
    (p) => (p.principal_type ?? p.type ?? '').toUpperCase() === 'GROUP',
  );
  const selectedGroup = groupsList.find((g) => g.id === selectedGroupId) ?? groupsList[0] ?? null;

  return (
    <div data-testid="workspace-settings-page" className="kb-settings-container">
      <header className="kb-settings-header">
        <div>
          <h1 className="kb-settings-title">Workspace Settings</h1>
          <p className="kb-settings-subtitle">Configure organization policies, membership, and workspace integrations.</p>
        </div>
        <StudioDocLink
          href="/docs/role-and-permission-matrix"
          title="Workspace Settings Documentation"
          testId="workspace-settings-doc-link"
        />
      </header>

      {errorMessage && (
        <div className="kb-settings-alert kb-settings-alert-error" role="alert">
          {errorMessage}
        </div>
      )}

      {successMessage && (
        <div className="kb-settings-alert kb-settings-alert-success" role="status">
          {successMessage}
        </div>
      )}

      {/* Tabs */}
      <nav className="kb-settings-tabs" role="tablist" aria-label="Workspace Settings Navigation">
        {isWsOrServerAdmin && (
          <>
            <button
              type="button"
              role="tab"
              id="tab-general"
              aria-selected={activeTab === 'general'}
              data-testid="tab-general"
              className={`kb-settings-tab ${activeTab === 'general' ? 'kb-settings-tab-active' : ''}`}
              onClick={() => { handleTabChange('general'); }}
            >
              General & Policy
            </button>
            <button
              type="button"
              role="tab"
              id="tab-members"
              aria-selected={activeTab === 'members'}
              data-testid="tab-members"
              className={`kb-settings-tab ${activeTab === 'members' ? 'kb-settings-tab-active' : ''}`}
              onClick={() => { handleTabChange('members'); }}
            >
              Workspace Members
            </button>
            <button
              type="button"
              role="tab"
              id="tab-groups"
              aria-selected={activeTab === 'groups'}
              data-testid="tab-groups"
              className={`kb-settings-tab ${activeTab === 'groups' ? 'kb-settings-tab-active' : ''}`}
              onClick={() => { handleTabChange('groups'); }}
            >
              Groups & Governance
            </button>
            <button
              type="button"
              role="tab"
              id="tab-roles"
              aria-selected={activeTab === 'roles'}
              data-testid="tab-roles"
              className={`kb-settings-tab ${activeTab === 'roles' ? 'kb-settings-tab-active' : ''}`}
              onClick={() => { handleTabChange('roles'); }}
            >
              Roles &amp; Permissions
            </button>
            <button
              type="button"
              role="tab"
              id="tab-ai"
              aria-selected={activeTab === 'ai'}
              data-testid="tab-ai"
              className={`kb-settings-tab ${activeTab === 'ai' ? 'kb-settings-tab-active' : ''}`}
              onClick={() => { handleTabChange('ai'); }}
            >
              AI Providers
            </button>
            <button
              type="button"
              role="tab"
              id="tab-agents"
              aria-selected={activeTab === 'agents'}
              data-testid="tab-agents"
              className={`kb-settings-tab ${activeTab === 'agents' ? 'kb-settings-tab-active' : ''}`}
              onClick={() => { handleTabChange('agents'); }}
            >
              Autonomous Agents
            </button>
          </>
        )}
        <button
          type="button"
          role="tab"
          id="tab-trash"
          aria-selected={activeTab === 'trash'}
          data-testid="tab-trash"
          className={`kb-settings-tab ${activeTab === 'trash' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { handleTabChange('trash'); }}
        >
          Trash &amp; Retention
        </button>
      </nav>

      <div className="kb-settings-panel">
        {activeTab === 'general' && (
          <form onSubmit={handleSaveGeneral} className="kb-settings-form" data-testid="workspace-general-form">
            <div className="kb-form-group">
              <label htmlFor="ws-name-input">
                Workspace Name
                <FieldHelpHint
                  title="Workspace Name"
                  summary="Human-readable organization workspace name shown in headers and navigation."
                  defaultValue="kanban"
                  docHref="/docs/studio-configuration-reference"
                  testId="ws-name-help"
                />
              </label>
              <input
                id="ws-name-input"
                type="text"
                data-testid="workspace-name-input"
                className="kb-input"
                value={name}
                onChange={(e) => { setName(e.target.value); }}
                required
              />
            </div>

            <div className="kb-form-group">
              <label htmlFor="ws-slug-input">
                Workspace Slug
                <FieldHelpHint
                  title="Workspace Slug"
                  summary="URL-safe lowercase identifier slug for workspace routes and API calls."
                  defaultValue="kanban"
                  validValues={['Lowercase letters, digits, and hyphens (a-z0-9-)']}
                  docHref="/docs/studio-configuration-reference"
                  testId="ws-slug-help"
                />
              </label>
              <input
                id="ws-slug-input"
                type="text"
                data-testid="workspace-slug-input"
                className="kb-input"
                value={slug}
                onChange={(e) => { setSlug(e.target.value); }}
                required
              />
            </div>

            <div className="kb-form-group">
              <label htmlFor="ws-display-name-input">
                Display Name
                <FieldHelpHint
                  title="Display Name"
                  summary="Optional public-facing organization display name."
                  defaultValue="Same as Workspace Name"
                  docHref="/docs/studio-configuration-reference"
                  testId="ws-display-name-help"
                />
              </label>
              <input
                id="ws-display-name-input"
                type="text"
                data-testid="workspace-display-name-input"
                className="kb-input"
                placeholder="Public organization display name"
                value={displayName}
                onChange={(e) => { setDisplayName(e.target.value); }}
              />
            </div>

            <div className="kb-form-group">
              <label htmlFor="ws-visibility-select">
                Default Project Visibility
                <FieldHelpHint
                  title="Default Project Visibility"
                  summary="Controls whether newly created projects default to workspace-wide visibility or strict private access."
                  defaultValue="Workspace (All members can view)"
                  validValues={[
                    { label: 'Workspace', description: 'All members of the workspace can discover and view by default.' },
                    { label: 'Private', description: 'Restricted strictly to explicitly invited members.' },
                  ]}
                  docHref="/docs/role-and-permission-matrix#workspace-level-roles"
                  testId="ws-visibility-help"
                />
              </label>
              <select
                id="ws-visibility-select"
                data-testid="workspace-visibility-select"
                className="kb-select"
                value={defaultVisibility}
                onChange={(e) => { setDefaultVisibility(e.target.value as 'private' | 'workspace'); }}
              >
                <option value="workspace">Workspace (All members can view)</option>
                <option value="private">Private (Explicit members only)</option>
              </select>
            </div>

            {/* Advanced Security & Governance (Progressive Disclosure - KAN-370) */}
            <AdvancedSection
              title="Advanced Security & Governance"
              summary="Granular field-level overrides, session idle and absolute TTLs, key lifetimes, air-gap mode, and export/webhook restrictions"
              testId="workspace-advanced-security-section"
              defaultOpen={false}
            >
              <div className="kb-form-group" data-testid="workspace-field-level-overrides">
                <label className="kb-label">
                  Granular Field-Level Override Rules
                  <FieldHelpHint
                    title="Granular Field-Level Override Rules"
                    summary="Configure custom permission overrides on individual issue and project attributes."
                    defaultValue="Strict workspace inheritance enabled"
                    docHref="/docs/role-and-permission-matrix#workspace-level-roles"
                    testId="ws-field-override-help"
                  />
                </label>
                <p className="kb-field-desc">
                  Strict workspace inheritance enabled. Role-based field override rules apply globally across member issues.
                </p>
              </div>

              <div className="kb-form-group">
                <label htmlFor="ws-idle-timeout-input">
                  Session Idle Timeout (Minutes, Default: 30)
                  <FieldHelpHint
                    title="Session Idle Timeout"
                    summary="Minutes of user inactivity before the session is expired and re-authentication is enforced."
                    defaultValue="30 minutes"
                    validValues={['5 to 1440 minutes (Minimum: 5 minutes)']}
                    docHref="/docs/multi-card-authentication-studio"
                    testId="ws-idle-timeout-help"
                  />
                </label>
                <div className="kb-duration-input-wrapper">
                  <input
                    id="ws-idle-timeout-input"
                    type="number"
                    data-testid="workspace-idle-timeout-input"
                    className="kb-input"
                    min="5"
                    value={idleTimeout}
                    onChange={(e) => { setIdleTimeout(Number(e.target.value)); }}
                    required
                  />
                  <span className="kb-readable-duration" data-testid="idle-readable-duration">
                    {formatIdleDuration(idleTimeout)}
                  </span>
                </div>
                <div className="kb-preset-pills" data-testid="idle-preset-pills">
                  {[
                    { label: '15m', value: 15 },
                    { label: '30m', value: 30 },
                    { label: '1h', value: 60 },
                    { label: '4h', value: 240 },
                  ].map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      className={`kb-preset-pill ${idleTimeout === preset.value ? 'kb-preset-pill-active' : ''}`}
                      data-testid={`idle-preset-${preset.label}`}
                      onClick={() => { setIdleTimeout(preset.value); }}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="kb-form-group">
                <label htmlFor="ws-abs-timeout-input">
                  Session Absolute Timeout (Minutes, Default: 480)
                  <FieldHelpHint
                    title="Session Absolute Timeout"
                    summary="Maximum lifetime of an authenticated browser session in minutes before mandatory re-login, regardless of activity."
                    defaultValue="480 minutes (8 hours)"
                    validValues={['60 to 43200 minutes (Minimum: 60 minutes)']}
                    docHref="/docs/multi-card-authentication-studio"
                    testId="ws-abs-timeout-help"
                  />
                </label>
                <div className="kb-duration-input-wrapper">
                  <input
                    id="ws-abs-timeout-input"
                    type="number"
                    data-testid="workspace-abs-timeout-input"
                    className="kb-input"
                    min="60"
                    value={absTimeout}
                    onChange={(e) => { setAbsTimeout(Number(e.target.value)); }}
                    required
                  />
                  <span className="kb-readable-duration" data-testid="abs-readable-duration">
                    {formatAbsoluteDuration(absTimeout)}
                  </span>
                </div>
                <div className="kb-preset-pills" data-testid="abs-preset-pills">
                  {[
                    { label: '8h', value: 480 },
                    { label: '24h', value: 1440 },
                    { label: '7d', value: 10080 },
                  ].map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      className={`kb-preset-pill ${absTimeout === preset.value ? 'kb-preset-pill-active' : ''}`}
                      data-testid={`abs-preset-${preset.label}`}
                      onClick={() => { setAbsTimeout(preset.value); }}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="kb-form-group">
                <label htmlFor="ws-trash-retention-input">
                  Trash Retention Days (Default: 30)
                  <FieldHelpHint
                    title="Trash Retention Days"
                    summary="Number of days soft-deleted projects, issues, docs, and stickies remain restorable in workspace trash before automated permanent sweep. Updating this policy requires a fresh AAL2 (2FA) session."
                    defaultValue="30 days"
                    validValues={['7 to 365 days']}
                    docHref="/docs/production-promotion-and-backup-runbook"
                    testId="ws-trash-retention-help"
                  />
                </label>
                <input
                  id="ws-trash-retention-input"
                  type="number"
                  data-testid="workspace-trash-retention-input"
                  className="kb-input"
                  min="7"
                  max="365"
                  value={trashRetention}
                  onChange={(e) => { setTrashRetention(Number(e.target.value)); }}
                  required
                />
              </div>

              <div className="kb-form-group">
                <label htmlFor="ws-mcp-key-max-ttl-input">
                  MCP Key Max TTL (Days, Default: 90)
                  <FieldHelpHint
                    title="MCP Key Max TTL (Days)"
                    summary="Maximum allowed expiration lifetime in days for newly minted Model Context Protocol (MCP) access keys in this workspace."
                    defaultValue="90 days"
                    validValues={['1 to 365 days']}
                    docHref="/docs/three-surface-mcp-server-architecture#scope-tiers"
                    testId="ws-mcp-key-ttl-help"
                  />
                </label>
                <input
                  id="ws-mcp-key-max-ttl-input"
                  type="number"
                  data-testid="workspace-mcp-key-max-ttl-input"
                  className="kb-input"
                  min="1"
                  max="365"
                  value={mcpKeyMaxTtl}
                  onChange={(e) => { setMcpKeyMaxTtl(Number(e.target.value)); }}
                  required
                />
              </div>

              <div className="kb-form-group kb-form-group-toggle">
                <label htmlFor="ws-air-gap-toggle" className="kb-toggle-label">
                  <input
                    id="ws-air-gap-toggle"
                    type="checkbox"
                    data-testid="workspace-air-gap-toggle"
                    className="kb-checkbox"
                    checked={airGapMode}
                    onChange={(e) => { setAirGapMode(e.target.checked); }}
                  />
                  <span className="kb-toggle-text">
                    📴 Air-Gap Mode (Strict local execution; disables external outbound telemetry)
                  </span>
                  <FieldHelpHint
                    title="Air-Gap Mode"
                    summary="Disables all outbound external network egress, telemetry, and external SaaS AI providers."
                    defaultValue="Disabled (false)"
                    caution="External AI integrations requiring internet access will fail while Air-Gap mode is enabled."
                    docHref="/docs/zero-trust-security-and-access-visibility"
                    testId="ws-air-gap-help"
                  />
                </label>
              </div>

              <div className="kb-form-group kb-form-group-toggle">
                <label htmlFor="ws-default-skip-loaded-seq" className="kb-toggle-label">
                  <input
                    id="ws-default-skip-loaded-seq"
                    type="checkbox"
                    data-testid="workspace-default-skip-loaded-seq-checkbox"
                    className="kb-checkbox"
                    checked={defaultSkipLoadedSeq}
                    onChange={(e) => { setDefaultSkipLoadedSeq(e.target.checked); }}
                  />
                  <span className="kb-toggle-text">
                    Agent-Safe Sequence Numbering (skip 13, 69, 88, 404, 420, 666, 1337, 1488)
                  </span>
                  <FieldHelpHint
                    title="Agent-Safe Sequence Numbering"
                    summary="Automatically skips culturally or technically ambiguous sequence numbers (13, 69, 88, 404, 420, 666, 1337, 1488) when allocating new ticket keys."
                    defaultValue="Enabled (true)"
                    docHref="/docs/ticket-screen-and-work-item-features"
                    testId="ws-skip-seq-help"
                  />
                </label>
              </div>

              <div className="kb-form-group kb-form-group-toggle">
                <label htmlFor="ws-issue-export-toggle" className="kb-toggle-label">
                  <input
                    id="ws-issue-export-toggle"
                    type="checkbox"
                    data-testid="workspace-setting-issue-export-toggle"
                    className="kb-checkbox"
                    checked={issueExportEnabled}
                    onChange={(e) => {
                      /* v8 ignore next */
                      setIssueExportEnabled(e.target.checked);
                    }}
                  />
                  <span className="kb-toggle-text">
                    Enable Issue Export (Allow exporting issues to CSV / Password-Protected ZIP)
                  </span>
                  <FieldHelpHint
                    title="Enable Issue Export"
                    summary="Allows authorized workspace roles to export work items to CSV or AES-256 password-protected ZIP archives."
                    defaultValue="Enabled (true)"
                    docHref="/docs/zero-trust-security-and-access-visibility"
                    testId="ws-issue-export-help"
                  />
                </label>
              </div>

              <div className="kb-form-group kb-form-group-toggle">
                <label htmlFor="ws-issue-import-toggle" className="kb-toggle-label">
                  <input
                    id="ws-issue-import-toggle"
                    type="checkbox"
                    data-testid="workspace-setting-issue-import-toggle"
                    className="kb-checkbox"
                    checked={issueImportEnabled}
                    onChange={(e) => {
                      /* v8 ignore next */
                      setIssueImportEnabled(e.target.checked);
                    }}
                  />
                  <span className="kb-toggle-text">
                    Enable Issue Import (Allow importing issues from CSV / Password-Protected ZIP)
                  </span>
                  <FieldHelpHint
                    title="Enable Issue Import"
                    summary="Allows authorized administrators to import work items from CSV or password-protected ZIP bundles."
                    defaultValue="Enabled (true)"
                    docHref="/docs/migration-and-cutover-runbook"
                    testId="ws-issue-import-help"
                  />
                </label>
              </div>

              <div className="kb-form-group" data-testid="workspace-setting-export-roles">
                <label className="kb-label">
                  Allowed Issue Export Roles
                  <FieldHelpHint
                    title="Allowed Issue Export Roles"
                    summary="Selects which workspace roles are permitted to trigger bulk CSV/ZIP issue exports when Issue Export is enabled."
                    defaultValue="Workspace Admin, Project Admin, Member"
                    docHref="/docs/role-and-permission-matrix"
                    testId="ws-export-roles-help"
                  />
                </label>
                <div className="kb-roles-checklist">
                  {[
                    { role: 'workspace_admin', label: 'Workspace Admin' },
                    { role: 'project_admin', label: 'Project Admin' },
                    { role: 'member', label: 'Member' },
                    { role: 'guest', label: 'Guest' },
                  ].map(({ role, label }) => {
                    const isChecked = issueExportAllowedRoles.includes(role);
                    return (
                      <label key={role} className="kb-checkbox-inline" htmlFor={`export-role-${role}`}>
                        <input
                          type="checkbox"
                          id={`export-role-${role}`}
                          aria-label={`Allowed export role ${label}`}
                          checked={isChecked}
                          value={role}
                          onChange={(e) => {
                            /* v8 ignore next 6 */
                            if (e.target.checked) {
                              setIssueExportAllowedRoles((prev) => [...prev, role]);
                            } else {
                              setIssueExportAllowedRoles((prev) => prev.filter((r) => r !== role));
                            }
                          }}
                        />
                        <span>{label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="kb-settings-info-card kb-webhook-restrictions-card" data-testid="workspace-webhook-restrictions">
                <div className="kb-card-header-with-badge">
                  <span className="kb-security-icon">🔒</span>
                  <label className="kb-label kb-card-title">
                    Webhook &amp; Egress Restrictions
                    <FieldHelpHint
                      title="Webhook Restrictions"
                      summary="Restrict outbound webhook notifications to pinned endpoints and signed payloads."
                      defaultValue="HMAC SHA-256 payload signing required"
                      docHref="/docs/zero-trust-security-and-access-visibility"
                      testId="ws-webhook-help"
                    />
                  </label>
                </div>
                <p className="kb-field-desc">
                  Outbound webhook deliveries require HMAC SHA-256 payload signing and strict endpoint pinning. Outbound internet egress is restricted under zero-trust governance.
                </p>
                <div className="kb-doc-link-wrapper">
                  <Link
                    to="/docs/zero-trust-security-and-access-visibility"
                    className="kb-link kb-doc-link"
                    data-testid="webhook-restrictions-doc-link"
                  >
                    📖 Read Zero-Trust Security &amp; Access Visibility Guide
                  </Link>
                </div>
              </div>
            </AdvancedSection>

            <button
              type="submit"
              data-testid="save-workspace-btn"
              className="kb-btn kb-btn-primary"
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : 'Save Workspace Settings'}
            </button>

            <div className="kb-integrations-grid" data-testid="workspace-mcp-section">
              <Link
                to="/settings/mcp?scope=workspace"
                className="kb-integration-card"
                data-testid="link-workspace-mcp"
              >
                <div className="kb-card-icon">🏢</div>
                <div className="kb-card-content">
                  <h3>Workspace MCP Access Keys</h3>
                  <p>Manage organization-level Model Context Protocol API tokens and client credentials.</p>
                </div>
              </Link>
            </div>
          </form>
        )}

        {activeTab === 'members' && (
          <div className="kb-members-section" data-testid="workspace-members-section">
            <form onSubmit={handleCreateUser} className="kb-add-member-form" data-testid="create-user-form" noValidate>
              <h3>+ Add Workspace User</h3>
              <div className="kb-form-group">
                <label htmlFor="new-user-handle" className="kb-visually-hidden">
                  User handle
                </label>
                <input
                  type="text"
                  id="new-user-handle"
                  aria-label="User handle"
                  data-testid="new-user-handle"
                  className="kb-input"
                  placeholder="@handle"
                  value={newHandle}
                  onChange={(e) => { setNewHandle(e.target.value); }}
                  required
                />
              </div>
              <div className="kb-form-group">
                <label htmlFor="new-user-name" className="kb-visually-hidden">
                  User display name
                </label>
                <input
                  type="text"
                  id="new-user-name"
                  aria-label="User display name"
                  data-testid="new-user-name"
                  className="kb-input"
                  placeholder="Full Name / Display Name"
                  value={newDisplayName}
                  onChange={(e) => { setNewDisplayName(e.target.value); }}
                  required
                />
              </div>
              <div className="kb-form-group">
                <label htmlFor="new-user-email" className="kb-visually-hidden">
                  User email
                </label>
                <input
                  type="email"
                  id="new-user-email"
                  aria-label="User email"
                  data-testid="new-user-email"
                  className="kb-input"
                  placeholder="email@example.com"
                  value={newEmail}
                  onChange={(e) => { setNewEmail(e.target.value); }}
                  required
                />
              </div>
              <div className="kb-form-group">
                <label htmlFor="new-user-password" className="kb-visually-hidden">
                  Initial password
                </label>
                <input
                  type="password"
                  id="new-user-password"
                  aria-label="Initial password"
                  data-testid="new-user-password"
                  className="kb-input"
                  placeholder="Initial Password (optional)"
                  value={newPassword}
                  onChange={(e) => { setNewPassword(e.target.value); }}
                />
              </div>
              <div className="kb-form-row">
                <label htmlFor="new-user-role-select" className="kb-visually-hidden">
                  User role
                </label>
                <select
                  id="new-user-role-select"
                  aria-label="New user role"
                  data-testid="new-user-role-select"
                  className="kb-select"
                  value={newRole}
                  onChange={(e) => { setNewRole(e.target.value as 'WORKSPACE_MEMBER' | 'WORKSPACE_GUEST' | 'WORKSPACE_ADMIN'); }}
                >
                  <option value="WORKSPACE_MEMBER">WORKSPACE_MEMBER (Standard)</option>
                  <option value="WORKSPACE_GUEST">WORKSPACE_GUEST (Restricted)</option>
                  <option value="WORKSPACE_ADMIN">WORKSPACE_ADMIN (Admin)</option>
                </select>
                <button
                  type="submit"
                  data-testid="create-user-submit-btn"
                  className="kb-btn kb-btn-primary"
                  disabled={isCreatingUser}
                >
                  {isCreatingUser ? 'Creating...' : 'Create User'}
                </button>
              </div>
            </form>

            <div className="kb-members-table-wrapper">
              <h3>Workspace Users & Principals</h3>
              <div className="kb-table-scroll-container">
                <table className="kb-table" data-testid="workspace-users-table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Email</th>
                    <th>Type</th>
                    <th>Role Grant</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {principals.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="kb-empty-cell">No users registered in this workspace.</td>
                    </tr>
                  ) : (
                    principals.map((p) => {
                      const pType = (p.principal_type ?? p.type ?? 'USER').toUpperCase();
                      const typeClass = pType.toLowerCase();
                      return (
                        <tr key={p.id} data-testid={`principal-row-${p.id}`}>
                          <td data-label="User">
                            <div className="kb-member-info">
                              <span className="kb-member-name" data-testid={`member-name-${p.id}`}>
                                {p.display_name ?? ((p.handle ?? p.principal) ? formatHandle(p.handle ?? p.principal) : p.id)}
                              </span>
                              {p.display_name && (p.handle ?? p.principal) && (
                                <span className="kb-member-handle" data-testid={`member-handle-${p.id}`}>
                                  {formatHandle(p.handle ?? p.principal)}
                                </span>
                              )}
                            </div>
                          </td>
                          <td data-label="Email">
                            <span className="kb-member-email" data-testid={`member-email-${p.id}`}>
                              {p.email ?? '-'}
                            </span>
                          </td>
                          <td data-label="Type">
                            <span
                              className={`kb-type-pill kb-type-pill--${typeClass}`}
                              data-testid={`type-pill-${p.id}`}
                            >
                              {pType.charAt(0) + pType.slice(1).toLowerCase()}
                            </span>
                          </td>
                          <td data-label="Role Grant">
                            <select
                              data-testid={`role-select-${p.id}`}
                              aria-label={`Role for ${p.display_name ?? p.handle ?? p.principal ?? p.id}`}
                              className="kb-select kb-member-role-select"
                              value={p.role ?? p.role_name ?? 'WORKSPACE_MEMBER'}
                              onChange={(e) => {
                                void handleUpdateRole(p.id, e.target.value);
                              }}
                            >
                              <option value="WORKSPACE_ADMIN">WORKSPACE_ADMIN</option>
                              <option value="WORKSPACE_MEMBER">WORKSPACE_MEMBER</option>
                              <option value="WORKSPACE_GUEST">WORKSPACE_GUEST</option>
                            </select>
                            <RoleLabelPicker principalId={p.id} />
                          </td>
                          <td data-label="Actions">
                            <button
                              type="button"
                              data-testid={`remove-member-btn-${p.id}`}
                              className="kb-btn kb-btn-danger-subtle"
                              onClick={() => {
                                void handleRemoveMember(p.id, p.role ?? p.role_name ?? undefined);
                              }}
                            >
                              Remove
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'groups' && (
          <div className="kb-groups-section" data-testid="workspace-groups-section">
            <div className="kb-groups-header-row">
              <h3>Administrative Groups & Hierarchy</h3>
              <p className="kb-settings-subtitle">
                Manage group membership and nested groups. Cycles are cryptographically rejected by the database.
              </p>
            </div>

            {/* Create Group Form */}
            <form onSubmit={handleCreateGroup} className="kb-add-group-form" data-testid="create-group-form">
              <h4>+ Create Group</h4>
              <div className="kb-form-row">
                <label htmlFor="new-group-name" className="kb-visually-hidden">
                  Group name
                </label>
                <input
                  type="text"
                  id="new-group-name"
                  aria-label="Group name"
                  data-testid="new-group-name"
                  className="kb-input"
                  placeholder="Group Name (e.g. Core Engineers)"
                  value={newGroupName}
                  onChange={(e) => { setNewGroupName(e.target.value); }}
                  required
                />
                <label htmlFor="new-group-handle" className="kb-visually-hidden">
                  Group handle
                </label>
                <input
                  type="text"
                  id="new-group-handle"
                  aria-label="Group handle"
                  data-testid="new-group-handle"
                  className="kb-input"
                  placeholder="@handle"
                  value={newGroupHandle}
                  onChange={(e) => { setNewGroupHandle(e.target.value); }}
                  required
                />
                <button
                  type="submit"
                  data-testid="create-group-btn"
                  className="kb-btn kb-btn-primary"
                  disabled={isCreatingGroup}
                >
                  {isCreatingGroup ? 'Creating...' : 'Create Group'}
                </button>
              </div>
            </form>

            <div className="kb-groups-layout">
              {/* Groups List */}
              <div className="kb-groups-list-sidebar">
                <h4>Groups ({groupsList.length})</h4>
                {groupsList.length === 0 ? (
                  <p className="kb-empty-cell">No groups created yet.</p>
                ) : (
                  <div className="kb-groups-list" role="list">
                    {groupsList.map((g) => {
                      const isSelected = selectedGroup?.id === g.id;
                      return (
                        <button
                          key={g.id}
                          type="button"
                          data-testid={`group-item-${g.id}`}
                          className={`kb-group-item ${isSelected ? 'kb-group-item-active' : ''}`}
                          onClick={() => { setSelectedGroupId(g.id); }}
                        >
                          <span className="kb-group-item-name">{g.display_name ?? g.handle ?? g.principal ?? g.id}</span>
                          <span className="kb-group-item-handle">{formatHandle(g.handle ?? g.principal ?? g.id)}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Selected Group Drill-down */}
              <div className="kb-groups-detail-pane" data-testid="group-detail-pane">
                {selectedGroup ? (
                  <>
                    <div className="kb-group-detail-header">
                      <div>
                        <h4 data-testid="selected-group-name">{selectedGroup.display_name ?? selectedGroup.handle ?? selectedGroup.principal}</h4>
                        <span className="kb-group-detail-handle" data-testid="selected-group-handle">
                          {formatHandle(selectedGroup.handle ?? selectedGroup.principal ?? selectedGroup.id)}
                        </span>
                      </div>
                    </div>

                    {groupActionError && (
                      <div data-testid="group-cycle-alert" id="group-cycle-alert" className="kb-settings-alert kb-settings-alert-error" role="alert">
                        <span>{groupActionError}</span>
                        {/cycle/i.test(groupActionError) && (
                          <span className="kb-badge kb-badge-error" data-testid="group-cycle-pill" style={{ marginLeft: '8px' }}>
                            Cycle Detected
                          </span>
                        )}
                      </div>
                    )}

                    {/* Add Member / Nested Group */}
                    <div className="kb-add-group-member-box">
                      <h5>Add Member or Nested Group</h5>
                      <div className="kb-form-row">
                        <label htmlFor="add-group-member-select" className="kb-visually-hidden">
                          Select a user, agent, or group to nest
                        </label>
                        <select
                          id="add-group-member-select"
                          aria-label="Select a user, agent, or group to nest"
                          aria-invalid={Boolean(groupActionError)}
                          aria-describedby={groupActionError ? 'group-cycle-alert' : undefined}
                          data-testid="add-group-member-select"
                          className="kb-select"
                          value={selectedAddMemberId}
                          onChange={(e) => { setSelectedAddMemberId(e.target.value); }}
                        >
                          <option value="">Select a user, agent, or group to nest...</option>
                          {principals
                            .filter((p) => p.id !== selectedGroup.id)
                            .map((p) => {
                              const pType = (p.principal_type ?? p.type ?? 'USER').toUpperCase();
                              return (
                                <option key={p.id} value={p.id}>
                                  [{pType}] {p.display_name ?? p.handle ?? p.principal ?? p.id} ({formatHandle(p.handle ?? p.principal ?? p.id)})
                                </option>
                              );
                            })}
                        </select>
                        <button
                          type="button"
                          data-testid="add-group-member-btn"
                          className="kb-btn kb-btn-primary"
                          disabled={!selectedAddMemberId || selectedAddMemberId === selectedGroup.id}
                          onClick={() => {
                            void handleAddGroupMember(selectedGroup.id, selectedAddMemberId);
                          }}
                        >
                          Add to Group
                        </button>
                      </div>
                    </div>

                    {/* Members List */}
                    <div className="kb-group-members-table-wrapper">
                      <h5>Group Members ({groupMembers.length})</h5>
                      {isLoadingGroupMembers ? (
                        <div className="kb-settings-loading">Loading members...</div>
                      ) : groupMembers.length === 0 ? (
                        <p className="kb-empty-cell" data-testid="empty-group-members">
                          No direct members or nested groups in this group.
                        </p>
                      ) : (
                        <div className="kb-table-scroll-container">
                          <table className="kb-table" data-testid="group-members-table">
                            <thead>
                              <tr>
                                <th>Principal</th>
                                <th>Type</th>
                                <th>Actions</th>
                              </tr>
                            </thead>
                            <tbody>
                              {groupMembers.map((m) => {
                                const mType = (m.principal_type ?? m.type ?? 'USER').toUpperCase();
                                const isNestedGroup = mType === 'GROUP';
                                return (
                                  <tr key={m.id} data-testid={`group-member-row-${m.id}`}>
                                    <td data-label="Principal">
                                      <div className="kb-member-info">
                                        <span className="kb-member-name">
                                          {m.display_name ?? formatHandle(m.handle ?? m.principal ?? m.id)}
                                        </span>
                                        {m.display_name && (
                                          <span className="kb-member-handle">
                                            {formatHandle(m.handle ?? m.principal ?? m.id)}
                                          </span>
                                        )}
                                      </div>
                                    </td>
                                    <td data-label="Type">
                                      <span
                                        className={`kb-type-pill kb-type-pill--${mType.toLowerCase()}`}
                                        data-testid={`group-member-type-${m.id}`}
                                      >
                                        {isNestedGroup ? 'Nested Group' : mType.charAt(0) + mType.slice(1).toLowerCase()}
                                      </span>
                                      {groupActionError && /cycle/i.test(groupActionError) && m.id === selectedAddMemberId && (
                                        <span className="kb-badge kb-badge-error" data-testid="group-cycle-pill" style={{ marginLeft: '6px' }}>
                                          Cycle Detected
                                        </span>
                                      )}
                                    </td>
                                    <td data-label="Actions">
                                      <button
                                        type="button"
                                        data-testid={`remove-group-member-${m.id}`}
                                        className="kb-btn kb-btn-danger-subtle"
                                        onClick={() => {
                                          void handleRemoveGroupMember(selectedGroup.id, m.id);
                                        }}
                                      >
                                        Remove
                                      </button>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="kb-empty-cell">Select or create a group to view and manage membership.</div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'roles' && (
          <div className="kb-roles-section" data-testid="workspace-roles-section">
            <RbacPolicyBuilder
              isServerAdmin={Boolean(currentUser?.is_server_admin)}
              workspaceId={settings?.workspace_id ?? settings?.id}
            />
          </div>
        )}

        {activeTab === 'ai' && (
          <div data-testid="workspace-ai-section">
            <AiStudioPage showSubnav={false} />
          </div>
        )}

        {activeTab === 'agents' && (
          <div data-testid="workspace-agents-section">
            <AgentStudioPage />
          </div>
        )}

        {activeTab === 'trash' && (
          <div className="kb-members-section" data-testid="workspace-trash-studio">
            <div className="kb-settings-header">
              <h2 className="kb-settings-title">Workspace Trash &amp; Retention Studio</h2>
              <p className="kb-settings-subtitle">
                Manage retention policies, browse soft-deleted workspace items, restore entities, or execute permanent purges.
              </p>
            </div>

            {trashActionError && (
              <div className="kb-settings-alert kb-settings-alert-error" role="alert">
                {trashActionError}
              </div>
            )}

            {trashActionSuccess && (
              <div className="kb-settings-alert kb-settings-alert-success" role="status">
                {trashActionSuccess}
              </div>
            )}

            {/* Retention Policy Card */}
            <div className="kb-retention-settings-card" data-testid="workspace-trash-retention-card">
              <h3 className="kb-settings-title">Retention Policy</h3>
              <p className="kb-settings-subtitle">
                Soft-deleted items are retained for <strong>{trashRetention} days</strong> before automated background sweep. Retention duration is configured on the{' '}
                <button
                  type="button"
                  className="kb-link-btn"
                  onClick={() => { handleTabChange('general'); }}
                >
                  General tab
                </button>.
              </p>
            </div>

            {/* Toolbar: Filter Pills + Search */}
            <div className="kb-trash-toolbar">
              <div className="kb-trash-filters">
                {['all', 'project', 'issue', 'doc', 'page', 'sticky', 'cycle', 'module', 'view'].map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    data-testid={`trash-filter-${kind}`}
                    className={`kb-trash-filter-btn ${trashKindFilter === kind ? 'kb-trash-filter-btn-active' : ''}`}
                    onClick={() => { setTrashKindFilter(kind); }}
                  >
                    {TRASH_FILTER_LABELS[kind]}
                  </button>
                ))}
              </div>
              <div className="kb-trash-search-box">
                <label htmlFor="trash-search-input" className="kb-visually-hidden">
                  Search trashed items by key or title
                </label>
                <input
                  type="text"
                  id="trash-search-input"
                  aria-label="Search trashed items by key or title"
                  data-testid="trash-search-input"
                  className="kb-input"
                  placeholder="Search trashed items by key or title..."
                  value={trashSearchQuery}
                  onChange={(e) => { setTrashSearchQuery(e.target.value); }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      void loadWorkspaceTrash(trashKindFilter, trashSearchQuery);
                    }
                  }}
                />
                <button
                  type="button"
                  data-testid="trash-search-btn"
                  className="kb-btn kb-btn-secondary"
                  onClick={() => { void loadWorkspaceTrash(trashKindFilter, trashSearchQuery); }}
                >
                  Search
                </button>
              </div>
            </div>

            {/* Permanent Purge Confirmation Modal / Box */}
            {purgeTarget && (
              <div className="kb-danger-purge-container" data-testid="permanent-purge-confirmation-dialog">
                <div className="kb-settings-alert kb-settings-alert-error" role="alert">
                  <strong>Permanent Cryptographic Purge (Stage 2)</strong>
                  <p className="kb-danger-purge-hint">
                    You are about to permanently purge &quot;{(purgeTarget.title ?? purgeTarget.key) ?? purgeTarget.kind}&quot; (ID: {purgeTarget.id}). This action immediately destroys all links, embeddings, and database rows with cryptographic certainty and CANNOT be undone.
                  </p>
                  {(purgeConfirmPhrase ?? `PURGE ${purgeTarget.kind.toUpperCase()} ${(purgeTarget.key ?? purgeTarget.id)}`) && (
                    <p className="kb-danger-purge-hint" data-testid="permanent-purge-confirm-phrase">
                      Confirm Phrase: <code>{purgeConfirmPhrase ?? `PURGE ${purgeTarget.kind.toUpperCase()} ${(purgeTarget.key ?? purgeTarget.id)}`}</code>
                    </p>
                  )}
                  {purgeBlastHash && (
                    <p className="kb-danger-purge-hint">
                      Blast Hash: <code>{purgeBlastHash}</code>
                    </p>
                  )}
                  <div className="kb-form-group kb-danger-confirm-phrase-input">
                    <label htmlFor="ws-purge-confirm-phrase-input">
                      Type Confirmation Phrase to Authorize Purge
                    </label>
                    <input
                      id="ws-purge-confirm-phrase-input"
                      type="text"
                      className="kb-input"
                      data-testid="permanent-purge-confirm-phrase-input"
                      placeholder={purgeConfirmPhrase ?? `PURGE ${purgeTarget.kind.toUpperCase()} ${(purgeTarget.key ?? purgeTarget.id)}`}
                      value={typedConfirmPhrase}
                      onChange={(e) => { setTypedConfirmPhrase(e.target.value); }}
                      autoComplete="off"
                    />
                  </div>
                  <div className="kb-form-group kb-danger-reason-input">
                    <label htmlFor="ws-purge-reason-input">Reason for Purge</label>
                    <input
                      id="ws-purge-reason-input"
                      type="text"
                      className="kb-input"
                      data-testid="permanent-purge-reason-input"
                      placeholder="Enter audit reason for permanent purge (min 8 chars)..."
                      value={purgeReason}
                      onChange={(e) => { setPurgeReason(e.target.value); }}
                    />
                  </div>
                  <div className="kb-danger-buttons-row">
                    <button
                      type="button"
                      data-testid="confirm-permanent-purge-btn"
                      className="kb-btn kb-btn-purge"
                      disabled={
                        isExecutingPurge ||
                        isRequestingPurge ||
                        !purgeConfirmationToken ||
                        typedConfirmPhrase.trim() !== (purgeConfirmPhrase ?? `PURGE ${purgeTarget.kind.toUpperCase()} ${(purgeTarget.key ?? purgeTarget.id)}`) ||
                        purgeReason.trim().length < 8
                      }
                      onClick={() => { void handleExecutePurge(); }}
                    >
                      {isExecutingPurge ? 'Purging...' : 'Confirm Permanent Purge'}
                    </button>
                    <button
                      type="button"
                      data-testid="cancel-permanent-purge-btn"
                      className="kb-btn kb-btn-secondary"
                      onClick={handleCancelPurge}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Trashed Items List / Table */}
            {isLoadingTrash ? (
              <div className="kb-trash-empty" data-testid="trash-loading-state">
                Loading trashed items...
              </div>
            ) : trashedItems.length === 0 ? (
              <div className="kb-trash-empty" data-testid="trash-empty-state">
                No trashed items in this workspace.
              </div>
            ) : (
              <div className="kb-table-scroll-container">
                <table className="kb-table" data-testid="trash-items-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Item</th>
                      <th>Deleted At</th>
                      <th>Days Remaining</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trashedItems.map((item) => (
                      <tr key={item.id} data-testid={`trash-row-${item.id}`}>
                        <td data-label="Type">
                          <span className="kb-role-badge kb-role-member">
                            {formatTrashKind(item.kind)}
                          </span>
                        </td>
                        <td data-label="Item">
                          <div className="kb-member-info">
                            {item.key && (
                              <strong className="kb-member-name" data-testid="trash-item-key">
                                {item.key}
                              </strong>
                            )}
                            <span className="kb-member-handle" data-testid="trash-item-title">
                              {item.title ?? item.id}
                            </span>
                          </div>
                        </td>
                        <td data-label="Deleted At">
                          <span data-testid="trash-deleted-at">
                            {new Date(item.deleted_at).toLocaleString()}
                          </span>
                        </td>
                        <td data-label="Days Remaining">
                          <span
                            data-testid="trash-remaining-days"
                            className={`kb-retention-pill ${item.remaining_days <= 3 ? 'kb-retention-pill-expired' : ''}`}
                          >
                            {item.remaining_days > 0
                              ? `${String(item.remaining_days)} days remaining`
                              : 'Expires today'}
                          </span>
                        </td>
                        <td data-label="Actions">
                          <div className="kb-edit-cell-row">
                            <button
                              type="button"
                              data-testid={`restore-btn-${item.id}`}
                              className="kb-btn kb-btn-secondary"
                              onClick={() => { void handleRestoreItem(item); }}
                            >
                              Restore
                            </button>
                            {Boolean(currentUser?.is_server_admin) && (
                              <button
                                type="button"
                                data-testid={`permanent-purge-btn-${item.id}`}
                                className="kb-btn kb-btn-purge"
                                onClick={() => { void handleRequestPurge(item); }}
                              >
                                Permanent Purge
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
export default WorkspaceSettingsPage;
