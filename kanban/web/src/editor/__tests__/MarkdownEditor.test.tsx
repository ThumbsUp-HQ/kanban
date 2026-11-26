/**
 * Unit & Integration Tests for MediaViewport & MarkdownEditor Theme Cadence (KAN-444).
 * Verifies semantic tokens, WCAG AA compliance, and Light/Dark theme rendering.
 */

import React from 'react';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MediaViewport } from '../media/MediaViewport';
import { MarkdownEditor } from '../MarkdownEditor';

describe('MediaViewport & MarkdownEditor Theme Cadence (KAN-444)', () => {
  const SAMPLE_BLOB = 'blob:http://localhost:3000/media-diagram-uuid';
  const RAW_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="currentColor"/></svg>';

  const originalTheme = document.documentElement.getAttribute('data-theme');

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    if (originalTheme !== null) {
      document.documentElement.setAttribute('data-theme', originalTheme);
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
  });

  it('renders diagram and SVG media controls cleanly in Light theme', () => {
    document.documentElement.setAttribute('data-theme', 'light');

    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="System Topology Diagram"
        rawSource={RAW_SVG}
        safeFilename="topology.svg"
        testId="viewport-light"
      />,
    );

    const controls = screen.getByTestId('viewport-light-controls');
    expect(controls).toBeDefined();

    const canvas = screen.getByTestId('viewport-light-canvas');
    expect(canvas.className).toContain('media-bg--theme');

    const backdropToggle = screen.getByTestId('viewport-light-backdrop-toggle');
    expect(backdropToggle).toBeDefined();

    const zoomOut = screen.getByTestId('viewport-light-zoom-out');
    const zoomIn = screen.getByTestId('viewport-light-zoom-in');
    const zoomReadout = screen.getByTestId('viewport-light-zoom-readout');
    expect(zoomOut).toBeDefined();
    expect(zoomIn).toBeDefined();
    expect(zoomReadout.textContent).toBe('100%');

    const copyBtn = screen.getByTestId('viewport-light-copy-source');
    expect(copyBtn).toBeDefined();
    expect(copyBtn.textContent).toBe('Copy');

    const downloadLink = screen.getByTestId('viewport-light-download');
    expect(downloadLink).toBeDefined();
    expect(downloadLink.getAttribute('download')).toBe('topology.svg');

    // Cycle through backdrop presets
    fireEvent.click(backdropToggle);
    expect(canvas.className).toContain('media-bg--light');

    fireEvent.click(backdropToggle);
    expect(canvas.className).toContain('media-bg--dark');

    fireEvent.click(backdropToggle);
    expect(canvas.className).toContain('media-bg--checkerboard');

    fireEvent.click(backdropToggle);
    expect(canvas.className).toContain('media-bg--theme');
  });

  it('renders diagram and SVG media controls cleanly in Dark theme', () => {
    document.documentElement.setAttribute('data-theme', 'dark');

    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="Architecture Overview"
        rawSource={RAW_SVG}
        safeFilename="arch.svg"
        testId="viewport-dark"
      />,
    );

    const controls = screen.getByTestId('viewport-dark-controls');
    expect(controls).toBeDefined();

    const altBadge = screen.getByTestId('viewport-dark-alt-badge');
    expect(altBadge).toBeDefined();
    expect(altBadge.textContent).toContain('Alt: Architecture');

    const zoomReadout = screen.getByTestId('viewport-dark-zoom-readout');
    expect(zoomReadout.textContent).toBe('100%');

    const zoomIn = screen.getByTestId('viewport-dark-zoom-in');
    fireEvent.click(zoomIn);
    expect(zoomReadout.textContent).toBe('125%');
  });

  it('verifies MediaViewport.css uses semantic tokens and avoids hardcoded dark slate rgba(15, 23, 42, 0.75)', () => {
    const cssPath = path.resolve(__dirname, '../media/MediaViewport.css');
    const cssContent = fs.readFileSync(cssPath, 'utf-8');

    // Invariant 1: Hardcoded rgba(15, 23, 42, 0.75) must be eliminated
    expect(cssContent).not.toContain('rgba(15, 23, 42, 0.75)');

    // Invariant 2: Viewport controls use semantic tokens
    expect(cssContent).toContain('.media-viewport__controls');
    expect(cssContent).toMatch(/background-color:\s*var\(--bg-surface-raised\)/);
    expect(cssContent).toMatch(/border:\s*1px solid var\(--border-subtle\)/);
    expect(cssContent).toMatch(/color:\s*var\(--fg-primary\)/);

    // Invariant 3: Button hover uses semantic tokens
    expect(cssContent).toContain('.media-btn:hover');
    expect(cssContent).toMatch(/\.media-btn:hover\s*\{[^}]*background-color:\s*var\(--bg-hover\)/);
    expect(cssContent).toMatch(/\.media-btn:hover\s*\{[^}]*color:\s*var\(--fg-primary\)/);
    expect(cssContent).not.toMatch(/\.media-btn:hover\s*\{[^}]*rgba\(255,\s*255,\s*255,\s*0\.12\)/);

    // Invariant 4: Alt badge uses semantic tokens
    expect(cssContent).toContain('.media-alt-badge');
    expect(cssContent).toMatch(/\.media-alt-badge\s*\{[^}]*background-color:\s*var\(--bg-surface-raised\)/);
    expect(cssContent).toMatch(/\.media-alt-badge\s*\{[^}]*border:\s*1px solid var\(--border-subtle\)/);
    expect(cssContent).toMatch(/\.media-alt-badge\s*\{[^}]*color:\s*var\(--fg-primary\)/);

    // Invariant 5: Backdrop presets pair background and foreground cleanly
    expect(cssContent).toMatch(/\.media-bg--theme\s*\{[^}]*background-color:\s*var\(--bg-surface\)/);
    expect(cssContent).toMatch(/\.media-bg--theme\s*\{[^}]*color:\s*var\(--fg-primary\)/);

    expect(cssContent).toMatch(/\.media-bg--light\s*\{[^}]*background-color:\s*#ffffff/);
    expect(cssContent).toMatch(/\.media-bg--light\s*\{[^}]*color:\s*#111827/);

    expect(cssContent).toMatch(/\.media-bg--dark\s*\{[^}]*background-color:\s*#0f172a/);
    expect(cssContent).toMatch(/\.media-bg--dark\s*\{[^}]*color:\s*#f8fafc/);

    expect(cssContent).toMatch(/\.media-bg--checkerboard\s*\{[^}]*background-color:\s*var\(--bg-hover\)/);
    expect(cssContent).toMatch(/\.media-bg--checkerboard\s*\{[^}]*color:\s*var\(--fg-primary\)/);
    expect(cssContent).toMatch(/\.media-bg--checkerboard\s*\{[^}]*repeating-conic-gradient\(var\(--border-subtle\)/);
  });

  it('renders MarkdownEditor containing markdown content cleanly in light and dark themes', () => {
    const markdownSample = '# Architecture\n\n```mermaid\ngraph TD\n  A[Client] --> B[Server]\n```\n';
    const handleChange = vi.fn();

    // Light theme test
    document.documentElement.setAttribute('data-theme', 'light');
    const { unmount } = render(
      <MarkdownEditor
        surface="description"
        value={markdownSample}
        onChange={handleChange}
        ariaLabel="Architecture Description"
        testId="md-editor-light"
      />,
    );
    expect(screen.getByTestId('md-editor-light-wysiwyg')).toBeDefined();
    unmount();

    // Dark theme test
    document.documentElement.setAttribute('data-theme', 'dark');
    render(
      <MarkdownEditor
        surface="description"
        value={markdownSample}
        onChange={handleChange}
        ariaLabel="Architecture Description Dark"
        testId="md-editor-dark"
      />,
    );
    expect(screen.getByTestId('md-editor-dark-wysiwyg')).toBeDefined();
  });
});
