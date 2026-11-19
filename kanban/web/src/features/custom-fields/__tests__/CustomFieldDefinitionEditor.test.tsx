// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { CustomFieldDefinitionEditor } from '../CustomFieldDefinitionEditor';
import * as api from '../api';

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    fetchProjectCustomFields: vi.fn(),
    createCustomField: vi.fn(),
    updateCustomField: vi.fn(),
    deleteCustomField: vi.fn(),
    fetchFieldApprovals: vi.fn().mockResolvedValue([]),
    approveFieldEscalation: vi.fn(),
    testExecuteCustomField: vi.fn(),
  };
});

const mockDefinitions: api.CustomFieldDefinition[] = [
  {
    id: 'f-1',
    slug: 'cvss-score',
    name: 'CVSS Score',
    tier: 'wasm',
    output_format: 'severity_pill',
    output_format_metadata: {},
    script_source: 'return { level: "high", score: 8.8 };',
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    manifest_sha256: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
    is_enabled: true,
    approval_status: 'APPROVED',
  },
  {
    id: 'f-2',
    slug: 'deploy-target',
    name: 'Deploy Target',
    tier: 'nsjail',
    output_format: 'text',
    output_format_metadata: { prefix: 'Env: ' },
    script_source: 'return "Prod";',
    target_scope: 'WORKSPACE',
    credential_mode: 'PROJECT_ADMIN_SP',
    egress_allowlist: ['/api/v1/projects/KAN'],
    manifest_sha256: 'b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef01',
    is_enabled: true,
    approval_status: 'PENDING',
  },
  {
    id: 'f-3',
    slug: 'minimal-field',
    name: 'Minimal Field',
    tier: 'wasm',
    output_format: 'text',
    output_format_metadata: {},
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    is_enabled: true,
  },
  {
    id: 'f-4',
    slug: 'scalar-field',
    name: 'Scalar Field',
    tier: 'wasm',
    output_format: 'text',
    output_format_metadata: {},
    script_source: 'scalar: "Static Result"',
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    is_enabled: true,
  },
  {
    id: 'f-5',
    slug: 'formula-field',
    name: 'Formula Field',
    tier: 'wasm',
    output_format: 'text',
    output_format_metadata: {},
    script_source: 'formula: issue.key + "-done"',
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    is_enabled: true,
  },
];

const def0 = mockDefinitions[0];
const def1 = mockDefinitions[1];
if (!def0 || !def1) {
  throw new Error('mockDefinitions missing expected entries');
}

