/**
 * Multi-Card Login, Local Admin + Passkey/TOTP Prompts & Setup Claim E2E Tests (KB-P3-35).
 * Validates S4.3, S4.2, S2.2, S6.1, S6.2 across Desktop, Tablet, and Mobile viewports.
 * Strict ASCII hyphens only.
 */

import { test, expect } from '../support/test';
import { mockApi, loadFixture } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

const VALID_SETUP_TOKEN = 'kb_setup_' + 'A'.repeat(43);

test.describe('Login & Setup Claim E2E Specifications (KB-P3-35)', () => {
  test.beforeEach(async ({ context }) => {
    // Provide CSRF cookie required by apiFetch on unsafe (POST) methods
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-123',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-login-cards: renders 3 top cards, Primary badge, gap 12px, collapsed disclosure', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
    });

    await page.goto('/login');
    await expect(page.locator('.auth-panel')).toBeVisible();

    // Exactly 3 top buttons
    const cardButtons = page.locator('.auth-card-list .auth-card-button');
    await expect(cardButtons).toHaveCount(3);
    await expect(cardButtons.nth(0)).toContainText('Okta SSO');
    await expect(cardButtons.nth(1)).toContainText('Corporate Active Directory');
    await expect(cardButtons.nth(2)).toContainText('GitHub Enterprise');

    // Primary badge only on the first card
    const primaryBadge = page.locator('.auth-primary-badge');
    await expect(primaryBadge).toHaveCount(1);
    await expect(cardButtons.nth(0).locator('.auth-primary-badge')).toBeVisible();

    // Local Admin disclosure exists and is collapsed
    const disclosureTrigger = page.locator(
      'button:has-text("Sign in with Local Admin + Passkey / TOTP")',
    );
    await expect(disclosureTrigger).toBeVisible();
    await expect(disclosureTrigger).toHaveAttribute('aria-expanded', 'false');

    // Probe layout styles
    await probeStyles(page, testInfo, {
      name: 'auth-login',
      probes: [
        { selector: '.auth-panel', props: ['padding'] },
        { selector: '.auth-card-list', props: ['row-gap'] },
        { selector: '.auth-card-button', props: ['padding', 'height', 'min-height'] },
        { selector: '.auth-section + .auth-section', props: ['margin-top'] },
      ],
    });

    // Capture visual proof
    await annotatedScreenshot(page, testInfo, {
      name: '01-login-cards',
      annotations: [
        {
          selector: '.auth-header-title-row',
          label: 'Header Title Row',
          note: '🛡️ Kanban Workspace Sign-in',
        },
        {
          selector: '.auth-card-item:first-child .auth-card-button',
          label: 'First Card (Primary)',
          note: 'padding 16px 18px',
        },
        {
          selector: '.auth-card-list',
          label: 'Card List Gap',
          note: '12px',
        },
        {
          selector: '.auth-card-item:nth-child(3) .auth-card-button',
          label: 'Third Card',
          note: 'order equals API order',
        },
        {
          selector: '.auth-disclosure-header',
          label: 'Local Admin Disclosure',
          note: 'collapsed',
        },
      ],
    });
  });

  test('02-login-ldap-expanded: expands LDAP form, checks inputs and submit button', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
    });

    await page.goto('/login');
    await expect(page.locator('.auth-panel')).toBeVisible();

    const ldapCardBtn = page.locator('.auth-card-button:has-text("Corporate Active Directory")');
    await ldapCardBtn.click();

    await expect(ldapCardBtn).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('#ldap-user-corp-ad')).toBeVisible();
    await expect(page.locator('#ldap-pwd-corp-ad')).toBeVisible();
    await expect(
      page.locator('.auth-ldap-submit-btn'),
    ).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '02-login-ldap-expanded',
      annotations: [
        {
          selector: '.auth-card-button[aria-expanded="true"]',
          label: 'Corp AD Expanded',
          note: 'aria-expanded=true',
        },
        {
          selector: '#ldap-user-corp-ad',
          label: 'Username Field',
          note: 'autocomplete="username"',
        },
        {
          selector: '#ldap-pwd-corp-ad',
          label: 'Password Field',
          note: 'type="password"',
        },
        {
          selector: '.auth-ldap-submit-btn',
          label: 'Submit Button',
          note: 'Sign in to Corporate Active Directory',
        },
      ],
    });
  });

  test('03-local-admin-hint: expands disclosure, hovers lock trigger, asserts exact EmojiHint text', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
    });

    await page.goto('/login');
    await expect(page.locator('.auth-panel')).toBeVisible();

    // Expand disclosure
    const disclosureBtn = page.locator(
      'button:has-text("Sign in with Local Admin + Passkey / TOTP")',
    );
    await disclosureBtn.click();
    await expect(page.locator('.auth-disclosure-panel')).toBeVisible();

    // Hover lock EmojiHint trigger
    const lockTrigger = page.locator('.auth-disclosure-header .emoji-hint');
    await lockTrigger.hover();

    const tooltip = page.locator('#kb-hint-root [role="tooltip"]');
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toHaveText(
      'Break-glass Local Administrator. Requires password plus Passkey or TOTP (AAL2). Use only when your identity provider is unavailable.',
    );

    await annotatedScreenshot(page, testInfo, {
      name: '03-local-admin-hint',
      annotations: [
        {
          selector: '.auth-disclosure-panel',
          label: 'Disclosure Expanded',
          note: 'form panel visible',
        },
        {
          selector: '.auth-disclosure-header .emoji-hint',
          label: 'Lock Trigger',
          note: '🔒 hint button',
        },
        {
          selector: '#kb-hint-root [role="tooltip"]',
          label: 'Tooltip Text',
          note: 'Break-glass Local Administrator...',
        },
      ],
    });
  });

  test('04-second-factor-totp: tests tablist, Authenticator code tab, 6-digit input', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
      'POST /api/v1/auth/local/login': {
        json: {
          status: 'mfa_required',
          challenge_id: 'chall-totp-e2e',
          methods: ['totp', 'recovery'],
        },
      },
    });

    await page.goto('/login');
    await expect(page.locator('.auth-panel')).toBeVisible();

    // Expand disclosure and submit local credentials
    await page.locator('button:has-text("Sign in with Local Admin + Passkey / TOTP")').click();
    await page.locator('#local-admin-username').fill('admin');
    await page.locator('#local-admin-password').fill('AdminPassword123!');
    await page.locator('button:has-text("Sign in as Local Administrator")').click();

    // Wait for SecondFactorStep
    await expect(page.locator('.auth-second-factor-step')).toBeVisible();

    // Authenticator tab is active
    const totpTab = page.locator('.auth-tab[aria-selected="true"]');
    await expect(totpTab).toHaveText('Authenticator code');
    await expect(page.locator('#totp-code-input')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '04-second-factor-totp',
      annotations: [
        {
          selector: '.auth-tablist',
          label: 'Method Tablist',
          note: 'methods order from API',
        },
        {
          selector: '.auth-tab[aria-selected="true"]',
          label: 'Selected Tab',
          note: 'Authenticator code',
        },
        {
          selector: '#totp-code-input',
          label: '6-digit Input',
          note: 'auto-submits on 6 digits',
        },
      ],
    });
  });

  test('05-login-error: tests role=alert with exact error copy and verifies alert focus', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-kan') },
      'POST /api/v1/auth/local/login': {
        status: 401,
        json: {
          status: 401,
          code: 'INVALID_CREDENTIALS',
          title: 'Unauthorized',
          detail: 'Invalid credentials provided',
        },
      },
    });

    await page.goto('/login');
    await expect(page.locator('.auth-panel')).toBeVisible();

    await page.locator('button:has-text("Sign in with Local Admin + Passkey / TOTP")').click();
    await page.locator('#local-admin-username').fill('admin');
    await page.locator('#local-admin-password').fill('WrongPassword123!');
    await page.locator('button:has-text("Sign in as Local Administrator")').click();

    const alert = page.locator('.auth-alert[role="alert"]');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText('Sign-in failed. Check your credentials and try again.');
    await expect(alert).toBeFocused();

    await annotatedScreenshot(page, testInfo, {
      name: '05-login-error',
      annotations: [
        {
          selector: '.auth-alert[role="alert"]',
          label: 'Error Alert',
          note: 'Sign-in failed. Check your credentials and try again.',
        },
        {
          selector: '.auth-alert[role="alert"]',
          label: 'Focused Element',
          note: 'focus moved to role=alert',
        },
      ],
    });
  });

  test('06-login-hostile-card: renders hostile card with literal text escaping and clamped length', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      'GET /api/v1/auth/cards': { json: loadFixture('auth-cards-hostile') },
    });

    await page.goto('/login');
    await expect(page.locator('.auth-panel')).toBeVisible();

    // Literal escaped XSS text
    const firstDisplayName = page.locator('.auth-card-item:first-child .auth-card-display-name');
    await expect(firstDisplayName).toHaveText('<img src=x onerror=alert(1)>');

    // Zero <img> tags created in DOM
    const imgCount = await page.locator('.auth-panel img').count();
    expect(imgCount).toBe(0);

    // Second card clamped name
    const secondDisplayName = page.locator('.auth-card-item:nth-child(2) .auth-card-display-name');
    const textContent = await secondDisplayName.textContent();
    expect(textContent).toContain('...');
    expect(textContent?.length).toBeLessThanOrEqual(83); // 80 chars + '...'

    await annotatedScreenshot(page, testInfo, {
      name: '06-login-hostile-card',
      annotations: [
        {
          selector: '.auth-card-item:first-child .auth-card-display-name',
          label: 'Literal Escaped XSS',
          note: 'zero <img> tags created',
        },
        {
          selector: '.auth-card-item:nth-child(2) .auth-card-display-name',
          label: 'Clamped Long Name',
          note: 'clamped to 80 chars + ...',
        },
      ],
    });
  });

  test('07-setup-step1: verifies clean address bar, token hygiene, and Step 1 fields', async ({
    page,
  }, testInfo) => {
    await page.goto(`/setup?token=${VALID_SETUP_TOKEN}`);
    await expect(page.locator('.auth-panel')).toBeVisible();

    // Token hygiene proof: URL pathname is /setup without token query param
    expect(page.url().endsWith('/setup')).toBe(true);

    // Document body must NOT contain setup token
    const bodyHtml = await page.content();
    expect(bodyHtml.includes(VALID_SETUP_TOKEN)).toBe(false);

    // Step indicator
    await expect(page.locator('.auth-step-pill')).toHaveText('Step 1 of 3');
    await expect(page.locator('#setup-username')).toBeVisible();

    await annotatedScreenshot(page, testInfo, {
      name: '07-setup-step1',
      annotations: [
        {
          selector: '[data-testid="current-url"]',
          label: 'Clean Address Bar',
          note: 'token stripped via replaceState',
        },
        {
          selector: '.auth-step-pill',
          label: 'Step Indicator',
          note: 'Step 1 of 3',
        },
        {
          selector: '#setup-username',
          label: 'Username Field',
          note: 'Server Administrator',
        },
      ],
    });
  });

  test('08-setup-recovery-codes: walks through setup to Step 3, asserts 10 codes and disabled button', async ({
    page,
  }, testInfo) => {
    await mockApi(page, {
      'POST /api/v1/setup/claim': {
        json: { status: 'enrollment_required', enrollment_id: 'enr-e2e-setup' },
      },
      'POST /api/v1/auth/totp/enroll': {
        json: {
          secret_base32: 'JBSWY3DPEHPK3PXP',
          otpauth_uri: 'otpauth://totp/kanban:admin?secret=JBSWY3DPEHPK3PXP',
        },
      },
      'POST /api/v1/auth/totp/enroll/verify': {
        json: {
          status: 'enrolled',
          recovery_codes: [
            'code-01-aaaa',
            'code-02-bbbb',
            'code-03-cccc',
            'code-04-dddd',
            'code-05-eeee',
            'code-06-ffff',
            'code-07-gggg',
            'code-08-hhhh',
            'code-09-iiii',
            'code-10-jjjj',
          ],
        },
      },
    });

    await page.goto(`/setup?token=${VALID_SETUP_TOKEN}`);
    await expect(page.locator('.auth-panel')).toBeVisible();

    // Step 1: Submit master password
    await page.locator('#setup-password').fill('SuperMasterPassword14Long!');
    await page.locator('#setup-confirm-password').fill('SuperMasterPassword14Long!');
    await page.locator('button:has-text("Claim Instance & Continue")').click();

    // Step 2: Choose Authenticator App and verify
    await expect(page.locator('.auth-step-pill')).toHaveText('Step 2 of 3');
    await page.locator('.auth-tab:has-text("Authenticator App")').click();
    await expect(page.locator('#setup-totp-verify')).toBeVisible();
    await page.locator('#setup-totp-verify').fill('123456');
    await page.locator('button:has-text("Verify & Continue")').click();

    // Step 3: Emergency recovery codes
    await expect(page.locator('.auth-step-pill')).toHaveText('Step 3 of 3');
    const codeItems = page.locator('.auth-recovery-code-item');
    await expect(codeItems).toHaveCount(10);

    // Hover recovery hint
    const recoveryHint = page.locator('button[aria-label="About recovery codes"]');
    await recoveryHint.hover();
    const tooltip = page.locator('#kb-hint-root [role="tooltip"]');
    await expect(tooltip).toBeVisible();

    // Continue button disabled until checkbox is checked
    const continueBtn = page.locator('button:has-text("Continue to workspace")');
    await expect(continueBtn).toBeDisabled();

    await annotatedScreenshot(page, testInfo, {
      name: '08-setup-recovery-codes',
      annotations: [
        {
          selector: '.auth-recovery-grid',
          label: '10 Recovery Codes',
          note: '2-column monospace grid',
        },
        {
          selector: '#kb-hint-root [role="tooltip"]',
          label: 'Recovery Hint',
          note: '🔒 Each recovery code works once...',
        },
        {
          selector: '.auth-checkbox-wrap input[type="checkbox"]',
          label: 'Unchecked Checkbox',
          note: 'must be checked to proceed',
        },
        {
          selector: 'button:has-text("Continue to workspace")',
          label: 'Disabled Continue Button',
          note: 'disabled until confirmed',
        },
      ],
    });
  });

  test('09-setup-invalid-token: asserts invalid setup link message and absence of form', async ({
    page,
  }, testInfo) => {
    await page.goto('/setup?token=invalid_too_short');
    await expect(page.locator('.auth-panel')).toBeVisible();

    // Invalid message displayed
    await expect(
      page.locator('text=This setup link is invalid or has already been used.'),
    ).toBeVisible();

    // Form is not rendered
    const formCount = await page.locator('.auth-panel form').count();
    expect(formCount).toBe(0);

    await annotatedScreenshot(page, testInfo, {
      name: '09-setup-invalid-token',
      annotations: [
        {
          selector: '.auth-panel',
          label: 'Invalid Link Message',
          note: 'Check container logs...',
        },
        {
          selector: '.auth-panel',
          label: 'Absence of Form',
          note: 'zero form fields rendered',
        },
      ],
    });
  });
});
