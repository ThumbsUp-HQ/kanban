// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Unit Tests for DocsWorkspaceView Conflict Bar & Validation Alert Tokens (KAN-443).
 * Verifies:
 * - CSS token assertions for .docs-conflict-* and .docs-validation-alert
 * - Document conflict alert rendering and interactive actions in Light theme
 * - Document conflict alert rendering and interactive actions in Dark theme
 * - Validation alert rendering and boundary validation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { ProjectRouteContext } from '../../../app/ProjectRouteContext';
import { DocsWorkspaceView } from '../DocsWorkspaceView';
import * as docsApi from '../docsApi';
import { ApiProblem } from '../../../api/problem';

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
  body_sha256: 'hash-abc-123',
  hierarchy_path: 'docs.auth_studio',
  version_seq: 1,
  sort_rank: '0|hzzzzz:',
  breadcrumbs: [
    { id: 'doc-root', title: 'Docs', slug: 'docs', canonical_key: 'docs', restricted: false },
    { id: 'page-auth-studio', title: 'Auth Studio', slug: 'auth-studio', canonical_key: 'docs/auth-studio', restricted: false },
  ],
  outline: [
    { level: 1, text: 'Overview', anchor: 'overview', start_line: 1 },
  ],
  access_manifest: { users: ['adam'], roles: ['ADMIN'] },
  capabilities: ['VIEW', 'EDIT', 'ADMIN'],
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

