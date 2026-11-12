/**
 * Unit Tests for ProseMirror GFM Schema, toDOM, getAttrs, and URI Sanitization (KB-P3-45).
 */

import { describe, it, expect } from 'vitest';
import {
  editorSchema,
  isAllowedUri,
  sanitizeUri,
} from './schema';

interface CustomParseRule {
  getAttrs?: (node: HTMLElement | string) => unknown;
}

describe('schema.ts URI Allowlist & Sanitization', () => {
  it('allows valid https, http, mailto, relative, anchor, and attachment schemes', () => {
    expect(isAllowedUri('https://example.com/api')).toBe(true);
    expect(isAllowedUri('http://127.0.0.1:8000')).toBe(true);
    expect(isAllowedUri('mailto:admin@example.com')).toBe(true);
    expect(isAllowedUri('#section-heading')).toBe(true);
    expect(isAllowedUri('/projects/kan/issues/123')).toBe(true);
    expect(isAllowedUri('attachment://att_0196abc')).toBe(true);
  });

  it('rejects dangerous and disallowed schemes', () => {
    expect(isAllowedUri('javascript:alert(1)')).toBe(false);
    expect(isAllowedUri('JAVASCRIPT:alert(document.cookie)')).toBe(false);
    expect(isAllowedUri('vbscript:msgbox(1)')).toBe(false);
    expect(isAllowedUri('data:text/html,<script>alert(1)</script>')).toBe(false);
    expect(isAllowedUri('file:///etc/passwd')).toBe(false);
    expect(isAllowedUri('//evil.example.com/payload')).toBe(false);
    expect(isAllowedUri('')).toBe(false);
    expect(isAllowedUri(null)).toBe(false);
    expect(isAllowedUri(undefined)).toBe(false);
  });

  it('sanitizeUri returns trimmed URI or null', () => {
    expect(sanitizeUri('  https://kanban.local  ')).toBe('https://kanban.local');
    expect(sanitizeUri('javascript:void(0)')).toBeNull();
    expect(sanitizeUri(null)).toBeNull();
    expect(sanitizeUri('')).toBeNull();
  });
});

