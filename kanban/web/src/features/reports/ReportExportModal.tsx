/**
 * Copyright 2026 Kanban Platform Contributors
 * Apache-2.0 License. See LICENSE for details.
 *
 * Report Export Modal (KB-JINJA-REPORTS).
 * Renders multi-format export dialog with template presets, dynamic parameter inputs,
 * 7 format pills (PDF, XLSX, CSV, DOCX, ODT, HTML, MD), AES-256 ZIP encryption toggle,
 * and live sandboxed preview.
 */

import React, { useState, useEffect, type JSX } from 'react';
import {
  fetchReportTemplates,
  previewReport,
  generateReport,
  type ReportTemplate,
} from './reportsApi';
import { ReportTemplateStudioModal } from './ReportTemplateStudioModal';
import './reports.css';

export interface ReportExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug?: string | undefined;
  projectKey: string;
  selectedIssueIds?: string[] | undefined;
}

const SUPPORTED_FORMATS = ['PDF', 'XLSX', 'CSV', 'DOCX', 'ODT', 'HTML', 'MD'] as const;

export function ReportExportModal({
  isOpen,
  onClose,
  workspaceSlug = 'default',
  projectKey,
  selectedIssueIds,
}: ReportExportModalProps): JSX.Element | null {
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [selectedTemplateSlug, setSelectedTemplateSlug] = useState<string>('security-assessment-report');
  const [selectedFormat, setSelectedFormat] = useState<string>('PDF');
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [isZipEncrypted, setIsZipEncrypted] = useState(false);
  const [zipPassword, setZipPassword] = useState('');
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isStudioOpen, setIsStudioOpen] = useState(false);

  // Load templates on modal open
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    let isSubscribed = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoadingTemplates(true);
    setError(null);

    fetchReportTemplates(workspaceSlug, projectKey)
      .then((items) => {
        /* v8 ignore next */
        if (!isSubscribed) return;
        setTemplates(items);
        if (items.length > 0) {
          const defaultTpl =
            items.find((t) => t.slug === 'security-assessment-report') ?? items[0];
          /* v8 ignore next */
          if (defaultTpl) {
            setSelectedTemplateSlug(defaultTpl.slug);
            const initialParams: Record<string, string> = {};
            /* v8 ignore next */
            if (Array.isArray(defaultTpl.parameters_schema_json)) {
              for (const param of defaultTpl.parameters_schema_json) {
                /* v8 ignore next */
                if (param.name && param.default) {
                  initialParams[param.name] = param.default;
                }
              }
            }
            setParameters(initialParams);
          }
        }
      })
      .catch((err: unknown) => {
        /* v8 ignore next */
        if (!isSubscribed) return;
        /* v8 ignore next */
        setError(err instanceof Error ? err.message : 'Failed to load report templates.');
      })
      .finally(() => {
        /* v8 ignore next */
        if (isSubscribed) setLoadingTemplates(false);
      });

    return () => {
      isSubscribed = false;
    };
  }, [isOpen, workspaceSlug, projectKey]);

  const activeTemplate = templates.find((t) => t.slug === selectedTemplateSlug);

  const handleTemplateChange = (slug: string) => {
    setSelectedTemplateSlug(slug);
    const tpl = templates.find((t) => t.slug === slug);
    /* v8 ignore next */
    if (tpl) {
      const initialParams: Record<string, string> = {};
      /* v8 ignore next */
      if (Array.isArray(tpl.parameters_schema_json)) {
        for (const param of tpl.parameters_schema_json) {
          /* v8 ignore next */
          if (param.name && param.default) {
            initialParams[param.name] = param.default;
          }
        }
      }
      setParameters(initialParams);
      setPreviewContent(null);
    }
  };

  const handleParameterChange = (paramName: string, value: string) => {
    setParameters((prev) => ({
      ...prev,
      [paramName]: value,
    }));
  };

  const handleRenderPreview = async () => {
    /* v8 ignore next */
    if (!activeTemplate) return;
    setLoadingPreview(true);
    setError(null);
    try {
      const res = await previewReport(workspaceSlug, {
        template_ref: activeTemplate.slug,
        project_ref: projectKey,
        parameters,
        issue_ids: selectedIssueIds,
        format: 'MD',
      });
      setPreviewContent(res.rendered_content);
    } catch (err) {
      /* v8 ignore next */
      setError(err instanceof Error ? err.message : 'Preview generation failed.');
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleExport = async () => {
    /* v8 ignore next */
    if (!activeTemplate) return;
    if (isZipEncrypted && (!zipPassword || zipPassword.length < 4)) {
      setError('Password protection requires at least 4 characters.');
      return;
    }

    setExporting(true);
    setError(null);
    try {
      const { blob, filename } = await generateReport(
        { projectRef: projectKey },
        {
          template_ref: activeTemplate.slug,
          format: selectedFormat,
          parameters,
          issue_ids: selectedIssueIds,
          zip_password: isZipEncrypted ? zipPassword : undefined,
        },
      );

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      onClose();
    } catch (err) {
      /* v8 ignore next */
      setError(err instanceof Error ? err.message : 'Export failed.');
    } finally {
      setExporting(false);
    }
  };

  if (!isOpen) {
    return null;
  }

  const parametersSchema = Array.isArray(activeTemplate?.parameters_schema_json)
    ? activeTemplate.parameters_schema_json
    : [];

  return (
    <>
      <div
        className="reports-modal-backdrop"
        data-testid="report-export-backdrop"
        onClick={(e) => {
          if (e.target === e.currentTarget) {
            onClose();
          }
        }}
      >
        <div
          className="reports-modal-container"
          role="dialog"
          aria-modal="true"
          aria-labelledby="report-export-title"
        >
          <div className="reports-modal-header">
            <h2 id="report-export-title" className="reports-modal-title">
              <span>📄</span> Export Report
            </h2>
            <button
              type="button"
              className="reports-modal-close-btn"
              data-testid="report-export-close-btn"
              onClick={onClose}
              aria-label="Close"
            >
              ✕
            </button>
          </div>

          <div className="reports-modal-body">
            {error && (
              <div className="reports-error-banner" data-testid="report-export-error">
                {error}
              </div>
            )}

            {/* Template Selector */}
            <div className="reports-form-group">
              <label htmlFor="report-template-select" className="reports-label">
                Report Template
              </label>
              <select
                id="report-template-select"
                data-testid="report-template-select"
                className="reports-select"
                value={selectedTemplateSlug}
                onChange={(e) => { handleTemplateChange(e.target.value); }}
                disabled={loadingTemplates}
              >
                {templates.map((t) => (
                  <option key={t.slug} value={t.slug}>
                    {t.name} {t.is_builtin ? '(Built-in)' : '(Custom)'}
                  </option>
                ))}
              </select>
            </div>

            {/* Format Pill Selector */}
            <div className="reports-form-group">
              <label className="reports-label">Export Format</label>
              <div className="reports-format-pills" data-testid="report-format-pills">
                {SUPPORTED_FORMATS.map((fmt) => {
                  const isActive = selectedFormat === fmt;
                  return (
                    <button
                      key={fmt}
                      type="button"
                      className={`reports-format-pill ${isActive ? 'reports-format-pill--active' : ''}`}
                      data-testid={`report-format-pill-${fmt.toLowerCase()}`}
                      aria-pressed={isActive}
                      onClick={() => { setSelectedFormat(fmt); }}
                    >
                      {fmt}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Dynamic Template Parameters */}
            {parametersSchema.length > 0 && (
              <div className="reports-form-group">
                <label className="reports-label">Template Parameters</label>
                <div className="reports-parameters-grid">
                  {parametersSchema.map((param) => (
                    <div key={param.name} className="reports-form-group">
                      <label htmlFor={`param-${param.name}`} className="reports-label">
                        {param.label}
                      </label>
                      {param.type === 'textarea' ? (
                        <textarea
                          id={`param-${param.name}`}
                          data-testid={`report-param-input-${param.name}`}
                          className="reports-textarea"
                          value={parameters[param.name] ?? ''}
                          onChange={(e) => { handleParameterChange(param.name, e.target.value); }}
                        />
                      ) : (
                        <input
                          id={`param-${param.name}`}
                          data-testid={`report-param-input-${param.name}`}
                          type="text"
                          className="reports-input"
                          value={parameters[param.name] ?? ''}
                          onChange={(e) => { handleParameterChange(param.name, e.target.value); }}
                        />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* AES-256 ZIP Password Toggle */}
            <div className="reports-encryption-box">
              <label className="reports-checkbox-row">
                <input
                  type="checkbox"
                  data-testid="reports-zip-toggle"
                  className="reports-checkbox"
                  checked={isZipEncrypted}
                  onChange={(e) => { setIsZipEncrypted(e.target.checked); }}
                />
                <span className="reports-checkbox-label">
                  🔒 Encrypt report in AES-256 password-protected ZIP archive
                </span>
              </label>

              {isZipEncrypted && (
                <div className="reports-form-group">
                  <input
                    type="password"
                    data-testid="reports-zip-password-input"
                    className="reports-input"
                    placeholder="Enter encryption passphrase (min 4 characters)"
                    value={zipPassword}
                    onChange={(e) => { setZipPassword(e.target.value); }}
                    required
                  />
                </div>
              )}
            </div>

            {/* Live Preview Container */}
            {previewContent && (
              <div className="reports-preview-container" data-testid="reports-preview-pane">
                <pre className="reports-preview-content">{previewContent}</pre>
              </div>
            )}
          </div>

          <div className="reports-modal-footer">
            <div className="reports-footer-left">
              <button
                type="button"
                className="reports-btn reports-btn--secondary"
                data-testid="reports-open-studio-btn"
                onClick={() => { setIsStudioOpen(true); }}
              >
                ⚙️ Template Studio
              </button>
              <button
                type="button"
                className="reports-btn reports-btn--secondary"
                data-testid="reports-preview-btn"
                onClick={() => { void handleRenderPreview(); }}
                disabled={loadingPreview}
              >
                {loadingPreview ? 'Previewing...' : '👁️ Preview'}
              </button>
            </div>

            <div className="reports-footer-right">
              <button
                type="button"
                className="reports-btn reports-btn--secondary"
                data-testid="reports-cancel-btn"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                type="button"
                className="reports-btn reports-btn--primary"
                data-testid="reports-export-submit-btn"
                onClick={() => { void handleExport(); }}
                disabled={exporting || loadingTemplates}
              >
                {exporting ? 'Generating...' : `Download ${selectedFormat}`}
              </button>
            </div>
          </div>
        </div>
      </div>

      {isStudioOpen && (
        <ReportTemplateStudioModal
          isOpen={isStudioOpen}
          onClose={() => { setIsStudioOpen(false); }}
          workspaceSlug={workspaceSlug}
          projectKey={projectKey}
          onTemplateSaved={(newTpl) => {
            setTemplates((prev) => [...prev, newTpl]);
            setSelectedTemplateSlug(newTpl.slug);
          }}
        />
      )}
    </>
  );
}
