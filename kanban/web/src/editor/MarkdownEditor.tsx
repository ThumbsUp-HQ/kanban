/**
 * Breathable Enterprise ProseMirror Markdown Editor (KB-P3-45, S5.1, S5.2, S6.1, S6.2).
 * Implements zero mode-picker clutter, lossless sourceSlice preservation, and raw Markdown toggle (📝).
 */

import React, {
  useEffect,
  useRef,
  useState,
  useCallback,
  type JSX,
} from 'react';
import { EditorState } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { toggleMark } from 'prosemirror-commands';
import { undo } from 'prosemirror-history';
import { editorSchema } from './schema';
import { parseMarkdown, getUtf8ByteLength } from './parseMarkdown';
import { serializeMarkdown } from './serializeMarkdown';
import {
  createEditorPlugins,
  createEditorNodeViews,
  type EditorSurfaceKind,
} from './editorSurfaceFactory';
import { createMediaNodeViews } from './media/MediaNodeViews';
import { registerMermaidExtension } from './mermaid/MermaidBlockView';
import { SparkleOverlayPortal } from './sparkle/SparkleOverlayPortal';
import {
  autoConvertPastePlugin,
  defaultUploadAttachment,
  MAX_ATTACHMENT_BYTES,
  ALLOWED_IMAGE_MIME_TYPES,
  convertHtmlToMarkdown,
} from './clipboard/autoConvertPaste';
import { pruneHiddenDom } from './clipboard/hiddenDomPruner';
import { SanitizedPastePill } from './clipboard/SanitizedPastePill';
import { EmojiHint } from '../components/emoji/EmojiHint';
import './MarkdownEditor.css';

// Ensure Mermaid extension is registered in surface factory
registerMermaidExtension();

export interface MarkdownEditorProps {
  surface: EditorSurfaceKind;
  value: string;
  onChange: (nextMarkdown: string) => void;
  onBlur?: ((currentMarkdown: string) => void) | undefined;
  readOnly?: boolean | undefined;
  maxBytes?: number | undefined;
  placeholder?: string | undefined;
  ariaLabel: string;
  testId?: string | undefined;
  projectId?: string | undefined;
  objectId?: string | null | undefined;
  enableSparkle?: boolean | undefined;
  onAnnounce?: ((message: string) => void) | undefined;
}

const DEFAULT_MAX_BYTES: Record<EditorSurfaceKind, number> = {
  sticky: 65_536,
  summary: 65_536,
  comment: 262_144,
  description: 1_048_576,
  doc: 1_048_576,
};

