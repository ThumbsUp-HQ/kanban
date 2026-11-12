/**
 * ProseMirror Editor Surface Factory and Extension Registry (KB-P3-45, S5.1).
 * Provides extension attachment hooks for subsequent Phase 3 and Phase 5 tickets.
 */

import { type Plugin, type Command } from 'prosemirror-state';
import { type NodeViewConstructor } from 'prosemirror-view';
import { keymap } from 'prosemirror-keymap';
import { history, undo, redo } from 'prosemirror-history';
import {
  baseKeymap,
  toggleMark,
  chainCommands,
  exitCode,
} from 'prosemirror-commands';
import {
  inputRules,
  wrappingInputRule,
  textblockTypeInputRule,
  InputRule,
} from 'prosemirror-inputrules';
import { splitListItem, liftListItem, sinkListItem } from 'prosemirror-schema-list';
import { tableEditing, goToNextCell } from 'prosemirror-tables';
import { editorSchema } from './schema';
import { createSourceSlicePlugin } from './sourceSlicePlugin';

export type EditorSurfaceKind = 'summary' | 'description' | 'comment' | 'sticky' | 'doc';

export interface EditorExtensionDescriptor {
  name: string;
  surfaces?: EditorSurfaceKind[];
  plugins?: (context: { surface: EditorSurfaceKind }) => Plugin[];
  nodeViews?: (context: { surface: EditorSurfaceKind }) => Record<string, NodeViewConstructor>;
}

const registeredExtensions: EditorExtensionDescriptor[] = [];

/**
 * Registers an editor extension (e.g. paste classifier, Mermaid nodeView, Sparkle completion).
 * Returns a teardown function that unregisters the extension.
 */
export function registerEditorExtension(ext: EditorExtensionDescriptor): () => void {
  registeredExtensions.push(ext);
  return () => {
    const idx = registeredExtensions.indexOf(ext);
    if (idx !== -1) {
      registeredExtensions.splice(idx, 1);
    }
  };
}

/**
 * Returns all registered extensions applicable to the given surface kind.
 */
export function getRegisteredExtensions(surface: EditorSurfaceKind): EditorExtensionDescriptor[] {
  return registeredExtensions.filter(
    (ext) => !ext.surfaces || ext.surfaces.length === 0 || ext.surfaces.includes(surface),
  );
}

/**
 * Clears all registered extensions (for testing isolation).
 */
export function clearEditorExtensions(): void {
  registeredExtensions.length = 0;
}

export interface CreateEditorPluginsOptions {
  onToggleRaw?: () => void;
}

/**
 * Creates standard GFM input rules:
 * - `# ` through `###### ` for headings
 * - `> ` for blockquotes
 * - `- ` or `* ` for bullet lists
 * - `1. ` for ordered lists
 * - `- [ ] ` or `- [x] ` for task lists
 * - ``` for code blocks
 * - `---` for horizontal rules
 * - `**bold**` or `__bold__`
 * - `*em*` or `_em_`
 * - `~~strike~~`
 * - `code`
 */
/**
 * Creates the list of standard GFM input rules.
 */
