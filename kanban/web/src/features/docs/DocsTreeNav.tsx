/**
 * WAI-ARIA Accessible Hierarchical ltree Sidebar Tree (KB-P3-50, S8.1, KB-P1-09).
 * Enforces role="tree" / role="treeitem", keyboard navigation, max_depth <= 10,
 * and cycle-preventing Move dialog.
 */

import React, {
  useState,
  useMemo,
  useCallback,
  useRef,
  useEffect,
  type JSX,
  type SyntheticEvent,
} from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import {
  fetchDocsTree,
  createPage,
  movePage,
  DEFAULT_DOC_MARKDOWN_TEMPLATE,
  type PageTreeNode,
} from './docsApi';
import './DocsWorkspaceView.css';

export interface DocsTreeNavProps {
  projectKey: string;
  activePageId?: string | undefined;
  readOnly?: boolean | undefined;
  onSelectPage: (pageId: string) => void;
  onAnnounce?: ((message: string) => void) | undefined;
}

export interface FlattenedTreeNode {
  node: PageTreeNode;
  depth: number; // 1 to 10
  parentId: string | null;
  hasChildren: boolean;
  expanded: boolean;
  id: string;
  title: string;
  restricted: boolean;
}

/** Computes max subtree depth from a node */
export function getSubtreeDepth(node: PageTreeNode): number {
  if (!node.children || node.children.length === 0) {
    return 1;
  }
  let maxChildDepth = 0;
  for (const child of node.children) {
    const d = getSubtreeDepth(child);
    if (d > maxChildDepth) {
      maxChildDepth = d;
    }
  }
  return 1 + maxChildDepth;
}

/** Collects all descendant IDs of a node */
export function getDescendantIds(node: PageTreeNode): Set<string> {
  const ids = new Set<string>();
  function walk(n: PageTreeNode) {
    if (n.children) {
      for (const child of n.children) {
        if (child.id) {
          ids.add(child.id);
          walk(child);
        }
      }
    }
  }
  walk(node);
  return ids;
}

