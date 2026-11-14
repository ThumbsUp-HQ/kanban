/**
 * Activity & Comment Section with 4-tab filtering, threaded comments, and hash chain inspect (KB-P3-44, S7.1, S7.2 8j/8k).
 */

import React, {
  useState,
  useEffect,
  useRef,
  type JSX,
  type KeyboardEvent,
} from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { IssueDetail } from '../drawer/slots';
import { qk } from '../../api/queryKeys';
import {
  type ActivityTab,
  type ActivityResponse,
  type CommentList,
  fetchActivity,
  fetchComments,
} from './activityApi';
import { ActivityEventRow } from './ActivityEventRow';
import { CommentCard } from './CommentCard';
import { CommentComposer } from './CommentComposer';
import './activity.css';

export interface ActivitySectionProps {
  readonly issue: IssueDetail;
  readonly currentUserId?: string;
}

const TABS: readonly {
  readonly id: ActivityTab;
  readonly label: string;
  readonly getBadgeCount?: (counts: ActivityResponse['counts']) => number;
  readonly isGate?: boolean;
}[] = [
  { id: 'all', label: 'All' },
  { id: 'comments', label: 'Comments', getBadgeCount: (c) => c.comments },
  { id: 'history', label: 'History' },
  { id: 'gates', label: 'Gates', getBadgeCount: (c) => c.gates, isGate: true },
];

