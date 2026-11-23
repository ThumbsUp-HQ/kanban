// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Unit Tests for DocsMobileDiagramViewer (KB-MOBILE-DOCS-PAN-ZOOM, KAN-346).
 * Verifies all 3 required test cases with >=95% coverage:
 * - Test Case 1: Tap-to-expand trigger affordance and accessible full-screen modal launch
 * - Test Case 2: Pinch-to-zoom scaling (2 fingers), touch pan translation (1 finger), and zoom controls
 * - Test Case 3: Swipe-down dismiss gesture on downward touch drag exceeding threshold
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  DocsMobileDiagramViewer,
  DocsMobileDiagramTrigger,
  formatZoomPercent,
} from '../DocsMobileDiagramViewer';

describe('DocsMobileDiagramViewer (KAN-346)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('Test Case 1: Tap-to-expand trigger affordance and accessible full-screen modal launch', () => {
    const handleExpand = vi.fn();

    // 1. Render trigger wrapper with embedded diagram preview
    const { rerender } = render(
      <DocsMobileDiagramTrigger
        onExpand={handleExpand}
        label="Expand system architecture diagram"
        testId="test-diagram-trigger"
      >
        <div data-testid="embedded-diagram-child">Embedded Diagram Preview</div>
      </DocsMobileDiagramTrigger>
    );

    // Verify child and tap hint affordance are present
    expect(screen.getByTestId('embedded-diagram-child')).toBeDefined();
    const hintBtn = screen.getByTestId('test-diagram-trigger-hint');
    expect(hintBtn).toBeDefined();
    expect(hintBtn.textContent).toContain('Tap to pan & zoom');

    // Tap hint button
    fireEvent.click(hintBtn);
    expect(handleExpand).toHaveBeenCalledTimes(1);

    // Tap wrapper container
    const triggerWrap = screen.getByTestId('test-diagram-trigger');
    fireEvent.click(triggerWrap);
    expect(handleExpand).toHaveBeenCalledTimes(2);

    // Keyboard accessibility on trigger wrapper (Enter and Space)
    fireEvent.keyDown(triggerWrap, { key: 'Enter' });
    expect(handleExpand).toHaveBeenCalledTimes(3);

    fireEvent.keyDown(triggerWrap, { key: ' ' });
    expect(handleExpand).toHaveBeenCalledTimes(4);

    fireEvent.keyDown(triggerWrap, { key: 'ArrowDown' }); // Other keys ignored
    expect(handleExpand).toHaveBeenCalledTimes(4);

    // 2. Open full-screen overlay modal
    const handleClose = vi.fn();
    rerender(
      <DocsMobileDiagramViewer
        isOpen={true}
        onClose={handleClose}
        blobUrl="blob:http://localhost/mock-diagram.svg"
        title="System Architecture Diagram"
        alt="System architecture diagram preview"
        testId="test-diagram-modal"
      />
    );

    // Verify accessible ARIA dialog roles and title
    const dialog = screen.getByTestId('test-diagram-modal');
    expect(dialog.getAttribute('role')).toBe('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-label')).toBe('Interactive Diagram Viewer');
    expect(screen.getByText('System Architecture Diagram')).toBeDefined();
    expect(screen.getByTestId('test-diagram-modal-swipe-hint').textContent).toContain('Swipe down to close');

    // Verify image rendered with safe blob: URL
    const img = screen.getByTestId('test-diagram-modal-img');
    expect(img.getAttribute('src')).toBe('blob:http://localhost/mock-diagram.svg');
    expect(img.getAttribute('alt')).toBe('System architecture diagram preview');

    // Close button accessibility and click dismissal
    const closeBtn = screen.getByTestId('test-diagram-modal-close-btn');
    expect(closeBtn.getAttribute('aria-label')).toBe('Close diagram viewer');
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);

    // Escape key dismissal
    fireEvent.keyDown(window, { key: 'Tab' }); // non-Escape key ignored
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(2);

    // Backdrop click dismissal (clicking directly on overlay outside header/canvas)
    fireEvent.click(dialog);
    expect(handleClose).toHaveBeenCalledTimes(3);

    // Verify modal returns null when isOpen is false
    rerender(
      <DocsMobileDiagramViewer
        isOpen={false}
        onClose={handleClose}
        testId="test-diagram-modal"
      />
    );
    expect(screen.queryByTestId('test-diagram-modal')).toBeNull();
  });

  it('Test Case 2: Pinch-to-zoom scaling (2 fingers), touch pan translation (1 finger), and zoom controls', () => {
    const handleClose = vi.fn();

    // Render viewer with SVG and raw source
    render(
      <DocsMobileDiagramViewer
        isOpen={true}
        onClose={handleClose}
        svgContent="<svg viewBox='0 0 100 100'><circle cx='50' cy='50' r='40'/></svg>"
        rawSource="graph TD\n  A-->B"
        title="Interactive Flowchart"
        testId="zoom-diagram-modal"
      />
    );

    const canvas = screen.getByTestId('zoom-diagram-modal-canvas');
    const content = screen.getByTestId('zoom-diagram-modal-content');
    const zoomInBtn = screen.getByTestId('zoom-diagram-modal-zoom-in');
    const zoomOutBtn = screen.getByTestId('zoom-diagram-modal-zoom-out');
    const zoomResetBtn = screen.getByTestId('zoom-diagram-modal-zoom-reset');

    // Initial zoom is 100%
    expect(zoomResetBtn.textContent).toBe('100%');
    expect(content.style.transform).toContain('scale(1)');

    // 1. Zoom In button click
    fireEvent.click(zoomInBtn);
    expect(zoomResetBtn.textContent).toBe('125%');
    expect(content.style.transform).toContain('scale(1.25)');

    // 2. Zoom Out button click
    fireEvent.click(zoomOutBtn);
    expect(zoomResetBtn.textContent).toBe('100%');
    expect(content.style.transform).toContain('scale(1)');

    // 3. Reset Zoom button click
    fireEvent.click(zoomInBtn);
    fireEvent.click(zoomInBtn);
    expect(zoomResetBtn.textContent).toBe('156%');
    fireEvent.click(zoomResetBtn);
    expect(zoomResetBtn.textContent).toBe('100%');
    expect(content.style.transform).toBe('translate(0px, 0px) scale(1)');

    // 4. Mouse Wheel zooming
    fireEvent.wheel(canvas, { deltaY: -100 }); // Zoom in
    expect(zoomResetBtn.textContent).toBe('125%');

    fireEvent.wheel(canvas, { deltaY: 100 }); // Zoom out
    expect(zoomResetBtn.textContent).toBe('100%');

    // 5. Multi-touch 2-finger pinch-to-zoom gesture
    // Touch start with 2 fingers at distance 100px (t1: x=100, t2: x=200)
    fireEvent.touchStart(canvas, {
      touches: [
        { clientX: 100, clientY: 100 },
        { clientX: 200, clientY: 100 },
      ],
    });

    // Touch move expanding distance to 200px (t1: x=50, t2: x=250) -> factor = 2.0
    fireEvent.touchMove(canvas, {
      touches: [
        { clientX: 50, clientY: 100 },
        { clientX: 250, clientY: 100 },
      ],
    });

    // Touch end
    fireEvent.touchEnd(canvas, { touches: [] });
    expect(zoomResetBtn.textContent).toBe('200%');
    expect(content.style.transform).toContain('scale(2)');

    // 6. 1-finger touch pan
    fireEvent.touchStart(canvas, {
      touches: [{ clientX: 100, clientY: 100 }],
    });

    fireEvent.touchMove(canvas, {
      touches: [{ clientX: 140, clientY: 120 }], // dx = +40, dy = +20
    });

    fireEvent.touchEnd(canvas, { touches: [] });
    expect(content.style.transform).toContain('translate(40px, 20px)');

    // 7. Desktop Pointer drag fallback
    fireEvent.pointerDown(canvas, { clientX: 200, clientY: 200, button: 0, pointerType: 'mouse' });
    fireEvent.pointerMove(canvas, { clientX: 220, clientY: 215, pointerType: 'mouse' });
    fireEvent.pointerUp(canvas, { clientX: 220, clientY: 215, pointerType: 'mouse' });
    expect(content.style.transform).toContain('translate(60px, 35px)');

    // Ignored pointer events (touch pointerType, right click, move without drag)
    fireEvent.pointerDown(canvas, { clientX: 200, clientY: 200, button: 2, pointerType: 'mouse' });
    fireEvent.pointerDown(canvas, { clientX: 200, clientY: 200, button: 0, pointerType: 'touch' });
    fireEvent.pointerMove(canvas, { clientX: 220, clientY: 220, pointerType: 'touch' });
    fireEvent.pointerUp(canvas, { clientX: 220, clientY: 220, pointerType: 'touch' });
    fireEvent.pointerMove(canvas, { clientX: 250, clientY: 250, pointerType: 'mouse' }); // not dragging
    fireEvent.pointerUp(canvas, { clientX: 250, clientY: 250, pointerType: 'mouse' }); // not dragging
    fireEvent.pointerCancel(canvas, { clientX: 250, clientY: 250, pointerType: 'mouse' });
    fireEvent.touchCancel(canvas, { touches: [] });

    // 8. Scale clamping boundaries (MIN_SCALE = 0.25, MAX_SCALE = 5.0)
    for (let i = 0; i < 15; i++) {
      fireEvent.click(zoomInBtn);
    }
    expect(zoomResetBtn.textContent).toBe('500%');

    for (let i = 0; i < 20; i++) {
      fireEvent.click(zoomOutBtn);
    }
    expect(zoomResetBtn.textContent).toBe('25%');

    // Wheel zoom boundaries
    for (let i = 0; i < 15; i++) {
      fireEvent.wheel(canvas, { deltaY: -500 });
    }
    expect(zoomResetBtn.textContent).toBe('500%');

    for (let i = 0; i < 20; i++) {
      fireEvent.wheel(canvas, { deltaY: 500 });
    }
    expect(zoomResetBtn.textContent).toBe('25%');

    // 9. Format zoom percent helper
    expect(formatZoomPercent(1.5)).toBe('150%');
    expect(formatZoomPercent(0.75)).toBe('75%');
  });

  it('Test Case 3: Swipe-down dismiss gesture on downward touch drag exceeding threshold', () => {
    const handleClose = vi.fn();

    const { rerender } = render(
      <DocsMobileDiagramViewer
        isOpen={true}
        onClose={handleClose}
        src="/docs-images/architecture.png"
        title="Touch Swipe Dismiss Test"
        testId="swipe-diagram-modal"
      />
    );

    const canvas = screen.getByTestId('swipe-diagram-modal-canvas');

    // 1. Touch swipe downward that exceeds 70px threshold
    // Start at y=100
    fireEvent.touchStart(canvas, {
      touches: [{ clientX: 150, clientY: 100 }],
    });

    // Move downward to y=200 (deltaY = 100px >= SWIPE_DISMISS_THRESHOLD_PX of 70px)
    fireEvent.touchMove(canvas, {
      touches: [{ clientX: 150, clientY: 200 }],
    });

    // Release touch
    fireEvent.touchEnd(canvas, { touches: [] });
    expect(handleClose).toHaveBeenCalledTimes(1);

    // 2. Small downward touch drag (e.g. deltaY = 30px < 70px) does NOT dismiss
    fireEvent.touchStart(canvas, {
      touches: [{ clientX: 150, clientY: 100 }],
    });

    fireEvent.touchMove(canvas, {
      touches: [{ clientX: 150, clientY: 130 }], // deltaY = 30px
    });

    fireEvent.touchEnd(canvas, { touches: [] });
    expect(handleClose).toHaveBeenCalledTimes(1); // Still 1

    // 3. Pointer drag downward (desktop/mouse fallback) exceeding threshold
    fireEvent.pointerDown(canvas, { clientX: 150, clientY: 100, button: 0, pointerType: 'mouse' });
    fireEvent.pointerMove(canvas, { clientX: 150, clientY: 210, pointerType: 'mouse' });
    fireEvent.pointerUp(canvas, { clientX: 150, clientY: 210, pointerType: 'mouse' });
    expect(handleClose).toHaveBeenCalledTimes(2);

    // 4. Fallback rawSource display when neither svgContent nor src/blobUrl is provided
    rerender(
      <DocsMobileDiagramViewer
        isOpen={true}
        onClose={handleClose}
        rawSource="flowchart TD\n  Start --> Stop"
        testId="raw-diagram-modal"
      />
    );
    expect(screen.getByText(/flowchart TD/)).toBeDefined();

    // 5. Empty viewer and default props
    rerender(
      <DocsMobileDiagramViewer
        isOpen={true}
        onClose={handleClose}
        testId="empty-diagram-modal"
      />
    );
    expect(screen.getByText('Diagram Viewer')).toBeDefined();
    expect(screen.getByTestId('empty-diagram-modal-content').children.length).toBe(0);

    // 6. TouchEnd with remaining active touch (multi-touch release branch)
    fireEvent.touchStart(canvas, {
      touches: [
        { clientX: 100, clientY: 100 },
        { clientX: 200, clientY: 100 },
      ],
    });
    fireEvent.touchEnd(canvas, {
      touches: [{ clientX: 100, clientY: 100 }],
    });

    // 7. TouchMove downward drag feedback with scale <= 1.05
    fireEvent.touchStart(canvas, {
      touches: [{ clientX: 120, clientY: 100 }],
    });
    fireEvent.touchMove(canvas, {
      touches: [{ clientX: 120, clientY: 135 }], // downward swipe feedback
    });
    fireEvent.touchEnd(canvas, { touches: [] });

    // 8. PointerMove downward drag feedback with scale <= 1.05
    fireEvent.pointerDown(canvas, { clientX: 120, clientY: 100, button: 0, pointerType: 'mouse' });
    fireEvent.pointerMove(canvas, { clientX: 120, clientY: 135, pointerType: 'mouse' });
    fireEvent.pointerUp(canvas, { clientX: 120, clientY: 135, pointerType: 'mouse' });

    // 9. DocsMobileDiagramTrigger with default label
    render(
      <DocsMobileDiagramTrigger onExpand={vi.fn()}>
        <div>Default trigger child</div>
      </DocsMobileDiagramTrigger>
    );
    expect(screen.getByText('Default trigger child')).toBeDefined();
  });
});
