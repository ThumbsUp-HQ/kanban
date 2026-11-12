/**
 * Unit & Integration Tests for 5-Branch Clipboard Classifier (KB-P3-46, S5.2).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { EditorState } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { undo } from 'prosemirror-history';
import { editorSchema } from '../schema';
import { parseMarkdown } from '../parseMarkdown';
import { serializeMarkdown } from '../serializeMarkdown';
import { createEditorPlugins } from '../editorSurfaceFactory';
import {
  autoConvertPastePlugin,
  convertHtmlToMarkdown,
  defaultUploadAttachment,
  MAX_ATTACHMENT_BYTES,
} from './autoConvertPaste';
import { MarkdownEditor } from '../MarkdownEditor';

class PolyfilledClipboardEvent extends Event {
  clipboardData: DataTransfer;
  constructor(
    type: string,
    init?: { clipboardData?: DataTransfer; bubbles?: boolean; cancelable?: boolean },
  ) {
    super(type, init);
    this.clipboardData = init?.clipboardData ?? ({} as DataTransfer);
  }
}

const SafeClipboardEvent =
  typeof ClipboardEvent !== 'undefined' ? ClipboardEvent : PolyfilledClipboardEvent;

function createMockDataTransfer(data: {
  html?: string;
  text?: string;
  vscode?: string;
  files?: File[];
}): DataTransfer {
  const dataStore: Record<string, string> = {};
  if (data.html) dataStore['text/html'] = data.html;
  if (data.text) dataStore['text/plain'] = data.text;
  if (data.vscode) dataStore['vscode-editor-data'] = data.vscode;

  const files = data.files ?? [];

  return {
    getData: (format: string) => dataStore[format] ?? '',
    types: Object.keys(dataStore),
    files: files as unknown as FileList,
    items: {
      length: files.length,
      add: () => undefined,
      remove: () => undefined,
      clear: () => undefined,
    } as unknown as DataTransferItemList,
    clearData: () => undefined,
    setData: () => undefined,
    dropEffect: 'none',
    effectAllowed: 'none',
  } as unknown as DataTransfer;
}

function dispatchSyntheticPaste(view: EditorView, dt: DataTransfer): void {
  const event = new SafeClipboardEvent('paste', {
    clipboardData: dt,
    bubbles: true,
    cancelable: true,
  });
  view.someProp('handlePaste', (fn) => fn(view, event, view.state.doc.slice(0, 0)));
}

describe('autoConvertPaste', () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it('Case 4: Branch 3 (Confluence / Google Docs / Jira HTML) converts rich HTML to canonical GFM and disarms javascript links', () => {
    const richHtml = `
      <h2>Architecture & Testing</h2>
      <table>
        <thead>
          <tr><th>Metric</th><th>Target</th></tr>
        </thead>
        <tbody>
          <tr><td>Coverage</td><td>95%</td></tr>
        </tbody>
      </table>
      <ul>
        <li><input type="checkbox" checked> Task 1 completed</li>
        <li><input type="checkbox"> Task 2 pending</li>
      </ul>
      <p>
        <a href="https://example.com">Documentation</a>
        <a href="javascript:alert(1)">Hostile Link</a>
      </p>
    `;

    const gfm = convertHtmlToMarkdown(richHtml);

    expect(gfm).toContain('## Architecture & Testing');
    expect(gfm).toContain('| Metric');
    expect(gfm).toContain('| Target');
    expect(gfm).toContain('| Coverage');
    expect(gfm).toContain('- [x] Task 1 completed');
    expect(gfm).toContain('- [ ] Task 2 pending');
    expect(gfm).toContain('[Documentation](https://example.com)');
    // javascript: link must be disarmed into plain text
    expect(gfm).toContain('Hostile Link');
    expect(gfm).not.toContain('javascript:alert(1)');
    expect(gfm).not.toContain('[Hostile Link]()');
  });

  it('Case 2: Branch 1 (Attachment Upload) uploads PNG and inserts markdown URI', async () => {
    const mockUpload = vi.fn().mockResolvedValue({
      markdownUri: 'attachment://att_0196ed42',
      id: 'att_0196ed42',
    });
    const handleAnnounce = vi.fn();

    const { doc } = parseMarkdown('Initial text.');
    let currentDoc = doc;

    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [
        ...createEditorPlugins('description'),
        autoConvertPastePlugin({
          projectId: 'KAN',
          onAnnounce: handleAnnounce,
          uploadAttachment: mockUpload,
        }),
      ],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, {
      state,
      dispatchTransaction(tr) {
        const nextState = view.state.apply(tr);
        view.updateState(nextState);
        currentDoc = nextState.doc;
      },
    });

    const pngFile = new File(['fake-png-content'], 'screen.png', { type: 'image/png' });
    const dt = createMockDataTransfer({ files: [pngFile] });

    dispatchSyntheticPaste(view, dt);

    // Initial placeholder should be present immediately
    expect(view.state.doc.textContent).toContain('[Uploading screen.png...]');

    // Wait for upload promise to resolve
    await Promise.resolve();
    await Promise.resolve();

    expect(mockUpload).toHaveBeenCalledTimes(1);
    expect(currentDoc.textContent).toContain('![screen.png](attachment://att_0196ed42)');
    expect(currentDoc.textContent).not.toContain('[Uploading screen.png...]');
  });

  it('Case 2: Branch 1 rejects file exceeding 25 MB client-side with 0 network calls', () => {
    const mockUpload = vi.fn();
    const handleAnnounce = vi.fn();

    const { doc } = parseMarkdown('Initial text.');
    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [
        autoConvertPastePlugin({
          projectId: 'KAN',
          onAnnounce: handleAnnounce,
          uploadAttachment: mockUpload,
        }),
      ],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, { state });

    const hugeFile = new File([''], 'large.png', { type: 'image/png' });
    Object.defineProperty(hugeFile, 'size', { value: MAX_ATTACHMENT_BYTES + 10 });

    const dt = createMockDataTransfer({ files: [hugeFile] });
    dispatchSyntheticPaste(view, dt);

    expect(mockUpload).not.toHaveBeenCalled();
    expect(handleAnnounce).toHaveBeenCalledWith('Attachment exceeds 25 MB limit');
  });

  it('Case 2: Branch 1 rolls back placeholder on 500 upload error cleanly', async () => {
    const mockUpload = vi.fn().mockRejectedValue(new Error('Internal Server Error 500'));
    const handleAnnounce = vi.fn();

    const { doc } = parseMarkdown('Initial text.');
    let currentDoc = doc;

    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [
        autoConvertPastePlugin({
          projectId: 'KAN',
          onAnnounce: handleAnnounce,
          uploadAttachment: mockUpload,
        }),
      ],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, {
      state,
      dispatchTransaction(tr) {
        const nextState = view.state.apply(tr);
        view.updateState(nextState);
        currentDoc = nextState.doc;
      },
    });

    const file = new File(['bad'], 'screen.png', { type: 'image/png' });
    const dt = createMockDataTransfer({ files: [file] });

    dispatchSyntheticPaste(view, dt);

    expect(view.state.doc.textContent).toContain('[Uploading screen.png...]');

    await Promise.resolve();
    await Promise.resolve();

    expect(currentDoc.textContent).not.toContain('[Uploading screen.png...]');
    expect(handleAnnounce).toHaveBeenCalledWith('Attachment upload failed');
  });

  it('Case 6: Two-step Cmd/Ctrl+Z undo contract: first undo restores plain text, second undo restores pre-paste state', () => {
    const initialMarkdown = 'Paragraph before paste.';
    const { doc } = parseMarkdown(initialMarkdown);

    let currentDoc = doc;
    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [
        ...createEditorPlugins('description'),
        autoConvertPastePlugin(),
      ],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, {
      state,
      dispatchTransaction(tr) {
        const nextState = view.state.apply(tr);
        view.updateState(nextState);
        currentDoc = nextState.doc;
      },
    });

    const htmlPayload = '<h2>Heading 2</h2><p>Converted content</p>';
    const plainTextPayload = 'Heading 2\n\nConverted content';

    const dt = createMockDataTransfer({
      html: htmlPayload,
      text: plainTextPayload,
    });

    dispatchSyntheticPaste(view, dt);

    // State 1: Converted Markdown should be in document
    const convertedSerialized = serializeMarkdown(currentDoc, '');
    expect(convertedSerialized).toContain('## Heading 2');

    // First Undo: Reverts Step 2, leaving exact plain text in the document
    undo(view.state, view.dispatch);
    const plainSerialized = serializeMarkdown(currentDoc, '');
    expect(plainSerialized).toContain('Heading 2');
    expect(plainSerialized).not.toContain('## Heading 2');

    // Second Undo: Reverts Step 1, restoring original pre-paste document
    undo(view.state, view.dispatch);
    const originalSerialized = serializeMarkdown(currentDoc, '');
    expect(originalSerialized).toBe(initialMarkdown);
  });

  it('Case 6 integration: MarkdownEditor renders SanitizedPastePill on HTML paste and auto-dismisses', () => {
    vi.useFakeTimers();

    function Harness(): React.JSX.Element {
      const [val, setVal] = React.useState('Initial content');
      return (
        <MarkdownEditor
          surface="description"
          value={val}
          onChange={setVal}
          ariaLabel="Editor"
          testId="int-editor"
        />
      );
    }

    render(<Harness />);

    // Verify pill is initially absent
    expect(screen.queryByTestId('int-editor-sanitized-pill')).toBeNull();

    // Trigger synthetic paste via ProseMirror view
    const wysiwyg = screen.getByTestId('int-editor-wysiwyg');
    const editorDom = wysiwyg.querySelector<HTMLElement>('.ProseMirror');
    expect(editorDom).not.toBeNull();
    if (!editorDom) {
      throw new Error('ProseMirror editor DOM missing');
    }

    const dt = createMockDataTransfer({
      html: '<h3>Subheading</h3><span style="display:none">secret</span>',
      text: 'Subheading',
    });

    const pasteEvt = new SafeClipboardEvent('paste', {
      clipboardData: dt,
      bubbles: true,
      cancelable: true,
    });

    act(() => {
      editorDom.dispatchEvent(pasteEvt);
    });

    // Verify pill appears with 🧼 and exact tooltip
    expect(screen.getByTestId('int-editor-sanitized-pill')).toBeDefined();
    expect(screen.getByText('🧼')).toBeDefined();

    // Fast-forward 4000ms
    act(() => {
      vi.advanceTimersByTime(4001);
    });

    // Verify pill auto-dismissed
    expect(screen.queryByTestId('int-editor-sanitized-pill')).toBeNull();

    vi.useRealTimers();
  });

  it('defaultUploadAttachment handles successful and failed fetch responses', async () => {
    const originalFetch = globalThis.fetch;
    try {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ markdown_uri: 'attachment://att_123', id: 'att_123' }),
      });

      const file = new File(['content'], 'test.png', { type: 'image/png' });
      const res = await defaultUploadAttachment(file, 'KAN');
      expect(res.id).toBe('att_123');
      expect(res.markdownUri).toBe('attachment://att_123');

      // Test failure response
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
      });

      await expect(defaultUploadAttachment(file, 'KAN')).rejects.toThrow('Upload failed with status 403');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('Case 3: Branch 2 (IDE Syntax-Highlighted Code) converts via autoConvertPastePlugin into fenced code block', () => {
    const { doc } = parseMarkdown('Initial');
    let currentDoc = doc;
    const handleConverted = vi.fn();

    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [
        ...createEditorPlugins('description'),
        autoConvertPastePlugin({
          onConverted: handleConverted,
        }),
      ],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, {
      state,
      dispatchTransaction(tr) {
        const nextState = view.state.apply(tr);
        view.updateState(nextState);
        currentDoc = nextState.doc;
      },
    });

    const dt = createMockDataTransfer({
      vscode: JSON.stringify({ mode: 'typescript' }),
      text: 'const y = 2;',
      html: '<div><span style="color:#d4d4d4">const y = 2;</span></div>',
    });

    dispatchSyntheticPaste(view, dt);

    expect(handleConverted).toHaveBeenCalledWith({ kind: 'ide', prunedHiddenNodes: 0 });
    const serialized = serializeMarkdown(currentDoc, '');
    expect(serialized).toContain('```ts\nconst y = 2;\n```');
  });

  it('Case 5: Branch 4 (Raw Markdown Density) parses multi-block text/plain directly into ProseMirror blocks', () => {
    const { doc } = parseMarkdown('Initial');
    let currentDoc = doc;
    const handleConverted = vi.fn();

    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [
        ...createEditorPlugins('description'),
        autoConvertPastePlugin({
          onConverted: handleConverted,
        }),
      ],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, {
      state,
      dispatchTransaction(tr) {
        const nextState = view.state.apply(tr);
        view.updateState(nextState);
        currentDoc = nextState.doc;
      },
    });

    const dt = createMockDataTransfer({
      text: '## High Priority\n\n- Fix issue\n- Deploy fix',
    });

    dispatchSyntheticPaste(view, dt);

    expect(handleConverted).toHaveBeenCalledWith({ kind: 'markdown', prunedHiddenNodes: 0 });
    const serialized = serializeMarkdown(currentDoc, '');
    expect(serialized).toContain('## High Priority');
    expect(serialized).toContain('- Fix issue');
  });

  it('Branch 5: Plain text without Markdown structural density falls through to default paste', () => {
    const { doc } = parseMarkdown('Initial');
    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [autoConvertPastePlugin()],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, { state });

    const dt = createMockDataTransfer({
      text: 'Cost is $5 * 2 #tag',
    });

    let handled = false;
    const event = new SafeClipboardEvent('paste', {
      clipboardData: dt,
      bubbles: true,
      cancelable: true,
    });
    view.someProp('handlePaste', (fn) => {
      handled = Boolean(fn(view, event, view.state.doc.slice(0, 0)));
      return handled;
    });

    expect(handled).toBe(false);
  });

  it('ignores unsupported non-image file uploads in clipboard', () => {
    const { doc } = parseMarkdown('Initial');
    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [autoConvertPastePlugin()],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, { state });

    const pdfFile = new File(['pdf-bytes'], 'report.pdf', { type: 'application/pdf' });
    const dt = createMockDataTransfer({ files: [pdfFile] });

    let handled = false;
    const event = new SafeClipboardEvent('paste', {
      clipboardData: dt,
      bubbles: true,
      cancelable: true,
    });
    view.someProp('handlePaste', (fn) => {
      handled = Boolean(fn(view, event, view.state.doc.slice(0, 0)));
      return handled;
    });

    expect(handled).toBe(false);
  });

  it('retrieves CSRF token from meta tag or cookie', async () => {
    const originalFetch = globalThis.fetch;
    try {
      // 1. Meta tag token
      const meta = document.createElement('meta');
      meta.setAttribute('name', 'csrf-token');
      meta.setAttribute('content', 'meta-secret-token');
      document.head.appendChild(meta);

      globalThis.fetch = vi.fn().mockImplementation((_url, init: RequestInit) => {
        const headers = init.headers as Record<string, string>;
        expect(headers['X-CSRF-Token']).toBe('meta-secret-token');
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ markdown_uri: 'attachment://att_meta', id: 'att_meta' }),
        });
      });

      const file = new File(['content'], 'test.png', { type: 'image/png' });
      await defaultUploadAttachment(file, 'KAN');
      meta.remove();

      // 2. Cookie token
      document.cookie = 'csrf_token=cookie-secret-token';
      globalThis.fetch = vi.fn().mockImplementation((_url, init: RequestInit) => {
        const headers = init.headers as Record<string, string>;
        expect(headers['X-CSRF-Token']).toBe('cookie-secret-token');
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ markdown_uri: 'attachment://att_cookie', id: 'att_cookie' }),
        });
      });

      await defaultUploadAttachment(file, 'KAN');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it('returns false when clipboardData is empty or absent', () => {
    const { doc } = parseMarkdown('Initial');
    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [autoConvertPastePlugin()],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, { state });

    const event = new Event('paste') as ClipboardEvent;
    let handled = false;
    view.someProp('handlePaste', (fn) => {
      handled = Boolean(fn(view, event, view.state.doc.slice(0, 0)));
      return handled;
    });
    expect(handled).toBe(false);
  });

  it('handles empty html and text inputs in convertHtmlToMarkdown', () => {
    expect(convertHtmlToMarkdown('')).toBe('');
    expect(convertHtmlToMarkdown('   ')).toBe('');
  });

  it('removes non-checkbox inputs and disarms data URIs in convertHtmlToMarkdown', () => {
    const html = `
      <form>
        <input type="text" name="user" value="victim">
        <ul>
          <li><input type="checkbox" checked> task</li>
        </ul>
        <a href="data:text/html,<script>alert(1)</script>">Dangerous</a>
      </form>
    `;
    const res = convertHtmlToMarkdown(html);
    expect(res).not.toContain('victim');
    expect(res).not.toContain('data:text/html');
    expect(res).toContain('- [x] task');
    expect(res).toContain('Dangerous');
  });

  it('supports SVG file uploads via Branch 1', async () => {
    const mockUpload = vi.fn().mockResolvedValue({
      markdownUri: 'attachment://att_svg_001',
      id: 'att_svg_001',
    });

    const { doc } = parseMarkdown('Start');
    let currentDoc = doc;

    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [
        autoConvertPastePlugin({
          uploadAttachment: mockUpload,
        }),
      ],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, {
      state,
      dispatchTransaction(tr) {
        const nextState = view.state.apply(tr);
        view.updateState(nextState);
        currentDoc = nextState.doc;
      },
    });

    const svgFile = new File(['<svg></svg>'], 'diagram.svg', { type: 'image/svg+xml' });
    const dt = createMockDataTransfer({ files: [svgFile] });

    dispatchSyntheticPaste(view, dt);
    await Promise.resolve();
    await Promise.resolve();

    expect(mockUpload).toHaveBeenCalledTimes(1);
    expect(currentDoc.textContent).toContain('![diagram.svg](attachment://att_svg_001)');
  });

  it('handles code containing backticks by generating 4-backtick fences', () => {
    const { doc } = parseMarkdown('Initial');
    let currentDoc = doc;

    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [
        ...createEditorPlugins('description'),
        autoConvertPastePlugin(),
      ],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, {
      state,
      dispatchTransaction(tr) {
        const nextState = view.state.apply(tr);
        view.updateState(nextState);
        currentDoc = nextState.doc;
      },
    });

    const dt = createMockDataTransfer({
      vscode: JSON.stringify({ mode: 'markdown' }),
      text: '```bash\necho 1\n```',
    });

    dispatchSyntheticPaste(view, dt);
    const serialized = serializeMarkdown(currentDoc, '');
    expect(serialized).toContain('````md');
  });

  it('falls through when HTML only contains hidden elements and produces empty markdown', () => {
    const { doc } = parseMarkdown('Initial');
    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [autoConvertPastePlugin()],
    });

    const domContainer = document.createElement('div');
    const view = new EditorView(domContainer, { state });

    const dt = createMockDataTransfer({
      html: '<span style="display:none">secret</span>',
      text: '',
    });

    let handled = false;
    const event = new SafeClipboardEvent('paste', {
      clipboardData: dt,
      bubbles: true,
      cancelable: true,
    });
    view.someProp('handlePaste', (fn) => {
      handled = Boolean(fn(view, event, view.state.doc.slice(0, 0)));
      return handled;
    });

    expect(handled).toBe(false);
  });

  describe('defaultUploadAttachment & edge branches', () => {
    const originalFetch = globalThis.fetch;

    beforeEach(() => {
      // Clear cookies and meta tags
      document.cookie = '';
      const existingMeta = document.querySelector('meta[name="csrf-token"]');
      if (existingMeta) {
        existingMeta.remove();
      }
    });

    it('uploads with meta CSRF token and returns markdown_uri', async () => {
      const meta = document.createElement('meta');
      meta.name = 'csrf-token';
      meta.content = 'meta-csrf-123';
      document.head.appendChild(meta);

      let capturedHeaders: Record<string, string> = {};
      globalThis.fetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        capturedHeaders = (init?.headers ?? {}) as Record<string, string>;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ markdown_uri: 'attachment://att_meta', id: 'att_meta' }),
        } as unknown as Response);
      });

      const file = new File(['png'], 'test.png', { type: 'image/png' });
      const res = await defaultUploadAttachment(file, 'KAN');

      expect(capturedHeaders['X-CSRF-Token']).toBe('meta-csrf-123');
      expect(res.markdownUri).toBe('attachment://att_meta');
      expect(res.id).toBe('att_meta');

      meta.remove();
      globalThis.fetch = originalFetch;
    });

    it('uploads with cookie CSRF token and falls back to attachment://id when markdown_uri missing', async () => {
      document.cookie = 'csrf_token=cookie-csrf-456; path=/';

      let capturedHeaders: Record<string, string> = {};
      globalThis.fetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        capturedHeaders = (init?.headers ?? {}) as Record<string, string>;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ id: 'att_only_id' }),
        } as unknown as Response);
      });

      const file = new File(['png'], 'test.png', { type: 'image/png' });
      const res = await defaultUploadAttachment(file, 'KAN');

      expect(capturedHeaders['X-CSRF-Token']).toBe('cookie-csrf-456');
      expect(res.markdownUri).toBe('attachment://att_only_id');
      expect(res.id).toBe('att_only_id');

      globalThis.fetch = originalFetch;
    });

    it('throws Error on non-ok upload response', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
      });

      const file = new File(['png'], 'test.png', { type: 'image/png' });
      await expect(defaultUploadAttachment(file, 'KAN')).rejects.toThrow('Upload failed with status 500');

      globalThis.fetch = originalFetch;
    });

    it('handles empty upload response payload and meta tag without content', async () => {
      const emptyMeta = document.createElement('meta');
      emptyMeta.name = 'csrf-token';
      document.head.appendChild(emptyMeta);

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });

      const file = new File(['png'], 'test.png', { type: 'image/png' });
      const res = await defaultUploadAttachment(file, 'KAN');
      expect(res.markdownUri).toBe('');
      expect(res.id).toBe('');

      emptyMeta.remove();
      globalThis.fetch = originalFetch;
    });

    it('handles image upload with unnamed file and empty markdownUri fallback in plugin', async () => {
      const mockUpload = vi.fn().mockResolvedValue({
        markdownUri: '',
        id: 'fallback_id',
      });

      const { doc } = parseMarkdown('Initial');
      let currentDoc = doc;
      const state = EditorState.create({
        doc,
        schema: editorSchema,
        plugins: [
          autoConvertPastePlugin({
            projectId: 'KAN',
            uploadAttachment: mockUpload,
          }),
        ],
      });

      const domContainer = document.createElement('div');
      const view = new EditorView(domContainer, {
        state,
        dispatchTransaction(tr) {
          const nextState = view.state.apply(tr);
          view.updateState(nextState);
          currentDoc = nextState.doc;
        },
      });

      // File with empty name
      const unnamedFile = new File(['data'], '', { type: 'image/png' });
      const dt = createMockDataTransfer({ files: [unnamedFile] });

      dispatchSyntheticPaste(view, dt);
      expect(view.state.doc.textContent).toContain('[Uploading image.png...]');

      await new Promise((r) => setTimeout(r, 20));

      expect(currentDoc.textContent).toContain('![image.png](attachment://fallback_id)');
    });

    it('handles SVG file by extension and default uploadAttachment path in plugin', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ markdown_uri: 'attachment://svg_1', id: 'svg_1' }),
      });

      const { doc } = parseMarkdown('Initial');
      let currentDoc = doc;
      const state = EditorState.create({
        doc,
        schema: editorSchema,
        plugins: [autoConvertPastePlugin({ projectId: 'PROJ' })],
      });

      const domContainer = document.createElement('div');
      const view = new EditorView(domContainer, {
        state,
        dispatchTransaction(tr) {
          const nextState = view.state.apply(tr);
          view.updateState(nextState);
          currentDoc = nextState.doc;
        },
      });

      const svgFile = new File(['<svg></svg>'], 'diagram.svg', { type: 'application/octet-stream' });
      const dt = createMockDataTransfer({ files: [svgFile] });

      dispatchSyntheticPaste(view, dt);
      expect(view.state.doc.textContent).toContain('[Uploading diagram.svg...]');

      await new Promise((r) => setTimeout(r, 20));

      expect(currentDoc.textContent).toContain('![diagram.svg](attachment://svg_1)');
      globalThis.fetch = originalFetch;
    });

    it('falls through on non-image files, null clipboardData, and plain text without structural markdown', () => {
      const { doc } = parseMarkdown('Initial');
      const state = EditorState.create({
        doc,
        schema: editorSchema,
        plugins: [autoConvertPastePlugin()],
      });

      const domContainer = document.createElement('div');
      const view = new EditorView(domContainer, { state });

      // 1. Non-image file
      const textFile = new File(['text'], 'readme.txt', { type: 'text/plain' });
      const dtFiles = createMockDataTransfer({ files: [textFile] });
      const ev1 = new SafeClipboardEvent('paste', { clipboardData: dtFiles });
      let h1 = false;
      view.someProp('handlePaste', (fn) => {
        h1 = Boolean(fn(view, ev1, view.state.doc.slice(0, 0)));
        return h1;
      });
      expect(h1).toBe(false);

      // 2. Null clipboardData
      const ev2 = new Event('paste');
      let h2 = false;
      view.someProp('handlePaste', (fn) => {
        h2 = Boolean(fn(view, ev2 as unknown as ClipboardEvent, view.state.doc.slice(0, 0)));
        return h2;
      });
      expect(h2).toBe(false);

      // Test handleDOMEvents.paste prop directly for both false and true returns
      const plugin = autoConvertPastePlugin();
      const handleDOMPaste = plugin.props.handleDOMEvents?.paste;
      expect(handleDOMPaste).toBeDefined();
      if (handleDOMPaste) {
        expect(handleDOMPaste.call(plugin, view, ev2 as unknown as ClipboardEvent)).toBe(false);

        const handledEvt = new SafeClipboardEvent('paste', {
          clipboardData: createMockDataTransfer({ text: '## Heading\n\n- item 1\n- item 2' }),
        });
        expect(handleDOMPaste.call(plugin, view, handledEvt)).toBe(true);
      }

      // 3. Plain text without structural markdown
      const dtPlain = createMockDataTransfer({ text: 'just some plain single line text' });
      const ev3 = new SafeClipboardEvent('paste', { clipboardData: dtPlain });
      let h3 = false;
      view.someProp('handlePaste', (fn) => {
        h3 = Boolean(fn(view, ev3, view.state.doc.slice(0, 0)));
        return h3;
      });
      expect(h3).toBe(false);
    });

    it('converts HTML with empty plainText and disarms empty/data/vbscript links & non-checkbox inputs', () => {
      expect(convertHtmlToMarkdown('')).toBe('');
      expect(convertHtmlToMarkdown('   \n  ')).toBe('');

      const complexHtml = `
        <p>
          <a href="">Empty Link</a>
          <a>No Href Link</a>
          <a href="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">Data Link</a>
          <a href="vbscript:msgbox(1)">VBS Link</a>
        </p>
        <p>
          <input />
          <input type="text" value="some text" />
          <input type="password" value="secret" />
          <input type="button" value="click" />
        </p>
      `;

      const result = convertHtmlToMarkdown(complexHtml);
      expect(result).toContain('Empty Link');
      expect(result).toContain('Data Link');
      expect(result).toContain('VBS Link');
      expect(result).not.toContain('vbscript:');
      expect(result).not.toContain('data:text');

      // Test rich HTML paste where plainText is empty
      const { doc } = parseMarkdown('Initial');
      let currentDoc = doc;
      const state = EditorState.create({
        doc,
        schema: editorSchema,
        plugins: [autoConvertPastePlugin()],
      });

      const domContainer = document.createElement('div');
      const view = new EditorView(domContainer, {
        state,
        dispatchTransaction(tr) {
          const nextState = view.state.apply(tr);
          view.updateState(nextState);
          currentDoc = nextState.doc;
        },
      });

      const dt = createMockDataTransfer({
        html: '<p>Paragraph from html</p>',
        text: '',
      });

      dispatchSyntheticPaste(view, dt);
      expect(currentDoc.textContent).toContain('Paragraph from html');
    });
  });
});
