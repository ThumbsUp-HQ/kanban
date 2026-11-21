import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router';
import {
  LayoutSwitcher,
  normalizeLayout,
  type LayoutOption,
} from './LayoutSwitcher';

describe('LayoutSwitcher', () => {
  it('normalizes arbitrary or malicious values to list', () => {
    expect(normalizeLayout(null)).toBe('list');
    expect(normalizeLayout('')).toBe('list');
    expect(normalizeLayout('unknown')).toBe('list');
    expect(normalizeLayout('<script>alert(1)</script>')).toBe('list');
    expect(normalizeLayout('BOARD')).toBe('board');
    expect(normalizeLayout('table')).toBe('table');
  });

  it('renders radiogroup with all 5 layout options', () => {
    render(
      <MemoryRouter>
        <LayoutSwitcher value="list" />
      </MemoryRouter>,
    );

    const radiogroup = screen.getByRole('radiogroup', { name: 'Layout' });
    expect(radiogroup).toBeDefined();

    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(5);
    expect(radios.map((r) => r.textContent.trim())).toEqual([
      'Issues',
      'Board',
      'Table',
      'Calendar',
      'Timeline',
    ]);
  });

  it('highlights the selected layout option', () => {
    render(
      <MemoryRouter>
        <LayoutSwitcher value="board" />
      </MemoryRouter>,
    );

    const boardRadio = screen.getByRole('radio', { name: 'Board' });
    expect(boardRadio.getAttribute('aria-checked')).toBe('true');

    const issuesRadio = screen.getByRole('radio', { name: 'Issues' });
    expect(issuesRadio.getAttribute('aria-checked')).toBe('false');
  });

  it('handles arrow key navigation across options including ArrowDown, ArrowUp, and ignore other keys', () => {
    const onChange = vi.fn();
    render(
      <MemoryRouter>
        <LayoutSwitcher value="list" onChange={onChange} />
      </MemoryRouter>,
    );

    const issuesRadio = screen.getByRole('radio', { name: 'Issues' });
    issuesRadio.focus();

    fireEvent.keyDown(issuesRadio, { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('board');

    fireEvent.keyDown(issuesRadio, { key: 'ArrowDown' });
    expect(onChange).toHaveBeenCalledWith('board');

    fireEvent.keyDown(issuesRadio, { key: 'ArrowLeft' });
    expect(onChange).toHaveBeenCalledWith('timeline');

    fireEvent.keyDown(issuesRadio, { key: 'ArrowUp' });
    expect(onChange).toHaveBeenCalledWith('timeline');

    // Other keys do nothing
    fireEvent.keyDown(issuesRadio, { key: 'Tab' });
    expect(onChange).toHaveBeenCalledTimes(4);
  });

  it('renders gracefully outside RouterProvider', () => {
    const onChange = vi.fn();
    render(<LayoutSwitcher value="table" onChange={onChange} />);

    const radio = screen.getByRole('radio', { name: 'Board' });
    act(() => {
      radio.click();
    });
    expect(onChange).toHaveBeenCalledWith('board');
  });

  it('synchronizes with URL search parameters inside router', () => {
    function TestHost() {
      return <LayoutSwitcher />;
    }

    render(
      <MemoryRouter initialEntries={['/projects/KAN/issues?layout=calendar']}>
        <Routes>
          <Route path="/projects/:projectKey/issues" element={<TestHost />} />
        </Routes>
      </MemoryRouter>,
    );

    const calendarRadio = screen.getByRole('radio', { name: 'Calendar' });
    expect(calendarRadio.getAttribute('aria-checked')).toBe('true');

    const tableRadio = screen.getByRole('radio', { name: 'Table' });
    act(() => {
      tableRadio.click();
    });
    expect(tableRadio.getAttribute('aria-checked')).toBe('true');
  });

  it('supports mobile collapsed dropdown menu', () => {
    const onChange = vi.fn();
    render(
      <MemoryRouter>
        <LayoutSwitcher value="board" onChange={onChange} />
      </MemoryRouter>,
    );

    const menuBtn = screen.getByRole('button', { name: 'Layout: Board' });
    expect(menuBtn).toBeDefined();

    act(() => {
      menuBtn.click();
    });

    const menu = screen.getByRole('menu', { name: 'Layout menu' });
    expect(menu).toBeDefined();

    const timelineItem = screen.getByRole('menuitemradio', { name: 'Timeline' });
    act(() => {
      timelineItem.click();
    });

    expect(onChange).toHaveBeenCalledWith('timeline');
  });

  it('falls back to default activeConfig when layout value is unrecognized', () => {
    render(
      <MemoryRouter>
        <LayoutSwitcher value={'unknown_custom' as unknown as LayoutOption} className="custom-class" />
      </MemoryRouter>,
    );

    const menuBtn = screen.getByRole('button', { name: 'Layout: Issues' });
    expect(menuBtn).toBeDefined();
  });
});
