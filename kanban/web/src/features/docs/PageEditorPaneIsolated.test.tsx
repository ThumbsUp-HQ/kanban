import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as docsApi from './docsApi';
import { ApiProblem } from '../../api/problem';

vi.mock('../../editor/MarkdownEditor', () => ({
  MarkdownEditor: ({
    onChange,
    onBlur,
  }: {
    onChange?: (val: string) => void;
    onBlur?: () => void;
  }) => (
    <div data-testid="mock-markdown-editor">
      <button
        data-testid="mock-md-change-btn"
        onClick={() => {
          onChange?.('New Markdown Content');
        }}
      />
      <button data-testid="mock-md-blur-btn" onClick={onBlur} />
    </div>
  ),
}));

import { PageEditorPane } from './PageEditorPane';

describe('PageEditorPaneIsolated', () => {
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

  it('renders loading state when page query is pending', () => {
    vi.spyOn(docsApi, 'fetchPage').mockReturnValue(new Promise(() => {
      // Intentionally pending forever to test loading state
    }));

    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane pageId="page-test" projectKey="KAN" />
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('page-loading')).toBeDefined();
    expect(screen.getByTestId('page-loading').textContent).toContain('Loading page...');
  });

  it('handles markdown change, shortcut save with active debounce, and blur save', async () => {
    vi.spyOn(docsApi, 'fetchPage').mockResolvedValue({
      id: 'page-test',
      canonical_key: 'docs/test',
      doc_id: 'doc-1',
      parent_page_id: null,
      workspace_id: 'ws-1',
      title: 'Initial Title',
      body_markdown: 'Initial Markdown',
      body_sha256: 'hash-initial',
      hierarchy_path: 'docs.test',
      version_seq: 1,
      sort_rank: '0|hzzzzz:',
      breadcrumbs: [],
      outline: [],
      access_manifest: {},
      capabilities: ['VIEW', 'EDIT'],
    });

    const updateSpy = vi.spyOn(docsApi, 'updatePage').mockResolvedValue({
      id: 'page-test',
      canonical_key: 'docs/test',
      doc_id: 'doc-1',
      parent_page_id: null,
      workspace_id: 'ws-1',
      title: 'Initial Title',
      body_markdown: 'New Markdown Content',
      body_sha256: 'hash-updated',
      hierarchy_path: 'docs.test',
      version_seq: 2,
      sort_rank: '0|hzzzzz:',
      breadcrumbs: [],
      outline: [],
      access_manifest: {},
      capabilities: ['VIEW', 'EDIT'],
    });

    const onMarkdownChange = vi.fn();

    render(
      <QueryClientProvider client={queryClient}>
        <PageEditorPane
          pageId="page-test"
          projectKey="KAN"
          onMarkdownChange={onMarkdownChange}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mock-md-change-btn')).toBeDefined();
    });

    // Trigger markdown change
    fireEvent.click(screen.getByTestId('mock-md-change-btn'));
    expect(onMarkdownChange).toHaveBeenCalledWith('New Markdown Content');

    // Press Cmd+S while debounce is active
    fireEvent.keyDown(window, { key: 's', metaKey: true });

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalled();
    });

    // Trigger another change and blur save
    fireEvent.click(screen.getByTestId('mock-md-change-btn'));
    fireEvent.click(screen.getByTestId('mock-md-blur-btn'));
  });

  it('handles copy draft timeout and clipboard rejection fallback', async () => {
    vi.spyOn(docsApi, 'fetchPage').mockResolvedValue({
      id: 'page-test',
      canonical_key: 'docs/test',
      doc_id: 'doc-1',
      parent_page_id: null,
      workspace_id: 'ws-1',
      title: 'Initial Title',
      body_markdown: 'Initial Markdown',
      body_sha256: 'hash-initial',
      hierarchy_path: 'docs.test',
      version_seq: 1,
      sort_rank: '0|hzzzzz:',
      breadcrumbs: [],
      outline: [],
      access_manifest: {},
      capabilities: ['VIEW', 'EDIT'],
    });

    // 412 Conflict
    const problem = new ApiProblem(412, {
      code: 'PRECONDITION_FAILED',
      detail: 'ETag mismatch',
      current_version_seq: 5,
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
        <PageEditorPane pageId="page-test" projectKey="KAN" />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('page-title-input')).toBeDefined();
    });

    // Cause save conflict
    fireEvent.change(screen.getByTestId('page-title-input'), {
      target: { value: 'Conflict Trigger' },
    });
    fireEvent.blur(screen.getByRole('main'));

    await waitFor(() => {
      expect(screen.getByTestId('copy-my-draft-btn')).toBeDefined();
    });

    // Click copy draft
    fireEvent.click(screen.getByTestId('copy-my-draft-btn'));
    await new Promise((r) => setTimeout(r, 2100));

    // Test clipboard error catch fallback
    writeTextSpy.mockRejectedValueOnce(new Error('Clipboard blocked'));
    fireEvent.click(screen.getByTestId('copy-my-draft-btn'));
  });
});
