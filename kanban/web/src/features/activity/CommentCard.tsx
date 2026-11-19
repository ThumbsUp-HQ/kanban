/**
 * Comment card with threaded replies (depth <= 1), 8-emoji reactions, permalink, edit & delete (KB-P3-44, S7.1, S7.2 8k).
 */

import React, { useState, type JSX } from 'react';
import { useNavigate, useLocation } from 'react-router';
import {
  type CommentResponse,
  type ReactionSummary,
  FROZEN_REACTION_EMOJIS,
  addReaction,
  removeReaction,
  deleteComment,
} from './activityApi';
import { SafeMarkdownPreview } from './SafeMarkdownPreview';
import { CommentComposer } from './CommentComposer';

export interface CommentCardProps {
  readonly comment: CommentResponse;
  readonly issueKey: string;
  readonly projectKey: string;
  readonly depth?: number | undefined;
  readonly currentUserId?: string | undefined;
  readonly onCommentUpdated?: (() => void) | undefined;
  readonly onCommentDeleted?: (() => void) | undefined;
}

export function CommentCard({
  comment,
  issueKey,
  projectKey,
  depth = 0,
  currentUserId,
  onCommentUpdated,
  onCommentDeleted,
}: CommentCardProps): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();

  const [isReplying, setIsReplying] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [reactions, setReactions] = useState<readonly ReactionSummary[]>(comment.reactions);
  const [copiedLink, setCopiedLink] = useState(false);

  const isTargeted = location.hash === `#comment-${comment.id}`;
  const isAuthor = Boolean(
    !comment.author.redacted &&
    currentUserId &&
    (comment.author_id === currentUserId || comment.author.id === currentUserId)
  );

  const handleCopyPermalink = (): void => {
    const fullUrl = `${window.location.origin}${location.pathname}${location.search}#comment-${comment.id}`;
    void navigator.clipboard.writeText(fullUrl);
    setCopiedLink(true);
    setTimeout(() => { setCopiedLink(false); }, 2000);
    void navigate(`${location.pathname}${location.search}#comment-${comment.id}`, { replace: true });
  };

  const handleToggleReaction = async (emoji: string): Promise<void> => {
    const existing = reactions.find((r) => r.emoji === emoji);
    const hasReacted = existing?.reacted_by_me ?? false;

    // Optimistic state update
    if (hasReacted) {
      setReactions((prev) =>
        prev
          .map((r) => (r.emoji === emoji ? { ...r, count: Math.max(0, r.count - 1), reacted_by_me: false } : r))
          .filter((r) => r.count > 0),
      );
      try {
        await removeReaction(comment.id, emoji);
      } catch {
        // Rollback
        setReactions(comment.reactions);
      }
    } else {
      setReactions((prev) => {
        const found = prev.some((r) => r.emoji === emoji);
        if (found) {
          return prev.map((r) =>
            r.emoji === emoji ? { ...r, count: r.count + 1, reacted_by_me: true } : r,
          );
        }
        return [...prev, { emoji, count: 1, reacted_by_me: true }];
      });
      try {
        await addReaction(comment.id, emoji);
      } catch {
        setReactions(comment.reactions);
      }
    }
    setShowPicker(false);
  };

  const handleDelete = async (): Promise<void> => {
    try {
      await deleteComment(comment.id);
      setShowDeleteConfirm(false);
      onCommentDeleted?.();
    } catch {
      // Handled by query refetch
    }
  };

  const formattedDate = new Date(comment.created_at).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <article
      id={`comment-${comment.id}`}
      className={`comment-card${isTargeted ? ' comment-card--targeted' : ''}${depth > 0 ? ' comment-card--reply' : ''}`}
    >
      {/* Header */}
      <div className="comment-card__header">
        <div className="comment-card__author-info">
          <span className="comment-card__author-name">
            {comment.author.redacted
              ? (comment.author.label ?? 'External Collaborator')
              : (comment.author.display_name ?? 'User')}
          </span>
          {!comment.author.redacted && Boolean(comment.author.handle) && (
            <span className="comment-card__author-handle">
              {`@${(comment.author.handle ?? '').replace(/^@/, '')}`}
            </span>
          )}
          <time dateTime={comment.created_at} className="comment-card__time">
            {formattedDate}
          </time>
          {comment.edited_at && <span className="comment-card__edited-badge">(edited)</span>}
        </div>

        <div className="comment-card__header-actions">
          {/* Permalink button */}
          <button
            type="button"
            className="comment-card__permalink-btn"
            aria-label="Copy permalink to comment"
            onClick={handleCopyPermalink}
            title={copiedLink ? 'Copied!' : 'Copy permalink'}
          >
            #
          </button>

          {/* Author Edit / Delete actions */}
          {!comment.deleted && isAuthor && !isEditing && (
            <>
              <button
                type="button"
                className="comment-card__action-btn"
                onClick={() => { setIsEditing(true); }}
              >
                Edit
              </button>
              <button
                type="button"
                className="comment-card__action-btn"
                onClick={() => { setShowDeleteConfirm(true); }}
              >
                Delete
              </button>
            </>
          )}
        </div>
      </div>

      {/* Delete Confirmation Prompt */}
      {showDeleteConfirm && (
        <div role="alertdialog" className="comment-card__delete-confirm">
          <span>Delete this comment?</span>
          <button
            type="button"
            className="delete-confirm-btn delete-confirm-btn--danger"
            onClick={() => { void handleDelete(); }}
          >
            Confirm Delete
          </button>
          <button
            type="button"
            className="delete-confirm-btn"
            onClick={() => { setShowDeleteConfirm(false); }}
          >
            Cancel
          </button>
        </div>
      )}

      {/* Body or Inline Editor */}
      {comment.deleted ? (
        <div className="comment-card__deleted-placeholder">
          <em>Comment deleted</em>
        </div>
      ) : isEditing ? (
        <div className="comment-card__inline-editor">
          <CommentComposer
            issueKey={issueKey}
            projectKey={projectKey}
            commentId={comment.id}
            initialValue={comment.body_markdown ?? ''}
            etag={comment.etag}
            isEditing={true}
            onSuccess={() => {
              setIsEditing(false);
              onCommentUpdated?.();
            }}
            onCancel={() => { setIsEditing(false); }}
          />
        </div>
      ) : (
        <div className="comment-card__body">
          <SafeMarkdownPreview markdown={comment.body_markdown ?? ''} />
        </div>
      )}

      {/* Reactions Bar & Reply Trigger */}
      {!comment.deleted && (
        <div className="comment-card__footer">
          <div className="comment-card__reactions-bar" role="group" aria-label="Emoji reactions">
            {reactions.map((r) => (
              <button
                key={r.emoji}
                type="button"
                className={`reaction-pill${r.reacted_by_me ? ' reaction-pill--active' : ''}`}
                aria-pressed={r.reacted_by_me}
                aria-label={`${r.emoji} reaction, ${String(r.count)} people reacted`}
                onClick={() => { void handleToggleReaction(r.emoji); }}
              >
                <span className="reaction-pill__emoji">{r.emoji}</span>
                <span className="reaction-pill__count">{r.count}</span>
              </button>
            ))}

            {/* Reaction Picker Button */}
            <div className="reaction-picker-wrapper">
              <button
                type="button"
                className="reaction-picker-btn"
                aria-label="Add reaction"
                onClick={() => { setShowPicker((prev) => !prev); }}
              >
                +😊
              </button>

              {showPicker && (
                <div className="reaction-picker-popover" role="dialog" aria-label="Select emoji reaction">
                  {FROZEN_REACTION_EMOJIS.map((emoji) => (
                    <button
                      key={emoji}
                      type="button"
                      className="reaction-picker-option"
                      onClick={() => { void handleToggleReaction(emoji); }}
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Depth <= 1 Reply action */}
          {depth === 0 && !isReplying && (
            <button
              type="button"
              className="comment-card__reply-btn"
              aria-label="Reply to comment"
              onClick={() => { setIsReplying(true); }}
            >
              Reply
            </button>
          )}
        </div>
      )}

      {/* Inline Reply Composer */}
      {isReplying && (
        <div className="comment-card__reply-composer">
          <CommentComposer
            issueKey={issueKey}
            projectKey={projectKey}
            parentCommentId={comment.id}
            placeholder="Write a reply..."
            onSuccess={() => {
              setIsReplying(false);
              onCommentUpdated?.();
            }}
            onCancel={() => { setIsReplying(false); }}
          />
        </div>
      )}

      {/* Nested Depth-1 Replies */}
      {depth === 0 && comment.replies && comment.replies.length > 0 && (
        <div className="comment-card__replies comment-replies">
          {comment.replies.map((reply) => (
            <CommentCard
              key={reply.id}
              comment={reply}
              issueKey={issueKey}
              projectKey={projectKey}
              depth={1}
              currentUserId={currentUserId}
              onCommentUpdated={onCommentUpdated}
              onCommentDeleted={onCommentDeleted}
            />
          ))}
        </div>
      )}
    </article>
  );
}