export function ActivitySection({
  issue,
  currentUserId,
}: ActivitySectionProps): JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<ActivityTab>('all');
  const [cursor, setCursor] = useState<string | null>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const issueKey = issue.key;
  const projectKey = issue.project_key;

  // Query Activity ledger records
  const {
    data: activityData,
    isLoading: isActivityLoading,
    refetch: refetchActivity,
  } = useQuery<ActivityResponse>({
    queryKey: [...qk.activity(issueKey, activeTab), cursor],
    queryFn: () => fetchActivity(issueKey, activeTab, cursor),
    staleTime: 30_000,
  });

  // Query Comments when on 'all' or 'comments' tab
  const shouldFetchComments = activeTab === 'all' || activeTab === 'comments';
  const {
    data: commentsData,
    isLoading: isCommentsLoading,
    refetch: refetchComments,
  } = useQuery<CommentList>({
    queryKey: ['comments', issueKey],
    queryFn: () => fetchComments(issueKey),
    enabled: shouldFetchComments,
    staleTime: 30_000,
  });

  const counts = activityData?.counts ?? {
    all: 0,
    comments: commentsData?.items.length ?? 0,
    history: 0,
    gates: 0,
  };

  // Scroll to targeted comment if #comment-<uuid> is present in hash
  useEffect(() => {
    if (location.hash.startsWith('#comment-')) {
      const commentId = location.hash.replace('#comment-', '');
      // Switch tab to 'all' or 'comments' if on history or gates
      if (activeTab === 'history' || activeTab === 'gates') {
        setTimeout(() => {
          setActiveTab('all');
        }, 0);
      }

      // Allow DOM to settle before scrolling
      const timer = setTimeout(() => {
        const targetEl = document.getElementById(`comment-${commentId}`);
        if (targetEl) {
          targetEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      }, 100);
      return () => {
        clearTimeout(timer);
      };
    }
  }, [location.hash, activeTab]);

  const handleJumpToComment = (commentId: string): void => {
    if (activeTab === 'history' || activeTab === 'gates') {
      setActiveTab('all');
    }
    const hash = `#comment-${commentId}`;
    void navigate(`${location.pathname}${location.search}${hash}`, { replace: true });
    setTimeout(() => {
      const targetEl = document.getElementById(`comment-${commentId}`);
      if (targetEl) {
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }, 100);
  };

  const handleTabKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number): void => {
    let nextIndex = index;
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      nextIndex = (index + 1) % TABS.length;
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      nextIndex = (index - 1 + TABS.length) % TABS.length;
    } else if (e.key === 'Home') {
      e.preventDefault();
      nextIndex = 0;
    } else if (e.key === 'End') {
      e.preventDefault();
      nextIndex = TABS.length - 1;
    }

    if (nextIndex !== index) {
      const target = TABS[nextIndex];
      if (target) {
        setActiveTab(target.id);
        tabRefs.current[nextIndex]?.focus();
      }
    }
  };

  const handleRefresh = (): void => {
    void refetchActivity();
    if (shouldFetchComments) {
      void refetchComments();
    }
    void queryClient.invalidateQueries({ queryKey: qk.activity(issueKey, activeTab) });
  };

  // Build rendered items based on active tab
  const activityItems = activityData?.items ?? [];
  const comments = commentsData?.items ?? [];

  return (
    <section className="activity-section" aria-labelledby="activity-heading">
      {/* Header and 4-Tab Bar */}
      <div className="activity-section__header">
        <h2 id="activity-heading" className="activity-section__title">
          Activity
        </h2>

        <div className="activity-tablist" role="tablist" aria-label="Activity filter tabs">
          {TABS.map((tab, idx) => {
            const isActive = activeTab === tab.id;
            const badgeCount = tab.getBadgeCount ? tab.getBadgeCount(counts) : undefined;
            const accessibleName = tab.isGate
              ? `Agent and workflow gates (${String(badgeCount ?? 0)})`
              : badgeCount !== undefined
                ? `${tab.label} (${String(badgeCount)})`
                : tab.label;

            return (
              <button
                key={tab.id}
                ref={(el) => { tabRefs.current[idx] = el; }}
                type="button"
                role="tab"
                id={`activity-tab-${tab.id}`}
                aria-selected={isActive}
                aria-controls={`activity-tabpanel-${tab.id}`}
                aria-label={accessibleName}
                tabIndex={isActive ? 0 : -1}
                className={`activity-tab${isActive ? ' activity-tab--active' : ''}`}
                onClick={() => {
                  setActiveTab(tab.id);
                  setCursor(null);
                }}
                onKeyDown={(e) => { handleTabKeyDown(e, idx); }}
              >
                {tab.isGate && <span aria-hidden="true">🤖 </span>}
                <span>{tab.label}</span>
                {badgeCount !== undefined && (
                  <span className="activity-tab__badge">({badgeCount})</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Panel */}
      <div
        id={`activity-tabpanel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`activity-tab-${activeTab}`}
        className="activity-feed"
      >
        {isActivityLoading && activityItems.length === 0 ? (
          <div className="activity-feed__loading">Loading activity...</div>
        ) : null}

        {/* Tab: Comments only */}
        {activeTab === 'comments' && (
          <>
            {comments.length === 0 && !isCommentsLoading && (
              <div className="activity-feed__empty">No comments yet.</div>
            )}
            {comments.map((comment) => (
              <CommentCard
                key={comment.id}
                comment={comment}
                issueKey={issueKey}
                projectKey={projectKey}
                currentUserId={currentUserId}
                onCommentUpdated={handleRefresh}
                onCommentDeleted={handleRefresh}
              />
            ))}
          </>
        )}

        {/* Tab: History only */}
        {activeTab === 'history' && (
          <>
            {activityItems.length === 0 && !isActivityLoading && (
              <div className="activity-feed__empty">No history recorded yet.</div>
            )}
            {activityItems
              .filter((item) => item.category === 'HISTORY')
              .map((item) => (
                <ActivityEventRow
                  key={item.id}
                  item={item}
                  onJumpToComment={handleJumpToComment}
                />
              ))}
          </>
        )}

        {/* Tab: Gates only */}
        {activeTab === 'gates' && (
          <>
            {activityItems.length === 0 && !isActivityLoading && (
              <div className="activity-feed__empty">No agent or workflow gates recorded yet.</div>
            )}
            {activityItems
              .filter((item) => item.category === 'AGENT_GATE')
              .map((item) => (
                <ActivityEventRow
                  key={item.id}
                  item={item}
                  onJumpToComment={handleJumpToComment}
                />
              ))}
          </>
        )}

        {/* Tab: All */}
        {activeTab === 'all' && (
          <>
            {activityItems.length === 0 && comments.length === 0 && !isActivityLoading && !isCommentsLoading && (
              <div className="activity-feed__empty">No activity yet.</div>
            )}
            {/* Render ledger items */}
            {activityItems.map((item) => (
              <ActivityEventRow
                key={item.id}
                item={item}
                onJumpToComment={handleJumpToComment}
              />
            ))}
            {/* Render top-level comments */}
            {comments.map((comment) => (
              <CommentCard
                key={comment.id}
                comment={comment}
                issueKey={issueKey}
                projectKey={projectKey}
                currentUserId={currentUserId}
                onCommentUpdated={handleRefresh}
                onCommentDeleted={handleRefresh}
              />
            ))}
          </>
        )}

        {/* Cursor Pagination Button */}
        {activityData?.next_cursor && (
          <button
            type="button"
            className="activity-feed__load-older"
            onClick={() => { setCursor(activityData.next_cursor); }}
          >
            Load older activity
          </button>
        )}
      </div>

      {/* Comment Composer */}
      <CommentComposer
        issueKey={issueKey}
        projectKey={projectKey}
        onSuccess={handleRefresh}
      />
    </section>
  );
}
