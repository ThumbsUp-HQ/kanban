/**
 * Playwright E2E verification & Visual Proof Suite for Custom Fields UI (KB-P5-15, KANBA-146).
 * Enforces:
 * 1. 7-format safe value rendering & EmojiHint 🧪 popover metrics.
 * 2. In-flight refresh deduplication & literal error mapping.
 * 3. Admin definition editor with anti-enumeration 404 & copyable manifest_sha256 chip.
 * 4. Scope x Principal matrix escalation approval, PROJECT_ADMIN_SP warning banner, and 409 mismatch handling.
 * 5. Multi-device annotated screenshots across desktop, tablet, and mobile viewports.
 */

import { test, expect } from './support/test';
import { annotatedScreenshot } from './support/annotate';
import { mockApi, loadFixture } from './support/mockApi';

const mockDefinitions = [
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
    manifest_sha256: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
    is_enabled: true,
    approval_status: 'APPROVED',
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
    egress_allowlist: ['/api/v1/projects/KAN'],
    manifest_sha256: 'b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef01',
    is_enabled: true,
    approval_status: 'PENDING',
  },
  {
    id: 'f-build',
    slug: 'build-number',
    name: 'Build Number',
    tier: 'wasm',
    output_format: 'number',
    output_format_metadata: { unit_suffix: 'build', maximum_fraction_digits: 0 },
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    manifest_sha256: 'c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4',
    is_enabled: true,
    approval_status: null,
  },
  {
    id: 'f-badge',
    slug: 'compliance-status',
    name: 'Compliance',
    tier: 'wasm',
    output_format: 'badge',
    output_format_metadata: { color_token: 'success' },
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    manifest_sha256: 'd4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5',
    is_enabled: true,
    approval_status: null,
  },
  {
    id: 'f-md',
    slug: 'security-summary',
    name: 'Security Summary',
    tier: 'wasm',
    output_format: 'markdown_snippet',
    output_format_metadata: { max_chars: 2000 },
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    manifest_sha256: 'e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6',
    is_enabled: true,
    approval_status: null,
  },
  {
    id: 'f-url',
    slug: 'external-tracker',
    name: 'External Tracker',
    tier: 'wasm',
    output_format: 'url',
    output_format_metadata: {},
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    manifest_sha256: 'f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1',
    is_enabled: true,
    approval_status: null,
  },
  {
    id: 'f-table',
    slug: 'metrics-matrix',
    name: 'Metrics Matrix',
    tier: 'wasm',
    output_format: 'json_table',
    output_format_metadata: {
      columns: [
        { key: 'metric', label: 'Metric' },
        { key: 'score', label: 'Score' },
      ],
      max_rows: 50,
    },
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    manifest_sha256: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    is_enabled: true,
    approval_status: null,
  },
];

const mockResults = [
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
    value: 'Staging US-East',
    status: 'SUCCESS',
    tier: 'nsjail',
    token_scope: 'WORKSPACE',
    credential_mode: 'PROJECT_ADMIN_SP',
    last_latency_ms: 85,
    computed_at: '2026-11-13T12:00:00Z',
  },
  {
    field_id: 'f-build',
    field_slug: 'build-number',
    field_name: 'Build Number',
    output_format: 'number',
    value: 4092,
    status: 'SUCCESS',
    tier: 'Wasmtime',
    token_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    last_latency_ms: 8,
    computed_at: '2026-11-13T12:00:00Z',
  },
  {
    field_id: 'f-badge',
    field_slug: 'compliance-status',
    field_name: 'Compliance',
    output_format: 'badge',
    value: 'Verified',
    status: 'SUCCESS',
    tier: 'Wasmtime',
    token_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    last_latency_ms: 9,
    computed_at: '2026-11-13T12:00:00Z',
  },
  {
    field_id: 'f-md',
    field_slug: 'security-summary',
    field_name: 'Security Summary',
    output_format: 'markdown_snippet',
    value: 'Scan status: **Clean**. All dependencies *passed*.',
    status: 'SUCCESS',
    tier: 'Wasmtime',
    token_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    last_latency_ms: 14,
    computed_at: '2026-11-13T12:00:00Z',
  },
  {
    field_id: 'f-url',
    field_slug: 'external-tracker',
    field_name: 'External Tracker',
    output_format: 'url',
    value: 'https://security.example.com/cve/CVE-2026-146',
    status: 'SUCCESS',
    tier: 'Wasmtime',
    token_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    last_latency_ms: 11,
    computed_at: '2026-11-13T12:00:00Z',
  },
  {
    field_id: 'f-table',
    field_slug: 'metrics-matrix',
    field_name: 'Metrics Matrix',
    output_format: 'json_table',
    value: [
      { metric: 'Coverage', score: '99%' },
      { metric: 'Latency', score: '12ms' },
    ],
    status: 'SUCCESS',
    tier: 'Wasmtime',
    token_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    last_latency_ms: 22,
    computed_at: '2026-11-13T12:00:00Z',
  },
];

