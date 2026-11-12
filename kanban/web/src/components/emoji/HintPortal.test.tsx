import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  HINT_ROOT_ID,
  HintPortal,
  getOrCreateHintRoot,
} from './HintPortal';

describe('HintPortal', () => {
  it('creates and reuses #kb-hint-root container', () => {
    const existing = document.getElementById(HINT_ROOT_ID);
    if (existing) {
      existing.remove();
    }

    const created = getOrCreateHintRoot();
    expect(created).not.toBeNull();
    expect(created?.id).toBe(HINT_ROOT_ID);
    expect(document.body.contains(created)).toBe(true);

    // Calling again returns the exact same instance
    const reused = getOrCreateHintRoot();
    expect(reused).toBe(created);
  });

  it('returns null when document is undefined or null', () => {
    expect(getOrCreateHintRoot(null)).toBeNull();
  });

  it('renders children into #kb-hint-root via portal', () => {
    render(
      <HintPortal>
        <div data-testid="portal-child">Portal Content</div>
      </HintPortal>,
    );

    const child = screen.getByTestId('portal-child');
    expect(child).toBeDefined();
    expect(child.parentElement?.id).toBe(HINT_ROOT_ID);
  });

  it('returns null when container is null', () => {
    const { container } = render(
      <HintPortal containerOverride={null}>
        <div data-testid="portal-null">Null Content</div>
      </HintPortal>,
    );
    expect(container.firstChild).toBeNull();
  });
});
