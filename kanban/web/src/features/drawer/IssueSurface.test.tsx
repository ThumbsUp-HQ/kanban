import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes, useNavigate, type NavigateFunction } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { IssueSurface, normalizeIssueDetail } from './IssueSurface';
import { setOpenerElement } from './IssueKeyLink';
import { apiClient } from '../../api/client';
import { ApiProblem } from '../../api/problem';
import { IssueSurfaceSlotsContext, type IssueDetail } from './slots';
import * as breakpoints from '../../styles/breakpoints';

const validIssue: IssueDetail = {
  key: 'KAN-142',
  object_id: '11111111-1111-1111-1111-111111111111',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
  description_markdown: 'Detailed description of the auth hardening task.',
  priority: {
    slug: 'high',
    label: 'High',
    emoji: '⚡',
    sort_order: 2,
    sla_target: null,
  },
  etag: '"etag-kan-142"',
};

function createTestHarness(initialEntries: string[] = ['/projects/KAN/issues?peek=KAN-142']) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 60_000 },
    },
  });

  let navigateRef: ReturnType<typeof useNavigate> | null = null;

  function NavCapture() {
    const nav = useNavigate();
    navigateRef = nav;
    return null;
  }

  function Harness() {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          <NavCapture />
          <Routes>
            <Route
              path="/projects/:projectKey/issues"
              element={
                <div id="main-content">
                  <main id="kb-main" tabIndex={-1}>
                    Main Canvas
                  </main>
                  <div id="kb-issue-surface-host">
                    <IssueSurface />
                  </div>
                </div>
              }
            />
            <Route
              path="/projects/:projectKey/issues/:issueKey"
              element={
                <div id="main-content">
                  <main id="kb-main" tabIndex={-1}>
                    Main Canvas
                  </main>
                  <div id="kb-issue-surface-host">
                    <IssueSurface />
                  </div>
                </div>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  return {
    queryClient,
    Harness,
    getNavigate: (): NavigateFunction => {
      if (!navigateRef) throw new Error('navigateRef not set');
      return navigateRef;
    },
  };
}

describe('IssueSurface', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Required Test Case 1: Positive / Zero-remount invariant', () => {
    it('maintains identical data-mount-id and data-mount-seq across 5 round-trip toggles with exactly 1 GET fetch', async () => {
      const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const { Harness, getNavigate } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);

      const { container } = render(<Harness />);

      await waitFor(() => {
        expect(screen.getByText('Harden Multi-Card OIDC & LDAPS Auth Studio')).toBeDefined();
      });

      const surface = container.querySelector('section');
      expect(surface).not.toBeNull();
      expect(surface?.className).toBe('surface--drawer');

      const initialMountId = surface?.getAttribute('data-mount-id');
      const initialMountSeq = surface?.getAttribute('data-mount-seq');
      expect(initialMountId).toBeTruthy();
      expect(initialMountSeq).toBeTruthy();

      const navigate = getNavigate();

      // Perform 5 round-trip toggles: drawer -> full -> drawer -> full ...
      for (let i = 0; i < 5; i++) {
        // Toggle to full screen
        void navigate('/projects/KAN/issues/KAN-142');
        await waitFor(() => {
          const current = container.querySelector('section');
          expect(current?.className).toBe('surface--full');
          expect(current?.getAttribute('data-mount-id')).toBe(initialMountId);
          expect(current?.getAttribute('data-mount-seq')).toBe(initialMountSeq);
        });

        // Toggle back to drawer
        void navigate('/projects/KAN/issues?peek=KAN-142');
        await waitFor(() => {
          const current = container.querySelector('section');
          expect(current?.className).toBe('surface--drawer');
          expect(current?.getAttribute('data-mount-id')).toBe(initialMountId);
          expect(current?.getAttribute('data-mount-seq')).toBe(initialMountSeq);
        });
      }

      // Mocked fetch was called exactly once for KAN-142
      expect(getSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe('Required Test Case 3: Negative / Security (XSS injection in summary & description)', () => {
    it('renders malicious payloads as literal text nodes; no script or img elements exist', async () => {
      const xssIssue: IssueDetail = {
        ...validIssue,
        summary: '<script>alert(1)</script><img src=x onerror=alert(1)>',
        description_markdown: '<script>alert(2)</script><img src=y onerror=alert(2)>',
      };
      vi.spyOn(apiClient, 'get').mockResolvedValue(xssIssue);

      const { Harness } = createTestHarness();
      const { container } = render(<Harness />);

      await waitFor(() => {
        expect(screen.getByText('<script>alert(1)</script><img src=x onerror=alert(1)>')).toBeDefined();
        expect(screen.getByText('<script>alert(2)</script><img src=y onerror=alert(2)>')).toBeDefined();
      });

      // Strict security invariant: zero script or injected img tags in the DOM
      const scripts = container.querySelectorAll('script');
      const imgs = container.querySelectorAll('img');
      expect(scripts.length).toBe(0);
      expect(imgs.length).toBe(0);
    });
  });

  describe('Required Test Case 7: Keyboard shortcuts and focus return', () => {
    it('Ctrl+Shift+F toggles mode', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const { Harness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);

      const { container } = render(<Harness />);

      await waitFor(() => {
        expect(screen.getByText('Harden Multi-Card OIDC & LDAPS Auth Studio')).toBeDefined();
      });

      expect(container.querySelector('section')?.className).toBe('surface--drawer');

      // Trigger Mod+Shift+F
      fireEvent.keyDown(window, {
        key: 'F',
        ctrlKey: true,
        shiftKey: true,
      });

      await waitFor(() => {
        expect(container.querySelector('section')?.className).toBe('surface--full');
      });
    });

    it('Escape from full returns to drawer, second Escape closes and focus returns to opener', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);

      const openerBtn = document.createElement('button');
      openerBtn.id = 'opener-button';
      document.body.appendChild(openerBtn);
      setOpenerElement(openerBtn);

      const { Harness } = createTestHarness(['/projects/KAN/issues/KAN-142']);
      const { container } = render(<Harness />);

      await waitFor(() => {
        expect(container.querySelector('section')?.className).toBe('surface--full');
      });

      // First Escape: returns to drawer
      fireEvent.keyDown(window, { key: 'Escape' });
      await waitFor(() => {
        expect(container.querySelector('section')?.className).toBe('surface--drawer');
      });

      // Second Escape: closes drawer and returns focus to opener
      fireEvent.keyDown(window, { key: 'Escape' });
      await waitFor(() => {
        expect(container.querySelector('section')).toBeNull();
        expect(document.activeElement).toBe(openerBtn);
      });

      document.body.removeChild(openerBtn);
    });

    it('returns focus to #kb-main when opener element was removed', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);

      const detachedBtn = document.createElement('button');
      // Do not append to body -> detached
      setOpenerElement(detachedBtn);

      const { Harness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      const { container } = render(<Harness />);

      await waitFor(() => {
        expect(container.querySelector('section')).toBeDefined();
      });

      fireEvent.keyDown(window, { key: 'Escape' });

      await waitFor(() => {
        expect(container.querySelector('section')).toBeNull();
        const main = document.getElementById('kb-main');
        expect(document.activeElement).toBe(main);
      });
    });
  });

  describe('Required Test Case 8: Viewport aria-modal property', () => {
    it('sets aria-modal="true" on mobile and aria-modal="false" on desktop', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);

      // Desktop
      vi.spyOn(breakpoints, 'useBreakpoint').mockReturnValue('desktop');
      const { Harness: DesktopHarness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      const { container: desktopContainer, unmount } = render(<DesktopHarness />);

      await waitFor(() => {
        expect(desktopContainer.querySelector('section')?.getAttribute('aria-modal')).toBe('false');
      });
      unmount();

      // Mobile
      vi.spyOn(breakpoints, 'useBreakpoint').mockReturnValue('mobile');
      const { Harness: MobileHarness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      const { container: mobileContainer } = render(<MobileHarness />);

      await waitFor(() => {
        expect(mobileContainer.querySelector('section')?.getAttribute('aria-modal')).toBe('true');
      });
    });
  });

  describe('Required Test Case 9: Error handling (403, 404, network error with Retry)', () => {
    it('renders identical anti-enumeration string for 403 and 404', async () => {
      // 404
      vi.spyOn(apiClient, 'get').mockRejectedValueOnce(
        new ApiProblem(404, { title: 'Not Found', status: 404 }),
      );
      const { Harness: Harness404, queryClient } = createTestHarness(['/projects/KAN/issues?peek=KAN-999']);
      const { unmount } = render(<Harness404 />);

      await waitFor(() => {
        expect(screen.getByText('Issue KAN-999 was not found or you do not have access.')).toBeDefined();
      });
      unmount();
      queryClient.clear();

      // 403
      vi.spyOn(apiClient, 'get').mockRejectedValueOnce(
        new ApiProblem(403, { title: 'Forbidden', status: 403 }),
      );
      const { Harness: Harness403 } = createTestHarness(['/projects/KAN/issues?peek=KAN-999']);
      render(<Harness403 />);

      await waitFor(() => {
        expect(screen.getByText('Issue KAN-999 was not found or you do not have access.')).toBeDefined();
      });
    });

    it('renders "Could not load <KEY>." and Retry button on network error', async () => {
      const getSpy = vi
        .spyOn(apiClient, 'get')
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce(validIssue);

      const { Harness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      render(<Harness />);

      await waitFor(() => {
        expect(screen.getByText('Could not load KAN-142.')).toBeDefined();
      });

      const retryBtn = screen.getByRole('button', { name: 'Retry' });
      fireEvent.click(retryBtn);

      await waitFor(() => {
        expect(getSpy).toHaveBeenCalledTimes(2);
        expect(screen.getByText('Harden Multi-Card OIDC & LDAPS Auth Studio')).toBeDefined();
      });
    });
  });

  describe('Live Persistence & Backend Normalization (KANBA-165)', () => {
    it('normalizes raw backend IssueResponse payloads and preserves complete fixtures', () => {
      expect(normalizeIssueDetail(validIssue, 'KAN')).toBe(validIssue);
      expect(normalizeIssueDetail(null, 'KAN')).toBeNull();

      const rawBackend = {
        id: '01931234-5678-7000-8000-000000000555',
        key: 'KANBA-55',
        summary: 'Backend Issue',
        description_markdown: '```mermaid\ngraph TD\nA-->B\n```',
        description_sha256: 'deadbeef12345678',
        labels: [{ id: 'lbl-1', name: 'Security' }, 'lbl-2'],
      } as unknown as IssueDetail;

      const normalized = normalizeIssueDetail(rawBackend, null);
      expect(normalized.project_key).toBe('KANBA');
      expect(normalized.object_id).toBe('01931234-5678-7000-8000-000000000555');
      expect(normalized.etag).toBe('"deadbeef12345678"');
      expect(normalized.label_ids).toEqual(['lbl-1', 'lbl-2']);
      expect(normalized.capabilities).toEqual(['EDIT', 'TRANSITION', 'COMMENT']);
    });

    it('edits and saves Markdown + Mermaid description via PATCH /api/v1/issues/{issue_key}', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const patchSpy = vi.spyOn(apiClient, 'patch').mockResolvedValue({
        ...validIssue,
        description_markdown: 'Updated markdown\n```mermaid\nflowchart LR\nX-->Y\n```',
      });

      const { Harness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      render(<Harness />);

      await waitFor(() => {
        expect(screen.getByText('Detailed description of the auth hardening task.')).toBeDefined();
      });

      // Click Edit description and then Cancel
      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      const textarea = screen.getByRole('textbox', { name: 'Description' });
      fireEvent.change(textarea, { target: { value: 'Draft cancelled' } });
      fireEvent.click(screen.getByRole('button', { name: 'Cancel description edit' }));
      expect(screen.getByText('Detailed description of the auth hardening task.')).toBeDefined();

      // Click Edit description, enter Markdown + Mermaid, and Save
      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      const textarea2 = screen.getByRole('textbox', { name: 'Description' });
      fireEvent.change(textarea2, {
        target: { value: 'Updated markdown\n```mermaid\nflowchart LR\nX-->Y\n```' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Save description' }));

      await waitFor(() => {
        expect(patchSpy).toHaveBeenCalledWith(
          '/api/v1/issues/{issue_key}',
          expect.objectContaining({
            ifMatch: '"etag-kan-142"',
            params: { issue_key: 'KAN-142' },
            body: { description_markdown: 'Updated markdown\n```mermaid\nflowchart LR\nX-->Y\n```' },
          }),
        );
        expect(screen.getByTestId('issue-mermaid-diagram')).toBeDefined();
      });
    });

    it('loads project workflow states and forwards onIssueUpdate when RailSlot is mounted', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const originalFetch = globalThis.fetch;
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            items: [{ id: '01931234-5678-7000-8000-000000000001', name: 'Todo', group: 'unstarted' }],
          }),
      });

      const MockRail = ({
        issue,
        onIssueUpdate,
      }: {
        issue: IssueDetail;
        onIssueUpdate?: (u: IssueDetail) => void;
      }) => (
        <button
          type="button"
          data-testid="mock-rail-update"
          onClick={() => onIssueUpdate?.({ ...issue, summary: 'Rail Updated Summary' })}
        >
          Rail {issue.summary}
        </button>
      );

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <IssueSurfaceSlotsContext.Provider value={{ rail: MockRail }}>
              <div id="main-content">
                <main id="kb-main" tabIndex={-1}>
                  Main
                </main>
                <div id="kb-issue-surface-host">
                  <IssueSurface />
                </div>
              </div>
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('mock-rail-update')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('mock-rail-update'));
      await waitFor(() => {
        expect(screen.getByText('Rail Updated Summary')).toBeDefined();
      });

      globalThis.fetch = originalFetch;
    });
  });
});
