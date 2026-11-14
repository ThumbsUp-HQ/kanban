/**
 * Unit Tests for StickiesGrid Component (KB-P3-51, S8.1, S8.2).
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { StickiesGrid } from './StickiesGrid';
import type { StickyItem } from './stickiesApi';

const mockStickies: StickyItem[] = [
  {
    id: 's-1',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    body_markdown: 'First sticky',
    color_token: 'amber',
    sort_rank: '0',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    capabilities: ['EDIT', 'DELETE'],
  },
  {
    id: 's-2',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    body_markdown: 'Promoted sticky note',
    color_token: 'slate',
    sort_rank: '1',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: 'doc-123',
    is_promoted_stub: true,
    promoted_to_doc: {
      id: 'doc-123',
      title: 'Promoted Architecture Doc',
      canonical_key: 'DOC-1',
    },
    triggers: [],
    capabilities: ['EDIT'],
  },
];

describe('StickiesGrid', () => {
  it('renders stickies grid with cards and promoted stubs', () => {
    render(
      <StickiesGrid
        stickies={mockStickies}
        projectKey="KAN"
        title="Project Overview Stickies"
        onUpdateSticky={vi.fn()}
        onDeleteSticky={vi.fn()}
        onPromoteSticky={vi.fn()}
        onUnarchiveCopy={vi.fn()}
      />,
    );

    expect(screen.getByText('Project Overview Stickies')).toBeDefined();
    expect(screen.getByTestId('sticky-card-s-1')).toBeDefined();
    expect(screen.getByTestId('promoted-sticky-stub-s-2')).toBeDefined();
  });

  it('renders empty state when stickies array is empty', () => {
    const onCreate = vi.fn();
    render(
      <StickiesGrid
        stickies={[]}
        projectKey="KAN"
        onCreateSticky={onCreate}
        onUpdateSticky={vi.fn()}
        onDeleteSticky={vi.fn()}
        onPromoteSticky={vi.fn()}
        onUnarchiveCopy={vi.fn()}
      />,
    );

    expect(screen.getByText('No stickies yet')).toBeDefined();
    const createBtn = screen.getByRole('button', { name: '+ Create your first sticky' });
    fireEvent.click(createBtn);
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it('renders loading state when isLoading is true and stickies are empty', () => {
    render(
      <StickiesGrid
        stickies={[]}
        isLoading={true}
        onUpdateSticky={vi.fn()}
        onDeleteSticky={vi.fn()}
        onPromoteSticky={vi.fn()}
        onUnarchiveCopy={vi.fn()}
      />,
    );

    expect(screen.getByText('Loading stickies...')).toBeDefined();
  });

  it('suppresses create button in empty state when readOnly is true', () => {
    render(
      <StickiesGrid
        stickies={[]}
        readOnly={true}
        onUpdateSticky={vi.fn()}
        onDeleteSticky={vi.fn()}
        onPromoteSticky={vi.fn()}
        onUnarchiveCopy={vi.fn()}
      />,
    );

    expect(screen.getByText('No stickies yet')).toBeDefined();
    expect(screen.queryByRole('button', { name: '+ Create your first sticky' })).toBeNull();
  });

  it('+ New Sticky header button triggers onCreateSticky', () => {
    const onCreate = vi.fn();
    render(
      <StickiesGrid
        stickies={mockStickies}
        onCreateSticky={onCreate}
        onUpdateSticky={vi.fn()}
        onDeleteSticky={vi.fn()}
        onPromoteSticky={vi.fn()}
        onUnarchiveCopy={vi.fn()}
      />,
    );

    const newBtn = screen.getByRole('button', { name: 'Create new sticky note' });
    fireEvent.click(newBtn);
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it('announces promotion and unarchive copy events in accessible live region', async () => {
    const onPromote = vi.fn().mockResolvedValue(undefined);
    const onUnarchive = vi.fn().mockResolvedValue(undefined);

    render(
      <StickiesGrid
        stickies={mockStickies}
        onUpdateSticky={vi.fn()}
        onDeleteSticky={vi.fn()}
        onPromoteSticky={onPromote}
        onUnarchiveCopy={onUnarchive}
      />,
    );

    const unarchiveBtn = screen.getByRole('button', { name: /Unarchive editable sticky copy/i });
    act(() => {
      fireEvent.click(unarchiveBtn);
    });

    const announcement = await screen.findByTestId('stickies-announcement');
    expect(announcement.textContent).toContain('Created editable copy of sticky note.');

    // Promote sticky s-1 via menu
    const menuTrigger = screen.getByTestId('sticky-menu-trigger-s-1');
    fireEvent.click(menuTrigger);
    const convertItem = screen.getByTestId('convert-to-doc-menuitem');
    act(() => {
      fireEvent.click(convertItem);
    });

    expect(onPromote).toHaveBeenCalledWith('s-1');
    await waitFor(() => {
      expect(announcement.textContent).toContain('Promoted sticky to Doc');
    });
  });
});
