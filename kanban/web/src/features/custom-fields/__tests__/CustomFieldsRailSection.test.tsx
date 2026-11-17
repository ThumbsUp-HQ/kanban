// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CustomFieldsRailSection } from '../CustomFieldsRailSection';
import * as api from '../api';

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    fetchProjectCustomFields: vi.fn(),
    fetchIssueCustomFields: vi.fn(),
    executeCustomField: vi.fn(),
  };
});

const mockDefinitions: api.CustomFieldDefinition[] = [
  {
    id: 'f-cvss',
    slug: 'cvss-score',
    name: 'CVSS Score',
    tier: 'wasm',
    output_format: 'severity_pill',
    output_format_metadata: {},
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    is_enabled: true,
  },
  {
    id: 'f-env',
    slug: 'target-env',
    name: 'Target Environment',
    tier: 'nsjail',
    output_format: 'text',
    output_format_metadata: { prefix: 'Env: ' },
    target_scope: 'WORKSPACE',
    credential_mode: 'PROJECT_ADMIN_SP',
    egress_allowlist: [],
    is_enabled: true,
  },
];

const mockResults: api.CustomFieldExecutionResult[] = [
  {
    field_id: 'f-cvss',
    field_slug: 'cvss-score',
    field_name: 'CVSS Score',
    output_format: 'severity_pill',
    value: { level: 'high', score: 8.8, label: 'High' },
    status: 'SUCCESS',
    tier: 'Wasmtime',
    token_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    last_latency_ms: 12,
    computed_at: '2026-11-13T12:00:00Z',
  },
  {
    field_id: 'f-env',
    field_slug: 'target-env',
    field_name: 'Target Environment',
    output_format: 'text',
    value: 'Staging',
    status: 'SUCCESS',
    tier: 'nsjail',
    token_scope: 'WORKSPACE',
    credential_mode: 'PROJECT_ADMIN_SP',
    last_latency_ms: 45,
    computed_at: '2026-11-13T12:00:00Z',
  },
];

