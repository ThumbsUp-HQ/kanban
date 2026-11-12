/**
 * Typed table column definitions, defaults, reordering, and storage validation (KB-P3-38, S6.4, S7.2 8f).
 */

export type TableColumnId =
  | 'key'
  | 'summary'
  | 'state'
  | 'priority'
  | 'assignees'
  | 'labels'
  | 'cycle'
  | 'modules'
  | 'start_date'
  | 'due_date'
  | 'created_by'
  | 'access';

export interface TableColumnDef {
  readonly id: TableColumnId;
  readonly label: string;
  readonly locked?: boolean;
  readonly defaultVisible: boolean;
  readonly sortable?: boolean;
  readonly sortField?: string;
}

export const ALL_TABLE_COLUMNS: readonly TableColumnDef[] = Object.freeze([
  Object.freeze({
    id: 'key',
    label: 'Key',
    locked: true,
    defaultVisible: true,
    sortable: true,
    sortField: 'key',
  }),
  Object.freeze({
    id: 'summary',
    label: 'Summary',
    locked: true,
    defaultVisible: true,
    sortable: true,
    sortField: 'summary',
  }),
  Object.freeze({
    id: 'state',
    label: 'State',
    defaultVisible: true,
    sortable: true,
    sortField: 'state',
  }),
  Object.freeze({
    id: 'priority',
    label: 'Priority',
    defaultVisible: true,
    sortable: true,
    sortField: 'priority',
  }),
  Object.freeze({
    id: 'assignees',
    label: 'Assignees',
    defaultVisible: true,
    sortable: false,
  }),
  Object.freeze({
    id: 'labels',
    label: 'Labels',
    defaultVisible: true,
    sortable: false,
  }),
  Object.freeze({
    id: 'cycle',
    label: 'Cycle',
    defaultVisible: true,
    sortable: false,
  }),
  Object.freeze({
    id: 'modules',
    label: 'Modules',
    defaultVisible: true,
    sortable: false,
  }),
  Object.freeze({
    id: 'start_date',
    label: 'Start date',
    defaultVisible: false,
    sortable: true,
    sortField: 'start_date',
  }),
  Object.freeze({
    id: 'due_date',
    label: 'Due date',
    defaultVisible: true,
    sortable: true,
    sortField: 'due_date',
  }),
  Object.freeze({
    id: 'created_by',
    label: 'Created by',
    defaultVisible: false,
    sortable: true,
    sortField: 'created_by',
  }),
  Object.freeze({
    id: 'access',
    label: 'Access',
    defaultVisible: false,
    sortable: false,
  }),
]);

const VALID_COLUMN_IDS: ReadonlySet<string> = new Set(
  ALL_TABLE_COLUMNS.map((col) => col.id)
);

/**
 * Returns default visible columns for a project, taking modules_enabled into account.
 */
export function getDefaultColumns(modulesEnabled = true): TableColumnId[] {
  return ALL_TABLE_COLUMNS
    .filter((col) => {
      if (col.id === 'modules' && !modulesEnabled) {
        return false;
      }
      return col.defaultVisible;
    })
    .map((col) => col.id);
}

/**
 * Returns all available column definitions for a project, taking modules_enabled into account.
 */
export function getAvailableColumns(modulesEnabled = true): TableColumnDef[] {
  return ALL_TABLE_COLUMNS.filter((col) => {
    if (col.id === 'modules' && !modulesEnabled) {
      return false;
    }
    return true;
  });
}

/**
 * Parse and validate a raw localStorage value or config array.
 * Falls back safely to default columns on corrupted, hostile, or invalid input.
 */
export function parseTableColumns(
  raw: unknown,
  _projectKey: string,
  modulesEnabled = true
): TableColumnId[] {
  let parsed: unknown = raw;

  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw);
    } catch {
      return getDefaultColumns(modulesEnabled);
    }
  }

  if (!Array.isArray(parsed)) {
    return getDefaultColumns(modulesEnabled);
  }

  const validIds: TableColumnId[] = [];
  const seen = new Set<string>();

  for (const item of parsed) {
    if (typeof item === 'string' && VALID_COLUMN_IDS.has(item) && !seen.has(item)) {
      if (item === 'modules' && !modulesEnabled) {
        continue;
      }
      seen.add(item);
      validIds.push(item as TableColumnId);
    }
  }

  // Ensure locked columns 'key' and 'summary' are present
  if (!seen.has('key')) {
    validIds.unshift('key');
    seen.add('key');
  }
  if (!seen.has('summary')) {
    // Insert summary right after key
    const keyIdx = validIds.indexOf('key');
    validIds.splice(keyIdx + 1, 0, 'summary');
    seen.add('summary');
  }

  if (validIds.length === 0) {
    return getDefaultColumns(modulesEnabled);
  }

  return validIds;
}

/**
 * Reorders a column up or down within the active columns list.
 * Locked columns ('key' and 'summary') cannot be moved past index 1.
 */
export function reorderColumn(
  columns: readonly TableColumnId[],
  columnId: TableColumnId,
  direction: 'up' | 'down'
): TableColumnId[] {
  const next = [...columns];
  const index = next.indexOf(columnId);
  if (index === -1) {
    return next;
  }

  const targetIndex = direction === 'up' ? index - 1 : index + 1;

  // Cannot move out of bounds
  if (targetIndex < 0 || targetIndex >= next.length) {
    return next;
  }

  // Do not allow reordering key or summary
  if (columnId === 'key' || columnId === 'summary') {
    return next;
  }

  // Cannot move non-locked column before locked columns
  if (targetIndex < 2) {
    return next;
  }

  const [moved] = next.splice(index, 1) as [TableColumnId];
  next.splice(targetIndex, 0, moved);
  return next;
}

/**
 * Toggles visibility of an optional column.
 * Locked columns ('key' and 'summary') cannot be hidden.
 */
export function toggleColumn(
  columns: readonly TableColumnId[],
  columnId: TableColumnId,
  visible: boolean,
  modulesEnabled = true
): TableColumnId[] {
  if (columnId === 'key' || columnId === 'summary') {
    return [...columns];
  }
  if (columnId === 'modules' && !modulesEnabled) {
    return columns.filter((id) => id !== 'modules');
  }

  const exists = columns.includes(columnId);
  if (visible && !exists) {
    // Append to end
    return [...columns, columnId];
  }
  if (!visible && exists) {
    return columns.filter((id) => id !== columnId);
  }
  return [...columns];
}

/**
 * Persist column choices to localStorage with defensive key names.
 */
export function saveTableColumns(columns: TableColumnId[], projectKey: string): void {
  try {
    const storageKey = `kb.tableCols.${projectKey}`;
    localStorage.setItem(storageKey, JSON.stringify(columns));
  } catch {
    // Ignore storage quota or disabled storage exceptions
  }
}
