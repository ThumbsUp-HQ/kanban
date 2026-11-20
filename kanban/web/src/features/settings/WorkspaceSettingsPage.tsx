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
import { apiFetch } from '../../api/client';
import { ensureSessionCsrfToken } from '../auth/useSessionGuard';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import './ProjectSettingsPage.css';

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

export type WorkspaceTab = 'general' | 'members' | 'groups' | 'trash';

export function parseTabFromHash(hash?: string | null): WorkspaceTab | null {
  if (!hash) return null;
  const clean = hash.trim().replace(/^#+/, '');
  if (clean === 'tab-general' || clean === 'general') return 'general';
  if (clean === 'tab-members' || clean === 'members') return 'members';
  if (clean === 'tab-groups' || clean === 'groups') return 'groups';
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

function getTrashError(err: unknown, fallback: string): string {
  const o = err as { detail?: string; message?: string } | undefined;
  return o?.detail ?? o?.message ?? fallback;
}

export function formatTrashKind(kind: string): string {
  return TRASH_KIND_LABELS[kind.toLowerCase()] ?? kind;
}

export function WorkspaceSettingsPage(): JSX.Element {
  const location = useLocation();
  const queryClient = useQueryClient();
  const locationHash = location.hash;

  const [activeTab, setActiveTab] = useState<WorkspaceTab>(() => {
    const rawHash = window.location.hash || locationHash;
    return parseTabFromHash(rawHash) ?? 'general';
  });

  useEffect(() => {
    const syncFromHash = (): void => {
      const currentHash = window.location.hash;
      const clean = currentHash.replace(/^#+/, '').trim();
      if (!clean) {
        setActiveTab('general');
        return;
      }
      const parsed = parseTabFromHash(currentHash);
      if (parsed) {
        setActiveTab(parsed);
      }
    };

    window.addEventListener('hashchange', syncFromHash);
    return () => {
      window.removeEventListener('hashchange', syncFromHash);
    };
  }, []);

  const handleTabChange = (tab: WorkspaceTab): void => {
    setActiveTab(tab);
    const targetHash = `#tab-${tab}`;
    if (window.location.hash !== targetHash) {
      window.location.hash = targetHash;
    }
  };
  const [, setSettings] = useState<WorkspaceSettingsData | null>(null);
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
  const [isSavingRetention, setIsSavingRetention] = useState<boolean>(false);

  // 2-stage permanent purge state (SERVER_ADMIN only)
  const [purgeTarget, setPurgeTarget] = useState<WorkspaceTrashedItem | null>(null);
  const [purgeConfirmationToken, setPurgeConfirmationToken] = useState<string | null>(null);
  const [purgeBlastHash, setPurgeBlastHash] = useState<string | null>(null);
  const [purgeConfirmPhrase, setPurgeConfirmPhrase] = useState<string | null>(null);
  const [purgeReason, setPurgeReason] = useState<string>('Permanent cryptographic purge');
  const [isRequestingPurge, setIsRequestingPurge] = useState<boolean>(false);
  const [isExecutingPurge, setIsExecutingPurge] = useState<boolean>(false);

  const [currentUser, setCurrentUser] = useState<{
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
  } | null>(null);

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
          };
          if (active) setCurrentUser(me);
          if (!me.is_server_admin && !me.is_workspace_admin) {
            if (active) setIsLoading(false);
            return;
          }
        } catch {
          // Fall back gracefully in offline unit tests
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
        if (active) {
          const errObj = err as { message?: string; detail?: string };
          setErrorMessage(errObj.detail ?? errObj.message ?? 'Failed to load workspace settings.');
        }
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

  const handleSaveRetention = (e: SyntheticEvent): void => {
    e.preventDefault();
    void (async () => {
      setIsSavingRetention(true);
      setTrashActionError(null);
      setTrashActionSuccess(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const payload = {
          trash_retention_days: trashRetention,
        };
        await apiFetch('PATCH', '/api/v1/admin/workspace-settings' as never, {
          headers,
          body: JSON.stringify(payload),
        });
        setTrashActionSuccess(`Trash retention policy updated to ${String(trashRetention)} days.`);
        await loadWorkspaceTrash();
      } catch (err: unknown) {
        setTrashActionError(getTrashError(err, 'Failed to update trash retention policy.'));
      } finally {
        setIsSavingRetention(false);
      }
    })();
  };

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
    } catch (err: unknown) {
      setTrashActionError(getTrashError(err, 'Failed to request permanent purge.'));
      setPurgeTarget(null);
      setPurgeConfirmationToken(null);
      setPurgeBlastHash(null);
      setPurgeConfirmPhrase(null);
    } finally {
      setIsRequestingPurge(false);
    }
  };

  const handleExecutePurge = async (): Promise<void> => {
    if (!purgeConfirmationToken || !purgeTarget) return;
    setIsExecutingPurge(true);
    setTrashActionError(null);
    setTrashActionSuccess(null);
    try {
      const csrf = await ensureSessionCsrfToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (csrf) headers['X-CSRF-Token'] = csrf;

      const defaultReason = 'Permanent cryptographic purge';
      const cleanReason = purgeReason.trim().length >= 10 ? purgeReason.trim() : defaultReason;
      const expectedConfirmPhrase =
        purgeConfirmPhrase ??
        `PURGE ${purgeTarget.kind.toUpperCase()} ${(purgeTarget.key ?? purgeTarget.id)}`;

      const body = {
        target_kind: purgeTarget.kind,
        target: purgeTarget.id,
        mode: 'permanent_purge',
        confirmation_token: purgeConfirmationToken,
        confirm_phrase: expectedConfirmPhrase,
        reason: cleanReason.slice(0, 500),
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
      setPurgeReason('Permanent cryptographic purge');
      await loadWorkspaceTrash();
    } catch (err: unknown) {
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
        const errObj = err as { message?: string; detail?: string };
        setErrorMessage(errObj.detail ?? errObj.message ?? 'Failed to create group.');
      } finally {
        setIsCreatingGroup(false);
      }
    })();
  };

  const handleAddGroupMember = async (groupId: string, memberId: string): Promise<void> => {
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

  if (currentUser && !currentUser.is_server_admin && !currentUser.is_workspace_admin) {
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
              <label htmlFor="ws-name-input">Workspace Name</label>
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
              <label htmlFor="ws-slug-input">Workspace Slug</label>
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
              <label htmlFor="ws-display-name-input">Display Name</label>
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

            <div className="kb-form-group">
              <label htmlFor="ws-idle-timeout-input">
                Session Idle Timeout (Minutes)
                <FieldHelpHint
                  title="Session Idle Timeout"
                  summary="Minutes of user inactivity before the session is expired and re-authentication is enforced."
                  docHref="/docs/multi-card-authentication-studio"
                  testId="ws-idle-timeout-help"
                />
              </label>
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
            </div>

            <div className="kb-form-group">
              <label htmlFor="ws-abs-timeout-input">Session Absolute Timeout (Minutes)</label>
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
            </div>

            <div className="kb-form-group">
              <label htmlFor="ws-trash-retention-input">Trash Retention Days</label>
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
              <label htmlFor="ws-mcp-key-max-ttl-input">MCP Key Max TTL (Days)</label>
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
                  caution="External AI integrations requiring internet access will fail while Air-Gap mode is enabled."
                  docHref="/docs/zero-trust-security-and-access-visibility"
                  testId="ws-air-gap-help"
                />
              </label>
            </div>

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
                <input
                  type="text"
                  data-testid="new-user-handle"
                  className="kb-input"
                  placeholder="@handle"
                  value={newHandle}
                  onChange={(e) => { setNewHandle(e.target.value); }}
                  required
                />
              </div>
              <div className="kb-form-group">
                <input
                  type="text"
                  data-testid="new-user-name"
                  className="kb-input"
                  placeholder="Full Name / Display Name"
                  value={newDisplayName}
                  onChange={(e) => { setNewDisplayName(e.target.value); }}
                  required
                />
              </div>
              <div className="kb-form-group">
                <input
                  type="email"
                  data-testid="new-user-email"
                  className="kb-input"
                  placeholder="email@example.com"
                  value={newEmail}
                  onChange={(e) => { setNewEmail(e.target.value); }}
                  required
                />
              </div>
              <div className="kb-form-group">
                <input
                  type="password"
                  data-testid="new-user-password"
                  className="kb-input"
                  placeholder="Initial Password (optional)"
                  value={newPassword}
                  onChange={(e) => { setNewPassword(e.target.value); }}
                />
              </div>
              <div className="kb-form-row">
                <select
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
                          <td>
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
                          <td>
                            <span className="kb-member-email" data-testid={`member-email-${p.id}`}>
                              {p.email ?? '-'}
                            </span>
                          </td>
                          <td>
                            <span
                              className={`kb-type-pill kb-type-pill--${typeClass}`}
                              data-testid={`type-pill-${p.id}`}
                            >
                              {pType.charAt(0) + pType.slice(1).toLowerCase()}
                            </span>
                          </td>
                          <td>
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
                          </td>
                          <td>
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
                <input
                  type="text"
                  data-testid="new-group-name"
                  className="kb-input"
                  placeholder="Group Name (e.g. Core Engineers)"
                  value={newGroupName}
                  onChange={(e) => { setNewGroupName(e.target.value); }}
                  required
                />
                <input
                  type="text"
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
                      <div data-testid="group-cycle-alert" className="kb-settings-alert kb-settings-alert-error" role="alert">
                        {groupActionError}
                      </div>
                    )}

                    {/* Add Member / Nested Group */}
                    <div className="kb-add-group-member-box">
                      <h5>Add Member or Nested Group</h5>
                      <div className="kb-form-row">
                        <select
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
                                    <td>
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
                                    <td>
                                      <span
                                        className={`kb-type-pill kb-type-pill--${mType.toLowerCase()}`}
                                        data-testid={`group-member-type-${m.id}`}
                                      >
                                        {isNestedGroup ? 'Nested Group' : mType.charAt(0) + mType.slice(1).toLowerCase()}
                                      </span>
                                    </td>
                                    <td>
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
                Set how long soft-deleted items remain in trash before automated multi-object sweep (7 to 365 days).
              </p>
              <form onSubmit={handleSaveRetention} className="kb-edit-cell-row">
                <label htmlFor="ws-trash-retention-input-trash-tab" className="kb-visually-hidden">
                  Trash Retention Days
                </label>
                <input
                  id="ws-trash-retention-input-trash-tab"
                  type="number"
                  data-testid="workspace-trash-retention-input-trash-tab"
                  className="kb-input"
                  min="7"
                  max="365"
                  value={trashRetention}
                  onChange={(e) => { setTrashRetention(Number(e.target.value)); }}
                  required
                />
                <button
                  type="submit"
                  data-testid="save-trash-retention-btn"
                  className="kb-btn kb-btn-primary"
                  disabled={isSavingRetention}
                >
                  {isSavingRetention ? 'Saving...' : 'Save Retention Policy'}
                </button>
              </form>
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
                    {kind === 'all'
                      ? 'All'
                      : kind.charAt(0).toUpperCase() + kind.slice(1) + 's'}
                  </button>
                ))}
              </div>
              <div className="kb-trash-search-box">
                <input
                  type="text"
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
                  <div className="kb-form-group kb-danger-reason-input">
                    <label htmlFor="ws-purge-reason-input">Reason for Purge</label>
                    <input
                      id="ws-purge-reason-input"
                      type="text"
                      className="kb-input"
                      data-testid="permanent-purge-reason-input"
                      value={purgeReason}
                      onChange={(e) => { setPurgeReason(e.target.value); }}
                    />
                  </div>
                  <div className="kb-danger-buttons-row">
                    <button
                      type="button"
                      data-testid="confirm-permanent-purge-btn"
                      className="kb-btn kb-btn-purge"
                      disabled={isExecutingPurge || isRequestingPurge || !purgeConfirmationToken}
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
                        <td>
                          <span className="kb-role-badge kb-role-member">
                            {formatTrashKind(item.kind)}
                          </span>
                        </td>
                        <td>
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
                        <td>
                          <span data-testid="trash-deleted-at">
                            {new Date(item.deleted_at).toLocaleString()}
                          </span>
                        </td>
                        <td>
                          <span
                            data-testid="trash-remaining-days"
                            className={`kb-retention-pill ${item.remaining_days <= 3 ? 'kb-retention-pill-expired' : ''}`}
                          >
                            {item.remaining_days > 0
                              ? `${String(item.remaining_days)} days remaining`
                              : 'Expires today'}
                          </span>
                        </td>
                        <td>
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
