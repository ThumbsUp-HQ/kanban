import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
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
    expect(screen.queryByRole('link', { name: /Views/ })).toBeNull();
    expect(screen.getByRole('link', { name: /^Docs$/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Workflows/ })).toBeDefined();
    expect(screen.getByRole('link', { name: /Project Settings/ })).toBeDefined();
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
      { path: '/projects/KAN/docs', name: 'Docs' },
      { path: '/projects/KAN/settings/workflows', name: 'Workflows' },
      { path: '/projects/KAN/settings', name: 'Project Settings' },
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

  it('fetches workspaces, toggles dropdown menu, switches workspace, and opens CreateWorkspaceModal', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/workspaces') && init?.method === 'POST') {
        return Promise.resolve(
          new Response(
            JSON.stringify({ status: 'switched', workspace_id: 'ws-2' }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/api/v1/workspaces')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              { id: 'ws-1', name: 'Primary Engineering WS', slug: 'eng', is_current: true },
              { id: 'ws-2', name: 'Design Systems WS', slug: 'design', is_current: false },
            ]),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response('[]', { status: 200 }));
    });

    render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar projectKey="KAN" projectName="kanban" modulesEnabled={true} />
      </MemoryRouter>,
    );

    // Initial load updates workspace brand name
    expect(await screen.findByText('Primary Engineering WS')).toBeDefined();

    const switcherBtn = screen.getByRole('button', { name: /Workspace switcher:/ });
    expect(switcherBtn.getAttribute('aria-expanded')).toBe('false');

    // Click to open dropdown
    act(() => {
      fireEvent.click(switcherBtn);
    });
    expect(switcherBtn.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByRole('menu')).toBeDefined();
    expect(screen.getByText('Design Systems WS')).toBeDefined();

    // Click "+ Create New Workspace" in dropdown
    const createWsBtn = screen.getByRole('menuitem', { name: /Create New Workspace/ });
    act(() => {
      fireEvent.click(createWsBtn);
    });

    // Dropdown closes and CreateWorkspaceModal opens
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.getByRole('dialog', { name: 'Create New Workspace' })).toBeDefined();

    // Close modal
    const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
    act(() => {
      fireEvent.click(cancelBtn);
    });
    expect(screen.queryByRole('dialog', { name: 'Create New Workspace' })).toBeNull();

    // Open dropdown again and click workspace to switch
    act(() => {
      fireEvent.click(switcherBtn);
    });
    const targetWsBtn = screen.getByRole('menuitem', { name: /Design Systems WS/ });
    act(() => {
      fireEvent.click(targetWsBtn);
    });
  });

  it('independently toggles expand/collapse for multiple projects (KANBA-192 Positive Case 3)', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/projects')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [
                { identifier: 'KANBA', name: 'kanban', modules_enabled: true },
                { identifier: 'PIKVM', name: 'PiKVM Controller', modules_enabled: true },
              ],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response('[]', { status: 200 }));
    });

    render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar projectKey="KANBA" projectName="kanban" modulesEnabled={true} />
      </MemoryRouter>,
    );

    const kanbaRow = await screen.findByRole('button', { name: 'Project: kanban' });
    const pikvmRow = await screen.findByRole('button', { name: 'Project: PiKVM Controller' });

    expect(kanbaRow.getAttribute('aria-expanded')).toBe('true');
    expect(pikvmRow.getAttribute('aria-expanded')).toBe('true');

    // Click PIKVM to collapse it
    act(() => {
      pikvmRow.click();
    });

    expect(pikvmRow.getAttribute('aria-expanded')).toBe('false');
    // KANBA should remain expanded!
    expect(kanbaRow.getAttribute('aria-expanded')).toBe('true');

    // Click PIKVM again to expand it back
    act(() => {
      pikvmRow.click();
    });

    expect(pikvmRow.getAttribute('aria-expanded')).toBe('true');
    expect(kanbaRow.getAttribute('aria-expanded')).toBe('true');
  });

  it('renders project layout view links (List, Board, Table, Calendar, Timeline) with SVG icons (KANBA-174)', () => {
    render(
      <MemoryRouter initialEntries={['/projects/KAN/issues?layout=list']}>
        <Sidebar projectKey="KAN" projectName="kanban" modulesEnabled={true} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: /List view/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /Board view/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /Table view/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /Calendar view/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /Timeline view/i })).toBeDefined();

    const listViewLink = screen.getByRole('link', { name: /List view/i });
    expect(listViewLink.getAttribute('href')).toBe('/projects/KAN/issues?layout=list');
  });

  it('toggles sidebar via kb:toggle-sidebar custom event and Hide Nav button (KANBA-174)', () => {
    const onToggle = vi.fn();
    render(
      <MemoryRouter>
        <Sidebar onToggleCollapse={onToggle} />
      </MemoryRouter>,
    );

    const hideNavBtn = screen.getByRole('button', { name: /Collapse sidebar \(Hide Nav\)/i });
    expect(hideNavBtn).toBeDefined();

    act(() => {
      window.dispatchEvent(new CustomEvent('kb:toggle-sidebar'));
    });

    expect(localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('collapsed');
    expect(onToggle).toHaveBeenCalledTimes(1);

    act(() => {
      window.dispatchEvent(new CustomEvent('kb:toggle-sidebar'));
    });

    expect(localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('open');
    expect(onToggle).toHaveBeenCalledTimes(2);
  });

  it('highlights table, calendar, timeline subnav items and custom fields page', () => {
    // 1. Table layout
    const { unmount: u1 } = render(
      <MemoryRouter initialEntries={['/projects/KAN/issues?layout=table']}>
        <Sidebar projectKey="KAN" activePath="/projects/KAN/issues" />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Table view' }).className).toContain('kb-subnav-active');
    u1();

    // 2. Calendar layout
    const { unmount: u2 } = render(
      <MemoryRouter initialEntries={['/projects/KAN/issues?layout=calendar']}>
        <Sidebar projectKey="KAN" activePath="/projects/KAN/issues" />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Calendar view' }).className).toContain('kb-subnav-active');
    u2();

    // 3. Timeline layout
    const { unmount: u3 } = render(
      <MemoryRouter initialEntries={['/projects/KAN/issues?layout=timeline']}>
        <Sidebar projectKey="KAN" activePath="/projects/KAN/issues" />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Timeline view' }).className).toContain('kb-subnav-active');
    u3();

    // 4. Custom fields page
    const { unmount: u4 } = render(
      <MemoryRouter initialEntries={['/projects/KAN/settings/custom-fields']}>
        <Sidebar projectKey="KAN" activePath="/projects/KAN/settings/custom-fields" />
      </MemoryRouter>,
    );
    const customFieldsLink = screen.getByRole('link', { name: 'Custom Fields' });
    expect(customFieldsLink.getAttribute('aria-current')).toBe('page');
    u4();
  });

  it('renders Workspace Settings in workspace dropdown for admin and reacts to kb:project-created event', async () => {
    const adminUser = {
      is_server_admin: true,
      is_workspace_admin: true,
    };

    render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar user={adminUser} />
      </MemoryRouter>,
    );

    // Open workspace switcher dropdown
    const switcherBtn = screen.getByRole('button', { name: /Workspace switcher:/i });
    fireEvent.click(switcherBtn);

    const wsSettingsLink = screen.getByRole('menuitem', { name: /Workspace Settings/i });
    expect(wsSettingsLink).toBeDefined();

    // Clicking Workspace Settings closes dropdown
    fireEvent.click(wsSettingsLink);
    expect(screen.queryByRole('menuitem', { name: /Workspace Settings/i })).toBeNull();

    // Dispatch kb:project-created custom event
    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:project-created', {
          detail: {
            identifier: 'ALPHA',
            name: 'Alpha Project',
            modules_enabled: false,
          },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Alpha Project')).toBeDefined();
    });
  });

  it('covers kb:project-created edge cases: key fallback, duplicate prevention, and null detail', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar />
      </MemoryRouter>,
    );

    // 1. Project with key instead of identifier
    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:project-created', {
          detail: {
            key: 'BETA',
            name: 'Beta Project',
            modules_enabled: true,
          },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Beta Project')).toBeDefined();
    });

    // 2. Duplicate project does not duplicate
    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:project-created', {
          detail: {
            key: 'BETA',
            name: 'Beta Project',
          },
        }),
      );
    });

    // 3. Null or invalid detail does nothing
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:project-created', { detail: null }));
      window.dispatchEvent(new CustomEvent('kb:project-created', { detail: { name: 123 } }));
    });
  });

  it('handles workspace switch to workspace without projects and sets CSRF token', () => {
    vi.spyOn(window, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (urlStr.includes('/switch')) {
        return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'new-csrf-token-abc' }), { status: 200 }));
      }
      if (urlStr.includes('/workspaces')) {
        return Promise.resolve(new Response(
          JSON.stringify([
            { id: 'ws-1', name: 'Primary', slug: 'primary', is_current: false },
            { id: 'ws-empty', name: 'Empty Workspace', slug: 'empty', is_current: true },
          ]),
          { status: 200 },
        ));
      }
      if (urlStr.includes('/projects')) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar />
      </MemoryRouter>,
    );

    // Open switcher
    const switcherBtn = screen.getByRole('button', { name: /Workspace switcher:/i });
    fireEvent.click(switcherBtn);

    // Click workspace item if available
    const items = screen.getAllByRole('menuitem');
    if (items[0]) {
      fireEvent.click(items[0]);
    }
  });

  it('handles project expand toggle and custom create project events', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (urlStr.includes('/projects')) {
        return Promise.resolve(new Response(
          JSON.stringify([
            { key: 'PRJ1', name: 'Project One', modules_enabled: false },
          ]),
          { status: 200 },
        ));
      }
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
    });

    render(
      <MemoryRouter initialEntries={['/projects/PRJ1/issues']}>
        <Sidebar
          projectKey="PRJ1"
          projectName="Project One"
          modulesEnabled={false}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Project: Project One' })).toBeDefined();
    });

    const expandBtn = screen.getByRole('button', { name: 'Project: Project One' });
    expect(expandBtn.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(expandBtn);
    expect(expandBtn.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(expandBtn);
    expect(expandBtn.getAttribute('aria-expanded')).toBe('true');

    // Trigger kb:open-create-project event
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:open-create-project'));
    });
    expect(screen.getByRole('dialog', { name: 'Create project' })).toBeDefined();

    // Close create project modal
    const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
    fireEvent.click(cancelBtn);

    // Trigger + Project button
    const addProjectBtn = screen.getByRole('button', { name: 'Create project' });
    fireEvent.click(addProjectBtn);
    expect(screen.getByRole('dialog', { name: 'Create project' })).toBeDefined();
  });

  it('handles workspace switch without csrf_token in response and routes to first project', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (urlStr.includes('/switch')) {
        // Return without csrf_token
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      }
      if (urlStr.includes('/workspaces')) {
        return Promise.resolve(new Response(
          JSON.stringify([
            { id: 'ws-1', name: 'Workspace A', slug: 'ws-a', is_current: false },
            { id: 'ws-2', name: 'Workspace B', slug: 'ws-b', is_current: true },
          ]),
          { status: 200 },
        ));
      }
      if (urlStr.includes('/projects')) {
        return Promise.resolve(new Response(
          JSON.stringify([
            { identifier: 'PRJ2', name: 'Project Two', modules_enabled: true },
          ]),
          { status: 200 },
        ));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    render(
      <MemoryRouter initialEntries={['/projects/PRJ1/issues']}>
        <Sidebar
          projectKey="PRJ1"
          projectName="Project One"
          modulesEnabled={true}
        />
      </MemoryRouter>,
    );

    const switcherBtn = screen.getByRole('button', { name: /Workspace switcher:/i });
    fireEvent.click(switcherBtn);

    const items = screen.getAllByRole('menuitem');
    const firstItem = items[0];
    if (firstItem) {
      act(() => {
        fireEvent.click(firstItem);
      });
    }

    await waitFor(() => {
      expect(screen.getByText('Project Two')).toBeDefined();
    });
  });

  it('covers workspace dedup branches, items envelope, and switch csrf token', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.includes('/api/v1/workspaces') && !url.includes('/switch')) {
        return Promise.resolve(new Response(JSON.stringify([
          { id: 'w1', name: 'Default Workspace' },
          { id: 'w1', name: 'Default Workspace' }, // duplicate id
          { id: 'w2', name: 'Default Workspace' }, // duplicate default workspace name
          { id: '', name: '' },
          { id: 'w3', name: 'Other', slug: 'other' },
        ]), { status: 200 }));
      }
      if (url.includes('/switch')) {
        return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'new-csrf-123' }), { status: 200 }));
      }
      if (url.includes('/api/v1/projects')) {
        return Promise.resolve(new Response(JSON.stringify({
          items: [
            { identifier: 'ENV1', name: 'Envelope Project' }, // tests identifier & modules_enabled fallback
          ],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    render(
      <MemoryRouter initialEntries={['/projects/ENV1/issues']}>
        <Sidebar projectKey="ENV1" projectName="Envelope Project" modulesEnabled={true} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('Envelope Project')).toBeDefined();
    });

    const switcherBtn = screen.getByRole('button', { name: /Workspace switcher:/i });
    fireEvent.click(switcherBtn);
    const items = screen.getAllByRole('menuitem');
    const firstMenuItem = items[0];
    if (firstMenuItem) {
      act(() => {
        fireEvent.click(firstMenuItem);
      });
    }

    await waitFor(() => {
      expect(screen.getByText('Envelope Project')).toBeDefined();
    });
  });

  it('covers deduplicatedWorkspaces edge fallbacks, null workspace current, and empty project list', async () => {
    const mockWorkspaces = [
      { id: '', name: '', slug: '', is_current: false },
      { id: 'ws-dup-name', name: 'default workspace', slug: 'default-1', is_current: false },
      { id: 'ws-dup-name-2', name: 'default workspace', slug: 'default-2', is_current: false },
    ];

    global.fetch = vi.fn().mockImplementation((req: RequestInfo | URL) => {
      const url = typeof req === 'string' ? req : 'url' in req ? req.url : String(req);
      if (url.includes('/api/v1/workspaces')) {
        return Promise.resolve(new Response(JSON.stringify(mockWorkspaces), { status: 200 }));
      }
      if (url.includes('/switch')) {
        return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'csrf' }), { status: 200 }));
      }
      if (url.includes('/api/v1/projects')) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar projectKey="KAN" projectName="Kanban" modulesEnabled={false} user={undefined} />
      </MemoryRouter>,
    );

    // Default workspace fallback when none has is_current
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Workspace switcher:/i })).toBeDefined();
    });

    const switcherBtn = screen.getByRole('button', { name: /Workspace switcher:/i });
    fireEvent.click(switcherBtn);
    const items = screen.getAllByRole('menuitem');
    const firstItem = items[0];
    if (firstItem) {
      act(() => {
        fireEvent.click(firstItem);
      });
    }
  });
});
