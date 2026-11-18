/**
 * Non-blocking realtime status chip and shared aria-live announcer (KB-P3-33).
 * Never steals focus, never overlays board input. Hidden while the connection is `open`.
 */

import { useEffect, useState } from 'react';
import { useRealtimeLiveState } from '../realtime/context';
import './RealtimeStatus.css';

export type RealtimeState = 'connecting' | 'open' | 'reconnecting' | 'sse-fallback' | 'closed';

type AnnounceListener = (message: string) => void;
const announceListeners = new Set<AnnounceListener>();

/** Publishes a polite announcement to the shared live region. */
export function announce(message: string): void {
  for (const listener of announceListeners) {
    listener(message);
  }
}

export interface RealtimeStatusProps {
  state?: RealtimeState;
}

const CHIP_ATTRS = { role: 'status', 'aria-live': 'polite' } as const;

/** Owns the elapsed counter so it restarts from zero on every (re)mount. */
function ReconnectingChip() {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setSeconds((prev) => prev + 1);
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="realtime-status-chip" {...CHIP_ATTRS} data-state="reconnecting">
      {seconds > 0 ? `Reconnecting... ${String(seconds)}s` : 'Reconnecting...'}
    </div>
  );
}

const STATIC_TEXT: Partial<Record<RealtimeState, string>> = {
  'sse-fallback': 'Live updates via fallback channel',
  closed: 'Offline - changes will sync when reconnected',
};

export function RealtimeStatus({ state: propState }: RealtimeStatusProps = {}) {
  const liveState = useRealtimeLiveState();
  const state = propState ?? liveState;
  const [announcement, setAnnouncement] = useState('');

  useEffect(() => {
    const listener: AnnounceListener = (message) => {
      setAnnouncement(message);
    };
    announceListeners.add(listener);
    return () => {
      announceListeners.delete(listener);
    };
  }, []);

  const staticText = STATIC_TEXT[state];

  return (
    <>
      <div className="realtime-live-region" role="status" aria-live="polite">
        {announcement}
      </div>
      {state === 'reconnecting' && <ReconnectingChip />}
      {staticText !== undefined && (
        <div className="realtime-status-chip" {...CHIP_ATTRS} data-state={state}>
          {staticText}
        </div>
      )}
    </>
  );
}
