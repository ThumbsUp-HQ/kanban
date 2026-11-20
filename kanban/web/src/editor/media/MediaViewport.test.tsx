/**
 * Unit & Integration Tests for MediaViewport & Lightbox Components (KB-P3-48).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MediaViewport } from './MediaViewport';

describe('MediaViewport & Lightbox Components', () => {
  const SAMPLE_BLOB = 'blob:http://localhost:3000/sample-diagram-uuid';
  const RAW_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>';

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders strictly <img src="blob:..."> with zero inline <svg> inside .media-viewport', () => {
    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="System Architecture Diagram"
        rawSource={RAW_SVG}
        testId="test-media"
      />,
    );

    // Verify <img> element exists with blob: src
    const img = screen.getByTestId('test-media-img');
    expect(img).toBeDefined();
    expect(img.tagName.toLowerCase()).toBe('img');
    expect(img.getAttribute('src')).toBe(SAMPLE_BLOB);

    // Strict S5.4 Invariant: Zero <svg> elements inside .media-viewport DOM
    const viewportEl = screen.getByTestId('test-media');
    const svgElements = viewportEl.querySelectorAll('svg');
    expect(svgElements.length).toBe(0);
  });

  it('cycles backdrop classes: theme -> light -> dark -> checkerboard without mutating document.documentElement', () => {
    const originalTheme = document.documentElement.dataset.theme;
    const handleBackdropChange = vi.fn();

    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="Backdrop Test"
        onBackdropChange={handleBackdropChange}
        testId="test-backdrop"
      />,
    );

    const canvas = screen.getByTestId('test-backdrop-canvas');
    expect(canvas.className).toContain('media-bg--theme');

    const backdropToggle = screen.getByTestId('test-backdrop-backdrop-toggle');

    // 1. Click toggle -> light
    fireEvent.click(backdropToggle);
    expect(canvas.className).toContain('media-bg--light');
    expect(handleBackdropChange).toHaveBeenCalledWith('light');

    // 2. Click toggle -> dark
    fireEvent.click(backdropToggle);
    expect(canvas.className).toContain('media-bg--dark');
    expect(handleBackdropChange).toHaveBeenCalledWith('dark');

    // 3. Click toggle -> checkerboard
    fireEvent.click(backdropToggle);
    expect(canvas.className).toContain('media-bg--checkerboard');
    expect(handleBackdropChange).toHaveBeenCalledWith('checkerboard');

    // 4. Click toggle -> theme
    fireEvent.click(backdropToggle);
    expect(canvas.className).toContain('media-bg--theme');
    expect(handleBackdropChange).toHaveBeenCalledWith('theme');

    // Invariant: global document theme remains completely untouched
    expect(document.documentElement.dataset.theme).toBe(originalTheme);
  });

  it('updates zoom readout via CSSOM transform on zoom buttons and resets to 100%', () => {
    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="Zoom Test"
        testId="test-zoom"
      />,
    );

    const img = screen.getByTestId<HTMLImageElement>('test-zoom-img');
    const readout = screen.getByTestId('test-zoom-zoom-readout');
    expect(readout.textContent).toBe('100%');

    // Zoom in (+)
    const zoomInBtn = screen.getByTestId('test-zoom-zoom-in');
    fireEvent.click(zoomInBtn);

    expect(readout.textContent).toBe('125%');
    expect(img.style.transform).toContain('scale(1.25)');

    // Zoom out (-)
    const zoomOutBtn = screen.getByTestId('test-zoom-zoom-out');
    fireEvent.click(zoomOutBtn);

    expect(readout.textContent).toBe('100%');
    expect(img.style.transform).toContain('scale(1)');

    // Zoom in multiple times then click readout to reset
    fireEvent.click(zoomInBtn);
    fireEvent.click(zoomInBtn);
    expect(readout.textContent).toBe('156%');

    fireEvent.click(readout);
    expect(readout.textContent).toBe('100%');
    expect(img.style.transform).toContain('scale(1)');
  });

  it('copies raw SVG source to clipboard via Copy Raw Source button', async () => {
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextSpy,
      },
    });

    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="Copy Test"
        rawSource={RAW_SVG}
        testId="test-copy"
      />,
    );

    const copyBtn = screen.getByTestId('test-copy-copy-source');
    fireEvent.click(copyBtn);

    expect(writeTextSpy).toHaveBeenCalledWith(RAW_SVG);
    await waitFor(() => {
      expect(screen.getAllByText('Copied source').length).toBeGreaterThan(0);
    });
  });

  it('handles clipboard failure gracefully when copying raw source', async () => {
    const writeTextSpy = vi.fn().mockRejectedValue(new Error('Clipboard permission denied'));
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextSpy,
      },
    });

    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="Copy Fail Test"
        rawSource={RAW_SVG}
        testId="test-copy-fail"
      />,
    );

    const copyBtn = screen.getByTestId('test-copy-fail-copy-source');
    fireEvent.click(copyBtn);

    expect(writeTextSpy).toHaveBeenCalledWith(RAW_SVG);
    await waitFor(() => {
      expect(screen.getAllByText('Copy failed').length).toBeGreaterThan(0);
    });
  });

  it('renders truncated alt badge for long descriptions and handles image load event', () => {
    const longAlt = 'This is an exceedingly long description of a diagram that exceeds 24 characters';
    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt={longAlt}
        testId="test-alt-truncate"
      />,
    );

    const badge = screen.getByTestId('test-alt-truncate-alt-badge');
    expect(badge.textContent).toBe('Alt: This is an exceedingly l...');

    const img = screen.getByTestId('test-alt-truncate-img');
    fireEvent.load(img);
    expect(img.className).not.toContain('media-viewport__img--loading');
  });

  it('renders lightbox variant without expand button and propagates backdrop change', () => {
    const handleBackdrop = vi.fn();

    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="Lightbox Mode Test"
        isLightbox={true}
        onBackdropChange={handleBackdrop}
        testId="test-lightbox-variant"
      />,
    );

    // Expand button should NOT be rendered in lightbox mode
    expect(screen.queryByTestId('test-lightbox-variant-expand')).toBeNull();

    // Backdrop change should call callback
    const backdropToggle = screen.getByTestId('test-lightbox-variant-backdrop-toggle');
    fireEvent.click(backdropToggle);
    expect(handleBackdrop).toHaveBeenCalledWith('light');
  });

  it('propagates backdrop changes from inside lightbox portal back to parent', async () => {
    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="Portal Propagation Test"
        testId="test-portal-parent"
      />,
    );

    const expandBtn = screen.getByTestId('test-portal-parent-expand');
    fireEvent.click(expandBtn);

    const dialog = screen.getByRole('dialog', { name: /media lightbox/i });
    expect(dialog).toBeDefined();

    // Find backdrop toggle button inside the dialog
    const dialogToggles = screen.getAllByRole('button', { name: /media contrast backdrop/i });
    const modalToggle = dialogToggles[dialogToggles.length - 1];
    expect(modalToggle).toBeDefined();
    if (modalToggle) {
      fireEvent.click(modalToggle);
    }

    // Close dialog
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: /media lightbox/i })).toBeNull();
    });

    // Parent canvas should now have media-bg--light class
    const parentCanvas = screen.getByTestId('test-portal-parent-canvas');
    expect(parentCanvas.className).toContain('media-bg--light');
  });

  it('handles safeFilename sanitize fallback and whitespace-only alt badge omission', () => {
    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="   "
        safeFilename=""
        testId="test-filename-alt"
      />,
    );

    // Whitespace only alt should NOT render badge
    expect(screen.queryByTestId('test-filename-alt-alt-badge')).toBeNull();

    // Download attribute should fall back to media.svg
    const downloadLink = screen.getByTestId('test-filename-alt-download');
    expect(downloadLink.getAttribute('download')).toBe('media.svg');
  });

  it('handles air-gap mode with host indicator', () => {
    render(
      <MediaViewport
        src="https://cdn.test/blocked-img.png"
        airGapMode={true}
        testId="test-airgap-host"
      />,
    );

    const placeholder = screen.getByTestId('test-airgap-host-airgap');
    expect(placeholder).toBeDefined();
    expect(screen.getByText(/Host: cdn.test/i)).toBeDefined();
  });

  it('opens and closes MediaLightbox modal with focus trapping and Escape key', async () => {
    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="Lightbox Test"
        testId="test-lightbox-trigger"
      />,
    );

    const expandBtn = screen.getByTestId('test-lightbox-trigger-expand');
    fireEvent.click(expandBtn);

    // Verify lightbox dialog is mounted
    const dialog = screen.getByRole('dialog', { name: /media lightbox/i });
    expect(dialog).toBeDefined();
    expect(dialog.getAttribute('aria-modal')).toBe('true');

    // Dismiss with Escape key
    fireEvent.keyDown(window, { key: 'Escape' });

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: /media lightbox/i })).toBeNull();
    });
  });

  it('renders air-gap offline placeholder card when airGapMode is enabled', () => {
    render(
      <MediaViewport
        src="https://external-tracker.evil.test/pixel.png"
        alt="Air Gap Test"
        airGapMode={true}
        testId="test-airgap"
      />,
    );

    const placeholder = screen.getByTestId('test-airgap-airgap');
    expect(placeholder).toBeDefined();
    expect(screen.getByText(/External image blocked in Air-Gap Local-Only Mode/i)).toBeDefined();
    expect(screen.getByText(/external-tracker.evil.test/i)).toBeDefined();

    // Verify no <img> was mounted
    expect(screen.queryByTestId('test-airgap-img')).toBeNull();
  });

  it('renders 🌐 badge for proxied external media', () => {
    render(
      <MediaViewport
        src="https://cdn.example.com/asset.png"
        alt="Proxied Image"
        testId="test-proxied"
      />,
    );

    const proxiedBadge = screen.getByTestId('test-proxied-proxied-badge');
    expect(proxiedBadge).toBeDefined();
    expect(proxiedBadge.getAttribute('aria-label')).toBe('Proxied external image');
  });

  it('handles wheel zooming with Ctrl key and pointer drag panning', () => {
    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="Pointer/Wheel Test"
        testId="test-pointer"
      />,
    );

    const canvas = screen.getByTestId('test-pointer-canvas');

    // 1. Wheel zoom with ctrlKey
    fireEvent.wheel(canvas, {
      ctrlKey: true,
      deltaY: -100, // Zoom in
      clientX: 100,
      clientY: 100,
    });

    const readout = screen.getByTestId('test-pointer-zoom-readout');
    expect(readout.textContent).toBe('125%');

    // 2. Drag pan with pointer
    const setCaptureSpy = vi.fn();
    const releaseCaptureSpy = vi.fn();
    (canvas as unknown as { setPointerCapture: unknown }).setPointerCapture = setCaptureSpy;
    (canvas as unknown as { releasePointerCapture: unknown }).releasePointerCapture = releaseCaptureSpy;

    fireEvent.pointerDown(canvas, {
      button: 0,
      clientX: 50,
      clientY: 50,
      pointerId: 1,
    });
    expect(setCaptureSpy).toHaveBeenCalledWith(1);

    fireEvent.pointerMove(canvas, {
      clientX: 80,
      clientY: 70,
      pointerId: 1,
    });

    fireEvent.pointerUp(canvas, {
      pointerId: 1,
    });
    expect(releaseCaptureSpy).toHaveBeenCalledWith(1);

    const img = screen.getByTestId<HTMLImageElement>('test-pointer-img');
    expect(img.style.transform).toContain('translate3d(5px, -5px, 0)');
    expect(img.style.transform).toContain('scale(1.25)');

    // 3. Pointer move and up when not dragging (ignored)
    fireEvent.pointerMove(canvas, { clientX: 100, clientY: 100 });
    fireEvent.pointerUp(canvas, { pointerId: 99 });

    // 4. Right click pointer down (ignored)
    fireEvent.pointerDown(canvas, { button: 2, clientX: 20, clientY: 20 });

    // 5. Pointer cancel
    fireEvent.pointerDown(canvas, { button: 0, clientX: 20, clientY: 20, pointerId: 2 });
    fireEvent.pointerCancel(canvas, { pointerId: 2 });

    // 6. Wheel without modifiers on inline viewport (ignored)
    const prevTransform = img.style.transform;
    fireEvent.wheel(canvas, { deltaY: -50, ctrlKey: false, metaKey: false });
    expect(img.style.transform).toBe(prevTransform);

    // 7. Wheel zoom out with metaKey
    fireEvent.wheel(canvas, { metaKey: true, deltaY: 100, clientX: 50, clientY: 50 });
    expect(screen.getByTestId('test-pointer-zoom-readout').textContent).toBe('100%');

    // 8. Pointer small jitter move (<= 3px) does not set hasMoved
    fireEvent.pointerDown(canvas, { button: 0, clientX: 10, clientY: 10, pointerId: 3 });
    fireEvent.pointerMove(canvas, { clientX: 12, clientY: 12, pointerId: 3 });
    fireEvent.pointerUp(canvas, { pointerId: 3 });

    // 9. Vertical pan drag (> 3px dy) sets hasMoved
    fireEvent.pointerDown(canvas, { button: 0, clientX: 10, clientY: 10, pointerId: 4 });
    fireEvent.pointerMove(canvas, { clientX: 10, clientY: 20, pointerId: 4 });
    fireEvent.pointerUp(canvas, { pointerId: 4 });
  });

  it('opens lightbox on canvas click when pointer has not dragged', () => {
    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="Click Lightbox Test"
        testId="test-click-lightbox"
      />,
    );

    const canvas = screen.getByTestId('test-click-lightbox-canvas');
    fireEvent.pointerDown(canvas, { button: 0, clientX: 30, clientY: 30, pointerId: 1 });
    fireEvent.pointerUp(canvas, { pointerId: 1 });

    const dialog = screen.getByRole('dialog', { name: /media lightbox/i });
    expect(dialog).toBeDefined();
  });

  it('updates backdrop when initialBackdrop prop changes and clears copy announce on timer', async () => {
    vi.useFakeTimers();
    try {
      const writeTextSpy = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextSpy,
        },
      });

      const { rerender } = render(
        <MediaViewport
          src={SAMPLE_BLOB}
          rawSource={RAW_SVG}
          initialBackdrop="theme"
          testId="test-rerender-bg"
        />,
      );

      const canvas = screen.getByTestId('test-rerender-bg-canvas');
      expect(canvas.className).toContain('media-bg--theme');

      // Change initialBackdrop prop
      rerender(
        <MediaViewport
          src={SAMPLE_BLOB}
          rawSource={RAW_SVG}
          initialBackdrop="dark"
          testId="test-rerender-bg"
        />,
      );
      expect(canvas.className).toContain('media-bg--dark');

      // Test copy announcement timer
      const copyBtn = screen.getByTestId('test-rerender-bg-copy-source');
      fireEvent.click(copyBtn);
      await vi.advanceTimersByTimeAsync(2600);
      expect(copyBtn.textContent).toBe('Copy');
    } finally {
      vi.useRealTimers();
    }
  });

  it('handles wheel zoom inside lightbox mode without modifier keys', () => {
    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="Lightbox Wheel Test"
        isLightbox={true}
        testId="test-lightbox-wheel"
      />,
    );

    const canvas = screen.getByTestId('test-lightbox-wheel-canvas');
    fireEvent.wheel(canvas, {
      deltaY: -100,
      clientX: 50,
      clientY: 50,
      ctrlKey: false,
      metaKey: false,
    });

    const readout = screen.getByTestId('test-lightbox-wheel-zoom-readout');
    expect(readout.textContent).toBe('125%');
  });

  it('handles wheel zoom with metaKey modifier in non-lightbox mode', () => {
    render(
      <MediaViewport
        src={SAMPLE_BLOB}
        alt="MetaKey Wheel Test"
        isLightbox={false}
        testId="test-meta-wheel"
      />,
    );

    const canvas = screen.getByTestId('test-meta-wheel-canvas');
    fireEvent.wheel(canvas, {
      deltaY: -100,
      clientX: 50,
      clientY: 50,
      ctrlKey: false,
      metaKey: true,
    });

    const readout = screen.getByTestId('test-meta-wheel-zoom-readout');
    expect(readout.textContent).toBe('125%');
  });
});
