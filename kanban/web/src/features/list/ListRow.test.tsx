import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ListRow } from './ListRow';
import type { IssueItem } from '../views/viewsApi';

describe('ListRow', () => {
  it('covers all priority, gate, and assignee variations', () => {
    const onToggleSelect = vi.fn();

    const issueWithLowAndVetoed: IssueItem = {
      id: 'row-1',
      key: 'KAN-201',
      summary: 'Low priority vetoed work item',
      state: { id: 's-1', name: 'In Review', group: 'started' },
      priority: { slug: 'low', label: 'Low', sort_order: 40 },
      gate_status: 'vetoed',
      has_explicit_acl: true,
      module_ids: ['mod-1'],
      due_date: '2026-12-31',
      assignees: [
        {
          id: 'asg-1',
          kind: 'principal',
          principal: { id: 'u-1', handle: 'bob', display_name: '', type: 'USER' }, // display_name empty -> falls back to handle
        },
      ],
    };

    render(
      <ListRow
        issue={issueWithLowAndVetoed}
        isSelected={true}
        onToggleSelect={onToggleSelect}
        modulesEnabled={true}
        isFocused={true}
      />
    );

    // Verify low priority glyph
    expect(screen.getByText('💤')).toBeDefined();
    // Verify vetoed gate glyph
    expect(screen.getByText('🛑🤖')).toBeDefined();
    // Fallback handle 'bob' rendered
    expect(screen.getByText('bob')).toBeDefined();

    // Checkbox toggle
    const checkbox = screen.getByRole('checkbox', { name: 'Select KAN-201' });
    fireEvent.click(checkbox);
    expect(onToggleSelect).toHaveBeenCalledWith('KAN-201', false);

    // Non-Enter keypress does not navigate
    const row = screen.getByRole('row');
    fireEvent.keyDown(row, { key: 'Escape' });
  });

  it('covers gatePending and overdue branches', () => {
    const issuePending: IssueItem = {
      id: 'row-2',
      key: 'KAN-202',
      summary: 'Pending gate and overdue item',
      state: { id: 's-2', name: 'In Progress', group: 'started' },
      priority: { slug: 'urgent', label: 'Urgent', sort_order: 10 },
      gate_status: 'pending',
      due_date: '2020-01-01', // in past -> overdue
    };

    render(
      <ListRow
        issue={issuePending}
        modulesEnabled={false}
      />
    );

    // Pending gate glyph
    expect(screen.getByText('⏳🤖')).toBeDefined();
    // Due date overdue
    const duePill = document.querySelector('.due-pill--overdue');
    expect(duePill).toBeDefined();
  });
});
