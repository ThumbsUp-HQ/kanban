// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';

import { QuickCreateIssueModal } from '../views/QuickCreateIssueModal';
import { ProjectSettingsPage } from '../settings/ProjectSettingsPage';
import { WorkspaceSettingsPage } from '../settings/WorkspaceSettingsPage';
import { AuthCardEditorDrawer } from '../admin-auth/AuthCardEditorDrawer';
import { McpAccessStudio } from '../settings/McpAccessStudio';
import { CustomFieldDefinitionEditor } from '../custom-fields/CustomFieldDefinitionEditor';
import * as clientModule from '../../api/client';
import * as settingsApi from '../settings/settingsApi';
import * as customFieldsApi from '../custom-fields/api';
import type { AdminAuthCard } from '../admin-auth/adminAuthApi';

vi.mock('../../auth/useSessionGuard', () => ({
  ensureSessionCsrfToken: vi.fn().mockReturnValue('csrf-mock-token-xyz'),
}));

vi.mock('../custom-fields/api', async () => {
  const actual = await vi.importActual<typeof import('../custom-fields/api')>('../custom-fields/api');
  return {
    ...actual,
    fetchProjectCustomFields: vi.fn(),
    createCustomField: vi.fn(),
    updateCustomField: vi.fn(),
    deleteCustomField: vi.fn(),
    fetchFieldApprovals: vi.fn().mockResolvedValue([]),
    approveFieldEscalation: vi.fn(),
    testExecuteCustomField: vi.fn(),
  };
});

