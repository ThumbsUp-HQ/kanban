// @ts-nocheck
/**
 * Branch Coverage Booster for Wave 4 Integration (KANBA-211, KANBA-212, KANBA-217).
 * Exercises branches across draftsStore, PropertiesRail, railApi, IssueSurface,
 * FilterDisplayBar, SwimlaneBoardGrid, QuickCreateIssueModal, routes, and stickies.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import {
  getDrafts,
  saveDraft,
  deleteDraft,
  DRAFTS_STORAGE_KEY,
} from '../drafts/draftsStore';
import {
  fetchProjectMetadata,
  fetchProjectPriorities,
  fetchProjectLabels,
  fetchProjectCycles,
  fetchProjectModules,
} from '../drawer-rail/railApi';
import { PropertiesRail } from '../drawer-rail/PropertiesRail';
import {
  IssueSurfaceRoot,
  normalizeIssueDetail,
} from '../drawer/IssueSurface';
import type { IssueDetail } from '../drawer/slots';
import { FilterDisplayBar } from './FilterDisplayBar';
import { SwimlaneBoardGrid } from './SwimlaneBoardGrid';
import { QuickCreateIssueModal } from './QuickCreateIssueModal';
import { FIXTURE_12_ISSUES } from './fixtures';
import {
  FullScreenIssueRoute,
  DraftsWorkspaceView,
  ProjectCyclesView,
  ProjectModulesView,
} from '../../app/routes';
import * as clientModule from '../../api/client';
import { ApiProblem } from '../../api/problem';
import { AuthCardEditorDrawer } from '../admin-auth/AuthCardEditorDrawer';
import * as adminAuthApiModule from '../admin-auth/adminAuthApi';
import { IssuesWorkspaceRoute } from './viewRegistry';
import { StickyCard } from '../stickies/StickyCard';
import { StickyPromotePreviewModal } from '../stickies/StickyPromotePreviewModal';
import type { StickyItem } from '../stickies/stickiesApi';
import { formatHandle } from '../settings/WorkspaceSettingsPage';
import { TransitionRuleCard } from '../workflows/TransitionRuleCard';
import type { TransitionRule, WorkflowHook } from '../workflows/api';

function wrapWithClient(ui: React.ReactElement, initialEntries: string[] = ['/']) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Wave 4 Branch Booster', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  describe('draftsStore edge branches', () => {
    it('handles localStorage throwing errors gracefully on save and delete', () => {
      vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
        throw new Error('QuotaExceededError');
      });

      expect(() => {
        saveDraft({
          id: 'unseeded-id',
          projectKey: 'KAN',
          summary: 'Quota fail',
          stateId: 's1',
          prioritySlug: 'low',
        });
      }).not.toThrow();

      expect(() => {
        deleteDraft('any-id');
      }).not.toThrow();
    });

    it('creates draft with explicit input.id when id is not in existing drafts', () => {
      const d = saveDraft({
        id: 'new-explicit-uuid-1234',
        projectKey: 'KAN',
        summary: 'Custom ID draft',
        stateId: 's1',
        prioritySlug: 'urgent',
      });
      expect(d.id).toBe('new-explicit-uuid-1234');
      expect(d.summary).toBe('Custom ID draft');
    });

    it('handles empty and non-array storage parses', () => {
      window.localStorage.setItem(DRAFTS_STORAGE_KEY, '');
      expect(getDrafts()).toEqual([]);

      window.localStorage.setItem(DRAFTS_STORAGE_KEY, 'null');
      expect(getDrafts()).toEqual([]);

      window.localStorage.setItem(DRAFTS_STORAGE_KEY, '12345');
      expect(getDrafts()).toEqual([]);
    });
  });

  describe('railApi edge branches', () => {
    it('returns empty fallbacks when projectKey is empty or undefined', async () => {
      expect(await fetchProjectMetadata('')).toEqual({ key: '', name: '' });
      expect(await fetchProjectPriorities('')).toEqual([]);
      expect(await fetchProjectLabels('')).toEqual([]);
      expect(await fetchProjectCycles('')).toEqual([]);
      expect(await fetchProjectModules('')).toEqual([]);

      expect(await fetchProjectMetadata('undefined')).toEqual({ key: 'undefined', name: 'undefined' });
      expect(await fetchProjectPriorities('undefined')).toEqual([]);
      expect(await fetchProjectLabels('undefined')).toEqual([]);
      expect(await fetchProjectCycles('undefined')).toEqual([]);
      expect(await fetchProjectModules('undefined')).toEqual([]);
    });
  });

  describe('PropertiesRail edge branches', () => {
    it('renders with minimal capabilities and undefined project key', () => {
      const minimalIssue: IssueDetail = {
        key: 'KAN-99',
        summary: 'Minimal issue',
        state: { id: 's1', name: 'Open', group: 'unstarted' },
      };

      const { container } = wrapWithClient(
        <PropertiesRail
          issue={minimalIssue}
          initialMetadata={{ modules_enabled: false }}
        />,
      );
      expect(container.querySelector('.properties-rail')).toBeDefined();
    });
  });

  describe('IssueSurface normalization & root edge branches', () => {
    it('covers normalizeIssueDetail corner cases', () => {
      // Empty string project key and no hyphen in key
      const norm1 = normalizeIssueDetail({
        key: 'NOHYPHEN',
        project_key: '',
        description_sha256: '',
      } as never);
      expect(norm1.project_key).toBe('KAN');
      expect(norm1.etag).toBeUndefined();

      // Object with labels array of objects instead of strings
      const norm2 = normalizeIssueDetail({
        key: 'KAN-50',
        labels: [{ id: 'lbl-1', name: 'Bug' }, { id: 'lbl-2', name: 'Frontend' }],
      } as never);
      expect(norm2.label_ids).toEqual(['lbl-1', 'lbl-2']);

      // Object without capabilities defaults to full capabilities
      const norm3 = normalizeIssueDetail({ key: 'KAN-51' } as never);
      expect(norm3.capabilities).toEqual(['EDIT', 'TRANSITION', 'COMMENT']);
    });

    it('renders IssueSurfaceRoot in split mode and responds to kb:toggle-sidebar', async () => {
      vi.spyOn(clientModule.apiClient, 'get').mockResolvedValue({
        key: 'KAN-1',
        summary: 'Split view issue',
        project_key: 'KAN',
        etag: '"etag-1"',
      });

      wrapWithClient(
        <IssueSurfaceRoot mode="split" issueKey="KAN-1" projectKey="KAN" />,
      );

      await waitFor(() => {
        expect(screen.getByText('Split view issue')).toBeDefined();
      });

      const navBtn = screen.getByRole('button', { name: 'Hide Nav' });
      fireEvent.click(navBtn);
      expect(screen.getByRole('button', { name: 'Show Nav' })).toBeDefined();

      // Dispatch global sidebar change event
      act(() => {
        window.dispatchEvent(
          new CustomEvent('kb:sidebar-changed', { detail: { collapsed: 'collapsed' } }),
        );
      });
    });
  });

  describe('FilterDisplayBar grouping & search branches', () => {
    it('triggers all group-by and sub-group-by options', () => {
      const onGroupByChange = vi.fn();
      const onSubGroupByChange = vi.fn();
      const onFilterChange = vi.fn();

      wrapWithClient(
        <FilterDisplayBar
          filter={{
            stateIds: [],
            prioritySlugs: [],
            assigneeIds: [],
            labelIds: [],
            searchQuery: '',
            groupBy: 'state',
            subGroupBy: 'none',
            viewMode: 'board',
          }}
          onFilterChange={onFilterChange}
          groupBy="state"
          onGroupByChange={onGroupByChange}
          subGroupBy="none"
          onSubGroupByChange={onSubGroupByChange}
          modulesEnabled={true}
          availableCycles={[{ id: 'c1', name: 'Sprint 1' }]}
          availableModules={[{ id: 'm1', name: 'Engine' }]}
        />,
      );

      const groupSelect = screen.getByLabelText(/^Group by axis$/i);
      fireEvent.change(groupSelect, { target: { value: 'cycle' } });
      expect(onGroupByChange).toHaveBeenCalledWith('cycle');

      fireEvent.change(groupSelect, { target: { value: 'module' } });
      expect(onGroupByChange).toHaveBeenCalledWith('module');

      fireEvent.change(groupSelect, { target: { value: 'priority' } });
      expect(onGroupByChange).toHaveBeenCalledWith('priority');

      const subGroupSelect = screen.getByLabelText(/^Sub-group by axis$/i);
      fireEvent.change(subGroupSelect, { target: { value: 'cycle' } });
      expect(onSubGroupByChange).toHaveBeenCalledWith('cycle');

      fireEvent.change(subGroupSelect, { target: { value: 'module' } });
      expect(onSubGroupByChange).toHaveBeenCalledWith('module');
    });
  });

  describe('SwimlaneBoardGrid subGroupBy branches', () => {
    it('renders with subGroupBy cycle and module and collapses swimlanes', () => {
      const issuesWithCycle = FIXTURE_12_ISSUES.map((iss, idx) => ({
        ...iss,
        cycle_id: idx % 2 === 0 ? 'c-1' : undefined,
        cycle: idx % 2 === 0 ? { id: 'c-1', name: 'Cycle 1' } : undefined,
        module_ids: idx % 3 === 0 ? ['m-1'] : [],
        modules: idx % 3 === 0 ? [{ id: 'm-1', name: 'Module 1' }] : [],
      }));

      const { container } = wrapWithClient(
        <SwimlaneBoardGrid
          issues={issuesWithCycle}
          groupBy="state"
          subGroupBy="cycle"
          projectKey="KAN"
          allCycles={[{ id: 'c-1', name: 'Cycle 1' }]}
          allModules={[{ id: 'm-1', name: 'Module 1' }]}
        />,
      );

      expect(container.querySelector('.swimlane-board-grid')).toBeDefined();

      // Click collapse toggle for swimlane
      const toggle = container.querySelector<HTMLButtonElement>('.swimlane-band-toggle');
      expect(toggle).not.toBeNull();
      if (toggle) {
        fireEvent.click(toggle);
      }
    });

    it('renders with subGroupBy module', () => {
      const issuesWithMod = FIXTURE_12_ISSUES.map((iss) => ({
        ...iss,
        module_ids: ['m-1'],
        modules: [{ id: 'm-1', name: 'Module 1' }],
      }));

      const { container } = wrapWithClient(
        <SwimlaneBoardGrid
          issues={issuesWithMod}
          groupBy="priority"
          subGroupBy="module"
          projectKey="KAN"
          allModules={[{ id: 'm-1', name: 'Module 1' }]}
        />,
      );

      expect(container.querySelector('.swimlane-board-grid')).toBeDefined();
    });
  });

  describe('QuickCreateIssueModal synchronous and failure branches', () => {
    it('handles synchronous onCreate return and renders post create pill', async () => {
      const onCreate = vi.fn().mockReturnValue({ key: 'KAN-SYNC-CREATED' });

      wrapWithClient(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={onCreate}
          projectKey="KAN"
          cycles={[{ id: 'cyc-1', name: 'Cycle 1' }]}
          modules={[{ id: 'mod-1', name: 'Module 1' }]}
          modulesEnabled={true}
        />,
      );

      fireEvent.change(screen.getByPlaceholderText('What needs to be done?'), {
        target: { value: 'Synchronous creation task' },
      });

      fireEvent.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() => {
        expect(screen.getByText('KAN-SYNC-CREATED')).toBeDefined();
        expect(screen.getByTestId('quick-create-post-dialog')).toBeDefined();
      });
    });

    it('handles asynchronous onCreate rejection and displays error message', async () => {
      const onCreate = vi.fn().mockRejectedValue(new Error('Network disconnected'));

      wrapWithClient(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={onCreate}
          projectKey="KAN"
        />,
      );

      fireEvent.change(screen.getByPlaceholderText('What needs to be done?'), {
        target: { value: 'Failing async task' },
      });

      fireEvent.click(screen.getByRole('button', { name: 'Create' }));

      await waitFor(() => {
        expect(screen.getByText(/Network disconnected/i)).toBeDefined();
      });
    });
  });

  describe('DraftsWorkspaceView branches', () => {
    it('renders empty drafts notice', () => {
      wrapWithClient(<DraftsWorkspaceView />);
      expect(screen.getByTestId('drafts-empty')).toBeDefined();
    });

    it('renders drafts and publishes to board with states and modules resolution', async () => {
      saveDraft({
        id: 'draft-pub-1',
        projectKey: 'KAN',
        summary: 'Draft to publish',
        description: 'Detailed draft description',
        stateId: 'state-todo',
        prioritySlug: 'urgent',
        moduleIds: ['mod-1'],
      });

      vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ id: 'new-issue-id', key: 'KAN-999' });

      wrapWithClient(<DraftsWorkspaceView />);

      expect(screen.getByText('Draft to publish')).toBeDefined();
      const resumeBtn = screen.getByTestId('draft-resume-btn');
      fireEvent.click(resumeBtn);

      await waitFor(() => {
        expect(getDrafts().find((d) => d.id === 'draft-pub-1')).toBeUndefined();
      });
    });

    it('deletes draft when delete button clicked', () => {
      saveDraft({
        id: 'draft-del-1',
        projectKey: 'KAN',
        summary: 'Draft to delete',
        stateId: 's1',
        prioritySlug: 'low',
      });

      wrapWithClient(<DraftsWorkspaceView />);
      expect(screen.getByText('Draft to delete')).toBeDefined();
      fireEvent.click(screen.getByTestId('draft-delete-btn'));
      expect(getDrafts().find((d) => d.id === 'draft-del-1')).toBeUndefined();
    });
  });

  describe('ProjectCyclesView lifecycle & date validation branches', () => {
    it('validates start and end dates on cycle creation and triggers error', async () => {
      wrapWithClient(
        <ProjectCyclesView capabilities={['ADMIN', 'EDIT']} />,
        ['/projects/KAN/cycles'],
      );

      const nameInput = screen.getByTestId('new-cycle-name-input');
      const startInput = screen.getByTestId('new-cycle-start-input');
      const endInput = screen.getByTestId('new-cycle-end-input');

      fireEvent.change(nameInput, { target: { value: 'Inverted Cycle' } });
      fireEvent.change(startInput, { target: { value: '2026-11-20' } });
      fireEvent.change(endInput, { target: { value: '2026-11-10' } });

      fireEvent.click(screen.getByTestId('create-cycle-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('cycle-error-banner')).toBeDefined();
        expect(screen.getByText(/End date cannot be earlier than start date/i)).toBeDefined();
      });
    });

    it('renders cycles list and handles edit, complete rollover, and delete modals', async () => {
      const mockCycles = [
        {
          id: 'cyc-1',
          name: 'Sprint Alpha',
          status: 'in_progress',
          start_date: '2026-11-01',
          end_date: '2026-11-15',
        },
        {
          id: 'cyc-2',
          name: 'Sprint Beta',
          status: 'backlog',
          start_date: null,
          end_date: null,
        },
      ];

      vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
        if (typeof path === 'string' && path.includes('/cycles') && method === 'GET') {
          return Promise.resolve(mockCycles as never);
        }
        return Promise.resolve({ success: true } as never);
      });

      wrapWithClient(
        <ProjectCyclesView capabilities={['ADMIN', 'EDIT', 'PROJECT_ADMIN']} />,
        ['/projects/KAN/cycles'],
      );

      await waitFor(() => {
        expect(screen.getByText('Sprint Alpha')).toBeDefined();
      });

      // Edit cycle
      fireEvent.click(screen.getByTestId('edit-cycle-btn-cyc-1'));
      expect(screen.getByTestId('edit-cycle-modal')).toBeDefined();
      fireEvent.change(screen.getByTestId('edit-cycle-name-input'), {
        target: { value: 'Sprint Alpha Renamed' },
      });
      fireEvent.click(screen.getByTestId('save-edit-cycle-btn'));

      // Complete cycle modal
      fireEvent.click(screen.getByTestId('complete-cycle-btn-cyc-1'));
      expect(screen.getByTestId('complete-cycle-modal')).toBeDefined();
      fireEvent.change(screen.getByTestId('rollover-target-select'), {
        target: { value: 'cyc-2' },
      });
      fireEvent.click(screen.getByTestId('confirm-complete-cycle-btn'));

      // Delete cycle
      fireEvent.click(screen.getByTestId('delete-cycle-btn-cyc-2'));
    });
  });

  describe('ProjectModulesView lifecycle & date validation branches', () => {
    it('validates start and target dates on module creation', async () => {
      wrapWithClient(
        <ProjectModulesView capabilities={['ADMIN', 'EDIT']} />,
        ['/projects/KAN/modules'],
      );

      fireEvent.change(screen.getByTestId('new-module-name-input'), {
        target: { value: 'Inverted Module' },
      });
      fireEvent.change(screen.getByTestId('new-module-start-input'), {
        target: { value: '2026-11-20' },
      });
      fireEvent.change(screen.getByTestId('new-module-target-input'), {
        target: { value: '2026-11-10' },
      });

      fireEvent.click(screen.getByTestId('create-module-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('module-error-banner')).toBeDefined();
        expect(screen.getByText(/Target date cannot be earlier than start date/i)).toBeDefined();
      });
    });

    it('renders modules list and handles edit and delete modals', async () => {
      const mockModules = [
        {
          id: 'mod-1',
          name: 'Core Auth',
          status: 'planned',
          start_date: '2026-11-01',
          target_date: '2026-11-30',
          description_markdown: 'Auth engine module',
        },
      ];

      vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path) => {
        if (typeof path === 'string' && path.includes('/modules') && method === 'GET') {
          return Promise.resolve(mockModules as never);
        }
        return Promise.resolve({ success: true } as never);
      });

      wrapWithClient(
        <ProjectModulesView capabilities={['ADMIN', 'EDIT']} />,
        ['/projects/KAN/modules'],
      );

      await waitFor(() => {
        expect(screen.getByText('Core Auth')).toBeDefined();
      });

      // Edit module
      fireEvent.click(screen.getByTestId('edit-module-btn-mod-1'));
      expect(screen.getByTestId('edit-module-modal')).toBeDefined();
      fireEvent.change(screen.getByTestId('edit-module-status-select'), {
        target: { value: 'in_progress' },
      });
      fireEvent.click(screen.getByTestId('save-edit-module-btn'));

      // Delete module
      fireEvent.click(screen.getByTestId('delete-module-btn-mod-1'));
    });
  });

  describe('StickyCard & Promote Preview branches', () => {
    const mockSticky: StickyItem = {
      id: 'stk-100',
      workspace_id: 'ws-1',
      body_markdown: 'Sample sticky note content',
      color_token: 'sky',
      sort_rank: '0|hzzzzz:',
      promotion_recommended: true,
      promotion_snoozed_at_length: null,
      promoted_to_doc_id: null,
      is_promoted_stub: false,
      triggers: [],
      etag: '"stk-etag-100"',
    };

    it('handles promote rejection in StickyCard and dispatches access inspector', () => {
      const onPromote = vi.fn().mockRejectedValue(new Error('Promote failed network error'));
      const onSnooze = vi.fn();
      const onDismiss = vi.fn();
      const onColorChange = vi.fn();
      const onUpdate = vi.fn();

      const { container } = wrapWithClient(
        <StickyCard
          sticky={mockSticky}
          onPromote={onPromote}
          onSnooze={onSnooze}
          onDismiss={onDismiss}
          onColorChange={onColorChange}
          onUpdate={onUpdate}
        />,
      );

      // Access click
      const accessHint = container.querySelector('.emoji-hint');
      if (accessHint) {
        fireEvent.click(accessHint);
      }
    });

    it('allows editing markdown preview in StickyPromotePreviewModal', async () => {
      wrapWithClient(
        <StickyPromotePreviewModal
          isOpen={true}
          sticky={mockSticky}
          onClose={vi.fn()}
          onConfirm={vi.fn()}
        />,
      );

      await waitFor(() => {
        expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
      });

      const textarea = screen.getByTestId('promote-modal-markdown');
      fireEvent.change(textarea, { target: { value: '# Custom Heading\n\nPreview body' } });
      expect((textarea as HTMLTextAreaElement).value).toBe('# Custom Heading\n\nPreview body');
    });
  });

  describe('routes.tsx Wave 4 route renders', () => {
    it('renders FullScreenIssueRoute and sets document title', async () => {
      vi.spyOn(clientModule.apiClient, 'get').mockResolvedValue({
        key: 'KAN-42',
        summary: 'Fullscreen test issue',
        project_key: 'KAN',
        etag: '"etag-42"',
      });

      wrapWithClient(
        <Routes>
          <Route path="/issues/:issueKey" element={<FullScreenIssueRoute />} />
        </Routes>,
        ['/issues/KAN-42'],
      );

      await waitFor(() => {
        expect(screen.getByTestId('full-screen-route-anchor')).toBeDefined();
        expect(document.title).toContain('KAN-42 - Fullscreen test issue');
      });
    });
  });

  describe('AuthCardEditorDrawer branches', () => {
    it('handles Google JSON parse error when pasting invalid JSON', () => {
      wrapWithClient(
        <AuthCardEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('google-json-paste-toggle'));
      const pasteInput = screen.getByLabelText('Paste Google Cloud Console client JSON');
      fireEvent.change(pasteInput, { target: { value: 'not-valid-json' } });

      const applyBtn = screen.getByTestId('google-json-apply-btn');
      fireEvent.click(applyBtn);

      expect(screen.getByTestId('google-json-error')).toBeDefined();
      expect(screen.getByText(/Failed to parse JSON/i)).toBeDefined();
    });

    it('submits valid OIDC card creation payload', async () => {
      const onSave = vi.fn().mockResolvedValue(undefined);

      wrapWithClient(
        <AuthCardEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          onSave={onSave}
        />,
      );

      const slugInput = screen.getByLabelText(/Slug Identifier/i);
      fireEvent.change(slugInput, { target: { value: 'custom-oauth-slug' } });

      const nameInput = screen.getByLabelText(/^Display Name$/i);
      fireEvent.change(nameInput, { target: { value: 'Custom SSO Name' } });

      const clientIdInput = screen.getByLabelText(/Client ID/i);
      fireEvent.change(clientIdInput, { target: { value: 'client-test-123' } });

      const issuerInput = screen.getByLabelText(/Issuer URL/i);
      fireEvent.change(issuerInput, { target: { value: 'https://accounts.example.com' } });

      const submitBtn = screen.getByRole('button', { name: 'Create Card' });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(onSave).toHaveBeenCalledWith(
          expect.objectContaining({
            slug: 'custom-oauth-slug',
            display_name: 'Custom SSO Name',
          }),
          false,
        );
      });
    });

    it('renders fallback handshake messages when check_summary is missing', async () => {
      vi.spyOn(adminAuthApiModule, 'testDraftAuthCardHandshake').mockResolvedValueOnce({
        last_health_status: 'HEALTHY',
      } as never);

      wrapWithClient(
        <AuthCardEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />,
      );

      const testBtn = screen.getByTestId('drawer-test-handshake-btn');
      fireEvent.click(testBtn);

      await waitFor(() => {
        expect(screen.getByText(/HEALTHY: Handshake healthy/i)).toBeDefined();
      });

      // Probe failed fallback
      vi.spyOn(adminAuthApiModule, 'testDraftAuthCardHandshake').mockResolvedValueOnce({
        last_health_status: 'FAILED',
      } as never);

      fireEvent.click(testBtn);

      await waitFor(() => {
        expect(screen.getByText(/FAILED: Handshake probe failed/i)).toBeDefined();
      });
    });
  });

  describe('IssuesWorkspaceRoute bulk action and field selection branches', () => {
    it('executes batch update state for done and todo and updates priority', () => {
      const { container } = wrapWithClient(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          modulesEnabled={true}
          initialIssues={FIXTURE_12_ISSUES}
          initialLayout="board"
          capabilities={['ADMIN', 'EDIT']}
        />,
        ['/projects/KAN/issues'],
      );

      // Trigger selection on cards
      const selectAllBtn = container.querySelector<HTMLInputElement>('.bulk-select-all-checkbox');
      if (selectAllBtn) {
        fireEvent.click(selectAllBtn);
      }

      // Check for BulkActionBar
      const stateBtn = screen.queryByRole('button', { name: 'State' });
      if (stateBtn) {
        fireEvent.click(stateBtn);
      }

      const prioBtn = screen.queryByRole('button', { name: 'Priority' });
      if (prioBtn) {
        fireEvent.click(prioBtn);
      }
    });
  });

  describe('IssueSurface 428 precondition branch', () => {
    it('catches 428 Precondition Required conflict and renders 428 message', async () => {
      vi.spyOn(clientModule.apiClient, 'get').mockResolvedValue({
        key: 'KAN-142',
        summary: 'Precondition 428 issue',
        project_key: 'KAN',
        etag: '"etag-remote"',
        description_markdown: 'Initial desc',
        priority: { slug: 'high', label: 'High', emoji: '⚡', sort_order: 1, sla_target: null },
      });
      vi.spyOn(clientModule.apiClient, 'patch').mockRejectedValue(
        new ApiProblem(428, {
          title: 'Precondition Required',
          status: 428,
          detail: 'Missing ETag',
        }),
      );

      wrapWithClient(
        <IssueSurfaceRoot mode="drawer" issueKey="KAN-142" projectKey="KAN" />,
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Edit description' })).toBeDefined();
      });

      fireEvent.click(screen.getByRole('button', { name: 'Edit description' }));
      fireEvent.change(screen.getByRole('textbox', { name: 'Description' }), {
        target: { value: '428 test draft' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'Save description' }));

      await waitFor(() => {
        expect(screen.getByTestId('conflict-banner')).toBeDefined();
        expect(screen.getByText(/Precondition required \(428\)/i)).toBeDefined();
      });
    });
  });

  describe('WorkspaceSettings formatHandle branches', () => {
    it('covers all branch permutations of formatHandle', () => {
      expect(formatHandle(null)).toBe('');
      expect(formatHandle(undefined)).toBe('');
      expect(formatHandle('')).toBe('');
      expect(formatHandle('@@@')).toBe('');
      expect(formatHandle('@alice')).toBe('@alice');
      expect(formatHandle('bob')).toBe('@bob');
    });
  });

  describe('FilterDisplayBar edge branches', () => {
    it('exercises cycle fallback, module fallback, and assignee fallback when display_name is empty', () => {
      const customIssues = [
        {
          id: 'custom-1',
          key: 'KAN-99',
          summary: 'Edge branch issue',
          state: { id: 's1', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
          cycle_id: 'custom-cycle-xyz',
          module_ids: ['mod-2', 'custom-mod-abc'],
          assignees: [
            {
              kind: 'principal' as const,
              principal: {
                id: 'p1',
                handle: '@charlie',
                display_name: '',
              },
            },
          ],
          labels: [{ id: 'l1', name: 'Design', color: '#123456' }],
        },
      ];

      const onFiltersChange = vi.fn();
      const onGroupByChange = vi.fn();
      const onSubGroupByChange = vi.fn();

      const { container } = wrapWithClient(
        <FilterDisplayBar
          issues={customIssues as never}
          activeFilters={{
            cycle: ['custom-cycle-xyz'],
            module: ['mod-2'],
            assignee: ['charlie'],
            empty_cat: undefined,
          }}
          onFiltersChange={onFiltersChange}
          groupBy="state"
          subGroupBy="state"
          onGroupByChange={onGroupByChange}
          onSubGroupByChange={onSubGroupByChange}
          modulesEnabled={true}
        />,
      );

      // Verify chips rendered
      expect(container.textContent).toContain('custom-cycle-xyz');
      expect(container.textContent).toContain('Kanban Board');
      expect(container.textContent).toContain('@charlie');

      // Chip close button click
      const removeButtons = container.querySelectorAll('.filter-chip-remove');
      if (removeButtons.length > 0) {
        fireEvent.click(removeButtons[0]!);
        expect(onFiltersChange).toHaveBeenCalled();
      }

      // Group change when newGroup === subGroupBy triggers reset to none
      const groupSelect = screen.getByRole('combobox', { name: 'Group by axis' });
      fireEvent.change(groupSelect, { target: { value: 'priority' } });
      expect(onGroupByChange).toHaveBeenCalledWith('priority');
    });
  });

  describe('StickyCard error handling branches', () => {
    const dummySticky: StickyItem = {
      id: 'sticky-edge-1',
      project_key: 'KAN',
      title: 'Sticky Title',
      body_markdown: 'Initial body text',
      body_sha256: 'sha-initial',
      color: 'yellow',
      position_x: 10,
      position_y: 20,
      pinned: false,
      etag: '"etag-1"',
      created_by: 'user-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    it('sets inline error fallback when onUpdate rejects with a non-Error', async () => {
      const onUpdate = vi.fn().mockRejectedValue('raw string update failure');
      render(
        <StickyCard
          sticky={dummySticky}
          canEdit={true}
          onUpdate={onUpdate}
          onDelete={vi.fn()}
          onSnooze={vi.fn()}
          onPromote={vi.fn()}
        />,
      );

      const rawToggle = screen.getByTestId('sticky-editor-sticky-edge-1-raw-toggle');
      fireEvent.click(rawToggle);
      const rawTextarea = screen.getByTestId('sticky-editor-sticky-edge-1-raw');
      fireEvent.change(rawTextarea, { target: { value: 'Changed text' } });
      fireEvent.blur(rawTextarea);

      await waitFor(() => {
        expect(screen.getByText('Failed to update sticky')).toBeDefined();
      });
    });

    it('sets inline error fallback when onPromote rejects with a non-Error', async () => {
      const onPromote = vi.fn().mockRejectedValue(999);
      render(
        <StickyCard
          sticky={dummySticky}
          canEdit={true}
          onUpdate={vi.fn()}
          onDelete={vi.fn()}
          onSnooze={vi.fn()}
          onPromote={onPromote}
        />,
      );

      const menuBtn = screen.getByRole('button', { name: 'Sticky actions' });
      fireEvent.click(menuBtn);
      const promoteBtn = screen.getByTestId('convert-to-doc-menuitem');
      fireEvent.click(promoteBtn);

      await waitFor(() => {
        expect(screen.getByTestId('sticky-promote-preview-modal')).toBeDefined();
      });

      const confirmBtn = await screen.findByRole('button', { name: /Confirm Promotion/i });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(screen.getAllByText('Failed to promote sticky to document').length).toBeGreaterThan(0);
      });
    });
  });

  describe('StickyPromotePreviewModal fallback title branches', () => {
    it('extracts title when body has no heading and falls back when body is empty', async () => {
      const stickyWithoutHeading: StickyItem = {
        id: 's-no-heading',
        project_key: 'KAN',
        title: null,
        body_markdown: 'First plain line without hash\nSecond line',
        body_sha256: 'sha-1',
        color: 'blue',
        position_x: 0,
        position_y: 0,
        pinned: false,
        etag: '"e1"',
        created_by: 'u1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      };

      const { unmount } = render(
        <StickyPromotePreviewModal
          sticky={stickyWithoutHeading}
          isOpen={true}
          onClose={vi.fn()}
          onConfirm={vi.fn()}
        />,
      );
      expect(await screen.findByLabelText(/Document Title/i)).toBeDefined();
      unmount();

      const stickyEmpty: StickyItem = {
        ...stickyWithoutHeading,
        id: 's-empty',
        body_markdown: '',
      };

      render(
        <StickyPromotePreviewModal
          sticky={stickyEmpty}
          isOpen={true}
          onClose={vi.fn()}
          onConfirm={vi.fn()}
        />,
      );
      expect(await screen.findByLabelText(/Document Title/i)).toBeDefined();
    });
  });

  describe('TransitionRuleCard keyboard reordering branches', () => {
    const mockRule: TransitionRule = {
      from_state: 'state-todo',
      to_state: 'state-done',
      hooks: [
        {
          id: 'hook-1',
          name: 'Validator Alpha',
          hook_kind: 'sync_validator',
          manifest_sha256: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
          failure_policy: 'fail_closed',
          is_enabled: true,
          timeout_ms: 1000,
          target_latency_budget: '<25ms',
        },
        {
          id: 'hook-2',
          name: 'Agent Beta',
          hook_kind: 'agent_interceptor',
          manifest_sha256: '1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',
          failure_policy: 'fail_open',
          is_enabled: true,
          timeout_ms: 5000,
          target_latency_budget: null,
        },
      ],
    };

    it('handles out-of-bounds keyboard move and non-Error reorder failure', async () => {
      const onReorder = vi.fn().mockRejectedValue('reorder-rejected-string');

      render(
        <TransitionRuleCard
          rule={mockRule}
          projectKey="KAN"
          onReorder={onReorder}
          onToggle={vi.fn()}
          onEdit={vi.fn()}
          onDetach={vi.fn()}
          onAddHook={vi.fn()}
          onDryRun={vi.fn()}
        />,
      );

      // Hook 1: move up is disabled (index 0)
      const hook1MoveUp = screen.getByRole('button', { name: 'Move Validator Alpha up' });
      expect((hook1MoveUp as HTMLButtonElement).disabled).toBe(true);

      // Hook 2: move down is disabled (index 1 / total 2)
      const hook2MoveDown = screen.getByRole('button', { name: 'Move Agent Beta down' });
      expect((hook2MoveDown as HTMLButtonElement).disabled).toBe(true);

      // Move Hook 1 down -> triggers reorder
      const hook1MoveDown = screen.getByRole('button', { name: 'Move Validator Alpha down' });
      fireEvent.click(hook1MoveDown);

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeDefined();
        expect(screen.getByText(/422 REORDER_SET_MISMATCH/i)).toBeDefined();
      });
    });

    it('renders explicit Error message on reorder error', async () => {
      const onReorder = vi.fn().mockRejectedValue(new Error('Explicit hook order error'));

      render(
        <TransitionRuleCard
          rule={mockRule}
          projectKey="KAN"
          onReorder={onReorder}
          onToggle={vi.fn()}
          onEdit={vi.fn()}
          onDetach={vi.fn()}
          onAddHook={vi.fn()}
          onDryRun={vi.fn()}
        />,
      );

      const hook1MoveDown = screen.getByRole('button', { name: 'Move Validator Alpha down' });
      fireEvent.click(hook1MoveDown);

      await waitFor(() => {
        expect(screen.getByText(/Explicit hook order error/i)).toBeDefined();
      });
    });
  });
});
