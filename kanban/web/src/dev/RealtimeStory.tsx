/**
 * Realtime status story (KB-P3-33). Mounted at /__dev/realtime (dev/story builds only, same
 * rule as the other /__dev routes). Buttons force each connection state for e2e verification.
 */

import { useState, type JSX } from 'react';
import { RealtimeStatus, type RealtimeState } from '../api/RealtimeStatus';

const FORCED_STATES: readonly RealtimeState[] = ['open', 'reconnecting', 'sse-fallback', 'closed'];

export function RealtimeStory(): JSX.Element {
  const [state, setState] = useState<RealtimeState>('open');

  return (
    <main data-testid="realtime-story">
      <h1>Realtime status chip</h1>
      <p>Force a connection state. The board control below must stay interactive.</p>
      <div role="group" aria-label="Force realtime state">
        {FORCED_STATES.map((forced) => (
          <button
            key={forced}
            type="button"
            data-testid={`force-${forced}`}
            onClick={() => {
              setState(forced);
            }}
          >
            {forced}
          </button>
        ))}
      </div>
      <button type="button" data-testid="board-focus-target">
        Board control (behind chip)
      </button>
      <RealtimeStatus state={state} />
    </main>
  );
}
