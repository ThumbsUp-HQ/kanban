/**
 * Keyboard Shortcuts Cheat Sheet Modal (KANBA-221, S6.4).
 * Accessible modal displaying comprehensive keyboard navigation and action shortcuts.
 */

import React, { useEffect, useRef, type JSX } from 'react';
import './ShortcutsCheatSheetModal.css';

export interface ShortcutsCheatSheetModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ShortcutEntry {
  combo: string;
  description: string;
  category: 'Navigation' | 'Board & Work Items' | 'Actions';
}

const SHORTCUTS_LIST: readonly ShortcutEntry[] = [
  { combo: 'Cmd/Ctrl + K', description: 'Open command palette & hybrid search', category: 'Navigation' },
  { combo: '[', description: 'Toggle sidebar navigation rail', category: 'Navigation' },
  { combo: '?', description: 'Open keyboard shortcuts cheat sheet', category: 'Navigation' },
  { combo: 'Esc', description: 'Close open dialog, drawer, or palette', category: 'Navigation' },
  { combo: 'J', description: 'Move focus down to next work item', category: 'Board & Work Items' },
  { combo: 'K', description: 'Move focus up to previous work item', category: 'Board & Work Items' },
  { combo: 'H', description: 'Move focus left across board columns', category: 'Board & Work Items' },
  { combo: 'L', description: 'Move focus right across board columns', category: 'Board & Work Items' },
  { combo: 'X', description: 'Toggle work item selection (Shift+X for range)', category: 'Board & Work Items' },
  { combo: 'C', description: 'Quick create new work item', category: 'Actions' },
  { combo: '/', description: 'Focus work items filter search bar', category: 'Actions' },
];

export function ShortcutsCheatSheetModal({
  isOpen,
  onClose,
}: ShortcutsCheatSheetModalProps): JSX.Element | null {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousActiveElementRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      previousActiveElementRef.current = document.activeElement as HTMLElement | null;
      dialogRef.current?.focus();
    } else if (previousActiveElementRef.current) {
      previousActiveElementRef.current.focus();
      previousActiveElementRef.current = null;
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const categories = ['Navigation', 'Board & Work Items', 'Actions'] as const;

  return (
    <div
      className="kb-shortcuts-backdrop"
      data-testid="shortcuts-modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        className="kb-shortcuts-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-modal-title"
        tabIndex={-1}
        data-testid="shortcuts-cheat-sheet-modal"
      >
        <header className="kb-shortcuts-header">
          <div className="kb-shortcuts-title-wrap">
            <span aria-hidden="true" className="kb-shortcuts-icon">⌨️</span>
            <h2 id="shortcuts-modal-title" className="kb-shortcuts-title">
              Keyboard Shortcuts
            </h2>
          </div>
          <button
            type="button"
            className="kb-shortcuts-close-btn"
            aria-label="Close shortcuts modal"
            onClick={onClose}
            data-testid="shortcuts-modal-close-btn"
          >
            ✕
          </button>
        </header>

        <div className="kb-shortcuts-body">
          {categories.map((cat) => {
            const items = SHORTCUTS_LIST.filter((s) => s.category === cat);
            return (
              <section key={cat} className="kb-shortcuts-section">
                <h3 className="kb-shortcuts-section-heading">{cat}</h3>
                <div className="kb-shortcuts-grid">
                  {items.map((item) => (
                    <div key={item.combo} className="kb-shortcuts-row">
                      <span className="kb-shortcuts-desc">{item.description}</span>
                      <kbd className="kb-shortcuts-kbd">{item.combo}</kbd>
                    </div>
                  ))}
                </div>
              </section>
            );
          })}
        </div>

        <footer className="kb-shortcuts-footer">
          <span className="kb-shortcuts-footer-hint">
            Shortcuts are automatically suppressed when typing inside inputs or editors.
          </span>
          <button
            type="button"
            className="kb-shortcuts-done-btn"
            onClick={onClose}
          >
            Got it
          </button>
        </footer>
      </div>
    </div>
  );
}