export function buildGfmRules(): InputRule[] {
  return [
    // Headings 1..6
    textblockTypeInputRule(
      new RegExp('^(#{1,6})\\s$'),
      editorSchema.nodes.heading,
      (match) => ({ level: match[1] ? match[1].length : 1 }),
    ),
    // Blockquote
    wrappingInputRule(/^\s*>\s$/, editorSchema.nodes.blockquote),
    // Bullet list
    wrappingInputRule(/^\s*[-*]\s$/, editorSchema.nodes.bullet_list),
    // Ordered list
    wrappingInputRule(/^\s*(\d+)\.\s$/, editorSchema.nodes.ordered_list, (match) => ({
      order: match[1] ? parseInt(match[1], 10) : 1,
    })),
    // Task list items
    wrappingInputRule(/^\s*-\s*\[ \]\s$/, editorSchema.nodes.task_list, () => ({})),
    wrappingInputRule(/^\s*-\s*\[x\]\s$/, editorSchema.nodes.task_list, () => ({})),
    // Code block
    textblockTypeInputRule(
      /^```([a-z0-9_-]*)\s$/,
      editorSchema.nodes.code_block,
      (match) => ({ lang: match[1] ?? '' }),
    ),
    // Horizontal rule
    new InputRule(/^(?:---|___|\*\*\*)\s$/, (state, _match, start, end) => {
      return state.tr.replaceWith(start - 1, end, editorSchema.nodes.horizontal_rule.create());
    }),
    // Inline bold: **text**
    new InputRule(/(?:\*\*|__)([^*_]+)(?:\*\*|__)$/, (state, match, start, end) => {
      const text = match[1] ?? '';
      if (!text) return null;
      const tr = state.tr;
      tr.replaceWith(start, end, editorSchema.text(text, [editorSchema.marks.strong.create()]));
      return tr;
    }),
    // Inline italic: *text* (excluding **)
    new InputRule(/(?:^|[^*])\*([^*]+)\*$/, (state, match, start, end) => {
      const text = match[1] ?? '';
      if (!text) return null;
      const prefixOffset = match[0].startsWith('*') ? 0 : 1;
      const tr = state.tr;
      tr.replaceWith(start + prefixOffset, end, editorSchema.text(text, [editorSchema.marks.em.create()]));
      return tr;
    }),
    // Inline strike: ~~text~~
    new InputRule(/~~([^~]+)~~$/, (state, match, start, end) => {
      const text = match[1] ?? '';
      if (!text) return null;
      const tr = state.tr;
      tr.replaceWith(start, end, editorSchema.text(text, [editorSchema.marks.strike.create()]));
      return tr;
    }),
    // Inline code: `text`
    new InputRule(/(?:^|[^`])`([^`]+)`$/, (state, match, start, end) => {
      const text = match[1] ?? '';
      if (!text) return null;
      const prefixOffset = match[0].startsWith('`') ? 0 : 1;
      const tr = state.tr;
      tr.replaceWith(start + prefixOffset, end, editorSchema.text(text, [editorSchema.marks.code.create()]));
      return tr;
    }),
  ];
}

/**
 * Creates standard GFM input rules plugin.
 */
export function createGfmInputRules(): Plugin {
  return inputRules({ rules: buildGfmRules() });
}

export function createEditorCustomKeybindings(
  options?: CreateEditorPluginsOptions,
): Record<string, Command> {
  const customKeybindings: Record<string, Command> = {
    'Mod-z': undo,
    'Mod-y': redo,
    'Shift-Mod-z': redo,
    'Mod-b': toggleMark(editorSchema.marks.strong),
    'Mod-B': toggleMark(editorSchema.marks.strong),
    'Mod-i': toggleMark(editorSchema.marks.em),
    'Mod-I': toggleMark(editorSchema.marks.em),
    'Mod-`': toggleMark(editorSchema.marks.code),
    Tab: goToNextCell(1),
    'Shift-Tab': goToNextCell(-1),
  };

  if (options?.onToggleRaw) {
    const handleToggle: Command = () => {
      options.onToggleRaw?.();
      return true;
    };
    customKeybindings['Mod-Shift-m'] = handleToggle;
    customKeybindings['Mod-Shift-M'] = handleToggle;
  }

  return customKeybindings;
}

export function createEditorPlugins(
  surface: EditorSurfaceKind,
  options?: CreateEditorPluginsOptions,
): Plugin[] {
  const customKeybindings = createEditorCustomKeybindings(options);

  const listKeymap = keymap({
    Enter: splitListItem(editorSchema.nodes.list_item),
    'Mod-[': liftListItem(editorSchema.nodes.list_item),
    'Mod-]': sinkListItem(editorSchema.nodes.list_item),
  });

  const taskListKeymap = keymap({
    Enter: splitListItem(editorSchema.nodes.task_item),
    'Mod-[': liftListItem(editorSchema.nodes.task_item),
    'Mod-]': sinkListItem(editorSchema.nodes.task_item),
  });

  const codeBlockKeymap = keymap({
    'Shift-Enter': chainCommands(exitCode),
  });

  const plugins: Plugin[] = [
    createSourceSlicePlugin(),
    history(),
    keymap(customKeybindings),
    listKeymap,
    taskListKeymap,
    codeBlockKeymap,
    keymap(baseKeymap),
    tableEditing(),
    createGfmInputRules(),
  ];

  // Append plugins from registered extensions
  const extensions = getRegisteredExtensions(surface);
  for (const ext of extensions) {
    if (ext.plugins) {
      plugins.push(...ext.plugins({ surface }));
    }
  }

  return plugins;
}

/**
 * Builds the collection of NodeViews for a given editor surface.
 */
export function createEditorNodeViews(
  surface: EditorSurfaceKind,
): Record<string, NodeViewConstructor> {
  const nodeViews: Record<string, NodeViewConstructor> = {};
  const extensions = getRegisteredExtensions(surface);
  for (const ext of extensions) {
    if (ext.nodeViews) {
      Object.assign(nodeViews, ext.nodeViews({ surface }));
    }
  }
  return nodeViews;
}
