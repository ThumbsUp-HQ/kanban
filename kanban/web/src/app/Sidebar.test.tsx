import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import {
  Sidebar,
  sanitizeSidebarState,
  SIDEBAR_STORAGE_KEY,
} from './Sidebar';

describe('Sidebar', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('sanitizes hostile localStorage sidebar state to open', () => {
    expect(sanitizeSidebarState('open')).toBe('open');
    expect(sanitizeSidebarState('collapsed')).toBe('collapsed');
    expect(sanitizeSidebarState('evil')).toBe('open');
    expect(sanitizeSidebarState(null)).toBe('open');
    expect(sanitizeSidebarState('<script>alert(1)</script>')).toBe('open');
  });

  it('renders sidebar navigation items in the specified order with [👍] 👍kanban branding', () => {
    render(
      <MemoryRouter initialEntries={['/projects/KAN/issues']}>
        <Sidebar projectKey="KAN" projectName="kanban" modulesEnabled={true} />
      </MemoryRouter>,
    );

    // Workspace branding
    expect(screen.getByText(/👍kanban/)).toBeDefined();
    expect(screen.getByText('+')).toBeDefined();
    expect(screen.getByText('New work item')).toBeDefined();

    // Section headings
    expect(screen.getByText('Workspace')).toBeDefined();
    expect(screen.getByText('Projects')).toBeDefined();

    // Workspace items
    expect(screen.getByRole('link', { name: /Home/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Drafts/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Your work/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Stickies/ })).toBeDefined();

    // Project items
    const workItemsLink = screen.getByRole('link', { name: /Work Items/ });
    expect(workItemsLink).toBeDefined();
    expect(workItemsLink.getAttribute('aria-current')).toBe('page');

    expect(screen.getByRole('link', { name: /Cycles/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Modules/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Views/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Docs \(Pages\)/ })).toBeDefined();
  });

  it('unmounts 🧩 Modules completely from the DOM when modulesEnabled is false', () => {
    render(
      <MemoryRouter>
        <Sidebar projectKey="KAN" projectName="kanban" modulesEnabled={false} />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('link', { name: /Modules/ })).toBeNull();
  });

  it('toggles collapse state via button and keyboard shortcut, persisting to localStorage', () => {
    const onToggle = vi.fn();
    render(
      <MemoryRouter>
        <Sidebar onToggleCollapse={onToggle} />
      </MemoryRouter>,
    );

    const collapseBtn = screen.getByRole('button', { name: /Collapse sidebar/ });
    act(() => {
      collapseBtn.click();
    });

    expect(localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('collapsed');
    expect(onToggle).toHaveBeenCalledTimes(1);

    // Trigger keyboard '['
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: '[' }));
    });

    expect(localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('open');
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it('handles mobile overlay dialog, focus trapping, and Escape closing', async () => {
    const triggerBtn = document.createElement('button');
    triggerBtn.textContent = 'Hamburger';
    document.body.appendChild(triggerBtn);

    const triggerRef = { current: triggerBtn };
    const onClose = vi.fn();

    // Mock mobile window width
    vi.stubGlobal('innerWidth', 1024);

    render(
      <MemoryRouter>
        <Sidebar
          isOpen={true}
          onClose={onClose}
          triggerButtonRef={triggerRef}
        />
      </MemoryRouter>,
    );

    // Wait for setTimeout to execute firstItemRef focus
    await new Promise((r) => setTimeout(r, 20));

    const dialog = screen.getByRole('dialog', { name: 'Sidebar navigation' });
    expect(dialog).toBeDefined();

    // Click scrim to close
    const scrim = document.querySelector('.kb-sidebar-scrim');
    expect(scrim).not.toBeNull();
    if (scrim) {
      act(() => {
        fireEvent.click(scrim);
      });
    }
    expect(onClose).toHaveBeenCalled();

    // Press Escape
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(document.activeElement).toBe(triggerBtn);

    document.body.removeChild(triggerBtn);
    vi.unstubAllGlobals();
  });

  it('collapses and expands project subitems section', () => {
    render(
      <MemoryRouter>
        <Sidebar projectKey="KAN" projectName="kanban" />
      </MemoryRouter>,
    );

    const projectRow = screen.getByRole('button', { name: 'Project: kanban' });
    expect(projectRow.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByRole('link', { name: /Work Items/ })).toBeDefined();

    act(() => {
      projectRow.click();
    });

    expect(projectRow.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('link', { name: /Work Items/ })).toBeNull();
  });

  it('traps Tab and Shift+Tab key navigation in mobile dialog', () => {
    vi.stubGlobal('innerWidth', 1024);

    render(
      <MemoryRouter>
        <Sidebar isOpen={true} />
      </MemoryRouter>,
    );

    const dialog = screen.getByRole('dialog', { name: 'Sidebar navigation' });
    const focusables = dialog.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    if (first && last) {
      first.focus();
      fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
      expect(document.activeElement).toBe(last);

      last.focus();
      fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: false });
      expect(document.activeElement).toBe(first);
    }

    // Tab and Shift+Tab when focus is on a middle element
    if (focusables.length > 2 && focusables[1]) {
      focusables[1].focus();
      fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: false });
      fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
    }

    vi.unstubAllGlobals();
  });

  it('handles localStorage errors gracefully falling back to open', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('QuotaExceeded');
    });

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByText('Projects')).toBeDefined();
  });

  it('triggers create issue event on new work item click', () => {
    const listener = vi.fn();
    window.addEventListener('kb:create-issue', listener);

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    const btn = screen.getByRole('button', { name: /New work item/ });
    act(() => {
      btn.click();
    });

    expect(listener).toHaveBeenCalled();
    window.removeEventListener('kb:create-issue', listener);
  });

  it('sets aria-current on active workspace and project subitem links', () => {
    const routesToTest = [
      { path: '/drafts', name: 'Drafts' },
      { path: '/your-work', name: 'Your work' },
      { path: '/stickies', name: 'Stickies' },
      { path: '/projects/KAN/cycles', name: 'Cycles' },
      { path: '/projects/KAN/modules', name: 'Modules' },
      { path: '/projects/KAN/views', name: 'Views' },
      { path: '/projects/KAN/docs', name: 'Docs (Pages)' },
    ];

    for (const { path, name } of routesToTest) {
      const { unmount } = render(
        <MemoryRouter initialEntries={[path]}>
          <Sidebar projectKey="KAN" projectName="kanban" modulesEnabled={true} />
        </MemoryRouter>,
      );

      const link = screen.getByRole('link', { name });
      expect(link.getAttribute('aria-current')).toBe('page');
      unmount();
    }
  });

  it('fetches dynamic projects from /api/v1/projects and opens CreateProjectModal via + Project button or custom event', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/projects')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [
                { identifier: 'KAN', name: 'kanban', modules_enabled: true },
                { identifier: 'SEC', name: 'Security', modules_enabled: true },
              ],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar projectKey="KAN" projectName="kanban" modulesEnabled={true} />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('button', { name: 'Project: Security' })).toBeDefined();

    const createBtn = screen.getByRole('button', { name: 'Create project' });
    act(() => {
      createBtn.click();
    });
    expect(screen.getByTestId('create-project-modal')).toBeDefined();

    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    });
    expect(screen.queryByTestId('create-project-modal')).toBeNull();

    act(() => {
      window.dispatchEvent(new CustomEvent('kb:open-create-project'));
    });
    expect(screen.getByTestId('create-project-modal')).toBeDefined();

    act(() => {
      window.dispatchEvent(new CustomEvent('kb:project-created'));
    });
  });
});
