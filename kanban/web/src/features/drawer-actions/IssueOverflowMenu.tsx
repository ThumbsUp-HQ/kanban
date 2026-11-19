/**
 * IssueOverflowMenu component (KB-P3-43, S7.1, S7.2 8n-8q).
 *
 * `[⋯]` overflow menu with:
 * 1. `📑 Make a copy`
 * 2. `↗ Open in full screen` / `Return to side panel`
 * 3. `🗄️ Archive` (rule-explained with exact reason sub-label when disabled)
 * 4. `🗑️ Delete...` (gated by DELETE capability)
 */

import React, { useEffect, useRef, useState, type JSX } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { announce } from '../../api/RealtimeStatus';
import type { IssueDetail } from '../drawer/slots';
import { DeleteBlastRadiusModal } from './DeleteBlastRadiusModal';
import { MakeCopyDialog } from './MakeCopyDialog';
import { archiveIssue, unarchiveIssue } from './actionsApi';
import './drawerActions.css';

export interface IssueOverflowMenuProps {
  issue: IssueDetail;
  mode: 'drawer' | 'full';
  toggleFullScreen: () => void;
}

export function IssueOverflowMenu({
  issue,
  mode,
  toggleFullScreen,
}: IssueOverflowMenuProps): JSX.Element {
  const queryClient = useQueryClient();
  const [menuOpen, setMenuOpen] = useState(false);
  const [copyDialogOpen, setCopyDialogOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const capabilities = (issue.capabilities && Array.isArray(issue.capabilities))
    ? issue.capabilities
    : ['VIEW', 'EDIT', 'DELETE'];
  const canEdit = capabilities.includes('EDIT') || capabilities.includes('ADMIN');
  const canDelete = capabilities.includes('DELETE') || capabilities.includes('ADMIN');

  const stateGroup = (issue.state && typeof issue.state.group === 'string')
    ? issue.state.group.toLowerCase()
    : '';
  const isArchiveEligible =
    stateGroup === 'completed' || stateGroup === 'cancelled' || stateGroup === 'done';
  const isArchived = Boolean(issue.archived_at);

  // Close menu on Escape or click outside
  useEffect(() => {
    if (!menuOpen) return;

    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        setMenuOpen(false);
      }
    }

    function handleClickOutside(e: MouseEvent): void {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [menuOpen]);

  // Arrow key navigation inside menu
  function handleMenuKeyDown(e: React.KeyboardEvent): void {
    if (!menuRef.current) return;
    const items = Array.from(
      menuRef.current.querySelectorAll<HTMLButtonElement>('[role="menuitem"]'),
    );
    const currentIndex = items.indexOf(document.activeElement as HTMLButtonElement);

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const nextIndex = (currentIndex + 1) % items.length;
      items[nextIndex]?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prevIndex = (currentIndex - 1 + items.length) % items.length;
      items[prevIndex]?.focus();
    } else if (e.key === 'Home') {
      e.preventDefault();
      items[0]?.focus();
    } else if (e.key === 'End') {
      e.preventDefault();
      items[items.length - 1]?.focus();
    }
  }

  const archiveMutation = useMutation({
    mutationFn: async () => {
      if (isArchived) {
        return await unarchiveIssue(issue.key);
      }
      return await archiveIssue(issue.key);
    },
    onSuccess: () => {
      announce(isArchived ? 'Unarchived' : 'Archived');
      void queryClient.invalidateQueries({ queryKey: qk.project(issue.project_key) });
      void queryClient.invalidateQueries({ queryKey: qk.issue(issue.key) });
      setMenuOpen(false);
    },
  });

  function handleArchiveClick(): void {
    if (!isArchiveEligible && !isArchived) {
      // Disallowed: 0 network calls
      return;
    }
    archiveMutation.mutate();
  }

  return (
    <div className="overflow-menu-container" ref={containerRef}>
      <button
        type="button"
        className={`drawer-action-btn ${menuOpen ? 'drawer-action-btn--active' : ''}`}
        aria-label="More actions"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        onClick={() => { setMenuOpen((prev) => !prev); }}
        data-testid="issue-overflow-trigger"
      >
        <span aria-hidden="true">⋯</span>
      </button>

      {menuOpen && (
        <div
          className="overflow-menu"
          role="menu"
          aria-label="Issue actions"
          ref={menuRef}
          onKeyDown={handleMenuKeyDown}
          data-testid="issue-overflow-menu"
        >
          {/* 1. Make a copy */}
          {canEdit && (
            <button
              type="button"
              className="overflow-menu__item"
              role="menuitem"
              onClick={() => {
                setMenuOpen(false);
                setCopyDialogOpen(true);
              }}
              data-testid="overflow-make-copy-btn"
            >
              <div className="overflow-menu__label-row">
                <span aria-hidden="true">📑</span>
                <span>Make a copy</span>
              </div>
            </button>
          )}

          {/* 2. Open in full screen / Return to side panel */}
          <button
            type="button"
            className="overflow-menu__item"
            role="menuitem"
            onClick={() => {
              setMenuOpen(false);
              toggleFullScreen();
            }}
            data-testid="overflow-toggle-fullscreen-btn"
          >
            <div className="overflow-menu__label-row">
              <span aria-hidden="true">↗</span>
              <span>{mode === 'full' ? 'Return to side panel' : 'Open in full screen'}</span>
            </div>
          </button>

          {/* 3. Archive / Unarchive */}
          {canEdit && (
            <button
              type="button"
              className="overflow-menu__item"
              role="menuitem"
              aria-disabled={!isArchiveEligible && !isArchived}
              onClick={handleArchiveClick}
              data-testid="overflow-archive-btn"
            >
              <div className="overflow-menu__label-row">
                <span aria-hidden="true">🗄️</span>
                <span>{isArchived ? 'Unarchive' : 'Archive'}</span>
              </div>
              {!isArchiveEligible && !isArchived && (
                <span className="overflow-menu__sublabel" data-testid="archive-disabled-reason">
                  Only completed or canceled work items can be archived
                </span>
              )}
            </button>
          )}

          {/* 4. Delete... (Rendered only when caller holds DELETE capability) */}
          {canDelete && (
            <button
              type="button"
              className="overflow-menu__item overflow-menu__item--danger"
              role="menuitem"
              onClick={() => {
                setMenuOpen(false);
                setDeleteModalOpen(true);
              }}
              data-testid="overflow-delete-btn"
            >
              <div className="overflow-menu__label-row">
                <span aria-hidden="true">🗑️</span>
                <span>Delete...</span>
              </div>
            </button>
          )}
        </div>
      )}

      {/* Make a Copy Dialog */}
      <MakeCopyDialog
        issue={issue}
        open={copyDialogOpen}
        onClose={() => { setCopyDialogOpen(false); }}
      />

      {/* Delete Blast Radius Modal */}
      <DeleteBlastRadiusModal
        issue={issue}
        open={deleteModalOpen}
        onClose={() => { setDeleteModalOpen(false); }}
      />
    </div>
  );
}
