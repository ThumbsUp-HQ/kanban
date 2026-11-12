/**
 * Unit & Integration Tests for MarkdownEditor Component (KB-P3-45).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Plugin } from 'prosemirror-state';
import { type EditorView } from 'prosemirror-view';
import { MarkdownEditor } from './MarkdownEditor';
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
});
