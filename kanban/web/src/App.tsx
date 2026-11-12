import type { JSX } from 'react';
import { TokenStory } from './dev/TokenStory';
import './App.css';

/**
 * Checks whether the development TokenStory page is enabled.
 */
export function isStoryEnabled(devMode: boolean, storyEnv?: string): boolean {
  if (devMode) {
    return true;
  }
  return storyEnv === '1';
}

export function App(): JSX.Element {
  const isEnabled = isStoryEnabled(
    import.meta.env.DEV,
    import.meta.env.VITE_ENABLE_STORY,
  );
  const isStoryRoute = window.location.pathname === '/__dev/tokens';

  if (isEnabled && isStoryRoute) {
    return <TokenStory />;
  }

  return (
    <main data-testid="app-root">
      <h1>Kanban</h1>
    </main>
  );
}
