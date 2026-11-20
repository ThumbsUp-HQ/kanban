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
  getChapter,
  resolveChapterSlug,
  searchDocs,
  slugifyAnchor,
  WIKI_CATEGORIES,
  WIKI_CHAPTERS,
  type SearchResult,
  type WikiChapter,
} from './docsService';
import './DocsCenterPage.css';

export function DocsCenterPage(): JSX.Element {
  const { slug: rawSlug } = useParams<{ slug?: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  const currentSlug = resolveChapterSlug(rawSlug ?? 'home');
  /* v8 ignore next 9 */
  const chapter: WikiChapter =
    getChapter(currentSlug) ?? WIKI_CHAPTERS[0] ?? {
      slug: 'home',
      title: 'Documentation',
      category: 'Overview',
      order: 1,
      summary: 'System documentation overview.',
      sections: [],
      content: '# Documentation\n\nNo content available.',
    };

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isMobileChaptersOpen, setIsMobileChaptersOpen] = useState(false);

  const activeAnchor = location.hash.replace(/^#+/, '') || null;

  const contentRef = useRef<HTMLDivElement | null>(null);
  const searchContainerRef = useRef<HTMLDivElement | null>(null);

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
    const cleanId = slugifyAnchor(anchorId);
    /* v8 ignore next */
    if (!contentRef.current) return;
    const targetEl = contentRef.current.querySelector(`#${cleanId}`);
    if (targetEl) {
      targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
      window.scrollTo({ top: 0, behavior: 'smooth' });
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

  return (
    <div className="kb-docs-page" data-testid="docs-center-page">
      {/* Top Header */}
      <header className="kb-docs-header">
        <div className="kb-docs-header-row-1">
          <div className="kb-docs-header-left">
            <Link to="/" className="kb-docs-logo" aria-label="Return to Board">
              <span role="img" aria-label="Kanban">
                &#128077;
              </span>{' '}
              Kanban Docs
            </Link>
            <span className="kb-docs-badge">Offline Center</span>
          </div>

          <button
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
                    <div className="kb-docs-search-item-cat">{res.category}</div>
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
            <nav className="kb-docs-mobile-drawer-nav" aria-label="Mobile Chapters Navigation">
              {WIKI_CATEGORIES.map((cat) => (
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
                            {ch.title}
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
          {WIKI_CATEGORIES.map((cat) => (
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
                        {ch.title}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* Content Area */}
        <main className="kb-docs-main" ref={contentRef} data-testid="docs-main-content">
          <div className="kb-docs-content-wrapper">
            <div className="kb-docs-meta-bar">
              <span>{chapter.category}</span>
              <span>
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
