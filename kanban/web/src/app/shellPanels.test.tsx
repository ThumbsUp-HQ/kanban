import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import React from 'react';
import {
  ShellPanelsProvider,
  useShellPanels,
  registerShellPanel,
} from './shellPanels';
import * as RealtimeStatusModule from '../api/RealtimeStatus';

describe('shellPanels', () => {
  it('throws when useShellPanels is used outside ShellPanelsProvider', () => {
    function InvalidConsumer() {
      useShellPanels();
      return null;
    }
    expect(() => render(<InvalidConsumer />)).toThrow(
      'useShellPanels must be used within a ShellPanelsProvider',
    );
  });

  it('calls announce("Panel not available yet") when opening an unregistered panel', () => {
    const announceSpy = vi
      .spyOn(RealtimeStatusModule, 'announce')
      .mockImplementation(() => {
        /* noop */
      });

    function Consumer() {
      const { openPanel } = useShellPanels();
      return (
        <button type="button" onClick={() => { openPanel('unregistered-panel'); }}>
          Open
        </button>
      );
    }

    render(
      <ShellPanelsProvider>
        <Consumer />
      </ShellPanelsProvider>,
    );

    const btn = screen.getByRole('button', { name: 'Open' });
    act(() => {
      btn.click();
    });

    expect(announceSpy).toHaveBeenCalledWith('Panel not available yet');
    announceSpy.mockRestore();
  });

  it('opens and closes registered panel successfully', () => {
    function DummyPanel({ onClose, arg }: { onClose: () => void; arg?: unknown }) {
      return (
        <div data-testid="dummy-panel">
          <span>Payload: {String(arg)}</span>
          <button type="button" onClick={onClose}>
            Close Panel
          </button>
        </div>
      );
    }

    const unregister = registerShellPanel('dummy', DummyPanel);

    function Consumer() {
      const { openPanel } = useShellPanels();
      return (
        <button type="button" onClick={() => { openPanel('dummy', 'test-payload'); }}>
          Open Dummy
        </button>
      );
    }

    render(
      <ShellPanelsProvider>
        <Consumer />
      </ShellPanelsProvider>,
    );

    const openBtn = screen.getByRole('button', { name: 'Open Dummy' });
    act(() => {
      openBtn.click();
    });

    const panel = screen.getByTestId('dummy-panel');
    expect(panel).toBeDefined();
    expect(panel.textContent).toContain('Payload: test-payload');

    const closeBtn = screen.getByRole('button', { name: 'Close Panel' });
    act(() => {
      closeBtn.click();
    });

    expect(screen.queryByTestId('dummy-panel')).toBeNull();
    unregister();
  });

  it('returns null if registered panel is removed while open', () => {
    function TempPanel(): React.JSX.Element {
      return <div data-testid="temp-panel">Temp</div>;
    }
    const unregister = registerShellPanel('temp', TempPanel);
    let openTemp: () => void = () => {
      /* noop */
    };
    function Consumer(): React.JSX.Element {
      const { openPanel } = useShellPanels();
      openTemp = () => {
        openPanel('temp');
      };
      return <div />;
    }
    const { rerender } = render(
      <ShellPanelsProvider>
        <Consumer />
      </ShellPanelsProvider>,
    );
    act(() => {
      openTemp();
    });
    expect(screen.getByTestId('temp-panel')).toBeDefined();
    act(() => {
      unregister();
    });
    rerender(
      <ShellPanelsProvider>
        <Consumer />
      </ShellPanelsProvider>,
    );
    expect(screen.queryByTestId('temp-panel')).toBeNull();
  });
});
