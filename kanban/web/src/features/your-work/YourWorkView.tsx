/**
 * Live Your Work Hub (KANBA-221, KB-AUDIT-15, S6.3).
 * Live RLS-filtered Assigned to Me, Created by Me, and Subscribed tabs across accessible projects,
 * with quick ?peek= inspection and zero static placeholder links.
 */

import React, { useState, useMemo, useContext, type JSX } from 'react';
import { useSearchParams } from 'react-router';
import { useQuery, QueryClientContext } from '@tanstack/react-query';
import { apiFetch } from '../../api/client';
import { qk } from '../../api/queryKeys';
import { StateBadge } from '../../components/state/StateBadge';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { useSessionGuard } from '../auth/useSessionGuard';
import type { IssueItem } from '../views/viewsApi';
import type { TopbarUser } from '../../app/Topbar';
import './YourWorkView.css';

export type YourWorkTab = 'assigned' | 'created' | 'subscribed';

interface ProjectInfo {
  id: string;
  identifier?: string | null | undefined;
  key: string;
  name: string;
}

interface NotificationFeedItem {
  id: string;
  issue?: { id?: string; key?: string; summary?: string } | undefined;
  link?: string | undefined;
  event_type?: string | undefined;
}

export function YourWorkViewInner(): JSX.Element {
  useSessionGuard();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<YourWorkTab>('assigned');
  const [filterQuery, setFilterQuery] = useState('');

  // 1. Current user identity
  const meQuery = useQuery<TopbarUser | null>({
    queryKey: qk.me(),
    queryFn: async () => {
      try {
        return (await apiFetch('GET', '/api/v1/auth/me')) as TopbarUser;
      } catch {
        return null;
      }
    },
    staleTime: 60000,
  });
  const currentUser = meQuery.data ?? null;

  // 2. Fetch accessible projects under RLS
  const projectsQuery = useQuery<ProjectInfo[]>({
    queryKey: qk.projects(),
    queryFn: async () => {
      try {
        const res = await apiFetch('GET', '/api/v1/projects');
        const data = res as unknown as { items?: { id: string; key?: string; identifier?: string; name: string }[] } | { id: string; key?: string; identifier?: string; name: string }[];
        const rawList = Array.isArray(data) ? data : (data.items ?? []);
        return rawList.map((p) => ({
          id: p.id,
          name: p.name,
          key: (p.key ?? p.identifier ?? ''),
        }));
      } catch {
        return [];
      }
    },
    staleTime: 30000,
  });

  const projects = projectsQuery.data ?? [];

  // 3. Fetch notifications to identify subscribed work items
  const notifQuery = useQuery<{ items: NotificationFeedItem[] }>({
    queryKey: ['notifications', 'feed'],
    queryFn: async () => {
      try {
        return (await apiFetch('GET', '/api/v1/notifications' as never, {
          query: { limit: 50 },
        })) as {
          items: NotificationFeedItem[];
        };
      } catch {
        return { items: [] };
      }
    },
    staleTime: 30000,
  });

  const subscribedKeys = useMemo(() => {
    const keys = new Set<string>();
    const notifs = notifQuery.data?.items ?? [];
    for (const n of notifs) {
      if (n.issue?.key) {
        keys.add(n.issue.key);
      } else if (n.link) {
        const match = n.link.match(/peek=([A-Z0-9_-]+)/i);
        if (match?.[1]) {
          keys.add(match[1]);
        }
      }
    }
    return keys;
  }, [notifQuery.data]);

  // 4. Load issues across accessible projects in parallel
  const issuesQuery = useQuery<IssueItem[]>({
    queryKey: ['your-work-issues', projects.map((p) => p.key).join(',')],
    queryFn: async () => {
      if (projects.length === 0) return [];
      const fetchPromises = projects.map(async (p) => {
        try {
          const res = await apiFetch(
            'GET',
            `/api/v1/projects/${encodeURIComponent(p.key)}/issues` as never,
            { query: { limit: 50 } },
          );
          const data = res as { items?: IssueItem[] } | IssueItem[];
          return Array.isArray(data) ? data : (data.items ?? []);
        } catch {
          return [];
        }
      });
      const results = await Promise.all(fetchPromises);
      return results.flat();
    },
    enabled: projects.length > 0,
    staleTime: 15000,
  });

  const allIssues = useMemo(() => issuesQuery.data ?? [], [issuesQuery.data]);

  // 5. Partition issues into tabs
  const { assignedIssues, createdIssues, subscribedIssues } = useMemo(() => {
    const userId = currentUser?.id ?? '';
    const userHandle = currentUser?.handle?.replace(/^@+/, '').toLowerCase() ?? '';
    const userEmail = currentUser?.email?.toLowerCase() ?? '';

    const assigned: IssueItem[] = [];
    const created: IssueItem[] = [];
    const subscribed: IssueItem[] = [];

    for (const issue of allIssues) {
      // Assigned to Me
      const isAssigned = (issue.assignees ?? []).some((rawA) => {
        const a = rawA as {
          id?: string | undefined;
          principal?: { id?: string | undefined; handle?: string | undefined; email?: string | undefined } | undefined;
          free_text?: string | undefined;
        };
        if (userId && (a.id === userId || a.principal?.id === userId)) return true;
        if (userHandle) {
          const rawHandle = a.principal?.handle || a.free_text;
          if (rawHandle && rawHandle.toLowerCase().replace(/^@+/, '') === userHandle) return true;
        }
        if (userEmail && a.principal?.email && a.principal.email.toLowerCase() === userEmail) return true;
        return false;
      });
      if (isAssigned) {
        assigned.push(issue);
      }

      // Created by Me
      const rawCreatedBy = (issue as { created_by?: string }).created_by;
      const isCreated =
        (userId && (issue.created_by_id === userId || rawCreatedBy === userId)) ||
        (userHandle && issue.created_by_handle?.toLowerCase().replace(/^@+/, '') === userHandle);
      if (isCreated) {
        created.push(issue);
      }

      // Subscribed
      const rawSubscribed = (issue as { subscribed?: boolean }).subscribed;
      if (rawSubscribed || subscribedKeys.has(issue.key)) {
        subscribed.push(issue);
      }
    }

    return { assignedIssues: assigned, createdIssues: created, subscribedIssues: subscribed };
  }, [allIssues, currentUser, subscribedKeys]);

  // Active list filtered by search query
  const displayedIssues = useMemo(() => {
    let source: IssueItem[] = [];
    if (activeTab === 'assigned') source = assignedIssues;
    else if (activeTab === 'created') source = createdIssues;
    else source = subscribedIssues;

    const q = filterQuery.trim().toLowerCase();
    if (!q) return source;

    return source.filter((issue) => {
      const projKey = (issue as { project_key?: string }).project_key;
      return (
        issue.key.toLowerCase().includes(q) ||
        issue.summary.toLowerCase().includes(q) ||
        (projKey?.toLowerCase().includes(q))
      );
    });
  }, [activeTab, assignedIssues, createdIssues, subscribedIssues, filterQuery]);

  const handleOpenPeek = (issueKey: string): void => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('peek', issueKey);
    setSearchParams(nextParams);
    window.dispatchEvent(
      new CustomEvent('kb:open-issue-peek', {
        detail: { issueKey },
        bubbles: true,
      }),
    );
  };

  const isLoading = projectsQuery.isLoading || issuesQuery.isLoading;

  return (
    <section data-testid="your-work-view" className="your-work-view">
      <header className="your-work-header">
        <div className="your-work-header-text">
          <h1 className="your-work-title">Your work</h1>
          <p className="your-work-subtitle">
            Live RLS-filtered work items assigned to you, created by you, and subscribed across your workspace.
          </p>
        </div>

        {/* Search filter input */}
        <div className="your-work-search-box">
          <span aria-hidden="true" className="your-work-search-icon">🔍</span>
          <input
            type="search"
            aria-label="Filter your work items"
            className="your-work-search-input"
            placeholder="Filter work items..."
            value={filterQuery}
            onChange={(e) => { setFilterQuery(e.target.value); }}
          />
        </div>
      </header>

      {/* Tabs */}
      <div className="your-work-tabs" role="tablist" aria-label="Your work categories">
        <button
          type="button"
          role="tab"
          id="tab-assigned"
          aria-selected={activeTab === 'assigned'}
          aria-controls="panel-your-work"
          className={`your-work-tab ${activeTab === 'assigned' ? 'your-work-tab--active' : ''}`}
          onClick={() => { setActiveTab('assigned'); }}
          data-testid="tab-assigned-to-me"
        >
          <span>Assigned to Me</span>
          <span className="your-work-tab-badge" data-testid="badge-assigned-count">
            {assignedIssues.length}
          </span>
        </button>

        <button
          type="button"
          role="tab"
          id="tab-created"
          aria-selected={activeTab === 'created'}
          aria-controls="panel-your-work"
          className={`your-work-tab ${activeTab === 'created' ? 'your-work-tab--active' : ''}`}
          onClick={() => { setActiveTab('created'); }}
          data-testid="tab-created-by-me"
        >
          <span>Created by Me</span>
          <span className="your-work-tab-badge" data-testid="badge-created-count">
            {createdIssues.length}
          </span>
        </button>

        <button
          type="button"
          role="tab"
          id="tab-subscribed"
          aria-selected={activeTab === 'subscribed'}
          aria-controls="panel-your-work"
          className={`your-work-tab ${activeTab === 'subscribed' ? 'your-work-tab--active' : ''}`}
          onClick={() => { setActiveTab('subscribed'); }}
          data-testid="tab-subscribed"
        >
          <span>Subscribed</span>
          <span className="your-work-tab-badge" data-testid="badge-subscribed-count">
            {subscribedIssues.length}
          </span>
        </button>
      </div>

      {/* Panel */}
      <div
        id="panel-your-work"
        role="tabpanel"
        aria-labelledby={`tab-${activeTab}`}
        className="your-work-panel"
      >
        {isLoading ? (
          <div className="your-work-loading" data-testid="your-work-loading">
            Loading your work items across accessible projects...
          </div>
        ) : displayedIssues.length === 0 ? (
          <div className="your-work-empty" data-testid="your-work-empty">
            <span aria-hidden="true" className="your-work-empty-icon">📭</span>
            <p className="your-work-empty-text">
              {filterQuery.trim()
                ? `No work items matching "${filterQuery}" in this tab.`
                : activeTab === 'assigned'
                  ? 'No work items currently assigned to you.'
                  : activeTab === 'created'
                    ? 'You have not created any work items yet.'
                    : 'You are not subscribed to any work items yet.'}
            </p>
          </div>
        ) : (
          <div className="your-work-list" data-testid="your-work-list">
            {displayedIssues.map((issue) => {
              const priority = (issue as Partial<IssueItem>).priority;
              const state = (issue as Partial<IssueItem>).state;
              let priorityKind: 'priorityUrgent' | 'priorityHigh' | 'priorityMedium' | 'priorityLow' = 'priorityMedium';
              const pSlug = priority?.slug?.toLowerCase() ?? '';
              if (pSlug === 'urgent') priorityKind = 'priorityUrgent';
              else if (pSlug === 'high') priorityKind = 'priorityHigh';
              else if (pSlug === 'low') priorityKind = 'priorityLow';

              const projectKey =
                (issue as { project_key?: string }).project_key ??
                (issue.key.includes('-') ? issue.key.split('-')[0] : 'KAN');

              return (
                <article
                  key={issue.key}
                  className="your-work-card"
                  data-testid={`your-work-item-${issue.key}`}
                  onClick={() => { handleOpenPeek(issue.key); }}
                >
                  <div className="your-work-card-left">
                    <span className="your-work-project-tag">{projectKey}</span>
                    <a
                      href={`?peek=${encodeURIComponent(issue.key)}`}
                      className="your-work-key-link"
                      onClick={(e) => {
                        e.preventDefault();
                        handleOpenPeek(issue.key);
                      }}
                      data-testid={`peek-link-${issue.key}`}
                    >
                      {issue.key}
                    </a>
                    <span className="your-work-summary">{issue.summary}</span>
                  </div>

                  <div className="your-work-card-right">
                    {priority && (
                      <span className="your-work-priority-cell">
                        <EmojiHint kind={priorityKind} />
                        <span className="your-work-priority-label">
                          {priority.label ?? priority.slug}
                        </span>
                      </span>
                    )}

                    {state && (
                      <StateBadge state={state} className="status-pill" />
                    )}

                    <button
                      type="button"
                      className="your-work-peek-btn"
                      aria-label={`Inspect ${issue.key}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleOpenPeek(issue.key);
                      }}
                    >
                      Inspect →
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

export function YourWorkView(): JSX.Element {
  const client = useContext(QueryClientContext);
  if (!client) {
    return (
      <section data-testid="your-work-view" className="your-work-view">
        <header className="your-work-header">
          <h1>Your Work</h1>
        </header>
        <div className="your-work-empty-state">No work items found</div>
      </section>
    );
  }
  return <YourWorkViewInner />;
}
