// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React, { createRef } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { ShellPanelsProvider } from '../../app/shellPanels';
import { Topbar } from '../../app/Topbar';
import { Sidebar } from '../../app/Sidebar';
import { AppShell } from '../../app/AppShell';
import { CommandPalette } from '../../app/CommandPalette';
import { DocsCenterPage } from '../docs-center/DocsCenterPage';

vi.mock('../docs/DocsTreeNav', () => ({
  DocsTreeNav: () => <div data-testid="mock-tree-nav">Tree Nav</div>,
}));

vi.mock('../docs/PageEditorPane', () => ({
  PageEditorPane: () => <div data-testid="mock-page-editor">Editor</div>,
}));

vi.mock('../docs/OutlineAndVersionsRail', () => ({
  OutlineAndVersionsRail: () => <div data-testid="mock-rail">Rail</div>,
}));

vi.mock('../docs/SelectionToIssueToolbar', () => ({
  SelectionToIssueToolbar: () => <div data-testid="mock-toolbar" />,
}));

import { DocsWorkspaceView } from '../docs/DocsWorkspaceView';

describe('WCAG 2.2 AA Full Review and Remediation Suite (KAN-315)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
      },
    });
    vi.restoreAllMocks();

    Element.prototype.scrollIntoView = vi.fn();

    // Default matchMedia mock
    window.matchMedia = vi.fn().mockImplementation((query: string) => {
      return {
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      };
    });
  });

  afterEach(() => {
    queryClient.clear();
  });

  describe('Problem 1: ARIA Semantics and Keyboard Traversal in Topbar, CommandPalette, and Sidebar', () => {
    it('Topbar theme options render inside role="group" with role="menuitemradio" and aria-checked', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <ShellPanelsProvider>
            <ThemeProvider>
              <MemoryRouter>
                <Topbar
                  workspaceName="Primary Workspace"
                  projectKey="KAN"
                  projectName="Platform Core"
                  user={{
                    id: 'u-1',
                    display_name: 'Adam Architect',
                    email: 'adam@example.com',
                    handle: 'adam',
                    is_server_admin: true,
                    is_workspace_admin: true,
                  }}
                />
              </MemoryRouter>
            </ThemeProvider>
          </ShellPanelsProvider>
        </QueryClientProvider>
      );

      const avatarBtn = screen.getByTestId('topbar-avatar-button');
      fireEvent.click(avatarBtn);

      const menu = await screen.findByRole('menu');
      expect(menu).toBeDefined();

      const themeGroup = screen.getByRole('group', { name: 'Theme preference' });
      expect(themeGroup).toBeDefined();

      const themeRadios = screen.getAllByRole('menuitemradio');
      expect(themeRadios.length).toBe(3);

      const checkedItems = themeRadios.filter(
        (radio) => radio.getAttribute('aria-checked') === 'true'
      );
      expect(checkedItems.length).toBe(1);

      const lightRadio = screen.getByRole('menuitemradio', { name: /light/i });
      const darkRadio = screen.getByRole('menuitemradio', { name: /dark/i });
      const systemRadio = screen.getByRole('menuitemradio', { name: /system/i });

      expect(lightRadio).toBeDefined();
      expect(darkRadio).toBeDefined();
      expect(systemRadio).toBeDefined();

      // Keyboard navigation with Home and End
      fireEvent.keyDown(menu, { key: 'End' });
      const menuItems = menu.querySelectorAll<HTMLElement>('[role^="menuitem"]');
      expect(document.activeElement).toBe(menuItems[menuItems.length - 1]);

      fireEvent.keyDown(menu, { key: 'Home' });
      expect(document.activeElement).toBe(menuItems[0]);

      // ArrowDown / ArrowUp traversal
      fireEvent.keyDown(menu, { key: 'ArrowDown' });
      expect(document.activeElement).toBe(menuItems[1]);

      fireEvent.keyDown(menu, { key: 'ArrowUp' });
      expect(document.activeElement).toBe(menuItems[0]);
    });

    it('Topbar attaches hamburgerButtonRef to hamburger button', () => {
      const hamburgerRef = createRef<HTMLButtonElement>();

      render(
        <QueryClientProvider client={queryClient}>
          <ShellPanelsProvider>
            <ThemeProvider>
              <MemoryRouter>
                <Topbar
                  hamburgerButtonRef={hamburgerRef}
                  workspaceName="Primary Workspace"
                />
              </MemoryRouter>
            </ThemeProvider>
          </ShellPanelsProvider>
        </QueryClientProvider>
      );

      expect(hamburgerRef.current).not.toBeNull();
      expect(hamburgerRef.current?.getAttribute('aria-label')).toBe('Open navigation');
    });

    it('CommandPalette combobox exposes aria-activedescendant that updates with selection', () => {
      const onClose = vi.fn();
      render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <MemoryRouter>
              <CommandPalette
                isOpen={true}
                onClose={onClose}
                projectKey="KAN"
                cachedIssues={[
                  { key: 'KAN-101', summary: 'Harden OAuth endpoints' },
                  { key: 'KAN-102', summary: 'Audit database indexes' },
                ]}
              />
            </MemoryRouter>
          </ThemeProvider>
        </QueryClientProvider>
      );

      const combobox = screen.getByRole('combobox');
      expect(combobox).toBeDefined();
      expect(combobox.getAttribute('aria-expanded')).toBe('true');
      expect(combobox.getAttribute('aria-autocomplete')).toBe('list');

      const initialActiveId = combobox.getAttribute('aria-activedescendant') ?? '';
      expect(initialActiveId).toBeTruthy();
      expect(document.getElementById(initialActiveId)).not.toBeNull();

      // ArrowDown updates active descendant
      fireEvent.keyDown(combobox, { key: 'ArrowDown' });
      const nextActiveId = combobox.getAttribute('aria-activedescendant') ?? '';
      expect(nextActiveId).toBeTruthy();
      expect(nextActiveId).not.toBe(initialActiveId);
      expect(document.getElementById(nextActiveId)).not.toBeNull();

      // ArrowUp returns back
      fireEvent.keyDown(combobox, { key: 'ArrowUp' });
      expect(combobox.getAttribute('aria-activedescendant')).toBe(initialActiveId);
    });

    it('Sidebar workspace switcher dropdown handles keyboard navigation and hides checkmark from screen readers', async () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <MemoryRouter>
              <Sidebar
                isOpen={true}
                projectKey="KAN"
                projectName="Platform Core"
              />
            </MemoryRouter>
          </ThemeProvider>
        </QueryClientProvider>
      );

      const switcher = container.querySelector<HTMLButtonElement>('.kb-workspace-switcher');
      expect(switcher).not.toBeNull();
      if (switcher) {
        fireEvent.click(switcher);
      }

      const dropdown = screen.getByRole('menu');
      expect(dropdown).toBeDefined();

      const menuItems = dropdown.querySelectorAll<HTMLElement>('[role="menuitem"]');
      expect(menuItems.length).toBeGreaterThan(0);

      // Checkmark in active item must have aria-hidden="true"
      const checkmark = dropdown.querySelector('.kb-workspace-dropdown-check');
      if (checkmark) {
        expect(checkmark.getAttribute('aria-hidden')).toBe('true');
      }

      // Keyboard navigation with ArrowDown, Home, End
      fireEvent.keyDown(dropdown, { key: 'ArrowDown' });
      fireEvent.keyDown(dropdown, { key: 'End' });
      expect(document.activeElement).toBe(menuItems[menuItems.length - 1]);

      fireEvent.keyDown(dropdown, { key: 'Home' });
      expect(document.activeElement).toBe(menuItems[0]);

      // Escape closes dropdown
      fireEvent.keyDown(dropdown, { key: 'Escape' });
      await waitFor(() => {
        expect(screen.queryByRole('menu')).toBeNull();
      });
    });
  });

  describe('Problem 2: Mobile Viewport Dialog Roles, Focus Trapping, and Inert Backgrounds', () => {
    it('Sidebar dynamically toggles role="dialog" and aria-modal="true" on mobile viewports', () => {
      window.matchMedia = vi.fn().mockImplementation((query: string) => {
        return {
          matches: query.includes('1279px'),
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        };
      });

      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <MemoryRouter>
              <Sidebar
                isOpen={true}
                projectKey="KAN"
                projectName="Platform Core"
              />
            </MemoryRouter>
          </ThemeProvider>
        </QueryClientProvider>
      );

      const aside = container.querySelector('aside');
      expect(aside?.getAttribute('role')).toBe('dialog');
      expect(aside?.getAttribute('aria-modal')).toBe('true');
    });

    it('AppShell marks main canvas with inert and aria-hidden when mobile sidebar is open', () => {
      vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(800);
      window.matchMedia = vi.fn().mockImplementation((query: string) => {
        return {
          matches: query.includes('1279px'),
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        };
      });

      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <ShellPanelsProvider>
            <ThemeProvider>
              <MemoryRouter>
                <AppShell>
                  <div data-testid="inner-content">Page Content</div>
                </AppShell>
              </MemoryRouter>
            </ThemeProvider>
          </ShellPanelsProvider>
        </QueryClientProvider>
      );

      const main = container.querySelector('#main');
      expect(main).toBeDefined();

      // Open mobile sidebar via Topbar hamburger
      const hamburger = screen.getByRole('button', { name: 'Open navigation' });
      fireEvent.click(hamburger);

      expect(main?.hasAttribute('inert')).toBe(true);
      expect(main?.getAttribute('aria-hidden')).toBe('true');

      // Close mobile sidebar
      fireEvent.click(hamburger);
      expect(main?.hasAttribute('inert')).toBe(false);
      expect(main?.getAttribute('aria-hidden')).toBeNull();
    });

    it('DocsWorkspaceView mobile tree and rail sheets enforce role="dialog" and aria-modal="true"', async () => {
      vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(800);

      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/docs']}>
            <Routes>
              <Route path="/projects/:projectKey/docs" element={<DocsWorkspaceView />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Open mobile tree sheet
      const toggleTreeBtn = screen.getByTestId('toggle-tree-sheet-btn');
      fireEvent.click(toggleTreeBtn);

      const treePane = container.querySelector('.docs-tree-wrapper');
      expect(treePane).toBeDefined();
      expect(treePane?.getAttribute('role')).toBe('dialog');
      expect(treePane?.getAttribute('aria-modal')).toBe('true');

      // Escape key closes mobile tree sheet and restores focus
      fireEvent.keyDown(window, { key: 'Escape' });
      await waitFor(() => {
        expect(treePane?.getAttribute('role')).toBeNull();
      });
      expect(document.activeElement).toBe(toggleTreeBtn);
    });

    it('DocsCenterPage mobile chapters drawer enforces role="dialog" and aria-modal="true"', async () => {
      const { container } = render(
        <MemoryRouter initialEntries={['/docs/home']}>
          <DocsCenterPage />
        </MemoryRouter>
      );

      const openDrawerBtn = screen.getByTestId('docs-mobile-chapters-btn');
      fireEvent.click(openDrawerBtn);

      const drawer = container.querySelector('.kb-docs-mobile-drawer');
      expect(drawer).toBeDefined();
      expect(drawer?.getAttribute('role')).toBe('dialog');
      expect(drawer?.getAttribute('aria-modal')).toBe('true');

      const closeDrawerBtn = screen.getByTestId('docs-mobile-drawer-close');
      fireEvent.click(closeDrawerBtn);

      await waitFor(() => {
        expect(container.querySelector('.kb-docs-mobile-drawer')).toBeNull();
      });
      expect(document.activeElement).toBe(openDrawerBtn);
    });
  });

  describe('Problem 4: prefers-reduced-motion in Smooth Scrolling Operations', () => {
    it('DocsCenterPage respects prefers-reduced-motion: reduce during anchor scrolling', () => {
      const scrollToSpy = vi.fn();
      window.scrollTo = scrollToSpy;

      window.matchMedia = vi.fn().mockImplementation((query: string) => {
        return {
          matches: query.includes('prefers-reduced-motion: reduce'),
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        };
      });

      render(
        <MemoryRouter initialEntries={['/docs/home']}>
          <DocsCenterPage />
        </MemoryRouter>
      );

      expect(scrollToSpy).toHaveBeenCalledWith({
        top: 0,
        behavior: 'auto',
      });
    });

    it('DocsCenterPage uses smooth behavior when prefers-reduced-motion is false', () => {
      const scrollToSpy = vi.fn();
      window.scrollTo = scrollToSpy;

      window.matchMedia = vi.fn().mockImplementation((query: string) => {
        return {
          matches: false,
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        };
      });

      render(
        <MemoryRouter initialEntries={['/docs/home']}>
          <DocsCenterPage />
        </MemoryRouter>
      );

      expect(scrollToSpy).toHaveBeenCalledWith({
        top: 0,
        behavior: 'smooth',
      });
    });
  });
});
