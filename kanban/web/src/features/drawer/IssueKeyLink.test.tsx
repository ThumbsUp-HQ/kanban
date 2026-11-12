import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import {
  IssueKeyLink,
  setOpenerElement,
  getOpenerElement,
} from './IssueKeyLink';

describe('IssueKeyLink', () => {
  it('records opener element and navigates on click', () => {
    const handleClick = vi.fn();

    render(
      <MemoryRouter initialEntries={['/projects/KAN/issues']}>
        <IssueKeyLink issueKey="KAN-142" onClick={handleClick}>
          Open KAN-142
        </IssueKeyLink>
      </MemoryRouter>,
    );

    const link = screen.getByRole('link', { name: 'Open KAN-142' });
    fireEvent.click(link);

    expect(handleClick).toHaveBeenCalledTimes(1);
    expect(getOpenerElement()).toBe(link);
  });

  it('getOpenerElement returns null if element is detached from document', () => {
    const detached = document.createElement('button');
    setOpenerElement(detached);
    expect(getOpenerElement()).toBeNull();
  });
});
