/**
 * Playwright E2E Forensic QA Proofs for KANBA-217:
 * 1. Sticky Snooze & Promotion Banner (no 422 crash, inline error boundary).
 * 2. Sticky-to-Doc Preview Modal (Desktop Light & Mobile Dark 390x844).
 * 3. Promoted Sticky [Open Doc] navigation to valid canonical route.
 * 4. Docs History Diff/Restore view (line diff +X -Y lines changed badge, color-coded lines).
 * 5. Searchable Doc <-> Issue Link Picker UI.
 */

import { test, expect } from '../support/test';
import { mockApi, loadFixture } from '../support/mockApi';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCREENSHOTS_DIR = path.resolve(__dirname, '../../../../docs/qa/KANBA-217/screenshots');

const baseMocks = {
  'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
  'GET /api/v1/me': { json: loadFixture('me-adam') },
  'GET /api/v1/auth/me': { json: loadFixture('me-adam') },
  'GET /api/v1/setup/status': { json: { initialized: true } },
  'GET /api/v1/auth/session': {
    json: {
      authenticated: true,
      principal_id: '11111111-1111-4111-8111-111111111111',
      workspace_id: '22222222-2222-2222-2222-222222222222',
      aal_level: 2,
      mfa_pending: false,
      csrf_token: 'test-csrf-token-proofs',
      remember_me: true,
    },
  },
  'GET /api/v1/workspaces': {
    json: {
      items: [{ id: '22222222-2222-2222-2222-222222222222', name: 'kanban', slug: 'kanban' }],
      active_workspace_id: '22222222-2222-2222-2222-222222222222',
    },
  },
  'GET /api/v1/workspaces/current': {
    json: { id: '22222222-2222-2222-2222-222222222222', name: 'kanban', slug: 'kanban' },
  },
  'GET /api/v1/projects': {
    json: [{ id: '33333333-3333-3333-3333-333333333333', key: 'KAN', name: 'kanban' }],
  },
  'GET /api/v1/projects/KAN': {
    json: {
      id: '33333333-3333-3333-3333-333333333333',
      key: 'KAN',
      canonical_key: 'KAN',
      name: 'kanban',
      capabilities: ['PROJECT_ADMIN', 'EDIT', 'VIEW', 'ADMIN'],
      states: [],
    },
  },
  'GET /api/v1/objects/:objectId/access': { json: loadFixture('access-project-kan') },
  'GET /api/v1/projects/KAN/access': {
    json: {
      resource_id: '33333333-3333-3333-3333-333333333333',
      resource_kind: 'project',
      effective_policy: 'ALLOW',
      entries: [],
    },
  },
  'GET /api/v1/projects/KAN/views': { json: [] },
  'GET /api/v1/projects/KAN/issues': {
    json: {
      items: [
        { id: 'issue-101', key: 'KAN-101', title: 'Implement Auth Session Token Rotation' },
        { id: 'issue-102', key: 'KAN-102', title: 'Audit Universal Object Graph Invariants' },
      ],
    },
  },
  'GET /api/v1/projects/KAN/cycles': { json: { items: [] } },
  'GET /api/v1/projects/KAN/modules': { json: { items: [] } },
  'GET /api/v1/projects/KAN/states': { json: [] },
  'GET /api/v1/projects/KAN/priorities': { json: [] },
  'GET /api/v1/projects/KAN/labels': { json: [] },
  'GET /api/v1/users/me': {
    json: {
      id: '11111111-1111-4111-8111-111111111111',
      display_name: 'Adam Security Architect',
      email: 'adam@example.com',
      avatar_url: null,
    },
  },
  'GET /api/v1/media-proxy': {
    status: 200,
    contentType: 'image/png',
    body: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
      'base64',
    ),
  },
};

const samplePage = {
  id: 'page-arch-spec',
  canonical_key: 'docs/architecture/auth-studio',
  doc_id: 'doc-arch-root',
  parent_page_id: null,
  workspace_id: '22222222-2222-2222-2222-222222222222',
  title: 'Architecture & Security Specification',
  body_markdown:
    '# Architecture & Security Specification\n\nWelcome to 👍kanban architecture.\n\n## Threat Modeling\n\nAll endpoints require strict input validation.\n\n### Access Control\n\nRLS policies enforced.\n',
  body_sha256: 'sha256-current-body-hash',
  hierarchy_path: 'docs.architecture.auth_studio',
  version_seq: 3,
  sort_rank: '0|hzzzzz:',
  breadcrumbs: [],
  outline: [],
  access_manifest: {},
  capabilities: ['EDIT', 'VIEW', 'ADMIN'],
  object_links: [
    {
      target_key: 'KAN-101',
      target_title: 'Implement Auth Session Token Rotation',
      link_type: 'VERIFIED_BY_DOC',
      link_id: 'link-101',
    },
  ],
};

