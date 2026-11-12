import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
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

  describe('isStoryEnabled helper logic', () => {
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
