import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { registerShellPanel, ShellPanelsProvider } from '../../app/shellPanels';
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
    const restrictedLinks = screen.queryAllByRole('link').filter((l) => l.getAttribute('data-testid') !== 'link-graph-doc-link');
    expect(restrictedLinks.length).toBe(0);
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

  describe('StudioDocLink Header Integration and HelpDrawer Invariants (KAN-492)', () => {
    it('renders StudioDocLink in popover header with required attributes and styling', () => {
      vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
        url: 'https://kanban.example/KAN-142',
        markdown: '[KAN-142](https://kanban.example/KAN-142)',
      });
      vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({ outbound: [], inbound: [] });

      renderComponent();
      fireEvent.click(screen.getByTestId('link-graph-trigger'));

      const popover = screen.getByTestId('link-graph-popover');
      expect(popover).toBeDefined();

      const docLink = screen.getByTestId('link-graph-doc-link');
      expect(docLink).toBeDefined();
      expect(docLink.tagName.toLowerCase()).toBe('a');
      expect(docLink.getAttribute('href')).toBe('/docs/universal-object-graph-and-link-auditor');
      expect(docLink.getAttribute('aria-label')).toBe('Object Graph Guide ->');
      expect(docLink.textContent).toContain('Object Graph Guide ->');

      // Verify header structure and title
      const header = popover.querySelector('.link-graph-header');
      expect(header).toBeDefined();
      expect(header?.textContent).toContain('Object Graph');
      expect(header?.contains(docLink)).toBe(true);
    });

    it('opens HelpDrawer when StudioDocLink is clicked inside ShellPanelsProvider without closing popover', async () => {
      vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
        url: 'https://kanban.example/KAN-142',
        markdown: '[KAN-142](https://kanban.example/KAN-142)',
      });
      vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({ outbound: [], inbound: [] });

      const DummyHelpDrawer = ({ arg }: { arg?: unknown }) => {
        const data = arg as { href?: string; title?: string } | undefined;
        return (
          <div className="kb-help-drawer" data-testid="dummy-help-drawer" data-href={data?.href} data-title={data?.title}>
            Help Content for {data?.title} ({data?.href})
          </div>
        );
      };
      const unregister = registerShellPanel('help', DummyHelpDrawer);

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      });

      render(
        <QueryClientProvider client={queryClient}>
          <ShellPanelsProvider>
            <LinkGraphAction issue={mockIssue} />
          </ShellPanelsProvider>
        </QueryClientProvider>,
      );

      fireEvent.click(screen.getByTestId('link-graph-trigger'));
      expect(screen.getByTestId('link-graph-popover')).toBeDefined();

      const docLink = screen.getByTestId('link-graph-doc-link');
      fireEvent.click(docLink);

      // Verify HelpDrawer opened
      await waitFor(() => {
        expect(screen.getByTestId('dummy-help-drawer')).toBeDefined();
      });
      const drawer = screen.getByTestId('dummy-help-drawer');
      expect(drawer.getAttribute('data-href')).toBe('/docs/universal-object-graph-and-link-auditor');
      expect(drawer.getAttribute('data-title')).toBe('Object Graph Guide ->');

      // Verify popover remains open
      expect(screen.getByTestId('link-graph-popover')).toBeDefined();

      unregister();
    });

    it('coordinates Escape and outside click events when HelpDrawer is active', () => {
      vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
        url: 'https://kanban.example/KAN-142',
        markdown: '[KAN-142](https://kanban.example/KAN-142)',
      });
      vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({ outbound: [], inbound: [] });

      renderComponent();
      fireEvent.click(screen.getByTestId('link-graph-trigger'));
      expect(screen.getByTestId('link-graph-popover')).toBeDefined();

      // Create dummy help drawer and backdrop elements in document
      const backdrop = document.createElement('div');
      backdrop.className = 'kb-help-drawer-backdrop';
      const drawer = document.createElement('div');
      drawer.className = 'kb-help-drawer';
      document.body.appendChild(backdrop);
      document.body.appendChild(drawer);

      // Press Escape while HelpDrawer is active - popover must yield and remain open
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(screen.getByTestId('link-graph-popover')).toBeDefined();

      // Click inside drawer or backdrop - popover must yield and remain open
      fireEvent.mouseDown(drawer);
      expect(screen.getByTestId('link-graph-popover')).toBeDefined();
      fireEvent.mouseDown(backdrop);
      expect(screen.getByTestId('link-graph-popover')).toBeDefined();

      // Remove HelpDrawer from DOM
      document.body.removeChild(drawer);
      document.body.removeChild(backdrop);

      // Now Escape closes the popover
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(screen.queryByTestId('link-graph-popover')).toBeNull();
    });

    it('handles read-only issue capabilities without edit or delete controls', async () => {
      vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
        url: 'https://kanban.example/KAN-142',
        markdown: '[KAN-142](https://kanban.example/KAN-142)',
      });
      vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({
        outbound: [
          {
            id: 'link-readonly-1',
            link_type: 'BLOCKS',
            link_state: 'ACTIVE',
            target: { id: 'obj-ro', type: 'issue', key: 'KAN-999', title: 'Target' },
          },
        ],
        inbound: [],
      });

      const readOnlyIssue: IssueDetail = {
        ...mockIssue,
        capabilities: ['VIEW'],
      };

      renderComponent(readOnlyIssue);
      fireEvent.click(screen.getByTestId('link-graph-trigger'));

      await screen.findByText('KAN-999');
      // Add link form is not rendered
      expect(screen.queryByTestId('add-link-submit-btn')).toBeNull();
      // Delete link button is not rendered
      expect(screen.queryByTestId('delete-link-link-readonly-1')).toBeNull();
    });

    it('covers error handling fallbacks and clipboard catch in actions', async () => {
      vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockResolvedValue({
        url: '',
        markdown: '',
      });
      vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({ outbound: [], inbound: [] });
      vi.spyOn(actionsApi, 'createObjectLink').mockRejectedValue({ status: 500 });

      const writeTextMock = vi.fn().mockRejectedValue(new Error('Clipboard blocked'));
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextMock,
        },
      });

      renderComponent();
      fireEvent.click(screen.getByTestId('link-graph-trigger'));

      // Test copy URL when canonical url is empty
      fireEvent.click(screen.getByTestId('copy-canonical-url-btn'));

      // Test clipboard error catch in keyboard shortcut
      fireEvent.keyDown(window, { key: 'c', ctrlKey: true, shiftKey: true });

      // Test add link with generic error fallback
      fireEvent.change(screen.getByTestId('link-target-input'), { target: { value: 'KAN-99' } });
      fireEvent.click(screen.getByTestId('add-link-submit-btn'));

      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe('Failed to add link');
      });
    });

    it('covers null activeElement and undefined canonical markdown copy', () => {
      let pendingResolve: ((val: actionsApi.CanonicalUrlResponse) => void) | null = null;
      vi.spyOn(actionsApi, 'fetchCanonicalUrl').mockReturnValue(
        new Promise<actionsApi.CanonicalUrlResponse>((resolve) => {
          pendingResolve = resolve;
        }),
      );
      vi.spyOn(actionsApi, 'fetchObjectLinks').mockResolvedValue({ outbound: [], inbound: [] });

      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText: writeTextMock } });

      renderComponent();

      // Test activeElement being null
      const origActiveElement =
        Object.getOwnPropertyDescriptor(Document.prototype, 'activeElement') ??
        Object.getOwnPropertyDescriptor(document, 'activeElement');
      Object.defineProperty(document, 'activeElement', {
        value: null,
        configurable: true,
      });
      fireEvent.keyDown(window, { key: 'c', ctrlKey: true, shiftKey: true });
      if (origActiveElement) {
        Object.defineProperty(document, 'activeElement', origActiveElement);
      }

      // Open popover while canonical is still undefined
      fireEvent.click(screen.getByTestId('link-graph-trigger'));
      fireEvent.click(screen.getByTestId('copy-markdown-btn'));
      expect(writeTextMock).toHaveBeenCalledWith('[KAN-142]()');
      expect(pendingResolve).toBeTypeOf('function');
    });
  });
});
