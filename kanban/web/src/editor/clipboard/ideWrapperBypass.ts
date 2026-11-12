/**
 * IDE Syntax-Highlighted Code Wrapper Bypass (KB-P3-46, S5.2).
 * Detects VS Code or editor syntax-highlighted HTML snippets and converts them into clean fenced code blocks.
 */

import { stripInvisibleUnicode } from './hiddenDomPruner';
import { ensureTrustedTypesPolicies } from './trustedTypes';

export interface IdeCodePasteResult {
  isIdeCode: boolean;
  codeText: string;
  language: string;
}

const VSCODE_MODE_MAP: Record<string, string> = {
  typescript: 'ts',
  typescriptreact: 'tsx',
  javascript: 'js',
  javascriptreact: 'jsx',
  python: 'py',
  markdown: 'md',
  shellscript: 'sh',
  bash: 'sh',
  sh: 'sh',
  dockerfile: 'dockerfile',
  rust: 'rs',
  golang: 'go',
  ruby: 'rb',
  csharp: 'cs',
  cpp: 'cpp',
  c: 'c',
  html: 'html',
  css: 'css',
  scss: 'scss',
  json: 'json',
  yaml: 'yaml',
  sql: 'sql',
};

const DISALLOWED_SEMANTIC_TAGS = new Set([
  'H1',
  'H2',
  'H3',
  'H4',
  'H5',
  'H6',
  'P',
  'UL',
  'OL',
  'LI',
  'TABLE',
  'THEAD',
  'TBODY',
  'TR',
  'TD',
  'TH',
  'BLOCKQUOTE',
  'A',
  'IMG',
  'HR',
]);

const ALLOWED_CODE_WRAPPER_TAGS = new Set(['PRE', 'DIV', 'CODE', 'SPAN', 'BR']);

/**
 * Detects whether pasted clipboard content originates from an IDE code editor wrapper.
 */
export function detectIdeCodePaste(clipboardData: DataTransfer): IdeCodePasteResult {
  const plainText = clipboardData.getData('text/plain');

  // 1. Check for vscode-editor-data
  const vscodeData = clipboardData.getData('vscode-editor-data');
  if (vscodeData) {
    try {
      const parsed = JSON.parse(vscodeData) as { mode?: string };
      const rawMode = (parsed.mode ?? '').trim().toLowerCase();
      const language = VSCODE_MODE_MAP[rawMode] ?? (/^[a-z0-9_-]+$/.test(rawMode) ? rawMode : '');
      return {
        isIdeCode: true,
        codeText: stripInvisibleUnicode(plainText),
        language,
      };
    } catch {
      // Invalid JSON in vscode-editor-data, fall through to HTML heuristic
    }
  }

  // 2. Check HTML structure for single <pre>/<div> code wrapper with only inline color spans
  const rawHtml = clipboardData.getData('text/html');
  if (!rawHtml || rawHtml.trim() === '') {
    return { isIdeCode: false, codeText: '', language: '' };
  }

  const { sanitizerPolicy } = ensureTrustedTypesPolicies();
  /* v8 ignore next */
  const policyInput = sanitizerPolicy ? sanitizerPolicy.createHTML(rawHtml) : rawHtml;

  const parser = new DOMParser();
  const doc = parser.parseFromString(policyInput, 'text/html');

  // Verify there are no semantic block elements
  const allElements = Array.from(doc.body.querySelectorAll('*'));
  for (const el of allElements) {
    if (DISALLOWED_SEMANTIC_TAGS.has(el.tagName)) {
      return { isIdeCode: false, codeText: '', language: '' };
    }
    if (!ALLOWED_CODE_WRAPPER_TAGS.has(el.tagName)) {
      return { isIdeCode: false, codeText: '', language: '' };
    }
  }

  // Check that root element is a single <pre> or <div>
  const rootElements = Array.from(doc.body.children);
  if (rootElements.length !== 1) {
    return { isIdeCode: false, codeText: '', language: '' };
  }

  const root = rootElements[0];
  /* v8 ignore next */
  if (!root) {
    return { isIdeCode: false, codeText: '', language: '' };
  }
  if (root.tagName !== 'PRE' && root.tagName !== 'DIV') {
    return { isIdeCode: false, codeText: '', language: '' };
  }

  // Check if spans or root contain inline styling (color, background, font-family)
  let hasCodeStyling = false;
  let detectedLang = '';

  const classAttr = (root.getAttribute('class') ?? '') + ' ' + allElements.map((e) => e.getAttribute('class') ?? '').join(' ');
  const langMatch = /\b(?:lang|language)-([a-z0-9_-]+)\b/i.exec(classAttr);
  if (langMatch?.[1]) {
    const raw = langMatch[1].toLowerCase();
    detectedLang = VSCODE_MODE_MAP[raw] ?? raw;
    hasCodeStyling = true;
  }

  for (const el of [root, ...allElements]) {
    const style = el.getAttribute('style') ?? '';
    if (/color\s*:/i.test(style) || /background\s*:/i.test(style) || /font-family\s*:\s*.*mono/i.test(style)) {
      hasCodeStyling = true;
      break;
    }
  }

  if (hasCodeStyling) {
    const code = plainText !== '' ? plainText : doc.body.textContent;
    return {
      isIdeCode: true,
      codeText: stripInvisibleUnicode(code),
      language: detectedLang,
    };
  }

  return { isIdeCode: false, codeText: '', language: '' };
}