export function MarkdownEditor({
  surface,
  value,
  onChange,
  onBlur,
  readOnly = false,
  maxBytes,
  ariaLabel,
  testId = 'markdown-editor',
  projectId = 'KAN',
  objectId,
  enableSparkle,
  onAnnounce,
}: MarkdownEditorProps): JSX.Element {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const [viewInstance, setViewInstance] = useState<EditorView | null>(null);
  const originalSourceRef = useRef<string>(value);
  const lastSerializedRef = useRef<string>(value);
  const valueRef = useRef<string>(value);
  const prevExternalValueRef = useRef<string>(value);
  const onChangeRef = useRef(onChange);
  const onBlurRef = useRef(onBlur);
  const onAnnounceRef = useRef(onAnnounce);

  const [isRawMode, setIsRawMode] = useState(false);
  const [rawText, setRawText] = useState(value);
  const rawTextRef = useRef<string>(rawText);
  const rawTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const rawUndoTextRef = useRef<string | null>(null);
  const [sanitizedPill, setSanitizedPill] = useState<{ prunedHiddenNodes: number } | null>(null);
  const [liveAnnouncement, setLiveAnnouncement] = useState<string | null>(null);

  useEffect(() => {
    valueRef.current = value;
    onChangeRef.current = onChange;
    onBlurRef.current = onBlur;
    onAnnounceRef.current = onAnnounce;
    rawTextRef.current = rawText;
  });

  const effectiveMaxBytes = maxBytes ?? DEFAULT_MAX_BYTES[surface];
  const currentBytes = getUtf8ByteLength(isRawMode ? rawText : value);
  const isByteLimitExceeded = currentBytes > effectiveMaxBytes;

  const isEditorial = surface === 'description' || surface === 'doc';

  // Toggle between WYSIWYG and Raw Markdown
  const handleToggleRaw = useCallback(() => {
    setIsRawMode((prev) => {
      if (prev) {
        // Raw -> WYSIWYG: notify parent with current raw text and transition to WYSIWYG
        const currentRaw = rawTextRef.current;
        lastSerializedRef.current = currentRaw;
        valueRef.current = currentRaw;
        onChangeRef.current(currentRaw);
        return false;
      } else {
        // WYSIWYG -> Raw: serialize current ProseMirror doc
        const currentView = viewRef.current;
        /* v8 ignore next */
        const currentMarkdown = currentView
          ? serializeMarkdown(currentView.state.doc, originalSourceRef.current)
          : valueRef.current;
        setRawText(currentMarkdown);
        rawTextRef.current = currentMarkdown;
        lastSerializedRef.current = currentMarkdown;
        valueRef.current = currentMarkdown;
        onChangeRef.current(currentMarkdown);
        return true;
      }
    });
  }, []);

  const getPlugins = useCallback(() => {
    return [
      ...createEditorPlugins(surface, {
        onToggleRaw: handleToggleRaw,
        projectId,
        objectId,
        enableSparkle,
      }),
      autoConvertPastePlugin({
        projectId,
        onAnnounce: (msg) => {
          setLiveAnnouncement(msg);
          onAnnounceRef.current?.(msg);
        },
        onConverted: (info) => {
          setSanitizedPill({ prunedHiddenNodes: info.prunedHiddenNodes });
        },
      }),
    ];
  }, [surface, projectId, objectId, enableSparkle, handleToggleRaw]);

  // Initialize and mount ProseMirror EditorView
  useEffect(() => {
    if (!mountRef.current || isRawMode) {
      return;
    }

    const initialSource = lastSerializedRef.current;
    const { doc, originalSource } = parseMarkdown(initialSource);
    originalSourceRef.current = originalSource;
    lastSerializedRef.current = initialSource;

    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: getPlugins(),
    });

    const view = new EditorView(mountRef.current, {
      state,
      editable: () => !readOnly,
      nodeViews: {
        ...createEditorNodeViews(surface),
        ...createMediaNodeViews(),
      },
      attributes: {
        'aria-label': ariaLabel,
        role: 'textbox',
        'aria-multiline': 'true',
      },
      dispatchTransaction(tr) {
        const nextState = view.state.apply(tr);
        view.updateState(nextState);

        if (tr.docChanged) {
          const serialized = serializeMarkdown(
            nextState.doc,
            originalSourceRef.current,
          );
          lastSerializedRef.current = serialized;
          onChangeRef.current(serialized);
        }
      },
      handleDOMEvents: {
        blur: () => {
          onBlurRef.current?.(lastSerializedRef.current);
          return false;
        },
      },
    });

    viewRef.current = view;
    setViewInstance(view);

    return () => {
      view.destroy();
      viewRef.current = null;
      setViewInstance(null);
    };
  }, [surface, isRawMode, ariaLabel, readOnly, getPlugins]);

  // Synchronize external value changes with ProseMirror state when in WYSIWYG mode
  useEffect(() => {
    if (isRawMode) {
      prevExternalValueRef.current = value;
      return;
    }

    if (value !== prevExternalValueRef.current && value !== lastSerializedRef.current && viewRef.current) {
      prevExternalValueRef.current = value;
      const { doc, originalSource } = parseMarkdown(value);
      originalSourceRef.current = originalSource;
      lastSerializedRef.current = value;

      const newState = EditorState.create({
        doc,
        schema: editorSchema,
        plugins: getPlugins(),
      });

      const tr = newState.tr.setMeta('skipSourceSliceDirty', true);
      viewRef.current.updateState(newState.apply(tr));
    } else {
      prevExternalValueRef.current = value;
    }
  }, [value, isRawMode, getPlugins]);

  // Toolbar Insertion and Formatting Handlers
  const insertTextInRaw = (before: string, after = '', placeholder = ''): void => {
    const textarea = rawTextareaRef.current;
    const current = rawTextRef.current;
    /* v8 ignore next 8 */
    if (!textarea) {
      const next = `${current}${before}${placeholder}${after}`;
      setRawText(next);
      rawTextRef.current = next;
      lastSerializedRef.current = next;
      onChangeRef.current(next);
      return;
    }
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = current.slice(start, end) || placeholder;
    const replacement = `${before}${selected}${after}`;
    const next = current.slice(0, start) + replacement + current.slice(end);
    setRawText(next);
    rawTextRef.current = next;
    lastSerializedRef.current = next;
    onChangeRef.current(next);
    setTimeout(() => {
      textarea.focus();
      const newCursor = start + before.length + selected.length;
      textarea.setSelectionRange(newCursor, newCursor);
    }, 0);
  };

  const handleToolbarBold = (): void => {
    if (isRawMode) {
      insertTextInRaw('**', '**', 'bold text');
      return;
    }
    /* v8 ignore next */
    if (!viewRef.current) return;
    toggleMark(editorSchema.marks.strong)(viewRef.current.state, viewRef.current.dispatch);
    viewRef.current.focus();
  };

  const handleToolbarItalic = (): void => {
    if (isRawMode) {
      insertTextInRaw('*', '*', 'italic text');
      return;
    }
    /* v8 ignore next */
    if (!viewRef.current) return;
    toggleMark(editorSchema.marks.em)(viewRef.current.state, viewRef.current.dispatch);
    viewRef.current.focus();
  };

  const handleToolbarCode = (): void => {
    if (isRawMode) {
      insertTextInRaw('`', '`', 'code');
      return;
    }
    /* v8 ignore next */
    if (!viewRef.current) return;
    toggleMark(editorSchema.marks.code)(viewRef.current.state, viewRef.current.dispatch);
    viewRef.current.focus();
  };

  const handleToolbarLink = (): void => {
    if (isRawMode) {
      insertTextInRaw('[', '](https://example.com)', 'link text');
      return;
    }
    /* v8 ignore next */
    if (!viewRef.current) return;
    const { state, dispatch } = viewRef.current;
    const { from, to, empty } = state.selection;
    if (empty) {
      const linkMark = editorSchema.marks.link.create({ href: 'https://example.com' });
      const textNode = editorSchema.text('link text', [linkMark]);
      dispatch(state.tr.replaceSelectionWith(textNode));
    } else {
      toggleMark(editorSchema.marks.link, { href: 'https://example.com' })(state, dispatch);
    }
    viewRef.current.focus();
  };

  const handleToolbarTasklist = (): void => {
    if (isRawMode) {
      insertTextInRaw('- [ ] ', '', 'task item\n');
      return;
    }
    /* v8 ignore next */
    if (!viewRef.current) return;
    const { state, dispatch } = viewRef.current;
    const p = editorSchema.nodes.paragraph.create({}, editorSchema.text('task item'));
    const item = editorSchema.nodes.task_item.create({ checked: false }, p);
    const list = editorSchema.nodes.task_list.create({}, item);
    dispatch(state.tr.replaceSelectionWith(list));
    viewRef.current.focus();
  };

  const handleToolbarMermaid = (): void => {
    if (isRawMode) {
      insertTextInRaw('```mermaid\ngraph TD;\n  A-->B;\n```\n', '', '');
      return;
    }
    /* v8 ignore next */
    if (!viewRef.current) return;
    const { state, dispatch } = viewRef.current;
    const mermaidText = 'graph TD;\n  A-->B;';
    const codeBlock = editorSchema.nodes.code_block.create(
      { lang: 'mermaid' },
      editorSchema.text(mermaidText),
    );
    dispatch(state.tr.replaceSelectionWith(codeBlock));
    viewRef.current.focus();
  };

  const handleTriggerMediaUpload = (): void => {
    fileInputRef.current?.click();
  };

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_ATTACHMENT_BYTES) {
      const msg = 'Attachment exceeds 25 MB limit';
      setLiveAnnouncement(msg);
      onAnnounceRef.current?.(msg);
      return;
    }
    try {
      const result = await defaultUploadAttachment(file, projectId);
      const targetUri = result.markdownUri !== '' ? result.markdownUri : `attachment://${result.id}`;
      if (isRawMode) {
        insertTextInRaw(`![${file.name}](${targetUri})`, '', '');
      } else {
        /* v8 ignore next */
        if (!viewRef.current) return;
        const imgNode = editorSchema.nodes.image.create({
          src: targetUri,
          alt: file.name,
        });
        viewRef.current.dispatch(viewRef.current.state.tr.replaceSelectionWith(imgNode));
        viewRef.current.focus();
      }
    } catch {
      const msg = 'Attachment upload failed';
      setLiveAnnouncement(msg);
      onAnnounceRef.current?.(msg);
    } finally {
      /* v8 ignore next */
      if (e.target) {
        e.target.value = '';
      }
    }
  };

  const handleRevertPaste = useCallback(() => {
    if (isRawMode) {
      /* v8 ignore next */
      if (rawUndoTextRef.current !== null) {
        setRawText(rawUndoTextRef.current);
        rawTextRef.current = rawUndoTextRef.current;
        lastSerializedRef.current = rawUndoTextRef.current;
        onChangeRef.current(rawUndoTextRef.current);
      }
      return;
    }
    /* v8 ignore next */
    if (!viewRef.current) return;
    undo(viewRef.current.state, viewRef.current.dispatch);
  }, [isRawMode]);

  // Handle Raw Textarea changes
  const handleRawChange = (e: React.ChangeEvent<HTMLTextAreaElement>): void => {
    const nextText = e.target.value;
    setRawText(nextText);
    rawTextRef.current = nextText;
    lastSerializedRef.current = nextText;
    onChangeRef.current(nextText);
  };

  const handleRawKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    const isMod = e.metaKey || e.ctrlKey;
    if (isMod && e.shiftKey && (e.key === 'm' || e.key === 'M')) {
      e.preventDefault();
      handleToggleRaw();
    }
  };

  const handleRawBlur = (): void => {
    onBlurRef.current?.(rawTextRef.current);
  };

  const handleRawPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>): void => {
    const clipboardData = e.clipboardData;
    /* v8 ignore next */
    if (!clipboardData) return;

    // Check image/svg files first
    const files = Array.from(clipboardData.files);
    if (files.length > 0) {
      const imageFile = files.find(
        (f) => ALLOWED_IMAGE_MIME_TYPES.has(f.type) || f.name.toLowerCase().endsWith('.svg'),
      );
      if (imageFile) {
        e.preventDefault();
        if (imageFile.size > MAX_ATTACHMENT_BYTES) {
          const msg = 'Attachment exceeds 25 MB limit';
          setLiveAnnouncement(msg);
          onAnnounceRef.current?.(msg);
          return;
        }
        void defaultUploadAttachment(imageFile, projectId)
          .then((result) => {
            const targetUri = result.markdownUri !== '' ? result.markdownUri : `attachment://${result.id}`;
            insertTextInRaw(`![${imageFile.name}](${targetUri})`, '', '');
          })
          .catch(() => {
            const msg = 'Attachment upload failed';
            setLiveAnnouncement(msg);
            onAnnounceRef.current?.(msg);
          });
        return;
      }
    }

    // Check HTML paste
    const html = clipboardData.getData('text/html');
    if (html && html.trim() !== '') {
      e.preventDefault();
      rawUndoTextRef.current = rawTextRef.current;
      const { prunedHtml, prunedHiddenNodes } = pruneHiddenDom(html);
      const convertedMarkdown = convertHtmlToMarkdown(prunedHtml);
      insertTextInRaw(convertedMarkdown, '', '');
      setSanitizedPill({ prunedHiddenNodes });
      setLiveAnnouncement('Converted HTML to Markdown');
      onAnnounceRef.current?.('Converted HTML to Markdown');
    }
  };

  return (
    <div
      className={`kb-editor ${isEditorial ? 'kb-editor--editorial' : 'kb-editor--compact'}`}
      data-testid={testId}
    >
      {/* Rich Markdown Formatting Toolbar */}
      <div
        className="kb-editor__toolbar"
        role="toolbar"
        aria-label="Markdown formatting"
        data-testid={`${testId}-toolbar`}
      >
        <button
          type="button"
          className="kb-editor__tool-btn"
          aria-label="Bold text"
          title="Bold (Cmd+B)"
          onClick={handleToolbarBold}
          data-testid={`${testId}-tool-bold`}
        >
          <strong>B</strong>
        </button>
        <button
          type="button"
          className="kb-editor__tool-btn"
          aria-label="Italic text"
          title="Italic (Cmd+I)"
          onClick={handleToolbarItalic}
          data-testid={`${testId}-tool-italic`}
        >
          <em>I</em>
        </button>
        <button
          type="button"
          className="kb-editor__tool-btn"
          aria-label="Insert code"
          title="Code (Cmd+`)"
          onClick={handleToolbarCode}
          data-testid={`${testId}-tool-code`}
        >
          <code>&lt;/&gt;</code>
        </button>
        <button
          type="button"
          className="kb-editor__tool-btn"
          aria-label="Insert link"
          title="Link"
          onClick={handleToolbarLink}
          data-testid={`${testId}-tool-link`}
        >
          🔗
        </button>
        <button
          type="button"
          className="kb-editor__tool-btn"
          aria-label="Insert tasklist"
          title="Tasklist (- [ ] )"
          onClick={handleToolbarTasklist}
          data-testid={`${testId}-tool-tasklist`}
        >
          ☑
        </button>
        <button
          type="button"
          className="kb-editor__tool-btn"
          aria-label="Insert Mermaid diagram"
          title="Mermaid diagram"
          onClick={handleToolbarMermaid}
          data-testid={`${testId}-tool-mermaid`}
        >
          📊
        </button>
        <button
          type="button"
          className="kb-editor__tool-btn"
          aria-label="Attach media or SVG"
          title="Attach media or SVG (<=25MB)"
          onClick={handleTriggerMediaUpload}
          data-testid={`${testId}-tool-media`}
        >
          📎
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,.svg"
          tabIndex={-1}
          aria-hidden="true"
          className="kb-editor__file-input"
          onChange={(e) => { void handleFileSelected(e); }}
          data-testid={`${testId}-file-input`}
        />
        <button
          type="button"
          className={`kb-editor__tool-btn kb-editor__tool-btn--raw${isRawMode ? ' is-active' : ''}`}
          aria-label="Raw markdown source view"
          title="Raw markdown source view (Cmd/Ctrl+Shift+M)"
          onClick={handleToggleRaw}
          data-testid={`${testId}-tool-raw`}
        >
          📝
        </button>
      </div>

      {/* 📝 Raw Markdown Source View Pill */}
      <div
        className={`kb-editor__hint-corner${isRawMode ? ' is-active' : ''}`}
        data-testid={`${testId}-hint-corner`}
      >
        <EmojiHint
          kind="rawMarkdown"
          variant="interactive"
          label="Raw markdown source view"
          content={
            isRawMode
              ? 'Raw canonical Markdown source inspection is active (Cmd/Ctrl+Shift+M to toggle)'
              : 'Indicates raw canonical Markdown source inspection is active (Cmd/Ctrl+Shift+M to toggle).'
          }
          activateLabel={isRawMode ? 'Switch to WYSIWYG' : 'Switch to Raw Markdown'}
          onActivate={handleToggleRaw}
          testId={`${testId}-raw-toggle`}
        />
      </div>

      {/* Editor Content Area */}
      {isRawMode ? (
        <textarea
          ref={rawTextareaRef}
          className="kb-editor__raw mono"
          aria-label={ariaLabel}
          value={rawText}
          onChange={handleRawChange}
          onKeyDown={handleRawKeyDown}
          onPaste={handleRawPaste}
          onBlur={handleRawBlur}
          readOnly={readOnly}
          data-testid={`${testId}-raw`}
        />
      ) : (
        <>
          <div ref={mountRef} className="kb-editor__surface" data-testid={`${testId}-wysiwyg`} />
          <SparkleOverlayPortal view={viewInstance} testId={`${testId}-sparkle`} />
        </>
      )}

      {/* Byte Limit Live Warning */}
      {isByteLimitExceeded && (
        <div
          className="kb-editor__byte-warning"
          role="status"
          aria-live="polite"
          data-testid={`${testId}-byte-warning`}
        >
          Maximum size of {effectiveMaxBytes.toLocaleString()} bytes exceeded (
          {currentBytes.toLocaleString()} bytes)
        </div>
      )}

      {/* Floating Sanitized Paste Status Pill (🧼) */}
      {sanitizedPill && (
        <SanitizedPastePill
          prunedHiddenNodes={sanitizedPill.prunedHiddenNodes}
          onDismiss={() => {
            setSanitizedPill(null);
          }}
          onRevert={handleRevertPaste}
          testId={`${testId}-sanitized-pill`}
        />
      )}

      {/* Screen Reader Live Announcement */}
      {liveAnnouncement && (
        <div
          className="kb-editor__announcement sr-only"
          role="status"
          aria-live="polite"
          data-testid={`${testId}-announcement`}
        >
          {liveAnnouncement}
        </div>
      )}
    </div>
  );
}
