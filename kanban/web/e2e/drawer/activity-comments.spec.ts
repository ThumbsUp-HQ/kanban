import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { loadFixture, mockApi, type MockRecorder } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

const issueKan142 = {
  key: 'KAN-142',
  object_id: '11111111-1111-1111-1111-111111111111',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
  description_markdown: 'Detailed description of the auth hardening task.',
  priority: {
    slug: 'high',
    label: 'High',
    emoji: '⚡',
    sort_order: 2,
    sla_target: null,
  },
  state: {
    name: 'In Progress',
    group: 'started',
  },
  etag: '"etag-kan-142"',
};

async function setupActivityMocks(page: Page): Promise<MockRecorder> {
  await page.unroute('**/api/v1/**');

  const activityFixture = loadFixture<Record<string, unknown>>('activity-kan-142');
  const commentsFixture = loadFixture<Record<string, unknown>>('comments-kan-142');

  return mockApi(page, {
    'GET /api/v1/me': { json: loadFixture('me-adam') },
    'GET /api/v1/system/status': { json: loadFixture('system-status-prod') },
    'GET /api/v1/projects/KAN': { json: loadFixture('project-kan') },
    'GET /api/v1/issues/KAN-142': { json: issueKan142 },
    'GET /api/v1/objects/11111111-1111-1111-1111-111111111111/access': {
      json: loadFixture('access-kan-142'),
    },
    'GET /api/v1/objects/KAN/access': {
      json: loadFixture('access-project-kan'),
    },
    'GET /api/v1/issues/KAN-142/activity': (req) => {
      const url = new URL(`http://localhost${req.path}`);
      const tab = url.searchParams.get('tab') ?? 'all';
      const rawItems = activityFixture.items;
      const items: Record<string, unknown>[] = Array.isArray(rawItems)
        ? (rawItems as Record<string, unknown>[])
        : [];

      let filteredItems = items;
      if (tab === 'gates') {
        filteredItems = items.filter((item) => item.category === 'AGENT_GATE');
      } else if (tab === 'history') {
        filteredItems = items.filter((item) => item.category === 'HISTORY');
      }

      return {
        status: 200,
        json: {
          ...activityFixture,
          tab,
          items: filteredItems,
        },
      };
    },
    'GET /api/v1/issues/KAN-142/comments': { json: commentsFixture },
    'GET /api/v1/projects/KAN/assignee-suggestions': {
      json: {
        items: [
          {
            id: '01930000-0000-7000-8000-000000000001',
            handle: 'adam',
            display_name: 'Adam Outler',
            is_agent: false,
          },
          {
            id: '01930000-0000-7000-8000-000000000002',
            handle: 'agy-reviewer',
            display_name: 'agy-reviewer',
            is_agent: true,
          },
        ],
      },
    },
    'POST /api/v1/issues/KAN-142/comments': (req) => {
      const body = req.body as {
        body_markdown?: string;
        acknowledge_mentions?: string[];
      };
      const text = body.body_markdown ?? '';

      if (text.includes('@maya') && !body.acknowledge_mentions?.includes('u-maya')) {
        return {
          status: 409,
          json: {
            code: 'MENTION_ACCESS_WARNING',
            status: 409,
            title: 'Mention Access Warning',
            detail: '@maya cannot view this issue. Posting will NOT grant access or send a notification to @maya.',
            unauthorized_mentions: [
              {
                handle: 'maya',
                principal_id: 'u-maya',
              },
            ],
          },
        };
      }

      return {
        status: 201,
        json: {
          id: 'c-new-created',
          issue_id: '11111111-1111-1111-1111-111111111111',
          parent_comment_id: null,
          author_id: '01930000-0000-7000-8000-000000000001',
          author: {
            id: '01930000-0000-7000-8000-000000000001',
            handle: 'adam',
            display_name: 'Adam Outler',
          },
          body_markdown: text,
          created_at: '2026-11-12T10:00:00Z',
          deleted: false,
          etag: '"etag-c-new"',
          reactions: [],
          replies: [],
        },
      };
    },
    'PUT /api/v1/comments/:id/reactions/:emoji': {
      status: 200,
      json: { ok: true },
    },
    'DELETE /api/v1/comments/:id/reactions/:emoji': {
      status: 204,
    },
  });
}

