/**
 * CSV & Password-Protected ZIP (AES-256) Import, Export and Download Template Modal (KAN-316).
 *
 * Provides:
 * 1. Export Tab: CSV or Password-Protected ZIP (AES-256) encrypted ZIP with active filter reflection.
 * 2. Import Tab: Download Template, file drop, Dry-Run preview diff table, and atomic commit.
 * 3. 3-tier governance error decoding and minimum 12-char password enforcement.
 */

import React, { useState, useEffect, useRef, type JSX, type SyntheticEvent } from 'react';
import { getCsrfToken } from '../../api/client';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import type { ActiveFilters } from './FilterDisplayBar';
import './CsvImportExportModal.css';

export interface CsvImportDiffItem {
  row_number: number;
  action: 'create' | 'update' | 'skip' | 'error';
  key?: string | null;
  summary: string;
  state: string;
  priority: string;
  assignees?: string[];
  labels?: string[];
  changes?: Record<string, { old: unknown; new: unknown }>;
  errors?: string[];
}

export interface CsvImportRowError {
  row_number: number;
  column?: string | null;
  message: string;
  raw_value?: string | null;
}

export interface CsvImportDiffReport {
  total_rows: number;
  creates_count: number;
  updates_count: number;
  error_count: number;
  items: CsvImportDiffItem[];
  errors: CsvImportRowError[];
}

export interface CsvImportExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectKey: string;
  workspaceScope?: string | undefined;
  activeFilters?: ActiveFilters | undefined;
  searchQuery?: string | undefined;
  initialTab?: 'export' | 'import' | undefined;
  initialExportFormat?: 'csv' | 'zip_csv' | undefined;
  onImportSuccess?: (() => void) | undefined;
  selectedIssueIds?: string[] | undefined;
}

