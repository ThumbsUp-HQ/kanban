import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React, { useRef } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  SummaryField,
  sanitizeSummary,
  getCodePointLength,
} from './SummaryField';
import type { IssueDetail } from './slots';
import { apiClient } from '../../api/client';
import { ApiProblem } from '../../api/problem';

const mockIssue: IssueDetail = {
  key: 'KAN-142',
  object_id: '11111111-1111-1111-1111-111111111111',
  project_key: 'KAN',
  project_name: 'kanban',
  summary: 'Original Summary',
  etag: '"etag-123"',
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, Wrapper };
}

describe('SummaryField', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('sanitizeSummary and getCodePointLength', () => {
    it('replaces newlines and C0/C1 control characters with single space', () => {
      expect(sanitizeSummary('a\nb\u0007c')).toBe('a b c');
      expect(sanitizeSummary('line1\r\nline2\tline3')).toBe('line1 line2 line3');
      expect(sanitizeSummary('hello\u001Fworld')).toBe('hello world');
    });

    it('counts code points correctly including surrogate pairs / 4-byte emoji', () => {
      expect(getCodePointLength('hello')).toBe(5);
      expect(getCodePointLength('🔥')).toBe(1);
      expect(getCodePointLength('👨‍👩‍👧‍👦')).toBe(7); // composite emoji code points
      expect(getCodePointLength('  test  ')).toBe(4); // trimmed
    });
  });

  describe('Required Test Case 4: Boundary & keyboard behavior', () => {
    it('commits valid 500 code point string including 4-byte emoji', async () => {
      const { Wrapper } = createWrapper();
      const patchSpy = vi.spyOn(apiClient, 'patch').mockResolvedValueOnce({
        ...mockIssue,
        summary: 'a'.repeat(499) + '🔥',
      });

      render(<SummaryField issue={mockIssue} />, { wrapper: Wrapper });

      const editBtn = screen.getByRole('button', { name: 'Edit summary' });
      fireEvent.click(editBtn);

      const textarea = screen.getByRole('textbox', { name: 'Summary' });
      const valid500 = 'a'.repeat(499) + '🔥';
      fireEvent.change(textarea, { target: { value: valid500 } });

      fireEvent.keyDown(textarea, { key: 'Enter' });

      await waitFor(() => {
        expect(patchSpy).toHaveBeenCalledWith(
          '/api/v1/issues/{issue_key}',
          expect.objectContaining({
            params: { issue_key: 'KAN-142' },
            body: { summary: valid500 },
          }),
        );
      });
    });

    it('shows inline alert when string exceeds 500 code points and blocks commit', () => {
      const { Wrapper } = createWrapper();
      const patchSpy = vi.spyOn(apiClient, 'patch');

      render(<SummaryField issue={mockIssue} />, { wrapper: Wrapper });

      fireEvent.click(screen.getByRole('button', { name: 'Edit summary' }));
      const textarea = screen.getByRole('textbox', { name: 'Summary' });

      const invalid501 = 'a'.repeat(501);
      fireEvent.change(textarea, { target: { value: invalid501 } });

      const alert = screen.getByRole('alert');
      expect(alert.textContent).toBe('Summary must be 500 characters or fewer (currently 501).');

      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(patchSpy).not.toHaveBeenCalled();
    });

    it('shows inline alert when input is whitespace-only and blocks commit', () => {
      const { Wrapper } = createWrapper();
      const patchSpy = vi.spyOn(apiClient, 'patch');

      render(<SummaryField issue={mockIssue} />, { wrapper: Wrapper });

      fireEvent.click(screen.getByRole('button', { name: 'Edit summary' }));
      const textarea = screen.getByRole('textbox', { name: 'Summary' });

      fireEvent.change(textarea, { target: { value: '    ' } });

      const alert = screen.getByRole('alert');
      expect(alert.textContent).toBe('Summary cannot be empty.');

      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(patchSpy).not.toHaveBeenCalled();
    });

    it('sanitizes pasted text containing control characters and newlines', () => {
      const { Wrapper } = createWrapper();
      render(<SummaryField issue={mockIssue} />, { wrapper: Wrapper });

      fireEvent.click(screen.getByRole('button', { name: 'Edit summary' }));
      const textarea = screen.getByRole('textbox', { name: 'Summary' });

      fireEvent.change(textarea, { target: { value: 'a\nb\u0007c' } });
      expect((textarea as HTMLTextAreaElement).value).toBe('a b c');
    });

    it('Enter commits and moves focus to description focusRef', async () => {
      const { Wrapper } = createWrapper();
      vi.spyOn(apiClient, 'patch').mockResolvedValueOnce({
        ...mockIssue,
        summary: 'Updated Summary',
      });

      function TestHarness() {
        const descRef = useRef<HTMLDivElement>(null);
        return (
          <div>
            <SummaryField issue={mockIssue} descriptionFocusRef={descRef} />
            <div ref={descRef} tabIndex={0} data-testid="description-target">
              Description
            </div>
          </div>
        );
      }

      render(<TestHarness />, { wrapper: Wrapper });

      fireEvent.click(screen.getByRole('button', { name: 'Edit summary' }));
      const textarea = screen.getByRole('textbox', { name: 'Summary' });

      fireEvent.change(textarea, { target: { value: 'Updated Summary' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });

      const descTarget = screen.getByTestId('description-target');
      await waitFor(() => {
        expect(document.activeElement).toBe(descTarget);
      });
    });

    it('Escape reverts changes and returns focus to edit button', async () => {
      const { Wrapper } = createWrapper();
      render(<SummaryField issue={mockIssue} />, { wrapper: Wrapper });

      const editBtn = screen.getByRole('button', { name: 'Edit summary' });
      fireEvent.click(editBtn);

      const textarea = screen.getByRole('textbox', { name: 'Summary' });
      fireEvent.change(textarea, { target: { value: 'Draft that will be reverted' } });

      fireEvent.keyDown(textarea, { key: 'Escape' });

      // Edit mode is exited and summary restored
      expect(screen.queryByRole('textbox')).toBeNull();
      expect(screen.getByText('Original Summary')).toBeDefined();

      await waitFor(() => {
        expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Edit summary' }));
      });
    });

    it('blur behavior: commits on blur when valid, ignores when invalid or targeting header', async () => {
      const { Wrapper } = createWrapper();
      const patchSpy = vi.spyOn(apiClient, 'patch').mockResolvedValue({
        ...mockIssue,
        summary: 'Committed On Blur',
      });

      const { unmount } = render(
        <div className="surface">
          <div className="surface__header">
            <button type="button" className="issue-header__btn" data-testid="hdr-btn">Header Btn</button>
          </div>
          <SummaryField issue={mockIssue} />
        </div>,
        { wrapper: Wrapper },
      );

      fireEvent.click(screen.getByRole('button', { name: 'Edit summary' }));
      const textarea = screen.getByRole('textbox', { name: 'Summary' });
      const hdrBtn = screen.getByTestId('hdr-btn');

      // Blur to header button -> does not commit
      fireEvent.blur(textarea, { relatedTarget: hdrBtn });
      expect(patchSpy).not.toHaveBeenCalled();

      // Blur with empty string -> does not commit
      fireEvent.change(textarea, { target: { value: '' } });
      fireEvent.blur(textarea);
      expect(patchSpy).not.toHaveBeenCalled();

      // Blur with >500 characters -> does not commit
      fireEvent.change(textarea, { target: { value: 'a'.repeat(501) } });
      fireEvent.blur(textarea);
      expect(patchSpy).not.toHaveBeenCalled();

      // Blur with valid modified value -> commits
      fireEvent.change(textarea, { target: { value: 'Committed On Blur' } });
      fireEvent.blur(textarea);
      await waitFor(() => {
        expect(patchSpy).toHaveBeenCalledWith(
          '/api/v1/issues/{issue_key}',
          expect.objectContaining({ body: { summary: 'Committed On Blur' } }),
        );
      });

      unmount();
    });
  });

  describe('Required Test Case 5: Conflict handling (412)', () => {
    it('restores previous summary on 412, displays conflict alert, and Reload refetches', async () => {
      const { Wrapper, queryClient } = createWrapper();
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const problem412 = new ApiProblem(412, {
        type: 'https://kanban.example.com/errors/precondition-failed',
        title: 'Precondition Failed',
        status: 412,
        detail: 'ETag mismatch',
      });
      vi.spyOn(apiClient, 'patch').mockRejectedValueOnce(problem412);

      render(<SummaryField issue={mockIssue} />, { wrapper: Wrapper });

      fireEvent.click(screen.getByRole('button', { name: 'Edit summary' }));
      const textarea = screen.getByRole('textbox', { name: 'Summary' });

      fireEvent.change(textarea, { target: { value: 'Conflicting Change' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });

      await waitFor(() => {
        const conflictAlert = screen.getByRole('alert');
        expect(conflictAlert.textContent).toContain(
          'This issue changed since you opened it. Reload to see the latest version.',
        );
      });

      const reloadBtn = screen.getByRole('button', { name: 'Reload' });
      fireEvent.click(reloadBtn);

      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['issue', 'KAN-142'] }),
      );
    });

    it('resets draftText when issue.summary prop changes externally while not editing', () => {
      const { Wrapper } = createWrapper();
      const { rerender } = render(<SummaryField issue={mockIssue} />, { wrapper: Wrapper });
      expect(screen.getByText('Original Summary')).toBeDefined();
      rerender(<SummaryField issue={{ ...mockIssue, summary: 'Brand New Summary' }} />);
      expect(screen.getByText('Brand New Summary')).toBeDefined();
    });
  });
});
