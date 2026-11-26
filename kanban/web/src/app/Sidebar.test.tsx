import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import {
  Sidebar,
  sanitizeSidebarState,
  extractProjectKeyFromPath,
  SIDEBAR_STORAGE_KEY,
} from './Sidebar';

describe('Sidebar', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('sanitizes hostile localStorage sidebar state to open', () => {
    expect(SIDEBAR_STORAGE_KEY).toBe('kb.sidebar');
    expect(sanitizeSidebarState('open')).toBe('open');
    expect(sanitizeSidebarState('collapsed')).toBe('collapsed');
    expect(sanitizeSidebarState('evil')).toBe('open');
    expect(sanitizeSidebarState(null)).toBe('open');
    expect(sanitizeSidebarState('<script>alert(1)</script>')).toBe('open');
  });

  it('renders sidebar navigation items with WorkspaceBadge and workspace brand', () => {
    render(
      <MemoryRouter initialEntries={['/projects/KAN/issues']}>
        <Sidebar projectKey="KAN" projectName="kanban" modulesEnabled={true} />
      </MemoryRouter>,
    );

    // Workspace branding with WorkspaceBadge
    expect(screen.getByTestId('workspace-badge')).toBeDefined();
    expect(screen.queryByText('[👍]')).toBeNull();
    expect(screen.getByRole('button', { name: 'Collapse navigation sidebar' })).toBeDefined();
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
    expect(screen.getAllByRole('link', { name: /Docs/ }).length).toBeGreaterThan(0);
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

  it('toggles collapse state via button next to workspace switcher, persisting to localStorage', () => {
    const onToggle = vi.fn();
    render(
      <MemoryRouter>
        <Sidebar onToggleCollapse={onToggle} />
      </MemoryRouter>,
    );

    const collapseBtn = screen.getByRole('button', { name: 'Collapse navigation sidebar' });
    act(() => {
      collapseBtn.click();
    });

    expect(onToggle).toHaveBeenCalledTimes(1);
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
      <MemoryRouter initialEntries={['/']}>
        <Sidebar projectKey="KAN" projectName="kanban" />
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

      const links = screen.getAllByRole('link', { name });
      expect(links.some((l) => l.getAttribute('aria-current') === 'page')).toBe(true);
      unmount();
    }
  });

  it('fetches dynamic projects from /api/v1/projects and opens CreateProjectModal via + Project button or custom event', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/projects')) {
        if (init?.method === 'POST') {
          return Promise.resolve(
            new Response(
              JSON.stringify({ identifier: 'NEW', name: 'New Project', modules_enabled: true }),
              { status: 201, headers: { 'Content-Type': 'application/json' } },
            ),
          );
        }
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

    document.cookie = 'csrf_token=test-csrf-token';
    const nameInput = screen.getByLabelText(/Project Name/i);
    const idInput = screen.getByLabelText('Project Key', { selector: 'input' });
    act(() => {
      fireEvent.change(nameInput, { target: { value: 'New Project' } });
      fireEvent.change(idInput, { target: { value: 'NEW' } });
    });
    const form = screen.getByTestId('create-project-submit').closest('form');
    expect(form).not.toBeNull();
    if (form) {
      act(() => {
        fireEvent.submit(form);
      });
    }

    await waitFor(() => {
      expect(screen.queryByTestId('create-project-modal')).toBeNull();
    });

    act(() => {
      window.dispatchEvent(new CustomEvent('kb:project-created'));
    });
    await waitFor(() => {
      expect(screen.getByText('Security')).toBeDefined();
    });
  });

  it('covers CreateProjectModal onCreated callback duplicate and modules_enabled branches', async () => {
    let postCallCount = 0;
    const fetchSpy = vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/projects')) {
        if (init?.method === 'POST') {
          postCallCount++;
          if (postCallCount === 1) {
            return Promise.resolve(
              new Response(
                JSON.stringify({ identifier: 'ALPHA', name: 'Alpha Project' }),
                { status: 201, headers: { 'Content-Type': 'application/json' } },
              ),
            );
          }
          return Promise.resolve(
            new Response(
              JSON.stringify({ identifier: 'ALPHA', name: 'Alpha Project', modules_enabled: true }),
              { status: 201, headers: { 'Content-Type': 'application/json' } },
            ),
          );
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [{ identifier: 'KAN', name: 'kanban', modules_enabled: true }],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    const { unmount } = render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar projectKey="KAN" projectName="kanban" modulesEnabled={true} />
      </MemoryRouter>,
    );

    act(() => {
      window.dispatchEvent(new CustomEvent('kb:open-create-project'));
    });
    expect(screen.getByTestId('create-project-modal')).toBeDefined();

    document.cookie = 'csrf_token=test-csrf-token';
    const nameInput = screen.getByLabelText(/Project Name/i);
    const idInput = screen.getByLabelText('Project Key', { selector: 'input' });
    act(() => {
      fireEvent.change(nameInput, { target: { value: 'Alpha Project' } });
      fireEvent.change(idInput, { target: { value: 'ALPHA' } });
    });
    const form = screen.getByTestId('create-project-submit').closest('form');
    expect(form).not.toBeNull();
    if (form) {
      act(() => {
        fireEvent.submit(form);
      });
    }
    await waitFor(() => {
      expect(screen.queryByTestId('create-project-modal')).toBeNull();
    });

    act(() => {
      window.dispatchEvent(new CustomEvent('kb:open-create-project'));
    });
    expect(screen.getByTestId('create-project-modal')).toBeDefined();
    const dupNameInput = screen.getByLabelText(/Project Name/i);
    const dupIdInput = screen.getByLabelText('Project Key', { selector: 'input' });
    act(() => {
      fireEvent.change(dupNameInput, { target: { value: 'Alpha Project' } });
      fireEvent.change(dupIdInput, { target: { value: 'ALPHA' } });
    });
    const dupForm = screen.getByTestId('create-project-submit').closest('form');
    if (dupForm) {
      act(() => {
        fireEvent.submit(dupForm);
      });
    }
    await waitFor(() => {
      expect(screen.queryByTestId('create-project-modal')).toBeNull();
    });

    unmount();
    fetchSpy.mockRestore();
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
    await waitFor(() => {
      expect(screen.queryByRole('menu')).toBeNull();
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

    expect(screen.getByRole('link', { name: /Issues view/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /Board view/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /Table view/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /Calendar view/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /Timeline view/i })).toBeDefined();

    const listViewLink = screen.getByRole('link', { name: /Issues view/i });
    expect(listViewLink.getAttribute('href')).toBe('/projects/KAN/issues?layout=list');
  });

  it('toggles sidebar collapse via header button next to workspace switcher', () => {
    const onToggle = vi.fn();
    render(
      <MemoryRouter>
        <Sidebar onToggleCollapse={onToggle} />
      </MemoryRouter>,
    );

    const collapseBtn = screen.getByRole('button', { name: 'Collapse navigation sidebar' });
    expect(collapseBtn).toBeDefined();

    act(() => {
      collapseBtn.click();
    });

    expect(onToggle).toHaveBeenCalledTimes(1);
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

  it('handles workspace switch to workspace without projects and sets CSRF token', async () => {
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
    const firstItem = items[0];
    if (firstItem) {
      act(() => {
        fireEvent.click(firstItem);
      });
      await waitFor(() => {
        expect(screen.queryByRole('menu')).toBeNull();
      });
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
      await waitFor(() => {
        expect(screen.queryByRole('menu')).toBeNull();
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
      await waitFor(() => {
        expect(screen.queryByRole('menu')).toBeNull();
      });
    }
  });

  it('covers no-projects empty state, custom events, and project expand toggle', async () => {
    let mockProjects: { identifier: string; name: string; modules_enabled?: boolean }[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.includes('/api/v1/workspaces') && !url.includes('/switch')) {
        return Promise.resolve(new Response(JSON.stringify([{ id: 'ws-out', name: 'Outside WS' }]), { status: 200 }));
      }
      if (url.includes('/switch')) {
        return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'csrf-outside' }), { status: 200 }));
      }
      if (url.includes('/api/v1/projects')) {
        return Promise.resolve(new Response(JSON.stringify(mockProjects), { status: 200 }));
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    const { unmount } = render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar projectKey="" projectName="" modulesEnabled={false} />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('sidebar-no-projects')).toBeDefined();
    });

    // Test workspace switch
    const switcherBtn = screen.getByRole('button', { name: /Workspace switcher:/i });
    fireEvent.click(switcherBtn);
    const menuItems = screen.getAllByRole('menuitem');
    const firstWs = menuItems[0];
    if (firstWs) {
      act(() => {
        fireEvent.click(firstWs);
      });
      await waitFor(() => {
        expect(screen.queryByRole('menu')).toBeNull();
      });
    }

    // 2. Dispatch custom events
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:open-create-project'));
    });
    expect(screen.getByTestId('create-project-modal')).toBeDefined();

    mockProjects = [{ identifier: 'EVT-PRJ', name: 'Event Project', modules_enabled: false }];
    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:project-created', {
          detail: { identifier: 'EVT-PRJ', name: 'Event Project', modules_enabled: false },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Event Project')).toBeDefined();
    });

    // 3. Toggle expand / collapse project
    const expandBtn = await screen.findByRole('button', { name: 'Project: Event Project' });
    expect(expandBtn.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(expandBtn);
    expect(expandBtn.getAttribute('aria-expanded')).toBe('false');

    // 4. Dispatch kb:workspace-created event
    act(() => {
      window.dispatchEvent(
        new CustomEvent('kb:workspace-created', {
          detail: { id: 'ws-new-created', name: 'New Created Workspace' },
        }),
      );
    });

    unmount();
  });

  it('covers remaining branches: outside click, escape key, mobile tab cycle, fetch fallbacks, and local collapse', () => {
    // 1. fetchWorkspaces with non-array response & fetchProjects with error res
    const fetchSpy = vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const u = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (u.includes('/workspaces/current')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ notAnArray: true }) } as unknown as Response);
      }
      if (u.includes('/projects')) {
        return Promise.resolve({ ok: false, status: 500 } as unknown as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as unknown as Response);
    });

    // 2. Local collapse without onToggleCollapse prop
    localStorage.removeItem('kb.sidebar');
    const { unmount } = render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    const collapseBtn = screen.getByRole('button', { name: 'Collapse navigation sidebar' });
    act(() => {
      collapseBtn.click();
    });
    expect(localStorage.getItem('kb.sidebar')).toBe('collapsed');
    act(() => {
      collapseBtn.click();
    });
    expect(localStorage.getItem('kb.sidebar')).toBe('open');

    // 3. Workspace dropdown escape key and outside click
    const switcherBtn = screen.getByRole('button', { name: /Workspace switcher:/i });
    act(() => {
      switcherBtn.click();
    });
    expect(screen.getByRole('menu')).toBeDefined();

    // Escape key
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();

    // Outside click
    act(() => {
      switcherBtn.click();
    });
    expect(screen.getByRole('menu')).toBeDefined();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('menu')).toBeNull();

    unmount();
    fetchSpy.mockRestore();
  });

  it('extractProjectKeyFromPath extracts project keys from project and workspace routes', () => {
    expect(extractProjectKeyFromPath('/projects/KAN/issues')).toBe('KAN');
    expect(extractProjectKeyFromPath('/projects/SEC')).toBe('SEC');
    expect(extractProjectKeyFromPath('/projects/PRJ-123/settings/workflows?foo=bar')).toBe('PRJ-123');
    expect(extractProjectKeyFromPath('/w/engineering/p/SEC/cycles')).toBe('SEC');
    expect(extractProjectKeyFromPath('/w/my-ws/p/OPS')).toBe('OPS');
    expect(extractProjectKeyFromPath('/w/default/projects/CORE/settings#hash')).toBe('CORE');
    expect(extractProjectKeyFromPath('/')).toBeNull();
    expect(extractProjectKeyFromPath('/drafts')).toBeNull();
    expect(extractProjectKeyFromPath('/your-work')).toBeNull();
    expect(extractProjectKeyFromPath('/stickies')).toBeNull();
    expect(extractProjectKeyFromPath('/docs')).toBeNull();
    expect(extractProjectKeyFromPath('/about')).toBeNull();
    expect(extractProjectKeyFromPath('')).toBeNull();
    expect(extractProjectKeyFromPath(null)).toBeNull();
    expect(extractProjectKeyFromPath(undefined)).toBeNull();
  });

  it('auto-collapses non-focused projects on route navigation or sub-route clicks while preserving manual toggles (KAN-53)', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input: RequestInfo | URL) => {
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
      return Promise.resolve(new Response('[]', { status: 200 }));
    });

    // 1. Initial render on /projects/KAN/issues: KAN should be expanded, SEC collapsed
    const { unmount } = render(
      <MemoryRouter initialEntries={['/projects/KAN/issues']}>
        <Sidebar projectKey="KAN" projectName="kanban" modulesEnabled={true} />
      </MemoryRouter>,
    );

    const kanRow = await screen.findByRole('button', { name: 'Project: kanban' });
    const secRow = await screen.findByRole('button', { name: 'Project: Security' });

    expect(kanRow.getAttribute('aria-expanded')).toBe('true');
    expect(secRow.getAttribute('aria-expanded')).toBe('false');

    // KAN subitems present, SEC subitems absent
    expect(screen.getByRole('link', { name: /Issues view/i })).toBeDefined();

    // 2. Manual expand SEC via arrow button: preserves manual toggle independently
    act(() => {
      secRow.click();
    });
    expect(secRow.getAttribute('aria-expanded')).toBe('true');
    expect(kanRow.getAttribute('aria-expanded')).toBe('true');

    // 3. Manual collapse KAN via arrow button: KAN collapsed, SEC still expanded
    act(() => {
      kanRow.click();
    });
    expect(kanRow.getAttribute('aria-expanded')).toBe('false');
    expect(secRow.getAttribute('aria-expanded')).toBe('true');

    // Re-expand KAN manually
    act(() => {
      kanRow.click();
    });
    expect(kanRow.getAttribute('aria-expanded')).toBe('true');
    expect(secRow.getAttribute('aria-expanded')).toBe('true');

    // 4. Click sub-route under SEC (e.g., Work Items or Cycles or subitems container):
    // Auto-collapses non-focused project (KAN) to false and keeps SEC true!
    const secSubitems = document.querySelectorAll('.kb-project-subitems');
    expect(secSubitems.length).toBe(2);
    const secLinks = screen.getAllByRole('link', { name: /Cycles/i });
    expect(secLinks.length).toBe(2);
    act(() => {
      secLinks[1]?.click();
    });
    expect(secRow.getAttribute('aria-expanded')).toBe('true');
    expect(kanRow.getAttribute('aria-expanded')).toBe('false');

    unmount();
  });

  it('preserves manual expand/collapse state when on non-project route / and updates on navigation (KAN-53)', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input: RequestInfo | URL) => {
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
      return Promise.resolve(new Response('[]', { status: 200 }));
    });

    // Render on / (non-project route): both projects default to expanded
    const { rerender } = render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar activePath="/" />
      </MemoryRouter>,
    );

    const kanRow = await screen.findByRole('button', { name: 'Project: kanban' });
    const secRow = await screen.findByRole('button', { name: 'Project: Security' });

    expect(kanRow.getAttribute('aria-expanded')).toBe('true');
    expect(secRow.getAttribute('aria-expanded')).toBe('true');

    // Manually collapse KAN on /
    act(() => {
      kanRow.click();
    });
    expect(kanRow.getAttribute('aria-expanded')).toBe('false');
    expect(secRow.getAttribute('aria-expanded')).toBe('true');

    // Navigate to /stickies (another non-project route): manual state preserved!
    rerender(
      <MemoryRouter initialEntries={['/stickies']}>
        <Sidebar activePath="/stickies" />
      </MemoryRouter>,
    );
    expect(kanRow.getAttribute('aria-expanded')).toBe('false');
    expect(secRow.getAttribute('aria-expanded')).toBe('true');

    // Navigate to /w/default/p/SEC/issues: focuses SEC, auto-collapses non-focused KAN
    rerender(
      <MemoryRouter initialEntries={['/w/default/p/SEC/issues']}>
        <Sidebar activePath="/w/default/p/SEC/issues" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(secRow.getAttribute('aria-expanded')).toBe('true');
      expect(kanRow.getAttribute('aria-expanded')).toBe('false');
    });

    // Navigate to /projects/KAN/issues: focuses KAN, auto-collapses SEC
    rerender(
      <MemoryRouter initialEntries={['/projects/KAN/issues']}>
        <Sidebar activePath="/projects/KAN/issues" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(kanRow.getAttribute('aria-expanded')).toBe('true');
      expect(secRow.getAttribute('aria-expanded')).toBe('false');
    });
  });

  it('handles workspace created callback from CreateWorkspaceModal and switches workspace', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/workspaces') && init?.method === 'POST') {
        return Promise.resolve(
          new Response(
            JSON.stringify({ id: 'created-ws', name: 'Created WS', slug: 'created-ws' }),
            { status: 201, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/switch')) {
        return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'ws-csrf' }), { status: 200 }));
      }
      return Promise.resolve(new Response('[]', { status: 200 }));
    });

    render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar projectKey="KAN" projectName="kanban" />
      </MemoryRouter>,
    );

    // Open workspace dropdown
    const switcherBtn = screen.getByRole('button', { name: /Workspace switcher:/i });
    act(() => {
      switcherBtn.click();
    });

    // Click "+ Create New Workspace"
    const createWsBtn = screen.getByRole('menuitem', { name: /Create New Workspace/i });
    act(() => {
      createWsBtn.click();
    });

    const modal = screen.getByRole('dialog', { name: 'Create New Workspace' });
    expect(modal).toBeDefined();

    const nameInput = screen.getByLabelText(/Workspace Name/i);
    act(() => {
      fireEvent.change(nameInput, { target: { value: 'New Test WS' } });
    });

    const submitBtn = screen.getByRole('button', { name: 'Create Workspace' });
    act(() => {
      fireEvent.click(submitBtn);
    });

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Create New Workspace' })).toBeNull();
    });
  });

  it('covers remaining branch variations for coverage threshold (KAN-53)', async () => {
    // 1. isOpen = false
    const { unmount: uClosed } = render(
      <MemoryRouter>
        <Sidebar isOpen={false} />
      </MemoryRouter>,
    );
    expect(document.querySelector('.kb-sidebar-scrim-active')).toBeNull();
    uClosed();

    // 2. /docs routes for docs link
    const { unmount: uHelp } = render(
      <MemoryRouter initialEntries={['/docs/getting-started']}>
        <Sidebar activePath="/docs/getting-started" />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('sidebar-docs-link').getAttribute('aria-current')).toBe('page');
    uHelp();

    // 3. Layout board active subnav
    const { unmount: uBoard } = render(
      <MemoryRouter initialEntries={['/projects/KAN/issues?layout=board']}>
        <Sidebar projectKey="KAN" activePath="/projects/KAN/issues" />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Board view' }).className).toContain('kb-subnav-active');
    uBoard();

    // 4. User permissions branches: is_server_admin true, is_workspace_admin false
    const { unmount: uAdmin1 } = render(
      <MemoryRouter>
        <Sidebar user={{ is_server_admin: true, is_workspace_admin: false }} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: 'Create project' })).toBeDefined();
    uAdmin1();

    // 5. User permissions: viewer role (canCreateProject false, canCreateWorkItem false)
    const { unmount: uViewer } = render(
      <MemoryRouter>
        <Sidebar user={{ is_server_admin: false, is_workspace_admin: false, workspace_role: 'VIEWER' }} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole('button', { name: 'Create project' })).toBeNull();
    expect(screen.queryByRole('button', { name: /New work item/ })).toBeNull();
    uViewer();

    // 6. fetchProjects array payload & invalid item handling
    const fetchSpy = vi.spyOn(window, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const u = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (u.includes('/api/v1/projects')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              { key: 'DIR1', name: 'Direct Array Project' },
              { key: '', name: 'Invalid' },
              { key: 'INV2', name: 123 },
            ]),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response('[]', { status: 200 }));
    });

    const { unmount: uArray } = render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText('Direct Array Project')).toBeDefined();
    });
    uArray();
    fetchSpy.mockRestore();

    // 7. handleCreateIssue on existing issues route (skips navigateFn branch)
    const { unmount: uOnIssues } = render(
      <MemoryRouter initialEntries={['/projects/KAN/issues']}>
        <Sidebar projectKey="KAN" activePath="/projects/KAN/issues" />
      </MemoryRouter>,
    );
    const newIssueBtn = screen.getByRole('button', { name: /New work item/ });
    act(() => {
      newIssueBtn.click();
    });
    uOnIssues();

    // 8. projectList merge with undefined projectName and non-array workspaces
    const fetchSpy2 = vi.spyOn(window, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const u = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (u.includes('/api/v1/workspaces')) {
        return Promise.resolve(new Response(JSON.stringify({ notAnArray: true }), { status: 200 }));
      }
      if (u.includes('/api/v1/projects')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              items: [
                { identifier: 'KAN', name: 'Existing Kanban', modules_enabled: true },
                { identifier: 'NO_MODS', name: 'No Mod Project' },
              ],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    const { unmount: uMerge } = render(
      <MemoryRouter>
        <Sidebar projectKey="KAN" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText('Existing Kanban')).toBeDefined();
    });
    uMerge();
    fetchSpy2.mockRestore();

    // 9. Mobile key down non-escape, non-tab key
    const triggerRef = { current: document.createElement('button') };
    const { unmount: uKey } = render(
      <MemoryRouter>
        <Sidebar isOpen={true} triggerButtonRef={triggerRef} />
      </MemoryRouter>,
    );
    const dialog = screen.getByRole('dialog', { name: 'Sidebar navigation' });
    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    uKey();

    // 10. User with workspace_admin=true, server_admin=false; user with undefined admin flags
    const { unmount: uWsAdmin } = render(
      <MemoryRouter>
        <Sidebar user={{ is_workspace_admin: true, is_server_admin: false }} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: 'Create project' })).toBeDefined();
    uWsAdmin();

    const { unmount: uUndefAdmin } = render(
      <MemoryRouter>
        <Sidebar user={{ workspace_role: 'MEMBER' }} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole('button', { name: 'Create project' })).toBeNull();
    uUndefAdmin();

    // 11. fetchProjects with empty object (data.items ?? [] fallback)
    const fetchSpyEmpty = vi.spyOn(window, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const u = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (u.includes('/api/v1/projects')) {
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      }
      return Promise.resolve(new Response('[]', { status: 200 }));
    });
    const { unmount: uEmptyItems } = render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('sidebar-no-projects')).toBeDefined();
    });
    uEmptyItems();
    fetchSpyEmpty.mockRestore();
  });

  it('KAN-58: Mobile Sidebar Dismiss & Navigation Auto-Close', () => {
    const onCloseSpy = vi.fn();
    const onToggleSpy = vi.fn();

    render(
      <MemoryRouter initialEntries={['/projects/KAN']}>
        <Sidebar
          isOpen={true}
          onClose={onCloseSpy}
          onToggleCollapse={onToggleSpy}
          projectKey="KAN"
          projectName="kanban"
        />
      </MemoryRouter>,
    );

    // 1. Close button in mobile overlay calls onClose, NOT desktop handleToggleCollapse
    const closeBtn = screen.getByRole('button', { name: 'Collapse navigation sidebar' });
    act(() => {
      closeBtn.click();
    });
    expect(onCloseSpy).toHaveBeenCalledTimes(1);
    expect(onToggleSpy).not.toHaveBeenCalled();

    // 2. Clicking any nav link in mobile overlay automatically closes the sidebar
    const homeLink = screen.getByRole('link', { name: /Home/i });
    act(() => {
      homeLink.click();
    });
    expect(onCloseSpy).toHaveBeenCalledTimes(2);
  });
});
