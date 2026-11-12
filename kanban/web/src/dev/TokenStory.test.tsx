import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { TokenStory, S61_TOKENS } from './TokenStory';
import { ThemeProvider } from '../theme/ThemeProvider';

function renderStory(): ReturnType<typeof render> {
  return render(
    <ThemeProvider>
      <TokenStory />
    </ThemeProvider>,
  );
}

describe('TokenStory Component (/__dev/tokens)', () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
    vi.restoreAllMocks();
  });

  it('renders the complete S6.1 token table with all 16 rows', () => {
    renderStory();

    expect(screen.getByTestId('token-table')).toBeDefined();
    expect(screen.getByTestId('token-table-header')).toBeDefined();

    for (const token of S61_TOKENS) {
      const row = screen.getByTestId(`token-row-${token.name}`);
      expect(row).toBeDefined();
      expect(row.textContent).toContain(token.name);
      expect(row.textContent).toContain(token.raw);
    }
  });

  it('renders spacing ruler elements and layout components', () => {
    renderStory();

    expect(screen.getByTestId('spacing-ruler')).toBeDefined();
    expect(screen.getByTestId('ruler-sample-card')).toBeDefined();
    expect(screen.getByTestId('ruler-card-gap-container')).toBeDefined();
    expect(screen.getByTestId('ruler-lane-container')).toBeDefined();
    expect(screen.getByTestId('ruler-lane-1')).toBeDefined();
    expect(screen.getByTestId('ruler-lane-2')).toBeDefined();
    expect(screen.getByTestId('ruler-list-row')).toBeDefined();
    expect(screen.getByTestId('ruler-prop-row')).toBeDefined();
  });

  it('renders semantic swatches, sticky swatches, and typography elements', () => {
    renderStory();

    expect(screen.getByTestId('color-swatches')).toBeDefined();
    expect(screen.getByTestId('semantic-swatches-container')).toBeDefined();
    expect(screen.getByTestId('swatch---fg-primary')).toBeDefined();
    expect(screen.getByTestId('swatch---accent-primary')).toBeDefined();
    expect(screen.getByTestId('sticky-swatches-container')).toBeDefined();

    const prose = screen.getByTestId('typography-prose');
    expect(prose).toBeDefined();
    expect(prose.textContent).toContain('Kanban');

    const monoKey = screen.getByTestId('typography-mono-key');
    expect(monoKey).toBeDefined();
    expect(monoKey.textContent).toBe('KAN-142');
  });

  it('provides accessible theme switcher radiogroup with keyboard navigation', () => {
    renderStory();

    const radiogroup = screen.getByTestId('theme-radiogroup');
    expect(radiogroup).toBeDefined();
    expect(radiogroup.getAttribute('role')).toBe('radiogroup');

    const optSystem = screen.getByTestId('theme-option-system');
    const optLight = screen.getByTestId('theme-option-light');
    const optDark = screen.getByTestId('theme-option-dark');

    // Default: system is checked
    expect(optSystem.getAttribute('aria-checked')).toBe('true');
    expect(optLight.getAttribute('aria-checked')).toBe('false');
    expect(optDark.getAttribute('aria-checked')).toBe('false');

    // Click Light
    act(() => {
      fireEvent.click(optLight);
    });
    expect(optLight.getAttribute('aria-checked')).toBe('true');
    expect(optSystem.getAttribute('aria-checked')).toBe('false');
    expect(document.documentElement.dataset.theme).toBe('light');

    // Keyboard navigation: ArrowRight moves from Light to Dark
    act(() => {
      fireEvent.keyDown(optLight, { key: 'ArrowRight' });
    });
    expect(optDark.getAttribute('aria-checked')).toBe('true');
    expect(document.documentElement.dataset.theme).toBe('dark');

    // Keyboard navigation: ArrowDown moves from Dark to System
    act(() => {
      fireEvent.keyDown(optDark, { key: 'ArrowDown' });
    });
    expect(optSystem.getAttribute('aria-checked')).toBe('true');
    expect(document.documentElement.dataset.theme).toBeUndefined();

    // Keyboard navigation: ArrowLeft moves from System back to Dark
    act(() => {
      fireEvent.keyDown(optSystem, { key: 'ArrowLeft' });
    });
    expect(optDark.getAttribute('aria-checked')).toBe('true');
    expect(document.documentElement.dataset.theme).toBe('dark');

    // Keyboard navigation: ArrowUp moves from Dark to Light
    act(() => {
      fireEvent.keyDown(optDark, { key: 'ArrowUp' });
    });
    expect(optLight.getAttribute('aria-checked')).toBe('true');
    expect(document.documentElement.dataset.theme).toBe('light');

    // Keyboard navigation: ArrowLeft from Light moves to System
    act(() => {
      fireEvent.keyDown(optLight, { key: 'ArrowLeft' });
    });
    expect(optSystem.getAttribute('aria-checked')).toBe('true');

    // Keyboard navigation: ArrowRight from System moves to Light
    act(() => {
      fireEvent.keyDown(optSystem, { key: 'ArrowRight' });
    });
    expect(optLight.getAttribute('aria-checked')).toBe('true');

    // Irrelevant key does nothing
    act(() => {
      fireEvent.keyDown(optLight, { key: 'Enter' });
    });
    expect(optLight.getAttribute('aria-checked')).toBe('true');
  });

  it('reads computed styles when returned by getComputedStyle', () => {
    vi.spyOn(window, 'getComputedStyle').mockImplementation(() => ({
      getPropertyValue: (prop: string) => {
        if (prop === '--card-pad') {
          return '16px 18px';
        }
        return '';
      },
    } as unknown as CSSStyleDeclaration));

    renderStory();
    const row = screen.getByTestId('token-row---card-pad');
    expect(row.textContent).toContain('16px 18px');
  });
});
