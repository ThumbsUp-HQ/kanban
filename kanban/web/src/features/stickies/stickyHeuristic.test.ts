/**
 * Unit Tests for Sticky Complexity Heuristics & Snooze Engine (KB-P3-51, S8.1, S8.2).
 */

import { describe, it, expect } from 'vitest';
import {
  evaluateStickyComplexity,
  STICKY_IDLE_DEBOUNCE_MS,
  STICKY_COLOR_TOKENS,
} from './stickyHeuristic';

describe('stickyHeuristic', () => {
  it('exports canonical constants', () => {
    expect(STICKY_IDLE_DEBOUNCE_MS).toBe(1000);
    expect(STICKY_COLOR_TOKENS).toEqual([
      'amber',
      'mint',
      'sky',
      'lavender',
      'coral',
      'slate',
    ]);
  });

  describe('Trigger 1: Character Length (> 600)', () => {
    it('does not trigger at exactly 600 characters', () => {
      const text600 = 'a'.repeat(600);
      const res = evaluateStickyComplexity(text600);
      expect(res.charLength).toBe(600);
      expect(res.exceeded).toBe(false);
      expect(res.reasons).toEqual([]);
      expect(res.shouldShowBanner).toBe(false);
    });

    it('triggers at 601 characters with exact reason string', () => {
      const text601 = 'a'.repeat(601);
      const res = evaluateStickyComplexity(text601);
      expect(res.charLength).toBe(601);
      expect(res.exceeded).toBe(true);
      expect(res.reasons).toEqual(['601 chars (> 600)']);
      expect(res.shouldShowBanner).toBe(true);
    });

    it('handles unicode multi-byte characters accurately matching code points', () => {
      // 301 emoji pairs (each 1 code point)
      const emojiText = '🚀'.repeat(601);
      const res = evaluateStickyComplexity(emojiText);
      expect(res.charLength).toBe(601);
      expect(res.exceeded).toBe(true);
      expect(res.reasons).toContain('601 chars (> 600)');
    });
  });

  describe('Trigger 2: Line Count (> 10)', () => {
    it('does not trigger at exactly 10 lines', () => {
      const text10 = Array.from({ length: 10 }, (_, i) => `line ${String(i + 1)}`).join('\n');
      const res = evaluateStickyComplexity(text10);
      expect(res.exceeded).toBe(false);
      expect(res.reasons).toEqual([]);
    });

    it('triggers at 11 lines with exact reason string', () => {
      const text11 = Array.from({ length: 11 }, (_, i) => `line ${String(i + 1)}`).join('\n');
      const res = evaluateStickyComplexity(text11);
      expect(res.exceeded).toBe(true);
      expect(res.reasons).toEqual(['11 lines (> 10)']);
    });
  });

  describe('Trigger 3: Headings Outside Code Fences (>= 2)', () => {
    it('does not trigger on 1 heading', () => {
      const text = '# Heading One\nSome regular paragraph text.';
      const res = evaluateStickyComplexity(text);
      expect(res.exceeded).toBe(false);
    });

    it('triggers on 2 headings with exact reason string', () => {
      const text = '# Heading One\n## Heading Two\nContent';
      const res = evaluateStickyComplexity(text);
      expect(res.exceeded).toBe(true);
      expect(res.reasons).toEqual(['2 headings (>= 2)']);
    });

    it('ignores # comments and headings inside code fences', () => {
      const text = [
        '# Real Heading',
        '```sh',
        '# comment 1',
        '# comment 2',
        '## fake heading inside fence',
        '```',
      ].join('\n');
      const res = evaluateStickyComplexity(text);
      expect(res.exceeded).toBe(false);
      expect(res.reasons).toEqual([]);
    });
  });

  describe('Trigger 4: Structured Blocks (Tables, Diagrams, >6-line Fences)', () => {
    it('triggers on GFM pipe table', () => {
      const table = [
        '| Header A | Header B |',
        '| --- | --- |',
        '| Val 1 | Val 2 |',
      ].join('\n');
      const res = evaluateStickyComplexity(table);
      expect(res.exceeded).toBe(true);
      expect(res.reasons).toEqual(['table, diagram, or >6-line code block']);
    });

    it('triggers on mermaid code block', () => {
      const mermaid = '```mermaid\ngraph TD;\nA-->B;\n```';
      const res = evaluateStickyComplexity(mermaid);
      expect(res.exceeded).toBe(true);
      expect(res.reasons).toEqual(['table, diagram, or >6-line code block']);
    });

    it('triggers on svg code fence or .svg reference', () => {
      const svgFence = '```svg\n<svg></svg>\n```';
      const res1 = evaluateStickyComplexity(svgFence);
      expect(res1.exceeded).toBe(true);
      expect(res1.reasons).toEqual(['table, diagram, or >6-line code block']);

      const svgRef = 'Architecture overview: ![diagram](assets/arch.svg)';
      const res2 = evaluateStickyComplexity(svgRef);
      expect(res2.exceeded).toBe(true);
      expect(res2.reasons).toEqual(['table, diagram, or >6-line code block']);
    });

    it('does not trigger on code fence with exactly 6 inner lines', () => {
      const inner = Array.from({ length: 6 }, (_, i) => `console.log(${String(i)});`).join('\n');
      const code6 = `\`\`\`js\n${inner}\n\`\`\``;
      const res = evaluateStickyComplexity(code6);
      expect(res.exceeded).toBe(false);
      expect(res.reasons).toEqual([]);
    });

    it('triggers on code fence with 7 inner lines (> 6)', () => {
      const inner = Array.from({ length: 7 }, (_, i) => `console.log(${String(i)});`).join('\n');
      const code7 = `\`\`\`js\n${inner}\n\`\`\``;
      const res = evaluateStickyComplexity(code7);
      expect(res.exceeded).toBe(true);
      expect(res.reasons).toEqual(['table, diagram, or >6-line code block']);
    });

    it('handles tilde fences (~~~) and unclosed fences > 6 lines', () => {
      const inner = Array.from({ length: 7 }, (_, i) => `val ${String(i)}`).join('\n');
      const tilde7 = `~~~\n${inner}\n~~~`;
      const resTilde = evaluateStickyComplexity(tilde7);
      expect(resTilde.exceeded).toBe(true);
      expect(resTilde.reasons).toEqual(['table, diagram, or >6-line code block']);

      const unclosed = `\`\`\`\n${inner}`;
      const resUnclosed = evaluateStickyComplexity(unclosed);
      expect(resUnclosed.exceeded).toBe(true);
      expect(resUnclosed.reasons).toEqual(['table, diagram, or >6-line code block']);
    });
  });

  describe('Trigger 5: Outbound Links Outside Code Fences (>= 3)', () => {
    it('does not trigger on 2 links', () => {
      const text = 'See [documentation](https://example.com) and <https://foo.bar>';
      const res = evaluateStickyComplexity(text);
      expect(res.exceeded).toBe(false);
      expect(res.reasons).toEqual([]);
    });

    it('triggers on 3 links with exact reason string', () => {
      const text = 'See [doc](https://example.com), <https://foo.bar>, and [KEY-123]';
      const res = evaluateStickyComplexity(text);
      expect(res.exceeded).toBe(true);
      expect(res.reasons).toEqual(['3 links (>= 3)']);
    });

    it('ignores links placed inside code blocks', () => {
      const text = [
        '[Real Link](https://example.com)',
        '```markdown',
        '[Fake 1](https://fake1.com)',
        '[Fake 2](https://fake2.com)',
        '```',
      ].join('\n');
      const res = evaluateStickyComplexity(text);
      expect(res.exceeded).toBe(false);
      expect(res.reasons).toEqual([]);
    });
  });

  describe('Snooze Math & >= 1.5x Boundary Logic', () => {
    const text620 = 'x'.repeat(620);

    it('shows banner when not snoozed (null)', () => {
      const res = evaluateStickyComplexity(text620, null);
      expect(res.exceeded).toBe(true);
      expect(res.shouldShowBanner).toBe(true);
    });

    it('suppresses banner immediately after snoozing at 620', () => {
      const res = evaluateStickyComplexity(text620, 620);
      expect(res.exceeded).toBe(true);
      expect(res.shouldShowBanner).toBe(false);
    });

    it('keeps banner suppressed at 929 chars (< 930 = 620 * 1.5)', () => {
      const text929 = 'x'.repeat(929);
      const res = evaluateStickyComplexity(text929, 620);
      expect(res.exceeded).toBe(true);
      expect(res.shouldShowBanner).toBe(false);
    });

    it('re-enables banner once sticky reaches 930 chars (>= 620 * 1.5)', () => {
      const text930 = 'x'.repeat(930);
      const res = evaluateStickyComplexity(text930, 620);
      expect(res.exceeded).toBe(true);
      expect(res.shouldShowBanner).toBe(true);
    });

    it('handles snooze at length 0: clears when charLength > 0', () => {
      const resEmpty = evaluateStickyComplexity('', 0);
      expect(resEmpty.shouldShowBanner).toBe(false);

      const resWithContent = evaluateStickyComplexity(text620, 0);
      expect(resWithContent.shouldShowBanner).toBe(true);
    });
  });

  describe('Promoted Stickies Exclusion', () => {
    it('returns exceeded: false and shouldShowBanner: false if already promoted to doc', () => {
      const largeContent = '# Doc Spec\n## Architecture\n' + 'y'.repeat(1000);
      const res = evaluateStickyComplexity(largeContent, null, 'doc-uuid-1234');
      expect(res.exceeded).toBe(false);
      expect(res.reasons).toEqual([]);
      expect(res.shouldShowBanner).toBe(false);
      expect(res.charLength).toBe(1027);
    });
  });

  describe('Empty and Edge Inputs', () => {
    it('handles empty string gracefully', () => {
      const res = evaluateStickyComplexity('');
      expect(res.charLength).toBe(0);
      expect(res.exceeded).toBe(false);
      expect(res.reasons).toEqual([]);
      expect(res.shouldShowBanner).toBe(false);
    });
  });
});
