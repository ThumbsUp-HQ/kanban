/**
 * ProseMirror GitHub-Flavored Markdown Schema with sourceSlice Block Attributes (KB-P3-45, S5.1, S5.2).
 */

import { Schema, type NodeSpec, type MarkSpec } from 'prosemirror-model';

export interface SourceSlice {
  from: number;
  to: number;
}

export interface CommonBlockAttrs {
  sourceSlice: SourceSlice | null;
  dirty: boolean;
}

export const commonBlockAttrs = {
  sourceSlice: { default: null },
  dirty: { default: false },
};

/**
 * Validates whether a URI scheme belongs to the approved allowlist (S5.2, S5.4).
 * Permits only: https://, http://, mailto:, #, /, and attachment://
 * Strictly strips javascript:, vbscript:, data:, file:, and protocol-relative // URIs.
 */
export function isAllowedUri(uri: string | null | undefined): boolean {
  if (!uri || typeof uri !== 'string') {
    return false;
  }
  const trimmed = uri.trim();
  if (trimmed.startsWith('#')) {
    return true;
  }
  if (trimmed.startsWith('/')) {
    // Relative path. Disallow protocol-relative '//'
    return !trimmed.startsWith('//');
  }
  const lower = trimmed.toLowerCase();
  return (
    lower.startsWith('https://') ||
    lower.startsWith('http://') ||
    lower.startsWith('mailto:') ||
    lower.startsWith('attachment://')
  );
}

/**
 * Sanitizes a URI against the allowlist. Returns null if invalid or dangerous.
 */
export function sanitizeUri(uri: string | null | undefined): string | null {
  if (!uri) {
    return null;
  }
  return isAllowedUri(uri) ? uri.trim() : null;
}

export type EditorNodeName =
  | 'doc'
  | 'paragraph'
  | 'heading'
  | 'code_block'
  | 'blockquote'
  | 'bullet_list'
  | 'ordered_list'
  | 'list_item'
  | 'task_list'
  | 'task_item'
  | 'table'
  | 'table_row'
  | 'table_header'
  | 'table_cell'
  | 'horizontal_rule'
  | 'image_block'
  | 'definition'
  | 'text'
  | 'hard_break'
  | 'image';

export type EditorMarkName = 'strong' | 'em' | 'strike' | 'code' | 'link';

