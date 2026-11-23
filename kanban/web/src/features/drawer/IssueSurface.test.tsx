import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes, useNavigate, createMemoryRouter, RouterProvider, type NavigateFunction } from 'react-router';
import * as reactRouter from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { IssueSurface, IssueSurfaceRoot, normalizeIssueDetail, getIssueAttachments } from './IssueSurface';
import { setOpenerElement } from './IssueKeyLink';
import { apiClient } from '../../api/client';
import { ApiProblem } from '../../api/problem';
import { IssueSurfaceSlotsContext, type IssueDetail } from './slots';
import * as breakpoints from '../../styles/breakpoints';
import * as autoConvertPasteMod from '../../editor/clipboard/autoConvertPaste';
import * as hiddenDomPrunerMod from '../../editor/clipboard/hiddenDomPruner';
import * as viewsApi from '../views/viewsApi';
import type { IssueItem } from '../views/viewsApi';
import * as railApi from '../drawer-rail/railApi';
import * as clipboardUtils from '../../utils/clipboard';

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
        act(() => {
          void navigate('/projects/KAN/issues/KAN-142');
        });
        await waitFor(() => {
          const current = container.querySelector('section');
          expect(current?.className).toBe('surface--full');
          expect(current?.getAttribute('data-mount-id')).toBe(initialMountId);
          expect(current?.getAttribute('data-mount-seq')).toBe(initialMountSeq);
        });

        // Toggle back to drawer
        act(() => {
          void navigate('/projects/KAN/issues?peek=KAN-142');
        });
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
    it('sets aria-modal="true" and role="dialog" on drawer across desktop and mobile', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);

      // Desktop
      vi.spyOn(breakpoints, 'useBreakpoint').mockReturnValue('desktop');
      const { Harness: DesktopHarness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      const { container: desktopContainer, unmount } = render(<DesktopHarness />);

      await waitFor(() => {
        expect(desktopContainer.querySelector('section')?.getAttribute('aria-modal')).toBe('true');
        expect(desktopContainer.querySelector('section')?.getAttribute('role')).toBe('dialog');
      });
      unmount();

      // Mobile
      vi.spyOn(breakpoints, 'useBreakpoint').mockReturnValue('mobile');
      const { Harness: MobileHarness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      const { container: mobileContainer } = render(<MobileHarness />);

      await waitFor(() => {
        expect(mobileContainer.querySelector('section')?.getAttribute('aria-modal')).toBe('true');
        expect(mobileContainer.querySelector('section')?.getAttribute('role')).toBe('dialog');
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
        expect(screen.getByTestId('mermaid-block')).toBeDefined();
      });
    });

    it('catches 412/428 precondition conflict, preserves draft text, and renders actionable conflict banner', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      vi.spyOn(apiClient, 'patch').mockRejectedValue(
        new ApiProblem(412, {
          title: 'Precondition Failed',
          status: 412,
          detail: 'Issue has been modified concurrently by another user.',
        }),
      );

      const { Harness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      render(<Harness />);

      await waitFor(() => {
        expect(screen.getByText('Detailed description of the auth hardening task.')).toBeDefined();
      });

      // Click Edit description, change text, and Save
      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      const textarea = screen.getByRole('textbox', { name: 'Description' });
      fireEvent.change(textarea, {
        target: { value: 'Conflicting draft edit' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Save description' }));

      // Conflict banner is rendered
      await waitFor(() => {
        expect(screen.getByTestId('conflict-banner')).toBeDefined();
      });
      expect(screen.getByText(/412 Precondition Failed/i)).toBeDefined();

      // Draft text is preserved in textarea
      expect(screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Description' }).value).toBe(
        'Conflicting draft edit',
      );

      // Verify actions exist: Reload Latest, Overwrite, Discard Draft
      expect(screen.getByRole('button', { name: 'Reload Latest' })).toBeDefined();
      expect(screen.getByRole('button', { name: 'Overwrite' })).toBeDefined();
      expect(screen.getByRole('button', { name: 'Discard Draft' })).toBeDefined();

      // Discard Draft dismisses banner and resets
      fireEvent.click(screen.getByRole('button', { name: 'Discard Draft' }));
      expect(screen.queryByTestId('conflict-banner')).toBeNull();
    });

    it('handles Reload Latest and Overwrite actions on conflict banner', async () => {
      const issueWithEtag = { ...validIssue, key: 'KAN-142', etag: '"etag-remote-2"' };
      vi.spyOn(apiClient, 'get').mockResolvedValue(issueWithEtag);
      const patchSpy = vi.spyOn(apiClient, 'patch');
      patchSpy.mockRejectedValueOnce(
        new ApiProblem(412, {
          title: 'Precondition Failed',
          status: 412,
          detail: 'Mid-air collision',
        }),
      );

      const { Harness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      render(<Harness />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Edit description' })).toBeDefined();
      });

      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      const textarea = screen.getByRole('textbox', { name: 'Description' });
      fireEvent.change(textarea, { target: { value: 'Conflict draft to overwrite' } });

      fireEvent.click(screen.getByRole('button', { name: 'Save description' }));

      await waitFor(() => {
        expect(screen.getByTestId('conflict-banner')).toBeDefined();
      });

      // Test Reload Latest action
      fireEvent.click(screen.getByRole('button', { name: 'Reload Latest' }));
      await waitFor(() => {
        expect(screen.queryByTestId('conflict-banner')).toBeNull();
      });

      // Trigger conflict again for Overwrite test
      patchSpy.mockRejectedValueOnce(
        new ApiProblem(412, {
          title: 'Precondition Failed',
          status: 412,
          detail: 'Second collision',
        }),
      );
      fireEvent.change(screen.getByRole('textbox', { name: 'Description' }), {
        target: { value: 'Second conflict draft' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Save description' }));

      await waitFor(() => {
        expect(screen.getByTestId('conflict-banner')).toBeDefined();
      });

      // Successful Overwrite
      patchSpy.mockResolvedValueOnce(issueWithEtag);
      fireEvent.click(screen.getByRole('button', { name: 'Overwrite' }));

      await waitFor(() => {
        expect(screen.queryByTestId('conflict-banner')).toBeNull();
      });
    });

    it('loads project workflow states and forwards onIssueUpdate when RailSlot is mounted', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        project_key: '',
        project_name: 'Kanban Custom Name',
      });
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
          onClick={() => onIssueUpdate?.({ ...issue, summary: 'Rail Updated Summary', project_key: 'KAN', project_name: undefined })}
        >
          Rail {issue.summary}
        </button>
      );

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <IssueSurfaceSlotsContext.Provider
              value={{
                rail: MockRail,
                activity: ({ issue }) => <div data-testid="mock-activity">Activity for {issue.key}</div>,
              }}
            >
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
        expect(screen.getByTestId('mock-activity')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('mock-rail-update'));
      await waitFor(() => {
        expect(screen.getByText('Rail Updated Summary')).toBeDefined();
      });

      globalThis.fetch = originalFetch;
    });

    it('covers all normalizeIssueDetail defensive fallback branches', () => {
      // 1. Primitive non-object input
      expect(normalizeIssueDetail('invalid' as unknown as IssueDetail, 'KAN')).toBe('invalid');
      expect(normalizeIssueDetail(42 as unknown as IssueDetail, 'KAN')).toBe(42);

      // 2. Candidate extracted from items array
      const fromItems = normalizeIssueDetail(
        { items: [{ id: 'i-nested', key: 'NEST-1', summary: 'Nested', description_sha256: 'sha1' }] } as unknown as IssueDetail,
        null,
      );
      expect(fromItems.key).toBe('NEST-1');
      expect(fromItems.project_key).toBe('NEST');
      expect(fromItems.object_id).toBe('i-nested');
      expect(fromItems.etag).toBe('"sha1"');

      // 3. Fallback project key when key lacks hyphen
      const noHyphen = normalizeIssueDetail(
        { key: 'NOHYPHEN', id: 'i-nohyphen' } as unknown as IssueDetail,
        'FALLBACK_PROJ',
      );
      expect(noHyphen.project_key).toBe('FALLBACK_PROJ');

      // 4. Default 'KAN' project key when key lacks hyphen and no fallback
      const defaultProj = normalizeIssueDetail(
        { key: 'SIMPLE', id: 'i-simple' } as unknown as IssueDetail,
        null,
      );
      expect(defaultProj.project_key).toBe('KAN');

      // 5. Existing capabilities and labels as strings array
      const withCustomCaps = normalizeIssueDetail(
        {
          key: 'KAN-99',
          id: 'i-99',
          capabilities: ['VIEW_ONLY'],
          labels: ['label-string-1', 'label-string-2'],
        } as unknown as IssueDetail,
        'KAN',
      );
      expect(withCustomCaps.capabilities).toEqual(['VIEW_ONLY']);
      expect(withCustomCaps.label_ids).toEqual(['label-string-1', 'label-string-2']);
    });

    it('renders IssueSurfaceRoot in split mode with new tab link and key', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <div className="kb-split-layout">
              <IssueSurfaceRoot mode="split" issueKey="KAN-142" projectKey="KAN" />
            </div>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByRole('link', { name: 'Open in new tab' })).toBeDefined();
      });

      // Open in new tab link
      const newTabLink = screen.getByRole('link', { name: 'Open in new tab' });
      expect(newTabLink.getAttribute('href')).toBe('/projects/KAN/issues/KAN-142');
      expect(newTabLink.getAttribute('target')).toBe('_blank');
    });

    it('renders IssueSurfaceRoot outside of router context via fallback props', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <IssueSurfaceRoot mode="full" issueKey="KAN-142" projectKey="KAN" />
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('KAN-142')).toBeDefined();
      });
    });

    it('covers split mode in loading and error states', async () => {
      // 1. Loading state
      let resolveFetch!: (v: unknown) => void;
      const pendingPromise = new Promise((resolve) => {
        resolveFetch = resolve;
      });
      vi.spyOn(apiClient, 'get').mockReturnValue(pendingPromise);
      const queryClient1 = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      const { unmount } = render(
        <QueryClientProvider client={queryClient1}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot mode="split" issueKey="KAN-999" projectKey="KAN" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(screen.getByText('#KAN-999')).toBeDefined();

      resolveFetch(validIssue);
      unmount();

      // 2. Error state
      vi.spyOn(apiClient, 'get').mockRejectedValue(new Error('Network drop'));
      const queryClient2 = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient2}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot mode="split" issueKey="KAN-FAIL" projectKey="KAN" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Could not load KAN-FAIL.')).toBeDefined();
      });
    });

    it('renders IssueSurfaceRoot outside Router context and handles fullscreen navigation fallback', async () => {
      const originalAssign = window.location.assign.bind(window.location);
      const assignMock = vi.fn();
      delete (window as unknown as { location?: unknown }).location;
      (window as unknown as { location: unknown }).location = {
        assign: assignMock,
        pathname: '/projects/KAN/issues',
        search: '?peek=KAN-142',
      };

      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        project_name: undefined,
        description_markdown: null,
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <IssueSurfaceRoot mode="drawer" issueKey="KAN-142" projectKey="KAN" />
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /open in full screen/i })).toBeDefined();
      });

      const expandBtn = screen.getByRole('button', { name: /open in full screen/i });
      fireEvent.click(expandBtn);
      expect(assignMock).toHaveBeenCalledWith('/projects/KAN/issues/KAN-142');

      (window as unknown as { location: unknown }).location = { assign: originalAssign, pathname: '/', search: '' };
    });

    it('covers normalizeIssueDetail edge cases: no hyphen key and empty description sha', () => {
      const normalized1 = normalizeIssueDetail({
        key: 'NOHYPHEN',
        summary: 'No hyphen key',
        description_sha256: '',
      } as never, null);
      expect(normalized1.project_key).toBe('KAN');
      expect(normalized1.etag).toBeUndefined();

      const normalized2 = normalizeIssueDetail({
        key: 'CUSTOM-1',
        summary: 'Custom key',
        project_key: '',
      }, null);
      expect(normalized2.project_key).toBe('CUSTOM');

      // Non-string key
      const normNonStringKey = normalizeIssueDetail({
        key: undefined as never,
        summary: 'Non string key',
      } as never, null);
      expect(normNonStringKey.project_key).toBe('KAN');

      // Key starting with hyphen
      const normHyphenStart = normalizeIssueDetail({
        key: '-123',
        summary: 'Hyphen start key',
      } as never, null);
      expect(normHyphenStart.project_key).toBe('');

      const normalized3 = normalizeIssueDetail({
        key: 123 as unknown as string,
        labels: [{ id: 'lbl-1', name: 'Bug' }],
        project_name: null as unknown as string,
      } as unknown as IssueDetail, 'KAN');
      expect(normalized3.project_key).toBe('KAN');
      expect(normalized3.label_ids).toEqual(['lbl-1']);

      // Candidate already fully shaped with project_key, object_id, and etag
      const completeCandidate = {
        key: 'KAN-99',
        project_key: 'KAN',
        object_id: 'obj-99',
        etag: '"etag-99"',
        summary: 'Full candidate',
      };
      expect(normalizeIssueDetail(completeCandidate as never, null)).toBe(completeCandidate);

      // candidate with object labels and fallbackProjectKey
      const normalizedWithObjLabels = normalizeIssueDetail({
        key: 'PLAIN',
        summary: 'Plain',
        labels: [{ id: 'lbl-uuid-1', name: 'Bug' }],
      } as never, 'FALLBACK_PRJ');
      expect(normalizedWithObjLabels.project_key).toBe('FALLBACK_PRJ');
      expect(normalizedWithObjLabels.label_ids).toEqual(['lbl-uuid-1']);
    });

    it('covers handleClose focusing fallback card in DOM, project metadata fallbacks', async () => {
      const card = document.createElement('div');
      card.setAttribute('data-testid', 'board-card-KAN-142');
      document.body.appendChild(card);
      const cardFocus = vi.spyOn(card, 'focus');

      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        project_name: undefined,
        description_markdown: undefined,
      });

      render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <IssueSurfaceRoot mode="drawer" issueKey="KAN-142" projectKey="KAN" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Close issue panel' })).toBeDefined();
      });

      fireEvent.click(screen.getByRole('button', { name: 'Close issue panel' }));
      expect(cardFocus).toHaveBeenCalled();
      card.remove();
    });

    it('connects toolbar buttons, media upload, preview toggle, and sanitized paste pill in description editor', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const uploadSpy = vi.spyOn(autoConvertPasteMod, 'defaultUploadAttachment');

      const { Harness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      render(<Harness />);

      await waitFor(() => {
        expect(screen.getByText('Detailed description of the auth hardening task.')).toBeDefined();
      });

      // Enter edit mode
      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Description' });

      // Click toolbar buttons
      fireEvent.click(screen.getByRole('button', { name: 'Bold text' }));
      expect(textarea.value).toContain('**bold text**');

      fireEvent.click(screen.getByRole('button', { name: 'Italic text' }));
      expect(textarea.value).toContain('*italic text*');

      fireEvent.click(screen.getByRole('button', { name: 'Insert code' }));
      expect(textarea.value).toContain('`code`');

      fireEvent.click(screen.getByRole('button', { name: 'Insert link' }));
      expect(textarea.value).toContain('[link text](https://example.com)');

      fireEvent.click(screen.getByRole('button', { name: 'Insert tasklist' }));
      expect(textarea.value).toContain('- [ ] task item');

      fireEvent.click(screen.getByRole('button', { name: 'Insert Mermaid diagram' }));
      expect(textarea.value).toContain('```mermaid');

      // Test clicking the attach button directly
      const fileInput = screen.getByTestId<HTMLInputElement>('desc-file-input');
      const attachBtn = screen.getByRole('button', { name: 'Attach media or SVG' });
      const clickSpy = vi.spyOn(fileInput, 'click');
      fireEvent.click(attachBtn);
      expect(clickSpy).toHaveBeenCalled();

      // Test file input with empty files
      fireEvent.change(fileInput, { target: { files: [] } });

      // Test file input with oversized file (>25 MiB)
      const oversizedFile = new File(['x'.repeat(100)], 'huge.png', { type: 'image/png' });
      Object.defineProperty(oversizedFile, 'size', { value: 26 * 1024 * 1024 });
      fireEvent.change(fileInput, { target: { files: [oversizedFile] } });
      expect(uploadSpy).toHaveBeenCalledTimes(0);

      // Test file input with custom markdownUri
      uploadSpy.mockResolvedValueOnce({
        id: 'desc_att_2',
        markdownUri: 'https://cdn.example.com/vector.svg',
      });
      const svgFile = new File(['<svg></svg>'], 'vector.svg', { type: 'image/svg+xml' });
      fireEvent.change(fileInput, { target: { files: [svgFile] } });
      await waitFor(() => {
        expect(uploadSpy).toHaveBeenCalledTimes(1);
        expect(textarea.value).toContain('![vector.svg](https://cdn.example.com/vector.svg)');
      });

      // Test paste with image file
      uploadSpy.mockResolvedValueOnce({
        id: 'desc_att_3',
        markdownUri: '',
      });
      const pastedImg = new File(['content'], 'pasted.png', { type: 'image/png' });
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [pastedImg],
          types: ['Files'],
          getData: () => '',
        },
      });
      await waitFor(() => {
        expect(uploadSpy).toHaveBeenCalledTimes(2);
        expect(textarea.value).toContain('![pasted.png](attachment://desc_att_3)');
      });

      // Test paste with oversized image file
      const pastedHugeImg = new File(['content'], 'huge_paste.png', { type: 'image/png' });
      Object.defineProperty(pastedHugeImg, 'size', { value: 26 * 1024 * 1024 });
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [pastedHugeImg],
          types: ['Files'],
          getData: () => '',
        },
      });
      expect(uploadSpy).toHaveBeenCalledTimes(2);

      // Test paste with SVG file
      uploadSpy.mockResolvedValueOnce({
        id: 'desc_att_4',
        markdownUri: '/api/v1/attachments/desc_att_4',
      });
      const pastedSvg = new File(['<svg></svg>'], 'pasted.svg', { type: 'image/svg+xml' });
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [pastedSvg],
          types: ['Files'],
          getData: () => '',
        },
      });
      await waitFor(() => {
        expect(uploadSpy).toHaveBeenCalledTimes(3);
      });

      // Test paste with non-HTML plain text
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [],
          types: ['text/plain'],
          getData: () => '',
        },
      });

      // Test paste with HTML containing 0 hidden nodes
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [],
          types: ['text/html'],
          getData: (format: string) => (format === 'text/html' ? '<p>Plain HTML</p>' : ''),
        },
      });

      // Test rich HTML paste and sanitized pill revert
      vi.spyOn(hiddenDomPrunerMod, 'pruneHiddenDom').mockReturnValueOnce({
        prunedHtml: '<p>Sanitized</p>',
        prunedHiddenNodes: 3,
      });
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [],
          types: ['text/html'],
          getData: (format: string) => (format === 'text/html' ? '<p>Pasted description</p>' : ''),
        },
      });

      const pill = await screen.findByTestId('desc-sanitized-pill');
      expect(pill).toBeDefined();

      const revertBtn = screen.getByTestId('desc-sanitized-pill-revert-btn');
      fireEvent.click(revertBtn);
      expect(screen.queryByTestId('desc-sanitized-pill')).toBeNull();

      // Test raw / preview toggle button and Cmd+Shift+M
      const rawBtn = screen.getByTestId('description-editor-tool-raw');
      fireEvent.click(rawBtn);
      expect(screen.getByTestId('desc-preview')).toBeDefined();

      fireEvent.click(rawBtn);
      expect(screen.getByRole('textbox', { name: 'Description' })).toBeDefined();

      const textareaAfter = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Description' });
      fireEvent.keyDown(textareaAfter, { key: 'a' });
      fireEvent.keyDown(textareaAfter, { key: 'm', metaKey: false });
      fireEvent.keyDown(textareaAfter, { key: 'm', metaKey: true, shiftKey: false });
      fireEvent.keyDown(textareaAfter, { key: 'm', metaKey: true, shiftKey: true });
      expect(screen.getByTestId('desc-preview')).toBeDefined();

      uploadSpy.mockRestore();
    });

    it('covers conflict banner actions: reload, overwrite, overwrite failure, and discard', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      vi.spyOn(apiClient, 'patch').mockRejectedValueOnce(
        new ApiProblem(412, { title: 'Precondition Failed', status: 412 }),
      );

      const { Harness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      render(<Harness />);

      await waitFor(() => {
        expect(screen.getByText('Detailed description of the auth hardening task.')).toBeDefined();
      });

      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      const textarea = screen.getByRole('textbox', { name: 'Description' });
      fireEvent.change(textarea, { target: { value: 'Conflict draft' } });
      fireEvent.click(screen.getByRole('button', { name: 'Save description' }));

      await waitFor(() => {
        expect(screen.getByTestId('conflict-banner')).toBeDefined();
      });

      // Reload Latest action
      const reloadBtn = screen.getByRole('button', { name: 'Reload Latest' });
      fireEvent.click(reloadBtn);
      await waitFor(() => {
        expect(screen.queryByTestId('conflict-banner')).toBeNull();
      });

      // Trigger conflict again for Overwrite
      vi.spyOn(apiClient, 'patch').mockRejectedValueOnce(
        new ApiProblem(412, { title: 'Precondition Failed', status: 412 }),
      );
      fireEvent.click(screen.getByRole('button', { name: 'Save description' }));
      await waitFor(() => {
        expect(screen.getByTestId('conflict-banner')).toBeDefined();
      });

      // Overwrite failure
      vi.spyOn(apiClient, 'patch').mockRejectedValueOnce(new Error('Network error'));
      const overwriteBtn = screen.getByRole('button', { name: 'Overwrite' });
      fireEvent.click(overwriteBtn);
      await waitFor(() => {
        expect(screen.getByTestId('conflict-banner')).toBeDefined();
      });

      // Overwrite success
      vi.spyOn(apiClient, 'patch').mockResolvedValueOnce({
        ...validIssue,
        description_markdown: 'Conflict draft',
      });
      fireEvent.click(overwriteBtn);
      await waitFor(() => {
        expect(screen.queryByTestId('conflict-banner')).toBeNull();
      });

      // Trigger conflict again for Discard Draft
      vi.spyOn(apiClient, 'patch').mockRejectedValueOnce(
        new ApiProblem(412, { title: 'Precondition Failed', status: 412 }),
      );
      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      fireEvent.click(screen.getByRole('button', { name: 'Save description' }));
      await waitFor(() => {
        expect(screen.getByTestId('conflict-banner')).toBeDefined();
      });
      const discardBtn = screen.getByRole('button', { name: 'Discard Draft' });
      fireEvent.click(discardBtn);
      expect(screen.queryByTestId('conflict-banner')).toBeNull();
    });

    it('covers selected text formatting, 428 precondition, network errors, and full mode toggle', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        etag: undefined,
      });

      const { Harness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      render(<Harness />);

      await waitFor(() => {
        expect(screen.getByText('Detailed description of the auth hardening task.')).toBeDefined();
      });

      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Description' });
      textarea.value = 'hello world';
      textarea.selectionStart = 0;
      textarea.selectionEnd = 5;

      // Wrap selected text
      fireEvent.click(screen.getByRole('button', { name: 'Bold text' }));
      expect(textarea.value).toContain('**hello**');

      // Test 428 Precondition Required
      vi.spyOn(apiClient, 'patch').mockRejectedValueOnce(
        new ApiProblem(428, { title: 'Precondition Required', status: 428 }),
      );
      fireEvent.click(screen.getByRole('button', { name: 'Save description' }));
      await waitFor(() => {
        expect(screen.getByTestId('conflict-banner')).toBeDefined();
        expect(screen.getByText(/428/)).toBeDefined();
      });

      // Clear conflict banner via Discard Draft
      fireEvent.click(screen.getByRole('button', { name: 'Discard Draft' }));
      expect(screen.queryByTestId('conflict-banner')).toBeNull();

      // Test network error save (offline mode)
      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      vi.spyOn(apiClient, 'patch').mockRejectedValueOnce(new TypeError('Failed to fetch'));
      fireEvent.click(screen.getByRole('button', { name: 'Save description' }));
      await waitFor(() => {
        expect(screen.queryByTestId('conflict-banner')).toBeNull();
      });

      // Test IssueSurfaceRoot with empty issueKey
      render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <IssueSurfaceRoot mode="split" issueKey="" projectKey="KAN" />
        </QueryClientProvider>,
      );
    });

    it('covers split mode nav toggling, view-only capability, and fullscreen close navigation', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        capabilities: ['VIEW'],
      });

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      const router = createMemoryRouter(
        [
          {
            path: '/projects/:project_key/issues/:issue_key',
            element: <IssueSurfaceRoot mode="split" issueKey="KAN-142" projectKey="KAN" />,
          },
        ],
        { initialEntries: ['/projects/KAN/issues/KAN-142'] },
      );
      render(
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Detailed description of the auth hardening task.')).toBeDefined();
      });

      // Edit description button is hidden due to capabilities: ['VIEW']
      expect(screen.queryByRole('button', { name: 'Edit description' })).toBeNull();
    });

    it('covers opener element capture, full mode toggle, non-image paste, and without router assign', async () => {
      const openerBtn = document.createElement('button');
      openerBtn.textContent = 'Opener';
      document.body.appendChild(openerBtn);
      openerBtn.focus();

      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);

      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount } = render(
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-142']}>
            <IssueSurfaceRoot mode="full" issueKey="KAN-142" projectKey="KAN" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Return to side panel' })).toBeDefined();
      });

      // Toggle from full mode back to peek
      fireEvent.click(screen.getByRole('button', { name: 'Return to side panel' }));

      // Test paste with text file (neither image nor svg)
      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Description' });
      const txtFile = new File(['text'], 'notes.txt', { type: 'text/plain' });
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [txtFile],
          types: ['Files'],
          getData: () => '',
        },
      });

      unmount();
      openerBtn.remove();
    });

    it('covers focus restoration fallbacks and localStorage error branch', async () => {
      // 1. localStorage throwing in useState initializer
      const originalGetItem = localStorage.getItem.bind(localStorage);
      localStorage.getItem = vi.fn().mockImplementation(() => {
        throw new Error('SecurityError: LocalStorage denied');
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <div id="main-content">
              <main id="kb-main" tabIndex={-1}>Main Content</main>
              <div id="kb-issue-surface-host">
                <IssueSurface />
              </div>
            </div>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Harden Multi-Card OIDC & LDAPS Auth Studio')).toBeDefined();
      });

      // Close drawer when opener is NOT in document: exercises focus fallback to #kb-main
      const closeBtn = screen.getByRole('button', { name: 'Close issue panel' });
      fireEvent.click(closeBtn);

      unmount();
      localStorage.getItem = originalGetItem;
    });

    it('covers escape with open popover, empty workflow states, empty markdownUri upload, and fence newlines', async () => {
      vi.spyOn(viewsApi, 'fetchProjectStates').mockResolvedValue([]);
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const uploadSpy = vi.spyOn(autoConvertPasteMod, 'defaultUploadAttachment').mockResolvedValue({
        id: 'att_fallback',
        markdownUri: '',
      });

      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount } = render(
        <IssueSurfaceSlotsContext.Provider value={{ rail: () => <div data-testid="test-rail" /> }}>
          <QueryClientProvider client={qc}>
            <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
              <IssueSurface />
            </MemoryRouter>
          </QueryClientProvider>
        </IssueSurfaceSlotsContext.Provider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Harden Multi-Card OIDC & LDAPS Auth Studio')).toBeDefined();
      });

      // 1. Escape with open hint popover
      const popover = document.createElement('div');
      popover.setAttribute('data-hint-open', 'true');
      document.body.appendChild(popover);
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.getByText('Harden Multi-Card OIDC & LDAPS Auth Studio')).toBeDefined();
      popover.remove();

      // 2. Escape with defaultPrevented = true
      const ev = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true });
      ev.preventDefault();
      window.dispatchEvent(ev);
      expect(screen.getByText('Harden Multi-Card OIDC & LDAPS Auth Studio')).toBeDefined();

      // 3. Edit description and test fence newline handling + empty markdownUri
      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Description' });

      // Click Insert Mermaid diagram at end
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
      fireEvent.click(screen.getByRole('button', { name: 'Insert Mermaid diagram' }));
      expect(textarea.value).toContain('```mermaid');
      expect(textarea.value).toContain('```\n');

      // Repeated click of Mermaid button when cursor is at end
      fireEvent.click(screen.getByRole('button', { name: 'Insert Mermaid diagram' }));

      // Attach file with empty markdownUri
      const fileInput = screen.getByTestId<HTMLInputElement>('desc-file-input');
      const testFile = new File(['image bytes'], 'diagram.png', { type: 'image/png' });
      fireEvent.change(fileInput, { target: { files: [testFile] } });
      await waitFor(() => {
        expect(textarea.value).toContain('![diagram.png](attachment://att_fallback)');
      });

      // Paste image with empty markdownUri
      fireEvent.paste(textarea, {
        clipboardData: {
          files: [testFile],
          types: ['Files'],
          getData: () => '',
        },
      });
      await waitFor(() => {
        expect(uploadSpy).toHaveBeenCalled();
      });

      uploadSpy.mockRestore();
      unmount();
    });

    it('clicking [aria-label="Insert Mermaid diagram"] twice consecutively produces exact 2-block output', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const { Harness } = createTestHarness(['/projects/KAN/issues?peek=KAN-142']);
      render(<Harness />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Edit description' })).toBeDefined();
      });

      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Description' });
      const mermaidBtn = screen.getByRole('button', { name: 'Insert Mermaid diagram' });

      // Clear description
      fireEvent.change(textarea, { target: { value: '' } });
      textarea.setSelectionRange(0, 0);

      // First click
      fireEvent.click(mermaidBtn);
      const expectedBlock1 = '```mermaid\ngraph TD\n  A[Start] --> B[End]\n```\n';
      expect(textarea.value).toBe(expectedBlock1);
      expect(textarea.selectionStart).toBe(expectedBlock1.length);
      expect(textarea.selectionEnd).toBe(expectedBlock1.length);

      // Second click: immediately click again with cursor at end of first block
      fireEvent.click(mermaidBtn);
      const expectedBlock2 = '```mermaid\ngraph TD\n  A[Start] --> B[End]\n```\n';
      const expectedFull = `${expectedBlock1}\n${expectedBlock2}`;
      expect(textarea.value).toBe(expectedFull);
      expect(textarea.selectionStart).toBe(expectedFull.length);
      expect(textarea.selectionEnd).toBe(expectedFull.length);

      const matches = Array.from(textarea.value.matchAll(/```mermaid\n([\s\S]*?)```/g));
      expect(matches).toHaveLength(2);
      expect(textarea.value).not.toContain(';');
      expect(textarea.value).toBe(
        '```mermaid\ngraph TD\n  A[Start] --> B[End]\n```\n\n```mermaid\ngraph TD\n  A[Start] --> B[End]\n```\n',
      );
    });
  });

  describe('Mobile & Split Surface State Controls (KAN-44)', () => {
    it('calls onClose when split-surface-close-btn is clicked in split mode', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const onClose = vi.fn();

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-142"
              projectKey="KAN"
              onClose={onClose}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-surface-close-btn')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('split-surface-close-btn'));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('KAN-58: renders issue-back-to-list-btn in split mode and full mode, navigating back to list cleanly', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const onClose = vi.fn();

      // Split mode
      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?layout=list&peek=KAN-142']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-142"
              projectKey="KAN"
              onClose={onClose}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('issue-back-to-list-btn')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('issue-back-to-list-btn'));
      expect(onClose).toHaveBeenCalledTimes(1);
      unmount();

      // Full mode
      const onCloseFull = vi.fn();
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-142']}>
            <IssueSurfaceRoot
              mode="full"
              issueKey="KAN-142"
              projectKey="KAN"
              onClose={onCloseFull}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('issue-back-to-list-btn')).toBeDefined();
      });
      expect(screen.getByTitle('Return to side panel')).toBeDefined();
      fireEvent.click(screen.getByTestId('issue-back-to-list-btn'));
      expect(onCloseFull).toHaveBeenCalledTimes(1);
    });

    it('renders split-surface-close-btn and invokes onClose in loading and error states', async () => {
      let resolvePromise: (val: unknown) => void = () => {
        /* no-op */
      };
      const pendingFetch = new Promise((resolve) => {
        resolvePromise = resolve;
      });
      vi.spyOn(apiClient, 'get').mockReturnValue(pendingFetch);
      const queryClient1 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const onCloseLoading = vi.fn();

      const { unmount } = render(
        <QueryClientProvider client={queryClient1}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-LOADING"
              projectKey="KAN"
              onClose={onCloseLoading}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(screen.getByTestId('issue-back-to-list-btn')).toBeDefined();
      const closeLoadingBtn = screen.getByTestId('split-surface-close-btn');
      fireEvent.click(closeLoadingBtn);
      expect(onCloseLoading).toHaveBeenCalledTimes(1);
      resolvePromise(validIssue);
      unmount();

      // Error state
      vi.spyOn(apiClient, 'get').mockRejectedValue(new Error('Load failed'));
      const queryClient2 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const onCloseError = vi.fn();

      render(
        <QueryClientProvider client={queryClient2}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-ERR"
              projectKey="KAN"
              onClose={onCloseError}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Could not load KAN-ERR.')).toBeDefined();
      });

      expect(screen.getByTestId('issue-back-to-list-btn')).toBeDefined();
      const closeErrorBtn = screen.getByTestId('split-surface-close-btn');
      fireEvent.click(closeErrorBtn);
      expect(onCloseError).toHaveBeenCalledTimes(1);
    });

    it('transitions state via split-state-select in split mode, calling patchIssue and handling success', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
      });
      const patchSpy = vi.spyOn(railApi, 'patchIssue').mockResolvedValue({
        ...validIssue,
        state: { id: 'state-in-progress', name: 'In Progress', group: 'started' },
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-142"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-state-select')).toBeDefined();
      });

      const select = screen.getByTestId('split-state-select');
      expect(within(select).getByRole('option', { name: 'In Progress' })).toBeDefined();
      fireEvent.change(select, { target: { value: 'state-in-progress' } });

      await waitFor(() => {
        expect(patchSpy).toHaveBeenCalledWith('KAN-142', { state_id: 'state-in-progress' }, validIssue.etag);
      });
      patchSpy.mockRestore();
    });

    it('transitions state via header-state-select in drawer mode, calling patchIssue and handling success', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
      });
      const patchSpy = vi.spyOn(railApi, 'patchIssue').mockResolvedValue({
        ...validIssue,
        state: { id: 'state-in-progress', name: 'In Progress', group: 'started' },
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot
              mode="drawer"
              issueKey="KAN-142"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('header-state-select')).toBeDefined();
      });

      const select = screen.getByTestId('header-state-select');
      expect(within(select).getByRole('option', { name: 'In Progress' })).toBeDefined();
      fireEvent.change(select, { target: { value: 'state-in-progress' } });

      await waitFor(() => {
        expect(patchSpy).toHaveBeenCalledWith('KAN-142', { state_id: 'state-in-progress' }, validIssue.etag);
      });
      patchSpy.mockRestore();
    });

    it('reverts state and displays conflict banner when patchIssue rejects with ApiProblem', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
      });
      const problem = new ApiProblem(412, {
        title: 'Precondition Failed',
        status: 412,
        detail: 'ETag conflict: modified by another session',
      });
      const patchSpy = vi.spyOn(railApi, 'patchIssue').mockRejectedValue(problem);

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-142"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-state-select')).toBeDefined();
      });

      const select = screen.getByTestId('split-state-select');
      expect(within(select).getByRole('option', { name: 'Done' })).toBeDefined();
      fireEvent.change(select, { target: { value: 'state-done' } });

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeDefined();
        expect(screen.getByText(/ETag conflict/i)).toBeDefined();
      });
      patchSpy.mockRestore();
    });

    it('reverts state and displays error banner when patchIssue rejects with standard Error', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
      });
      const patchSpy = vi.spyOn(railApi, 'patchIssue').mockRejectedValue(new Error('WIP limit exceeded'));

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-142"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-state-select')).toBeDefined();
      });

      const select = screen.getByTestId('split-state-select');
      expect(within(select).getByRole('option', { name: 'Done' })).toBeDefined();
      fireEvent.change(select, { target: { value: 'state-done' } });

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeDefined();
        expect(screen.getByText(/WIP limit exceeded/i)).toBeDefined();
      });
      patchSpy.mockRestore();
    });

    it('renders quick properties bar and allows state change via quick-props-state-select', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
      });
      const patchSpy = vi.spyOn(railApi, 'patchIssue').mockResolvedValue({
        ...validIssue,
        state: { id: 'state-done', name: 'Done', group: 'completed' },
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot
              mode="drawer"
              issueKey="KAN-142"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('quick-properties-bar')).toBeDefined();
      });

      const quickSelect = screen.getByTestId('quick-props-state-select');
      fireEvent.change(quickSelect, { target: { value: 'state-done' } });

      await waitFor(() => {
        expect(patchSpy).toHaveBeenCalledWith('KAN-142', { state_id: 'state-done' }, validIssue.etag);
      });
      patchSpy.mockRestore();
    });

    it('renders read-only badges in quick properties bar and split header when user is VIEWER', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        capabilities: ['VIEWER'],
      });
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-142"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-state-badge')).toBeDefined();
        expect(screen.queryByTestId('split-state-select')).toBeNull();
        expect(screen.queryByTestId('quick-props-state-select')).toBeNull();
      });
    });

    it('covers IssueSurfaceRoot props: issueId, object_id, and DescriptionSlot override', async () => {
      const issueWithAssignees: IssueDetail = {
        ...validIssue,
        priority: undefined,
        assignees: [
          { id: 'u1', kind: 'free_text', free_text: 'User One', notify: false, hint: '' },
        ],
      };
      vi.spyOn(apiClient, 'get').mockResolvedValue(issueWithAssignees);
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      const customSlots = {
        description: () => <div data-testid="custom-desc-slot">Custom Description</div>,
      };

      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceSlotsContext.Provider value={customSlots}>
              <IssueSurfaceRoot
                mode="drawer"
                issueKey="KAN-142"
                issueId="id-1111"
                projectKey="KAN"
              />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('custom-desc-slot')).toBeDefined();
        expect(screen.getByText('None')).toBeDefined();
        expect(screen.getByText('User One')).toBeDefined();
      });

      // Test with object_id and other assignee types: display_name, handle, free_text, principal, and fallback
      const variations = [
        { assignees: [{ id: 'u2', display_name: 'Display Name' }], expected: 'Display Name' },
        { assignees: [{ id: 'u3', handle: '@handle' }], expected: '@handle' },
        { assignees: [{ id: 'u4', free_text: 'Contractor' }], expected: 'Contractor' },
        { assignees: [{ id: 'u5' }], expected: 'Assigned' },
        { assignees: [{ id: 'u6', principal: { id: 'p1', handle: 'phandle', display_name: 'Principal Name', type: 'USER' } }], expected: 'Principal Name' },
        { assignees: [{ id: 'u7', principal: { id: 'p2', handle: 'onlyhandle', display_name: '', type: 'USER' } }], expected: 'onlyhandle' },
        { assignees: [{ id: 'u8', name: 'User Name' }], expected: 'User Name' },
        { assignees: [{ id: 'u9', display_name: '', name: '', handle: '', free_text: '', principal: { id: 'p3', display_name: '', handle: '' } }], expected: 'Assigned' },
      ];

      for (const variation of variations) {
        vi.spyOn(apiClient, 'get').mockResolvedValue({
          ...validIssue,
          assignees: variation.assignees,
        });
        queryClient.clear();
        rerender(
          <QueryClientProvider client={queryClient}>
            <MemoryRouter initialEntries={['/projects/KAN/issues']}>
              <IssueSurfaceRoot
                mode="drawer"
                issueKey="KAN-142"
                object_id="obj-2222"
                projectKey="KAN"
              />
            </MemoryRouter>
          </QueryClientProvider>,
        );

        await waitFor(() => {
          expect(screen.getByText(variation.expected)).toBeDefined();
        });
      }
    });

    it('covers projectStates matching, non-matching optimistic states, null patchIssue response, and title-only error', async () => {
      const mockProjectStates = [
        { id: 'st-ready', name: 'Ready', group: 'unstarted' as const, color_hex: '#10b981' },
        { id: 'st-prog', name: 'In Prog', group: 'started' as const, color_hex: '#3b82f6' },
      ];
      vi.spyOn(viewsApi, 'fetchProjectStates').mockResolvedValueOnce(mockProjectStates);
      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...validIssue,
        state: { id: 'st-custom', name: 'Custom', group: 'unstarted' },
      });
      // Return null from patchIssue
      vi.spyOn(railApi, 'patchIssue').mockResolvedValueOnce(null as unknown as IssueDetail);

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-142"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-state-select')).toBeDefined();
      });

      const select = screen.getByTestId('split-state-select');
      expect(within(select).getByRole('option', { name: 'Ready' })).toBeDefined();
      expect(within(select).getByRole('option', { name: 'Custom' })).toBeDefined();
      // Change to st-prog
      fireEvent.change(select, { target: { value: 'st-prog' } });

      // Error with title only in ApiProblem
      const titleOnlyProblem = new ApiProblem(409, { title: 'Concurrent Conflict', status: 409 });
      vi.spyOn(railApi, 'patchIssue').mockRejectedValueOnce(titleOnlyProblem);

      fireEvent.change(select, { target: { value: 'st-unknown' } });

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeDefined();
        expect(screen.getByText('Concurrent Conflict')).toBeDefined();
      });

      // Error with message only (no title, no detail) in ApiProblem
      const msgOnlyProblem = new ApiProblem(500, { code: 'SERVER_ERR' });
      vi.spyOn(railApi, 'patchIssue').mockRejectedValueOnce(msgOnlyProblem);
      fireEvent.change(select, { target: { value: 'st-unknown-2' } });
      await waitFor(() => {
        expect(screen.getByText('API error 500 (SERVER_ERR)')).toBeDefined();
      });

      // Generic error without message
      vi.spyOn(railApi, 'patchIssue').mockRejectedValueOnce({ status: 422 });
      fireEvent.change(select, { target: { value: 'st-unknown-3' } });
      await waitFor(() => {
        expect(screen.getByText('State transition failed')).toBeDefined();
      });

      // Test when issue state matches one of projectStates
      act(() => {
        queryClient.setQueryData(['issue', 'KAN-142'], {
          ...validIssue,
          state: { id: 'st-ready', name: 'Ready', group: 'unstarted' },
        });
      });
      expect(screen.getByTestId('split-state-select')).toBeDefined();

      // Test when issue state is null with projectStates populated
      act(() => {
        queryClient.setQueryData(['issue', 'KAN-142'], {
          ...validIssue,
          state: null,
        });
      });
      expect(screen.getByTestId('split-state-select')).toBeDefined();

      await waitFor(() => {
        expect(screen.getByTestId('split-surface-close-btn')).toBeDefined();
      });
    });

    it('covers empty description preview and fallback project_key in RailSlotWithMeta', async () => {
      const issueWithoutProjKey: IssueDetail = {
        ...validIssue,
        project_key: '',
        project_name: undefined,
        description_markdown: '',
      };
      vi.spyOn(apiClient, 'get').mockResolvedValue(issueWithoutProjKey);
      let capturedMeta: { key: string } | undefined;
      const customSlots = {
        rail: (({ projectMetadata }: { issue: IssueDetail; projectMetadata?: { key: string } }) => {
          capturedMeta = projectMetadata;
          return <div data-testid="custom-rail">Custom Rail</div>;
        }) as React.ComponentType<{ issue: IssueDetail }>,
      };

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/FALLBACK_KEY/issues']}>
            <IssueSurfaceSlotsContext.Provider value={customSlots}>
              <IssueSurfaceRoot
                mode="drawer"
                issueKey="KAN-142"
                projectKey="FALLBACK_KEY"
              />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('custom-rail')).toBeDefined();
      });
      expect(capturedMeta?.key).toBe('FALLBACK_KEY');

      // Edit description, set to empty, and toggle preview
      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: 'Description' });
      fireEvent.change(textarea, { target: { value: '' } });
      fireEvent.click(screen.getByTestId('description-editor-tool-raw'));

      await waitFor(() => {
        expect(screen.getByText('No description')).toBeDefined();
      });
    });

    it('suppresses duplicate drawer when on project issues route in list layout', () => {
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?layout=list&peek=KAN-142']}>
            <IssueSurface />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      expect(container.firstChild).toBeNull();
    });

    it('renders drawer when on project issues route with peek but without list layout', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(validIssue);
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?layout=board&peek=KAN-142']}>
            <IssueSurface />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      await waitFor(() => {
        expect(screen.getByTestId('header-state-select')).toBeDefined();
      });
    });

    it('covers favorite toggle off, corrupt storage fallback, copy fallbacks, auth/me failure, and description cancel', async () => {
      // 1. Pre-seed favorite in localStorage
      localStorage.setItem('kb_favorite_issues', JSON.stringify(['KAN-142']));

      vi.spyOn(apiClient, 'get').mockImplementation((url: string) => {
        if (url.includes('/api/v1/auth/me')) {
          return Promise.reject(new Error('Auth endpoint down'));
        }
        return Promise.resolve(validIssue);
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-142"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-action-toolbar')).toBeDefined();
      });

      // Toggle favorite off
      const favBtn = screen.getByTestId('favorite-issue-toggle');
      fireEvent.click(favBtn);
      const stored = localStorage.getItem('kb_favorite_issues');
      expect(stored).toBe('[]');

      // Corrupt localStorage and dispatch change event
      localStorage.setItem('kb_favorite_issues', '{corrupt json');
      act(() => {
        window.dispatchEvent(new CustomEvent('kb:favorites-changed'));
      });

      // Assign to me when auth/me rejects
      vi.spyOn(railApi, 'addAssignee').mockResolvedValueOnce({
        id: 'asg-u-me',
        kind: 'principal',
        principal: { id: 'u-me', handle: 'me', display_name: 'Current User', type: 'USER' },
      });
      queryClient.setQueryData(['issues', 'KAN'], [validIssue]);
      const assignBtn = screen.getByTestId('split-assign-btn');
      await act(async () => {
        fireEvent.click(assignBtn);
        await Promise.resolve();
      });

      // Second assign click when already assigned
      await act(async () => {
        fireEvent.click(assignBtn);
        await Promise.resolve();
      });

      // Add comment button click when comment composer is present in document
      const dummyComposer = document.createElement('textarea');
      dummyComposer.className = 'surface__comment-input';
      const mockScroll = vi.fn();
      dummyComposer.scrollIntoView = mockScroll;
      document.body.appendChild(dummyComposer);

      const addCommentBtn = screen.getByTestId('split-add-comment-btn');
      fireEvent.click(addCommentBtn);
      expect(mockScroll).toHaveBeenCalled();
      dummyComposer.remove();

      // Double-click share button and branch button to cover timeout clearance
      const shareBtn = screen.getByTestId('split-share-btn');
      const branchBtn = screen.getByTestId('split-git-branch-copy');
      await act(async () => {
        fireEvent.click(shareBtn);
        fireEvent.click(shareBtn);
        fireEvent.click(branchBtn);
        fireEvent.click(branchBtn);
        await Promise.resolve();
      });

      // Test clipboard failure fallback
      Object.assign(navigator, {
        clipboard: {
          writeText: vi.fn().mockRejectedValue(new Error('no clipboard')),
        },
      });
      vi.spyOn(clipboardUtils, 'copyToClipboard').mockRejectedValue(new Error('execCommand failed'));
      await act(async () => {
        fireEvent.click(shareBtn);
        await Promise.resolve();
      });

      // Edit description, click media tool, and cancel edit
      const editDescBtn = screen.getByTestId('split-edit-btn');
      fireEvent.click(editDescBtn);

      const mediaBtn = screen.getByTestId('description-editor-tool-media');
      fireEvent.click(mediaBtn);

      const cancelBtn = screen.getByRole('button', { name: 'Cancel description edit' });
      fireEvent.click(cancelBtn);

      unmount();
      localStorage.clear();
    });

    it('covers pager without onNavigate, storage parse error, and alreadyAssigned branch', async () => {
      // 1. Storage not an array for isFavorite and toggleFavorite
      localStorage.setItem('kb_favorite_issues', JSON.stringify({ not: 'an_array' }));

      // 2. Mock auth/me returning object without id: { handle: 'adam', display_name: 'Adam Outler' }
      vi.spyOn(apiClient, 'get').mockImplementation((url: string) => {
        if (url.includes('/api/v1/auth/me')) {
          return Promise.resolve({ handle: 'adam', display_name: 'Adam Outler' });
        }
        return Promise.resolve({
          ...validIssue,
          description_markdown: undefined,
          project_name: undefined,
          assignees: [
            'adam',
            'u-me',
            { handle: 'adam' },
            { principal: { handle: 'adam' } },
            { id: 'u-me' },
            { principal: { id: 'u-me' } },
            { principal_id: 'u-me' },
          ],
        });
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const issuesListMock = [
        { key: 'KAN-141', summary: 'Prev' },
        { key: 'KAN-142', summary: 'Current' },
        { key: 'KAN-143', summary: 'Next' },
      ];

      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-142"
              projectKey="KAN"
              issuesList={issuesListMock as unknown as viewsApi.IssueItem[]}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-action-toolbar')).toBeDefined();
      });

      // Pager prev and next buttons without onNavigateIssue
      const prevBtn = screen.getByTestId('issue-prev-btn');
      const nextBtn = screen.getByTestId('issue-next-btn');
      fireEvent.click(prevBtn);
      fireEvent.click(nextBtn);

      // Toggle favorite when storage has non-array JSON
      const favBtn = screen.getByTestId('favorite-issue-toggle');
      fireEvent.click(favBtn);

      // Click assign button when assignees already include all variations of adam / u-me
      const assignBtn = screen.getByTestId('split-assign-btn');
      await act(async () => {
        fireEvent.click(assignBtn);
        await Promise.resolve();
      });

      unmount();
      localStorage.clear();
    });

    it('covers addAssignee returning payload without id and query cache mapping', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation((url: string) => {
        if (url.includes('/api/v1/auth/me')) {
          return Promise.resolve({ handle: 'adam', display_name: 'Adam Outler' });
        }
        return Promise.resolve({
          ...validIssue,
          assignees: [],
        });
      });

      const addSpy = vi
        .spyOn(railApi, 'addAssignee')
        .mockResolvedValueOnce({ success: true } as unknown as railApi.AssigneeItem);

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      queryClient.setQueryData(['issues', 'KAN'], [validIssue, { key: 'OTHER-99' }]);

      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-142"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-assign-btn')).toBeDefined();
      });

      await act(async () => {
        fireEvent.click(screen.getByTestId('split-assign-btn'));
        await Promise.resolve();
      });

      expect(addSpy).toHaveBeenCalled();
      unmount();
    });

    it('covers handleAssignToMe error branches: ApiProblem detail/title/message, numeric status, Error, and fallback', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation((url: string) => {
        if (url.includes('/api/v1/auth/me')) {
          return Promise.resolve({ handle: 'testuser', display_name: 'Test User' });
        }
        return Promise.resolve({
          ...validIssue,
          assignees: [],
        });
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-142"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-assign-btn')).toBeDefined();
      });

      // a. ApiProblem with detail
      vi.spyOn(railApi, 'addAssignee').mockRejectedValueOnce(
        new ApiProblem(422, { detail: 'Cannot assign detail' }),
      );
      await act(async () => {
        fireEvent.click(screen.getByTestId('split-assign-btn'));
        await Promise.resolve();
      });
      await waitFor(() => {
        expect(screen.getByText('Cannot assign detail')).toBeDefined();
      });

      // b. ApiProblem with title
      vi.spyOn(railApi, 'addAssignee').mockRejectedValueOnce(
        new ApiProblem(422, { title: 'Cannot assign title' }),
      );
      await act(async () => {
        fireEvent.click(screen.getByTestId('split-assign-btn'));
        await Promise.resolve();
      });
      await waitFor(() => {
        expect(screen.getByText('Cannot assign title')).toBeDefined();
      });

      // c. ApiProblem with message
      vi.spyOn(railApi, 'addAssignee').mockRejectedValueOnce(
        new ApiProblem(500, { message: 'Cannot assign message' }),
      );
      await act(async () => {
        fireEvent.click(screen.getByTestId('split-assign-btn'));
        await Promise.resolve();
      });

      // d. Object with status number
      vi.spyOn(railApi, 'addAssignee').mockRejectedValueOnce({
        status: 400,
        message: 'Obj status error',
      });
      await act(async () => {
        fireEvent.click(screen.getByTestId('split-assign-btn'));
        await Promise.resolve();
      });

      // e. Standard Error
      vi.spyOn(railApi, 'addAssignee').mockRejectedValueOnce(new Error('Standard assign error'));
      await act(async () => {
        fireEvent.click(screen.getByTestId('split-assign-btn'));
        await Promise.resolve();
      });
      await waitFor(() => {
        expect(screen.getByText('Standard assign error')).toBeDefined();
      });

      // f. Primitive string error
      vi.spyOn(railApi, 'addAssignee').mockRejectedValueOnce('Primitive assign error');
      await act(async () => {
        fireEvent.click(screen.getByTestId('split-assign-btn'));
        await Promise.resolve();
      });
      await waitFor(() => {
        expect(screen.getByText('Failed to assign issue')).toBeDefined();
      });

      unmount();
    });
  });

  describe('Cross-prefix issue alias normalization', () => {
    it('normalizes drawer URL from cross-prefix alias KANBA-119 to canonical KAN-42', async () => {
      const canonicalIssue: IssueDetail = {
        ...validIssue,
        key: 'KAN-42',
        project_key: 'KAN',
      };
      vi.spyOn(apiClient, 'get').mockResolvedValue(canonicalIssue);
      const { Harness, getNavigate } = createTestHarness([
        '/projects/KAN/issues?peek=KANBA-119',
      ]);
      const { unmount } = render(<Harness />);
      await waitFor(() => {
        expect(getNavigate()).toBeDefined();
      });
      await waitFor(() => {
        expect(screen.getByText('KAN-42')).toBeDefined();
      });
      unmount();
    });

    it('normalizes full screen URL from cross-prefix alias KANBA-119 to canonical KAN-42', async () => {
      const canonicalIssue: IssueDetail = {
        ...validIssue,
        key: 'KAN-42',
        project_key: 'KAN',
      };
      vi.spyOn(apiClient, 'get').mockResolvedValue(canonicalIssue);
      const { Harness, getNavigate } = createTestHarness([
        '/projects/KAN/issues/KANBA-119',
      ]);
      const { unmount } = render(<Harness />);
      await waitFor(() => {
        expect(getNavigate()).toBeDefined();
      });
      await waitFor(() => {
        expect(screen.getByText('KAN-42')).toBeDefined();
      });
      unmount();
    });

    it('verifies navigate is called with { replace: true } on canonical alias normalization', async () => {
      const canonicalIssue: IssueDetail = {
        ...validIssue,
        key: 'KAN-42',
        project_key: 'KAN',
      };
      vi.spyOn(apiClient, 'get').mockResolvedValue(canonicalIssue);
      const navSpy = vi.fn();
      vi.spyOn(reactRouter, 'useNavigate').mockReturnValue(navSpy);

      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
      });

      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KANBA-119']}>
            <div id="kb-issue-surface-host">
              <IssueSurface />
            </div>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(navSpy).toHaveBeenCalledWith(
          expect.stringContaining('peek=KAN-42'),
          expect.objectContaining({ replace: true }),
        );
      });
      unmount();
    });
  });

  describe('getIssueAttachments helper and split-section-attachments', () => {
    it('returns empty array when issue is null or undefined', () => {
      expect(getIssueAttachments(null)).toEqual([]);
      expect(getIssueAttachments(undefined)).toEqual([]);
    });

    it('extracts attachments from issue.attachments with ?download=1', () => {
      const issueWithAtts: IssueDetail = {
        ...validIssue,
        attachments: [
          {
            id: 'att_123',
            original_filename: 'spec.pdf',
            content_type: 'application/pdf',
            byte_size: 5000,
            page_count: 2,
            blob_sha256: 'abcdef1234567890',
          },
        ],
      };
      const atts = getIssueAttachments(issueWithAtts);
      expect(atts).toHaveLength(1);
      expect(atts[0]?.id).toBe('123');
      expect(atts[0]?.filename).toBe('spec.pdf');
      expect(atts[0]?.contentType).toBe('application/pdf');
      expect(atts[0]?.byteSize).toBe(5000);
      expect(atts[0]?.pageCount).toBe(2);
      expect(atts[0]?.url).toBe('/api/v1/attachments/123?download=1');
    });

    it('extracts attachments from description_markdown and comments and deduplicates them', () => {
      const issueWithDesc: IssueDetail = {
        ...validIssue,
        description_markdown:
          'See [arch.pdf](attachment://att_456) and ![img.png](/api/v1/attachments/att_789)',
      };
      const comments = [
        {
          body_markdown:
            'Also see updated [arch.pdf](attachment://att_456) and [notes.pdf](attachment://att_999)',
        },
      ];
      const atts = getIssueAttachments(issueWithDesc, comments);
      expect(atts).toHaveLength(3);
      const ids = atts.map((a) => a.id);
      expect(ids).toContain('456');
      expect(ids).toContain('789');
      expect(ids).toContain('999');

      const archAtt = atts.find((a) => a.id === '456');
      expect(archAtt?.filename).toBe('arch.pdf');
      expect(archAtt?.contentType).toBe('application/pdf');
      expect(archAtt?.url).toBe('/api/v1/attachments/456?download=1');

      const imgAtt = atts.find((a) => a.id === '789');
      expect(imgAtt?.filename).toBe('img.png');
      expect(imgAtt?.contentType).toBe('image/png');
      expect(imgAtt?.url).toBe('/api/v1/attachments/789?download=1');
    });

    it('renders split-section-attachments with PdfAttachmentCard when attachments are present', async () => {
      const issueWithPdf: IssueDetail = {
        ...validIssue,
        description_markdown: 'Deliverable: [deliverable-spec.pdf](attachment://att_pdf_1)',
      };
      vi.spyOn(apiClient, 'get').mockResolvedValue(issueWithPdf);

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot mode="split" issueKey="KAN-142" projectKey="KAN" />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('split-section-attachments')).toBeDefined();
      });

      const attachmentsSection = screen.getByTestId('split-section-attachments');
      expect(attachmentsSection).toBeDefined();
      expect(within(attachmentsSection).getByText('deliverable-spec.pdf')).toBeDefined();
      expect(within(attachmentsSection).getByTestId('issue-attachment-pdf-pdf_1')).toBeDefined();

      const downloadLink = within(attachmentsSection).getByRole('link', {
        name: 'Download deliverable-spec.pdf',
      });
      expect(downloadLink.getAttribute('href')).toContain('/api/v1/attachments/pdf_1?download=1');

      unmount();
    });

    it('KAN-309: seeds placeholderData from summary items for immediate header/state/priority display and shows issue-description-skeleton during lazy lod=full hydration', async () => {
      const summaryItem: IssueItem = {
        id: '01931234-5678-7000-8000-000000000309',
        key: 'KAN-309',
        summary: 'Instant Summary Title from Staged Load',
        state: { id: 's-in-prog', name: 'In Progress', group: 'started' },
        priority: { slug: 'urgent', label: 'Urgent', emoji: '🔥' },
        assignees: [
          {
            id: 'asg-309',
            kind: 'principal',
            principal: { id: 'u-309', handle: 'architect', display_name: 'Lead Architect', type: 'USER' },
          },
        ],
      };

      const fullItem: IssueDetail = {
        id: summaryItem.id,
        key: summaryItem.key,
        object_id: summaryItem.id,
        project_key: 'KAN',
        summary: summaryItem.summary,
        state: summaryItem.state,
        priority: { slug: 'urgent', label: 'Urgent', emoji: '🔥' },
        etag: '"etag-309-full"',
        description_markdown: '### Detailed Specification Hydrated via lod=full\n\nAll lazy data loaded.',
        capabilities: ['EDIT', 'TRANSITION', 'COMMENT'],
      };

      let resolveFullIssue!: (val: unknown) => void;
      const fullPromise = new Promise((resolve) => {
        resolveFullIssue = resolve;
      });

      const getSpy = vi.spyOn(apiClient, 'get').mockImplementation((path: string, options?: unknown) => {
        if (typeof path === 'string' && path.includes('issues/')) {
          const opts = options as { query?: { lod?: string } } | undefined;
          expect(opts?.query?.lod).toBe('full');
          return fullPromise.then(() => fullItem);
        }
        return Promise.resolve({});
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <IssueSurfaceRoot
              mode="drawer"
              issueKey="KAN-309"
              projectKey="KAN"
              issuesList={[summaryItem]}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Instant hydration from placeholderData: header, summary title, state, priority, assignees exist immediately
      expect(screen.getByText('Instant Summary Title from Staged Load')).toBeDefined();
      expect(screen.getByText('Lead Architect')).toBeDefined();
      expect(screen.getByText('Urgent')).toBeDefined();

      // Description skeleton is shown while lod=full request is in-flight
      expect(screen.getByTestId('issue-description-skeleton')).toBeDefined();
      expect(screen.queryByText('Detailed Specification Hydrated via lod=full')).toBeNull();

      // Resolve full issue
      resolveFullIssue(null);

      // Skeleton replaced by rendered markdown description
      await waitFor(() => {
        expect(screen.queryByTestId('issue-description-skeleton')).toBeNull();
      });
      expect(screen.getByText('Detailed Specification Hydrated via lod=full')).toBeDefined();

      getSpy.mockRestore();
      unmount();
    });

    it('KAN-309: renders issue-description-skeleton in split mode while description loads', async () => {
      const summaryItem: IssueItem = {
        id: '01931234-5678-7000-8000-000000000310',
        key: 'KAN-310',
        summary: 'Split Mode Summary Title',
        state: { id: 's-todo', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'low', label: 'Low', emoji: '☕' },
      };

      const fullItem: IssueDetail = {
        id: summaryItem.id,
        key: summaryItem.key,
        object_id: summaryItem.id,
        project_key: 'KAN',
        summary: summaryItem.summary,
        state: summaryItem.state,
        priority: { slug: 'low', label: 'Low', emoji: '☕' },
        etag: '"etag-310-full"',
        description_markdown: '### Split Mode Markdown Body',
        capabilities: ['EDIT', 'TRANSITION'],
      };

      let resolveFull!: (val: unknown) => void;
      const fullPromise = new Promise((resolve) => {
        resolveFull = resolve;
      });

      const getSpy = vi.spyOn(apiClient, 'get').mockImplementation((path: string) => {
        if (typeof path === 'string' && path.includes('issues/')) {
          return fullPromise.then(() => fullItem);
        }
        return Promise.resolve({});
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-310']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-310"
              projectKey="KAN"
              issuesList={[summaryItem]}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Instant title rendered
      expect(screen.getByText('Split Mode Summary Title')).toBeDefined();

      // Skeleton visible in split mode
      expect(screen.getByTestId('issue-description-skeleton')).toBeDefined();

      // Resolve full issue
      resolveFull(null);

      await waitFor(() => {
        expect(screen.queryByTestId('issue-description-skeleton')).toBeNull();
      });
      expect(screen.getByText('Split Mode Markdown Body')).toBeDefined();

      getSpy.mockRestore();
      unmount();
    });

    it('renders tripped rework banner when rework_tripped_at is set', async () => {
      const issueWithBreaker = {
        id: '01932e6b-0000-7000-8000-000000000071',
        key: 'KAN-71',
        project_key: 'KAN',
        summary: 'Breaker Test Issue',
        description_markdown: 'Breaker test description',
        rework_tripped_at: '2026-11-22T20:00:00Z',
        rework_rejection_streak: 3,
      };

      const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue(issueWithBreaker);
      const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({ status: 'ok' });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-71']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-71"
              projectKey="KAN"
              issuesList={[issueWithBreaker as unknown as IssueItem]}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const banner = await screen.findByTestId('rework-tripped-banner');
      expect(banner).toBeDefined();
      expect(screen.getByText(/Rework loop limit exceeded/i)).toBeDefined();

      const resetBtn = screen.getByTestId('rework-reset-btn');
      fireEvent.click(resetBtn);

      await waitFor(() => {
        expect(postSpy).toHaveBeenCalledWith(
          '/api/v1/issues/{issue_key}/reset-rework-breaker',
          expect.objectContaining({
            params: { issue_key: 'KAN-71' },
          }),
        );
      });

      getSpy.mockRestore();
      postSpy.mockRestore();
      unmount();

      // Also test in drawer mode (proseBody branches) and when reset post rejects
      const getDrawerSpy = vi.spyOn(apiClient, 'get').mockResolvedValue(issueWithBreaker);
      const postDrawerSpy = vi.spyOn(apiClient, 'post').mockRejectedValueOnce(new Error('fail'));
      const drawerRender = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-71']}>
            <IssueSurfaceRoot
              mode="drawer"
              issueKey="KAN-71"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      const drawerBanner = await screen.findByTestId('rework-tripped-banner');
      expect(drawerBanner).toBeDefined();
      fireEvent.click(screen.getByTestId('rework-reset-btn'));
      await waitFor(() => {
        expect(postDrawerSpy).toHaveBeenCalled();
      });
      getDrawerSpy.mockRestore();
      postDrawerSpy.mockRestore();
      drawerRender.unmount();
    });

    it('renders collapsible workpad section with workpad notes and revision', async () => {
      const issueWithWorkpad = {
        id: '01932e6b-0000-7000-8000-000000000072',
        key: 'KAN-72',
        project_key: 'KAN',
        summary: 'Workpad Test Issue',
        description_markdown: 'Workpad test description',
        workpad: {
          id: '01932e6b-0000-7000-8000-000000000073',
          body_markdown: '# Agent Investigation Notes\n- Verified breaker wiring',
          revision: 2,
          updated_at: '2026-11-22T20:05:00Z',
        },
      };

      const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue(issueWithWorkpad);

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-72']}>
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-72"
              projectKey="KAN"
              issuesList={[issueWithWorkpad as unknown as IssueItem]}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const workpadSection = await screen.findByTestId('split-section-workpad');
      expect(workpadSection).toBeDefined();

      const workpadBody = screen.getByTestId('surface-section-workpad');
      expect(workpadBody).toBeDefined();
      expect(screen.getByText(/Agent Investigation Notes/i)).toBeDefined();
      expect(screen.getByText(/Revision 2/i)).toBeDefined();

      getSpy.mockRestore();
      unmount();

      // Also test in drawer mode with empty body_markdown fallback and custom WorkpadSlot
      const emptyWorkpadIssue = {
        ...issueWithWorkpad,
        key: 'KAN-73',
        workpad: {
          id: '01932e6b-0000-7000-8000-000000000074',
          body_markdown: '',
          revision: 1,
        },
      };
      const getDrawerSpy = vi.spyOn(apiClient, 'get').mockResolvedValue(emptyWorkpadIssue);
      const drawerQc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const drawerRender = render(
        <QueryClientProvider client={drawerQc}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-73']}>
            <IssueSurfaceRoot
              mode="drawer"
              issueKey="KAN-73"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );
      await screen.findByTestId('split-section-workpad');
      expect(screen.getByText(/Revision 1/i)).toBeDefined();
      drawerRender.unmount();

      const customSlotRender = render(
        <QueryClientProvider client={drawerQc}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-73']}>
            <IssueSurfaceSlotsContext.Provider
              value={{ workpad: () => <div data-testid="custom-workpad-slot">Custom Workpad</div> }}
            >
              <IssueSurfaceRoot
                mode="drawer"
                issueKey="KAN-73"
                projectKey="KAN"
              />
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );
      await screen.findByTestId('custom-workpad-slot');
      customSlotRender.unmount();
      getDrawerSpy.mockRestore();
    });
  });
});
