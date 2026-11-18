/**
 * Unit Tests for PromotedStickyStub (KB-P3-51, S8.2).
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PromotedStickyStub } from './PromotedStickyStub';
import type { StickyItem } from './stickiesApi';

const promotedSticky: StickyItem = {
  id: 'sticky-10',
  workspace_id: 'ws-1',
  project_id: 'proj-1',
  body_markdown: '# Architecture Plan\n## Core Security\nHardened mutual TLS configuration.',
  color_token: 'slate',
  sort_rank: '1',
  promotion_recommended: false,
  promotion_snoozed_at_length: null,
  promoted_to_doc_id: 'doc-page-123',
  is_promoted_stub: true,
  promoted_to_doc: {
    id: 'doc-page-123',
    canonical_key: 'DOC-10',
    title: 'Architecture Plan Spec',
    restricted: false,
  },
  triggers: [],
  capabilities: ['EDIT', 'DELETE'],
};

describe('PromotedStickyStub', () => {
  it('renders promoted badge, title, stripped preview, and open link', () => {
    const onUnarchive = vi.fn();

    render(
      <PromotedStickyStub
        sticky={promotedSticky}
        projectKey="KAN"
        onUnarchiveCopy={onUnarchive}
      />,
    );

    expect(screen.getByText('Promoted to Doc')).toBeDefined();
    expect(screen.getByText('Architecture Plan Spec')).toBeDefined();
    expect(screen.getByText(/Hardened mutual TLS configuration/)).toBeDefined();

    const openLink = screen.getByRole('link', { name: /Open Doc/i });
    expect(openLink.getAttribute('href')).toBe('/projects/KAN/docs/doc-page-123');

    const unarchiveBtn = screen.getByRole('button', { name: /Unarchive editable sticky copy/i });
    fireEvent.click(unarchiveBtn);
    expect(onUnarchive).toHaveBeenCalledTimes(1);
  });

  it('renders fallback title and link when projectKey or title are missing', () => {
    const minimalSticky: StickyItem = {
      ...promotedSticky,
      body_markdown: '',
      promoted_to_doc: { id: 'doc-fallback-id' },
      promoted_to_doc_id: null,
    };

    render(
      <PromotedStickyStub
        sticky={minimalSticky}
        onUnarchiveCopy={vi.fn()}
      />,
    );

    expect(screen.getByText('Promoted Specification')).toBeDefined();
    const openLink = screen.getByRole('link', { name: /Open Doc/i });
    expect(openLink.getAttribute('href')).toBe('/docs/doc-fallback-id');
  });

  it('handles sticky with null promoted_to_doc and null promoted_to_doc_id', () => {
    const emptySticky: StickyItem = {
      ...promotedSticky,
      body_markdown: '',
      promoted_to_doc: undefined,
      promoted_to_doc_id: null,
    };

    render(
      <PromotedStickyStub
        sticky={emptySticky}
        onUnarchiveCopy={vi.fn()}
      />,
    );

    const openLink = screen.getByRole('link', { name: /Open Doc/i });
    expect(openLink.getAttribute('href')).toBe('/docs/');
  });

  it('disables unarchive button when isUnarchiving is true', () => {
    render(
      <PromotedStickyStub
        sticky={promotedSticky}
        isUnarchiving={true}
        onUnarchiveCopy={vi.fn()}
      />,
    );

    const btn = screen.getByRole('button', { name: /Unarchive editable sticky copy/i });
    expect(btn.textContent).toBe('Copying...');
    expect(btn.hasAttribute('disabled')).toBe(true);
  });

  it('handles access inspector click with custom callback or custom event', () => {
    const onAccess = vi.fn();
    const { unmount } = render(
      <PromotedStickyStub
        sticky={promotedSticky}
        onUnarchiveCopy={vi.fn()}
        onOpenAccessInspector={onAccess}
      />,
    );

    const accessBtn = screen.getByRole('button', { name: 'Inspect effective access' });
    fireEvent.click(accessBtn);
    expect(onAccess).toHaveBeenCalledTimes(1);
    unmount();

    // Event listener fallback
    const eventHandler = vi.fn();
    window.addEventListener('kb:open-access-inspector', eventHandler);

    render(
      <PromotedStickyStub
        sticky={promotedSticky}
        onUnarchiveCopy={vi.fn()}
      />,
    );

    const accessBtn2 = screen.getByRole('button', { name: 'Inspect effective access' });
    fireEvent.click(accessBtn2);
    expect(eventHandler).toHaveBeenCalled();

    window.removeEventListener('kb:open-access-inspector', eventHandler);
  });
});
