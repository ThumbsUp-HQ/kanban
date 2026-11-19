// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AvatarLightboxModal } from '../AvatarLightboxModal';

describe('AvatarLightboxModal', () => {
  const origImage = global.Image;

  beforeEach(() => {
    class MockImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      crossOrigin = '';
      width = 600;
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
  });

  afterEach(() => {
    global.Image = origImage;
    vi.restoreAllMocks();
  });

  it('renders lightbox dialog with title and handles zoom adjustments', async () => {
    const onClose = vi.fn();
    render(
      <AvatarLightboxModal
        avatarUrl="/api/v1/users/user-123/avatar"
        displayName="Alice Developer"
        onClose={onClose}
      />,
    );

    expect(screen.getByTestId('avatar-lightbox-modal')).toBeDefined();
    expect(screen.getByText('Alice Developer Picture')).toBeDefined();

    await waitFor(() => {
      expect(screen.getByTestId('avatar-lightbox-zoom-value').textContent).toBe('1.0x');
    });

    // Zoom in
    fireEvent.click(screen.getByTestId('avatar-lightbox-zoom-in'));
    expect(screen.getByTestId('avatar-lightbox-zoom-value').textContent).toBe('1.2x');

    // Zoom out
    fireEvent.click(screen.getByTestId('avatar-lightbox-zoom-out'));
    expect(screen.getByTestId('avatar-lightbox-zoom-value').textContent).toBe('1.0x');

    // Zoom slider
    fireEvent.change(screen.getByTestId('avatar-lightbox-zoom-slider'), { target: { value: '3.0' } });
    expect(screen.getByTestId('avatar-lightbox-zoom-value').textContent).toBe('3.0x');

    // Reset zoom button
    fireEvent.click(screen.getByTestId('avatar-lightbox-reset-btn'));
    expect(screen.getByTestId('avatar-lightbox-zoom-value').textContent).toBe('1.0x');
  });

  it('handles mouse wheel, keyboard arrows, and pointer dragging', async () => {
    const onClose = vi.fn();
    render(
      <AvatarLightboxModal
        avatarUrl="/api/v1/users/user-123/avatar"
        displayName="Alice Developer"
        onClose={onClose}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('avatar-lightbox-viewport')).toBeDefined();
    });

    const viewport = screen.getByTestId('avatar-lightbox-viewport');
    viewport.setPointerCapture = vi.fn();

    // Wheel zoom in and out
    fireEvent.wheel(viewport, { deltaY: -100 });
    expect(screen.getByTestId('avatar-lightbox-zoom-value').textContent).toBe('1.1x');
    fireEvent.wheel(viewport, { deltaY: 100 });
    expect(screen.getByTestId('avatar-lightbox-zoom-value').textContent).toBe('1.0x');

    // Zoom in with slider first so pan has range
    fireEvent.change(screen.getByTestId('avatar-lightbox-zoom-slider'), { target: { value: '2.5' } });

    // Keyboard arrow keys
    fireEvent.keyDown(viewport, { key: 'ArrowRight' });
    fireEvent.keyDown(viewport, { key: 'ArrowLeft' });
    fireEvent.keyDown(viewport, { key: 'ArrowDown' });
    fireEvent.keyDown(viewport, { key: 'ArrowUp' });
    fireEvent.keyDown(viewport, { key: 'Enter' });

    // Pointer drag
    fireEvent.pointerDown(viewport, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(viewport, { pointerId: 1, clientX: 150, clientY: 120 });
    fireEvent.pointerUp(viewport, { pointerId: 1 });

    // 2-pointer pinch
    fireEvent.pointerDown(viewport, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerDown(viewport, { pointerId: 2, clientX: 200, clientY: 100 });
    fireEvent.pointerMove(viewport, { pointerId: 2, clientX: 250, clientY: 100 });
    fireEvent.pointerUp(viewport, { pointerId: 2 });
    fireEvent.pointerUp(viewport, { pointerId: 1 });
  });

  it('handles close button, backdrop click, and Escape key', () => {
    const onClose = vi.fn();
    render(
      <AvatarLightboxModal
        avatarUrl="/api/v1/users/user-123/avatar"
        displayName=""
        onClose={onClose}
      />,
    );

    // Fallback displayName to 'User'
    expect(screen.getByText('User Picture')).toBeDefined();

    // Close button
    fireEvent.click(screen.getByTestId('avatar-lightbox-close-btn'));
    expect(onClose).toHaveBeenCalledTimes(1);

    // Clicking inside dialog card does not close
    fireEvent.click(screen.getByText('User Picture'));
    expect(onClose).toHaveBeenCalledTimes(1);

    // Backdrop click
    fireEvent.click(screen.getByTestId('avatar-lightbox-modal'));
    expect(onClose).toHaveBeenCalledTimes(2);

    // Escape key
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(3);

    // Other key
    fireEvent.keyDown(window, { key: 'Space' });
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('handles image loading error gracefully', async () => {
    class FailingImage {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      crossOrigin = '';
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
        }, 10);
      }
    }
    global.Image = FailingImage as unknown as typeof Image;

    const onClose = vi.fn();
    render(
      <AvatarLightboxModal
        avatarUrl="/api/v1/users/user-123/avatar"
        displayName="User"
        onClose={onClose}
      />,
    );

    expect(screen.getByTestId('avatar-lightbox-modal')).toBeDefined();
    // Wait for onerror to execute
    await new Promise((resolve) => setTimeout(resolve, 50));
  });

  it('covers pointer move without active pointer and pinch zoom clamping', async () => {
    const onClose = vi.fn();
    render(
      <AvatarLightboxModal
        avatarUrl="/api/v1/users/user-123/avatar"
        displayName="User"
        onClose={onClose}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('avatar-lightbox-viewport')).toBeDefined();
    });

    const viewport = screen.getByTestId('avatar-lightbox-viewport');
    viewport.setPointerCapture = vi.fn();

    // Move pointer that is not registered
    fireEvent.pointerMove(viewport, { pointerId: 999, clientX: 20, clientY: 20 });

    // Multi-pointer pinch clamp: shrink (1.0 clamp) and expand (4.0 clamp)
    fireEvent.pointerDown(viewport, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerDown(viewport, { pointerId: 2, clientX: 200, clientY: 100 });
    // Shrink distance
    fireEvent.pointerMove(viewport, { pointerId: 2, clientX: 102, clientY: 100 });
    // Expand distance
    fireEvent.pointerMove(viewport, { pointerId: 2, clientX: 900, clientY: 100 });
    // Release pointer 2
    fireEvent.pointerUp(viewport, { pointerId: 2 });
    // Move single remaining pointer 1
    fireEvent.pointerMove(viewport, { pointerId: 1, clientX: 130, clientY: 130 });
    // Release pointer 1
    fireEvent.pointerUp(viewport, { pointerId: 1 });

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
      }
    }
    global.Image = SlowImage as unknown as typeof Image;

    const onClose = vi.fn();
    const { unmount } = render(
      <AvatarLightboxModal
        avatarUrl="/api/v1/users/user-123/avatar"
        displayName="User"
        onClose={onClose}
      />,
    );

    const viewport = screen.getByTestId('avatar-lightbox-viewport');
    // Zoom in, zoom out, wheel, slider, pinch, and keydown before image loaded
    fireEvent.click(screen.getByTestId('avatar-lightbox-zoom-in'));
    fireEvent.click(screen.getByTestId('avatar-lightbox-zoom-out'));
    fireEvent.wheel(viewport, { deltaY: -50 });
    fireEvent.keyDown(viewport, { key: 'ArrowRight' });
    fireEvent.change(screen.getByTestId('avatar-lightbox-zoom-slider'), { target: { value: '2.0' } });

    // Multi-pointer pinch before image loaded
    fireEvent.pointerDown(viewport, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerDown(viewport, { pointerId: 2, clientX: 200, clientY: 100 });
    fireEvent.pointerMove(viewport, { pointerId: 2, clientX: 250, clientY: 100 });
    fireEvent.pointerUp(viewport, { pointerId: 2 });
    fireEvent.pointerUp(viewport, { pointerId: 1 });

    // Unmount before image loads
    unmount();
  });

  it('handles null 2d context when image is loaded', async () => {
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue(null);
    const onClose = vi.fn();
    render(
      <AvatarLightboxModal
        avatarUrl="/api/v1/users/user-123/avatar"
        displayName="User"
        onClose={onClose}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('avatar-lightbox-modal')).toBeDefined();
    });
  });
});
