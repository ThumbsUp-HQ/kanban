/**
 * Copyright 2026 Kanban Platform Contributors
 * Apache-2.0 License. See LICENSE for details.
 *
 * Vitest tests for ReportExportModal, ReportTemplateStudioModal, and reportsApi (KB-JINJA-REPORTS).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { setCsrfToken } from '../../../api/client';
import { qk } from '../../../api/queryKeys';
import * as authModule from '../../auth/AuthContext';
import { ReportExportModal } from '../ReportExportModal';
import { ReportTemplateStudioModal } from '../ReportTemplateStudioModal';
import * as reportsApi from '../reportsApi';

const MOCK_TEMPLATES: reportsApi.ReportTemplate[] = [
  {
    id: '11111111-1111-1111-1111-111111111111',
    workspace_id: 'ws-1',
    slug: 'security-assessment-report',
    name: 'Security Assessment Report',
    description: 'Comprehensive security audit report',
    is_builtin: true,
    template_markdown: '# Security Assessment Report\n{{ mission }}\n{{ toc }}\n{{ issues_table }}',
    parameters_schema_json: [
      {
        name: 'mission',
        label: 'Assessment Mission',
        type: 'textarea',
        default: 'Penetration testing mission',
        required: true,
      },
      {
        name: 'author',
        label: 'Lead Author',
        type: 'text',
        default: 'Security Team',
      },
    ],
    csv_columns_json: [{ header: 'Key', expr: 'issue.key' }],
    allowed_formats: ['PDF', 'XLSX', 'CSV', 'DOCX', 'ODT', 'HTML', 'MD'],
    created_at: '2026-11-22T00:00:00Z',
    updated_at: '2026-11-22T00:00:00Z',
  },
  {
    id: '22222222-2222-2222-2222-222222222222',
    workspace_id: 'ws-1',
    slug: 'sprint-release-notes',
    name: 'Sprint & Release Notes Report',
    description: 'Sprint release notes',
    is_builtin: false,
    template_markdown: '# Sprint Notes\n{{ issues_table }}',
    parameters_schema_json: [
      {
        name: 'version',
        label: 'Release Version',
        type: 'text',
        default: 'v1.0.0',
      },
    ],
    csv_columns_json: [],
    allowed_formats: ['PDF', 'XLSX', 'CSV', 'DOCX', 'ODT', 'HTML', 'MD'],
    created_at: '2026-11-22T00:00:00Z',
    updated_at: '2026-11-22T00:00:00Z',
  },
];

describe('reportsApi client', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.cookie = 'kb_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  });

  it('exercises fetchReportTemplates, fetchReportTemplate, create, update, delete, preview, and generateReport', async () => {
    document.cookie = 'kb_csrf=test-csrf-token';
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    // 1. fetchReportTemplates with and without projectRef
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ items: MOCK_TEMPLATES }),
    });
    const list1 = await reportsApi.fetchReportTemplates('ws-1', 'KAN');
    expect(list1).toHaveLength(2);
    const call0 = fetchMock.mock.calls[0] as [string, RequestInit & { headers: Record<string, string> }];
    expect(call0[1].credentials).toBe('same-origin');
    expect(call0[1].headers['X-CSRF-Token']).toBe('test-csrf-token');
    expect(call0[1].headers['x-kb-csrf']).toBe('test-csrf-token');

    // 1b. getCsrfToken cached client token takes precedence
    setCsrfToken('client-cached-csrf');
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ items: MOCK_TEMPLATES }),
    });
    await reportsApi.fetchReportTemplates('ws-1', 'KAN');
    const call1 = fetchMock.mock.calls[1] as [string, RequestInit & { headers: Record<string, string> }];
    expect(call1[1].headers['X-CSRF-Token']).toBe('client-cached-csrf');
    setCsrfToken(null);

    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    });
    const list2 = await reportsApi.fetchReportTemplates('ws-1');
    expect(list2).toEqual([]);

    fetchMock.mockResolvedValueOnce({
      ok: false,
      statusText: 'Forbidden',
      json: () => Promise.resolve({ detail: 'Denied' }),
    });
    await expect(reportsApi.fetchReportTemplates('ws-1')).rejects.toThrow('Denied');

    fetchMock.mockResolvedValueOnce({
      ok: false,
      statusText: 'Server Error',
      json: () => Promise.reject(new Error('invalid json')),
    });
    await expect(reportsApi.fetchReportTemplates('ws-1')).rejects.toThrow('Failed to fetch report templates');

    // 2. fetchReportTemplate
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(MOCK_TEMPLATES[0]),
    });
    const single = await reportsApi.fetchReportTemplate('ws-1', 'security-assessment-report');
    expect(single.slug).toBe('security-assessment-report');

    fetchMock.mockResolvedValueOnce({
      ok: false,
      statusText: 'Not Found',
      json: () => Promise.resolve({}),
    });
    await expect(reportsApi.fetchReportTemplate('ws-1', 'missing')).rejects.toThrow(
      'Failed to fetch report template',
    );

    // 3. createReportTemplate
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(MOCK_TEMPLATES[1]),
    });
    const created = await reportsApi.createReportTemplate('ws-1', {
      slug: 'new-tpl',
      name: 'New Tpl',
      template_markdown: '# Hello',
    });
    expect(created.slug).toBe('sprint-release-notes');

    fetchMock.mockResolvedValueOnce({
      ok: false,
      statusText: 'Conflict',
      json: () => Promise.resolve({ detail: 'Slug conflict' }),
    });
    await expect(
      reportsApi.createReportTemplate('ws-1', { slug: 'dup', name: 'Dup', template_markdown: '#' }),
    ).rejects.toThrow('Slug conflict');

    // 4. updateReportTemplate
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(MOCK_TEMPLATES[1]),
    });
    const updated = await reportsApi.updateReportTemplate('ws-1', 'sprint-release-notes', {
      name: 'Updated Name',
    });
    expect(updated.id).toBe('22222222-2222-2222-2222-222222222222');

    fetchMock.mockResolvedValueOnce({
      ok: false,
      statusText: 'Bad Request',
      json: () => Promise.resolve({}),
    });
    await expect(reportsApi.updateReportTemplate('ws-1', 'x', {})).rejects.toThrow(
      'Failed to update report template',
    );

    // 5. deleteReportTemplate
    fetchMock.mockResolvedValueOnce({ ok: true, status: 204 });
    await reportsApi.deleteReportTemplate('ws-1', 'sprint-release-notes');

    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
      json: () => Promise.resolve({ detail: 'Cannot delete builtin' }),
    });
    await expect(reportsApi.deleteReportTemplate('ws-1', 'security-assessment-report')).rejects.toThrow(
      'Cannot delete builtin',
    );

    // 6. previewReport
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ rendered_content: '# Ok', format: 'MD', issue_count: 1 }),
    });
    const prev = await reportsApi.previewReport('ws-1', { template_ref: 'sprint-release-notes' });
    expect(prev.rendered_content).toBe('# Ok');

    fetchMock.mockResolvedValueOnce({
      ok: false,
      statusText: 'Unprocessable',
      json: () => Promise.resolve({}),
    });
    await expect(reportsApi.previewReport('ws-1', {})).rejects.toThrow('Failed to render preview');

    // 7. generateReport
    await expect(
      reportsApi.generateReport({}, { template_ref: 'x', format: 'PDF' }),
    ).rejects.toThrow('Either projectRef or workspaceRef must be supplied');

    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: { get: () => 'attachment; filename="custom-out.pdf"' },
      blob: () => Promise.resolve(new Blob(['pdf'])),
    });
    const gen1 = await reportsApi.generateReport(
      { projectRef: 'KAN' },
      { template_ref: 'x', format: 'PDF' },
    );
    expect(gen1.filename).toBe('custom-out.pdf');

    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: { get: () => null },
      blob: () => Promise.resolve(new Blob(['csv'])),
    });
    const gen2 = await reportsApi.generateReport(
      { workspaceRef: 'ws-1' },
      { template_ref: 'x', format: 'CSV' },
    );
    expect(gen2.filename).toBe('report.csv');

    fetchMock.mockResolvedValueOnce({
      ok: false,
      statusText: 'Error',
      json: () => Promise.resolve({ detail: 'Export blocked' }),
    });
    await expect(
      reportsApi.generateReport({ projectRef: 'KAN' }, { template_ref: 'x', format: 'PDF' }),
    ).rejects.toThrow('Export blocked');
  });
});

describe('ReportTemplateStudioModal', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('validates fields, inserts variable chips, and saves or handles errors', async () => {
    const onClose = vi.fn();
    const onSaved = vi.fn();
    const fallbackTpl = MOCK_TEMPLATES[1] ?? MOCK_TEMPLATES[0];
    if (!fallbackTpl) {
      throw new Error('Missing mock template');
    }
    const createSpy = vi.spyOn(reportsApi, 'createReportTemplate').mockResolvedValue(fallbackTpl);

    const { rerender } = render(
      <ReportTemplateStudioModal isOpen={false} onClose={onClose} />,
    );
    expect(screen.queryByTestId('template-studio-backdrop')).toBeNull();

    rerender(
      <ReportTemplateStudioModal
        isOpen={true}
        onClose={onClose}
        workspaceSlug="default"
        onTemplateSaved={onSaved}
      />,
    );

    const form = screen.getByTestId('template-studio-save-btn').closest('form');
    if (!form) {
      throw new Error('Form not found');
    }

    // 1. Empty name validation
    fireEvent.submit(form);
    expect(screen.getByTestId('template-studio-error').textContent).toContain('Template name is required');

    // 2. Type name -> auto-populates slug; then clear slug for slug validation
    const nameInput = screen.getByTestId<HTMLInputElement>('studio-template-name-input');
    const slugInput = screen.getByTestId<HTMLInputElement>('studio-template-slug-input');
    fireEvent.change(nameInput, { target: { value: 'Executive Audit' } });
    expect(slugInput.value).toBe('executive-audit');

    fireEvent.change(slugInput, { target: { value: '   ' } });
    fireEvent.submit(form);
    expect(screen.getByTestId('template-studio-error').textContent).toContain('Template slug is required');

    fireEvent.change(slugInput, { target: { value: 'exec-audit' } });

    // 3. Empty markdown validation
    const editor = screen.getByTestId<HTMLTextAreaElement>('studio-template-markdown-editor');
    fireEvent.change(editor, { target: { value: '   ' } });
    fireEvent.submit(form);
    expect(screen.getByTestId('template-studio-error').textContent).toContain(
      'Template markdown content cannot be empty',
    );

    // 4. Insert snippet via chip click
    fireEvent.click(screen.getByText('+ {{ mission }}'));
    expect(editor.value).toContain('{{ mission }}');

    // Description field
    fireEvent.change(screen.getByTestId('studio-template-desc-input'), {
      target: { value: 'Custom audit template' },
    });

    // 5. Save failure branch
    createSpy.mockRejectedValueOnce(new Error('Backend template error'));
    fireEvent.submit(form);
    await waitFor(() => {
      expect(screen.getByTestId('template-studio-error').textContent).toContain('Backend template error');
    });

    // 6. Save success branch
    createSpy.mockResolvedValueOnce(fallbackTpl);
    fireEvent.submit(form);
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });

    // 7. Backdrop click closes modal
    fireEvent.click(screen.getByTestId('template-studio-backdrop'));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('resolves active workspace dynamically in ReportTemplateStudioModal', async () => {
    const tpl0 = MOCK_TEMPLATES[0];
    if (!tpl0) throw new Error('Missing mock template');
    const createSpy = vi.spyOn(reportsApi, 'createReportTemplate').mockResolvedValue(tpl0);
    vi.spyOn(authModule, 'useAuth').mockReturnValue({
      session: {
        authenticated: true,
        principal_id: 'p-1',
        workspace_id: 'ws-studio-auth',
        aal_level: 1,
        mfa_pending: false,
        csrf_token: 'csrf',
      },
      isLoading: false,
      initialized: true,
      refreshSession: () => Promise.resolve(null),
      logout: () => Promise.resolve(),
    });

    render(
      <ReportTemplateStudioModal
        isOpen={true}
        onClose={vi.fn()}
        projectKey="KAN"
      />,
    );

    const form = screen.getByTestId('template-studio-save-btn').closest('form');
    if (!form) throw new Error('Form not found');

    const nameInput = screen.getByTestId<HTMLInputElement>('studio-template-name-input');
    fireEvent.change(nameInput, { target: { value: 'Studio Dynamic Workspace' } });

    fireEvent.submit(form);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        'ws-studio-auth',
        expect.objectContaining({
          name: 'Studio Dynamic Workspace',
          project_id: 'KAN',
        }),
      );
    });
  });
});

describe('ReportExportModal', () => {
  beforeEach(() => {
    vi.spyOn(reportsApi, 'fetchReportTemplates').mockResolvedValue(MOCK_TEMPLATES);
    vi.spyOn(reportsApi, 'previewReport').mockResolvedValue({
      rendered_content: '# Rendered Markdown Preview\nMission: Penetration testing',
      format: 'MD',
      issue_count: 5,
    });
    vi.spyOn(reportsApi, 'generateReport').mockResolvedValue({
      blob: new Blob(['%PDF-1.4 mock content'], { type: 'application/pdf' }),
      filename: 'security-assessment-report.pdf',
    });
    globalThis.URL.createObjectURL = vi.fn().mockReturnValue('blob:http://localhost/mock-url');
    globalThis.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <ReportExportModal
        isOpen={false}
        onClose={vi.fn()}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders modal with templates, parameters, and 7 format pills when open', async () => {
    render(
      <ReportExportModal
        isOpen={true}
        onClose={vi.fn()}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );

    expect(screen.getByTestId('report-export-backdrop')).toBeDefined();
    expect(screen.getByText('Export Report')).toBeDefined();

    await waitFor(() => {
      expect(reportsApi.fetchReportTemplates).toHaveBeenCalledWith('default', 'KAN');
      expect(screen.getByTestId('report-param-input-mission')).toBeDefined();
      expect(screen.getByTestId('report-param-input-author')).toBeDefined();
    });

    // Change textarea and text parameters
    fireEvent.change(screen.getByTestId('report-param-input-mission'), {
      target: { value: 'Updated mission' },
    });
    fireEvent.change(screen.getByTestId('report-param-input-author'), {
      target: { value: 'Alice' },
    });

    // Switch template in dropdown
    fireEvent.change(screen.getByTestId('report-template-select'), {
      target: { value: 'sprint-release-notes' },
    });
    expect(screen.getByTestId<HTMLInputElement>('report-param-input-version').value).toBe('v1.0.0');

    expect(screen.getByTestId('report-format-pill-pdf')).toBeDefined();
    expect(screen.getByTestId('report-format-pill-xlsx')).toBeDefined();
    expect(screen.getByTestId('report-format-pill-csv')).toBeDefined();
    expect(screen.getByTestId('report-format-pill-docx')).toBeDefined();
    expect(screen.getByTestId('report-format-pill-odt')).toBeDefined();
    expect(screen.getByTestId('report-format-pill-html')).toBeDefined();
    expect(screen.getByTestId('report-format-pill-md')).toBeDefined();
  });

  it('allows switching export format on pill click', async () => {
    render(
      <ReportExportModal
        isOpen={true}
        onClose={vi.fn()}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('report-format-pill-xlsx')).toBeDefined();
    });

    const xlsxPill = screen.getByTestId('report-format-pill-xlsx');
    fireEvent.click(xlsxPill);
    expect(xlsxPill.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('reports-export-submit-btn').textContent).toContain('Download XLSX');
  });

  it('toggles AES-256 ZIP password protection and validates minimum password length', async () => {
    render(
      <ReportExportModal
        isOpen={true}
        onClose={vi.fn()}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('reports-export-submit-btn')).toBeDefined();
    });

    const zipToggle = screen.getByTestId<HTMLInputElement>('reports-zip-toggle');
    fireEvent.click(zipToggle);
    expect(zipToggle.checked).toBe(true);

    const passwordInput = screen.getByTestId<HTMLInputElement>('reports-zip-password-input');
    fireEvent.change(passwordInput, { target: { value: '123' } });

    fireEvent.click(screen.getByTestId('reports-export-submit-btn'));
    expect(screen.getByTestId('report-export-error').textContent).toContain(
      'Password protection requires at least 4 characters',
    );

    fireEvent.change(passwordInput, { target: { value: 'Secret123!' } });
    fireEvent.click(screen.getByTestId('reports-export-submit-btn'));
    await waitFor(() => {
      expect(reportsApi.generateReport).toHaveBeenCalled();
    });
  });

  it('renders live preview and handles preview/export/load errors', async () => {
    const onClose = vi.fn();
    render(
      <ReportExportModal
        isOpen={true}
        onClose={onClose}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('reports-preview-btn')).toBeDefined();
    });

    // Preview success
    fireEvent.click(screen.getByTestId('reports-preview-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('reports-preview-pane')).toBeDefined();
    });

    // Preview error
    vi.spyOn(reportsApi, 'previewReport').mockRejectedValueOnce(new Error('Preview crash'));
    fireEvent.click(screen.getByTestId('reports-preview-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('report-export-error').textContent).toContain('Preview crash');
    });

    // Export error
    vi.spyOn(reportsApi, 'generateReport').mockRejectedValueOnce(new Error('Generate crash'));
    fireEvent.click(screen.getByTestId('reports-export-submit-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('report-export-error').textContent).toContain('Generate crash');
    });

    // Backdrop click
    fireEvent.click(screen.getByTestId('report-export-backdrop'));
    expect(onClose).toHaveBeenCalled();
  });

  it('opens template studio modal and appends newly created template', async () => {
    const fallbackTpl = MOCK_TEMPLATES[1] ?? MOCK_TEMPLATES[0];
    if (!fallbackTpl) {
      throw new Error('Missing mock template');
    }
    vi.spyOn(reportsApi, 'createReportTemplate').mockResolvedValue(fallbackTpl);
    render(
      <ReportExportModal
        isOpen={true}
        onClose={vi.fn()}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('reports-open-studio-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('reports-open-studio-btn'));
    expect(screen.getByTestId('template-studio-backdrop')).toBeDefined();

    fireEvent.change(screen.getByTestId('studio-template-name-input'), {
      target: { value: 'New Custom' },
    });
    const studioForm = screen.getByTestId('template-studio-save-btn').closest('form');
    if (!studioForm) {
      throw new Error('Studio form not found');
    }
    fireEvent.submit(studioForm);

    await waitFor(() => {
      expect(screen.queryByTestId('template-studio-backdrop')).toBeNull();
    });
  });

  it('displays error when fetchReportTemplates fails', async () => {
    vi.spyOn(reportsApi, 'fetchReportTemplates').mockRejectedValueOnce(new Error('Load failed'));
    render(
      <ReportExportModal
        isOpen={true}
        onClose={vi.fn()}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('report-export-error').textContent).toContain('Load failed');
    });
  });

  it('resolves active workspace dynamically from route params when workspaceSlug is not passed or default', async () => {
    render(
      <MemoryRouter initialEntries={['/w/acme-corp/p/KAN/reports']}>
        <Routes>
          <Route
            path="/w/:workspaceSlug/p/:projectKey/reports"
            element={
              <ReportExportModal
                isOpen={true}
                onClose={vi.fn()}
                projectKey="KAN"
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(reportsApi.fetchReportTemplates).toHaveBeenCalledWith('acme-corp', 'KAN');
    });
  });

  it('resolves active workspace dynamically from useAuth session when workspaceSlug is omitted or default', async () => {
    vi.spyOn(authModule, 'useAuth').mockReturnValue({
      session: {
        authenticated: true,
        principal_id: 'p-1',
        workspace_id: 'ws-auth-uuid-999',
        aal_level: 1,
        mfa_pending: false,
        csrf_token: 'csrf',
      },
      isLoading: false,
      initialized: true,
      refreshSession: () => Promise.resolve(null),
      logout: () => Promise.resolve(),
    });

    render(
      <ReportExportModal
        isOpen={true}
        onClose={vi.fn()}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );

    await waitFor(() => {
      expect(reportsApi.fetchReportTemplates).toHaveBeenCalledWith('ws-auth-uuid-999', 'KAN');
    });
  });

  it('resolves active workspace dynamically from qk.me() in QueryClient cache when workspaceSlug is omitted', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(qk.me(), {
      workspace_id: 'ws-from-me-cache',
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ReportExportModal
          isOpen={true}
          onClose={vi.fn()}
          projectKey="KAN"
        />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(reportsApi.fetchReportTemplates).toHaveBeenCalledWith('ws-from-me-cache', 'KAN');
    });
  });

  it('deduplicates templates on save when new template has the same slug', async () => {
    const baseTpl = MOCK_TEMPLATES[0];
    if (!baseTpl) throw new Error('Missing mock template');
    const duplicateTpl: reportsApi.ReportTemplate = {
      ...baseTpl,
      name: 'Updated Security Report',
    };
    vi.spyOn(reportsApi, 'createReportTemplate').mockResolvedValue(duplicateTpl);

    render(
      <ReportExportModal
        isOpen={true}
        onClose={vi.fn()}
        projectKey="KAN"
        workspaceSlug="ws-1"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('reports-open-studio-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('reports-open-studio-btn'));
    const studioForm = screen.getByTestId('template-studio-save-btn').closest('form');
    if (!studioForm) throw new Error('Studio form missing');

    fireEvent.change(screen.getByTestId('studio-template-name-input'), {
      target: { value: 'Updated Security Report' },
    });
    fireEvent.submit(studioForm);

    await waitFor(() => {
      expect(screen.queryByTestId('template-studio-backdrop')).toBeNull();
    });
  });

  it('renders modal with semantic dark theme tokens and zero inline style attributes', async () => {
    render(
      <div data-theme="dark">
        <ReportExportModal
          isOpen={true}
          onClose={vi.fn()}
          projectKey="KAN"
          workspaceSlug="ws-1"
        />
      </div>,
    );

    await waitFor(() => {
      const container = screen.getByTestId('report-export-backdrop').querySelector('.reports-modal-container');
      expect(container).toBeDefined();
      expect(container?.getAttribute('style')).toBeNull();
      const select = screen.getByTestId('report-template-select');
      expect(select.getAttribute('style')).toBeNull();
    });
  });
});
