// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type JSX,
} from 'react';
import { defaultHintController, type HintController } from '../emoji/hintTiming';
import { HintPortal } from '../emoji/HintPortal';
import { positionHint } from '../emoji/positionHint';
import { useOptionalShellPanels } from '../../app/shellPanels';
import './FieldHelpHint.css';

export interface FieldHelpValueItem {
  label: string;
  description: string;
}

export interface FieldHelpHintProps {
  title?: string;
  fieldKey?: string;
  summary: string;
  validValues?: (FieldHelpValueItem | string)[] | Record<string, string>;
  defaultValue?: string;
  example?: string;
  caution?: string;
  docHref?: string;
  testId?: string;
  ariaLabel?: string;
  controller?: HintController;
}

/**
 * Accessible (?) FieldHelpHint Popover component (KAN-15, KB-P3-AUDIT-09).
 * Provides 180ms hover delay, 0ms keyboard focus, 120ms hover-bridge grace period,
 * 44x44px coarse hit area, strict CSP zero inline style props, dl key-value pairs,
 * example/caution blocks, and More info -> documentation link.
 */
export function FieldHelpHint({
  title,
  summary,
  validValues,
  defaultValue,
  example,
  caution,
  docHref = '/docs/custom-fields',
  testId,
  ariaLabel,
  controller,
}: FieldHelpHintProps): JSX.Element {
  const ctrl = controller ?? defaultHintController;
  const shellPanels = useOptionalShellPanels();

  const rawId = useId();
  const sanitizedId = rawId.replace(/[^a-zA-Z0-9_-]/g, '');
  const popupId = `kb-field-help-popup-${sanitizedId}`;
  const triggerId = `kb-field-help-trigger-${sanitizedId}`;

  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const popupRef = useRef<HTMLDivElement | null>(null);
  const isPointerDownRef = useRef(false);
  const isTouchRef = useRef(false);
  const suppressNextFocusRef = useRef(false);

  const prevActivePanelRef = useRef(shellPanels?.activePanel);
  useEffect(() => {
    if (prevActivePanelRef.current?.id === 'help' && !shellPanels?.activePanel) {
      suppressNextFocusRef.current = true;
    }
    prevActivePanelRef.current = shellPanels?.activePanel;
  }, [shellPanels?.activePanel]);

  const [hintState, setHintState] = useState(() => ctrl.getState());

  useEffect(() => {
    return ctrl.subscribe(setHintState);
  }, [ctrl]);

  const isOpen = hintState.openId === popupId;

  // Restore focus if dismissed via Escape
  useEffect(() => {
    if (hintState.restoreFocusId === popupId && triggerRef.current) {
      suppressNextFocusRef.current = true;
      triggerRef.current.focus();
    }
  }, [hintState.restoreFocusId, popupId]);

  // Position popup via CSSOM without inline style JSX props (strict CSP style-src 'self')
  useLayoutEffect(() => {
    if (!isOpen) {
      return;
    }

    const updatePosition = (): void => {
      const triggerEl = triggerRef.current;
      const popupEl = popupRef.current;
      /* v8 ignore next 3 */
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

  // Close when clicking/tapping outside
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
    if (triggerRef.current?.getAttribute('data-kb-suppress-focus') === 'true') {
      triggerRef.current.removeAttribute('data-kb-suppress-focus');
      suppressNextFocusRef.current = false;
      return;
    }
    if (suppressNextFocusRef.current) {
      suppressNextFocusRef.current = false;
      return;
    }
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

  const handleClick = (): void => {
    isPointerDownRef.current = false;
    if (isTouchRef.current) {
      if (!isOpen) {
        ctrl.focus(popupId);
      } else {
        ctrl.close(popupId);
      }
    } else {
      ctrl.tap(popupId);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>): void => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      e.nativeEvent.stopImmediatePropagation();
      ctrl.escape();
      return;
    }

    // Keyboard Tab forward moves into the popover when open
    if (e.key === 'Tab' && isOpen && !e.shiftKey) {
      const popupEl = popupRef.current;
      /* v8 ignore next 3 */
      if (!popupEl) {
        return;
      }
      const focusable = popupEl.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      const first = focusable[0];
      /* v8 ignore next 4 */
      if (first) {
        e.preventDefault();
        first.focus();
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
  };

  const handlePopupKeyDown = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      e.nativeEvent.stopImmediatePropagation();
      ctrl.escape();
      return;
    }

    if (e.key === 'Tab') {
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

  // Normalize validValues into array
  const normalizedValues: FieldHelpValueItem[] = React.useMemo(() => {
    if (!validValues) return [];
    if (Array.isArray(validValues)) {
      return validValues.map((v) =>
        typeof v === 'string' ? { label: v, description: '' } : v,
      );
    }
    return Object.entries(validValues).map(([label, description]) => ({
      label,
      description,
    }));
  }, [validValues]);

  const handleDocLinkClick = (e: React.MouseEvent<HTMLAnchorElement>): void => {
    if (shellPanels && docHref) {
      e.preventDefault();
      suppressNextFocusRef.current = true;
      triggerRef.current?.setAttribute('data-kb-suppress-focus', 'true');
      triggerRef.current?.focus();
      suppressNextFocusRef.current = true;
      ctrl.close(popupId);
      shellPanels.openPanel('help', { href: docHref, title });
    }
  };

  const effectiveAriaLabel = ariaLabel ?? (title ? `Help for ${title}` : 'Help information');

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        id={triggerId}
        className="field-help-hint"
        data-testid={testId}
        aria-label={effectiveAriaLabel}
        aria-describedby={isOpen ? popupId : undefined}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        aria-controls={isOpen ? popupId : undefined}
        onPointerDown={handlePointerDown}
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
      >
        <span aria-hidden="true" className="field-help-hint-icon">
          ?
        </span>
      </button>

      {isOpen && (
        <HintPortal>
          <div
            ref={popupRef}
            id={popupId}
            className="field-help-hint-popover"
            role="dialog"
            aria-label={title}
            data-testid={testId ? `${testId}-popover` : 'field-help-hint-popover'}
            onPointerDown={handlePopupPointerDown}
            onPointerEnter={handlePopupPointerEnter}
            onPointerLeave={handlePopupPointerLeave}
            onBlur={handlePopupBlur}
            onKeyDown={handlePopupKeyDown}
          >
            <div className="field-help-hint-header">
              <strong className="field-help-hint-title">{title}</strong>
            </div>

            <div className="field-help-hint-summary">{summary}</div>

            {defaultValue && (
              <div
                className="field-help-hint-default"
                data-testid={testId ? `${testId}-default` : 'field-help-default-value'}
              >
                <span className="field-help-hint-subhead">Default:</span>
                <code className="field-help-hint-code">{defaultValue}</code>
              </div>
            )}

            {normalizedValues.length > 0 && (
              <div className="field-help-hint-values">
                <span className="field-help-hint-subhead">Valid Values:</span>
                <dl className="field-help-hint-dl">
                  {normalizedValues.map((v, i) => (
                    <React.Fragment key={v.label || String(i)}>
                      <dt className="field-help-hint-dt">{v.label}</dt>
                      <dd className="field-help-hint-dd">{v.description}</dd>
                    </React.Fragment>
                  ))}
                </dl>
              </div>
            )}

            {example && (
              <div className="field-help-hint-example">
                <span className="field-help-hint-subhead">Example:</span>
                <code className="field-help-hint-code">{example}</code>
              </div>
            )}

            {caution && (
              <div className="field-help-hint-caution">
                <span className="field-help-hint-caution-icon" aria-hidden="true">
                  ⚠️
                </span>
                <span className="field-help-hint-caution-text">{caution}</span>
              </div>
            )}

            <div className="field-help-hint-footer">
              <a
                className="field-help-hint-link"
                href={docHref}
                target="_blank"
                rel="noopener noreferrer"
                data-testid={testId ? `${testId}-doc-link` : 'field-help-doc-link'}
                onClick={handleDocLinkClick}
              >
                More info -&gt;
              </a>
            </div>
          </div>
        </HintPortal>
      )}
    </>
  );
}
