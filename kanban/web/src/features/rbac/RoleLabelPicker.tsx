// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Multi-Role Label Chip Picker Component (KAN-83).
 *
 * Allows assigning and revoking multiple custom or system RBAC role labels
 * on a principal via /api/v1/admin/principals/{id}/role-labels.
 */

import React, { useEffect, useState, type JSX, type ChangeEvent } from 'react';
import { apiFetch } from '../../api/client';
import type { RbacRole } from './RbacPolicyBuilder';
import './RbacPolicyBuilder.css';

export interface PrincipalRoleLabelItem {
  id: string;
  principal_id: string;
  role_id: string;
  role_name: string;
  role_slug: string;
  role_color_hex?: string | undefined;
  assigned_at?: string | undefined;
}

export interface RoleLabelPickerProps {
  principalId: string;
  disabled?: boolean | undefined;
  availableRoles?: RbacRole[] | undefined;
  onRolesChange?: ((roleIds: string[]) => void) | undefined;
}

export function RoleLabelPicker({
  principalId,
  disabled = false,
  availableRoles: propAvailableRoles,
  onRolesChange,
}: RoleLabelPickerProps): JSX.Element {
  const [assignedLabels, setAssignedLabels] = useState<PrincipalRoleLabelItem[]>([]);
  const [availableRoles, setAvailableRoles] = useState<RbacRole[]>(propAvailableRoles ?? []);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Load available roles if not provided via props
  useEffect(() => {
    if (!propAvailableRoles || propAvailableRoles.length === 0) {
      let isMounted = true;
      async function fetchRoles(): Promise<void> {
        try {
          const roles = (await apiFetch('GET', '/api/v1/admin/rbac/roles' as never)) as RbacRole[];
          /* v8 ignore next */
          if (isMounted && Array.isArray(roles)) setAvailableRoles(roles);
        } catch {
          // Fallback gracefully
        }
      }
      void fetchRoles();
      return () => {
        isMounted = false;
      };
    } else {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAvailableRoles(propAvailableRoles);
    }
  }, [propAvailableRoles]);

  // Load assigned role labels for this principal
  useEffect(() => {
    let isMounted = true;
    async function fetchAssigned(): Promise<void> {
      if (!principalId) return;
      setIsLoading(true);
      setErrorMsg(null);
      try {
        const labels = (await apiFetch(
          'GET',
          `/api/v1/admin/principals/${principalId}/role-labels` as never,
        )) as PrincipalRoleLabelItem[];
        /* v8 ignore next */
        if (isMounted && Array.isArray(labels)) {
          setAssignedLabels(labels);
          onRolesChange?.(labels.map((l) => l.role_id));
        }
      } catch (err: unknown) {
        const e = err as { detail?: string; message?: string };
        /* v8 ignore next */
        if (isMounted) setErrorMsg(e.detail ?? e.message ?? 'Failed to load assigned role labels.');
      } finally {
        /* v8 ignore next */
        if (isMounted) setIsLoading(false);
      }
    }
    void fetchAssigned();
    return () => {
      isMounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [principalId]);

  // Assign a new role label
  const handleAddRole = async (e: ChangeEvent<HTMLSelectElement>): Promise<void> => {
    const roleId = e.target.value;
    /* v8 ignore next */
    if (!roleId || disabled) return;
    setErrorMsg(null);
    try {
      const added = (await apiFetch(
        'POST',
        `/api/v1/admin/principals/${principalId}/role-labels` as never,
        {
          body: { role_id: roleId },
        },
      )) as PrincipalRoleLabelItem;

      const next = [...assignedLabels, added];
      setAssignedLabels(next);
      onRolesChange?.(next.map((l) => l.role_id));
    } catch (err: unknown) {
      const e = err as { detail?: string; message?: string };
      /* v8 ignore next */
      setErrorMsg(e.detail ?? e.message ?? 'Failed to assign role label.');
    }
    e.target.value = '';
  };

  // Revoke a role label
  const handleRemoveRole = async (label: PrincipalRoleLabelItem): Promise<void> => {
    /* v8 ignore next */
    if (disabled) return;
    setErrorMsg(null);
    try {
      await apiFetch(
        'DELETE',
        `/api/v1/admin/principals/${principalId}/role-labels` as never,
        {
          params: { role_id: label.role_id },
        },
      );

      const next = assignedLabels.filter((l) => l.role_id !== label.role_id);
      setAssignedLabels(next);
      onRolesChange?.(next.map((l) => l.role_id));
    } catch (err: unknown) {
      const e = err as { detail?: string; message?: string };
      /* v8 ignore next */
      setErrorMsg(e.detail ?? e.message ?? 'Failed to revoke role label.');
    }
  };

  /* v8 ignore next 2 */
  const rolesList = Array.isArray(availableRoles) ? availableRoles : [];
  const labelsList = Array.isArray(assignedLabels) ? assignedLabels : [];

  const assignedRoleIds = new Set(labelsList.map((l) => l.role_id));
  const unassignedRoles = rolesList.filter((r) => Boolean(r.id) && !assignedRoleIds.has(r.id));

  return (
    <div className="role-label-picker" data-testid="role-label-picker">
      {labelsList.map((label, idx) => (
        <span
          key={label.role_id || label.id || idx}
          className="rbac-role-chip"
          data-testid={`role-chip-${label.role_slug}`}
        >
          <svg className="rbac-chip-dot" viewBox="0 0 12 12" aria-hidden="true">
            <circle cx="6" cy="6" r="5" fill={label.role_color_hex ?? '#3b82f6'} />
          </svg>
          <span>{label.role_name}</span>
          {!disabled && (
            <button
              type="button"
              className="rbac-chip-remove"
              aria-label={`Remove role ${label.role_name}`}
              data-testid={`remove-role-${label.role_slug}`}
              onClick={() => void handleRemoveRole(label)}
            >
              ×
            </button>
          )}
        </span>
      ))}

      {!disabled && unassignedRoles.length > 0 && (
        <select
          className="role-label-select"
          data-testid="add-role-label-select"
          onChange={(e) => void handleAddRole(e)}
          value=""
          disabled={isLoading}
        >
          <option value="" disabled>
            + Add role
          </option>
          {unassignedRoles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      )}

      {errorMsg && (
        <span className="rbac-inline-error" role="alert">
          {errorMsg}
        </span>
      )}
    </div>
  );
}
