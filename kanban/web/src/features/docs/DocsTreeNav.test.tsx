import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DocsTreeNav, getSubtreeDepth, getDescendantIds } from './DocsTreeNav';
import * as docsApi from './docsApi';

const mockTreeData: docsApi.PageTreeNode[] = [
  {
    id: 'page-arch',
    title: 'Architecture',
    slug: 'architecture',
    sort_rank: '0|hzzzzz:',
    restricted: false,
    children: [
      {
        id: 'page-auth',
        title: 'Auth Studio',
        slug: 'auth-studio',
        sort_rank: '0|hzzzzz:1',
        restricted: false,
        children: [
          {
            id: 'page-pkce',
            title: 'PKCE Flow',
            slug: 'pkce-flow',
            sort_rank: '0|hzzzzz:1:1',
            restricted: false,
            children: [],
          },
        ],
      },
    ],
  },
  {
    id: 'page-restricted',
    restricted: true,
    label: '🔒 Restricted Page',
    children: [],
  },
  {
    id: 'page-d1',
    title: 'D1',
    restricted: false,
    children: [
      {
        id: 'page-d2',
        title: 'D2',
        restricted: false,
        children: [
          {
            id: 'page-d3',
            title: 'D3',
            restricted: false,
            children: [
              {
                id: 'page-d4',
                title: 'D4',
                restricted: false,
                children: [
                  {
                    id: 'page-d5',
                    title: 'D5',
                    restricted: false,
                    children: [
                      {
                        id: 'page-d6',
                        title: 'D6',
                        restricted: false,
                        children: [
                          {
                            id: 'page-d7',
                            title: 'D7',
                            restricted: false,
                            children: [
                              {
                                id: 'page-d8',
                                title: 'D8',
                                restricted: false,
                                children: [
                                  {
                                    id: 'page-d9',
                                    title: 'D9',
                                    restricted: false,
                                    children: [
                                      {
                                        id: 'page-d10',
                                        title: 'D10',
                                        restricted: false,
                                        children: [],
                                      },
                                    ],
                                  },
                                ],
                              },
                            ],
                          },
                        ],
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
];

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

describe('DocsTreeNav', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.restoreAllMocks();
    vi.spyOn(docsApi, 'fetchDocsTree').mockResolvedValue(mockTreeData);
  });

  it('renders tree structure and expands nodes to activePageId', async () => {
    const onSelectPage = vi.fn();
    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav
          projectKey="KAN"
          activePageId="page-pkce"
          onSelectPage={onSelectPage}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('Architecture')).toBeDefined();
    });

    // Should have expanded down to PKCE Flow
    await waitFor(() => {
      expect(screen.getByText('Auth Studio')).toBeDefined();
      expect(screen.getByText('PKCE Flow')).toBeDefined();
    });
  });

  it('supports WAI-ARIA keyboard tree navigation', async () => {
    const onSelectPage = vi.fn();
    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav
          projectKey="KAN"
          activePageId="page-arch"
          onSelectPage={onSelectPage}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('Architecture')).toBeDefined();
    });

    const archItem = screen.getByTestId('treeitem-architecture');

    // ArrowRight to expand
    fireEvent.keyDown(archItem, { key: 'ArrowRight' });
    expect(screen.getByText('Auth Studio')).toBeDefined();

    // ArrowDown moves focus
    fireEvent.keyDown(archItem, { key: 'ArrowDown' });
    const authItem = screen.getByTestId('treeitem-auth-studio');

    // Enter selects page
    fireEvent.keyDown(authItem, { key: 'Enter' });
    expect(onSelectPage).toHaveBeenCalledWith('page-auth');

    // ArrowLeft collapses or moves up
    fireEvent.keyDown(authItem, { key: 'ArrowLeft' });

    // ArrowRight on already expanded archItem
    fireEvent.keyDown(archItem, { key: 'ArrowRight' });
    // ArrowLeft on archItem collapses it
    fireEvent.keyDown(archItem, { key: 'ArrowLeft' });
    // ArrowUp on archItem
    fireEvent.keyDown(archItem, { key: 'ArrowUp' });
  });

  it('enforces max_depth <= 10 by disabling + Sub-page button at depth 10', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav
          projectKey="KAN"
          activePageId="page-d10"
          onSelectPage={vi.fn()}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('D10')).toBeDefined();
    });

    const d10SubpageBtn = screen.getByTestId<HTMLButtonElement>('add-subpage-page-d10');
    expect(d10SubpageBtn.disabled).toBe(true);
    expect(d10SubpageBtn.getAttribute('aria-disabled')).toBe('true');
    expect(d10SubpageBtn.title).toBe('Maximum nesting depth of 10 pages reached');
  });

  it('handles page creation validation and submission', async () => {
    const createSpy = vi.spyOn(docsApi, 'createPage').mockResolvedValue({
      id: 'page-new',
      title: 'New Page',
      canonical_key: 'docs/new-page',
      doc_id: 'doc-1',
      parent_page_id: null,
      workspace_id: 'ws-1',
      body_markdown: '',
      body_sha256: 'hash',
      hierarchy_path: 'docs.new_page',
      version_seq: 1,
      sort_rank: '0|i00000:',
      breadcrumbs: [],
      outline: [],
      access_manifest: {},
      capabilities: ['VIEW'],
    });

    const onSelectPage = vi.fn();
    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav
          projectKey="KAN"
          onSelectPage={onSelectPage}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('create-root-doc-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('create-root-doc-btn'));
    expect(screen.getByLabelText('Create page')).toBeDefined();

    const titleInput = screen.getByTestId('new-page-title-input');
    const submitBtn = screen.getByTestId('submit-create-page-btn');

    // Check placeholder prompt
    expect(titleInput.getAttribute('placeholder')).toBe('What do you want to call this doc?');

    // Empty validation
    fireEvent.change(titleInput, { target: { value: '   ' } });
    fireEvent.click(submitBtn);
    expect(screen.getByRole('alert').textContent).toContain('Title cannot be empty');

    // Valid submission
    fireEvent.change(titleInput, { target: { value: 'My Root Doc' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith('KAN', {
        title: 'My Root Doc',
        body_markdown: docsApi.DEFAULT_DOC_MARKDOWN_TEMPLATE,
        parent_page_id: null,
      });
      expect(onSelectPage).toHaveBeenCalledWith('page-new');
    });
  });

  it('handles move dialog with cycle prevention and depth guard', async () => {
    const dummyPage: docsApi.PageResponse = {
      id: 'page-arch',
      canonical_key: 'docs/arch',
      doc_id: 'doc-1',
      parent_page_id: null,
      workspace_id: 'ws-1',
      title: 'Arch',
      body_markdown: '',
      body_sha256: 'hash',
      hierarchy_path: 'docs.arch',
      version_seq: 1,
      sort_rank: '0|hzzzzz:',
      breadcrumbs: [],
      outline: [],
      access_manifest: {},
      capabilities: ['VIEW'],
    };
    const moveSpy = vi.spyOn(docsApi, 'movePage').mockResolvedValue(dummyPage);

    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav
          projectKey="KAN"
          activePageId="page-arch"
          onSelectPage={vi.fn()}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('move-page-architecture')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('move-page-architecture'));
    expect(screen.getByLabelText('Move page')).toBeDefined();

    const moveSelect = screen.getByTestId<HTMLSelectElement>('move-target-select');
    // Architecture has Auth Studio and PKCE Flow as descendants - they must not be options!
    const optionValues = Array.from(moveSelect.options).map((o) => o.value);
    expect(optionValues).not.toContain('page-arch');
    expect(optionValues).not.toContain('page-auth');
    expect(optionValues).not.toContain('page-pkce');

    fireEvent.click(screen.getByTestId('submit-move-page-btn'));
    await waitFor(() => {
      expect(moveSpy).toHaveBeenCalledWith('page-arch', {
        parent_page_id: null,
      });
    });
  });

  it('renders restricted nodes with lock icon and masked title', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav
          projectKey="KAN"
          onSelectPage={vi.fn()}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('🔒 Restricted Page')).toBeDefined();
    });
  });

  it('calculates subtree depth and descendant IDs correctly', () => {
    const archNode = mockTreeData[0];
    if (!archNode) {
      throw new Error('archNode not found');
    }
    expect(getSubtreeDepth(archNode)).toBe(3);
    const descendants = getDescendantIds(archNode);
    expect(descendants.has('page-auth')).toBe(true);
    expect(descendants.has('page-pkce')).toBe(true);
    expect(descendants.has('page-d1')).toBe(false);
  });

  it('cancels create and move modals when clicking Cancel', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav projectKey="KAN" onSelectPage={vi.fn()} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('create-root-doc-btn')).toBeDefined();
    });

    // Open create modal and cancel
    fireEvent.click(screen.getByTestId('create-root-doc-btn'));
    expect(screen.getByLabelText('Create page')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByLabelText('Create page')).toBeNull();

    // Open move modal and cancel
    fireEvent.click(screen.getByTestId('move-page-architecture'));
    expect(screen.getByLabelText('Move page')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByLabelText('Move page')).toBeNull();
  });

  it('displays mutation error messages when create or move fails', async () => {
    vi.spyOn(docsApi, 'createPage').mockRejectedValue(new Error('Backend depth error'));
    vi.spyOn(docsApi, 'movePage').mockRejectedValue(new Error('Backend cycle error'));

    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav projectKey="KAN" onSelectPage={vi.fn()} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('create-root-doc-btn')).toBeDefined();
    });

    // Create error
    fireEvent.click(screen.getByTestId('create-root-doc-btn'));
    const input = screen.getByTestId('new-page-title-input');
    fireEvent.change(input, { target: { value: 'Title' } });
    fireEvent.click(screen.getByTestId('submit-create-page-btn'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Backend depth error');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    // Move error
    fireEvent.click(screen.getByTestId('move-page-architecture'));
    fireEvent.click(screen.getByTestId('submit-move-page-btn'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Backend cycle error');
    });
  });
});
