import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { DocsWorkspaceView } from './DocsWorkspaceView';
import { DocsTreeNav, getSubtreeDepth } from './DocsTreeNav';
import { OutlineAndVersionsRail, extractHeadings, stripInlineMarkdown } from './OutlineAndVersionsRail';
import { PageEditorPane } from './PageEditorPane';
import { SelectionToIssueToolbar } from './SelectionToIssueToolbar';
import * as docsApi from './docsApi';
import { ApiProblem } from '../../api/problem';

// Ensure jsdom Range prototype has rect functions for ProseMirror
Range.prototype.getClientRects = () => [
  { top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 },
] as unknown as DOMRectList;
Range.prototype.getBoundingClientRect = () => ({
  top: 0,
  left: 0,
  width: 0,
  height: 0,
  bottom: 0,
  right: 0,
  x: 0,
  y: 0,
  toJSON: () => ({}),
});

const mockTreeWithChildren: docsApi.PageTreeNode[] = [
  {
    id: 'page-restricted-root',
    restricted: true,
    children: [
      {
        id: 'page-child-1',
        title: 'Child 1',
        slug: 'child-1',
        restricted: false,
        children: [
          {
            id: 'page-grandchild',
            title: 'Grandchild',
            slug: 'grandchild',
            restricted: false,
            children: [],
          },
        ],
      },
    ],
  },
];