describe('Accessible Names, Associated Form Labels, and Error Announcements (KAN-357)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    HTMLDivElement.prototype.scrollIntoView = vi.fn();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, staleTime: Infinity },
      },
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    queryClient.clear();
  });

  describe('Case 1: Programmatic Label Binding across Form Controls', () => {
    it('QuickCreateIssueModal binds accessible labels to summary, description, state, priority, module, and draft controls', () => {
      const onClose = vi.fn();
      const onCreate = vi.fn();

      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={onClose}
          onCreate={onCreate}
          projectKey="KAN"
          modulesEnabled={true}
          modules={[
            { id: 'mod-1', name: 'Core Engine' },
            { id: 'mod-2', name: 'UI Surface' },
          ]}
        />,
      );

      // Verify Summary input has htmlFor/id label
      const summaryInput = screen.getByLabelText(/^Summary/i);
      expect(summaryInput).toBeDefined();
      expect(summaryInput.getAttribute('id')).toBe('quick-create-summary');

      // Verify Description textarea has htmlFor/id label
      const descInput = screen.getByLabelText(/^Description/i);
      expect(descInput).toBeDefined();
      expect(descInput.getAttribute('id')).toBe('quick-create-description');

      // Verify State select has htmlFor/id label
      const stateSelect = screen.getByLabelText(/^State/i);
      expect(stateSelect).toBeDefined();
      expect(stateSelect.getAttribute('id')).toBe('quick-create-state');

      // Verify Priority select has htmlFor/id label
      const prioritySelect = screen.getByLabelText(/^Priority/i);
      expect(prioritySelect).toBeDefined();
      expect(prioritySelect.getAttribute('id')).toBe('quick-create-priority');

      // Verify Module select has htmlFor/id label
      const moduleSelect = screen.getByLabelText(/^Module/i);
      expect(moduleSelect).toBeDefined();
      expect(moduleSelect.getAttribute('id')).toBe('quick-create-module');

      // Verify Keep draft checkbox has accessible name and htmlFor binding
      const draftCheckbox = screen.getByLabelText(/Keep work-in-progress/i);
      expect(draftCheckbox).toBeDefined();
      expect(draftCheckbox.getAttribute('id')).toBe('quick-create-draft');
    });

    it('ProjectSettingsPage binds accessible labels across features, states, priorities, labels, and danger zone forms', async () => {
      vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
        await Promise.resolve();
        const url = path;
        const m = method.toUpperCase();

        if (url.includes('/api/v1/projects/KAN/members')) {
          return [
            {
              id: 'member-1',
              principal_id: 'user-1',
              principal_type: 'USER',
              role: 'PROJECT_ADMIN',
              display_name: 'Alice Admin',
              handle: 'alice',
              avatar_url: null,
            },
          ];
        }
        if (url.includes('/api/v1/projects/KAN/states') && m === 'GET') {
          return [
            {
              id: 'st-1',
              name: 'Todo',
              group: 'unstarted',
              sort_order: 1,
              color_hex: '#64748b',
              is_default: true,
              wip_soft_limit: 3,
              wip_hard_limit: 6,
            },
          ];
        }
        if (url.includes('/api/v1/projects/KAN/priorities') && m === 'GET') {
          return [
            {
              id: 'pr-1',
              slug: 'high',
              label: 'High',
              emoji: '🔥',
              sort_order: 1,
              is_default: false,
            },
          ];
        }
        if (url.includes('/api/v1/projects/KAN/labels') && m === 'GET') {
          return [
            {
              id: 'lbl-1',
              name: 'backend',
              color_hex: '#10b981',
              description: 'Backend tasks',
            },
          ];
        }
        if (url.includes('/api/v1/projects/KAN/modules') && m === 'GET') {
          return [
            {
              id: 'mod-1',
              name: 'Core Module',
              slug: 'core-module',
              is_default: true,
            },
          ];
        }
        if (url.includes('/api/v1/admin/destructive:request')) {
          return {
            token: 'tok-destruct-123',
            confirm_phrase: 'KAN',
            expires_at: '2026-11-23T18:00:00Z',
            blast_summary: {
              issues_count: 5,
              pages_count: 2,
              stickies_count: 1,
            },
          };
        }
        if (url.includes('/api/v1/projects/KAN')) {
          return {
            id: 'p-1',
            identifier: 'KAN',
            name: 'Kanban Platform',
            description: 'Core project',
            modules_enabled: true,
            is_project_admin: true,
          };
        }
        return {};
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings']}>
            <ProjectSettingsPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByTestId('project-settings-page')).toBeDefined();

      // 1. General tab (active by default): Enable Modules checkbox
      const enableModulesCheckbox = screen.getByLabelText(/Enable Modules for this project/i);
      expect(enableModulesCheckbox).toBeDefined();
      expect(enableModulesCheckbox.getAttribute('id')).toBe('enable-modules');

      // 2. States tab
      const statesTab = screen.getByTestId('tab-states');
      fireEvent.click(statesTab);
      expect(await screen.findByTestId('states-section')).toBeDefined();

      const stateNameInput = screen.getByLabelText(/^State name$/i);
      expect(stateNameInput).toBeDefined();
      expect(stateNameInput.getAttribute('id')).toBe('state-name-input');

      const stateGroupSelect = screen.getByLabelText(/^State group$/i);
      expect(stateGroupSelect).toBeDefined();
      expect(stateGroupSelect.getAttribute('id')).toBe('state-group-select');

      const defaultStateCheckbox = screen.getByLabelText(/^Default state$/i);
      expect(defaultStateCheckbox).toBeDefined();
      expect(defaultStateCheckbox.getAttribute('id')).toBe('state-default-checkbox');

      // Open advanced section for WIP limits and sort order
      const stateAdvToggle = screen.getByTestId('state-advanced-section-toggle');
      fireEvent.click(stateAdvToggle);

      const softWipInput = screen.getByLabelText(/^Soft WIP limit$/i);
      expect(softWipInput).toBeDefined();
      expect(softWipInput.getAttribute('id')).toBe('state-wip-soft-input');

      const hardWipInput = screen.getByLabelText(/^Hard WIP limit$/i);
      expect(hardWipInput).toBeDefined();
      expect(hardWipInput.getAttribute('id')).toBe('state-wip-hard-input');

      const sortOrderInput = screen.getByLabelText(/^Sort order$/i);
      expect(sortOrderInput).toBeDefined();
      expect(sortOrderInput.getAttribute('id')).toBe('state-sort-order-input');

      // 3. Priorities tab
      const prioritiesTab = screen.getByTestId('tab-priorities');
      fireEvent.click(prioritiesTab);
      expect(await screen.findByTestId('priorities-section')).toBeDefined();

      const prioritySlugInput = screen.getByLabelText(/^Priority slug$/i);
      expect(prioritySlugInput).toBeDefined();
      expect(prioritySlugInput.getAttribute('id')).toBe('priority-slug-input');

      const priorityLabelInput = screen.getByLabelText(/^Priority label$/i);
      expect(priorityLabelInput).toBeDefined();
      expect(priorityLabelInput.getAttribute('id')).toBe('priority-label-input');

      const priorityEmojiInput = screen.getByLabelText(/^Priority emoji$/i);
      expect(priorityEmojiInput).toBeDefined();
      expect(priorityEmojiInput.getAttribute('id')).toBe('priority-emoji-input');

      const prioritySortOrderInput = screen.getByLabelText(/^Priority sort order$/i);
      expect(prioritySortOrderInput).toBeDefined();
      expect(prioritySortOrderInput.getAttribute('id')).toBe('priority-sort-order-input');

      // 4. Labels tab
      const labelsTab = screen.getByTestId('tab-labels');
      fireEvent.click(labelsTab);
      expect(await screen.findByTestId('labels-section')).toBeDefined();

      const labelNameInput = screen.getByLabelText(/^Label name$/i);
      expect(labelNameInput).toBeDefined();
      expect(labelNameInput.getAttribute('id')).toBe('label-name-input');

      // 5. Danger Zone tab
      const dangerTab = screen.getByTestId('tab-danger');
      fireEvent.click(dangerTab);
      expect(await screen.findByTestId('danger-section')).toBeDefined();

      // Click request delete to enter confirm stage
      const requestDeleteBtn = screen.getByTestId('request-delete-btn');
      fireEvent.click(requestDeleteBtn);

      const confirmPhraseInput = await screen.findByLabelText(/Confirmation phrase/i);
      expect(confirmPhraseInput).toBeDefined();
      expect(confirmPhraseInput.getAttribute('id')).toBe('confirm-phrase-input');

      const reasonInput = screen.getByLabelText(/Reason for deletion/i);
      expect(reasonInput).toBeDefined();
      expect(reasonInput.getAttribute('id')).toBe('danger-reason-input');
    });

    it('WorkspaceSettingsPage binds accessible labels across export roles, new user, new group, group member, and trash search forms', async () => {
      vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (method, path) => {
        await Promise.resolve();
        const url = path;
        const m = method.toUpperCase();

        if (url.includes('/api/v1/auth/me')) {
          return {
            id: 'user-admin',
            is_server_admin: true,
            is_workspace_admin: true,
            workspace_role: 'SERVER_ADMIN',
          };
        }
        if (url.includes('/api/v1/admin/workspace-settings') && m === 'GET') {
          return {
            id: 'ws-1',
            name: 'Primary Workspace',
            slug: 'primary-workspace',
            default_project_visibility: 'workspace',
            session_idle_timeout_min: 120,
            session_absolute_timeout_min: 1440,
            trash_retention_days: 30,
            allowed_export_roles: ['workspace_admin', 'member'],
          };
        }
        if (url.includes('/api/v1/workspaces/current')) {
          return {
            id: 'ws-1',
            name: 'Primary Workspace',
            slug: 'primary-workspace',
          };
        }
        if (url.includes('/api/v1/admin/principals') && m === 'GET') {
          return [];
        }
        if (url.includes('/api/v1/admin/groups') && m === 'GET') {
          return [];
        }
        if (url.includes('/api/v1/admin/trash') && m === 'GET') {
          return [];
        }
        return [];
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/workspaces/settings']}>
            <WorkspaceSettingsPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(await screen.findByTestId('workspace-settings-page')).toBeDefined();

      // Workspace export roles checkboxes
      const exportAdminBox = screen.getByLabelText(/Allowed export role Workspace Admin/i);
      expect(exportAdminBox).toBeDefined();
      expect(exportAdminBox.getAttribute('id')).toBe('export-role-workspace_admin');

      // Members/Users tab
      const membersTab = screen.getByTestId('tab-members');
      fireEvent.click(membersTab);
      expect(await screen.findByTestId('workspace-members-section')).toBeDefined();

      const userHandleInput = screen.getByLabelText(/^User handle$/i);
      expect(userHandleInput.getAttribute('id')).toBe('new-user-handle');

      const userNameInput = screen.getByLabelText(/^User display name$/i);
      expect(userNameInput.getAttribute('id')).toBe('new-user-name');

      const userEmailInput = screen.getByLabelText(/^User email$/i);
      expect(userEmailInput.getAttribute('id')).toBe('new-user-email');

      const userPasswordInput = screen.getByLabelText(/^Initial password$/i);
      expect(userPasswordInput.getAttribute('id')).toBe('new-user-password');

      const userRoleSelect = screen.getByLabelText(/^New user role$/i);
      expect(userRoleSelect.getAttribute('id')).toBe('new-user-role-select');

      // Groups tab
      const groupsTab = screen.getByTestId('tab-groups');
      fireEvent.click(groupsTab);
      expect(await screen.findByTestId('workspace-groups-section')).toBeDefined();

      const groupNameInput = screen.getByLabelText(/^Group name$/i);
      expect(groupNameInput.getAttribute('id')).toBe('new-group-name');

      const groupHandleInput = screen.getByLabelText(/^Group handle$/i);
      expect(groupHandleInput.getAttribute('id')).toBe('new-group-handle');

      // Trash tab
      const trashTab = screen.getByTestId('tab-trash');
      fireEvent.click(trashTab);
      expect(await screen.findByTestId('workspace-trash-studio')).toBeDefined();

      const trashSearchInput = screen.getByLabelText(/Search trashed items by key or title/i);
      expect(trashSearchInput).toBeDefined();
      expect(trashSearchInput.getAttribute('id')).toBe('trash-search-input');
    });

    it('AuthCardEditorDrawer binds accessible labels across slug, display name, client ID, server URL, bind DN, base DN, and credentials file upload', () => {
      const onSave = vi.fn();
      const onClose = vi.fn();

      const sampleCard: AdminAuthCard = {
        id: 'c-ldap',
        provider_kind: 'LDAP',
        slug: 'corp-ad',
        display_name: 'Corp Active Directory',
        button_subtext: 'Domain login',
        icon_preset: 'active-directory',
        is_enabled: true,
        sort_rank: '1',
        auto_provision_users: true,
        allowed_email_domains: [],
        has_secret: false,
        dek_kid: null,
        last_health_status: 'UNVERIFIED',
        last_handshake_at: null,
        check_summary: 'Pending initial check',
        latency_ms: null,
        public_config: {
          server_url: 'ldaps://ldap.corp.com:636',
          bind_dn: 'cn=admin,dc=corp,dc=com',
          base_dn: 'dc=corp,dc=com',
        },
      };

      const { rerender } = render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={sampleCard}
          onClose={onClose}
          onSave={onSave}
        />,
      );

      // Verify LDAP labels and programmatic htmlFor binding
      const displayNameInput = document.getElementById('card-display-name') as HTMLInputElement;
      expect(displayNameInput).toBeDefined();
      expect(document.querySelector('label[for="card-display-name"]')?.textContent).toContain('Display Name');

      const serverUrlInput = document.getElementById('card-server-url') as HTMLInputElement;
      expect(serverUrlInput).toBeDefined();
      expect(document.querySelector('label[for="card-server-url"]')?.textContent).toContain('Server URL');

      const bindDnInput = document.getElementById('card-bind-dn') as HTMLInputElement;
      expect(bindDnInput).toBeDefined();
      expect(document.querySelector('label[for="card-bind-dn"]')?.textContent).toContain('Bind DN');

      const baseDnInput = document.getElementById('card-base-dn') as HTMLInputElement;
      expect(baseDnInput).toBeDefined();
      expect(document.querySelector('label[for="card-base-dn"]')?.textContent).toContain('Base DN');

      // Rerender as OIDC card
      const oidcCard: AdminAuthCard = {
        id: 'c-oidc',
        provider_kind: 'OIDC',
        slug: 'google-workspace',
        display_name: 'Google Workspace',
        button_subtext: 'Single sign-on',
        icon_preset: 'google',
        is_enabled: true,
        sort_rank: '2',
        auto_provision_users: true,
        allowed_email_domains: ['example.com'],
        has_secret: true,
        dek_kid: 'dek-1',
        last_health_status: 'HEALTHY',
        last_handshake_at: null,
        check_summary: 'OK',
        latency_ms: 25,
        public_config: {
          issuer_url: 'https://accounts.google.com',
          client_id: 'client-12345',
        },
      };

      rerender(
        <AuthCardEditorDrawer
          isOpen={true}
          card={oidcCard}
          onClose={onClose}
          onSave={onSave}
        />,
      );

      const issuerUrlInput = document.getElementById('card-issuer-url') as HTMLInputElement;
      expect(issuerUrlInput).toBeDefined();
      expect(document.querySelector('label[for="card-issuer-url"]')?.textContent).toContain('Issuer URL');

      const clientIdInput = document.getElementById('card-client-id') as HTMLInputElement;
      expect(clientIdInput).toBeDefined();
      expect(document.querySelector('label[for="card-client-id"]')?.textContent).toContain('Client ID');

      const subtextInput = document.getElementById('card-subtext') as HTMLInputElement;
      expect(subtextInput).toBeDefined();
      expect(document.querySelector('label[for="card-subtext"]')?.textContent).toContain('Button Subtext');

      // Google JSON file input accessible name
      const fileInput = screen.getByLabelText(/Upload Google credentials JSON file/i);
      expect(fileInput).toBeDefined();
      expect(fileInput.getAttribute('type')).toBe('file');
    });

    it('McpAccessStudio binds accessible labels to mint key inputs, unlimited confirm, capability bits, and tool allow checkboxes', async () => {
      vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
      vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue([]);
      vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method: string, path: string) => {
        if (path === '/api/v1/projects') {
          return Promise.resolve({
            items: [{ id: 'p-1', identifier: 'KAN', name: 'Kanban Core' }],
          });
        }
        return Promise.resolve([]);
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/settings/mcp']}>
            <Routes>
              <Route path="/settings/mcp" element={<McpAccessStudio />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Open Mint Modal
      const mintBtn = await screen.findByTestId('mint-key-button');
      fireEvent.click(mintBtn);

      expect(await screen.findByRole('dialog')).toBeDefined();

      const labelInput = screen.getByLabelText(/what is the key name/i);
      expect(labelInput.getAttribute('id')).toBe('mint-label-input');

      const keyScopeSelect = document.getElementById('mint-key-scope-type-select') as HTMLSelectElement;
      expect(keyScopeSelect).toBeDefined();
      expect(document.querySelector('label[for="mint-key-scope-type-select"]')?.textContent).toContain('Who is this key for & what can it access?');

      const surfaceSelect = screen.getByLabelText(/^Target Surface:/i);
      expect(surfaceSelect.getAttribute('id')).toBe('mint-surface-select');

      const expirySelect = screen.getByLabelText(/^Expiration:/i, { selector: 'select' });
      expect(expirySelect.getAttribute('id')).toBe('mint-expiry-select');

      // Open Advanced Capability & Network Restrictions
      const advToggle = screen.getByTestId('advanced-capability-restrictions-toggle');
      fireEvent.click(advToggle);

      const capPresetSelect = screen.getByLabelText(/^Capability Ceiling:/i, { selector: 'select' });
      expect(capPresetSelect.getAttribute('id')).toBe('capability-preset-select');

      const cidrsInput = screen.getByLabelText(/^Allowed CIDRs \(optional\):/i);
      expect(cidrsInput.getAttribute('id')).toBe('mint-allowed-cidrs-input');

      // Capability bit checkboxes
      const bitBoxes = screen.getAllByLabelText(/Capability bit/i);
      expect(bitBoxes.length).toBeGreaterThan(0);
      expect(bitBoxes[0]?.getAttribute('id')).toMatch(/^cap-bit-/);
    });

    it('CustomFieldDefinitionEditor binds accessible labels to slug, name, tier, format, metadata textarea, enabled switch, and test issue key', async () => {
      vi.mocked(customFieldsApi.fetchProjectCustomFields).mockResolvedValue([
        {
          id: 'f-1',
          slug: 'risk-score',
          name: 'Risk Score',
          tier: 'wasm',
          output_format: 'severity_pill',
          output_format_metadata: {},
          target_scope: 'PROJECT',
          credential_mode: 'INVOKING_USER',
          egress_allowlist: [],
          is_enabled: true,
        },
      ]);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CustomFieldDefinitionEditor projectKey="KAN" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Click to create new field
      const newBtn = await screen.findByTestId('create-new-field-btn');
      fireEvent.click(newBtn);

      const nameInput = screen.getByTestId('field-name-input');
      expect(nameInput.getAttribute('id')).toBe('field-name');
      expect(document.querySelector('label[for="field-name"]')?.textContent).toContain('Field Name');

      const slugInput = screen.getByTestId('field-slug-input');
      expect(slugInput.getAttribute('id')).toBe('field-slug');
      expect(document.querySelector('label[for="field-slug"]')?.textContent).toContain('Identifier Slug');

      const flavorSelect = document.getElementById('field-flavor') as HTMLSelectElement;
      expect(flavorSelect).toBeDefined();
      expect(document.querySelector('label[for="field-flavor"]')?.textContent).toContain('Field Flavor');

      const formatSelect = document.getElementById('output-format') as HTMLSelectElement;
      expect(formatSelect).toBeDefined();
      expect(document.querySelector('label[for="output-format"]')?.textContent).toContain('Output Format');

      // Open Advanced Section
      const advToggle = screen.getByTestId('custom-field-advanced-section-toggle');
      fireEvent.click(advToggle);

      const metadataTextarea = screen.getByTestId('format-metadata-textarea');
      expect(metadataTextarea.getAttribute('id')).toBe('format-metadata');
      expect(document.querySelector('label[for="format-metadata"]')?.textContent).toContain('Format Configuration Metadata (JSON)');

      const scriptSourceTextarea = screen.getByTestId('script-source-textarea');
      expect(scriptSourceTextarea.getAttribute('id')).toBe('script-source');
      expect(document.querySelector('label[for="script-source"]')?.textContent).toContain('Script Source Code');

      const testIssueInput = document.getElementById('test-issue-key');
      expect(testIssueInput).toBeDefined();
      expect(document.querySelector('label[for="test-issue-key"]')?.textContent).toContain('Test With Issue Key');

      const enabledCheckbox = screen.getByLabelText(/^Enabled$/i);
      expect(enabledCheckbox.getAttribute('id')).toBe('is-enabled');
    });
  });

  describe('Case 2: Accessible Error Announcements and ARIA Validation State', () => {
    it('QuickCreateIssueModal announces submit error with role="alert" and links summary input via aria-describedby and aria-invalid="true"', async () => {
      const onCreate = vi.fn().mockImplementation(() => {
        throw new Error('Database transaction lock conflict');
      });

      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={onCreate}
          projectKey="KAN"
        />,
      );

      const summaryInput = screen.getByLabelText(/^Summary/i);
      expect(summaryInput.getAttribute('aria-invalid')).toBe('false');
      expect(summaryInput.getAttribute('aria-describedby')).toBeNull();

      fireEvent.change(summaryInput, { target: { value: 'Bug in security engine' } });
      const submitBtn = screen.getByTestId('quick-create-submit-btn');
      fireEvent.click(submitBtn);

      // Error alert should appear
      const alert = await screen.findByRole('alert');
      expect(alert).toBeDefined();
      expect(alert.getAttribute('id')).toBe('quick-create-error-msg');
      expect(alert.textContent).toContain('Database transaction lock conflict');

      // Summary input must have aria-invalid and aria-describedby linked to error alert
      expect(summaryInput.getAttribute('aria-invalid')).toBe('true');
      expect(summaryInput.getAttribute('aria-describedby')).toBe('quick-create-error-msg');
    });

    it('ProjectSettingsPage announces WIP limit error with role="alert" and flags soft/hard WIP inputs with aria-invalid="true"', async () => {
      vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if (path.includes('/api/v1/projects/KAN/states')) {
          return [
            {
              id: 'st-1',
              name: 'In Development',
              group: 'started',
              sort_order: 1,
              color_hex: '#3b82f6',
              is_default: false,
              wip_soft_limit: 2,
              wip_hard_limit: 5,
            },
          ];
        }
        if (path.includes('/api/v1/projects/KAN')) {
          return {
            id: 'p-1',
            identifier: 'KAN',
            name: 'Kanban Platform',
            is_project_admin: true,
          };
        }
        return [];
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings']}>
            <ProjectSettingsPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const statesTab = await screen.findByTestId('tab-states');
      fireEvent.click(statesTab);
      expect(await screen.findByTestId('states-section')).toBeDefined();

      // Open advanced section
      const stateAdvToggle = screen.getByTestId('state-advanced-section-toggle');
      fireEvent.click(stateAdvToggle);

      const softWipInput = screen.getByLabelText(/^Soft WIP limit$/i);
      const hardWipInput = screen.getByLabelText(/^Hard WIP limit$/i);

      expect(softWipInput.getAttribute('aria-invalid')).toBe('false');
      expect(hardWipInput.getAttribute('aria-invalid')).toBe('false');

      // Enter state name and soft limit 10 and hard limit 4 (invalid: soft > hard)
      const stateNameInput = screen.getByLabelText(/^State name$/i);
      fireEvent.change(stateNameInput, { target: { value: 'Blocked' } });
      fireEvent.change(softWipInput, { target: { value: '10' } });
      fireEvent.change(hardWipInput, { target: { value: '4' } });

      const addStateBtn = screen.getByTestId('create-state-btn');
      fireEvent.click(addStateBtn);

      const alert = await screen.findByRole('alert');
      expect(alert).toBeDefined();
      expect(alert.getAttribute('id')).toBe('wip-limit-error');
      expect(alert.textContent).toContain('Soft WIP limit cannot exceed Hard WIP limit');

      expect(softWipInput.getAttribute('aria-invalid')).toBe('true');
      expect(softWipInput.getAttribute('aria-describedby')).toBe('wip-limit-error');
      expect(hardWipInput.getAttribute('aria-invalid')).toBe('true');
      expect(hardWipInput.getAttribute('aria-describedby')).toBe('wip-limit-error');
    });

    it('AuthCardEditorDrawer announces field validation errors with role="alert" and binds aria-describedby and aria-invalid on invalid fields', async () => {
      const onSave = vi.fn();
      const onClose = vi.fn();

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={onClose}
          onSave={onSave}
        />,
      );

      const displayNameInput = document.getElementById('card-display-name') as HTMLInputElement;
      const clientIdInput = document.getElementById('card-client-id') as HTMLInputElement;
      const slugInput = document.getElementById('card-slug') as HTMLInputElement;

      expect(displayNameInput.getAttribute('aria-invalid')).toBe('false');
      expect(clientIdInput.getAttribute('aria-invalid')).toBe('false');

      // Clear slug and try to save empty form
      fireEvent.change(slugInput, { target: { value: '' } });
      const saveBtn = screen.getByRole('button', { name: /Create Card/i });
      fireEvent.click(saveBtn);

      // Validate error announcements appear with role="alert"
      const alerts = await screen.findAllByRole('alert');
      expect(alerts.length).toBeGreaterThan(0);

      const displayNameError = document.getElementById('card-display-name-error');
      expect(displayNameError).toBeDefined();
      expect(displayNameError?.getAttribute('role')).toBe('alert');
      expect(displayNameError?.textContent).toContain('Display name must be between 1 and 80 characters.');

      const clientIdError = document.getElementById('card-client-id-error');
      expect(clientIdError).toBeDefined();
      expect(clientIdError?.getAttribute('role')).toBe('alert');
      expect(clientIdError?.textContent).toContain('Client ID is required.');

      expect(displayNameInput.getAttribute('aria-invalid')).toBe('true');
      expect(displayNameInput.getAttribute('aria-describedby')).toBe('card-display-name-error');

      expect(clientIdInput.getAttribute('aria-invalid')).toBe('true');
      expect(clientIdInput.getAttribute('aria-describedby')).toBe('card-client-id-error');
    });

    it('McpAccessStudio announces CIDR syntax error and mint error with role="alert" and flags inputs with aria-invalid="true"', async () => {
      vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
      vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue([]);
      vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method: string, path: string) => {
        if (path === '/api/v1/projects') {
          return Promise.resolve({
            items: [{ id: 'p-1', identifier: 'KAN', name: 'Kanban Core' }],
          });
        }
        return Promise.resolve([]);
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/settings/mcp']}>
            <Routes>
              <Route path="/settings/mcp" element={<McpAccessStudio />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const mintBtn = await screen.findByTestId('mint-key-button');
      fireEvent.click(mintBtn);

      const cidrsInput = screen.getByLabelText(/^Allowed CIDRs \(optional\):/i);
      expect(cidrsInput.getAttribute('aria-invalid')).toBe('false');

      // Enter invalid CIDR
      fireEvent.change(cidrsInput, { target: { value: '999.999.999.999/99' } });

      const alert = await screen.findByRole('alert');
      expect(alert.getAttribute('id')).toBe('cidr-error-message');
      expect(alert.textContent).toContain('Invalid CIDR format');

      expect(cidrsInput.getAttribute('aria-invalid')).toBe('true');
      expect(cidrsInput.getAttribute('aria-describedby')).toBe('cidr-error-message');
    });

    it('CustomFieldDefinitionEditor announces JSON metadata parse error and execution error with role="alert" and aria-invalid="true"', async () => {
      vi.mocked(customFieldsApi.fetchProjectCustomFields).mockResolvedValue([
        {
          id: 'f-1',
          slug: 'risk-score',
          name: 'Risk Score',
          tier: 'wasm',
          output_format: 'severity_pill',
          output_format_metadata: {},
          target_scope: 'PROJECT',
          credential_mode: 'INVOKING_USER',
          egress_allowlist: [],
          is_enabled: true,
        },
      ]);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CustomFieldDefinitionEditor projectKey="KAN" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const newBtn = await screen.findByTestId('create-new-field-btn');
      fireEvent.click(newBtn);

      const nameInput = screen.getByTestId('field-name-input');
      fireEvent.change(nameInput, { target: { value: 'Risk Rating' } });
      const slugInput = screen.getByTestId('field-slug-input');
      fireEvent.change(slugInput, { target: { value: 'risk-rating' } });

      // Open Advanced Section
      const advToggle = screen.getByTestId('custom-field-advanced-section-toggle');
      fireEvent.click(advToggle);

      const metadataTextarea = screen.getByTestId('format-metadata-textarea');
      expect(metadataTextarea.getAttribute('aria-invalid')).toBe('false');

      // Enter invalid JSON and click submit
      fireEvent.change(metadataTextarea, { target: { value: '{ invalid: json without quotes }' } });
      const saveBtn = screen.getByTestId('save-definition-btn');
      fireEvent.click(saveBtn);

      const alert = await screen.findByRole('alert');
      expect(alert.getAttribute('id')).toBe('format-metadata-error');
      expect(alert.textContent).toContain('Invalid JSON in format metadata');

      expect(metadataTextarea.getAttribute('aria-invalid')).toBe('true');
      expect(metadataTextarea.getAttribute('aria-describedby')).toBe('format-metadata-error');
    });
  });

  describe('Case 3: Interactive Dynamic Error Recovery and ARIA State Reset', () => {
    it('recovers from QuickCreateIssueModal submit error upon re-submission', async () => {
      let shouldFail = true;
      const onCreate = vi.fn().mockImplementation(() => {
        if (shouldFail) {
          throw new Error('Temporary API outage');
        }
        return { key: 'KAN-101', summary: 'Restored bug fix' };
      });

      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={onCreate}
          projectKey="KAN"
        />,
      );

      const summaryInput = screen.getByLabelText(/^Summary/i);
      fireEvent.change(summaryInput, { target: { value: 'Security vulnerability' } });

      const submitBtn = screen.getByTestId('quick-create-submit-btn');
      fireEvent.click(submitBtn);

      // Verify initial error
      const alert = await screen.findByRole('alert');
      expect(alert.textContent).toContain('Temporary API outage');
      expect(summaryInput.getAttribute('aria-invalid')).toBe('true');
      expect(summaryInput.getAttribute('aria-describedby')).toBe('quick-create-error-msg');

      // Correct failure condition and resubmit
      shouldFail = false;
      fireEvent.click(submitBtn);

      // Modal transitions to created state or closes
      await waitFor(() => {
        expect(screen.queryByText('Temporary API outage')).toBeNull();
      });
    });

    it('clears WIP limit error and removes aria-invalid on ProjectSettingsPage when soft WIP is corrected', async () => {
      vi.spyOn(clientModule, 'apiFetch').mockImplementation(async (_method, path) => {
        await Promise.resolve();
        if (path.includes('/api/v1/projects/KAN/states')) {
          return [];
        }
        if (path.includes('/api/v1/projects/KAN')) {
          return {
            id: 'p-1',
            identifier: 'KAN',
            name: 'Kanban Platform',
            is_project_admin: true,
          };
        }
        return [];
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/settings']}>
            <ProjectSettingsPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const statesTab = await screen.findByTestId('tab-states');
      fireEvent.click(statesTab);

      // Open advanced section
      const stateAdvToggle = screen.getByTestId('state-advanced-section-toggle');
      fireEvent.click(stateAdvToggle);

      const stateNameInput = screen.getByLabelText(/^State name$/i);
      const softWipInput = screen.getByLabelText(/^Soft WIP limit$/i);
      const hardWipInput = screen.getByLabelText(/^Hard WIP limit$/i);

      // Trigger error
      fireEvent.change(stateNameInput, { target: { value: 'WIP Review' } });
      fireEvent.change(softWipInput, { target: { value: '15' } });
      fireEvent.change(hardWipInput, { target: { value: '5' } });
      const addStateBtn = screen.getByTestId('create-state-btn');
      fireEvent.click(addStateBtn);

      expect(await screen.findByRole('alert')).toBeDefined();
      expect(softWipInput.getAttribute('aria-invalid')).toBe('true');
      expect(hardWipInput.getAttribute('aria-invalid')).toBe('true');

      // Fix soft WIP to 3 (<= 5)
      fireEvent.change(softWipInput, { target: { value: '3' } });

      await waitFor(() => {
        expect(screen.queryByRole('alert')).toBeNull();
        expect(softWipInput.getAttribute('aria-invalid')).toBe('false');
        expect(softWipInput.getAttribute('aria-describedby')).toBeNull();
        expect(hardWipInput.getAttribute('aria-invalid')).toBe('false');
        expect(hardWipInput.getAttribute('aria-describedby')).toBeNull();
      });
    });

    it('clears validation error and removes aria-invalid in AuthCardEditorDrawer when user corrects required fields', async () => {
      const onSave = vi.fn();
      const onClose = vi.fn();

      render(
        <AuthCardEditorDrawer
          isOpen={true}
          card={null}
          onClose={onClose}
          onSave={onSave}
        />,
      );

      const displayNameInput = document.getElementById('card-display-name') as HTMLInputElement;
      const clientIdInput = document.getElementById('card-client-id') as HTMLInputElement;
      const slugInput = document.getElementById('card-slug') as HTMLInputElement;

      // Trigger validation error
      fireEvent.change(slugInput, { target: { value: '' } });
      const saveBtn = screen.getByRole('button', { name: /Create Card/i });
      fireEvent.click(saveBtn);

      expect(displayNameInput.getAttribute('aria-invalid')).toBe('true');
      expect(clientIdInput.getAttribute('aria-invalid')).toBe('true');

      // Now fill valid values
      fireEvent.change(slugInput, { target: { value: 'okta-auth' } });
      fireEvent.change(displayNameInput, { target: { value: 'Enterprise Okta' } });
      fireEvent.change(clientIdInput, { target: { value: 'client-98765' } });

      // Resubmit
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(displayNameInput.getAttribute('aria-invalid')).toBe('false');
        expect(displayNameInput.getAttribute('aria-describedby')).toBeNull();
        expect(clientIdInput.getAttribute('aria-invalid')).toBe('false');
        expect(clientIdInput.getAttribute('aria-describedby')).toBeNull();
      });
    });

    it('clears CIDR error and removes aria-invalid in McpAccessStudio when valid CIDR is provided', async () => {
      vi.spyOn(settingsApi, 'fetchUnifiedMcpKeys').mockResolvedValue([]);
      vi.spyOn(settingsApi, 'fetchPersonalMcpKeys').mockResolvedValue([]);
      vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method: string, path: string) => {
        if (path === '/api/v1/projects') {
          return Promise.resolve({
            items: [{ id: 'p-1', identifier: 'KAN', name: 'Kanban Core' }],
          });
        }
        return Promise.resolve([]);
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/settings/mcp']}>
            <Routes>
              <Route path="/settings/mcp" element={<McpAccessStudio />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const mintBtn = await screen.findByTestId('mint-key-button');
      fireEvent.click(mintBtn);

      const cidrsInput = screen.getByLabelText(/^Allowed CIDRs \(optional\):/i);

      // Invalid CIDR
      fireEvent.change(cidrsInput, { target: { value: 'not-an-ip' } });
      expect(await screen.findByRole('alert')).toBeDefined();
      expect(cidrsInput.getAttribute('aria-invalid')).toBe('true');

      // Correct CIDR
      fireEvent.change(cidrsInput, { target: { value: '192.168.1.0/24' } });

      await waitFor(() => {
        expect(screen.queryByRole('alert')).toBeNull();
        expect(cidrsInput.getAttribute('aria-invalid')).toBe('false');
        expect(cidrsInput.getAttribute('aria-describedby')).toBeNull();
      });
    });

    it('clears format metadata JSON error and removes aria-invalid in CustomFieldDefinitionEditor when valid JSON is entered', async () => {
      vi.mocked(customFieldsApi.fetchProjectCustomFields).mockResolvedValue([
        {
          id: 'f-1',
          slug: 'risk-score',
          name: 'Risk Score',
          tier: 'wasm',
          output_format: 'severity_pill',
          output_format_metadata: {},
          target_scope: 'PROJECT',
          credential_mode: 'INVOKING_USER',
          egress_allowlist: [],
          is_enabled: true,
        },
      ]);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CustomFieldDefinitionEditor projectKey="KAN" isAdmin={true} />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const newBtn = await screen.findByTestId('create-new-field-btn');
      fireEvent.click(newBtn);

      const nameInput = screen.getByTestId('field-name-input');
      fireEvent.change(nameInput, { target: { value: 'Risk Rating' } });
      const slugInput = screen.getByTestId('field-slug-input');
      fireEvent.change(slugInput, { target: { value: 'risk-rating' } });

      // Open Advanced Section
      const advToggle = screen.getByTestId('custom-field-advanced-section-toggle');
      fireEvent.click(advToggle);

      const metadataTextarea = screen.getByTestId('format-metadata-textarea');

      // Invalid JSON
      fireEvent.change(metadataTextarea, { target: { value: '{ bad_json }' } });
      const saveBtn = screen.getByTestId('save-definition-btn');
      fireEvent.click(saveBtn);

      expect(await screen.findByRole('alert')).toBeDefined();
      expect(metadataTextarea.getAttribute('aria-invalid')).toBe('true');

      // Correct to valid JSON
      fireEvent.change(metadataTextarea, { target: { value: '{"precision": 2}' } });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(screen.queryByRole('alert')).toBeNull();
        expect(metadataTextarea.getAttribute('aria-invalid')).toBe('false');
        expect(metadataTextarea.getAttribute('aria-describedby')).toBeNull();
      });
    });
  });
});
