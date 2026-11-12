/**
 * Dev Story Showcase for Breathable ProseMirror GFM Editor (KB-P3-45).
 * Mounted at /__dev/editor during development and E2E visual verification.
 */

import { useState, type JSX } from 'react';
import { MarkdownEditor } from '../editor/MarkdownEditor';
import './EditorStory.css';

export const INITIAL_STORY_MARKDOWN = `# Architectural Specification

| Component | Status | Latency |
| :--- | :---: | ---: |
| Database | Active | 0.8ms |
| ProseMirror | Ready | 1.2ms |

Fix teh typo in this paragraph to verify surgical update.

Check [Plane parity][1] for reference implementation.

\`\`\`\`ts
export function demo(): string {
  return "4-backtick fence";
}
\`\`\`\`

- [ ] Unfinished task
- [x] Completed task

[1]: https://kanban.hackedyour.info`;

export function EditorStory(): JSX.Element {
  const [markdown, setMarkdown] = useState(INITIAL_STORY_MARKDOWN);

  const isByteEqual = markdown === INITIAL_STORY_MARKDOWN;

  const handleFixTypo = (): void => {
    // Surgically replace "teh" with "the" in paragraph 3
    setMarkdown((prev) => prev.replace('Fix teh typo', 'Fix the typo'));
  };

  const handleReset = (): void => {
    setMarkdown(INITIAL_STORY_MARKDOWN);
  };

  const getProseMirrorElement = (): HTMLElement | null => {
    return document.querySelector('[data-testid="story-editor-wysiwyg"] .ProseMirror');
  };

  const handlePasteRichHtml = (): void => {
    const el = getProseMirrorElement();
    if (!el) return;

    const dt = new DataTransfer();
    const html =
      '<h2>Specifications</h2><table><thead><tr><th>Metric</th><th>Target</th></tr></thead><tbody><tr><td>Latency</td><td>&lt; 1ms</td></tr></tbody></table><span style="display:none">hidden payload 1</span><span hidden>hidden payload 2</span>';
    const plain = 'Specifications\n\nMetric | Target\nLatency | < 1ms';

    dt.setData('text/html', html);
    dt.setData('text/plain', plain);

    const pasteEvt = new ClipboardEvent('paste', {
      clipboardData: dt,
      bubbles: true,
      cancelable: true,
    });
    el.dispatchEvent(pasteEvt);
  };

  const handlePasteIdeCode = (): void => {
    const el = getProseMirrorElement();
    if (!el) return;

    const dt = new DataTransfer();
    const vscodeMeta = JSON.stringify({ mode: 'typescript' });
    const html = '<div><span style="color:#569cd6">const</span> <span style="color:#4fc1ff">server</span> = <span style="color:#dcdcaa">init</span>();</div>';
    const plain = 'const server = init();';

    dt.setData('vscode-editor-data', vscodeMeta);
    dt.setData('text/html', html);
    dt.setData('text/plain', plain);

    const pasteEvt = new ClipboardEvent('paste', {
      clipboardData: dt,
      bubbles: true,
      cancelable: true,
    });
    el.dispatchEvent(pasteEvt);
  };

  const handlePasteImage = (): void => {
    const el = getProseMirrorElement();
    if (!el) return;

    const dt = new DataTransfer();
    const file = new File(['fake-png-bytes'], 'screen.png', { type: 'image/png' });
    dt.items.add(file);

    const pasteEvt = new ClipboardEvent('paste', {
      clipboardData: dt,
      bubbles: true,
      cancelable: true,
    });
    el.dispatchEvent(pasteEvt);
  };

  const handleUndo = (): void => {
    const el = getProseMirrorElement();
    if (!el) return;

    const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent);
    const evt = new KeyboardEvent('keydown', {
      key: 'z',
      code: 'KeyZ',
      ctrlKey: !isMac,
      metaKey: isMac,
      bubbles: true,
      cancelable: true,
    });
    el.dispatchEvent(evt);
  };

  return (
    <div className="kb-editor-story" data-testid="editor-story">
      <header className="kb-editor-story__header">
        <h1 className="kb-editor-story__title">ProseMirror GFM Editor Showcase</h1>
        <p className="kb-editor-story__desc">
          Breathable typography, lossless sourceSlice preservation, and raw Markdown toggle (📝).
        </p>
      </header>

      <div className="kb-editor-story__actions">
        <button
          type="button"
          className="kb-editor-story__btn"
          data-testid="btn-fix-typo"
          onClick={handleFixTypo}
        >
          Fix typo in paragraph 3
        </button>
        <button
          type="button"
          className="kb-editor-story__btn"
          data-testid="btn-reset"
          onClick={handleReset}
        >
          Reset document
        </button>
        <button
          type="button"
          className="kb-editor-story__btn"
          data-testid="btn-paste-rich-html"
          onClick={handlePasteRichHtml}
        >
          Paste Rich HTML (2 hidden)
        </button>
        <button
          type="button"
          className="kb-editor-story__btn"
          data-testid="btn-paste-ide-code"
          onClick={handlePasteIdeCode}
        >
          Paste VS Code TS
        </button>
        <button
          type="button"
          className="kb-editor-story__btn"
          data-testid="btn-paste-image"
          onClick={handlePasteImage}
        >
          Paste PNG Image
        </button>
        <button
          type="button"
          className="kb-editor-story__btn"
          data-testid="btn-undo"
          onClick={handleUndo}
        >
          Undo (Cmd+Z)
        </button>
        <div
          className={`kb-editor-story__status${isByteEqual ? ' is-identical' : ''}`}
          data-testid="byte-equality-status"
        >
          {isByteEqual ? 'BYTE_IDENTICAL' : 'MODIFIED'}
        </div>
      </div>

      <main className="kb-editor-story__main">
        <MarkdownEditor
          surface="description"
          value={markdown}
          onChange={setMarkdown}
          ariaLabel="Editorial description editor"
          testId="story-editor"
        />
      </main>

      <section className="kb-editor-story__panels">
        <div className="kb-editor-story__panel">
          <h2 className="kb-editor-story__panel-title">Live Serialized Markdown Output</h2>
          <pre className="kb-editor-story__output" data-testid="serialized-output">
            {markdown}
          </pre>
        </div>
      </section>
    </div>
  );
}
