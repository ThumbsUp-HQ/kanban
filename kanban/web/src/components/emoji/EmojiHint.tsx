import React, {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type JSX,
  type ReactNode,
} from 'react';
import {
  EMOJI_REGISTRY,
  EXTENDED_EMOJI_REGISTRY,
  type ExtendedEmojiKey,
  type EmojiEntry,
} from './emojiRegistry';
import {
  defaultHintController,
  type HintController,
} from './hintTiming';
import { HintPortal } from './HintPortal';
import { positionHint } from './positionHint';
import './EmojiHint.css';

export interface EmojiHintProps {
  kind: ExtendedEmojiKey;
  content?: ReactNode | (() => ReactNode);
  label?: string;
  variant?: 'tooltip' | 'interactive';
  onActivate?: () => void;
  onAction?: () => void;
  activateLabel?: string;
  actionLabel?: string;
  testId?: string;
  controller?: HintController;
}

/**
 * Accessible 24x24 semantic status emoji pill with hover/focus elaboration popover (KB-P3-31, S6.2).
 */
export function EmojiHint({
  kind,
  content,
  label,
  variant = 'tooltip',
  onActivate,
  onAction,
  activateLabel,
  actionLabel,
  testId,
  controller,
}: EmojiHintProps): JSX.Element {
  const entry: EmojiEntry | undefined =
    (EMOJI_REGISTRY as Record<string, EmojiEntry>)[kind] ??
    EXTENDED_EMOJI_REGISTRY[kind];
  const safeEntry: EmojiEntry = entry ?? {
    glyph: '❓',
    domain: 'Unknown',
    ariaLabel: 'Status indicator',
    defaultHint: 'Unknown status',
  };
  const ctrl = controller ?? defaultHintController;
  const isInteractive = variant === 'interactive';

  const rawId = useId();
  const sanitizedId = rawId.replace(/[^a-zA-Z0-9_-]/g, '');
  const popupId = `kb-hint-popup-${sanitizedId}`;
  const triggerId = `kb-hint-trigger-${sanitizedId}`;

  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const popupRef = useRef<HTMLDivElement | null>(null);
  const isPointerDownRef = useRef(false);
  const isTouchRef = useRef(false);

  const [hintState, setHintState] = useState(() => ctrl.getState());

  useEffect(() => {
    return ctrl.subscribe(setHintState);
  }, [ctrl]);

  const isOpen = hintState.openId === popupId;

  // Restore focus if dismissed via Escape
  useEffect(() => {
    if (hintState.restoreFocusId === popupId && triggerRef.current) {
      triggerRef.current.focus();
    }
  }, [hintState.restoreFocusId, popupId]);

  // Position popup via CSSOM without inline style string in JSX
  useLayoutEffect(() => {
    if (!isOpen) {
      return;
    }

    const updatePosition = (): void => {
      const triggerEl = triggerRef.current;
      const popupEl = popupRef.current;
      /* v8 ignore next */
      if (!triggerEl || !popupEl) {
        return;
      }

      const triggerRect = triggerEl.getBoundingClientRect();
      const popupRect = popupEl.getBoundingClientRect();
      const viewport = {
        width: window.innerWidth,
        height: window.innerHeight,
      };

      const pos = positionHint(
        triggerRect,
        { width: popupRect.width, height: popupRect.height },
        viewport,
      );

      popupEl.style.top = `${String(pos.top)}px`;
      popupEl.style.left = `${String(pos.left)}px`;
      popupEl.dataset.placement = pos.placement;
    };

    updatePosition();

    window.addEventListener('resize', updatePosition, { passive: true });
    window.addEventListener('scroll', updatePosition, { capture: true, passive: true });

    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, { capture: true });
    };
  }, [isOpen]);

  // Close when tapping / clicking outside
  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handlePointerDownOutside = (e: PointerEvent): void => {
      const target = e.target as Node | null;
      if (
        !target ||
        triggerRef.current?.contains(target) ||
        popupRef.current?.contains(target)
      ) {
        return;
      }
      ctrl.close(popupId);
    };

    window.addEventListener('pointerdown', handlePointerDownOutside);
    return () => {
      window.removeEventListener('pointerdown', handlePointerDownOutside);
    };
  }, [isOpen, ctrl, popupId]);

  const handlePointerDown = (e: React.PointerEvent<HTMLButtonElement>): void => {
    isPointerDownRef.current = true;
    isTouchRef.current = e.pointerType === 'touch';
  };

  const handlePointerEnter = (): void => {
    if (!isTouchRef.current) {
      ctrl.pointerEnterTrigger(popupId);
    }
  };

  const handlePointerLeave = (): void => {
    if (!isTouchRef.current) {
      ctrl.pointerLeaveTrigger(popupId);
    }
  };

  const handleFocus = (): void => {
    if (!isPointerDownRef.current) {
      ctrl.focus(popupId);
    }
  };

  const handleBlur = (e: React.FocusEvent): void => {
    isPointerDownRef.current = false;
    if (isTouchRef.current) {
      return;
    }
    const nextTarget = e.relatedTarget as Node | null;
    if (nextTarget && popupRef.current?.contains(nextTarget)) {
      return;
    }
    ctrl.blur(popupId);
  };

  const effectiveAction = onAction ?? onActivate;
  const effectiveActionLabel = actionLabel ?? activateLabel ?? 'Open';

  const handleClick = (): void => {
    isPointerDownRef.current = false;
    if (isTouchRef.current) {
      if (!isOpen) {
        ctrl.focus(popupId);
      } else {
        ctrl.close(popupId);
      }
    } else {
      if (effectiveAction) {
        effectiveAction();
      } else {
        ctrl.tap(popupId);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>): void => {
    if (e.key === 'Escape') {
      e.preventDefault();
      ctrl.escape();
      return;
    }

    if (e.key === 'Tab' && isInteractive && isOpen && !e.shiftKey) {
      const popupEl = popupRef.current;
      if (popupEl) {
        const focusable = popupEl.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        const first = focusable[0];
        if (first) {
          e.preventDefault();
          first.focus();
        }
      }
    }
  };

  const handlePopupPointerDown = (e: React.PointerEvent<HTMLDivElement>): void => {
    if (e.pointerType === 'touch') {
      isTouchRef.current = true;
    }
  };

  const handlePopupPointerEnter = (): void => {
    ctrl.pointerEnterPopup(popupId);
  };

  const handlePopupPointerLeave = (): void => {
    ctrl.pointerLeavePopup(popupId);
  };

  const handlePopupBlur = (e: React.FocusEvent): void => {
    if (isInteractive) {
      if (isTouchRef.current) {
        return;
      }
      const nextTarget = e.relatedTarget as Node | null;
      if (
        nextTarget &&
        (popupRef.current?.contains(nextTarget) || triggerRef.current?.contains(nextTarget))
      ) {
        return;
      }
      ctrl.blur(popupId);
    }
  };

  const handlePopupKeyDown = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Escape') {
      e.preventDefault();
      ctrl.escape();
      return;
    }

    if (isInteractive && e.key === 'Tab') {
      const popupEl = popupRef.current ?? e.currentTarget;
      const focusable = Array.from(
        popupEl.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) {
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        triggerRef.current?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        triggerRef.current?.focus();
      }
    }
  };

  const handleActionClick = (e: React.MouseEvent<HTMLButtonElement>): void => {
    e.stopPropagation();
    if (onAction) {
      onAction();
      ctrl.close(popupId);
    } else if (onActivate) {
      onActivate();
    }
  };

  const effectiveLabel = label ?? safeEntry.ariaLabel;
  let resolvedContent: ReactNode = safeEntry.defaultHint;
  if (content !== undefined) {
    resolvedContent = typeof content === 'function' ? (isOpen ? content() : null) : content;
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        id={triggerId}
        className="emoji-hint"
        data-testid={testId}
        aria-label={effectiveLabel}
        aria-describedby={!isInteractive && isOpen ? popupId : undefined}
        aria-expanded={isInteractive ? isOpen : undefined}
        aria-controls={isInteractive && isOpen ? popupId : undefined}
        onPointerDown={handlePointerDown}
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
      >
        <span aria-hidden="true" className="emoji-hint-glyph">
          {safeEntry.glyph}
        </span>
      </button>

      {isOpen && (
        <HintPortal>
          <div
            ref={popupRef}
            id={popupId}
            className={`emoji-hint-popup${isInteractive ? ' emoji-hint-popup--interactive' : ''}`}
            role={isInteractive ? 'dialog' : 'tooltip'}
            aria-label={isInteractive ? effectiveLabel : undefined}
            data-testid={testId ? `${testId}-popup` : 'emoji-hint-popup'}
            onPointerDown={handlePopupPointerDown}
            onPointerEnter={handlePopupPointerEnter}
            onPointerLeave={handlePopupPointerLeave}
            onBlur={handlePopupBlur}
            onKeyDown={handlePopupKeyDown}
          >
            <div className="emoji-hint-popup-content">{resolvedContent}</div>
            {effectiveAction && (
              <button
                type="button"
                className="emoji-hint-action-btn"
                data-testid={testId ? `${testId}-action-btn` : 'emoji-hint-action-btn'}
                onMouseDown={(e) => {
                  e.preventDefault();
                }}
                onClick={handleActionClick}
              >
                {effectiveActionLabel}
              </button>
            )}
          </div>
        </HintPortal>
      )}
    </>
  );
}
