/**
 * Unit Tests for Markdown Structural Density Detector (KB-P3-46, S5.2).
 */

import { describe, it, expect } from 'vitest';
import { isStructuralMarkdown } from './markdownDensity';

describe('markdownDensity', () => {
  it('Case 5: Branch 4 (Raw Markdown Density) detects multi-block Markdown and ignores casual prose', () => {
    // Heading + list (>= 2 block tokens) -> true
    expect(isStructuralMarkdown('## Plan\n\n- item 1\n- item 2')).toBe(true);

    // Single mermaid code block -> true
    expect(isStructuralMarkdown('```mermaid\ngraph TD\nA-->B\n```')).toBe(true);

    // Single tilde code block -> true
    expect(isStructuralMarkdown('~~~python\nprint(1)\n~~~')).toBe(true);

    // Indented 4-space code block without fence does not trigger by itself
    expect(isStructuralMarkdown('    const x = 1;')).toBe(false);

    // Regular bullet list with 2 items -> true
    expect(isStructuralMarkdown('* Item A\n* Item B')).toBe(true);

    // Single SVG code block -> true
    expect(isStructuralMarkdown('```svg\n<svg></svg>\n```')).toBe(true);

    // Casual prose with accidental * or # -> false
    expect(isStructuralMarkdown('Cost is $5 * 2 #tag')).toBe(false);
  });

  it('detects GFM pipe tables as structural Markdown', () => {
    const table = '| Header A | Header B |\n| --- | --- |\n| Cell 1 | Cell 2 |';
    expect(isStructuralMarkdown(table)).toBe(true);
  });

  it('detects task list items as structural Markdown', () => {
    expect(isStructuralMarkdown('- [ ] Incomplete task')).toBe(true);
    expect(isStructuralMarkdown('- [x] Complete task')).toBe(true);
  });

  it('detects blockquotes and thematic breaks', () => {
    expect(isStructuralMarkdown('> First quote\n\n> Second quote')).toBe(true);
    expect(isStructuralMarkdown('## Header\n\n---')).toBe(true);
  });

  it('returns false for single-line text or inline-only markup without structural blocks', () => {
    expect(isStructuralMarkdown('')).toBe(false);
    expect(isStructuralMarkdown('Just plain text without anything')).toBe(false);
    expect(isStructuralMarkdown('This is *italic* and **bold** inline text')).toBe(false);
  });

  it('handles empty children or parse failures cleanly', () => {
    // When text contains only markdown symbol but produces no children
    expect(isStructuralMarkdown('   #   ')).toBe(false);
  });
});
