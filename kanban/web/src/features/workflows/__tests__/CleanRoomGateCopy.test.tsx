// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { AttachHookDialog } from '../AttachHookDialog';
import { DEFAULT_PROJECT_STATES } from '../api';

describe('AttachHookDialog clean-room gate copy (KAN-539)', () => {
  it('shows no-gate info note on terminal transition and explainer for agent hook', () => {
    const last = DEFAULT_PROJECT_STATES.at(-1)?.name ?? 'Done';
    render(
      <MemoryRouter>
        <AttachHookDialog
          isOpen
          projectKey="KAN"
          states={DEFAULT_PROJECT_STATES}
          initialTransition={{ from_state: null, to_state: last }}
          onSave={() => undefined}
          onClose={() => undefined}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('no-gate-info-note')).toBeTruthy();
    fireEvent.click(screen.getByDisplayValue('agent_interceptor'));
    expect(screen.getByTestId('clean-room-gate-explainer')).toBeTruthy();
    expect(screen.queryByTestId('no-gate-info-note')).toBeNull();
  });
});
