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
import { useParams } from 'react-router';
import { QueryClientContext } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthContext';
import { qk } from '../../api/queryKeys';
import {
  fetchReportTemplates,
  previewReport,
  generateReport,
  type ReportTemplate,
} from './reportsApi';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { StudioDocLink } from '../../components/help/StudioDocLink';
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
  workspaceSlug,
  projectKey,
  selectedIssueIds,
}: ReportExportModalProps): JSX.Element | null {
  const routeParams = useParams<{ workspaceSlug?: string }>();
  const auth = useAuth();
  const queryContext = React.useContext(QueryClientContext);
  const cachedMe = queryContext ? queryContext.getQueryData<{ workspace_id?: string }>(qk.me()) : undefined;

  const resolvedWorkspaceSlug =
    (workspaceSlug && workspaceSlug !== 'default' && workspaceSlug.trim().length > 0)
      ? workspaceSlug.trim()
      : (routeParams.workspaceSlug && routeParams.workspaceSlug !== 'default' && routeParams.workspaceSlug.trim().length > 0)
        ? routeParams.workspaceSlug.trim()
        : (auth.session?.workspace_id && auth.session.workspace_id.trim().length > 0)
          ? auth.session.workspace_id.trim()
          : (cachedMe?.workspace_id && cachedMe.workspace_id.trim().length > 0)
            ? cachedMe.workspace_id.trim()
            : (workspaceSlug ?? 'default');

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

    fetchReportTemplates(resolvedWorkspaceSlug, projectKey)
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
  }, [isOpen, resolvedWorkspaceSlug, projectKey]);

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
      const res = await previewReport(resolvedWorkspaceSlug, {
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
        { projectRef: projectKey, workspaceRef: resolvedWorkspaceSlug },
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
          data-testid="report-export-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="report-export-title"
        >
          <div className="reports-modal-header">
            <h2 id="report-export-title" className="reports-modal-title">
              <span>📄</span> Export Report
            </h2>
            <div className="reports-modal-header-actions">
              <StudioDocLink
                href="/docs/studio-configuration-reference"
                label="Reports Documentation ->"
                testId="report-export-doc-link"
              />
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
                    {t.name} {t.is_builtin ? '(Built-in)' : '(Custom)'}{t.slug === 'security-assessment-report' ? ' (Default)' : ''}
                  </option>
                ))}
              </select>
            </div>

            {/* Format Pill Selector */}
            <div className="reports-form-group">
              <span id="report-export-format-label" className="reports-label">Export Format</span>
              <div
                className="reports-format-pills"
                data-testid="report-format-pills"
                role="group"
                aria-labelledby="report-export-format-label"
              >
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
                      {fmt === 'PDF' ? 'PDF (Default)' : fmt}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Dynamic Template Parameters */}
            {parametersSchema.length > 0 && (
              <div className="reports-form-group">
                <span className="reports-label">Template Parameters</span>
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
              <div className="reports-checkbox-row-wrapper">
                <label className="reports-checkbox-row" htmlFor="reports-zip-toggle">
                  <input
                    id="reports-zip-toggle"
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
                <FieldHelpHint
                  title="Report Encryption"
                  summary="Encrypts generated report artifacts inside an AES-256 password-protected ZIP archive."
                  defaultValue="Disabled"
                  docHref="/docs/studio-configuration-reference"
                  testId="report-encryption-help-hint"
                />
              </div>

              {isZipEncrypted && (
                <div className="reports-form-group">
                  <input
                    type="password"
                    data-testid="reports-zip-password-input"
                    aria-label="Archive Password"
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
          workspaceSlug={resolvedWorkspaceSlug}
          projectKey={projectKey}
          onTemplateSaved={(newTpl) => {
            setTemplates((prev) => {
              const filtered = prev.filter((t) => t.slug !== newTpl.slug);
              return [...filtered, newTpl];
            });
            setSelectedTemplateSlug(newTpl.slug);
          }}
        />
      )}
    </>
  );
}
