/**
 * Admin Auth Studio E2E Specifications (KB-P3-36).
 * Validates card list, drag/keyboard reordering, write-only secret contracts,
 * live handshake status hints, LOCKOUT_PREVENTED safeguards, and non-admin access gating.
 * Strict ASCII hyphens only.
 */

import { test, expect } from '../support/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

interface AuthCardsFixture {
  cards: Record<string, unknown>[];
}

function getBaseShellMocks() {
  return {
    'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
    'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/users/me': { json: loadFixture('me-adam') },
  };
}

test.describe('Admin Auth Studio E2E Specifications (KB-P3-36)', () => {
  test.beforeEach(async ({ context }) => {
    // Provide CSRF cookie required by apiFetch on unsafe HTTP methods
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-123',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-auth-studio-list: renders 4 cards in sort_rank order with Primary badge and healthy chip', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      ...getBaseShellMocks(),
      'GET /api/v1/auth/me': { json: loadFixture('me-admin-auth') },
      'GET /api/v1/admin/auth-cards': { json: loadFixture('admin-auth-cards') },
    });

    await page.goto('/admin/auth');
    await expect(page.locator('.auth-studio-page')).toBeVisible();
    await expect(page.locator('.auth-studio-title')).toHaveText('Authentication Studio');

    // Exactly 4 card rows
    const cardRows = page.locator('.auth-card-row');
    await expect(cardRows).toHaveCount(4);

    // Primary badge only on the first enabled external card (Okta SSO)
    const firstCard = cardRows.nth(0);
    await expect(firstCard).toContainText('Okta SSO');
    await expect(firstCard.locator('.auth-badge--primary')).toBeVisible();
    await expect(firstCard.locator('.auth-badge--primary')).toHaveText('Primary');

    // Status chip and handshake trigger
    await expect(firstCard.locator('.auth-status-chip--healthy')).toBeVisible();
    await expect(firstCard.locator('.auth-status-chip--healthy')).toContainText('HEALTHY (42 ms)');
    await expect(firstCard.locator('button:has-text("Test handshake")')).toBeVisible();

    // Enable switch is present
    await expect(firstCard.locator('.auth-switch-label')).toBeVisible();
    await expect(firstCard.locator('.auth-switch-input')).toBeChecked();

    // Fourth card is pinned Local Administrator
    const pinnedCard = page.locator('.auth-card-row--pinned');
    await expect(pinnedCard).toHaveCount(1);
    await expect(pinnedCard).toContainText('Local Administrator');

    // Style probe measurements
    await probeStyles(page, testInfo, {
      name: 'admin-auth-studio',
      probes: [
        { selector: '.auth-studio-list', props: ['row-gap'] },
        { selector: '.auth-card-row', props: ['padding'] },
        { selector: '.emoji-hint', props: ['width', 'height'] },
        { selector: '.auth-studio-header', props: ['margin-bottom'] },
      ],
    });

    // Capture annotated screenshot 01
    await annotatedScreenshot(page, testInfo, {
      name: '01-auth-studio-list',
      annotations: [
        {
          selector: '.auth-studio-header',
          label: 'Header Title Row',
          note: 'Authentication Studio with access EmojiHint',
        },
        {
          selector: '.auth-card-row:first-child',
          label: 'Okta OIDC Row',
          note: 'padding 16px 18px with Primary badge',
        },
        {
          selector: '.auth-card-row:first-child .auth-status-chip--healthy',
          label: 'Status Chip & Handshake',
          note: 'HEALTHY (42 ms) chip with test button',
        },
        {
          selector: '.auth-card-row:first-child .auth-switch-label',
          label: 'Enable Switch',
          note: 'Interactive toggle switch',
        },
        {
          selector: '.auth-card-row--pinned',
          label: 'Local Admin Row',
          note: 'Pinned break-glass access row',
        },
      ],
    });
  });

  test('02-card-reordered: reorders card via keyboard Move Up control into slot 2', async ({
    page,
  }, testInfo) => {
    const fixture = loadFixture<AuthCardsFixture>('admin-auth-cards');
    // Arrange order: Okta (1), Corp AD (2), GitHub (3), Local Admin (z)
    const okta = fixture.cards[0];
    const github = fixture.cards[1];
    const ldap = fixture.cards[2];
    const local = fixture.cards[3];
    if (!okta || !github || !ldap || !local) {
      throw new Error('Fixture missing required card definition');
    }

    const initialCards = [
      { ...okta, sort_rank: '1' },
      { ...ldap, sort_rank: '2' },
      { ...github, sort_rank: '3' },
      { ...local, sort_rank: 'z' },
    ];

    await mockApi(page, {
      ...getBaseShellMocks(),
      'GET /api/v1/auth/me': { json: loadFixture('me-admin-auth') },
      'GET /api/v1/admin/auth-cards': { json: { cards: initialCards } },
      'POST /api/v1/admin/auth-cards/card-github-2/reorder': {
        json: { ...github, sort_rank: '1V' },
      },
    });

    await page.goto('/admin/auth');
    await expect(page.locator('.auth-card-row')).toHaveCount(4);

    // Initial third card is GitHub Enterprise
    await expect(page.locator('.auth-card-row').nth(2)).toContainText('GitHub Enterprise');

    // Click Move Up on GitHub Enterprise
    const moveUpButton = page.locator('button[aria-label="Move GitHub Enterprise up"]');
    await expect(moveUpButton).toBeVisible();
    await moveUpButton.click();

    // Verify GitHub Enterprise is now in slot 2 (index 1), above Corp AD
    const secondCard = page.locator('.auth-card-row').nth(1);
    await expect(secondCard).toContainText('GitHub Enterprise');
    const thirdCard = page.locator('.auth-card-row').nth(2);
    await expect(thirdCard).toContainText('Corporate Active Directory');

    // Capture annotated screenshot 02
    await annotatedScreenshot(page, testInfo, {
      name: '02-card-reordered',
      annotations: [
        {
          selector: '.auth-card-row:nth-child(2)',
          label: 'Moved Card Slot 2',
          note: 'GitHub Enterprise moved above Corp LDAPS',
        },
        {
          selector: '.auth-card-row:nth-child(2) .auth-card-reorder-group',
          label: 'Reorder Controls',
          note: 'Keyboard Move up and Move down controls',
        },
      ],
    });
  });

  test('03-edit-drawer-write-only: editing Okta OIDC shows PKCE badge and empty secret input with dek_kid placeholder', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      ...getBaseShellMocks(),
      'GET /api/v1/auth/me': { json: loadFixture('me-admin-auth') },
      'GET /api/v1/admin/auth-cards': { json: loadFixture('admin-auth-cards') },
    });

    await page.goto('/admin/auth');
    await expect(page.locator('.auth-card-row')).toHaveCount(4);

    // Open edit drawer for Okta SSO
    const editButton = page.locator('.auth-card-row').first().locator('button:has-text("Edit")');
    await expect(editButton).toBeVisible();
    await editButton.click();

    // Assert drawer is open
    const drawer = page.locator('.auth-editor-drawer');
    await expect(drawer).toBeVisible();
    await expect(page.locator('.auth-editor-title')).toHaveText('Edit Okta SSO');

    // PKCE enforced badge
    const pkceBadge = page.locator('.auth-badge--pkce');
    await expect(pkceBadge).toBeVisible();
    await expect(pkceBadge).toHaveText('PKCE S256 (enforced)');

    // Write-only secret contract: input is empty, placeholder contains dek_kid, disabled until replace checked
    const secretInput = page.locator('#card-client-secret');
    await expect(secretInput).toBeVisible();
    await expect(secretInput).toHaveValue('');
    const placeholder = await secretInput.getAttribute('placeholder');
    expect(placeholder).toContain('dek-oidc-42');
    await expect(secretInput).toBeDisabled();

    // Replace stored secret checkbox is unchecked
    const replaceCheckbox = page.locator('#card-replace-secret');
    await expect(replaceCheckbox).toBeVisible();
    await expect(replaceCheckbox).not.toBeChecked();

    // Probe drawer and prop row styles
    await probeStyles(page, testInfo, {
      name: 'admin-auth-drawer',
      probes: [
        { selector: '.auth-editor-drawer', props: ['padding', 'width'] },
        { selector: '.auth-editor-prop-row', props: ['min-height'] },
      ],
    });

    // Capture annotated screenshot 03
    await annotatedScreenshot(page, testInfo, {
      name: '03-edit-drawer-write-only',
      annotations: [
        {
          selector: '.auth-badge--pkce',
          label: 'PKCE Badge',
          note: 'PKCE S256 (enforced)',
        },
        {
          selector: '#card-client-secret',
          label: 'Write-only Secret Field',
          note: 'Empty with dek_kid placeholder',
        },
        {
          selector: 'label[for="card-replace-secret"]',
          label: 'Replace Secret Box',
          note: 'Unchecked by default',
        },
        {
          selector: '.auth-editor-prop-row',
          label: 'Property Row Height',
          note: '38px min-height',
        },
      ],
    });
  });

  test('04-lockout-prevented-banner: disabling Local Administrator triggers 409 alert banner and switch rollback', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      ...getBaseShellMocks(),
      'GET /api/v1/auth/me': { json: loadFixture('me-admin-auth') },
      'GET /api/v1/admin/auth-cards': { json: loadFixture('admin-auth-cards') },
      'PATCH /api/v1/admin/auth-cards/card-local-4/enabled': {
        status: 409,
        json: {
          code: 'LOCKOUT_PREVENTED',
          reason_code: 'HANDSHAKE_STALE_FOR_LOCAL_DISABLE',
          message:
            'Local Administrator cannot be disabled until at least one external Server-Admin identity provider card completes a verified login handshake within the past 15 minutes.',
        },
      },
    });

    await page.goto('/admin/auth');
    await expect(page.locator('.auth-card-row')).toHaveCount(4);

    // Toggle Local Administrator switch to trigger lockout safeguard
    const localSwitch = page.locator('input[aria-label="Enable Local Administrator"]');
    await expect(localSwitch).toBeChecked();
    await page.locator('.auth-card-row--pinned .auth-switch-label').click();

    // Assert Lockout banner is displayed and focused
    const banner = page.locator('.auth-lockout-banner');
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute('role', 'alert');
    await expect(banner).toContainText('15 minutes');

    // Assert switch rolled back to enabled
    await expect(localSwitch).toBeChecked();

    // Expand emergency host recovery disclosure
    const disclosure = page.locator('.auth-lockout-disclosure');
    await expect(disclosure).toBeVisible();
    await disclosure.locator('summary').click();

    const codeSnippet = page.locator('.auth-lockout-code');
    await expect(codeSnippet).toBeVisible();
    await expect(codeSnippet).toContainText('kanban-ctl auth emergency-unlock --enable-local-admin');

    // Capture annotated screenshot 04
    await annotatedScreenshot(page, testInfo, {
      name: '04-lockout-prevented-banner',
      annotations: [
        {
          selector: '.auth-lockout-banner',
          label: 'Lockout Alert Banner',
          note: 'role="alert" with 15-minute handshake rule',
        },
        {
          selector: '.auth-card-row--pinned .auth-switch-label',
          label: 'Switch Rolled Back',
          note: 'LOCAL_ADMIN switch kept enabled',
        },
        {
          selector: '.auth-lockout-disclosure',
          label: 'Emergency Recovery CLI',
          note: 'kanban-ctl auth emergency-unlock command',
        },
      ],
    });
  });

  test('05-handshake-failed-hint: shows failure summary tooltip on failed LDAP card', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      ...getBaseShellMocks(),
      'GET /api/v1/auth/me': { json: loadFixture('me-admin-auth') },
      'GET /api/v1/admin/auth-cards': { json: loadFixture('admin-auth-cards') },
    });

    await page.goto('/admin/auth');
    await expect(page.locator('.auth-card-row')).toHaveCount(4);

    // Corporate Active Directory has failed chip
    const failedChip = page.locator('[data-testid="health-chip-corp-ad"]');
    await expect(failedChip).toBeVisible();
    await expect(failedChip).toContainText('FAILED');

    // Click warning EmojiHint to display failure popup
    const hintTrigger = failedChip.locator('.emoji-hint');
    await expect(hintTrigger).toBeVisible();
    await hintTrigger.click();

    // Verify popup content (HintPortal renders into document.body)
    const popup = page.locator('.emoji-hint-popup');
    await expect(popup).toBeVisible();
    await expect(popup).toContainText('Connection timeout to ldaps://dc01.corp:636');

    // Capture annotated screenshot 05
    await annotatedScreenshot(page, testInfo, {
      name: '05-handshake-failed-hint',
      annotations: [
        {
          selector: '[data-testid="health-chip-corp-ad"] .emoji-hint',
          label: 'Warning Trigger',
          note: '24px x 24px emoji hint trigger',
        },
        {
          selector: '.emoji-hint-popup',
          label: 'Check Summary Tooltip',
          note: 'TLS/bind failure plain text tooltip',
        },
      ],
    });
  });

  test('06-non-admin-not-found: non-server-admin renders uniform Not found or no access empty state', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      ...getBaseShellMocks(),
      'GET /api/v1/auth/me': { json: loadFixture('me-member') },
      'GET /api/v1/admin/auth-cards': {
        status: 404,
        json: { code: 'NOT_FOUND', message: 'Not found' },
      },
    });

    await page.goto('/admin/auth');

    // Uniform access gate empty state
    const emptyState = page.locator('.auth-empty-state');
    await expect(emptyState).toBeVisible();
    await expect(emptyState.locator('h2')).toHaveText('Not found or no access');

    // No cards or admin controls rendered
    await expect(page.locator('.auth-studio-list')).toHaveCount(0);
    await expect(page.locator('.auth-card-row')).toHaveCount(0);

    // Capture annotated screenshot 06
    await annotatedScreenshot(page, testInfo, {
      name: '06-non-admin-not-found',
      annotations: [
        {
          selector: '.auth-empty-state',
          label: 'Access Gate',
          note: 'Uniform Not found or no access view',
        },
      ],
    });
  });
});
