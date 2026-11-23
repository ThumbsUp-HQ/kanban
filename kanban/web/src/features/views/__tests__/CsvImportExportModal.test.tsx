import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CsvImportExportModal } from '../CsvImportExportModal';

describe('CsvImportExportModal (KAN-316)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    projectKey: 'TESTPROJ',
    workspaceScope: 'test-ws',
    activeFilters: {
      state: ['todo', 'in_progress'],
      priority: ['high'],
    },
    searchQuery: 'backend',
    initialTab: 'export' as const,
    onImportSuccess: vi.fn(),
  };

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <CsvImportExportModal {...defaultProps} isOpen={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders export tab with format selection and submit button', () => {
    render(<CsvImportExportModal {...defaultProps} />);

    expect(screen.getByTestId('csv-import-export-modal')).toBeDefined();
    expect(screen.getByTestId('csv-modal-tab-export')).toBeDefined();
    expect(screen.getByTestId('csv-modal-tab-import')).toBeDefined();
    expect(screen.getByTestId('export-format-csv')).toBeDefined();
    expect(screen.getByTestId('export-format-zip')).toBeDefined();
    expect(screen.getByTestId('export-submit-btn')).toBeDefined();
  });

  it('switches between export and import tabs', () => {
    render(<CsvImportExportModal {...defaultProps} />);

    const importTab = screen.getByTestId('csv-modal-tab-import');
    fireEvent.click(importTab);

    expect(screen.getByTestId('download-template-btn')).toBeDefined();
    expect(screen.getByTestId('import-file-input')).toBeDefined();
    expect(screen.getByTestId('import-preview-btn')).toBeDefined();

    const exportTab = screen.getByTestId('csv-modal-tab-export');
    fireEvent.click(exportTab);
    expect(screen.getByTestId('export-format-csv')).toBeDefined();
  });

  it('enforces 12-char password validation when WinZip AES-256 ZIP format is chosen', async () => {
    render(<CsvImportExportModal {...defaultProps} />);

    const zipRadio = screen.getByTestId('export-format-zip');
    fireEvent.click(zipRadio);

    const passwordInput = screen.getByTestId('export-zip-password-input');
    const submitBtn = screen.getByTestId('export-submit-btn') as HTMLButtonElement;

    // Initially empty -> disabled
    expect(submitBtn.disabled).toBe(true);

    // Short password (< 12 chars) -> disabled and invalid banner
    fireEvent.change(passwordInput, { target: { value: 'short-pwd' } });
    expect(submitBtn.disabled).toBe(true);
    expect(screen.getByTestId('export-password-validation').textContent).toContain(
      'Password must be at least 12 characters',
    );

    // Valid password (>= 12 chars) -> enabled and valid banner
    fireEvent.change(passwordInput, { target: { value: 'super-secure-long-password-123' } });
    expect(submitBtn.disabled).toBe(false);
    expect(screen.getByTestId('export-password-validation').textContent).toContain(
      'Password meets minimum length',
    );
  });

  it('triggers download template API on button click', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['key,summary\n'], { type: 'text/csv' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    // Mock URL.createObjectURL and revokeObjectURL
    const createObjectURLMock = vi.fn().mockReturnValue('blob:mock-url');
    const revokeObjectURLMock = vi.fn();
    window.URL.createObjectURL = createObjectURLMock;
    window.URL.revokeObjectURL = revokeObjectURLMock;

    render(<CsvImportExportModal {...defaultProps} initialTab="import" />);

    const downloadBtn = screen.getByTestId('download-template-btn');
    fireEvent.click(downloadBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/projects/TESTPROJ/issues/import-template.csv',
        expect.objectContaining({ method: 'GET' }),
      );
    });
  });

  it('renders dry-run preview diff stats and rows on successful preview', async () => {
    const mockDiffReport = {
      total_rows: 2,
      creates_count: 1,
      updates_count: 1,
      error_count: 0,
      items: [
        {
          row_number: 1,
          action: 'create',
          key: null,
          summary: 'New issue summary',
          state: 'Todo',
          priority: 'High',
        },
        {
          row_number: 2,
          action: 'update',
          key: 'TESTPROJ-1',
          summary: 'Updated issue summary',
          state: 'In Progress',
          priority: 'Medium',
        },
      ],
      errors: [],
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockDiffReport,
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<CsvImportExportModal {...defaultProps} initialTab="import" />);

    const fileInput = screen.getByTestId('import-file-input');
    const dummyFile = new File(['key,summary\n'], 'issues.csv', { type: 'text/csv' });
    fireEvent.change(fileInput, { target: { files: [dummyFile] } });

    expect(screen.getByTestId('import-selected-filename')).toBeDefined();

    const previewBtn = screen.getByTestId('import-preview-btn');
    fireEvent.click(previewBtn);

    await waitFor(() => {
      expect(screen.getByTestId('import-preview-table')).toBeDefined();
      expect(screen.getByTestId('import-stat-total').textContent).toBe('2');
      expect(screen.getByTestId('import-stat-creates').textContent).toBe('1');
      expect(screen.getByTestId('import-stat-updates').textContent).toBe('1');
      expect(screen.getByTestId('import-stat-errors').textContent).toBe('0');
      expect(screen.getByText('New issue summary')).toBeDefined();
      expect(screen.getByText('Updated issue summary')).toBeDefined();
    });

    // Confirm button should be enabled now
    const confirmBtn = screen.getByTestId('import-confirm-btn') as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(false);

    // Run Confirm Import
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByTestId('import-success-banner')).toBeDefined();
      expect(screen.getByTestId('import-success-banner').textContent).toContain(
        'Import complete: 1 created, 1 updated.',
      );
      expect(defaultProps.onImportSuccess).toHaveBeenCalled();
    });
  });

  it('decodes governance error message when export is disabled', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'EXPORT_DISABLED_BY_SYSTEM_ADMIN' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<CsvImportExportModal {...defaultProps} />);

    const submitBtn = screen.getByTestId('export-submit-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByTestId('csv-modal-error')).toBeDefined();
      expect(screen.getByTestId('csv-modal-error').textContent).toContain(
        'Export is disabled globally by System Administrator.',
      );
    });
  });
});
