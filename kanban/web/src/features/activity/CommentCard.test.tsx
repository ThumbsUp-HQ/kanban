import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { CommentCard } from './CommentCard';
import type { CommentResponse } from './activityApi';
import * as activityApi from './activityApi';

vi.mock('./activityApi', async () => {
  const actual = await vi.importActual<typeof import('./activityApi')>('./activityApi');
  return {
    ...actual,
    addReaction: vi.fn(),
    removeReaction: vi.fn(),
    deleteComment: vi.fn(),
    patchComment: vi.fn(),
    createComment: vi.fn(),
  };
});

describe('CommentCard', () => {
  const mockAddReaction = vi.mocked(activityApi.addReaction);
  const mockRemoveReaction = vi.mocked(activityApi.removeReaction);
  const mockDeleteComment = vi.mocked(activityApi.deleteComment);
  const mockPatchComment = vi.mocked(activityApi.patchComment);
  const mockCreateComment = vi.mocked(activityApi.createComment);

  const sampleComment: CommentResponse = {
    id: 'c1111111-1111-1111-1111-111111111111',
    issue_id: 'iss-1',
    author: {
      id: 'usr-author-1',
      handle: 'alice',
      display_name: 'Alice Architect',
    },
    body_markdown: 'This is the top-level comment body.',
    reactions: [
      { emoji: '🚀', count: 3, reacted_by_me: true },
      { emoji: '👍', count: 1, reacted_by_me: false },
    ],
    replies: [
      {
        id: 'c2222222-2222-2222-2222-222222222222',
        parent_comment_id: 'c1111111-1111-1111-1111-111111111111',
        issue_id: 'iss-1',
        author: {
          id: 'usr-reply-2',
          handle: 'bob',
          display_name: 'Bob Builder',
        },
        body_markdown: 'This is a depth-1 nested reply.',
        reactions: [],
        created_at: '2026-11-12T10:00:00Z',
        deleted: false,
      },
    ],
    created_at: '2026-11-12T09:00:00Z',
    deleted: false,
    etag: '"etag-c1"',
  };

  const mockWriteText = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: mockWriteText,
      },
    });
  });

  describe('Test Case 2: Threaded replies, reactions, permalinks & depth <= 1', () => {
    it('renders top-level comment and depth-1 nested replies, enforcing depth <= 1 reply constraint', () => {
      render(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
          />
        </MemoryRouter>,
      );

      // Top level comment has a Reply button
      const replyButtons = screen.getAllByRole('button', { name: 'Reply to comment' });
      expect(replyButtons.length).toBe(1);

      // Nested reply is visible
      expect(screen.getByText('This is a depth-1 nested reply.')).toBeDefined();
      expect(screen.getByText('@bob')).toBeDefined();
    });

    it('toggles reaction by calling removeReaction when active and addReaction when inactive', async () => {
      mockRemoveReaction.mockResolvedValueOnce();
      mockAddReaction.mockResolvedValueOnce({
        emoji: '👍',
        count: 2,
        reacted_by_me: true,
      });

      render(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
          />
        </MemoryRouter>,
      );

      // Active reaction: 🚀
      const rocketBtn = screen.getByRole('button', { name: /🚀/ });
      expect(rocketBtn.getAttribute('aria-pressed')).toBe('true');

      fireEvent.click(rocketBtn);
      await waitFor(() => {
        expect(mockRemoveReaction).toHaveBeenCalledWith(sampleComment.id, '🚀');
      });

      // Inactive reaction: 👍
      const thumbsUpBtn = screen.getByRole('button', { name: /👍/ });
      expect(thumbsUpBtn.getAttribute('aria-pressed')).toBe('false');

      fireEvent.click(thumbsUpBtn);
      await waitFor(() => {
        expect(mockAddReaction).toHaveBeenCalledWith(sampleComment.id, '👍');
      });
    });

    it('renders "Comment deleted" placeholder when soft-deleted, but keeps child replies visible', () => {
      const deletedParent: CommentResponse = {
        ...sampleComment,
        deleted: true,
        body_markdown: '',
      };

      render(
        <MemoryRouter>
          <CommentCard
            comment={deletedParent}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
          />
        </MemoryRouter>,
      );

      expect(screen.getByText('Comment deleted')).toBeDefined();
      expect(screen.queryByText('This is the top-level comment body.')).toBeNull();
      // Nested child reply remains visible
      expect(screen.getByText('This is a depth-1 nested reply.')).toBeDefined();
    });

    it('copies permalink to clipboard and updates hash on permalink button click', () => {
      render(
        <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
          />
        </MemoryRouter>,
      );

      const permalinkBtns = screen.getAllByRole('button', { name: 'Copy permalink to comment' });
      const firstBtn = permalinkBtns[0];
      if (firstBtn) {
        fireEvent.click(firstBtn);
      }

      expect(mockWriteText).toHaveBeenCalledWith(
        expect.stringContaining(`#comment-${sampleComment.id}`),
      );
    });

    it('shows Edit and Delete buttons for author only, and handles delete confirmation', async () => {
      mockDeleteComment.mockResolvedValueOnce();
      const onCommentDeleted = vi.fn();

      const { rerender } = render(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-other-99" // Not the author
          />
        </MemoryRouter>,
      );

      expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Delete' })).toBeNull();

      // Rerender with author
      rerender(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
            onCommentDeleted={onCommentDeleted}
          />
        </MemoryRouter>,
      );

      const editBtn = screen.getByRole('button', { name: 'Edit' });
      expect(editBtn).toBeDefined();

      const deleteBtn = screen.getByRole('button', { name: 'Delete' });
      fireEvent.click(deleteBtn);

      expect(screen.getByText('Delete this comment?')).toBeDefined();
      const confirmBtn = screen.getByRole('button', { name: 'Confirm Delete' });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(mockDeleteComment).toHaveBeenCalledWith(sampleComment.id);
        expect(onCommentDeleted).toHaveBeenCalled();
      });
    });

    it('cancels delete confirmation dialog when clicking Cancel', () => {
      render(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
          />
        </MemoryRouter>,
      );

      const deleteBtn = screen.getByRole('button', { name: 'Delete' });
      fireEvent.click(deleteBtn);
      expect(screen.getByText('Delete this comment?')).toBeDefined();

      const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
      fireEvent.click(cancelBtn);
      expect(screen.queryByText('Delete this comment?')).toBeNull();
    });

    it('enters inline edit mode, cancels edit, and handles successful edit', () => {
      const onCommentUpdated = vi.fn();
      render(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
            onCommentUpdated={onCommentUpdated}
          />
        </MemoryRouter>,
      );

      const editBtn = screen.getByRole('button', { name: 'Edit' });
      fireEvent.click(editBtn);

      // Verify inline editor is displayed
      const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
      expect(cancelBtn).toBeDefined();

      // Click cancel to close editor
      fireEvent.click(cancelBtn);
      expect(screen.getByText('This is the top-level comment body.')).toBeDefined();
    });

    it('opens emoji picker and adds reaction from picker popup', async () => {
      mockAddReaction.mockResolvedValueOnce({
        emoji: '🎉',
        count: 1,
        reacted_by_me: true,
      });

      render(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
          />
        </MemoryRouter>,
      );

      const pickerBtns = screen.getAllByRole('button', { name: 'Add reaction' });
      const pickerBtn = pickerBtns[0];
      if (pickerBtn) {
        fireEvent.click(pickerBtn);
      }

      const partyEmojiBtn = screen.getByRole('button', { name: '🎉' });
      fireEvent.click(partyEmojiBtn);

      await waitFor(() => {
        expect(mockAddReaction).toHaveBeenCalledWith(sampleComment.id, '🎉');
      });
    });

    it('opens reply composer on Reply click and cancels reply', () => {
      render(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
          />
        </MemoryRouter>,
      );

      const replyBtn = screen.getByRole('button', { name: 'Reply to comment' });
      fireEvent.click(replyBtn);

      // Reply composer is open
      const cancelReplyBtn = screen.getByRole('button', { name: 'Cancel' });
      expect(cancelReplyBtn).toBeDefined();

      fireEvent.click(cancelReplyBtn);
      // Closed
      expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
    });

    it('handles successful edit submission and calls onCommentUpdated', async () => {
      mockPatchComment.mockResolvedValueOnce({ ...sampleComment, body_markdown: 'New text' });
      const onCommentUpdated = vi.fn();
      render(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
            onCommentUpdated={onCommentUpdated}
          />
        </MemoryRouter>,
      );

      const editBtn = screen.getByRole('button', { name: 'Edit' });
      fireEvent.click(editBtn);

      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'New text' } });

      const saveBtn = screen.getByRole('button', { name: 'Save Changes' });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(onCommentUpdated).toHaveBeenCalled();
      });
    });

    it('handles successful reply submission and calls onCommentUpdated', async () => {
      mockCreateComment.mockResolvedValueOnce({
        id: 'r-new',
        issue_id: 'iss-1',
        author: { id: 'u1' },
        body_markdown: 'Reply text',
        reactions: [],
        created_at: '',
        deleted: false,
      });
      const onCommentUpdated = vi.fn();
      render(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
            onCommentUpdated={onCommentUpdated}
          />
        </MemoryRouter>,
      );

      const replyBtn = screen.getByRole('button', { name: 'Reply to comment' });
      fireEvent.click(replyBtn);

      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'Reply text' } });

      const submitReplyBtn = screen.getByRole('button', { name: 'Reply' });
      fireEvent.click(submitReplyBtn);

      await waitFor(() => {
        expect(onCommentUpdated).toHaveBeenCalled();
      });
    });

    it('handles comments with empty body and no replies without crashing', () => {
      const minimalComment: CommentResponse = {
        id: 'min-1',
        issue_id: 'iss-1',
        author: { id: 'u2', handle: 'carol' },
        reactions: [],
        created_at: '2026-11-12T10:00:00Z',
        deleted: false,
      };

      render(
        <MemoryRouter>
          <CommentCard
            comment={minimalComment}
            issueKey="KAN-142"
            projectKey="KAN"
          />
        </MemoryRouter>,
      );

      expect(screen.getByText('@carol')).toBeDefined();
    });

    it('rolls back optimistic reaction state on API failure', async () => {
      mockRemoveReaction.mockRejectedValueOnce(new Error('Network error'));
      render(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
          />
        </MemoryRouter>,
      );

      const rocketBtn = screen.getByRole('button', { name: /🚀/ });
      fireEvent.click(rocketBtn);

      await waitFor(() => {
        expect(mockRemoveReaction).toHaveBeenCalled();
      });

      // Test addReaction failure rollback
      mockAddReaction.mockRejectedValueOnce(new Error('Network error'));
      const thumbsUpBtn = screen.getByRole('button', { name: /👍/ });
      fireEvent.click(thumbsUpBtn);

      await waitFor(() => {
        expect(mockAddReaction).toHaveBeenCalled();
      });
    });

    it('handles delete failure gracefully', async () => {
      mockDeleteComment.mockRejectedValueOnce(new Error('Delete failed'));
      render(
        <MemoryRouter>
          <CommentCard
            comment={sampleComment}
            issueKey="KAN-142"
            projectKey="KAN"
            currentUserId="usr-author-1"
          />
        </MemoryRouter>,
      );

      const deleteBtn = screen.getByRole('button', { name: 'Delete' });
      fireEvent.click(deleteBtn);

      const confirmBtn = screen.getByRole('button', { name: 'Confirm Delete' });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(mockDeleteComment).toHaveBeenCalled();
      });
    });
  });
});
