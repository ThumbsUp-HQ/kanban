/**
 * 5-Branch Clipboard Classifier & Auto-Convert Paste Plugin (KB-P3-46, S5.2).
 * Implements:
 * 1. Image/.svg binary paste upload
 * 2. IDE syntax-highlighted code wrapper bypass
 * 3. Rich HTML paste (Step A hidden-DOM prune -> Step B DOMPurify + hast-util-to-mdast -> remark-gfm)
 * 4. Structural Markdown in text/plain
 * 5. Plain text fallback + 2-step Cmd/Ctrl+Z undo contract
 */

import { Plugin } from 'prosemirror-state';
import { type EditorView } from 'prosemirror-view';
import { closeHistory } from 'prosemirror-history';
import { type Node as ProsemirrorNode } from 'prosemirror-model';
import DOMPurify from 'dompurify';
import { fromDom } from 'hast-util-from-dom';
import { toMdast } from 'hast-util-to-mdast';
import { unified } from 'unified';
import remarkGfm from 'remark-gfm';
import remarkStringify from 'remark-stringify';
import { pruneHiddenDom, stripInvisibleUnicode } from './hiddenDomPruner';
import { detectIdeCodePaste } from './ideWrapperBypass';
import { isStructuralMarkdown } from './markdownDensity';
import { ensureTrustedTypesPolicies } from './trustedTypes';
import { parseMarkdown } from '../parseMarkdown';

export const MAX_ATTACHMENT_BYTES = 26_214_400; // 25 MiB

export const ALLOWED_IMAGE_MIME_TYPES = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/avif',
  'image/gif',
  'image/svg+xml',
]);

export interface ConvertedPasteInfo {
  kind: 'html' | 'ide' | 'markdown';
  prunedHiddenNodes: number;
}

export interface AutoConvertPasteOptions {
  projectId?: string;
  onAnnounce?: (message: string) => void;
  onConverted?: (info: ConvertedPasteInfo) => void;
  uploadAttachment?: (
    file: File,
    projectId: string,
  ) => Promise<{ markdownUri: string; id: string }>;
}

function getDomPurify(): typeof DOMPurify {
  /* v8 ignore start */
  if (typeof DOMPurify.sanitize !== 'function') {
    return (DOMPurify as unknown as (w: Window) => typeof DOMPurify)(window);
  }
  /* v8 ignore stop */
  return DOMPurify;
}

function getCsrfToken(): string | null {
  /* v8 ignore next 3 */
  if (typeof document === 'undefined') {
    return null;
  }
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) {
    const content = meta.getAttribute('content');
    if (content) {
      return content;
    }
  }
  const match = /(?:^|;\s*)(?:csrf_token|XSRF-TOKEN|csrftoken)=([^;]+)/.exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export async function defaultUploadAttachment(
  file: File,
  projectId: string,
): Promise<{ markdownUri: string; id: string }> {
  const formData = new FormData();
  formData.append('file', file);

  const headers: Record<string, string> = {};
  const csrf = getCsrfToken();
  if (csrf) {
    headers['X-CSRF-Token'] = csrf;
  }

  const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/attachments`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!res.ok) {
    throw new Error(`Upload failed with status ${String(res.status)}`);
  }

  const data = (await res.json()) as { markdown_uri?: string; id?: string };
  return {
    markdownUri: data.markdown_uri ?? (data.id ? `attachment://${data.id}` : ''),
    id: data.id ?? '',
  };
}

/**
 * Converts rich HTML to canonical GFM Markdown via AST transformation pipeline.
 */