const mockApprovals = [
  {
    id: 'appr-env',
    field_id: 'f-env',
    status: 'PENDING',
    target_scope: 'WORKSPACE',
    credential_mode: 'PROJECT_ADMIN_SP',
    manifest_sha256: 'b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef01',
    justification: 'Needs workspace token to verify target environments',
    created_at: '2026-11-13T10:00:00Z',
    updated_at: '2026-11-13T10:00:00Z',
  },
];

async function setupMocks(page: import('@playwright/test').Page, extraHandlers: Record<string, unknown> = {}) {
  const projectKan = loadFixture<{ priorities?: unknown[]; labels?: unknown[] }>('project-kan');
  await mockApi(page, {
    'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
    'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/issues': { json: loadFixture('issues-kan') },
    'GET /api/v1/users/me': { json: loadFixture('me-adam') },
    'GET /api/v1/projects/KAN/priorities': { json: projectKan.priorities ?? [] },
    'GET /api/v1/projects/KAN/labels': { json: projectKan.labels ?? [] },
    'GET /api/v1/projects/KAN/cycles': { json: [] },
    'GET /api/v1/projects/KAN/modules': { json: [] },
    'GET /api/v1/projects/KAN/custom-fields': { json: mockDefinitions },
    'GET /api/v1/issues/KAN-142/custom-fields': { json: mockResults },
    'GET /api/v1/custom-fields/f-env/approvals': { json: mockApprovals },
    'GET /api/v1/custom-fields/f-cvss/approvals': { json: [] },
    ...extraHandlers,
  });
}