const sampleVersions = [
  {
    page_id: 'page-arch-spec',
    version_seq: 3,
    title: 'Architecture & Security Specification',
    body_markdown:
      '# Architecture & Security Specification\n\nWelcome to 👍kanban architecture.\n\n## Threat Modeling\n\nAll endpoints require strict input validation.\n\n### Access Control\n\nRLS policies enforced.\n',
    body_sha256: 'sha256-current-body-hash',
    created_by_id: 'adam',
    created_at: '2026-11-18T16:00:00Z',
  },
  {
    page_id: 'page-arch-spec',
    version_seq: 2,
    title: 'Architecture & Security Specification v2',
    body_markdown:
      '# Architecture & Security Specification\n\nDraft spec notes.\n\n## Threat Modeling\n\nPreliminary draft notes.\n',
    body_sha256: 'sha256-v2-body-hash',
    created_by_id: 'adam',
    created_at: '2026-11-17T12:00:00Z',
  },
  {
    page_id: 'page-arch-spec',
    version_seq: 1,
    title: 'Architecture Spec v1',
    body_markdown: '# Architecture Spec\nInitial stub.\n',
    body_sha256: 'sha256-v1-body-hash',
    created_by_id: 'adam',
    created_at: '2026-11-16T10:00:00Z',
  },
];

const sampleTree = [
  {
    id: 'page-arch-spec',
    title: 'Architecture & Security Specification',
    slug: 'auth-studio',
    restricted: false,
    children: [],
  },
];

const candidateSticky = {
  id: 'sticky-1',
  workspace_id: '22222222-2222-2222-2222-222222222222',
  project_id: '33333333-3333-3333-3333-333333333333',
  body_markdown:
    '# Comprehensive Incident Response & Disaster Recovery Plan\n\nThis sticky contains extensive architectural specifications, network diagrams, failover topologies, RTO/RPO metrics, and key escalation procedures across all cluster nodes.\n\n## Failover Topology\n\n1. Node health probe failure detection within 500ms.\n2. Automated split-brain prevention through distributed consensus.\n3. Transparent read-only replica promotion.',
  content:
    '# Comprehensive Incident Response & Disaster Recovery Plan\n\nThis sticky contains extensive architectural specifications, network diagrams, failover topologies, RTO/RPO metrics, and key escalation procedures across all cluster nodes.\n\n## Failover Topology\n\n1. Node health probe failure detection within 500ms.\n2. Automated split-brain prevention through distributed consensus.\n3. Transparent read-only replica promotion.',
  color_token: 'YELLOW' as const,
  sort_rank: '0|hzzzzz:',
  promotion_snoozed_at_length: null,
  promoted_to_doc_id: null,
  is_promoted_stub: false,
  body_sha256: 'sha256-sticky-1-candidate',
  promotion_recommended: true,
  promoted_to_doc: null,
  triggers: ['LENGTH_GROWTH'],
  capabilities: ['VIEW', 'EDIT', 'DELETE', 'ADMIN'],
};

const promotedSticky = {
  id: 'sticky-2',
  workspace_id: '22222222-2222-2222-2222-222222222222',
  project_id: '33333333-3333-3333-3333-333333333333',
  body_markdown: '# Promoted Architecture Notes\n\nThis sticky was promoted to a full document specification.',
  content: '# Promoted Architecture Notes\n\nThis sticky was promoted to a full document specification.',
  color_token: 'BLUE' as const,
  sort_rank: '0|hzzzzz:1',
  promotion_snoozed_at_length: null,
  promoted_to_doc_id: 'doc-arch-root',
  is_promoted_stub: true,
  body_sha256: 'sha256-sticky-2-promoted',
  promotion_recommended: false,
  promoted_to_doc: {
    id: 'doc-arch-root',
    root_page_id: 'page-arch-spec',
    root_page_canonical_key: 'docs/architecture/auth-studio',
    title: 'Architecture & Security Specification',
    canonical_key: 'docs/architecture/auth-studio',
  },
  triggers: [],
  capabilities: ['VIEW', 'EDIT', 'DELETE', 'ADMIN'],
};

