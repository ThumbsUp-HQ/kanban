import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import * as docsApi from './docsApi';

vi.mock('./DocsTreeNav', () => ({
  DocsTreeNav: ({ onAnnounce }: { onAnnounce?: (msg: string) => void }) => (
    <div data-testid="mock-tree-nav">
      <button
        data-testid="mock-announce-btn"
        onClick={() => onAnnounce?.('Test announcement from tree')}
      />
    </div>
  ),
}));

vi.mock('./PageEditorPane', () => ({
  PageEditorPane: () => <div data-testid="mock-page-editor" />,
}));

vi.mock('./OutlineAndVersionsRail', () => ({
  OutlineAndVersionsRail: () => <div data-testid="mock-rail" />,
}));

vi.mock('./SelectionToIssueToolbar', () => ({
  SelectionToIssueToolbar: () => <div data-testid="mock-toolbar" />,
}));

import { DocsWorkspaceView } from './DocsWorkspaceView';

describe('DocsWorkspaceViewIsolated', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
      },
    });
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('executes own tree and page queryFn and handles announcement timeout', async () => {
    const fetchTreeSpy = vi.spyOn(docsApi, 'fetchDocsTree').mockResolvedValue([
      {
        id: 'page-iso-1',
        title: 'Isolated Page',
        slug: 'iso-1',
        restricted: false,
        children: [],
      },
    ]);

    const fetchPageSpy = vi.spyOn(docsApi, 'fetchPage').mockResolvedValue({
      id: 'page-iso-1',
      canonical_key: 'docs/iso-1',
      doc_id: 'doc-1',
      parent_page_id: null,
      workspace_id: 'ws-1',
      title: 'Isolated Page',
      body_markdown: '# Content',
      body_sha256: 'hash',
      hierarchy_path: 'docs.iso_1',
      version_seq: 1,
      sort_rank: '0|hzzzzz:',
      breadcrumbs: [],
      outline: [],
      access_manifest: {},
      capabilities: ['VIEW'],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/docs/page-iso-1']}>
          <Routes>
            <Route path="/projects/:projectKey/docs/:pageId" element={<DocsWorkspaceView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Verify query functions are called
    await waitFor(() => {
      expect(fetchTreeSpy).toHaveBeenCalledWith('KAN');
    });

    await waitFor(() => {
      expect(fetchPageSpy).toHaveBeenCalledWith('page-iso-1');
    });

    // Test announcement
    expect(screen.getByTestId('mock-announce-btn')).toBeDefined();
    fireEvent.click(screen.getByTestId('mock-announce-btn'));
    await new Promise((r) => setTimeout(r, 4100));
  });
});
