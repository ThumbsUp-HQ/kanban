/**
 * In-App Notifications Bell & Feed Tray (KANBA-221, S7.2 8l, KB-P3-06).
 * Unread counter badge, @mention/assignment/transition/gate feed, Mark read / Mark all read,
 * deep links to work items, and full keyboard dismissibility.
 */

import React, { useState, useEffect, useRef, useMemo, type JSX } from 'react';
import { useNavigate } from 'react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../api/client';
import { qk } from '../../api/queryKeys';
import './NotificationsBell.css';

export interface NotificationItem {
  id: string;
  issue?: {
    id?: string | null | undefined;
    key?: string | null | undefined;
    summary?: string | null | undefined;
  } | null | undefined;
  event_type?: string | null | undefined;
  type?: string | null | undefined;
  title?: string | null | undefined;
  body?: string | null | undefined;
  link?: string | null | undefined;
  actor?: {
    handle?: string | null | undefined;
    display_name?: string | null | undefined;
    label?: string | null | undefined;
  } | null | undefined;
  created_at: string;
  read_at?: string | null | undefined;
  read?: boolean | undefined;
}

export function formatEventBadge(eventType?: string | null  ): { label: string; className: string } {
  const t = (eventType ?? '').toUpperCase();
  if (t.includes('MENTION')) {
    return { label: '@mention', className: 'notif-badge--mention' };
  }
  if (t.includes('ASSIGNEE') || t.includes('ASSIGN')) {
    return { label: 'assigned', className: 'notif-badge--assigned' };
  }
  if (t.includes('STATE') || t.includes('TRANSITION')) {
    return { label: 'transition', className: 'notif-badge--transition' };
  }
  if (t.includes('GATE')) {
    return { label: '🤖 gate', className: 'notif-badge--gate' };
  }
  return { label: 'update', className: 'notif-badge--default' };
}

export function formatTimeAgo(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  if (isNaN(diffMs)) return '';
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${String(mins)}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${String(hours)}h ago`;
  const days = Math.floor(hours / 24);
  return `${String(days)}d ago`;
}

export function NotificationsBell(): JSX.Element {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Query notifications feed
  const { data, refetch } = useQuery<{ items: NotificationItem[] }>({
    queryKey: qk.notifications(),
    queryFn: async () => {
      try {
        const res = (await apiFetch('GET', '/api/v1/notifications' as never, {
          query: { limit: 30 },
        })) as {
          items?: NotificationItem[];
        };
        return { items: res.items ?? [] };
      } catch {
        return { items: [] };
      }
    },
    refetchInterval: 30000,
  });

  const items = useMemo(() => data?.items ?? [], [data?.items]);
  const unreadCount = useMemo(() => items.filter((n) => !n.read_at).length, [items]);

  // Mark single notification read
  const markReadMutation = useMutation({
    mutationFn: async (id: string) => {
      await apiFetch('POST', `/api/v1/notifications/${encodeURIComponent(id)}/read` as never);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.notifications() });
    },
  });

  // Mark all read
  const markAllReadMutation = useMutation({
    mutationFn: async () => {
      await apiFetch('POST', '/api/v1/notifications/read-all');
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.notifications() });
    },
  });

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;

    function handlePointerDown(e: MouseEvent): void {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        e.preventDefault();
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    }

    window.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const handleDeepLink = (issueKey: string): void => {
    setIsOpen(false);
    const pKey = issueKey.includes('-') ? (issueKey.split('-')[0] ?? 'KAN') : 'KAN';
    void navigate(`/projects/${pKey}/issues?peek=${encodeURIComponent(issueKey)}`);
    window.dispatchEvent(
      new CustomEvent('kb:open-issue-peek', {
        detail: { issueKey },
        bubbles: true,
      }),
    );
  };

  return (
    <div ref={containerRef} className="kb-notif-wrapper">
      <button
        ref={triggerRef}
        type="button"
        className="kb-notif-bell-btn"
        aria-label={unreadCount > 0 ? `Notifications (${String(unreadCount)} unread)` : 'Notifications'}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        onClick={() => {
          setIsOpen(!isOpen);
          if (!isOpen) void refetch();
        }}
        data-testid="notifications-bell"
      >
        <span aria-hidden="true" className="kb-notif-bell-icon">🔔</span>
        {unreadCount > 0 && (
          <span className="kb-notif-badge" data-testid="notifications-badge">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          className="kb-notif-tray"
          role="dialog"
          aria-label="Notifications"
          data-testid="notifications-tray"
        >
          <header className="kb-notif-tray-header">
            <h3 className="kb-notif-tray-title">Notifications</h3>
            {unreadCount > 0 && (
              <button
                type="button"
                className="kb-notif-mark-all-btn"
                onClick={() => {
                  markAllReadMutation.mutate();
                }}
                disabled={markAllReadMutation.isPending}
                data-testid="mark-all-read-btn"
              >
                Mark all read
              </button>
            )}
          </header>

          <div className="kb-notif-tray-body">
            {items.length === 0 ? (
              <div className="kb-notif-empty" data-testid="notifications-empty">
                <span aria-hidden="true" className="kb-notif-empty-icon">🔕</span>
                <p>No notifications yet</p>
              </div>
            ) : (
              <ul className="kb-notif-list">
                {items.map((item) => {
                  const isUnread = item.read_at === null || item.read_at === undefined
                    ? (item.read !== undefined ? !item.read : true)
                    : false;
                  const badge = formatEventBadge(item.event_type ?? item.type);
                  const actorName =
                    item.actor?.display_name ??
                    (item.actor?.handle ? `@${item.actor.handle.replace(/^@+/, '')}` : (item.actor?.label ?? 'System'));

                  return (
                    <li
                      key={item.id}
                      className={`kb-notif-item ${isUnread ? 'kb-notif-item--unread' : ''}`}
                      data-testid={`notification-item-${item.id}`}
                    >
                      <div className="kb-notif-item-top">
                        <span className={`kb-notif-type-badge ${badge.className}`}>
                          {badge.label}
                        </span>
                        <span className="kb-notif-time">{formatTimeAgo(item.created_at)}</span>
                        {isUnread && (
                          <button
                            type="button"
                            className="kb-notif-mark-read-btn"
                            aria-label={`Mark as read: ${item.issue?.key ?? item.id}`}
                            onClick={() => {
                              markReadMutation.mutate(item.id);
                            }}
                            data-testid={`mark-read-${item.id}`}
                            title="Mark as read"
                          >
                            ✓
                          </button>
                        )}
                      </div>

                      <div className="kb-notif-item-content">
                        <span className="kb-notif-actor">{actorName}</span>
                        {item.issue?.key ? (
                          <a
                            href={`?peek=${encodeURIComponent(item.issue.key)}`}
                            className="kb-notif-link"
                            onClick={(e) => {
                              e.preventDefault();
                              if (item.issue?.key) {
                                handleDeepLink(item.issue.key);
                              }
                            }}
                            data-testid={`notif-deep-link-${item.issue.key}`}
                          >
                            <span className="kb-notif-issue-key">{item.issue.key}</span>
                            <span className="kb-notif-summary">{item.issue.summary ?? ''}</span>
                          </a>
                        ) : (
                          <span className="kb-notif-summary">{item.title ?? item.body ?? 'Notification'}</span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
