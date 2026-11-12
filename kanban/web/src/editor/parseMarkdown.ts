/**
 * Byte-Exact sourceSlice Markdown Parser (KB-P3-45, S5.1, S5.2).
 * Parses canonical GFM Markdown into ProseMirror document nodes with exact byte offsets.
 */

import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import type { Node as ProsemirrorNode, Mark } from 'prosemirror-model';
import { editorSchema, isAllowedUri, type SourceSlice } from './schema';

export class EditorRangeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'EditorRangeError';
  }
}

export const MARKDOWN_MAX_BYTES = 1_048_576; // 1 MiB

/**
 * Computes exact UTF-8 byte length for a given string.
 */
export function getUtf8ByteLength(str: string): number {
  return new TextEncoder().encode(str).length;
}

interface MdastPositionPoint {
  line: number;
  column: number;
  offset?: number;
}

interface MdastPosition {
  start: MdastPositionPoint;
  end: MdastPositionPoint;
}

export interface MdastNode {
  type: string;
  position?: MdastPosition;
  value?: string;
  children?: MdastNode[];
  depth?: number;
  lang?: string | null;
  meta?: string | null;
  ordered?: boolean | null;
  start?: number | null;
  checked?: boolean | null;
  align?: ('left' | 'center' | 'right' | null)[] | null;
  identifier?: string;
  label?: string | null;
  url?: string;
  title?: string | null;
  alt?: string | null;
}

interface MdastRoot extends MdastNode {
  type: 'root';
  children: MdastNode[];
}

const remarkProcessor = unified().use(remarkParse).use(remarkGfm);

/**
 * Parses a canonical GFM Markdown string into a ProseMirror document.
 * Enforces a strict 1 MiB input cap, attaching { from, to } offsets to all top-level blocks.
 */
export function parseMarkdown(markdown: string): {
  doc: ProsemirrorNode;
  originalSource: string;
} {
  if (getUtf8ByteLength(markdown) > MARKDOWN_MAX_BYTES) {
    throw new EditorRangeError('MARKDOWN_MAX_BYTES_EXCEEDED');
  }

  if (markdown.trim() === '') {
    const emptyDoc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create({
        sourceSlice: { from: 0, to: markdown.length },
        dirty: false,
      }),
    ]);
    return { doc: emptyDoc, originalSource: markdown };
  }

  const tree = remarkProcessor.parse(markdown) as unknown as MdastRoot;
  const blocks: ProsemirrorNode[] = [];

  for (const child of tree.children) {
    const converted = convertTopLevelNode(child);
    if (converted) {
      blocks.push(converted);
    }
  }

  const doc = editorSchema.nodes.doc.create(null, blocks);
  return { doc, originalSource: markdown };
}

function extractSlice(node: MdastNode): SourceSlice | null {
  const pos = node.position;
  if (pos && typeof pos.start.offset === 'number' && typeof pos.end.offset === 'number') {
    return {
      from: pos.start.offset,
      to: pos.end.offset,
    };
  }
  return null;
}

interface ParseContext {
  sanitized: boolean;
}

export function convertTopLevelNode(node: MdastNode): ProsemirrorNode | null {
  const context: ParseContext = { sanitized: false };
  const block = convertNodeWithContext(node, context);
  if (!block) return null;

  if (context.sanitized) {
    return block.type.create({ ...block.attrs, sourceSlice: null, dirty: true }, block.content, block.marks);
  }

  return block;
}

