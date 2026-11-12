import { describe, expect, it } from 'vitest';
import {
  BRIDGE_GRACE_MS,
  FOCUS_OPEN_DELAY_MS,
  HOVER_OPEN_DELAY_MS,
  NEIGHBOR_WARMUP_WINDOW_MS,
  createHintController,
  defaultHintController,
  type HintClock,
} from './hintTiming';

class FakeClock implements HintClock {
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

describe('hintTiming engine', () => {
  it('exports correct constants matching S6.2 spec and operates default controller', () => {
    expect(HOVER_OPEN_DELAY_MS).toBe(180);
    expect(NEIGHBOR_WARMUP_WINDOW_MS).toBe(400);
    expect(FOCUS_OPEN_DELAY_MS).toBe(0);
    expect(BRIDGE_GRACE_MS).toBe(120);
    expect(defaultHintController).toBeDefined();

    // Exercise defaultHintController with window timer clock
    const ctrl = createHintController();
    ctrl.pointerEnterTrigger('test-default-clock');
    ctrl.close();
    expect(ctrl.getState().openId).toBeNull();
  });

  it('pointer enter: not open at 179ms, open at 180ms', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    ctrl.pointerEnterTrigger('hint-1');
    expect(ctrl.getState().openId).toBeNull();

    clock.advance(179);
    expect(ctrl.getState().openId).toBeNull();

    clock.advance(1);
    expect(ctrl.getState().openId).toBe('hint-1');

    // Re-entering trigger of already open hint is a no-op
    ctrl.pointerEnterTrigger('hint-1');
    expect(ctrl.getState().openId).toBe('hint-1');
  });

  it('leave at 100ms cancels pending open', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    ctrl.pointerEnterTrigger('hint-1');
    clock.advance(100);
    ctrl.pointerLeaveTrigger('hint-1');

    clock.advance(100);
    expect(ctrl.getState().openId).toBeNull();
  });

