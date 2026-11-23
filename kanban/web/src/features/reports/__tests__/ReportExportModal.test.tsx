/**
 * Copyright 2026 Kanban Platform Contributors
 * Apache-2.0 License. See LICENSE for details.
 *
 * Vitest tests for ReportExportModal (KB-JINJA-REPORTS).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ReportExportModal } from '../ReportExportModal';
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
    is_builtin: true,
    template_markdown: '# Sprint Notes\n{{ issues_table }}',
    parameters_schema_json: [],
    csv_columns_json: [],
    allowed_formats: ['PDF', 'XLSX', 'CSV', 'DOCX', 'ODT', 'HTML', 'MD'],
    created_at: '2026-11-22T00:00:00Z',
    updated_at: '2026-11-22T00:00:00Z',
  },
];

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
    // Mock URL.createObjectURL and URL.revokeObjectURL
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

  it('renders modal with templates and 7 format pills when open', async () => {
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
    });

    // Check that format pills are rendered
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

  it('toggles AES-256 ZIP password protection', () => {
    render(
      <ReportExportModal
        isOpen={true}
        onClose={vi.fn()}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );

    const zipToggle = screen.getByTestId<HTMLInputElement>('reports-zip-toggle');
    expect(zipToggle.checked).toBe(false);
    expect(screen.queryByTestId('reports-zip-password-input')).toBeNull();

    fireEvent.click(zipToggle);
    expect(zipToggle.checked).toBe(true);

    const passwordInput = screen.getByTestId<HTMLInputElement>('reports-zip-password-input');
    expect(passwordInput).toBeDefined();

    fireEvent.change(passwordInput, { target: { value: 'Secret123!' } });
    expect(passwordInput.value).toBe('Secret123!');
  });

  it('renders live preview on preview button click', async () => {
    render(
      <ReportExportModal
        isOpen={true}
        onClose={vi.fn()}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('reports-preview-btn')).toBeDefined();
    });

    const previewBtn = screen.getByTestId('reports-preview-btn');
    fireEvent.click(previewBtn);

    await waitFor(() => {
      expect(reportsApi.previewReport).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByTestId('reports-preview-pane')).toBeDefined();
      expect(screen.getByText(/Rendered Markdown Preview/)).toBeDefined();
    });
  });

  it('triggers export and download on submit', async () => {
    const handleClose = vi.fn();
    render(
      <ReportExportModal
        isOpen={true}
        onClose={handleClose}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('reports-export-submit-btn')).toBeDefined();
    });

    const exportBtn = screen.getByTestId('reports-export-submit-btn');
    fireEvent.click(exportBtn);

    await waitFor(() => {
      expect(reportsApi.generateReport).toHaveBeenCalled();
      expect(handleClose).toHaveBeenCalled();
    });
  });

  it('opens template studio modal on studio button click', () => {
    render(
      <ReportExportModal
        isOpen={true}
        onClose={vi.fn()}
        projectKey="KAN"
        workspaceSlug="default"
      />,
    );

    const studioBtn = screen.getByTestId('reports-open-studio-btn');
    fireEvent.click(studioBtn);

    expect(screen.getByTestId('template-studio-backdrop')).toBeDefined();
    expect(screen.getByText('Report Template Studio')).toBeDefined();
  });
});
