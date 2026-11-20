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
import * as autoConvertPasteMod from '../../editor/clipboard/autoConvertPaste';
import { sanitizeAndValidateMermaid } from '../../editor/mermaid/mermaidFirewall';
import { renderMermaidSVG } from 'beautiful-mermaid';

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
      expect(isCursorInsideCode('', 0)).toBe(false);
      expect(isCursorInsideCode('hello world', 5)).toBe(false);
      expect(isCursorInsideCode('line 1\nline 2', 8)).toBe(false);

      const fenced = '```\nconst a = 1;\n```';
      expect(isCursorInsideCode(fenced, 10)).toBe(true);
      expect(isCursorInsideCode(fenced, 2)).toBe(false);

      const inline = '`const x = 1` outside';
      expect(isCursorInsideCode(inline, 5)).toBe(true);
      expect(isCursorInsideCode(inline, 16)).toBe(false);

      const multiline = 'line1\n`code on line 2` outside';
      expect(isCursorInsideCode(multiline, 12)).toBe(true);
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

      // Select via Tab key
      mockFetchAssigneeSuggestions.mockResolvedValueOnce({
        items: [{ id: 'u2', handle: 'alex', display_name: 'Alex' }],
      });
      fireEvent.change(textarea, { target: { value: 'Hey @alex and @al', selectionStart: 18, selectionEnd: 18 } });
      await screen.findByRole('option', { name: /@alex/ });
      fireEvent.keyDown(textarea, { key: 'Tab' });
      await waitFor(() => {
        expect(textarea.value).toContain('@alex ');
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

    it('handles keyboard navigation and selection in mention autocomplete and shortcut submit', async () => {
      mockFetchAssigneeSuggestions.mockResolvedValue({
        items: [
          { id: 'u1', handle: 'alice', display_name: 'Alice' },
          { id: 'u2', handle: 'bob', display_name: 'Bob' },
        ],
      });
      mockCreateComment.mockResolvedValueOnce({
        id: 'c-sub',
        issue_id: 'i-142',
        body_markdown: '@alice test',
        created_at: '2026-11-18T00:00:00Z',
        deleted: false,
        author: { id: 'u1', handle: 'me', display_name: 'Me' },
        mentions: [],
        reactions: [],
      });

      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      // Trigger suggestions
      fireEvent.change(textarea, {
        target: { value: '@', selectionStart: 1, selectionEnd: 1 },
      });

      await screen.findByRole('option', { name: /@alice/ });

      // Arrow down to bob
      fireEvent.keyDown(textarea, { key: 'ArrowDown' });
      // Arrow up back to alice
      fireEvent.keyDown(textarea, { key: 'ArrowUp' });

      // Press Enter to choose alice
      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(textarea.value).toBe('@alice ');

      // Trigger again and dismiss with Escape
      fireEvent.change(textarea, {
        target: { value: '@alice @b', selectionStart: 9, selectionEnd: 9 },
      });
      await screen.findByRole('option', { name: /@bob/ });
      fireEvent.keyDown(textarea, { key: 'Escape' });
      expect(screen.queryByRole('listbox')).toBeNull();

      // Submit via Ctrl+Enter
      fireEvent.change(textarea, { target: { value: '@alice test' } });
      fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true });

      await waitFor(() => {
        expect(mockCreateComment).toHaveBeenCalledWith('KAN-142', expect.objectContaining({
          body_markdown: '@alice test',
        }));
      });
    });

    it('inserts bold, italic, and mermaid markdown templates from toolbar buttons', () => {
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      fireEvent.click(screen.getByRole('button', { name: 'Bold text' }));
      expect(textarea.value).toContain('**bold text**');

      fireEvent.click(screen.getByRole('button', { name: 'Italic text' }));
      expect(textarea.value).toContain('*italic text*');

      fireEvent.click(screen.getByRole('button', { name: 'Insert Mermaid diagram' }));
      expect(textarea.value).toContain('```mermaid\ngraph TD\n  A[Start] --> B[End]\n```');
    });

    it('fence newlines: prepends newline when start > 0 and appends trailing newline after closing fence', () => {
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      // Type some text without a newline
      fireEvent.change(textarea, { target: { value: 'existing text' } });
      textarea.setSelectionRange(13, 13);

      // Click Mermaid button
      const mermaidBtn = screen.getByRole('button', { name: 'Insert Mermaid diagram' });
      fireEvent.click(mermaidBtn);

      expect(textarea.value).toBe('existing text\n\n```mermaid\ngraph TD\n  A[Start] --> B[End]\n```\n');

      // Click Mermaid button again without cursor move: should not glue lines together
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
      fireEvent.click(mermaidBtn);

      expect(textarea.value).toBe(
        'existing text\n\n```mermaid\ngraph TD\n  A[Start] --> B[End]\n```\n\n```mermaid\ngraph TD\n  A[Start] --> B[End]\n```\n',
      );

      // Click Code button
      const codeBtn = screen.getByRole('button', { name: 'Insert code' });
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
      fireEvent.click(codeBtn);

      expect(textarea.value).toContain('```\ncode\n```\n');
      expect(textarea.value.endsWith('\n')).toBe(true);
    });

    it('clicking Mermaid button twice in a row produces two separate closed blocks and both validate and render', () => {
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
      const mermaidBtn = screen.getByRole('button', { name: 'Insert Mermaid diagram' });

      // First click: inserts first block on empty textarea, cursor lands after closing fence
      fireEvent.click(mermaidBtn);
      const expectedBlock1 = '```mermaid\ngraph TD\n  A[Start] --> B[End]\n```\n';
      expect(textarea.value).toBe(expectedBlock1);
      expect(textarea.selectionStart).toBe(expectedBlock1.length);
      expect(textarea.selectionEnd).toBe(expectedBlock1.length);

      // Second click: immediately inserts second block separated by newline
      fireEvent.click(mermaidBtn);
      const expectedBlock2 = '```mermaid\ngraph TD\n  A[Start] --> B[End]\n```\n';
      const expectedFull = `${expectedBlock1}\n${expectedBlock2}`;
      expect(textarea.value).toBe(expectedFull);
      expect(textarea.selectionStart).toBe(expectedFull.length);
      expect(textarea.selectionEnd).toBe(expectedFull.length);

      // Validate both blocks using the real Mermaid parser/validator and renderer
      const matches = Array.from(textarea.value.matchAll(/```mermaid\n([\s\S]*?)```/g));
      expect(matches).toHaveLength(2);

      for (const match of matches) {
        const diagramSource = match[1]?.trim() ?? '';
        expect(diagramSource).toBeTruthy();
        const firewallResult = sanitizeAndValidateMermaid(diagramSource);
        expect(firewallResult.ok).toBe(true);
        if (firewallResult.ok) {
          expect(firewallResult.diagramType).toBe('graph');
          expect(firewallResult.nodeCount).toBeGreaterThanOrEqual(2);
          expect(firewallResult.edgeCount).toBeGreaterThanOrEqual(1);

          // Verify with real renderer that SVG renders with 0 errors
          const rawSvg = renderMermaidSVG(firewallResult.sanitizedSource, {
            bg: '#ffffff',
            fg: '#111827',
            border: '#d1d5db',
            accent: '#1d4ed8',
            line: '#d1d5db',
            surface: '#ffffff',
            transparent: false,
          });
          expect(rawSvg).toContain('<svg');
          expect(rawSvg).toContain('Start');
          expect(rawSvg).toContain('End');
        }
      }
    });

    it('handles ApiProblem with empty message on submit', async () => {
      mockCreateComment.mockRejectedValueOnce(new ApiProblem(500, { detail: '' }));
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);

      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'Testing empty ApiProblem' } });

      const submitBtn = screen.getByRole('button', { name: 'Comment' });
      fireEvent.click(submitBtn);

      const alert = await screen.findByRole('alert');
      expect(alert.textContent).toBe('Failed to submit comment.');
    });

    it('connects tasklist, raw/preview toggle (📝) and Cmd+Shift+M shortcut', () => {
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      // Click tasklist button
      const tasklistBtn = screen.getByRole('button', { name: 'Insert tasklist' });
      fireEvent.click(tasklistBtn);
      expect(textarea.value).toContain('- [ ] task item');

      // Click Raw/Preview toggle button
      const rawBtn = screen.getByTestId('comment-tool-raw');
      fireEvent.click(rawBtn);
      expect(screen.getByTestId('comment-preview')).toBeDefined();

      // Click toggle button again to switch back
      fireEvent.click(rawBtn);
      expect(screen.getByRole('textbox', { name: 'Write a comment' })).toBeDefined();

      // Toggle via Cmd+Shift+M
      const textareaAfter = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
      fireEvent.keyDown(textareaAfter, { key: 'm', metaKey: true, shiftKey: true });
      expect(screen.getByTestId('comment-preview')).toBeDefined();
    });

    it('handles file input attachment upload, oversized file check, and upload error', async () => {
      const uploadSpy = vi
        .spyOn(autoConvertPasteMod, 'defaultUploadAttachment')
        .mockResolvedValueOnce({ markdownUri: 'attachment://comm_att_1', id: 'comm_att_1' })
        .mockRejectedValueOnce(new Error('Upload error'))
        .mockResolvedValueOnce({ markdownUri: '', id: 'fallback_att_2' });

      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const fileInput = screen.getByTestId<HTMLInputElement>('comment-file-input');
      const validFile = new File(['valid'], 'chart.png', { type: 'image/png' });

      // 1. Oversized file (>25 MB)
      const hugeFile = new File(['huge'], 'huge.png', { type: 'image/png' });
      Object.defineProperty(hugeFile, 'size', { value: 26 * 1024 * 1024 });
      fireEvent.change(fileInput, { target: { files: [hugeFile] } });
      expect(screen.getByRole('alert').textContent).toBe('Attachment exceeds 25 MB limit');

      // 2. Empty files list
      fireEvent.change(fileInput, { target: { files: [] } });

      // 3. Successful upload
      fireEvent.change(fileInput, { target: { files: [validFile] } });
      await waitFor(() => {
        expect(uploadSpy).toHaveBeenCalledTimes(1);
        const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
        expect(textarea.value).toContain('![chart.png](attachment://comm_att_1)');
      });

      // 4. Failed upload
      fireEvent.change(fileInput, { target: { files: [validFile] } });
      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe('Attachment upload failed');
      });

      // 5. Fallback URI when markdownUri is empty
      fireEvent.change(fileInput, { target: { files: [validFile] } });
      await waitFor(() => {
        const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
        expect(textarea.value).toContain('![chart.png](attachment://fallback_att_2)');
      });
      uploadSpy.mockRestore();
    });

    it('handles drag and drop for image attachments including bounds and errors', async () => {
      const uploadSpy = vi
        .spyOn(autoConvertPasteMod, 'defaultUploadAttachment')
        .mockResolvedValueOnce({ markdownUri: 'attachment://drop_1', id: 'drop_1' })
        .mockRejectedValueOnce(new Error('Network drop error'));

      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const wrapper = screen.getByRole('textbox', { name: 'Write a comment' }).parentElement ?? document.body;

      // Drag over
      fireEvent.dragOver(wrapper);

      // Empty drop
      fireEvent.drop(wrapper, { dataTransfer: { files: [] } });

      // Non-image file drop
      const txtFile = new File(['txt'], 'doc.txt', { type: 'text/plain' });
      fireEvent.drop(wrapper, { dataTransfer: { files: [txtFile] } });

      // Oversized drop
      const hugeFile = new File(['huge'], 'huge.png', { type: 'image/png' });
      Object.defineProperty(hugeFile, 'size', { value: 26 * 1024 * 1024 });
      fireEvent.drop(wrapper, { dataTransfer: { files: [hugeFile] } });
      expect(screen.getByRole('alert').textContent).toBe('Attachment exceeds 25 MB limit');

      // Valid image drop
      const validImg = new File(['img'], 'photo.png', { type: 'image/png' });
      fireEvent.drop(wrapper, { dataTransfer: { files: [validImg] } });
      await waitFor(() => {
        expect(uploadSpy).toHaveBeenCalledTimes(1);
        const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
        expect(textarea.value).toContain('![photo.png](attachment://drop_1)');
      });

      // Failed drop upload
      fireEvent.drop(wrapper, { dataTransfer: { files: [validImg] } });
      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe('Attachment upload failed');
      });
      uploadSpy.mockRestore();
    });

    it('handles clipboard paste of images and rich HTML with 1-click revert', async () => {
      const uploadSpy = vi
        .spyOn(autoConvertPasteMod, 'defaultUploadAttachment')
        .mockResolvedValueOnce({ markdownUri: 'attachment://paste_1', id: 'paste_1' })
        .mockRejectedValueOnce(new Error('Fail'));

      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      // 1. Oversized image paste
      const hugeFile = new File(['huge'], 'huge.png', { type: 'image/png' });
      Object.defineProperty(hugeFile, 'size', { value: 26 * 1024 * 1024 });
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [hugeFile],
          types: ['Files'],
          getData: () => '',
        },
      });
      expect(screen.getByRole('alert').textContent).toBe('Attachment exceeds 25 MB limit');

      // 2. Successful image paste
      const validImg = new File(['img'], 'paste.png', { type: 'image/png' });
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [validImg],
          types: ['Files'],
          getData: () => '',
        },
      });
      await waitFor(() => {
        expect(uploadSpy).toHaveBeenCalledTimes(1);
        expect(textarea.value).toContain('![paste.png](attachment://paste_1)');
      });

      // 3. Failed image paste
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [validImg],
          types: ['Files'],
          getData: () => '',
        },
      });
      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe('Attachment upload failed');
      });

      // 4. Image paste with fallback markdownUri
      uploadSpy.mockResolvedValueOnce({ markdownUri: '', id: 'paste_fallback_9' });
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [validImg],
          types: ['Files'],
          getData: () => '',
        },
      });
      await waitFor(() => {
        expect(textarea.value).toContain('![paste.png](attachment://paste_fallback_9)');
      });

      // 5. Rich HTML paste with SanitizedPastePill and 1-click revert
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [],
          types: ['text/html'],
          getData: (type: string) => (type === 'text/html' ? '<h3>Title</h3><p>Hello world</p>' : ''),
        },
      });

      const pill = await screen.findByTestId('comment-sanitized-pill');
      expect(pill).toBeDefined();
      expect(textarea.value).toContain('Title');

      // Click revert on pill
      const revertBtn = screen.getByTestId('comment-sanitized-pill-revert-btn');
      fireEvent.click(revertBtn);
      expect(screen.queryByTestId('comment-sanitized-pill')).toBeNull();

      // Dismiss pill via onDismiss
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [],
          types: ['text/html'],
          getData: (type: string) => (type === 'text/html' ? '<p>Second paste</p>' : ''),
        },
      });
      const pill2 = await screen.findByTestId('comment-sanitized-pill');
      fireEvent.keyDown(pill2, { key: 'Escape' });
      expect(screen.queryByTestId('comment-sanitized-pill')).toBeNull();
      uploadSpy.mockRestore();
    });

    it('renders ACL badge for bot/agent in mention suggestions', async () => {
      mockFetchAssigneeSuggestions.mockResolvedValueOnce({
        items: [
          { id: 'bot-1', handle: 'agent-audit', display_name: 'Audit Bot', is_agent: true },
          { id: 'usr-1', handle: 'human-dev', display_name: 'Human Dev', is_agent: false },
        ],
      });

      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: '@ag', selectionStart: 3, selectionEnd: 3 } });

      const agentOpt = await screen.findByRole('option', { name: /🤖 Agent/ });
      expect(agentOpt).toBeDefined();

      const memberOpt = await screen.findByRole('option', { name: /👤 Member/ });
      expect(memberOpt).toBeDefined();
    });

    it('renders Reply button when parentCommentId is provided, and handles suggestion fetch errors', async () => {
      // 1. Reply button
      render(<CommentComposer issueKey="KAN-142" projectKey="KAN" parentCommentId="parent-123" />);
      expect(screen.getByRole('button', { name: 'Reply' })).toBeDefined();

      // 2. Suggestion fetch error
      mockFetchAssigneeSuggestions.mockRejectedValueOnce(new Error('Network error'));
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: '@error', selectionStart: 6, selectionEnd: 6 } });
      await waitFor(() => {
        expect(mockFetchAssigneeSuggestions).toHaveBeenCalledWith('KAN', 'error');
        expect(screen.queryByRole('listbox')).toBeNull();
      });

      // 3. Non-image file paste falling through
      const nonImageFile = new File(['text content'], 'notes.txt', { type: 'text/plain' });
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [nonImageFile],
          types: ['Files'],
          getData: () => '',
        },
      });

      // 4. Empty draft preview mode
      fireEvent.change(textarea, { target: { value: '' } });
      const rawBtn = screen.getByTestId('comment-tool-raw');
      fireEvent.click(rawBtn);
      expect(screen.getByText('No comment content')).toBeDefined();
    });

    it('covers additional edge branches: tab suggestion, empty markdownUri, and submitting states', async () => {
      const uploadSpy = vi
        .spyOn(autoConvertPasteMod, 'defaultUploadAttachment')
        .mockResolvedValue({ markdownUri: '', id: 'att_fallback_9' });

      // 1. isEditing = true rendering 'Save Changes'
      render(
        <CommentComposer
          issueKey="KAN-142"
          projectKey="KAN"
          isEditing={true}
          commentId="c-1"
          initialValue="Editing text"
        />,
      );
      expect(screen.getByRole('button', { name: 'Save Changes' })).toBeDefined();

      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      // 2. Drop with empty markdownUri
      const validImg = new File(['img'], 'drop_test.png', { type: 'image/png' });
      fireEvent.drop(textarea.parentElement ?? textarea, { dataTransfer: { files: [validImg] } });
      await waitFor(() => {
        expect(textarea.value).toContain('![drop_test.png](attachment://att_fallback_9)');
      });

      // 3. Paste image with empty markdownUri
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [validImg],
          types: ['Files'],
          getData: () => '',
        },
      });
      await waitFor(() => {
        expect(textarea.value).toContain('![drop_test.png](attachment://att_fallback_9)');
      });

      // 4. Paste with empty files list
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [],
          types: [],
          getData: () => '',
        },
      });

      // 5. Paste whitespace-only HTML
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [],
          types: ['text/html'],
          getData: (type: string) => (type === 'text/html' ? '   ' : ''),
        },
      });

      // 6. Suggestion selection with Tab key and enter without chosen
      mockFetchAssigneeSuggestions.mockResolvedValueOnce({
        items: [
          { id: 'u1', display_name: 'Alice', is_agent: false, handle: 'alice' },
        ],
      });
      fireEvent.change(textarea, { target: { value: '@al', selectionStart: 3, selectionEnd: 3 } });
      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeDefined();
      });

      // Tab selects active suggestion
      fireEvent.keyDown(textarea, { key: 'Tab' });
      expect(textarea.value).toContain('@alice ');

      // Enter without modifier key when no suggestions
      fireEvent.keyDown(textarea, { key: 'Enter' });

      // Shortcut with metaKey vs ctrlKey
      fireEvent.keyDown(textarea, { key: 'm', metaKey: true, shiftKey: true });
      expect(screen.getByTestId('comment-preview')).toBeDefined();
      fireEvent.click(screen.getByTestId('comment-tool-raw'));
      expect(screen.queryByTestId('comment-preview')).toBeNull();

      // Suggestion navigation with invalid chosen idx
      const freshTextarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
      mockFetchAssigneeSuggestions.mockResolvedValueOnce({
        items: [
          { id: 'u2', display_name: 'Bob', is_agent: false, handle: 'bob' },
        ],
      });
      fireEvent.change(freshTextarea, { target: { value: '@bo', selectionStart: 3, selectionEnd: 3 } });
      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeDefined();
      });
      // Fire keydown with key other than arrows/enter/tab/escape
      fireEvent.keyDown(freshTextarea, { key: 'Space' });
      // Clear suggestions via typing empty prefix
      fireEvent.change(freshTextarea, { target: { value: 'plain', selectionStart: 5, selectionEnd: 5 } });

      // 7. Submitting state (Saving...)
      let resolveSubmit!: (v: unknown) => void;
      const pendingSubmit = new Promise((resolve) => {
        resolveSubmit = resolve;
      });
      mockCreateComment.mockReturnValue(pendingSubmit as unknown as Promise<activityApi.CommentResponse>);

      fireEvent.change(freshTextarea, { target: { value: 'New content to save' } });
      fireEvent.keyDown(freshTextarea, { key: 'Enter', ctrlKey: true });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Saving...' })).toBeDefined();
      });

      resolveSubmit({ id: 'c-new', body: 'New content to save' });

      // 8. ApiProblem with other status code (400)
      fireEvent.change(freshTextarea, { target: { value: 'Content for error test' } });
      mockPatchComment.mockRejectedValueOnce(new ApiProblem(400, { detail: 'Bad request' }));
      fireEvent.keyDown(freshTextarea, { key: 'Enter', ctrlKey: true });
      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe('Bad request');
      });

      fireEvent.change(freshTextarea, { target: { value: 'Content for empty error' } });
      mockPatchComment.mockRejectedValueOnce(new Error(''));
      fireEvent.keyDown(freshTextarea, { key: 'Enter', ctrlKey: true });
      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe('Failed to submit comment.');
      });

      uploadSpy.mockRestore();
    });
  });
});
