import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { DocsWorkspaceView } from './DocsWorkspaceView';
import * as docsApi from './docsApi';

const mockTreeData: docsApi.PageTreeNode[] = [
  {
    id: 'page-auth-studio',
    title: 'Auth Studio',
    slug: 'auth-studio',
    restricted: false,
    children: [],
  },
];

const mockPageData: docsApi.PageResponse = {
  id: 'page-auth-studio',
  canonical_key: 'docs/auth-studio',
  doc_id: 'doc-1',
  parent_page_id: null,
  workspace_id: 'ws-1',
  title: 'Auth Studio',
  body_markdown: '# Overview\n\nDoc content.',
  body_sha256: 'hash',
  hierarchy_path: 'docs.auth_studio',
  version_seq: 1,
  sort_rank: '0|hzzzzz:',
  breadcrumbs: [],
  outline: [],
  access_manifest: {},
  capabilities: ['VIEW'],
};

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

describe('DocsWorkspaceView', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.restoreAllMocks();
    vi.spyOn(docsApi, 'fetchDocsTree').mockResolvedValue(mockTreeData);
    vi.spyOn(docsApi, 'fetchPage').mockResolvedValue(mockPageData);
    vi.spyOn(docsApi, 'fetchPageVersions').mockResolvedValue([]);
  });

  it('renders 3-pane shell and loads page editor for active page', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/docs/page-auth-studio']}>
          <Routes>
            <Route path="/projects/:projectKey/docs/:pageId" element={<DocsWorkspaceView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('docs-workspace-view')).toBeDefined();
    });

    expect(screen.getByTestId('docs-tree-wrapper')).toBeDefined();
    expect(screen.getByTestId('page-title-input')).toBeDefined();
    expect(screen.getByTestId('docs-rail-wrapper')).toBeDefined();
  });

  it('toggles mobile sheets and closes via backdrop', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/docs/page-auth-studio']}>
          <Routes>
            <Route path="/projects/:projectKey/docs/:pageId" element={<DocsWorkspaceView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('toggle-tree-sheet-btn')).toBeDefined();
    });

    // Toggle tree sheet
    fireEvent.click(screen.getByTestId('toggle-tree-sheet-btn'));
    expect(screen.getByTestId('docs-sheet-backdrop')).toBeDefined();

    // Toggle rail sheet
    fireEvent.click(screen.getByTestId('toggle-rail-sheet-btn'));
    expect(screen.getByTestId('docs-sheet-backdrop')).toBeDefined();

    // Backdrop click dismisses sheets
    fireEvent.click(screen.getByTestId('docs-sheet-backdrop'));
    expect(screen.queryByTestId('docs-sheet-backdrop')).toBeNull();
  });

  it('renders empty state when no pages are available in tree', async () => {
    vi.spyOn(docsApi, 'fetchDocsTree').mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/docs']}>
          <Routes>
            <Route path="/projects/:projectKey/docs" element={<DocsWorkspaceView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('docs-empty-state')).toBeDefined();
    });
  });

  it('selects page from tree nav and updates active view', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/docs/page-auth-studio']}>
          <Routes>
            <Route path="/projects/:projectKey/docs/:pageId" element={<DocsWorkspaceView />} />
            <Route path="/projects/:projectKey/docs" element={<DocsWorkspaceView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('treeitem-auth-studio')).toBeDefined();
    });

    // Toggle tree and rail sheets
    const toggleTreeBtn = screen.getByTestId('toggle-tree-sheet-btn');
    fireEvent.click(toggleTreeBtn);
    expect(screen.getByTestId('docs-sheet-backdrop')).toBeDefined();

    // Click tree item to select
    const treeItem = screen.getByTestId('treeitem-auth-studio');
    fireEvent.click(treeItem);
    expect(screen.queryByTestId('docs-sheet-backdrop')).toBeNull();
  });
});
