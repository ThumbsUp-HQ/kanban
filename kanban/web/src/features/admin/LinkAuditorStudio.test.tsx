// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { LinkAuditorStudio, formatEntitySummary } from './LinkAuditorStudio';
import { apiFetch, Aal2StepUpCancelledError } from '../../api/client';

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>(
    '../../api/client',
  );
  return {
    ...actual,
    apiFetch: vi.fn(),
    getCsrfToken: vi.fn(() => 'csrf-mock-token'),
  };
});

const mockAdminUser = {
  id: 'usr-admin-1',
  email: 'admin@example.com',
  is_server_admin: true,
  is_workspace_admin: true,
  aal_level: 2,
  auth_aal: 'aal2',
};

const mockNonAdminUser = {
  id: 'usr-member-1',
  email: 'member@example.com',
  is_server_admin: false,
  is_workspace_admin: false,
  workspace_role: 'MEMBER',
  aal_level: 1,
  auth_aal: 'aal1',
};

const mockAuditItems = [
  {
    id: 'aud-1',
    workspace_id: 'ws-1',
    link_id: 'lnk-1',
    reason: 'DANGLING_TARGET',
    detected_at: '2026-11-18T12:00:00Z',
    purged_at: null,
    resolved_at: null,
    link_snapshot: {
      source_id: 'iss-1',
      target_id: 'iss-999-dangling',
      link_type: 'BLOCKS',
    },
    source_snapshot: {
      id: 'iss-1',
      canonical_key: 'KAN-142',
      title: 'Fix access checks',
      kind: 'issue',
    },
    target_snapshot: null,
  },
  {
    id: 'aud-2',
    workspace_id: 'ws-1',
    link_id: 'lnk-2',
    reason: 'SOFT_DELETED_ENDPOINT',
    detected_at: '2026-11-18T13:00:00Z',
    purged_at: null,
    resolved_at: null,
    link_snapshot: {
      source_id: 'iss-2',
      target_id: 'iss-3',
      link_type: 'RELATES_TO',
    },
    source_snapshot: {
      id: 'iss-2',
      canonical_key: 'KAN-143',
      title: 'Active issue',
      kind: 'issue',
    },
    target_snapshot: {
      id: 'iss-3',
      canonical_key: 'KAN-99',
      title: 'Soft-deleted ticket',
      kind: 'issue',
      deleted_at: '2026-11-17T00:00:00Z',
    },
  },
  {
    id: 'aud-3',
    workspace_id: 'ws-1',
    link_id: 'lnk-3',
    reason: 'CROSS_WORKSPACE_LEAK',
    detected_at: '2026-11-18T14:00:00Z',
    purged_at: '2026-11-18T15:00:00Z',
    resolved_at: null,
    link_snapshot: {
      source_id: 'iss-10',
      target_id: 'iss-20',
      link_type: 'PARENT_OF',
    },
    source_snapshot: {
      id: 'iss-10',
      canonical_key: 'KAN-200',
      title: 'Source cross ticket',
    },
    target_snapshot: {
      id: 'iss-20',
      canonical_key: 'OTHER-1',
      title: 'Cross workspace target',
    },
  },
  {
    id: 'aud-unknown',
    workspace_id: 'ws-1',
    link_id: 'lnk-unknown',
    reason: 'UNKNOWN_FUTURE_REASON',
    detected_at: '2026-11-18T15:00:00Z',
    purged_at: null,
    resolved_at: null,
    link_snapshot: { source_id: 'iss-unk', target_id: 'iss-unk-2' },
    source_snapshot: null,
    target_snapshot: null,
  },
];

