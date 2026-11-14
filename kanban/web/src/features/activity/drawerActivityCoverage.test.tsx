import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  formatActorName,
  formatEventSummary,
  ActivityEventRow,
} from './ActivityEventRow';
import {
  CommentComposer,
  isCursorInsideCode,
  extractMentionPrefix,
} from './CommentComposer';
import { ActivitySection } from './ActivitySection';
import { CommentCard } from './CommentCard';
import {
  SafeMarkdownPreview,
  renderInlineContent,
  registerCommentBodyRenderer,
} from './SafeMarkdownPreview';
import type { ActivityItem } from './activityApi';
import * as activityApi from './activityApi';
import { ApiProblem } from '../../api/problem';

vi.mock('./activityApi', async () => {
  const actual = await vi.importActual<typeof import('./activityApi')>('./activityApi');
  return {
    ...actual,
    createComment: vi.fn(),
    patchComment: vi.fn(),
    deleteComment: vi.fn(),
    addReaction: vi.fn(),
    removeReaction: vi.fn(),
    fetchActivity: vi.fn(),
    fetchComments: vi.fn(),
    fetchAssigneeSuggestions: vi.fn(),
  };
});

describe('Branch Coverage Booster', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    registerCommentBodyRenderer(null);
  });

  describe('ActivityEventRow Branches', () => {
    it('covers all formatActorName branches', () => {
      // Redacted without label
      expect(formatActorName({ redacted: true })).toBe('1 External Collaborator');
      // Redacted with label
      expect(formatActorName({ redacted: true, label: 'Custom' })).toBe('Custom');
      // Agent with display_name
      expect(formatActorName({ type: 'AGENT', display_name: 'Bot' })).toBe('Bot');
      // Agent with slug only
      expect(formatActorName({ type: 'AGENT', slug: 'sluggy' })).toBe('sluggy');
      // Agent with neither
      expect(formatActorName({ type: 'AGENT' })).toBe('Agent');
      // User with handle
      expect(formatActorName({ handle: '@john' })).toBe('@john');
      expect(formatActorName({ handle: 'john' })).toBe('@john');
      // User with display_name only
      expect(formatActorName({ display_name: 'John Doe' })).toBe('John Doe');
      // User with nothing
      expect(formatActorName({})).toBe('System');
    });

    it('covers formatEventSummary branches with empty, non-string, or alternative keys', () => {
      expect(
        formatEventSummary({
          id: '1',
          event_type: 'CREATOR_OVERRIDDEN',
          actor: {},
          payload: {},
          created_at: '',
        }),
      ).toBe('Creator overridden: Unknown -> Unknown');

      expect(
        formatEventSummary({
          id: '2',
          event_type: 'STATE_CHANGED',
          actor: {},
          payload: { from_state: 123, to_state: null },
          created_at: '',
        }),
      ).toBe('changed State from  to ');

      expect(
        formatEventSummary({
          id: '3',
          event_type: 'PRIORITY_CHANGED',
          actor: {},
          payload: { from_priority: true, to_priority: false },
          created_at: '',
        }),
      ).toBe('changed Priority from  to ');

      expect(
        formatEventSummary({
          id: '4',
          event_type: 'ASSIGNEE_ADDED',
          actor: {},
          payload: { assignee_name: 'Sarah' },
          created_at: '',
        }),
      ).toBe('assigned Sarah');

      expect(
        formatEventSummary({
          id: '5',
          event_type: 'ASSIGNEE_REMOVED',
          actor: {},
          payload: { assignee_handle: '@sarah' },
          created_at: '',
        }),
      ).toBe('unassigned @sarah');

      expect(
        formatEventSummary({
          id: '6',
          event_type: 'LABEL_ADDED',
          actor: {},
          payload: {},
          created_at: '',
        }),
      ).toBe('added label ');

      expect(
        formatEventSummary({
          id: '7',
          event_type: 'LABEL_REMOVED',
          actor: {},
          payload: {},
          created_at: '',
        }),
      ).toBe('removed label ');

      expect(
        formatEventSummary({
          id: '8',
          event_type: 'GATE_PENDING',
          actor: {},
          payload: {},
          created_at: '',
        }),
      ).toBe('Transition gate pending: ');

      expect(
        formatEventSummary({
          id: '9',
          event_type: 'GATE_APPROVED',
          actor: {},
          payload: {},
          created_at: '',
        }),
      ).toBe('Transition gate approved: ');

      expect(
        formatEventSummary({
          id: '10',
          event_type: 'GATE_VETOED',
          actor: {},
          payload: {},
          created_at: '',
        }),
      ).toBe('Transition gate vetoed: ');
    });

    it('covers ActivityEventRow jump button in tooltip when onJumpToComment is called', () => {
      const onJumpToComment = vi.fn();
      const vetoItem: ActivityItem = {
        id: 'v1',
        event_type: 'GATE_VETOED',
        actor: { type: 'AGENT', display_name: 'Gate' },
        payload: {
          hook_name: 'qa-gate',
          audit_comment_id: 'comm-99',
        },
        created_at: '2026-11-12T10:00:00Z',
      };

      render(<ActivityEventRow item={vetoItem} onJumpToComment={onJumpToComment} />);
      const trigger = screen.getByRole('button', { name: 'Gate Vetoed: qa-gate' });
      fireEvent.focus(trigger);

      const jumpTooltipBtn = document.querySelector('.gate-tooltip__jump-btn');
      expect(jumpTooltipBtn).not.toBeNull();
      if (jumpTooltipBtn) {
        fireEvent.click(jumpTooltipBtn);
      }
      expect(onJumpToComment).toHaveBeenCalledWith('comm-99');
    });
  });

  describe('CommentComposer Branches', () => {
    it('covers isCursorInsideCode edge cases', () => {
      // Even backticks inside code
      expect(isCursorInsideCode('`a` outside `b`', 5)).toBe(false);
      expect(isCursorInsideCode('`a` outside `b', 14)).toBe(true);
      // Multi-line code block
      const multi = '```\nline 1\nline 2\n```\noutside';
      expect(isCursorInsideCode(multi, 8)).toBe(true);
      expect(isCursorInsideCode(multi, 25)).toBe(false);
    });

    it('covers extractMentionPrefix boundaries', () => {
      expect(extractMentionPrefix('@', 1)).toBe('');
      expect(extractMentionPrefix('@user-name_1', 12)).toBe('user-name_1');
      expect(extractMentionPrefix('email@domain.com', 8)).toBeNull();
    });

    it('covers Ctrl+Enter submission shortcut', async () => {
      const mockCreate = vi.mocked(activityApi.createComment);
      mockCreate.mockResolvedValueOnce({
        id: 'c1',
        issue_id: 'i1',
        author: { id: 'u1' },
        body_markdown: 'Ctrl enter text',
        reactions: [],
        created_at: '',
        deleted: false,
      });

      render(<CommentComposer issueKey="KAN-1" projectKey="KAN" />);
      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'Ctrl enter text' } });
      fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true });

      await waitFor(() => {
        expect(mockCreate).toHaveBeenCalled();
      });
    });

    it('covers text selection wrapping in insertTextAtCursor', () => {
      render(<CommentComposer issueKey="KAN-1" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      // Type text and select "world"
      fireEvent.change(textarea, { target: { value: 'Hello world today' } });
      textarea.setSelectionRange(6, 11);

      const boldBtn = screen.getByRole('button', { name: 'Bold text' });
      fireEvent.click(boldBtn);

      expect(textarea.value).toBe('Hello **world** today');
    });

    it('handles suggestion fetch failure gracefully by clearing suggestions', async () => {
      const mockSuggestions = vi.mocked(activityApi.fetchAssigneeSuggestions);
      mockSuggestions.mockRejectedValueOnce(new Error('Suggestions endpoint down'));

      render(<CommentComposer issueKey="KAN-1" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      fireEvent.change(textarea, { target: { value: 'Hey @fail', selectionStart: 8, selectionEnd: 8 } });
      await waitFor(() => {
        expect(mockSuggestions).toHaveBeenCalled();
      });
      expect(screen.queryByRole('listbox')).toBeNull();
    });

    it('handles ApiProblem with 500 status code', async () => {
      const mockCreate = vi.mocked(activityApi.createComment);
      mockCreate.mockRejectedValueOnce(new ApiProblem(500, { detail: 'Internal failure' }));

      render(<CommentComposer issueKey="KAN-1" projectKey="KAN" />);
      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'A comment' } });

      const submitBtn = screen.getByRole('button', { name: 'Comment' });
      fireEvent.click(submitBtn);

      const alert = await screen.findByRole('alert');
      expect(alert.textContent).toBe('Internal failure');
    });

    it('selects suggestion with Tab key and renders agent emoji for agent suggestions', async () => {
      const mockSuggestions = vi.mocked(activityApi.fetchAssigneeSuggestions);
      mockSuggestions.mockResolvedValueOnce({
        items: [
          { id: 'ag-1', handle: 'review-bot', display_name: 'Code Reviewer', is_agent: true },
        ],
      });

      render(<CommentComposer issueKey="KAN-1" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      fireEvent.change(textarea, { target: { value: 'cc @rev', selectionStart: 7, selectionEnd: 7 } });

      const option = await screen.findByRole('option', { name: /review-bot/ });
      expect(option.textContent).toContain('🤖');

      // Press Tab to select
      fireEvent.keyDown(textarea, { key: 'Tab' });
      await waitFor(() => {
        expect(textarea.value).toBe('cc @review-bot ');
      });
    });

    it('handles ApiProblem with empty message', async () => {
      const mockCreate = vi.mocked(activityApi.createComment);
      const err = new ApiProblem(400, {});
      Object.defineProperty(err, 'message', { value: '' });
      mockCreate.mockRejectedValueOnce(err);

      render(<CommentComposer issueKey="KAN-1" projectKey="KAN" />);
      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'Something' } });

      const submitBtn = screen.getByRole('button', { name: 'Comment' });
      fireEvent.click(submitBtn);

      const alert = await screen.findByRole('alert');
      expect(alert.textContent).toBe('Failed to submit comment.');
    });

    it('covers Escape key to dismiss suggestions and keyboard navigation ArrowUp/ArrowDown', async () => {
      const mockSuggestions = vi.mocked(activityApi.fetchAssigneeSuggestions);
      mockSuggestions.mockResolvedValueOnce({
        items: [
          { id: 'u1', handle: 'alice', display_name: 'Alice', is_agent: false },
          { id: 'u2', handle: '@bob', display_name: 'Bob', is_agent: false },
        ],
      });

      render(<CommentComposer issueKey="KAN-1" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      fireEvent.change(textarea, { target: { value: 'Hi @', selectionStart: 4, selectionEnd: 4 } });

      const listbox = await screen.findByRole('listbox');
      expect(listbox).not.toBeNull();

      // ArrowDown moves selection
      fireEvent.keyDown(textarea, { key: 'ArrowDown' });
      // ArrowUp moves selection back
      fireEvent.keyDown(textarea, { key: 'ArrowUp' });

      // Escape dismisses
      fireEvent.keyDown(textarea, { key: 'Escape' });
      expect(screen.queryByRole('listbox')).toBeNull();
    });

    it('covers applyMention with leading @ in handle and Meta+Enter submission shortcut', async () => {
      const mockSuggestions = vi.mocked(activityApi.fetchAssigneeSuggestions);
      mockSuggestions.mockResolvedValueOnce({
        items: [
          { id: 'u2', handle: '@bob', display_name: 'Bob', is_agent: false },
        ],
      });

      const mockCreate = vi.mocked(activityApi.createComment);
      mockCreate.mockResolvedValueOnce({
        id: 'c2',
        issue_id: 'i1',
        author: { id: 'u1' },
        body_markdown: 'Hi @bob ',
        reactions: [],
        created_at: '',
        deleted: false,
      });

      render(<CommentComposer issueKey="KAN-1" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      fireEvent.change(textarea, { target: { value: 'Hi @b', selectionStart: 5, selectionEnd: 5 } });
      const option = await screen.findByRole('option', { name: /@bob/ });
      expect(option).not.toBeNull();

      // Press Enter to select suggestion
      fireEvent.keyDown(textarea, { key: 'Enter' });
      await waitFor(() => {
        expect(textarea.value).toBe('Hi @bob ');
      });

      // Submit with Meta+Enter
      fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true });
      await waitFor(() => {
        expect(mockCreate).toHaveBeenCalled();
      });
    });

    it('clicks a mention suggestion to apply mention', async () => {
      const mockSuggestions = vi.mocked(activityApi.fetchAssigneeSuggestions);
      mockSuggestions.mockResolvedValueOnce({
        items: [
          { id: 'u1', handle: 'carol', display_name: 'Carol', is_agent: false },
        ],
      });

      render(<CommentComposer issueKey="KAN-1" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      fireEvent.change(textarea, { target: { value: '@car', selectionStart: 4, selectionEnd: 4 } });
      const optionBtn = await screen.findByRole('option', { name: /carol/ });
      fireEvent.mouseDown(optionBtn);

      await waitFor(() => {
        expect(textarea.value).toBe('@carol ');
      });
    });

    it('ignores normal Enter without modifier keys and falls through non-nav keys while suggestions open', async () => {
      const mockSuggestions = vi.mocked(activityApi.fetchAssigneeSuggestions);
      mockSuggestions.mockResolvedValueOnce({
        items: [
          { id: 'u1', handle: 'alice', display_name: 'Alice', is_agent: false },
        ],
      });

      render(<CommentComposer issueKey="KAN-1" projectKey="KAN" />);
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

      // Type @ to open suggestions
      fireEvent.change(textarea, { target: { value: '@', selectionStart: 1, selectionEnd: 1 } });
      await screen.findByRole('listbox');

      // Regular character key while suggestions open falls through
      fireEvent.keyDown(textarea, { key: 'x' });
      expect(screen.getByRole('listbox')).not.toBeNull();

      // Normal Enter when suggestions are closed
      fireEvent.keyDown(textarea, { key: 'Escape' });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      // Should not submit
      expect(activityApi.createComment).not.toHaveBeenCalled();
    });

    it('handles generic non-ApiProblem error with empty message', async () => {
      const mockCreate = vi.mocked(activityApi.createComment);
      mockCreate.mockRejectedValueOnce(new Error(''));

      render(<CommentComposer issueKey="KAN-1" projectKey="KAN" />);
      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'Something' } });

      const submitBtn = screen.getByRole('button', { name: 'Comment' });
      fireEvent.click(submitBtn);

      const alert = await screen.findByRole('alert');
      expect(alert.textContent).toBe('Failed to submit comment.');
    });
  });

  describe('ActivitySection Branches', () => {
    it('covers keyboard navigation wrapping: ArrowLeft from 0 wraps to 3', async () => {
      const mockFetch = vi.mocked(activityApi.fetchActivity);
      mockFetch.mockResolvedValue({
        items: [],
        next_cursor: null,
        counts: { all: 0, comments: 0, history: 0, gates: 0 },
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <ActivitySection
              issue={{
                key: 'KAN-1',
                object_id: '1',
                project_key: 'KAN',
                project_name: 'P',
                summary: 'S',
              }}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const allTab = await screen.findByRole('tab', { name: 'All' });
      allTab.focus();

      // ArrowLeft wraps to Gates tab
      fireEvent.keyDown(allTab, { key: 'ArrowLeft' });
      const gatesTab = screen.getByRole('tab', { name: /^Agent and workflow gates/ });
      expect(gatesTab.getAttribute('aria-selected')).toBe('true');
    });

    it('covers ActivitySection handleJumpToComment with element found in DOM', async () => {
      const mockFetch = vi.mocked(activityApi.fetchActivity);
      mockFetch.mockResolvedValue({
        items: [
          {
            id: 'gate-v',
            category: 'AGENT_GATE',
            event_type: 'GATE_VETOED',
            actor: { type: 'AGENT' },
            payload: {
              hook_name: 'test-veto',
              audit_comment_id: 'target-comm',
            },
            created_at: '',
          },
        ],
        next_cursor: null,
        counts: { all: 1, comments: 0, history: 0, gates: 1 },
      });

      const scrollIntoViewMock = vi.fn();
      const dummyEl = document.createElement('div');
      dummyEl.id = 'comment-target-comm';
      dummyEl.scrollIntoView = scrollIntoViewMock;
      document.body.appendChild(dummyEl);

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <ActivitySection
              issue={{
                key: 'KAN-1',
                object_id: '1',
                project_key: 'KAN',
                project_name: 'P',
                summary: 'S',
              }}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Select gates tab
      const gatesTab = await screen.findByRole('tab', { name: /^Agent and workflow gates/ });
      fireEvent.click(gatesTab);

      // Click jump button
      const jumpBtn = await screen.findByRole('button', { name: 'View audit details' });
      fireEvent.click(jumpBtn);

      await waitFor(() => {
        expect(scrollIntoViewMock).toHaveBeenCalled();
      });

      document.body.removeChild(dummyEl);
    });

    it('triggers handleRefresh on history tab without refetching comments', async () => {
      const mockFetch = vi.mocked(activityApi.fetchActivity);
      mockFetch.mockResolvedValue({
        items: [
          {
            id: 'h1',
            category: 'HISTORY',
            event_type: 'STATE_CHANGED',
            actor: { handle: 'alice' },
            created_at: '',
          },
          {
            id: 'g1',
            category: 'AGENT_GATE',
            event_type: 'GATE_APPROVED',
            actor: { handle: 'gate' },
            created_at: '',
          },
        ],
        next_cursor: null,
        counts: { all: 2, comments: 0, history: 1, gates: 1 },
      });

      const mockComments = vi.mocked(activityApi.fetchComments);
      mockComments.mockResolvedValue({ items: [], next_cursor: null });

      const mockCreate = vi.mocked(activityApi.createComment);
      mockCreate.mockResolvedValueOnce({
        id: 'new-c',
        issue_id: '1',
        author: { id: 'u1' },
        body_markdown: 'Hist comment',
        reactions: [],
        created_at: '',
        deleted: false,
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <ActivitySection
              issue={{
                key: 'KAN-1',
                object_id: '1',
                project_key: 'KAN',
                project_name: 'P',
                summary: 'S',
              }}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Select history tab
      const historyTab = await screen.findByRole('tab', { name: 'History' });
      fireEvent.click(historyTab);

      // Submit comment from composer
      const textarea = screen.getByRole('textbox', { name: 'Write a comment' });
      fireEvent.change(textarea, { target: { value: 'Hist comment' } });

      const submitBtn = screen.getByRole('button', { name: 'Comment' });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(mockCreate).toHaveBeenCalled();
      });
    });
  });

  describe('CommentCard Branches', () => {
    it('renders (edited) badge when comment.edited_at is present', () => {
      render(
        <MemoryRouter>
          <CommentCard
            comment={{
              id: 'c-edit-1',
              issue_id: 'i1',
              author: { id: 'u1', handle: 'alice', display_name: 'Alice' },
              body_markdown: 'Edited text',
              reactions: [],
              created_at: '2026-11-12T10:00:00Z',
              edited_at: '2026-11-12T11:00:00Z',
              deleted: false,
            }}
            issueKey="KAN-1"
            projectKey="KAN"
          />
        </MemoryRouter>,
      );
      expect(screen.getByText('(edited)')).not.toBeNull();
    });

    it('enters inline edit mode, renders composer and handles cancel', () => {
      render(
        <MemoryRouter>
          <CommentCard
            comment={{
              id: 'c-edit-2',
              issue_id: 'i1',
              author: { id: 'u1', handle: 'alice', display_name: 'Alice' },
              body_markdown: 'My comment to edit',
              reactions: [],
              created_at: '2026-11-12T10:00:00Z',
              deleted: false,
            }}
            currentUserId="u1"
            issueKey="KAN-1"
            projectKey="KAN"
          />
        </MemoryRouter>,
      );

      const editBtn = screen.getByRole('button', { name: 'Edit' });
      fireEvent.click(editBtn);

      // Composer should be open with Cancel button
      const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
      expect(cancelBtn).not.toBeNull();

      fireEvent.click(cancelBtn);
      // Cancelled, composer is closed
      expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
    });

    it('renders comment with null or empty body_markdown gracefully', () => {
      render(
        <MemoryRouter>
          <CommentCard
            comment={{
              id: 'c-edit-3',
              issue_id: 'i1',
              author: { id: 'u1', handle: 'alice', display_name: 'Alice' },
              body_markdown: null,
              reactions: [],
              created_at: '2026-11-12T10:00:00Z',
              deleted: false,
            }}
            issueKey="KAN-1"
            projectKey="KAN"
          />
        </MemoryRouter>,
      );
      expect(screen.getByText('Alice')).not.toBeNull();
    });

    it('enters inline edit mode when body_markdown is undefined', () => {
      render(
        <MemoryRouter>
          <CommentCard
            comment={{
              id: 'c-edit-undef',
              issue_id: 'i1',
              author: { id: 'u1', handle: 'alice', display_name: 'Alice' },
              reactions: [],
              created_at: '2026-11-12T10:00:00Z',
              deleted: false,
            }}
            currentUserId="u1"
            issueKey="KAN-1"
            projectKey="KAN"
          />
        </MemoryRouter>,
      );
      const editBtn = screen.getByRole('button', { name: 'Edit' });
      fireEvent.click(editBtn);
      const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
      expect(cancelBtn).not.toBeNull();
    });
  });

  describe('SafeMarkdownPreview Branches', () => {
    it('handles whitespace-only lines and broken empty link syntax', () => {
      const { container } = render(<SafeMarkdownPreview markdown={"First\n   \n\nSecond\n\n[](https://foo.com) and [bar]()"} />);
      const paragraphs = container.querySelectorAll('p');
      expect(paragraphs.length).toBeGreaterThan(0);
    });

    it('renders pure italic markdown text', () => {
      const { container } = render(<SafeMarkdownPreview markdown="*pure italic text*" />);
      const em = container.querySelector('em');
      expect(em).not.toBeNull();
      expect(em?.textContent).toBe('pure italic text');
    });

    it('handles multiple blank lines between paragraphs gracefully', () => {
      const { container } = render(<SafeMarkdownPreview markdown={"First paragraph\n\n\n\nSecond paragraph"} />);
      const paragraphs = container.querySelectorAll('p');
      expect(paragraphs.length).toBe(2);
    });

    it('renders unclosed fenced code block without language at EOF', () => {
      const { container } = render(<SafeMarkdownPreview markdown={"```\nplain unclosed code"} />);
      const preCode = container.querySelector('pre code');
      expect(preCode).not.toBeNull();
      expect(preCode?.className).toBe('');
      expect(preCode?.textContent).toContain('plain unclosed code');
    });

    it('renders inline fallback content when no pattern matches', () => {
      const nodes = renderInlineContent('Just plain simple text', 'test');
      expect(nodes.length).toBeGreaterThan(0);
      expect(nodes[0]).toBe('Just plain simple text');
    });

    it('renders unclosed fenced code block at EOF', () => {
      const { container } = render(<SafeMarkdownPreview markdown={"```js\nconst unclosed = true;"} />);
      const preCode = container.querySelector('pre code');
      expect(preCode).not.toBeNull();
      expect(preCode?.textContent).toContain('const unclosed = true;');
    });

    it('renders fenced code block without language', () => {
      const { container } = render(<SafeMarkdownPreview markdown={"```\nplain text code\n```"} />);
      const code = container.querySelector('code');
      expect(code).not.toBeNull();
      expect(code?.className).toBe('');
      expect(code?.textContent).toContain('plain text code');
    });
  });
});
