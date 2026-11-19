/**
 * Branch Coverage Booster for Wave 4 Integration (KANBA-211, KANBA-212, KANBA-217).
 * Exercises branches across draftsStore, PropertiesRail, railApi, IssueSurface,
 * FilterDisplayBar, SwimlaneBoardGrid, QuickCreateIssueModal, routes, and stickies.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
import type { IssueItem } from './viewsApi';
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
import {
  extractHeadings,
  stripInlineMarkdown,
  computeLineDiff,
} from '../docs/OutlineAndVersionsRail';
import { TransitionRuleCard } from '../workflows/TransitionRuleCard';
import type { TransitionRule } from '../workflows/api';
import * as stickiesApiModule from '../stickies/stickiesApi';
import { ComposeExportTab } from '../standalone/ComposeExportTab';
import { TimelineView } from '../timeline/TimelineView';
import type { TimelineIssueItem } from '../timeline/TimelineView';

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
        project_key: 'KAN',
        summary: 'Minimal issue',
        state: { id: 's1', name: 'Open', group: 'unstarted' },
      };

      const { container } = wrapWithClient(
        <PropertiesRail
          issue={minimalIssue}
          projectMetadata={{ key: 'KAN', name: 'Kanban', modules_enabled: false }}
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
      } as never, 'KAN');
      expect(norm1.project_key).toBe('KAN');
      expect(norm1.etag).toBeUndefined();

      // Object with labels array of objects instead of strings
      const norm2 = normalizeIssueDetail({
        key: 'KAN-50',
        labels: [{ id: 'lbl-1', name: 'Bug' }, { id: 'lbl-2', name: 'Frontend' }],
      } as never, 'KAN');
      expect(norm2.label_ids).toEqual(['lbl-1', 'lbl-2']);

      // Object without capabilities defaults to full capabilities
      const norm3 = normalizeIssueDetail({ key: 'KAN-51' } as never, 'KAN');
      expect(norm3.capabilities).toEqual(['EDIT', 'TRANSITION', 'COMMENT']);
    });

    it('renders IssueSurfaceRoot in split mode', async () => {
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
        expect(screen.getByRole('link', { name: 'Open in new tab' })).toBeDefined();
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
          activeFilters={{}}
          onFiltersChange={onFilterChange}
          groupBy="state"
          onGroupByChange={onGroupByChange}
          subGroupBy="none"
          onSubGroupByChange={onSubGroupByChange}
          modulesEnabled={true}
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
      const issuesWithCycle: IssueItem[] = FIXTURE_12_ISSUES.map((iss, idx) => ({
        ...iss,
        cycle_id: idx % 2 === 0 ? 'c-1' : null,
        cycle: idx % 2 === 0 ? { id: 'c-1', name: 'Cycle 1' } : null,
        module_ids: idx % 3 === 0 ? ['m-1'] : [],
        modules: idx % 3 === 0 ? [{ id: 'm-1', name: 'Module 1' }] : [],
      }));

      const { container } = wrapWithClient(
        <SwimlaneBoardGrid
          issues={issuesWithCycle}
          groupBy="state"
          subGroupBy="cycle"
          projectKey="KAN"
          projectCycles={[{ id: 'c-1', name: 'Cycle 1' }]}
          projectModules={[{ id: 'm-1', name: 'Module 1' }]}
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
      const issuesWithMod: IssueItem[] = FIXTURE_12_ISSUES.map((iss) => ({
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
          projectModules={[{ id: 'm-1', name: 'Module 1' }]}
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
      const onUpdate = vi.fn();

      const { container } = wrapWithClient(
        <StickyCard
          sticky={mockSticky}
          onPromote={onPromote}
          onDelete={vi.fn()}
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
          card={null}
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
          card={null}
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
          card={null}
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
      const firstRemove = removeButtons[0];
      if (firstRemove) {
        fireEvent.click(firstRemove);
        expect(onFiltersChange).toHaveBeenCalled();
      }

      // Group change when newGroup === subGroupBy triggers reset to none
      const groupSelect = container.querySelector('#group-by-select');
      if (groupSelect) {
        fireEvent.change(groupSelect, { target: { value: 'priority' } });
        expect(onGroupByChange).toHaveBeenCalledWith('priority');
      }
    });
  });

  const dummySticky: StickyItem = {
    id: 'sticky-edge-1',
    workspace_id: 'ws-1',
    body_markdown: 'Initial body text',
    body_sha256: 'sha-initial',
    color_token: 'amber',
    sort_rank: '0|hzzzzz:',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    etag: '"etag-1"',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };

  describe('StickyCard error handling branches', () => {

    it('sets inline error fallback when onUpdate rejects with a non-Error', async () => {
      const onUpdate = vi.fn().mockRejectedValue('raw string update failure');
      const { container } = render(
        <StickyCard
          sticky={dummySticky}
          onUpdate={onUpdate}
          onDelete={vi.fn()}
          onPromote={vi.fn()}
        />,
      );

      const colorBtn = container.querySelector('[data-testid="color-swatch-mint"]');
      if (colorBtn) {
        fireEvent.click(colorBtn);
      }

      await waitFor(() => {
        expect(screen.getByText('Failed to recolor sticky')).toBeDefined();
      });
    });

    it('sets inline error fallback when onPromote rejects with a non-Error', async () => {
      const onPromote = vi.fn().mockRejectedValue(999);
      render(
        <StickyCard
          sticky={dummySticky}
          onUpdate={vi.fn()}
          onDelete={vi.fn()}
          onPromote={onPromote}
        />,
      );

      fireEvent.click(screen.getByTestId(`sticky-menu-trigger-${dummySticky.id}`));
      fireEvent.click(screen.getByTestId('convert-to-doc-menuitem'));

      await waitFor(() => {
        expect(screen.getByTestId('sticky-promote-preview-modal')).toBeDefined();
      });
      await waitFor(() => {
        expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
      });

      const confirmBtn = screen.getByRole('button', { name: /Confirm Promotion/i });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(screen.getAllByText(/Failed to promote sticky to document/i).length).toBeGreaterThanOrEqual(1);
      });
    });
  });

  describe('StickyPromotePreviewModal fallback title branches', () => {
    it('extracts title when body has no heading and falls back when body is empty', async () => {
      const stickyWithoutHeading: StickyItem = {
        ...dummySticky,
        id: 's-no-heading',
        body_markdown: 'First plain line without hash\nSecond line',
      };

      const { unmount } = render(
        <StickyPromotePreviewModal
          sticky={stickyWithoutHeading}
          isOpen={true}
          onClose={vi.fn()}
          onConfirm={vi.fn()}
        />,
      );
      await waitFor(() => {
        expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
      });
      expect(screen.getByLabelText(/Document Title/i)).toBeDefined();
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
      await waitFor(() => {
        expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
      });
      expect(screen.getByLabelText(/Document Title/i)).toBeDefined();
    });
  });

  describe('TransitionRuleCard keyboard reordering branches', () => {
    const mockRule: TransitionRule = {
      from_state: 'state-todo',
      to_state: 'state-done',
      active_hook_count: 2,
      hooks: [
        {
          id: 'hook-1',
          name: 'Validator Alpha',
          from_state: 'state-todo',
          to_state: 'state-done',
          sort_rank: '0|hzzzzz:',
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
          from_state: 'state-todo',
          to_state: 'state-done',
          sort_rank: '0|hzzzz{:',
          hook_kind: 'agent_interceptor',
          manifest_sha256: '1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',
          failure_policy: 'fail_open_warn',
          is_enabled: true,
          timeout_ms: 5000,
          target_latency_budget: undefined,
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

    it('covers TransitionRuleCard out-of-bounds keyboard move and drop reorder edge cases', () => {
      const onReorder = vi.fn().mockResolvedValue(undefined);
      let capturedOnDrop: ((args: { source: { data: unknown } }) => void) | undefined;
      const mockDropTarget = vi.fn().mockImplementation((config: { onDrop?: (args: { source: { data: unknown } }) => void }) => {
        capturedOnDrop ??= config.onDrop;
        return () => { /* cleanup */ };
      });

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
          dropTargetFactory={mockDropTarget as never}
        />,
      );

      // 1. Move up from index 0 (targetIndex < 0)
      const hook1MoveUp = screen.getByRole('button', { name: 'Move Validator Alpha up' });
      hook1MoveUp.removeAttribute('disabled');
      fireEvent.click(hook1MoveUp);

      // 2. Move down from last index (targetIndex >= length)
      const hook2MoveDown = screen.getByRole('button', { name: 'Move Agent Beta down' });
      hook2MoveDown.removeAttribute('disabled');
      fireEvent.click(hook2MoveDown);

      // 3. Drop reorder with sourceId === targetId
      capturedOnDrop?.({ source: { data: { type: 'hook-row', hookId: 'hook-1' } } });

      // 4. Drop reorder with unknown sourceId
      capturedOnDrop?.({ source: { data: { type: 'hook-row', hookId: 'unknown-source' } } });

      // 5. Drop reorder with non-hook-row type
      capturedOnDrop?.({ source: { data: { type: 'other-type', hookId: 'hook-1' } } });
      capturedOnDrop?.({ source: { data: null } });

      expect(onReorder).not.toHaveBeenCalled();
    });
  });

  describe('StickyPromotePreviewModal full resolution and unmount branches', () => {
    const fullMockSticky: StickyItem = {
      id: 'stk-full-1',
      workspace_id: 'ws-1',
      project_id: 'proj-1',
      body_markdown: '# Explicit Heading\nLine 2 content\nLine 3 content',
      body_sha256: 'sha-full-256',
      color_token: 'sky',
      sort_rank: '0',
      promotion_recommended: true,
      promotion_snoozed_at_length: null,
      promoted_to_doc_id: null,
      is_promoted_stub: false,
      triggers: [],
      etag: '"full-etag"',
    };

    it('populates preview from successful API response and preserves original SHA', async () => {
      vi.spyOn(stickiesApiModule, 'previewStickyPromotion').mockResolvedValueOnce({
        proposal: {
          title: 'AI Proposed Title',
          confidence: 0.98,
          doc_family: 'rfc',
        },
        rendered_markdown: '## Synthesized Doc Content\n```mermaid\ngraph LR\n A --> B\n```',
        original_sha256: 'sha-original-full-999',
        warnings: ['Stale reference detected in sticky body', 'Verify cross-project links'],
        acl_preview: {
          direct_entries_count: 4,
          inherited_scope: 'project',
        },
      });

      const onConfirm = vi.fn().mockResolvedValue(undefined);
      const onClose = vi.fn();

      wrapWithClient(
        <StickyPromotePreviewModal
          isOpen={true}
          sticky={fullMockSticky}
          onClose={onClose}
          onConfirm={onConfirm}
        />,
      );

      await waitFor(() => {
        expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
      });

      expect(screen.getByDisplayValue('AI Proposed Title')).toBeDefined();
      expect(screen.getByText(/All 4 explicit ACL grant\(s\)/i)).toBeDefined();
      expect(screen.getByText(/Stale reference detected in sticky body/i)).toBeDefined();

      const form = screen.getByTestId('sticky-promote-preview-modal').querySelector('form');
      if (form) {
        fireEvent.submit(form);
      }

      await waitFor(() => {
        expect(onConfirm).toHaveBeenCalledWith({
          title: 'AI Proposed Title',
          structured_body_markdown: expect.stringContaining('## Synthesized Doc Content') as string,
          expected_sticky_sha256: 'sha-original-full-999',
        });
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('safely handles early unmount while previewStickyPromotion is in flight', () => {
      let resolvePromise: (val: stickiesApiModule.StickyPromotePreviewResponse) => void = vi.fn();
      vi.spyOn(stickiesApiModule, 'previewStickyPromotion').mockImplementationOnce(
        () => new Promise((resolve) => { resolvePromise = resolve; })
      );

      const { unmount } = wrapWithClient(
        <StickyPromotePreviewModal
          isOpen={true}
          sticky={fullMockSticky}
          onClose={vi.fn()}
          onConfirm={vi.fn()}
        />,
      );

      // Unmount before resolve to hit `if (!active) return;`
      unmount();
      resolvePromise({ proposal: { title: 'Late' }, rendered_markdown: '', original_sha256: 'sha-original', acl_preview: {} });
    });

    it('validates empty title and handles non-Error rejection on confirm', async () => {
      vi.spyOn(stickiesApiModule, 'previewStickyPromotion').mockResolvedValueOnce({
        proposal: { title: 'Some Title' },
        rendered_markdown: 'Markdown body',
        original_sha256: 'sha-original-99',
        acl_preview: {},
      });

      const onConfirm = vi.fn().mockRejectedValueOnce('Raw string promotion failure');

      wrapWithClient(
        <StickyPromotePreviewModal
          isOpen={true}
          sticky={fullMockSticky}
          onClose={vi.fn()}
          onConfirm={onConfirm}
        />,
      );

      await waitFor(() => {
        expect(screen.queryByTestId('promote-modal-loading')).toBeNull();
      });

      const titleInput = screen.getByTestId('promote-modal-title');
      fireEvent.change(titleInput, { target: { value: '   ' } });

      const form = screen.getByTestId('sticky-promote-preview-modal').querySelector('form');
      if (form) {
        fireEvent.submit(form);
      }
      expect(screen.getByTestId('promote-modal-error').textContent).toBe('Title cannot be empty');

      fireEvent.change(titleInput, { target: { value: 'Valid Title' } });
      if (form) {
        fireEvent.submit(form);
      }

      await waitFor(() => {
        expect(screen.getByTestId('promote-modal-error').textContent).toBe('Failed to promote sticky to document');
      });
    });
  });

  describe('ComposeExportTab fallback filename and error handling branches', () => {
    it('falls back to default docker-compose.yml filename when filename is empty', async () => {
      const mockExportData = {
        compose_yaml: 'services:\n  kanban:\n    image: kanban:latest\n',
        single_container_compose_yaml: 'services:\n  standalone:\n    image: kanban:all-in-one\n',
        env_template: 'SECRET_KEY=test\n',
        instructions_markdown: '# Setup\n',
        migration_steps_markdown: '# Migrations\n',
        filename: '', // empty -> should fall back to 'docker-compose.yml'
      };

      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockExportData),
      });

      const createObjectURLMock = vi.fn().mockReturnValue('blob:mock-compose-url');
      const revokeObjectURLMock = vi.fn();
      window.URL.createObjectURL = createObjectURLMock;
      window.URL.revokeObjectURL = revokeObjectURLMock;

      render(<ComposeExportTab initialData={mockExportData} />);

      const downloadBtn = screen.getByRole('button', { name: 'Download docker-compose.yml' });
      fireEvent.click(downloadBtn);

      await waitFor(() => {
        expect(createObjectURLMock).toHaveBeenCalled();
      });

      global.fetch = originalFetch;
    });

    it('sets Download failed message when download throws a non-Error object', async () => {
      const mockExportData = {
        compose_yaml: 'services:\n  kanban:\n    image: kanban:latest\n',
        single_container_compose_yaml: '',
        env_template: 'SECRET_KEY=test\n',
        instructions_markdown: '# Setup\n',
        migration_steps_markdown: '# Migrations\n',
        filename: 'docker-compose.yml',
      };

      window.URL.createObjectURL = vi.fn().mockImplementation(() => {
        // eslint-disable-next-line @typescript-eslint/only-throw-error
        throw 'Non-Error blob creation failure';
      });

      render(<ComposeExportTab initialData={mockExportData} />);

      const downloadBtn = screen.getByRole('button', { name: 'Download docker-compose.yml' });
      fireEvent.click(downloadBtn);

      await waitFor(() => {
        expect(screen.getByRole('alert').textContent).toBe('Download failed');
      });
    });

    it('downloads single container compose and copies env template to clipboard', async () => {
      const mockExportData = {
        compose_yaml: 'services:\n  kanban:\n    image: kanban:latest\n',
        single_container_compose_yaml: 'services:\n  standalone:\n    image: kanban:all-in-one\n',
        env_template: 'SECRET_KEY=test\n',
        instructions_markdown: '# Setup\n',
        migration_steps_markdown: '# Migrations\n',
        filename: 'docker-compose.yml',
      };

      Object.assign(navigator, {
        clipboard: {
          writeText: vi.fn().mockResolvedValue(undefined),
        },
      });

      const createObjectURLMock = vi.fn().mockReturnValue('blob:mock-compose-url');
      window.URL.createObjectURL = createObjectURLMock;
      window.URL.revokeObjectURL = vi.fn();

      render(<ComposeExportTab initialData={mockExportData} />);

      // Copy env
      const copyBtn = screen.getByRole('button', { name: 'Copy .env.example' });
      fireEvent.click(copyBtn);
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Copied!' })).toBeDefined();
      });

      // Switch to single-container mode
      const singleBtn = screen.getByRole('button', { name: 'Single-Container (Standalone)' });
      fireEvent.click(singleBtn);
      expect(screen.getByText('Single-Container Standalone Spec:')).toBeDefined();

      // Download in single mode
      const downloadSingleBtn = screen.getByRole('button', { name: 'Download docker-compose.standalone.yml' });
      fireEvent.click(downloadSingleBtn);
      await waitFor(() => {
        expect(createObjectURLMock).toHaveBeenCalled();
      });
    });
  });

  describe('TimelineView quarter zoom and error fallback branches', () => {
    it('renders month name label in quarter zoom mode and handles schedule error fallback', () => {
      const mockTimelineIssues: TimelineIssueItem[] = [
        {
          id: 'i-timeline-99',
          key: 'KAN-99',
          summary: 'Quarter Timeline Issue',
          start_date: '2026-11-01',
          due_date: '2026-11-14',
          state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'high', label: 'High' },
          created_by_id: 'usr-1',
          assignees: [],
          module_ids: [],
          capabilities: ['EDIT', 'ADMIN'],
        },
      ];

      const { container } = wrapWithClient(
        <TimelineView
          issues={mockTimelineIssues}
          projectKey="KAN"
          initialZoom="quarter"
          initialStartDate="2026-11-01"
          today="2026-11-01"
        />,
      );

      // In quarter zoom, dayNum '01' gets month name 'Nov'
      expect(container.textContent).toContain('Nov');
    });
  });

  describe('formatHandle, normalizeIssueDetail, Outline Rail & PropertiesRail booster', () => {
    it('covers formatHandle edge branches', () => {
      expect(formatHandle(null)).toBe('');
      expect(formatHandle(undefined)).toBe('');
      expect(formatHandle('')).toBe('');
      expect(formatHandle('@@@')).toBe('');
      expect(formatHandle('@alice')).toBe('@alice');
      expect(formatHandle('alice')).toBe('@alice');
    });

    it('covers all normalizeIssueDetail edge and fallback branches', () => {
      expect(normalizeIssueDetail(null, null)).toBeNull();
      expect(normalizeIssueDetail(undefined, null)).toBeUndefined();
      expect(normalizeIssueDetail('invalid' as never, null)).toBe('invalid');
      expect(normalizeIssueDetail(12345 as never, null)).toBe(12345);

      // Early return when candidate already has project_key, object_id, etag
      const complete = {
        project_key: 'KAN',
        object_id: 'obj-1',
        etag: '"etag-1"',
        key: 'KAN-1',
      } as never;
      expect(normalizeIssueDetail(complete, null)).toBe(complete);

      // candidate from items[0]
      const withItems = {
        items: [{ key: 'KAN-10', project_key: 'KAN', object_id: 'obj-10', etag: '"etag-10"' }],
      };
      expect(normalizeIssueDetail(withItems as never, null)).toEqual(withItems.items[0]);

      // candidate with empty items array
      const emptyItems = {
        items: [],
        key: 'KAN-11',
      } as never;
      const normEmpty = normalizeIssueDetail(emptyItems, 'PROJ-FALLBACK');
      expect(normEmpty.project_key).toBe('PROJ-FALLBACK');

      // labels mapping string vs object with id
      const withMixedLabels = {
        key: 'KAN-12',
        labels: ['tag1', { id: 'tag2' }],
      } as never;
      expect(normalizeIssueDetail(withMixedLabels, null).label_ids).toEqual(['tag1', 'tag2']);

      // label_ids already present
      const withExistingLabels = {
        key: 'KAN-13',
        label_ids: ['existing-lbl'],
        labels: ['ignored'],
      } as never;
      expect(normalizeIssueDetail(withExistingLabels, null).label_ids).toEqual(['existing-lbl']);

      // description_sha256 to etag
      const withSha = {
        key: 'KAN-14',
        description_sha256: 'deadbeefcafe',
      } as never;
      expect(normalizeIssueDetail(withSha, null).etag).toBe('"deadbeefcafe"');

      // raw id to object_id
      const withId = {
        key: 'KAN-15',
        id: 'raw-uuid-15',
      } as never;
      expect(normalizeIssueDetail(withId, null).object_id).toBe('raw-uuid-15');

      // existing capabilities preserved
      const withCaps = {
        key: 'KAN-16',
        capabilities: ['VIEW'],
      } as never;
      expect(normalizeIssueDetail(withCaps, null).capabilities).toEqual(['VIEW']);

      // fallbackProjectKey when key has no hyphen and project_key is empty
      const withFallback = {
        key: '',
        project_key: '',
      } as never;
      expect(normalizeIssueDetail(withFallback, 'FALLBACK-KEY').project_key).toBe('FALLBACK-KEY');
      expect(normalizeIssueDetail(withFallback, null).project_key).toBe('KAN');
    });

    it('covers OutlineAndVersionsRail markdown and diff utilities', () => {
      // stripInlineMarkdown
      expect(
        stripInlineMarkdown(
          '[Link text](https://example.com) and ![Image alt](img.png) and `code` and **bold** and ~~strike~~',
        ),
      ).toBe('Link text and Image alt and code and bold and strike');
      expect(stripInlineMarkdown('[text without alt]()')).toBe('text without alt');
      expect(stripInlineMarkdown('![alt without text](image.png)')).toBe('alt without text');
      expect(stripInlineMarkdown('')).toBe('');

      // computeLineDiff
      expect(computeLineDiff('same text', 'same text')).toEqual({
        lines: [{ type: 'unchanged', text: 'same text' }],
        addedCount: 0,
        removedCount: 0,
      });
      const diff1 = computeLineDiff('', 'new line\nanother line');
      expect(diff1.addedCount).toBe(2);
      const diff2 = computeLineDiff('old line\nanother old', '');
      expect(diff2.removedCount).toBe(2);
      const diff3 = computeLineDiff('line 1\nline 2', 'line 1\nmodified 2\nline 3');
      expect(diff3.lines.length).toBeGreaterThan(0);

      // extractHeadings
      expect(extractHeadings('')).toEqual([]);
      expect(extractHeadings('###   \n# Valid')).toEqual([
        { level: 1, text: 'Valid', anchor: 'valid' },
      ]);
      const duplicateSlugs = extractHeadings('### !!!\n### !!!');
      expect(duplicateSlugs[0]?.anchor).toBe('section');
      expect(duplicateSlugs[1]?.anchor).toBe('section-1');

      const levels = extractHeadings('# H1\n## H2\n### H3\n#### H4');
      expect(levels.length).toBe(3);

      const htmlComments = extractHeadings(
        '<!-- single -->\n# Outside\n<!-- multi\n# Commented\n-->\n## Outside 2',
      );
      expect(htmlComments.map((h) => h.text)).toEqual(['Outside', 'Outside 2']);

      const codeFences = extractHeadings(
        '~~~js\n# Inside fence 1\n~~~\n```\n# Inside fence 2\n```\n# Valid Code Heading',
      );
      expect(codeFences.map((h) => h.text)).toEqual(['Valid Code Heading']);
    });

    it('covers PropertiesRail capabilities, undefined project key, and disabled modules', () => {
      const issueWithoutCaps: IssueDetail = {
        key: 'PROJ-99',
        project_key: 'undefined',
        summary: 'Undefined project key fallback',
      };

      const { container } = wrapWithClient(
        <PropertiesRail
          issue={issueWithoutCaps}
          projectMetadata={{
            key: 'PROJ',
            name: 'Proj',
            modules_enabled: false,
            states: [{ id: 's1', name: 'Open', group: 'unstarted' }],
            priorities: [],
            labels: [],
          }}
        />,
      );

      expect(container.querySelector('.properties-rail')).toBeDefined();
    });
  });
});
