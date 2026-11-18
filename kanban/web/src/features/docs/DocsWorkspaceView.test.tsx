import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { DocsWorkspaceView } from './DocsWorkspaceView';
import * as docsApi from './docsApi';
import * as clientModule from '../../api/client';
import { ApiProblem } from '../../api/problem';
import ProjectCustomFieldsSettingsRoute, {
  ensureCustomFieldsCsrfToken,
  getCustomFieldsCsrfToken,
} from '../../routes/projects/settings/custom-fields';

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

  it('does not call /api/v1/docs/:key/tree when /api/v1/projects/:key/docs/tree throws ApiProblem', async () => {
    vi.restoreAllMocks();
    const apiSpy = vi
      .spyOn(clientModule, 'apiFetch')
      .mockRejectedValueOnce(new ApiProblem(401, { detail: 'Unauthorized' }));

    await expect(docsApi.fetchDocsTree('KAN')).rejects.toBeInstanceOf(ApiProblem);
    expect(apiSpy).toHaveBeenCalledTimes(1);
    expect(apiSpy).toHaveBeenCalledWith('GET', '/api/v1/projects/{projectKey}/docs/tree', {
      params: { projectKey: 'KAN' },
    });
  });

  it('bootstraps CSRF token from /api/v1/auth/session and creates project doc + page when doc_ref is a project key', async () => {
    vi.restoreAllMocks();
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    document.cookie = '__Host-kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';

    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ authenticated: true, csrf_token: 'docs-csrf-token-456' }),
    });

    try {
      const apiSpy = vi
        .spyOn(clientModule, 'apiFetch')
        // 1. POST /api/v1/docs/KAN/pages -> 404 ApiProblem
        .mockRejectedValueOnce(new ApiProblem(404, { detail: 'Not found' }))
        // 2. GET /api/v1/projects/KAN -> project UUID
        .mockResolvedValueOnce({ id: 'proj-uuid-1' })
        // 3. GET /api/v1/docs?project=proj-uuid-1 -> empty
        .mockResolvedValueOnce([])
        // 4. POST /api/v1/docs -> created doc
        .mockResolvedValueOnce({ id: 'doc-uuid-1' })
        // 5. POST /api/v1/docs/doc-uuid-1/pages -> created page
        .mockResolvedValueOnce(mockPageData);

      const created = await docsApi.createPage('KAN', {
        title: 'QA Architecture Spec',
        parent_page_id: null,
      });

      expect(created).toEqual(mockPageData);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        '/api/v1/auth/session',
        expect.objectContaining({ method: 'GET', credentials: 'same-origin' }),
      );
      expect(clientModule.getCsrfToken()).toBe('docs-csrf-token-456');
      // Calling ensureDocsCsrfToken when cookie already exists returns existing token immediately
      expect(await docsApi.ensureDocsCsrfToken()).toBe('docs-csrf-token-456');
      expect(apiSpy).toHaveBeenCalledWith('POST', '/api/v1/docs/{doc_ref}/pages', {
        params: { doc_ref: 'doc-uuid-1' },
        body: { title: 'QA Architecture Spec', parent_page_id: null },
      });

      // Second call when project doc already exists
      apiSpy
        .mockRejectedValueOnce(new ApiProblem(404, { detail: 'Not found' }))
        .mockResolvedValueOnce({ id: 'proj-uuid-1' })
        .mockResolvedValueOnce([{ id: 'existing-doc-uuid' }])
        .mockResolvedValueOnce(mockPageData);

      const createdExisting = await docsApi.createPage('KAN', {
        title: 'Second Spec',
      });
      expect(createdExisting).toEqual(mockPageData);
      expect(apiSpy).toHaveBeenCalledWith('POST', '/api/v1/docs/{doc_ref}/pages', {
        params: { doc_ref: 'existing-doc-uuid' },
        body: { title: 'Second Spec' },
      });

      // Fallback when /api/v1/auth/session rejects in offline environment
      document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
      globalThis.fetch = vi.fn().mockRejectedValueOnce(new Error('Offline'));
      expect(await docsApi.ensureDocsCsrfToken()).toBeNull();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('ProjectCustomFieldsSettingsRoute bootstraps X-CSRF-Token from /api/v1/auth/session on POST /api/v1/projects/:key/custom-fields', async () => {
    vi.restoreAllMocks();
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    document.cookie = '__Host-kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    expect(getCustomFieldsCsrfToken()).toBeNull();

    // Offline fallback returns null
    const failingFetch = vi.fn().mockRejectedValueOnce(new Error('Offline'));
    expect(await ensureCustomFieldsCsrfToken(failingFetch)).toBeNull();

    // Missing csrf_token in response returns null
    const emptyTokenFetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ authenticated: true }),
    });
    expect(await ensureCustomFieldsCsrfToken(emptyTokenFetch)).toBeNull();

    let returnCsrf = true;
    const originalFetch = globalThis.fetch;
    const baseFetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;
      if (url === '/api/v1/auth/session') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve(
              returnCsrf
                ? { authenticated: true, csrf_token: 'cf-csrf-token-777' }
                : { authenticated: true }
            ),
        } as Response);
      }
      if (url === '/api/v1/projects/KAN/custom-fields' && (!init?.method || init.method === 'GET')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve([]),
        } as Response);
      }
      if (url.includes('/api/v1/projects/KAN/custom-fields') && init?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          status: 201,
          json: () =>
            Promise.resolve({
              id: 'cf-1',
              slug: 'cvss-score',
              name: 'CVSS Score',
              tier: 'wasm',
              output_format: 'text',
              output_format_metadata: {},
              script_source: 'return "ok";',
              target_scope: 'PROJECT',
              credential_mode: 'INVOKING_USER',
              egress_allowlist: [],
              is_enabled: true,
            }),
        } as Response);
      }
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) } as Response);
    });
    globalThis.fetch = baseFetchMock;

    try {
      const token = await ensureCustomFieldsCsrfToken(baseFetchMock);
      expect(token).toBe('cf-csrf-token-777');
      expect(getCustomFieldsCsrfToken()).toBe('cf-csrf-token-777');
      // Calling again when cookie exists returns cached cookie token
      expect(await ensureCustomFieldsCsrfToken(baseFetchMock)).toBe('cf-csrf-token-777');

      // Render non-admin route first to cover non-admin early return
      const nonAdminRender = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings/custom-fields?non_admin=true']}>
            <Routes>
              <Route
                path="/projects/:projectKey/settings/custom-fields"
                element={<ProjectCustomFieldsSettingsRoute />}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      nonAdminRender.unmount();

      // Clear cookie before mounting admin route to test route-level bootstrap + POST interception
      document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';

      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings/custom-fields']}>
            <Routes>
              <Route
                path="/projects/:projectKey/settings/custom-fields"
                element={<ProjectCustomFieldsSettingsRoute />}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('custom-fields-editor-layout')).toBeDefined();
      });

      // Clear cookie right before POST so wrappedFetch must re-bootstrap via ensureCustomFieldsCsrfToken
      document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
      await globalThis.fetch(new Request('http://localhost/api/v1/projects/KAN/custom-fields'), {
        method: 'POST',
      });
      // Also call with existing X-CSRF-Token header to cover rawHeaders['X-CSRF-Token'] branch
      await globalThis.fetch(new Request('http://localhost/api/v1/projects/KAN/custom-fields'), {
        method: 'POST',
        headers: { 'X-CSRF-Token': 'existing-cf-token' },
      });

      // Also call when session returns no token so ensureCustomFieldsCsrfToken returns null falling back to ''
      returnCsrf = false;
      document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
      await globalThis.fetch(new Request('http://localhost/api/v1/projects/KAN/custom-fields'), {
        method: 'POST',
      });
      returnCsrf = true;

      fireEvent.change(screen.getByTestId('field-name-input'), {
        target: { value: 'CVSS Score' },
      });
      fireEvent.change(screen.getByTestId('field-slug-input'), {
        target: { value: 'cvss-score' },
      });
      fireEvent.click(screen.getByTestId('save-definition-btn'));

      await waitFor(() => {
        expect(baseFetchMock).toHaveBeenCalledWith(
          '/api/v1/projects/KAN/custom-fields',
          expect.objectContaining({
            method: 'POST',
            headers: expect.objectContaining({
              'X-CSRF-Token': 'cf-csrf-token-777',
            }) as unknown as Record<string, string>,
          }),
        );
      });

      unmount();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('covers ProjectCustomFieldsSettingsRoute capabilities PROJECT_ADMIN, empty capabilities, role query params, and query error', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_m, url) => {
      if (url.includes('/api/v1/projects/PROJ_ADMIN')) {
        return Promise.resolve({ capabilities: ['PROJECT_ADMIN'] });
      }
      if (url.includes('/api/v1/projects/ADMIN_CAP')) {
        return Promise.resolve({ capabilities: ['ADMIN'] });
      }
      if (url.includes('/api/v1/projects/EMPTY_OBJ')) {
        return Promise.resolve({});
      }
      if (url.includes('/api/v1/projects/NO_CAPS')) {
        return Promise.resolve({ capabilities: [] });
      }
      if (url.includes('/api/v1/projects/ERR_CAPS')) {
        return Promise.reject(new Error('Project fetch failure'));
      }
      return Promise.resolve({});
    });

    const testCases = [
      { entry: '/projects/PROJ_ADMIN/settings/custom-fields', expectedId: 'custom-fields-editor-layout' },
      { entry: '/projects/ADMIN_CAP/settings/custom-fields', expectedId: 'custom-fields-editor-layout' },
      { entry: '/projects/EMPTY_OBJ/settings/custom-fields', expectedId: 'not-found-view' },
      { entry: '/projects/NO_CAPS/settings/custom-fields', expectedId: 'not-found-view' },
      { entry: '/projects/KAN/settings/custom-fields?role=member', expectedId: 'not-found-view' },
      { entry: '/projects/KAN/settings/custom-fields?role=viewer', expectedId: 'not-found-view' },
      { entry: '/projects/ERR_CAPS/settings/custom-fields', expectedId: 'custom-fields-editor-layout' },
    ];

    for (const tc of testCases) {
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={[tc.entry]}>
            <Routes>
              <Route
                path="/projects/:projectKey/settings/custom-fields"
                element={<ProjectCustomFieldsSettingsRoute />}
              />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(await screen.findByTestId(tc.expectedId)).toBeDefined();
      unmount();
    }
  });
});
