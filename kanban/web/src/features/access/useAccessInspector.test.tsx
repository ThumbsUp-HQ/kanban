import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  AccessInspectorHost,
  useAccessInspector,
  UUID_REGEX,
  parseAccessTarget,
} from './useAccessInspector';
import { ShellPanelsProvider, useShellPanels } from '../../app/shellPanels';
import * as AccessIndex from './index';
import kan142Data from '../../../e2e/fixtures/access-inspector-kan-142.json';

const VALID_UUID = 'c0000000-0000-0000-0000-000000000142';
const INVALID_UUID = '../../admin';

function TestTriggerComponent({ uuid }: { uuid: string }) {
  const { open } = useAccessInspector();
  return (
    <button type="button" onClick={() => { open(uuid); }}>
      Open Trigger
    </button>
  );
}

function TestShellPanelOpener({ uuid }: { uuid: string }) {
  const { openPanel } = useShellPanels();
  return (
    <button type="button" onClick={() => { openPanel('access', uuid); }}>
      Shell Open Trigger
    </button>
  );
}

describe('useAccessInspector & AccessInspectorHost', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('exports all expected members from index.ts', () => {
    expect(AccessIndex.AccessInspectorPopover).toBeDefined();
    expect(AccessIndex.AgentKillSwitchControl).toBeDefined();
    expect(AccessIndex.AccessInspectorHost).toBeDefined();
    expect(AccessIndex.useAccessInspector).toBeDefined();
    expect(AccessIndex.UUID_REGEX).toBeDefined();
  });

  it('validates UUIDs and ignores path-traversal or malformed identifiers', () => {
    expect(UUID_REGEX.test(VALID_UUID)).toBe(true);
    expect(UUID_REGEX.test(INVALID_UUID)).toBe(false);
    expect(UUID_REGEX.test('not-a-uuid')).toBe(false);

    expect(parseAccessTarget(VALID_UUID)).toEqual({ objectId: VALID_UUID });
    expect(parseAccessTarget(INVALID_UUID)).toBeNull();
    expect(parseAccessTarget(null)).toBeNull();
    expect(parseAccessTarget(123)).toBeNull();
    expect(parseAccessTarget({ objectId: VALID_UUID })).toEqual({
      objectId: VALID_UUID,
      anchorEl: null,
    });
    const dummyEl = document.createElement('div');
    expect(parseAccessTarget({ objectId: VALID_UUID, anchorEl: dummyEl })).toEqual({
      objectId: VALID_UUID,
      anchorEl: dummyEl,
    });
    expect(parseAccessTarget({ objectId: INVALID_UUID })).toBeNull();
  });

  it('opens inspector via window.dispatchEvent and ignores invalid objectId', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(['access', VALID_UUID], kan142Data);

    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    render(
      <QueryClientProvider client={queryClient}>
        <AccessInspectorHost />
        <TestTriggerComponent uuid={INVALID_UUID} />
      </QueryClientProvider>,
    );

    // Click trigger with invalid id
    fireEvent.click(screen.getByRole('button', { name: /open trigger/i }));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();

    // Now dispatch valid UUID event without shellPanels (standalone mode)
    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-access-inspector', {
          detail: { objectId: VALID_UUID },
        }),
      );
    });

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByText('EFFECTIVE ACCESS FOR ISSUE')).toBeDefined();

    // Close standalone
    fireEvent.click(screen.getByRole('button', { name: /close access inspector/i }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens inspector via openPanel("access", uuid) within ShellPanelsProvider', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(['access', VALID_UUID], kan142Data);

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <AccessInspectorHost />
          <TestShellPanelOpener uuid={VALID_UUID} />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: /shell open trigger/i }));

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByText('KAN-142')).toBeDefined();

    // Close dialog
    fireEvent.click(screen.getByRole('button', { name: /close access inspector/i }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('handles custom event when ShellPanelsProvider is active', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(['access', VALID_UUID], kan142Data);

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <AccessInspectorHost />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-access-inspector', {
          detail: { objectId: VALID_UUID },
        }),
      );
    });

    expect(screen.getByRole('dialog')).toBeDefined();
  });

  it('triggers open() hook with valid UUID and ignores invalid custom events', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(['access', VALID_UUID], kan142Data);

    render(
      <QueryClientProvider client={queryClient}>
        <AccessInspectorHost />
        <TestTriggerComponent uuid={VALID_UUID} />
      </QueryClientProvider>,
    );

    // Call open() hook with valid UUID
    fireEvent.click(screen.getByRole('button', { name: /open trigger/i }));
    expect(screen.getByRole('dialog')).toBeDefined();

    // Dispatch invalid custom event (line 76 branch)
    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:open-access-inspector', {
          detail: { objectId: '../../bad-id' },
        }),
      );
    });
  });

  it('ignores shell panel open with invalid target', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ShellPanelsProvider>
          <AccessInspectorHost />
          <TestShellPanelOpener uuid={INVALID_UUID} />
        </ShellPanelsProvider>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: /shell open trigger/i }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
