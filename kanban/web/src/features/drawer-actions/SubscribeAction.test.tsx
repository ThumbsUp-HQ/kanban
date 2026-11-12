import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SubscribeAction } from './SubscribeAction';
import * as actionsApi from './actionsApi';
import type { IssueDetail } from '../drawer/slots';

const mockIssue: IssueDetail = {
  key: 'KAN-142',
  object_id: '018f0000-0000-7000-8000-000000000001',
  project_key: 'KAN',
  project_name: 'Kanban Platform',
  summary: 'Harden OAuth and MCP token security',
};

function renderComponent(issue = mockIssue, client?: QueryClient) {
  const queryClient =
    client ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

  return render(
    <QueryClientProvider client={queryClient}>
      <SubscribeAction issue={issue} />
    </QueryClientProvider>,
  );
}

describe('SubscribeAction (KB-P3-43, S7.2 8l)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders Subscribe button when unsubscribed and toggles to Subscribed via PUT', async () => {
    vi.spyOn(actionsApi, 'fetchSubscription').mockResolvedValue({
      subscribed: false,
      muted_event_types: [],
      source: null,
    });
    const subscribeSpy = vi.spyOn(actionsApi, 'subscribeIssue').mockResolvedValue({
      subscribed: true,
      muted_event_types: [],
      source: 'manual',
    });

    renderComponent();

    const btn = await screen.findByTestId('subscribe-toggle-btn');
    expect(btn.textContent).toContain('Subscribe');
    expect(btn.getAttribute('aria-pressed')).toBe('false');

    // Mute trigger absent when unsubscribed
    expect(screen.queryByTestId('subscribe-mute-trigger')).toBeNull();

    fireEvent.click(btn);

    await waitFor(() => {
      expect(subscribeSpy).toHaveBeenCalledWith('KAN-142');
    });
  });

  it('toggles from Subscribed to unsubscribed via DELETE', async () => {
    vi.spyOn(actionsApi, 'fetchSubscription').mockResolvedValue({
      subscribed: true,
      muted_event_types: [],
      source: 'manual',
    });
    const unsubscribeSpy = vi.spyOn(actionsApi, 'unsubscribeIssue').mockResolvedValue(undefined);

    renderComponent();

    const btn = await screen.findByTestId('subscribe-toggle-btn');
    expect(btn.textContent).toContain('Subscribed');
    expect(btn.getAttribute('aria-pressed')).toBe('true');

    // Mute trigger present when subscribed
    const muteTrigger = screen.getByTestId('subscribe-mute-trigger');
    expect(muteTrigger).toBeDefined();

    fireEvent.click(btn);

    await waitFor(() => {
      expect(unsubscribeSpy).toHaveBeenCalledWith('KAN-142');
    });
  });

  it('opens mute popover and toggles muted event types via PATCH', async () => {
    vi.spyOn(actionsApi, 'fetchSubscription').mockResolvedValue({
      subscribed: true,
      muted_event_types: ['COMMENT_CREATED'],
      source: 'manual',
    });
    const patchSpy = vi.spyOn(actionsApi, 'patchSubscription').mockResolvedValue({
      subscribed: true,
      muted_event_types: ['COMMENT_CREATED', 'ISSUE_STATE_CHANGED'],
      source: 'manual',
    });

    renderComponent();

    const muteTrigger = await screen.findByTestId('subscribe-mute-trigger');
    fireEvent.click(muteTrigger);

    const popover = screen.getByTestId('mute-popover');
    expect(popover).toBeDefined();

    // Checkbox COMMENT_CREATED is checked
    const commentCb = screen.getByTestId<HTMLInputElement>('mute-checkbox-COMMENT_CREATED');
    expect(commentCb.checked).toBe(true);

    // Checkbox ISSUE_STATE_CHANGED is unchecked
    const stateCb = screen.getByTestId<HTMLInputElement>('mute-checkbox-ISSUE_STATE_CHANGED');
    expect(stateCb.checked).toBe(false);

    // Toggle ISSUE_STATE_CHANGED
    fireEvent.click(stateCb);

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('KAN-142', [
        'COMMENT_CREATED',
        'ISSUE_STATE_CHANGED',
      ]);
    });

    // Unmute COMMENT_CREATED
    fireEvent.click(commentCb);
    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith('KAN-142', []);
    });
  });

  it('rolls back optimistic state on mutation errors', async () => {
    vi.spyOn(actionsApi, 'fetchSubscription').mockResolvedValue({
      subscribed: false,
      muted_event_types: [],
      source: null,
    });
    vi.spyOn(actionsApi, 'subscribeIssue').mockRejectedValue(new Error('Network error'));
    vi.spyOn(actionsApi, 'patchSubscription').mockRejectedValue(new Error('Patch error'));

    renderComponent();

    const btn = await screen.findByTestId('subscribe-toggle-btn');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(btn.getAttribute('aria-pressed')).toBe('false');
    });
  });

  it('closes mute popover on Escape key or outside click', async () => {
    vi.spyOn(actionsApi, 'fetchSubscription').mockResolvedValue({
      subscribed: true,
      muted_event_types: [],
      source: 'manual',
    });

    renderComponent();

    const muteTrigger = await screen.findByTestId('subscribe-mute-trigger');
    fireEvent.click(muteTrigger);
    expect(screen.getByTestId('mute-popover')).toBeDefined();

    // Escape closes popover
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(screen.getByTestId('mute-popover')).toBeDefined();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('mute-popover')).toBeNull();

    // Click inside container does not close
    fireEvent.click(muteTrigger);
    expect(screen.getByTestId('mute-popover')).toBeDefined();
    fireEvent.mouseDown(screen.getByTestId('mute-popover'));
    expect(screen.getByTestId('mute-popover')).toBeDefined();

    // Click outside closes popover
    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId('mute-popover')).toBeNull();
  });

  it('rolls back muted event types when patch fails', async () => {
    vi.spyOn(actionsApi, 'fetchSubscription').mockResolvedValue({
      subscribed: true,
      muted_event_types: ['COMMENT_CREATED'],
      source: 'manual',
    });
    vi.spyOn(actionsApi, 'patchSubscription').mockRejectedValue(new Error('Network failure'));

    renderComponent();

    const muteTrigger = await screen.findByTestId('subscribe-mute-trigger');
    fireEvent.click(muteTrigger);

    const stateCb = screen.getByTestId<HTMLInputElement>('mute-checkbox-ISSUE_STATE_CHANGED');
    expect(stateCb.checked).toBe(false);

    fireEvent.click(stateCb);

    await waitFor(() => {
      // Should roll back to unchecked
      expect(stateCb.checked).toBe(false);
    });
  });

  it('rolls back when unsubscribe mutation fails', async () => {
    vi.spyOn(actionsApi, 'fetchSubscription').mockResolvedValue({
      subscribed: true,
      muted_event_types: ['COMMENT_CREATED'],
      source: 'manual',
    });
    vi.spyOn(actionsApi, 'unsubscribeIssue').mockRejectedValue(new Error('Unsubscribe error'));

    renderComponent();

    const btn = await screen.findByTestId('subscribe-toggle-btn');
    expect(btn.getAttribute('aria-pressed')).toBe('true');

    fireEvent.click(btn);

    await waitFor(() => {
      expect(btn.getAttribute('aria-pressed')).toBe('true');
    });
  });

  it('handles empty query cache during mutation error', async () => {
    vi.spyOn(actionsApi, 'fetchSubscription').mockReturnValue(new Promise<never>(() => {
      // Intentionally pending
    }));
    vi.spyOn(actionsApi, 'subscribeIssue').mockRejectedValue(new Error('Immediate fail'));

    renderComponent();

    const btn = screen.getByTestId('subscribe-toggle-btn');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(btn.getAttribute('aria-pressed')).toBe('false');
    });
  });
});
