// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, {
  useEffect,
  useRef,
  useState,
  type JSX,
  type ChangeEvent,
} from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router';
import { DocMarkdownViewer } from './DocMarkdownViewer';
import {
  CHAPTER_BY_SLUG,
  getChapter,
  resolveChapterSlug,
  resolveSectionElement,
  searchDocs,
  WIKI_CATEGORIES,
  WIKI_CHAPTERS,
  type SearchResult,
  type WikiChapter,
  type WikiChapterCategory,
} from './docsService';
import { formatDocumentTitle, useDocumentTitle } from '../../app/documentTitle';
import { useFocusTrap } from '../drawer/useFocusTrap';
import { buildAgentOnboardingPrompt } from '../settings/agentOnboardingPrompt';
import { copyToClipboard } from '../../utils/clipboard';
import './DocsCenterPage.css';

export type CategoryFilter = 'all' | WikiChapterCategory;

export function DocsCenterPage(): JSX.Element {
  const { slug: rawSlug } = useParams<{ slug?: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  const currentSlug = resolveChapterSlug(rawSlug ?? 'home');
  const fallbackChapter: WikiChapter = {
    slug: 'home',
    title: 'Documentation',
    category: 'informational',
    track: 'Overview',
    subtrack: 'Overview',
    audience: 'All Users',
    order: 1,
    summary: 'System documentation overview.',
    sections: [],
    content: '# Documentation\n\nNo content available.',
  };
  const chapter: WikiChapter =
    getChapter(currentSlug) ?? WIKI_CHAPTERS[0] ?? fallbackChapter;

  useDocumentTitle(
    formatDocumentTitle(['Docs', chapter.title !== 'Documentation' ? chapter.title : null]),
  );

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isMobileChaptersOpen, setIsMobileChaptersOpen] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>('all');
  const [isCopiedPrompt, setIsCopiedPrompt] = useState(false);

  const activeAnchor = location.hash.replace(/^#+/, '') || null;

  const contentRef = useRef<HTMLDivElement | null>(null);
  const searchContainerRef = useRef<HTMLDivElement | null>(null);
  const mobileChaptersBtnRef = useRef<HTMLButtonElement | null>(null);
  const mobileChaptersDrawerRef = useRef<HTMLElement | null>(null);
  const wasMobileChaptersOpenRef = useRef<boolean>(false);

  useFocusTrap(isMobileChaptersOpen, mobileChaptersDrawerRef);

  useEffect(() => {
    if (wasMobileChaptersOpenRef.current && !isMobileChaptersOpen) {
      mobileChaptersBtnRef.current?.focus();
    }
    wasMobileChaptersOpenRef.current = isMobileChaptersOpen;
  }, [isMobileChaptersOpen]);

  // Close mobile chapters drawer on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape' && isMobileChaptersOpen) {
        setIsMobileChaptersOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isMobileChaptersOpen]);

  // Scroll to anchor on hash change or navigation
  const scrollToAnchor = (anchorId: string): void => {
    /* v8 ignore next */
    if (!contentRef.current) return;
    const targetEl = resolveSectionElement(contentRef.current, anchorId);
    if (targetEl) {
      const prefersReducedMotion =
        typeof window !== 'undefined' &&
        typeof window.matchMedia === 'function' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      targetEl.scrollIntoView({
        behavior: prefersReducedMotion ? 'auto' : 'smooth',
        block: 'start',
      });
    }
  };

  useEffect(() => {
    const rawHash = location.hash.replace(/^#+/, '');
    if (rawHash) {
      const timer = window.setTimeout(() => {
        scrollToAnchor(rawHash);
      }, 50);
      return () => {
        window.clearTimeout(timer);
      };
    } else {
      const prefersReducedMotion =
        typeof window !== 'undefined' &&
        typeof window.matchMedia === 'function' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      window.scrollTo({ top: 0, behavior: prefersReducedMotion ? 'auto' : 'smooth' });
    }
  }, [location.hash, currentSlug]);

  // Instant client-side search
  const handleSearchChange = (e: ChangeEvent<HTMLInputElement>): void => {
    const q = e.target.value;
    setSearchQuery(q);
    if (q.trim().length > 0) {
      const results = searchDocs(q, 8);
      setSearchResults(results);
      setIsSearchOpen(true);
    } else {
      setSearchResults([]);
      setIsSearchOpen(false);
    }
  };

  // Close search dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent): void => {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(e.target as Node)
      ) {
        setIsSearchOpen(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, []);

  // Compute Prev / Next chapters
  const currentIndex = WIKI_CHAPTERS.findIndex((c) => c.slug === chapter.slug);
  const prevChapter = currentIndex > 0 ? WIKI_CHAPTERS[currentIndex - 1] : null;
  const nextChapter =
    currentIndex !== -1 && currentIndex < WIKI_CHAPTERS.length - 1
      ? WIKI_CHAPTERS[currentIndex + 1]
      : null;

  // Filter categories and chapters by selected category filter
  const filteredCategories = WIKI_CATEGORIES.map((cat) => {
    const chapters = cat.chapters.filter((ch) => {
      if (categoryFilter === 'all') return true;
      const chapterData = CHAPTER_BY_SLUG[ch.slug];
      /* v8 ignore next */
      const catType = ch.category ?? chapterData?.category;
      return catType === categoryFilter;
    });
    return { ...cat, chapters };
  }).filter((cat) => cat.chapters.length > 0);

  const formatCategoryBadge = (cat?: string): string => {
    const lower = (cat ?? '').toLowerCase();
    if (lower === 'guide') return '[Guide]';
    if (lower === 'architectural') return '[Architectural]';
    return '[Informational]';
  };

  const stripCategoryPrefix = (title: string): string =>
    title.replace(/^\[(Guide|Informational|Architectural)\]\s+/i, '');

  const renderFilterTabs = (): JSX.Element => (
    <div
      className="kb-docs-filter-tabs docs-category-filter-bar"
      role="tablist"
      aria-label="Documentation category filters"
      data-testid="docs-category-filter-bar"
    >
      <button
        type="button"
        role="tab"
        aria-selected={categoryFilter === 'all'}
        className={`kb-docs-filter-tab ${categoryFilter === 'all' ? 'active' : ''}`}
        data-testid="docs-filter-all"
        onClick={() => {
          setCategoryFilter('all');
        }}
      >
        All
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={categoryFilter === 'guide'}
        className={`kb-docs-filter-tab ${categoryFilter === 'guide' ? 'active' : ''}`}
        data-testid="docs-filter-guide"
        onClick={() => {
          setCategoryFilter('guide');
        }}
      >
        Guides
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={categoryFilter === 'informational'}
        className={`kb-docs-filter-tab ${categoryFilter === 'informational' ? 'active' : ''}`}
        data-testid="docs-filter-informational"
        onClick={() => {
          setCategoryFilter('informational');
        }}
      >
        Informational
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={categoryFilter === 'architectural'}
        className={`kb-docs-filter-tab ${categoryFilter === 'architectural' ? 'active' : ''}`}
        data-testid="docs-filter-architectural"
        onClick={() => {
          setCategoryFilter('architectural');
        }}
      >
        Architectural
      </button>
    </div>
  );

  const handleSkipToMain = (e: React.MouseEvent<HTMLAnchorElement>): void => {
    e.preventDefault();
    const mainEl = document.getElementById('main') ?? contentRef.current;
    if (mainEl) {
      mainEl.focus();
    }
  };

  const handleCopyAgentPrompt = async (): Promise<void> => {
    const prompt = buildAgentOnboardingPrompt();
    const ok = await copyToClipboard(prompt);
    if (ok) {
      setIsCopiedPrompt(true);
      window.setTimeout(() => {
        setIsCopiedPrompt(false);
      }, 2000);
    }
  };

  return (
    <div className="kb-docs-page" data-testid="docs-center-page">
      {/* Skip to Content Link (A11y) */}
      <a
        href="#main"
        className="kb-skip-link"
        onClick={handleSkipToMain}
      >
        Skip to content
      </a>

      {/* Top Header */}
      <header className="kb-docs-header">
        <h1 className="sr-only">Kanban Documentation Center</h1>
        <div className="kb-docs-header-row-1">
          <div className="kb-docs-header-left">
            <Link to="/" className="kb-docs-logo" aria-label="Return to Board">
              <span role="img" aria-label="Kanban">
                &#128077;
              </span>{' '}
              Kanban Docs
            </Link>
            <span className="kb-docs-badge">Offline Center</span>
            <a
              href="/llms.txt"
              target="_blank"
              rel="noopener noreferrer"
              className="kb-docs-llms-txt-link"
              data-testid="docs-llms-txt-link"
            >
              <span aria-hidden="true">&#129302;</span> /llms.txt
            </a>
            <button
              type="button"
              className="kb-docs-copy-prompt-btn"
              data-testid="docs-copy-agent-prompt-btn"
              title="Copy Agent Onboarding Prompt"
              onClick={() => {
                void handleCopyAgentPrompt();
              }}
            >
              <span aria-hidden="true">&#128203;</span> {isCopiedPrompt ? 'Copied!' : 'Copy Agent Prompt'}
            </button>
          </div>

          <button
            ref={mobileChaptersBtnRef}
            type="button"
            className="kb-docs-mobile-chapters-btn"
            data-testid="docs-mobile-chapters-btn"
            aria-expanded={isMobileChaptersOpen}
            aria-label="Toggle chapters navigation"
            onClick={() => {
              setIsMobileChaptersOpen((prev) => !prev);
            }}
          >
            <span aria-hidden="true">&#128218;</span> Chapters
          </button>
        </div>

        <div ref={searchContainerRef} className="kb-docs-search-container">
          <span className="kb-docs-search-icon" aria-hidden="true">
            &#128269;
          </span>
          <input
            type="search"
            className="kb-docs-search-input"
            data-testid="docs-search-input"
            placeholder="Search offline docs..."
            value={searchQuery}
            onChange={handleSearchChange}
            onFocus={() => {
              if (searchQuery.trim().length > 0) {
                setIsSearchOpen(true);
              }
            }}
            aria-label="Search documentation"
          />

          {isSearchOpen && searchResults.length > 0 && (
            <div
              className="kb-docs-search-dropdown"
              data-testid="docs-search-results"
              role="listbox"
            >
              {searchResults.map((res) => {
                const targetUrl = `/docs/${res.slug}${res.matchedSection ? `#${res.matchedSection.id}` : ''}`;
                return (
                  <Link
                    key={`${res.slug}-${res.matchedSection?.id ?? 'main'}`}
                    to={targetUrl}
                    className="kb-docs-search-item"
                    role="option"
                    aria-selected={false}
                    onClick={() => {
                      setIsSearchOpen(false);
                      setSearchQuery('');
                    }}
                  >
                    <div className="kb-docs-search-item-title">
                      {res.title}
                      {res.matchedSection && ` > ${res.matchedSection.title}`}
                    </div>
                    <div className="kb-docs-search-item-cat">
                      <span className={`kb-docs-badge-pill kb-badge-${res.category.toLowerCase()}`}>
                        {formatCategoryBadge(res.category)}
                      </span>
                    </div>
                    <div className="kb-docs-search-item-snippet">{res.snippet}</div>
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      </header>

      {/* Mobile & Tablet Chapters Slide-Over Drawer */}
      {isMobileChaptersOpen && (
        <>
          <div
            className="kb-docs-mobile-drawer-backdrop"
            data-testid="docs-mobile-drawer-backdrop"
            onClick={() => {
              setIsMobileChaptersOpen(false);
            }}
            aria-hidden="true"
          />
          <aside
            ref={mobileChaptersDrawerRef}
            className="kb-docs-mobile-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Documentation Chapters"
            data-testid="docs-mobile-chapters-drawer"
          >
            <div className="kb-docs-mobile-drawer-header">
              <h2 className="kb-docs-mobile-drawer-title">Chapters</h2>
              <button
                type="button"
                className="kb-docs-mobile-drawer-close"
                data-testid="docs-mobile-drawer-close"
                aria-label="Close chapters drawer"
                onClick={() => {
                  setIsMobileChaptersOpen(false);
                }}
              >
                &#10005;
              </button>
            </div>
            {renderFilterTabs()}
            <nav className="kb-docs-mobile-drawer-nav" aria-label="Mobile Chapters Navigation">
              {filteredCategories.map((cat) => (
                <div key={cat.name} className="kb-docs-cat-group">
                  <div className="kb-docs-cat-title">{cat.name}</div>
                  <ul className="kb-docs-nav-list">
                    {cat.chapters.map((ch) => {
                      const isActive = ch.slug === chapter.slug;
                      return (
                        <li key={ch.slug}>
                          <Link
                            to={`/docs/${ch.slug}`}
                            className={`kb-docs-nav-link ${isActive ? 'active' : ''}`}
                            aria-current={isActive ? 'page' : undefined}
                            onClick={() => {
                              setIsMobileChaptersOpen(false);
                            }}
                          >
                            <span className="kb-docs-nav-link-text">{stripCategoryPrefix(ch.title)}</span>
                            {/* v8 ignore next */}
                            <span
                              className={`kb-docs-badge-pill kb-badge-${ch.category ?? 'informational'}`}
                            >
                              {formatCategoryBadge(ch.category)}
                            </span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </nav>
          </aside>
        </>
      )}

      {/* Main Body Layout */}
      <div className="kb-docs-layout">
        {/* Navigation Sidebar */}
        <nav
          className="kb-docs-sidebar"
          aria-label="Documentation Chapters"
          data-testid="docs-categories-sidebar"
        >
          {renderFilterTabs()}
          {filteredCategories.map((cat) => (
            <div key={cat.name} className="kb-docs-cat-group">
              <div className="kb-docs-cat-title">{cat.name}</div>
              <ul className="kb-docs-nav-list">
                {cat.chapters.map((ch) => {
                  const isActive = ch.slug === chapter.slug;
                  return (
                    <li key={ch.slug}>
                      <Link
                        to={`/docs/${ch.slug}`}
                        className={`kb-docs-nav-link ${isActive ? 'active' : ''}`}
                        aria-current={isActive ? 'page' : undefined}
                      >
                        <span className="kb-docs-nav-link-text">{stripCategoryPrefix(ch.title)}</span>
                        {/* v8 ignore next */}
                        <span
                          className={`kb-docs-badge-pill kb-badge-${ch.category ?? 'informational'}`}
                        >
                          {formatCategoryBadge(ch.category)}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* Content Area */}
        <main
          id="main"
          tabIndex={-1}
          className="kb-docs-main"
          ref={contentRef}
          data-testid="docs-main-content"
        >
          <div className="kb-docs-content-wrapper">
            <div className="kb-docs-meta-bar" data-testid="docs-meta-bar">
              <span
                className={`kb-docs-badge-pill kb-badge-${chapter.category}`}
                data-testid="docs-category-badge"
              >
                {formatCategoryBadge(chapter.category)}
              </span>
              <span className="kb-docs-meta-track">{chapter.track}</span>
              {chapter.subtrack && (
                <span className="kb-docs-meta-subtrack">{chapter.subtrack}</span>
              )}
              <span className="kb-docs-meta-audience">{chapter.audience}</span>
              <span className="kb-docs-meta-order">
                Chapter {chapter.order} of {WIKI_CHAPTERS.length}
              </span>
            </div>

            <DocMarkdownViewer
              content={chapter.content}
              testId="docs-markdown-viewer"
              onNavigateSection={(secId) => {
                void navigate(`/docs/${chapter.slug}#${secId}`);
                scrollToAnchor(secId);
              }}
              onNavigateDoc={(href) => {
                void navigate(href);
              }}
            />

            {/* Pagination Controls */}
            <nav className="kb-docs-pagination" aria-label="Chapter Pagination">
              {prevChapter ? (
                <Link
                  to={`/docs/${prevChapter.slug}`}
                  className="kb-docs-pager-btn"
                  data-testid="docs-prev-chapter"
                >
                  <span className="kb-docs-pager-label">&larr; Previous Chapter</span>
                  <span className="kb-docs-pager-title">{prevChapter.title}</span>
                </Link>
              ) : (
                <div />
              )}

              {nextChapter ? (
                <Link
                  to={`/docs/${nextChapter.slug}`}
                  className="kb-docs-pager-btn"
                  data-testid="docs-next-chapter"
                >
                  <span className="kb-docs-pager-label">Next Chapter &rarr;</span>
                  <span className="kb-docs-pager-title">{nextChapter.title}</span>
                </Link>
              ) : (
                <div />
              )}
            </nav>
          </div>
        </main>

        {/* Right Section TOC Rail */}
        {chapter.sections.length > 0 && (
          <aside
            className="kb-docs-toc-rail"
            aria-label="On this page"
            data-testid="docs-toc-rail"
          >
            <div className="kb-docs-toc-title">On This Page</div>
            <ul className="kb-docs-toc-list">
              {chapter.sections.map((sec, secIdx) => (
                <li
                  key={`${sec.id}-${String(secIdx)}`}
                  className={`kb-docs-toc-item level-${String(sec.level)}`}
                >
                  <a
                    href={`#${sec.id}`}
                    className={`kb-docs-toc-link ${activeAnchor === sec.id ? 'active' : ''}`}
                    onClick={(e) => {
                      e.preventDefault();
                      void navigate(`/docs/${chapter.slug}#${sec.id}`);
                      scrollToAnchor(sec.id);
                    }}
                  >
                    {sec.title.replace(/`/g, '')}
                  </a>
                </li>
              ))}
            </ul>
          </aside>
        )}
      </div>
    </div>
  );
}
