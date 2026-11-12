import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, act } from '@testing-library/react';
import { EmojiHint } from './EmojiHint';
import { createHintController, type HintClock } from './hintTiming';

class TestClock implements HintClock {
  currentTime = 1000;
  private timerSeq = 1;
  private timers = new Map<number, { cb: () => void; triggerTime: number }>();

  now(): number {
    return this.currentTime;
  }

  setTimer(cb: () => void, ms: number): number {
    const id = this.timerSeq++;
    this.timers.set(id, { cb, triggerTime: this.currentTime + ms });
    return id;
  }

  clearTimer(id: unknown): void {
    this.timers.delete(id as number);
  }

  advance(ms: number): void {
    const target = this.currentTime + ms;
    while (this.timers.size > 0) {
      let earliestId: number | null = null;
      let earliestTime = Infinity;
      for (const [id, item] of this.timers.entries()) {
        if (item.triggerTime <= target && item.triggerTime < earliestTime) {
          earliestId = id;
          earliestTime = item.triggerTime;
        }
      }
      if (earliestId === null) {
        break;
      }
      const item = this.timers.get(earliestId);
      if (!item) {
        break;
      }
      this.timers.delete(earliestId);
      this.currentTime = item.triggerTime;
      item.cb();
    }
    this.currentTime = target;
  }
}

