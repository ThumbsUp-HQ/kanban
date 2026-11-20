/**
 * Docs Workspace 3-Pane View (KB-P3-50, S8.1, S6.1).
 * Responsive shell hosting DocsTreeNav, PageEditorPane, and OutlineAndVersionsRail.
 */

import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  type JSX,
} from 'react';
import { useParams, useNavigate } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { ensureDocsCsrfToken, fetchDocsTree, fetchPage, type PageTreeNode } from './docsApi';
import { DocsTreeNav } from './DocsTreeNav';
import { PageEditorPane } from './PageEditorPane';
import { OutlineAndVersionsRail } from './OutlineAndVersionsRail';
import { SelectionToIssueToolbar } from './SelectionToIssueToolbar';
import { useProjectRouteContext } from '../../app/ProjectRouteContext';
import './DocsWorkspaceView.css';

export function DocsWorkspaceView(): JSX.Element {
  const { projectKey = 'KAN', pageId } = useParams<{ projectKey: string; pageId?: string }>();
  const navigate = useNavigate();
  const ctx = useProjectRouteContext();

  const effectiveCaps = ctx.projectKey
    ? ctx.capabilities
    : (ctx.capabilities.length > 0 ? ctx.capabilities : ['EDIT', 'ADMIN']);
  const canEdit = effectiveCaps.includes('EDIT') || effectiveCaps.includes('ADMIN') || ctx.isProjectAdmin;

  const [currentMarkdown, setCurrentMarkdown] = useState<string | undefined>(undefined);
  const [isTreeSheetOpen, setIsTreeSheetOpen] = useState(false);
  const [isRailSheetOpen, setIsRailSheetOpen] = useState(
    () => !(typeof window !== 'undefined' && window.innerWidth <= 1024)
  );
  const [railTab, setRailTab] = useState<'outline' | 'history'>('outline');
  const [announcement, setAnnouncement] = useState<string | null>(null);

  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth <= 1024
  );

  useEffect(() => {
    function handleResize() {
      setIsMobile(window.innerWidth <= 1024);
    }
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  const handleOpenHistory = useCallback(() => {
    setIsRailSheetOpen(true);
    setRailTab('history');
  }, []);

  useEffect(() => {
    void ensureDocsCsrfToken();
  }, []);

  // Load tree to find default initial page if pageId is not in URL
  const { data: treeData = [] } = useQuery({
    queryKey: qk.docsTree(projectKey),
    queryFn: () => fetchDocsTree(projectKey),
  });

  const firstAvailablePageId = useMemo(() => {
    function findFirst(nodes: PageTreeNode[]): string | null {
      for (const n of nodes) {
        if (!n.restricted && n.id) return n.id;
        if (n.children && n.children.length > 0) {
          const found = findFirst(n.children);
          if (found) return found;
        }
      }
      return null;
    }
    return findFirst(treeData);
  }, [treeData]);

  // If no pageId in URL and tree has pages, navigate to first page
  useEffect(() => {
    if (!pageId && firstAvailablePageId) {
      void navigate(`/projects/${projectKey}/docs/${firstAvailablePageId}`, { replace: true });
    }
  }, [pageId, firstAvailablePageId, projectKey, navigate]);

  const activePageId = pageId ?? firstAvailablePageId ?? undefined;
  const resolvedPageId = activePageId ?? '';

  // Page query for right rail & toolbar
  const { data: pageData } = useQuery({
    queryKey: qk.page(resolvedPageId),
    queryFn: () => fetchPage(resolvedPageId),
    enabled: Boolean(activePageId),
  });

  const handleSelectPage = useCallback(
    (nextId: string) => {
      setIsTreeSheetOpen(false);
      void navigate(`/projects/${projectKey}/docs/${nextId}`);
    },
    [projectKey, navigate],
  );

  const handleAnnounce = useCallback((msg: string) => {
    setAnnouncement(msg);
    setTimeout(() => {
      setAnnouncement(null);
    }, 4000);
  }, []);

  return (
    <div className="docs-workspace-view" data-testid="docs-workspace-view">
      <h1 className="sr-only">Documentation - {pageData?.title ?? 'Workspace Docs'}</h1>
      {/* Mobile Topbar */}
      <div className="docs-mobile-bar" data-testid="docs-mobile-bar">
        <button
          type="button"
          className="docs-mobile-btn"
          onClick={() => {
            setIsTreeSheetOpen((prev) => !prev);
            setIsRailSheetOpen(false);
          }}
          aria-label="Toggle document tree"
          data-testid="toggle-tree-sheet-btn"
        >
          📂 Pages Tree
        </button>
        <button
          type="button"
          className="docs-mobile-btn"
          onClick={() => {
            setIsRailSheetOpen((prev) => !prev);
            setIsTreeSheetOpen(false);
          }}
          aria-label="Toggle outline and history"
          data-testid="toggle-rail-sheet-btn"
        >
          📑 Outline & History
        </button>
      </div>

      {/* Screen reader live region */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>

      {/* 3-Pane Body */}
      <div className="docs-workspace-body">
        {/* Backdrop for mobile sheets */}
        {isMobile && (isTreeSheetOpen || isRailSheetOpen) && (
          <div
            className="docs-sheet-backdrop"
            onClick={() => {
              setIsTreeSheetOpen(false);
              setIsRailSheetOpen(false);
            }}
            data-testid="docs-sheet-backdrop"
          />
        )}

        {/* Left Pane (Tree) */}
        <div
          className={`docs-tree-wrapper ${isTreeSheetOpen ? 'docs-tree-pane--open' : ''}`}
          data-testid="docs-tree-wrapper"
        >
          <DocsTreeNav
            projectKey={projectKey}
            activePageId={activePageId}
            readOnly={!canEdit}
            onSelectPage={handleSelectPage}
            onAnnounce={handleAnnounce}
          />
        </div>

        {/* Center Pane (Editor) */}
        {activePageId ? (
          <>
            <PageEditorPane
              pageId={activePageId}
              projectKey={projectKey}
              readOnly={!canEdit}
              onToggleRail={() => {
                setIsRailSheetOpen((prev) => !prev);
              }}
              onOpenHistory={handleOpenHistory}
              isRailOpen={isRailSheetOpen}
              onAnnounce={handleAnnounce}
              onMarkdownChange={setCurrentMarkdown}
            />
            {canEdit && (
              <SelectionToIssueToolbar
                pageId={activePageId}
                projectKey={projectKey}
                pageTitle={pageData?.title ?? 'Document'}
                onAnnounce={handleAnnounce}
              />
            )}
          </>
        ) : (
          <main className="docs-center-pane" aria-label="Page Editor">
            <div className="docs-center-pane__empty" data-testid="docs-empty-state">
              Select a document from the tree or create a new one to begin editing.
            </div>
          </main>
        )}

        {/* Right Pane (Outline & History) */}
        {activePageId && (
          <div
            className={`docs-rail-wrapper ${isRailSheetOpen ? 'docs-rail-pane--open' : ''}`}
            data-testid="docs-rail-wrapper"
          >
            <OutlineAndVersionsRail
              pageId={activePageId}
              projectKey={projectKey}
              page={pageData}
              markdownContent={currentMarkdown}
              onAnnounce={handleAnnounce}
              activeTab={railTab}
              onTabChange={setRailTab}
            />
          </div>
        )}
      </div>
    </div>
  );
}