const firstDef = mockDefinitions[0];
const firstRes = mockResults[0];
if (!firstDef || !firstRes) {
  throw new Error('mock definitions/results not populated');
}

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe('CustomFieldsRailSection', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('does NOT mount section when project has 0 custom fields (S7.1)', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);
    vi.mocked(api.fetchIssueCustomFields).mockResolvedValue([]);

    const { container } = renderWithQuery(
      <CustomFieldsRailSection projectKey="KAN" issueKey="KAN-42" />,
    );

    await waitFor(() => {
      expect(api.fetchProjectCustomFields).toHaveBeenCalledWith('KAN');
    });

    expect(screen.queryByTestId('custom-fields-rail-section')).toBeNull();
    expect(container.firstChild).toBeNull();
  });

  it('renders literal section header and rows with 🧪 popover metadata', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);
    vi.mocked(api.fetchIssueCustomFields).mockResolvedValue(mockResults);

    renderWithQuery(<CustomFieldsRailSection projectKey="KAN" issueKey="KAN-42" />);

    // Literal section header
    const heading = await screen.findByRole('heading', {
      name: 'Custom Fields (Admin-Defined 🧪)',
    });
    expect(heading).toBeDefined();

    // Field labels and values
    expect(screen.getByText('CVSS Score')).toBeDefined();
    expect(screen.getByText('Target Environment')).toBeDefined();
    const cvssVal = await screen.findByTestId('custom-field-value-cvss-score');
    expect(cvssVal.textContent).toContain('8.8');
    expect(cvssVal.textContent).toContain('High');
    expect(screen.getByTestId('custom-field-value-target-env').textContent).toContain('Env: Staging');

    // EmojiHint popover content
    const hintTrigger = screen.getByTestId('custom-field-emoji-hint-cvss-score');
    act(() => {
      hintTrigger.focus();
    });
    const popover = await screen.findByTestId('custom-field-hint-popover-cvss-score');
    expect(popover.textContent).toContain('Tier: Wasmtime');
    expect(popover.textContent).toContain('Scope: PROJECT');
    expect(popover.textContent).toContain('Principal: INVOKING_USER');
    expect(popover.textContent).toContain('Latency: 12ms');
  });

  it('deduplicates rapid double-click on refresh sending exactly 1 execute request', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);
    vi.mocked(api.fetchIssueCustomFields).mockResolvedValue(mockResults);

    let resolveExecution!: (res: api.CustomFieldExecutionResult) => void;
    const executionPromise = new Promise<api.CustomFieldExecutionResult>((resolve) => {
      resolveExecution = resolve;
    });
    vi.mocked(api.executeCustomField).mockImplementation(() => executionPromise);

    renderWithQuery(<CustomFieldsRailSection projectKey="KAN" issueKey="KAN-42" />);

    const refreshBtn = await screen.findByTestId<HTMLButtonElement>('refresh-field-cvss-score');
    expect(refreshBtn.getAttribute('aria-label')).toBe('Refresh CVSS Score');
    expect(refreshBtn.getAttribute('aria-busy')).toBe('false');

    // Rapid double click
    fireEvent.click(refreshBtn);
    fireEvent.click(refreshBtn);

    // Only 1 execution dispatched
    await waitFor(() => {
      expect(api.executeCustomField).toHaveBeenCalledTimes(1);
    });
    expect(api.executeCustomField).toHaveBeenCalledWith('KAN-42', 'f-cvss');

    // While in flight: aria-busy is true and disabled
    expect(refreshBtn.getAttribute('aria-busy')).toBe('true');
    expect(refreshBtn.disabled).toBe(true);

    // Resolve execution with updated value
    const baseRes = firstRes;
    resolveExecution({
      field_id: baseRes.field_id,
      field_slug: baseRes.field_slug,
      field_name: baseRes.field_name,
      output_format: baseRes.output_format,
      value: { level: 'critical', score: 9.8, label: 'Critical' },
      status: baseRes.status,
      tier: baseRes.tier,
      token_scope: baseRes.token_scope,
      credential_mode: baseRes.credential_mode,
      last_latency_ms: 8,
      computed_at: baseRes.computed_at,
    });

    await waitFor(() => {
      expect(refreshBtn.getAttribute('aria-busy')).toBe('false');
      expect(refreshBtn.disabled).toBe(false);
    });

    expect(screen.getByTestId('custom-field-value-cvss-score').textContent).toContain('9.8');
    expect(screen.getByTestId('custom-field-value-cvss-score').textContent).toContain('Critical');
  });

  it('maps server error codes to inline text without alerts and never leaks detail', async () => {
    const errorResults: api.CustomFieldExecutionResult[] = [
      {
        field_id: 'f-cvss',
        field_slug: 'cvss-score',
        field_name: 'CVSS Score',
        output_format: 'severity_pill',
        value: null,
        status: 'ERROR',
        error_code: 'SCRIPT_TIMEOUT',
        error_message: 'Internal stack trace: thread killed at line 42',
        tier: 'Wasmtime',
        token_scope: 'PROJECT',
        credential_mode: 'INVOKING_USER',
        last_latency_ms: 1005,
        computed_at: '2026-11-13T12:00:00Z',
      },
      {
        field_id: 'f-env',
        field_slug: 'target-env',
        field_name: 'Target Environment',
        output_format: 'text',
        value: null,
        status: 'ERROR',
        error_code: 'APPROVAL_REVOKED',
        error_message: 'Secret token leak in stdout',
        tier: 'nsjail',
        token_scope: 'WORKSPACE',
        credential_mode: 'PROJECT_ADMIN_SP',
        last_latency_ms: 2,
        computed_at: '2026-11-13T12:00:00Z',
      },
    ];

    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);
    vi.mocked(api.fetchIssueCustomFields).mockResolvedValue(errorResults);

    renderWithQuery(<CustomFieldsRailSection projectKey="KAN" issueKey="KAN-42" />);

    // Literal error mappings
    const err1 = await screen.findByTestId('custom-field-error-cvss-score');
    expect(err1.textContent).toBe('Timed out');
    const err2 = screen.getByTestId('custom-field-error-target-env');
    expect(err2.textContent).toBe('Approval revoked - admin re-sign required');

    // Verify raw backend error messages/details are NEVER leaked
    expect(screen.queryByText(/thread killed at line 42/)).toBeNull();
    expect(screen.queryByText(/Secret token leak in stdout/)).toBeNull();
  });

  it('maps other error codes (SCRIPT_FUEL_EXHAUSTED, STANDALONE, unknown) to mapped inline text', async () => {
    const errorCodes = [
      { code: 'SCRIPT_FUEL_EXHAUSTED', expected: 'Compute limit reached' },
      {
        code: 'SANDBOX_UNAVAILABLE_IN_STANDALONE',
        expected: 'Optional CLI Sandbox not enabled in single-container mode',
      },
      { code: 'INTERNAL_EXCEPTION_XYZ', expected: 'Unavailable' },
    ];

    for (const item of errorCodes) {
      const res: api.CustomFieldExecutionResult[] = [
        {
          field_id: 'f-cvss',
          field_slug: 'cvss-score',
          field_name: 'CVSS Score',
          output_format: 'severity_pill',
          value: null,
          status: 'ERROR',
          error_code: item.code,
          tier: 'Wasmtime',
          token_scope: 'PROJECT',
          credential_mode: 'INVOKING_USER',
          last_latency_ms: 10,
          computed_at: '2026-11-13T12:00:00Z',
        },
      ];

      vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([firstDef]);
      vi.mocked(api.fetchIssueCustomFields).mockResolvedValue(res);

      const { unmount } = renderWithQuery(
        <CustomFieldsRailSection projectKey="KAN" issueKey="KAN-42" />,
      );

      const err = await screen.findByTestId('custom-field-error-cvss-score');
      expect(err.textContent).toBe(item.expected);
      unmount();
    }
  });

  it('renders Uncomputed when field execution result is not found', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([firstDef]);
    vi.mocked(api.fetchIssueCustomFields).mockResolvedValue([]);

    renderWithQuery(<CustomFieldsRailSection projectKey="KAN" issueKey="KAN-42" />);

    const uncomputed = await screen.findByTestId('custom-field-uncomputed-cvss-score');
    expect(uncomputed.textContent).toBe('Uncomputed');
  });

  it('updates query cache when refreshing a previously uncomputed field', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([firstDef]);
    vi.mocked(api.fetchIssueCustomFields).mockResolvedValue([]);
    vi.mocked(api.executeCustomField).mockResolvedValue(firstRes);

    renderWithQuery(<CustomFieldsRailSection projectKey="KAN" issueKey="KAN-42" />);

    const refreshBtn = await screen.findByTestId('refresh-field-cvss-score');
    fireEvent.click(refreshBtn);

    const val = await screen.findByTestId('custom-field-value-cvss-score');
    expect(val.textContent).toContain('8.8');
  });

  it('renders null when mounted without QueryClientProvider', () => {
    const { container } = render(<CustomFieldsRailSection projectKey="KAN" issueKey="KAN-42" />);
    expect(container.firstChild).toBeNull();
  });
});
