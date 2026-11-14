/**
 * SubscribeAction component (KB-P3-43, S7.2 8l).
 *
 * 1-click toggle `🔔 Subscribe` <-> `Subscribed` with per-event mute checkboxes popover.
 */

import React, { useEffect, useRef, useState, type JSX } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import type { IssueDetail } from '../drawer/slots';
import {
  EVENT_TYPE_LABELS,
  MUTABLE_EVENT_TYPES,
  fetchSubscription,
  patchSubscription,
  subscribeIssue,
  unsubscribeIssue,
  type SubscriptionResponse,
} from './actionsApi';
import './drawerActions.css';

export interface SubscribeActionProps {
  issue: IssueDetail;
}

export function SubscribeAction({ issue }: SubscribeActionProps): JSX.Element {
  const queryClient = useQueryClient();
  const [popoverOpen, setPopoverOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data: subscription } = useQuery<SubscriptionResponse>({
    queryKey: qk.subscription(issue.key),
    queryFn: () => fetchSubscription(issue.key),
    staleTime: 30000,
  });

  const isSubscribed = Boolean(subscription?.subscribed);
  const mutedTypes = (subscription && Array.isArray(subscription.muted_event_types))
    ? subscription.muted_event_types
    : [];

  // Close popover on click outside or Escape
  useEffect(() => {
    if (!popoverOpen) return;

    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        setPopoverOpen(false);
      }
    }

    function handleClickOutside(e: MouseEvent): void {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setPopoverOpen(false);
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [popoverOpen]);

  const toggleMutation = useMutation({
    mutationFn: async () => {
      if (isSubscribed) {
        await unsubscribeIssue(issue.key);
        return { subscribed: false, muted_event_types: [], source: null };
      }
      return await subscribeIssue(issue.key);
    },
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: qk.subscription(issue.key) });
      const prev = queryClient.getQueryData<SubscriptionResponse>(qk.subscription(issue.key));
      const fallbackMuted = prev?.muted_event_types ?? [];
      queryClient.setQueryData<SubscriptionResponse>(qk.subscription(issue.key), {
        subscribed: !isSubscribed,
        muted_event_types: isSubscribed ? [] : fallbackMuted,
        source: isSubscribed ? null : 'manual',
      });
      return { prev };
    },
    onError: (_err, _vars, context) => {
      if (context?.prev) {
        queryClient.setQueryData(qk.subscription(issue.key), context.prev);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: qk.subscription(issue.key) });
    },
  });

  const patchMutation = useMutation({
    mutationFn: async (updatedMuted: string[]) => {
      return await patchSubscription(issue.key, updatedMuted);
    },
    onMutate: async (updatedMuted: string[]) => {
      await queryClient.cancelQueries({ queryKey: qk.subscription(issue.key) });
      const prev = queryClient.getQueryData<SubscriptionResponse>(qk.subscription(issue.key));
      queryClient.setQueryData<SubscriptionResponse>(qk.subscription(issue.key), {
        subscribed: isSubscribed,
        muted_event_types: updatedMuted,
        source: prev?.source ?? 'manual',
      });
      return { prev };
    },
    onError: (_err, _vars, context) => {
      if (context?.prev) {
        queryClient.setQueryData(qk.subscription(issue.key), context.prev);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: qk.subscription(issue.key) });
    },
  });

  function handleToggleMute(type: string): void {
    const isMuted = mutedTypes.includes(type);
    const updated = isMuted
      ? mutedTypes.filter((t) => t !== type)
      : [...mutedTypes, type];
    patchMutation.mutate(updated);
  }

  return (
    <div className="subscribe-group" ref={containerRef}>
      <button
        type="button"
        className={`drawer-action-btn subscribe-btn ${isSubscribed ? 'drawer-action-btn--active' : ''}`}
        aria-pressed={isSubscribed}
        onClick={() => { toggleMutation.mutate(); }}
        data-testid="subscribe-toggle-btn"
      >
        <span aria-hidden="true">🔔</span>
        <span>{isSubscribed ? 'Subscribed' : 'Subscribe'}</span>
      </button>

      {isSubscribed && (
        <button
          type="button"
          className={`drawer-action-btn subscribe-mute-trigger ${popoverOpen ? 'drawer-action-btn--active' : ''}`}
          aria-label="Mute events"
          aria-haspopup="true"
          aria-expanded={popoverOpen}
          onClick={() => { setPopoverOpen((prev) => !prev); }}
          data-testid="subscribe-mute-trigger"
        >
          <span aria-hidden="true">▾</span>
        </button>
      )}

      {popoverOpen && isSubscribed && (
        <div
          className="mute-popover"
          role="dialog"
          aria-label="Mute event notifications"
          data-testid="mute-popover"
        >
          <div className="mute-popover__title">Mute Notifications</div>
          <ul className="mute-popover__list">
            {MUTABLE_EVENT_TYPES.map((type) => {
              const checked = mutedTypes.includes(type);
              const label = EVENT_TYPE_LABELS[type];
              return (
                <li key={type}>
                  <label className="mute-checkbox-label">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => { handleToggleMute(type); }}
                      data-testid={`mute-checkbox-${type}`}
                    />
                    <span>{label}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
