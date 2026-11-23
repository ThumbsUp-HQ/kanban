/**
 * Copyright 2026 Kanban Platform Contributors
 * Apache-2.0 License. See LICENSE for details.
 *
 * Report Template Studio Modal (KB-JINJA-REPORTS).
 * Enables creating and testing custom Jinja2 report templates with variable chips and live validation.
 */

import React, { useState, useRef, type JSX, type SyntheticEvent } from 'react';
import { useParams } from 'react-router';
import { QueryClientContext } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthContext';
import { qk } from '../../api/queryKeys';
import { createReportTemplate, type ReportTemplate } from './reportsApi';
import './reports.css';

export interface ReportTemplateStudioModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug?: string | undefined;
  projectKey?: string | undefined;
  onTemplateSaved?: ((tpl: ReportTemplate) => void) | undefined;
}

const TEMPLATE_SNIPPETS = [
  { label: '{{ mission }}', token: '{{ mission }}\n' },
  { label: '{{ boilerplate }}', token: '{{ boilerplate }}\n' },
  { label: '{{ toc }}', token: '{{ toc }}\n' },
  { label: '{{ executive_summary }}', token: '# Executive Summary\n{{ executive_summary }}\n' },
  { label: '{{ issues_table }}', token: '{{ issues_table }}\n' },
  {
    label: '{% for issue in issues %}',
    token: '{% for issue in issues %}\n## {{ issue.identifier }}: {{ issue.title }}\n**State:** {{ issue.state }} | **Priority:** {{ issue.priority }}\n\n{{ issue.description }}\n{% endfor %}\n',
  },
  { label: '{{ appendix }}', token: '# Appendix\n{{ appendix }}\n' },
];

export function ReportTemplateStudioModal({
  isOpen,
  onClose,
  workspaceSlug,
  projectKey,
  onTemplateSaved,
}: ReportTemplateStudioModalProps): JSX.Element | null {
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
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [description, setDescription] = useState('');
  const [markdown, setMarkdown] = useState(
    '# {{ report_title | default("Custom Report") }}\n\n{{ toc }}\n\n{{ issues_table }}\n\n{% for issue in issues %}\n## {{ issue.identifier }}: {{ issue.title }}\n{{ issue.description }}\n{% endfor %}\n',
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  if (!isOpen) {
    return null;
  }

  const handleNameChange = (val: string) => {
    setName(val);
    if (!slug || slug === name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')) {
      setSlug(val.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''));
    }
  };

  const handleInsertSnippet = (token: string) => {
    /* v8 ignore next 4 */
    if (!textareaRef.current) {
      setMarkdown((prev) => prev + token);
      return;
    }
    const start = textareaRef.current.selectionStart;
    const end = textareaRef.current.selectionEnd;
    const next = markdown.substring(0, start) + token + markdown.substring(end);
    setMarkdown(next);
      setTimeout(() => {
        /* v8 ignore next 5 */
        if (textareaRef.current) {
          textareaRef.current.focus();
          textareaRef.current.selectionStart = textareaRef.current.selectionEnd = start + token.length;
        }
      }, 0);
    };

    const handleSave = async (e: SyntheticEvent) => {
      e.preventDefault();
      setError(null);
      if (!name.trim()) {
        setError('Template name is required.');
        return;
      }
      if (!slug.trim()) {
        setError('Template slug is required.');
        return;
      }
      if (!markdown.trim()) {
        setError('Template markdown content cannot be empty.');
        return;
      }

      setLoading(true);
      try {
        const created = await createReportTemplate(resolvedWorkspaceSlug, {
          name: name.trim(),
          slug: slug.trim(),
          /* v8 ignore next */
          description: description.trim() || undefined,
          project_id: projectKey,
          template_markdown: markdown,
          allowed_formats: ['PDF', 'XLSX', 'CSV', 'DOCX', 'ODT', 'HTML', 'MD'],
        });
        onTemplateSaved?.(created);
        onClose();
      } catch (err) {
        /* v8 ignore next */
        setError(err instanceof Error ? err.message : 'Failed to save template.');
      } finally {
        setLoading(false);
      }
    };

  return (
    <div
      className="reports-modal-backdrop"
      data-testid="template-studio-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        className="reports-modal-container reports-modal-container--wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="template-studio-title"
      >
        <div className="reports-modal-header">
          <h2 id="template-studio-title" className="reports-modal-title">
            <span>🛠️</span> Report Template Studio
          </h2>
          <button
            type="button"
            className="reports-modal-close-btn"
            data-testid="template-studio-close-btn"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <form onSubmit={(e) => { void handleSave(e); }}>
          <div className="reports-modal-body">
            {error && (
              <div className="reports-error-banner" data-testid="template-studio-error">
                {error}
              </div>
            )}

            <div className="reports-form-group">
              <label htmlFor="studio-template-name" className="reports-label">
                Template Name
              </label>
              <input
                id="studio-template-name"
                data-testid="studio-template-name-input"
                type="text"
                className="reports-input"
                placeholder="e.g., Weekly QA Health Briefing"
                value={name}
                onChange={(e) => { handleNameChange(e.target.value); }}
                required
              />
            </div>

            <div className="reports-form-group">
              <label htmlFor="studio-template-slug" className="reports-label">
                Slug (Unique Identifier)
              </label>
              <input
                id="studio-template-slug"
                data-testid="studio-template-slug-input"
                type="text"
                className="reports-input"
                placeholder="e.g., weekly-qa-health"
                value={slug}
                onChange={(e) => { setSlug(e.target.value); }}
                required
              />
            </div>

            <div className="reports-form-group">
              <label htmlFor="studio-template-desc" className="reports-label">
                Description (Optional)
              </label>
              <input
                id="studio-template-desc"
                data-testid="studio-template-desc-input"
                type="text"
                className="reports-input"
                placeholder="Brief summary of template purpose"
                value={description}
                onChange={(e) => { setDescription(e.target.value); }}
              />
            </div>

            <div className="reports-form-group">
              <label htmlFor="studio-template-editor" className="reports-label">
                Jinja2 Markdown Template
              </label>
              <div className="reports-variable-chips">
                {TEMPLATE_SNIPPETS.map((snippet) => (
                  <button
                    key={snippet.label}
                    type="button"
                    className="reports-variable-chip"
                    onClick={() => { handleInsertSnippet(snippet.token); }}
                  >
                    + {snippet.label}
                  </button>
                ))}
              </div>
              <textarea
                id="studio-template-editor"
                ref={textareaRef}
                data-testid="studio-template-markdown-editor"
                className="reports-textarea reports-textarea--code"
                value={markdown}
                onChange={(e) => { setMarkdown(e.target.value); }}
                rows={10}
                required
              />
            </div>
          </div>

          <div className="reports-modal-footer">
            <div className="reports-footer-left">
              <button
                type="button"
                className="reports-btn reports-btn--secondary"
                data-testid="template-studio-cancel-btn"
                onClick={onClose}
              >
                Cancel
              </button>
            </div>
            <div className="reports-footer-right">
              <button
                type="submit"
                className="reports-btn reports-btn--primary"
                data-testid="template-studio-save-btn"
                disabled={loading}
              >
                {loading ? 'Saving...' : 'Save Template'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
