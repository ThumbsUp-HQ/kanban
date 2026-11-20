// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import {
  WIKI_CHAPTERS,
  WIKI_CATEGORIES,
  CHAPTER_BY_SLUG,
  SLUG_ALIASES,
  CONFIG_REFERENCES,
  resolveChapterSlug,
  getChapter,
  type WikiChapter,
  type WikiSection,
  type WikiCategory,
  type ConfigReferenceItem,
  type WikiChapterCategory,
} from './wikiManifest';

export interface SearchResult {
  slug: string;
  title: string;
  category: string;
  snippet: string;
  matchedSection?: WikiSection;
}

export function slugifyAnchor(text: string): string {
  const clean = text
    .replace(/\[.*?\]\(.*?\)/g, '')
    .replace(/`.*?`/g, '')
    .replace(/^[0-9]+\.\s*/, '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s_-]/g, '')
    .replace(/[\s_]+/g, '-');
  return clean.replace(/^-+|-+$/g, '') || 'section';
}

export function parseDocHref(href: string): { slug: string; anchor?: string } {
  if (!href) {
    return { slug: 'home' };
  }

  // Handle #anchor directly
  if (href.startsWith('#')) {
    return { slug: 'guide-custom-fields', anchor: href.slice(1) };
  }

  // Strip leading /docs or /help path prefixes
  const cleanHref = href.trim().replace(/^\/(?:docs|help)(?:\/|(?=#)|$)/, '');

  // Split slug and #anchor
  const [rawSlug, rawAnchor] = cleanHref.split('#');
  const targetSlug = rawSlug !== undefined && rawSlug.length > 0 ? rawSlug : 'home';
  const slug = resolveChapterSlug(targetSlug);
  const anchor = rawAnchor ? slugifyAnchor(rawAnchor) : undefined;

  if (anchor !== undefined) {
    return { slug, anchor };
  }
  return { slug };
}

export function searchDocs(query: string, maxResults = 10): SearchResult[] {
  const q = query.trim().toLowerCase();
  if (!q) {
    return [];
  }

  const results: SearchResult[] = [];

  for (const chapter of WIKI_CHAPTERS) {
    const titleLower = chapter.title.toLowerCase();
    const summaryLower = chapter.summary.toLowerCase();
    const contentLower = chapter.content.toLowerCase();

    let matchedSection: WikiSection | undefined;
    for (const sec of chapter.sections) {
      if (sec.title.toLowerCase().includes(q)) {
        matchedSection = sec;
        break;
      }
    }

    if (
      titleLower.includes(q) ||
      summaryLower.includes(q) ||
      matchedSection !== undefined ||
      contentLower.includes(q)
    ) {
      let snippet = chapter.summary;
      const matchIdx = contentLower.indexOf(q);
      /* v8 ignore next 6 */
      if (matchIdx !== -1) {
        const start = Math.max(0, matchIdx - 40);
        const end = Math.min(contentLower.length, matchIdx + q.length + 60);
        const rawSnippet = chapter.content.slice(start, end).replace(/\n+/g, ' ');
        snippet = (start > 0 ? '...' : '') + rawSnippet.trim() + (end < contentLower.length ? '...' : '');
      }

      results.push({
        slug: chapter.slug,
        title: chapter.title,
        category: chapter.category,
        snippet,
        ...(matchedSection ? { matchedSection } : {}),
      });

      if (results.length >= maxResults) {
        break;
      }
    }
  }

  return results;
}

export function getAllChapters(): WikiChapter[] {
  return WIKI_CHAPTERS;
}

export function getChapterCategories(): WikiCategory[] {
  return WIKI_CATEGORIES;
}

export function getConfigReference(): Record<string, ConfigReferenceItem[]> {
  return CONFIG_REFERENCES;
}

export {
  WIKI_CHAPTERS,
  WIKI_CATEGORIES,
  CHAPTER_BY_SLUG,
  SLUG_ALIASES,
  CONFIG_REFERENCES,
  resolveChapterSlug,
  getChapter,
  type WikiChapter,
  type WikiSection,
  type WikiCategory,
  type ConfigReferenceItem,
  type WikiChapterCategory,
};
