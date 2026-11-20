import { describe, expect, it, vi } from 'vitest';
import * as clientModule from '../../api/client.ts';
import {
  applyOptimisticMove,
  moveIssueApi,
  type BoardIssue,
} from './boardApi.ts';

describe('boardApi', () => {
  it('moveIssueApi constructs request body and calls apiFetch with all params', async () => {
    const fetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({
      issue_key: 'KAN-1',
      state_id: 'st-2',
      board_rank: 'rank-1',
      rebalance_scheduled: false,
    });

    const res = await moveIssueApi({
      projectKey: 'KAN',
      issueKey: 'KAN-1',
      targetStateId: 'st-2',
      afterIssueKey: 'KAN-0',
      beforeIssueKey: 'KAN-2',
      boardRank: 'rank-1',
      overrideWip: true,
      wipOverrideReason: 'Critical security fix release',
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/issues/{issue_ref}/move',
      {
        params: { issue_ref: 'KAN-1' },
        body: {
          override_wip: true,
          target_state_id: 'st-2',
          after_issue: 'KAN-0',
          before_issue: 'KAN-2',
          wip_override_reason: 'Critical security fix release',
        },
      },
    );
    expect(res.issue_key).toBe('KAN-1');
  });

  it('moveIssueApi handles minimal params with defaults', async () => {
    const fetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({
      issue_key: 'KAN-1',
      state_id: 'st-1',
      board_rank: 'rank-1',
      rebalance_scheduled: false,
    });

    await moveIssueApi({
      projectKey: 'KAN',
      issueKey: 'KAN-1',
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/issues/{issue_ref}/move',
      {
        params: { issue_ref: 'KAN-1' },
        body: {
          override_wip: false,
        },
      },
    );

    // Call with afterIssueKey only
    await moveIssueApi({
      projectKey: 'KAN',
      issueKey: 'KAN-1',
      afterIssueKey: 'KAN-PREV',
    });
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'POST',
      '/api/v1/issues/{issue_ref}/move',
      {
        params: { issue_ref: 'KAN-1' },
        body: {
          override_wip: false,
          after_issue: 'KAN-PREV',
        },
      },
    );

    // Call with beforeIssueKey and wipOverrideReason only
    await moveIssueApi({
      projectKey: 'KAN',
      issueKey: 'KAN-1',
      beforeIssueKey: 'KAN-NEXT',
      wipOverrideReason: 'Override reason text',
    });
    expect(fetchSpy).toHaveBeenLastCalledWith(
      'POST',
      '/api/v1/issues/{issue_ref}/move',
      {
        params: { issue_ref: 'KAN-1' },
        body: {
          override_wip: false,
          before_issue: 'KAN-NEXT',
          wip_override_reason: 'Override reason text',
        },
      },
    );
  });

  it('applyOptimisticMove returns empty array for empty or undefined cache', () => {
    expect(applyOptimisticMove(undefined, { projectKey: 'KAN', issueKey: 'KAN-1' })).toEqual([]);
    expect(applyOptimisticMove([], { projectKey: 'KAN', issueKey: 'KAN-1' })).toEqual([]);
  });

  it('applyOptimisticMove returns unchanged cache if issue is not found', () => {
    const cache: BoardIssue[] = [
      { id: '1', key: 'KAN-1', summary: 'Item 1', state_id: 'st-1', board_rank: 'r1' },
    ];
    const res = applyOptimisticMove(cache, { projectKey: 'KAN', issueKey: 'KAN-999' });
    expect(res).toBe(cache);
  });

  it('applyOptimisticMove updates state and rank preserving all optional fields', () => {
    const cache: BoardIssue[] = [
      {
        id: '1',
        key: 'KAN-1',
        summary: 'Item 1',
        state_id: 'st-1',
        board_rank: 'r1',
        priority: { id: 'p1', label: 'Urgent', slug: 'urgent' },
        assignees: [{ id: 'u1', handle: 'alice' }],
        cycle: { id: 'c1', name: 'Sprint 1' },
        due_date: '2026-12-01',
        gate_status: 'approved',
        has_explicit_acl: true,
      },
    ];

    const res = applyOptimisticMove(cache, {
      projectKey: 'KAN',
      issueKey: 'KAN-1',
      targetStateId: 'st-2',
      boardRank: 'r2',
    });

    expect(res[0]?.state_id).toBe('st-2');
    expect(res[0]?.board_rank).toBe('r2');
    expect(res[0]?.priority?.slug).toBe('urgent');
    expect(res[0]?.cycle?.name).toBe('Sprint 1');
    expect(res[0]?.has_explicit_acl).toBe(true);
  });

  it('applyOptimisticMove preserves issues when optional fields are omitted', () => {
    const minimalCache: BoardIssue[] = [
      {
        id: '1',
        key: 'KAN-MIN',
        summary: 'Minimal issue',
        state_id: 'st-1',
        board_rank: 'r1',
      },
    ];

    const res = applyOptimisticMove(minimalCache, {
      projectKey: 'KAN',
      issueKey: 'KAN-MIN',
      targetStateId: 'st-2',
    });

    expect(res[0]?.state_id).toBe('st-2');
    expect(res[0]?.board_rank).toBe('r1');
    expect(res[0]?.priority).toBeUndefined();
    expect(res[0]?.assignees).toBeUndefined();
    expect(res[0]?.cycle).toBeUndefined();
    expect(res[0]?.due_date).toBeUndefined();
    expect(res[0]?.gate_status).toBeUndefined();
    expect(res[0]?.has_explicit_acl).toBeUndefined();

    // Test with targetStateId omitted (only boardRank provided)
    const resRankOnly = applyOptimisticMove(minimalCache, {
      projectKey: 'KAN',
      issueKey: 'KAN-MIN',
      boardRank: 'r-updated',
    });
    expect(resRankOnly[0]?.state_id).toBe('st-1');
    expect(resRankOnly[0]?.board_rank).toBe('r-updated');
  });

  it('applyOptimisticMove preserves full IssueSummary fields and resolves state from availableStates', () => {
    const fullIssueCache = [
      {
        id: '01912345-6789-7000-8000-000000000001',
        key: 'KAN-42',
        summary: 'Full Issue Summary',
        description_markdown: 'Detailed description',
        state_id: 'state-todo',
        state: {
          id: 'state-todo',
          name: 'To Do',
          group: 'unstarted',
          color_hex: '#3b82f6',
        },
        priority: { slug: 'high', label: 'High', emoji: '🔺' },
        labels: [{ id: 'lbl-1', name: 'security' }],
        module_ids: ['mod-1'],
        board_rank: '000010',
      },
    ];

    const availableStates = [
      { id: 'state-todo', name: 'To Do', group: 'unstarted', color_hex: '#3b82f6' },
      { id: 'state-in-progress', name: 'In Progress', group: 'started', color_hex: '#f59e0b' },
    ];

    const res = applyOptimisticMove(
      fullIssueCache,
      {
        projectKey: 'KAN',
        issueKey: 'KAN-42',
        targetStateId: 'state-in-progress',
        boardRank: '000020',
      },
      availableStates,
    );

    expect(Array.isArray(res)).toBe(true);
    const updated = res[0];
    expect(updated?.state_id).toBe('state-in-progress');
    expect(updated?.state).toEqual({
      id: 'state-in-progress',
      name: 'In Progress',
      group: 'started',
      color_hex: '#f59e0b',
    });
    expect(updated?.description_markdown).toBe('Detailed description');
    expect(updated?.labels).toEqual([{ id: 'lbl-1', name: 'security' }]);
    expect(updated?.module_ids).toEqual(['mod-1']);
    expect(updated?.board_rank).toBe('000020');
  });

  it('applyOptimisticMove supports object envelope { items: [...] }', () => {
    const envelope = {
      items: [
        {
          id: '1',
          key: 'KAN-1',
          summary: 'Enveloped Item',
          state_id: 'st-1',
          board_rank: 'r1',
        },
      ],
      total: 1,
    };

    const res = applyOptimisticMove(envelope, {
      projectKey: 'KAN',
      issueKey: 'KAN-1',
      targetStateId: 'st-2',
      boardRank: 'r2',
    });

    expect(typeof res).toBe('object');
    expect('items' in res).toBe(true);
    const updatedEnvelope = res as { items: typeof envelope.items; total: number };
    expect(updatedEnvelope.items[0]?.state_id).toBe('st-2');
    expect(updatedEnvelope.items[0]?.board_rank).toBe('r2');
    expect(updatedEnvelope.total).toBe(1);

    // Empty envelope
    const emptyRes = applyOptimisticMove({ items: [] }, { projectKey: 'KAN', issueKey: 'KAN-1' });
    expect(emptyRes).toEqual({ items: [] });
  });
});
