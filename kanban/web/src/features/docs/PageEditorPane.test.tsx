import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PageEditorPane } from './PageEditorPane';
import * as docsApi from './docsApi';
import { ApiProblem } from '../../api/problem';

const mockPageData: docsApi.PageResponse = {
  id: 'page-auth-studio',
  canonical_key: 'docs/architecture/auth-studio',
  doc_id: 'doc-arch',
  parent_page_id: 'page-arch',
  workspace_id: 'ws-1',
  title: 'Auth Studio',
  body_markdown: '# Overview\n\nAuth Studio specification.\n\n## PKCE S256\n\nDetails.',
  body_sha256: 'a1b2c3d4e5f6',
  hierarchy_path: 'docs.architecture.auth_studio',
  version_seq: 7,
  sort_rank: '0|hzzzzz:',
  breadcrumbs: [
    { id: 'doc-root', title: 'Docs', slug: 'docs', canonical_key: 'docs', restricted: false },
    { id: 'page-arch', title: 'Architecture', slug: 'architecture', canonical_key: 'docs/architecture', restricted: false },
    { id: 'page-auth-studio', title: 'Auth Studio', slug: 'auth-studio', canonical_key: 'docs/architecture/auth-studio', restricted: false },
  ],
  outline: [
    { level: 1, text: 'Overview', anchor: 'overview', start_line: 1 },
    { level: 2, text: 'PKCE S256', anchor: 'pkce-s256', start_line: 5 },
  ],
  access_manifest: { users: ['adam'], roles: ['ADMIN'] },
  capabilities: ['VIEW', 'EDIT', 'DELETE'],
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

describe('PageEditorPane', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.restoreAllMocks();
    vi.spyOn(docsApi, 'fetchPage').mockResolvedValue(mockPageData);
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
  });

  it('renders page metadata, breadcrumbs, version pill, and access pill', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane pageId="page-auth-studio" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    // Title input
    const titleInput = screen.getByTestId<HTMLTextAreaElement>('page-title-input');
    expect(titleInput.value).toBe('Auth Studio');

    // Breadcrumbs
    expect(screen.getByText('Docs')).toBeDefined();
    expect(screen.getByText('Architecture')).toBeDefined();

    // Version pill
    expect(screen.getByTestId('page-version-pill').textContent).toBe('v7');

    // Access pill
    expect(screen.getByTestId('page-access-pill')).toBeDefined();
  });

  it('dispatches kb:open-access-inspector custom event when access pill is activated', async () => {
    const eventSpy = vi.fn();
    window.addEventListener('kb:open-access-inspector', eventSpy);

    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane pageId="page-auth-studio" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-access-pill')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('page-access-pill'));
    expect(eventSpy).toHaveBeenCalled();
    const event = eventSpy.mock.calls[0]?.[0] as CustomEvent<{ object_id: string }> | undefined;
    expect(event?.detail.object_id).toBe('page-auth-studio');

    window.removeEventListener('kb:open-access-inspector', eventSpy);
  });

  it('triggers debounced save with If-Match ETag on title change', async () => {
    const updateSpy = vi.spyOn(docsApi, 'updatePage').mockResolvedValue({
      ...mockPageData,
      title: 'Auth Studio Updated',
      version_seq: 8,
      body_sha256: 'b2c3d4e5f6a1',
    });

    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane pageId="page-auth-studio" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    const titleInput = screen.getByTestId('page-title-input');
    fireEvent.change(titleInput, { target: { value: 'Auth Studio Updated' } });

    // Trigger blur or wait for debounce
    fireEvent.blur(screen.getByRole('main'));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'page-auth-studio',
        {
          title: 'Auth Studio Updated',
          body_markdown: mockPageData.body_markdown,
        },
        '"a1b2c3d4e5f6"',
      );
    });
  });

  it('handles 412 Precondition Failed conflict and provides Copy My Draft and Reload Latest', async () => {
    const problem = new ApiProblem(412, {
      code: 'PRECONDITION_FAILED',
      detail: 'ETag mismatch',
      current_version_seq: 9,
    });
    vi.spyOn(docsApi, 'updatePage').mockRejectedValue(problem);

    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextSpy,
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane pageId="page-auth-studio" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    const titleInput = screen.getByTestId('page-title-input');
    fireEvent.change(titleInput, { target: { value: 'Conflicted Title' } });
    fireEvent.blur(screen.getByRole('main'));

    await waitFor(() => {
      expect(screen.getByTestId('docs-conflict-alert')).toBeDefined();
    });

    expect(screen.getByTestId('docs-conflict-alert').textContent).toContain(
      'Page was updated elsewhere (v9)',
    );

    // Test Copy My Draft button
    fireEvent.click(screen.getByTestId('copy-my-draft-btn'));
    await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalled();
    });

    // Test Reload Latest button
    fireEvent.click(screen.getByTestId('reload-latest-btn'));
    await waitFor(() => {
      expect(screen.queryByTestId('docs-conflict-alert')).toBeNull();
    });
  });

  it('validates title length boundary (empty or > 500 chars)', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane pageId="page-auth-studio" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    const titleInput = screen.getByTestId('page-title-input');

    // Empty title
    fireEvent.change(titleInput, { target: { value: '   ' } });
    expect(screen.getByTestId('page-validation-alert').textContent).toContain(
      'Title cannot be empty',
    );

    // 501 char title
    const longTitle = 'a'.repeat(501);
    fireEvent.change(titleInput, { target: { value: longTitle } });
    expect(screen.getByTestId('page-validation-alert').textContent).toContain(
      'Title cannot exceed 500 characters',
    );
  });

  it('renders identical copy for 403 and 404 page errors (S3.4 security invariant)', async () => {
    // Test 404
    vi.spyOn(docsApi, 'fetchPage').mockRejectedValue(
      new ApiProblem(404, { code: 'NOT_FOUND' }),
    );

    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane pageId="missing-page" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-not-found')).toBeDefined();
    });
    expect(screen.getByTestId('page-not-found').textContent).toBe(
      'Page was not found or you do not have access.',
    );
    unmount();

    // Test 403
    const client403 = createTestQueryClient();
    vi.spyOn(docsApi, 'fetchPage').mockRejectedValue(
      new ApiProblem(403, { code: 'FORBIDDEN' }),
    );

    render(
      <QueryClientProvider client={client403}>
        <PageEditorPane pageId="forbidden-page" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-not-found')).toBeDefined();
    });
    expect(screen.getByTestId('page-not-found').textContent).toBe(
      'Page was not found or you do not have access.',
    );
  });

  it('triggers save on Cmd+S shortcut and supports Enter in title input', async () => {
    const updateSpy = vi.spyOn(docsApi, 'updatePage').mockResolvedValue(mockPageData);
    const onToggleRail = vi.fn();

    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane
          pageId="page-auth-studio"
          projectKey="KAN"
          onToggleRail={onToggleRail}
          isRailOpen={true}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    const titleInput = screen.getByTestId('page-title-input');
    fireEvent.keyDown(titleInput, { key: 'Enter' });

    // Press Cmd+S
    fireEvent.keyDown(window, { key: 's', metaKey: true });

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalled();
    });

    // Test rail toggle button
    fireEvent.click(screen.getByTestId('rail-toggle-btn'));
    expect(onToggleRail).toHaveBeenCalled();
  });

  it('displays validation error banner on non-412 save errors', async () => {
    vi.spyOn(docsApi, 'updatePage').mockRejectedValue(new Error('Network error on save'));

    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane pageId="page-auth-studio" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    fireEvent.change(screen.getByTestId('page-title-input'), { target: { value: 'New T' } });
    fireEvent.blur(screen.getByRole('main'));

    await waitFor(() => {
      expect(screen.getByTestId('page-validation-alert').textContent).toContain('Network error on save');
    });
  });
});
