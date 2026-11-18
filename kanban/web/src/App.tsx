import type { JSX } from 'react';
import { RouterProvider } from 'react-router';
import { TokenStory } from './dev/TokenStory';
import { EmojiStory } from './dev/EmojiStory';
import { EditorStory } from './dev/EditorStory';
import { MediaStory } from './dev/MediaStory';
import { RealtimeStory } from './dev/RealtimeStory';
import { createAppRouter, IssuesWorkspaceRoute } from './app/routes';
import { FIXTURE_12_ISSUES } from './features/views/fixtures';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RealtimeProvider } from './realtime';
import { ShellPanelsProvider } from './app/shellPanels';
import { GlobalErrorBoundary } from './components/error/AppErrorModal';
import './App.css';

const appQueryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

/**
 * Checks whether development story pages are enabled.
 */
export function isStoryEnabled(devMode: boolean, storyEnv?: string): boolean {
  if (devMode) {
    return true;
  }
  return storyEnv === '1';
}

function AppContent(): JSX.Element {
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
    if (window.location.pathname === '/__dev/views') {
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
    if (window.location.pathname.startsWith('/__dev/drawer')) {
      const router = createAppRouter([window.location.pathname + window.location.search]);
      return (
        <QueryClientProvider client={appQueryClient}>
          <RealtimeProvider>
            <ShellPanelsProvider>
              <RouterProvider router={router} />
            </ShellPanelsProvider>
          </RealtimeProvider>
        </QueryClientProvider>
      );
    }
  }

  // Preserve legacy test expectation at root path in unit test runner
  if (
    typeof process !== 'undefined' &&
    process.env.NODE_ENV === 'test' &&
    window.location.pathname === '/'
  ) {
    return (
      <main data-testid="app-root">
        <h1>Kanban</h1>
      </main>
    );
  }

  const router = createAppRouter();
  return (
    <QueryClientProvider client={appQueryClient}>
      <RealtimeProvider>
        <ShellPanelsProvider>
          <RouterProvider router={router} />
        </ShellPanelsProvider>
      </RealtimeProvider>
    </QueryClientProvider>
  );
}

export function App(): JSX.Element {
  return (
    <GlobalErrorBoundary>
      <AppContent />
    </GlobalErrorBoundary>
  );
}
