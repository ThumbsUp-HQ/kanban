import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  ALL_TABLE_COLUMNS,
  getDefaultColumns,
  getAvailableColumns,
  parseTableColumns,
  reorderColumn,
  toggleColumn,
  saveTableColumns,
  type TableColumnId,
} from './tableColumns';

describe('tableColumns', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('provides all expected column definitions', () => {
    expect(ALL_TABLE_COLUMNS.length).toBe(13);
    const ids = ALL_TABLE_COLUMNS.map((c) => c.id);
    expect(ids).toContain('key');
    expect(ids).toContain('summary');
    expect(ids).toContain('state');
    expect(ids).toContain('priority');
    expect(ids).toContain('assignees');
    expect(ids).toContain('labels');
    expect(ids).toContain('cycle');
    expect(ids).toContain('modules');
    expect(ids).toContain('start_date');
    expect(ids).toContain('due_date');
    expect(ids).toContain('updated_at');
    expect(ids).toContain('created_by');
    expect(ids).toContain('access');
  });

  it('unmounts modules when modulesEnabled is false', () => {
    const withModules = getAvailableColumns(true);
    expect(withModules.some((c) => c.id === 'modules')).toBe(true);

    const withoutModules = getAvailableColumns(false);
    expect(withoutModules.some((c) => c.id === 'modules')).toBe(false);

    const defaultWith = getDefaultColumns(true);
    expect(defaultWith).toContain('modules');

    const defaultWithout = getDefaultColumns(false);
    expect(defaultWithout).not.toContain('modules');
  });

  it('parses valid and default columns from localStorage', () => {
    const custom = ['key', 'summary', 'state', 'due_date'];
    const parsed = parseTableColumns(JSON.stringify(custom), 'KAN', true);
    expect(parsed).toEqual(['key', 'summary', 'state', 'due_date']);
  });

  it('handles negative/security hostile corrupt values gracefully', () => {
    // Malformed JSON string
    expect(parseTableColumns('{corrupt}', 'KAN', true)).toEqual(
      getDefaultColumns(true)
    );

    // Hostile prototype injection object
    expect(parseTableColumns('{"__proto__":1}', 'KAN', true)).toEqual(
      getDefaultColumns(true)
    );

    // Hostile scripts or invalid IDs
    const hostile = ['<script>', 'alert(1)', 'unknown'];
    const parsed = parseTableColumns(JSON.stringify(hostile), 'KAN', true);
    // Locked columns are prepended
    expect(parsed).toContain('key');
    expect(parsed).toContain('summary');

    // Modules stripped when modulesEnabled is false even if explicitly present
    const withStaleModules = ['key', 'summary', 'modules', 'state'];
    const parsedNoMod = parseTableColumns(
      JSON.stringify(withStaleModules),
      'KAN',
      false
    );
    expect(parsedNoMod).not.toContain('modules');
    expect(parsedNoMod).toEqual(['key', 'summary', 'state']);
  });

  it('reorders non-locked columns and prevents illegal moves', () => {
    const initial: TableColumnId[] = ['key', 'summary', 'state', 'priority', 'due_date'];

    // Move priority up before state
    const movedUp = reorderColumn(initial, 'priority', 'up');
    expect(movedUp).toEqual(['key', 'summary', 'priority', 'state', 'due_date']);

    // Move priority down
    const movedDown = reorderColumn(movedUp, 'priority', 'down');
    expect(movedDown).toEqual(initial);

    // Cannot move locked key or summary
    expect(reorderColumn(initial, 'key', 'down')).toEqual(initial);
    expect(reorderColumn(initial, 'summary', 'down')).toEqual(initial);

    // Cannot move beyond bounds
    expect(reorderColumn(initial, 'state', 'up')).toEqual(initial); // cannot move into index 1 (summary is locked at index 1)
    expect(reorderColumn(initial, 'due_date', 'down')).toEqual(initial);

    // Unknown column returns unchanged
    expect(reorderColumn(initial, 'access', 'up')).toEqual(initial);
  });

  it('toggles column visibility respecting locks and modulesEnabled', () => {
    const initial: TableColumnId[] = ['key', 'summary', 'state'];

    // Toggle start_date on
    const withStart = toggleColumn(initial, 'start_date', true);
    expect(withStart).toContain('start_date');

    // Toggle start_date off
    const withoutStart = toggleColumn(withStart, 'start_date', false);
    expect(withoutStart).not.toContain('start_date');

    // Cannot toggle locked columns off
    expect(toggleColumn(initial, 'key', false)).toEqual(initial);
    expect(toggleColumn(initial, 'summary', false)).toEqual(initial);

    // Cannot toggle modules on if modulesEnabled is false
    expect(toggleColumn(initial, 'modules', true, false)).not.toContain('modules');

    // Redundant toggles return current list
    expect(toggleColumn(initial, 'state', true)).toEqual(initial);
    expect(toggleColumn(initial, 'access', false)).toEqual(initial);
  });

  it('saves columns to localStorage and handles storage exceptions', () => {
    const cols: TableColumnId[] = ['key', 'summary', 'state'];
    saveTableColumns(cols, 'KAN');
    expect(localStorage.getItem('kb.tableCols.KAN')).toBe(JSON.stringify(cols));

    vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => {
      throw new Error('QuotaExceededError');
    });
    expect(() => { saveTableColumns(cols, 'KAN'); }).not.toThrow();
  });
});