export function DocsTreeNav({
  projectKey,
  activePageId,
  readOnly = false,
  onSelectPage,
  onAnnounce,
}: DocsTreeNavProps): JSX.Element {
  const queryClient = useQueryClient();
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());
  const [focusedId, setFocusedId] = useState<string | null>(null);

  // Modals state
  const [creatingParentId, setCreatingParentId] = useState<string | null | undefined>(undefined);
  const [newPageTitle, setNewPageTitle] = useState('');
  const [movingNode, setMovingNode] = useState<PageTreeNode | null>(null);
  const [selectedMoveTargetId, setSelectedMoveTargetId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const treeContainerRef = useRef<HTMLDivElement | null>(null);

  const {
    data: treeData = [],
    isLoading,
    isError,
  } = useQuery({
    queryKey: qk.docsTree(projectKey),
    queryFn: () => fetchDocsTree(projectKey),
  });

  // Automatically expand parent of activePageId on load
  useEffect(() => {
    if (!activePageId || treeData.length === 0) return;
    function findPath(nodes: PageTreeNode[], target: string, path: string[]): boolean {
      for (const node of nodes) {
        if (!node.id) continue;
        if (node.id === target) return true;
        if (node.children && node.children.length > 0) {
          if (findPath(node.children, target, [...path, node.id])) {
            const nodeId = node.id;
            setExpandedIds((prev) => new Set([...prev, nodeId]));
            return true;
          }
        }
      }
      return false;
    }
    findPath(treeData, activePageId, []);
  }, [activePageId, treeData]);

  // Flatten visible nodes according to expanded state
  const flattenedList: FlattenedTreeNode[] = useMemo(() => {
    const result: FlattenedTreeNode[] = [];
    let counter = 0;
    function flatten(nodes: PageTreeNode[], depth: number, parentId: string | null) {
      for (const node of nodes) {
        counter += 1;
        const id = node.id ?? `node-${String(counter)}`;
        const hasChildren = Boolean(node.children && node.children.length > 0);
        const isExpanded = expandedIds.has(id);
        const title = node.restricted ? (node.label ?? '🔒 Restricted Page') : (node.title ?? 'Untitled');

        result.push({
          node,
          depth,
          parentId,
          hasChildren,
          expanded: isExpanded,
          id,
          title,
          restricted: node.restricted,
        });

        if (hasChildren && isExpanded && node.children) {
          flatten(node.children, depth + 1, id);
        }
      }
    }
    flatten(treeData, 1, null);
    return result;
  }, [treeData, expandedIds]);

  const toggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Keyboard navigation handler
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent, currentItem: FlattenedTreeNode) => {
      const currentIndex = flattenedList.findIndex((item) => item.id === currentItem.id);
      if (currentIndex === -1) return;

      switch (e.key) {
        case 'ArrowDown': {
          e.preventDefault();
          if (currentIndex < flattenedList.length - 1) {
            const nextItem = flattenedList[currentIndex + 1];
            if (nextItem) {
              setFocusedId(nextItem.id);
              const el = document.getElementById(`treeitem-${nextItem.id}`);
              el?.focus();
            }
          }
          break;
        }
        case 'ArrowUp': {
          e.preventDefault();
          if (currentIndex > 0) {
            const prevItem = flattenedList[currentIndex - 1];
            if (prevItem) {
              setFocusedId(prevItem.id);
              const el = document.getElementById(`treeitem-${prevItem.id}`);
              el?.focus();
            }
          }
          break;
        }
        case 'ArrowRight': {
          e.preventDefault();
          if (currentItem.hasChildren) {
            if (!currentItem.expanded) {
              toggleExpand(currentItem.id);
            } else if (currentIndex < flattenedList.length - 1) {
              const nextItem = flattenedList[currentIndex + 1];
              if (nextItem && nextItem.depth > currentItem.depth) {
                setFocusedId(nextItem.id);
                document.getElementById(`treeitem-${nextItem.id}`)?.focus();
              }
            }
          }
          break;
        }
        case 'ArrowLeft': {
          e.preventDefault();
          if (currentItem.hasChildren && currentItem.expanded) {
            toggleExpand(currentItem.id);
          } else if (currentItem.parentId) {
            const parentItem = flattenedList.find((item) => item.id === currentItem.parentId);
            if (parentItem) {
              setFocusedId(parentItem.id);
              document.getElementById(`treeitem-${parentItem.id}`)?.focus();
            }
          }
          break;
        }
        case 'Enter': {
          e.preventDefault();
          if (!currentItem.restricted && currentItem.id) {
            onSelectPage(currentItem.id);
          }
          break;
        }
        default:
          break;
      }
    },
    [flattenedList, toggleExpand, onSelectPage],
  );

  // Mutations
  const createMutation = useMutation({
    mutationFn: async ({ parentId, title }: { parentId: string | null; title: string }) => {
      return createPage(projectKey, {
        title,
        body_markdown: DEFAULT_DOC_MARKDOWN_TEMPLATE,
        parent_page_id: parentId,
      });
    },
    onSuccess: (newPage) => {
      void queryClient.invalidateQueries({ queryKey: qk.docsTree(projectKey) });
      setCreatingParentId(undefined);
      setNewPageTitle('');
      setErrorMessage(null);
      if (newPage.id) {
        onSelectPage(newPage.id);
        onAnnounce?.(`Created page ${newPage.title}`);
      }
    },
    onError: (err: unknown) => {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to create page');
    },
  });

  const moveMutation = useMutation({
    mutationFn: async ({ pageId, targetParentId }: { pageId: string; targetParentId: string | null }) => {
      return movePage(pageId, {
        parent_page_id: targetParentId,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.docsTree(projectKey) });
      setMovingNode(null);
      setSelectedMoveTargetId(null);
      setErrorMessage(null);
      onAnnounce?.('Page moved successfully');
    },
    onError: (err: unknown) => {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to move page');
    },
  });

  const handleStartCreate = (parentId: string | null) => {
    setCreatingParentId(parentId);
    setNewPageTitle('');
    setErrorMessage(null);
  };

  const handleSubmitCreate = (e: SyntheticEvent) => {
    e.preventDefault();
    const trimmed = newPageTitle.trim();
    if (!trimmed) {
      setErrorMessage('Title cannot be empty');
      return;
    }
    if (trimmed.length > 500) {
      setErrorMessage('Title cannot exceed 500 characters');
      return;
    }
    createMutation.mutate({
      parentId: creatingParentId ?? null,
      title: trimmed,
    });
  };

  const handleStartMove = (node: PageTreeNode) => {
    setMovingNode(node);
    setSelectedMoveTargetId(null);
    setErrorMessage(null);
  };

  const handleSubmitMove = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!movingNode?.id) return;
    moveMutation.mutate({
      pageId: movingNode.id,
      targetParentId: selectedMoveTargetId,
    });
  };

  // Valid move targets: exclude self, descendants, and targets pushing depth > 10
  const validMoveTargets = useMemo(() => {
    if (!movingNode?.id) return [];
    const forbidden = getDescendantIds(movingNode);
    forbidden.add(movingNode.id);

    const subtreeDepth = getSubtreeDepth(movingNode);

    // Filter flattened nodes
    return flattenedList
      .filter((item) => {
        if (forbidden.has(item.id)) return false;
        // target depth + subtree depth must be <= 10
        if (item.depth + subtreeDepth > 10) return false;
        return true;
      });
  }, [movingNode, flattenedList]);

  return (
    <aside className="docs-tree-pane" aria-label="Documentation navigation">
      <div className="docs-tree-pane__header">
        <h2 className="docs-tree-pane__title">Pages</h2>
        {!readOnly && (
          <button
            type="button"
            className="docs-tree-btn docs-tree-btn--primary"
            onClick={() => {
              handleStartCreate(null);
            }}
            aria-label="Create new root doc"
            data-testid="create-root-doc-btn"
          >
            + New Doc
          </button>
        )}
      </div>

      {isLoading && (
        <div className="docs-tree-pane__loading" data-testid="docs-tree-loading">
          Loading document tree...
        </div>
      )}

      {isError && (
        <div className="docs-tree-pane__error" role="alert" data-testid="docs-tree-error">
          Failed to load document tree.
        </div>
      )}

      {!isLoading && !isError && treeData.length === 0 && (
        <div className="docs-tree-pane__empty" data-testid="docs-tree-empty">
          No documents yet. Create one to get started.
        </div>
      )}

      <div
        ref={treeContainerRef}
        className="docs-tree-view"
        role="tree"
        aria-label="Project documents"
        tabIndex={0}
      >
        {flattenedList.map((item) => {
          const isSelected = item.id === activePageId;
          const isFocused = focusedId === item.id || (!focusedId && isSelected);
          const isAtMaxDepth = item.depth >= 10;

          return (
            <div
              key={item.id}
              id={`treeitem-${item.id}`}
              className={`docs-tree-item ${isSelected ? 'docs-tree-item--selected' : ''}`}
              role="treeitem"
              aria-level={item.depth}
              aria-expanded={item.hasChildren ? item.expanded : undefined}
              aria-current={isSelected ? 'page' : undefined}
              tabIndex={isFocused ? 0 : -1}
              data-depth={item.depth}
              data-testid={`treeitem-${item.node.slug ?? item.id}`}
              onClick={() => {
                setFocusedId(item.id);
                if (!item.restricted) {
                  onSelectPage(item.id);
                }
              }}
              onKeyDown={(e) => {
                handleKeyDown(e, item);
              }}
            >
              <div className="docs-tree-item__indent" data-depth={item.depth} />
              
              {item.hasChildren ? (
                <button
                  type="button"
                  className="docs-tree-item__toggle"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleExpand(item.id);
                  }}
                  aria-label={item.expanded ? `Collapse ${item.title}` : `Expand ${item.title}`}
                  tabIndex={-1}
                >
                  {item.expanded ? '▼' : '▶'}
                </button>
              ) : (
                <span className="docs-tree-item__spacer" />
              )}

              <span className="docs-tree-item__icon" aria-hidden="true">
                {item.restricted ? '🔒' : '📄'}
              </span>

              <span className="docs-tree-item__title" title={item.title}>
                {item.title}
              </span>

              {!readOnly && (
                <div
                  className="docs-tree-item__actions"
                  onClick={(e) => {
                    e.stopPropagation();
                  }}
                >
                  <button
                    type="button"
                    className="docs-tree-item__action-btn"
                    title={isAtMaxDepth ? 'Maximum nesting depth of 10 pages reached' : 'Add sub-page'}
                    aria-label={`Add sub-page to ${item.title}`}
                    aria-disabled={isAtMaxDepth ? 'true' : undefined}
                    disabled={isAtMaxDepth}
                    data-testid={`add-subpage-${item.node.slug ?? item.id}`}
                    onClick={() => {
                      handleStartCreate(item.id);
                    }}
                  >
                    +
                  </button>

                  {!item.restricted && (
                    <button
                      type="button"
                      className="docs-tree-item__action-btn"
                      title="Move page"
                      aria-label={`Move page ${item.title}`}
                      data-testid={`move-page-${item.node.slug ?? item.id}`}
                      onClick={() => {
                        handleStartMove(item.node);
                      }}
                    >
                      ↗
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Create Page Modal */}
      {creatingParentId !== undefined && (
        <div className="docs-modal-overlay" role="dialog" aria-modal="true" aria-label="Create page">
          <div className="docs-modal">
            <h3 className="docs-modal__title">
              {creatingParentId === null ? 'Create Root Document' : 'Create Sub-page'}
            </h3>
            {errorMessage && (
              <div className="docs-modal__error" role="alert">
                {errorMessage}
              </div>
            )}
            <form onSubmit={handleSubmitCreate}>
              <label htmlFor="new-page-title" className="docs-modal__label">
                Title
              </label>
              <input
                id="new-page-title"
                type="text"
                className="docs-modal__input"
                value={newPageTitle}
                onChange={(e) => {
                  setNewPageTitle(e.target.value);
                }}
                placeholder="What do you want to call this doc?"
                autoFocus
                required
                maxLength={500}
                data-testid="new-page-title-input"
              />
              <div className="docs-modal__actions">
                <button
                  type="button"
                  className="docs-tree-btn"
                  onClick={() => {
                    setCreatingParentId(undefined);
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="docs-tree-btn docs-tree-btn--primary"
                  disabled={createMutation.isPending}
                  data-testid="submit-create-page-btn"
                >
                  {createMutation.isPending ? 'Creating...' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Move Page Modal */}
      {movingNode !== null && (
        <div className="docs-modal-overlay" role="dialog" aria-modal="true" aria-label="Move page">
          <div className="docs-modal">
            <h3 className="docs-modal__title">Move &quot;{movingNode.title}&quot;</h3>
            {errorMessage && (
              <div className="docs-modal__error" role="alert">
                {errorMessage}
              </div>
            )}
            <form onSubmit={handleSubmitMove}>
              <label htmlFor="move-target-select" className="docs-modal__label">
                Target Parent
              </label>
              <select
                id="move-target-select"
                className="docs-modal__select"
                value={selectedMoveTargetId ?? ''}
                onChange={(e) => {
                  setSelectedMoveTargetId(e.target.value || null);
                }}
                data-testid="move-target-select"
              >
                <option value="">(Doc Root - Depth 1)</option>
                {validMoveTargets.map((target) => (
                  <option key={target.id} value={target.id}>
                    {'- '.repeat(target.depth - 1)} {target.title} (Level {String(target.depth)})
                  </option>
                ))}
              </select>
              <div className="docs-modal__actions">
                <button
                  type="button"
                  className="docs-tree-btn"
                  onClick={() => {
                    setMovingNode(null);
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="docs-tree-btn docs-tree-btn--primary"
                  disabled={moveMutation.isPending}
                  data-testid="submit-move-page-btn"
                >
                  {moveMutation.isPending ? 'Moving...' : 'Move'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </aside>
  );
}
