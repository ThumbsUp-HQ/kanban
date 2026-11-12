import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import {
  CommentComposer,
  isCursorInsideCode,
  extractMentionPrefix,
  formatMentionWarning,
  getUtf8ByteLength,
  MAX_COMMENT_BYTES,
} from './CommentComposer';
import * as activityApi from './activityApi';
import { ApiProblem } from '../../api/problem';

vi.mock('./activityApi', async () => {
  const actual = await vi.importActual<typeof import('./activityApi')>('./activityApi');
  return {
    ...actual,
    createComment: vi.fn(),
    patchComment: vi.fn(),
    fetchAssigneeSuggestions: vi.fn(),
  };
});

describe('CommentComposer', () => {
  const mockCreateComment = vi.mocked(activityApi.createComment);
  const mockPatchComment = vi.mocked(activityApi.patchComment);
  const mockFetchAssigneeSuggestions = vi.mocked(activityApi.fetchAssigneeSuggestions);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Utility functions', () => {
    it('calculates UTF-8 byte length correctly including multi-byte emojis', () => {
      expect(getUtf8ByteLength('abc')).toBe(3);
      expect(getUtf8ByteLength('🚀')).toBe(4);
      expect(getUtf8ByteLength('こんにちは')).toBe(15);
    });

    it('detects when cursor is inside fenced code block or inline backticks', () => {
      const fenced = '```\nconst a = 1;\n```';
      expect(isCursorInsideCode(fenced, 10)).toBe(true);
      expect(isCursorInsideCode(fenced, 2)).toBe(false);

      const inline = '`const x = 1` outside';
      expect(isCursorInsideCode(inline, 5)).toBe(true);
      expect(isCursorInsideCode(inline, 16)).toBe(false);
    });

    it('extracts mention prefix when outside code and suppresses inside code', () => {
      expect(extractMentionPrefix('Hello @adam', 11)).toBe('adam');
      expect(extractMentionPrefix('Hello @', 7)).toBe('');
      expect(extractMentionPrefix('`@adam`', 5)).toBeNull();
      expect(extractMentionPrefix('```\n@adam\n```', 8)).toBeNull();
    });

    it('formats single and multiple unauthorized mention warnings without granting access', () => {
      const single = formatMentionWarning([{ handle: 'maya' }]);
      expect(single).toBe(
        '@maya cannot view this issue. Posting will NOT grant access or send a notification to @maya.',
      );

      const multiple = formatMentionWarning([{ handle: 'maya' }, { handle: 'alex' }]);
      expect(multiple).toBe(
        '@maya, @alex cannot view this issue. Posting will NOT grant access or send notifications to them.',
      );
    });
  });

  describe('Test Case 3 & 4: Composer interactions, mentions, warnings & bounds', () => {
    it('blocks empty submission and comments exceeding 262,144 bytes client-side', async () => {
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);

      const submitBtn = screen.getByRole('button', { name: 'Comment' });
      fireEvent.click(submitBtn);

      const errEmpty = await screen.findByText('Comment cannot be empty.');
      expect(errEmpty).toBeDefined();
      expect(mockCreateComment).not.toHaveBeenCalled();

      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      // Create string larger than MAX_COMMENT_BYTES
      const hugeString = 'a'.repeat(MAX_COMMENT_BYTES + 1);
      fireEvent.change(textarea, { target: { value: hugeString } });
      fireEvent.click(submitBtn);

      const errLarge = await screen.findByText('Comment exceeds maximum size of 262,144 bytes.');
      expect(errLarge).toBeDefined();
      expect(mockCreateComment).not.toHaveBeenCalled();
    });

    it('inserts formatting tokens from toolbar buttons', () => {
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);

      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      // Click Bold
      const boldBtn = screen.getByRole('button', { name: 'Bold text' });
      fireEvent.click(boldBtn);
      expect(textarea.value).toBe('**bold text**');

      // Click Italic
      const italicBtn = screen.getByRole('button', { name: 'Italic text' });
      fireEvent.click(italicBtn);
      expect(textarea.value).toContain('*italic text*');

      // Click Mermaid
      const mermaidBtn = screen.getByRole('button', { name: 'Insert Mermaid diagram' });
      fireEvent.click(mermaidBtn);
      expect(textarea.value).toContain('```mermaid');
    });

    it('triggers assignee suggestions when typing @prefix and inserts selected handle', async () => {
      mockFetchAssigneeSuggestions.mockResolvedValueOnce({
        items: [
          { id: 'u1', handle: 'adam', display_name: 'Adam Outler' },
          { id: 'u2', handle: 'alex', display_name: 'Alex Developer' },
        ],
      });

      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);

      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, {
        target: { value: 'Hey @ad', selectionStart: 7, selectionEnd: 7 },
      });

      await waitFor(() => {
        expect(mockFetchAssigneeSuggestions).toHaveBeenCalledWith('KAN', 'ad');
      });

      const suggestionItem = await screen.findByRole('option', { name: /@adam/ });
      expect(suggestionItem).toBeDefined();

      fireEvent.click(suggestionItem);
      await waitFor(() => {
        expect(textarea.value).toBe('Hey @adam ');
      });
    });

    it('displays 409 MENTION_ACCESS_WARNING alert and resubmits with acknowledged principals', async () => {
      const warningProblem = new ApiProblem(409, {
        code: 'MENTION_ACCESS_WARNING',
        unauthorized_mentions: [
          { handle: 'maya', principal_id: '0193-maya-uuid' },
        ],
      });
      mockCreateComment.mockRejectedValueOnce(warningProblem);

      const onSuccess = vi.fn();
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" onSuccess={onSuccess} />);

      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'cc @maya please check' } });

      const submitBtn = screen.getByRole('button', { name: 'Comment' });
      fireEvent.click(submitBtn);

      const alert = await screen.findByRole('alert');
      expect(alert.textContent).toContain(
        '@maya cannot view this issue. Posting will NOT grant access or send a notification to @maya.',
      );
      expect(textarea.value).toBe('cc @maya please check');

      // Now click "Post without granting access"
      mockCreateComment.mockResolvedValueOnce({
        id: 'new-c-uuid',
        issue_id: 'iss-1',
        author: { id: 'u1', handle: 'me' },
        body_markdown: 'cc @maya please check',
        reactions: [],
        created_at: new Date().toISOString(),
        deleted: false,
      });

      const postWithoutAccessBtn = screen.getByRole('button', {
        name: 'Post without granting access',
      });
      fireEvent.click(postWithoutAccessBtn);

      await waitFor(() => {
        expect(mockCreateComment).toHaveBeenCalledWith('KAN-142', {
          body_markdown: 'cc @maya please check',
          parent_comment_id: null,
          acknowledge_mentions: ['0193-maya-uuid'],
        });
      });
      expect(onSuccess).toHaveBeenCalled();
    });

    it('handles 412 Precondition Failed during edit by keeping draft and displaying conflict alert', async () => {
      const conflictProblem = new ApiProblem(412, {
        code: 'PRECONDITION_FAILED',
        detail: 'ETag mismatch',
      });
      mockPatchComment.mockRejectedValueOnce(conflictProblem);

      render(
        <CommentComposer
          issueKey="KAN-142"
          projectKey="KAN"
          commentId="comm-1"
          etag='"etag-v1"'
          initialValue="Existing text"
          isEditing={true}
        />,
      );

      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'Modified text' } });

      const saveBtn = screen.getByRole('button', { name: 'Save Changes' });
      fireEvent.click(saveBtn);

      const alert = await screen.findByRole('alert');
      expect(alert.textContent).toContain(
        'This comment was edited elsewhere. Copy your changes and reload.',
      );
      expect(textarea.value).toBe('Modified text');
    });

    it('submits on Cmd+Enter / Ctrl+Enter keyboard shortcut', async () => {
      mockCreateComment.mockResolvedValueOnce({
        id: 'new-c',
        issue_id: 'i1',
        author: { id: 'u1' },
        body_markdown: 'Shortcut comment',
        reactions: [],
        created_at: '',
        deleted: false,
      });

      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'Shortcut comment' } });

      fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true });

      await waitFor(() => {
        expect(mockCreateComment).toHaveBeenCalledWith('KAN-142', expect.objectContaining({
          body_markdown: 'Shortcut comment',
        }));
      });
    });

    it('handles suggestion keyboard navigation (ArrowDown, ArrowUp, Enter, Escape)', async () => {
      mockFetchAssigneeSuggestions.mockResolvedValueOnce({
        items: [
          { id: 'u1', handle: 'adam', display_name: 'Adam Outler' },
          { id: 'u2', handle: 'alex', display_name: 'Alex Developer' },
        ],
      });

      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      fireEvent.change(textarea, {
        target: { value: 'Hey @a', selectionStart: 6, selectionEnd: 6 },
      });

      await screen.findByRole('option', { name: /@adam/ });

      // ArrowDown to move to second suggestion (@alex)
      fireEvent.keyDown(textarea, { key: 'ArrowDown' });
      // ArrowUp back to first suggestion (@adam)
      fireEvent.keyDown(textarea, { key: 'ArrowUp' });
      // Enter to select first suggestion
      fireEvent.keyDown(textarea, { key: 'Enter' });

      await waitFor(() => {
        expect(textarea.value).toBe('Hey @adam ');
      });

      // Now trigger autocomplete again and press Escape to dismiss
      mockFetchAssigneeSuggestions.mockResolvedValueOnce({
        items: [{ id: 'u1', handle: 'adam', display_name: 'Adam Outler' }],
      });
      fireEvent.change(textarea, {
        target: { value: 'Hey @adam and @a', selectionStart: 16, selectionEnd: 16 },
      });
      await screen.findByRole('option', { name: /@adam/ });

      fireEvent.keyDown(textarea, { key: 'Escape' });
      expect(screen.queryByRole('listbox')).toBeNull();
    });

    it('calls onCancel callback when Cancel button is clicked', () => {
      const onCancel = vi.fn();
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" onCancel={onCancel} />);

      const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
      fireEvent.click(cancelBtn);
      expect(onCancel).toHaveBeenCalled();
    });

    it('dismisses mention warning and refocuses textarea when Edit comment is clicked', async () => {
      const warningProblem = new ApiProblem(409, {
        code: 'MENTION_ACCESS_WARNING',
        unauthorized_mentions: [
          { handle: 'maya', principal_id: '0193-maya-uuid' },
        ],
      });
      mockCreateComment.mockRejectedValueOnce(warningProblem);

      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: '@maya test' } });

      const submitBtn = screen.getByRole('button', { name: 'Comment' });
      fireEvent.click(submitBtn);

      const editCommentBtn = await screen.findByRole('button', { name: 'Edit comment' });
      fireEvent.click(editCommentBtn);

      expect(screen.queryByRole('alert')).toBeNull();
    });

    it('handles onMouseDown on mention suggestions', async () => {
      mockFetchAssigneeSuggestions.mockResolvedValueOnce({
        items: [{ id: 'u1', handle: 'adam', display_name: 'Adam Outler' }],
      });

      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, {
        target: { value: 'Hi @ad', selectionStart: 6, selectionEnd: 6 },
      });

      const option = await screen.findByRole('option', { name: /@adam/ });
      fireEvent.mouseDown(option);

      await waitFor(() => {
        expect(textarea.value).toBe('Hi @adam ');
      });
    });

    it('inserts code, link, and media markdown templates from toolbar buttons', () => {
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      // Click Code button
      const codeBtn = screen.getByRole('button', { name: 'Insert code' });
      fireEvent.click(codeBtn);
      expect(textarea.value).toContain('```\ncode\n```');

      // Click Link button
      const linkBtn = screen.getByRole('button', { name: 'Insert link' });
      fireEvent.click(linkBtn);
      expect(textarea.value).toContain('[link text](https://example.com)');

      // Click Media button
      const mediaBtn = screen.getByRole('button', { name: 'Attach media or SVG' });
      fireEvent.click(mediaBtn);
      expect(textarea.value).toContain('![alt text](https://example.com/media.png)');
    });

    it('handles generic non-ApiProblem errors on submit', async () => {
      mockCreateComment.mockRejectedValueOnce(new Error('Network offline'));
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);

      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'Test comment' } });

      const submitBtn = screen.getByRole('button', { name: 'Comment' });
      fireEvent.click(submitBtn);

      const alert = await screen.findByRole('alert');
      expect(alert.textContent).toBe('Network offline');
    });

    it('clears suggestions when typing text without @ prefix', () => {
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      // Type normal text without @
      fireEvent.change(textarea, { target: { value: 'Just normal text', selectionStart: 10, selectionEnd: 10 } });
      expect(screen.queryByRole('listbox')).toBeNull();
    });

    it('falls back to default error text when error has empty message', async () => {
      mockCreateComment.mockRejectedValueOnce(new Error(''));
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);

      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'Something' } });

      const submitBtn = screen.getByRole('button', { name: 'Comment' });
      fireEvent.click(submitBtn);

      const alert = await screen.findByRole('alert');
      expect(alert.textContent).toBe('Failed to submit comment.');
    });
  });
});
