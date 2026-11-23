// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Narrative RBAC Policy Builder Component (KAN-83).
 *
 * Implements narrative sentence configuration header:
 * "As a [system admin | workspace admin | project admin] I want [ ● role x ] ... to have access to"
 * with tri-state checkboxes across Workspace (8), Issue (10), and Field (12) permissions,
 * tier governance locking, and inline role creation popover.
 */

import React, { useEffect, useRef, useState, type JSX, type ChangeEvent, type SyntheticEvent } from 'react';
import { apiFetch } from '../../api/client';
import './RbacPolicyBuilder.css';

export interface RbacRole {
  id: string;
  workspace_id?: string | undefined;
  slug: string;
  name: string;
  color_hex?: string | undefined;
  description?: string | null | undefined;
  is_system?: boolean | undefined;
  system_role?: string | null | undefined;
  scope_tier?: string | undefined;
  permissions?: string[] | undefined;
}

export interface RbacPolicyBuilderProps {
  workspaceId?: string | undefined;
  projectId?: string | undefined;
  isServerAdmin?: boolean | undefined;
  initialRoleTier?: 'system admin' | 'workspace admin' | 'project admin' | undefined;
  onRolesChanged?: (() => void) | undefined;
}

export const WORKSPACE_PERMS = [
  { key: 'workspace:create', title: 'Create Workspaces', desc: 'Provision new workspaces' },
  { key: 'workspace:edit_settings', title: 'Edit Settings', desc: 'Modify workspace name and settings' },
  { key: 'workspace:manage_members', title: 'Manage Members', desc: 'Invite and remove workspace users' },
  { key: 'workspace:manage_roles', title: 'Manage Roles', desc: 'Configure RBAC roles and permissions' },
  { key: 'workspace:manage_integrations', title: 'Manage Integrations', desc: 'Manage OAuth, webhooks, and MCP' },
  { key: 'workspace:audit_logs', title: 'View Audit Logs', desc: 'Inspect immutable security audit ledger' },
  { key: 'workspace:export_data', title: 'Export Data', desc: 'Generate system and workspace backups' },
  { key: 'workspace:purge_trash', title: 'Purge Trash', desc: 'Permanently destroy soft-deleted entities' },
] as const;

export const ISSUE_PERMS = [
  { key: 'issue:create', title: 'Create Issues', desc: 'File new issues and tickets' },
  { key: 'issue:view', title: 'View Issues', desc: 'Read issues and their metadata' },
  { key: 'issue:comment', title: 'Comment on Issues', desc: 'Post and react to comments' },
  { key: 'issue:transition', title: 'Transition States', desc: 'Move issues between workflow states' },
  { key: 'issue:move_rank', title: 'Re-order / Move Rank', desc: 'Change kanban card ordering' },
  { key: 'issue:copy', title: 'Copy Issues', desc: 'Clone issue and subtree hierarchy' },
  { key: 'issue:archive', title: 'Archive Issues', desc: 'Archive and unarchive issues' },
  { key: 'issue:delete', title: 'Delete Issues', desc: 'Move issues to trash or restore them' },
  { key: 'issue:link', title: 'Link Objects', desc: 'Create typed object relationships' },
  { key: 'issue:subscribe', title: 'Subscribe to Issues', desc: 'Manage event notifications' },
] as const;

export const FIELD_PERMS = [
  { key: 'field:modify_summary', title: 'Modify Summary', desc: 'Edit issue title/summary' },
  { key: 'field:modify_description', title: 'Modify Description', desc: 'Edit markdown description' },
  { key: 'field:modify_state', title: 'Modify State', desc: 'Change workflow state directly' },
  { key: 'field:modify_priority', title: 'Modify Priority', desc: 'Change issue priority' },
  { key: 'field:modify_assignees', title: 'Modify Assignees', desc: 'Add or remove issue assignees' },
  { key: 'field:modify_labels', title: 'Modify Labels', desc: 'Attach or detach issue tags' },
  { key: 'field:modify_dates', title: 'Modify Dates', desc: 'Update target dates and estimates' },
  { key: 'field:modify_cycle', title: 'Modify Cycle', desc: 'Assign or reassign sprint cycles' },
  { key: 'field:modify_module', title: 'Modify Module', desc: 'Attach or detach feature modules' },
  { key: 'field:modify_parent', title: 'Modify Parent', desc: 'Change parent issue hierarchy' },
  { key: 'field:modify_custom_fields', title: 'Modify Custom Fields', desc: 'Update custom field values' },
  { key: 'field:attach_files', title: 'Attach Files', desc: 'Upload documents and image attachments' },
] as const;

