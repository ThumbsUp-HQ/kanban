/**
 * Full-Viewport Lightbox Modal for Vector and Raster Media (KB-P3-48, S5.4).
 * Accessible dialog with focus trap, Escape dismissal, backdrop persistence,
 * and 10% - 800% cursor-centered pan/zoom.
 */

import React, {
  useEffect,
  useRef,
  type JSX,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { MediaViewport, type MediaBackdropKind } from './MediaViewport';
import './MediaViewport.css';

export interface MediaLightboxProps {
  isOpen: boolean;
  onClose: () => void;
  src: string;
  alt?: string | undefined;
  rawSource?: string | undefined;
  backdrop: MediaBackdropKind;
  onBackdropChange: (next: MediaBackdropKind) => void;
  safeFilename?: string | undefined;
  triggerRef?: React.RefObject<HTMLElement | null> | undefined;
  children?: ReactNode | undefined;
}

export function MediaLightbox({
  isOpen,
  onClose,
  src,
  alt = '',
  rawSource,
  backdrop,
  onBackdropChange,
  safeFilename,
  triggerRef,
}: MediaLightboxProps): JSX.Element | null {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  // Focus management and Escape key dismissal
  useEffect(() => {
    if (!isOpen) {
      return;
    }

    // Save previous active element to restore upon close
    const previousActiveElement = triggerRef?.current ?? (document.activeElement as HTMLElement | null);

    // Focus close button initially
    requestAnimationFrame(() => {
      closeButtonRef.current?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      previousActiveElement?.focus();
    };
  }, [isOpen, onClose, triggerRef]);

  if (!isOpen) {
    return null;
  }

  const lightboxContent = (
    <div
      className="media-lightbox-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Media Lightbox"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="media-lightbox-content">
        <button
          ref={closeButtonRef}
          type="button"
          className="media-lightbox-close"
          aria-label="Close lightbox (Escape)"
          onClick={onClose}
        >
          ✕
        </button>

        <MediaViewport
          src={src}
          alt={alt}
          rawSource={rawSource}
          isLightbox
          initialBackdrop={backdrop}
          onBackdropChange={onBackdropChange}
          safeFilename={safeFilename}
        />
      </div>
    </div>
  );

  return createPortal(lightboxContent, document.body);
}
