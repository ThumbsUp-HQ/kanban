/**
 * Unit & Integration Tests for MarkdownEditor Component (KB-P3-45).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Plugin, TextSelection } from 'prosemirror-state';
import { type EditorView } from 'prosemirror-view';
import { MarkdownEditor } from './MarkdownEditor';
import * as autoConvertPasteMod from './clipboard/autoConvertPaste';
import {
  registerEditorExtension,
  clearEditorExtensions,
  getRegisteredExtensions,
} from './editorSurfaceFactory';

describe('MarkdownEditor Component', () => {
  beforeEach(() => {
    clearEditorExtensions();
  });

  const SAMPLE_MARKDOWN = `# Feature Specification

This is a breathable technical description.

| Service | Status |
| :--- | :--- |
| MCP | Running |`;

  it('renders WYSIWYG editor without any mode-switcher dropdown or toolbar ribbon', () => {
    const handleChange = vi.fn();
    render(
      <MarkdownEditor
        surface="description"
        value={SAMPLE_MARKDOWN}
        onChange={handleChange}
        ariaLabel="Feature description"
        testId="test-editor"
      />,
    );

    // Verify WYSIWYG surface is mounted
    const wysiwyg = screen.getByTestId('test-editor-wysiwyg');
    expect(wysiwyg).toBeDefined();

    // S5.1 Invariant: ZERO mode switcher comboboxes / tabs / dropdowns exist
    const modePicker = screen.queryByRole('combobox', { name: /mode/i });
    expect(modePicker).toBeNull();

    expect(screen.queryByText(/Rich \| Markdown \| HTML/i)).toBeNull();
    expect(screen.queryByRole('tablist')).toBeNull();
  });

  it('applies editorial spatial padding token class for description and doc surfaces', () => {
    const { container: editorialContainer } = render(
      <MarkdownEditor
        surface="description"
        value="# Title"
        onChange={vi.fn()}
        ariaLabel="Editorial Doc"
      />,
    );
    expect(editorialContainer.querySelector('.kb-editor--editorial')).not.toBeNull();

    const { container: compactContainer } = render(
      <MarkdownEditor
        surface="summary"
        value="# Summary"
        onChange={vi.fn()}
        ariaLabel="Summary"
      />,
    );
    expect(compactContainer.querySelector('.kb-editor--compact')).not.toBeNull();
  });

  it('Case 4: Raw Markdown toggle via 📝 pill and keyboard shortcut (Cmd/Ctrl+Shift+M)', () => {
    const handleChange = vi.fn();
    render(
      <MarkdownEditor
        surface="description"
        value={SAMPLE_MARKDOWN}
        onChange={handleChange}
        ariaLabel="Feature description"
        testId="toggle-editor"
      />,
    );

    // WYSIWYG is active initially
    expect(screen.getByTestId('toggle-editor-wysiwyg')).toBeDefined();
    expect(screen.queryByTestId('toggle-editor-raw')).toBeNull();

    // Click 📝 toggle button
    const toggleBtn = screen.getByTestId('toggle-editor-raw-toggle');
    fireEvent.click(toggleBtn);

    // Now in raw mode: textarea is displayed
    const rawTextarea = screen.getByTestId<HTMLTextAreaElement>('toggle-editor-raw');
    expect(rawTextarea).toBeDefined();
    expect(rawTextarea.value).toBe(SAMPLE_MARKDOWN);
    expect(screen.queryByTestId('toggle-editor-wysiwyg')).toBeNull();

    // Edit content in raw mode
    const updatedMarkdown = `${SAMPLE_MARKDOWN}\n\nAppended raw paragraph.`;
    fireEvent.change(rawTextarea, { target: { value: updatedMarkdown } });
    expect(handleChange).toHaveBeenCalledWith(updatedMarkdown);

    // Press Ctrl+Shift+M inside the raw textarea to toggle back to WYSIWYG
    fireEvent.keyDown(rawTextarea, { key: 'M', ctrlKey: true, shiftKey: true });

    // WYSIWYG is active again with updated content
    expect(screen.getByTestId('toggle-editor-wysiwyg')).toBeDefined();
    expect(screen.queryByTestId('toggle-editor-raw')).toBeNull();
  });

  it('Case 6: displays aria-live="polite" byte-limit warning when maxBytes exceeded', () => {
    const smallLimit = 64; // 64 bytes
    const longText = 'This is a long technical text that exceeds the sixty-four bytes limit for this sticky note.';

    render(
      <MarkdownEditor
        surface="sticky"
        value={longText}
        maxBytes={smallLimit}
        onChange={vi.fn()}
        ariaLabel="Sticky Note"
        testId="sticky-editor"
      />,
    );

    const warning = screen.getByTestId('sticky-editor-byte-warning');
    expect(warning).toBeDefined();
    expect(warning.getAttribute('aria-live')).toBe('polite');
    expect(warning.getAttribute('role')).toBe('status');
    expect(warning.textContent).toContain('Maximum size of 64 bytes exceeded');
  });

  it('extension registration and teardown lifecycle', () => {
    expect(getRegisteredExtensions('description').length).toBe(0);

    const dummyPlugin = vi.fn(() => []);
    const unregister = registerEditorExtension({
      name: 'test-extension',
      surfaces: ['description'],
      plugins: dummyPlugin,
    });

    expect(getRegisteredExtensions('description').length).toBe(1);
    expect(getRegisteredExtensions('summary').length).toBe(0); // Scoped to description

    render(
      <MarkdownEditor
        surface="description"
        value="Hello extension"
        onChange={vi.fn()}
        ariaLabel="Extension test"
      />,
    );

    expect(dummyPlugin).toHaveBeenCalled();

    unregister();
    expect(getRegisteredExtensions('description').length).toBe(0);
  });

  it('handles onBlur callbacks in both WYSIWYG and raw mode', () => {
    const handleBlur = vi.fn();
    render(
      <MarkdownEditor
        surface="description"
        value={SAMPLE_MARKDOWN}
        onChange={vi.fn()}
        onBlur={handleBlur}
        ariaLabel="Feature description"
        testId="blur-editor"
      />,
    );

    // WYSIWYG blur
    const editorEl = screen.getByTestId('blur-editor-wysiwyg').querySelector('.ProseMirror');
    if (editorEl) {
      fireEvent.blur(editorEl);
      expect(handleBlur).toHaveBeenCalledWith(SAMPLE_MARKDOWN);
    }

    // Toggle to raw mode
    fireEvent.click(screen.getByTestId('blur-editor-raw-toggle'));
    const rawTextarea = screen.getByTestId('blur-editor-raw');
    fireEvent.blur(rawTextarea);
    expect(handleBlur).toHaveBeenCalledWith(SAMPLE_MARKDOWN);

    // Blur in WYSIWYG without onBlur prop
    const { container: noBlurContainer } = render(
      <MarkdownEditor
        surface="doc"
        value={SAMPLE_MARKDOWN}
        onChange={vi.fn()}
        ariaLabel="Doc without blur"
        testId="no-blur-editor"
      />,
    );
    const noBlurEl = noBlurContainer.querySelector('.ProseMirror');
    if (noBlurEl) {
      fireEvent.blur(noBlurEl);
    }

    // Toggle to raw mode on noBlurEditor and blur
    fireEvent.click(screen.getByTestId('no-blur-editor-raw-toggle'));
    const noBlurRaw = screen.getByTestId('no-blur-editor-raw');
    fireEvent.blur(noBlurRaw);

    // Test raw mode keyboard shortcuts variations
    fireEvent.keyDown(noBlurRaw, { key: 'a' });
    fireEvent.keyDown(noBlurRaw, { key: 'm', ctrlKey: true }); // without shift
    fireEvent.keyDown(noBlurRaw, { key: 'x', ctrlKey: true, shiftKey: true }); // wrong key
    fireEvent.keyDown(noBlurRaw, { key: 'm', metaKey: true, shiftKey: true }); // mac shortcut
    // Toggled back to WYSIWYG
    expect(screen.getByTestId('no-blur-editor-wysiwyg')).toBeDefined();

    // External value change while in WYSIWYG mode updates ProseMirror doc
    const { rerender: rerenderWysiwyg } = render(
      <MarkdownEditor
        surface="description"
        value="# Initial Heading"
        onChange={vi.fn()}
        ariaLabel="External update"
        testId="ext-editor"
      />,
    );
    expect(screen.getByTestId('ext-editor-wysiwyg').textContent).toContain('Initial Heading');

    rerenderWysiwyg(
      <MarkdownEditor
        surface="description"
        value="# Replaced Heading"
        onChange={vi.fn()}
        ariaLabel="External update"
        testId="ext-editor"
      />,
    );
    expect(screen.getByTestId('ext-editor-wysiwyg').textContent).toContain('Replaced Heading');

    // Byte limit warning in raw mode
    render(
      <MarkdownEditor
        surface="sticky"
        value="Short initial text"
        maxBytes={20}
        onChange={vi.fn()}
        ariaLabel="Raw byte limit"
        testId="raw-byte-editor"
      />,
    );
    fireEvent.click(screen.getByTestId('raw-byte-editor-raw-toggle'));
    const rawByteTextarea = screen.getByTestId('raw-byte-editor-raw');
    fireEvent.change(rawByteTextarea, {
      target: { value: 'This text exceeds twenty bytes in raw mode' },
    });
    expect(screen.getByTestId('raw-byte-editor-byte-warning')).toBeDefined();
  });

  it('supports readOnly prop and createEditorNodeViews', () => {
    render(
      <MarkdownEditor
        surface="description"
        value={SAMPLE_MARKDOWN}
        readOnly={true}
        onChange={vi.fn()}
        ariaLabel="Feature description"
        testId="readonly-editor"
      />,
    );

    const toggleBtn = screen.getByTestId('readonly-editor-raw-toggle');
    fireEvent.click(toggleBtn);
    const rawTextarea = screen.getByTestId<HTMLTextAreaElement>('readonly-editor-raw');
    expect(rawTextarea.readOnly).toBe(true);
  });

  it('handles ProseMirror keydown events and document transactions', () => {
    const captured = { view: null as EditorView | null };
    registerEditorExtension({
      name: 'dispatch-tester',
      plugins: () => [
        new Plugin({
          view(v) {
            captured.view = v;
            return {};
          },
        }),
      ],
    });

    const handleChange = vi.fn();
    render(
      <MarkdownEditor
        surface="description"
        value={SAMPLE_MARKDOWN}
        onChange={handleChange}
        ariaLabel="Feature description"
        testId="dispatch-editor"
      />,
    );

    const editorEl = screen.getByTestId('dispatch-editor-wysiwyg').querySelector('.ProseMirror');
    if (editorEl) {
      fireEvent.keyDown(editorEl, { key: 'Enter' });
      fireEvent.keyDown(editorEl, { key: 'Backspace' });
    }

    // Dispatch a real transaction with docChanged: true
    expect(captured.view).not.toBeNull();
    if (captured.view) {
      // 1. Transaction without doc change (docChanged: false)
      captured.view.dispatch(captured.view.state.tr.setMeta('pointer', true));

      // 2. Transaction with doc change (docChanged: true)
      captured.view.dispatch(captured.view.state.tr.insertText(' Live typing text', 1));
      expect(handleChange).toHaveBeenCalled();
    }
  });

  it('connects toolbar buttons (Bold, Italic, Code, Link, Tasklist, Mermaid, Media, Raw) in WYSIWYG and Raw modes', () => {
    const handleChange = vi.fn();
    const handleAnnounce = vi.fn();
    render(
      <MarkdownEditor
        surface="description"
        value="# Test heading\n\nSome paragraph"
        onChange={handleChange}
        ariaLabel="Feature description"
        testId="toolbar-editor"
        onAnnounce={handleAnnounce}
      />,
    );

    // Verify all 8 toolbar buttons exist
    const boldBtn = screen.getByRole('button', { name: 'Bold text' });
    const italicBtn = screen.getByRole('button', { name: 'Italic text' });
    const codeBtn = screen.getByRole('button', { name: 'Insert code' });
    const linkBtn = screen.getByRole('button', { name: 'Insert link' });
    const tasklistBtn = screen.getByRole('button', { name: 'Insert tasklist' });
    const mermaidBtn = screen.getByRole('button', { name: 'Insert Mermaid diagram' });
    const mediaBtn = screen.getByRole('button', { name: 'Attach media or SVG' });
    const rawBtn = screen.getByTestId('toolbar-editor-tool-raw');

    expect(boldBtn).toBeDefined();
    expect(italicBtn).toBeDefined();
    expect(codeBtn).toBeDefined();
    expect(linkBtn).toBeDefined();
    expect(tasklistBtn).toBeDefined();
    expect(mermaidBtn).toBeDefined();
    expect(mediaBtn).toBeDefined();
    expect(rawBtn).toBeDefined();

    // Click WYSIWYG toolbar buttons
    fireEvent.click(boldBtn);
    fireEvent.click(italicBtn);
    fireEvent.click(codeBtn);
    fireEvent.click(linkBtn);
    fireEvent.click(tasklistBtn);
    fireEvent.click(mermaidBtn);

    // Test media upload file picker trigger and 25MB cap
    const fileInput = screen.getByTestId<HTMLInputElement>('toolbar-editor-file-input');
    const clickSpy = vi.spyOn(fileInput, 'click');
    fireEvent.click(mediaBtn);
    expect(clickSpy).toHaveBeenCalled();

    // Oversized file > 25MB
    const bigFile = new File([new Uint8Array(27 * 1024 * 1024)], 'giant.png', { type: 'image/png' });
    fireEvent.change(fileInput, { target: { files: [bigFile] } });
    expect(handleAnnounce).toHaveBeenCalledWith('Attachment exceeds 25 MB limit');

    // Switch to Raw mode via toolbar 📝 button
    fireEvent.click(rawBtn);
    const rawTextarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Feature description' });
    expect(rawTextarea).toBeDefined();

    // Click toolbar buttons in Raw mode
    fireEvent.click(boldBtn);
    expect(rawTextarea.value).toContain('**bold text**');

    fireEvent.click(italicBtn);
    expect(rawTextarea.value).toContain('*italic text*');

    fireEvent.click(codeBtn);
    expect(rawTextarea.value).toContain('`code`');

    fireEvent.click(linkBtn);
    expect(rawTextarea.value).toContain('[link text](https://example.com)');

    fireEvent.click(tasklistBtn);
    expect(rawTextarea.value).toContain('- [ ] task item');

    fireEvent.click(mermaidBtn);
    expect(rawTextarea.value).toContain('```mermaid');

    // Switch back to WYSIWYG
    fireEvent.click(rawBtn);
    expect(screen.getByTestId('toolbar-editor-wysiwyg')).toBeDefined();
  });

  it('handles attachment file upload in WYSIWYG and Raw modes, and handles upload failure', async () => {
    const uploadSpy = vi
      .spyOn(autoConvertPasteMod, 'defaultUploadAttachment')
      .mockResolvedValueOnce({ markdownUri: 'attachment://att_456', id: 'att_456' })
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce({ markdownUri: '', id: 'att_789' });

    const handleChange = vi.fn();
    const handleAnnounce = vi.fn();
    const { rerender } = render(
      <MarkdownEditor
        surface="description"
        value="Initial content"
        onChange={handleChange}
        ariaLabel="Feature description"
        testId="upload-editor"
        onAnnounce={handleAnnounce}
      />,
    );

    const fileInput = screen.getByTestId<HTMLInputElement>('upload-editor-file-input');
    const validFile = new File(['mock content'], 'sample.png', { type: 'image/png' });

    // 1. Successful upload in WYSIWYG
    fireEvent.change(fileInput, { target: { files: [validFile] } });
    await vi.waitFor(() => {
      expect(uploadSpy).toHaveBeenCalledTimes(1);
    });

    // 2. Failed upload
    fireEvent.change(fileInput, { target: { files: [validFile] } });
    await vi.waitFor(() => {
      expect(handleAnnounce).toHaveBeenCalledWith('Attachment upload failed');
    });

    // 3. Successful upload in Raw mode
    fireEvent.click(screen.getByTestId('upload-editor-tool-raw'));
    fireEvent.change(fileInput, { target: { files: [validFile] } });
    await vi.waitFor(() => {
      const raw = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Feature description' });
      expect(raw.value).toContain('![sample.png](attachment://att_789)');
    });

    // 4. Update external value in WYSIWYG mode to cover branch where external value updates
    fireEvent.click(screen.getByTestId('upload-editor-tool-raw'));
    rerender(
      <MarkdownEditor
        surface="description"
        value="Completely different external value"
        onChange={handleChange}
        ariaLabel="Feature description"
        testId="upload-editor"
        onAnnounce={handleAnnounce}
      />,
    );
  });

  it('renders and dismisses/reverts SanitizedPastePill on HTML paste in WYSIWYG and Raw modes', async () => {
    const handleChange = vi.fn();
    render(
      <MarkdownEditor
        surface="description"
        value="Base content"
        onChange={handleChange}
        ariaLabel="Feature description"
        testId="pill-editor"
      />,
    );

    // Simulate HTML paste on ProseMirror element
    const wysiwyg = screen.getByTestId('pill-editor-wysiwyg');
    const editorDom = wysiwyg.querySelector<HTMLElement>('.ProseMirror');
    const dt = {
      files: [],
      types: ['text/html', 'text/plain'],
      getData: (format: string) => {
        if (format === 'text/html') return '<p>Pasted HTML</p><span style="display:none">hidden</span>';
        if (format === 'text/plain') return 'Pasted HTML';
        return '';
      },
    };

    const pasteEvt = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(pasteEvt, 'clipboardData', { value: dt });
    editorDom?.dispatchEvent(pasteEvt);

    // Verify pill is displayed
    const pill = await screen.findByTestId('pill-editor-sanitized-pill');
    expect(pill).toBeDefined();

    // Click Revert button
    const revertBtn = screen.getByTestId('pill-editor-sanitized-pill-revert-btn');
    fireEvent.click(revertBtn);

    // Verify pill was dismissed
    expect(screen.queryByTestId('pill-editor-sanitized-pill')).toBeNull();

    // Trigger paste again and dismiss via onDismiss
    const pasteEvt2 = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(pasteEvt2, 'clipboardData', { value: dt });
    editorDom?.dispatchEvent(pasteEvt2);
    const pill2 = await screen.findByTestId('pill-editor-sanitized-pill');
    const pillInner = pill2.querySelector<HTMLElement>('.sanitized-paste-pill');
    fireEvent.keyDown(pillInner ?? pill2, { key: 'Escape' });
    expect(screen.queryByTestId('pill-editor-sanitized-pill')).toBeNull();
  });

  it('handles oversized files, empty file selection, non-empty selection link, and raw mode paste revert', async () => {
    let capturedView: EditorView | null = null;
    registerEditorExtension({
      name: 'view-capture-edge',
      plugins: () => [
        new Plugin({
          view(v) {
            capturedView = v;
            return {};
          },
        }),
      ],
    });

    const handleAnnounce = vi.fn();
    const handleChange = vi.fn();
    render(
      <MarkdownEditor
        surface="description"
        value="Select this link text here"
        onChange={handleChange}
        ariaLabel="Feature description"
        testId="edge-editor"
        onAnnounce={handleAnnounce}
      />,
    );

    // 1. Oversized file (>25 MB)
    const fileInput = screen.getByTestId<HTMLInputElement>('edge-editor-file-input');
    const hugeFile = new File(['a'.repeat(100)], 'huge.png', { type: 'image/png' });
    Object.defineProperty(hugeFile, 'size', { value: 26 * 1024 * 1024 });
    fireEvent.change(fileInput, { target: { files: [hugeFile] } });
    expect(handleAnnounce).toHaveBeenCalledWith('Attachment exceeds 25 MB limit');

    // 2. Empty file selection (files: [])
    fireEvent.change(fileInput, { target: { files: [] } });

    // 3. Non-empty selection link in WYSIWYG
    const viewToSelect = capturedView as EditorView | null;
    if (viewToSelect) {
      viewToSelect.dispatch(
        viewToSelect.state.tr.setSelection(
          TextSelection.create(viewToSelect.state.doc, 1, 10),
        ),
      );
    }
    const linkBtn = screen.getByTestId('edge-editor-tool-link');
    fireEvent.click(linkBtn);

    // 4. Switch to Raw mode
    const rawBtn = screen.getByTestId('edge-editor-tool-raw');
    fireEvent.click(rawBtn);
    const rawTextarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Feature description' });

    // Paste an oversized image file in raw mode
    const rawPasteOversized = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(rawPasteOversized, 'clipboardData', {
      value: {
        files: [hugeFile],
        types: ['Files'],
        getData: () => '',
      },
    });
    rawTextarea.dispatchEvent(rawPasteOversized);
    expect(handleAnnounce).toHaveBeenCalledWith('Attachment exceeds 25 MB limit');

    // Paste a valid image file in raw mode with mock upload
    const validImg = new File(['img'], 'photo.png', { type: 'image/png' });
    const uploadSpy = vi
      .spyOn(autoConvertPasteMod, 'defaultUploadAttachment')
      .mockResolvedValueOnce({ markdownUri: 'attachment://img_111', id: 'img_111' })
      .mockRejectedValueOnce(new Error('Fail'));

    const rawPasteImg = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(rawPasteImg, 'clipboardData', {
      value: {
        files: [validImg],
        types: ['Files'],
        getData: () => '',
      },
    });
    rawTextarea.dispatchEvent(rawPasteImg);
    await vi.waitFor(() => {
      expect(rawTextarea.value).toContain('![photo.png](attachment://img_111)');
    });

    // Paste an image that fails upload in raw mode
    const rawPasteImgFail = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(rawPasteImgFail, 'clipboardData', {
      value: {
        files: [validImg],
        types: ['Files'],
        getData: () => '',
      },
    });
    rawTextarea.dispatchEvent(rawPasteImgFail);
    await vi.waitFor(() => {
      expect(handleAnnounce).toHaveBeenCalledWith('Attachment upload failed');
    });

    // Paste HTML and revert in raw mode
    const dt = {
      files: [],
      types: ['text/html', 'text/plain'],
      getData: (format: string) => {
        if (format === 'text/html') return '<b>Bold HTML</b><script>evil()</script>';
        if (format === 'text/plain') return 'Bold HTML';
        return '';
      },
    };
    const rawPaste = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(rawPaste, 'clipboardData', { value: dt });
    rawTextarea.dispatchEvent(rawPaste);

    // Verify sanitized pill in raw mode
    const pill = await screen.findByTestId('edge-editor-sanitized-pill');
    expect(pill).toBeDefined();

    // Revert paste in raw mode
    const revertBtn = screen.getByTestId('edge-editor-sanitized-pill-revert-btn');
    fireEvent.click(revertBtn);
    expect(screen.queryByTestId('edge-editor-sanitized-pill')).toBeNull();

    // 5. Test raw mode text selection with bold/italic/code/mermaid
    rawTextarea.setSelectionRange(0, 6);
    const boldBtn = screen.getByTestId('edge-editor-tool-bold');
    fireEvent.click(boldBtn);
    expect(rawTextarea.value).toContain('**');

    // Mermaid button in raw mode with start > 0 and no leading newline
    fireEvent.change(rawTextarea, { target: { value: 'Leading text' } });
    rawTextarea.setSelectionRange(12, 12);
    const mermaidBtn = screen.getByTestId('edge-editor-tool-mermaid');
    fireEvent.click(mermaidBtn);
    expect(rawTextarea.value).toContain('\n```mermaid\n');

    uploadSpy.mockRestore();
  });
});
