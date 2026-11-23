import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CsvImportExportModal } from '../CsvImportExportModal';
import * as clientModule from '../../../api/client';

describe('CsvImportExportModal (KAN-316)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-url');
    window.URL.revokeObjectURL = vi.fn();
  });

  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    projectKey: 'TESTPROJ',
    workspaceScope: 'test-ws',
    activeFilters: {
      state: ['todo', 'in_progress'],
      priority: ['high'],
      cycle: ['cyc-1'],
      module: ['mod-1'],
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

  it('renders export tab and executes both CSV and AES-256 ZIP exports successfully', async () => {
    vi.spyOn(clientModule, 'getCsrfToken').mockReturnValue('csrf-tok-123');
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(new Blob(['key,summary\n'], { type: 'text/csv' })),
    });
    vi.stubGlobal('fetch', fetchMock);

    const { rerender } = render(<CsvImportExportModal {...defaultProps} />);

    // 1. Standard CSV export
    fireEvent.click(screen.getByTestId('export-submit-btn'));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/projects/TESTPROJ/issues/export',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    // 2. WinZip AES-256 ZIP export on workspace fallback (empty projectKey)
    rerender(<CsvImportExportModal {...defaultProps} projectKey="" />);
    expect(screen.getByText('Password-Protected ZIP (AES-256)')).toBeDefined();
    expect(screen.queryByText(/WinZip/i)).toBeNull();
    fireEvent.click(screen.getByTestId('export-format-zip'));
    fireEvent.change(screen.getByTestId('export-zip-password-input'), {
      target: { value: 'super-secure-long-password-123' },
    });
    fireEvent.click(screen.getByTestId('export-submit-btn'));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/workspaces/test-ws/issues/export',
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  it('supports initialExportFormat prop to pre-select CSV or ZIP format (KAN-374)', () => {
    const { rerender } = render(
      <CsvImportExportModal {...defaultProps} initialExportFormat="zip_csv" />,
    );
    const zipRadio = screen.getByTestId<HTMLInputElement>('export-format-zip');
    expect(zipRadio.checked).toBe(true);

    rerender(<CsvImportExportModal {...defaultProps} initialExportFormat="csv" />);
    const csvRadio = screen.getByTestId<HTMLInputElement>('export-format-csv');
    expect(csvRadio.checked).toBe(true);
  });

  it('switches between export and import tabs and handles template download success and failure', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        blob: () => Promise.resolve(new Blob(['key,summary\n'], { type: 'text/csv' })),
      })
      .mockResolvedValueOnce({
        ok: false,
        text: () => Promise.resolve('IMPORT_DISABLED_BY_WORKSPACE_ADMIN'),
      });
    vi.stubGlobal('fetch', fetchMock);

    const { rerender } = render(<CsvImportExportModal {...defaultProps} />);

    fireEvent.click(screen.getByTestId('csv-modal-tab-import'));
    fireEvent.click(screen.getByTestId('download-template-btn'));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/projects/TESTPROJ/issues/import-template.csv',
        expect.objectContaining({ method: 'GET' }),
      );
    });

    // Workspace-scoped template download failure
    rerender(<CsvImportExportModal {...defaultProps} projectKey="" initialTab="import" />);
    fireEvent.click(screen.getByTestId('download-template-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('csv-modal-error').textContent).toContain(
        'Import is disabled for this workspace by Workspace Administrator.',
      );
    });

    fireEvent.click(screen.getByTestId('csv-modal-tab-export'));
    expect(screen.getByTestId('export-format-csv')).toBeDefined();
  });

  it('renders dry-run preview diff stats, row errors, ZIP password field, and confirms import', async () => {
    vi.spyOn(clientModule, 'getCsrfToken').mockReturnValue('csrf-tok-123');
    const mockDiffReport = {
      total_rows: 2,
      creates_count: 1,
      updates_count: 1,
      error_count: 2,
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
      errors: [
        { row_number: 3, column: 'priority', message: 'Invalid priority' },
        { row_number: 4, column: null, message: 'Malformed row' },
      ],
    };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockDiffReport),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<CsvImportExportModal {...defaultProps} initialTab="import" />);
    expect(
      screen.getByText(
        /Import issues from CSV or password-protected ZIP \(AES-256\) archive/,
      ),
    ).toBeDefined();
    expect(screen.queryByText(/WinZip/i)).toBeNull();

    const fileInput = screen.getByTestId('import-file-input');
    const dropzone = fileInput.parentElement;
    if (dropzone) {
      fireEvent.click(dropzone);
    }
    fireEvent.change(fileInput, { target: { files: [] } });
    const zipFile = new File(['PK\x03\x04'], 'issues.zip', { type: 'application/zip' });
    fireEvent.change(fileInput, { target: { files: [zipFile] } });

    expect(screen.getByTestId('import-selected-filename')).toBeDefined();
    const zipPassInput = screen.getByTestId('import-zip-password-input');
    fireEvent.change(zipPassInput, { target: { value: 'zip-secret-pass-123' } });

    fireEvent.click(screen.getByTestId('import-preview-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('import-preview-table')).toBeDefined();
      expect(screen.getByText(/Invalid priority/)).toBeDefined();
      expect(screen.getByText(/Malformed row/)).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('import-confirm-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('import-success-banner').textContent).toContain(
        'Import complete: 1 created, 1 updated.',
      );
      expect(defaultProps.onImportSuccess).toHaveBeenCalled();
    });
  });

  it('decodes all governance and archive security error codes', async () => {
    const errorCases: [string, string][] = [
      ['EXPORT_DISABLED_BY_SYSTEM_ADMIN', 'Export is disabled globally by System Administrator.'],
      ['EXPORT_DISABLED_BY_WORKSPACE_ADMIN', 'Export is disabled for this workspace by Workspace Administrator.'],
      ['IMPORT_DISABLED_BY_SYSTEM_ADMIN', 'Import is disabled globally by System Administrator.'],
      ['INSUFFICIENT_CAPABILITY', 'You do not have permission to perform this action.'],
      ['PASSWORD_REQUIRED', 'A password is required to decrypt this ZIP archive.'],
      ['INVALID_PASSWORD', 'The provided password is incorrect or file has been tampered with.'],
      ['ZIP_BOMB_DETECTED', 'Archive exceeded compression ratio or decompressed size limit.'],
      ['PATH_TRAVERSAL_DETECTED', 'Archive contains invalid relative path traversal.'],
      ['INVALID_UTF8_SURROGATE', 'File contains invalid UTF-16 surrogates.'],
      ['CUSTOM_BACKEND_ERROR', 'CUSTOM_BACKEND_ERROR'],
    ];

    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    render(<CsvImportExportModal {...defaultProps} />);
    const submitBtn = screen.getByTestId('export-submit-btn');

    for (const [code, expectedText] of errorCases) {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ detail: code }),
      });
      fireEvent.click(submitBtn);
      await waitFor(() => {
        expect(screen.getByTestId('csv-modal-error').textContent).toContain(expectedText);
      });
    }
  });

  it('wires selectedIssueIds and initialExportFormat into export payload (KAN-372)', async () => {
    vi.spyOn(clientModule, 'getCsrfToken').mockReturnValue('csrf-tok-372');
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(new Blob(['key,summary\n'], { type: 'text/csv' })),
    });
    vi.stubGlobal('fetch', fetchMock);

    // 1. Mount with selectedIssueIds and initialExportFormat="csv"
    const { rerender } = render(
      <CsvImportExportModal
        {...defaultProps}
        selectedIssueIds={['ISSUE-42', 'ISSUE-43']}
        initialExportFormat="csv"
      />,
    );

    fireEvent.click(screen.getByTestId('export-submit-btn'));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/projects/TESTPROJ/issues/export',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    const calls = fetchMock.mock.calls as unknown as [string, { body: string }][];
    const firstCallInit = calls[0]?.[1];
    const rawParsed: unknown = JSON.parse(firstCallInit?.body ?? '{}');
    const lastCallBody = rawParsed as {
      issue_ids?: string[];
      format?: string;
      zip_password?: string;
    };
    expect(lastCallBody.issue_ids).toEqual(['ISSUE-42', 'ISSUE-43']);
    expect(lastCallBody.format).toBe('csv');

    // 2. Mount with initialExportFormat="zip_csv"
    fetchMock.mockClear();
    rerender(
      <CsvImportExportModal
        {...defaultProps}
        selectedIssueIds={['ISSUE-99']}
        initialExportFormat="zip_csv"
      />,
    );

    const zipRadio = screen.getByTestId<HTMLInputElement>('export-format-zip');
    expect(zipRadio.checked).toBe(true);

    const passwordInput = screen.getByTestId('export-zip-password-input');
    fireEvent.change(passwordInput, {
      target: { value: 'secure-password-123' },
    });

    fireEvent.click(screen.getByTestId('export-submit-btn'));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/projects/TESTPROJ/issues/export',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    const zipCalls = fetchMock.mock.calls as unknown as [string, { body: string }][];
    const zipCallInit = zipCalls[0]?.[1];
    const rawZipParsed: unknown = JSON.parse(zipCallInit?.body ?? '{}');
    const zipCallBody = rawZipParsed as {
      issue_ids?: string[];
      format?: string;
      zip_password?: string;
    };
    expect(zipCallBody.issue_ids).toEqual(['ISSUE-99']);
    expect(zipCallBody.format).toBe('zip_csv');
    expect(zipCallBody.zip_password).toBe('secure-password-123');
  });
});
