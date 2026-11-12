/**
 * Dev Story Showcase for Breathable ProseMirror GFM Editor (KB-P3-45, KB-P3-47).
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

export const MERMAID_SAMPLE_MARKDOWN = `# Architectural Specification

## System Topology
\`\`\`mermaid
flowchart TD
  Client[Web Client] --> Gateway[API Gateway]
  Gateway --> DB[(PostgreSQL)]
\`\`\`

## Authentication Flow
\`\`\`mermaid
sequenceDiagram
  autonumber
  Client->>Auth: POST /api/v1/auth/login
  Auth-->>Client: 200 OK Set-Cookie
\`\`\`
`;

export function generateOverlimitMarkdown(): string {
  let res = '## Overlimit Node Cap Fallback\n\n```mermaid\nflowchart TD\n';
  for (let i = 0; i <= 400; i++) {
    res += `  N${String(i)}["Node ${String(i)}"]\n`;
  }
  res += '```\n';
  return res;
}

export function EditorStory(): JSX.Element {
  const [markdown, setMarkdown] = useState(INITIAL_STORY_MARKDOWN);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    if (typeof document !== 'undefined') {
      return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    }
    return 'light';
  });

  const isByteEqual = markdown === INITIAL_STORY_MARKDOWN;

  const handleFixTypo = (): void => {
    // Surgically replace "teh" with "the" in paragraph 3
    setMarkdown((prev) => prev.replace('Fix teh typo', 'Fix the typo'));
  };

  const handleReset = (): void => {
    setMarkdown(INITIAL_STORY_MARKDOWN);
  };

  const handleLoadMermaid = (): void => {
    setMarkdown(MERMAID_SAMPLE_MARKDOWN);
  };

  const handleLoadFallback = (): void => {
    setMarkdown(generateOverlimitMarkdown());
  };

  const handleToggleTheme = (): void => {
    const nextTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(nextTheme);
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', nextTheme);
    }
  };

  return (
    <div className="kb-editor-story" data-testid="editor-story">
      <header className="kb-editor-story__header">
        <h1 className="kb-editor-story__title">ProseMirror GFM Editor Showcase</h1>
        <p className="kb-editor-story__desc">
          Breathable typography, lossless sourceSlice preservation, and raw Markdown toggle.
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
          data-testid="btn-load-mermaid"
          onClick={handleLoadMermaid}
        >
          Load Mermaid Diagrams
        </button>
        <button
          type="button"
          className="kb-editor-story__btn"
          data-testid="btn-load-fallback"
          onClick={handleLoadFallback}
        >
          Simulate Fallback Diagram
        </button>
        <button
          type="button"
          className="kb-editor-story__btn"
          data-testid="btn-toggle-theme"
          onClick={handleToggleTheme}
        >
          Toggle Theme ({theme === 'light' ? 'Dark' : 'Light'})
        </button>
        <div
          className="kb-editor-story__theme-badge"
          data-testid="theme-indicator"
        >
          {theme === 'dark' ? 'Dark' : 'Light'}
        </div>
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
