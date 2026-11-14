import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SelectionToIssueToolbar } from './SelectionToIssueToolbar';
import * as docsApi from './docsApi';

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
}

describe('SelectionToIssueToolbar', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.restoreAllMocks();
  });

  it('reveals floating trigger when selecting text inside .docs-prose and creates linked issue', async () => {
    const createIssueSpy = vi.spyOn(docsApi, 'createIssue').mockResolvedValue({
      id: 'issue-150',
      key: 'KAN-150',
      title: 'Enforce S256 PKCE on all OAuth2 cards',
    });
    const createLinkSpy = vi.spyOn(docsApi, 'createLink').mockResolvedValue({});

    const onAnnounce = vi.fn();

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <div>
          <div className="docs-prose">
            <p id="prose-target">Enforce S256 PKCE on all OAuth2 cards</p>
          </div>
          <SelectionToIssueToolbar
            pageId="page-auth-studio"
            projectKey="KAN"
            pageTitle="Auth Studio"
            onAnnounce={onAnnounce}
          />
        </div>
      </QueryClientProvider>,
    );

    const proseTarget = container.querySelector('#prose-target');
    if (!proseTarget) throw new Error('proseTarget missing');

    // Mock window.getSelection
    const mockRange = {
      commonAncestorContainer: proseTarget,
      getBoundingClientRect: () => ({
        top: 100,
        left: 100,
        width: 200,
        height: 20,
        bottom: 120,
        right: 300,
      }),
    };

    const mockSelection = {
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => mockRange,
      toString: () => 'Enforce S256 PKCE on all OAuth2 cards',
    };

    vi.spyOn(window, 'getSelection').mockReturnValue(mockSelection as unknown as Selection);

    // Trigger selectionchange
    fireEvent(document, new Event('selectionchange'));

    await waitFor(() => {
      expect(screen.getByTestId('create-linked-issue-floating-btn')).toBeDefined();
    });

    // Click floating action button
    fireEvent.click(screen.getByTestId('create-linked-issue-floating-btn'));

    await waitFor(() => {
      expect(screen.getByLabelText('Create linked issue')).toBeDefined();
    });

    const summaryInput: HTMLInputElement = screen.getByTestId('issue-summary-input');
    expect(summaryInput.value).toBe('Enforce S256 PKCE on all OAuth2 cards');

    const descInput: HTMLTextAreaElement = screen.getByTestId('issue-description-input');
    expect(descInput.value).toContain('> Enforce S256 PKCE on all OAuth2 cards');
    expect(descInput.value).toContain('Source: [Auth Studio](/projects/KAN/docs/page-auth-studio)');

    // Submit modal form
    fireEvent.click(screen.getByTestId('submit-issue-create-btn'));

    await waitFor(() => {
      expect(createIssueSpy).toHaveBeenCalledWith('KAN', {
        title: 'Enforce S256 PKCE on all OAuth2 cards',
        description: descInput.value,
      });
      expect(createLinkSpy).toHaveBeenCalledWith({
        source_id: 'issue-150',
        target_id: 'page-auth-studio',
        link_type: 'VERIFIED_BY_DOC',
      });
    });

    expect(screen.getByTestId('issue-created-announcement')).toBeDefined();
    expect(onAnnounce).toHaveBeenCalledWith('Created linked issue KAN-150');
  });

  it('does NOT reveal floating trigger when selection is outside .docs-prose', () => {
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <div>
          <div className="outside-container">
            <p id="outside-target">Some outside text</p>
          </div>
          <div className="docs-prose">
            <p>Prose here</p>
          </div>
          <SelectionToIssueToolbar
            pageId="page-auth-studio"
            projectKey="KAN"
            pageTitle="Auth Studio"
          />
        </div>
      </QueryClientProvider>,
    );

    const outsideTarget = container.querySelector('#outside-target');
    if (!outsideTarget) throw new Error('outsideTarget missing');
    const mockRange = {
      commonAncestorContainer: outsideTarget,
      getBoundingClientRect: () => ({ top: 50, left: 50, width: 100, height: 20 }),
    };

    const mockSelection = {
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => mockRange,
      toString: () => 'Some outside text',
    };

    vi.spyOn(window, 'getSelection').mockReturnValue(mockSelection as unknown as Selection);
    fireEvent(document, new Event('selectionchange'));

    expect(screen.queryByTestId('create-linked-issue-floating-btn')).toBeNull();
  });

  it('dismisses floating trigger or closes modal on Escape key', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <div>
          <div className="docs-prose">
            <p id="prose-target">Selectable text</p>
          </div>
          <SelectionToIssueToolbar
            pageId="page-auth-studio"
            projectKey="KAN"
            pageTitle="Auth Studio"
          />
        </div>
      </QueryClientProvider>,
    );

    const proseTarget = document.querySelector('#prose-target');
    if (!proseTarget) throw new Error('proseTarget missing');
    const mockRange = {
      commonAncestorContainer: proseTarget,
      getBoundingClientRect: () => ({ top: 100, left: 100, width: 100, height: 20 }),
    };
    const mockSelection = {
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => mockRange,
      toString: () => 'Selectable text',
    };
    vi.spyOn(window, 'getSelection').mockReturnValue(mockSelection as unknown as Selection);
    fireEvent(document, new Event('selectionchange'));

    await waitFor(() => {
      expect(screen.getByTestId('create-linked-issue-floating-btn')).toBeDefined();
    });

    // Press Escape to dismiss floating button
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('create-linked-issue-floating-btn')).toBeNull();
  });

  it('handles empty summary validation, link fallback to RELATES_TO, and modal close', async () => {
    vi.spyOn(docsApi, 'createIssue').mockResolvedValue({ id: 'iss-2', key: 'KAN-2' });
    const createLinkSpy = vi.spyOn(docsApi, 'createLink')
      .mockRejectedValueOnce(new Error('Link type not supported'))
      .mockResolvedValueOnce({});

    render(
      <QueryClientProvider client={queryClient}>
        <div>
          <div className="docs-prose">
            <p id="prose-target-2">Selectable text two</p>
          </div>
          <SelectionToIssueToolbar
            pageId="page-auth-studio"
            projectKey="KAN"
            pageTitle="Auth Studio"
          />
        </div>
      </QueryClientProvider>,
    );

    const proseTarget = document.querySelector('#prose-target-2');
    if (!proseTarget) throw new Error('proseTarget missing');
    const mockRange = {
      commonAncestorContainer: proseTarget,
      getBoundingClientRect: () => ({ top: 100, left: 100, width: 100, height: 20 }),
    };
    const mockSelection = {
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => mockRange,
      toString: () => 'Selectable text two',
    };
    vi.spyOn(window, 'getSelection').mockReturnValue(mockSelection as unknown as Selection);
    fireEvent(document, new Event('selectionchange'));

    await waitFor(() => {
      expect(screen.getByTestId('create-linked-issue-floating-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('create-linked-issue-floating-btn'));

    const summaryInput: HTMLInputElement = screen.getByTestId('issue-summary-input');
    // Test empty validation
    fireEvent.change(summaryInput, { target: { value: '   ' } });
    fireEvent.click(screen.getByTestId('submit-issue-create-btn'));

    expect(screen.getByRole('alert').textContent).toContain('Summary cannot be empty');

    // Fill valid summary
    fireEvent.change(summaryInput, { target: { value: 'Valid Summary' } });
    fireEvent.click(screen.getByTestId('submit-issue-create-btn'));

    await waitFor(() => {
      expect(createLinkSpy).toHaveBeenCalledWith({
        source_id: 'iss-2',
        target_id: 'page-auth-studio',
        link_type: 'RELATES_TO',
      });
    });

    // Close modal
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByLabelText('Create linked issue')).toBeNull();
  });
});
