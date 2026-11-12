import type { IssueItem, ProjectMetadata } from './viewsApi';

export const FIXTURE_PROJECT_KAN: ProjectMetadata = {
  key: 'KAN',
  name: 'Platform Core',
  modules_enabled: true,
};

export const FIXTURE_PROJECT_NOMODULES: ProjectMetadata = {
  key: 'KAN',
  name: 'Platform Core (No Modules)',
  modules_enabled: false,
};

export const FIXTURE_12_ISSUES: IssueItem[] = [
  {
    id: '01931234-0001-7000-8000-000000000001',
    key: 'KAN-140',
    summary: 'Evaluate Postgres RLS performance under heavy load',
    state: { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 10 },
    priority: { slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 30 },
    due_date: '2026-12-01',
    labels: [{ id: 'lbl-1', name: 'Database', color_hex: '#2563eb' }],
    assignees: [
      {
        id: 'asg-1',
        kind: 'principal',
        principal: { id: 'u-1', handle: 'alice', display_name: 'Alice Cooper', type: 'USER' },
      },
    ],
  },
  {
    id: '01931234-0002-7000-8000-000000000002',
    key: 'KAN-141',
    summary: 'Design database schema for cycle burndown metrics',
    state: { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 10 },
    priority: { slug: 'low', label: 'Low', emoji: '💤', sort_order: 40 },
    due_date: '2026-12-05',
  },
  {
    id: '01931234-0003-7000-8000-000000000003',
    key: 'KAN-142',
    summary: 'Refactor OAuth token rotation and HMAC verification',
    state: { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 30 },
    priority: { slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 10 },
    due_date: '2026-11-20',
    has_explicit_acl: true,
    gate_status: 'approved',
    module_ids: ['mod-1'],
    labels: [
      { id: 'lbl-sec', name: 'Security', color_hex: '#dc2626' },
      { id: 'lbl-auth', name: 'Auth', color_hex: '#7c3aed' },
      { id: 'lbl-extra', name: 'Extra', color_hex: '#10b981' },
    ],
    assignees: [
      {
        id: 'asg-ext',
        kind: 'free_text',
        free_text: 'Ext: SecAudit',
        notify: false,
        hint: 'External free-text label - grants zero access and sends zero notifications',
      },
    ],
  },
  {
    id: '01931234-0004-7000-8000-000000000004',
    key: 'KAN-143',
    summary: 'Implement Pragmatic DnD board column virtualization',
    state: { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 20 },
    priority: { slug: 'high', label: 'High', emoji: '⚡', sort_order: 20 },
    due_date: '2026-11-15',
    cycle_id: 'cycle-1',
  },
  {
    id: '01931234-0005-7000-8000-000000000005',
    key: 'KAN-144',
    summary: 'Audit CSP violations on third party script injections',
    state: { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 20 },
    priority: { slug: 'high', label: 'High', emoji: '⚡', sort_order: 20 },
    due_date: '2026-11-18',
  },
  {
    id: '01931234-0006-7000-8000-000000000006',
    key: 'KAN-145',
    summary: 'Integrate WebAuthn Passkeys userVerification required',
    state: { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 30 },
    priority: { slug: 'high', label: 'High', emoji: '⚡', sort_order: 20 },
    due_date: '2026-11-25',
    gate_status: 'pending',
  },
  {
    id: '01931234-0007-7000-8000-000000000007',
    key: 'KAN-146',
    summary: 'Review surgical right-click contextmenu event handling',
    state: { id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 40 },
    priority: { slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 30 },
    due_date: '2026-11-30',
  },
  {
    id: '01931234-0008-7000-8000-000000000008',
    key: 'KAN-147',
    summary: 'Verify isolated Mermaid Web Worker sandbox security',
    state: { id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 40 },
    priority: { slug: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 10 },
    gate_status: 'vetoed',
  },
  {
    id: '01931234-0009-7000-8000-000000000009',
    key: 'KAN-148',
    summary: 'Completed issue past due date should not be marked overdue',
    state: { id: 'state-done', name: 'Done', group: 'completed', sort_order: 50 },
    priority: { slug: 'low', label: 'Low', emoji: '💤', sort_order: 40 },
    due_date: '2026-01-01', // in past, but completed -> NOT overdue!
  },
  {
    id: '01931234-0010-7000-8000-000000000010',
    key: 'KAN-149',
    summary: 'Setup tmpfs Postgres template database for CI pipeline',
    state: { id: 'state-done', name: 'Done', group: 'completed', sort_order: 50 },
    priority: { slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 30 },
    due_date: '2026-02-01',
  },
  {
    id: '01931234-0011-7000-8000-000000000011',
    key: 'KAN-150',
    summary: 'Cancelled issue should also suppress overdue highlight',
    state: { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled', sort_order: 60 },
    priority: { slug: 'low', label: 'Low', emoji: '💤', sort_order: 40 },
    due_date: '2026-01-15',
  },
  {
    id: '01931234-0012-7000-8000-000000000012',
    key: 'KAN-151',
    summary: 'Final regression testing and release packaging',
    state: { id: 'state-done', name: 'Done', group: 'completed', sort_order: 50 },
    priority: { slug: 'medium', label: 'Medium', emoji: '🔹', sort_order: 30 },
  },
];
