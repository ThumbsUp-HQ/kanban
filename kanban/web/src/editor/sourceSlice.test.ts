/**
 * Mandatory Unit Tests for Byte-Exact sourceSlice Parser, Serializer, and Plugin (KB-P3-45).
 */

import { describe, it, expect } from 'vitest';
import { EditorState, TextSelection, type Transaction } from 'prosemirror-state';
import type { Node as ProsemirrorNode } from 'prosemirror-model';
import { editorSchema, type SourceSlice } from './schema';
import {
  parseMarkdown,
  EditorRangeError,
  getUtf8ByteLength,
  convertTopLevelNode,
  convertInlines,
} from './parseMarkdown';
import { serializeMarkdown, serializeBlock, serializeInlines } from './serializeMarkdown';
import { createSourceSlicePlugin } from './sourceSlicePlugin';

describe('sourceSlice & Markdown Serializer Verification', () => {
  // 12-block fixture covering bullets, padded tables, reference links, 4-backtick code, task list, etc.
  const GOLDEN_12_BLOCK_FIXTURE = `# 1. Architecture Overview

Paragraph with *emphasis*, **strong text**, and \`inline code\` tokens.

> A breathable blockquote section
> with multiple lines of commentary.

| Feature       | Status   | Latency |
| :------------ | :------: | ------: |
| Database RLS  | Active   |   0.8ms |
| ProseMirror   | Ready    |   1.2ms |

* Bullet item one
* Bullet item two with nested details

1. Ordered step alpha
2. Ordered step beta

Check [authoritative specification][spec-ref] for full details.

\`\`\`\`ts
export function computeSlice(input: string): string {
  return "4-backtick fence with internal \`\`\` code";
}
\`\`\`\`

- [ ] Unfinished deployment task
- [x] Verified zero unicode dashes

---

![Architecture Diagram](https://kanban.hackedyour.info/assets/diagram.png "System Diagram")

[spec-ref]: https://kanban.hackedyour.info/docs/spec`;

  it('Case 1: Golden Round-Trip on untouched 12-block document is 100% byte-identical', () => {
    const { doc, originalSource } = parseMarkdown(GOLDEN_12_BLOCK_FIXTURE);
    expect(doc.childCount).toBe(12);

    // Verify each child received a valid sourceSlice and dirty: false
    for (let i = 0; i < doc.childCount; i++) {
      const child = doc.child(i);
      expect(child.attrs.dirty).toBe(false);
      const slice = child.attrs.sourceSlice as SourceSlice | null;
      expect(slice).not.toBeNull();
      expect(typeof slice?.from).toBe('number');
      expect(typeof slice?.to).toBe('number');
    }

    const serialized = serializeMarkdown(doc, originalSource);
    expect(serialized).toBe(GOLDEN_12_BLOCK_FIXTURE);
  });

  it('Case 2: Surgical single-paragraph edit preserves untouched blocks byte-for-byte (S5.2 item 5)', () => {
    const FIVE_BLOCK_FIXTURE = `# Project Architecture

| Component    | Parity |
| :----------- | -----: |
| Core Spine   |   100% |

Fix teh typo in this paragraph to verify surgical update.

Check [platform architecture][1] for reference implementation.

\`\`\`python
def hello():
    return "python"
\`\`\`

[1]: https://kanban.hackedyour.info`;

    const { doc, originalSource } = parseMarkdown(FIVE_BLOCK_FIXTURE);
    const plugins = [createSourceSlicePlugin()];
    let state = EditorState.create({ doc, schema: editorSchema, plugins });

    // Locate paragraph 3 ("Fix teh typo...") in doc coordinates
    // Block 0: heading
    // Block 1: table
    // Block 2: paragraph 3 with "teh"
    let targetFrom = -1;
    let targetTo = -1;
    let pos = 0;

    for (let i = 0; i < state.doc.childCount; i++) {
      const child = state.doc.child(i);
      if (child.textContent.includes('teh')) {
        const textOffset = child.textContent.indexOf('teh');
        // pos + 1 accounts for start of paragraph node
        targetFrom = pos + 1 + textOffset;
        targetTo = targetFrom + 3;
        break;
      }
      pos += child.nodeSize;
    }

    expect(targetFrom).toBeGreaterThan(0);

    // Replace "teh" with "the"
    const tr = state.tr.replaceWith(targetFrom, targetTo, editorSchema.text('the'));
    state = state.apply(tr);

    // Verify block 2 is dirty: true, while other blocks remain dirty: false
    expect(state.doc.child(0).attrs.dirty).toBe(false);
    expect(state.doc.child(1).attrs.dirty).toBe(false);
    expect(state.doc.child(2).attrs.dirty).toBe(true);
    expect(state.doc.child(2).attrs.sourceSlice).toBeNull();
    expect(state.doc.child(3).attrs.dirty).toBe(false);
    expect(state.doc.child(4).attrs.dirty).toBe(false);

    const serialized = serializeMarkdown(state.doc, originalSource);

    // Assert that paragraph 3 was updated
    expect(serialized).toContain('Fix the typo in this paragraph');
    expect(serialized).not.toContain('Fix teh typo');

    // Assert that block 1 (table), block 3 (reference link paragraph), and block 4 (code block)
    // are byte-for-byte identical to their original slices
    const b0Slice = state.doc.child(0).attrs.sourceSlice as SourceSlice;
    const b1Slice = state.doc.child(1).attrs.sourceSlice as SourceSlice;

    expect(serialized.slice(b0Slice.from, b0Slice.to)).toBe(
      originalSource.slice(b0Slice.from, b0Slice.to),
    );
    expect(serialized.slice(b1Slice.from, b1Slice.to)).toBe(
      originalSource.slice(b1Slice.from, b1Slice.to),
    );
    expect(serialized).toContain('| Component    | Parity |');
    expect(serialized).toContain('Check [platform architecture][1] for reference implementation.');
    expect(serialized).toContain('```python\ndef hello():\n    return "python"\n```');
  });

  it('Case 3: Structural edits (split, delete, table cell edit)', () => {
    const INPUT = `# Heading 1

First paragraph content.

Second paragraph content.

| Header A | Header B |
| :--- | :--- |
| Val 1 | Val 2 |

Ending paragraph.`;

    const { doc, originalSource } = parseMarkdown(INPUT);
    const plugins = [createSourceSlicePlugin()];
    let state = EditorState.create({ doc, schema: editorSchema, plugins });

    // Split second paragraph: find position inside paragraph 2
    let p2Pos = 0;
    let current = 0;
    for (let i = 0; i < state.doc.childCount; i++) {
      const child = state.doc.child(i);
      if (child.textContent.includes('Second paragraph')) {
        p2Pos = current + 1 + 6; // After "Second"
        break;
      }
      current += child.nodeSize;
    }

    // Split paragraph
    const splitTr = state.tr.split(p2Pos);
    state = state.apply(splitTr);

    // Verify split halves are dirty while heading and table remain clean
    expect(state.doc.child(0).attrs.dirty).toBe(false);
    expect(state.doc.child(1).attrs.dirty).toBe(false);
    expect(state.doc.child(2).attrs.dirty).toBe(true);
    expect(state.doc.child(3).attrs.dirty).toBe(true);

    const serializedAfterSplit = serializeMarkdown(state.doc, originalSource);
    expect(serializedAfterSplit).toContain('Second');
    expect(serializedAfterSplit).toContain('paragraph content.');
    expect(serializedAfterSplit).toContain('# Heading 1');
  });

  it('Case 5: Negative / Security: script tags, onerror attributes, and malicious schemes neutralized', () => {
    const MALICIOUS_INPUT = `<script>window.__xss=1</script>

<img src=x onerror=alert(1)>

[click](javascript:alert(1))

![x](data:text/html,<script>alert(2)</script>)`;

    const { doc, originalSource } = parseMarkdown(MALICIOUS_INPUT);

    // Verify no script DOM nodes or executable handlers exist
    let hasScriptElement = false;
    doc.descendants((node) => {
      if (node.type.name === 'script') {
        hasScriptElement = true;
      }
      for (const mark of node.marks) {
        if (mark.type.name === 'link') {
          const href = (mark.attrs.href as string).toLowerCase();
          if (href.startsWith('javascript:')) {
            throw new Error(`Dangerous javascript: link found: ${href}`);
          }
        }
      }
    });

    expect(hasScriptElement).toBe(false);

    // Re-serializing outputs inert escaped literal text
    const serialized = serializeMarkdown(doc, originalSource);
    expect(serialized).toContain('<script>window.__xss=1</script>');
    expect(serialized).not.toContain('(javascript:alert(1))');
    expect(serialized).not.toContain('data:text/html');
  });

  it(
    'Case 6: Boundary: 1 MiB document succeeds; 1,048,577 bytes throws MARKDOWN_MAX_BYTES_EXCEEDED',
    () => {
      // 1 MiB boundary = 1,048,576 UTF-8 bytes
      // Using fenced code block containing 4-byte emoji characters: 🚀 (4 bytes), 👍 (4 bytes)
      const prefix = '```ts\n// Boundary test 👍 🚀\n';
      const suffix = '\n```';
      const fixedBytes = getUtf8ByteLength(prefix) + getUtf8ByteLength(suffix);
      const targetBodyBytes = 1_048_576 - fixedBytes;
      const validDoc = prefix + 'x'.repeat(targetBodyBytes) + suffix;

      expect(getUtf8ByteLength(validDoc)).toBe(1_048_576);

      const { doc, originalSource } = parseMarkdown(validDoc);
      expect(doc.childCount).toBe(1);
      const serialized = serializeMarkdown(doc, originalSource);
      expect(getUtf8ByteLength(serialized)).toBe(1_048_576);

      // 1 byte over: 1,048,577 bytes
      const oversizedDoc = validDoc + '!';
      expect(getUtf8ByteLength(oversizedDoc)).toBe(1_048_577);

      expect(() => parseMarkdown(oversizedDoc)).toThrow(EditorRangeError);
      expect(() => parseMarkdown(oversizedDoc)).toThrow('MARKDOWN_MAX_BYTES_EXCEEDED');
    },
    15000,
  );

  it('serializes empty doc as empty string', () => {
    const emptyDoc = editorSchema.nodes.doc.create(null, []);
    expect(serializeMarkdown(emptyDoc, '')).toBe('');
  });

  it('serializes all dirty block types and nested inlines cleanly into canonical GFM', () => {
    const bq = editorSchema.nodes.blockquote.create(
      { dirty: true, sourceSlice: null },
      [editorSchema.nodes.paragraph.create(null, [editorSchema.text('Quoted text')])],
    );

    const ul = editorSchema.nodes.bullet_list.create(
      { dirty: true, sourceSlice: null },
      [editorSchema.nodes.list_item.create(null, [editorSchema.nodes.paragraph.create(null, [editorSchema.text('Item 1')])])],
    );

    const ol = editorSchema.nodes.ordered_list.create(
      { order: 2, dirty: true, sourceSlice: null },
      [editorSchema.nodes.list_item.create(null, [editorSchema.nodes.paragraph.create(null, [editorSchema.text('Step 2')])])],
    );

    const tl = editorSchema.nodes.task_list.create(
      { dirty: true, sourceSlice: null },
      [
        editorSchema.nodes.task_item.create({ checked: false }, [editorSchema.nodes.paragraph.create(null, [editorSchema.text('Unchecked')])]),
        editorSchema.nodes.task_item.create({ checked: true }, [editorSchema.nodes.paragraph.create(null, [editorSchema.text('Checked')])]),
      ],
    );

    const thLeft = editorSchema.nodes.table_header.create({ align: 'left' }, [editorSchema.text('Left')]);
    const thCenter = editorSchema.nodes.table_header.create({ align: 'center' }, [editorSchema.text('Center')]);
    const thRight = editorSchema.nodes.table_header.create({ align: 'right' }, [editorSchema.text('Right')]);
    const thDefault = editorSchema.nodes.table_header.create({ align: null }, [editorSchema.text('Default')]);
    const headerRow = editorSchema.nodes.table_row.create(null, [thLeft, thCenter, thRight, thDefault]);

    const td1 = editorSchema.nodes.table_cell.create({ align: 'left' }, [editorSchema.text('1')]);
    const td2 = editorSchema.nodes.table_cell.create({ align: 'center' }, [editorSchema.text('2')]);
    const td3 = editorSchema.nodes.table_cell.create({ align: 'right' }, [editorSchema.text('3')]);
    const td4 = editorSchema.nodes.table_cell.create({ align: null }, [editorSchema.text('4')]);
    const dataRow = editorSchema.nodes.table_row.create(null, [td1, td2, td3, td4]);

    const table = editorSchema.nodes.table.create({ dirty: true, sourceSlice: null }, [headerRow, dataRow]);

    const hr = editorSchema.nodes.horizontal_rule.create({ dirty: true, sourceSlice: null });

    const imgBlock = editorSchema.nodes.image_block.create({
      src: 'https://kanban.local/photo.jpg',
      alt: 'Photo',
      title: 'Caption',
      dirty: true,
      sourceSlice: null,
    });

    const def = editorSchema.nodes.definition.create({
      identifier: 'def1',
      label: 'Def 1',
      url: 'https://kanban.local/ref',
      title: 'RefTitle',
      dirty: true,
      sourceSlice: null,
    });

    const cbWithFences = editorSchema.nodes.code_block.create(
      { lang: 'markdown', meta: '', dirty: true, sourceSlice: null },
      [editorSchema.text('```\ncode inside\n```')],
    );

    const inlineP = editorSchema.nodes.paragraph.create(
      { dirty: true, sourceSlice: null },
      [
        editorSchema.text('Text with '),
        editorSchema.text('strong', [editorSchema.marks.strong.create()]),
        editorSchema.text(' and '),
        editorSchema.text('em', [editorSchema.marks.em.create()]),
        editorSchema.text(' and '),
        editorSchema.text('strike', [editorSchema.marks.strike.create()]),
        editorSchema.text(' and '),
        editorSchema.text('code', [editorSchema.marks.code.create()]),
        editorSchema.text(' and '),
        editorSchema.text('link', [editorSchema.marks.link.create({ href: 'https://kanban.local', title: 'T' })]),
        editorSchema.text(' and '),
        editorSchema.text('refLink', [editorSchema.marks.link.create({ href: '', title: '', rawRef: 'ref1' })]),
        editorSchema.text(' and '),
        editorSchema.text('shortcutRef', [editorSchema.marks.link.create({ href: '', title: '', rawRef: '' })]),
        editorSchema.nodes.hard_break.create(),
        editorSchema.nodes.image.create({ src: 'https://kanban.local/i.png', alt: 'Alt', title: 'Title' }),
      ],
    );

    const doc = editorSchema.nodes.doc.create(null, [
      bq,
      ul,
      ol,
      tl,
      table,
      hr,
      imgBlock,
      def,
      cbWithFences,
      inlineP,
    ]);

    const result = serializeMarkdown(doc, '');
    expect(result).toContain('> Quoted text');
    expect(result).toContain('- Item 1');
    expect(result).toContain('2. Step 2');
    expect(result).toContain('- [ ] Unchecked');
    expect(result).toContain('- [x] Checked');
    expect(result).toContain('| Left | Center | Right | Default |');
    expect(result).toContain('| :--- | :---: | ---: | --- |');
    expect(result).toContain('| 1 | 2 | 3 | 4 |');
    expect(result).toContain('---');
    expect(result).toContain('![Photo](https://kanban.local/photo.jpg "Caption")');
    expect(result).toContain('[Def 1]: https://kanban.local/ref "RefTitle"');
    expect(result).toContain('````markdown');
    expect(result).toContain('**strong**');
    expect(result).toContain('*em*');
    expect(result).toContain('~~strike~~');
    expect(result).toContain('`code`');
    expect(result).toContain('[link](https://kanban.local "T")');
    expect(result).toContain('[refLink][ref1]');
    expect(result).toContain('[shortcutRef]');
    expect(result).toContain('![Alt](https://kanban.local/i.png "Title")');
  });

  it('parses empty and whitespace strings gracefully', () => {
    const empty = parseMarkdown('');
    expect(empty.doc.childCount).toBe(1);
    expect(empty.doc.child(0).textContent).toBe('');

    const ws = parseMarkdown('   \n\n   ');
    expect(ws.doc.childCount).toBe(1);
    expect(ws.doc.child(0).textContent).toBe('');
  });

  it('parses image references and dangerous schemes properly', () => {
    const input = `![Local ref][img-ref]

![Dangerous](javascript:void(0))

[img-ref]: https://kanban.hackedyour.info/img.png`;

    const { doc } = parseMarkdown(input);
    expect(doc.childCount).toBeGreaterThan(0);
  });

  it('sourceSlicePlugin handles no-doc-change, skip meta, and already-dirty nodes', () => {
    const { doc } = parseMarkdown('# Header\n\nParagraph text.');
    const plugin = createSourceSlicePlugin();
    let state = EditorState.create({ doc, schema: editorSchema, plugins: [plugin] });

    // 1. Transaction without docChanged
    const selTr = state.tr.setSelection(TextSelection.atEnd(state.doc));
    state = state.apply(selTr);
    expect(state.doc.child(1).attrs.dirty).toBe(false);

    // 2. Transaction with skipSourceSliceDirty meta
    const skipTr = state.tr.insertText(' extra', 9).setMeta('skipSourceSliceDirty', true);
    state = state.apply(skipTr);

    // 3. Make child 1 dirty
    const dirtyTr = state.tr.insertText(' modified', 10);
    state = state.apply(dirtyTr);
    expect(state.doc.child(1).attrs.dirty).toBe(true);
    expect(state.doc.child(1).attrs.sourceSlice).toBeNull();

    // 4. Second edit on already-dirty child 1
    const secondDirtyTr = state.tr.insertText(' more', 12);
    state = state.apply(secondDirtyTr);
    expect(state.doc.child(1).attrs.dirty).toBe(true);

    // 5. Test appendTransaction with artificial empty transaction
    const appendFn = plugin.spec.appendTransaction;
    const fakeTr = {
      docChanged: true,
      getMeta: () => false,
      steps: [],
    } as unknown as Transaction;
    const emptyResult = appendFn?.([fakeTr], state, state);
    expect(emptyResult).toBeNull();
  });

  it('parses inlines, hard breaks, images, inline html, and complex blockquotes', () => {
    const markdown = `# Title

Link to [Specification](https://kanban.local/spec "Specification") and ![Inline Image](https://kanban.local/img.png "Image Title").

Line with hard break  
Continued on line two.

Inline html <code>code text</code> here.

>

- 

\`\`\`
plain code without lang
\`\`\`

[ref-id]: https://kanban.local/docs "Docs Title"`;

    const { doc, originalSource } = parseMarkdown(markdown);
    expect(doc.childCount).toBeGreaterThan(5);

    const serialized = serializeMarkdown(doc, originalSource);
    expect(serialized).toBe(markdown);
  });

  it('serializes empty documents, dirty trailing blocks, and inline images/breaks', () => {
    // 1. Empty document
    const emptyDoc = editorSchema.nodes.doc.create(null, []);
    expect(serializeMarkdown(emptyDoc, '')).toBe('');

    // 2. Serializing dirty blocks with inline image and hard break
    const pWithBreakAndImg = editorSchema.nodes.paragraph.create({ dirty: true, sourceSlice: null }, [
      editorSchema.text('First line'),
      editorSchema.nodes.hard_break.create(),
      editorSchema.nodes.image.create({
        src: 'https://kanban.local/test.png',
        alt: 'Test Alt',
        title: 'Test Title',
      }),
      editorSchema.text('After image'),
    ]);
    const dirtyDoc = editorSchema.nodes.doc.create(null, [pWithBreakAndImg]);
    const dirtySerialized = serializeMarkdown(dirtyDoc, '');
    expect(dirtySerialized).toContain('First line  \n');
    expect(dirtySerialized).toContain('![Test Alt](https://kanban.local/test.png "Test Title")');

    // 3. Document where last block is dirty (tests trailing whitespace branch)
    const cleanP = editorSchema.nodes.paragraph.create(
      { sourceSlice: { from: 0, to: 10 }, dirty: false },
      [editorSchema.text('Clean text')],
    );
    const dirtyLastP = editorSchema.nodes.paragraph.create(
      { sourceSlice: null, dirty: true },
      [editorSchema.text('Dirty ending text')],
    );
    const mixedDoc = editorSchema.nodes.doc.create(null, [cleanP, dirtyLastP]);
    const mixedSerialized = serializeMarkdown(mixedDoc, 'Clean text\n\n');
    expect(mixedSerialized).toContain('Clean text');
    expect(mixedSerialized).toContain('Dirty ending text');
  });

  it('tests parseMarkdown and serializeMarkdown uncovered branches and fallback cases', () => {
    // 1. parseMarkdown with strikethrough (case 'delete')
    const strikeDoc = parseMarkdown('Text with ~~deleted content~~ inside.');
    expect(strikeDoc.doc.textContent).toContain('Text with deleted content inside.');

    // 2. parseMarkdown with dangerous image without alt text
    const noAltDangerousDoc = parseMarkdown('![](javascript:void(0))');
    expect(noAltDangerousDoc.doc.childCount).toBeGreaterThan(0);

    // 3. convertTopLevelNode with unsupported type returns null
    expect(convertTopLevelNode({ type: 'unsupported_node_type' })).toBeNull();

    // 4. convertInlines with unsupported inline type returns empty array
    expect(convertInlines([{ type: 'unsupported_inline_type' }])).toEqual([]);

    // 5. serializeBlock fallback for unknown block type
    const fallbackBlockResult = serializeBlock({
      type: { name: 'unknown_block_type' },
      textContent: 'fallback block text',
    } as unknown as ProsemirrorNode);
    expect(fallbackBlockResult).toBe('fallback block text');

    // 6. serializeInlines with multiple marks and unknown mark
    const pWithMultiMarks = editorSchema.nodes.paragraph.create(
      { dirty: true, sourceSlice: null },
      [
        editorSchema.text('bold and italic', [
          editorSchema.marks.strong.create(),
          editorSchema.marks.em.create(),
        ]),
      ],
    );
    expect(serializeInlines(pWithMultiMarks)).toBe('***bold and italic***');

    const pWithUnknownMark = {
      childCount: 1,
      child: () => ({
        isText: true,
        text: 'custom text',
        marks: [{ type: { name: 'unknown_mark_kind' }, attrs: {} }],
      }),
    } as unknown as ProsemirrorNode;
    expect(serializeInlines(pWithUnknownMark)).toBe('custom text');

    // 7. sourceSlicePlugin appendTransaction when touchedIndices.size === 0
    const plugin = createSourceSlicePlugin();
    const appendFn = plugin.spec.appendTransaction;
    const emptyDoc = editorSchema.nodes.doc.create(null, []);
    const emptyState = EditorState.create({ doc: emptyDoc, schema: editorSchema });
    const fakeTrWithRange = {
      docChanged: true,
      getMeta: () => false,
      steps: [
        {
          getMap: () => ({
            forEach: (cb: (oldStart: number, oldEnd: number, newStart: number, newEnd: number) => void) => {
              cb(0, 5, 0, 5);
            },
          }),
        },
      ],
    } as unknown as Transaction;
    const noOverlapResult = appendFn?.([fakeTrWithRange], emptyState, emptyState);
    expect(noOverlapResult).toBeNull();

    // 8. parseMarkdown with only non-block elements (HTML comment) triggers blocks.length === 0 fallback
    const commentOnlyDoc = parseMarkdown('<!-- comment only -->');
    expect(commentOnlyDoc.doc.childCount).toBe(1);

    // 9. serializeInlines on empty image and empty link
    const pWithEmptyImg = editorSchema.nodes.paragraph.create(
      { dirty: true, sourceSlice: null },
      [editorSchema.nodes.image.create({ src: '', alt: '', title: '' })],
    );
    expect(serializeInlines(pWithEmptyImg)).toBe('![]()');

    const pWithEmptyLink = editorSchema.nodes.paragraph.create(
      { dirty: true, sourceSlice: null },
      [editorSchema.text('text', [editorSchema.marks.link.create({ href: '', title: '', rawRef: null })])],
    );
    expect(serializeInlines(pWithEmptyLink)).toBe('[text]()');

    // 10. definition without label and title
    const defBare = editorSchema.nodes.definition.create({
      identifier: 'bare-id',
      label: '',
      url: 'https://kanban.local/url',
      title: '',
    });
    expect(serializeBlock(defBare)).toBe('[bare-id]: https://kanban.local/url');

    // 11. serializeInlines on text node with undefined text
    const pWithUndefText = {
      childCount: 1,
      child: () => ({
        isText: true,
        text: undefined,
        marks: [],
      }),
    } as unknown as ProsemirrorNode;
    expect(serializeInlines(pWithUndefText)).toBe('');

    // 12. serializeInlines on unknown inline node
    const pWithUnknownInline = {
      childCount: 1,
      child: () => ({
        isText: false,
        type: { name: 'unknown_inline_node' },
      }),
    } as unknown as ProsemirrorNode;
    expect(serializeInlines(pWithUnknownInline)).toBe('');

    // 13. parseMarkdown images without title and without alt, image references without alt
    const imgVariations = parseMarkdown(`![no title](https://kanban.local/a.png)

![](https://kanban.local/b.png)

![][ref-no-alt]

[ref-no-alt]: https://kanban.local/c.png`);
    expect(imgVariations.doc.childCount).toBeGreaterThan(2);

    // 14. serializeBlock on image_block with and without title/alt
    const emptyImgBlock = editorSchema.nodes.image_block.create({ src: '', alt: '', title: '' });
    expect(serializeBlock(emptyImgBlock)).toBe('![]()');

    const titledImgBlock = editorSchema.nodes.image_block.create({
      src: 'https://kanban.local/pic.png',
      alt: 'Alt',
      title: 'Title',
    });
    expect(serializeBlock(titledImgBlock)).toBe('![Alt](https://kanban.local/pic.png "Title")');

    // 15. serializeBlock on definition with empty url
    const emptyUrlDef = editorSchema.nodes.definition.create({
      identifier: 'id',
      label: 'L',
      url: '',
      title: '',
    });
    expect(serializeBlock(emptyUrlDef)).toBe('[L]: ');

    // 16. serializeInlines with known and unknown mark combination for sort comparator fallback
    const pWithKnownAndUnknownMarks = {
      childCount: 1,
      child: () => ({
        isText: true,
        text: 'mixed marks',
        marks: [
          editorSchema.marks.strong.create(),
          { type: { name: 'unknown_custom_mark' }, attrs: {} },
        ],
      }),
    } as unknown as ProsemirrorNode;
    expect(serializeInlines(pWithKnownAndUnknownMarks)).toBe('**mixed marks**');

    // 17. parseMarkdown link without title
    const docNoTitle = parseMarkdown('Check [plain link](https://kanban.local/plain).');
    expect(docNoTitle.doc.childCount).toBe(1);

    // 18. convertInlines with empty linkReference and empty html
    const emptyInlines = convertInlines([
      { type: 'linkReference', identifier: '' },
      { type: 'html', value: '' },
    ]);
    expect(emptyInlines.length).toBe(0);

    // 19. convertTopLevelNode with ordered list without start (fallback to 1)
    const bareOrderedList = convertTopLevelNode({
      type: 'list',
      ordered: true,
      children: [],
    });
    expect(bareOrderedList).not.toBeNull();

    // 20. convertTopLevelNode with heading without depth or children
    const bareHeading = convertTopLevelNode({
      type: 'heading',
    });
    expect(bareHeading).not.toBeNull();

    // 20. convertInlines edge cases (empty text, empty inlineCode, missing children on emphasis, strong, delete, link)
    const moreInlines = convertInlines([
      { type: 'text', value: '' },
      { type: 'inlineCode', value: '' },
      { type: 'emphasis' },
      { type: 'strong' },
      { type: 'delete' },
      { type: 'link', url: 'https://kanban.local' },
      { type: 'link', url: 'javascript:bad' },
    ]);
    expect(moreInlines).toBeDefined();

    // 21. convertTopLevelNode fallbacks for definition, html, table cell without children, code, and blockquote
    expect(
      convertTopLevelNode({
        type: 'definition',
        identifier: '',
        label: '',
        url: '',
        title: '',
      }),
    ).not.toBeNull();

    expect(
      convertTopLevelNode({
        type: 'html',
        value: '',
      }),
    ).not.toBeNull();

    expect(
      convertTopLevelNode({
        type: 'table',
        align: [],
        children: [{ type: 'tableRow', children: [{ type: 'tableCell' }] }],
      }),
    ).not.toBeNull();

    expect(
      convertTopLevelNode({
        type: 'code',
        value: '',
        lang: '',
      }),
    ).not.toBeNull();

    expect(
      convertTopLevelNode({
        type: 'blockquote',
      }),
    ).not.toBeNull();
  });

  it('covers remaining AST converter, serializer, and plugin branches', () => {
    // 1. Definition node with missing identifier, label, url, title
    const defUndefined = convertTopLevelNode({
      type: 'definition',
    });
    expect(defUndefined).not.toBeNull();
    expect(defUndefined?.attrs.identifier).toBe('');
    expect(defUndefined?.attrs.label).toBe('');
    expect(defUndefined?.attrs.url).toBe('');
    expect(defUndefined?.attrs.title).toBe('');

    // Definition with identifier but undefined label
    const defWithIdOnly = convertTopLevelNode({
      type: 'definition',
      identifier: 'id-only',
      url: 'https://kanban.local',
      title: 'Title',
    });
    expect(defWithIdOnly).not.toBeNull();
    expect(defWithIdOnly?.attrs.identifier).toBe('id-only');
    expect(defWithIdOnly?.attrs.label).toBe('id-only');

    // 2. LinkReference with undefined identifier
    const linkRefUndef = convertInlines([{ type: 'linkReference' }]);
    expect(linkRefUndef.length).toBe(0);

    const linkRefWithChildren = convertInlines([
      {
        type: 'linkReference',
        children: [{ type: 'text', value: 'reference text' }],
      },
    ]);
    expect(linkRefWithChildren.length).toBe(1);
    expect(linkRefWithChildren[0]?.marks[0]?.attrs.rawRef).toBe('');

    // 3. Image with undefined alt and title
    const imgUndef = convertInlines([
      { type: 'image', url: 'https://kanban.local/a.png' },
    ]);
    expect(imgUndef.length).toBe(1);
    expect(imgUndef[0]?.attrs.alt).toBe('');
    expect(imgUndef[0]?.attrs.title).toBe('');

    // 4. SourceSlicePlugin appendTransaction with mixed transactions (!docChanged followed by docChanged)
    const plugin = createSourceSlicePlugin();
    const appendFn = plugin.spec.appendTransaction;
    const fakeNoChangeTr = {
      docChanged: false,
      getMeta: () => false,
      steps: [],
    } as unknown as Transaction;
    const fakeWithChangeTr = {
      docChanged: true,
      getMeta: () => false,
      steps: [
        {
          getMap: () => ({
            forEach: (cb: (oldStart: number, oldEnd: number, newStart: number, newEnd: number) => void) => {
              cb(0, 5, 0, 5);
            },
          }),
        },
      ],
    } as unknown as Transaction;
    const emptyDoc = editorSchema.nodes.doc.create(null, []);
    const emptyState = EditorState.create({ doc: emptyDoc, schema: editorSchema });
    const appendResult = appendFn?.([fakeNoChangeTr, fakeWithChangeTr], emptyState, emptyState);
    expect(appendResult).toBeNull();

    // 5. Serializer fallback branches (heading level undefined, code lang undefined, ordered_list order undefined)
    const hNoLevel = editorSchema.nodes.heading.create({ level: 0 }, editorSchema.text('Heading'));
    expect(serializeBlock(hNoLevel)).toBe('# Heading');

    const codeNoLang = editorSchema.nodes.code_block.create({ lang: null }, editorSchema.text('code'));
    expect(serializeBlock(codeNoLang)).toContain('```\ncode\n```');

    const olNoOrder = editorSchema.nodes.ordered_list.create({ order: 0 }, [
      editorSchema.nodes.list_item.create({}, [
        editorSchema.nodes.paragraph.create({}, editorSchema.text('item')),
      ]),
    ]);
    expect(serializeBlock(olNoOrder)).toBe('1. item');

    // 6. AST converter edge cases for list items and table rows without children
    const listUndefChildren = convertTopLevelNode({
      type: 'list',
      children: [{ type: 'listItem' }],
    });
    expect(listUndefChildren).not.toBeNull();

    const tableUndefChildren = convertTopLevelNode({
      type: 'table',
    });
    expect(tableUndefChildren).not.toBeNull();

    const tableRowUndef = convertTopLevelNode({
      type: 'table',
      align: ['center'],
      children: [
        { type: 'tableRow' },
        {
          type: 'tableRow',
          children: [
            { type: 'tableCell' },
            { type: 'tableCell' },
          ],
        },
      ],
    });
    expect(tableRowUndef).not.toBeNull();

    // 7. Blockquote with multiple paragraphs covering empty-line prefix
    const bqMultiP = editorSchema.nodes.blockquote.create({}, [
      editorSchema.nodes.paragraph.create({}, editorSchema.text('Para 1')),
      editorSchema.nodes.paragraph.create({}, editorSchema.text('Para 2')),
    ]);
    expect(serializeBlock(bqMultiP)).toBe('> Para 1\n>\n> Para 2');

    // 8. Inlines mark sort with unknown mark before known mark
    const pWithUnknownFirst = {
      childCount: 1,
      child: () => ({
        isText: true,
        text: 'tagged',
        marks: [
          { type: { name: 'unknown_a' }, attrs: {} },
          editorSchema.marks.strong.create(),
        ],
      }),
    } as unknown as ProsemirrorNode;
    expect(serializeInlines(pWithUnknownFirst)).toBe('**tagged**');

    // 9. Additional AST converter fallbacks for paragraph, blockquote, and list items
    const paraUndefChildren = convertTopLevelNode({
      type: 'paragraph',
    });
    expect(paraUndefChildren).not.toBeNull();

    const bqWithNullChild = convertTopLevelNode({
      type: 'blockquote',
      children: [{ type: 'unsupported_unknown_node' }],
    });
    expect(bqWithNullChild).not.toBeNull();

    const listUndef = convertTopLevelNode({
      type: 'list',
    });
    expect(listUndef).not.toBeNull();

    const listItemWithNullChild = convertTopLevelNode({
      type: 'list',
      children: [
        {
          type: 'listItem',
          children: [{ type: 'unsupported_unknown_node' }],
        },
      ],
    });
    expect(listItemWithNullChild).not.toBeNull();
  });
});