const nodes: Record<EditorNodeName, NodeSpec> = {
  doc: {
    content: 'block+',
  },

  paragraph: {
    group: 'block',
    content: 'inline*',
    attrs: {
      ...commonBlockAttrs,
    },
    parseDOM: [{ tag: 'p' }],
    toDOM() {
      return ['p', 0];
    },
  },

  heading: {
    group: 'block',
    content: 'inline*',
    attrs: {
      level: { default: 1 },
      ...commonBlockAttrs,
    },
    defining: true,
    parseDOM: [
      { tag: 'h1', attrs: { level: 1 } },
      { tag: 'h2', attrs: { level: 2 } },
      { tag: 'h3', attrs: { level: 3 } },
      { tag: 'h4', attrs: { level: 4 } },
      { tag: 'h5', attrs: { level: 5 } },
      { tag: 'h6', attrs: { level: 6 } },
    ],
    toDOM(node) {
      return [`h${String(node.attrs.level)}`, 0];
    },
  },

  code_block: {
    group: 'block',
    content: 'text*',
    marks: '',
    code: true,
    defining: true,
    attrs: {
      lang: { default: '' },
      meta: { default: '' },
      ...commonBlockAttrs,
    },
    parseDOM: [
      {
        tag: 'pre',
        preserveWhitespace: 'full',
        getAttrs(dom) {
          const el = dom;
          const codeEl = el.querySelector('code');
          const className = codeEl?.className ?? el.className;
          const match = /language-([a-z0-9_-]+)/i.exec(className);
          return { lang: match ? match[1] : '' };
        },
      },
    ],
    toDOM(node) {
      const lang = (node.attrs.lang as string) || '';
      return [
        'pre',
        { class: 'kb-code-block' },
        ['code', { class: lang ? `language-${lang}` : undefined }, 0],
      ];
    },
  },

  blockquote: {
    group: 'block',
    content: 'block+',
    defining: true,
    attrs: {
      ...commonBlockAttrs,
    },
    parseDOM: [{ tag: 'blockquote' }],
    toDOM() {
      return ['blockquote', 0];
    },
  },

  bullet_list: {
    group: 'block',
    content: 'list_item+',
    attrs: {
      ...commonBlockAttrs,
    },
    parseDOM: [{ tag: 'ul:not([data-task-list])' }],
    toDOM() {
      return ['ul', 0];
    },
  },

  ordered_list: {
    group: 'block',
    content: 'list_item+',
    attrs: {
      order: { default: 1 },
      ...commonBlockAttrs,
    },
    parseDOM: [
      {
        tag: 'ol',
        getAttrs(dom) {
          const startAttr = (dom).getAttribute('start');
          const order = startAttr ? parseInt(startAttr, 10) : 1;
          return { order: Number.isNaN(order) ? 1 : order };
        },
      },
    ],
    toDOM(node) {
      const order = node.attrs.order as number;
      return order === 1 ? ['ol', 0] : ['ol', { start: order }, 0];
    },
  },

  list_item: {
    content: 'paragraph block*',
    defining: true,
    parseDOM: [{ tag: 'li:not([data-task-item])' }],
    toDOM() {
      return ['li', 0];
    },
  },

  task_list: {
    group: 'block',
    content: 'task_item+',
    attrs: {
      ...commonBlockAttrs,
    },
    parseDOM: [{ tag: 'ul[data-task-list]' }],
    toDOM() {
      return ['ul', { 'data-task-list': 'true', class: 'kb-task-list' }, 0];
    },
  },

  task_item: {
    content: 'paragraph block*',
    defining: true,
    attrs: {
      checked: { default: false },
    },
    parseDOM: [
      {
        tag: 'li[data-task-item]',
        getAttrs(dom) {
          const input = (dom).querySelector('input[type="checkbox"]');
          return { checked: input ? (input as HTMLInputElement).checked : false };
        },
      },
    ],
    toDOM(node) {
      const checked = Boolean(node.attrs.checked);
      return [
        'li',
        { 'data-task-item': 'true', class: `kb-task-item${checked ? ' is-checked' : ''}` },
        [
          'input',
          {
            type: 'checkbox',
            class: 'kb-task-checkbox',
            disabled: 'disabled',
            checked: checked ? 'checked' : undefined,
          },
        ],
        ['div', { class: 'kb-task-item__content' }, 0],
      ];
    },
  },

  table: {
    group: 'block',
    content: 'table_row+',
    isolating: true,
    attrs: {
      ...commonBlockAttrs,
    },
    parseDOM: [{ tag: 'table' }],
    toDOM() {
      return ['table', { class: 'kb-table' }, ['tbody', 0]];
    },
  },

  table_row: {
    content: '(table_cell | table_header)*',
    parseDOM: [{ tag: 'tr' }],
    toDOM() {
      return ['tr', 0];
    },
  },

  table_header: {
    content: 'inline*',
    isolating: true,
    attrs: {
      align: { default: null },
    },
    parseDOM: [
      {
        tag: 'th',
        getAttrs(dom) {
          const el = dom;
          const styleAlign = el.style.textAlign;
          const align = el.getAttribute('align') ?? (styleAlign !== '' ? styleAlign : null);
          return { align };
        },
      },
    ],
    toDOM(node) {
      const align = node.attrs.align as string | null;
      return ['th', align ? { align, 'data-align': align } : {}, 0];
    },
  },

  table_cell: {
    content: 'inline*',
    isolating: true,
    attrs: {
      align: { default: null },
    },
    parseDOM: [
      {
        tag: 'td',
        getAttrs(dom) {
          const el = dom;
          const styleAlign = el.style.textAlign;
          const align = el.getAttribute('align') ?? (styleAlign !== '' ? styleAlign : null);
          return { align };
        },
      },
    ],
    toDOM(node) {
      const align = node.attrs.align as string | null;
      return ['td', align ? { align, 'data-align': align } : {}, 0];
    },
  },

  horizontal_rule: {
    group: 'block',
    attrs: {
      ...commonBlockAttrs,
    },
    parseDOM: [{ tag: 'hr' }],
    toDOM() {
      return ['hr', { class: 'kb-hr' }];
    },
  },

  image_block: {
    group: 'block',
    draggable: true,
    attrs: {
      src: { default: '' },
      alt: { default: '' },
      title: { default: '' },
      ...commonBlockAttrs,
    },
    parseDOM: [
      {
        tag: 'div[data-image-block]',
        getAttrs(dom) {
          const img = (dom).querySelector('img');
          return {
            src: img?.getAttribute('src') ?? '',
            alt: img?.getAttribute('alt') ?? '',
            title: img?.getAttribute('title') ?? '',
          };
        },
      },
    ],
    toDOM(node) {
      const safeSrc = sanitizeUri(node.attrs.src as string) ?? '';
      return [
        'div',
        { 'data-image-block': 'true', class: 'kb-editor__image-block' },
        ['img', { src: safeSrc, alt: (node.attrs.alt as string) || '', title: (node.attrs.title as string) || undefined }],
      ];
    },
  },

  definition: {
    group: 'block',
    attrs: {
      identifier: { default: '' },
      label: { default: '' },
      url: { default: '' },
      title: { default: '' },
      ...commonBlockAttrs,
    },
    parseDOM: [
      {
        tag: 'div[data-definition]',
        getAttrs(dom) {
          const el = dom;
          return {
            identifier: el.getAttribute('data-definition') ?? '',
            label: el.getAttribute('data-label') ?? '',
            url: el.getAttribute('data-url') ?? '',
            title: el.getAttribute('data-title') ?? '',
          };
        },
      },
    ],
    toDOM(node) {
      const label = (node.attrs.label as string) || (node.attrs.identifier as string);
      return [
        'div',
        {
          class: 'kb-editor__definition',
          'data-definition': node.attrs.identifier as string,
          'data-label': label,
          'data-url': node.attrs.url as string,
          'data-title': (node.attrs.title as string) || '',
        },
        `[${label}]: ${node.attrs.url as string}`,
      ];
    },
  },

  text: {
    group: 'inline',
  },

  hard_break: {
    group: 'inline',
    inline: true,
    selectable: false,
    parseDOM: [{ tag: 'br' }],
    toDOM() {
      return ['br'];
    },
  },

  image: {
    group: 'inline',
    inline: true,
    draggable: true,
    attrs: {
      src: { default: '' },
      alt: { default: '' },
      title: { default: '' },
    },
    parseDOM: [
      {
        tag: 'img:not([data-image-block] img)',
        getAttrs(dom) {
          const el = dom;
          return {
            src: el.getAttribute('src') ?? '',
            alt: el.getAttribute('alt') ?? '',
            title: el.getAttribute('title') ?? '',
          };
        },
      },
    ],
    toDOM(node) {
      const safeSrc = sanitizeUri(node.attrs.src as string) ?? '';
      return [
        'img',
        {
          src: safeSrc,
          alt: (node.attrs.alt as string) || '',
          title: (node.attrs.title as string) || undefined,
          class: 'kb-inline-image',
        },
      ];
    },
  },
};