describe('schema.ts Node Spec toDOM and getAttrs', () => {
  it('tests paragraph toDOM', () => {
    const p = editorSchema.nodes.paragraph.create();
    expect(p.type.spec.toDOM?.(p)).toEqual(['p', 0]);
  });

  it('tests heading toDOM', () => {
    for (let level = 1; level <= 6; level++) {
      const h = editorSchema.nodes.heading.create({ level });
      expect(h.type.spec.toDOM?.(h)).toEqual([`h${String(level)}`, 0]);
    }
  });

  it('tests code_block toDOM and parseDOM getAttrs', () => {
    const cb = editorSchema.nodes.code_block.create({ lang: 'python' });
    expect(cb.type.spec.toDOM?.(cb)).toEqual([
      'pre',
      { class: 'kb-code-block' },
      ['code', { class: 'language-python' }, 0],
    ]);

    const cbNoLang = editorSchema.nodes.code_block.create({ lang: '' });
    expect(cbNoLang.type.spec.toDOM?.(cbNoLang)).toEqual([
      'pre',
      { class: 'kb-code-block' },
      ['code', { class: undefined }, 0],
    ]);

    const parseSpec = editorSchema.nodes.code_block.spec.parseDOM?.[0];
    const dummyEl = document.createElement('pre');
    const codeEl = document.createElement('code');
    codeEl.className = 'language-typescript';
    dummyEl.appendChild(codeEl);
    expect(parseSpec?.getAttrs?.(dummyEl)).toEqual({ lang: 'typescript' });

    const dummyEl2 = document.createElement('pre');
    dummyEl2.className = 'language-rust';
    expect(parseSpec?.getAttrs?.(dummyEl2)).toEqual({ lang: 'rust' });

    const dummyEl3 = document.createElement('pre');
    expect(parseSpec?.getAttrs?.(dummyEl3)).toEqual({ lang: '' });
  });

  it('tests blockquote toDOM', () => {
    const bq = editorSchema.nodes.blockquote.create();
    expect(bq.type.spec.toDOM?.(bq)).toEqual(['blockquote', 0]);
  });

  it('tests bullet_list toDOM', () => {
    const bl = editorSchema.nodes.bullet_list.create();
    expect(bl.type.spec.toDOM?.(bl)).toEqual(['ul', 0]);
  });

  it('tests ordered_list toDOM and getAttrs', () => {
    const ol1 = editorSchema.nodes.ordered_list.create({ order: 1 });
    expect(ol1.type.spec.toDOM?.(ol1)).toEqual(['ol', 0]);

    const ol5 = editorSchema.nodes.ordered_list.create({ order: 5 });
    expect(ol5.type.spec.toDOM?.(ol5)).toEqual(['ol', { start: 5 }, 0]);

    const parseSpec = editorSchema.nodes.ordered_list.spec.parseDOM?.[0];
    const el = document.createElement('ol');
    el.setAttribute('start', '3');
    expect(parseSpec?.getAttrs?.(el)).toEqual({ order: 3 });

    const elInvalid = document.createElement('ol');
    elInvalid.setAttribute('start', 'invalid');
    expect(parseSpec?.getAttrs?.(elInvalid)).toEqual({ order: 1 });
  });

  it('tests list_item toDOM', () => {
    const li = editorSchema.nodes.list_item.create();
    expect(li.type.spec.toDOM?.(li)).toEqual(['li', 0]);
  });

  it('tests task_list and task_item toDOM and getAttrs', () => {
    const tl = editorSchema.nodes.task_list.create();
    expect(tl.type.spec.toDOM?.(tl)).toEqual([
      'ul',
      { 'data-task-list': 'true', class: 'kb-task-list' },
      0,
    ]);

    const tiChecked = editorSchema.nodes.task_item.create({ checked: true });
    expect(tiChecked.type.spec.toDOM?.(tiChecked)).toEqual([
      'li',
      { 'data-task-item': 'true', class: 'kb-task-item is-checked' },
      [
        'input',
        {
          type: 'checkbox',
          class: 'kb-task-checkbox',
          disabled: 'disabled',
          checked: 'checked',
        },
      ],
      ['div', { class: 'kb-task-item__content' }, 0],
    ]);

    const tiUnchecked = editorSchema.nodes.task_item.create({ checked: false });
    expect(tiUnchecked.type.spec.toDOM?.(tiUnchecked)).toEqual([
      'li',
      { 'data-task-item': 'true', class: 'kb-task-item' },
      [
        'input',
        {
          type: 'checkbox',
          class: 'kb-task-checkbox',
          disabled: 'disabled',
          checked: undefined,
        },
      ],
      ['div', { class: 'kb-task-item__content' }, 0],
    ]);

    const parseSpec = editorSchema.nodes.task_item.spec.parseDOM?.[0];
    const liEl = document.createElement('li');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = true;
    liEl.appendChild(input);
    expect(parseSpec?.getAttrs?.(liEl)).toEqual({ checked: true });

    const liElEmpty = document.createElement('li');
    expect(parseSpec?.getAttrs?.(liElEmpty)).toEqual({ checked: false });
  });

  it('tests table, table_row, table_header, table_cell toDOM and getAttrs', () => {
    const table = editorSchema.nodes.table.create();
    expect(table.type.spec.toDOM?.(table)).toEqual(['table', { class: 'kb-table' }, ['tbody', 0]]);

    const tr = editorSchema.nodes.table_row.create();
    expect(tr.type.spec.toDOM?.(tr)).toEqual(['tr', 0]);

    const thCenter = editorSchema.nodes.table_header.create({ align: 'center' });
    expect(thCenter.type.spec.toDOM?.(thCenter)).toEqual([
      'th',
      { align: 'center', 'data-align': 'center' },
      0,
    ]);

    const thNull = editorSchema.nodes.table_header.create({ align: null });
    expect(thNull.type.spec.toDOM?.(thNull)).toEqual(['th', {}, 0]);

    const tdRight = editorSchema.nodes.table_cell.create({ align: 'right' });
    expect(tdRight.type.spec.toDOM?.(tdRight)).toEqual([
      'td',
      { align: 'right', 'data-align': 'right' },
      0,
    ]);

    const tdNull = editorSchema.nodes.table_cell.create({ align: null });
    expect(tdNull.type.spec.toDOM?.(tdNull)).toEqual(['td', {}, 0]);

    // getAttrs
    const thParse = editorSchema.nodes.table_header.spec.parseDOM?.[0];
    const thEl = document.createElement('th');
    thEl.setAttribute('align', 'center');
    expect(thParse?.getAttrs?.(thEl)).toEqual({ align: 'center' });

    const tdParse = editorSchema.nodes.table_cell.spec.parseDOM?.[0];
    const tdEl = document.createElement('td');
    tdEl.style.textAlign = 'right';
    expect(tdParse?.getAttrs?.(tdEl)).toEqual({ align: 'right' });
  });

  it('tests horizontal_rule toDOM', () => {
    const hr = editorSchema.nodes.horizontal_rule.create();
    expect(hr.type.spec.toDOM?.(hr)).toEqual(['hr', { class: 'kb-hr' }]);
  });

  it('tests image_block toDOM and parseDOM getAttrs', () => {
    const imgBlock = editorSchema.nodes.image_block.create({
      src: 'https://kanban.local/pic.png',
      alt: 'Pic',
      title: 'Title',
    });
    expect(imgBlock.type.spec.toDOM?.(imgBlock)).toEqual([
      'div',
      { 'data-image-block': 'true', class: 'kb-editor__image-block' },
      ['img', { src: 'https://kanban.local/pic.png', alt: 'Pic', title: 'Title' }],
    ]);

    const parseSpec = editorSchema.nodes.image_block.spec.parseDOM?.[0];
    const container = document.createElement('div');
    const imgEl = document.createElement('img');
    imgEl.setAttribute('src', 'https://kanban.local/img.png');
    imgEl.setAttribute('alt', 'Alt');
    imgEl.setAttribute('title', 'T');
    container.appendChild(imgEl);
    expect(parseSpec?.getAttrs?.(container)).toEqual({
      src: 'https://kanban.local/img.png',
      alt: 'Alt',
      title: 'T',
    });

    const emptyContainer = document.createElement('div');
    expect(parseSpec?.getAttrs?.(emptyContainer)).toEqual({
      src: '',
      alt: '',
      title: '',
    });
  });

  it('tests definition toDOM and parseDOM getAttrs', () => {
    const def = editorSchema.nodes.definition.create({
      identifier: 'ref1',
      label: 'Ref One',
      url: 'https://example.com',
      title: 'Title',
    });
    expect(def.type.spec.toDOM?.(def)).toEqual([
      'div',
      {
        class: 'kb-editor__definition',
        'data-definition': 'ref1',
        'data-label': 'Ref One',
        'data-url': 'https://example.com',
        'data-title': 'Title',
      },
      '[Ref One]: https://example.com',
    ]);

    const parseSpec = editorSchema.nodes.definition.spec.parseDOM?.[0];
    const el = document.createElement('div');
    el.setAttribute('data-definition', 'd1');
    el.setAttribute('data-label', 'Label1');
    el.setAttribute('data-url', 'https://kanban.local');
    el.setAttribute('data-title', 'T1');
    expect(parseSpec?.getAttrs?.(el)).toEqual({
      identifier: 'd1',
      label: 'Label1',
      url: 'https://kanban.local',
      title: 'T1',
    });
  });

  it('tests inline image and hard_break toDOM and getAttrs', () => {
    const hb = editorSchema.nodes.hard_break.create();
    expect(hb.type.spec.toDOM?.(hb)).toEqual(['br']);

    const img = editorSchema.nodes.image.create({
      src: 'https://kanban.local/icon.svg',
      alt: 'Icon',
      title: 'IconTitle',
    });
    expect(img.type.spec.toDOM?.(img)).toEqual([
      'img',
      {
        src: 'https://kanban.local/icon.svg',
        alt: 'Icon',
        title: 'IconTitle',
        class: 'kb-inline-image',
      },
    ]);

    const parseSpec = editorSchema.nodes.image.spec.parseDOM?.[0];
    const imgEl = document.createElement('img');
    imgEl.setAttribute('src', 'https://kanban.local/i.png');
    imgEl.setAttribute('alt', 'A');
    imgEl.setAttribute('title', 'T');
    expect(parseSpec?.getAttrs?.(imgEl)).toEqual({
      src: 'https://kanban.local/i.png',
      alt: 'A',
      title: 'T',
    });
  });

  it('tests marks toDOM and getAttrs', () => {
    const strongM = editorSchema.marks.strong.create();
    expect(strongM.type.spec.toDOM?.(strongM, true)).toEqual(['strong', 0]);

    const emM = editorSchema.marks.em.create();
    expect(emM.type.spec.toDOM?.(emM, true)).toEqual(['em', 0]);

    const strikeM = editorSchema.marks.strike.create();
    expect(strikeM.type.spec.toDOM?.(strikeM, true)).toEqual(['s', 0]);

    const codeM = editorSchema.marks.code.create();
    expect(codeM.type.spec.toDOM?.(codeM, true)).toEqual([
      'code',
      { class: 'kb-inline-code' },
      0,
    ]);

    const link = editorSchema.marks.link.create({
      href: 'https://kanban.local',
      title: 'Title',
      rawRef: '1',
    });
    expect(link.type.spec.toDOM?.(link, true)).toEqual([
      'a',
      {
        href: 'https://kanban.local',
        title: 'Title',
        'data-raw-ref': '1',
        class: 'kb-link',
        rel: 'noopener noreferrer',
      },
      0,
    ]);

    const linkParse = editorSchema.marks.link.spec.parseDOM?.[0] as CustomParseRule | undefined;
    const aEl = document.createElement('a');
    aEl.setAttribute('href', 'https://kanban.local');
    aEl.setAttribute('title', 'Home');
    aEl.setAttribute('data-raw-ref', 'r1');
    expect(linkParse?.getAttrs?.(aEl)).toEqual({
      href: 'https://kanban.local',
      title: 'Home',
      rawRef: 'r1',
    });

    // Test strong mark font-weight parseDOM getAttrs
    const strongParseRule = editorSchema.marks.strong.spec.parseDOM?.[2] as CustomParseRule | undefined;
    expect(strongParseRule?.getAttrs?.('bold')).toBe(null);
    expect(strongParseRule?.getAttrs?.('bolder')).toBe(null);
    expect(strongParseRule?.getAttrs?.('700')).toBe(null);
    expect(strongParseRule?.getAttrs?.('800')).toBe(null);
    expect(strongParseRule?.getAttrs?.('900')).toBe(null);
    expect(strongParseRule?.getAttrs?.('normal')).toBe(false);
    expect(strongParseRule?.getAttrs?.('lighter')).toBe(false);
    expect(strongParseRule?.getAttrs?.('400')).toBe(false);
  });

  it('tests parseDOM and toDOM edge cases for table cells, task items, and images', () => {
    // Table header and cell with style.textAlign
    const thParse = editorSchema.nodes.table_header.spec.parseDOM?.[0] as CustomParseRule | undefined;
    const thEl = document.createElement('th');
    thEl.style.textAlign = 'center';
    expect(thParse?.getAttrs?.(thEl)).toEqual({ align: 'center' });

    const bareTh = document.createElement('th');
    expect(thParse?.getAttrs?.(bareTh)).toEqual({ align: null });

    const thWithAttr = document.createElement('th');
    thWithAttr.setAttribute('align', 'left');
    expect(thParse?.getAttrs?.(thWithAttr)).toEqual({ align: 'left' });

    const tdParse = editorSchema.nodes.table_cell.spec.parseDOM?.[0] as CustomParseRule | undefined;
    const bareTd = document.createElement('td');
    expect(tdParse?.getAttrs?.(bareTd)).toEqual({ align: null });

    const tdEl = document.createElement('td');
    tdEl.style.textAlign = 'right';
    expect(tdParse?.getAttrs?.(tdEl)).toEqual({ align: 'right' });

    const tdWithAttr = document.createElement('td');
    tdWithAttr.setAttribute('align', 'right');
    expect(tdParse?.getAttrs?.(tdWithAttr)).toEqual({ align: 'right' });

    // Table header and cell toDOM with align null vs string
    const thNull = editorSchema.nodes.table_header.create({ align: null });
    expect(thNull.type.spec.toDOM?.(thNull)).toEqual(['th', {}, 0]);
    const tdCenter = editorSchema.nodes.table_cell.create({ align: 'center' });
    expect(tdCenter.type.spec.toDOM?.(tdCenter)).toEqual([
      'td',
      { align: 'center', 'data-align': 'center' },
      0,
    ]);

    // Task item parseDOM getAttrs without checkbox
    const taskItemParse = editorSchema.nodes.task_item.spec.parseDOM?.[0];
    const emptyLi = document.createElement('li');
    expect(taskItemParse?.getAttrs?.(emptyLi)).toEqual({ checked: false });

    // Ordered list parseDOM getAttrs with invalid start
    const olParse = editorSchema.nodes.ordered_list.spec.parseDOM?.[0];
    const invalidOl = document.createElement('ol');
    invalidOl.setAttribute('start', 'not-a-number');
    expect(olParse?.getAttrs?.(invalidOl)).toEqual({ order: 1 });

    const noStartOl = document.createElement('ol');
    expect(olParse?.getAttrs?.(noStartOl)).toEqual({ order: 1 });

    // Image block parseDOM without img
    const imgBlockParse = editorSchema.nodes.image_block.spec.parseDOM?.[0];
    const divNoImg = document.createElement('div');
    expect(imgBlockParse?.getAttrs?.(divNoImg)).toEqual({
      src: '',
      alt: '',
      title: '',
    });

    // Image block toDOM with disallowed scheme and title
    const badImgBlock = editorSchema.nodes.image_block.create({
      src: 'javascript:alert(1)',
      alt: 'Bad',
      title: 'Bad Title',
    });
    expect(badImgBlock.type.spec.toDOM?.(badImgBlock)).toEqual([
      'div',
      { 'data-image-block': 'true', class: 'kb-editor__image-block' },
      ['img', { src: '', alt: 'Bad', title: 'Bad Title' }],
    ]);

    // Inline image toDOM with disallowed scheme and no title
    const badInlineImg = editorSchema.nodes.image.create({
      src: 'vbscript:msgbox',
      alt: 'Inline',
    });
    expect(badInlineImg.type.spec.toDOM?.(badInlineImg)).toEqual([
      'img',
      { src: '', alt: 'Inline', title: undefined, class: 'kb-inline-image' },
    ]);

    // Definition toDOM without label
    const defNoLabel = editorSchema.nodes.definition.create({
      identifier: 'def-id',
      label: '',
      url: 'https://kanban.local',
    });
    expect(defNoLabel.type.spec.toDOM?.(defNoLabel)).toEqual([
      'div',
      {
        class: 'kb-editor__definition',
        'data-definition': 'def-id',
        'data-label': 'def-id',
        'data-url': 'https://kanban.local',
        'data-title': '',
      },
      '[def-id]: https://kanban.local',
    ]);

    // Link toDOM with unsafe href, empty title, and null rawRef
    const unsafeLink = editorSchema.marks.link.create({
      href: 'javascript:alert(1)',
      title: '',
      rawRef: null,
    });
    expect(unsafeLink.type.spec.toDOM?.(unsafeLink, true)).toEqual([
      'a',
      {
        href: '#',
        title: undefined,
        'data-raw-ref': undefined,
        class: 'kb-link',
        rel: 'noopener noreferrer',
      },
      0,
    ]);

    // Link parseDOM getAttrs with bare href (missing title and data-raw-ref)
    const linkParseSpec = editorSchema.marks.link.spec.parseDOM?.[0] as CustomParseRule | undefined;
    const bareA = document.createElement('a');
    bareA.setAttribute('href', 'https://kanban.local/bare');
    expect(linkParseSpec?.getAttrs?.(bareA)).toEqual({
      href: 'https://kanban.local/bare',
      title: '',
      rawRef: null,
    });

    const noHrefA = document.createElement('a');
    expect(linkParseSpec?.getAttrs?.(noHrefA)).toEqual({
      href: '',
      title: '',
      rawRef: null,
    });

    // Bare image parseDOM getAttrs (empty src, alt, title)
    const bareImg = document.createElement('img');
    const imgParseSpec = editorSchema.nodes.image.spec.parseDOM?.[0];
    expect(imgParseSpec?.getAttrs?.(bareImg)).toEqual({
      src: '',
      alt: '',
      title: '',
    });

    // Image toDOM with empty alt
    const emptyAltImg = editorSchema.nodes.image.create({
      src: 'https://kanban.local/img.png',
      alt: '',
    });
    expect(emptyAltImg.type.spec.toDOM?.(emptyAltImg)).toEqual([
      'img',
      {
        src: 'https://kanban.local/img.png',
        alt: '',
        title: undefined,
        class: 'kb-inline-image',
      },
    ]);

    // Definition parseDOM getAttrs with bare div (empty attributes)
    const defParseSpec = editorSchema.nodes.definition.spec.parseDOM?.[0];
    const bareDiv = document.createElement('div');
    expect(defParseSpec?.getAttrs?.(bareDiv)).toEqual({
      identifier: '',
      label: '',
      url: '',
      title: '',
    });

    // Image block toDOM with empty alt and title
    const emptyImgBlock = editorSchema.nodes.image_block.create({
      src: 'https://kanban.local/i.png',
      alt: '',
      title: '',
    });
    expect(emptyImgBlock.type.spec.toDOM?.(emptyImgBlock)).toEqual([
      'div',
      { 'data-image-block': 'true', class: 'kb-editor__image-block' },
      ['img', { src: 'https://kanban.local/i.png', alt: '', title: undefined }],
    ]);
  });
});
