import { useState, useEffect, useCallback } from 'react';
import type { IssueItem } from './viewsApi';
import type { QuickFieldType } from './QuickFieldPopover';

export interface UseIssueKeyboardMapOptions {
  issues: IssueItem[];
  layout?: string | undefined;
  selectedIds: string[];
  setSelectedIds: React.Dispatch<React.SetStateAction<string[]>>;
  modulesEnabled?: boolean | undefined;
  onOpenCreateModal?: (() => void) | undefined;
  onOpenFilter?: (() => void) | undefined;
  onOpenFieldPopover?: ((
    field: QuickFieldType,
    issue: IssueItem,
    rect: DOMRect | null
  ) => void) | undefined;
  onToggleAssigneeMe?: ((issue: IssueItem) => void) | undefined;
  isPopoverOrModalOpen?: boolean | undefined;
}

export interface UseIssueKeyboardMapReturn {
  focusedKey: string | null;
  setFocusedKey: (key: string | null) => void;
  anchorKey: string | null;
  setAnchorKey: (key: string | null) => void;
  handleRowClick: (key: string, isShift: boolean) => void;
}

function getIssueAnchorRect(issueKey: string): DOMRect | null {
  const el = document.querySelector(`[data-issue-key="${issueKey}"]`);
  return el ? el.getBoundingClientRect() : null;
}

