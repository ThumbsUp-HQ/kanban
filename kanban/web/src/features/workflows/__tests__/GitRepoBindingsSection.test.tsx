// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GitRepoBindingsSection } from '../GitRepoBindingsSection';
import * as api from '../api';
import type { RepoBindingDetail } from '../api';

describe('GitRepoBindingsSection', () => {
  let queryClient: QueryClient;

  const mockBindings: RepoBindingDetail[] = [
    {
      id: 'repo-1',
      slug: 'core-repo',
      remote_url: 'https://github.com/example/core.git',
      default_ref: 'main',
      access_mode: 'ro_vfs_mount',
      last_fetched_commit: 'abc1234567890',
      last_fetched_at: '2026-11-18T12:00:00Z',
    },
    {
      id: 'repo-2',
      slug: 'docs-repo',
      remote_url: 'git@github.com:example/docs.git',
      default_ref: 'master',
      access_mode: 'bare_git_tools',
      last_fetch_error: 'Connection timed out',
    },
    {
      id: 'repo-3',
      slug: 'pending-repo',
      remote_url: 'https://github.com/example/pending.git',
      default_ref: 'develop',
      access_mode: 'ro_vfs_mount',
    },
  ];

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, staleTime: Infinity },
      },
    });
    vi.restoreAllMocks();
  });

  function renderSection(props: {
    projectKey?: string;
    isUserAdmin?: boolean;
    onAal2Intercept?: (
      err: unknown,
      mutation: { type: string; execute: () => Promise<void> },
    ) => boolean;
  } = {}) {
    return render(
      <QueryClientProvider client={queryClient}>
        <GitRepoBindingsSection
          projectKey={props.projectKey ?? 'KAN'}
          isUserAdmin={props.isUserAdmin ?? true}
          onAal2Intercept={props.onAal2Intercept}
        />
      </QueryClientProvider>,
    );
  }

  it('renders empty state when no repo bindings exist', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue([]);

    renderSection();

    expect(await screen.findByTestId('empty-repo-bindings')).toBeDefined();
    expect(screen.getByText(/No git repository mirrors bound to this project/i)).toBeDefined();
  });

  it('renders repository list with status badges and details', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue(mockBindings);

    renderSection();

    expect(await screen.findByText('core-repo')).toBeDefined();
    expect(screen.getByText('docs-repo')).toBeDefined();
    expect(screen.getByText('pending-repo')).toBeDefined();

    // Badges
    expect(screen.getAllByText('VFS Mount (:ro)')).toHaveLength(2);
    expect(screen.getByText('Bare Git Tools')).toBeDefined();
    expect(screen.getByText('Synced (abc1234)')).toBeDefined();
    expect(screen.getByText('Sync Error')).toBeDefined();
    expect(screen.getByText('Pending Sync')).toBeDefined();
    expect(screen.getByText('Connection timed out')).toBeDefined();
  });

  it('hides admin action buttons when isUserAdmin is false', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue(mockBindings);

    renderSection({ isUserAdmin: false });

    await waitFor(() => {
      expect(screen.getByText('core-repo')).toBeDefined();
    });

    expect(screen.queryByText('+ Bind Git Repository')).toBeNull();
    expect(screen.queryByText('Refresh Mirror')).toBeNull();
    expect(screen.queryByText('Remove')).toBeNull();
  });

  it('handles Refresh Mirror button and triggers refreshRepoBinding', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue(mockBindings);
    const refreshedBinding: RepoBindingDetail = {
      id: 'repo-1',
      slug: 'core-repo',
      remote_url: 'https://github.com/example/core.git',
      default_ref: 'main',
      access_mode: 'ro_vfs_mount',
      last_fetched_commit: 'def5678901234',
      last_fetched_at: '2026-11-18T12:00:00Z',
    };
    const refreshSpy = vi.spyOn(api, 'refreshRepoBinding').mockResolvedValue(refreshedBinding);

    renderSection();

    const refreshBtn = await screen.findByLabelText('Refresh mirror core-repo');
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(refreshSpy).toHaveBeenCalledWith('repo-1');
    });
  });

  it('handles Refresh Mirror error with AAL2 interception', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue(mockBindings);
    const aal2Error = { status: 403, code: 'AAL2_REQUIRED' };
    vi.spyOn(api, 'refreshRepoBinding').mockRejectedValue(aal2Error);

    let capturedMutation: { type: string; execute: () => Promise<void> } | null = null;
    const onAal2Intercept = vi.fn((err: unknown, mutation: { type: string; execute: () => Promise<void> }) => {
      capturedMutation = mutation;
      return true;
    });

    renderSection({ onAal2Intercept });

    const refreshBtn = await screen.findByLabelText('Refresh mirror core-repo');
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(onAal2Intercept).toHaveBeenCalled();
    });
    expect(capturedMutation).toBeDefined();
  });

  it('handles Refresh Mirror error without AAL2 displaying alert', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue(mockBindings);
    vi.spyOn(api, 'refreshRepoBinding').mockRejectedValue(new Error('Network unreachable'));

    renderSection();

    const refreshBtn = await screen.findByLabelText('Refresh mirror core-repo');
    fireEvent.click(refreshBtn);

    expect(await screen.findByText('Network unreachable')).toBeDefined();
  });

  it('handles Remove button when user confirms', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue(mockBindings);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const deleteSpy = vi.spyOn(api, 'deleteRepoBinding').mockResolvedValue();

    renderSection();

    const removeBtn = await screen.findByLabelText('Remove mirror core-repo');
    fireEvent.click(removeBtn);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('repo-1');
    });
  });

  it('does nothing when Remove button confirmation is cancelled', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue(mockBindings);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const deleteSpy = vi.spyOn(api, 'deleteRepoBinding').mockResolvedValue();

    renderSection();

    const removeBtn = await screen.findByLabelText('Remove mirror core-repo');
    fireEvent.click(removeBtn);

    expect(deleteSpy).not.toHaveBeenCalled();
  });

  it('handles Remove error with AAL2 interception', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue(mockBindings);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(api, 'deleteRepoBinding').mockRejectedValue(new Error('AAL2 stepup'));

    const onAal2Intercept = vi.fn().mockReturnValue(true);
    renderSection({ onAal2Intercept });

    const removeBtn = await screen.findByLabelText('Remove mirror core-repo');
    fireEvent.click(removeBtn);

    await waitFor(() => {
      expect(onAal2Intercept).toHaveBeenCalled();
    });
  });

  it('handles Remove error displaying alert message', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue(mockBindings);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(api, 'deleteRepoBinding').mockRejectedValue(new Error('Permission denied'));

    renderSection();

    const removeBtn = await screen.findByLabelText('Remove mirror core-repo');
    fireEvent.click(removeBtn);

    expect(await screen.findByText('Permission denied')).toBeDefined();
  });

  it('opens modal, validates slug and URL, and submits successfully', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue([]);
    const createSpy = vi.spyOn(api, 'createRepoBinding').mockResolvedValue({
      id: 'new-repo',
      slug: 'new-mirror',
      remote_url: 'https://github.com/myorg/myrepo.git',
      default_ref: 'main',
      access_mode: 'ro_vfs_mount',
    });

    renderSection();

    const openBtn = await screen.findByText('+ Bind Git Repository');
    fireEvent.click(openBtn);

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByText('Bind Git Repository (:ro Bare Mirror)')).toBeDefined();

    const slugInput = screen.getByLabelText(/Repository Identifier \/ Slug/i);
    const urlInput = screen.getByLabelText(/Remote Git URL/i);
    const refInput = screen.getByLabelText(/Default Branch \/ Ref/i);
    const accessSelect = screen.getByLabelText(/Access Mode/i);
    const credSelect = screen.getByLabelText(/Authentication Credential/i);

    // Test invalid slug validation
    fireEvent.change(slugInput, { target: { value: 'INVALID_SLUG!' } });
    fireEvent.change(urlInput, { target: { value: 'https://github.com/valid/repo.git' } });
    fireEvent.click(screen.getByText('Bind Repository'));

    expect(await screen.findByText(/Slug must be 2-63 lowercase alphanumeric/i)).toBeDefined();

    // Test invalid SSRF URL validation
    fireEvent.change(slugInput, { target: { value: 'valid-slug' } });
    fireEvent.change(urlInput, { target: { value: 'http://127.0.0.1/malicious.git' } });
    const dialogForm = screen.getByRole('dialog').querySelector('form');
    if (dialogForm) fireEvent.submit(dialogForm);

    expect(await screen.findAllByText(/Insecure URL scheme rejected/i)).toHaveLength(2);

    // Test valid inputs
    fireEvent.change(urlInput, { target: { value: 'https://github.com/myorg/myrepo.git' } });
    fireEvent.change(refInput, { target: { value: 'release/v1.0' } });
    fireEvent.change(accessSelect, { target: { value: 'bare_git_tools' } });
    fireEvent.change(credSelect, { target: { value: 'workspace-pat' } });

    expect(screen.getByText('Valid remote git URL (HTTPS / SSH).')).toBeDefined();

    fireEvent.click(screen.getByText('Bind Repository'));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith('KAN', {
        slug: 'valid-slug',
        remote_url: 'https://github.com/myorg/myrepo.git',
        default_ref: 'release/v1.0',
        access_mode: 'bare_git_tools',
        credential: 'workspace-pat',
      });
    });

    // Modal closes
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });

  it('handles createRepoBinding error with AAL2 intercept', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue([]);
    vi.spyOn(api, 'createRepoBinding').mockRejectedValue(new Error('AAL2 stepup'));

    const onAal2Intercept = vi.fn().mockReturnValue(true);
    renderSection({ onAal2Intercept });

    fireEvent.click(await screen.findByText('+ Bind Git Repository'));

    const slugInput = screen.getByLabelText(/Repository Identifier \/ Slug/i);
    const urlInput = screen.getByLabelText(/Remote Git URL/i);

    fireEvent.change(slugInput, { target: { value: 'repo-aal2' } });
    fireEvent.change(urlInput, { target: { value: 'https://github.com/myorg/myrepo.git' } });
    fireEvent.click(screen.getByText('Bind Repository'));

    await waitFor(() => {
      expect(onAal2Intercept).toHaveBeenCalled();
    });
  });

  it('handles createRepoBinding generic failure displaying form error', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue([]);
    vi.spyOn(api, 'createRepoBinding').mockRejectedValue(new Error('Duplicate slug rejected'));

    renderSection();

    fireEvent.click(await screen.findByText('+ Bind Git Repository'));

    const slugInput = screen.getByLabelText(/Repository Identifier \/ Slug/i);
    const urlInput = screen.getByLabelText(/Remote Git URL/i);

    fireEvent.change(slugInput, { target: { value: 'repo-dup' } });
    fireEvent.change(urlInput, { target: { value: 'https://github.com/myorg/myrepo.git' } });
    fireEvent.click(screen.getByText('Bind Repository'));

    expect(await screen.findByText('Duplicate slug rejected')).toBeDefined();
  });

  it('closes modal when Cancel button is clicked', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue([]);

    renderSection();

    fireEvent.click(await screen.findByText('+ Bind Git Repository'));
    expect(screen.getByRole('dialog')).toBeDefined();

    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('handles empty url and defaultRef fallback to main', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue([]);
    const createSpy = vi.spyOn(api, 'createRepoBinding').mockResolvedValue({
      id: 'r-fallback',
      slug: 'fallback-slug',
      remote_url: 'https://github.com/org/repo.git',
      default_ref: 'main',
      access_mode: 'ro_vfs_mount',
    });

    renderSection();

    fireEvent.click(await screen.findByText('+ Bind Git Repository'));

    const slugInput = screen.getByLabelText(/Repository Identifier \/ Slug/i);
    const urlInput = screen.getByLabelText(/Remote Git URL/i);
    const refInput = screen.getByLabelText(/Default Branch \/ Ref/i);

    // Enter valid URL then empty it
    fireEvent.change(urlInput, { target: { value: 'https://github.com/temp/url.git' } });
    expect(screen.getByText('Valid remote git URL (HTTPS / SSH).')).toBeDefined();
    fireEvent.change(urlInput, { target: { value: '   ' } });
    expect(screen.queryByText('Valid remote git URL (HTTPS / SSH).')).toBeNull();

    // Fill valid data with empty defaultRef
    fireEvent.change(slugInput, { target: { value: 'fallback-slug' } });
    fireEvent.change(urlInput, { target: { value: 'https://github.com/org/repo.git' } });
    fireEvent.change(refInput, { target: { value: '   ' } });

    fireEvent.click(screen.getByText('Bind Repository'));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith('KAN', expect.objectContaining({
        slug: 'fallback-slug',
        default_ref: 'main',
      }));
    });
  });

  it('handles non-Error string rejection in refresh, delete, and create', async () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue(mockBindings);
    vi.spyOn(api, 'refreshRepoBinding').mockRejectedValue('string-refresh-error');
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(api, 'deleteRepoBinding').mockRejectedValue('string-delete-error');
    vi.spyOn(api, 'createRepoBinding').mockRejectedValue('string-create-error');

    renderSection();

    // Refresh non-Error
    const refreshBtn = await screen.findByLabelText('Refresh mirror core-repo');
    fireEvent.click(refreshBtn);
    expect(await screen.findByText('Failed to refresh repository mirror.')).toBeDefined();

    // Delete non-Error
    const removeBtn = screen.getByLabelText('Remove mirror core-repo');
    fireEvent.click(removeBtn);
    expect(await screen.findByText('Failed to delete repository mirror.')).toBeDefined();

    // Create non-Error
    fireEvent.click(screen.getByText('+ Bind Git Repository'));
    const slugInput = screen.getByLabelText(/Repository Identifier \/ Slug/i);
    const urlInput = screen.getByLabelText(/Remote Git URL/i);
    fireEvent.change(slugInput, { target: { value: 'new-repo' } });
    fireEvent.change(urlInput, { target: { value: 'https://github.com/org/repo.git' } });
    fireEvent.click(screen.getByText('Bind Repository'));
    expect(await screen.findByText('Failed to bind git repository.')).toBeDefined();
  });

  it('renders SSRF restriction callout and masked PAT input with data-1p-ignore and zero password inputs', () => {
    vi.spyOn(api, 'fetchRepoBindings').mockResolvedValue(mockBindings);

    renderSection();

    fireEvent.click(screen.getByText('+ Bind Git Repository'));

    // Verify SSRF callout
    const ssrfCallout = screen.getByTestId('repo-url-ssrf-callout');
    expect(ssrfCallout).toBeDefined();
    expect(ssrfCallout.textContent).toContain('SSRF Restrictions');

    // Switch credential to workspace-pat
    const credSelect = screen.getByLabelText(/Authentication Credential \/ Secret/i);
    fireEvent.change(credSelect, { target: { value: 'workspace-pat' } });

    // Verify PAT input
    const patInput = screen.getByTestId('repo-pat-input');
    expect(patInput).toBeDefined();
    expect(patInput.getAttribute('type')).toBe('text');
    expect(patInput.className).toContain('kb-masked-api-key');
    expect(patInput.getAttribute('data-1p-ignore')).toBe('true');
    expect(patInput.getAttribute('autoComplete')).toBe('off');

    // Verify ZERO password inputs
    const passwordInputs = document.querySelectorAll('input[type="password"]');
    expect(passwordInputs.length).toBe(0);
  });
});
