// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect } from 'vitest';
import { canModifyIssueField, hasIssuePermission } from '../permissions';

describe('Granular RBAC Issue Permissions Evaluator (KAN-83)', () => {
  it('respects editable_fields list over legacy capabilities', () => {
    const issue = {
      capabilities: ['EDIT'],
      editable_fields: ['summary', 'description'],
      issue_permissions: ['issue:view', 'issue:comment'],
    };

    expect(canModifyIssueField(issue, 'summary')).toBe(true);
    expect(canModifyIssueField(issue, 'description')).toBe(true);
    expect(canModifyIssueField(issue, 'priority')).toBe(false);
    expect(canModifyIssueField(issue, 'state')).toBe(false);
  });

  it('falls back to capabilities when editable_fields is absent and defaults to true when both absent', () => {
    const editIssue = {
      capabilities: ['EDIT'],
    };
    expect(canModifyIssueField(editIssue, 'priority')).toBe(true);
    expect(canModifyIssueField(editIssue, 'summary')).toBe(true);

    const adminIssue = {
      capabilities: ['ADMIN'],
    };
    expect(canModifyIssueField(adminIssue, 'priority')).toBe(true);

    const viewerIssue = {
      capabilities: ['VIEW'],
    };
    expect(canModifyIssueField(viewerIssue, 'priority')).toBe(false);
    expect(canModifyIssueField(viewerIssue, 'summary')).toBe(false);

    expect(canModifyIssueField({}, 'summary')).toBe(true);
  });

  it('respects issue_permissions list over legacy capabilities', () => {
    const issue = {
      capabilities: ['VIEW'],
      editable_fields: [],
      issue_permissions: ['issue:view', 'issue:comment', 'field:attach_files'],
    };

    expect(hasIssuePermission(issue, 'issue:view')).toBe(true);
    expect(hasIssuePermission(issue, 'issue:comment')).toBe(true);
    expect(hasIssuePermission(issue, 'field:attach_files')).toBe(true);
    expect(hasIssuePermission(issue, 'issue:delete')).toBe(false);
    expect(hasIssuePermission(issue, 'issue:transition')).toBe(false);
  });

  it('evaluates legacy capabilities mappings in hasIssuePermission when issue_permissions is absent', () => {
    expect(hasIssuePermission({ capabilities: ['ADMIN'] }, 'issue:delete')).toBe(true);
    expect(hasIssuePermission({ capabilities: ['VIEW'] }, 'issue:view')).toBe(true);
    expect(hasIssuePermission({ capabilities: ['EDIT'] }, 'field:view_summary')).toBe(true);
    expect(hasIssuePermission({ capabilities: [] }, 'issue:view')).toBe(false);

    expect(hasIssuePermission({ capabilities: ['COMMENT'] }, 'issue:comment')).toBe(true);
    expect(hasIssuePermission({ capabilities: ['EDIT'] }, 'issue:comment')).toBe(true);
    expect(hasIssuePermission({ capabilities: ['VIEW'] }, 'issue:comment')).toBe(false);

    expect(hasIssuePermission({ capabilities: ['TRANSITION'] }, 'issue:transition')).toBe(true);
    expect(hasIssuePermission({ capabilities: ['EDIT'] }, 'issue:transition')).toBe(true);
    expect(hasIssuePermission({ capabilities: ['VIEW'] }, 'issue:transition')).toBe(false);

    expect(hasIssuePermission({ capabilities: ['DELETE'] }, 'issue:delete')).toBe(true);
    expect(hasIssuePermission({ capabilities: ['VIEW'] }, 'issue:delete')).toBe(false);

    expect(hasIssuePermission({ capabilities: ['EDIT'] }, 'issue:move_rank')).toBe(true);
    expect(hasIssuePermission({ capabilities: ['VIEW'] }, 'issue:move_rank')).toBe(false);

    expect(hasIssuePermission({}, 'issue:move_rank')).toBe(true);
  });

  it('returns false for null or undefined issue', () => {
    expect(canModifyIssueField(null, 'summary')).toBe(false);
    expect(canModifyIssueField(undefined, 'summary')).toBe(false);
    expect(hasIssuePermission(null, 'issue:view')).toBe(false);
    expect(hasIssuePermission(undefined, 'issue:view')).toBe(false);
  });
});
