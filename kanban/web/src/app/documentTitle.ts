// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { useEffect } from 'react';

export const BRAND_TITLE = 'kanban';

/**
 * Strips leading thumbs-up emoji (👍 / U+1F44D with optional variation selector)
 * and direct surrounding whitespace from a string.
 */
export function stripLeadingThumb(text: string): string {
  if (!text) {
    return '';
  }
  return text.replace(/^[\s\u{1F44D}\u{FE0F}]+/u, '').trim();
}

/**
 * Formats document title from parts, ensuring no leading thumbs,
 * omitting empty parts, and appending BRAND_TITLE ('kanban') if not already present.
 */
export function formatDocumentTitle(parts: readonly (string | null | undefined)[]): string {
  const cleanedParts: string[] = [];
  for (const part of parts) {
    if (part === null || part === undefined) continue;
    const cleaned = stripLeadingThumb(part);
    if (cleaned.length > 0) {
      cleanedParts.push(cleaned);
    }
  }

  if (cleanedParts.length === 0) {
    return BRAND_TITLE;
  }

  const lastPart = cleanedParts[cleanedParts.length - 1];
  if (lastPart && lastPart.toLowerCase() !== BRAND_TITLE.toLowerCase()) {
    cleanedParts.push(BRAND_TITLE);
  }

  return cleanedParts.join(' - ');
}

/**
 * Synchronizes document.title with the provided title, formatting with BRAND_TITLE,
 * and restoring previous title on unmount.
 */
export function useDocumentTitle(title: string | null | undefined): void {
  useEffect(() => {
    if (typeof globalThis === 'undefined' || typeof globalThis.document === 'undefined') {
      return;
    }
    const doc = globalThis.document;
    const prevTitle = doc.title;
    if (title !== null && title !== undefined && title.trim().length > 0) {
      const trimmed = title.trim();
      const formatted = trimmed.toLowerCase().endsWith(BRAND_TITLE.toLowerCase())
        ? stripLeadingThumb(trimmed)
        : formatDocumentTitle([trimmed]);
      doc.title = formatted;
    } else {
      doc.title = BRAND_TITLE;
    }
    return () => {
      doc.title = prevTitle;
    };
  }, [title]);
}