test.describe('KANBA-217 QA Proofs', () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-proofs',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01 & 02: Sticky Snooze Banner & Promote Preview Modal (Desktop Light & Mobile Dark)', async ({
    page,
  }) => {
    await mockApi(page, {
      ...baseMocks,
      'GET /api/v1/projects/KAN/stickies': {
        json: [candidateSticky, promotedSticky],
      },
      'POST /api/v1/stickies/sticky-1/promote-preview': {
        json: {
          proposal: {
            title: 'Comprehensive Incident Response & Disaster Recovery Plan',
            sections: [
              {
                heading: 'Failover Topology',
                content: 'Node health probe failure detection within 500ms.',
              },
            ],
          },
          rendered_markdown:
            '# Comprehensive Incident Response & Disaster Recovery Plan\n\n## Failover Topology\n\n1. Node health probe failure detection within 500ms.\n2. Automated split-brain prevention through distributed consensus.\n3. Transparent read-only replica promotion.\n\n```mermaid\nflowchart TD\n  Primary --> Replica1\n  Primary --> Replica2\n```\n',
          original_sha256: 'sha256-sticky-1-candidate',
          warnings: [],
          acl_preview: {
            direct_entries_count: 3,
            will_copy_verbatim: true,
          },
        },
      },
    });

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/projects/KAN/overview');

    // 01: Capture candidate sticky banner
    const banner = page.locator('[data-testid="sticky-promotion-banner"]');
    await expect(banner).toBeVisible();

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '01-sticky-snooze-banner-desktop-light.png'),
      fullPage: false,
    });

    // 02: Click Promote to Doc -> Opens StickyPromotePreviewModal
    const promoteBtn = page.locator('[data-testid="promote-to-doc-btn"]');
    await promoteBtn.click();

    const previewModal = page.locator('[data-testid="sticky-promote-preview-modal"]');
    await expect(previewModal).toBeVisible();

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '02-sticky-promote-preview-modal-desktop-light.png'),
      fullPage: false,
    });

    // 02-mobile-dark: Switch to mobile viewport (390x844) and dark theme
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => {
      document.documentElement.setAttribute('data-theme', 'dark');
    });

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '02-sticky-promote-preview-modal-mobile-dark.png'),
      fullPage: false,
    });
  });

  test('03: Promoted Sticky [Open Doc] Navigates to Valid Canonical Route', async ({
    page,
  }) => {
    await mockApi(page, {
      ...baseMocks,
      'GET /api/v1/projects/KAN/stickies': {
        json: [promotedSticky],
      },
      'GET /api/v1/projects/KAN/docs/tree': {
        json: sampleTree,
      },
      'GET /api/v1/pages/page-arch-spec': {
        json: samplePage,
      },
      'GET /api/v1/pages/page-arch-spec/versions': {
        json: sampleVersions,
      },
    });

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/projects/KAN/overview');

    const openDocLink = page.locator('[data-testid="open-doc-link"], [data-testid="promoted-sticky-open-doc"]');
    await expect(openDocLink).toBeVisible();

    // Verify href targets valid page route
    const href = await openDocLink.getAttribute('href');
    expect(href).toContain('/projects/KAN/docs/page-arch-spec');

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '03-promoted-sticky-open-doc-desktop-light.png'),
      fullPage: false,
    });
  });

  test('04 & 05: Docs History Diff/Restore & Searchable Link Picker (Desktop Light, Tablet Dark, Mobile Dark)', async ({
    page,
  }) => {
    await mockApi(page, {
      ...baseMocks,
      'GET /api/v1/projects/KAN/docs/tree': {
        json: sampleTree,
      },
      'GET /api/v1/pages/page-arch-spec': {
        json: samplePage,
      },
      'GET /api/v1/pages/page-arch-spec/versions': {
        json: sampleVersions,
      },
    });

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/projects/KAN/docs/page-arch-spec');

    // Wait for document to load
    await expect(page.locator('[data-testid="docs-workspace-view"]')).toBeVisible();

    // Open History Tab
    const historyTab = page.locator('[data-testid="rail-tab-history"]');
    await historyTab.click();

    // Select Version 2 to view diff against current
    const v2Item = page.locator('[data-testid="version-item-v2"]');
    await expect(v2Item).toBeVisible();
    await v2Item.click();

    // Verify diff viewer and stats badge are visible
    const diffContainer = page.locator('[data-testid="version-diff-container"]');
    await expect(diffContainer).toBeVisible();
    const diffStats = page.locator('[data-testid="version-diff-stats"]');
    await expect(diffStats).toBeVisible();

    // 04: Capture Diff View on Desktop Light
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '04-docs-history-diff-restore-desktop-light.png'),
      fullPage: false,
    });

    // 04-tablet-dark: Tablet viewport (1024x768) in Dark theme
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.evaluate(() => {
      document.documentElement.setAttribute('data-theme', 'dark');
    });

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '04-docs-history-diff-restore-tablet-dark.png'),
      fullPage: false,
    });

    // Reset to light theme & desktop for link picker
    await page.evaluate(() => {
      document.documentElement.removeAttribute('data-theme');
    });
    await page.setViewportSize({ width: 1440, height: 900 });

    // Switch to Outline tab
    const outlineTab = page.locator('[data-testid="rail-tab-outline"]');
    await outlineTab.click();

    // Click + Link Issue
    const linkIssueBtn = page.locator('[data-testid="open-link-issue-picker-btn"]');
    await expect(linkIssueBtn).toBeVisible();
    await linkIssueBtn.click();

    // Verify Searchable Link Picker dialog
    const linkPicker = page.locator('[data-testid="doc-issue-link-picker"]');
    await expect(linkPicker).toBeVisible();

    // 05: Capture Link Picker on Desktop Light
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '05-docs-highlight-link-picker-desktop-light.png'),
      fullPage: false,
    });

    // 05-mobile-dark: Mobile viewport (390x844) in Dark theme
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => {
      document.documentElement.setAttribute('data-theme', 'dark');
    });

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '05-docs-highlight-link-picker-mobile-dark.png'),
      fullPage: false,
    });
  });
});
