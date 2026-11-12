import type { JSX } from 'react';
import { TokenStory } from './dev/TokenStory';
import { EmojiStory } from './dev/EmojiStory';
import { EditorStory } from './dev/EditorStory';
import './App.css';

/**
 * Checks whether development story pages are enabled.
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

  if (isEnabled) {
    if (window.location.pathname === '/__dev/tokens') {
      return <TokenStory />;
    }
    if (window.location.pathname === '/__dev/emoji') {
      return <EmojiStory />;
    }
    if (window.location.pathname === '/__dev/editor') {
      return <EditorStory />;
    }
  }

  return (
    <main data-testid="app-root">
      <h1>Kanban</h1>
    </main>
  );
}