const PRESET_COLORS = [
  '#3b82f6', '#64748b', '#4f46e5', '#0891b2', '#0d9488',
  '#059669', '#d97706', '#ea580c', '#e11d48', '#dc2626',
  '#7c3aed', '#db2777',
];

export function RbacPolicyBuilder({
  isServerAdmin = false,
  initialRoleTier = 'workspace admin',
  onRolesChanged,
}: RbacPolicyBuilderProps): JSX.Element {
  const [roleTier, setRoleTier] = useState<'system admin' | 'workspace admin' | 'project admin'>(
    isServerAdmin ? 'system admin' : initialRoleTier,
  );
  const [roles, setRoles] = useState<RbacRole[]>([]);
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([]);
  const [rolePermsMap, setRolePermsMap] = useState<Record<string, Set<string>>>({});
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Popover state
  const [isPopoverOpen, setIsPopoverOpen] = useState(false);
  const [newRoleName, setNewRoleName] = useState('');
  const [newRoleSlug, setNewRoleSlug] = useState('');
  const [newRoleColor, setNewRoleColor] = useState('#3b82f6');
  const [cloneFromId, setCloneFromId] = useState<string>('');
  const [isCreating, setIsCreating] = useState(false);

  const checkboxRefs = useRef<Record<string, HTMLInputElement | null>>({});

  // Fetch roles
  const loadRoles = async (): Promise<void> => {
    setErrorMsg(null);
    try {
      const fetched = (await apiFetch('GET', '/api/v1/admin/rbac/roles' as never)) as RbacRole[];
      /* v8 ignore next */
      const safeFetched = Array.isArray(fetched) ? fetched : [];
      setRoles(safeFetched);

      // Load permissions for each role
      const permMap: Record<string, Set<string>> = {};
      for (const r of safeFetched) {
        if (r.permissions) {
          permMap[r.id] = new Set(r.permissions);
        } else {
          try {
            const pRes = (await apiFetch(
              'GET',
              `/api/v1/admin/rbac/roles/${r.id}/permissions` as never,
            )) as { permissions?: string[] };
            /* v8 ignore next */
            permMap[r.id] = new Set(Array.isArray(pRes.permissions) ? pRes.permissions : []);
          } catch {
            permMap[r.id] = new Set();
          }
        }
      }
      setRolePermsMap(permMap);

      // Default select users role or first role if none selected
      if (selectedRoleIds.length === 0 && safeFetched.length > 0) {
        /* v8 ignore next */
        const defaultRole = safeFetched.find((r) => r.slug === 'users') ?? safeFetched[0];
        /* v8 ignore next */
        if (defaultRole) {
          setSelectedRoleIds([defaultRole.id]);
        }
      }
    } catch (err: unknown) {
      const e = err as { detail?: string; message?: string };
      /* v8 ignore next */
      setErrorMsg(e.detail ?? e.message ?? 'Failed to load RBAC roles.');
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadRoles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleToggleRoleSelection = (roleId: string): void => {
    setSelectedRoleIds((prev) =>
      prev.includes(roleId) ? prev.filter((id) => id !== roleId) : [...prev, roleId],
    );
  };

  const handleSelectRoleFromDropdown = (e: ChangeEvent<HTMLSelectElement>): void => {
    const roleId = e.target.value;
    if (roleId && !selectedRoleIds.includes(roleId)) {
      setSelectedRoleIds((prev) => [...prev, roleId]);
    }
    e.target.value = '';
  };

  // Checkbox tri-state computation
  const getPermissionState = (permKey: string): { checked: boolean; indeterminate: boolean } => {
    if (selectedRoleIds.length === 0) {
      return { checked: false, indeterminate: false };
    }
    let count = 0;
    for (const rId of selectedRoleIds) {
      const perms = rolePermsMap[rId];
      if (perms?.has(permKey)) {
        count++;
      }
    }
    if (count === selectedRoleIds.length) {
      return { checked: true, indeterminate: false };
    }
    if (count > 0) {
      return { checked: false, indeterminate: true };
    }
    return { checked: false, indeterminate: false };
  };

  // Toggle permission
  const handleTogglePermission = async (permKey: string): Promise<void> => {
    /* v8 ignore next */
    if (selectedRoleIds.length === 0) return;
    const { checked, indeterminate } = getPermissionState(permKey);
    // If checked or indeterminate, toggle to false (revoke); if unchecked, toggle to true (grant)
    const nextGranted = !checked && !indeterminate;

    try {
      await apiFetch('PUT', '/api/v1/admin/rbac/roles/permissions:batch' as never, {
        body: {
          role_ids: selectedRoleIds,
          permission_key: permKey,
          granted: nextGranted,
        },
      });

      // Update local state
      setRolePermsMap((prev) => {
        const next = { ...prev };
        for (const rId of selectedRoleIds) {
          /* v8 ignore next */
          const currentSet = new Set(next[rId] ?? []);
          if (nextGranted) {
            currentSet.add(permKey);
          } else {
            currentSet.delete(permKey);
          }
          next[rId] = currentSet;
        }
        return next;
      });
    } catch (err: unknown) {
      const e = err as { detail?: string; message?: string };
      /* v8 ignore next */
      setErrorMsg(e.detail ?? e.message ?? 'Failed to update permission.');
    }
  };

  // Create custom role
  const handleOpenPopover = (): void => {
    setNewRoleName('');
    setNewRoleSlug('');
    setNewRoleColor('#3b82f6');
    /* v8 ignore next */
    setCloneFromId(roles[0]?.id ?? '');
    setIsPopoverOpen(true);
  };

  const handleRoleNameChange = (e: ChangeEvent<HTMLInputElement>): void => {
    const val = e.target.value;
    setNewRoleName(val);
    const autoSlug = val.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    setNewRoleSlug(autoSlug);
  };

  const handleCreateRole = async (e: SyntheticEvent): Promise<void> => {
    e.preventDefault();
    /* v8 ignore next */
    if (!newRoleName.trim()) return;

    setIsCreating(true);
    setErrorMsg(null);
    try {
      const created = (await apiFetch('POST', '/api/v1/admin/rbac/roles' as never, {
        body: {
          name: newRoleName.trim(),
          /* v8 ignore next */
          slug: newRoleSlug.trim() || undefined,
          color_hex: newRoleColor,
          /* v8 ignore next */
          clone_from_role_id: cloneFromId || undefined,
        },
      })) as RbacRole;

      setIsPopoverOpen(false);
      await loadRoles();
      setSelectedRoleIds((prev) => [...prev, created.id]);
      onRolesChanged?.();
    } catch (err: unknown) {
      const eObj = err as { detail?: string; message?: string };
      /* v8 ignore next */
      setErrorMsg(eObj.detail ?? eObj.message ?? 'Failed to create role.');
    } finally {
      setIsCreating(false);
    }
  };

  const selectedRoles = roles.filter((r) => selectedRoleIds.includes(r.id));
  const unselectedRoles = roles.filter((r) => !selectedRoleIds.includes(r.id));
  const isWorkspaceDisabled = roleTier !== 'system admin' && !isServerAdmin;

  return (
    <div className="rbac-builder-container" data-testid="rbac-policy-builder">
      {/* Narrative Sentence Header */}
      <header className="rbac-narrative-header" aria-label="Narrative RBAC sentence">
        <span>As a</span>
        <select
          className="rbac-tier-select"
          value={roleTier}
          data-testid="rbac-tier-select"
          onChange={(e) => { setRoleTier(e.target.value as 'system admin' | 'workspace admin' | 'project admin'); }
          }
        >
          {isServerAdmin && <option value="system admin">system admin</option>}
          <option value="workspace admin">workspace admin</option>
          <option value="project admin">project admin</option>
        </select>
        <span>I want</span>
        <div className="rbac-chips-group">
          {selectedRoles.map((r) => (
            <span key={r.id} className="rbac-role-chip" data-testid={`rbac-selected-role-${r.slug}`}>
              <svg className="rbac-chip-dot" viewBox="0 0 12 12" aria-hidden="true">
                <circle cx="6" cy="6" r="5" fill={r.color_hex ?? '#3b82f6'} />
              </svg>
              <span>{r.name}</span>
              <button
                type="button"
                className="rbac-chip-remove"
                aria-label={`Deselect ${r.name}`}
                onClick={() => { handleToggleRoleSelection(r.id); }}
              >
                ×
              </button>
            </span>
          ))}
          {unselectedRoles.length > 0 && (
            <select
              className="rbac-select-role"
              data-testid="rbac-select-role-dropdown"
              onChange={handleSelectRoleFromDropdown}
              value=""
            >
              <option value="" disabled>
                + Select role
              </option>
              {unselectedRoles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            className="rbac-create-role-btn"
            data-testid="rbac-open-create-role"
            onClick={handleOpenPopover}
          >
            *create new*
          </button>
        </div>
        <span>to have access to</span>
      </header>

      {errorMsg && (
        <div className="rbac-warning-banner" role="alert" data-testid="rbac-error-banner">
          ⚠️ {errorMsg}
        </div>
      )}

      {/* Permission Fieldsets */}
      <div className="rbac-sections-container">
        {/* 1. Workspace Permissions (8) */}
        <fieldset
          className="rbac-fieldset rbac-fieldset--workspace"
          disabled={isWorkspaceDisabled}
          data-testid="rbac-fieldset-workspace"
        >
          <legend>Workspace (8 permissions)</legend>
          {isWorkspaceDisabled && (
            <div className="rbac-warning-banner" role="alert" data-testid="workspace-locked-banner">
              🔒 Workspace permissions can only be modified by a System Admin.
            </div>
          )}
          <div className="rbac-perms-grid">
            {WORKSPACE_PERMS.map((p) => {
              const { checked, indeterminate } = getPermissionState(p.key);
              return (
                <label key={p.key} className="rbac-perm-item" data-testid={`perm-item-${p.key}`}>
                  <input
                    type="checkbox"
                    className="rbac-checkbox"
                    checked={checked}
                    ref={(el) => {
                      if (el) {
                        el.indeterminate = indeterminate;
                        checkboxRefs.current[p.key] = el;
                      }
                    }}
                    disabled={isWorkspaceDisabled}
                    onChange={() => void handleTogglePermission(p.key)}
                  />
                  <div className="rbac-perm-text">
                    <span className="rbac-perm-title">{p.title}</span>
                    <span className="rbac-perm-key">{p.key}</span>
                  </div>
                </label>
              );
            })}
          </div>
        </fieldset>

        {/* 2. Issue Permissions (10) */}
        <fieldset className="rbac-fieldset rbac-fieldset--issue" data-testid="rbac-fieldset-issue">
          <legend>Issue (10 permissions)</legend>
          <div className="rbac-perms-grid">
            {ISSUE_PERMS.map((p) => {
              const { checked, indeterminate } = getPermissionState(p.key);
              return (
                <label key={p.key} className="rbac-perm-item" data-testid={`perm-item-${p.key}`}>
                  <input
                    type="checkbox"
                    className="rbac-checkbox"
                    checked={checked}
                    ref={(el) => {
                      if (el) {
                        el.indeterminate = indeterminate;
                        checkboxRefs.current[p.key] = el;
                      }
                    }}
                    onChange={() => void handleTogglePermission(p.key)}
                  />
                  <div className="rbac-perm-text">
                    <span className="rbac-perm-title">{p.title}</span>
                    <span className="rbac-perm-key">{p.key}</span>
                  </div>
                </label>
              );
            })}
          </div>
        </fieldset>

        {/* 3. Field Permissions (12) */}
        <fieldset className="rbac-fieldset rbac-fieldset--field" data-testid="rbac-fieldset-field">
          <legend>Field (12 permissions)</legend>
          <div className="rbac-perms-grid">
            {FIELD_PERMS.map((p) => {
              const { checked, indeterminate } = getPermissionState(p.key);
              return (
                <label key={p.key} className="rbac-perm-item" data-testid={`perm-item-${p.key}`}>
                  <input
                    type="checkbox"
                    className="rbac-checkbox"
                    checked={checked}
                    ref={(el) => {
                      if (el) {
                        el.indeterminate = indeterminate;
                        checkboxRefs.current[p.key] = el;
                      }
                    }}
                    onChange={() => void handleTogglePermission(p.key)}
                  />
                  <div className="rbac-perm-text">
                    <span className="rbac-perm-title">{p.title}</span>
                    <span className="rbac-perm-key">{p.key}</span>
                  </div>
                </label>
              );
            })}
          </div>
        </fieldset>
      </div>

      {/* Inline Create Role Popover */}
      {isPopoverOpen && (
        <div className="rbac-popover-backdrop" role="dialog" aria-modal="true">
          <div className="rbac-popover-card" data-testid="rbac-create-role-popover">
            <h3 className="rbac-popover-title">Create New Role</h3>
            <form onSubmit={(e) => void handleCreateRole(e)}>
              <div className="rbac-form-group">
                <label className="rbac-form-label" htmlFor="new-role-name">
                  Role Name
                </label>
                <input
                  id="new-role-name"
                  type="text"
                  className="rbac-form-input"
                  data-testid="rbac-new-role-name"
                  value={newRoleName}
                  onChange={handleRoleNameChange}
                  placeholder="e.g. Lead Developer"
                  required
                />
              </div>

              <div className="rbac-form-group">
                <label className="rbac-form-label" htmlFor="new-role-slug">
                  Slug
                </label>
                <input
                  id="new-role-slug"
                  type="text"
                  className="rbac-form-input"
                  data-testid="rbac-new-role-slug"
                  value={newRoleSlug}
                  onChange={(e) => { setNewRoleSlug(e.target.value); }}
                  placeholder="e.g. lead-developer"
                />
              </div>

              <div className="rbac-form-group">
                <label className="rbac-form-label">Role Pill Color</label>
                <div className="rbac-color-picker-row" data-testid="rbac-color-picker">
                  {PRESET_COLORS.map((hex) => (
                    <button
                      key={hex}
                      type="button"
                      className={`rbac-color-swatch-btn ${newRoleColor === hex ? 'rbac-color-swatch-btn--selected' : ''}`}
                      onClick={() => { setNewRoleColor(hex); }}
                      aria-label={`Select color ${hex}`}
                    >
                      <svg width="22" height="22" viewBox="0 0 22 22">
                        <circle cx="11" cy="11" r="9" fill={hex} />
                      </svg>
                    </button>
                  ))}
                </div>
              </div>

              <div className="rbac-form-group">
                <label className="rbac-form-label" htmlFor="clone-from-role">
                  Clone permissions from
                </label>
                <select
                  id="clone-from-role"
                  className="rbac-form-select"
                  data-testid="rbac-clone-role-select"
                  value={cloneFromId}
                  onChange={(e) => { setCloneFromId(e.target.value); }}
                >
                  <option value="">(None - Start Empty)</option>
                  {roles.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} ({r.slug})
                    </option>
                  ))}
                </select>
              </div>

              <div className="rbac-popover-actions">
                <button
                  type="button"
                  className="rbac-btn-cancel"
                  onClick={() => { setIsPopoverOpen(false); }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rbac-btn-submit"
                  data-testid="rbac-submit-create-role"
                  disabled={isCreating || !newRoleName.trim()}
                >
                  {isCreating ? 'Creating...' : 'Create Role'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
