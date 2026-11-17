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

export function OutlineAndVersionsRail({
  pageId,
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
            <h3 className="docs-rail-heading">Headings</h3>
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
            <h3 className="docs-rail-heading">Linked Work Items</h3>
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

      {/* HISTORY TAB PANEL */}
      {activeTab === 'history' && (
        <div
          id="panel-history"
          role="tabpanel"
          aria-labelledby="tab-history"
          className="docs-rail-panel"
        >
          <div className="docs-history-section">
            <h3 className="docs-rail-heading">Version History</h3>
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

          {/* Read-only Preview of Selected Version */}
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
                >
                  {restoreMutation.isPending
                    ? 'Restoring...'
                    : `Restore v${String(selectedVersion.version_seq)}`}
                </button>
              </div>
              <pre className="docs-version-preview__body mono" data-testid="version-preview-body">
                {selectedVersion.body_markdown}
              </pre>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