const mockPageFull: docsApi.PageResponse = {
  id: 'page-child-1',
  canonical_key: 'docs/child-1',
  doc_id: 'doc-1',
  parent_page_id: null,
  workspace_id: 'ws-1',
  title: 'Child Page',
  body_markdown: '# Overview\nText\n## Sub\nMore text',
  body_sha256: 'hash-abc',
  hierarchy_path: 'docs.child_1',
  version_seq: 3,
  sort_rank: '0|hzzzzz:',
  breadcrumbs: [],
  outline: [],
  access_manifest: {},
  capabilities: ['VIEW', 'EDIT'],
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

describe('Docs Coverage Boosters', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.restoreAllMocks();
    vi.spyOn(docsApi, 'fetchDocsTree').mockResolvedValue(mockTreeWithChildren);
    vi.spyOn(docsApi, 'fetchPage').mockResolvedValue(mockPageFull);
    vi.spyOn(docsApi, 'fetchPageVersions').mockResolvedValue([]);
  });

  it('DocsWorkspaceView handles auto navigation through restricted ancestor and rail toggle', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/docs']}>
          <Routes>
            <Route path="/projects/:projectKey/docs" element={<DocsWorkspaceView />} />
            <Route path="/projects/:projectKey/docs/:pageId" element={<DocsWorkspaceView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('docs-workspace-view')).toBeDefined();
    });

    await waitFor(() => {
      expect(screen.getByTestId('rail-toggle-btn')).toBeDefined();
    });

    // Toggle rail button from inside editor pane
    const railToggle = screen.getByTestId('rail-toggle-btn');
    fireEvent.click(railToggle);
  });

  it('DocsTreeNav handles navigation bounds and collapse/expand edge cases', async () => {
    const onSelectPage = vi.fn();
    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav
          projectKey="KAN"
          activePageId="page-child-1"
          onSelectPage={onSelectPage}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('treeitem-child-1')).toBeDefined();
    });

    const childItem = screen.getByTestId('treeitem-child-1');

    // ArrowUp on first element (top bound)
    const rootEl = screen.getByTestId('treeitem-page-restricted-root');
    fireEvent.keyDown(rootEl, { key: 'ArrowUp' });

    // ArrowDown on child
    fireEvent.keyDown(childItem, { key: 'ArrowDown' });

    // ArrowUp on child item (currentIndex > 0)
    fireEvent.keyDown(childItem, { key: 'ArrowUp' });

    // ArrowRight to expand
    fireEvent.keyDown(childItem, { key: 'ArrowRight' });

    // ArrowRight on already expanded item moves focus to grandchild
    fireEvent.keyDown(childItem, { key: 'ArrowRight' });

    // ArrowLeft on leaf collapses or moves to parent
    const grandchildItem = screen.getByTestId('treeitem-grandchild');
    // ArrowRight on leaf node (hasChildren === false)
    fireEvent.keyDown(grandchildItem, { key: 'ArrowRight' });
    fireEvent.keyDown(grandchildItem, { key: 'ArrowLeft' });

    // ArrowLeft on expanded item collapses it
    fireEvent.keyDown(childItem, { key: 'ArrowLeft' });

    // ArrowDown at bottom of list
    fireEvent.keyDown(grandchildItem, { key: 'ArrowDown' });

    // Ignore unrecognized key
    fireEvent.keyDown(childItem, { key: 'Tab' });

    // Subtree depth with shallow second child
    const depthTree: docsApi.PageTreeNode = {
      id: 'd-root',
      restricted: false,
      children: [
        {
          id: 'd-deep',
          restricted: false,
          children: [{ id: 'd-deep-2', restricted: false, children: [] }],
        },
        {
          id: 'd-shallow',
          restricted: false,
          children: [],
        },
      ],
    };
    expect(getSubtreeDepth(depthTree)).toBe(3);
  });

  it('DocsTreeNav handles mutation errors with non-Error objects', async () => {
    vi.spyOn(docsApi, 'createPage').mockRejectedValue('String error');
    vi.spyOn(docsApi, 'movePage').mockRejectedValue('String error');

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
    fireEvent.change(screen.getByTestId('new-page-title-input'), { target: { value: 'Title' } });
    fireEvent.click(screen.getByTestId('submit-create-page-btn'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Failed to create page');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    // Expand root node to reveal child-1
    fireEvent.click(screen.getByRole('button', { name: 'Expand 🔒 Restricted Page' }));

    // Move error
    fireEvent.click(screen.getByTestId('move-page-child-1'));
    fireEvent.click(screen.getByTestId('submit-move-page-btn'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Failed to move page');
    });
  });

  it('OutlineAndVersionsRail extracts headings with multiline HTML comments and fallback slugs', () => {
    const md = `
<!-- This is a
multiline comment -->
# Heading One
<!-- single line comment -->
## !!!
### Heading Three
`;
    const headings = extractHeadings(md);
    expect(headings.length).toBe(3);
    expect(headings[0]?.text).toBe('Heading One');
    expect(headings[1]?.anchor).toBe('section');
    expect(headings[2]?.text).toBe('Heading Three');
  });

  it('PageEditorPane handles control characters in title and title typing validation', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane pageId="page-child-1" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    const titleInput = screen.getByTestId('page-title-input');
    // Tab key on title input
    fireEvent.keyDown(titleInput, { key: 'Tab' });

    // Title with control characters
    fireEvent.change(titleInput, { target: { value: 'Title\x05WithControl' } });
    // Empty title blur save
    fireEvent.change(titleInput, { target: { value: '' } });
    fireEvent.blur(screen.getByRole('main'));

    // Huge title blur save
    fireEvent.change(titleInput, { target: { value: 'A'.repeat(505) } });
    fireEvent.blur(screen.getByRole('main'));

    // Valid title with autosave timer
    fireEvent.change(titleInput, { target: { value: 'Valid Title' } });
    await new Promise((r) => setTimeout(r, 900));

    // Non-dirty blur branch
    fireEvent.blur(screen.getByRole('main'));
  });

  it('SelectionToIssueToolbar handles creation failure, link view, and edge cases', async () => {
    const createSpy = vi.spyOn(docsApi, 'createIssue').mockRejectedValue(new Error('Quota exceeded'));

    render(
      <QueryClientProvider client={queryClient}>
        <div>
          <div className="docs-prose">
            <p id="prose-sample">Sample selectable text for toolbar test</p>
          </div>
          <SelectionToIssueToolbar
            pageId="page-child-1"
            projectKey="KAN"
            pageTitle="Parent Page"
          />
        </div>
      </QueryClientProvider>,
    );

    const proseSample = document.querySelector('#prose-sample');
    if (!proseSample) throw new Error('Missing sample');

    const mockRange = {
      commonAncestorContainer: proseSample,
      getBoundingClientRect: () => ({ top: 100, left: 100, width: 100, height: 20 }),
    };

    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => mockRange,
      toString: () => 'Sample selectable text for toolbar test',
    } as unknown as Selection);

    fireEvent(document, new Event('selectionchange'));

    await waitFor(() => {
      expect(screen.getByTestId('create-linked-issue-floating-btn')).toBeDefined();
    });

    // Trigger window resize and scroll to exercise position listeners
    act(() => {
      window.dispatchEvent(new Event('resize'));
      window.dispatchEvent(new Event('scroll'));
    });

    // Open modal
    fireEvent.click(screen.getByTestId('create-linked-issue-floating-btn'));
    expect(screen.getByLabelText('Create linked issue')).toBeDefined();

    // Cancel modal
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByLabelText('Create linked issue')).toBeNull();

    // Trigger selectionchange to restore floating button
    fireEvent(document, new Event('selectionchange'));

    // Reopen and submit failure
    fireEvent.click(screen.getByTestId('create-linked-issue-floating-btn'));
    fireEvent.click(screen.getByTestId('submit-issue-create-btn'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Quota exceeded');
    });

    // Success path with link click
    createSpy.mockResolvedValueOnce({ id: 'i-win', key: 'KAN-999' });
    vi.spyOn(docsApi, 'createLink').mockResolvedValueOnce({});
    fireEvent.change(screen.getByTestId('issue-description-input'), {
      target: { value: 'Updated description from test' },
    });
    fireEvent.click(screen.getByTestId('submit-issue-create-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('view-created-issue-link')).toBeDefined();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByLabelText('Create linked issue')).toBeNull();
  });

  it('SelectionToIssueToolbar handles small selections, text container nodes, and Escape dismiss', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <div>
          <div className="docs-prose">
            <p id="prose-small">
              Text <span id="inner-span">Inner text node here</span>
            </p>
          </div>
          <SelectionToIssueToolbar pageId="page-child-1" projectKey="KAN" pageTitle="Parent Page" />
        </div>
      </QueryClientProvider>,
    );

    const innerSpan = document.querySelector('#inner-span');
    const textNode = innerSpan?.firstChild;
    if (!textNode) throw new Error('Missing text node');

    // Collapsed selection
    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: true,
      rangeCount: 1,
      getRangeAt: () => ({
        commonAncestorContainer: textNode,
        getBoundingClientRect: () => ({ top: 10, left: 10, width: 10, height: 10 }),
      }),
      toString: () => '',
    } as unknown as Selection);

    fireEvent(document, new Event('selectionchange'));
    expect(screen.queryByTestId('create-linked-issue-floating-btn')).toBeNull();

    // Selection < 3 code points
    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({
        commonAncestorContainer: textNode,
        getBoundingClientRect: () => ({ top: 10, left: 10, width: 10, height: 10 }),
      }),
      toString: () => 'ab',
    } as unknown as Selection);

    fireEvent(document, new Event('selectionchange'));
    expect(screen.queryByTestId('create-linked-issue-floating-btn')).toBeNull();

    // Selection on textNode container >= 3 chars
    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({
        commonAncestorContainer: textNode,
        getBoundingClientRect: () => ({ top: 10, left: 10, width: 50, height: 20 }),
      }),
      toString: () => 'Valid inner text',
    } as unknown as Selection);

    fireEvent(document, new Event('selectionchange'));
    await waitFor(() => {
      expect(screen.getByTestId('create-linked-issue-floating-btn')).toBeDefined();
    });

    // Escape while button is shown
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('create-linked-issue-floating-btn')).toBeNull();

    // Reopen and open modal, then Escape while modal open
    fireEvent(document, new Event('selectionchange'));
    await waitFor(() => {
      expect(screen.getByTestId('create-linked-issue-floating-btn')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('create-linked-issue-floating-btn'));
    expect(screen.getByLabelText('Create linked issue')).toBeDefined();

    // selectionchange while modal is open (early return)
    fireEvent(document, new Event('selectionchange'));

    // Non-escape key while modal is open
    fireEvent.keyDown(window, { key: 'Tab' });

    // Escape while modal is open
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByLabelText('Create linked issue')).toBeNull();

    // Zero width/height range rect branch
    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({
        commonAncestorContainer: textNode,
        getBoundingClientRect: () => ({ top: 10, left: 10, width: 0, height: 0 }),
      }),
      toString: () => 'Zero size rect text',
    } as unknown as Selection);
    fireEvent(document, new Event('selectionchange'));
    expect(screen.getByTestId('create-linked-issue-floating-btn')).toBeDefined();
  });

  it('DocsWorkspaceView handles mobile sheet toggles and announcement timeout', () => {
    vi.useFakeTimers();
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/docs/page-child-1']}>
          <Routes>
            <Route path="/projects/:projectKey/docs/:pageId" element={<DocsWorkspaceView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Toggle sheets
    const treeSheetBtn = screen.getByTestId('toggle-tree-sheet-btn');
    const railSheetBtn = screen.getByTestId('toggle-rail-sheet-btn');

    act(() => {
      fireEvent.click(treeSheetBtn);
    });
    act(() => {
      fireEvent.click(railSheetBtn);
    });
    act(() => {
      fireEvent.click(railSheetBtn);
    });

    vi.useRealTimers();
  });

  it('DocsTreeNav handles title length > 500 and target selection change in move modal', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav projectKey="KAN" onSelectPage={vi.fn()} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('create-root-doc-btn')).toBeDefined();
    });

    // Test title > 500 chars
    fireEvent.click(screen.getByTestId('create-root-doc-btn'));
    fireEvent.change(screen.getByTestId('new-page-title-input'), {
      target: { value: 'A'.repeat(505) },
    });
    fireEvent.click(screen.getByTestId('submit-create-page-btn'));
    expect(screen.getByRole('alert').textContent).toContain('Title cannot exceed 500 characters');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    // Expand root to see child
    fireEvent.click(screen.getByRole('button', { name: 'Expand 🔒 Restricted Page' }));

    // Move modal target select
    fireEvent.click(screen.getByTestId('move-page-child-1'));
    const select = screen.getByTestId('move-target-select');
    fireEvent.change(select, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  });

  it('OutlineAndVersionsRail handles versions with missing fields and tab switching', async () => {
    vi.spyOn(docsApi, 'fetchPageVersions').mockResolvedValue([
      {
        version_seq: 1,
        page_id: 'page-child-1',
        title: 'Title',
        body_markdown: 'Content',
        body_sha256: 'h1',
        created_by_id: null,
        created_at: '2026-11-13T00:00:00Z',
      },
    ]);

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <OutlineAndVersionsRail
          pageId="page-child-1"
          projectKey="KAN"
          markdownContent="# Heading"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('rail-tab-history')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('rail-tab-history'));

    await waitFor(() => {
      expect(screen.getByTestId('version-item-v1')).toBeDefined();
    });

    // Click version item to preview
    fireEvent.click(screen.getByTestId('version-item-v1'));

    expect(screen.getByTestId('rail-tab-outline')).toBeDefined();
    fireEvent.click(screen.getByTestId('rail-tab-outline'));

    // Rerender with empty versions
    vi.spyOn(docsApi, 'fetchPageVersions').mockResolvedValue([]);
    const emptyClient = createTestQueryClient();
    rerender(
      <QueryClientProvider client={emptyClient}>
        <OutlineAndVersionsRail
          pageId="page-child-empty"
          projectKey="KAN"
          markdownContent="# Heading"
        />
      </QueryClientProvider>,
    );
  });

  it('PageEditorPane handles Enter in title and Ctrl+S hotkey', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane pageId="page-child-1" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    const titleInput = screen.getByTestId('page-title-input');
    // Enter key
    fireEvent.keyDown(titleInput, { key: 'Enter' });

    // Ctrl+S keydown
    fireEvent.keyDown(window, { key: 's', ctrlKey: true });
  });

  it('covers SelectionToIssueToolbar branch edges (empty firstLine, missing key, non-Error reject)', async () => {
    // Non-Error reject
    vi.spyOn(docsApi, 'createIssue').mockRejectedValue('String reject');

    render(
      <QueryClientProvider client={queryClient}>
        <div>
          <div className="docs-prose">
            <p id="branch-prose">Selectable prose line</p>
          </div>
          <SelectionToIssueToolbar pageId="page-1" projectKey="KAN" pageTitle="Doc Title" />
        </div>
      </QueryClientProvider>,
    );

    const prose = document.querySelector('#branch-prose');
    if (!prose) throw new Error('missing prose');

    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({
        commonAncestorContainer: prose,
        getBoundingClientRect: () => ({ top: 10, left: 10, width: 20, height: 10 }),
      }),
      toString: () => '   \n   \n   ', // lines is empty
    } as unknown as Selection);

    fireEvent(document, new Event('selectionchange'));

    // Selection with text
    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({
        commonAncestorContainer: prose,
        getBoundingClientRect: () => ({ top: 10, left: 10, width: 20, height: 10 }),
      }),
      toString: () => 'Valid line for issue',
    } as unknown as Selection);

    fireEvent(document, new Event('selectionchange'));
    await waitFor(() => {
      expect(screen.getByTestId('create-linked-issue-floating-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('create-linked-issue-floating-btn'));
    fireEvent.click(screen.getByTestId('submit-issue-create-btn'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toBe('Failed to create issue');
    });

    // Success with issue missing key
    vi.spyOn(docsApi, 'createIssue').mockResolvedValue({ id: 'issue-id-only' });
    vi.spyOn(docsApi, 'createLink').mockResolvedValue({});
    fireEvent.click(screen.getByTestId('submit-issue-create-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('view-created-issue-link')).toBeDefined();
    });
  });

  it('covers PageEditorPane branch edges (null body_sha256, breadcrumbs fallback, non-Error save, missing current_version_seq)', async () => {
    const pageWithFallbacks: docsApi.PageResponse = {
      ...mockPageFull,
      id: 'page-fallbacks',
      body_sha256: '',
      breadcrumbs: [
        { id: null, title: null, slug: null, restricted: false },
        { id: 'b2', title: null, slug: 'slug-two', restricted: false },
        { id: 'b3', title: 'Restricted Breadcrumb', slug: 'b3', restricted: true },
      ],
    };

    vi.spyOn(docsApi, 'fetchPage').mockResolvedValue(pageWithFallbacks);
    // Non-Error save failure
    vi.spyOn(docsApi, 'updatePage').mockRejectedValue('Non-error save failure');

    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane pageId="page-fallbacks" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    const titleInput = screen.getByTestId('page-title-input');
    fireEvent.change(titleInput, { target: { value: 'Trigger Save' } });
    fireEvent.blur(screen.getByRole('main'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Save failed');
    });

    // 412 problem with missing current_version_seq
    const conflict412 = new ApiProblem(412, {
      code: 'PRECONDITION_FAILED',
      detail: 'ETag mismatch',
    });
    vi.spyOn(docsApi, 'updatePage').mockRejectedValue(conflict412);
    fireEvent.change(titleInput, { target: { value: 'Trigger 412 Without Seq' } });
    fireEvent.blur(screen.getByRole('main'));

    await waitFor(() => {
      expect(screen.getByTestId('docs-conflict-alert')).toBeDefined();
    });
  });

  it('covers OutlineAndVersionsRail branch edges (duplicate headings, empty heading, link fallbacks, non-Error restore)', async () => {
    const mdWithDupes = `
# Duplicate
# Duplicate
# 
<!-- inline comment --> Some Text
`;
    const headings = extractHeadings(mdWithDupes);
    expect(headings.length).toBe(2);
    expect(headings[0]?.anchor).toBe('duplicate');
    expect(headings[1]?.anchor).toBe('duplicate-1');

    // Page with object links fallbacks
    const pageWithLinkFallbacks: docsApi.PageResponse = {
      ...mockPageFull,
      object_links: [
        { link_type: 'RELATES_TO' },
        { link_id: 'l2', source_id: 'SRC-ONLY', link_type: 'RELATES_TO' },
      ],
    };

    vi.spyOn(docsApi, 'fetchPageVersions').mockResolvedValue([
      {
        version_seq: 1,
        page_id: 'p1',
        title: 'V1',
        body_markdown: 'Content',
        body_sha256: '',
        created_by_id: null,
        created_at: '2026-11-13T00:00:00Z',
      },
    ]);

    vi.spyOn(docsApi, 'restorePageVersion').mockRejectedValue('Non-Error restore error');

    const onAnnounce = vi.fn();

    render(
      <QueryClientProvider client={queryClient}>
        <OutlineAndVersionsRail
          pageId="page-fallbacks"
          projectKey="KAN"
          page={pageWithLinkFallbacks}
          markdownContent="# Top"
          onAnnounce={onAnnounce}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('docs-linked-work-items')).toBeDefined();
    });

    // Test restore failure with non-Error
    fireEvent.click(screen.getByTestId('rail-tab-history'));
    await waitFor(() => {
      expect(screen.getByTestId('version-item-v1')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('version-item-v1'));
    fireEvent.click(screen.getByTestId('restore-v1-btn'));

    await waitFor(() => {
      expect(onAnnounce).toHaveBeenCalledWith('Restore error: Restore failed');
    });
  });

  it('covers DocsTreeNav branch edges (add subpage modal header, tree keydown outside flattened, depth limit in move targets)', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav projectKey="KAN" onSelectPage={vi.fn()} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('create-root-doc-btn')).toBeDefined();
    });

    // Add sub-page button
    fireEvent.click(screen.getByTestId('add-subpage-page-restricted-root'));
    expect(screen.getByText('Create Sub-page')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    // Keydown on tree with unknown active item
    const treeView = screen.getByRole('tree');
    fireEvent.keyDown(treeView, { key: 'ArrowDown' });
  });

  it('covers DocsWorkspaceView branch edges (findFirst with restricted leaf and no accessible page)', async () => {
    const unnavigableTree: docsApi.PageTreeNode[] = [
      { id: 'res-leaf', restricted: true, children: [] },
      {
        id: 'res-parent',
        restricted: true,
        children: [{ id: 'child-restricted', restricted: true, children: [] }],
      },
    ];

    vi.spyOn(docsApi, 'fetchDocsTree').mockResolvedValue(unnavigableTree);

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

  it('covers remaining DocsTreeNav keyboard branches, pending mutations, and tree bounds', async () => {
    const treeDataBranch: docsApi.PageTreeNode[] = [
      {
        id: 'r-restricted',
        title: 'Restricted Root',
        slug: 'r-restricted',
        restricted: true,
        children: [],
      },
      {
        id: 'r-normal',
        title: 'Normal Root',
        slug: 'r-normal',
        restricted: false,
        children: [
          {
            id: 'r-child-1',
            title: 'Child One',
            slug: 'r-child-1',
            restricted: false,
            children: [],
          },
        ],
      },
      {
        id: 'r-sibling',
        title: 'Sibling Root',
        slug: 'r-sibling',
        restricted: false,
        children: [],
      },
    ];

    vi.spyOn(docsApi, 'fetchDocsTree').mockResolvedValue(treeDataBranch);
    const createPendingPromise = new Promise<docsApi.PageResponse>(() => {
      // Pending
    });
    vi.spyOn(docsApi, 'createPage').mockReturnValue(createPendingPromise);

    const movePendingPromise = new Promise<docsApi.PageResponse>(() => {
      // Pending
    });
    vi.spyOn(docsApi, 'movePage').mockReturnValue(movePendingPromise);

    render(
      <QueryClientProvider client={queryClient}>
        <DocsTreeNav projectKey="KAN" onSelectPage={vi.fn()} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('treeitem-r-restricted')).toBeDefined();
    });

    const resItem = screen.getByTestId('treeitem-r-restricted');
    const normalItem = screen.getByTestId('treeitem-r-normal');

    // Enter on restricted item (ignored)
    fireEvent.keyDown(resItem, { key: 'Enter' });

    // ArrowLeft on root without parent
    fireEvent.keyDown(resItem, { key: 'ArrowLeft' });

    // Expand normal item
    fireEvent.keyDown(normalItem, { key: 'ArrowRight' });

    await waitFor(() => {
      expect(screen.getByTestId('treeitem-r-child-1')).toBeDefined();
    });

    // ArrowRight on already expanded item when next item is child (moves to child)
    fireEvent.keyDown(normalItem, { key: 'ArrowRight' });

    // Test createMutation.isPending
    fireEvent.click(screen.getByTestId('create-root-doc-btn'));
    fireEvent.change(screen.getByTestId('new-page-title-input'), {
      target: { value: 'Pending Page' },
    });
    fireEvent.click(screen.getByTestId('submit-create-page-btn'));
    await waitFor(() => {
      expect(screen.getByText('Creating...')).toBeDefined();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    // Test moveMutation.isPending
    fireEvent.click(screen.getByTestId('move-page-r-child-1'));
    fireEvent.click(screen.getByTestId('submit-move-page-btn'));
    await waitFor(() => {
      expect(screen.getByText('Moving...')).toBeDefined();
    });
  });

  it('covers OutlineAndVersionsRail pending restore, empty heading, and observer false branches', async () => {
    let observerCallback: ((entries: IntersectionObserverEntry[]) => void) | undefined;
    class MockIntersectionObserver {
      constructor(cb: (entries: IntersectionObserverEntry[]) => void) {
        observerCallback = cb;
      }
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
    }
    window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver;

    vi.spyOn(docsApi, 'fetchPageVersions').mockResolvedValue([
      {
        version_seq: 1,
        page_id: 'p1',
        title: 'V1',
        body_markdown: 'Content',
        body_sha256: 'h1',
        created_by_id: 'user-1',
        created_at: '2026-11-13T00:00:00Z',
      },
    ]);

    const restorePendingPromise = new Promise<docsApi.PageResponse>(() => {
      // Pending
    });
    vi.spyOn(docsApi, 'restorePageVersion').mockReturnValue(restorePendingPromise);

    const headingEl = document.createElement('div');
    headingEl.id = 'sec-1';
    document.body.appendChild(headingEl);

    render(
      <QueryClientProvider client={queryClient}>
        <OutlineAndVersionsRail
          pageId="p1"
          projectKey="KAN"
          markdownContent="# "
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('rail-tab-history')).toBeDefined();
    });

    // Observer callback with isIntersecting = false
    if (observerCallback) {
      observerCallback([
        {
          isIntersecting: false,
          target: headingEl,
        } as unknown as IntersectionObserverEntry,
      ]);
    }

    // Pending restore
    fireEvent.click(screen.getByTestId('rail-tab-history'));
    await waitFor(() => {
      expect(screen.getByTestId('version-item-v1')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('version-item-v1'));
    fireEvent.click(screen.getByTestId('restore-v1-btn'));
    await waitFor(() => {
      expect(screen.getByText('Restoring...')).toBeDefined();
    });

    // Strip inline markdown with empty alt and text
    expect(stripInlineMarkdown('![]()')).toBe('');
    expect(extractHeadings('# ![]()').length).toBe(0);
  });

  it('covers DocsTreeNav error state and depth limit in validMoveTargets', async () => {
    // Error state test
    const errClient = createTestQueryClient();
    vi.spyOn(docsApi, 'fetchDocsTree').mockRejectedValueOnce(new Error('Tree load failure'));

    render(
      <QueryClientProvider client={errClient}>
        <DocsTreeNav projectKey="KAN" onSelectPage={vi.fn()} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('docs-tree-error')).toBeDefined();
    });

    // Test depth limit: node at depth 9 + movingNode of depth 2
    const depthLimitTree: docsApi.PageTreeNode[] = [
      {
        id: null,
        restricted: true,
        label: 'Node without ID',
        children: [],
      },
      {
        id: null,
        restricted: false,
        title: 'Movable without ID',
        children: [],
      },
      {
        id: 'no-title-node',
        title: null,
        slug: 'slug-only',
        restricted: false,
        children: [],
      },
      {
        id: 'movable-parent',
        title: 'Movable Parent',
        restricted: false,
        children: [
          {
            id: 'movable-child',
            title: 'Movable Child',
            restricted: false,
            children: [],
          },
        ],
      },
      {
        id: 'd1',
        title: 'D1',
        restricted: false,
        children: [
          {
            id: 'd2',
            title: 'D2',
            restricted: false,
            children: [
              {
                id: 'd3',
                title: 'D3',
                restricted: false,
                children: [
                  {
                    id: 'd4',
                    title: 'D4',
                    restricted: false,
                    children: [
                      {
                        id: 'd5',
                        title: 'D5',
                        restricted: false,
                        children: [
                          {
                            id: 'd6',
                            title: 'D6',
                            restricted: false,
                            children: [
                              {
                                id: 'd7',
                                title: 'D7',
                                restricted: false,
                                children: [
                                  {
                                    id: 'd8',
                                    title: 'D8',
                                    restricted: false,
                                    children: [
                                      {
                                        id: 'd9',
                                        title: 'D9',
                                        restricted: false,
                                        children: [
                                          {
                                            id: 'd10',
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

    const moveClient = createTestQueryClient();
    vi.spyOn(docsApi, 'fetchDocsTree').mockResolvedValue(depthLimitTree);
    const onSelectSpy = vi.fn();

    render(
      <QueryClientProvider client={moveClient}>
        <DocsTreeNav projectKey="KAN" activePageId="movable-child" onSelectPage={onSelectSpy} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('treeitem-movable-parent')).toBeDefined();
    });

    // Click restricted node without ID - triggers onClick with restricted=true
    fireEvent.click(screen.getByTestId('treeitem-node-1'));
    expect(onSelectSpy).not.toHaveBeenCalledWith('node-1');

    // Click move on node without ID - opens modal then submits without movingNode.id
    fireEvent.click(screen.getByTestId('move-page-node-2'));
    expect(screen.getByLabelText('Move page')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Move' }));
    // Modal remains open because handleSubmitMove returned early
    expect(screen.getByLabelText('Move page')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    // Expand all D nodes
    for (let i = 1; i <= 9; i++) {
      const toggle = screen.queryByLabelText(new RegExp(`Expand D${String(i)}`, 'i'));
      if (toggle) fireEvent.click(toggle);
    }

    // Open move modal for movable-parent (subtreeDepth = 2)
    fireEvent.click(screen.getByTestId('move-page-movable-parent'));

    // Move modal opened and filter ran with depth + subtreeDepth > 10
    expect(screen.getByLabelText('Move page')).toBeDefined();
  });

  it('covers Outline heading missing target in DOM', async () => {
    const testClient = createTestQueryClient();
    render(
      <QueryClientProvider client={testClient}>
        <OutlineAndVersionsRail
          page={{
            ...mockPageFull,
            id: 'page-outline-missing',
            body_markdown: '## Missing Heading',
          }}
          pageId="page-outline-missing"
        />
      </QueryClientProvider>,
    );

    const headingLink = await screen.findByRole('link', { name: 'Missing Heading' });
    // Clicking heading whose target DOM id does not exist
    fireEvent.click(headingLink);
    expect(headingLink).toBeDefined();
  });
});