export function convertHtmlToMarkdown(html: string): string {
  if (!html || html.trim() === '') {
    return '';
  }

  const { sanitizerPolicy } = ensureTrustedTypesPolicies();
  /* v8 ignore next */
  const initialPolicyInput = sanitizerPolicy ? sanitizerPolicy.createHTML(html) : html;

  const parser = new DOMParser();
  const doc = parser.parseFromString(initialPolicyInput, 'text/html');

  // 1. Unwrap or disarm non-allowlisted links (e.g. javascript:)
  const anchors = Array.from(doc.body.querySelectorAll('a'));
  for (const a of anchors) {
    const href = a.getAttribute('href') ?? '';
    const lower = href.trim().toLowerCase();
    if (!href || lower.startsWith('javascript:') || lower.startsWith('data:') || lower.startsWith('vbscript:')) {
      const text = a.textContent;
      a.replaceWith(doc.createTextNode(text));
    }
  }

  // 2. Remove non-checkbox inputs so task checkboxes are preserved
  const inputs = Array.from(doc.body.querySelectorAll('input'));
  for (const input of inputs) {
    const type = (input.getAttribute('type') ?? '').toLowerCase();
    if (type !== 'checkbox') {
      input.remove();
    }
  }

  /* v8 ignore next */
  const policyInput = sanitizerPolicy ? sanitizerPolicy.createHTML(doc.body.innerHTML) : doc.body.innerHTML;

  const purify = getDomPurify();
  const clean = purify.sanitize(policyInput, {
    RETURN_DOM_FRAGMENT: true,
    FORBID_TAGS: ['style', 'script', 'iframe', 'form'],
    FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick', 'onmouseover'],
  });

  const hast = fromDom(clean);
  const mdast = toMdast(hast);
  /* v8 ignore next 3 */
  const rootNode =
    typeof mdast === 'object' && 'type' in mdast && mdast.type === 'root'
      ? mdast
      : { type: 'root', children: [mdast] };

  const processor = unified()
    .use(remarkGfm)
    .use(remarkStringify, { bullet: '-', fence: '`' });

  const markdown = processor.stringify(rootNode as never);

  return markdown.trim();
}

/**
 * Executes the two-step undo transaction contract:
 * Tr1 inserts plain text (followed by closeHistory).
 * Tr2 replaces that range with the converted Markdown slice (followed by closeHistory).
 * Cmd+Z once reverts to plain text; Cmd+Z twice restores pre-paste state.
 */
export function applyTwoStepPaste(
  view: EditorView,
  plainText: string,
  convertedMarkdown: string,
): void {
  const { from, to } = view.state.selection;

  // Step 1: Insert plain text
  const tr1 = view.state.tr.insertText(plainText, from, to);
  closeHistory(tr1);
  view.dispatch(tr1);

  // Step 2: Replace plain text with converted Markdown blocks
  const insertedEnd = from + plainText.length;
  const { doc } = parseMarkdown(convertedMarkdown);
  const slice = doc.slice(0, doc.content.size);

  const tr2 = view.state.tr.replaceRange(from, insertedEnd, slice);
  closeHistory(tr2);
  view.dispatch(tr2);
}

function findTextPosition(doc: ProsemirrorNode, text: string): number | null {
  let result: number | null = null;
  doc.descendants((node, pos) => {
    if (node.isText && node.text?.includes(text)) {
      result = pos + node.text.indexOf(text);
      return false;
    }
    return true;
  });
  return result;
}

