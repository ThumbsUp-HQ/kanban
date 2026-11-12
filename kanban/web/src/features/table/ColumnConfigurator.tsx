import React, { useState, useRef, useEffect, type JSX } from 'react';
import {
  type TableColumnId,
  getAvailableColumns,
  getDefaultColumns,
  saveTableColumns,
  reorderColumn,
  toggleColumn,
} from './tableColumns';

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
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
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
            <span>Configure Columns</span>
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
