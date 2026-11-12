import { useState, type JSX } from 'react';
import { RouterProvider } from 'react-router';
import { QueryClientProvider } from '@tanstack/react-query';
import { TokenStory } from './dev/TokenStory';
import { EmojiStory } from './dev/EmojiStory';
import { EditorStory } from './dev/EditorStory';
import { MediaStory } from './dev/MediaStory';
import { RealtimeStory } from './dev/RealtimeStory';
import { createAppRouter } from './app/routes';
import { createQueryClient } from './api/queryClient';
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

function RoutedApp(): JSX.Element {
  const [queryClient] = useState(() => createQueryClient());
  const [router] = useState(() => createAppRouter());

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
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
    if (window.location.pathname.startsWith('/__dev/drawer')) {
      return <RoutedApp />;
    }
  }

  if (window.location.pathname.startsWith('/projects/')) {
    return <RoutedApp />;
  }

  return (
    <main data-testid="app-root">
      <h1>Kanban</h1>
    </main>
  );
}