export function handleClipboardPaste(
  view: EditorView,
  event: ClipboardEvent,
  options?: AutoConvertPasteOptions,
): boolean {
  const projectId = options?.projectId ?? 'KAN';
  const clipboardData = event.clipboardData;
  if (!clipboardData) {
    return false;
  }

  // Branch 1: Binary Image / .svg paste
  const files = Array.from(clipboardData.files);
  if (files.length > 0) {
    const imageFile = files.find(
      (f) => ALLOWED_IMAGE_MIME_TYPES.has(f.type) || f.name.toLowerCase().endsWith('.svg'),
    );

    if (imageFile) {
      // Guard: Reject files exceeding 25 MB client-side without network upload
      if (imageFile.size > MAX_ATTACHMENT_BYTES) {
        options?.onAnnounce?.('Attachment exceeds 25 MB limit');
        return true;
      }

      const rawName = imageFile.name !== '' ? imageFile.name : 'image.png';
      const sanitizedName = rawName.replace(/[^\w.-]/g, '_');
      const placeholder = `[Uploading ${sanitizedName}...]`;

      // Insert optimistic placeholder
      const { from, to } = view.state.selection;
      const tr = view.state.tr.insertText(placeholder, from, to);
      view.dispatch(tr);

      // Execute upload asynchronously
      const doUpload = options?.uploadAttachment ?? defaultUploadAttachment;
      void doUpload(imageFile, projectId)
        .then((result) => {
          const foundPos = findTextPosition(view.state.doc, placeholder);
          /* v8 ignore start */
          if (foundPos === null) {
            return;
          }
          /* v8 ignore stop */
          const targetUri = result.markdownUri !== '' ? result.markdownUri : `attachment://${result.id}`;
          const imageMarkdown = `![${sanitizedName}](${targetUri})`;
          const replaceTr = view.state.tr.insertText(
            imageMarkdown,
            foundPos,
            foundPos + placeholder.length,
          );
          view.dispatch(replaceTr);
        })
        .catch(() => {
          // Roll back placeholder on error
          const foundPos = findTextPosition(view.state.doc, placeholder);
          /* v8 ignore start */
          if (foundPos === null) {
            return;
          }
          /* v8 ignore stop */
          const rollbackTr = view.state.tr.delete(foundPos, foundPos + placeholder.length);
          view.dispatch(rollbackTr);
          options?.onAnnounce?.('Attachment upload failed');
        });

      return true;
    }
  }

  // Branch 2: IDE syntax-highlighted code wrapper bypass
  const ideResult = detectIdeCodePaste(clipboardData);
  if (ideResult.isIdeCode) {
    const lang = ideResult.language;
    const code = ideResult.codeText;
    const fence = code.includes('```') ? '````' : '```';
    const convertedMarkdown = `${fence}${lang}\n${code}\n${fence}`;

    applyTwoStepPaste(view, code, convertedMarkdown);
    options?.onConverted?.({ kind: 'ide', prunedHiddenNodes: 0 });
    return true;
  }

  // Branch 3: Rich HTML paste
  const rawHtml = clipboardData.getData('text/html');
  if (rawHtml.trim().length > 0) {
    const { prunedHtml, prunedHiddenNodes } = pruneHiddenDom(rawHtml);
    const convertedMarkdown = convertHtmlToMarkdown(prunedHtml);
    const plainText = stripInvisibleUnicode(clipboardData.getData('text/plain'));

    if (convertedMarkdown.length > 0) {
      applyTwoStepPaste(
        view,
        plainText !== '' ? plainText : convertedMarkdown,
        convertedMarkdown,
      );
      options?.onConverted?.({ kind: 'html', prunedHiddenNodes });
      return true;
    }
  }

  // Branch 4: Raw Markdown in text/plain
  const plainText = stripInvisibleUnicode(clipboardData.getData('text/plain'));
  if (plainText.length > 0 && isStructuralMarkdown(plainText)) {
    applyTwoStepPaste(view, plainText, plainText);
    options?.onConverted?.({ kind: 'markdown', prunedHiddenNodes: 0 });
    return true;
  }

  // Branch 5: Fall through to default plain-text insertion
  return false;
}

/**
 * ProseMirror Plugin for 5-branch auto-convert clipboard paste handling.
 */
export function autoConvertPastePlugin(options?: AutoConvertPasteOptions): Plugin {
  return new Plugin({
    props: {
      handleDOMEvents: {
        paste(view: EditorView, event: Event): boolean {
          const clipboardEvent = event as ClipboardEvent;
          if (handleClipboardPaste(view, clipboardEvent, options)) {
            event.preventDefault();
            return true;
          }
          return false;
        },
      },
      handlePaste(view: EditorView, event: ClipboardEvent): boolean {
        return handleClipboardPaste(view, event, options);
      },
    },
  });
}