const marks: Record<EditorMarkName, MarkSpec> = {
  strong: {
    parseDOM: [
      { tag: 'strong' },
      { tag: 'b' },
      {
        style: 'font-weight',
        getAttrs: (val) => /^(bold(er)?|[7-9]\d{2})$/.test(val) && null,
      },
    ],
    toDOM() {
      return ['strong', 0];
    },
  },

  em: {
    parseDOM: [
      { tag: 'em' },
      { tag: 'i' },
      { style: 'font-style=italic' },
    ],
    toDOM() {
      return ['em', 0];
    },
  },

  strike: {
    parseDOM: [
      { tag: 's' },
      { tag: 'del' },
      { tag: 'strike' },
      { style: 'text-decoration=line-through' },
    ],
    toDOM() {
      return ['s', 0];
    },
  },

  code: {
    parseDOM: [{ tag: 'code' }],
    toDOM() {
      return ['code', { class: 'kb-inline-code' }, 0];
    },
  },

  link: {
    attrs: {
      href: { default: '' },
      title: { default: '' },
      rawRef: { default: null },
    },
    inclusive: false,
    parseDOM: [
      {
        tag: 'a[href]',
        getAttrs(dom) {
          const el = dom;
          return {
            href: el.getAttribute('href') ?? '',
            title: el.getAttribute('title') ?? '',
            rawRef: el.getAttribute('data-raw-ref'),
          };
        },
      },
    ],
    toDOM(mark) {
      const safeHref = sanitizeUri(mark.attrs.href as string) ?? '#';
      const title = (mark.attrs.title as string) || undefined;
      const rawRef = mark.attrs.rawRef as string | null;
      return [
        'a',
        {
          href: safeHref,
          title,
          'data-raw-ref': rawRef ?? undefined,
          class: 'kb-link',
          rel: 'noopener noreferrer',
        },
        0,
      ];
    },
  },
};

export const editorSchema = new Schema<EditorNodeName, EditorMarkName>({
  nodes,
  marks,
});
