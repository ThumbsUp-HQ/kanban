// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EscalationApprovalPanel } from '../EscalationApprovalPanel';
import * as api from '../api';

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    fetchFieldApprovals: vi.fn(),
    requestFieldApproval: vi.fn(),
    approveFieldEscalation: vi.fn(),
  };
});

const elevatedFieldSp: api.CustomFieldDefinition = {
  id: 'f-sp',
  slug: 'project-sp-field',
  name: 'Project SP Field',
  tier: 'wasm',
  output_format: 'text',
  output_format_metadata: {},
  target_scope: 'PROJECT',
  credential_mode: 'PROJECT_ADMIN_SP',
  egress_allowlist: [],
  manifest_sha256: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
  is_enabled: true,
};

const elevatedFieldWs: api.CustomFieldDefinition = {
  id: 'f-ws',
  slug: 'workspace-field',
  name: 'Workspace Field',
  tier: 'nsjail',
  output_format: 'text',
  output_format_metadata: {},
  target_scope: 'WORKSPACE',
  credential_mode: 'INVOKING_USER',
  egress_allowlist: [],
  manifest_sha256: 'b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef01',
  is_enabled: true,
};

const pendingApproval: api.CustomFieldApproval = {
  id: 'appr-1',
  field_id: 'f-sp',
  status: 'PENDING',
  target_scope: 'PROJECT',
  credential_mode: 'PROJECT_ADMIN_SP',
  manifest_sha256: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
  justification: 'Automated CI/CD integration token required',
  created_at: '2026-11-13T10:00:00Z',
  updated_at: '2026-11-13T10:00:00Z',
};

function renderPanel(props: React.ComponentProps<typeof EscalationApprovalPanel>) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <EscalationApprovalPanel {...props} />
    </QueryClientProvider>,
  );
}

