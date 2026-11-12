/**
 * Lossless sourceSlice & Canonical GFM Markdown Serializer (KB-P3-45, S5.1, S5.2).
 * Emits untouched blocks byte-for-byte from originalSource while re-serializing only modified blocks.
 */

import type { Node as ProsemirrorNode } from 'prosemirror-model';
import type { SourceSlice } from './schema';

/**
 * Serializes a ProseMirror document back to canonical UTF-8 Markdown.
 * Untouched blocks (dirty: false, sourceSlice !== null) are sliced byte-for-byte from originalSource.
 * Touched blocks (dirty: true or sourceSlice === null) are serialized using canonical GFM rules.
 */
export function serializeMarkdown(doc: ProsemirrorNode, originalSource: string): string {
  if (doc.childCount === 0) {
    return '';
  }

  // Check if every top-level block is untouched
  let allClean = true;
  for (let i = 0; i < doc.childCount; i++) {
    const child = doc.child(i);
    const slice = child.attrs.sourceSlice as SourceSlice | null;
    const dirty = Boolean(child.attrs.dirty);
    if (dirty || slice === null) {
      allClean = false;
      break;
    }
  }

  if (allClean) {
    return originalSource;
  }

  let output = '';

  for (let i = 0; i < doc.childCount; i++) {
    const curr = doc.child(i);
    const prev = i > 0 ? doc.child(i - 1) : null;

    const currSlice = curr.attrs.sourceSlice as SourceSlice | null;
    const currDirty = Boolean(curr.attrs.dirty);
    const isCurrClean = !currDirty && currSlice !== null;

    const prevSlice = prev ? (prev.attrs.sourceSlice as SourceSlice | null) : null;
    const prevDirty = prev ? Boolean(prev.attrs.dirty) : false;
    const isPrevClean = prev !== null && !prevDirty && prevSlice !== null;

    // Separators between blocks
    if (i === 0) {
      if (isCurrClean) {
        output += originalSource.slice(0, currSlice.from);
      }
    } else {
      if (isPrevClean && isCurrClean) {
        output += originalSource.slice(prevSlice.to, currSlice.from);
      } else {
        output += '\n\n';
      }
    }

    // Block content
    if (isCurrClean) {
      output += originalSource.slice(currSlice.from, currSlice.to);
    } else {
      output += serializeBlock(curr);
    }
  }

  // Trailing whitespace after last block if last block was clean
  const lastChild = doc.child(doc.childCount - 1);
  const lastSlice = lastChild.attrs.sourceSlice as SourceSlice | null;
  const lastDirty = Boolean(lastChild.attrs.dirty);
  if (!lastDirty && lastSlice !== null) {
    output += originalSource.slice(lastSlice.to);
  }

  return output;
}

