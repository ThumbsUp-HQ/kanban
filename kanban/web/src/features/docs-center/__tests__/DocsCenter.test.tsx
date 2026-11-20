// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';

// Mock MermaidBlockView to avoid background web-worker invocation in unit tests
vi.mock('../../../editor/mermaid/MermaidBlockView', () => ({
  MermaidBlockView: ({ source, readOnly }: { source: string; readOnly?: boolean }) => (
    <div data-testid="mock-mermaid-block-view" data-readonly={String(readOnly)}>
      {source}
    </div>
  ),
}));

import * as docsCenterIndex from '../index';
import * as helpIndex from '../../help/index';
import {
  searchDocs,
  slugifyAnchor,
  parseDocHref,
  resolveChapterSlug,
  getChapter,
  getAllChapters,
  getChapterCategories,
  getConfigReference,
  WIKI_CHAPTERS,
  CHAPTER_BY_SLUG,
} from '../docsService';
import {
  DocMarkdownViewer,
  renderInlineMarkdown,
  resolveSafeDocImageUrl,
} from '../DocMarkdownViewer';
import { HelpDrawer } from '../HelpDrawer';
import { DocsCenterPage } from '../DocsCenterPage';
import { StudioDocLink } from '../../../components/help/StudioDocLink';
import { FieldHelpHint } from '../../../components/help/FieldHelpHint';
import {
  registerShellPanel,
  ShellPanelsProvider,
} from '../../../app/shellPanels';

