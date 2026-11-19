/**
 * Dedicated Edge Tests for TransitionRuleCard (KANBA-211, S8.1).
 * Directly triggers out-of-bounds keyboard reorder and drop edge paths.
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TransitionRuleCard } from './TransitionRuleCard';
import type { TransitionRule, WorkflowHook } from './api';

vi.mock('./HookPipelineRow', () => ({
  HookPipelineRow: (props: {
    hook: WorkflowHook;
    index: number;
    total: number;
    onMove?: (id: string, dir: 'up' | 'down') => void;
    onDropReorder?: (src: string, tgt: string) => void;
  }) => (
    <div data-testid={`hook-row-${props.hook.id}`}>
      <button
        data-testid={`move-up-${props.hook.id}`}
        onClick={() => props.onMove?.(props.hook.id, 'up')}
      >
        Move Up
      </button>
      <button
        data-testid={`move-down-${props.hook.id}`}
        onClick={() => props.onMove?.(props.hook.id, 'down')}
      >
        Move Down
      </button>
      <button
        data-testid={`move-nonexistent-${props.hook.id}`}
        onClick={() => props.onMove?.('non-existent-hook', 'up')}
      >
        Move Nonexistent
      </button>
      <button
        data-testid={`drop-same-${props.hook.id}`}
        onClick={() => props.onDropReorder?.(props.hook.id, props.hook.id)}
      >
        Drop Same
      </button>
      <button
        data-testid={`drop-unknown-src-${props.hook.id}`}
        onClick={() => props.onDropReorder?.('unknown-src', props.hook.id)}
      >
        Drop Unknown Source
      </button>
      <button
        data-testid={`drop-unknown-tgt-${props.hook.id}`}
        onClick={() => props.onDropReorder?.(props.hook.id, 'unknown-tgt')}
      >
        Drop Unknown Target
      </button>
    </div>
  ),
}));

describe('TransitionRuleCard Edge Reordering Branches', () => {
  const mockHooks: WorkflowHook[] = [
    {
      id: 'hk-1',
      name: 'Hook Alpha',
      from_state: 'todo',
      to_state: 'in_progress',
      hook_kind: 'sync_validator',
      harness_kind: 'in_app_sdk',
      sort_rank: '0|hzzzzz:',
      failure_policy: 'fail_closed',
      is_enabled: true,
      manifest_sha256: 'sha-1',
    },
    {
      id: 'hk-2',
      name: 'Hook Beta',
      from_state: 'todo',
      to_state: 'in_progress',
      hook_kind: 'sync_validator',
      harness_kind: 'in_app_sdk',
      sort_rank: '0|hzzzzz:',
      failure_policy: 'fail_closed',
      is_enabled: true,
      manifest_sha256: 'sha-2',
    },
  ];

  const mockRule: TransitionRule = {
    from_state: 'todo',
    to_state: 'in_progress',
    active_hook_count: 2,
    hooks: mockHooks,
  };

  it('covers all early return branches for keyboard moves and drop reordering', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);

    render(
      <TransitionRuleCard
        rule={mockRule}
        projectKey="KAN"
        onReorder={onReorder}
        onToggle={vi.fn()}
        onEdit={vi.fn()}
        onDetach={vi.fn()}
        onAddHook={vi.fn()}
        onDryRun={vi.fn()}
      />,
    );

    // 1. Move up from index 0 -> targetIndex (-1) < 0
    fireEvent.click(screen.getByTestId('move-up-hk-1'));

    // 2. Move down from last index -> targetIndex (2) >= length (2)
    fireEvent.click(screen.getByTestId('move-down-hk-2'));

    // 3. Move nonexistent hook -> currentIndex === -1
    fireEvent.click(screen.getByTestId('move-nonexistent-hk-1'));

    // 4. Drop same hook -> sourceIndex === targetIndex
    fireEvent.click(screen.getByTestId('drop-same-hk-1'));

    // 5. Drop with unknown source -> sourceIndex === -1
    fireEvent.click(screen.getByTestId('drop-unknown-src-hk-1'));

    // 6. Drop with unknown target -> targetIndex === -1
    fireEvent.click(screen.getByTestId('drop-unknown-tgt-hk-1'));

    // None of these should call onReorder because all returned early
    expect(onReorder).not.toHaveBeenCalled();
  });
});
