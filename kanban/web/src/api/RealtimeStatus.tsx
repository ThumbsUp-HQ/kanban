/**
 * Non-blocking realtime status chip and shared aria-live announcer (KB-P3-33).
 * Never steals focus, never overlays board input. Hidden while the connection is `open`.
 */

import { useEffect, useState } from 'react';
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

interface Tick {
  forState: RealtimeState;
  seconds: number;
}

function chipText(state: RealtimeState, seconds: number): string | null {
  switch (state) {
    case 'reconnecting':
      return seconds > 0 ? `Reconnecting... ${String(seconds)}s` : 'Reconnecting...';
    case 'sse-fallback':
      return 'Live updates via fallback channel';
    case 'closed':
      return 'Offline - changes will sync when reconnected';
    case 'connecting':
    case 'open':
      return null;
  }
}

export function RealtimeStatus({ state = 'open' }: RealtimeStatusProps) {
  const [announcement, setAnnouncement] = useState('');
  const [tick, setTick] = useState<Tick>({ forState: state, seconds: 0 });

  useEffect(() => {
    const listener: AnnounceListener = (message) => {
      setAnnouncement(message);
    };
    announceListeners.add(listener);
    return () => {
      announceListeners.delete(listener);
    };
  }, []);

  useEffect(() => {
    if (state !== 'reconnecting') {
      return undefined;
    }
    const timer = setInterval(() => {
      setTick((prev) => ({
        forState: state,
        seconds: prev.forState === state ? prev.seconds + 1 : 1,
      }));
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, [state]);

  const text = chipText(state, tick.forState === state ? tick.seconds : 0);

  return (
    <>
      <div className="realtime-live-region" role="status" aria-live="polite">
        {announcement}
      </div>
      {text !== null && (
        <div className="realtime-status-chip" role="status" aria-live="polite" data-state={state}>
          {text}
        </div>
      )}
    </>
  );
}
