/**
 * Playwright E2E Tests for 5-Branch Clipboard Classifier & Hidden-DOM Pruner (KB-P3-46).
 * Validates Branch 1 (binary image upload), Branch 2 (IDE code wrapper bypass),
 * Branch 3 (rich HTML autoconvert with sanitized 🧼 pill), and Branch 5 (two-step Cmd+Z undo).
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

test.describe('Clipboard 5-Branch Auto-Convert & Sanitized Pill E2E Verification (KB-P3-46)', () => {
  test.beforeEach(async ({ page }) => {
    const response = await page.goto('/__dev/editor');
    expect(response).not.toBeNull();
    expect(response?.status()).toBe(200);
    await expect(page.locator('[data-testid="editor-story"]')).toBeVisible();
  });

  test('01: Branch 3 HTML paste converts to clean Markdown and renders sanitized status pill with exact tooltip', async ({
    page,
  }, testInfo) => {
    // 1. Clear editor so converted content is front and center
    const editor = page.locator('[data-testid="story-editor-wysiwyg"] .ProseMirror');
    await editor.click();
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.press('Backspace');

    // 2. Trigger Rich HTML paste with 2 hidden payloads
    const pasteBtn = page.locator('[data-testid="btn-paste-rich-html"]');
    await pasteBtn.click();

    // 3. Assert converted GFM elements appear in the editor
    const table = page.locator('[data-testid="story-editor-wysiwyg"] table');
    await expect(table).toBeVisible();

    const heading = page.locator('[data-testid="story-editor-wysiwyg"] h2');
    await expect(heading).toHaveText('Specifications');

    // 4. Assert serialized markdown output reflects converted GFM
    const serialized = page.locator('[data-testid="serialized-output"]');
    await expect(serialized).toContainText('## Specifications');
    await expect(serialized).toContainText('| Metric');
    await expect(serialized).toContainText('| Target');
    await expect(serialized).not.toContainText('hidden payload');

    // 5. Assert sanitized status pill is mounted
    const pill = page.locator('[data-testid="story-editor-sanitized-pill"]');
    await expect(pill).toBeVisible();

    const pillLabel = page.locator('[data-testid="story-editor-sanitized-pill-label"]');
    await expect(pillLabel).toHaveText('Converted to Markdown');

    // 6. Hover emoji hint trigger to display tooltip
    const emojiHint = page.locator('[data-testid="story-editor-sanitized-pill-emoji-hint"]');
    await expect(emojiHint).toBeVisible();
    await emojiHint.hover();

    const tooltip = page.locator('[data-testid="story-editor-sanitized-pill-emoji-hint-popup"]');
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toContainText(
      'Converted pasted HTML to clean Markdown - Cmd+Z to paste plain text (stripped 2 hidden element(s))',
    );

    // 7. Capture computed style measurements for the pill
    await probeStyles(page, testInfo, {
      name: 'sanitized-paste-pill-measurements',
      probes: [
        {
          selector: '.sanitized-paste-pill',
          props: ['position', 'right', 'bottom', 'z-index'],
        },
        {
          selector: '.sanitized-paste-pill .emoji-hint',
          props: ['width', 'height', 'display', 'align-items', 'justify-content'],
        },
      ],
    });

    // 8. Capture annotated screenshot 01
    await annotatedScreenshot(page, testInfo, {
      name: '01-html-paste-with-pill',
      annotations: [
        {
          selector: '[data-testid="story-editor-wysiwyg"] table',
          label: 'Converted GFM Table',
          note: 'Rich HTML converted to canonical pipe table',
        },
        {
          selector: '[data-testid="story-editor-sanitized-pill-emoji-hint"]',
          label: 'Sanitized 🧼 Pill',
          note: '24x24 status pill indicating clean conversion',
        },
        {
          selector: '[data-testid="story-editor-sanitized-pill-emoji-hint-popup"]',
          label: 'Paste-Jacking Defense Hint',
          note: 'Tooltip showing 2 hidden elements stripped with Cmd+Z hint',
        },
      ],
    });
  });

  test('02: Two-step Cmd/Ctrl+Z undo reverts converted HTML to plain text', async ({
    page,
  }, testInfo) => {
    // 1. Clear editor so converted content is front and center
    const editor = page.locator('[data-testid="story-editor-wysiwyg"] .ProseMirror');
    await editor.click();
    await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.press('Backspace');

    // 2. Paste rich HTML
    const pasteBtn = page.locator('[data-testid="btn-paste-rich-html"]');
    await pasteBtn.click();

    // Verify converted table is present
    await expect(page.locator('[data-testid="story-editor-wysiwyg"] table')).toBeVisible();

    // 3. Trigger first Undo (Cmd+Z)
    const undoBtn = page.locator('[data-testid="btn-undo"]');
    await undoBtn.click();

    // 4. Assert editor content reverted to unformatted plain text
    const serialized = page.locator('[data-testid="serialized-output"]');
    await expect(serialized).toContainText('Specifications');
    await expect(serialized).toContainText('Metric | Target');
    await expect(serialized).toContainText('Latency | < 1ms');
    await expect(serialized).not.toContainText('## Specifications');

    // 5. Capture annotated screenshot 02
    await annotatedScreenshot(page, testInfo, {
      name: '02-cmd-z-plaintext-fallback',
      annotations: [
        {
          selector: '[data-testid="btn-undo"]',
          label: 'Cmd+Z Undo Trigger',
          note: 'First undo reverts to plain text paste',
        },
        {
          selector: '[data-testid="story-editor-wysiwyg"]',
          label: 'Plain-Text Fallback',
          note: 'Unformatted plain-text content in editor',
        },
        {
          selector: '[data-testid="serialized-output"]',
          label: 'Serialized Plain Text',
          note: 'Live serialized output confirming plain-text state',
        },
      ],
    });
  });

  test('03: Branch 2 IDE paste converts VS Code HTML into clean fenced code block', async ({
    page,
  }, testInfo) => {
    // 1. Reset document
    await page.locator('[data-testid="btn-reset"]').click();

    // 2. Paste VS Code TypeScript snippet
    await page.locator('[data-testid="btn-paste-ide-code"]').click();

    // 3. Assert code block rendered in editor
    const codeBlock = page.locator('[data-testid="story-editor-wysiwyg"] pre').filter({ hasText: 'const server = init();' });
    await expect(codeBlock).toBeVisible();
    await expect(codeBlock).toContainText('const server = init();');

    // 4. Assert serialized markdown has canonical ts code fence
    const serialized = page.locator('[data-testid="serialized-output"]');
    await expect(serialized).toContainText('```ts');
    await expect(serialized).toContainText('const server = init();');

    // 5. Capture annotated screenshot 03
    await annotatedScreenshot(page, testInfo, {
      name: '03-ide-code-paste',
      annotations: [
        {
          selector: '[data-testid="btn-paste-ide-code"]',
          label: 'IDE Code Paste Trigger',
          note: 'VS Code HTML and metadata paste trigger',
        },
        {
          selector: '[data-testid="story-editor-wysiwyg"] pre:has-text("const server = init();")',
          label: 'Fenced Code Block',
          note: 'Clean fenced ts code block with zero syntax span noise',
        },
        {
          selector: '[data-testid="serialized-output"]',
          label: 'Canonical Code Fence',
          note: 'Serialized markdown with ts language identifier',
        },
      ],
    });
  });

  test('04: Branch 1 binary image paste optimistic placeholder and attachment upload', async ({
    page,
  }, testInfo) => {
    // 1. Mock attachment upload API endpoint
    await page.route('**/api/v1/projects/*/attachments', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'att_0196ed42',
          markdown_uri: 'attachment://att_0196ed42',
        }),
      });
    });

    // 2. Reset document
    await page.locator('[data-testid="btn-reset"]').click();

    // 3. Paste PNG image
    await page.locator('[data-testid="btn-paste-image"]').click();

    // 4. Assert serialized output contains attachment URI
    const serialized = page.locator('[data-testid="serialized-output"]');
    await expect(serialized).toContainText('![screen.png](attachment://att_0196ed42)');

    // 5. Capture annotated screenshot 04
    await annotatedScreenshot(page, testInfo, {
      name: '04-image-paste-upload',
      annotations: [
        {
          selector: '[data-testid="btn-paste-image"]',
          label: 'Binary Image Paste Trigger',
          note: 'PNG clipboard paste trigger',
        },
        {
          selector: '[data-testid="serialized-output"]',
          label: 'Attachment Markdown URI',
          note: 'Optimistic placeholder replaced with attachment:// URI',
        },
      ],
    });
  });
});
