// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { FieldHelpHint } from './FieldHelpHint';
import { createHintController, type HintClock } from '../emoji/hintTiming';
import { registerShellPanel, ShellPanelsProvider } from '../../app/shellPanels';

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

describe('FieldHelpHint Component', () => {
  it('renders compact (?) trigger button with accessible aria-label', () => {
    render(
      <FieldHelpHint
        title="Display Name"
        summary="The human-readable label."
        testId="test-name-hint"
      />,
    );

    const trigger = screen.getByTestId('test-name-hint');
    expect(trigger).toBeDefined();
    expect(trigger.getAttribute('aria-label')).toBe('Help for Display Name');
    expect(trigger.textContent).toBe('?');
  });

  it('uses custom ariaLabel when provided', () => {
    render(
      <FieldHelpHint
        title="Custom Title"
        summary="Custom summary"
        ariaLabel="Learn more about Custom Title"
        testId="custom-aria-hint"
      />,
    );

    const trigger = screen.getByTestId('custom-aria-hint');
    expect(trigger.getAttribute('aria-label')).toBe('Learn more about Custom Title');
  });

  it('keyboard focus opens popover immediately at 0ms and blur closes it', () => {
    render(
      <FieldHelpHint
        title="Field Flavor"
        summary="Execution paradigm governing compute."
        testId="flavor-hint"
      />,
    );

    const trigger = screen.getByTestId('flavor-hint');
    expect(screen.queryByTestId('flavor-hint-popover')).toBeNull();

    act(() => {
      trigger.focus();
    });

    const popover = screen.getByTestId('flavor-hint-popover');
    expect(popover).toBeDefined();
    expect(popover.textContent).toContain('Field Flavor');
    expect(popover.textContent).toContain('Execution paradigm governing compute.');

    act(() => {
      trigger.blur();
    });

    expect(screen.queryByTestId('flavor-hint-popover')).toBeNull();
  });

  it('hover opens popover after 180ms delay', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);

    render(
      <FieldHelpHint
        title="Identifier Slug"
        summary="Unique lowercase identifier."
        controller={ctrl}
        testId="slug-hint"
      />,
    );

    const trigger = screen.getByTestId('slug-hint');

    act(() => {
      fireEvent.pointerEnter(trigger);
    });

    // Before 180ms: still closed
    act(() => {
      clock.advance(100);
    });
    expect(screen.queryByTestId('slug-hint-popover')).toBeNull();

    // At 180ms: opened
    act(() => {
      clock.advance(80);
    });
    expect(screen.getByTestId('slug-hint-popover')).toBeDefined();
  });

  it('supports 120ms hover bridge between trigger and popover', () => {
    const clock = new TestClock();
    const ctrl = createHintController(clock);

    render(
      <FieldHelpHint
        title="Bridge Test"
        summary="Testing hover bridge grace period."
        controller={ctrl}
        testId="bridge-hint"
      />,
    );

    const trigger = screen.getByTestId('bridge-hint');

    act(() => {
      fireEvent.pointerEnter(trigger);
      clock.advance(180);
    });
    const popover = screen.getByTestId('bridge-hint-popover');
    expect(popover).toBeDefined();

    // Leave trigger: grace period begins
    act(() => {
      fireEvent.pointerLeave(trigger);
    });

    // Advance 50ms into 120ms grace window: still open
    act(() => {
      clock.advance(50);
    });
    expect(screen.queryByTestId('bridge-hint-popover')).not.toBeNull();

    // Enter popover: cancels closing
    act(() => {
      fireEvent.pointerEnter(popover);
      clock.advance(100);
    });
    expect(screen.queryByTestId('bridge-hint-popover')).not.toBeNull();

    // Leave popover: grace period starts again
    act(() => {
      fireEvent.pointerLeave(popover);
      clock.advance(125);
    });
    expect(screen.queryByTestId('bridge-hint-popover')).toBeNull();
  });

  it('Escape key on trigger closes popover and restores focus', () => {
    render(
      <FieldHelpHint
        title="Escape Test"
        summary="Dismiss test."
        testId="escape-hint"
      />,
    );

    const trigger = screen.getByTestId('escape-hint');

    act(() => {
      trigger.focus();
    });
    expect(screen.getByTestId('escape-hint-popover')).toBeDefined();

    act(() => {
      fireEvent.keyDown(trigger, { key: 'Escape' });
    });
    expect(screen.queryByTestId('escape-hint-popover')).toBeNull();
  });

  it('Escape key inside popover closes popover and restores focus to trigger', () => {
    render(
      <FieldHelpHint
        title="Escape Popover Test"
        summary="Dismiss inside popover."
        testId="escape-popover-hint"
      />,
    );

    const trigger = screen.getByTestId('escape-popover-hint');

    act(() => {
      trigger.focus();
    });
    const popover = screen.getByTestId('escape-popover-hint-popover');

    act(() => {
      fireEvent.keyDown(popover, { key: 'Escape' });
    });
    expect(screen.queryByTestId('escape-popover-hint-popover')).toBeNull();
  });

  it('renders validValues array as definition list <dl>', () => {
    const values = [
      { label: 'scalar', description: 'Static value' },
      { label: 'formula', description: 'Single issue AST' },
    ];

    render(
      <FieldHelpHint
        title="Flavors"
        summary="Available flavors"
        validValues={values}
        testId="values-hint"
      />,
    );

    act(() => {
      screen.getByTestId('values-hint').focus();
    });

    const popover = screen.getByTestId('values-hint-popover');
    expect(popover.querySelector('dl')).toBeDefined();
    expect(popover.textContent).toContain('scalar');
    expect(popover.textContent).toContain('Static value');
    expect(popover.textContent).toContain('formula');
    expect(popover.textContent).toContain('Single issue AST');
  });

  it('renders validValues record dictionary as definition list <dl>', () => {
    const valuesRecord = {
      wasm: 'WebAssembly Tier A',
      nsjail: 'Linux namespaces Tier B',
    };

    render(
      <FieldHelpHint
        title="Tiers"
        summary="Execution tiers"
        validValues={valuesRecord}
        testId="dict-values-hint"
      />,
    );

    act(() => {
      screen.getByTestId('dict-values-hint').focus();
    });

    const popover = screen.getByTestId('dict-values-hint-popover');
    expect(popover.querySelector('dl')).toBeDefined();
    expect(popover.textContent).toContain('wasm');
    expect(popover.textContent).toContain('WebAssembly Tier A');
  });

  it('renders optional example and caution blocks when provided', () => {
    render(
      <FieldHelpHint
        title="Formula Source"
        summary="AST formula."
        example="issue.state === 'DONE' ? 100 : 0"
        caution="Cannot access external network."
        testId="blocks-hint"
      />,
    );

    act(() => {
      screen.getByTestId('blocks-hint').focus();
    });

    const popover = screen.getByTestId('blocks-hint-popover');
    expect(popover.textContent).toContain("issue.state === 'DONE' ? 100 : 0");
    expect(popover.textContent).toContain('Cannot access external network.');
  });

  it('renders More info -> footer link defaulting to /docs/custom-fields', () => {
    render(
      <FieldHelpHint
        title="Default Link"
        summary="Summary."
        testId="default-link-hint"
      />,
    );

    act(() => {
      screen.getByTestId('default-link-hint').focus();
    });

    const link = screen.getByTestId('default-link-hint-doc-link');
    expect(link.getAttribute('href')).toBe('/docs/custom-fields');
    expect(link.textContent).toContain('More info ->');
  });

  it('renders custom docHref when provided', () => {
    render(
      <FieldHelpHint
        title="Custom Doc Link"
        summary="Summary."
        docHref="/docs/custom-fields#egress-allowlist"
        testId="custom-link-hint"
      />,
    );

    act(() => {
      screen.getByTestId('custom-link-hint').focus();
    });

    const link = screen.getByTestId('custom-link-hint-doc-link');
    expect(link.getAttribute('href')).toBe('/docs/custom-fields#egress-allowlist');
  });

  it('handles click and tap toggle interactions', () => {
    render(
      <FieldHelpHint
        title="Toggle Test"
        summary="Click toggling."
        testId="toggle-hint"
      />,
    );

    const trigger = screen.getByTestId('toggle-hint');

    // Click to open
    act(() => {
      fireEvent.click(trigger);
    });
    expect(screen.getByTestId('toggle-hint-popover')).toBeDefined();

    // Click again to close
    act(() => {
      fireEvent.click(trigger);
    });
    expect(screen.queryByTestId('toggle-hint-popover')).toBeNull();
  });

  it('handles touch pointerdown and tap toggle', () => {
    render(
      <FieldHelpHint
        title="Touch Test"
        summary="Touch toggle."
        testId="touch-hint"
      />,
    );

    const trigger = screen.getByTestId('touch-hint');

    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'touch' });
      fireEvent.click(trigger);
    });
    expect(screen.getByTestId('touch-hint-popover')).toBeDefined();

    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'touch' });
      fireEvent.click(trigger);
    });
    expect(screen.queryByTestId('touch-hint-popover')).toBeNull();
  });

  it('closes when clicking outside the popover', () => {
    render(
      <div>
        <div data-testid="outside-el">Outside</div>
        <FieldHelpHint
          title="Outside Test"
          summary="Dismiss outside."
          testId="outside-hint"
        />
      </div>,
    );

    const trigger = screen.getByTestId('outside-hint');

    act(() => {
      fireEvent.click(trigger);
    });
    expect(screen.getByTestId('outside-hint-popover')).toBeDefined();

    act(() => {
      fireEvent.pointerDown(screen.getByTestId('outside-el'));
    });
    expect(screen.queryByTestId('outside-hint-popover')).toBeNull();
  });

  it('supports Tab forward navigation into popover focusable elements', () => {
    render(
      <FieldHelpHint
        title="Tab Test"
        summary="Tabbing."
        testId="tab-hint"
      />,
    );

    const trigger = screen.getByTestId('tab-hint');

    act(() => {
      trigger.focus();
    });
    const popover = screen.getByTestId('tab-hint-popover');
    const docLink = screen.getByTestId('tab-hint-doc-link');

    // Tab on trigger moves to link
    act(() => {
      fireEvent.keyDown(trigger, { key: 'Tab' });
    });
    expect(document.activeElement).toBe(docLink);

    // Shift+Tab on link moves back to trigger
    act(() => {
      fireEvent.keyDown(popover, { key: 'Tab', shiftKey: true });
    });
    expect(document.activeElement).toBe(trigger);
  });

  it('handles resize and scroll events while open without throwing', () => {
    render(
      <FieldHelpHint
        title="Position Test"
        summary="Reposition on scroll/resize."
        testId="pos-hint"
      />,
    );

    const trigger = screen.getByTestId('pos-hint');

    act(() => {
      trigger.focus();
    });

    act(() => {
      window.dispatchEvent(new Event('resize'));
      window.dispatchEvent(new Event('scroll'));
    });

    expect(screen.getByTestId('pos-hint-popover')).toBeDefined();
  });

  it('handles pointerDown before focus without duplicate open', () => {
    render(
      <FieldHelpHint
        title="Pointer Focus Test"
        summary="Pointer down suppresses duplicate focus open."
        testId="pointer-focus-hint"
      />,
    );

    const trigger = screen.getByTestId('pointer-focus-hint');
    act(() => {
      fireEvent.pointerDown(trigger);
      trigger.focus();
    });
    // Still opens via click
    act(() => {
      fireEvent.click(trigger);
    });
    expect(screen.getByTestId('pointer-focus-hint-popover')).toBeDefined();
  });

  it('handles blur to relatedTarget inside popup and touch blur correctly', () => {
    render(
      <FieldHelpHint
        title="Blur Target Test"
        summary="Blur to related target."
        testId="blur-target-hint"
      />,
    );

    const trigger = screen.getByTestId('blur-target-hint');
    act(() => {
      trigger.focus();
    });

    const popover = screen.getByTestId('blur-target-hint-popover');
    const docLink = screen.getByTestId('blur-target-hint-doc-link');

    // Blur from trigger into docLink inside popup (should not close)
    act(() => {
      fireEvent.blur(trigger, { relatedTarget: docLink });
    });
    expect(screen.getByTestId('blur-target-hint-popover')).toBeDefined();

    // Blur from popup to trigger (should not close)
    act(() => {
      fireEvent.blur(popover, { relatedTarget: trigger });
    });
    expect(screen.getByTestId('blur-target-hint-popover')).toBeDefined();

    // Popup touch pointer down then blur (should return early)
    act(() => {
      fireEvent.pointerDown(popover, { pointerType: 'touch' });
      fireEvent.blur(popover);
    });
    expect(screen.getByTestId('blur-target-hint-popover')).toBeDefined();

    // Trigger touch pointer down then blur (should return early)
    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'touch' });
      fireEvent.blur(trigger);
    });
    expect(screen.getByTestId('blur-target-hint-popover')).toBeDefined();
  });

  it('handles popover blur to outside element when not in touch mode', () => {
    render(
      <FieldHelpHint
        title="Outside Blur Test"
        summary="Blur to outside element."
        testId="outside-blur-hint"
      />,
    );

    const trigger = screen.getByTestId('outside-blur-hint');
    act(() => {
      trigger.focus();
    });
    const popover = screen.getByTestId('outside-blur-hint-popover');

    const outsideEl = document.createElement('div');
    document.body.appendChild(outsideEl);
    act(() => {
      fireEvent.blur(popover, { relatedTarget: outsideEl });
    });
    document.body.removeChild(outsideEl);
    expect(screen.queryByTestId('outside-blur-hint-popover')).toBeNull();
  });

  it('handles popup tab key when document.activeElement is first element with shiftKey', () => {
    render(
      <FieldHelpHint
        title="Shift Tab Cycle Test"
        summary="Shift Tab cycle in popover."
        testId="shift-tab-hint"
      />,
    );

    const trigger = screen.getByTestId('shift-tab-hint');
    act(() => {
      trigger.focus();
    });

    const popover = screen.getByTestId('shift-tab-hint-popover');
    const docLink = screen.getByTestId('shift-tab-hint-doc-link');

    // First element focused with shiftKey: focus returns to trigger
    act(() => {
      docLink.focus();
      fireEvent.keyDown(popover, { key: 'Tab', shiftKey: true });
    });
    expect(document.activeElement).toBe(trigger);

    // Tab key on a mock div without focusables
    const emptyDiv = document.createElement('div');
    act(() => {
      fireEvent.keyDown(emptyDiv, { key: 'Tab' });
    });
  });

  it('handles popup tab key when document.activeElement is last element', () => {
    render(
      <FieldHelpHint
        title="Tab Cycle Test"
        summary="Tab cycle in popover."
        testId="tab-cycle-hint"
      />,
    );

    const trigger = screen.getByTestId('tab-cycle-hint');
    act(() => {
      trigger.focus();
    });

    const popover = screen.getByTestId('tab-cycle-hint-popover');
    const docLink = screen.getByTestId('tab-cycle-hint-doc-link');

    // Focus link as last element, then press Tab without shift
    act(() => {
      docLink.focus();
      fireEvent.keyDown(popover, { key: 'Tab', shiftKey: false });
    });
    expect(document.activeElement).toBe(trigger);

    // With shiftKey when empty focusable (or not matching first/last)
    act(() => {
      fireEvent.keyDown(popover, { key: 'OtherKey' });
    });
    // Tab key on popup when focusables are removed
    const linkEl = popover.querySelector('a');
    if (linkEl) linkEl.remove();
    act(() => {
      fireEvent.keyDown(popover, { key: 'Tab' });
    });
  });

  it('renders default testids and handles non-escape keys and touch pointer enter/leave', () => {
    render(
      <FieldHelpHint
        title="No TestId"
        summary="Testing fallback test ids."
      />,
    );

    const trigger = screen.getByRole('button', { name: /Help for No TestId/ });

    // Touch pointer enter / leave returns early
    act(() => {
      fireEvent.pointerDown(trigger, { pointerType: 'touch' });
      fireEvent.pointerEnter(trigger);
      fireEvent.pointerLeave(trigger);
    });

    // Press Tab while closed (does not open or move focus)
    act(() => {
      fireEvent.keyDown(trigger, { key: 'Tab' });
      fireEvent.keyDown(trigger, { key: 'Tab', shiftKey: true });
      fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    });

    // Open via click
    act(() => {
      fireEvent.click(trigger);
    });

    const popover = screen.getByTestId('field-help-hint-popover');
    expect(popover).toBeDefined();

    const link = screen.getByTestId('field-help-doc-link');
    expect(link).toBeDefined();

    // Tab with shiftKey while open (does not move focus into popover)
    act(() => {
      fireEvent.keyDown(trigger, { key: 'Tab', shiftKey: true });
    });
  });

  it('focuses trigger button before opening panel when More info link is clicked (KAN-16)', () => {
    const MockPanel = ({ onClose }: { onClose: () => void }) => {
      return (
        <div data-testid="mock-panel">
          <button type="button" onClick={onClose} data-testid="mock-panel-close">
            Close
          </button>
        </div>
      );
    };
    registerShellPanel('help', MockPanel);

    render(
      <ShellPanelsProvider>
        <div>
          <FieldHelpHint
            title="Focus Test"
            summary="Testing trigger focus restoration."
            docHref="/docs/custom-fields"
            testId="focus-test-hint"
          />
        </div>
      </ShellPanelsProvider>,
    );

    const trigger = screen.getByTestId('focus-test-hint');
    act(() => {
      fireEvent.click(trigger);
    });

    const moreInfoLink = screen.getByTestId('focus-test-hint-doc-link');
    act(() => {
      fireEvent.click(moreInfoLink);
    });

    expect(screen.getByTestId('mock-panel')).toBeDefined();
    expect(document.activeElement).toBe(trigger);
  });
});