describe('EmojiHint Component', () => {
  it('renders 24x24 trigger button with glyph and accessible name', () => {
    render(<EmojiHint kind="access" testId="test-hint" label="Access Inspector" />);

    const trigger = screen.getByTestId('test-hint');
    expect(trigger).toBeDefined();
    expect(trigger.getAttribute('aria-label')).toBe('Access Inspector');
    expect(trigger.textContent).toContain('🛡️');
  });

  it('uses default controller and default hint when props are omitted', () => {
    render(<EmojiHint kind="airGap" testId="airgap-hint" />);

    const trigger = screen.getByTestId('airgap-hint');
    expect(trigger.getAttribute('aria-label')).toBe('Air-gap local-only mode');

    act(() => {
      trigger.focus();
    });

    const popup = screen.getByTestId('airgap-hint-popup');
    expect(popup.textContent).toContain('Confirms external LLM/media egress is disabled');

    act(() => {
      trigger.blur();
    });
    expect(screen.queryByTestId('airgap-hint-popup')).toBeNull();
  });

  it('keyboard a11y: focus opens tooltip immediately at 0ms and aria-describedby matches id', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);

    render(
      <EmojiHint
        kind="access"
        testId="test-hint"
        controller={ctrl}
        content="Platform Core scope summary"
      />,
    );

    const trigger = screen.getByTestId('test-hint');
    expect(screen.queryByTestId('test-hint-popup')).toBeNull();

    act(() => {
      trigger.focus();
    });

    const popup = screen.getByTestId('test-hint-popup');
    expect(popup).toBeDefined();
    expect(popup.getAttribute('role')).toBe('tooltip');
    expect(trigger.getAttribute('aria-describedby')).toBe(popup.id);
    expect(popup.textContent).toContain('Platform Core scope summary');
  });

  it('repositions on window resize and scroll events', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);

    render(
      <EmojiHint
        kind="access"
        testId="pos-hint"
        controller={ctrl}
      />,
    );

    const trigger = screen.getByTestId('pos-hint');
    act(() => {
      trigger.focus();
    });

    const popup = screen.getByTestId('pos-hint-popup');
    expect(popup).toBeDefined();

    act(() => {
      window.dispatchEvent(new Event('resize'));
      window.dispatchEvent(new Event('scroll'));
    });

    expect(popup.style.top).toBeTruthy();
    expect(popup.style.left).toBeTruthy();
  });

  it('escape hides tooltip and restores focus to trigger', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);

    render(<EmojiHint kind="warning" testId="warn-hint" controller={ctrl} />);

    const trigger = screen.getByTestId('warn-hint');
    act(() => {
      trigger.focus();
    });

    expect(screen.getByTestId('warn-hint-popup')).toBeDefined();

    act(() => {
      fireEvent.keyDown(trigger, { key: 'Escape' });
    });

    expect(screen.queryByTestId('warn-hint-popup')).toBeNull();
    expect(document.activeElement).toBe(trigger);

    // Escape inside popup also closes
    act(() => {
      fireEvent.focus(trigger);
    });
    const popup = screen.getByTestId('warn-hint-popup');
    act(() => {
      fireEvent.keyDown(popup, { key: 'Escape' });
    });
    expect(screen.queryByTestId('warn-hint-popup')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('interactive variant: aria-expanded toggles, Tab enters popup, Shift+Tab returns', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);
    const onActivate = vi.fn();

    render(
      <EmojiHint
        kind="access"
        variant="interactive"
        testId="interactive-hint"
        controller={ctrl}
        activateLabel="Inspect Access"
        onActivate={onActivate}
        content={
          <div>
            <button type="button" data-testid="second-action">Second Action</button>
          </div>
        }
      />,
    );

    const trigger = screen.getByTestId('interactive-hint');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');

    act(() => {
      trigger.focus();
    });

    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    const popup = screen.getByTestId('interactive-hint-popup');
    expect(popup.getAttribute('role')).toBe('dialog');
    expect(trigger.getAttribute('aria-controls')).toBe(popup.id);

    // Tab key from trigger moves focus into the first focusable button inside popup
    const secondBtn = screen.getByTestId('second-action');
    const actionBtn = screen.getByTestId('interactive-hint-action-btn');

    act(() => {
      fireEvent.keyDown(trigger, { key: 'Tab' });
    });
    expect(document.activeElement).toBe(secondBtn);

    // Moving focus inside popup does not close interactive dialog
    act(() => {
      fireEvent.blur(trigger, { relatedTarget: secondBtn });
    });
    expect(screen.getByTestId('interactive-hint-popup')).toBeDefined();

    // Tab forward from last button wraps back to trigger
    actionBtn.focus();
    act(() => {
      fireEvent.keyDown(popup, { key: 'Tab' });
    });
    expect(document.activeElement).toBe(trigger);

    // Shift+Tab from first button returns focus to trigger
    secondBtn.focus();
    act(() => {
      fireEvent.keyDown(popup, { key: 'Tab', shiftKey: true });
    });
    expect(document.activeElement).toBe(trigger);

    // Blur from popup to outside closes dialog
    act(() => {
      fireEvent.blur(popup, { relatedTarget: document.body });
    });
    expect(screen.queryByTestId('interactive-hint-popup')).toBeNull();
  });

  it('interactive variant with no focusable elements handles Tab without crashing', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);

    render(
      <EmojiHint
        kind="access"
        variant="interactive"
        testId="no-focus-hint"
        controller={ctrl}
        content={<div>Non-interactive text only</div>}
      />,
    );

    const trigger = screen.getByTestId('no-focus-hint');
    act(() => {
      trigger.focus();
    });

    const popup = screen.getByTestId('no-focus-hint-popup');
    act(() => {
      fireEvent.keyDown(popup, { key: 'Tab' });
    });
    // Still open, didn't throw
    expect(screen.getByTestId('no-focus-hint-popup')).toBeDefined();
  });

  it('touch: pointerType: "touch" tap opens popup without calling onActivate, tapping button activates', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);
    const onActivate = vi.fn();

    render(
      <EmojiHint
        kind="gateApproved"
        testId="touch-hint"
        controller={ctrl}
        onActivate={onActivate}
        activateLabel="Inspect Verdict"
      />,
    );

    const trigger = screen.getByTestId('touch-hint');

    // Simulate touch tap: pointerDown with pointerType: 'touch' then click
    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'touch' });
      fireEvent.click(trigger);
    });

    // Tap opens popup; onActivate was NOT called!
    expect(screen.getByTestId('touch-hint-popup')).toBeDefined();
    expect(onActivate).not.toHaveBeenCalled();

    // Tap again on open trigger to test touch closing branch
    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'touch' });
      fireEvent.click(trigger);
    });
    expect(screen.queryByTestId('touch-hint-popup')).toBeNull();

    // Re-open for the rest of the test
    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'touch' });
      fireEvent.click(trigger);
    });
    expect(screen.getByTestId('touch-hint-popup')).toBeDefined();

    // Now tap the action button inside popup
    const actionBtn = screen.getByTestId('touch-hint-action-btn');
    expect(actionBtn.textContent).toBe('Inspect Verdict');

    act(() => {
      fireEvent.click(actionBtn);
    });
    expect(onActivate).toHaveBeenCalledTimes(1);

    // Clicking trigger does not close when outside click listener runs
    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'touch' });
    });
    expect(screen.getByTestId('touch-hint-popup')).toBeDefined();

    // Clicking inside popup does not close
    const popup = screen.getByTestId('touch-hint-popup');
    act(() => {
      fireEvent.pointerDown(popup, { pointerType: 'touch' });
    });
    expect(screen.getByTestId('touch-hint-popup')).toBeDefined();

    // Tap outside closes the popup
    act(() => {
      fireEvent.pointerDown(document.body, { pointerType: 'touch' });
    });
    expect(screen.queryByTestId('touch-hint-popup')).toBeNull();
  });

  it('mouse click toggles when onActivate is not provided', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);

    render(
      <EmojiHint
        kind="warning"
        testId="toggle-hint"
        controller={ctrl}
      />,
    );

    const trigger = screen.getByTestId('toggle-hint');

    // Click opens
    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'mouse' });
      fireEvent.click(trigger);
    });
    expect(screen.getByTestId('toggle-hint-popup')).toBeDefined();

    // Click again toggles closed
    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'mouse' });
      fireEvent.click(trigger);
    });
    expect(screen.queryByTestId('toggle-hint-popup')).toBeNull();
  });

  it('mouse click calls onActivate directly when provided', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);
    const onActivate = vi.fn();

    render(
      <EmojiHint
        kind="access"
        testId="mouse-hint"
        controller={ctrl}
        onActivate={onActivate}
      />,
    );

    const trigger = screen.getByTestId('mouse-hint');

    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'mouse' });
      fireEvent.click(trigger);
    });

    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it('negative / security: content with HTML string renders literal text with 0 img elements', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);

    render(
      <EmojiHint
        kind="warning"
        testId="sec-hint"
        controller={ctrl}
        content={'<img src=x onerror=alert(1)>'}
      />,
    );

    const trigger = screen.getByTestId('sec-hint');
    act(() => {
      trigger.focus();
    });

    const popup = screen.getByTestId('sec-hint-popup');
    expect(popup.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(popup.querySelector('img')).toBeNull();
  });

  it('lazy content evaluation: function is evaluated only when opened', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);
    const contentFn = vi.fn(() => <span>Lazy loaded payload</span>);

    render(
      <EmojiHint
        kind="sparkle"
        testId="lazy-hint"
        controller={ctrl}
        content={contentFn}
      />,
    );

    expect(contentFn).not.toHaveBeenCalled();

    const trigger = screen.getByTestId('lazy-hint');
    act(() => {
      trigger.focus();
    });

    expect(contentFn).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('lazy-hint-popup').textContent).toContain('Lazy loaded payload');
  });

  it('exercises fallback branches when testId and activateLabel are omitted', () => {
    const onActivate = vi.fn();
    render(
      <EmojiHint
        kind="access"
        variant="interactive"
        onActivate={onActivate}
      />,
    );

    const trigger = screen.getByRole('button', { name: 'Access and sharing' });
    act(() => {
      fireEvent.focus(trigger);
    });

    const openBtn = screen.getByRole('button', { name: 'Open' });
    expect(openBtn).toBeDefined();

    act(() => {
      fireEvent.click(openBtn);
    });
    expect(onActivate).toHaveBeenCalledTimes(1);
  });

  it('hover timing integration: opens after 180ms delay, pointer leave cancels', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);

    render(
      <EmojiHint
        kind="priorityUrgent"
        testId="hover-hint"
        controller={ctrl}
      />,
    );

    const trigger = screen.getByTestId('hover-hint');

    act(() => {
      fireEvent.pointerEnter(trigger);
    });
    expect(screen.queryByTestId('hover-hint-popup')).toBeNull();

    act(() => {
      clock.advance(179);
    });
    expect(screen.queryByTestId('hover-hint-popup')).toBeNull();

    act(() => {
      clock.advance(1);
    });
    expect(screen.getByTestId('hover-hint-popup')).toBeDefined();

    // Hover into popup and out
    const popup = screen.getByTestId('hover-hint-popup');
    act(() => {
      fireEvent.pointerLeave(trigger);
      clock.advance(50);
      fireEvent.pointerEnter(popup);
      clock.advance(100);
    });
    expect(screen.getByTestId('hover-hint-popup')).toBeDefined();

    act(() => {
      fireEvent.pointerLeave(popup);
      clock.advance(121);
    });
    expect(screen.queryByTestId('hover-hint-popup')).toBeNull();
  });

  it('touch interaction does not close dialog on synthetic blur', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);
    const onActivate = vi.fn();

    render(
      <EmojiHint
        kind="access"
        variant="interactive"
        testId="touch-hint"
        controller={ctrl}
        activateLabel="Action"
        onActivate={onActivate}
      />,
    );

    const trigger = screen.getByTestId('touch-hint');
    // Simulate touch tap on trigger
    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'touch' });
      fireEvent.click(trigger);
    });

    expect(screen.getByTestId('touch-hint-popup')).toBeDefined();

    // In mobile touch emulation, tapping inside popup or an action button triggers blur with null relatedTarget
    act(() => {
      fireEvent.blur(trigger, { relatedTarget: null });
    });
    expect(screen.getByTestId('touch-hint-popup')).toBeDefined();

    const popup = screen.getByTestId('touch-hint-popup');
    act(() => {
      fireEvent.pointerDown(popup, { pointerType: 'touch' });
      fireEvent.blur(popup, { relatedTarget: null });
    });
    expect(screen.getByTestId('touch-hint-popup')).toBeDefined();
  });

  it('tests handlePopupBlur and handlePopupKeyDown forward tab and non-tab keys', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);

    render(
      <EmojiHint
        kind="rawMarkdown"
        variant="interactive"
        activateLabel="Action"
        onActivate={vi.fn()}
        testId="tab-trap-hint"
        controller={ctrl}
      />,
    );

    const trigger = screen.getByTestId('tab-trap-hint');
    act(() => {
      fireEvent.focus(trigger);
    });

    const popup = screen.getByTestId('tab-trap-hint-popup');
    expect(popup).toBeDefined();

    // 1. Non-Tab keydown in popup
    fireEvent.keyDown(popup, { key: 'ArrowDown' });

    // 2. Tab and Shift-Tab on open trigger
    fireEvent.keyDown(trigger, { key: 'Tab', shiftKey: true });
    fireEvent.keyDown(trigger, { key: 'Tab', shiftKey: false });

    // 3. Forward Tab on action button (last focusable element)
    const actionBtn = popup.querySelector('button');
    if (actionBtn) {
      actionBtn.focus();
      fireEvent.keyDown(popup, { key: 'Tab', shiftKey: false });
    }

    // 4. Popup blur with touch and relatedTarget variations
    fireEvent.pointerDown(popup, { pointerType: 'touch' });
    fireEvent.blur(popup);
    fireEvent.blur(popup, { relatedTarget: popup });
    fireEvent.blur(popup, { relatedTarget: trigger });

    // 5. Blur on non-interactive subtle hint popup
    const subtleCtrl = createHintController(new TestClock());
    render(
      <EmojiHint
        kind="rawMarkdown"
        variant="tooltip"
        testId="subtle-blur-hint"
        controller={subtleCtrl}
      />,
    );
    const subtleTrigger = screen.getByTestId('subtle-blur-hint');
    // Tab on closed trigger
    fireEvent.keyDown(subtleTrigger, { key: 'Tab' });
    act(() => {
      fireEvent.pointerEnter(subtleTrigger);
    });

    // 6. Multi-focusable popup tab navigation middle elements
    const multiClock = new TestClock();
    const multiCtrl = createHintController(multiClock);
    render(
      <EmojiHint
        kind="rawMarkdown"
        variant="interactive"
        activateLabel="Action 1"
        onActivate={vi.fn()}
        testId="multi-btn-hint"
        controller={multiCtrl}
      />,
    );
    const multiTrigger = screen.getByTestId('multi-btn-hint');
    act(() => {
      fireEvent.focus(multiTrigger);
    });
    const multiPopup = screen.getByTestId('multi-btn-hint-popup');
    const extraBtn = document.createElement('button');
    extraBtn.textContent = 'Action 2';
    multiPopup.appendChild(extraBtn);

    const firstBtn = multiPopup.querySelector('button');
    if (firstBtn) {
      firstBtn.focus();
    }
    // Non-shift Tab on first button (which is not last button)
    fireEvent.keyDown(multiPopup, { key: 'Tab', shiftKey: false });

    extraBtn.focus();
    // Shift Tab on last button (which is not first button)
    fireEvent.keyDown(multiPopup, { key: 'Tab', shiftKey: true });

    // Blur with outside target
    fireEvent.blur(multiPopup, { relatedTarget: document.body });
  });
});