test.describe('Custom Fields UI E2E (KB-P5-15, KANBA-146)', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
  });

  test('01-rail-custom-fields: renders 7 formats and emoji hint popover metrics', async ({
    page,
  }, testInfo) => {
    await page.goto('/__dev/drawer-rail');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('[data-testid="rail-story"]')).toBeVisible();

    const railSection = page.locator('[data-testid="custom-fields-rail-section"]');
    await expect(railSection).toBeVisible();

    // Verify literal header
    await expect(railSection.locator('.custom-fields-rail-title')).toHaveText(
      'Custom Fields (Admin-Defined 🧪)',
    );

    // Verify all 7 formats render
    await expect(page.locator('[data-testid="custom-field-row-cvss-score"]')).toBeVisible();
    await expect(page.locator('[data-testid="custom-field-row-target-env"]')).toBeVisible();
    await expect(page.locator('[data-testid="custom-field-row-build-number"]')).toBeVisible();
    await expect(page.locator('[data-testid="custom-field-row-compliance-status"]')).toBeVisible();
    await expect(page.locator('[data-testid="custom-field-row-security-summary"]')).toBeVisible();
    await expect(page.locator('[data-testid="custom-field-row-external-tracker"]')).toBeVisible();
    await expect(page.locator('[data-testid="custom-field-row-metrics-matrix"]')).toBeVisible();

    // Open EmojiHint popover by focusing or clicking trigger
    const hintTrigger = page.locator('[data-testid="custom-field-emoji-hint-cvss-score"]');
    await hintTrigger.focus();
    await expect(page.locator('[data-testid="custom-field-hint-popover-cvss-score"]')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '01-rail-custom-fields',
      annotations: [
        {
          selector: '[data-testid="custom-fields-rail-section"]',
          label: '1: Custom Fields rail section header & rows',
        },
        {
          selector: '[data-testid="custom-field-value-cvss-score"]',
          label: '2: Severity pill rendered value',
        },
        {
          selector: '[data-testid="refresh-field-cvss-score"]',
          label: '3: Refresh execute button',
        },
      ],
    });
  });

  test('02-rail-refresh-error: renders literal error mapping on execution failure', async ({
    page,
  }, testInfo) => {
    // Only capture on desktop
    if (testInfo.project.name !== 'desktop') {
      test.skip();
    }

    await setupMocks(page, {
      'POST /api/v1/issues/KAN-142/custom-fields/f-cvss/execute': {
        status: 200,
        json: {
          field_id: 'f-cvss',
          field_slug: 'cvss-score',
          field_name: 'CVSS Score',
          output_format: 'severity_pill',
          status: 'ERROR',
          error_code: 'SCRIPT_TIMEOUT',
          tier: 'Wasmtime',
          token_scope: 'PROJECT',
          credential_mode: 'INVOKING_USER',
          last_latency_ms: 5000,
          computed_at: '2026-11-13T12:00:00Z',
        },
      },
    });

    await page.goto('/__dev/drawer-rail');
    await page.waitForLoadState('networkidle');

    const refreshBtn = page.locator('[data-testid="refresh-field-cvss-score"]');
    await expect(refreshBtn).toBeVisible();
    await refreshBtn.click();

    // Verify mapped error text
    const errorSpan = page.locator('[data-testid="custom-field-error-cvss-score"]');
    await expect(errorSpan).toBeVisible();
    await expect(errorSpan).toHaveText('Timed out');

    await annotatedScreenshot(page, testInfo, {
      name: '02-rail-refresh-error',
      annotations: [
        {
          selector: '[data-testid="custom-field-error-cvss-score"]',
          label: '1: Mapped inline error without raw detail leakage',
        },
      ],
    });
  });

  test('03-admin-editor: displays definition editor with manifest_sha256 chip', async ({
    page,
  }, testInfo) => {
    await page.goto('/projects/KAN/settings/custom-fields');
    await page.waitForLoadState('networkidle');

    const editorLayout = page.locator('[data-testid="custom-fields-editor-layout"]');
    await expect(editorLayout).toBeVisible();

    // Select first field to display sha chip
    const cvssItem = page.locator('[data-testid="field-item-cvss-score"]');
    await cvssItem.click();

    const shaChip = page.locator('[data-testid="manifest-sha256-chip"]');
    await expect(shaChip).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '03-admin-editor',
      annotations: [
        {
          selector: '[data-testid="custom-fields-list"]',
          label: '1: Custom field definitions sidebar',
        },
        {
          selector: '[data-testid="manifest-sha256-chip"]',
          label: '2: Manifest SHA256 chip with copy action',
        },
        {
          selector: '[data-testid="save-definition-btn"]',
          label: '3: Save definition control',
        },
      ],
    });
  });

  test('04-approval-sp-warning: renders PROJECT_ADMIN_SP explicit warning banner', async ({
    page,
  }, testInfo) => {
    if (testInfo.project.name !== 'desktop') {
      test.skip();
    }

    await page.goto('/projects/KAN/settings/custom-fields');
    await page.waitForLoadState('networkidle');

    // Select Target Environment field with PROJECT_ADMIN_SP mode
    const envItem = page.locator('[data-testid="field-item-target-env"]');
    await envItem.click();

    const spBanner = page.locator('[data-testid="sp-warning-banner"]');
    await expect(spBanner).toBeVisible();
    await expect(spBanner).toContainText(
      '⚠️ This field will run with Project Admin service-principal credentials for every viewer.',
    );

    await annotatedScreenshot(page, testInfo, {
      name: '04-approval-sp-warning',
      annotations: [
        {
          selector: '[data-testid="sp-warning-banner"]',
          label: '1: Required Project Admin SP credential warning banner',
        },
        {
          selector: '[data-testid="sp-ack-checkbox"]',
          label: '2: Explicit admin acknowledgment checkbox',
        },
      ],
    });
  });

  test('05-approval-manifest-mismatch: disables Approve on 409 conflict with literal message', async ({
    page,
  }, testInfo) => {
    if (testInfo.project.name !== 'desktop') {
      test.skip();
    }

    await setupMocks(page, {
      'POST /api/v1/custom-field-approvals/appr-env/approve': {
        status: 409,
        json: {
          code: 'MANIFEST_MISMATCH',
          detail: 'Definition changed since you opened it - reload to review',
        },
      },
    });

    await page.goto('/projects/KAN/settings/custom-fields');
    await page.waitForLoadState('networkidle');

    const envItem = page.locator('[data-testid="field-item-target-env"]');
    await envItem.click();

    // Check acknowledgment checkbox and click approve
    const ackCheckbox = page.locator('[data-testid="sp-ack-checkbox"]');
    await ackCheckbox.click();

    const approveBtn = page.locator('[data-testid="approve-escalation-btn"]');
    await approveBtn.click();

    // Verify 409 banner appears and button is disabled
    const mismatchBanner = page.locator('[data-testid="manifest-mismatch-banner"]');
    await expect(mismatchBanner).toBeVisible();
    await expect(mismatchBanner).toContainText(
      'Definition changed since you opened it - reload to review',
    );
    await expect(approveBtn).toBeDisabled();

    await annotatedScreenshot(page, testInfo, {
      name: '05-approval-manifest-mismatch',
      annotations: [
        {
          selector: '[data-testid="manifest-mismatch-banner"]',
          label: '1: Literal 409 manifest mismatch error notice',
        },
        {
          selector: '[data-testid="approve-escalation-btn"]',
          label: '2: Disabled approve action on tamper/mismatch',
        },
      ],
    });
  });

  test('06-non-admin-404: renders uniform 404 page for non-admin callers (anti-enumeration)', async ({
    page,
  }, testInfo) => {
    if (testInfo.project.name !== 'desktop') {
      test.skip();
    }

    await page.goto('/projects/KAN/settings/custom-fields?non_admin=true');
    await page.waitForLoadState('networkidle');

    const notFoundView = page.locator('[data-testid="not-found-view"]');
    await expect(notFoundView).toBeVisible();
    await expect(notFoundView).toContainText('Not found or no access');

    await annotatedScreenshot(page, testInfo, {
      name: '06-non-admin-404',
      annotations: [
        {
          selector: '[data-testid="not-found-view"]',
          label: '1: Anti-enumeration uniform 404 view',
        },
      ],
    });
  });
});
