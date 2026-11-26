// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Multi-Role Label Chip Picker Component (KAN-83, KAN-502).
 *
 * Allows assigning and revoking multiple custom or system RBAC role labels
 * on a principal via /api/v1/admin/principals/{id}/role-labels with contextual
 * FieldHelpHint popover guidance and explicit default role indication.
 */

import React, { useEffect, useState, type JSX, type ChangeEvent } from 'react';
import { apiFetch } from '../../api/client';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import type { RbacRole } from './RbacPolicyBuilder';
import './RbacPolicyBuilder.css';
import './RoleLabelPicker.css';

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
  defaultValue?: string | undefined;
  docHref?: string | undefined;
  helpTitle?: string | undefined;
  helpSummary?: string | undefined;
  showHelpHint?: boolean | undefined;
  label?: string | undefined;
}

export function RoleLabelPicker({
  principalId,
  disabled = false,
  availableRoles: propAvailableRoles,
  onRolesChange,
  defaultValue = 'Member',
  docHref = '/docs/custom-fields',
  helpTitle = 'Role Labels and Default Permissions',
  helpSummary = 'New workspace members receive the base Member role by default. Custom role labels supplement base member privileges with specialized domain permissions without revoking standard access.',
  showHelpHint = true,
  label = 'Role Labels',
}: RoleLabelPickerProps): JSX.Element {
  const [assignedLabels, setAssignedLabels] = useState<PrincipalRoleLabelItem[]>([]);
  const [availableRoles, setAvailableRoles] = useState<RbacRole[]>(propAvailableRoles ?? []);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const sanitizedId = principalId ? principalId.replace(/[^a-zA-Z0-9_-]/g, '') : 'default';
  const selectId = `add-role-label-select-${sanitizedId}`;

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
  const handleRemoveRole = async (labelItem: PrincipalRoleLabelItem): Promise<void> => {
    /* v8 ignore next */
    if (disabled) return;
    setErrorMsg(null);
    try {
      await apiFetch(
        'DELETE',
        `/api/v1/admin/principals/${principalId}/role-labels` as never,
        {
          params: { role_id: labelItem.role_id },
        },
      );

      const next = assignedLabels.filter((l) => l.role_id !== labelItem.role_id);
      setAssignedLabels(next);
      onRolesChange?.(next.map((l) => l.role_id));
    } catch (err: unknown) {
      const e = err as { detail?: string; message?: string };
      /* v8 ignore next */
      setErrorMsg(e.detail ?? e.message ?? 'Failed to revoke role label.');
    }
  };

  const rolesList = availableRoles;
  const labelsList = assignedLabels;

  const assignedRoleIds = new Set(labelsList.map((l) => l.role_id));
  const unassignedRoles = rolesList.filter((r) => Boolean(r.id) && !assignedRoleIds.has(r.id));

  return (
    <div className="role-label-picker-container" data-testid="role-label-picker-container">
      <div className="role-label-picker-header">
        <label htmlFor={selectId} className="role-label-picker-label">
          <span className="role-label-picker-label-text">
            {label}
            <span
              className="role-label-default-indicator"
              data-testid="role-label-default-indicator"
            >
              (Default: {defaultValue})
            </span>
          </span>
        </label>
        {showHelpHint && (
          <FieldHelpHint
            testId="role-label-help"
            title={helpTitle}
            summary={helpSummary}
            defaultValue={defaultValue}
            validValues={[
              {
                label: 'Member',
                description:
                  'Default base role assigned to invited users with standard read and write permissions.',
              },
              {
                label: 'Custom Role',
                description:
                  'Supplemental role label granting scoped domain privileges (e.g., Lead Dev, QA Tester) alongside base permissions.',
              },
            ]}
            docHref={docHref}
            ariaLabel="Help for Role Labels"
          />
        )}
      </div>

      <div className="role-label-picker" data-testid="role-label-picker">
        {labelsList.map((lItem) => (
          <span
            key={lItem.role_id}
            className="rbac-role-chip"
            data-testid={`role-chip-${lItem.role_slug}`}
          >
            <svg
              className="rbac-chip-dot"
              width="10"
              height="10"
              viewBox="0 0 12 12"
              aria-hidden="true"
            >
              <circle cx="6" cy="6" r="5" fill={lItem.role_color_hex ?? '#3b82f6'} />
            </svg>
            <span>{lItem.role_name}</span>
            {!disabled && (
              <button
                type="button"
                className="rbac-chip-remove"
                aria-label={`Remove role ${lItem.role_name}`}
                data-testid={`remove-role-${lItem.role_slug}`}
                onClick={() => void handleRemoveRole(lItem)}
              >
                ×
              </button>
            )}
          </span>
        ))}

        {!disabled && unassignedRoles.length > 0 && (
          <select
            id={selectId}
            className="role-label-select"
            data-testid="add-role-label-select"
            aria-label="Add role"
            aria-describedby={`role-label-hint-${sanitizedId}`}
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

      <span id={`role-label-hint-${sanitizedId}`} className="role-label-help-sr-only">
        Default role is {defaultValue}. Custom roles supplement base member privileges.
      </span>
    </div>
  );
}
