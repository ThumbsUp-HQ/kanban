/**
 * Markdown Structural Density Detector (KB-P3-46, S5.2).
 * Distinguishes intentional raw Markdown from casual plain text containing accidental * or #.
 */

import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';

interface MdastNode {
  type: string;
  lang?: string | null;
  checked?: boolean | null;
  children?: MdastNode[];
}

interface MdastRoot {
  type: 'root';
  children: MdastNode[];
}

const remarkProcessor = unified().use(remarkParse).use(remarkGfm);

/**
 * Evaluates whether plain text contains sufficient structural Markdown density
 * to trigger automatic conversion into ProseMirror blocks.
 *
 * Threshold:
 * - >= 1 fenced code block / ```mermaid / ```svg, OR
 * - >= 1 GFM pipe table, OR
 * - >= 2 structural block tokens (headings, lists, blockquotes, task items, thematic breaks).
 */
export function isStructuralMarkdown(plainText: string): boolean {
  if (!plainText || plainText.trim() === '') {
    return false;
  }

  // Fast check: If no markdown structural indicators exist, return false early
  if (!/[#`>|\-*_~]/.test(plainText)) {
    return false;
  }

  let tree: MdastRoot;
  /* v8 ignore next 5 */
  try {
    tree = remarkProcessor.parse(plainText) as unknown as MdastRoot;
  } catch {
    return false;
  }

  /* v8 ignore next 3 */
  if (tree.children.length === 0) {
    return false;
  }

  let structuralBlockCount = 0;

  for (const child of tree.children) {
    // 1. Fenced code block or table triggers immediately
    if (child.type === 'code' && (plainText.includes('```') || plainText.includes('~~~'))) {
      return true;
    }

    if (child.type === 'table') {
      return true;
    }

    // 2. Count structural block tokens
    if (child.type === 'heading') {
      structuralBlockCount++;
    } else if (child.type === 'blockquote') {
      structuralBlockCount++;
    } else if (child.type === 'thematicBreak') {
      structuralBlockCount++;
    } else if (child.type === 'list' && child.children) {
      const items = child.children;
      structuralBlockCount += items.length;
      for (const item of items) {
        if (typeof item.checked === 'boolean') {
          structuralBlockCount++;
        }
      }
    }

    if (structuralBlockCount >= 2) {
      return true;
    }
  }

  return false;
}
