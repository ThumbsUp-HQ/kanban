// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AvatarCropModal } from '../AvatarCropModal';

describe('AvatarCropModal', () => {
  const origImage = global.Image;

  beforeEach(() => {
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn().mockReturnValue('blob:mock-image'),
      revokeObjectURL: vi.fn(),
    });

    class MockImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      width = 800;
      height = 600;
      private _src = '';
      get src(): string {
        return this._src;
      }
      set src(val: string) {
        this._src = val;
        setTimeout(() => {
          if (this.onload) this.onload();
        }, 0);
      }
    }
    global.Image = MockImage as unknown as typeof Image;

    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
      clearRect: vi.fn(),
      drawImage: vi.fn(),
    });

    HTMLCanvasElement.prototype.toBlob = vi.fn().mockImplementation((cb: (blob: Blob | null) => void) => {
      cb(new Blob(['mock-png-bytes'], { type: 'image/png' }));
    });
  });

  afterEach(() => {
    global.Image = origImage;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders crop modal and handles zoom adjustments via buttons and slider', async () => {
    const file = new File(['image-content'], 'test.png', { type: 'image/png' });
    const onSave = vi.fn();
    const onClose = vi.fn();

    render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);

    expect(screen.getByTestId('avatar-crop-modal')).toBeDefined();
    expect(screen.getByText('Crop Profile Picture')).toBeDefined();

    // Wait for image onload to execute
    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-zoom-value').textContent).toBe('1.0x');
    });

    // Zoom in button
    const zoomInBtn = screen.getByTestId('avatar-crop-zoom-in');
    fireEvent.click(zoomInBtn);
    expect(screen.getByTestId('avatar-crop-zoom-value').textContent).toBe('1.2x');

    // Zoom out button
    const zoomOutBtn = screen.getByTestId('avatar-crop-zoom-out');
    fireEvent.click(zoomOutBtn);
    expect(screen.getByTestId('avatar-crop-zoom-value').textContent).toBe('1.0x');

    // Zoom slider
    const slider = screen.getByTestId('avatar-crop-zoom-slider');
    fireEvent.change(slider, { target: { value: '2.5' } });
    expect(screen.getByTestId('avatar-crop-zoom-value').textContent).toBe('2.5x');
  });

  it('handles mouse wheel zoom and keyboard arrow panning', async () => {
    const file = new File(['image-content'], 'test.png', { type: 'image/png' });
    const onSave = vi.fn();
    const onClose = vi.fn();

    render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);

    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-zoom-value').textContent).toBe('1.0x');
    });

    const viewport = screen.getByTestId('avatar-crop-viewport');

    // Wheel zoom in
    fireEvent.wheel(viewport, { deltaY: -100 });
    expect(screen.getByTestId('avatar-crop-zoom-value').textContent).toBe('1.1x');

    // Wheel zoom out
    fireEvent.wheel(viewport, { deltaY: 100 });
    expect(screen.getByTestId('avatar-crop-zoom-value').textContent).toBe('1.0x');

    // Zoom in with slider first so panning has range
    fireEvent.change(screen.getByTestId('avatar-crop-zoom-slider'), { target: { value: '3.0' } });

    // Keyboard arrow keys
    fireEvent.keyDown(viewport, { key: 'ArrowRight' });
    fireEvent.keyDown(viewport, { key: 'ArrowLeft' });
    fireEvent.keyDown(viewport, { key: 'ArrowDown' });
    fireEvent.keyDown(viewport, { key: 'ArrowUp' });
    fireEvent.keyDown(viewport, { key: 'Enter' }); // Ignored non-arrow key
  });

  it('handles pointer drag and multi-pointer pinch zoom', async () => {
    const file = new File(['image-content'], 'test.png', { type: 'image/png' });
    const onSave = vi.fn();
    const onClose = vi.fn();

    render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);

    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-viewport')).toBeDefined();
    });

    const viewport = screen.getByTestId('avatar-crop-viewport');
    viewport.setPointerCapture = vi.fn();

    // Zoom in first to allow pan
    fireEvent.change(screen.getByTestId('avatar-crop-zoom-slider'), { target: { value: '2.0' } });

    // 1. Single pointer drag
    fireEvent.pointerDown(viewport, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(viewport, { pointerId: 1, clientX: 140, clientY: 130 });
    fireEvent.pointerUp(viewport, { pointerId: 1 });

    // 2. Two pointer pinch
    fireEvent.pointerDown(viewport, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerDown(viewport, { pointerId: 2, clientX: 200, clientY: 100 });
    // Move pointers further apart (pinch in/out)
    fireEvent.pointerMove(viewport, { pointerId: 2, clientX: 250, clientY: 100 });
    // Release pointer 2 (transitions back to 1 active pointer)
    fireEvent.pointerUp(viewport, { pointerId: 2 });
    // Release pointer 1
    fireEvent.pointerUp(viewport, { pointerId: 1 });
  });

  it('handles Escape key, close button, cancel button, and backdrop click', () => {
    const file = new File(['image-content'], 'test.png', { type: 'image/png' });
    const onSave = vi.fn();
    const onClose = vi.fn();

    const { rerender } = render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);

    // Close button
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);

    // Cancel button
    fireEvent.click(screen.getByTestId('avatar-crop-cancel-btn'));
    expect(onClose).toHaveBeenCalledTimes(2);

    // Clicking inside the modal card does not trigger onClose
    fireEvent.click(screen.getByText('Crop Profile Picture'));
    expect(onClose).toHaveBeenCalledTimes(2);

    // Backdrop click
    const backdrop = screen.getByTestId('avatar-crop-modal');
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(3);

    // Escape key
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(4);

    // Other key ignored
    fireEvent.keyDown(window, { key: 'Tab' });
    expect(onClose).toHaveBeenCalledTimes(4);

    // When isSaving is true, Escape and Backdrop do not call onClose
    rerender(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} isSaving={true} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(4);
  });

  it('exports 512x512 raster blob and calls onSave', async () => {
    const file = new File(['image-content'], 'test.png', { type: 'image/png' });
    const onSave = vi.fn();
    const onClose = vi.fn();

    render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);

    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-save-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('avatar-crop-save-btn'));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
      const calledArg: unknown = onSave.mock.calls[0]?.[0];
      expect(calledArg).toBeDefined();
    });
  });

  it('handles image error gracefully and falls back to original file when canvas fails', async () => {
    class FailingImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      width = 0;
      height = 0;
      private _src = '';
      get src(): string {
        return this._src;
      }
      set src(val: string) {
        this._src = val;
        setTimeout(() => {
          if (this.onerror) this.onerror();
        }, 0);
      }
    }
    global.Image = FailingImage as unknown as typeof Image;

    const file = new File(['corrupt-data'], 'bad.png', { type: 'image/png' });
    const onSave = vi.fn();
    const onClose = vi.fn();

    render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);

    // Even if image fails to load, Save Picture falls back to onSave(file)
    fireEvent.click(screen.getByTestId('avatar-crop-save-btn'));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(file);
    });
  });

  it('covers export canvas fallback branches when context or blob is missing', async () => {
    const file = new File(['image-content'], 'test.png', { type: 'image/png' });
    const onSave = vi.fn();
    const onClose = vi.fn();

    // 1. getContext returns null for exportCanvas
    const getContextSpy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function (
      this: HTMLCanvasElement,
    ) {
      if (this.width === 512) {
        return null;
      }
      return { clearRect: vi.fn(), drawImage: vi.fn() } as unknown as CanvasRenderingContext2D;
    });

    const { unmount } = render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-save-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('avatar-crop-save-btn'));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(file);
    });
    unmount();
    getContextSpy.mockRestore();

    // 2. toBlob returns null blob
    const toBlobSpy = vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((cb: (blob: Blob | null) => void) => {
      cb(null);
    });

    const onSave2 = vi.fn();
    const { unmount: unmount2 } = render(<AvatarCropModal file={file} onSave={onSave2} onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-save-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('avatar-crop-save-btn'));
    await waitFor(() => {
      expect(onSave2).toHaveBeenCalledWith(file);
    });
    unmount2();
    toBlobSpy.mockRestore();

    // 3. toBlob is undefined
    // eslint-disable-next-line @typescript-eslint/unbound-method
    const origToBlob = HTMLCanvasElement.prototype.toBlob;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-member-access
    delete (HTMLCanvasElement.prototype as any).toBlob;

    const onSave3 = vi.fn();
    render(<AvatarCropModal file={file} onSave={onSave3} onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-save-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('avatar-crop-save-btn'));
    await waitFor(() => {
      expect(onSave3).toHaveBeenCalledWith(file);
    });
    HTMLCanvasElement.prototype.toBlob = origToBlob;
  });

  it('covers pointer move without active pointer and pointer transitions', async () => {
    const file = new File(['image-content'], 'test.png', { type: 'image/png' });
    const onSave = vi.fn();
    const onClose = vi.fn();

    render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-viewport')).toBeDefined();
    });

    const viewport = screen.getByTestId('avatar-crop-viewport');
    viewport.setPointerCapture = vi.fn();

    // Pointer move when pointer is not active
    fireEvent.pointerMove(viewport, { pointerId: 999, clientX: 50, clientY: 50 });

    // Two pointer pinch with distance shrinking and growing to zoom clamps
    fireEvent.pointerDown(viewport, { pointerId: 10, clientX: 100, clientY: 100 });
    fireEvent.pointerDown(viewport, { pointerId: 20, clientX: 200, clientY: 100 });
    // Shrink distance (factor < 1, hits Math.max(1.0, ...))
    fireEvent.pointerMove(viewport, { pointerId: 20, clientX: 105, clientY: 100 });
    // Expand distance (factor > 4, hits Math.min(4.0, ...))
    fireEvent.pointerMove(viewport, { pointerId: 20, clientX: 800, clientY: 100 });
    // Release pointer 20 while pointer 10 remains
    fireEvent.pointerUp(viewport, { pointerId: 20 });
    // Now move pointer 10 while single active pointer
    fireEvent.pointerMove(viewport, { pointerId: 10, clientX: 120, clientY: 120 });
    // Release pointer 10
    fireEvent.pointerUp(viewport, { pointerId: 10 });

    // Three pointer transition to test size > 2 branches
    fireEvent.pointerDown(viewport, { pointerId: 101, clientX: 100, clientY: 100 });
    fireEvent.pointerDown(viewport, { pointerId: 102, clientX: 200, clientY: 100 });
    fireEvent.pointerDown(viewport, { pointerId: 103, clientX: 300, clientY: 100 });
    fireEvent.pointerMove(viewport, { pointerId: 103, clientX: 310, clientY: 110 });
    fireEvent.pointerUp(viewport, { pointerId: 103 }); // leaves 2 active
    fireEvent.pointerUp(viewport, { pointerId: 102 }); // leaves 1 active
    fireEvent.pointerUp(viewport, { pointerId: 101 }); // leaves 0 active
  });

  it('handles null canvas context and pre-load user interactions', () => {
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue(null);

    class SlowImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      width = 500;
      height = 500;
      private _src = '';
      get src(): string {
        return this._src;
      }
      set src(val: string) {
        this._src = val;
        // Never automatically fire onload to test interactions before image loads
      }
    }
    global.Image = SlowImage as unknown as typeof Image;

    const file = new File(['image-content'], 'test.png', { type: 'image/png' });
    const onSave = vi.fn();
    const onClose = vi.fn();

    const { unmount } = render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);
    const viewport = screen.getByTestId('avatar-crop-viewport');

    // Zoom buttons, wheel, slider, and keyboard while image is not yet loaded
    fireEvent.click(screen.getByTestId('avatar-crop-zoom-in'));
    fireEvent.click(screen.getByTestId('avatar-crop-zoom-out'));
    fireEvent.wheel(viewport, { deltaY: -50 });
    fireEvent.keyDown(viewport, { key: 'ArrowLeft' });
    fireEvent.change(screen.getByTestId('avatar-crop-zoom-slider'), { target: { value: '2.0' } });

    // Multi-pointer pinch before image loads
    fireEvent.pointerDown(viewport, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerDown(viewport, { pointerId: 2, clientX: 200, clientY: 100 });
    fireEvent.pointerMove(viewport, { pointerId: 2, clientX: 250, clientY: 100 });
    fireEvent.pointerUp(viewport, { pointerId: 2 });
    fireEvent.pointerUp(viewport, { pointerId: 1 });

    // Unmount before image loads to test cleanup
    unmount();
  });

  it('handles null 2d context when image is loaded in AvatarCropModal', async () => {
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue(null);
    const file = new File(['image-content'], 'test.png', { type: 'image/png' });
    const onSave = vi.fn();
    const onClose = vi.fn();
    render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-modal')).toBeDefined();
    });
  });

  it('handles toBlob returning null and fallback when toBlob is undefined', async () => {
    const file = new File(['image-content'], 'test.png', { type: 'image/png' });
    const onSave = vi.fn();
    const onClose = vi.fn();

    // 1. toBlob returns null
    HTMLCanvasElement.prototype.toBlob = vi.fn().mockImplementation((cb: (blob: Blob | null) => void) => {
      cb(null);
    });
    const { unmount } = render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-zoom-value').textContent).toBe('1.0x');
    });
    fireEvent.click(screen.getByTestId('avatar-crop-save-btn'));
    expect(onSave).toHaveBeenCalledWith(file);
    unmount();

    // 2. toBlob is undefined
    const onSave2 = vi.fn();
    const origDescriptor = Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype, 'toBlob');
    // @ts-expect-error testing missing toBlob
    delete HTMLCanvasElement.prototype.toBlob;
    render(<AvatarCropModal file={file} onSave={onSave2} onClose={onClose} />);
    await waitFor(() => {
      expect(screen.getByTestId('avatar-crop-zoom-value').textContent).toBe('1.0x');
    });
    fireEvent.click(screen.getByTestId('avatar-crop-save-btn'));
    expect(onSave2).toHaveBeenCalledWith(file);
    if (origDescriptor) {
      Object.defineProperty(HTMLCanvasElement.prototype, 'toBlob', origDescriptor);
    }
  });

  describe('StudioDocLink Header Integration (KAN-499)', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
    });

    it('renders avatar-crop-doc-link with correct href, label, and ARIA title in Light and Dark themes', () => {
      const file = new File(['image-content'], 'test.png', { type: 'image/png' });
      const onSave = vi.fn();
      const onClose = vi.fn();

      for (const theme of ['light', 'dark'] as const) {
        document.documentElement.setAttribute('data-theme', theme);
        const { unmount } = render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);

        const docLink = screen.getByTestId('avatar-crop-doc-link');
        expect(docLink).toBeDefined();
        expect(docLink.getAttribute('href')).toBe(
          '/docs/studio-configuration-reference#user-avatars-profile-media',
        );
        expect(docLink.getAttribute('aria-label')).toBe(
          'User Avatars & Profile Media Documentation',
        );
        expect(docLink.textContent).toContain('Documentation ->');

        const headerActions = docLink.closest('.kb-avatar-crop-header-actions');
        expect(headerActions).not.toBeNull();
        expect(headerActions?.closest('.kb-avatar-crop-header')).not.toBeNull();

        unmount();
      }
    });

    it('supports keyboard focus and interaction on StudioDocLink', () => {
      const file = new File(['image-content'], 'test.png', { type: 'image/png' });
      const onSave = vi.fn();
      const onClose = vi.fn();

      render(<AvatarCropModal file={file} onSave={onSave} onClose={onClose} />);

      const docLink = screen.getByTestId('avatar-crop-doc-link');
      docLink.focus();
      expect(document.activeElement).toBe(docLink);
      expect(docLink.tagName.toLowerCase()).toBe('a');
      expect(docLink.getAttribute('aria-label')).toBe(
        'User Avatars & Profile Media Documentation',
      );
    });
  });
});
