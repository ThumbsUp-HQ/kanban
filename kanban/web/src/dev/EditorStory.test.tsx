/**
 * Unit Tests for EditorStory Component (KB-P3-45).
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EditorStory, INITIAL_STORY_MARKDOWN } from './EditorStory';

describe('EditorStory Component (/__dev/editor)', () => {
  it('renders story with title, initial markdown, and byte-identical status', () => {
    render(<EditorStory />);

    expect(screen.getByTestId('editor-story')).toBeDefined();
    expect(screen.getByTestId('byte-equality-status').textContent).toBe('BYTE_IDENTICAL');
    expect(screen.getByTestId('serialized-output').textContent).toBe(INITIAL_STORY_MARKDOWN);
  });

  it('fixes typo on button click and updates status, then resets', () => {
    render(<EditorStory />);

    const fixBtn = screen.getByTestId('btn-fix-typo');
    fireEvent.click(fixBtn);

    expect(screen.getByTestId('byte-equality-status').textContent).toBe('MODIFIED');
    expect(screen.getByTestId('serialized-output').textContent).toContain('Fix the typo');

    const resetBtn = screen.getByTestId('btn-reset');
    fireEvent.click(resetBtn);

    expect(screen.getByTestId('byte-equality-status').textContent).toBe('BYTE_IDENTICAL');
    expect(screen.getByTestId('serialized-output').textContent).toBe(INITIAL_STORY_MARKDOWN);
  });
});