function convertNodeWithContext(node: MdastNode, context: ParseContext): ProsemirrorNode | null {
  const sourceSlice = extractSlice(node);
  const commonAttrs = { sourceSlice, dirty: false };

  switch (node.type) {
    case 'heading': {
      const inlines = convertInlines(node.children ?? [], [], context);
      return editorSchema.nodes.heading.create(
        { level: node.depth ?? 1, ...commonAttrs },
        inlines,
      );
    }

    case 'paragraph': {
      const inlines = convertInlines(node.children ?? [], [], context);
      return editorSchema.nodes.paragraph.create(commonAttrs, inlines);
    }

    case 'code': {
      const content = node.value ? [editorSchema.text(node.value)] : undefined;
      return editorSchema.nodes.code_block.create(
        { lang: node.lang ?? '', meta: node.meta ?? '', ...commonAttrs },
        content,
      );
    }

    case 'blockquote': {
      const innerBlocks: ProsemirrorNode[] = [];
      for (const item of node.children ?? []) {
        const blk = convertBlockNode(item, context);
        if (blk) {
          innerBlocks.push(blk);
        }
      }
      if (innerBlocks.length === 0) {
        innerBlocks.push(editorSchema.nodes.paragraph.create());
      }
      return editorSchema.nodes.blockquote.create(commonAttrs, innerBlocks);
    }

    case 'list': {
      const listChildren = node.children ?? [];
      const isTaskList = listChildren.some(
        (li) => li.checked !== null && li.checked !== undefined,
      );

      const items: ProsemirrorNode[] = [];
      for (const li of listChildren) {
        const itemContent: ProsemirrorNode[] = [];
        for (const blk of li.children ?? []) {
          const convertedBlk = convertBlockNode(blk, context);
          if (convertedBlk) {
            itemContent.push(convertedBlk);
          }
        }
        if (itemContent.length === 0) {
          itemContent.push(editorSchema.nodes.paragraph.create());
        }

        if (isTaskList) {
          items.push(
            editorSchema.nodes.task_item.create(
              { checked: Boolean(li.checked) },
              itemContent,
            ),
          );
        } else {
          items.push(editorSchema.nodes.list_item.create(null, itemContent));
        }
      }

      if (isTaskList) {
        return editorSchema.nodes.task_list.create(commonAttrs, items);
      }
      if (node.ordered) {
        return editorSchema.nodes.ordered_list.create(
          { order: node.start ?? 1, ...commonAttrs },
          items,
        );
      }
      return editorSchema.nodes.bullet_list.create(commonAttrs, items);
    }

    case 'table': {
      const rows: ProsemirrorNode[] = [];
      const alignments = node.align ?? [];
      const tableChildren = node.children ?? [];

      let rIdx = 0;
      for (const row of tableChildren) {
        const cells: ProsemirrorNode[] = [];
        const rowChildren = row.children ?? [];

        let cIdx = 0;
        for (const cell of rowChildren) {
          const align = alignments[cIdx] ?? null;
          const inlines = convertInlines(cell.children ?? [], [], context);

          if (rIdx === 0) {
            cells.push(editorSchema.nodes.table_header.create({ align }, inlines));
          } else {
            cells.push(editorSchema.nodes.table_cell.create({ align }, inlines));
          }
          cIdx++;
        }
        rows.push(editorSchema.nodes.table_row.create(null, cells));
        rIdx++;
      }

      return editorSchema.nodes.table.create(commonAttrs, rows);
    }

    case 'thematicBreak': {
      return editorSchema.nodes.horizontal_rule.create(commonAttrs);
    }

    case 'definition': {
      return editorSchema.nodes.definition.create({
        identifier: node.identifier ?? '',
        label: (node.label ?? node.identifier) ?? '',
        url: node.url ?? '',
        title: node.title ?? '',
        ...commonAttrs,
      });
    }

    case 'html': {
      // Raw HTML block is rendered strictly as inert literal text in a paragraph
      const inlines = node.value ? [editorSchema.text(node.value)] : undefined;
      return editorSchema.nodes.paragraph.create(commonAttrs, inlines);
    }

    default:
      return null;
  }
}

function convertBlockNode(node: MdastNode, context: ParseContext): ProsemirrorNode | null {
  return convertNodeWithContext(node, context);
}

export function convertInlines(
  nodes: MdastNode[],
  activeMarks: readonly Mark[] = [],
  context: ParseContext = { sanitized: false },
): ProsemirrorNode[] {
  const result: ProsemirrorNode[] = [];

  for (const node of nodes) {
    switch (node.type) {
      case 'text': {
        if (node.value) {
          result.push(editorSchema.text(node.value, activeMarks));
        }
        break;
      }

      case 'inlineCode': {
        if (node.value) {
          const codeMark = editorSchema.marks.code.create();
          result.push(editorSchema.text(node.value, [...activeMarks, codeMark]));
        }
        break;
      }

      case 'emphasis': {
        const emMark = editorSchema.marks.em.create();
        result.push(...convertInlines(node.children ?? [], [...activeMarks, emMark], context));
        break;
      }

      case 'strong': {
        const strongMark = editorSchema.marks.strong.create();
        result.push(...convertInlines(node.children ?? [], [...activeMarks, strongMark], context));
        break;
      }

      case 'delete': {
        const strikeMark = editorSchema.marks.strike.create();
        result.push(...convertInlines(node.children ?? [], [...activeMarks, strikeMark], context));
        break;
      }

      case 'link': {
        if (isAllowedUri(node.url)) {
          const linkMark = editorSchema.marks.link.create({
            href: node.url,
            title: node.title ?? '',
            rawRef: null,
          });
          result.push(...convertInlines(node.children ?? [], [...activeMarks, linkMark], context));
        } else {
          // Stripped to plain text if URI scheme is dangerous or unapproved
          context.sanitized = true;
          result.push(...convertInlines(node.children ?? [], activeMarks, context));
        }
        break;
      }

      case 'linkReference': {
        const linkMark = editorSchema.marks.link.create({
          href: '',
          title: '',
          rawRef: node.identifier ?? '',
        });
        result.push(...convertInlines(node.children ?? [], [...activeMarks, linkMark], context));
        break;
      }

      case 'image': {
        if (isAllowedUri(node.url)) {
          result.push(
            editorSchema.nodes.image.create({
              src: node.url,
              alt: node.alt ?? '',
              title: node.title ?? '',
            }),
          );
        } else {
          // Dangerous image URI scheme stripped: render alt text or omit
          context.sanitized = true;
          if (node.alt) {
            result.push(editorSchema.text(node.alt, activeMarks));
          }
        }
        break;
      }

      case 'imageReference': {
        if (node.alt) {
          result.push(editorSchema.text(node.alt, activeMarks));
        }
        break;
      }

      case 'break': {
        result.push(editorSchema.nodes.hard_break.create());
        break;
      }

      case 'html': {
        // Inline raw HTML is rendered strictly as inert literal text
        if (node.value) {
          result.push(editorSchema.text(node.value, activeMarks));
        }
        break;
      }

      default:
        break;
    }
  }

  return result;
}
