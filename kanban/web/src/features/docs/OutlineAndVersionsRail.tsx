/**
 * Outline and Version History Right Rail (KB-P3-50, S8.1, KB-P1-09).
 * Features accessible tabs (Outline / History), heading extraction outside code fences,
 * active heading tracking, linked object_links, and immutable version history restore.
 */

import React, {
  useState,
  useMemo,
  useEffect,
  type JSX,
} from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import {
  fetchPageVersions,
  restorePageVersion,
  fetchProjectIssues,
  createLink,
  type PageResponse,
} from './docsApi';
import './DocsWorkspaceView.css';

export interface OutlineAndVersionsRailProps {
  pageId: string;
  projectKey?: string | undefined;
  page?: PageResponse | undefined;
  markdownContent?: string | undefined;
  onAnnounce?: ((message: string) => void) | undefined;
  activeTab?: ('outline' | 'history') | undefined;
  onTabChange?: ((tab: 'outline' | 'history') => void) | undefined;
}

export interface ExtractedHeading {
  level: number; // 1, 2, 3
  text: string;
  anchor: string;
}

const HEADING_RE = /^(#{1,3})\s+(.*?)(?:\s+#+\s*)?$/;
const FENCE_RE = /^(```+|~~~+)/;
const LINK_IMAGE_RE = /!\[([^\]]*)\]\([^)]*\)|\[([^\]]+)\]\([^)]*\)/g;
const INLINE_CODE_RE = /`([^`]+)`/g;
const BOLD_ITALIC_RE = /(\*{1,3}|_{1,3})([^*_]+)\1/g;
const STRIKE_RE = /~~([^~]+)~~/g;
const NON_ALPHANUM_RE = /[^\w\s-]/g;
const SPACES_RE = /[\s-]+/g;

/** Clean inline markdown from heading */
export function stripInlineMarkdown(raw: string): string {
  let cleaned = raw.replace(LINK_IMAGE_RE, (_, alt?: string, text?: string) => alt ?? text ?? '');
  cleaned = cleaned.replace(INLINE_CODE_RE, '$1');
  cleaned = cleaned.replace(BOLD_ITALIC_RE, '$2');
  cleaned = cleaned.replace(STRIKE_RE, '$1');
  return cleaned.trim();
}

/** Extracts h1..h3 headings outside fenced code blocks and HTML comments */
export function extractHeadings(markdown: string): ExtractedHeading[] {
  const lines = markdown.split(/\r?\n/);
  const headings: ExtractedHeading[] = [];
  const seenCounts = new Map<string, number>();

  let inFence = false;
  let fenceChar = '';
  let fenceLen = 0;
  let inHtmlComment = false;

  for (const line of lines) {
    const trimmed = line.trim();

    // Track HTML comment blocks
    if (!inFence) {
      if (trimmed.startsWith('<!--') && !trimmed.endsWith('-->')) {
        inHtmlComment = true;
        continue;
      }
      if (inHtmlComment) {
        if (trimmed.endsWith('-->') || trimmed.includes('-->')) {
          inHtmlComment = false;
        }
        continue;
      }
    }

    // Track fenced code blocks
    const fenceMatch = FENCE_RE.exec(trimmed);
    if (fenceMatch?.[1]) {
      const char = fenceMatch[1].charAt(0);
      const len = fenceMatch[1].length;
      if (!inFence) {
        inFence = true;
        fenceChar = char;
        fenceLen = len;
        continue;
      } else if (char === fenceChar && len >= fenceLen) {
        inFence = false;
        continue;
      }
    }

    if (inFence || inHtmlComment) {
      continue;
    }

    const headingMatch = HEADING_RE.exec(trimmed);
    if (headingMatch?.[1] && headingMatch[2]) {
      const level = headingMatch[1].length;
      const rawText = headingMatch[2];
      const text = stripInlineMarkdown(rawText);
      if (!text) continue;

      // Deterministic GitHub-style slug
      const base = text.toLowerCase().replace(NON_ALPHANUM_RE, '').trim();
      let slug = base.replace(SPACES_RE, '-').replace(/^-+|-+$/g, '');
      if (!slug) {
        slug = 'section';
      }

      const count = seenCounts.get(slug) ?? 0;
      seenCounts.set(slug, count + 1);

      const anchor = count === 0 ? slug : `${slug}-${String(count)}`;
      headings.push({ level, text, anchor });
    }
  }

  return headings;
}

export interface DiffLine {
  type: 'added' | 'removed' | 'unchanged';
  text: string;
}

export interface DiffResult {
  lines: DiffLine[];
  addedCount: number;
  removedCount: number;
}

/** Computes line-by-line diff between base (old) and head (new) texts */
export function computeLineDiff(oldText: string, newText: string): DiffResult {
  const oldLines = oldText.split(/\r?\n/);
  const newLines = newText.split(/\r?\n/);

  if (oldText === newText) {
    return {
      lines: oldLines.map((text) => ({ type: 'unchanged', text })),
      addedCount: 0,
      removedCount: 0,
    };
  }

  const n = Math.min(oldLines.length, 500);
  const m = Math.min(newLines.length, 500);

  const dp: number[][] = [];
  for (let rowIdx = 0; rowIdx <= n; rowIdx++) {
    dp.push(new Array<number>(m + 1).fill(0));
  }

  for (let i = 0; i < n; i++) {
    const rowCurr = dp[i];
    const rowNext = dp[i + 1];
    if (!rowCurr || !rowNext) continue;

    const oldLine = oldLines[i];
    for (let j = 0; j < m; j++) {
      const newLine = newLines[j];
      if (oldLine === newLine) {
        rowNext[j + 1] = (rowCurr[j] ?? 0) + 1;
      } else {
        const fromLeft = rowNext[j] ?? 0;
        const fromTop = rowCurr[j + 1] ?? 0;
        rowNext[j + 1] = Math.max(fromLeft, fromTop);
      }
    }
  }

  let i = n;
  let j = m;
  let addedCount = 0;
  let removedCount = 0;

  const stack: DiffLine[] = [];
  while (i > 0 || j > 0) {
    const oldLine = i > 0 ? (oldLines[i - 1] ?? '') : '';
    const newLine = j > 0 ? (newLines[j - 1] ?? '') : '';
    const rowCurr = dp[i];
    const rowPrev = i > 0 ? dp[i - 1] : undefined;

    if (i > 0 && j > 0 && oldLine === newLine) {
      stack.push({ type: 'unchanged', text: oldLine });
      i--;
      j--;
    } else if (
      j > 0 &&
      (i === 0 || (rowCurr?.[j - 1] ?? 0) >= (rowPrev?.[j] ?? 0))
    ) {
      stack.push({ type: 'added', text: newLine });
      addedCount++;
      j--;
    } else if (i > 0) {
      stack.push({ type: 'removed', text: oldLine });
      removedCount++;
      i--;
    }
  }

  const lines: DiffLine[] = [];
  while (stack.length > 0) {
    const item = stack.pop();
    if (item) {
      lines.push(item);
    }
  }

  return { lines, addedCount, removedCount };
}

export function OutlineAndVersionsRail({
  pageId,
  projectKey = 'KAN',
  page,
  markdownContent,
  onAnnounce,
  activeTab: propActiveTab,
  onTabChange,
}: OutlineAndVersionsRailProps): JSX.Element {
  const queryClient = useQueryClient();
  const [internalTab, setInternalTab] = useState<'outline' | 'history'>('outline');
  const activeTab = propActiveTab ?? internalTab;

  const setActiveTab = (tab: 'outline' | 'history') => {
    setInternalTab(tab);
    onTabChange?.(tab);
  };
  const [activeHeadingAnchor, setActiveHeadingAnchor] = useState<string | null>(null);
  const [selectedVersionSeq, setSelectedVersionSeq] = useState<number | null>(null);
  const [versionViewMode, setVersionViewMode] = useState<'diff' | 'raw'>('diff');

  // Link picker state
  const [isLinkPickerOpen, setIsLinkPickerOpen] = useState(false);
  const [issueSearchQuery, setIssueSearchQuery] = useState('');
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);
  const [selectedLinkType, setSelectedLinkType] = useState<string>('VERIFIED_BY_DOC');
  const [linkError, setLinkError] = useState<string | null>(null);

  // Issues query for link picker
  const { data: projectIssues = [], isLoading: isLoadingIssues } = useQuery({
    queryKey: ['project-issues', projectKey],
    queryFn: () => fetchProjectIssues(projectKey),
    enabled: isLinkPickerOpen,
  });

  const filteredIssues = useMemo(() => {
    const q = issueSearchQuery.trim().toLowerCase();
    if (!q) return projectIssues;
    return projectIssues.filter(
      (issue) =>
        issue.key.toLowerCase().includes(q) || issue.title.toLowerCase().includes(q),
    );
  }, [projectIssues, issueSearchQuery]);

  // Extract headings live from current editor markdown (falling back to page.outline or page.body_markdown)
  const currentMarkdown = markdownContent ?? page?.body_markdown ?? '';
  const headings = useMemo(() => {
    return extractHeadings(currentMarkdown);
  }, [currentMarkdown]);

  // Version history query
  const {
    data: versions = [],
    isLoading: isLoadingVersions,
  } = useQuery({
    queryKey: ['docs', 'page', pageId, 'versions'],
    queryFn: () => fetchPageVersions(pageId),
    enabled: activeTab === 'history',
  });

  // Selected version detail for preview
  const selectedVersion = useMemo(() => {
    if (selectedVersionSeq === null) return null;
    return versions.find((v) => v.version_seq === selectedVersionSeq) ?? null;
  }, [versions, selectedVersionSeq]);

  const diffResult = useMemo(() => {
    if (!selectedVersion) {
      return { lines: [], addedCount: 0, removedCount: 0 };
    }
    return computeLineDiff(selectedVersion.body_markdown, currentMarkdown);
  }, [selectedVersion, currentMarkdown]);

  // Restore mutation
  const restoreMutation = useMutation({
    mutationFn: async (versionSeq: number) => {
      const currentEtag = page?.body_sha256 ? `"${page.body_sha256}"` : '*';
      return restorePageVersion(pageId, versionSeq, currentEtag);
    },
    onSuccess: (updatedPage) => {
      void queryClient.setQueryData(qk.page(pageId), updatedPage);
      void queryClient.invalidateQueries({ queryKey: ['docs', 'page', pageId, 'versions'] });
      setSelectedVersionSeq(null);
      setActiveTab('outline');
      onAnnounce?.(`Restored to v${String(updatedPage.version_seq)}`);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Restore failed';
      onAnnounce?.(`Restore error: ${msg}`);
    },
  });

  // Link issue mutation
  const linkMutation = useMutation({
    mutationFn: async ({ issueId, linkType }: { issueId: string; linkType: string }) => {
      try {
        return await createLink({
          source_id: issueId,
          target_id: pageId,
          link_type: linkType,
        });
      } catch {
        return await createLink({
          source_id: pageId,
          target_id: issueId,
          link_type: linkType,
        });
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.page(pageId) });
      setIsLinkPickerOpen(false);
      setIssueSearchQuery('');
      setSelectedIssueId(null);
      setLinkError(null);
      onAnnounce?.('Linked issue successfully');
    },
    onError: (err: unknown) => {
      setLinkError(err instanceof Error ? err.message : 'Failed to link issue');
    },
  });

  // Active section tracking via IntersectionObserver
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined' || headings.length === 0 || activeTab !== 'outline') return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveHeadingAnchor(entry.target.id);
            break;
          }
        }
      },
      { rootMargin: '-20px 0px -60% 0px', threshold: 0.1 },
    );

    const elements: HTMLElement[] = [];
    for (const h of headings) {
      const el = document.getElementById(h.anchor);
      if (el) {
        observer.observe(el);
        elements.push(el);
      }
    }

    return () => {
      for (const el of elements) {
        observer.unobserve(el);
      }
    };
  }, [headings, activeTab]);

  const handleHeadingClick = (anchor: string) => {
    setActiveHeadingAnchor(anchor);
    const target = document.getElementById(anchor);
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const objectLinks = page?.object_links ?? [];

  return (
    <aside className="docs-rail-pane" aria-label="Document Outline and History">
      {/* Tabs Header */}
      <div className="docs-rail-tabs" role="tablist" aria-label="Documentation Rail Tabs">
        <button
          type="button"
          role="tab"
          id="tab-outline"
          aria-selected={activeTab === 'outline'}
          aria-controls="panel-outline"
          className={`docs-rail-tab ${activeTab === 'outline' ? 'docs-rail-tab--active' : ''}`}
          onClick={() => {
            setActiveTab('outline');
          }}
          data-testid="rail-tab-outline"
        >
          Outline
        </button>
        <button
          type="button"
          role="tab"
          id="tab-history"
          aria-selected={activeTab === 'history'}
          aria-controls="panel-history"
          className={`docs-rail-tab ${activeTab === 'history' ? 'docs-rail-tab--active' : ''}`}
          onClick={() => {
            setActiveTab('history');
          }}
          data-testid="rail-tab-history"
        >
          History
        </button>
      </div>

      {/* OUTLINE TAB PANEL */}
      {activeTab === 'outline' && (
        <div
          id="panel-outline"
          role="tabpanel"
          aria-labelledby="tab-outline"
          className="docs-rail-panel"
        >
          <div className="docs-outline-section">
            <h2 className="docs-rail-heading">Headings</h2>
            {headings.length === 0 ? (
              <p className="docs-rail-empty">No headings found in document.</p>
            ) : (
              <nav aria-label="Page Table of Contents" className="docs-outline-nav">
                <ul className="docs-outline-list">
                  {headings.map((h, i) => {
                    const isActive = activeHeadingAnchor === h.anchor;
                    return (
                      <li
                        key={`${h.anchor}-${String(i)}`}
                        className={`docs-outline-item docs-outline-item--level-${String(h.level)}`}
                        data-level={h.level}
                      >
                        <a
                          href={`#${h.anchor}`}
                          className={`docs-outline-link ${isActive ? 'docs-outline-link--active' : ''}`}
                          aria-current={isActive ? 'location' : undefined}
                          onClick={(e) => {
                            e.preventDefault();
                            handleHeadingClick(h.anchor);
                          }}
                          data-testid={`outline-heading-${h.anchor}`}
                        >
                          {h.text}
                        </a>
                      </li>
                    );
                  })}
                </ul>
              </nav>
            )}
          </div>

          {/* Linked Work Items Section */}
          <div className="docs-linked-items-section">
            <div className="docs-linked-items-header">
              <h2 className="docs-rail-heading">Linked Work Items</h2>
              <button
                type="button"
                className="docs-tree-btn docs-tree-btn--secondary docs-open-link-picker-btn"
                data-testid="open-link-issue-picker-btn"
                onClick={() => {
                  setIsLinkPickerOpen(true);
                  setIssueSearchQuery('');
                  setSelectedIssueId(null);
                  setLinkError(null);
                }}
              >
                + Link Issue
              </button>
            </div>
            {objectLinks.length === 0 ? (
              <p className="docs-rail-empty">No linked issues.</p>
            ) : (
              <ul className="docs-linked-list" data-testid="docs-linked-work-items">
                {objectLinks.map((link, idx) => (
                  <li key={link.link_id ?? String(idx)} className="docs-linked-item">
                    <span className="docs-linked-chip mono">
                      {link.target_key ?? (link.source_id ?? 'LINK')}
                    </span>
                    {link.target_title && (
                      <span className="docs-linked-title" title={link.target_title}>
                        {link.target_title}
                      </span>
                    )}
                    {link.link_type === 'PROMOTED_TO_DOC' && (
                      <span className="docs-promoted-badge" title="Promoted from Sticky">
                        📄 Promoted
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Searchable Doc <-> Issue Link Picker Modal */}
      {isLinkPickerOpen && (
        <div
          className="docs-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Link issue to document"
          data-testid="doc-issue-link-picker"
        >
          <div className="docs-modal-dialog">
            <div className="docs-modal-header">
              <h3 className="docs-modal-title">Link Work Item to Document</h3>
              <button
                type="button"
                className="docs-modal-close-btn"
                onClick={() => {
                  setIsLinkPickerOpen(false);
                }}
                aria-label="Close dialog"
              >
                ✕
              </button>
            </div>

            <div className="docs-modal-body">
              {linkError && (
                <div className="docs-inline-error" role="alert" data-testid="link-issue-error">
                  {linkError}
                </div>
              )}

              <div className="docs-form-group">
                <label htmlFor="link-issue-search-input" className="docs-form-label">
                  Search Issue by Key or Title
                </label>
                <input
                  id="link-issue-search-input"
                  data-testid="link-issue-search-input"
                  className="docs-modal-input"
                  type="text"
                  placeholder="Search by key (e.g. KAN-1) or title..."
                  value={issueSearchQuery}
                  onChange={(e) => {
                    setIssueSearchQuery(e.target.value);
                  }}
                  autoFocus
                />
              </div>

              <div className="docs-form-group">
                <label htmlFor="link-issue-type-select" className="docs-form-label">
                  Relationship Type
                </label>
                <select
                  id="link-issue-type-select"
                  data-testid="link-issue-type-select"
                  className="docs-modal-input"
                  value={selectedLinkType}
                  onChange={(e) => {
                    setSelectedLinkType(e.target.value);
                  }}
                >
                  <option value="VERIFIED_BY_DOC">VERIFIED_BY_DOC (Verified by this doc)</option>
                  <option value="RELATES_TO">RELATES_TO (General reference)</option>
                </select>
              </div>

              <div className="docs-form-group">
                <span className="docs-form-label">Select Issue</span>
                {isLoadingIssues && <p className="docs-rail-empty">Loading issues...</p>}
                {!isLoadingIssues && filteredIssues.length === 0 && (
                  <p className="docs-rail-empty" data-testid="link-issue-empty">
                    No matching issues found.
                  </p>
                )}
                <ul className="docs-issue-picker-list" data-testid="link-issue-search-results">
                  {filteredIssues.map((issue) => {
                    const isSelected = selectedIssueId === issue.id;
                    return (
                      <li
                        key={issue.id}
                        className={`docs-issue-picker-item ${isSelected ? 'docs-issue-picker-item--selected' : ''}`}
                        onClick={() => {
                          setSelectedIssueId(issue.id);
                        }}
                        data-testid={`link-issue-result-${issue.key}`}
                      >
                        <span className="docs-linked-chip mono">{issue.key}</span>
                        <span className="docs-issue-picker-title">{issue.title}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>

            <div className="docs-modal-actions">
              <button
                type="button"
                className="docs-tree-btn"
                onClick={() => {
                  setIsLinkPickerOpen(false);
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="docs-tree-btn docs-tree-btn--primary"
                data-testid="confirm-link-issue-btn"
                disabled={!selectedIssueId || linkMutation.isPending}
                onClick={() => {
                  if (selectedIssueId) {
                    linkMutation.mutate({ issueId: selectedIssueId, linkType: selectedLinkType });
                  }
                }}
              >
                {linkMutation.isPending ? 'Linking...' : 'Link Issue'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* HISTORY TAB PANEL */}
      {activeTab === 'history' && (
        <div
          id="panel-history"
          role="tabpanel"
          aria-labelledby="tab-history"
          className="docs-rail-panel"
        >
          <div className="docs-history-section">
            <h2 className="docs-rail-heading">Version History</h2>
            {isLoadingVersions && (
              <p className="docs-rail-empty" data-testid="versions-loading">
                Loading versions...
              </p>
            )}
            {!isLoadingVersions && versions.length === 0 && (
              <p className="docs-rail-empty">No prior versions recorded.</p>
            )}
            <ul className="docs-version-list" data-testid="version-history-list">
              {versions.map((ver) => {
                const isSelected = selectedVersionSeq === ver.version_seq;
                const shortDigest = ver.body_sha256 ? ver.body_sha256.slice(0, 8) : 'unknown';
                return (
                  <li
                    key={ver.version_seq}
                    className={`docs-version-item ${isSelected ? 'docs-version-item--selected' : ''}`}
                    onClick={() => {
                      setSelectedVersionSeq(ver.version_seq);
                    }}
                    data-testid={`version-item-v${String(ver.version_seq)}`}
                  >
                    <div className="docs-version-item__top">
                      <span className="docs-version-item__seq mono">v{ver.version_seq}</span>
                      <span className="docs-version-item__digest mono" title={ver.body_sha256}>
                        {shortDigest}
                      </span>
                    </div>
                    <div className="docs-version-item__meta">
                      <span className="docs-version-item__author">
                        {ver.created_by_id ?? 'author'}
                      </span>
                      <time className="docs-version-item__time">
                        {new Date(ver.created_at).toLocaleDateString()}
                      </time>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Read-only Preview / Diff of Selected Version */}
          {selectedVersion && (
            <div className="docs-version-preview" data-testid="version-preview-pane">
              <div className="docs-version-preview__header">
                <span className="docs-version-preview__title mono">
                  v{selectedVersion.version_seq} Preview
                </span>
                <button
                  type="button"
                  className="docs-tree-btn docs-tree-btn--primary docs-version-restore-btn"
                  onClick={() => {
                    restoreMutation.mutate(selectedVersion.version_seq);
                  }}
                  disabled={restoreMutation.isPending}
                  data-testid={`restore-v${String(selectedVersion.version_seq)}-btn`}
                  aria-label={`Restore v${String(selectedVersion.version_seq)}`}
                >
                  {restoreMutation.isPending
                    ? 'Restoring...'
                    : `Restore v${String(selectedVersion.version_seq)}`}
                </button>
              </div>

              {/* Diff vs Raw Toggle */}
              <div className="docs-version-view-mode-toggle" role="tablist" aria-label="Version View Mode">
                <button
                  type="button"
                  role="tab"
                  aria-selected={versionViewMode === 'diff'}
                  className={`docs-version-view-btn ${versionViewMode === 'diff' ? 'docs-version-view-btn--active' : ''}`}
                  onClick={() => {
                    setVersionViewMode('diff');
                  }}
                  data-testid="version-view-diff-tab"
                >
                  Diff vs Current
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={versionViewMode === 'raw'}
                  className={`docs-version-view-btn ${versionViewMode === 'raw' ? 'docs-version-view-btn--active' : ''}`}
                  onClick={() => {
                    setVersionViewMode('raw');
                  }}
                  data-testid="version-view-raw-tab"
                >
                  Raw Content
                </button>
              </div>

              {versionViewMode === 'diff' && (
                <div className="docs-diff-container" data-testid="version-diff-container">
                  <div className="docs-diff-stats" data-testid="version-diff-stats">
                    +{diffResult.addedCount} -{diffResult.removedCount} lines changed
                  </div>
                  <div className="docs-diff-viewer" data-testid="version-diff-viewer">
                    {diffResult.lines.map((line, idx) => (
                      <div
                        key={idx}
                        className={`docs-diff-line docs-diff-line--${line.type}`}
                        data-type={line.type}
                      >
                        <span className="docs-diff-prefix">
                          {line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' '}
                        </span>
                        <span className="docs-diff-text">{line.text || '\u00A0'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <pre
                className={`docs-version-preview__body mono ${versionViewMode === 'diff' ? 'sr-only' : ''}`}
                data-testid="version-preview-body"
              >
                {selectedVersion.body_markdown}
              </pre>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