describe('DocsCenter & Help System (KAN-16)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.scrollTo = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = vi.fn();
  });

  describe('docs-center & help module re-exports', () => {
    it('exports all public symbols from docs-center and help index files', () => {
      expect(docsCenterIndex.DocsCenterPage).toBeDefined();
      expect(docsCenterIndex.HelpDrawer).toBeDefined();
      expect(docsCenterIndex.DocMarkdownViewer).toBeDefined();
      expect(docsCenterIndex.searchDocs).toBeDefined();
      expect(docsCenterIndex.slugifyAnchor).toBeDefined();

      expect(helpIndex.HelpDrawer).toBeDefined();
      expect(helpIndex.DocMarkdownViewer).toBeDefined();
      expect(helpIndex.searchDocs).toBeDefined();
      expect(helpIndex.getChapter).toBeDefined();
    });
  });

  describe('docsService (Offline Search & Resolver Engine)', () => {
    it('slugifies headers and anchor strings into clean ASCII identifiers', () => {
      expect(slugifyAnchor('1. Introduction to WebAuthn / Passkeys')).toBe(
        'introduction-to-webauthn-passkeys',
      );
      expect(slugifyAnchor('Why Offline-First (Priority #0)?')).toBe(
        'why-offline-first-priority-0',
      );
      expect(slugifyAnchor('   Multiple    Spaces & Special! Characters@#$   ')).toBe(
        'multiple-spaces-special-characters',
      );
      expect(slugifyAnchor('')).toBe('section');
    });

    it('parses diverse doc hrefs into chapter slugs and anchors', () => {
      expect(parseDocHref('')).toEqual({ slug: 'home' });
      expect(parseDocHref('#custom-fields')).toEqual({
        slug: 'guide-custom-fields',
        anchor: 'custom-fields',
      });
      expect(parseDocHref('/docs/role-and-permission-matrix')).toEqual({
        slug: 'role-and-permission-matrix',
        anchor: undefined,
      });
      expect(parseDocHref('/docs/role-and-permission-matrix#workspace-admin')).toEqual({
        slug: 'role-and-permission-matrix',
        anchor: 'workspace-admin',
      });
      expect(parseDocHref('/help/guide-custom-fields#sandbox-limits')).toEqual({
        slug: 'guide-custom-fields',
        anchor: 'sandbox-limits',
      });
      expect(parseDocHref('/docs')).toEqual({
        slug: 'home',
        anchor: undefined,
      });
      expect(parseDocHref('/help')).toEqual({
        slug: 'home',
        anchor: undefined,
      });
      expect(parseDocHref('/docs#quick-start')).toEqual({
        slug: 'home',
        anchor: 'quick-start',
      });
      expect(parseDocHref('/help#quick-start')).toEqual({
        slug: 'home',
        anchor: 'quick-start',
      });
      expect(parseDocHref('/help/roles')).toEqual({
        slug: 'role-and-permission-matrix',
        anchor: undefined,
      });
      expect(parseDocHref('/docs/unknown-nonexistent-chapter')).toEqual({
        slug: 'unknown-nonexistent-chapter',
        anchor: undefined,
      });
    });

    it('resolves valid, alias, and fallback chapter slugs', () => {
      expect(resolveChapterSlug('home')).toBe('home');
      expect(resolveChapterSlug('roles')).toBe('role-and-permission-matrix');
      expect(resolveChapterSlug('custom-fields')).toBe('guide-custom-fields');
      expect(resolveChapterSlug('auth')).toBe('multi-card-authentication-studio');
      expect(resolveChapterSlug('mcp')).toBe('mcp-tools-reference');
      expect(resolveChapterSlug('mcp-server')).toBe('three-surface-mcp-server-architecture');
      expect(resolveChapterSlug('api')).toBe('rest-api-architecture-and-openapi-guide');
      expect(resolveChapterSlug('workflows')).toBe(
        'scripted-workflows-and-transition-helpers',
      );
      expect(resolveChapterSlug('ai')).toBe('multi-provider-ai-engine-and-runners');
      expect(resolveChapterSlug('standalone')).toBe('production-promotion-and-backup-runbook');
      expect(resolveChapterSlug('non-existent-slug')).toBe('non-existent-slug');
    });

    it('fetches chapter metadata, all chapters, and categories', () => {
      const chapter = getChapter('home');
      expect(chapter).toBeDefined();
      expect(chapter?.title).toBeDefined();
      expect(chapter?.category).toBeDefined();
      expect(chapter?.content.length).toBeGreaterThan(0);

      const invalid = getChapter('definitely-not-a-chapter-slug');
      expect(invalid).toBeUndefined();

      const all = getAllChapters();
      expect(all.length).toBe(WIKI_CHAPTERS.length);

      const categories = getChapterCategories();
      expect(categories.length).toBeGreaterThan(0);
      expect(categories[0]?.name).toBeDefined();
      expect(categories[0]?.chapters.length).toBeGreaterThan(0);

      const configRef = getConfigReference();
      expect(configRef).toBeDefined();
      expect(configRef.environment_variables).toBeDefined();
    });

    it('executes client-side instant search with score sorting and snippet generation', () => {
      expect(searchDocs('')).toEqual([]);
      expect(searchDocs('   ')).toEqual([]);

      const results = searchDocs('Passkey', 5);
      expect(results.length).toBeGreaterThan(0);
      expect(results.length).toBeLessThanOrEqual(5);

      const first = results[0];
      expect(first?.slug).toBeDefined();
      expect(first?.title).toBeDefined();
      expect(first?.category).toBeDefined();
      expect(first?.snippet).toBeDefined();

      // Search match at the start of chapter content
      const startMatch = searchDocs('Modern', 1);
      expect(startMatch.length).toBe(1);

      // Max results limit break
      const limitedResults = searchDocs('the', 2);
      expect(limitedResults.length).toBe(2);

      // Verify snippet cleans markdown symbols
      expect(first?.snippet).not.toContain('```');
      expect(first?.snippet).not.toContain('###');
    });
  });

  describe('DocMarkdownViewer Component', () => {
    it('renders headings with generated anchor IDs and handles anchor navigation', () => {
      const onNavigate = vi.fn();
      const markdown = `
# Main Header
## Sub Header Two
### Deep Header Three
`;
      render(
        <DocMarkdownViewer
          content={markdown}
          testId="test-markdown"
          onNavigateSection={onNavigate}
        />,
      );

      const h1 = screen.getByRole('heading', { level: 1 });
      expect(h1.textContent).toContain('Main Header');
      expect(h1.id).toBe('main-header');

      const h2 = screen.getByRole('heading', { level: 2 });
      expect(h2.textContent).toContain('Sub Header Two');
      expect(h2.id).toBe('sub-header-two');

      const h3 = screen.getByRole('heading', { level: 3 });
      expect(h3.textContent).toContain('Deep Header Three');
      expect(h3.id).toBe('deep-header-three');

      // Click anchor links on headings with onNavigateSection
      const h2Anchor = h2.querySelector('.kb-doc-anchor-link');
      if (h2Anchor) {
        fireEvent.click(h2Anchor);
        expect(onNavigate).toHaveBeenCalledWith('sub-header-two');
      }

      const h3Anchor = h3.querySelector('.kb-doc-anchor-link');
      if (h3Anchor) {
        fireEvent.click(h3Anchor);
        expect(onNavigate).toHaveBeenCalledWith('deep-header-three');
      }
    });

    it('handles heading anchor clicks when onNavigateSection is not provided', () => {
      const { container } = render(
        <DocMarkdownViewer content="## Standalone Header\n### Sub Heading" />,
      );
      const links = container.querySelectorAll('.kb-doc-anchor-link');
      links.forEach((l) => {
        fireEvent.click(l);
      });
    });

    it('handles malformed table with single header line without failing', () => {
      const markdown = `
| Incomplete table header only |
\n   \n   \n
Paragraph afterwards.
`;
      render(<DocMarkdownViewer content={markdown} />);
      expect(screen.getByText(/Paragraph afterwards/)).toBeDefined();
    });

    it('renders mermaid code blocks via MermaidBlockView in readOnly mode', () => {
      const markdown = `
Here is an architecture diagram:

\`\`\`mermaid
graph TD
  Client --> API
  API --> Database
\`\`\`
`;
      render(<DocMarkdownViewer content={markdown} />);

      const mermaidBlock = screen.getByTestId('mock-mermaid-block-view');
      expect(mermaidBlock).toBeDefined();
      expect(mermaidBlock.getAttribute('data-readonly')).toBe('true');
      expect(mermaidBlock.textContent).toContain('Client --> API');
    });

    it('renders regular code blocks with syntax styling and language label', () => {
      const markdown = `
\`\`\`python
def calculate_story_points(issues):
    return sum(i.points for i in issues)
\`\`\`

\`\`\`
raw code without language
\`\`\`
`;
      render(<DocMarkdownViewer content={markdown} />);

      const codeBlock = screen.getByText(/calculate_story_points/);
      expect(codeBlock).toBeDefined();
      expect(codeBlock.className).toContain('language-python');

      const rawBlock = screen.getByText(/raw code without language/);
      expect(rawBlock).toBeDefined();
    });

    it('renders markdown tables with headers and rows', () => {
      const markdown = `
| Setting | Type | Default |
| :--- | :--- | :--- |
| \`SESSION_IDLE_TIMEOUT\` | integer | 3600 |
| \`AIR_GAP_MODE\` | boolean | false |
`;
      render(<DocMarkdownViewer content={markdown} />);

      expect(screen.getByRole('table')).toBeDefined();
      expect(screen.getByText('Setting')).toBeDefined();
      expect(screen.getByText('SESSION_IDLE_TIMEOUT')).toBeDefined();
      expect(screen.getByText('3600')).toBeDefined();
      expect(screen.getByText('AIR_GAP_MODE')).toBeDefined();
    });

    it('renders blockquotes, unordered lists, ordered lists, and inline text formatting', () => {
      const onNavigate = vi.fn();
      const markdown = `
> This is a crucial security note.

- Unordered item 1
- Unordered item 2

1. Ordered step 1
2. Ordered step 2

Here is **bold text**, *italic text*, \`inline code\`, and a [TOC Anchor](#my-anchor).
`;
      render(
        <DocMarkdownViewer content={markdown} onNavigateSection={onNavigate} />,
      );

      expect(screen.getByText(/This is a crucial security note/)).toBeDefined();
      expect(screen.getByText('Unordered item 1')).toBeDefined();
      expect(screen.getByText('Ordered step 1')).toBeDefined();
      expect(screen.getByText('bold text')).toBeDefined();
      expect(screen.getByText('italic text')).toBeDefined();
      expect(screen.getByText('inline code')).toBeDefined();

      const anchorLink = screen.getByText('TOC Anchor');
      expect(anchorLink).toBeDefined();
      fireEvent.click(anchorLink);
      expect(onNavigate).toHaveBeenCalledWith('my-anchor');
    });

    it('handles helper renderInlineMarkdown with safe and external links', () => {
      const onNav = vi.fn();
      const nodes = renderInlineMarkdown(
        'Check [Internal Link](/docs/home), [External Link](https://example.com), and [Unsafe](javascript:alert(1))',
        'prefix',
        onNav,
      );
      render(<div>{nodes}</div>);

      const extLink = screen.getByText<HTMLAnchorElement>('External Link');
      expect(extLink.href).toBe('https://example.com/');
      expect(extLink.target).toBe('_blank');

      const intLink = screen.getByText<HTMLAnchorElement>('Internal Link');
      expect(intLink.getAttribute('href')).toBe('/docs/home');

      expect(screen.getByText(/Unsafe/)).toBeDefined();
    });
  });

  describe('HelpDrawer Component', () => {
    it('renders drawer with category badge, chapter title, TOC sections, and footer with fallback arg', () => {
      const onClose = vi.fn();
      render(
        <MemoryRouter>
          <HelpDrawer
            arg={null}
            onClose={onClose}
          />
        </MemoryRouter>,
      );

      const drawer = screen.getByTestId('help-drawer');
      expect(drawer).toBeDefined();
      expect(drawer.getAttribute('aria-modal')).toBe('true');

      // Close button
      const closeBtn = screen.getByTestId('help-drawer-close-btn');
      fireEvent.click(closeBtn);
      expect(onClose).toHaveBeenCalled();

      // Category badge
      const badge = screen.getByTestId('help-drawer-category-badge');
      expect(badge).toBeDefined();
      expect(badge.textContent).toBe('[Guide]');
    });

    it('scrolls to anchor when section link is clicked and covers anchor timer and target element fallback', async () => {
      const onClose = vi.fn();

      const { container } = render(
        <MemoryRouter>
          <HelpDrawer
            arg={{ href: '/docs/home#core-system-architecture' }}
            onClose={onClose}
          />
        </MemoryRouter>,
      );

      const secLinks = container.querySelectorAll('.kb-help-drawer-toc-link');
      const firstSecLink = secLinks[0];
      if (firstSecLink) {
        act(() => {
          fireEvent.click(firstSecLink);
        });
      }

      await act(async () => {
        await new Promise((r) => setTimeout(r, 80));
      });

      // Close via backdrop click
      const backdrop = screen.getByTestId('help-drawer-backdrop');
      act(() => {
        fireEvent.click(backdrop);
      });
      expect(onClose).toHaveBeenCalled();
    });

    it('handles keyboard Escape and other keys on window and on drawer container', () => {
      const onClose = vi.fn();
      render(
        <MemoryRouter>
          <HelpDrawer arg={{ slug: 'guide-custom-fields' }} onClose={onClose} />
        </MemoryRouter>,
      );

      const drawer = screen.getByTestId('help-drawer');
      // Non-escape keys should not close
      act(() => {
        fireEvent.keyDown(drawer, { key: 'Tab' });
        fireEvent.keyDown(window, { key: 'Tab' });
      });
      expect(onClose).not.toHaveBeenCalled();

      // Escape keys close
      act(() => {
        fireEvent.keyDown(drawer, { key: 'Escape' });
      });
      expect(onClose).toHaveBeenCalledTimes(1);

      act(() => {
        fireEvent.keyDown(window, { key: 'Escape' });
      });
      expect(onClose).toHaveBeenCalledTimes(2);
    });

    it('handles Open in /docs -> button click with and without active anchor', () => {
      const onClose1 = vi.fn();
      const { unmount } = render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route
              path="/"
              element={
                <HelpDrawer
                  arg={{ href: '/docs/role-and-permission-matrix#system-roles' }}
                  onClose={onClose1}
                />
              }
            />
            <Route
              path="/docs/:slug"
              element={<div data-testid="destination-docs-route">Docs Route</div>}
            />
          </Routes>
        </MemoryRouter>,
      );

      const openDocsBtn1 = screen.getByTestId('help-drawer-open-docs');
      act(() => {
        fireEvent.click(openDocsBtn1);
      });
      expect(onClose1).toHaveBeenCalled();
      expect(screen.getByTestId('destination-docs-route')).toBeDefined();
      unmount();

      // Without active anchor
      const onClose2 = vi.fn();
      render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route
              path="/"
              element={
                <HelpDrawer
                  arg={{ slug: 'home' }}
                  onClose={onClose2}
                />
              }
            />
            <Route
              path="/docs/:slug"
              element={<div data-testid="destination-docs-route-no-anchor">Docs Route No Anchor</div>}
            />
          </Routes>
        </MemoryRouter>,
      );

      const openDocsBtn2 = screen.getByTestId('help-drawer-open-docs');
      act(() => {
        fireEvent.click(openDocsBtn2);
      });
      expect(onClose2).toHaveBeenCalled();
      expect(screen.getByTestId('destination-docs-route-no-anchor')).toBeDefined();
    });
  });

  describe('DocsCenterPage Component', () => {
    it('renders root /docs route with default home chapter', () => {
      render(
        <MemoryRouter initialEntries={['/docs']}>
          <Routes>
            <Route path="/docs" element={<DocsCenterPage />} />
          </Routes>
        </MemoryRouter>,
      );

      expect(screen.getByTestId('docs-center-page')).toBeDefined();
    });

    it('renders full-page layout with categories sidebar, chapter content, and TOC rail', () => {
      render(
        <MemoryRouter initialEntries={['/docs/home']}>
          <Routes>
            <Route path="/docs/:slug" element={<DocsCenterPage />} />
          </Routes>
        </MemoryRouter>,
      );

      expect(screen.getByTestId('docs-center-page')).toBeDefined();
      expect(screen.getByTestId('docs-search-input')).toBeDefined();
      expect(screen.getByTestId('docs-categories-sidebar')).toBeDefined();
      expect(screen.getByTestId('docs-main-content')).toBeDefined();
    });

    it('performs instant search, handles onFocus, empty queries, and navigates on result click', async () => {
      render(
        <MemoryRouter initialEntries={['/docs/home']}>
          <Routes>
            <Route path="/docs" element={<DocsCenterPage />} />
            <Route path="/docs/:slug" element={<DocsCenterPage />} />
          </Routes>
        </MemoryRouter>,
      );

      const searchInput = screen.getByTestId<HTMLInputElement>('docs-search-input');

      // Focus while empty does not open dropdown
      act(() => {
        fireEvent.focus(searchInput);
      });
      expect(screen.queryByTestId('docs-search-results')).toBeNull();

      // Query with results
      act(() => {
        fireEvent.change(searchInput, { target: { value: 'Docker' } });
      });

      await waitFor(() => {
        expect(screen.getByTestId('docs-search-results')).toBeDefined();
      });

      // Focus while non-empty opens dropdown
      act(() => {
        fireEvent.focus(searchInput);
      });
      expect(screen.getByTestId('docs-search-results')).toBeDefined();

      // Clear query closes results
      act(() => {
        fireEvent.change(searchInput, { target: { value: '' } });
      });

      await waitFor(() => {
        expect(screen.queryByTestId('docs-search-results')).toBeNull();
      });

      // Query again and click result
      act(() => {
        fireEvent.change(searchInput, { target: { value: 'Docker' } });
      });

      await waitFor(() => {
        expect(screen.getByTestId('docs-search-results')).toBeDefined();
      });

      const results = screen.getAllByRole('option');
      expect(results.length).toBeGreaterThan(0);
      const firstResult = results[0];
      if (firstResult) {
        act(() => {
          fireEvent.click(firstResult);
        });
      }

      await waitFor(() => {
        expect(screen.queryByTestId('docs-search-results')).toBeNull();
      });
    });

    it('navigates next and previous chapters, TOC rail sections, and markdown anchor links', async () => {
      render(
        <MemoryRouter initialEntries={['/docs/role-and-permission-matrix#system-roles']}>
          <Routes>
            <Route path="/docs/:slug" element={<DocsCenterPage />} />
          </Routes>
        </MemoryRouter>,
      );

      await act(async () => {
        await new Promise((r) => setTimeout(r, 80));
      });

      // TOC rail section click
      const tocRail = screen.queryByTestId('docs-toc-rail');
      if (tocRail) {
        const secLinks = tocRail.querySelectorAll('.kb-docs-toc-link');
        const firstTocLink = secLinks[0];
        if (firstTocLink) {
          act(() => {
            fireEvent.click(firstTocLink);
          });
        }
      }

      // Main article onNavigateSection via heading anchor click
      const viewer = screen.getByTestId('docs-markdown-viewer');
      const headingAnchorLinks = viewer.querySelectorAll('.kb-doc-anchor-link');
      const firstHeadingLink = headingAnchorLinks[0];
      if (firstHeadingLink) {
        act(() => {
          fireEvent.click(firstHeadingLink);
        });
      }

      const innerLinks = viewer.querySelectorAll('.kb-doc-link');
      innerLinks.forEach((l) => {
        if (l.getAttribute('href')?.startsWith('#')) {
          act(() => {
            fireEvent.click(l);
          });
        }
      });

      // Next chapter pagination button
      const nextBtn = screen.queryByTestId('docs-next-chapter');
      if (nextBtn) {
        act(() => {
          fireEvent.click(nextBtn);
        });
      }

      // Prev chapter pagination button
      const prevBtn = screen.queryByTestId('docs-prev-chapter');
      if (prevBtn) {
        act(() => {
          fireEvent.click(prevBtn);
        });
      }
    });

    it('renders first chapter without prev button', () => {
      const firstChapter = WIKI_CHAPTERS[0];
      const firstSlug = firstChapter ? firstChapter.slug : 'home';
      render(
        <MemoryRouter initialEntries={[`/docs/${firstSlug}`]}>
          <Routes>
            <Route path="/docs/:slug" element={<DocsCenterPage />} />
          </Routes>
        </MemoryRouter>,
      );
      expect(screen.queryByTestId('docs-prev-chapter')).toBeNull();
      expect(screen.getByTestId('docs-next-chapter')).toBeDefined();
    });

    it('renders last chapter without next button', () => {
      const lastChapter = WIKI_CHAPTERS[WIKI_CHAPTERS.length - 1];
      const lastSlug = lastChapter ? lastChapter.slug : 'home';
      render(
        <MemoryRouter initialEntries={[`/docs/${lastSlug}`]}>
          <Routes>
            <Route path="/docs/:slug" element={<DocsCenterPage />} />
          </Routes>
        </MemoryRouter>,
      );
      expect(screen.queryByTestId('docs-next-chapter')).toBeNull();
      expect(screen.getByTestId('docs-prev-chapter')).toBeDefined();
    });

    it('handles click outside to dismiss search results', async () => {
      render(
        <MemoryRouter initialEntries={['/docs/home']}>
          <Routes>
            <Route path="/docs/:slug" element={<DocsCenterPage />} />
          </Routes>
        </MemoryRouter>,
      );

      const searchInput = screen.getByTestId('docs-search-input');
      act(() => {
        fireEvent.change(searchInput, { target: { value: 'Docker' } });
      });

      await waitFor(() => {
        expect(screen.getByTestId('docs-search-results')).toBeDefined();
      });

      // Click outside
      act(() => {
        fireEvent.click(document.body);
      });

      await waitFor(() => {
        expect(screen.queryByTestId('docs-search-results')).toBeNull();
      });
    });

    it('renders category filter tabs and filters sidebar categories and chapters', () => {
      render(
        <MemoryRouter initialEntries={['/docs/home']}>
          <Routes>
            <Route path="/docs/:slug" element={<DocsCenterPage />} />
          </Routes>
        </MemoryRouter>,
      );

      const filterBar = screen.getByTestId('docs-category-filter-bar');
      expect(filterBar).toBeDefined();

      const filterAll = screen.getByTestId('docs-filter-all');
      const filterGuide = screen.getByTestId('docs-filter-guide');
      const filterInfo = screen.getByTestId('docs-filter-informational');
      const filterArch = screen.getByTestId('docs-filter-architectural');

      expect(filterAll).toBeDefined();
      expect(filterGuide).toBeDefined();
      expect(filterInfo).toBeDefined();
      expect(filterArch).toBeDefined();

      expect(filterAll.getAttribute('aria-selected')).toBe('true');
      expect(filterGuide.getAttribute('aria-selected')).toBe('false');

      // Filter by "Guides"
      act(() => {
        fireEvent.click(filterGuide);
      });
      expect(filterGuide.getAttribute('aria-selected')).toBe('true');
      expect(filterAll.getAttribute('aria-selected')).toBe('false');

      // Sidebar should display Guide chapters
      const sidebar = screen.getByTestId('docs-categories-sidebar');
      expect(sidebar.textContent).toContain('Step-by-Step Guides');
      // When filtered to guides, should NOT contain Track 4 Engineering & Security Architecture
      expect(sidebar.textContent).not.toContain('Functional Architecture');

      // Filter by "Architectural"
      act(() => {
        fireEvent.click(filterArch);
      });
      expect(filterArch.getAttribute('aria-selected')).toBe('true');
      expect(sidebar.textContent).toContain('Track 4: Engineering & Security Architecture');
      expect(sidebar.textContent).toContain('System Topology and Multi-Container Architecture');
      expect(sidebar.textContent).not.toContain('Track 1: Step-by-Step Guides');

      // Filter by "Informational"
      act(() => {
        fireEvent.click(filterInfo);
      });
      expect(filterInfo.getAttribute('aria-selected')).toBe('true');
      expect(sidebar.textContent).toContain('Track 2: Feature & Field Reference');
      expect(sidebar.textContent).not.toContain('Track 4: Engineering & Security Architecture');

      // Return to "All"
      act(() => {
        fireEvent.click(filterAll);
      });
      expect(filterAll.getAttribute('aria-selected')).toBe('true');
      expect(sidebar.textContent).toContain('Track 1: Step-by-Step Guides');
      expect(sidebar.textContent).toContain('Track 2: Feature & Field Reference');
      expect(sidebar.textContent).toContain('Track 4: Engineering & Security Architecture');
    });

    it('displays category badge pills in chapter meta bar, sidebar, and search results', async () => {
      render(
        <MemoryRouter initialEntries={['/docs/guide-custom-fields']}>
          <Routes>
            <Route path="/docs/:slug" element={<DocsCenterPage />} />
          </Routes>
        </MemoryRouter>,
      );

      // Meta bar category badge
      const metaBadge = screen.getByTestId('docs-category-badge');
      expect(metaBadge).toBeDefined();
      expect(metaBadge.textContent).toBe('[Guide]');
      expect(metaBadge.className).toContain('kb-badge-guide');

      // Sidebar category badge pills
      const sidebar = screen.getByTestId('docs-categories-sidebar');
      const badges = sidebar.querySelectorAll('.kb-docs-badge-pill');
      expect(badges.length).toBeGreaterThan(0);

      // Instant search category badge pills
      const searchInput = screen.getByTestId('docs-search-input');
      act(() => {
        fireEvent.change(searchInput, { target: { value: 'Docker' } });
      });

      await waitFor(() => {
        expect(screen.getByTestId('docs-search-results')).toBeDefined();
      });

      const searchBadges = screen.getAllByText(/\[Guide\]|\[Informational\]|\[Architectural\]/);
      expect(searchBadges.length).toBeGreaterThan(0);
    });
  });

  describe('StudioDocLink Component', () => {
    it('renders with 📖 icon, custom label, and data-testid', () => {
      render(
        <StudioDocLink
          href="/docs/home"
          title="Getting Started Guide"
          label="Read Guides ->"
          testId="custom-studio-doc-link"
        />,
      );

      const link = screen.getByTestId('custom-studio-doc-link');
      expect(link).toBeDefined();
      expect(link.textContent).toContain('Read Guides ->');
      expect(link.getAttribute('href')).toBe('/docs/home');
    });

    it('navigates normally when clicked outside ShellPanelsProvider', () => {
      render(
        <StudioDocLink
          href="/docs/home"
          testId="unwrapped-studio-doc-link"
        />,
      );

      const link = screen.getByTestId('unwrapped-studio-doc-link');
      act(() => {
        fireEvent.click(link);
      });
      expect(link.getAttribute('href')).toBe('/docs/home');
    });

    it('intercepts click inside ShellPanelsProvider and opens help panel without navigating away', () => {
      function TestStudioShell(): JSX.Element {
        return (
          <ShellPanelsProvider>
            <div data-testid="studio-page">
              <StudioDocLink
                href="/docs/role-and-permission-matrix#system-roles"
                testId="studio-header-doc-link"
              />
            </div>
          </ShellPanelsProvider>
        );
      }

      registerShellPanel('help', HelpDrawer);

      render(
        <MemoryRouter>
          <TestStudioShell />
        </MemoryRouter>,
      );

      const docLink = screen.getByTestId('studio-header-doc-link');
      act(() => {
        fireEvent.click(docLink);
      });

      const drawer = screen.getByTestId('help-drawer');
      expect(drawer).toBeDefined();
      expect(screen.getByTestId('studio-page')).toBeDefined();
    });
  });

  describe('Form Preservation & FieldHelpHint -> HelpDrawer Integration', () => {
    function UnsavedFormFixture(): JSX.Element {
      const [workspaceName, setWorkspaceName] = useState('My Secret Workspace');
      const [idleTimeout, setIdleTimeout] = useState('1800');

      return (
        <ShellPanelsProvider>
          <div data-testid="settings-form-container">
            <h2>Workspace Settings</h2>
            <form onSubmit={(e) => { e.preventDefault(); }}>
              <div className="kb-form-group">
                <label htmlFor="ws-name">Workspace Name</label>
                <input
                  id="ws-name"
                  data-testid="ws-name-input"
                  value={workspaceName}
                  onChange={(e) => { setWorkspaceName(e.target.value); }}
                />
              </div>

              <div className="kb-form-group">
                <label htmlFor="ws-timeout">
                  Session Idle Timeout
                  <FieldHelpHint
                    title="Session Idle Timeout"
                    fieldKey="session_idle_timeout"
                    docHref="/docs/home#system-topology"
                    summary="Timeout in seconds before an idle session is revoked."
                    validValues={['900', '1800', '3600', '86400']}
                    defaultValue="3600"
                    testId="timeout-field-hint"
                  />
                </label>
                <input
                  id="ws-timeout"
                  data-testid="ws-timeout-input"
                  value={idleTimeout}
                  onChange={(e) => { setIdleTimeout(e.target.value); }}
                />
              </div>
            </form>
          </div>
        </ShellPanelsProvider>
      );
    }

    it('preserves unsaved form inputs when (?) More info -> opens HelpDrawer beside the form', () => {
      registerShellPanel('help', HelpDrawer);

      render(
        <MemoryRouter>
          <UnsavedFormFixture />
        </MemoryRouter>,
      );

      const nameInput = screen.getByTestId<HTMLInputElement>('ws-name-input');
      const timeoutInput = screen.getByTestId<HTMLInputElement>('ws-timeout-input');

      // 1. User types in-progress unsaved draft changes
      act(() => {
        fireEvent.change(nameInput, { target: { value: 'Unsaved Critical Draft Work 1234' } });
        fireEvent.change(timeoutInput, { target: { value: '7200' } });
      });

      expect(nameInput.value).toBe('Unsaved Critical Draft Work 1234');
      expect(timeoutInput.value).toBe('7200');

      // 2. User opens the (?) hint popover
      const hintBtn = screen.getByTestId('timeout-field-hint');
      act(() => {
        fireEvent.click(hintBtn);
      });

      const popover = screen.getByTestId('timeout-field-hint-popover');
      expect(popover).toBeDefined();

      // 3. User clicks "More info ->" link inside the hint popover
      const moreInfoLink = screen.getByTestId('timeout-field-hint-doc-link');
      act(() => {
        fireEvent.click(moreInfoLink);
      });

      // 4. Popover closed, HelpDrawer mounted beside the form
      expect(screen.queryByTestId('timeout-field-hint-popover')).toBeNull();
      const helpDrawer = screen.getByTestId('help-drawer');
      expect(helpDrawer).toBeDefined();

      // 5. CRUCIAL: Verify that the parent form inputs were NOT reset or unmounted!
      expect(nameInput.value).toBe('Unsaved Critical Draft Work 1234');
      expect(timeoutInput.value).toBe('7200');

      // 6. User closes HelpDrawer
      const closeBtn = screen.getByTestId('help-drawer-close-btn');
      act(() => {
        fireEvent.click(closeBtn);
      });

      expect(screen.queryByTestId('help-drawer')).toBeNull();

      // 7. Form inputs still 100% intact
      expect(nameInput.value).toBe('Unsaved Critical Draft Work 1234');
      expect(timeoutInput.value).toBe('7200');
    });

    it('restores document.activeElement to the (?) trigger button when closing HelpDrawer via Escape (KAN-16)', () => {
      registerShellPanel('help', HelpDrawer);

      render(
        <MemoryRouter>
          <UnsavedFormFixture />
        </MemoryRouter>,
      );

      const hintBtn = screen.getByTestId('timeout-field-hint');
      act(() => {
        fireEvent.click(hintBtn);
      });

      const moreInfoLink = screen.getByTestId('timeout-field-hint-doc-link');
      act(() => {
        fireEvent.click(moreInfoLink);
      });

      expect(screen.getByTestId('help-drawer')).toBeDefined();

      // Press Escape to close HelpDrawer
      act(() => {
        fireEvent.keyDown(window, { key: 'Escape' });
      });

      expect(screen.queryByTestId('help-drawer')).toBeNull();
      expect(document.activeElement).toBe(hintBtn);
    });
  });

  describe('Release Candidate Polish & Accessibility (KAN-16 RC1)', () => {
    it('places Home at Chapter 1 of 28 with informational category and Overview track', () => {
      expect(WIKI_CHAPTERS[0]?.slug).toBe('home');
      expect(WIKI_CHAPTERS[0]?.order).toBe(1);
      expect(WIKI_CHAPTERS[0]?.category).toBe('informational');
      expect(WIKI_CHAPTERS[0]?.track).toBe('Overview');
      expect(WIKI_CHAPTERS.length).toBe(28);
    });

    it('exercises resolveSafeDocImageUrl branches directly', () => {
      expect(resolveSafeDocImageUrl('images/test.png')).toBe('/docs-images/test.png');
      expect(resolveSafeDocImageUrl('./images/test.png')).toBe('/docs-images/test.png');
      expect(resolveSafeDocImageUrl('/docs-images/test.png')).toBe('/docs-images/test.png');
      expect(resolveSafeDocImageUrl('docs-images/test.png')).toBe('/docs-images/test.png');
      expect(resolveSafeDocImageUrl('https://evil.com/x.png')).toBeNull();
      expect(resolveSafeDocImageUrl('http://evil.com/x.png')).toBeNull();
      expect(resolveSafeDocImageUrl('//evil.com/x.png')).toBeNull();
      expect(resolveSafeDocImageUrl('data:image/png;base64,...')).toBeNull();
      expect(resolveSafeDocImageUrl('javascript:alert(1)')).toBeNull();
      expect(resolveSafeDocImageUrl('other/unknown/path.png')).toBeNull();
    });

    it('safely renders markdown images mapping images/... to /docs-images/..., rejecting external URLs', () => {
      const markdown = `
![Block Architecture](images/14-custom-fields-studio.png)

![](images/53-custom-fields-test-execute.png)

![Unsafe Standalone](https://evil.com/leak2.png)

Paragraph with inline ![Inline Icon](./images/01-first-boot-setup.png) media, ![](images/02-multi-card-login.png) empty alt, and ![Unsafe Remote](https://evil.com/leak.png) attempt.
`;
      render(<DocMarkdownViewer content={markdown} />);

      // Block-level figure and img
      const blockImgs = screen.getAllByTestId('doc-image');
      expect(blockImgs[0]?.getAttribute('src')).toBe('/docs-images/14-custom-fields-studio.png');
      expect(blockImgs[0]?.getAttribute('alt')).toBe('Block Architecture');
      expect(blockImgs[0]?.getAttribute('loading')).toBe('lazy');
      expect(screen.getByText('Block Architecture')).toBeDefined();

      // Empty alt fallback
      expect(blockImgs[1]?.getAttribute('src')).toBe('/docs-images/53-custom-fields-test-execute.png');
      expect(blockImgs[1]?.getAttribute('alt')).toBe('Documentation media');

      // Inline images
      const inlineImgs = screen.getAllByTestId('doc-inline-image');
      expect(inlineImgs[0]?.getAttribute('src')).toBe('/docs-images/01-first-boot-setup.png');
      expect(inlineImgs[0]?.getAttribute('alt')).toBe('Inline Icon');
      expect(inlineImgs[1]?.getAttribute('src')).toBe('/docs-images/02-multi-card-login.png');
      expect(inlineImgs[1]?.getAttribute('alt')).toBe('Documentation image');

      // Unsafe remote image must NOT be rendered as an img tag
      const allImgs = screen.getAllByRole('img');
      allImgs.forEach((img) => {
        expect(img.getAttribute('src')).not.toContain('evil.com');
      });
      expect(screen.getByText(/Unsafe Remote/)).toBeDefined();
    });

    it('opens mobile chapters drawer, selects a chapter to auto-close, and dismisses on Escape or backdrop click', () => {
      render(
        <MemoryRouter initialEntries={['/docs/home']}>
          <DocsCenterPage />
        </MemoryRouter>,
      );

      // 1. Mobile chapters toggle button is present
      const toggleBtn = screen.getByTestId('docs-mobile-chapters-btn');
      expect(toggleBtn).toBeDefined();
      expect(toggleBtn.getAttribute('aria-expanded')).toBe('false');
      expect(screen.queryByTestId('docs-mobile-chapters-drawer')).toBeNull();

      // 1b. Test non-Escape key and Escape while drawer is closed
      act(() => {
        fireEvent.keyDown(window, { key: 'Enter' });
        fireEvent.keyDown(window, { key: 'Escape' });
      });
      expect(screen.queryByTestId('docs-mobile-chapters-drawer')).toBeNull();

      // 2. Open drawer
      act(() => {
        fireEvent.click(toggleBtn);
      });
      expect(toggleBtn.getAttribute('aria-expanded')).toBe('true');
      const drawer = screen.getByTestId('docs-mobile-chapters-drawer');
      expect(drawer).toBeDefined();

      // 3. Close via close button
      const closeBtn = screen.getByTestId('docs-mobile-drawer-close');
      act(() => {
        fireEvent.click(closeBtn);
      });
      expect(screen.queryByTestId('docs-mobile-chapters-drawer')).toBeNull();

      // 4. Re-open and dismiss via Escape key
      act(() => {
        fireEvent.click(toggleBtn);
      });
      expect(screen.getByTestId('docs-mobile-chapters-drawer')).toBeDefined();
      act(() => {
        fireEvent.keyDown(window, { key: 'Escape' });
      });
      expect(screen.queryByTestId('docs-mobile-chapters-drawer')).toBeNull();

      // 5. Re-open and auto-close on chapter link click
      act(() => {
        fireEvent.click(toggleBtn);
      });
      const chapterLinks = screen.getByTestId('docs-mobile-chapters-drawer').querySelectorAll('a');
      expect(chapterLinks.length).toBeGreaterThan(0);
      const firstChapterLink = chapterLinks[0];
      expect(firstChapterLink).toBeDefined();
      if (firstChapterLink) {
        act(() => {
          fireEvent.click(firstChapterLink);
        });
      }
      expect(screen.queryByTestId('docs-mobile-chapters-drawer')).toBeNull();

      // 6. Dismiss via backdrop click
      act(() => {
        fireEvent.click(toggleBtn);
      });
      const backdrop = screen.getByTestId('docs-mobile-drawer-backdrop');
      act(() => {
        fireEvent.click(backdrop);
      });
      expect(screen.queryByTestId('docs-mobile-chapters-drawer')).toBeNull();
    });

    it('manages WAI-ARIA modal dialog focus, traps Tab/Shift+Tab, restores trigger focus on close, and resyncs on arg change', async () => {
      const triggerBtn = document.createElement('button');
      triggerBtn.textContent = 'Open Help Trigger';
      document.body.appendChild(triggerBtn);
      triggerBtn.focus();
      expect(document.activeElement).toBe(triggerBtn);

      const onClose = vi.fn();
      const { rerender, unmount } = render(
        <MemoryRouter>
          <HelpDrawer
            arg={{ slug: 'guide-custom-fields', anchor: 'custom-fields' }}
            onClose={onClose}
          />
        </MemoryRouter>,
      );

      const drawer = screen.getByTestId('help-drawer');
      expect(drawer).toBeDefined();

      // Verify close button receives initial focus
      const closeBtn = screen.getByTestId('help-drawer-close-btn');
      await waitFor(() => {
        expect(document.activeElement).toBe(closeBtn);
      });

      // Verify focus trap on Tab and Shift+Tab
      const focusables = drawer.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      expect(focusables.length).toBeGreaterThan(1);
      const firstFocusable = focusables[0];
      const lastFocusable = focusables[focusables.length - 1];
      expect(firstFocusable).toBeDefined();
      expect(lastFocusable).toBeDefined();

      // Shift+Tab from first element wraps to last element
      firstFocusable?.focus();
      act(() => {
        fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
      });
      expect(document.activeElement).toBe(lastFocusable);

      // Tab from last element wraps to first element
      lastFocusable?.focus();
      act(() => {
        fireEvent.keyDown(window, { key: 'Tab', shiftKey: false });
      });
      expect(document.activeElement).toBe(firstFocusable);

      // Tab on middle element does not wrap
      const middleFocusable = focusables[1];
      if (middleFocusable) {
        middleFocusable.focus();
        act(() => {
          fireEvent.keyDown(window, { key: 'Tab', shiftKey: false });
          fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
        });
      }

      // Escape on drawer container triggers onClose
      act(() => {
        fireEvent.keyDown(drawer, { key: 'Escape' });
      });
      expect(onClose).toHaveBeenCalled();

      // Verify arg prop resync while mounted
      rerender(
        <MemoryRouter>
          <HelpDrawer
            arg={{ slug: 'multi-card-authentication-studio', anchor: 'ldap-settings' }}
            onClose={onClose}
          />
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByText('Multi-Card Authentication Studio')).toBeDefined();
      });

      // Unmount / close restores focus to invoking trigger
      unmount();
      expect(document.activeElement).toBe(triggerBtn);
      document.body.removeChild(triggerBtn);
    });

    it('strips raw markdown backticks from TOC section labels in HelpDrawer and DocsCenterPage', () => {
      const originalHome = CHAPTER_BY_SLUG.home;
      if (!originalHome) throw new Error('Home chapter not found');

      CHAPTER_BY_SLUG.home = {
        ...originalHome,
        sections: [
          { id: 'sec-code', title: 'Using `kubectl` and `docker` CLI', level: 2 },
          { id: 'sec-env', title: 'The `DATABASE_URL` setting', level: 3 },
        ],
      };

      try {
        const { unmount } = render(
          <MemoryRouter initialEntries={['/docs/home']}>
            <DocsCenterPage />
          </MemoryRouter>,
        );

        const tocRail = screen.getByTestId('docs-toc-rail');
        expect(tocRail.textContent).toContain('Using kubectl and docker CLI');
        expect(tocRail.textContent).not.toContain('`');
        expect(tocRail.textContent).toContain('The DATABASE_URL setting');
        unmount();

        // In HelpDrawer
        render(
          <MemoryRouter>
            <HelpDrawer arg={{ slug: 'home' }} onClose={() => { /* noop */ }} />
          </MemoryRouter>,
        );

        const drawerBody = screen.getByTestId('help-drawer-body');
        expect(drawerBody.textContent).toContain('Using kubectl and docker CLI');
        expect(drawerBody.textContent).not.toContain('`kubectl`');
      } finally {
        CHAPTER_BY_SLUG.home = originalHome;
      }
    });
  });
});
