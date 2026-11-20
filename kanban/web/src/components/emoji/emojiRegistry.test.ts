import { describe, expect, it } from 'vitest';
import {
  EMOJI_REGISTRY,
  EXTENDED_EMOJI_REGISTRY,
  type EmojiKey,
} from './emojiRegistry';

describe('emojiRegistry', () => {
  const EXPECTED_GLYPHS: Record<EmojiKey, string> = {
    access: '🛡️',
    restricted: '🔒',
    warning: '⚠️',
    airGap: '📴',
    priorityUrgent: '🔥',
    priorityHigh: '⚡',
    priorityMedium: '🔹',
    priorityLow: '🔽',
    agent: '🤖',
    gatePending: '⏳🤖',
    gateVetoed: '🛑🤖',
    gateApproved: '✅🤖',
    externalAssignee: '🏷️',
    creatorOverride: '🔄',
    sparkle: '✨',
    sanitized: '🧼',
    rawMarkdown: '📝',
    stickyPromotion: '💡📄',
    brokenLink: '🕸️⚠️',
    scriptedField: '🧪',
    mediaBackdrop: '🌓',
  };

  it('contains exactly 21 keys', () => {
    const keys = Object.keys(EMOJI_REGISTRY);
    expect(keys).toHaveLength(21);
    expect(keys.sort()).toEqual(Object.keys(EXPECTED_GLYPHS).sort());
  });

  it('matches all specified glyphs exactly', () => {
    for (const [key, expectedGlyph] of Object.entries(EXPECTED_GLYPHS) as [EmojiKey, string][]) {
      const entry = EMOJI_REGISTRY[key];
      expect(entry).toBeDefined();
      expect(entry.glyph).toBe(expectedGlyph);
      expect(entry.domain).toBeTruthy();
      expect(entry.ariaLabel).toBeTruthy();
      expect(entry.defaultHint).toBeTruthy();
    }
  });

  it('is deeply frozen to prevent runtime mutation', () => {
    expect(Object.isFrozen(EMOJI_REGISTRY)).toBe(true);
    for (const entry of Object.values(EMOJI_REGISTRY)) {
      expect(Object.isFrozen(entry)).toBe(true);
    }
    expect(Object.isFrozen(EXTENDED_EMOJI_REGISTRY)).toBe(true);
  });

  it('contains no duplicate glyphs among registry entries', () => {
    const glyphs = Object.values(EMOJI_REGISTRY).map((entry) => entry.glyph);
    const uniqueGlyphs = new Set(glyphs);
    expect(uniqueGlyphs.size).toBe(glyphs.length);
  });

  it('ensures EXTENDED_EMOJI_REGISTRY has no key collision with EmojiKey', () => {
    const registryKeys = new Set(Object.keys(EMOJI_REGISTRY));
    for (const extKey of Object.keys(EXTENDED_EMOJI_REGISTRY)) {
      expect(registryKeys.has(extKey)).toBe(false);
    }
  });

  it('matches literal spec strings for externalAssignee and sanitized', () => {
    expect(EMOJI_REGISTRY.externalAssignee.defaultHint).toBe(
      'External free-text label - grants zero access and sends zero notifications',
    );
    expect(EMOJI_REGISTRY.sanitized.defaultHint).toBe(
      'Converted pasted HTML to clean Markdown - Cmd+Z to paste plain text',
    );
  });

  it('provides frozen agentSafeNumbering entry in EXTENDED_EMOJI_REGISTRY with correct metadata', () => {
    const entry = EXTENDED_EMOJI_REGISTRY.agentSafeNumbering;
    expect(entry).toBeDefined();
    if (!entry) {
      throw new Error('agentSafeNumbering entry missing');
    }
    expect(entry.glyph).toBe('🔢');
    expect(entry.domain).toBe('Agent-Safe Sequence Numbering');
    expect(entry.ariaLabel).toBe('Agent-safe sequence numbering');
    expect(entry.defaultHint).toBe(
      'Skips culturally loaded and superstitious sequence numbers (13, 69, 88, 404, 420, 666, 1337, 1488) to prevent autonomous LLM context drift, safety-filter refusals, and associative hallucination.',
    );
    expect(Object.isFrozen(entry)).toBe(true);
    // Strict invariant: EMOJI_REGISTRY remains exactly 21 keys
    expect(Object.keys(EMOJI_REGISTRY)).toHaveLength(21);
  });
});
