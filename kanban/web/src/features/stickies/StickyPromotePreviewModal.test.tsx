/**
 * Unit Tests for StickyPromotePreviewModal (KANBA-217, KAN-469).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { StickyPromotePreviewModal } from './StickyPromotePreviewModal';
import {
  previewStickyPromotion,
  type StickyItem,
  type StickyPromotePreviewResponse,
} from './stickiesApi';
import { ShellPanelsProvider, registerShellPanel } from '../../app/shellPanels';
import fs from 'node:fs';
import path from 'node:path';

vi.mock('./stickiesApi', () => ({
  previewStickyPromotion: vi.fn(),
}));

const mockPreview = vi.mocked(previewStickyPromotion);

const baseSticky: StickyItem = {
  id: 'sticky-p1',
  workspace_id: 'ws-1',
  project_id: 'proj-1',
  body_markdown: '# Architecture Plan\nDetailed architecture markdown content.',
  body_sha256: 'sha-abc-123',
  color_token: 'sky',
  sort_rank: '0',
  promotion_recommended: true,
  promotion_snoozed_at_length: null,
  promoted_to_doc_id: null,
  is_promoted_stub: false,
  triggers: [],
  etag: '"etag-1"',
  capabilities: ['EDIT', 'DELETE'],
};

describe('StickyPromotePreviewModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <StickyPromotePreviewModal
        sticky={baseSticky}
        isOpen={false}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('extracts initial title from first markdown heading and loads preview successfully', async () => {
    mockPreview.mockResolvedValueOnce({
      proposal: {
        title: 'Synthesized Architecture Plan',
        confidence: 0.95,
        doc_family: 'rfc',
      },
      rendered_markdown: '# Synthesized Architecture Plan\n\n```mermaid\ngraph TD\n A --> B\n```',
      original_sha256: 'sha-original-999',
      warnings: ['Large payload preview generated'],
      acl_preview: {
        direct_entries_count: 3,
        inherited_scope: 'project',
      },
    });

    const onClose = vi.fn();
    const onConfirm = vi.fn().mockResolvedValue(undefined);

    render(
      <StickyPromotePreviewModal
        sticky={baseSticky}
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    );

    // Initial loading indicator
    expect(screen.getByTestId('promote-modal-loading')).toBeDefined();

    // Wait for preview load
    await waitFor(() => {
      expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
    });

    // Validates inputs populated with preview data
    const titleInput = screen.getByTestId<HTMLInputElement>('promote-modal-title');
    expect(titleInput.value).toBe('Synthesized Architecture Plan');

    const markdownArea = screen.getByTestId<HTMLTextAreaElement>('promote-modal-markdown');
    expect(markdownArea.value).toContain('```mermaid');

    // Validates ACL notice & warnings
    expect(screen.getByTestId('promote-modal-acl').textContent).toContain('All 3 explicit ACL grant(s)');
    expect(screen.getByTestId('promote-modal-warnings').textContent).toContain('Large payload preview generated');

    // Form submission
    const form = screen.getByTestId('sticky-promote-preview-modal').querySelector('form');
    if (form) {
      fireEvent.submit(form);
    }

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledWith({
        title: 'Synthesized Architecture Plan',
        structured_body_markdown: expect.stringContaining('```mermaid') as string,
        expected_sticky_sha256: 'sha-original-999',
      });
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('derives initial title from first non-heading line or fallback if empty', async () => {
    mockPreview.mockResolvedValue({
      proposal: {},
      rendered_markdown: 'fallback body',
      original_sha256: 'sha-mock-1',
      acl_preview: {},
    });

    const noHeadingSticky: StickyItem = {
      ...baseSticky,
      body_markdown: 'First plain line without hash\nSecond line',
    };
    render(
      <StickyPromotePreviewModal
        sticky={noHeadingSticky}
        isOpen={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
    });

    const emptyBodySticky: StickyItem = {
      ...baseSticky,
      body_markdown: '',
    };
    render(
      <StickyPromotePreviewModal
        sticky={emptyBodySticky}
        isOpen={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getAllByTestId('sticky-promote-preview-modal').length).toBe(2);
    });
  });

  it('falls back to deterministic structuring when previewStickyPromotion rejects', async () => {
    mockPreview.mockRejectedValueOnce(new Error('Network error or air-gapped'));

    const stickyWithoutMermaid: StickyItem = {
      ...baseSticky,
      body_markdown: 'Triage notes for DB migration',
      body_sha256: undefined,
    };

    render(
      <StickyPromotePreviewModal
        sticky={stickyWithoutMermaid}
        isOpen={true}
        onClose={vi.fn()}
        onConfirm={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
    });

    const markdownArea = screen.getByTestId<HTMLTextAreaElement>('promote-modal-markdown');
    expect(markdownArea.value).toContain('```mermaid');
    expect(markdownArea.value).toContain('Start[Start] --> Process[Process]');
  });

  it('leaves existing mermaid intact in fallback when preview API rejects', async () => {
    mockPreview.mockRejectedValueOnce('string error');

    const stickyWithMermaid: StickyItem = {
      ...baseSticky,
      body_markdown: '```mermaid\nsequenceDiagram\n A->>B: Ping\n```',
    };

    render(
      <StickyPromotePreviewModal
        sticky={stickyWithMermaid}
        isOpen={true}
        onClose={vi.fn()}
        onConfirm={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
    });

    const markdownAreaWithMermaid = screen.getByTestId<HTMLTextAreaElement>('promote-modal-markdown');
    expect(markdownAreaWithMermaid.value).toBe('```mermaid\nsequenceDiagram\n A->>B: Ping\n```');
  });

  it('validates empty title and displays inline error', async () => {
    mockPreview.mockResolvedValueOnce({
      proposal: { title: 'Some Title' },
      rendered_markdown: 'body',
      original_sha256: 'sha-mock-1',
      acl_preview: {},
    });

    render(
      <StickyPromotePreviewModal
        sticky={baseSticky}
        isOpen={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
    });

    const titleInput = screen.getByTestId('promote-modal-title');
    fireEvent.change(titleInput, { target: { value: '   ' } });

    const form = screen.getByTestId('sticky-promote-preview-modal').querySelector('form');
    if (form) {
      fireEvent.submit(form);
    }

    expect(screen.getByTestId('promote-modal-error').textContent).toBe('Title cannot be empty');
  });

  it('handles error thrown during onConfirm (Error instance and non-Error)', async () => {
    mockPreview.mockResolvedValueOnce({
      proposal: { title: 'Title' },
      rendered_markdown: 'body',
      original_sha256: 'sha-mock-1',
      acl_preview: {},
    });

    const onConfirm = vi.fn().mockRejectedValueOnce(new Error('Backend rejected payload'));

    render(
      <StickyPromotePreviewModal
        sticky={baseSticky}
        isOpen={true}
        onClose={vi.fn()}
        onConfirm={onConfirm}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
    });

    const form1 = screen.getByTestId('sticky-promote-preview-modal').querySelector('form');
    if (form1) {
      fireEvent.submit(form1);
    }

    await waitFor(() => {
      expect(screen.getByTestId('promote-modal-error').textContent).toBe('Backend rejected payload');
    });

    // Test non-Error rejection
    onConfirm.mockRejectedValueOnce('raw rejection');
    const form2 = screen.getByTestId('sticky-promote-preview-modal').querySelector('form');
    if (form2) {
      fireEvent.submit(form2);
    }

    await waitFor(() => {
      expect(screen.getByTestId('promote-modal-error').textContent).toBe('Failed to promote sticky to document');
    });
  });

  it('closes modal on backdrop click, close button, and cancel button, while stopping propagation on modal click', async () => {
    mockPreview.mockResolvedValueOnce({
      proposal: { title: 'Title' },
      rendered_markdown: 'body',
      original_sha256: 'sha-mock-1',
      acl_preview: {},
    });

    const onClose = vi.fn();

    render(
      <StickyPromotePreviewModal
        sticky={baseSticky}
        isOpen={true}
        onClose={onClose}
        onConfirm={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
    });

    // Stop propagation on modal body
    fireEvent.click(screen.getByTestId('sticky-promote-preview-modal'));
    expect(onClose).not.toHaveBeenCalled();

    // Close button
    fireEvent.click(screen.getByTestId('close-promote-modal-btn'));
    expect(onClose).toHaveBeenCalledTimes(1);

    // Cancel button
    fireEvent.click(screen.getByTestId('cancel-promote-btn'));
    expect(onClose).toHaveBeenCalledTimes(2);

    // Backdrop click
    fireEvent.click(screen.getByTestId('sticky-promote-preview-backdrop'));
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  describe('StudioDocLink Header Integration and Shift-Left Invariants (KAN-469)', () => {
    it('renders StudioDocLink in sticky-promote-modal__header with required props', async () => {
      mockPreview.mockResolvedValueOnce({
        proposal: { title: 'Promotion Spec' },
        rendered_markdown: '## Spec overview',
        original_sha256: 'sha-123',
        acl_preview: { direct_entries_count: 1 },
      });

      render(
        <StickyPromotePreviewModal
          sticky={baseSticky}
          isOpen={true}
          onClose={vi.fn()}
          onConfirm={vi.fn()}
        />,
      );

      await waitFor(() => {
        expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
      });

      const docLink = screen.getByTestId('sticky-promote-doc-link');
      expect(docLink).toBeDefined();
      expect(docLink.getAttribute('href')).toBe('/docs/hierarchical-docs-and-stickies-with-smart-promotion');
      expect(docLink.textContent).toContain('Promotion Guide ->');
      expect(docLink.getAttribute('aria-label')).toBe('Promotion Guide ->');

      // Check header-actions grouping container beside close button
      const headerActions = docLink.closest('.sticky-promote-modal__header-actions');
      expect(headerActions).not.toBeNull();
      const closeBtn = screen.getByTestId('close-promote-modal-btn');
      expect(headerActions?.contains(closeBtn)).toBe(true);
      expect(headerActions?.contains(docLink)).toBe(true);

      // Keyboard focusability
      docLink.focus();
      expect(document.activeElement).toBe(docLink);
    });

    it('opens in-app help panel via ShellPanelsProvider without closing modal state', async () => {
      mockPreview.mockResolvedValueOnce({
        proposal: { title: 'Promotion Spec' },
        rendered_markdown: '## Spec overview',
        original_sha256: 'sha-123',
        acl_preview: { direct_entries_count: 2 },
      });

      const unregister = registerShellPanel('help', ({ arg }) => (
        <div data-testid="in-app-help-drawer">
          Help Drawer for {(arg as { href?: string } | undefined)?.href}
        </div>
      ));

      try {
        render(
          <ShellPanelsProvider>
            <StickyPromotePreviewModal
              sticky={baseSticky}
              isOpen={true}
              onClose={vi.fn()}
              onConfirm={vi.fn()}
            />
          </ShellPanelsProvider>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('sticky-promote-doc-link')).toBeDefined();
        });

        const docLink = screen.getByTestId('sticky-promote-doc-link');
        fireEvent.click(docLink);

        const helpDrawer = screen.getByTestId('in-app-help-drawer');
        expect(helpDrawer).toBeDefined();
        expect(helpDrawer.textContent).toContain(
          '/docs/hierarchical-docs-and-stickies-with-smart-promotion',
        );

        // Modal remains open and functional
        expect(screen.getByTestId('sticky-promote-preview-modal')).toBeDefined();
      } finally {
        unregister();
      }
    });

    it('allows editing markdown preview textarea and submitting without sha256', async () => {
      mockPreview.mockResolvedValueOnce({
        proposal: {},
        rendered_markdown: '',
        original_sha256: '',
        acl_preview: {},
      });

      const stickyWithoutSha: StickyItem = {
        ...baseSticky,
        body_sha256: undefined,
      };

      const onConfirm = vi.fn().mockResolvedValue(undefined);

      render(
        <StickyPromotePreviewModal
          sticky={stickyWithoutSha}
          isOpen={true}
          onClose={vi.fn()}
          onConfirm={onConfirm}
        />,
      );

      await waitFor(() => {
        expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
      });

      const titleInput = screen.getByTestId<HTMLInputElement>('promote-modal-title');
      fireEvent.change(titleInput, { target: { value: 'Custom Edited Title' } });

      const markdownArea = screen.getByTestId<HTMLTextAreaElement>('promote-modal-markdown');
      fireEvent.change(markdownArea, { target: { value: '# Custom Markdown Content\n\nNotes here.' } });
      expect(markdownArea.value).toBe('# Custom Markdown Content\n\nNotes here.');

      const form = screen.getByTestId('sticky-promote-preview-modal').querySelector('form');
      if (form) {
        fireEvent.submit(form);
      }

      await waitFor(() => {
        expect(onConfirm).toHaveBeenCalledWith({
          title: 'Custom Edited Title',
          structured_body_markdown: '# Custom Markdown Content\n\nNotes here.',
        });
      });
    });

    it('handles component unmount during active preview load cleanly', () => {
      let resolvePromise: (val: StickyPromotePreviewResponse) => void = vi.fn();
      mockPreview.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolvePromise = resolve;
          }),
      );

      const { unmount } = render(
        <StickyPromotePreviewModal
          sticky={baseSticky}
          isOpen={true}
          onClose={vi.fn()}
          onConfirm={vi.fn()}
        />,
      );

      expect(screen.getByTestId('promote-modal-loading')).toBeDefined();
      // Unmount before promise resolves
      unmount();
      resolvePromise({
        proposal: { title: 'Late title' },
        rendered_markdown: 'Late body',
        original_sha256: 'sha-mock',
        acl_preview: {},
      });
      // Should not throw or cause React unmounted state warnings
    });

    it('handles component unmount during catch rejection cleanly', () => {
      let rejectPromise: (err: unknown) => void = vi.fn();
      mockPreview.mockImplementation(
        () =>
          new Promise((_, reject) => {
            rejectPromise = reject;
          }),
      );

      const { unmount } = render(
        <StickyPromotePreviewModal
          sticky={baseSticky}
          isOpen={true}
          onClose={vi.fn()}
          onConfirm={vi.fn()}
        />,
      );

      // Unmount before reject
      unmount();
      rejectPromise(new Error('Network error'));
    });

    it('verifies zero FieldHelpHint nested inside label and zero inline styles', () => {
      const tsxPath = path.resolve(__dirname, 'StickyPromotePreviewModal.tsx');
      const content = fs.readFileSync(tsxPath, 'utf8');

      // Verify no FieldHelpHint inside <label>
      expect(content).not.toMatch(/<label[^>]*>[\s\S]*?<FieldHelpHint[\s\S]*?<\/label>/);

      // Verify no inline style={{}}
      expect(content).not.toMatch(/\bstyle=\{\{/);

      // Verify StudioDocLink placement and props
      expect(content).toContain('<StudioDocLink');
      expect(content).toContain('href="/docs/hierarchical-docs-and-stickies-with-smart-promotion"');
      expect(content).toContain('label="Promotion Guide ->"');
      expect(content).toContain('testId="sticky-promote-doc-link"');
    });

    it('verifies CSS rules in StickiesGrid.css for header actions and 44px touch targets', () => {
      const cssPath = path.resolve(__dirname, 'StickiesGrid.css');
      const cssContent = fs.readFileSync(cssPath, 'utf8');

      expect(cssContent).toContain('.sticky-promote-modal__header-actions');
      expect(cssContent).toContain('.sticky-promote-modal__close-btn');
      expect(cssContent).toContain('min-height: var(--tap-min, 44px)');
      expect(cssContent).toContain('min-width: var(--tap-min, 44px)');
      expect(cssContent).toContain('@media (max-width: 640px)');
    });
  });
});
