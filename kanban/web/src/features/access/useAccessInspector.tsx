/**
 * Effective Access Inspector hook and shell integration host (KB-P3-49, S3.4).
 * Coordinates ShellPanelsProvider registration, CustomEvent activation, and UUID validation.
 */

import React, {
  useCallback,
  useEffect,
  useState,
} from 'react';
import { registerShellPanel, useOptionalShellPanels } from '../../app/shellPanels';
import { AccessInspectorPopover } from './AccessInspectorPopover';

export const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export interface AccessInspectorTarget {
  objectId: string;
  anchorEl?: HTMLElement | null;
}

export function parseAccessTarget(arg: unknown): AccessInspectorTarget | null {
  if (typeof arg === 'string' && UUID_REGEX.test(arg)) {
    return { objectId: arg };
  }
  if (typeof arg === 'object' && arg !== null) {
    const candidate = arg as { objectId?: unknown; anchorEl?: unknown };
    if (typeof candidate.objectId === 'string' && UUID_REGEX.test(candidate.objectId)) {
      return {
        objectId: candidate.objectId,
        anchorEl: candidate.anchorEl instanceof HTMLElement ? candidate.anchorEl : null,
      };
    }
  }
  return null;
}

/**
 * Access Inspector Host component mounted in AppShell.
 * Handles both ShellPanelsProvider registration and global CustomEvent dispatch.
 */
export function AccessInspectorHost(): React.JSX.Element | null {
  const shellPanels = useOptionalShellPanels();

  const [localTarget, setLocalTarget] = useState<AccessInspectorTarget | null>(null);

  // Register shell panel handler
  useEffect(() => {
    const unregister = registerShellPanel('access', ({ arg, onClose }) => {
      const target = parseAccessTarget(arg);
      if (!target) {
        return null;
      }
      return (
        <AccessInspectorPopover
          objectId={target.objectId}
          anchorEl={target.anchorEl}
          onClose={onClose}
        />
      );
    });
    return unregister;
  }, []);

  const handleCustomEvent = useCallback(
    (e: Event): void => {
      const ce = e as CustomEvent<{ objectId?: unknown; anchorEl?: unknown }>;
      const target = parseAccessTarget(ce.detail);
      if (!target) {
        return;
      }
      if (shellPanels) {
        shellPanels.openPanel('access', target);
      } else {
        setLocalTarget(target);
      }
    },
    [shellPanels],
  );

  useEffect(() => {
    window.addEventListener('kb:open-access-inspector', handleCustomEvent);
    return () => {
      window.removeEventListener('kb:open-access-inspector', handleCustomEvent);
    };
  }, [handleCustomEvent]);

  // When rendered outside ShellPanelsProvider, render local target directly
  if (!shellPanels && localTarget) {
    return (
      <AccessInspectorPopover
        objectId={localTarget.objectId}
        anchorEl={localTarget.anchorEl}
        onClose={() => { setLocalTarget(null); }}
      />
    );
  }

  return null;
}

export function useAccessInspector(): {
  open: (objectId: string, anchorEl?: HTMLElement | null) => void;
} {
  const open = useCallback((objectId: string, anchorEl?: HTMLElement | null): void => {
    if (!UUID_REGEX.test(objectId)) {
      return;
    }
    window.dispatchEvent(
      new CustomEvent('kb:open-access-inspector', {
        detail: { objectId, anchorEl },
      }),
    );
  }, []);

  return { open };
}
