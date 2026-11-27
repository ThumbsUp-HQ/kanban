import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SaveViewModal } from './SaveViewModal';
import * as clientModule from '../../api/client';

vi.mock('../../api/client', () => ({
  apiFetch: vi.fn(),
}));

describe('SaveViewModal (KANBA-221)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.clearAllMocks();
  });

  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    projectKey: 'KAN',
    layout: 'board' as const,
    groupBy: 'priority',
    subGroupBy: 'state',
    activeFilters: {
      stateIds: ['state-1'],
      priorityIds: ['high'],
      assigneeIds: ['user-1'],
      cycleIds: ['cycle-1'],
      moduleIds: ['mod-1'],
      searchQuery: 'bug',
    },
    onSaved: vi.fn(),
  };

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <SaveViewModal {...defaultProps} isOpen={false} />
      </QueryClientProvider>,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders modal dialog with form controls when open', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SaveViewModal {...defaultProps} />
      </QueryClientProvider>,
    );

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Save as view' })).toBeDefined();
    expect(screen.getByTestId('save-view-name-input')).toBeDefined();
    expect(screen.getByTestId('save-view-desc-input')).toBeDefined();
    expect(screen.getByTestId('save-view-shared-checkbox')).toBeDefined();
    expect(screen.getByText('Layout: board')).toBeDefined();
    expect(screen.getByText('Group: priority')).toBeDefined();
  });

  it('validates empty name on submit', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SaveViewModal {...defaultProps} />
      </QueryClientProvider>,
    );

    const form = screen.getByRole('dialog').querySelector('form');
    if (form) fireEvent.submit(form);

    expect(await screen.findByRole('alert')).toBeDefined();
    expect(screen.getByRole('alert').textContent).toContain('View name is required');
  });

  it('successfully submits view creation and calls onSaved and onClose', async () => {
    const apiFetchMock = vi.mocked(clientModule.apiFetch);
    apiFetchMock.mockResolvedValueOnce({ id: 'view-123' });

    render(
      <QueryClientProvider client={queryClient}>
        <SaveViewModal {...defaultProps} />
      </QueryClientProvider>,
    );

    const nameInput = screen.getByTestId('save-view-name-input');
    const descInput = screen.getByTestId('save-view-desc-input');
    const shareCheckbox = screen.getByTestId('save-view-shared-checkbox');

    fireEvent.change(nameInput, { target: { value: 'My Custom Board' } });
    fireEvent.change(descInput, { target: { value: 'High priority bugs' } });
    fireEvent.click(shareCheckbox);

    const submitBtn = screen.getByRole('button', { name: 'Save view' });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(
        'POST',
        '/api/v1/projects/KAN/views',
        {
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
          body: expect.objectContaining({
            name: 'My Custom Board',
            description_markdown: 'High priority bugs',
            layout: 'board',
            group_by: 'priority',
            sub_group_by: 'state',
            is_shared: true,
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
            filters: expect.objectContaining({
              state_ids: ['state-1'],
              priority_ids: ['high'],
              search_query: 'bug',
            }),
          }),
        },
      );
    });

    await waitFor(() => {
      expect(defaultProps.onSaved).toHaveBeenCalledWith('view-123');
      expect(defaultProps.onClose).toHaveBeenCalled();
    });
  });

  it('displays API error if mutation fails', async () => {
    const apiFetchMock = vi.mocked(clientModule.apiFetch);
    apiFetchMock.mockRejectedValueOnce(new Error('Name already taken'));

    render(
      <QueryClientProvider client={queryClient}>
        <SaveViewModal {...defaultProps} />
      </QueryClientProvider>,
    );

    const nameInput = screen.getByTestId('save-view-name-input');
    fireEvent.change(nameInput, { target: { value: 'Duplicate View' } });

    const submitBtn = screen.getByRole('button', { name: 'Save view' });
    fireEvent.click(submitBtn);

    expect(await screen.findByRole('alert')).toBeDefined();
    expect(screen.getByRole('alert').textContent).toContain('Name already taken');
  });

  it('closes modal on cancel button or backdrop click', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SaveViewModal {...defaultProps} />
      </QueryClientProvider>,
    );

    const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
    fireEvent.click(cancelBtn);
    expect(defaultProps.onClose).toHaveBeenCalled();

    const backdrop = screen.getByTestId('save-view-modal-backdrop');
    fireEvent.click(backdrop);
    expect(defaultProps.onClose).toHaveBeenCalledTimes(2);
  });

  it('displays saving state while mutation is pending', async () => {
    let resolvePromise: ((val: unknown) => void) | undefined;
    vi.mocked(clientModule.apiFetch).mockReturnValue(
      new Promise((resolve) => {
        resolvePromise = resolve;
      }),
    );
    render(
      <QueryClientProvider client={queryClient}>
        <SaveViewModal {...defaultProps} />
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByTestId('save-view-name-input'), {
      target: { value: 'My View' },
    });
    const form = screen.getByRole('dialog').querySelector('form');
    if (form) fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByTestId('save-view-submit-btn').textContent).toBe('Saving...');
    });
    resolvePromise?.({ id: 'v-new' });
    await waitFor(() => {
      expect(defaultProps.onSaved).toHaveBeenCalled();
    });
  });

  describe('KAN-482: StudioDocLink, FieldHelpHint, Escape/Backdrop Yielding, and Touch Invariants', () => {
    it('renders StudioDocLink in kb-save-view-header with required props', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal {...defaultProps} />
        </QueryClientProvider>,
      );

      const header = screen.getByRole('dialog').querySelector('.kb-save-view-header');
      expect(header).toBeDefined();

      const docLink = screen.getByTestId('save-view-doc-link');
      expect(docLink).toBeDefined();
      expect(docLink.getAttribute('href')).toBe(
        '/docs/enterprise-whitespace-and-kanban-board#saved-views',
      );
      expect(docLink.textContent).toContain('Saved Views Guide ->');
      expect(header?.contains(docLink)).toBe(true);
    });

    it('renders FieldHelpHint as a sibling to label in kb-save-view-shared-row (HTML 4.10.4)', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal {...defaultProps} />
        </QueryClientProvider>,
      );

      const sharedRow = screen.getByRole('dialog').querySelector('.kb-save-view-shared-row');
      expect(sharedRow).toBeDefined();

      const label = sharedRow?.querySelector('.kb-save-view-checkbox-label');
      expect(label).toBeDefined();
      expect(label?.textContent).toContain('Share view with workspace collaborators');

      const helpHint = screen.getByTestId('save-view-shared-help');
      expect(helpHint).toBeDefined();

      // STRICT HTML 4.10.4: FieldHelpHint must be sibling, never nested inside <label>
      expect(label?.contains(helpHint)).toBe(false);
      expect(sharedRow?.contains(helpHint)).toBe(true);
      expect(label).not.toBeNull();
      if (label && sharedRow) {
        expect(sharedRow.contains(label)).toBe(true);
      }
    });

    it('displays FieldHelpHint details on focus/click including default value and doc link', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal {...defaultProps} />
        </QueryClientProvider>,
      );

      const trigger = screen.getByTestId('save-view-shared-help');
      fireEvent.click(trigger);

      const popover = await screen.findByTestId('save-view-shared-help-popover');
      expect(popover).toBeDefined();
      expect(popover.textContent).toContain('View Visibility');
      expect(popover.textContent).toContain('Default:');
      expect(popover.textContent).toContain('Off (Private to you)');
      expect(popover.textContent).toContain('Off');
      expect(popover.textContent).toContain('On');

      const docLink = screen.getByTestId('save-view-shared-help-doc-link');
      expect(docLink.getAttribute('href')).toBe(
        '/docs/enterprise-whitespace-and-kanban-board#saved-views',
      );
    });

    it('handles Escape key to close modal when no popovers or help drawer are open', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal {...defaultProps} />
        </QueryClientProvider>,
      );

      fireEvent.keyDown(window, { key: 'Escape' });
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    });

    it('yields Escape key without closing modal when kb-help-drawer is open', () => {
      const drawer = document.createElement('div');
      drawer.className = 'kb-help-drawer';
      document.body.appendChild(drawer);

      try {
        render(
          <QueryClientProvider client={queryClient}>
            <SaveViewModal {...defaultProps} />
          </QueryClientProvider>,
        );

        fireEvent.keyDown(window, { key: 'Escape' });
        expect(defaultProps.onClose).not.toHaveBeenCalled();
      } finally {
        drawer.remove();
      }
    });

    it('yields Escape key without closing modal when field-help-hint-popover is open', () => {
      const popover = document.createElement('div');
      popover.className = 'field-help-hint-popover';
      document.body.appendChild(popover);

      try {
        render(
          <QueryClientProvider client={queryClient}>
            <SaveViewModal {...defaultProps} />
          </QueryClientProvider>,
        );

        fireEvent.keyDown(window, { key: 'Escape' });
        expect(defaultProps.onClose).not.toHaveBeenCalled();
      } finally {
        popover.remove();
      }
    });

    it('yields backdrop click without closing modal when kb-help-drawer is open', () => {
      const drawer = document.createElement('div');
      drawer.className = 'kb-help-drawer';
      document.body.appendChild(drawer);

      try {
        render(
          <QueryClientProvider client={queryClient}>
            <SaveViewModal {...defaultProps} />
          </QueryClientProvider>,
        );

        const backdrop = screen.getByTestId('save-view-modal-backdrop');
        fireEvent.click(backdrop);
        expect(defaultProps.onClose).not.toHaveBeenCalled();
      } finally {
        drawer.remove();
      }
    });

    it('yields backdrop click without closing modal when field-help-hint-popover is open', () => {
      const popover = document.createElement('div');
      popover.className = 'field-help-hint-popover';
      document.body.appendChild(popover);

      try {
        render(
          <QueryClientProvider client={queryClient}>
            <SaveViewModal {...defaultProps} />
          </QueryClientProvider>,
        );

        const backdrop = screen.getByTestId('save-view-modal-backdrop');
        fireEvent.click(backdrop);
        expect(defaultProps.onClose).not.toHaveBeenCalled();
      } finally {
        popover.remove();
      }
    });

    it('does not close modal when clicking inside modal dialog content', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal {...defaultProps} />
        </QueryClientProvider>,
      );

      const dialog = screen.getByTestId('save-view-modal');
      fireEvent.click(dialog);
      expect(defaultProps.onClose).not.toHaveBeenCalled();
    });

    it('resets form fields and error when modal transitions from closed to open', () => {
      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal {...defaultProps} isOpen={false} />
        </QueryClientProvider>,
      );

      rerender(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal {...defaultProps} isOpen={true} />
        </QueryClientProvider>,
      );

      const nameInput = screen.getByTestId('save-view-name-input');
      expect(nameInput).toHaveProperty('value', '');
      const sharedCheck = screen.getByTestId('save-view-shared-checkbox');
      expect(sharedCheck).toHaveProperty('checked', false);
    });

    it('clears error on name input typing and handles string error in mutation', async () => {
      const apiFetchMock = vi.mocked(clientModule.apiFetch);
      apiFetchMock.mockRejectedValueOnce('Non-error string failure');

      render(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal {...defaultProps} />
        </QueryClientProvider>,
      );

      const form = screen.getByRole('dialog').querySelector('form');
      if (form) fireEvent.submit(form);

      const alert = await screen.findByRole('alert');
      expect(alert.textContent).toBe('View name is required');

      // Typing clears error
      const nameInput = screen.getByTestId('save-view-name-input');
      fireEvent.change(nameInput, { target: { value: 'Valid Name' } });
      expect(screen.queryByRole('alert')).toBeNull();

      // Submit again to trigger non-error rejection
      if (form) fireEvent.submit(form);
      const alert2 = await screen.findByRole('alert');
      expect(alert2.textContent).toBe('Failed to save view');
    });

    it('handles none grouping and empty search query in mutation payload', async () => {
      const apiFetchMock = vi.mocked(clientModule.apiFetch);
      apiFetchMock.mockResolvedValueOnce({ id: 'view-none' });

      render(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal
            {...defaultProps}
            groupBy="none"
            subGroupBy="none"
            activeFilters={{ ...defaultProps.activeFilters, searchQuery: null }}
          />
        </QueryClientProvider>,
      );

      const nameInput = screen.getByTestId('save-view-name-input');
      fireEvent.change(nameInput, { target: { value: 'Plain Board' } });

      const form = screen.getByRole('dialog').querySelector('form');
      if (form) fireEvent.submit(form);

      await waitFor(() => {
        expect(apiFetchMock).toHaveBeenCalledWith(
          'POST',
          '/api/v1/projects/KAN/views',
          {
            // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
            body: expect.objectContaining({
              name: 'Plain Board',
              group_by: null,
              sub_group_by: null,
              // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
              filters: expect.objectContaining({
                search_query: null,
              }),
            }),
          },
        );
      });
    });

    it('verifies close button glyph is ✕ and accessible label is Close', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <SaveViewModal {...defaultProps} />
        </QueryClientProvider>,
      );

      const closeBtn = screen.getByRole('button', { name: 'Close' });
      expect(closeBtn).toBeDefined();
      expect(closeBtn.textContent.trim()).toBe('✕');
    });
  });
});