describe('EscalationApprovalPanel', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders literal SP warning banner for PROJECT_ADMIN_SP', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([]);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    const banner = await screen.findByTestId('sp-warning-banner');
    expect(banner.textContent).toContain(
      '⚠️ This field will run with Project Admin service-principal credentials for every viewer.',
    );
  });

  it('hides Approve button when caller tier is below required approver tier (S13.2)', async () => {
    // Field requires WORKSPACE_ADMIN, caller is only PROJECT_ADMIN
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([
      { ...pendingApproval, field_id: 'f-ws', target_scope: 'WORKSPACE' },
    ]);

    renderPanel({
      field: elevatedFieldWs,
      callerTier: 'PROJECT_ADMIN', // Below WORKSPACE_ADMIN
    });

    await screen.findByTestId('escalation-approval-panel');

    // Approve button MUST be absent from DOM (not merely disabled)
    expect(screen.queryByTestId('approve-escalation-btn')).toBeNull();
  });

  it('shows Approve button when caller tier meets required approver tier', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([
      { ...pendingApproval, field_id: 'f-ws', target_scope: 'WORKSPACE' },
    ]);

    renderPanel({
      field: elevatedFieldWs,
      callerTier: 'WORKSPACE_ADMIN', // Meets required tier
    });

    expect(await screen.findByTestId('approve-escalation-btn')).toBeDefined();
  });

  it('submits approval request with justification', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([]);
    vi.mocked(api.requestFieldApproval).mockResolvedValue(pendingApproval);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    const reqBtn = await screen.findByTestId('request-approval-btn');
    fireEvent.click(reqBtn);

    const input = screen.getByTestId('approval-justification-input');
    fireEvent.change(input, {
      target: { value: 'This is a valid business justification for the ticket' },
    });

    fireEvent.click(screen.getByTestId('submit-approval-request-btn'));

    await waitFor(() => {
      expect(api.requestFieldApproval).toHaveBeenCalledWith(
        'f-sp',
        expect.objectContaining({
          manifest_sha256: elevatedFieldSp.manifest_sha256,
          justification: 'This is a valid business justification for the ticket',
        }),
      );
    });
  });

  it('handles 403 AAL2_REQUIRED opening step-up prompt and retries once', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([pendingApproval]);

    const aal2Error = api.createApiError('AAL2 authentication required', 403, 'AAL2_REQUIRED');

    vi.mocked(api.approveFieldEscalation)
      .mockRejectedValueOnce(aal2Error)
      .mockResolvedValueOnce({
        ...pendingApproval,
        status: 'APPROVED',
      });

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    // Check acknowledgment checkbox (required for SP mode)
    const checkbox = await screen.findByTestId('sp-ack-checkbox');
    fireEvent.click(checkbox);

    // Click Approve
    const approveBtn = screen.getByTestId('approve-escalation-btn');
    fireEvent.click(approveBtn);

    // AAL2 Step-Up Modal appears
    expect(await screen.findByTestId('aal2-stepup-modal')).toBeDefined();

    // Enter OTP code and submit
    fireEvent.change(screen.getByTestId('aal2-otp-input'), {
      target: { value: '123456' },
    });
    fireEvent.click(screen.getByTestId('aal2-verify-btn'));

    // Retried approval
    await waitFor(() => {
      expect(api.approveFieldEscalation).toHaveBeenCalledTimes(2);
    });
  });

  it('handles 409 MANIFEST_MISMATCH disabling Approve with literal message', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([pendingApproval]);

    const mismatchError = api.createApiError('Manifest mismatch', 409, 'MANIFEST_MISMATCH');

    vi.mocked(api.approveFieldEscalation).mockRejectedValueOnce(mismatchError);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    fireEvent.click(await screen.findByTestId('sp-ack-checkbox'));

    const approveBtn = screen.getByTestId('approve-escalation-btn');
    fireEvent.click(approveBtn);

    // Literal mismatch message rendered
    const banner = await screen.findByTestId('manifest-mismatch-banner');
    expect(banner.textContent).toContain(
      'Definition changed since you opened it - reload to review',
    );

    // Approve button is disabled
    expect((approveBtn as HTMLButtonElement).disabled).toBe(true);
  });

  it('triggers onAal2Challenge callback if provided and retries on true', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([pendingApproval]);

    const aal2Error = api.createApiError('AAL2 authentication required', 403, 'AAL2_REQUIRED');

    vi.mocked(api.approveFieldEscalation)
      .mockRejectedValueOnce(aal2Error)
      .mockResolvedValueOnce({
        ...pendingApproval,
        status: 'APPROVED',
      });

    const onAal2Challenge = vi.fn().mockResolvedValue(true);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
      onAal2Challenge,
    });

    fireEvent.click(await screen.findByTestId('sp-ack-checkbox'));
    fireEvent.click(screen.getByTestId('approve-escalation-btn'));

    await waitFor(() => {
      expect(onAal2Challenge).toHaveBeenCalledTimes(1);
      expect(api.approveFieldEscalation).toHaveBeenCalledTimes(2);
    });
  });

  it('opens AAL2 modal when onAal2Challenge returns false or rejects', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([pendingApproval]);

    const aal2Error = api.createApiError('AAL2 authentication required', 403, 'AAL2_REQUIRED');

    vi.mocked(api.approveFieldEscalation).mockRejectedValueOnce(aal2Error);

    const onAal2Challenge = vi.fn().mockResolvedValue(false);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
      onAal2Challenge,
    });

    fireEvent.click(await screen.findByTestId('sp-ack-checkbox'));
    fireEvent.click(screen.getByTestId('approve-escalation-btn'));

    expect(await screen.findByTestId('aal2-stepup-modal')).toBeDefined();
  });

  it('ignores AAL2 form submit when OTP code has fewer than 6 characters', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([pendingApproval]);

    const aal2Error = api.createApiError('AAL2 authentication required', 403, 'AAL2_REQUIRED');
    vi.mocked(api.approveFieldEscalation).mockRejectedValueOnce(aal2Error);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    fireEvent.click(await screen.findByTestId('sp-ack-checkbox'));
    fireEvent.click(screen.getByTestId('approve-escalation-btn'));
    expect(await screen.findByTestId('aal2-stepup-modal')).toBeDefined();

    // Enter only 3 characters
    fireEvent.change(screen.getByTestId('aal2-otp-input'), {
      target: { value: '123' },
    });
    fireEvent.click(screen.getByTestId('aal2-verify-btn'));

    // Did not retry approval
    expect(api.approveFieldEscalation).toHaveBeenCalledTimes(1);
  });

  it('allows canceling request approval modal', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([]);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    fireEvent.click(await screen.findByTestId('request-approval-btn'));
    expect(screen.getByTestId('approval-justification-input')).toBeDefined();
    fireEvent.click(screen.getByTestId('cancel-request-btn'));
    expect(screen.queryByTestId('approval-justification-input')).toBeNull();
  });

  it('allows canceling AAL2 modal', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([pendingApproval]);

    const aal2Error = api.createApiError('AAL2 authentication required', 403, 'AAL2_REQUIRED');
    vi.mocked(api.approveFieldEscalation).mockRejectedValueOnce(aal2Error);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    fireEvent.click(await screen.findByTestId('sp-ack-checkbox'));
    fireEvent.click(screen.getByTestId('approve-escalation-btn'));
    expect(await screen.findByTestId('aal2-stepup-modal')).toBeDefined();
    fireEvent.click(screen.getByTestId('cancel-aal2-btn'));
    expect(screen.queryByTestId('aal2-stepup-modal')).toBeNull();
  });

  it('renders SERVER_ADMIN tier and dual control note for SERVER scope (S13.2)', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([]);

    const serverField: api.CustomFieldDefinition = {
      ...elevatedFieldWs,
      id: 'f-srv',
      target_scope: 'SERVER',
    };

    renderPanel({
      field: serverField,
      callerTier: 'SERVER_ADMIN',
    });

    const panel = await screen.findByTestId('escalation-approval-panel');
    expect(panel.textContent).toContain('SERVER_ADMIN');
    expect(panel.textContent).toContain('(Dual-Control Required)');
  });

  it('displays general error when requestFieldApproval fails', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([]);
    vi.mocked(api.requestFieldApproval).mockRejectedValueOnce(new Error('Quota exceeded'));

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    fireEvent.click(await screen.findByTestId('request-approval-btn'));
    fireEvent.change(screen.getByTestId('approval-justification-input'), {
      target: { value: 'Valid business justification here' },
    });
    fireEvent.click(screen.getByTestId('submit-approval-request-btn'));

    expect(await screen.findByText('Quota exceeded')).toBeDefined();
  });

  it('displays general error when approval fails with 500 error', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([pendingApproval]);
    vi.mocked(api.approveFieldEscalation).mockRejectedValueOnce(
      new Error('Internal database timeout'),
    );

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    fireEvent.click(await screen.findByTestId('sp-ack-checkbox'));
    fireEvent.click(screen.getByTestId('approve-escalation-btn'));

    expect(await screen.findByText('Internal database timeout')).toBeDefined();
  });

  it('renders approved status and badge when status is APPROVED', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([
      { ...pendingApproval, status: 'APPROVED' },
    ]);

    renderPanel({
      field: { ...elevatedFieldSp, approval_status: 'APPROVED' },
      callerTier: 'PROJECT_ADMIN',
    });

    const chip = await screen.findByTestId('approval-status-chip');
    expect(chip.textContent).toContain('Approved');
  });

  it('calls onApproved callback when approveFieldEscalation succeeds', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([pendingApproval]);
    vi.mocked(api.approveFieldEscalation).mockResolvedValue({
      ...pendingApproval,
      status: 'APPROVED',
    });

    const onApproved = vi.fn();

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
      onApproved,
    });

    fireEvent.click(await screen.findByTestId('sp-ack-checkbox'));
    fireEvent.click(screen.getByTestId('approve-escalation-btn'));

    await waitFor(() => {
      expect(onApproved).toHaveBeenCalledTimes(1);
    });
  });

  it('renders pending second approver and revoked status chips', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([
      { ...pendingApproval, status: 'PENDING_SECOND_APPROVER' },
    ]);

    const { unmount } = renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    const chip1 = await screen.findByTestId('approval-status-chip');
    expect(chip1.textContent).toContain('Pending second approver');
    unmount();

    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([
      { ...pendingApproval, status: 'REVOKED' },
    ]);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    const chip2 = await screen.findByTestId('approval-status-chip');
    expect(chip2.textContent).toContain('Revoked');
  });

  it('approves field with null manifest_sha256 using empty string fallback', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([
      { ...pendingApproval, manifest_sha256: '' },
    ]);
    vi.mocked(api.approveFieldEscalation).mockResolvedValue({
      ...pendingApproval,
      status: 'APPROVED',
    });

    const fieldWithoutSha: api.CustomFieldDefinition = {
      ...elevatedFieldSp,
      manifest_sha256: null,
    };

    renderPanel({
      field: fieldWithoutSha,
      callerTier: 'PROJECT_ADMIN',
    });

    fireEvent.click(await screen.findByTestId('sp-ack-checkbox'));
    fireEvent.click(screen.getByTestId('approve-escalation-btn'));

    await waitFor(() => {
      expect(api.approveFieldEscalation).toHaveBeenCalledWith(
        'appr-1',
        expect.objectContaining({ manifest_sha256: '' }),
      );
    });
  });

  it('displays Submitting... while request approval mutation is in flight', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([]);
    let resolveRequest!: (val: api.CustomFieldApproval) => void;
    vi.mocked(api.requestFieldApproval).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }),
    );

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    fireEvent.click(await screen.findByTestId('request-approval-btn'));
    fireEvent.change(screen.getByTestId('approval-justification-input'), {
      target: { value: 'Valid justification with > 10 chars' },
    });

    const submitBtn = screen.getByTestId('submit-approval-request-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByTestId('submit-approval-request-btn').textContent).toBe('Submitting...');
    });
    act(() => {
      resolveRequest(pendingApproval);
    });
  });

  it('renders dual-control explanation banner when approval status is PENDING or PENDING_SECOND_APPROVER', async () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([pendingApproval]);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    const banner = await screen.findByTestId('dual-control-explanation-banner');
    expect(banner).toBeDefined();
    expect(banner.textContent).toContain('Dual-Control Policy:');
    expect(banner.textContent).toContain('Self-approval is blocked (403 Forbidden)');
  });

  it('handles MEMBER caller tier and cannot approve', () => {
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([pendingApproval]);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'MEMBER',
    });

    expect(screen.queryByTestId('approve-escalation-btn')).toBeNull();
  });

  it('updates query cache when requesting approval on a field with existing revoked approval', async () => {
    const revokedApproval: api.CustomFieldApproval = {
      ...pendingApproval,
      id: 'appr-revoked',
      status: 'REVOKED',
    };
    vi.mocked(api.fetchFieldApprovals).mockResolvedValue([revokedApproval]);
    vi.mocked(api.requestFieldApproval).mockResolvedValue(pendingApproval);

    renderPanel({
      field: elevatedFieldSp,
      callerTier: 'PROJECT_ADMIN',
    });

    fireEvent.click(await screen.findByTestId('request-approval-btn'));
    fireEvent.change(screen.getByTestId('approval-justification-input'), {
      target: { value: 'New justification for re-approval' },
    });
    fireEvent.click(screen.getByTestId('submit-approval-request-btn'));

    await waitFor(() => {
      expect(api.requestFieldApproval).toHaveBeenCalled();
    });
  });
});