export function useIssueKeyboardMap({
  issues,
  layout = 'list',
  selectedIds,
  setSelectedIds,
  modulesEnabled = true,
  onOpenCreateModal,
  onOpenFilter,
  onOpenFieldPopover,
  onToggleAssigneeMe,
  isPopoverOrModalOpen = false,
}: UseIssueKeyboardMapOptions): UseIssueKeyboardMapReturn {
  const [focusedKey, setFocusedKey] = useState<string | null>(null);
  const [anchorKey, setAnchorKey] = useState<string | null>(null);

  // Helper selecting a contiguous range between anchorKey and targetKey
  const selectRange = useCallback(
    (targetKey: string) => {
      const fromKey = anchorKey ?? focusedKey ?? issues[0]?.key;
      if (!fromKey) return;

      const fromIndex = issues.findIndex((i) => i.key === fromKey);
      const toIndex = issues.findIndex((i) => i.key === targetKey);
      if (fromIndex === -1 || toIndex === -1) return;

      const start = Math.min(fromIndex, toIndex);
      const end = Math.max(fromIndex, toIndex);
      const rangeKeys = issues.slice(start, end + 1).map((i) => i.key);

      setSelectedIds((prev) => {
        const merged = Array.from(new Set([...prev, ...rangeKeys]));
        if (merged.length > 100) {
          return merged.slice(0, 100);
        }
        return merged;
      });
    },
    [anchorKey, focusedKey, issues, setSelectedIds]
  );

  const handleRowClick = useCallback(
    (key: string, isShift: boolean) => {
      setFocusedKey(key);
      if (isShift) {
        selectRange(key);
      } else {
        setAnchorKey(key);
        setSelectedIds((prev) =>
          prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
        );
      }
    },
    [selectRange, setSelectedIds]
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 1. Ignore if typing in text inputs, textareas, selects, or contenteditable
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return;
      }

      // 2. Ignore during IME composition
      if (e.isComposing) {
        return;
      }

      // 3. Ignore if modal dialog is open (unless it's Escape)
      const hasOpenDialog =
        isPopoverOrModalOpen ||
        document.querySelector('dialog[open], [role="dialog"]') !== null;

      if (e.key === 'Escape') {
        // If modal or popover is open, let modal handle it
        if (!hasOpenDialog && selectedIds.length > 0) {
          e.preventDefault();
          setSelectedIds([]);
        }
        return;
      }

      if (hasOpenDialog) {
        return;
      }

      // Ignore if modifier keys are pressed (except Shift for range select)
      if (e.ctrlKey || e.metaKey || e.altKey) {
        return;
      }

      const key = e.key;
      const lowerKey = key.toLowerCase();

      // Shortcut: 'C' -> open quick create modal
      if (lowerKey === 'c') {
        e.preventDefault();
        onOpenCreateModal?.();
        return;
      }

      // Shortcut: '/' -> open filter search
      if (key === '/') {
        e.preventDefault();
        onOpenFilter?.();
        return;
      }

      // If no issues exist, navigation cannot proceed
      const firstIssue = issues[0];
      if (!firstIssue) {
        return;
      }

      // Find current focused index
      const currentIndex = focusedKey
        ? issues.findIndex((i) => i.key === focusedKey)
        : -1;

      // Shortcut: 'J' -> move down
      if (lowerKey === 'j') {
        e.preventDefault();
        const nextIndex =
          currentIndex === -1 || currentIndex >= issues.length - 1
            ? 0
            : currentIndex + 1;
        const nextItem = issues[nextIndex] ?? firstIssue;
        setFocusedKey(nextItem.key);
        if (!anchorKey) setAnchorKey(nextItem.key);
        return;
      }

      // Shortcut: 'K' -> move up
      if (lowerKey === 'k') {
        e.preventDefault();
        const prevIndex =
          currentIndex <= 0 ? issues.length - 1 : currentIndex - 1;
        const prevItem = issues[prevIndex] ?? firstIssue;
        setFocusedKey(prevItem.key);
        if (!anchorKey) setAnchorKey(prevItem.key);
        return;
      }

      // Shortcuts: 'H' / 'L' -> move across columns on Board layout
      if (layout === 'board' && lowerKey === 'h') {
        e.preventDefault();
        // Move to previous issue or column
        const prevIdx =
          currentIndex <= 0 ? issues.length - 1 : currentIndex - 1;
        const prevItem = issues[prevIdx] ?? firstIssue;
        setFocusedKey(prevItem.key);
        return;
      }

      if (layout === 'board' && lowerKey === 'l') {
        e.preventDefault();
        // Move to next column issue
        const nextIdx =
          currentIndex === -1 || currentIndex >= issues.length - 1
            ? 0
            : currentIndex + 1;
        const nextItem = issues[nextIdx] ?? firstIssue;
        setFocusedKey(nextItem.key);
        return;
      }

      // Shortcut: 'X' -> toggle selection on focusedKey (or Shift+X for range select)
      if (lowerKey === 'x') {
        e.preventDefault();
        const target = focusedKey ?? firstIssue.key;

        if (e.shiftKey) {
          selectRange(target);
        } else {
          setAnchorKey(target);
          setSelectedIds((prev) => {
            if (prev.includes(target)) {
              return prev.filter((k) => k !== target);
            }
            if (prev.length >= 100) {
              return prev;
            }
            return [...prev, target];
          });
        }
        return;
      }

      // Shortcut: 'Enter' or 'Space' -> peek issue
      if (key === 'Enter' || key === ' ') {
        if (focusedKey) {
          e.preventDefault();
          const targetUrl = `?layout=${encodeURIComponent(layout)}&peek=${encodeURIComponent(focusedKey)}`;
          window.location.href = targetUrl;
        }
        return;
      }

      // Field shortcut popovers: S, P, A, L, M, D
      const activeIssue =
        (focusedKey ? issues.find((i) => i.key === focusedKey) : null) ?? firstIssue;

      const anchorRect = getIssueAnchorRect(activeIssue.key);

      if (lowerKey === 's') {
        e.preventDefault();
        onOpenFieldPopover?.('state', activeIssue, anchorRect);
        return;
      }

      if (lowerKey === 'p') {
        e.preventDefault();
        onOpenFieldPopover?.('priority', activeIssue, anchorRect);
        return;
      }

      if (lowerKey === 'a') {
        e.preventDefault();
        onOpenFieldPopover?.('assignee', activeIssue, anchorRect);
        return;
      }

      if (layout !== 'board' && lowerKey === 'l') {
        e.preventDefault();
        onOpenFieldPopover?.('labels', activeIssue, anchorRect);
        return;
      }

      // Shortcut 'M': module popover (strict no-op when modulesEnabled is false)
      if (lowerKey === 'm') {
        if (modulesEnabled) {
          e.preventDefault();
          onOpenFieldPopover?.('module', activeIssue, anchorRect);
        }
        return;
      }

      if (lowerKey === 'd') {
        e.preventDefault();
        onOpenFieldPopover?.('due_date', activeIssue, anchorRect);
        return;
      }

      // Shortcut 'I': assign / unassign current user 'me' optimistically
      if (lowerKey === 'i') {
        e.preventDefault();
        onToggleAssigneeMe?.(activeIssue);
        return;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => { window.removeEventListener('keydown', handleKeyDown); };
  }, [
    issues,
    focusedKey,
    anchorKey,
    selectedIds,
    layout,
    modulesEnabled,
    isPopoverOrModalOpen,
    onOpenCreateModal,
    onOpenFilter,
    onOpenFieldPopover,
    onToggleAssigneeMe,
    selectRange,
    setSelectedIds,
  ]);

  return {
    focusedKey,
    setFocusedKey,
    anchorKey,
    setAnchorKey,
    handleRowClick,
  };
}
