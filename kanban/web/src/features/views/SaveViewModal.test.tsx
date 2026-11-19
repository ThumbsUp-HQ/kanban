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

    const form = screen.getByRole('dialog').querySelector('form')!;
    fireEvent.submit(form);

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
          body: expect.objectContaining({
            name: 'My Custom Board',
            description_markdown: 'High priority bugs',
            layout: 'board',
            group_by: 'priority',
            sub_group_by: 'state',
            is_shared: true,
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
    let resolvePromise: (val: unknown) => void = () => {};
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
    fireEvent.submit(screen.getByRole('dialog').querySelector('form')!);

    await waitFor(() => {
      expect(screen.getByTestId('save-view-submit-btn').textContent).toBe('Saving...');
    });
    resolvePromise({ id: 'v-new' });
    await waitFor(() => {
      expect(defaultProps.onSaved).toHaveBeenCalled();
    });
  });
});
