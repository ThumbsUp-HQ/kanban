// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Granular RBAC Frontend Field and Issue Permission Evaluator (KAN-83).
 */

export interface PermissionBearerIssue {
  capabilities?: string[] | undefined;
  editable_fields?: string[] | undefined;
  issue_permissions?: string[] | undefined;
  [key: string]: unknown;
}

/**
 * Check if the current user has permission to modify a specific field on an issue.
 *
 * Precedence:
 * 1. If issue.editable_fields is provided, check if fieldName is included.
 * 2. Fall back to issue.capabilities check (EDIT or ADMIN).
 * 3. Default to true if neither is present.
 */
export function canModifyIssueField(
  issue: PermissionBearerIssue | null | undefined,
  fieldName: string,
): boolean {
  if (!issue) return false;

  if (Array.isArray(issue.editable_fields)) {
    return issue.editable_fields.includes(fieldName);
  }

  if (Array.isArray(issue.capabilities)) {
    return issue.capabilities.includes('EDIT') || issue.capabilities.includes('ADMIN');
  }

  return true;
}

/**
 * Check if the current user has a specific granular issue permission.
 *
 * Precedence:
 * 1. If issue.issue_permissions is provided, check if permissionKey is included.
 * 2. Fall back to issue.capabilities mappings.
 * 3. Default to true if neither is present.
 */
export function hasIssuePermission(
  issue: PermissionBearerIssue | null | undefined,
  permissionKey: string,
): boolean {
  if (!issue) return false;

  if (Array.isArray(issue.issue_permissions)) {
    return issue.issue_permissions.includes(permissionKey);
  }

  if (Array.isArray(issue.capabilities)) {
    if (issue.capabilities.includes('ADMIN')) return true;
    if (permissionKey === 'issue:view' || permissionKey.startsWith('field:view')) {
      return issue.capabilities.includes('VIEW') || issue.capabilities.includes('EDIT');
    }
    if (permissionKey === 'issue:comment') {
      return issue.capabilities.includes('COMMENT') || issue.capabilities.includes('EDIT');
    }
    if (permissionKey === 'issue:transition') {
      return issue.capabilities.includes('TRANSITION') || issue.capabilities.includes('EDIT');
    }
    if (permissionKey === 'issue:delete') {
      return issue.capabilities.includes('DELETE') || issue.capabilities.includes('ADMIN');
    }
    return issue.capabilities.includes('EDIT');
  }

  return true;
}