describe('LinkAuditorStudio', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
  });

  it('renders uniform 404 view for non-admin users without leaking existence', async () => {
    vi.mocked(apiFetch).mockImplementation(async (_method, path) => {
      await Promise.resolve();
      await Promise.resolve();
      if (path === '/api/v1/auth/me') {
        return mockNonAdminUser;
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('not-found-view')).toBeDefined();
      expect(screen.getByText(/Not found or no access/i)).toBeDefined();
    });
    expect(screen.queryByTestId('link-auditor-studio')).toBeNull();
  });

  it('renders studio and loads flagged link audits for authorized admin', async () => {
    vi.mocked(apiFetch).mockImplementation(async (_method, path) => {
      await Promise.resolve();
      await Promise.resolve();
      if (path === '/api/v1/auth/me') {
        return mockAdminUser;
      }
      if (path === '/api/v1/admin/object-links/audits') {
        return {
          items: mockAuditItems,
          has_more: false,
          total: 3,
        };
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('link-auditor-studio')).toBeDefined();
    });

    expect(
      screen.getByText(/Invalid Object Link Auditor & Purger/i),
    ).toBeDefined();
    expect(screen.getByTestId('run-scan-btn')).toBeDefined();
    expect(screen.getByTestId('audit-links-table')).toBeDefined();

    // Verify row items
    await waitFor(() => {
      expect(screen.getByText(/KAN-142: Fix access checks/i)).toBeDefined();
      expect(screen.getByText(/Dangling Target \(iss-999-\.\.\.\)/i)).toBeDefined();
      expect(screen.getAllByText('Dangling Target').length).toBe(2);
      expect(screen.getAllByText('Soft-Deleted Endpoint').length).toBe(2);
      expect(screen.getAllByText('Purged').length).toBe(2);
      expect(screen.getByText('UNKNOWN_FUTURE_REASON')).toBeDefined();
      expect(screen.getAllByText('Flagged').length).toBe(3);
    });
  });

  it('triggers integrity scan and updates breakdown metrics', async () => {
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/auth/me') {
        return mockAdminUser;
      }
      if (path === '/api/v1/admin/object-links/audits') {
        return { items: mockAuditItems, has_more: false };
      }
      if (method === 'POST' && path === '/api/v1/admin/object-links:audit') {
        return {
          flagged_total: 42,
          by_reason: {
            DANGLING_SOURCE: 5,
            DANGLING_TARGET: 12,
            SOFT_DELETED_ENDPOINT: 8,
            ARCHIVED_POLICY_VIOLATION: 3,
            TYPE_MATRIX_VIOLATION: 4,
            CROSS_WORKSPACE_LEAK: 10,
          },
        };
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('run-scan-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('run-scan-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('link-auditor-alert')).toBeDefined();
      expect(
        screen.getByText(/42 invalid links flagged across universal object graph/i),
      ).toBeDefined();
    });

    // Check updated counts on metric cards
    expect(screen.getByTestId('metric-card-DANGLING_TARGET').textContent).toContain(
      '12',
    );
    expect(
      screen.getByTestId('metric-card-CROSS_WORKSPACE_LEAK').textContent,
    ).toContain('10');

    // Click metric card to filter by reason
    const targetCard = screen.getByTestId('metric-card-DANGLING_TARGET');
    fireEvent.click(targetCard);
    expect(targetCard.classList.contains('metric-card--active')).toBe(true);

    // Click again to unselect and reset to ALL
    fireEvent.click(targetCard);
    expect(targetCard.classList.contains('metric-card--active')).toBe(false);
  });

  it('handles inspect drawer view with JSON snapshots', async () => {
    vi.mocked(apiFetch).mockImplementation(async (_method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/auth/me') {
        return mockAdminUser;
      }
      if (path === '/api/v1/admin/object-links/audits') {
        return { items: mockAuditItems, has_more: false };
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('inspect-btn-aud-1')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('inspect-btn-aud-1'));

    await waitFor(() => {
      expect(screen.getByTestId('inspect-drawer')).toBeDefined();
      expect(screen.getByText('Audit ID:')).toBeDefined();
      expect(screen.getByText('aud-1')).toBeDefined();
      expect(screen.getByText('Source Object Snapshot')).toBeDefined();
      expect(screen.getByText('Target Object Snapshot')).toBeDefined();
    });

    // Close inspector
    const closeBtn = screen.getByRole('button', { name: 'Close inspector' });
    fireEvent.click(closeBtn);

    expect(screen.queryByTestId('inspect-drawer')).toBeNull();
  });

  it('executes audited purge with validation and reason enforcement', async () => {
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/auth/me') {
        return mockAdminUser;
      }
      if (path === '/api/v1/admin/object-links/audits') {
        return { items: mockAuditItems, has_more: false };
      }
      if (method === 'POST' && path === '/api/v1/admin/object-links:purge') {
        return {
          purged_count: 1,
          activity_ids: ['act-purge-1'],
        };
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('purge-single-btn-aud-1')).toBeDefined();
    });

    // Click single purge button
    fireEvent.click(screen.getByTestId('purge-single-btn-aud-1'));

    await waitFor(() => {
      expect(screen.getByTestId('purge-modal')).toBeDefined();
      expect(screen.getByText(/Confirm Audited Link Purge/i)).toBeDefined();
    });

    const confirmBtn = screen.getByTestId('confirm-purge-btn');
    expect(confirmBtn.hasAttribute('disabled')).toBe(true);

    const textarea = screen.getByTestId('purge-reason-input');

    // Type short reason (< 10 chars)
    fireEvent.change(textarea, { target: { value: 'too short' } });
    expect(confirmBtn.hasAttribute('disabled')).toBe(true);
    expect(screen.getByTestId('reason-validation-error')).toBeDefined();

    // Type valid reason (>= 10 chars)
    fireEvent.change(textarea, {
      target: {
        value: 'Purging dangling target link as part of object graph hygiene',
      },
    });
    expect(confirmBtn.hasAttribute('disabled')).toBe(false);

    // Submit purge
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByTestId('link-auditor-alert')).toBeDefined();
      expect(screen.getByText(/Successfully purged 1 invalid links/i)).toBeDefined();
    });
  });

  it('handles bulk selection and purge', async () => {
    vi.mocked(apiFetch).mockImplementation(async (_method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/auth/me') {
        return mockAdminUser;
      }
      if (path === '/api/v1/admin/object-links/audits') {
        return { items: mockAuditItems, has_more: false };
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('checkbox-aud-1')).toBeDefined();
    });

    // Select all
    fireEvent.click(screen.getByTestId('select-all-checkbox'));
    expect(screen.getByText('4 links selected')).toBeDefined();

    // Open purge modal from bulk action
    fireEvent.click(screen.getByTestId('purge-selected-btn'));
    expect(screen.getByTestId('purge-modal')).toBeDefined();

    // Cancel modal
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByTestId('purge-modal')).toBeNull();
  });

  it('filters by status filter pills', async () => {
    vi.mocked(apiFetch).mockImplementation(async (_method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/auth/me') {
        return mockAdminUser;
      }
      if (path === '/api/v1/admin/object-links/audits') {
        return { items: [], has_more: false };
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-filter-purged')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('status-filter-purged'));
    expect(
      screen
        .getByTestId('status-filter-purged')
        .classList.contains('filter-pill--active'),
    ).toBe(true);

    await waitFor(() => {
      expect(screen.getByTestId('empty-audit-state')).toBeDefined();
    });
  });

  it('handles scan and purge error responses gracefully', async () => {
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/auth/me') {
        return mockAdminUser;
      }
      if (path === '/api/v1/admin/object-links/audits') {
        return { items: mockAuditItems, has_more: false };
      }
      if (method === 'POST' && path === '/api/v1/admin/object-links:audit') {
        throw new Error('Database transaction timeout during scan');
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('run-scan-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('run-scan-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('link-auditor-alert')).toBeDefined();
      expect(
        screen.getByText(/Database transaction timeout during scan/i),
      ).toBeDefined();
    });
  });

  it('formatEntitySummary handles edge cases and fallbacks', () => {
    expect(
      formatEntitySummary(
        { canonical_key: 'KAN-1', title: 'Test' },
        undefined,
        'Source',
      ),
    ).toBe('KAN-1: Test');
    expect(
      formatEntitySummary({ id: 'uuid-12345678-abcd' }, undefined, 'Target'),
    ).toBe('Target (uuid-123...)');
    expect(formatEntitySummary(null, 'dangling-12345678', 'Target')).toBe(
      'Dangling Target (dangling...)',
    );
    expect(formatEntitySummary(null, undefined, 'Source')).toBe('Unknown Source');
  });

  it('covers interactive drawer and modal backdrops, drawer purge, and alert dismissals', async () => {
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/auth/me') {
        return mockAdminUser;
      }
      if (path === '/api/v1/admin/object-links/audits') {
        return {
          items: [
            ...mockAuditItems,
            {
              id: 'aud-4-resolved',
              workspace_id: 'ws-1',
              link_id: 'lnk-4',
              reason: 'PERMISSION_SEVERED',
              detected_at: '2026-11-18T10:00:00Z',
              purged_at: null,
              resolved_at: '2026-11-18T11:00:00Z',
              link_snapshot: { source_id: 'iss-40', target_id: 'iss-50' },
              source_snapshot: null,
              target_snapshot: null,
            },
          ],
          has_more: false,
        };
      }
      if (method === 'POST' && path === '/api/v1/admin/object-links:purge') {
        return { purged_count: 1, activity_ids: ['act-p'] };
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('inspect-btn-aud-1')).toBeDefined();
    });

    // Inspect aud-1
    fireEvent.click(screen.getByTestId('inspect-btn-aud-1'));
    expect(screen.getByTestId('inspect-drawer')).toBeDefined();

    // Click Purge from inside inspect drawer
    fireEvent.click(screen.getByTestId('drawer-purge-btn'));
    expect(screen.getByTestId('purge-modal')).toBeDefined();

    // Close purge modal via header close button
    const purgeCloseBtn = screen.getByRole('button', { name: 'Close purge dialog' });
    fireEvent.click(purgeCloseBtn);
    expect(screen.queryByTestId('purge-modal')).toBeNull();

    // Inspect aud-4 (resolved record)
    fireEvent.click(screen.getByTestId('inspect-btn-aud-4-resolved'));
    expect(screen.getByTestId('inspect-drawer')).toBeDefined();
    expect(screen.queryByTestId('drawer-purge-btn')).toBeNull();

    // Close via secondary close button in drawer footer
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByTestId('inspect-drawer')).toBeNull();

    // Inspect aud-1 and click backdrop
    fireEvent.click(screen.getByTestId('inspect-btn-aud-1'));
    const backdrop = document.querySelector('.link-auditor-backdrop');
    expect(backdrop).not.toBeNull();
    if (backdrop) {
      fireEvent.click(backdrop);
    }
    expect(screen.queryByTestId('inspect-drawer')).toBeNull();

    // Open purge modal and click backdrop
    fireEvent.click(screen.getByTestId('purge-single-btn-aud-1'));
    const purgeBackdrop = document.querySelector('.link-auditor-backdrop');
    expect(purgeBackdrop).not.toBeNull();
    if (purgeBackdrop) {
      fireEvent.click(purgeBackdrop);
    }
    expect(screen.queryByTestId('purge-modal')).toBeNull();

    // Toggle individual checkbox on and off (aud-1 was selected by single purge)
    const checkbox1 = screen.getByTestId('checkbox-aud-1');
    fireEvent.click(checkbox1); // unselects
    expect(screen.queryByText(/link selected/i)).toBeNull();
    fireEvent.click(checkbox1); // re-selects
    expect(screen.getByText('1 link selected')).toBeDefined();
    fireEvent.click(checkbox1); // unselects again
    expect(screen.queryByText(/link selected/i)).toBeNull();

    // Unselect all when all were selected
    fireEvent.click(screen.getByTestId('select-all-checkbox'));
    fireEvent.click(screen.getByTestId('select-all-checkbox'));
    expect(screen.queryByText(/links selected/i)).toBeNull();

    // Change reason filter dropdown
    fireEvent.change(screen.getByTestId('reason-select'), {
      target: { value: 'DANGLING_TARGET' },
    });
    expect(screen.getByTestId<HTMLSelectElement>('reason-select').value).toBe(
      'DANGLING_TARGET',
    );

    // Trigger non-instanceof Error handling in scan and purge mutations
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/auth/me') return mockAdminUser;
      if (method === 'POST' && path === '/api/v1/admin/object-links:audit') {
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('String scan failure');
      }
      if (method === 'POST' && path === '/api/v1/admin/object-links:purge') {
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('String purge failure');
      }
      return [];
    });

    fireEvent.click(screen.getByTestId('run-scan-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('link-auditor-alert')).toBeDefined();
      expect(screen.getByText('Scan execution failed.')).toBeDefined();
    });

    // Dismiss alert
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss message' }));
    expect(screen.queryByTestId('link-auditor-alert')).toBeNull();
  });

  it('covers purge mutation error handling and csrf bootstrap branches', async () => {
    const { getCsrfToken } = await import('../../api/client');
    vi.mocked(getCsrfToken).mockReturnValue(null);

    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/auth/me') {
        return {
          id: 'usr-ws-admin',
          is_server_admin: false,
          workspace_role: 'WORKSPACE_ADMIN',
          aal_level: 'aal2',
        };
      }
      if (path === '/api/v1/admin/object-links/audits') {
        return { items: mockAuditItems, has_more: false };
      }
      if (method === 'POST' && path === '/api/v1/admin/object-links:audit') {
        return { flagged_total: 0, by_reason: {} };
      }
      if (method === 'POST' && path === '/api/v1/admin/object-links:purge') {
        throw new Error('Purge conflict error 409');
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('purge-single-btn-aud-1')).toBeDefined();
    });

    // Run scan with null csrf
    fireEvent.click(screen.getByTestId('run-scan-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('link-auditor-alert')).toBeDefined();
    });

    // Run purge with null csrf and error response
    fireEvent.click(screen.getByTestId('purge-single-btn-aud-1'));
    fireEvent.change(screen.getByTestId('purge-reason-input'), {
      target: { value: 'Valid administrative reason for purge' },
    });
    fireEvent.click(screen.getByTestId('confirm-purge-btn'));

    await waitFor(() => {
      expect(screen.getByText(/Purge conflict error 409/i)).toBeDefined();
    });

    // Run purge mutation with non-Error throw
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/auth/me') return mockAdminUser;
      if (path === '/api/v1/admin/object-links/audits') return { items: mockAuditItems, has_more: false };
      if (method === 'POST' && path === '/api/v1/admin/object-links:purge') {
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('String purge error');
      }
      return [];
    });

    fireEvent.click(screen.getByTestId('confirm-purge-btn'));
    await waitFor(() => {
      expect(screen.getByText('Purge execution failed.')).toBeDefined();
    });
  });

  it('renders 404 when auth/me rejects or returns null', async () => {
    vi.mocked(apiFetch).mockRejectedValueOnce(new Error('Network offline'));

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('not-found-view')).toBeDefined();
    });
  });

  it('renders loading state when session is loading', () => {
    vi.mocked(apiFetch).mockReturnValue(new Promise((resolve) => { setTimeout(resolve, 10_000_000); })); // Never resolves

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('link-auditor-loading')).toBeDefined();
  });

  it('silently ignores Aal2StepUpCancelledError during purge with zero role="alert" banners (KAN-404)', async () => {
    vi.mocked(apiFetch).mockImplementation(async (method, path) => {
      await Promise.resolve();
      if (path === '/api/v1/auth/me') return mockAdminUser;
      if (path === '/api/v1/admin/object-links/audits') {
        return { items: mockAuditItems, has_more: false };
      }
      if (path === '/api/v1/admin/object-links:purge') {
        throw new Aal2StepUpCancelledError();
      }
      return [];
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/admin/link-auditor']}>
          <LinkAuditorStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('purge-single-btn-aud-1')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('purge-single-btn-aud-1'));
    fireEvent.change(screen.getByTestId('purge-reason-input'), {
      target: { value: 'Valid administrative reason for purge' },
    });
    await waitFor(() => {
      expect(screen.getByTestId('confirm-purge-btn')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('confirm-purge-btn'));
    await waitFor(() => {
      expect(screen.queryByRole('alert')).toBeNull();
    });
  });

  describe('KAN-527: Link Auditor badge contrast and semantic theme tokens', () => {
    it('verifies LinkAuditorStudio.css eliminates dark-only hardcoded hexes and uses semantic variables', () => {
      const cssPath = path.resolve(__dirname, 'LinkAuditorStudio.css');
      const cssContent = fs.readFileSync(cssPath, 'utf8');

      // Assert removal of dark-only hardcoded badge hexes
      expect(cssContent).not.toMatch(/#ff7b72/i);
      expect(cssContent).not.toMatch(/#d29922/i);
      expect(cssContent).not.toMatch(/#f0883e/i);
      expect(cssContent).not.toMatch(/#58a6ff/i);
      expect(cssContent).not.toMatch(/#3fb950/i);

      // Assert presence of WCAG AA semantic tokens
      expect(cssContent).toContain('var(--danger-fg)');
      expect(cssContent).toContain('var(--warn-fg)');
      expect(cssContent).toContain('var(--badge-fg)');
      expect(cssContent).toContain('var(--text-success)');

      // Verify specific class assignments
      expect(cssContent).toMatch(/\.badge-danger\s*\{[^}]*background-color:\s*var\(--danger-bg\);[^}]*color:\s*var\(--danger-fg\);[^}]*border:\s*1px\s+solid\s+var\(--border-danger\);/s);
      expect(cssContent).toMatch(/\.badge-warning\s*\{[^}]*background-color:\s*var\(--warn-bg\);[^}]*color:\s*var\(--warn-fg\);[^}]*border:\s*1px\s+solid\s+var\(--border-warning\);/s);
      expect(cssContent).toMatch(/\.badge-critical\s*\{[^}]*background-color:\s*var\(--warn-bg\);[^}]*color:\s*var\(--warn-fg\);[^}]*border:\s*1px\s+solid\s+var\(--warn-fg\);[^}]*font-weight:\s*700;/s);
      expect(cssContent).toMatch(/\.badge-info\s*\{[^}]*background-color:\s*var\(--badge-bg\);[^}]*color:\s*var\(--badge-fg\);[^}]*border:\s*1px\s+solid\s+var\(--badge-border\);/s);
      expect(cssContent).toMatch(/\.status-badge--purged\s*\{[^}]*background-color:\s*var\(--bg-secondary\);[^}]*color:\s*var\(--fg-secondary\);[^}]*border:\s*1px\s+solid\s+var\(--border-subtle\);/s);
      expect(cssContent).toMatch(/\.status-badge--resolved\s*\{[^}]*background-color:\s*var\(--bg-success-subtle\);[^}]*color:\s*var\(--text-success\);[^}]*border:\s*1px\s+solid\s+var\(--border-success\);/s);
      expect(cssContent).toMatch(/\.link-auditor-btn--danger\s*\{[^}]*background-color:\s*var\(--bg-danger\);[^}]*color:\s*var\(--accent-primary-fg\);/s);
      expect(cssContent).toMatch(/\.metric-card--active\s*\{[^}]*border-color:\s*var\(--accent-primary\);[^}]*background-color:\s*var\(--bg-accent-subtle\);/s);
    });

    it('renders dangling endpoint badges cleanly in Light theme', async () => {
      document.documentElement.removeAttribute('data-theme');
      vi.mocked(apiFetch).mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if (path === '/api/v1/auth/me') return mockAdminUser;
        if (path === '/api/v1/admin/object-links/audits') {
          return { items: mockAuditItems, has_more: false };
        }
        return [];
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/admin/link-auditor']}>
            <LinkAuditorStudio />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('link-auditor-studio')).toBeDefined();
      });

      await waitFor(() => {
        // Verify dangling and reason badges are present
        expect(screen.getAllByText('Dangling Target').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Soft-Deleted Endpoint').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Cross-Workspace Leak').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Flagged').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Purged').length).toBeGreaterThan(0);
      });

      // Verify badges have expected CSS classes
      const danglingTargetBadge = screen.getByTestId('metric-card-DANGLING_TARGET');
      expect(danglingTargetBadge).toBeDefined();

      const purgeSelectedBtn = screen.getByTestId('purge-selected-btn');
      expect(purgeSelectedBtn.className).toContain('link-auditor-btn--danger');
    });

    it('renders dangling endpoint badges cleanly in Dark theme', async () => {
      document.documentElement.setAttribute('data-theme', 'dark');
      try {
        vi.mocked(apiFetch).mockImplementation(async (_method, path) => {
          await Promise.resolve();
          if (path === '/api/v1/auth/me') return mockAdminUser;
          if (path === '/api/v1/admin/object-links/audits') {
            return { items: mockAuditItems, has_more: false };
          }
          return [];
        });

        render(
          <QueryClientProvider client={queryClient}>
            <MemoryRouter initialEntries={['/admin/link-auditor']}>
              <LinkAuditorStudio />
            </MemoryRouter>
          </QueryClientProvider>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('link-auditor-studio')).toBeDefined();
        });

        await waitFor(() => {
          expect(screen.getAllByText('Dangling Target').length).toBeGreaterThan(0);
          expect(screen.getAllByText('Soft-Deleted Endpoint').length).toBeGreaterThan(0);
          expect(screen.getAllByText('Flagged').length).toBeGreaterThan(0);
        });
      } finally {
        document.documentElement.removeAttribute('data-theme');
      }
    });
  });
});
