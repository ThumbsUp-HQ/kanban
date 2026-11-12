import type { JSX } from 'react';
import { TokenStory } from './dev/TokenStory';
import { EmojiStory } from './dev/EmojiStory';
import { EditorStory } from './dev/EditorStory';
import { MediaStory } from './dev/MediaStory';
import { RealtimeStory } from './dev/RealtimeStory';
import { IssuesWorkspaceRoute } from './app/routes';
import { FIXTURE_12_ISSUES } from './features/views/fixtures';
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
    if (window.location.pathname === '/__dev/media') {
      return <MediaStory />;
    }
    if (window.location.pathname === '/__dev/realtime') {
      return <RealtimeStory />;
    }
    if (
      window.location.pathname.startsWith('/projects/') ||
      window.location.pathname === '/__dev/views'
    ) {
      const isNoModules =
        window.location.pathname.includes('nomodules') ||
        window.location.search.includes('nomodules=1');
      return (
        <IssuesWorkspaceRoute
          projectKey="KAN"
          modulesEnabled={!isNoModules}
          initialIssues={FIXTURE_12_ISSUES}
        />
      );
    }
  }

  return (
    <main data-testid="app-root">
      <h1>Kanban</h1>
    </main>
  );
}
