/**
 * Unit Tests for StickyCard Component (KB-P3-51, S8.1, S8.2).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { StickyCard } from './StickyCard';
import type { StickyItem } from './stickiesApi';

const baseSticky: StickyItem = {
  id: 'sticky-1',
  workspace_id: 'ws-1',
  project_id: 'proj-1',
  body_markdown: 'Short triage note',
  color_token: 'amber',
  sort_rank: '0',
  promotion_recommended: false,
  promotion_snoozed_at_length: null,
  promoted_to_doc_id: null,
  is_promoted_stub: false,
  triggers: [],
  etag: '"etag-1"',
  capabilities: ['EDIT', 'DELETE'],
};

describe('StickyCard', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders 6-swatch radiogroup without any inline styles', () => {
    const onUpdate = vi.fn();
    render(
      <StickyCard
        sticky={baseSticky}
        onUpdate={onUpdate}
        onDelete={vi.fn()}
        onPromote={vi.fn()}
      />,
    );

    const radiogroup = screen.getByRole('radiogroup', { name: 'Sticky color' });
    expect(radiogroup).toBeDefined();

    const swatches = screen.getAllByRole('radio');
    expect(swatches).toHaveLength(6);

    // Selected swatch is amber
    const amberSwatch = screen.getByRole('radio', { name: 'Color amber' });
    expect(amberSwatch.getAttribute('aria-checked')).toBe('true');
    expect(amberSwatch.getAttribute('style')).toBeNull();

    // Select mint
    const mintSwatch = screen.getByRole('radio', { name: 'Color mint' });
    fireEvent.click(mintSwatch);

    expect(onUpdate).toHaveBeenCalledWith(
      'sticky-1',
      { color_token: 'mint' },
      '"etag-1"',
    );
  });

  it('supports keyboard arrow navigation across the color radiogroup', () => {
    const onUpdate = vi.fn();
    render(
      <StickyCard
        sticky={baseSticky}
        onUpdate={onUpdate}
        onDelete={vi.fn()}
        onPromote={vi.fn()}
      />,
    );

    const radiogroup = screen.getByRole('radiogroup', { name: 'Sticky color' });

    // ArrowRight moves from amber to mint
    fireEvent.keyDown(radiogroup, { key: 'ArrowRight' });
    expect(onUpdate).toHaveBeenLastCalledWith('sticky-1', { color_token: 'mint' }, '"etag-1"');

    // ArrowDown also moves to next (mint to sky)
    fireEvent.keyDown(radiogroup, { key: 'ArrowDown' });
    expect(onUpdate).toHaveBeenLastCalledWith('sticky-1', { color_token: 'sky' }, '"etag-1"');

    // ArrowLeft moves back (sky to mint)
    fireEvent.keyDown(radiogroup, { key: 'ArrowLeft' });
    expect(onUpdate).toHaveBeenLastCalledWith('sticky-1', { color_token: 'mint' }, '"etag-1"');

    // ArrowUp also moves to previous (mint to amber)
    fireEvent.keyDown(radiogroup, { key: 'ArrowUp' });
    expect(onUpdate).toHaveBeenLastCalledWith('sticky-1', { color_token: 'amber' }, '"etag-1"');

    // ArrowLeft wraps from amber to slate (wrap around)
    fireEvent.keyDown(radiogroup, { key: 'ArrowLeft' });
    expect(onUpdate).toHaveBeenLastCalledWith('sticky-1', { color_token: 'slate' }, '"etag-1"');

    // Other keys do not trigger update
    fireEvent.keyDown(radiogroup, { key: 'Escape' });
    expect(onUpdate).toHaveBeenCalledTimes(5);
  });

  it('evaluates 1000ms idle debounce: banner suppressed at 999ms and appears at 1000ms', () => {
    const onUpdate = vi.fn();
    render(
      <StickyCard
        sticky={baseSticky}
        onUpdate={onUpdate}
        onDelete={vi.fn()}
        onPromote={vi.fn()}
      />,
    );

    // Initial state: short note, no banner
    expect(screen.queryByTestId('sticky-promotion-banner')).toBeNull();

    // Toggle raw mode to input markdown text
    const rawToggle = screen.getByTestId('sticky-editor-sticky-1-raw-toggle');
    fireEvent.click(rawToggle);
    const rawTextarea = screen.getByTestId('sticky-editor-sticky-1-raw');

    // Type first chunk to start debounce timer
    fireEvent.change(rawTextarea, { target: { value: 'Partial text' } });
    act(() => {
      vi.advanceTimersByTime(500);
    });

    // Type 650 chars note (re-triggers debounce, clearing previous timer)
    const longNote = '# Spec Overview\n## Goals\n' + 'x'.repeat(630);
    fireEvent.change(rawTextarea, { target: { value: longNote } });

    // Advance 999ms: debounce has not fired, banner not yet displayed
    act(() => {
      vi.advanceTimersByTime(999);
    });

    expect(screen.queryByTestId('sticky-promotion-banner')).toBeNull();

    // Advance to 1000ms
    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(screen.getByTestId('sticky-promotion-banner')).toBeDefined();
    expect(screen.getByText('Growing into a spec')).toBeDefined();
  });

  it('clicking snooze immediately suppresses the promotion banner', () => {
    const onUpdate = vi.fn();
    const longNoteSticky: StickyItem = {
      ...baseSticky,
      body_markdown: 'y'.repeat(650),
    };

    render(
      <StickyCard
        sticky={longNoteSticky}
        onUpdate={onUpdate}
        onDelete={vi.fn()}
        onPromote={vi.fn()}
      />,
    );

    expect(screen.getByTestId('sticky-promotion-banner')).toBeDefined();

    const snoozeBtn = screen.getByRole('button', { name: 'Snooze promotion' });
    fireEvent.click(snoozeBtn);

    expect(onUpdate).toHaveBeenCalledWith(
      'sticky-1',
      { promotion_snoozed_at_length: 650 },
      '"etag-1"',
    );

    expect(screen.queryByTestId('sticky-promotion-banner')).toBeNull();
  });

  it('clicking Promote to Doc invokes onPromote callback', () => {
    const onPromote = vi.fn().mockResolvedValue(undefined);
    const longSticky: StickyItem = {
      ...baseSticky,
      body_markdown: 'z'.repeat(650),
    };

    render(
      <StickyCard
        sticky={longSticky}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onPromote={onPromote}
      />,
    );

    const promoteBtn = screen.getByRole('button', { name: 'Promote to Doc' });
    act(() => {
      fireEvent.click(promoteBtn);
    });

    expect(onPromote).toHaveBeenCalledWith('sticky-1');
  });

  it('⋯ menu allows Convert to Doc and Delete Sticky actions', () => {
    const onDelete = vi.fn();
    const onPromote = vi.fn().mockResolvedValue(undefined);

    render(
      <StickyCard
        sticky={baseSticky}
        onUpdate={vi.fn()}
        onDelete={onDelete}
        onPromote={onPromote}
      />,
    );

    const menuTrigger = screen.getByRole('button', { name: 'Sticky actions' });
    fireEvent.click(menuTrigger);

    const deleteItem = screen.getByRole('menuitem', { name: 'Delete Sticky' });
    fireEvent.click(deleteItem);

    expect(onDelete).toHaveBeenCalledWith('sticky-1');

    // Re-open and convert to doc
    fireEvent.click(menuTrigger);
    const convertItem = screen.getByRole('menuitem', { name: 'Convert to Doc' });
    act(() => {
      fireEvent.click(convertItem);
    });

    expect(onPromote).toHaveBeenCalledWith('sticky-1');
  });

  it('access inspector button dispatches custom event', () => {
    const eventHandler = vi.fn();
    window.addEventListener('kb:open-access-inspector', eventHandler);

    render(
      <StickyCard
        sticky={baseSticky}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onPromote={vi.fn()}
      />,
    );

    const accessBtn = screen.getByRole('button', { name: 'Inspect effective access' });
    fireEvent.click(accessBtn);

    expect(eventHandler).toHaveBeenCalled();
    window.removeEventListener('kb:open-access-inspector', eventHandler);
  });

  it('flushes unsaved changes on blur', () => {
    const onUpdate = vi.fn();
    render(
      <StickyCard
        sticky={baseSticky}
        onUpdate={onUpdate}
        onDelete={vi.fn()}
        onPromote={vi.fn()}
      />,
    );

    const rawToggle = screen.getByTestId('sticky-editor-sticky-1-raw-toggle');
    fireEvent.click(rawToggle);
    const rawTextarea = screen.getByTestId('sticky-editor-sticky-1-raw');

    // Blur without any change
    fireEvent.blur(rawTextarea);
    expect(onUpdate).not.toHaveBeenCalled();

    // Blur after change
    fireEvent.change(rawTextarea, { target: { value: 'Changed text' } });
    fireEvent.blur(rawTextarea);

    expect(onUpdate).toHaveBeenCalledWith(
      'sticky-1',
      { body_markdown: 'Changed text' },
      '"etag-1"',
    );
  });

  it('renders hostile HTML without executing script or creating raw img tags', () => {
    const hostileSticky: StickyItem = {
      ...baseSticky,
      body_markdown: '<img src=x onerror=alert(1)>',
    };

    const { container } = render(
      <StickyCard
        sticky={hostileSticky}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onPromote={vi.fn()}
      />,
    );

    expect(container.querySelectorAll('img')).toHaveLength(0);
  });

  it('covers capabilities ADMIN and VIEW-only hiding overflow menu', () => {
    // 1. ADMIN capability allows edit and delete
    const adminSticky: StickyItem = {
      ...baseSticky,
      capabilities: ['ADMIN'],
    };
    const { unmount } = render(
      <StickyCard
        sticky={adminSticky}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onPromote={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Sticky actions' })).toBeDefined();
    unmount();

    // 2. VIEW capability hides overflow menu
    const viewSticky: StickyItem = {
      ...baseSticky,
      capabilities: ['VIEW'],
    };
    render(
      <StickyCard
        sticky={viewSticky}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onPromote={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Sticky actions' })).toBeNull();
  });

  it('falls back to default capabilities when sticky.capabilities is undefined', () => {
    // 1. readOnly = false -> defaults to EDIT, DELETE, ADMIN
    const unassignedSticky = {
      ...baseSticky,
      capabilities: undefined,
    } as unknown as StickyItem;

    const { unmount } = render(
      <StickyCard
        sticky={unassignedSticky}
        readOnly={false}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onPromote={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Sticky actions' })).toBeDefined();
    unmount();

    // 2. readOnly = true -> defaults to VIEW
    render(
      <StickyCard
        sticky={unassignedSticky}
        readOnly={true}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onPromote={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Sticky actions' })).toBeNull();
  });
});
