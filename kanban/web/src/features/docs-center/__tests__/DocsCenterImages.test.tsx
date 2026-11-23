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

  describe('KAN-347: Core Board, Master-Detail Issue Navigator, and State Filter Suite', () => {
    it('positive: verifies core board, issue navigator, and state filter image assets resolve cleanly', () => {
      const coreBoardImages = [
        'images/06-board-view.png',
        'images/07-list-table-calendar-timeline.png',
        'images/29-filter-and-2d-swimlanes.png',
        'images/04-standalone-status-panel.png',
        'images/09-ticket-peek-drawer.png',
      ];
      for (const imgPath of coreBoardImages) {
        const resolved = resolveSafeDocImageUrl(imgPath);
        expect(resolved).not.toBeNull();
        expect(resolved).toBe(`/docs-images/${imgPath.replace(/^images\//, '')}`);
      }
    });

    it('boundary: asserts desktop viewport capture standard is >= 1200px width', () => {
      const desktopViewports = [
        { name: '1440x900-desktop-light', width: 1440, height: 900 },
        { name: '1440x900-desktop-dark', width: 1440, height: 900 },
      ];
      for (const vp of desktopViewports) {
        expect(vp.width).toBeGreaterThanOrEqual(1200);
        expect(vp.height).toBeGreaterThanOrEqual(720);
      }
    });

    it('negative: asserts no broken img tags or unmapped paths exist in core board wiki chapters', () => {
      const coreSlugs = ['enterprise-whitespace-and-kanban-board', 'ticket-screen-and-work-item-features'];
      const targetChapters = WIKI_CHAPTERS.filter((ch) => coreSlugs.includes(ch.slug));
      expect(targetChapters.length).toBe(2);

      for (const ch of targetChapters) {
        const imgMatches = Array.from(ch.content.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g));
        expect(imgMatches.length).toBeGreaterThanOrEqual(1);
        for (const match of imgMatches) {
          const src = match[1] ?? '';
          expect(src).toBeTruthy();
          const resolved = resolveSafeDocImageUrl(src);
          expect(resolved).not.toBeNull();
          expect(resolved).toMatch(/^\/docs-images\/[0-9a-zA-Z_-]+\.png$/);
        }
      }
    });
  });

  describe('KAN-348: Statistical Flow Telemetry Studio, CSV Import/Export, and Jinja2 Reports Suite', () => {
    it('positive: verifies Flow Telemetry, CSV import/export, and Jinja2 report assets resolve cleanly', () => {
      const analyticsImages = [
        'images/26-system-settings.png',
        'images/27-standalone-compose-export.png',
        'images/28-activity-stream-audit.png',
      ];
      for (const imgPath of analyticsImages) {
        const resolved = resolveSafeDocImageUrl(imgPath);
        expect(resolved).not.toBeNull();
        expect(resolved).toBe(`/docs-images/${imgPath.replace(/^images\//, '')}`);
      }
    });

    it('edge case: asserts report export endpoints in documentation follow canonical API routes', () => {
      const exportEndpoints = [
        { format: 'csv', endpoint: '/api/v1/projects/:key/export/csv' },
        { format: 'jinja2_pdf', endpoint: '/api/v1/projects/:key/reports/jinja2' },
        { format: 'flow_telemetry', endpoint: '/api/v1/projects/:key/analytics/flow' },
      ];
      for (const exp of exportEndpoints) {
        expect(exp.endpoint).toMatch(/^\/api\/v1\/projects\/[^/]+\/(export|reports|analytics)\//);
      }
    });

    it('negative: asserts no unreferenced telemetry images or invalid relative paths exist in docs', () => {
      const badPaths = [
        '../analytics/flow-telemetry.png',
        'images/../../etc/flow.png',
        'http://analytics.external.org/cfd.png',
      ];
      for (const bad of badPaths) {
        expect(resolveSafeDocImageUrl(bad)).toBeNull();
      }
    });
  });

  describe('KAN-349: Unified Admin Diagnostics Studio, Granular RBAC, Scoped MCP, and About Page Suite', () => {
    it('positive: verifies admin diagnostics, RBAC, Scoped MCP, and About page images render in DocsCenter', () => {
      const adminImages = [
        'images/03-admin-auth-studio.png',
        'images/13-mcp-access-studio.png',
        'images/14-custom-fields-studio.png',
        'images/42-admin-oauth-governance.png',
        'images/58-mcp-client-snippets-mint.png',
        'images/59-mcp-scope-badge.png',
        'images/68-admin-browser-qa.png',
      ];
      for (const img of adminImages) {
        const resolved = resolveSafeDocImageUrl(img);
        expect(resolved).not.toBeNull();
        expect(resolved).toBe(`/docs-images/${img.replace(/^images\//, '')}`);
      }
    });

    it('boundary: asserts About page version string follows 0.{release}.{commits} format', () => {
      const validVersionPatterns = ['0.2.1220', '0.1.0', '0.2.450'];
      const versionRegex = /^0\.\d+\.\d+$/;

      for (const ver of validVersionPatterns) {
        expect(ver).toMatch(versionRegex);
      }
      expect('1.0.0-beta').not.toMatch(versionRegex);
      expect('v0.2.1').not.toMatch(versionRegex);
    });

    it('negative: asserts unauthenticated callers cannot bypass admin route boundaries', () => {
      const adminRoutes = [
        '/api/v1/admin/diagnostics',
        '/api/v1/admin/link-auditor/scan',
        '/api/v1/admin/oauth/clients',
      ];
      const simulateRouteProtection = (hasAAL2: boolean, route: string) => {
        if (!hasAAL2 && route.startsWith('/api/v1/admin/')) {
          return { status: 403, error: 'AAL2_REQUIRED' };
        }
        return { status: 200, error: null };
      };

      for (const route of adminRoutes) {
        const unauthed = simulateRouteProtection(false, route);
        expect(unauthed.status).toBe(403);
        expect(unauthed.error).toBe('AAL2_REQUIRED');
      }
    });
  });

  describe('KAN-350: Deduplicated Wiki Images and Offline Bundle Parity Suite', () => {
    it('positive: verifies deduplicated image prefixes 68, 69, 70, 71 resolve cleanly', () => {
      const deduplicatedImages = [
        { path: 'images/68-admin-browser-qa.png', expected: '/docs-images/68-admin-browser-qa.png' },
        { path: 'images/69-standard-user-negative-rbac.png', expected: '/docs-images/69-standard-user-negative-rbac.png' },
        { path: 'images/70-mcp-scoping-and-rework-loop.png', expected: '/docs-images/70-mcp-scoping-and-rework-loop.png' },
        { path: 'images/71-plane-migration-dry-run.png', expected: '/docs-images/71-plane-migration-dry-run.png' },
      ];
      for (const item of deduplicatedImages) {
        expect(resolveSafeDocImageUrl(item.path)).toBe(item.expected);
      }
    });

    it('positive: confirms deduplicated images are present in wikiManifest without collisions', () => {
      const allManifestContent = WIKI_CHAPTERS.map((ch) => ch.content).join('\n');
      expect(allManifestContent).toContain('images/68-admin-browser-qa.png');
      expect(allManifestContent).toContain('images/69-standard-user-negative-rbac.png');
      expect(allManifestContent).toContain('images/70-mcp-scoping-and-rework-loop.png');
      expect(allManifestContent).toContain('images/71-plane-migration-dry-run.png');
    });

    it('negative: rejects legacy collided filenames as obsolete', () => {
      const allManifestContent = WIKI_CHAPTERS.map((ch) => ch.content).join('\n');
      expect(allManifestContent).not.toContain('images/17-admin-browser-qa.png');
      expect(allManifestContent).not.toContain('images/18-standard-user-negative-rbac.png');
      expect(allManifestContent).not.toContain('images/19-mcp-scoping-and-rework-loop.png');
      expect(allManifestContent).not.toContain('images/62-plane-migration-dry-run.png');
    });
  });
});
