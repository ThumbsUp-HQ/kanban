import React, { useState, useRef, useEffect, type JSX } from 'react';
import {
  type TableColumnId,
  getAvailableColumns,
  getDefaultColumns,
  saveTableColumns,
  reorderColumn,
  toggleColumn,
} from './tableColumns';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { StudioDocLink } from '../../components/help/StudioDocLink';

export interface ColumnConfiguratorProps {
  columns: TableColumnId[];
  onChange: (columns: TableColumnId[]) => void;
  projectKey: string;
  modulesEnabled?: boolean;
}

/**
 * Accessible column configuration popover menu (KB-P3-38, S6.4, S7.2 8f).
 */
export function ColumnConfigurator({
  columns,
  onChange,
  projectKey,
  modulesEnabled = true,
}: ColumnConfiguratorProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const available = getAvailableColumns(modulesEnabled);
  const total = available.length;
  // Visible count among available columns
  const visibleCount = columns.filter((id) =>
    available.some((col) => col.id === id)
  ).length;

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node | null;
      if (
        document.querySelector(
          '.kb-help-drawer, .kb-help-drawer-backdrop, .field-help-hint-popover'
        ) ||
        (target instanceof Element &&
          target.closest(
            '.kb-help-drawer, .kb-help-drawer-backdrop, .field-help-hint-popover'
          ))
      ) {
        return;
      }
      if (
        containerRef.current &&
        !containerRef.current.contains(target)
      ) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        if (
          document.querySelector(
            '.kb-help-drawer, .kb-help-drawer-backdrop, .field-help-hint-popover'
          )
        ) {
          return;
        }
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const handleToggle = (columnId: TableColumnId, checked: boolean) => {
    const next = toggleColumn(columns, columnId, checked, modulesEnabled);
    saveTableColumns(next, projectKey);
    onChange(next);
  };

  const handleMove = (columnId: TableColumnId, direction: 'up' | 'down') => {
    const next = reorderColumn(columns, columnId, direction);
    saveTableColumns(next, projectKey);
    onChange(next);
  };

  const handleReset = () => {
    const defaults = getDefaultColumns(modulesEnabled);
    saveTableColumns(defaults, projectKey);
    onChange(defaults);
  };

  return (
    <div className="column-configurator-container" ref={containerRef}>
      <button
        type="button"
        className="column-configurator-trigger"
        onClick={() => { setIsOpen((prev) => !prev); }}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
      >
        <span>Columns ({visibleCount}/{total})</span>
      </button>

      {isOpen && (
        <div
          role="dialog"
          aria-label="Configure table columns"
          className="column-configurator-dialog"
        >
          <div className="column-configurator-header">
            <div className="column-configurator-header-title-wrap">
              <span>Configure Columns</span>
              <StudioDocLink
                href="/docs/enterprise-whitespace-and-kanban-board#table-view-and-column-customization"
                label="Columns Guide ->"
                testId="column-config-doc-link"
              />
            </div>
            <button
              type="button"
              className="column-configurator-btn-move"
              onClick={() => { setIsOpen(false); }}
              aria-label="Close column configuration"
            >
              ✕
            </button>
          </div>

          <div className="column-configurator-list">
            {available.map((col) => {
              const isVisible = columns.includes(col.id);
              const colIndex = columns.indexOf(col.id);
              const isLocked = Boolean(col.locked);
              const canMoveUp = !isLocked && colIndex > 2;
              const canMoveDown =
                !isLocked && colIndex >= 2 && colIndex < columns.length - 1;

              return (
                <div
                  key={col.id}
                  className="column-configurator-item"
                  data-col-id={col.id}
                >
                  <label className="column-configurator-item-left">
                    <input
                      type="checkbox"
                      checked={isVisible}
                      disabled={isLocked}
                      onChange={(e) => { handleToggle(col.id, e.target.checked); }}
                      aria-label={col.label}
                    />
                    <span>{col.label}</span>
                  </label>

                  {isLocked && col.id === 'key' && (
                    <FieldHelpHint
                      title="Pinned Columns"
                      summary="Identifier and Summary columns are permanently pinned to provide consistent issue identification and navigation."
                      defaultValue="Pinned (Identifier, Summary)"
                      validValues={[
                        { label: 'Identifier (Key)', description: 'Immutable unique project issue tracking key.' },
                        { label: 'Summary', description: 'Primary headline describing the work item.' },
                      ]}
                      docHref="/docs/enterprise-whitespace-and-kanban-board#table-view-and-column-customization"
                      testId="pinned-columns-help"
                      ariaLabel="Why Key and Summary are pinned"
                    />
                  )}

                  {isVisible && !isLocked && (
                    <div className="column-configurator-item-actions">
                      <button
                        type="button"
                        className="column-configurator-btn-move"
                        disabled={!canMoveUp}
                        onClick={() => { handleMove(col.id, 'up'); }}
                        aria-label={`Move ${col.label} up`}
                      >
                        ▲
                      </button>
                      <button
                        type="button"
                        className="column-configurator-btn-move"
                        disabled={!canMoveDown}
                        onClick={() => { handleMove(col.id, 'down'); }}
                        aria-label={`Move ${col.label} down`}
                      >
                        ▼
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <button
            type="button"
            className="column-configurator-reset"
            onClick={handleReset}
          >
            Reset defaults
          </button>
        </div>
      )}
    </div>
  );
}
