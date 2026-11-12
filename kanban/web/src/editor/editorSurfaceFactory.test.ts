/**
 * Unit Tests for editorSurfaceFactory (KB-P3-45).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { EditorState, type Transaction } from 'prosemirror-state';
import { editorSchema } from './schema';

interface InputRuleInternal {
  match: RegExp;
  handler: (state: EditorState, match: RegExpMatchArray | string[], start: number, end: number) => Transaction | null;
}
import {
  createEditorPlugins,
  createEditorNodeViews,
  createEditorCustomKeybindings,
  buildGfmRules,
  createGfmInputRules,
  registerEditorExtension,
  getRegisteredExtensions,
  clearEditorExtensions,
  type EditorSurfaceKind,
} from './editorSurfaceFactory';

describe('editorSurfaceFactory', () => {
  beforeEach(() => {
    clearEditorExtensions();
  });

  const surfaces: EditorSurfaceKind[] = [
    'summary',
    'description',
    'comment',
    'sticky',
    'doc',
  ];

  it('creates default plugins for all surface kinds with onToggleRaw callback', () => {
    const handleToggle = vi.fn();
    for (const surface of surfaces) {
      const plugins = createEditorPlugins(surface, {
        onToggleRaw: handleToggle,
      });
      expect(plugins.length).toBeGreaterThan(5);

      const state = EditorState.create({
        schema: editorSchema,
        plugins,
      });
      expect(state).toBeDefined();
    }
  });

  it('executes custom keybindings including toggleRaw and mark toggles', () => {
    const toggleSpy = vi.fn();
    const keybindings = createEditorCustomKeybindings({
      onToggleRaw: toggleSpy,
    });

    expect(keybindings['Mod-Shift-m']).toBeDefined();
    expect(keybindings['Mod-Shift-M']).toBeDefined();

    const state = EditorState.create({ schema: editorSchema });
    keybindings['Mod-Shift-m']?.(state, vi.fn());
    expect(toggleSpy).toHaveBeenCalledTimes(1);
    keybindings['Mod-Shift-M']?.(state, vi.fn());
    expect(toggleSpy).toHaveBeenCalledTimes(2);
  });

  it('executes all GFM input rules handlers and pattern matching', () => {
    const rules = buildGfmRules();
    expect(rules.length).toBe(12);

    const doc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(null, [
        editorSchema.text('Initial text that is long enough for all input rules test cases'),
      ]),
    ]);
    const state = EditorState.create({ doc, schema: editorSchema });

    // Test HR rule
    const hrRule = rules.find((r) => (r as unknown as InputRuleInternal).match.test('--- '));
    expect(hrRule).toBeDefined();
    const hrResult = (hrRule as unknown as InputRuleInternal).handler(state, ['--- '], 1, 4);
    expect(hrResult).not.toBeNull();

    // Test Bold rule
    const boldRule = rules.find((r) => (r as unknown as InputRuleInternal).match.test('**bold**'));
    expect(boldRule).toBeDefined();
    const boldResult = (boldRule as unknown as InputRuleInternal).handler(state, ['**bold**', 'bold'], 1, 9);
    expect(boldResult).not.toBeNull();
    expect((boldRule as unknown as InputRuleInternal).handler(state, ['**bold**'], 1, 9)).toBeNull();

    // Test Italic rule
    const italicRule = rules.find((r) => (r as unknown as InputRuleInternal).match.test('*italic*'));
    expect(italicRule).toBeDefined();
    const italicResult = (italicRule as unknown as InputRuleInternal).handler(state, ['*italic*', 'italic'], 1, 9);
    expect(italicResult).not.toBeNull();
    expect((italicRule as unknown as InputRuleInternal).handler(state, ['*italic*'], 1, 9)).toBeNull();

    // Test Strike rule
    const strikeRule = rules.find((r) => (r as unknown as InputRuleInternal).match.test('~~strike~~'));
    expect(strikeRule).toBeDefined();
    const strikeResult = (strikeRule as unknown as InputRuleInternal).handler(state, ['~~strike~~', 'strike'], 1, 11);
    expect(strikeResult).not.toBeNull();
    expect((strikeRule as unknown as InputRuleInternal).handler(state, ['~~strike~~'], 1, 11)).toBeNull();

    // Test Code rule
    const codeRule = rules.find((r) => (r as unknown as InputRuleInternal).match.test('`code`'));
    expect(codeRule).toBeDefined();
    const codeResult = (codeRule as unknown as InputRuleInternal).handler(state, ['`code`', 'code'], 1, 7);
    expect(codeResult).not.toBeNull();
    expect((codeRule as unknown as InputRuleInternal).handler(state, ['`code`'], 1, 7)).toBeNull();

    // Test createGfmInputRules plugin instance
    const plugin = createGfmInputRules();
    expect(plugin).toBeDefined();

    // Test input rule matcher functions directly
    // Heading rule with different levels
    const headingRule = rules[0] as unknown as InputRuleInternal;
    expect(headingRule).toBeDefined();
    // Test handler for heading with and without group
    headingRule.handler(state, ['# ', '#'], 1, 3);
    headingRule.handler(state, ['# '], 1, 3);

    // Blockquote wrapping rule
    const bqRule = rules[1] as unknown as InputRuleInternal;
    expect(bqRule).toBeDefined();
    bqRule.handler(state, ['> '], 1, 3);

    // Bullet list wrapping rule
    const bulletRule = rules[2] as unknown as InputRuleInternal;
    expect(bulletRule).toBeDefined();
    bulletRule.handler(state, ['- '], 1, 3);

    // Ordered list match handler with and without group
    const olRule = rules[3] as unknown as InputRuleInternal;
    expect(olRule).toBeDefined();
    olRule.handler(state, ['42. ', '42'], 1, 5);
    olRule.handler(state, ['1. '], 1, 4);

    // Task list rules (unchecked and checked)
    const taskRule1 = rules[4] as unknown as InputRuleInternal;
    expect(taskRule1).toBeDefined();
    taskRule1.handler(state, ['- [ ] '], 1, 7);

    const taskRule2 = rules[5] as unknown as InputRuleInternal;
    expect(taskRule2).toBeDefined();
    taskRule2.handler(state, ['- [x] '], 1, 7);

    // Code block match handler with and without group
    const cbRule = rules[6] as unknown as InputRuleInternal;
    expect(cbRule).toBeDefined();
    cbRule.handler(state, ['```typescript ', 'typescript'], 1, 15);
    cbRule.handler(state, ['``` '], 1, 5);

    // Italic rule match handler with leading character
    const italicRuleMatch = rules[9] as unknown as InputRuleInternal;
    expect(italicRuleMatch).toBeDefined();
    const italicWithCharResult = italicRuleMatch.handler(state, [' a*italic*', 'italic'], 1, 10);
    expect(italicWithCharResult).not.toBeNull();

    // Inline code rule match handler with leading character
    const codeRuleMatch = rules[11] as unknown as InputRuleInternal;
    expect(codeRuleMatch).toBeDefined();
    const codeWithCharResult = codeRuleMatch.handler(state, [' a`code`', 'code'], 1, 8);
    expect(codeWithCharResult).not.toBeNull();
  });

  it('handles default options and undefined callbacks in createEditorPlugins and keybindings', () => {
    // Register extension without plugins property to test if (ext.plugins) false branch
    registerEditorExtension({ name: 'extension-without-plugins' });

    // Call without options
    const plugins = createEditorPlugins('sticky');
    expect(plugins.length).toBeGreaterThan(0);

    const keybindings = createEditorCustomKeybindings();
    expect(keybindings['Mod-Shift-m']).toBeUndefined();
    expect(keybindings['Mod-z']).toBeDefined();
    expect(keybindings['Mod-y']).toBeDefined();
    expect(keybindings['Shift-Mod-z']).toBeDefined();
    expect(keybindings['Mod-b']).toBeDefined();
    expect(keybindings['Mod-B']).toBeDefined();
    expect(keybindings['Mod-i']).toBeDefined();
    expect(keybindings['Mod-I']).toBeDefined();
    expect(keybindings['Mod-`']).toBeDefined();
    expect(keybindings.Tab).toBeDefined();
    expect(keybindings['Shift-Tab']).toBeDefined();

    // Call with empty options
    const keybindingsEmpty = createEditorCustomKeybindings({});
    expect(keybindingsEmpty['Mod-Shift-m']).toBeUndefined();
  });

  it('supports extensions with all surfaces, empty surfaces, and missing properties', () => {
    // Extension with no surfaces specified (applies to all)
    const unregisterAll = registerEditorExtension({
      name: 'global-extension',
    });
    expect(getRegisteredExtensions('summary').length).toBe(1);
    expect(getRegisteredExtensions('doc').length).toBe(1);

    // Extension with empty surfaces array
    const unregisterEmptySurfaces = registerEditorExtension({
      name: 'empty-surfaces-ext',
      surfaces: [],
    });
    expect(getRegisteredExtensions('summary').length).toBe(2);

    // Calling unregister twice is safe
    unregisterAll();
    unregisterAll();
    unregisterEmptySurfaces();
    expect(getRegisteredExtensions('summary').length).toBe(0);
  });

  it('creates editor nodeViews from registered extensions', () => {
    const dummyViewConstructor = vi.fn();
    const unregister = registerEditorExtension({
      name: 'mermaid-view',
      surfaces: ['doc', 'description'],
      nodeViews: () => ({
        code_block: dummyViewConstructor,
      }),
    });

    const docViews = createEditorNodeViews('doc');
    expect(docViews.code_block).toBe(dummyViewConstructor);

    const summaryViews = createEditorNodeViews('summary');
    expect(summaryViews.code_block).toBeUndefined();

    unregister();
    expect(createEditorNodeViews('doc').code_block).toBeUndefined();
  });

  it('supports extension with custom plugins', () => {
    const customPluginFactory = vi.fn(() => []);
    registerEditorExtension({
      name: 'sparkle-plugin',
      plugins: customPluginFactory,
    });

    const plugins = createEditorPlugins('comment');
    expect(customPluginFactory).toHaveBeenCalledWith({ surface: 'comment' });
    expect(plugins.length).toBeGreaterThan(0);
  });
});
