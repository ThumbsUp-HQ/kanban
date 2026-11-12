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
import { editorSchema } from './schema';
import { parseMarkdown, getUtf8ByteLength } from './parseMarkdown';
import { serializeMarkdown } from './serializeMarkdown';
import {
  createEditorPlugins,
  createEditorNodeViews,
  type EditorSurfaceKind,
} from './editorSurfaceFactory';
import { autoConvertPastePlugin } from './clipboard/autoConvertPaste';
import { SanitizedPastePill } from './clipboard/SanitizedPastePill';
import { EmojiHint } from '../components/emoji/EmojiHint';
import './MarkdownEditor.css';

export interface MarkdownEditorProps {
  surface: EditorSurfaceKind;
  value: string;
  onChange: (nextMarkdown: string) => void;
  onBlur?: (currentMarkdown: string) => void;
  readOnly?: boolean;
  maxBytes?: number;
  placeholder?: string;
  ariaLabel: string;
  testId?: string;
  projectId?: string;
  onAnnounce?: (message: string) => void;
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
  onAnnounce,
}: MarkdownEditorProps): JSX.Element {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const originalSourceRef = useRef<string>(value);
  const lastSerializedRef = useRef<string>(value);
  const valueRef = useRef<string>(value);
  const onChangeRef = useRef(onChange);
  const onBlurRef = useRef(onBlur);
  const onAnnounceRef = useRef(onAnnounce);

  const [isRawMode, setIsRawMode] = useState(false);
  const [rawText, setRawText] = useState(value);
  const rawTextRef = useRef<string>(rawText);
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
        const nextVal = rawTextRef.current;
        lastSerializedRef.current = nextVal;
        onChangeRef.current(nextVal);
        return false;
      } else {
        // WYSIWYG -> Raw: serialize current ProseMirror doc
        const currentView = viewRef.current;
        const currentMarkdown = currentView
          ? serializeMarkdown(currentView.state.doc, originalSourceRef.current)
          : valueRef.current;
        setRawText(currentMarkdown);
        rawTextRef.current = currentMarkdown;
        lastSerializedRef.current = currentMarkdown;
        return true;
      }
    });
  }, []);

  const getPlugins = useCallback(() => {
    return [
      ...createEditorPlugins(surface, {
        onToggleRaw: handleToggleRaw,
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
  }, [surface, projectId, handleToggleRaw]);

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
      nodeViews: createEditorNodeViews(surface),
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

    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [surface, isRawMode, ariaLabel, readOnly, getPlugins]);

  // Synchronize external value changes with ProseMirror state when in WYSIWYG mode
  useEffect(() => {
    if (isRawMode) {
      return;
    }

    if (value !== lastSerializedRef.current && viewRef.current) {
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
    }
  }, [value, isRawMode, getPlugins]);

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

  return (
    <div
      className={`kb-editor ${isEditorial ? 'kb-editor--editorial' : 'kb-editor--compact'}`}
      data-testid={testId}
    >
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
          className="kb-editor__raw mono"
          aria-label={ariaLabel}
          value={rawText}
          onChange={handleRawChange}
          onKeyDown={handleRawKeyDown}
          onBlur={handleRawBlur}
          readOnly={readOnly}
          data-testid={`${testId}-raw`}
        />
      ) : (
        <div ref={mountRef} className="kb-editor__surface" data-testid={`${testId}-wysiwyg`} />
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
