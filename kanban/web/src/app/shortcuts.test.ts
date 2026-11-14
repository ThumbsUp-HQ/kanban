import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  registerShortcut,
  isEditableElement,
  matchesCombo,
} from './shortcuts';

describe('shortcuts', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('identifies editable elements correctly', () => {
    expect(isEditableElement(null)).toBe(false);

    const div = document.createElement('div');
    expect(isEditableElement(div)).toBe(false);

    const input = document.createElement('input');
    expect(isEditableElement(input)).toBe(true);

    const textarea = document.createElement('textarea');
    expect(isEditableElement(textarea)).toBe(true);

    const select = document.createElement('select');
    expect(isEditableElement(select)).toBe(true);

    div.contentEditable = 'true';
    expect(isEditableElement(div)).toBe(true);

    const divAttr = document.createElement('div');
    divAttr.setAttribute('contenteditable', 'true');
    expect(isEditableElement(divAttr)).toBe(true);

    const notAnEl = {} as Element;
    expect(isEditableElement(notAnEl)).toBe(false);
  });

  it('matches keyboard combos correctly for Mod and modifiers', () => {
    const isMac = /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent);

    const eventModK = new KeyboardEvent('keydown', {
      key: 'k',
      metaKey: isMac,
      ctrlKey: !isMac,
    });
    expect(matchesCombo(eventModK, 'Mod+K')).toBe(true);
    expect(matchesCombo(eventModK, 'Cmd/Ctrl+K')).toBe(true);

    const eventPlainK = new KeyboardEvent('keydown', { key: 'k' });
    expect(matchesCombo(eventPlainK, 'Mod+K')).toBe(false);

    const eventBracket = new KeyboardEvent('keydown', { key: '[' });
    expect(matchesCombo(eventBracket, '[')).toBe(true);
    expect(matchesCombo(eventBracket, ']')).toBe(false);

    const eventCtrlA = new KeyboardEvent('keydown', { key: 'a', ctrlKey: true });
    expect(matchesCombo(eventCtrlA, 'ctrl+a')).toBe(true);
    expect(matchesCombo(eventPlainK, 'ctrl+a')).toBe(false);

    const eventMetaA = new KeyboardEvent('keydown', { key: 'a', metaKey: true });
    expect(matchesCombo(eventMetaA, 'meta+a')).toBe(true);
    expect(matchesCombo(eventPlainK, 'meta+a')).toBe(false);

    const eventShiftA = new KeyboardEvent('keydown', { key: 'a', shiftKey: true });
    expect(matchesCombo(eventShiftA, 'shift+a')).toBe(true);
    expect(matchesCombo(eventPlainK, 'shift+a')).toBe(false);

    const eventAltA = new KeyboardEvent('keydown', { key: 'a', altKey: true });
    expect(matchesCombo(eventAltA, 'alt+a')).toBe(true);
    expect(matchesCombo(eventPlainK, 'alt+a')).toBe(false);
  });

  it('registers and triggers shortcut, ignoring editable elements by default', () => {
    const handler = vi.fn();
    const unregister = registerShortcut('[', handler);

    // Trigger on body
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '[' }));
    expect(handler).toHaveBeenCalledTimes(1);

    // Trigger while inside an input
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    window.dispatchEvent(new KeyboardEvent('keydown', { key: '[' }));
    // Should NOT have fired second time
    expect(handler).toHaveBeenCalledTimes(1);

    unregister();
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '[' }));
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('allows shortcuts inside inputs when allowInInputs is true', () => {
    const handler = vi.fn();
    const isMac = /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent);
    const unregister = registerShortcut('Mod+K', handler, { allowInInputs: true });

    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    window.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'k',
        metaKey: isMac,
        ctrlKey: !isMac,
      }),
    );
    expect(handler).toHaveBeenCalledTimes(1);

    unregister();
  });

  it('handles Alt modifier and multiple registered shortcuts with teardown', () => {
    const handler1 = vi.fn();
    const handler2 = vi.fn();

    const unreg1 = registerShortcut('Alt+X', handler1);
    const unreg2 = registerShortcut('Alt+Y', handler2);

    window.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'x', altKey: true }),
    );
    expect(handler1).toHaveBeenCalledTimes(1);
    expect(handler2).not.toHaveBeenCalled();

    window.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'y', altKey: true }),
    );
    expect(handler2).toHaveBeenCalledTimes(1);

    unreg1();
    unreg2();

    // After unregistering all, listener should be torn down
    window.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'x', altKey: true }),
    );
    expect(handler1).toHaveBeenCalledTimes(1);
  });

  it('ignores events when isComposing is true', () => {
    const handler = vi.fn();
    const unregister = registerShortcut('[', handler);

    const event = new KeyboardEvent('keydown', { key: '[' });
    Object.defineProperty(event, 'isComposing', { value: true });

    window.dispatchEvent(event);
    expect(handler).not.toHaveBeenCalled();

    unregister();
  });

  it('handles Alt modifier and multiple registered shortcuts with teardown', () => {
    const handler1 = vi.fn();
    const handler2 = vi.fn();

    const unreg1 = registerShortcut('Alt+X', handler1);
    const unreg2 = registerShortcut('Alt+Y', handler2);

    window.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'x', altKey: true }),
    );
    expect(handler1).toHaveBeenCalledTimes(1);
    expect(handler2).not.toHaveBeenCalled();

    window.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'y', altKey: true }),
    );
    expect(handler2).toHaveBeenCalledTimes(1);

    unreg1();
    unreg2();

    // After unregistering all, listener should be torn down
    window.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'x', altKey: true }),
    );
    expect(handler1).toHaveBeenCalledTimes(1);
  });
});