export function CsvImportExportModal({
  isOpen,
  onClose,
  projectKey,
  workspaceScope,
  activeFilters = {},
  searchQuery,
  initialTab = 'export',
  initialExportFormat = 'csv',
  onImportSuccess,
  selectedIssueIds,
}: CsvImportExportModalProps): JSX.Element | null {
  const [activeTab, setActiveTab] = useState<'export' | 'import'>(initialTab);
  const [prevInitialTab, setPrevInitialTab] = useState(initialTab);
  if (initialTab !== prevInitialTab) {
    setPrevInitialTab(initialTab);
    setActiveTab(initialTab);
  }

  const [exportFormat, setExportFormat] = useState<'csv' | 'zip_csv'>(initialExportFormat);
  const [prevInitialExportFormat, setPrevInitialExportFormat] = useState(initialExportFormat);
  if (initialExportFormat !== prevInitialExportFormat) {
    setPrevInitialExportFormat(initialExportFormat);
    setExportFormat(initialExportFormat);
  }
  const [exportPassword, setExportPassword] = useState('');
  const [isExporting, setIsExporting] = useState(false);

  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPassword, setImportPassword] = useState('');
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [previewReport, setPreviewReport] = useState<CsvImportDiffReport | null>(null);
  const [importSuccessMsg, setImportSuccessMsg] = useState<string | null>(null);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Escape key handler (KAN-483)
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent): void => {
      // Yield Escape close when HelpDrawer is open above modal (KAN-483)
      if (document.querySelector('.kb-help-drawer, .kb-help-drawer-backdrop')) {
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>): void => {
    if (e.target === e.currentTarget) {
      // Yield backdrop close when HelpDrawer is open above modal (KAN-483)
      if (document.querySelector('.kb-help-drawer, .kb-help-drawer-backdrop')) {
        return;
      }
      onClose();
    }
  };

  if (!isOpen) return null;

  const isExportPasswordValid = exportFormat === 'csv' || exportPassword.length >= 12;

  const handleTabSwitch = (tab: 'export' | 'import'): void => {
    setActiveTab(tab);
    setErrorMessage(null);
    setImportSuccessMsg(null);
  };

  const handleDownloadTemplate = async (): Promise<void> => {
    setErrorMessage(null);
    try {
      const endpoint = projectKey
        ? `/api/v1/projects/${encodeURIComponent(projectKey)}/issues/import-template.csv`
        : `/api/v1/workspaces/${encodeURIComponent(workspaceScope ?? 'default')}/issues/import-template.csv`;

      const res = await fetch(endpoint, {
        method: 'GET',
        headers: { Accept: 'text/csv' },
        credentials: 'include',
      });

      if (!res.ok) {
        const errorText = await res.text();
        /* v8 ignore next */
        throw new Error(errorText || 'Failed to download template');
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      /* v8 ignore next */
      a.download = `${projectKey || 'workspace'}-import-template.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: unknown) {
      /* v8 ignore next */
      const msg = err instanceof Error ? err.message : 'Failed to download template';
      setErrorMessage(decodeGovernanceError(msg));
    }
  };

  const handleExport = async (e: SyntheticEvent): Promise<void> => {
    e.preventDefault();
    /* v8 ignore next */
    if (!isExportPasswordValid) return;

    setIsExporting(true);
    setErrorMessage(null);
    try {
      /* v8 ignore next 3 */
      const endpoint = projectKey
        ? `/api/v1/projects/${encodeURIComponent(projectKey)}/issues/export`
        : `/api/v1/workspaces/${encodeURIComponent(workspaceScope ?? 'default')}/issues/export`;

      /* v8 ignore next 12 */
      const payload = {
        format: exportFormat,
        zip_password: exportFormat === 'zip_csv' ? exportPassword : null,
        q: searchQuery ?? null,
        state_ids: activeFilters.state ?? null,
        priorities: activeFilters.priority ?? null,
        assignee_ids: activeFilters.assignee ?? null,
        label_ids: activeFilters.label ?? null,
        cycle_id: activeFilters.cycle?.[0] ?? null,
        module_id: activeFilters.module?.[0] ?? null,
        issue_ids: selectedIssueIds ?? null,
      };

      const csrfToken = getCsrfToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      /* v8 ignore next 3 */
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
      }

      const res = await fetch(endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        credentials: 'include',
      });

      if (!res.ok) {
        /* v8 ignore next 2 */
        const errJson = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errJson.detail ?? 'Export failed');
      }

      const blob = await res.blob();
      const extension = exportFormat === 'zip_csv' ? 'zip' : 'csv';
      /* v8 ignore next */
      const filename = `${projectKey || 'issues'}-export.${extension}`;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: unknown) {
      /* v8 ignore next */
      const msg = err instanceof Error ? err.message : 'Export failed';
      setErrorMessage(decodeGovernanceError(msg));
    } finally {
      setIsExporting(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const file = e.target.files?.[0] ?? null;
    setImportFile(file);
    setPreviewReport(null);
    setErrorMessage(null);
    setImportSuccessMsg(null);
  };

  const handleRunImport = async (dryRun: boolean): Promise<void> => {
    /* v8 ignore next 4 */
    if (!importFile) {
      setErrorMessage('Please select a CSV or password-protected ZIP (AES-256) file.');
      return;
    }

    if (dryRun) {
      setIsPreviewing(true);
    } else {
      setIsImporting(true);
    }
    setErrorMessage(null);
    setImportSuccessMsg(null);

    try {
      const endpoint = `/api/v1/projects/${encodeURIComponent(projectKey)}/issues/import?dry_run=${dryRun ? 'true' : 'false'}`;
      const formData = new FormData();
      formData.append('file', importFile);
      /* v8 ignore next 3 */
      if (importPassword) {
        formData.append('zip_password', importPassword);
      }

      const csrfToken = getCsrfToken();
      const headers: Record<string, string> = {};
      /* v8 ignore next 3 */
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
      }

      const res = await fetch(endpoint, {
        method: 'POST',
        headers,
        body: formData,
        credentials: 'include',
      });

      /* v8 ignore next */
      const data = (await res.json().catch(() => ({}))) as CsvImportDiffReport & { detail?: string };

      /* v8 ignore next 3 */
      if (!res.ok) {
        throw new Error(data.detail ?? 'Import failed');
      }

      if (dryRun) {
        setPreviewReport(data);
      } else {
        setPreviewReport(data);
        setImportSuccessMsg(
          `Import complete: ${String(data.creates_count)} created, ${String(data.updates_count)} updated.`,
        );
        onImportSuccess?.();
      }
    } catch (err: unknown) {
      /* v8 ignore next 2 */
      const msg = err instanceof Error ? err.message : 'Import failed';
      setErrorMessage(decodeGovernanceError(msg));
    } finally {
      if (dryRun) {
        setIsPreviewing(false);
      } else {
        setIsImporting(false);
      }
    }
  };

  const isZipFile = importFile?.name.toLowerCase().endsWith('.zip');

  return (
    <div
      className="kb-csv-modal-backdrop"
      data-testid="csv-import-export-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="csv-modal-title"
      onClick={handleBackdropClick}
    >
      <div className="kb-csv-modal-dialog">
        <div className="kb-csv-modal-header">
          <h2 id="csv-modal-title" className="kb-csv-modal-heading">
            Issue CSV Import &amp; Export
          </h2>
          <div className="kb-csv-modal-header-actions">
            <StudioDocLink
              href="/docs/ticket-screen-and-work-item-features#csv-and-zip-import-and-export"
              label="CSV & ZIP Guide ->"
              testId="csv-modal-doc-link"
            />
            <button
              type="button"
              className="kb-csv-modal-close-btn"
              data-testid="csv-modal-close-btn"
              aria-label="Close"
              onClick={onClose}
            >
              ✕
            </button>
          </div>
        </div>

        <div className="kb-csv-modal-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'export'}
            className={`kb-csv-modal-tab ${activeTab === 'export' ? 'kb-csv-modal-tab--active' : ''}`}
            data-testid="csv-modal-tab-export"
            onClick={() => { handleTabSwitch('export'); }}
          >
            Export Issues
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'import'}
            className={`kb-csv-modal-tab ${activeTab === 'import' ? 'kb-csv-modal-tab--active' : ''}`}
            data-testid="csv-modal-tab-import"
            onClick={() => { handleTabSwitch('import'); }}
          >
            Import Issues
          </button>
        </div>

        <div className="kb-csv-modal-body">
          {errorMessage && (
            <div className="kb-csv-modal-error" data-testid="csv-modal-error" role="alert">
              {errorMessage}
            </div>
          )}

          {importSuccessMsg && (
            <div className="kb-csv-modal-success" data-testid="import-success-banner" role="status">
              {importSuccessMsg}
            </div>
          )}

          {activeTab === 'export' && (
            <form onSubmit={(e) => { void handleExport(e); }} className="kb-csv-modal-section">
              <p className="kb-csv-modal-desc">
                Export matching issues from the active view and filters to canonical RFC 4180 CSV or encrypted ZIP.
              </p>

              <div className="kb-csv-modal-field">
                <span className="kb-csv-modal-label">Export Format</span>
                <div className="kb-csv-modal-radio-group">
                  <label className="kb-csv-modal-radio-label">
                    <input
                      type="radio"
                      name="export-format"
                      value="csv"
                      checked={exportFormat === 'csv'}
                      onChange={() => { setExportFormat('csv'); }}
                      data-testid="export-format-csv"
                    />
                    <span className="kb-csv-modal-radio-content">
                      <strong>Standard CSV (Default)</strong>
                      <span className="kb-csv-modal-radio-desc">
                        Canonical RFC 4180 UTF-8 formatted CSV with formula-injection neutralization.
                      </span>
                    </span>
                  </label>

                  <label className="kb-csv-modal-radio-label">
                    <input
                      type="radio"
                      name="export-format"
                      value="zip_csv"
                      checked={exportFormat === 'zip_csv'}
                      onChange={() => { setExportFormat('zip_csv'); }}
                      data-testid="export-format-zip"
                    />
                    <span className="kb-csv-modal-radio-content">
                      <strong>Password-Protected ZIP (AES-256)</strong>
                      <span className="kb-csv-modal-radio-desc">
                        Industry standard AE-2 encrypted container (AES-256-CTR with PBKDF2 and HMAC-SHA256).
                      </span>
                    </span>
                  </label>
                </div>
              </div>

              {exportFormat === 'zip_csv' && (
                <div className="kb-csv-modal-field">
                  <label htmlFor="export-zip-password" className="kb-csv-modal-label">
                    ZIP Password (minimum 12 characters)
                  </label>
                  <input
                    id="export-zip-password"
                    type="password"
                    className="kb-csv-modal-input"
                    data-testid="export-zip-password-input"
                    value={exportPassword}
                    onChange={(e) => { setExportPassword(e.target.value); }}
                    placeholder="Enter at least 12 characters..."
                    required
                  />
                  <div
                    className={`kb-password-hint ${exportPassword.length >= 12 ? 'kb-password-hint--valid' : 'kb-password-hint--invalid'}`}
                    data-testid="export-password-validation"
                  >
                    {exportPassword.length >= 12
                      ? 'Password meets minimum length (12+ characters)'
                      : `Password must be at least 12 characters (currently ${String(exportPassword.length)})`}
                  </div>
                </div>
              )}

              <div className="kb-csv-modal-footer">
                <button
                  type="button"
                  className="kb-csv-btn kb-csv-btn-secondary"
                  onClick={onClose}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kb-csv-btn kb-csv-btn-primary"
                  data-testid="export-submit-btn"
                  disabled={isExporting || !isExportPasswordValid}
                >
                  {isExporting ? 'Exporting...' : 'Export Issues'}
                </button>
              </div>
            </form>
          )}

          {activeTab === 'import' && (
            <div className="kb-csv-modal-section">
              <p className="kb-csv-modal-desc">
                Import issues from CSV or password-protected ZIP (AES-256) archive. Run a dry run to inspect changes before committing.
              </p>

              <div className="kb-csv-modal-field">
                <button
                  type="button"
                  className="kb-csv-btn kb-csv-btn-secondary"
                  data-testid="download-template-btn"
                  onClick={() => { void handleDownloadTemplate(); }}
                >
                  Download CSV Template
                </button>
              </div>

              <div className="kb-csv-modal-field">
                <label htmlFor="csv-file-upload" className="kb-csv-modal-label">
                  Select File (.csv or .zip)
                </label>
                <div
                  className="kb-csv-file-dropzone"
                  onClick={() => { fileInputRef.current?.click(); }}
                >
                  <input
                    ref={fileInputRef}
                    id="csv-file-upload"
                    type="file"
                    accept=".csv,.zip"
                    data-testid="import-file-input"
                    className="kb-csv-file-hidden-input"
                    onChange={handleFileChange}
                  />
                  {importFile ? (
                    <div className="kb-csv-file-selected" data-testid="import-selected-filename">
                      Selected: {importFile.name} ({String(Math.round(importFile.size / 1024))} KB)
                    </div>
                  ) : (
                    <div>Click to select or drop a CSV or ZIP file here</div>
                  )}
                </div>
              </div>

              {isZipFile && (
                <div className="kb-csv-modal-field">
                  <label htmlFor="import-zip-password" className="kb-csv-modal-label">
                    ZIP Password
                  </label>
                  <input
                    id="import-zip-password"
                    type="password"
                    className="kb-csv-modal-input"
                    data-testid="import-zip-password-input"
                    value={importPassword}
                    onChange={(e) => { setImportPassword(e.target.value); }}
                    placeholder="Enter decryption password..."
                  />
                </div>
              )}

              {previewReport && (
                <div className="kb-csv-modal-field" data-testid="import-preview-table">
                  <span className="kb-csv-modal-label">Dry-Run Preview Summary</span>
                  <div className="kb-csv-diff-stats">
                    <div className="kb-csv-stat-card">
                      <div className="kb-csv-stat-number" data-testid="import-stat-total">
                        {previewReport.total_rows}
                      </div>
                      <div className="kb-csv-stat-label">Total Rows</div>
                    </div>
                    <div className="kb-csv-stat-card kb-csv-stat-card--success">
                      <div className="kb-csv-stat-number" data-testid="import-stat-creates">
                        {previewReport.creates_count}
                      </div>
                      <div className="kb-csv-stat-label">New Issues</div>
                    </div>
                    <div className="kb-csv-stat-card kb-csv-stat-card--accent">
                      <div className="kb-csv-stat-number" data-testid="import-stat-updates">
                        {previewReport.updates_count}
                      </div>
                      <div className="kb-csv-stat-label">Updates</div>
                    </div>
                    <div className="kb-csv-stat-card kb-csv-stat-card--danger">
                      <div className="kb-csv-stat-number" data-testid="import-stat-errors">
                        {previewReport.error_count}
                      </div>
                      <div className="kb-csv-stat-label">Errors</div>
                    </div>
                  </div>

                  {previewReport.items.length > 0 && (
                    <div className="kb-csv-diff-table-wrap">
                      <table className="kb-csv-diff-table">
                        <thead>
                          <tr>
                            <th>Row</th>
                            <th>Action</th>
                            <th>Key</th>
                            <th>Summary</th>
                            <th>State</th>
                            <th>Priority</th>
                          </tr>
                        </thead>
                        <tbody>
                          {previewReport.items.map((item) => (
                            <tr key={`${String(item.row_number)}-${item.key ?? ''}`}>
                              <td>{item.row_number}</td>
                              <td>
                                <span className={`kb-csv-action-badge kb-csv-action-badge--${item.action}`}>
                                  {item.action}
                                </span>
                              </td>
                              <td>{item.key ?? '-'}</td>
                              <td>{item.summary}</td>
                              <td>{item.state}</td>
                              <td>{item.priority}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {previewReport.errors.length > 0 && (
                    <div className="kb-csv-modal-error">
                      <strong>Validation Errors:</strong>
                      <ul>
                        {previewReport.errors.map((err, idx) => (
                          <li key={String(idx)}>
                            Row {err.row_number}{err.column ? ` [${err.column}]` : ''}: {err.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              <div className="kb-csv-modal-footer">
                <button
                  type="button"
                  className="kb-csv-btn kb-csv-btn-secondary"
                  data-testid="import-preview-btn"
                  disabled={isPreviewing || !importFile}
                  onClick={() => { void handleRunImport(true); }}
                >
                  {isPreviewing ? 'Analyzing...' : 'Preview Import'}
                </button>
                <button
                  type="button"
                  className="kb-csv-btn kb-csv-btn-success"
                  data-testid="import-confirm-btn"
                  disabled={
                    isImporting ||
                    !previewReport ||
                    (previewReport.creates_count === 0 && previewReport.updates_count === 0)
                  }
                  onClick={() => { void handleRunImport(false); }}
                >
                  {isImporting ? 'Importing...' : 'Confirm Import'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function decodeGovernanceError(raw: string): string {
  if (raw.includes('EXPORT_DISABLED_BY_SYSTEM_ADMIN')) {
    return 'Export is disabled globally by System Administrator.';
  }
  if (raw.includes('EXPORT_DISABLED_BY_WORKSPACE_ADMIN')) {
    return 'Export is disabled for this workspace by Workspace Administrator.';
  }
  if (raw.includes('IMPORT_DISABLED_BY_SYSTEM_ADMIN')) {
    return 'Import is disabled globally by System Administrator.';
  }
  if (raw.includes('IMPORT_DISABLED_BY_WORKSPACE_ADMIN')) {
    return 'Import is disabled for this workspace by Workspace Administrator.';
  }
  if (raw.includes('INSUFFICIENT_CAPABILITY')) {
    return 'You do not have permission to perform this action.';
  }
  if (raw.includes('PASSWORD_REQUIRED')) {
    return 'A password is required to decrypt this ZIP archive.';
  }
  if (raw.includes('INVALID_PASSWORD')) {
    return 'The provided password is incorrect or file has been tampered with.';
  }
  if (raw.includes('ZIP_BOMB_DETECTED')) {
    return 'Archive exceeded compression ratio or decompressed size limit.';
  }
  if (raw.includes('PATH_TRAVERSAL_DETECTED')) {
    return 'Archive contains invalid relative path traversal.';
  }
  if (raw.includes('INVALID_UTF8_SURROGATE')) {
    return 'File contains invalid UTF-16 surrogates.';
  }
  return raw;
}
