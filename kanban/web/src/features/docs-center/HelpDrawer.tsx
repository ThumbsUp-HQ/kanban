// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, {
  useEffect,
  useRef,
  useState,
  type JSX,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { useNavigate } from 'react-router';
import { DocMarkdownViewer } from './DocMarkdownViewer';
import {
  getChapter,
  parseDocHref,
  WIKI_CHAPTERS,
  type WikiChapter,
} from './docsService';
import './HelpDrawer.css';

export interface HelpDrawerArg {
  href?: string;
  slug?: string;
  anchor?: string;
  title?: string;
}

export interface HelpDrawerProps {
  arg?: unknown;
  onClose: () => void;
}

export function HelpDrawer({ arg, onClose }: HelpDrawerProps): JSX.Element {
  const navigate = useNavigate();
  const drawerRef = useRef<HTMLDivElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const previousActiveElementRef = useRef<HTMLElement | null>(null);

  const parsedArg: HelpDrawerArg =
    typeof arg === 'object' && arg !== null ? arg : {};

  const { slug: resolvedSlug, anchor: resolvedAnchor } = parsedArg.href
    ? parseDocHref(parsedArg.href)
    : {
        slug: parsedArg.slug ?? 'guide-custom-fields',
        anchor: parsedArg.anchor,
      };

  const [activeSlug, setActiveSlug] = useState<string>(resolvedSlug);
  const [activeAnchor, setActiveAnchor] = useState<string | undefined>(resolvedAnchor);

  // Resync activeSlug and activeAnchor if arg changes while already mounted
  const [prevResolvedSlug, setPrevResolvedSlug] = useState(resolvedSlug);
  const [prevResolvedAnchor, setPrevResolvedAnchor] = useState(resolvedAnchor);

  if (resolvedSlug !== prevResolvedSlug || resolvedAnchor !== prevResolvedAnchor) {
    setPrevResolvedSlug(resolvedSlug);
    setPrevResolvedAnchor(resolvedAnchor);
    setActiveSlug(resolvedSlug);
    setActiveAnchor(resolvedAnchor);
  }

  // Save document.activeElement on open and restore on unmount
  useEffect(() => {
    previousActiveElementRef.current = document.activeElement as HTMLElement | null;
    return () => {
      if (
        previousActiveElementRef.current &&
        typeof previousActiveElementRef.current.focus === 'function'
      ) {
        previousActiveElementRef.current.setAttribute('data-kb-suppress-focus', 'true');
        previousActiveElementRef.current.focus();
      }
    };
  }, []);

  // Move initial focus into the dialog on open
  useEffect(() => {
    const timer = window.setTimeout(() => {
      /* v8 ignore next 5 */
      if (closeButtonRef.current) {
        closeButtonRef.current.focus();
      } else if (drawerRef.current) {
        drawerRef.current.focus();
      }
    }, 10);
    return () => {
      window.clearTimeout(timer);
    };
  }, []);

  /* v8 ignore next 14 */
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
  /* v8 ignore next */
  const chapter: WikiChapter =
    getChapter(activeSlug) ?? WIKI_CHAPTERS[0] ?? fallbackChapter;

  // Scroll to section when anchor is set or changes
  const scrollToAnchor = (anchorId: string): void => {
    setActiveAnchor(anchorId);
    /* v8 ignore next */
    if (!bodyRef.current) return;
    const targetEl = bodyRef.current.querySelector(`#${anchorId}`);
    if (targetEl) {
      targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  useEffect(() => {
    if (activeAnchor) {
      // Delay slightly for DOM to settle
      const timer = window.setTimeout(() => {
        scrollToAnchor(activeAnchor);
      }, 50);
      return () => {
        window.clearTimeout(timer);
      };
    }
  }, [activeAnchor, activeSlug]);

  // Global Escape and Tab focus trap listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key === 'Tab' && drawerRef.current) {
        const focusableElements = drawerRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        /* v8 ignore next */
        if (focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];
        /* v8 ignore next */
        if (!firstElement || !lastElement) return;

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  const handleOpenInDocs = (): void => {
    const targetUrl = `/docs/${chapter.slug}${activeAnchor ? `#${activeAnchor}` : ''}`;
    onClose();
    void navigate(targetUrl);
  };

  const handleTrapKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
    }
  };

  return (
    <>
      <div
        className="kb-help-drawer-backdrop"
        onClick={onClose}
        aria-hidden="true"
        data-testid="help-drawer-backdrop"
      />
      <aside
        ref={drawerRef}
        className="kb-help-drawer"
        role="dialog"
        aria-label={`Help: ${chapter.title}`}
        aria-modal="true"
        data-testid="help-drawer"
        tabIndex={-1}
        onKeyDown={handleTrapKeyDown}
      >
        <header className="kb-help-drawer-header">
          <div className="kb-help-drawer-title-group">
            <span
              className={`kb-help-drawer-badge kb-badge-${chapter.category}`}
              data-testid="help-drawer-category-badge"
            >
              {chapter.category === 'guide'
                ? '[Guide]'
                : chapter.category === 'architectural'
                ? '[Architectural]'
                : '[Informational]'}
            </span>
            <h2 className="kb-help-drawer-title">{chapter.title}</h2>
          </div>
          <div className="kb-help-drawer-actions">
            <button
              type="button"
              className="kb-help-drawer-open-btn"
              data-testid="help-drawer-open-docs"
              onClick={handleOpenInDocs}
              aria-label="Open in full documentation center"
            >
              Open in /docs -&gt;
            </button>
            <button
              ref={closeButtonRef}
              type="button"
              className="kb-help-drawer-close-btn"
              data-testid="help-drawer-close-btn"
              aria-label="Close help drawer"
              onClick={onClose}
            >
              &#10005;
            </button>
          </div>
        </header>

        <div ref={bodyRef} className="kb-help-drawer-body" data-testid="help-drawer-body">
          {chapter.sections.length > 0 && (
            <nav className="kb-help-drawer-toc" aria-label="Chapter Table of Contents">
              <div className="kb-help-drawer-toc-title">Sections</div>
              <ul className="kb-help-drawer-toc-list">
                {chapter.sections.map((sec, secIdx) => (
                  <li key={`${sec.id}-${String(secIdx)}`}>
                    <a
                      href={`#${sec.id}`}
                      className={`kb-help-drawer-toc-link ${activeAnchor === sec.id ? 'active' : ''}`}
                      onClick={(e) => {
                        e.preventDefault();
                        scrollToAnchor(sec.id);
                      }}
                    >
                      {sec.title.replace(/`/g, '')}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          )}

          <DocMarkdownViewer
            content={chapter.content}
            testId="help-drawer-markdown"
            onNavigateSection={scrollToAnchor}
          />
        </div>

        <footer className="kb-help-drawer-footer">
          <span className="kb-help-drawer-footer-text">
            Offline Documentation &bull; Chapter {chapter.order} of {WIKI_CHAPTERS.length}
          </span>
          <button
            type="button"
            className="kb-help-drawer-open-btn"
            onClick={handleOpenInDocs}
          >
            Full Page View
          </button>
        </footer>
      </aside>
    </>
  );
}
