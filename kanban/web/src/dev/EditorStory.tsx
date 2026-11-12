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
