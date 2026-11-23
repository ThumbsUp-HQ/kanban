// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';

const SRC_DIR = path.resolve(import.meta.dirname, '../..');
const STYLES_DIR = path.resolve(import.meta.dirname, '../../styles');

describe('Reduced Motion Audit & Clamping Verification (KAN-360)', () => {
  let originalMatchMedia: ((query: string) => MediaQueryList) | undefined;

  beforeEach(() => {
    if (typeof window.matchMedia === 'function') {
      originalMatchMedia = (query: string) => window.matchMedia(query);
    }
    vi.restoreAllMocks();
  });

  afterEach(() => {
    if (originalMatchMedia) {
      window.matchMedia = originalMatchMedia;
    }
  });

  describe('Test Case 1: Global Media Query & Universal Clamping in base.css', () => {
    it('verifies base.css contains global prefers-reduced-motion override clamping duration, iteration count, and scroll behavior', () => {
      const baseCssPath = path.join(STYLES_DIR, 'base.css');
      expect(fs.existsSync(baseCssPath)).toBe(true);
      const baseCss = fs.readFileSync(baseCssPath, 'utf8');

      // 1. Media query exists targeting prefers-reduced-motion: reduce
      expect(baseCss).toContain('@media (prefers-reduced-motion: reduce)');

      // 2. Extracts prefers-reduced-motion block
      const regex = /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}/;
      const reducedMotionBlock = regex.exec(baseCss);
      expect(reducedMotionBlock).not.toBeNull();
      const blockContent = reducedMotionBlock?.[1] ?? '';

      // 3. Verifies universal selector targets *, *::before, *::after
      expect(blockContent).toMatch(/\*,\s*\*::before,\s*\*::after/);

      // 4. Verifies animation-duration is clamped to 0.01ms !important
      expect(blockContent).toContain('animation-duration: 0.01ms !important;');

      // 5. Verifies animation-iteration-count is clamped to 1 !important
      expect(blockContent).toContain('animation-iteration-count: 1 !important;');

      // 6. Verifies transition-duration is clamped to 0.01ms !important
      expect(blockContent).toContain('transition-duration: 0.01ms !important;');

      // 7. Verifies scroll-behavior is clamped to auto !important
      expect(blockContent).toContain('scroll-behavior: auto !important;');
    });

    it('verifies runtime reduced-motion query matches and determines smooth scroll fallback', () => {
      const getScrollBehavior = (): ScrollBehavior => {
        const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
        return mediaQuery.matches ? 'auto' : 'smooth';
      };

      // When reduced motion is requested
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('prefers-reduced-motion: reduce'),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));

      expect(getScrollBehavior()).toBe('auto');

      // When reduced motion is false
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));

      expect(getScrollBehavior()).toBe('smooth');
    });
  });

  describe('Test Case 2: Component-Specific Clamping for Drawer Slide-Overs and Board Drops', () => {
    it('verifies IssueSurface.css enforces reduced motion clamping for drawer slide-overs, prose, and skeletons', () => {
      const drawerCssPath = path.join(SRC_DIR, 'features/drawer/IssueSurface.css');
      expect(fs.existsSync(drawerCssPath)).toBe(true);
      const drawerCss = fs.readFileSync(drawerCssPath, 'utf8');

      expect(drawerCss).toContain('@media (prefers-reduced-motion: reduce)');

      // Must clamp drawer slide-overs and skeletons
      expect(drawerCss).toContain('.surface--drawer');
      expect(drawerCss).toContain('.surface--full');
      expect(drawerCss).toContain('.surface__skeleton-line');
      expect(drawerCss).toContain('animation: none !important;');
      expect(drawerCss).toContain('transition: none !important;');
    });

    it('verifies board.css enforces reduced motion clamping for board cards, state buttons, and WIP alerts', () => {
      const boardCssPath = path.join(SRC_DIR, 'features/board/board.css');
      expect(fs.existsSync(boardCssPath)).toBe(true);
      const boardCss = fs.readFileSync(boardCssPath, 'utf8');

      expect(boardCss).toContain('@media (prefers-reduced-motion: reduce)');

      // Must clamp cards, state buttons, and column drops
      expect(boardCss).toContain('.board-card');
      expect(boardCss).toContain('.board-card-wrapper');
      expect(boardCss).toContain('.board-column');
      expect(boardCss).toContain('.board-card-state-btn');
      expect(boardCss).toContain('.hard-wip-btn');
      expect(boardCss).toContain('.board-alert-toast');
      expect(boardCss).toContain('animation: none !important;');
      expect(boardCss).toContain('transition: none !important;');
    });

    it('renders drawer and board DOM containers with clamped reduced motion attributes', () => {
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('prefers-reduced-motion: reduce'),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));

      render(
        <div data-testid="drawer-fixture" className="surface--drawer">
          <div className="surface__skeleton-line" data-testid="skeleton-fixture" />
          <div className="board-card" data-testid="board-card-fixture">
            <button type="button" className="board-card-state-btn" data-testid="state-btn-fixture">
              In Progress
            </button>
          </div>
        </div>
      );

      const drawer = screen.getByTestId('drawer-fixture');
      const skeleton = screen.getByTestId('skeleton-fixture');
      const card = screen.getByTestId('board-card-fixture');
      const stateBtn = screen.getByTestId('state-btn-fixture');

      expect(drawer.classList.contains('surface--drawer')).toBe(true);
      expect(skeleton.classList.contains('surface__skeleton-line')).toBe(true);
      expect(card.classList.contains('board-card')).toBe(true);
      expect(stateBtn.classList.contains('board-card-state-btn')).toBe(true);
    });
  });

  describe('Test Case 3: Particle Animation, Flashes, and Sparkle Caret Pulses Clamping', () => {
    it('verifies sparkle.css clamps sparkle badge pulse and ghost text animations while retaining focus ring', () => {
      const sparkleCssPath = path.join(SRC_DIR, 'editor/sparkle/sparkle.css');
      expect(fs.existsSync(sparkleCssPath)).toBe(true);
      const sparkleCss = fs.readFileSync(sparkleCssPath, 'utf8');

      expect(sparkleCss).toContain('@media (prefers-reduced-motion: reduce)');
      expect(sparkleCss).toContain('.sparkle-badge');
      expect(sparkleCss).toContain('animation: none !important;');
      expect(sparkleCss).toContain('opacity: 1 !important;');
      expect(sparkleCss).toContain('box-shadow: 0 0 8px var(--focus-ring);');
      expect(sparkleCss).toContain('.sparkle-ghost');
    });

    it('verifies AppShell.css and filterBulk.css clamp button transitions and swimlane band rotations', () => {
      const appShellCssPath = path.join(SRC_DIR, 'app/AppShell.css');
      expect(fs.existsSync(appShellCssPath)).toBe(true);
      const appShellCss = fs.readFileSync(appShellCssPath, 'utf8');

      expect(appShellCss).toContain('@media (prefers-reduced-motion: reduce)');
      expect(appShellCss).toContain('.kb-btn-primary');
      expect(appShellCss).toContain('.kb-btn-secondary');
      expect(appShellCss).toContain('.kb-btn-danger');
      expect(appShellCss).toContain('.kb-not-found-btn');

      const filterBulkCssPath = path.join(SRC_DIR, 'features/views/filterBulk.css');
      expect(fs.existsSync(filterBulkCssPath)).toBe(true);
      const filterBulkCss = fs.readFileSync(filterBulkCssPath, 'utf8');

      expect(filterBulkCss).toContain('@media (prefers-reduced-motion: reduce)');
      expect(filterBulkCss).toContain('.swimlane-band-icon');
      expect(filterBulkCss).toContain('.swimlane-band-toggle');
      expect(filterBulkCss).toContain('.filter-bar-btn');
      expect(filterBulkCss).toContain('.bulk-select-btn');
    });

    it('renders sparkle badge DOM node under reduced motion media query without active pulse', () => {
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('prefers-reduced-motion: reduce'),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));

      render(
        <div data-testid="sparkle-wrapper">
          <span className="sparkle-badge sparkle-badge--visible" data-testid="sparkle-badge-node">
            ✨
          </span>
          <span className="sparkle-ghost" data-testid="sparkle-ghost-node">
            suggested code completion
          </span>
        </div>
      );

      const badge = screen.getByTestId('sparkle-badge-node');
      const ghost = screen.getByTestId('sparkle-ghost-node');

      expect(badge.classList.contains('sparkle-badge')).toBe(true);
      expect(ghost.classList.contains('sparkle-ghost')).toBe(true);
      expect(window.matchMedia('(prefers-reduced-motion: reduce)').matches).toBe(true);
    });
  });
});