  it('entering another trigger while pending open cancels the first', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    ctrl.pointerEnterTrigger('hint-1');
    ctrl.pointerEnterTrigger('hint-2');

    clock.advance(130);
    expect(ctrl.getState().openId).toBeNull();

    clock.advance(50);
    expect(ctrl.getState().openId).toBe('hint-2');
  });

  it('second hint entered 399ms after first closed opens at 0ms, entered at 401ms waits 180ms', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    // Open first hint and close it
    ctrl.focus('hint-1');
    expect(ctrl.getState().openId).toBe('hint-1');
    ctrl.close('hint-1');
    expect(ctrl.getState().openId).toBeNull();

    // 399ms later: entered hint-2 within neighbor warmup window (< 400ms)
    clock.advance(399);
    ctrl.pointerEnterTrigger('hint-2');
    expect(ctrl.getState().openId).toBe('hint-2'); // 0ms warmup open!

    // Close hint-2
    ctrl.close('hint-2');
    expect(ctrl.getState().openId).toBeNull();

    // 401ms later: entered hint-3 outside neighbor warmup window (>= 400ms)
    clock.advance(401);
    ctrl.pointerEnterTrigger('hint-3');
    expect(ctrl.getState().openId).toBeNull(); // not open at 0ms!

    clock.advance(179);
    expect(ctrl.getState().openId).toBeNull();

    clock.advance(1);
    expect(ctrl.getState().openId).toBe('hint-3');
  });

  it('focus opens immediately at 0ms and blur closes', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    // Focus while pending open cancels pending open
    ctrl.pointerEnterTrigger('hint-pending');
    ctrl.focus('hint-focus');
    expect(ctrl.getState().openId).toBe('hint-focus');

    // Focus while pending close timer is active on another hint
    ctrl.pointerLeaveTrigger('hint-focus');
    ctrl.focus('hint-new-focus');
    expect(ctrl.getState().openId).toBe('hint-new-focus');

    // Refocusing same id clears pending close timer if any
    ctrl.pointerLeaveTrigger('hint-new-focus');
    ctrl.focus('hint-new-focus');
    expect(ctrl.getState().openId).toBe('hint-new-focus');

    // Focus while another is open
    ctrl.focus('hint-other');
    expect(ctrl.getState().openId).toBe('hint-other');

    ctrl.blur('hint-other');
    expect(ctrl.getState().openId).toBeNull();
  });

  it('blur cancels pending open timer', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    ctrl.pointerEnterTrigger('hint-blur-pending');
    clock.advance(50);
    ctrl.blur('hint-blur-pending');
    clock.advance(150);
    expect(ctrl.getState().openId).toBeNull();
  });

  it('leave trigger then enter popup at 119ms stays open, at 121ms closed', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    // Case A: enters popup at 119ms within 120ms bridge grace window
    ctrl.focus('hint-bridge');
    expect(ctrl.getState().openId).toBe('hint-bridge');

    ctrl.pointerLeaveTrigger('hint-bridge');
    // Multiple leaves restart bridge timer cleanly
    ctrl.pointerLeaveTrigger('hint-bridge');
    clock.advance(119);
    ctrl.pointerEnterPopup('hint-bridge');

    clock.advance(200);
    expect(ctrl.getState().openId).toBe('hint-bridge'); // stays open!

    // Case B: leaves popup, reaches 121ms grace period without re-entry
    ctrl.pointerLeavePopup('hint-bridge');
    ctrl.pointerLeavePopup('hint-bridge');
    clock.advance(121);
    expect(ctrl.getState().openId).toBeNull();

    // Late enter popup after it already closed does nothing
    ctrl.pointerEnterPopup('hint-bridge');
    expect(ctrl.getState().openId).toBeNull();
  });

  it('re-entering trigger within bridge grace cancels close timer', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    ctrl.focus('hint-reenter');
    ctrl.pointerLeaveTrigger('hint-reenter');

    clock.advance(80);
    ctrl.pointerEnterTrigger('hint-reenter'); // re-enter trigger!

    clock.advance(150);
    expect(ctrl.getState().openId).toBe('hint-reenter');
  });

  it('entering different trigger within bridge grace cancels old and closes immediately', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    ctrl.focus('hint-old');
    ctrl.pointerLeaveTrigger('hint-old');
    clock.advance(50);

    ctrl.pointerEnterTrigger('hint-new');
    expect(ctrl.getState().openId).toBe('hint-new'); // opens under warmup!
  });

  it('pointer enter while another hint is open closes the old hint', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    ctrl.focus('hint-first');
    expect(ctrl.getState().openId).toBe('hint-first');

    // Pointer enter another hint
    ctrl.pointerEnterTrigger('hint-second');
    // Old is closed, new opens under warmup
    expect(ctrl.getState().openId).toBe('hint-second');
  });

  it('escape closes immediately and clears pending close timer if active', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    // Escape when nothing is open does not crash
    ctrl.escape();
    expect(ctrl.getState().openId).toBeNull();

    ctrl.focus('hint-esc');
    expect(ctrl.getState().openId).toBe('hint-esc');

    // Start bridge close timer then escape
    ctrl.pointerLeaveTrigger('hint-esc');
    ctrl.escape();
    expect(ctrl.getState().openId).toBeNull();
    expect(ctrl.getState().restoreFocusId).toBe('hint-esc');
  });

  it('tap toggles the active hint open and closed', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    ctrl.tap('hint-tap');
    expect(ctrl.getState().openId).toBe('hint-tap');

    ctrl.tap('hint-tap');
    expect(ctrl.getState().openId).toBeNull();

    ctrl.tap('hint-tap');
    expect(ctrl.getState().openId).toBe('hint-tap');

    // Tap different hint switches
    ctrl.tap('hint-other');
    expect(ctrl.getState().openId).toBe('hint-other');
  });

  it('close cancels pending open or closes currently open hint', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);

    // Close with no open hint does nothing
    ctrl.close();
    expect(ctrl.getState().openId).toBeNull();

    // Close pending open
    ctrl.pointerEnterTrigger('hint-pending-close');
    ctrl.close();
    clock.advance(200);
    expect(ctrl.getState().openId).toBeNull();

    // Close with specific id
    ctrl.focus('hint-active');
    ctrl.close('hint-active');
    expect(ctrl.getState().openId).toBeNull();

    // Close with wrong id does not close
    ctrl.focus('hint-keep');
    ctrl.close('hint-wrong');
    expect(ctrl.getState().openId).toBe('hint-keep');
  });

  it('subscribers receive state transitions and can unsubscribe', () => {
    const clock = new FakeClock();
    const ctrl = createHintController(clock);
    const states: (string | null)[] = [];

    const unsubscribe = ctrl.subscribe((st) => {
      states.push(st.openId);
    });

    ctrl.focus('hint-sub-1');
    ctrl.close();
    unsubscribe();
    ctrl.focus('hint-sub-2');

    expect(states).toEqual(['hint-sub-1', null]);
  });
});
