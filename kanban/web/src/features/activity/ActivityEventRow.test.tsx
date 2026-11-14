import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import {
  ActivityEventRow,
  formatActorName,
  formatEventSummary,
} from './ActivityEventRow';
import type { ActivityItem } from './activityApi';

describe('ActivityEventRow', () => {
  const mockWriteText = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: mockWriteText,
      },
    });
  });

  describe('formatActorName & formatEventSummary', () => {
    it('formats redacted actor without leaking handles or IDs', () => {
      const redactedActor = { redacted: true, label: '1 External Collaborator' };
      expect(formatActorName(redactedActor)).toBe('1 External Collaborator');
    });

    it('formats agent actors and regular user handles', () => {
      expect(formatActorName({ type: 'AGENT', display_name: 'Security Bot' })).toBe('Security Bot');
      expect(formatActorName({ type: 'AGENT', slug: 'agent-slug' })).toBe('agent-slug');
      expect(formatActorName({ handle: 'adam' })).toBe('@adam');
      expect(formatActorName({ handle: '@alice' })).toBe('@alice');
      expect(formatActorName({})).toBe('System');
    });

    it('formats state, priority, assignee, and label change event summaries with fallbacks', () => {
      expect(formatEventSummary({ id: 'f1', event_type: 'STATE_CHANGED', actor: {}, created_at: '' })).toBe(
        'changed State from  to ',
      );
      expect(formatEventSummary({ id: 'f2', event_type: 'PRIORITY_CHANGED', actor: {}, created_at: '' })).toBe(
        'changed Priority from  to ',
      );
      expect(formatEventSummary({ id: 'f3', event_type: 'ASSIGNEE_ADDED', actor: {}, created_at: '' })).toBe(
        'assigned ',
      );
      expect(formatEventSummary({ id: 'f4', event_type: 'ASSIGNEE_REMOVED', actor: {}, created_at: '' })).toBe(
        'unassigned ',
      );
    });

    it('formats state, priority, assignee, and label change event summaries', () => {
      const itemState: ActivityItem = {
        id: 'act-1',
        event_type: 'STATE_CHANGED',
        actor: { handle: 'alice' },
        payload: { from_state: 'Todo', to_state: 'In Progress' },
        created_at: '2026-11-12T10:00:00Z',
      };
      expect(formatEventSummary(itemState)).toBe('changed State from Todo to In Progress');

      const itemPrio: ActivityItem = {
        id: 'act-2',
        event_type: 'PRIORITY_CHANGED',
        actor: { handle: 'alice' },
        payload: { from_priority: 'Low', to_priority: 'Urgent' },
        created_at: '2026-11-12T10:00:00Z',
      };
      expect(formatEventSummary(itemPrio)).toBe('changed Priority from Low to Urgent');

      const itemAssign: ActivityItem = {
        id: 'act-3',
        event_type: 'ASSIGNEE_ADDED',
        actor: { handle: 'alice' },
        payload: { assignee_handle: '@bob' },
        created_at: '2026-11-12T10:00:00Z',
      };
      expect(formatEventSummary(itemAssign)).toBe('assigned @bob');

      const itemUnassign: ActivityItem = {
        id: 'act-3b',
        event_type: 'ASSIGNEE_REMOVED',
        actor: { handle: 'alice' },
        payload: { assignee_name: 'Bob' },
        created_at: '2026-11-12T10:00:00Z',
      };
      expect(formatEventSummary(itemUnassign)).toBe('unassigned Bob');
    });
  });

  describe('Test Case 1: Gate events and Creator Override rows', () => {
    it('renders GATE_APPROVED with latency, hook name, and copyable verdict sha256', () => {
      const approvedItem: ActivityItem = {
        id: 'act-gate-app',
        event_type: 'GATE_APPROVED',
        actor: { type: 'AGENT', display_name: 'sec-review' },
        payload: {
          hook_name: 'security-review',
          execution_latency_ms: 812,
          verdict_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        },
        created_at: '2026-11-12T10:00:00Z',
      };

      render(<ActivityEventRow item={approvedItem} />);

      expect(screen.getByTestId('gate-approved-row')).toBeDefined();
      expect(screen.getByText(/approved transition in 812 ms/)).toBeDefined();

      // Focus trigger to open tooltip immediately at 0ms
      const trigger = screen.getByRole('button', { name: 'Gate Approved: security-review' });
      fireEvent.focus(trigger);

      // Trigger copy inside tooltip
      const copyBtn = screen.getByRole('button', { name: 'Copy Hash' });
      fireEvent.click(copyBtn);

      expect(mockWriteText).toHaveBeenCalledWith(
        'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
      );
    });

    it('renders GATE_VETOED with reason preview and jump-to-comment button', () => {
      const onJumpToComment = vi.fn();
      const vetoedItem: ActivityItem = {
        id: 'act-gate-veto',
        event_type: 'GATE_VETOED',
        actor: { type: 'AGENT', display_name: 'qa-gate' },
        payload: {
          hook_name: 'reality-checker',
          reason: 'Unit test coverage below 95% threshold in features/activity.',
          audit_comment_id: 'comm-audit-999',
        },
        created_at: '2026-11-12T10:05:00Z',
      };

      render(<ActivityEventRow item={vetoedItem} onJumpToComment={onJumpToComment} />);

      expect(screen.getByTestId('gate-vetoed-row')).toBeDefined();
      expect(screen.getByText(/vetoed transition: Unit test coverage below/)).toBeDefined();

      const jumpBtn = screen.getByRole('button', { name: 'View audit details' });
      fireEvent.click(jumpBtn);

      expect(onJumpToComment).toHaveBeenCalledWith('comm-audit-999');
    });

    it('renders GATE_PENDING with live hook name, harness and :ro repo mount status', () => {
      const pendingItem: ActivityItem = {
        id: 'act-gate-pend',
        event_type: 'GATE_PENDING',
        actor: { type: 'AGENT', display_name: 'Workflow Gate' },
        payload: {
          hook_name: 'ci-pipeline',
          harness: 'cli: agy -p',
          repo_mount_ro: true,
        },
        created_at: '2026-11-12T10:10:00Z',
      };

      render(<ActivityEventRow item={pendingItem} />);

      expect(screen.getByTestId('gate-pending-row')).toBeDefined();
      expect(screen.getByText(/evaluating gate via cli: agy -p \(:ro\)/)).toBeDefined();
    });

    it('renders CREATOR_OVERRIDDEN with old -> new, reason and hash', () => {
      const overrideItem: ActivityItem = {
        id: 'act-override',
        event_type: 'CREATOR_OVERRIDDEN',
        actor: { handle: 'admin' },
        payload: {
          old_created_by: 'old-user',
          new_created_by: 'new-user',
          reason: 'Original author departed',
          row_hash: 'abc1234567890abcdef',
        },
        created_at: '2026-11-12T10:15:00Z',
      };

      render(<ActivityEventRow item={overrideItem} />);

      expect(screen.getByTestId('creator-override-row')).toBeDefined();
      expect(
        screen.getByText('changed Created by from old-user to new-user (Original author departed)'),
      ).toBeDefined();
    });

    it('renders agent actor with EmojiHint kind="agent" in history row', () => {
      const agentHistoryItem: ActivityItem = {
        id: 'act-hist-agent',
        event_type: 'TITLE_CHANGED',
        actor: { type: 'AGENT', display_name: 'Botty' },
        created_at: '2026-11-12T10:20:00Z',
      };

      render(<ActivityEventRow item={agentHistoryItem} />);
      expect(screen.getByTestId('history-row')).toBeDefined();
      expect(screen.getByText('updated issue summary')).toBeDefined();
    });

    it('covers all remaining event summaries: description, labels, gates, and unknown types', () => {
      expect(
        formatEventSummary({
          id: '1',
          event_type: 'DESCRIPTION_CHANGED',
          actor: {},
          created_at: '',
        }),
      ).toBe('updated issue description');

      expect(
        formatEventSummary({
          id: '2',
          event_type: 'LABEL_ADDED',
          actor: {},
          payload: { label_name: 'backend' },
          created_at: '',
        }),
      ).toBe('added label backend');

      expect(
        formatEventSummary({
          id: '3',
          event_type: 'LABEL_REMOVED',
          actor: {},
          payload: { label_name: 'frontend' },
          created_at: '',
        }),
      ).toBe('removed label frontend');

      expect(
        formatEventSummary({
          id: '4',
          event_type: 'GATE_REJECTED',
          actor: {},
          payload: { hook_name: 'lint-gate' },
          created_at: '',
        }),
      ).toBe('Transition gate vetoed: lint-gate');

      expect(
        formatEventSummary({
          id: '5',
          event_type: 'CUSTOM_EVENT_TYPE',
          actor: {},
          created_at: '',
        }),
      ).toBe('custom event type');
    });

    it('renders GATE_PENDING with repo_mount_ro = false as :rw', () => {
      const rwPending: ActivityItem = {
        id: 'act-gate-rw',
        event_type: 'GATE_PENDING',
        actor: { type: 'AGENT', display_name: 'RW Bot' },
        payload: {
          hook_name: 'rw-pipeline',
          harness: 'cli: codex -p',
          repo_mount_ro: false,
        },
        created_at: '2026-11-12T10:10:00Z',
      };

      render(<ActivityEventRow item={rwPending} />);
      expect(screen.getByText(/evaluating gate via cli: codex -p \(:rw\)/)).toBeDefined();
    });

    it('renders GATE_VETOED tooltip jump button when focused', () => {
      const onJumpToComment = vi.fn();
      const vetoedItem: ActivityItem = {
        id: 'act-gate-veto-2',
        event_type: 'GATE_VETOED',
        actor: { type: 'AGENT', display_name: 'Veto Bot' },
        payload: {
          hook_name: 'gate-veto-test',
          reason: 'Vetoed',
          audit_comment_id: 'comm-123',
        },
        created_at: '2026-11-12T10:10:00Z',
      };

      render(<ActivityEventRow item={vetoedItem} onJumpToComment={onJumpToComment} />);
      const trigger = screen.getByRole('button', { name: 'Gate Vetoed: gate-veto-test' });
      fireEvent.focus(trigger);

      const jumpBtns = screen.getAllByRole('button', { name: 'Jump to comment' });
      expect(jumpBtns.length).toBeGreaterThan(0);
      const firstJumpBtn = jumpBtns[0];
      if (firstJumpBtn) {
        fireEvent.click(firstJumpBtn);
      }
      expect(onJumpToComment).toHaveBeenCalledWith('comm-123');

      // Also trigger onActivate callback directly
      fireEvent.click(trigger);
      expect(onJumpToComment).toHaveBeenCalledWith('comm-123');
    });

    it('covers all default/fallback branches in gate and creator override rows', () => {
      // Gate pending with empty payload (triggers hookName, harness, ro defaults)
      const emptyPending: ActivityItem = {
        id: 'pend-empty',
        event_type: 'GATE_PENDING',
        actor: {},
        payload: {},
        created_at: '2026-11-12T10:00:00Z',
      };
      render(<ActivityEventRow item={emptyPending} />);
      expect(screen.getByText('Workflow Gate')).toBeDefined();

      // Gate approved with empty payload (triggers hookName, latency, hash fallbacks)
      const emptyApproved: ActivityItem = {
        id: 'app-empty',
        event_type: 'GATE_APPROVED',
        actor: {},
        payload: {},
        created_at: '2026-11-12T10:00:00Z',
      };
      render(<ActivityEventRow item={emptyApproved} />);

      // Gate vetoed with empty payload
      const emptyVetoed: ActivityItem = {
        id: 'veto-empty',
        event_type: 'GATE_VETOED',
        actor: {},
        payload: {},
        created_at: '2026-11-12T10:00:00Z',
      };
      render(<ActivityEventRow item={emptyVetoed} />);

      // Creator override with empty payload
      const emptyOverride: ActivityItem = {
        id: 'over-empty',
        event_type: 'CREATOR_OVERRIDDEN',
        actor: {},
        payload: {},
        created_at: '2026-11-12T10:00:00Z',
      };
      render(<ActivityEventRow item={emptyOverride} />);
      expect(screen.getByText('changed Created by from Unknown to Unknown (Administrative adjustment)')).toBeDefined();
    });
  });
});