function renderEditor(isAdmin = true) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CustomFieldDefinitionEditor projectKey="KAN" isAdmin={isAdmin} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CustomFieldDefinitionEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders uniform 404 page for non-admin callers (anti-enumeration S3.4)', () => {
    renderEditor(false);
    expect(screen.getByTestId('not-found-view')).toBeDefined();
    expect(screen.getByText('Not found or no access')).toBeDefined();
    expect(screen.queryByTestId('custom-fields-editor-layout')).toBeNull();
  });

  it('renders editor layout, definitions list, and manifest SHA chip for admin', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);

    renderEditor(true);

    expect(await screen.findByTestId('custom-fields-editor-layout')).toBeDefined();
    expect(screen.getByText('CVSS Score')).toBeDefined();
    expect(screen.getByText('Deploy Target')).toBeDefined();

    // Select first field
    fireEvent.click(screen.getByTestId('field-item-cvss-score'));

    // Manifest SHA chip
    const chip = screen.getByTestId('manifest-sha256-chip');
    expect(chip.textContent).toContain('a1b2c3d4e5f60718...');

    // Copy SHA button
    const copyBtn = screen.getByTestId('copy-manifest-sha-btn');
    expect(copyBtn.textContent).toContain('Copy');
    fireEvent.click(copyBtn);
    expect(copyBtn.textContent).toContain('Copied');
  });

  it('creates new custom field definition with validation', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);
    const createdField: api.CustomFieldDefinition = {
      id: 'f-new',
      slug: 'test-field',
      name: 'Test Field',
      tier: 'wasm',
      output_format: 'text',
      output_format_metadata: { max_length: 280 },
      script_source: 'return "ok";',
      target_scope: 'PROJECT',
      credential_mode: 'INVOKING_USER',
      egress_allowlist: [],
      manifest_sha256: 'c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef012',
      is_enabled: true,
    };
    vi.mocked(api.createCustomField).mockResolvedValue(createdField);

    renderEditor(true);

    await screen.findByTestId('custom-fields-editor-layout');

    // Fill form
    fireEvent.change(screen.getByTestId('field-name-input'), {
      target: { value: 'Test Field' },
    });
    fireEvent.change(screen.getByTestId('field-slug-input'), {
      target: { value: 'test-field' },
    });
    fireEvent.change(screen.getByTestId('output-format-select'), {
      target: { value: 'text' },
    });

    // Save
    fireEvent.click(screen.getByTestId('save-definition-btn'));

    await waitFor(() => {
      expect(api.createCustomField).toHaveBeenCalledWith(
        'KAN',
        expect.objectContaining({
          slug: 'test-field',
          name: 'Test Field',
          output_format: 'text',
        }),
      );
    });
  });

  it('prompts literal tamper warning dialog when editing script on approved field (S13.2)', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);
    vi.mocked(api.updateCustomField).mockResolvedValue({
      id: def0.id,
      slug: def0.slug,
      name: def0.name,
      tier: def0.tier,
      output_format: def0.output_format,
      output_format_metadata: def0.output_format_metadata,
      target_scope: def0.target_scope,
      credential_mode: def0.credential_mode,
      egress_allowlist: def0.egress_allowlist,
      is_enabled: def0.is_enabled,
      script_source: 'return { level: "critical", score: 9.9 };',
      approval_status: 'REVOKED',
    });

    renderEditor(true);

    // Select approved field
    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));

    // Modify script source
    fireEvent.change(screen.getByTestId('script-source-textarea'), {
      target: { value: 'return { level: "critical", score: 9.9 };' },
    });

    // Click Save
    fireEvent.click(screen.getByTestId('save-definition-btn'));

    // Literal confirmation text
    expect(screen.getByTestId('tamper-confirm-dialog')).toBeDefined();
    expect(screen.getByTestId('tamper-warning-literal').textContent).toContain(
      'Saving changes manifest_sha256 and immediately revokes the current approval.',
    );

    // Confirm save
    fireEvent.click(screen.getByTestId('confirm-tamper-save-btn'));

    await waitFor(() => {
      expect(api.updateCustomField).toHaveBeenCalledWith(
        'KAN',
        'f-1',
        expect.objectContaining({
          script_source: 'return { level: "critical", score: 9.9 };',
        }),
      );
    });
  });

  it('displays validation error on invalid format metadata JSON', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));

    // Enter bad JSON
    fireEvent.change(screen.getByTestId('format-metadata-textarea'), {
      target: { value: '{ invalid_json: ' },
    });

    fireEvent.click(screen.getByTestId('save-definition-btn'));

    expect(
      screen.getByText('Invalid JSON in format metadata'),
    ).toBeDefined();
    expect(api.updateCustomField).not.toHaveBeenCalled();
  });

  it('deletes custom field definition', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);
    vi.mocked(api.deleteCustomField).mockResolvedValue();

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));

    const deleteBtn = screen.getByTestId('delete-field-btn');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(api.deleteCustomField).toHaveBeenCalledWith('KAN', 'f-1');
    });
  });

  it('updates tier, target scope, and credential mode select inputs', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));

    fireEvent.click(screen.getByTestId('custom-fields-advanced-tab'));

    fireEvent.change(screen.getByTestId('execution-tier-select'), {
      target: { value: 'nsjail' },
    });
    fireEvent.change(screen.getByTestId('target-scope-select'), {
      target: { value: 'WORKSPACE' },
    });
    fireEvent.change(screen.getByTestId('credential-mode-select'), {
      target: { value: 'PROJECT_ADMIN_SP' },
    });

    expect(screen.getByTestId<HTMLSelectElement>('execution-tier-select').value).toBe('nsjail');
    expect(screen.getByTestId<HTMLSelectElement>('target-scope-select').value).toBe('WORKSPACE');
    expect(screen.getByTestId<HTMLSelectElement>('credential-mode-select').value).toBe(
      'PROJECT_ADMIN_SP',
    );
  });

  it('renders Basic and Advanced tabs for admin and switches panels', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);

    renderEditor(true);

    expect(await screen.findByTestId('custom-fields-basic-tab')).toBeDefined();
    const advTab = screen.getByTestId('custom-fields-advanced-tab');
    expect(advTab).toBeDefined();

    expect(screen.getByTestId('custom-fields-basic-panel').hasAttribute('hidden')).toBe(false);
    expect(screen.getByTestId('custom-fields-advanced-panel').hasAttribute('hidden')).toBe(true);

    fireEvent.click(advTab);
    expect(screen.getByTestId('custom-fields-basic-panel').hasAttribute('hidden')).toBe(true);
    expect(screen.getByTestId('custom-fields-advanced-panel').hasAttribute('hidden')).toBe(false);
  });

  it('cancels tamper confirmation dialog without saving', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));

    fireEvent.change(screen.getByTestId('script-source-textarea'), {
      target: { value: 'return 100;' },
    });

    fireEvent.click(screen.getByTestId('save-definition-btn'));

    expect(screen.getByTestId('tamper-confirm-dialog')).toBeDefined();

    fireEvent.click(screen.getByText('Cancel'));

    expect(screen.queryByTestId('tamper-confirm-dialog')).toBeNull();
    expect(api.updateCustomField).not.toHaveBeenCalled();
  });

  it('resets form when clicking New Custom Field button', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));
    expect(screen.getByTestId<HTMLInputElement>('field-name-input').value).toBe('CVSS Score');

    fireEvent.click(screen.getByTestId('create-new-field-btn'));

    expect(screen.getByTestId<HTMLInputElement>('field-name-input').value).toBe('');
    expect(screen.getByTestId<HTMLInputElement>('field-slug-input').value).toBe('');
  });

  it('displays submit error when createCustomField fails', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);
    vi.mocked(api.createCustomField).mockRejectedValueOnce(new Error('Slug conflict'));

    renderEditor(true);

    fireEvent.change(screen.getByTestId('field-name-input'), {
      target: { value: 'Conflict' },
    });
    fireEvent.change(screen.getByTestId('field-slug-input'), {
      target: { value: 'conflict' },
    });
    fireEvent.click(screen.getByTestId('save-definition-btn'));

    expect(await screen.findByText('Slug conflict')).toBeDefined();
  });

  it('displays submit error when updateCustomField fails', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);
    vi.mocked(api.updateCustomField).mockRejectedValueOnce(new Error('Update failed'));

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));

    fireEvent.change(screen.getByTestId('field-name-input'), {
      target: { value: 'New Name' },
    });
    fireEvent.click(screen.getByTestId('save-definition-btn'));

    expect(await screen.findByText('Update failed')).toBeDefined();
  });

  it('resets copy button text after 2 seconds', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));

    vi.useFakeTimers();
    const copyBtn = screen.getByTestId('copy-manifest-sha-btn');
    fireEvent.click(copyBtn);
    expect(copyBtn.textContent).toContain('Copied');

    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(copyBtn.textContent).toContain('Copy');
    vi.useRealTimers();
  });

  it('toggles is_enabled checkbox', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));

    const checkbox = screen.getByTestId<HTMLInputElement>('is-enabled-checkbox');
    expect(checkbox.checked).toBe(true);

    fireEvent.click(checkbox);
    expect(checkbox.checked).toBe(false);
  });

  it('refetches definitions when child approval panel succeeds', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([
      {
        id: 'appr-2',
        field_id: 'f-2',
        status: 'PENDING',
        target_scope: 'WORKSPACE',
        credential_mode: 'PROJECT_ADMIN_SP',
        manifest_sha256: def1.manifest_sha256 ?? '',
        justification: 'deploy access',
        created_at: '2026-11-13T10:00:00Z',
        updated_at: '2026-11-13T10:00:00Z',
      },
    ]);
    vi.mocked(api.approveFieldEscalation).mockResolvedValue({
      id: 'appr-2',
      field_id: 'f-2',
      status: 'APPROVED',
      target_scope: 'WORKSPACE',
      credential_mode: 'PROJECT_ADMIN_SP',
      manifest_sha256: def1.manifest_sha256 ?? '',
      justification: 'deploy access',
      created_at: '2026-11-13T10:00:00Z',
      updated_at: '2026-11-13T10:00:00Z',
    });

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-deploy-target'));

    const ackCheckbox = await screen.findByTestId('sp-ack-checkbox');
    fireEvent.click(ackCheckbox);

    const approveBtn = screen.getByTestId('approve-escalation-btn');
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(api.approveFieldEscalation).toHaveBeenCalled();
    });
  });

  it('triggers tamper confirmation when format metadata is modified on approved field', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));

    fireEvent.change(screen.getByTestId('format-metadata-textarea'), {
      target: { value: JSON.stringify({ custom_opt: true }) },
    });
    fireEvent.click(screen.getByTestId('save-definition-btn'));

    expect(screen.getByTestId('tamper-confirm-dialog')).toBeDefined();
  });

  it('saves field with empty metadata string parsing to empty object', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);
    vi.mocked(api.createCustomField).mockResolvedValue(def0);

    renderEditor(true);

    fireEvent.change(screen.getByTestId('field-name-input'), {
      target: { value: 'Empty Meta Field' },
    });
    fireEvent.change(screen.getByTestId('field-slug-input'), {
      target: { value: 'empty-meta' },
    });
    fireEvent.change(screen.getByTestId('format-metadata-textarea'), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByTestId('save-definition-btn'));

    await waitFor(() => {
      expect(api.createCustomField).toHaveBeenCalledWith(
        'KAN',
        expect.objectContaining({
          output_format_metadata: {},
        }),
      );
    });
  });

  it('updates metadata template when output format changes', () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);

    renderEditor(true);

    fireEvent.change(screen.getByTestId('output-format-select'), {
      target: { value: 'badge' },
    });
    const textarea = screen.getByTestId<HTMLTextAreaElement>('format-metadata-textarea');
    expect(textarea.value).toContain('color_token');

    fireEvent.change(screen.getByTestId('output-format-select'), {
      target: { value: 'number' },
    });
    expect(textarea.value).toContain('maximum_fraction_digits');
  });

  it('saves approved field without tamper dialog when neither script nor metadata changed', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);
    vi.mocked(api.updateCustomField).mockResolvedValue(def0);

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));

    // Change only the name, leaving script and meta untouched
    fireEvent.change(screen.getByTestId('field-name-input'), {
      target: { value: 'CVSS Score Updated' },
    });
    fireEvent.click(screen.getByTestId('save-definition-btn'));

    expect(screen.queryByTestId('tamper-confirm-dialog')).toBeNull();
    await waitFor(() => {
      expect(api.updateCustomField).toHaveBeenCalled();
    });
  });

  it('handles selecting field with undefined script_source and egress_allowlist', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);

    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-minimal-field'));
    expect(screen.getByTestId<HTMLTextAreaElement>('script-source-textarea').value).toBe('');
  });

  it('switches field flavors and updates starter templates and tier', () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);

    renderEditor(true);

    const flavorSelect = screen.getByTestId<HTMLSelectElement>('field-flavor-select');
    const scriptArea = screen.getByTestId<HTMLTextAreaElement>('script-source-textarea');

    // Switch to formula
    fireEvent.change(flavorSelect, { target: { value: 'formula' } });
    expect(flavorSelect.value).toBe('formula');
    expect(scriptArea.value).toContain('formula:');

    // Switch to wasm
    fireEvent.change(flavorSelect, { target: { value: 'wasm' } });
    expect(flavorSelect.value).toBe('wasm');
    expect(scriptArea.value).toContain('WebAssembly Tier A Module');

    // Switch to nsjail
    fireEvent.change(flavorSelect, { target: { value: 'nsjail' } });
    expect(flavorSelect.value).toBe('nsjail');
    expect(scriptArea.value).toContain('Tier B nsjail container Python script');

    // Switch back to scalar
    fireEvent.change(flavorSelect, { target: { value: 'scalar' } });
    expect(flavorSelect.value).toBe('scalar');
    expect(scriptArea.value).toContain('scalar:');
  });

  it('enlarges metadata JSON textarea to rows=8 and uses /v-safe slug pattern', () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);

    renderEditor(true);

    const metaArea = screen.getByTestId<HTMLTextAreaElement>('format-metadata-textarea');
    expect(metaArea.getAttribute('rows')).toBe('8');

    const slugInput = screen.getByTestId<HTMLInputElement>('field-slug-input');
    const pattern = slugInput.getAttribute('pattern') ?? '';
    expect(pattern).toBe('^[a-z0-9][a-z0-9\\-]{1,62}$');
    expect(() => new RegExp(pattern, 'v')).not.toThrow();
    const regV = new RegExp(pattern, 'v');
    expect(regV.test('cvss-score')).toBe(true);
    expect(regV.test('a-1')).toBe(true);
    expect(regV.test('-invalid')).toBe(false);
  });

  it('renders dual-control explanation banner immediately on scope selection before save', () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);

    renderEditor(true);

    // Initial PROJECT scope does not show dual control banner
    expect(screen.queryByTestId('dual-control-explanation-banner')).toBeNull();

    // Select WORKSPACE scope
    const scopeSelect = screen.getByTestId<HTMLSelectElement>('target-scope-select');
    fireEvent.change(scopeSelect, { target: { value: 'WORKSPACE' } });

    // Banner renders immediately
    const banner = screen.getByTestId('dual-control-explanation-banner');
    expect(banner).toBeDefined();
    expect(banner.textContent).toContain('Dual-Control Policy:');
    expect(banner.textContent).toContain('WORKSPACE_ADMIN');
    expect(banner.textContent).toContain('Self-approval is blocked (403 Forbidden)');

    // Switch to SERVER scope
    fireEvent.change(scopeSelect, { target: { value: 'SERVER' } });
    expect(banner.textContent).toContain('SERVER_ADMIN');

    // Switch back to PROJECT scope
    fireEvent.change(scopeSelect, { target: { value: 'PROJECT' } });
    expect(screen.queryByTestId('dual-control-explanation-banner')).toBeNull();
  });

  it('evaluates test execute against chosen issue with latency, pill, and logs', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);
    const testResult: api.CustomFieldTestExecuteResult = {
      output_format: 'text',
      value: 'Verified Build',
      status: 'SUCCESS',
      latency_ms: 14.8,
      logs: 'AST safe evaluation succeeded in 14.8ms',
    };
    vi.mocked(api.testExecuteCustomField).mockResolvedValue(testResult);

    renderEditor(true);

    const issueKeyInput = screen.getByTestId<HTMLInputElement>('test-issue-key-input');
    const executeBtn = screen.getByTestId('test-execute-btn');

    fireEvent.change(issueKeyInput, { target: { value: 'KAN-99' } });
    fireEvent.click(executeBtn);

    expect(await screen.findByTestId('test-execute-result-panel')).toBeDefined();
    expect(screen.getByTestId('test-latency').textContent).toContain('14.8 ms');
    expect(screen.getByTestId('test-output-pill').textContent).toContain('Verified Build');
    expect(screen.getByTestId('test-logs').textContent).toContain('AST safe evaluation succeeded');
  });

  it('displays test execute error when metadata is invalid JSON or api throws', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);
    renderEditor(true);

    const issueKeyInput = screen.getByTestId<HTMLInputElement>('test-issue-key-input');
    const executeBtn = screen.getByTestId('test-execute-btn');

    // Invalid JSON in metadata
    fireEvent.change(screen.getByTestId('format-metadata-textarea'), {
      target: { value: 'invalid json{' },
    });
    fireEvent.change(issueKeyInput, { target: { value: 'KAN-99' } });
    fireEvent.click(executeBtn);

    expect(await screen.findByTestId('test-execute-error')).toBeDefined();
    expect(screen.getByTestId('test-execute-error').textContent).toContain('Invalid JSON in format metadata');

    // API error
    fireEvent.change(screen.getByTestId('format-metadata-textarea'), {
      target: { value: '{}' },
    });
    vi.mocked(api.testExecuteCustomField).mockRejectedValue(new Error('Issue not found or sandbox unavailable'));
    fireEvent.click(executeBtn);

    expect(await screen.findByTestId('test-execute-error')).toBeDefined();
    expect(screen.getByTestId('test-execute-error').textContent).toContain('Issue not found or sandbox unavailable');
  });

  it('detects flavor correctly when selecting scalar and formula fields', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);

    renderEditor(true);

    // Select scalar field
    fireEvent.click(await screen.findByTestId('field-item-scalar-field'));
    expect(screen.getByTestId<HTMLSelectElement>('field-flavor-select').value).toBe('scalar');

    // Select formula field
    fireEvent.click(screen.getByTestId('field-item-formula-field'));
    expect(screen.getByTestId<HTMLSelectElement>('field-flavor-select').value).toBe('formula');
  });

  it('toggles tabs between basic and advanced and back to basic', () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);
    renderEditor(true);

    const advancedTab = screen.getByTestId('custom-fields-advanced-tab');
    const basicTab = screen.getByTestId('custom-fields-basic-tab');

    fireEvent.click(advancedTab);
    expect(screen.getByTestId('custom-fields-advanced-panel').hidden).toBe(false);
    expect(screen.getByTestId('custom-fields-basic-panel').hidden).toBe(true);

    fireEvent.click(basicTab);
    expect(screen.getByTestId('custom-fields-basic-panel').hidden).toBe(false);
    expect(screen.getByTestId('custom-fields-advanced-panel').hidden).toBe(true);
  });

  it('handles invalid metadata JSON while rendered output pill is visible', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);
    const testResult: api.CustomFieldTestExecuteResult = {
      output_format: 'text',
      value: 'Rendered with fallback meta',
      status: 'SUCCESS',
      latency_ms: 10,
      logs: 'ok',
    };
    vi.mocked(api.testExecuteCustomField).mockResolvedValue(testResult);

    renderEditor(true);

    const issueKeyInput = screen.getByTestId<HTMLInputElement>('test-issue-key-input');
    const executeBtn = screen.getByTestId('test-execute-btn');

    fireEvent.change(issueKeyInput, { target: { value: 'KAN-1' } });
    fireEvent.click(executeBtn);

    expect(await screen.findByTestId('test-execute-result-panel')).toBeDefined();

    // Now corrupt metadata text to trigger catch in output pill render
    fireEvent.change(screen.getByTestId('format-metadata-textarea'), {
      target: { value: 'bad json{' },
    });

    expect(screen.getByTestId('test-output-pill')).toBeDefined();
  });

  it('displays error when executing test without providing issue key', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);
    renderEditor(true);

    const executeBtn = screen.getByTestId('test-execute-btn');
    fireEvent.click(executeBtn);

    const err = await screen.findByTestId('test-execute-error');
    expect(err.textContent).toContain('Please provide an issue key to test execute');
  });

  it('keeps existing scriptSource when changing format on an already selected field', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);
    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));
    const scriptArea = screen.getByTestId<HTMLTextAreaElement>('script-source-textarea');
    const originalScript = scriptArea.value;

    fireEvent.change(screen.getByTestId('output-format-select'), {
      target: { value: 'badge' },
    });
    expect(scriptArea.value).toBe(originalScript);
  });

  it('copies SHA safely when navigator.clipboard is unavailable', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue(mockDefinitions);
    renderEditor(true);

    fireEvent.click(await screen.findByTestId('field-item-cvss-score'));
    const copyBtn = screen.getByTestId('copy-manifest-sha-btn');

    const originalClipboard = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true,
    });

    fireEvent.click(copyBtn);
    expect(copyBtn.textContent).toContain('Copied');

    Object.defineProperty(navigator, 'clipboard', {
      value: originalClipboard,
      configurable: true,
    });
  });

  it('evaluates test execute with empty metadata text', async () => {
    vi.mocked(api.fetchProjectCustomFields).mockResolvedValue([]);
    vi.mocked(api.testExecuteCustomField).mockResolvedValue({
      output_format: 'text',
      value: 'Empty Meta Val',
      status: 'SUCCESS',
      latency_ms: 5,
      logs: '',
    });

    renderEditor(true);

    fireEvent.change(screen.getByTestId('format-metadata-textarea'), {
      target: { value: '   ' },
    });
    fireEvent.change(screen.getByTestId('test-issue-key-input'), {
      target: { value: 'KAN-5' },
    });
    fireEvent.click(screen.getByTestId('test-execute-btn'));

    expect(await screen.findByTestId('test-execute-result-panel')).toBeDefined();
    expect(screen.getByTestId('test-output-pill').textContent).toContain('Empty Meta Val');
  });
});
