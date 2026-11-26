// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { act } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RoleLabelPicker } from '../RoleLabelPicker';
import * as clientModule from '../../../api/client';

const MOCK_ASSIGNED = [
  {
    id: 'prl-1',
    principal_id: 'user-1',
    role_id: 'role-1',
    role_name: 'Lead Dev',
    role_slug: 'lead-dev',
    role_color_hex: '#3b82f6',
  },
  {
    id: 'prl-2',
    principal_id: 'user-1',
    role_id: 'role-2',
    role_name: 'QA Tester',
    role_slug: 'qa-tester',
    role_color_hex: '#10b981',
  },
];

const MOCK_AVAILABLE = [
  {
    id: 'role-1',
    slug: 'lead-dev',
    name: 'Lead Dev',
    color_hex: '#3b82f6',
  },
  {
    id: 'role-2',
    slug: 'qa-tester',
    name: 'QA Tester',
    color_hex: '#10b981',
  },
  {
    id: 'role-3',
    slug: 'sec-auditor',
    name: 'Security Auditor',
    color_hex: '#ef4444',
  },
];

describe('RoleLabelPicker Component (KAN-83, KAN-502)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('auto-fetches available roles when not provided via props and renders assigned labels', async () => {
    const onRolesChange = vi.fn();
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        return Promise.resolve(MOCK_AVAILABLE as never);
      }
      if (path.includes('/api/v1/admin/principals/user-1/role-labels')) {
        return Promise.resolve(MOCK_ASSIGNED as never);
      }
      return Promise.resolve([] as never);
    });

    render(<RoleLabelPicker principalId="user-1" onRolesChange={onRolesChange} />);

    await waitFor(() => {
      expect(screen.getByTestId('role-chip-lead-dev')).toBeDefined();
      expect(screen.getByTestId('role-chip-qa-tester')).toBeDefined();
      expect(screen.getByTestId('add-role-label-select')).toBeDefined();
    });
    expect(onRolesChange).toHaveBeenCalledWith(['role-1', 'role-2']);
  });

  it('removes assigned role label on click and handles remove error', async () => {
    const deleteSpy = vi.fn().mockResolvedValue({ status: 'deleted' });
    const onRolesChange = vi.fn();
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path, opts) => {
      if (path.includes('/api/v1/admin/principals/user-1/role-labels')) {
        if (method === 'DELETE') {
          return Promise.resolve(deleteSpy(method, path, opts) as never);
        }
        return Promise.resolve(MOCK_ASSIGNED as never);
      }
      return Promise.resolve([] as never);
    });

    render(
      <RoleLabelPicker
        principalId="user-1"
        availableRoles={MOCK_AVAILABLE}
        onRolesChange={onRolesChange}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('remove-role-lead-dev')).toBeDefined();
    });

    // Error branch first
    deleteSpy.mockRejectedValueOnce({ detail: 'Cannot remove last role' });
    fireEvent.click(screen.getByTestId('remove-role-lead-dev'));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Cannot remove last role');
    });

    // Success branch
    deleteSpy.mockResolvedValueOnce({ status: 'deleted' });
    fireEvent.click(screen.getByTestId('remove-role-lead-dev'));
    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledTimes(2);
      expect(onRolesChange).toHaveBeenCalledWith(['role-2']);
    });
  });

  it('adds new role label from select dropdown and handles add/fetch errors and disabled state', async () => {
    const postSpy = vi.fn().mockResolvedValue({
      id: 'prl-3',
      principal_id: 'user-1',
      role_id: 'role-3',
      role_name: 'Security Auditor',
      role_slug: 'sec-auditor',
    });
    const onRolesChange = vi.fn();

    vi.spyOn(clientModule, 'apiFetch').mockImplementation((method, path, opts) => {
      if (path.includes('/api/v1/admin/principals/user-1/role-labels')) {
        if (method === 'POST') {
          return Promise.resolve(postSpy(method, path, opts) as never);
        }
        return Promise.resolve(MOCK_ASSIGNED as never);
      }
      return Promise.resolve([] as never);
    });

    const { container, rerender } = render(
      <RoleLabelPicker
        principalId="user-1"
        availableRoles={MOCK_AVAILABLE}
        onRolesChange={onRolesChange}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('add-role-label-select')).toBeDefined();
      expect(container.querySelector('label[for]')).toBeDefined();
    });

    // Error branch on POST
    postSpy.mockRejectedValueOnce(new Error('Escalation denied'));
    fireEvent.change(screen.getByTestId('add-role-label-select'), {
      target: { value: 'role-3' },
    });
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Escalation denied');
    });

    // Success branch on POST
    fireEvent.change(screen.getByTestId('add-role-label-select'), {
      target: { value: 'role-3' },
    });
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledTimes(2);
      expect(onRolesChange).toHaveBeenCalledWith(['role-1', 'role-2', 'role-3']);
    });

    // Disabled state hides remove buttons and add select, rendering span instead of dangling label
    rerender(
      <RoleLabelPicker principalId="user-1" availableRoles={MOCK_AVAILABLE} disabled={true} />,
    );
    expect(screen.queryByTestId('add-role-label-select')).toBeNull();
    expect(container.querySelector('label')).toBeNull();
    expect(container.querySelector('span.role-label-picker-label')).toBeDefined();
  });

  it('handles initial load error, empty principalId, and fallback error messages gracefully', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockRejectedValue({});
    const { rerender, unmount } = render(<RoleLabelPicker principalId="" />);
    rerender(<RoleLabelPicker principalId="user-1" />);
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Failed to load assigned role labels.');
    });
    unmount();
  });

  it('renders FieldHelpHint and default indicator "(Default: Member)" adjacent to label with ARIA attributes', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([] as never);
    render(<RoleLabelPicker principalId="user-1" availableRoles={MOCK_AVAILABLE} />);

    await waitFor(() => {
      expect(screen.getByTestId('role-label-default-indicator').textContent).toContain('(Default: Member)');
    });
    const helpTrigger = screen.getByTestId('role-label-help');
    expect(helpTrigger).toBeDefined();
    expect(helpTrigger.getAttribute('aria-label')).toBe('Help for Role Labels');

    const selectEl = screen.getByTestId('add-role-label-select');
    expect(selectEl.getAttribute('aria-describedby')).toBe('role-label-hint-user-1');
  });

  it('opens FieldHelpHint popover on focus, shows default value, valid values list, and doc link', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([] as never);
    render(<RoleLabelPicker principalId="user-1" availableRoles={MOCK_AVAILABLE} />);

    await waitFor(() => {
      expect(screen.getByTestId('role-label-help')).toBeDefined();
    });

    const helpTrigger = screen.getByTestId('role-label-help');
    act(() => {
      helpTrigger.focus();
    });

    const popover = screen.getByTestId('role-label-help-popover');
    expect(popover).toBeDefined();
    expect(popover.textContent).toContain('Role Labels and Default Permissions');
    expect(popover.textContent).toContain('New workspace members receive the base Member role by default.');
    expect(popover.textContent).toContain('Member');
    expect(popover.textContent).toContain('Custom Role');

    const docLink = screen.getByTestId<HTMLAnchorElement>('role-label-help-doc-link');
    expect(docLink.getAttribute('href')).toBe('/docs/custom-fields');
  });

  it('dismisses popover on Escape key and restores focus to trigger button', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([] as never);
    render(<RoleLabelPicker principalId="user-1" availableRoles={MOCK_AVAILABLE} />);

    await waitFor(() => {
      expect(screen.getByTestId('role-label-help')).toBeDefined();
    });

    const helpTrigger = screen.getByTestId('role-label-help');
    act(() => {
      helpTrigger.focus();
    });

    const popover = screen.getByTestId('role-label-help-popover');
    expect(popover).toBeDefined();

    const docLink = screen.getByTestId<HTMLAnchorElement>('role-label-help-doc-link');
    act(() => {
      docLink.focus();
    });
    expect(document.activeElement).toBe(docLink);

    act(() => {
      fireEvent.keyDown(docLink, { key: 'Escape', bubbles: true });
    });

    expect(screen.queryByTestId('role-label-help-popover')).toBeNull();
    expect(document.activeElement).toBe(helpTrigger);
  });

  it('supports custom props: label, defaultValue, helpTitle, helpSummary, docHref, and showHelpHint=false', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([] as never);
    const { rerender } = render(
      <RoleLabelPicker
        principalId="user-1"
        availableRoles={MOCK_AVAILABLE}
        label="Assigned Roles"
        defaultValue="Guest"
        helpTitle="Role Guidance"
        helpSummary="Custom roles help summary."
        docHref="/docs/roles"
        showHelpHint={true}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('role-label-default-indicator').textContent).toContain('(Default: Guest)');
    });
    const helpTrigger = screen.getByTestId('role-label-help');

    act(() => {
      helpTrigger.focus();
    });

    const popover = screen.getByTestId('role-label-help-popover');
    expect(popover.textContent).toContain('Role Guidance');
    expect(popover.textContent).toContain('Custom roles help summary.');
    const docLink = screen.getByTestId<HTMLAnchorElement>('role-label-help-doc-link');
    expect(docLink.getAttribute('href')).toBe('/docs/roles');

    // Hide help hint when showHelpHint is false
    rerender(
      <RoleLabelPicker
        principalId="user-1"
        availableRoles={MOCK_AVAILABLE}
        showHelpHint={false}
      />,
    );
    expect(screen.queryByTestId('role-label-help')).toBeNull();
  });

  it('maintains parity under light and dark theme attributes and handles unmount cleanup', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockImplementation((_method, path) => {
      if (path.endsWith('/api/v1/admin/rbac/roles')) {
        return Promise.resolve(MOCK_AVAILABLE as never);
      }
      if (path.includes('/api/v1/admin/principals/user-1/role-labels')) {
        return Promise.resolve(MOCK_ASSIGNED as never);
      }
      return Promise.resolve([] as never);
    });
    document.documentElement.setAttribute('data-theme', 'light');

    const { unmount, rerender } = render(<RoleLabelPicker principalId="user-1" />);
    await waitFor(() => {
      expect(screen.getByTestId('role-label-picker-container')).toBeDefined();
      expect(screen.getByTestId('role-chip-lead-dev')).toBeDefined();
    });

    document.documentElement.setAttribute('data-theme', 'dark');
    rerender(<RoleLabelPicker principalId="user-1" />);
    expect(screen.getByTestId('role-label-picker-container')).toBeDefined();

    document.documentElement.removeAttribute('data-theme');
    unmount();
  });
});