test.describe('Activity Feed & Comments E2E Verification & Design Proofs (KB-P3-44)', () => {
  test('01: Activity 4-tab bar, gate rows, creator override, comments, reactions & composer', async ({
    page,
  }, testInfo) => {
    await setupActivityMocks(page);

    await page.goto('/__dev/drawer?peek=KAN-142');

    const activitySection = page.locator('.activity-section');
    await expect(activitySection).toBeVisible();

    const topComment = page.locator('#comment-c1111111-1111-1111-1111-111111111111');
    await expect(topComment).toBeVisible();

    const composer = page.locator('.comment-composer');
    await expect(composer).toBeVisible();

    // Probe styles across viewports
    await probeStyles(page, testInfo, {
      name: 'activity-drawer',
      probes: [
        {
          selector: '.activity-section',
          props: ['border-top-width', 'padding-top'],
        },
        {
          selector: '.activity-tablist',
          props: ['display', 'gap'],
        },
        {
          selector: '.comment-card',
          props: ['padding-top', 'padding-right', 'padding-bottom', 'padding-left', 'row-gap'],
        },
        {
          selector: '.comment-card__body',
          props: ['font-size', 'line-height'],
        },
        {
          selector: '.comment-replies',
          props: ['padding-left', 'margin-left'],
        },
        {
          selector: '.comment-composer',
          props: ['padding-top', 'padding-right', 'padding-bottom', 'padding-left', 'border-radius'],
        },
        {
          selector: '.activity-event-row .emoji-hint',
          props: ['width', 'height'],
        },
      ],
    });

    // Screenshot 01: 01-activity-all-tab-<project>.png
    await annotatedScreenshot(page, testInfo, {
      name: '01-activity-all-tab',
      annotations: [
        {
          selector: '.activity-tablist',
          label: '4-tab bar All | Comments (4) | History | 🤖 Gates (2)',
        },
        {
          selector: '[data-testid="gate-approved-row"]',
          label: '✅🤖 sec-review gate row',
        },
        {
          selector: '[data-testid="creator-override-row"]',
          label: '🔄 creator-override history row',
        },
        {
          selector: '#comment-c1111111-1111-1111-1111-111111111111',
          label: 'top-level comment (16px 18px) + 24px-indented reply',
        },
        {
          selector: '#comment-c1111111-1111-1111-1111-111111111111 .comment-card__reactions-bar',
          label: '8-emoji reactions bar (🚀 3)',
        },
        {
          selector: '.comment-composer',
          label: 'CommentComposer with formatting toolbar',
        },
      ],
    });
  });

  test('02: Gates tab hover tooltip with verdict details and jump-to-comment', async ({
    page,
  }, testInfo) => {
    await setupActivityMocks(page);

    await page.goto('/__dev/drawer?peek=KAN-142');
    await expect(page.locator('.activity-section')).toBeVisible();

    // Select Gates tab
    const gatesTab = page.locator('button[role="tab"]').filter({ hasText: 'Gates' });
    await gatesTab.click();
    await expect(gatesTab).toHaveAttribute('aria-selected', 'true');

    // Find the vetoed gate row and hover its emoji trigger
    const vetoRow = page.locator('[data-testid="gate-vetoed-row"]');
    await expect(vetoRow).toBeVisible();

    const trigger = vetoRow.locator('.emoji-hint');
    await trigger.hover();

    const popup = page.locator('.emoji-hint-popup');
    await expect(popup).toBeVisible();

    // Screenshot 02: 02-gates-tab-hover-<project>.png
    await annotatedScreenshot(page, testInfo, {
      name: '02-gates-tab-hover',
      annotations: [
        {
          selector: 'button[role="tab"][aria-selected="true"]',
          label: 'active 🤖 Gates (2) tab',
        },
        {
          selector: '[data-testid="gate-vetoed-row"] .emoji-hint',
          label: '🛑🤖 trigger (24x24)',
        },
        {
          selector: '.emoji-hint-popup',
          label: 'veto tooltip showing agent, harness, 2-line reason, and jump button',
        },
      ],
    });
  });

  test('03: Targeted permalink with highlight ring', async ({
    page,
  }, testInfo) => {
    await setupActivityMocks(page);

    // Open directly with comment permalink hash
    await page.goto('/__dev/drawer?peek=KAN-142#comment-c1111111-1111-1111-1111-111111111111');

    const targetedComment = page.locator('#comment-c1111111-1111-1111-1111-111111111111');
    await expect(targetedComment).toBeVisible();
    await expect(targetedComment).toHaveClass(/comment-card--targeted/);

    // Screenshot 03: 03-permalink-targeted-<project>.png
    await annotatedScreenshot(page, testInfo, {
      name: '03-permalink-targeted',
      annotations: [
        {
          selector: '#comment-c1111111-1111-1111-1111-111111111111',
          label: '.comment-card--targeted highlight ring',
        },
        {
          selector: '#comment-c1111111-1111-1111-1111-111111111111 .comment-card__permalink-btn',
          label: '# permalink button',
        },
      ],
    });
  });

  test('04: Mention autocomplete suggestions', async ({
    page,
  }, testInfo) => {
    await setupActivityMocks(page);

    await page.goto('/__dev/drawer?peek=KAN-142');
    await expect(page.locator('.activity-section')).toBeVisible();

    const textarea = page.locator('.comment-composer__textarea');
    await textarea.fill('Hello @a');

    const listbox = page.locator('.comment-composer__suggestions[role="listbox"]');
    await expect(listbox).toBeVisible();

    const adamOption = listbox.locator('[role="option"]').filter({ hasText: 'adam' });
    await expect(adamOption).toBeVisible();

    // Screenshot 04: 04-mention-autocomplete-<project>.png
    await annotatedScreenshot(page, testInfo, {
      name: '04-mention-autocomplete',
      annotations: [
        {
          selector: '.comment-composer__textarea',
          label: '@a token in composer textarea',
        },
        {
          selector: '.comment-composer__suggestions',
          label: 'VIEW-filtered suggestions popover (@adam, 🤖 agy-reviewer)',
        },
      ],
    });
  });

  test('05: Mention access warning banner on 409', async ({
    page,
  }, testInfo) => {
    await setupActivityMocks(page);

    await page.goto('/__dev/drawer?peek=KAN-142');
    await expect(page.locator('.activity-section')).toBeVisible();

    const textarea = page.locator('.comment-composer__textarea');
    await textarea.fill('Please review this issue @maya');
    await page.keyboard.press('Escape');

    const submitBtn = page.locator('button.composer-submit-btn');
    await submitBtn.click();

    const warningBanner = page.locator('.comment-composer__warning-banner[role="alert"]');
    await expect(warningBanner).toBeVisible();
    await expect(warningBanner).toContainText('@maya cannot view this issue');

    // Screenshot 05: 05-mention-no-access-warning-<project>.png
    await annotatedScreenshot(page, testInfo, {
      name: '05-mention-no-access-warning',
      annotations: [
        {
          selector: '.comment-composer__warning-banner',
          label: 'focused role="alert" banner for @maya',
        },
        {
          selector: '.comment-composer__textarea',
          label: 'preserved draft text',
        },
        {
          selector: '.warning-banner__actions',
          label: 'Post without granting access and Edit comment buttons',
        },
      ],
    });
  });
});
