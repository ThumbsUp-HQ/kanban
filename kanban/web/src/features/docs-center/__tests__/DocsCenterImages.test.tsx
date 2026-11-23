// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router';

// Mock MermaidBlockView to avoid background web-worker invocation in unit tests
vi.mock('../../../editor/mermaid/MermaidBlockView', () => ({
  MermaidBlockView: ({ source }: { source: string }) => (
    <div data-testid="mock-mermaid-block-view">{source}</div>
  ),
}));

import { WIKI_CHAPTERS } from '../docsService';
import {
  DocMarkdownViewer,
  resolveSafeDocImageUrl,
  resolveSafeDocLinkHref,
} from '../DocMarkdownViewer';
import { DocsCenterPage } from '../DocsCenterPage';

describe('DocsCenterImages & Visual Media Tests (KAN-323 / KAN-311)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.scrollTo = vi.fn();
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  describe('resolveSafeDocImageUrl URL mapping and security sanitization', () => {
    it('maps relative images/... paths to /docs-images/... paths', () => {
      expect(resolveSafeDocImageUrl('images/01-first-boot-setup.png')).toBe(
        '/docs-images/01-first-boot-setup.png',
      );
      expect(resolveSafeDocImageUrl('./images/06-board-view.png')).toBe(
        '/docs-images/06-board-view.png',
      );
      expect(resolveSafeDocImageUrl('images/17-access-visibility-inspector.png')).toBe(
        '/docs-images/17-access-visibility-inspector.png',
      );
      expect(resolveSafeDocImageUrl('images/68-admin-browser-qa.png')).toBe(
        '/docs-images/68-admin-browser-qa.png',
      );
      expect(resolveSafeDocImageUrl('images/69-standard-user-negative-rbac.png')).toBe(
        '/docs-images/69-standard-user-negative-rbac.png',
      );
      expect(resolveSafeDocImageUrl('images/70-mcp-scoping-and-rework-loop.png')).toBe(
        '/docs-images/70-mcp-scoping-and-rework-loop.png',
      );
      expect(resolveSafeDocImageUrl('images/71-plane-migration-dry-run.png')).toBe(
        '/docs-images/71-plane-migration-dry-run.png',
      );
    });

    it('preserves existing /docs-images/... root relative paths', () => {
      expect(resolveSafeDocImageUrl('/docs-images/04-standalone-status-panel.png')).toBe(
        '/docs-images/04-standalone-status-panel.png',
      );
    });

    it('rejects external URLs (http/https) to maintain 100% offline self-containment', () => {
      expect(resolveSafeDocImageUrl('https://evil.corp/payload.png')).toBeNull();
      expect(resolveSafeDocImageUrl('http://192.168.1.101/leak.png')).toBeNull();
      expect(resolveSafeDocImageUrl('//cdn.example.com/image.png')).toBeNull();
    });

    it('rejects dangerous javascript:, data:, and blob: schemes', () => {
      expect(resolveSafeDocImageUrl('javascript:alert(1)')).toBeNull();
      expect(resolveSafeDocImageUrl('data:image/svg+xml;base64,PHN2Zz4=')).toBeNull();
      expect(resolveSafeDocImageUrl('blob:http://localhost/uuid')).toBeNull();
    });

    it('rejects directory traversal and non-image paths', () => {
      expect(resolveSafeDocImageUrl('../../../etc/passwd')).toBeNull();
      expect(resolveSafeDocImageUrl('/api/v1/admin/secret')).toBeNull();
    });
  });

  describe('DocMarkdownViewer image rendering in Markdown documents', () => {
    it('renders img elements for valid images/... markdown tags', () => {
      const markdown = `
# System Architecture

Here is the board view:
![Board View](images/06-board-view.png)

And the access visibility inspector:
![Access Visibility Inspector](images/17-access-visibility-inspector.png)
`;
      const { container } = render(<DocMarkdownViewer content={markdown} />);
      const images = container.querySelectorAll('img');
      expect(images.length).toBe(2);

      expect(images[0]?.getAttribute('src')).toBe('/docs-images/06-board-view.png');
      expect(images[0]?.getAttribute('alt')).toBe('Board View');
      expect(images[0]?.getAttribute('loading')).toBe('lazy');

      expect(images[1]?.getAttribute('src')).toBe('/docs-images/17-access-visibility-inspector.png');
      expect(images[1]?.getAttribute('alt')).toBe('Access Visibility Inspector');
    });

    it('sanitizes and drops external image tags in markdown body', () => {
      const maliciousMarkdown = `
# Phishing Chapter
![Tracker](https://attacker.example.com/tracking-pixel.png)
![Legit Offline](images/01-first-boot-setup.png)
`;
      const { container } = render(<DocMarkdownViewer content={maliciousMarkdown} />);
      const images = container.querySelectorAll('img');
      expect(images.length).toBe(1);
      expect(images[0]?.getAttribute('src')).toBe('/docs-images/01-first-boot-setup.png');
    });
  });

  describe('Wiki Manifest Image Audit & DocsCenterPage integration', () => {
    it('verifies all images in wikiManifest.ts use valid /docs-images targets', () => {
      let imageCount = 0;
      const allImageSrcs: string[] = [];

      for (const ch of WIKI_CHAPTERS) {
        const matches = ch.content.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g);
        for (const m of matches) {
          const rawSrc = m[1];
          if (rawSrc) {
            imageCount++;
            const safeUrl = resolveSafeDocImageUrl(rawSrc);
            expect(safeUrl).not.toBeNull();
            expect(safeUrl).toMatch(/^\/docs-images\/[0-9a-zA-Z_-]+\.png$/);
            if (safeUrl) {
              allImageSrcs.push(safeUrl);
            }
          }
        }
      }

      expect(imageCount).toBeGreaterThanOrEqual(40);
      expect(allImageSrcs).toContain('/docs-images/01-first-boot-setup.png');
      expect(allImageSrcs).toContain('/docs-images/06-board-view.png');
      expect(allImageSrcs).toContain('/docs-images/17-access-visibility-inspector.png');
      expect(allImageSrcs).toContain('/docs-images/71-plane-migration-dry-run.png');
    });

    it('renders DocsCenterPage on a chapter with embedded images without crashes', () => {
      render(
        <MemoryRouter initialEntries={['/docs/enterprise-whitespace-and-kanban-board']}>
          <Routes>
            <Route path="/docs/:slug" element={<DocsCenterPage />} />
          </Routes>
        </MemoryRouter>,
      );

      expect(screen.getByTestId('docs-center-page')).toBeDefined();
      const imgs = document.querySelectorAll('img.kb-doc-image');
      expect(imgs.length).toBeGreaterThanOrEqual(1);
      for (const img of Array.from(imgs)) {
        expect(img.getAttribute('src')).toMatch(/^\/docs-images\//);
      }
    });
  });
});