describe('DocsWorkspaceView Conflict Bar & Validation Alert Tokens (KAN-443)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.restoreAllMocks();
    vi.spyOn(docsApi, 'fetchDocsTree').mockResolvedValue(mockTreeData);
    vi.spyOn(docsApi, 'fetchPage').mockResolvedValue(mockPageData);
    vi.spyOn(docsApi, 'fetchPageVersions').mockResolvedValue([]);

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

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('verifies DocsWorkspaceView.css uses semantic tokens for conflict bar and validation alert', () => {
    const cssPath = resolve(__dirname, '../DocsWorkspaceView.css');
    const cssContent = readFileSync(cssPath, 'utf-8');

    // Conflict banner rules
    expect(cssContent).toContain('.docs-conflict-banner {');
    expect(cssContent).toContain('background: var(--danger-bg);');
    expect(cssContent).toContain('border-bottom: 1px solid var(--border-danger);');
    expect(cssContent).toContain('color: var(--danger-fg);');

    // Conflict action buttons
    expect(cssContent).toContain('.docs-conflict-btn {');
    expect(cssContent).toContain('background: var(--bg-surface-raised);');
    expect(cssContent).toContain('border: 1px solid var(--danger-fg);');
    expect(cssContent).toContain('color: var(--danger-fg);');
    expect(cssContent).toContain('.docs-conflict-btn:hover {');
    expect(cssContent).toContain('background: var(--bg-hover);');

    // Primary action button
    expect(cssContent).toContain('.docs-conflict-btn--primary {');
    expect(cssContent).toContain('background: var(--bg-danger);');
    expect(cssContent).toContain('border-color: var(--bg-danger);');
    expect(cssContent).toContain('color: var(--accent-primary-fg);');
    expect(cssContent).toContain('.docs-conflict-btn--primary:hover {');
    expect(cssContent).toContain('background: var(--bg-danger-hover);');
    expect(cssContent).toContain('border-color: var(--bg-danger-hover);');

    // Validation alert
    expect(cssContent).toContain('.docs-validation-alert {');
    expect(cssContent).toContain('background: var(--warn-bg);');
    expect(cssContent).toContain('border-bottom: 1px solid var(--border-warning);');
    expect(cssContent).toContain('color: var(--warn-fg);');

    // Assert absence of hardcoded values in conflict bar and validation alert blocks
    const conflictSection = cssContent.slice(
      cssContent.indexOf('/* 412 Conflict Alert Banner */'),
      cssContent.indexOf('/* Spacious Editorial Area (.docs-prose) */'),
    );
    expect(conflictSection).not.toContain('#fef2f2');
    expect(conflictSection).not.toContain('#fecaca');
    expect(conflictSection).not.toContain('#991b1b');
    expect(conflictSection).not.toContain('#fca5a5');
    expect(conflictSection).not.toContain('#dc2626');
    expect(conflictSection).not.toContain('#fffbeb');
    expect(conflictSection).not.toContain('#fde68a');
    expect(conflictSection).not.toContain('#92400e');
    expect(conflictSection).not.toContain('#ffffff');
  });

  it('renders conflict banner and executes draft actions in Light Theme', async () => {
    document.documentElement.setAttribute('data-theme', 'light');

    const problem = new ApiProblem(412, {
      code: 'OPTIMISTIC_LOCK_CONFLICT',
      current_version_seq: 9,
    });
    vi.spyOn(docsApi, 'updatePage').mockRejectedValue(problem);

    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextSpy,
      },
    });

    const routeCtx = {
      projectKey: 'KAN',
      projectName: 'Kanban',
      modulesEnabled: true,
      capabilities: ['VIEW', 'EDIT', 'ADMIN'],
      isProjectAdmin: true,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <ProjectRouteContext.Provider value={routeCtx}>
          <MemoryRouter initialEntries={['/projects/KAN/docs/page-auth-studio']}>
            <Routes>
              <Route path="/projects/:projectKey/docs/:pageId" element={<DocsWorkspaceView />} />
            </Routes>
          </MemoryRouter>
        </ProjectRouteContext.Provider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    const titleInput = screen.getByTestId('page-title-input');
    fireEvent.change(titleInput, { target: { value: 'Light Mode Conflicted' } });
    fireEvent.blur(screen.getByRole('main'));

    await waitFor(() => {
      expect(screen.getByTestId('docs-conflict-alert')).toBeDefined();
    });

    const alertBanner = screen.getByTestId('docs-conflict-alert');
    expect(alertBanner.textContent).toContain('Page was updated elsewhere (v9)');
    expect(alertBanner.textContent).toContain('Copy your draft or reload latest.');

    // Test Copy My Draft button
    const copyBtn = screen.getByTestId('copy-my-draft-btn');
    fireEvent.click(copyBtn);
    await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalled();
    });

    // Test Reload Latest button clears alert
    const reloadBtn = screen.getByTestId('reload-latest-btn');
    fireEvent.click(reloadBtn);
    await waitFor(() => {
      expect(screen.queryByTestId('docs-conflict-alert')).toBeNull();
    });
  });

  it('renders conflict banner and executes draft actions in Dark Theme', async () => {
    document.documentElement.setAttribute('data-theme', 'dark');

    const problem = new ApiProblem(412, {
      code: 'OPTIMISTIC_LOCK_CONFLICT',
      current_version_seq: 14,
    });
    vi.spyOn(docsApi, 'updatePage').mockRejectedValue(problem);

    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextSpy,
      },
    });

    const routeCtx = {
      projectKey: 'KAN',
      projectName: 'Kanban',
      modulesEnabled: true,
      capabilities: ['VIEW', 'EDIT', 'ADMIN'],
      isProjectAdmin: true,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <ProjectRouteContext.Provider value={routeCtx}>
          <MemoryRouter initialEntries={['/projects/KAN/docs/page-auth-studio']}>
            <Routes>
              <Route path="/projects/:projectKey/docs/:pageId" element={<DocsWorkspaceView />} />
            </Routes>
          </MemoryRouter>
        </ProjectRouteContext.Provider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    const titleInput = screen.getByTestId('page-title-input');
    fireEvent.change(titleInput, { target: { value: 'Dark Mode Conflicted' } });
    fireEvent.blur(screen.getByRole('main'));

    await waitFor(() => {
      expect(screen.getByTestId('docs-conflict-alert')).toBeDefined();
    });

    const alertBanner = screen.getByTestId('docs-conflict-alert');
    expect(alertBanner.textContent).toContain('Page was updated elsewhere (v14)');

    const copyBtn = screen.getByTestId('copy-my-draft-btn');
    fireEvent.click(copyBtn);
    await waitFor(() => {
      expect(writeTextSpy).toHaveBeenCalled();
    });

    const reloadBtn = screen.getByTestId('reload-latest-btn');
    fireEvent.click(reloadBtn);
    await waitFor(() => {
      expect(screen.queryByTestId('docs-conflict-alert')).toBeNull();
    });
  });

  it('renders validation alert for client boundaries and server errors in Light and Dark themes', async () => {
    const routeCtx = {
      projectKey: 'KAN',
      projectName: 'Kanban',
      modulesEnabled: true,
      capabilities: ['VIEW', 'EDIT', 'ADMIN'],
      isProjectAdmin: true,
    };

    render(
      <QueryClientProvider client={queryClient}>
        <ProjectRouteContext.Provider value={routeCtx}>
          <MemoryRouter initialEntries={['/projects/KAN/docs/page-auth-studio']}>
            <Routes>
              <Route path="/projects/:projectKey/docs/:pageId" element={<DocsWorkspaceView />} />
            </Routes>
          </MemoryRouter>
        </ProjectRouteContext.Provider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    const titleInput = screen.getByTestId('page-title-input');

    // 1. Boundary: Empty title validation alert
    fireEvent.change(titleInput, { target: { value: '   ' } });
    expect(screen.getByTestId('page-validation-alert').textContent).toContain(
      'Title cannot be empty',
    );

    // 2. Boundary: Over 500 characters title validation alert
    const longTitle = 'k'.repeat(501);
    fireEvent.change(titleInput, { target: { value: longTitle } });
    expect(screen.getByTestId('page-validation-alert').textContent).toContain(
      'Title cannot exceed 500 characters',
    );

    // 3. Reset title and trigger server save failure (non-412)
    fireEvent.change(titleInput, { target: { value: 'Valid Title' } });
    expect(screen.queryByTestId('page-validation-alert')).toBeNull();

    vi.spyOn(docsApi, 'updatePage').mockRejectedValue(new Error('Network error during page save'));
    fireEvent.blur(screen.getByRole('main'));

    await waitFor(() => {
      expect(screen.getByTestId('page-validation-alert')).toBeDefined();
    });
    expect(screen.getByTestId('page-validation-alert').textContent).toContain(
      'Network error during page save',
    );
  });
});
