import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { App, isStoryEnabled } from './App';
import { ThemeProvider } from './theme/ThemeProvider';

describe('App component', () => {
  it('renders and getByTestId("app-root") contains heading text Kanban', () => {
    render(<App />);
    const appRoot = screen.getByTestId('app-root');
    expect(appRoot).toBeDefined();
    expect(appRoot.textContent).toContain('Kanban');
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading.textContent).toBe('Kanban');
  });

  it('renders TokenStory when pathname is /__dev/tokens', () => {
    const originalPathname = window.location.pathname;
    try {
      window.history.pushState({}, '', '/__dev/tokens');
      render(
        <ThemeProvider>
          <App />
        </ThemeProvider>,
      );
      const story = screen.getByTestId('token-story');
      expect(story).toBeDefined();
    } finally {
      window.history.pushState({}, '', originalPathname);
    }
  });

  it('renders EmojiStory when pathname is /__dev/emoji', () => {
    const originalPathname = window.location.pathname;
    try {
      window.history.pushState({}, '', '/__dev/emoji');
      render(
        <ThemeProvider>
          <App />
        </ThemeProvider>,
      );
      const story = screen.getByTestId('emoji-story');
      expect(story).toBeDefined();
    } finally {
      window.history.pushState({}, '', originalPathname);
    }
  });

  it('renders EditorStory when pathname is /__dev/editor', () => {
    const originalPathname = window.location.pathname;
    try {
      window.history.pushState({}, '', '/__dev/editor');
      render(
        <ThemeProvider>
          <App />
        </ThemeProvider>,
      );
      const story = screen.getByTestId('editor-story');
      expect(story).toBeDefined();
    } finally {
      window.history.pushState({}, '', originalPathname);
    }
  });

  it('renders RealtimeStory when pathname is /__dev/realtime and forces each state', () => {
    const originalPathname = window.location.pathname;
    try {
      window.history.pushState({}, '', '/__dev/realtime');
      render(
        <ThemeProvider>
          <App />
        </ThemeProvider>,
      );
      expect(screen.getByTestId('realtime-story')).toBeDefined();
      expect(document.querySelector('.realtime-status-chip')).toBeNull();
      fireEvent.click(screen.getByTestId('force-closed'));
      expect(document.querySelector('.realtime-status-chip')?.textContent).toBe(
        'Offline - changes will sync when reconnected',
      );
      fireEvent.click(screen.getByTestId('force-sse-fallback'));
      expect(document.querySelector('.realtime-status-chip')?.textContent).toBe(
        'Live updates via fallback channel',
      );
    } finally {
      window.history.pushState({}, '', originalPathname);
    }
  });

  describe('isStoryEnabled helper logic', () => {
    it('renders standard app root when stories are disabled', () => {
      vi.stubEnv('DEV', false);
      vi.stubEnv('VITE_ENABLE_STORY', '0');
      try {
        render(<App />);
        expect(screen.getByTestId('app-root')).toBeDefined();
      } finally {
        vi.unstubAllEnvs();
      }
    });

    it('returns true when devMode is true regardless of env variable', () => {
      expect(isStoryEnabled(true, undefined)).toBe(true);
      expect(isStoryEnabled(true, '0')).toBe(true);
      expect(isStoryEnabled(true, '1')).toBe(true);
    });

    it('returns true when devMode is false but storyEnv is 1', () => {
      expect(isStoryEnabled(false, '1')).toBe(true);
    });

    it('returns false when devMode is false and storyEnv is not 1', () => {
      expect(isStoryEnabled(false, undefined)).toBe(false);
      expect(isStoryEnabled(false, '0')).toBe(false);
      expect(isStoryEnabled(false, 'true')).toBe(false);
    });
  });
});