export function serializeBlock(node: ProsemirrorNode): string {
  switch (node.type.name) {
    case 'heading': {
      const level = (node.attrs.level as number) || 1;
      const hashes = '#'.repeat(Math.max(1, Math.min(6, level)));
      return `${hashes} ${serializeInlines(node)}`;
    }

    case 'paragraph': {
      return serializeInlines(node);
    }

    case 'code_block': {
      const lang = (node.attrs.lang as string) || '';
      const text = node.textContent;
      let fence = '```';
      while (text.includes(fence)) {
        fence += '`';
      }
      return `${fence}${lang}\n${text}\n${fence}`;
    }

    case 'blockquote': {
      const innerBlocks: string[] = [];
      for (let i = 0; i < node.childCount; i++) {
        innerBlocks.push(serializeBlock(node.child(i)));
      }
      const combined = innerBlocks.join('\n\n');
      return combined
        .split('\n')
        .map((line) => (line ? `> ${line}` : '>'))
        .join('\n');
    }

    case 'bullet_list': {
      const items: string[] = [];
      for (let i = 0; i < node.childCount; i++) {
        items.push(`- ${serializeListItemContent(node.child(i))}`);
      }
      return items.join('\n');
    }

    case 'ordered_list': {
      const start = (node.attrs.order as number) || 1;
      const items: string[] = [];
      for (let i = 0; i < node.childCount; i++) {
        items.push(`${String(start + i)}. ${serializeListItemContent(node.child(i))}`);
      }
      return items.join('\n');
    }

    case 'task_list': {
      const items: string[] = [];
      for (let i = 0; i < node.childCount; i++) {
        const item = node.child(i);
        const mark = item.attrs.checked ? '[x]' : '[ ]';
        items.push(`- ${mark} ${serializeListItemContent(item)}`);
      }
      return items.join('\n');
    }

    case 'table': {
      const rows: string[] = [];
      let headerRow = true;
      const aligns: ('left' | 'center' | 'right' | null)[] = [];

      for (let rIdx = 0; rIdx < node.childCount; rIdx++) {
        const rowNode = node.child(rIdx);
        const cells: string[] = [];

        for (let cIdx = 0; cIdx < rowNode.childCount; cIdx++) {
          const cellNode = rowNode.child(cIdx);
          cells.push(serializeInlines(cellNode).trim());
          if (headerRow) {
            aligns.push((cellNode.attrs.align as 'left' | 'center' | 'right' | null) ?? null);
          }
        }
        rows.push(`| ${cells.join(' | ')} |`);

        if (headerRow) {
          headerRow = false;
          const delimiters = aligns.map((align) => {
            if (align === 'left') return ':---';
            if (align === 'center') return ':---:';
            if (align === 'right') return '---:';
            return '---';
          });
          rows.push(`| ${delimiters.join(' | ')} |`);
        }
      }
      return rows.join('\n');
    }

    case 'horizontal_rule': {
      return '---';
    }

    case 'image_block': {
      const alt = (node.attrs.alt as string) || '';
      const src = (node.attrs.src as string) || '';
      const title = node.attrs.title ? ` "${String(node.attrs.title)}"` : '';
      return `![${alt}](${src}${title})`;
    }

    case 'definition': {
      const label = (node.attrs.label as string) || (node.attrs.identifier as string);
      const url = (node.attrs.url as string) || '';
      const title = node.attrs.title ? ` "${String(node.attrs.title)}"` : '';
      return `[${label}]: ${url}${title}`;
    }

    default:
      return node.textContent;
  }
}

function serializeListItemContent(item: ProsemirrorNode): string {
  const blocks: string[] = [];
  for (let i = 0; i < item.childCount; i++) {
    blocks.push(serializeBlock(item.child(i)));
  }
  return blocks.join('\n\n');
}

export function serializeInlines(parent: ProsemirrorNode): string {
  let result = '';

  for (let i = 0; i < parent.childCount; i++) {
    const node = parent.child(i);

    if (node.isText) {
      let text = node.text ?? '';
      // Sort marks so inner marks (code) are wrapped before outer marks (link)
      const markOrder: Record<string, number> = {
        code: 1,
        em: 2,
        strike: 3,
        strong: 4,
        link: 5,
      };
      const sortedMarks = [...node.marks].sort(
        (a, b) => (markOrder[a.type.name] ?? 0) - (markOrder[b.type.name] ?? 0),
      );

      for (const mark of sortedMarks) {
        switch (mark.type.name) {
          case 'code':
            text = `\`${text}\``;
            break;
          case 'em':
            text = `*${text}*`;
            break;
          case 'strike':
            text = `~~${text}~~`;
            break;
          case 'strong':
            text = `**${text}**`;
            break;
          case 'link': {
            const rawRef = mark.attrs.rawRef as string | null;
            if (rawRef !== null) {
              text = rawRef === '' ? `[${text}]` : `[${text}][${rawRef}]`;
            } else {
              const href = (mark.attrs.href as string) || '';
              const title = mark.attrs.title ? ` "${String(mark.attrs.title)}"` : '';
              text = `[${text}](${href}${title})`;
            }
            break;
          }
          default:
            break;
        }
      }
      result += text;
    } else if (node.type.name === 'hard_break') {
      result += '  \n';
    } else if (node.type.name === 'image') {
      const alt = (node.attrs.alt as string) || '';
      const src = (node.attrs.src as string) || '';
      const title = node.attrs.title ? ` "${String(node.attrs.title)}"` : '';
      result += `![${alt}](${src}${title})`;
    }
  }

  return result;
}
