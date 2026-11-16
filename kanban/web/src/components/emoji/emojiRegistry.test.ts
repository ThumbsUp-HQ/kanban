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
});
