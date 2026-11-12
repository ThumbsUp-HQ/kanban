import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LinkGraphAction } from './LinkGraphAction';
import * as actionsApi from './actionsApi';
import * as RealtimeStatusModule from '../../api/RealtimeStatus';
import type { IssueDetail } from '../drawer/slots';

const mockIssue: IssueDetail = {
  key: 'KAN-142',
  object_id: '018f0000-0000-7000-8000-000000000001',
  project_key: 'KAN',
  project_name: 'Kanban Platform',
  summary: 'Harden OAuth and MCP token security',
};

function renderComponent(issue = mockIssue) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <LinkGraphAction issue={issue} />
    </QueryClientProvider>,
  );
}

describe('LinkGraphAction (KB-P3-43, S7.2 8m)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('triggers Markdown link copy on Ctrl+Shift+C shortcut and announces', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [],
      inbound: [],
    });

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    const announceSpy = vi.spyOn(RealtimeStatusModule, 'announce');

    renderComponent();

    // Wait for canonical query to resolve
    await waitFor(() => {
      expect(actionsApi.fetchCanonicalUrl).toHaveBeenCalledWith('KAN-142');
    });

    // Trigger Ctrl+Shift+C
    fireEvent.keyDown(window, {
      key: 'c',
      ctrlKey: true,
      shiftKey: true,
    });

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith(
        '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
      );
      expect(announceSpy).toHaveBeenCalledWith('Copied [KAN-142](...) to clipboard');
    });
  });

  it('renders masked restricted target (🔒) with zero links or keys', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [
        {
          id: 'link-out-1',
          link_type: 'BLOCKS',
          link_state: 'ACTIVE',
          target: { restricted: true, label: '🔒 Restricted Object' },
        },
      ],
      inbound: [
        {
          id: 'link-in-1',
          link_type: 'BLOCKED_BY',
          link_state: 'ACTIVE',
          source: { restricted: true, label: '🔒 Restricted Object' },
        },
      ],
    });

    renderComponent();

    // Open popover
    fireEvent.click(screen.getByTestId('link-graph-trigger'));

    await waitFor(() => {
      const restrictedLabels = screen.getAllByText('Restricted Object');
      expect(restrictedLabels.length).toBe(2);
    });

    // Zero link hrefs to restricted targets
    const links = screen.queryAllByRole('link');
    expect(links.length).toBe(0);
  });

  it('renders FLAGGED_INVALID link with brokenLink emoji hint (🕸️⚠️)', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [
        {
          id: 'link-broken-1',
          link_type: 'RELATES_TO',
          link_state: 'FLAGGED_INVALID',
          target: {
            id: 'obj-2',
            type: 'issue',
            key: 'KAN-99',
            title: 'Subscribed issue',
          },
        },
      ],
      inbound: [],
    });

    renderComponent();

    fireEvent.click(screen.getByTestId('link-graph-trigger'));

    await waitFor(() => {
      expect(screen.getByText('KAN-99')).toBeDefined();
      expect(screen.getByText('Subscribed issue')).toBeDefined();
      expect(screen.getAllByText('RELATES_TO').length).toBeGreaterThan(0);
    });
  });

  it('select dropdown only contains the 6 user-creatable kinds and never PROMOTED_TO_DOC', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [],
      inbound: [],
    });

    renderComponent();
    fireEvent.click(screen.getByTestId('link-graph-trigger'));

    await screen.findByTestId('link-type-select');
    const select = screen.getByTestId<HTMLSelectElement>('link-type-select');
    const options = Array.from(select.options).map((o) => o.value);

    expect(options).toEqual([
      'BLOCKS',
      'BLOCKED_BY',
      'RELATES_TO',
      'DUPLICATES',
      'VERIFIED_BY_DOC',
      'DERIVED_FROM_STICKY',
    ]);
    expect(options).not.toContain('PROMOTED_TO_DOC');
  });

  it('submits new link creation and deletes outbound link', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [
        {
          id: 'link-del-1',
          link_type: 'BLOCKS',
          link_state: 'ACTIVE',
          target: { id: 'obj-3', type: 'issue', key: 'KAN-7', title: 'Dependency task' },
        },
      ],
      inbound: [],
    });

    const createSpy = vi.spyOn(actionsApi, 'createObjectLink').mockResolvedValue({
      id: 'link-new-1',
      link_type: 'BLOCKS',
      link_state: 'ACTIVE',
      target: { id: 'obj-4', type: 'issue', key: 'KAN-8', title: 'Target' },
    });
    const deleteSpy = vi.spyOn(actionsApi, 'deleteObjectLink').mockResolvedValue(undefined);

    renderComponent();
    fireEvent.click(screen.getByTestId('link-graph-trigger'));

    // Test delete link
    const deleteBtn = await screen.findByTestId('delete-link-link-del-1');
    fireEvent.click(deleteBtn);
    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('link-del-1');
    });

    // Test add link
    const targetInput = screen.getByTestId('link-target-input');
    fireEvent.change(targetInput, { target: { value: 'KAN-8' } });

    const submitBtn = screen.getByTestId('add-link-submit-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith('KAN-142', 'KAN-8', 'RELATES_TO');
    });
  });

  it('renders hostile script title as safe literal text without execution', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [
        {
          id: 'link-xss-1',
          link_type: 'RELATES_TO',
          link_state: 'ACTIVE',
          target: {
            id: 'obj-evil',
            type: 'issue',
            key: 'KAN-666',
            title: '<script>alert(1)</script>',
          },
        },
      ],
      inbound: [],
    });

    renderComponent();
    fireEvent.click(screen.getByTestId('link-graph-trigger'));

    await waitFor(() => {
      const titleEl = screen.getByText('<script>alert(1)</script>');
      expect(titleEl).toBeDefined();
      expect(document.querySelectorAll('script').length).toBe(0);
    });
  });

  it('clicking copy buttons in popover copies URL and Markdown link to clipboard and announces', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [],
      inbound: [],
    });

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    const announceSpy = vi.spyOn(RealtimeStatusModule, 'announce');

    renderComponent();
    fireEvent.click(screen.getByTestId('link-graph-trigger'));

    const copyUrlBtn = await screen.findByTestId('copy-canonical-url-btn');
    fireEvent.click(copyUrlBtn);

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith(
        'https://kanban.example/projects/KAN/issues/KAN-142',
      );
      expect(announceSpy).toHaveBeenCalledWith('Copied URL to clipboard');
    });

    const copyMdBtn = screen.getByTestId('copy-markdown-btn');
    fireEvent.click(copyMdBtn);

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith(
        '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
      );
      expect(announceSpy).toHaveBeenCalledWith('Copied [KAN-142](...) to clipboard');
    });
  });

  it('displays error message when add link fails', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [],
      inbound: [],
    });
    vi.spyOn(actionsApi, 'createObjectLink').mockRejectedValue({
      detail: 'Cannot create cycle in dependency graph',
    });

    renderComponent();
    fireEvent.click(screen.getByTestId('link-graph-trigger'));

    const targetInput = await screen.findByTestId('link-target-input');
    fireEvent.change(targetInput, { target: { value: 'KAN-99' } });

    const submitBtn = screen.getByTestId('add-link-submit-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('Cannot create cycle in dependency graph')).toBeDefined();
    });
  });

  it('closes popover on Escape or clicking outside', () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [],
      inbound: [],
    });

    renderComponent();
    fireEvent.click(screen.getByTestId('link-graph-trigger'));
    expect(screen.getByTestId('link-graph-popover')).toBeDefined();

    // Non-escape key leaves popover open
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(screen.getByTestId('link-graph-popover')).toBeDefined();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('link-graph-popover')).toBeNull();

    fireEvent.click(screen.getByTestId('link-graph-trigger'));
    expect(screen.getByTestId('link-graph-popover')).toBeDefined();

    // Mousedown inside container does not close
    fireEvent.mouseDown(screen.getByTestId('link-graph-popover'));
    expect(screen.getByTestId('link-graph-popover')).toBeDefined();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId('link-graph-popover')).toBeNull();
  });

  it('select dropdown onChange updates link type', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [],
      inbound: [],
    });

    renderComponent();
    fireEvent.click(screen.getByTestId('link-graph-trigger'));

    const select = await screen.findByTestId('link-type-select');
    fireEvent.change(select, { target: { value: 'BLOCKS' } });
    expect((select as HTMLSelectElement).value).toBe('BLOCKS');
  });

  it('handles empty targetRef submit, message error fallback, and string error fallback', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [],
      inbound: [],
    });
    const addSpy = vi.spyOn(actionsApi, 'createObjectLink').mockRejectedValue({
      message: 'Network link error',
    });

    renderComponent();
    fireEvent.click(screen.getByTestId('link-graph-trigger'));

    const targetInput = await screen.findByTestId('link-target-input');
    const form = targetInput.closest('form');
    expect(form).not.toBeNull();
    if (!form) return;

    // Submit with empty target
    fireEvent.submit(form);
    expect(addSpy).not.toHaveBeenCalled();

    // Submit with value that rejects with message
    fireEvent.change(targetInput, { target: { value: 'KAN-50' } });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Network link error')).toBeDefined();
    });

    // Rejection with object lacking detail and message
    addSpy.mockRejectedValueOnce({ status: 500 });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Failed to add link')).toBeDefined();
    });

    // Rejection with primitive string
    addSpy.mockRejectedValueOnce('Simple string rejection');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText('Failed to add link')).toBeDefined();
    });
  });

  it('ignores Cmd+Shift+C when active element is an input and handles metaKey', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/projects/KAN/issues/KAN-142',
      markdown: '[KAN-142](https://kanban.example/projects/KAN/issues/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [],
      inbound: [],
    });

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    renderComponent();

    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    // Trigger Cmd+Shift+C while input is active - should be ignored
    fireEvent.keyDown(window, {
      key: 'C',
      metaKey: true,
      shiftKey: true,
    });
    expect(writeTextMock).not.toHaveBeenCalled();

    // Blur input
    input.blur();

    // Trigger Cmd+Shift+C when active element is not editable - should execute
    fireEvent.keyDown(window, {
      key: 'C',
      metaKey: true,
      shiftKey: true,
    });

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalled();
    });

    document.body.removeChild(input);
  });

  it('renders normal unrestricted inbound links and copies when canonical is empty', async () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({ url: '', markdown: '' });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
      outbound: [
        {
          id: 'out-1',
          link_type: 'RELATES_TO',
          link_state: 'ACTIVE',
          target: { id: 'obj-20', type: 'issue', key: 'KAN-20', title: 'Target 20' },
        },
      ],
      inbound: [
        {
          id: 'in-1',
          link_type: 'BLOCKS',
          link_state: 'FLAGGED_INVALID',
          source: { id: 'obj-10', type: 'issue', key: 'KAN-10', title: 'Source 10' },
        },
      ],
    });

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    renderComponent();
    fireEvent.click(screen.getByTestId('link-graph-trigger'));

    // Check normal inbound link
    expect(await screen.findByText('Source 10')).toBeDefined();
    expect(screen.getByText('KAN-10')).toBeDefined();

    // Trigger copy markdown with empty canonical fallback
    fireEvent.click(screen.getByTestId('copy-markdown-btn'));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith('[KAN-142]()');
    });

    // Trigger copy URL with empty url
    fireEvent.click(screen.getByTestId('copy-canonical-url-btn'));
  });

  it('tests textarea, select, contenteditable, and missing clipboard in shortcut handler', () => {
    vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
      url: 'https://kanban.example/KAN-142',
      markdown: '[KAN-142](https://kanban.example/KAN-142)',
    });
    vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({ outbound: [], inbound: [] });

    renderComponent();

    // Textarea
    const textarea = document.createElement('textarea');
    document.body.appendChild(textarea);
    textarea.focus();
    fireEvent.keyDown(window, { key: 'c', ctrlKey: true, shiftKey: true });
    document.body.removeChild(textarea);

    // Select
    const select = document.createElement('select');
    document.body.appendChild(select);
    select.focus();
    fireEvent.keyDown(window, { key: 'c', ctrlKey: true, shiftKey: true });
    document.body.removeChild(select);

    // ContentEditable
    const div = document.createElement('div');
    div.contentEditable = 'true';
    document.body.appendChild(div);
    div.focus();
    fireEvent.keyDown(window, { key: 'c', ctrlKey: true, shiftKey: true });
    document.body.removeChild(div);

    // Without clipboard writeText
    const originalClipboard = navigator.clipboard;
    Object.assign(navigator, { clipboard: null });
    fireEvent.keyDown(window, { key: 'c', ctrlKey: true, shiftKey: true });
    Object.assign(navigator, { clipboard: originalClipboard });
  });
});
