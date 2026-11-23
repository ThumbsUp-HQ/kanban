import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { CommentEditor } from '../CommentEditor';
import * as activityApi from '../../activity/activityApi';

vi.mock('../../activity/activityApi', async () => {
  const actual = await vi.importActual<typeof import('../../activity/activityApi')>(
    '../../activity/activityApi',
  );
  return {
    ...actual,
    createComment: vi.fn(),
    patchComment: vi.fn(),
    fetchAssigneeSuggestions: vi.fn(),
  };
});

describe('CommentEditorMobile (KAN-345)', () => {
  const mockCreateComment = vi.mocked(activityApi.createComment);
  const originalInnerWidth = window.innerWidth;
  const originalVisualViewport = window.visualViewport;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    window.innerWidth = originalInnerWidth;
    Object.defineProperty(window, 'visualViewport', {
      value: originalVisualViewport,
      writable: true,
      configurable: true,
    });
  });

  it('Case 1 (Positive): mobile toolbar collapses secondary buttons into overflow menu when width <= 480px', () => {
    // 1. Simulate mobile viewport <= 480px
    window.innerWidth = 390;

    render(<CommentEditor issueKey="KAN-142" projectKey="KAN" />);

    // Primary formatting actions remain immediately visible and accessible
    expect(screen.getByRole('button', { name: 'Bold text' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Italic text' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Insert tasklist' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Insert link' })).toBeDefined();

    // Secondary formatting buttons are collapsed and not directly visible in toolbar
    expect(screen.queryByRole('button', { name: 'Insert code' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Insert table' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Insert Mermaid diagram' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Attach media, SVG, or PDF' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Raw markdown source view' })).toBeNull();

    // The overflow toggle button is present
    const overflowBtn = screen.getByRole('button', { name: 'More formatting options' });
    expect(overflowBtn).toBeDefined();
    expect(overflowBtn.getAttribute('aria-expanded')).toBe('false');

    // Click overflow button to open menu
    fireEvent.click(overflowBtn);
    expect(overflowBtn.getAttribute('aria-expanded')).toBe('true');

    const overflowMenu = screen.getByRole('menu', { name: 'More formatting options' });
    expect(overflowMenu).toBeDefined();

    // Secondary items are now present inside the overflow menu
    const codeMenuItem = screen.getByRole('menuitem', { name: 'Insert code' });
    const tableMenuItem = screen.getByRole('menuitem', { name: 'Insert table' });
    const attachMenuItem = screen.getByRole('menuitem', { name: 'Attach media, SVG, or PDF' });
    const mermaidMenuItem = screen.getByRole('menuitem', { name: 'Insert Mermaid diagram' });
    const previewMenuItem = screen.getByRole('menuitem', { name: 'Raw markdown source view' });

    expect(codeMenuItem).toBeDefined();
    expect(tableMenuItem).toBeDefined();
    expect(attachMenuItem).toBeDefined();
    expect(mermaidMenuItem).toBeDefined();
    expect(previewMenuItem).toBeDefined();

    // Clicking an item inserts markdown template and closes the overflow menu
    fireEvent.click(tableMenuItem);
    const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
    expect(textarea.value).toContain('| Column 1 | Column 2 |');
    expect(screen.queryByRole('menu', { name: 'More formatting options' })).toBeNull();

    // Resize viewport to desktop (> 480px) and verify full toolbar expands
    act(() => {
      window.innerWidth = 1024;
      fireEvent(window, new Event('resize'));
    });

    expect(screen.getByRole('button', { name: 'Insert code' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Insert table' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Insert Mermaid diagram' })).toBeDefined();
    expect(screen.queryByRole('button', { name: 'More formatting options' })).toBeNull();
  });

  it('Case 2 (Negative): editor does not scroll out of view when focused on mobile', () => {
    window.innerWidth = 390;

    // Mock scrollIntoView to verify element positioning
    const scrollIntoViewMock = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoViewMock;

    // Mock window.visualViewport to simulate mobile virtual keyboard popup
    const listeners: Record<string, (() => void)[]> = {};
    const mockVisualViewport = {
      height: 400,
      width: 390,
      offsetTop: 0,
      offsetLeft: 0,
      pageTop: 0,
      pageLeft: 0,
      scale: 1,
      addEventListener: vi.fn((event: string, cb: () => void) => {
        const bucket = listeners[event] ?? [];
        bucket.push(cb);
        listeners[event] = bucket;
      }),
      removeEventListener: vi.fn((event: string, cb: () => void) => {
        if (listeners[event]) {
          listeners[event] = listeners[event].filter((fn) => fn !== cb);
        }
      }),
    };

    Object.defineProperty(window, 'visualViewport', {
      value: mockVisualViewport,
      writable: true,
      configurable: true,
    });

    render(<CommentEditor issueKey="KAN-142" projectKey="KAN" />);

    // Simulate virtual keyboard appearance by shrinking visualViewport
    act(() => {
      mockVisualViewport.height = 360;
      listeners.resize?.forEach((fn) => { fn(); });
      listeners.scroll?.forEach((fn) => { fn(); });
    });

    const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });

    // Focus the textarea as the user starts typing
    fireEvent.focus(textarea);

    // Verify scrollIntoView was called to keep composer within visible viewport
    expect(scrollIntoViewMock).toHaveBeenCalledWith({
      block: 'nearest',
      behavior: 'smooth',
    });

    // Negative verification: editor container is NOT hidden, displaced, or unmounted
    expect(document.body.contains(textarea)).toBe(true);
    const composer = screen.getByTestId('comment-composer');
    expect(composer).toBeDefined();
    expect(document.body.contains(composer)).toBe(true);
  });

  it('Case 3 (Boundary): comment submit button is disabled during submission and maintains touch target bounds', async () => {
    window.innerWidth = 390;

    let resolveSubmission: ((val: activityApi.CommentResponse) => void) | undefined;
    const submissionPromise = new Promise<activityApi.CommentResponse>((resolve) => {
      resolveSubmission = resolve;
    });
    mockCreateComment.mockReturnValueOnce(submissionPromise);

    const onCancel = vi.fn();
    render(<CommentEditor issueKey="KAN-142" projectKey="KAN" onCancel={onCancel} />);

    const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
    fireEvent.change(textarea, { target: { value: 'Mobile test comment' } });

    const submitBtn = screen.getByRole<HTMLButtonElement>('button', { name: 'Comment' });
    const cancelBtn = screen.getByRole<HTMLButtonElement>('button', { name: 'Cancel' });

    // Prior to submission: buttons are enabled and maintain touch target class
    expect(submitBtn.disabled).toBe(false);
    expect(cancelBtn.disabled).toBe(false);
    expect(submitBtn.className).toContain('composer-submit-btn');
    expect(cancelBtn.className).toContain('composer-cancel-btn');

    // Trigger submission
    fireEvent.click(submitBtn);

    // During submission: boundary verification
    expect(submitBtn.disabled).toBe(true);
    expect(cancelBtn.disabled).toBe(true);
    expect(submitBtn.textContent).toBe('Saving...');
    expect(submitBtn.className).toContain('composer-submit-btn');

    // Resolve submission
    act(() => {
      resolveSubmission?.({
        id: 'c-new',
        issue_id: 'i-1',
        author: {
          id: 'u-1',
          display_name: 'Adam Outler',
          handle: 'adam',
        },
        body_markdown: 'Mobile test comment',
        created_at: new Date().toISOString(),
        deleted: false,
        reactions: [],
      });
    });

    await waitFor(() => {
      expect(submitBtn.disabled).toBe(false);
      expect(textarea.value).toBe('');
    });
  });

  it('covers overflow menu interactions: code, mermaid, attach, preview, and click outside dismissal', () => {
    window.innerWidth = 360;

    render(<CommentEditor issueKey="KAN-142" projectKey="KAN" />);

    const overflowBtn = screen.getByRole('button', { name: 'More formatting options' });

    // 1. Insert code
    fireEvent.click(overflowBtn);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Insert code' }));
    const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Write a comment' });
    expect(textarea.value).toContain('```');

    // 2. Insert mermaid
    fireEvent.click(overflowBtn);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Insert Mermaid diagram' }));
    expect(textarea.value).toContain('```mermaid');

    // 3. Attach file trigger
    fireEvent.click(overflowBtn);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Attach media, SVG, or PDF' }));
    expect(screen.queryByRole('menu', { name: 'More formatting options' })).toBeNull();

    // 4. Raw preview toggle
    fireEvent.click(overflowBtn);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Raw markdown source view' }));
    expect(screen.getByTestId('comment-preview')).toBeDefined();

    // 5. Dismiss overflow by clicking outside
    fireEvent.click(overflowBtn);
    expect(screen.getByRole('menu', { name: 'More formatting options' })).toBeDefined();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('menu', { name: 'More formatting options' })).toBeNull();
  });
});
