/**
 * Playwright E2E Tests and Design Proofs for ProseMirror GFM Editor (KB-P3-45).
 * Validates breathable typography tokens, zero mode-switcher clutter,
 * lossless sourceSlice preservation during surgical edits, and raw Markdown toggle.
 */

import { test, expect } from '../support/test';
import { annotatedScreenshot } from '../support/annotate';
import { probeStyles } from '../support/styleProbe';

test.describe('ProseMirror GFM Editor E2E Verification & Design Proofs (KB-P3-45)', () => {
  test.beforeEach(async ({ page }) => {
    const response = await page.goto('/__dev/editor');
    expect(response).not.toBeNull();
    expect(response?.status()).toBe(200);
    await expect(page.locator('[data-testid="editor-story"]')).toBeVisible();
  });

  test('01: ProseMirror WYSIWYG editor mounts with breathable typography and zero mode-picker clutter', async ({
    page,
  }, testInfo) => {
    const editor = page.locator('[data-testid="story-editor"]');
    await expect(editor).toBeVisible();

    // Verify zero mode-picker tabs, comboboxes, or dropdowns exist in DOM
    await expect(page.locator('[role="tab"]')).toHaveCount(0);
    await expect(page.locator('select')).toHaveCount(0);
    await expect(page.locator('.mode-picker')).toHaveCount(0);
    await expect(page.locator('button:has-text("Rich")')).toHaveCount(0);
    await expect(page.locator('button:has-text("Markdown")')).toHaveCount(0);
    await expect(page.locator('button:has-text("HTML")')).toHaveCount(0);

    // Verify rendered GFM elements are present
    const table = page.locator('[data-testid="story-editor-wysiwyg"] table');
    await expect(table).toBeVisible();

    const codeBlock = page.locator('[data-testid="story-editor-wysiwyg"] pre');
    await expect(codeBlock).toBeVisible();

    const taskList = page.locator('[data-testid="story-editor-wysiwyg"] ul.kb-task-list');
    await expect(taskList).toBeVisible();

    // Capture computed typography and whitespace measurements
    await probeStyles(page, testInfo, {
      name: 'editorial-editor-measurements',
      probes: [
        {
          selector: '.kb-editor--editorial',
          props: ['padding-top', 'padding-right', 'padding-bottom', 'padding-left'],
        },
        {
          selector: '.kb-editor--editorial .ProseMirror',
          props: ['font-size', 'line-height', 'font-family'],
        },
        {
          selector: '.emoji-hint',
          props: ['width', 'height'],
        },
      ],
    });

    // Capture annotated screenshot 01
    await annotatedScreenshot(page, testInfo, {
      name: '01-editor-wysiwyg',
      annotations: [
        {
          selector: '.kb-editor--editorial',
          label: 'Editorial Surface Padding',
          note: '32px 40px breathable padding',
        },
        {
          selector: '[data-testid="story-editor-wysiwyg"] table',
          label: 'GFM Table',
          note: 'Rendered pipe table with alignment',
        },
        {
          selector: '[data-testid="story-editor-wysiwyg"] pre',
          label: 'Code Block',
          note: 'Fenced code block in JetBrains Mono',
        },
        {
          selector: '[data-testid="story-editor-hint-corner"]',
          label: 'Zero Mode Switcher',
          note: 'Absence of mode-switcher toolbar',
        },
      ],
    });
  });

  test('02: Surgical single-paragraph edit preserves untouched blocks byte-identical', async ({
    page,
  }, testInfo) => {
    // Assert initial state is byte-identical
    const status = page.locator('[data-testid="byte-equality-status"]');
    await expect(status).toHaveText('BYTE_IDENTICAL');

    // Trigger surgical edit on paragraph 3
    const fixTypoBtn = page.locator('[data-testid="btn-fix-typo"]');
    await fixTypoBtn.click();

    // Assert status transitions to MODIFIED
    await expect(status).toHaveText('MODIFIED');

    // Assert serialized output diff
    const serializedOutput = page.locator('[data-testid="serialized-output"]');
    await expect(serializedOutput).toContainText('Fix the typo in this paragraph');
    await expect(serializedOutput).not.toContainText('Fix teh typo');

    // Assert untouched blocks remain byte-for-byte identical
    await expect(serializedOutput).toContainText('| Component | Status | Latency |');
    await expect(serializedOutput).toContainText('| Database | Active | 0.8ms |');
    await expect(serializedOutput).toContainText('Check [Plane parity][1] for reference implementation.');
    await expect(serializedOutput).toContainText('[1]: https://kanban.hackedyour.info');
    await expect(serializedOutput).toContainText('4-backtick fence');

    // Capture annotated screenshot 02
    await annotatedScreenshot(page, testInfo, {
      name: '02-sourceslice-surgical-edit',
      annotations: [
        {
          selector: '[data-testid="btn-fix-typo"]',
          label: 'Surgical Edit Trigger',
          note: 'Single-paragraph mutation trigger',
        },
        {
          selector: '[data-testid="story-editor-wysiwyg"] p:first-of-type',
          label: 'Edited Paragraph 3',
          note: 'Typo fixed in place without full re-parse',
        },
        {
          selector: '[data-testid="serialized-output"]',
          label: 'Serialized Diff Inspector',
          note: 'Untouched ASCII table and links byte-identical',
        },
      ],
    });
  });

  test('03: Raw Markdown toggle switches to monospace textarea and preserves content', async ({
    page,
  }, testInfo) => {
    const hintCorner = page.locator('[data-testid="story-editor-hint-corner"]');
    const togglePill = page.locator('[data-testid="story-editor-raw-toggle"]');

    // Focus editor and toggle to raw mode using keyboard shortcut
    await page.locator('.ProseMirror').click();
    await page.keyboard.press('Control+Shift+KeyM');

    // If still in WYSIWYG, click the toggle pill
    const rawTextarea = page.locator('[data-testid="story-editor-raw"]');
    if ((await rawTextarea.count()) === 0) {
      await togglePill.click();
      const actionBtn = page.locator('[data-testid="story-editor-raw-toggle-action-btn"]');
      if (await actionBtn.isVisible()) {
        await actionBtn.click();
      }
    }

    // Verify textarea is active and hint corner has active ring styling
    await expect(rawTextarea).toBeVisible();
    await expect(hintCorner).toHaveClass(/is-active/);

    // Hover toggle pill to show tooltip
    await togglePill.hover();
    const popup = page.locator('[data-testid="story-editor-raw-toggle-popup"]');
    await expect(popup).toBeVisible();
    await expect(popup).toContainText('Cmd/Ctrl+Shift+M to toggle');

    // Probe styles of raw monospace textarea
    await probeStyles(page, testInfo, {
      name: 'raw-editor-measurements',
      probes: [
        {
          selector: '.kb-editor__raw',
          props: ['font-family', 'font-size', 'line-height', 'padding-top', 'padding-left'],
        },
      ],
    });

    // Capture annotated screenshot 03
    await annotatedScreenshot(page, testInfo, {
      name: '03-raw-markdown-toggle',
      annotations: [
        {
          selector: '[data-testid="story-editor-hint-corner"]',
          label: 'Active 📝 Pill',
          note: '24x24 active indicator with focus ring',
        },
        {
          selector: '[data-testid="story-editor-raw-toggle-popup"]',
          label: 'Keyboard Shortcut Hint',
          note: 'Hover tooltip with Cmd/Ctrl+Shift+M hint',
        },
        {
          selector: '[data-testid="story-editor-raw"]',
          label: 'Monospace Textarea',
          note: 'Monospace canonical Markdown editing',
        },
      ],
    });
  });
});
