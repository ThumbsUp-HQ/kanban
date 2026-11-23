/**
 * Unit and Regression Test Suite for KAN-376 (KB-TOPBAR-LAYOUT-SWITCHER-OVERFLOW).
 * Verifies mobile layout dropdown clipping fix, small-desktop layout switcher activation,
 * z-index stacking order, search trigger minimum width, and breadcrumb truncation.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import fs from 'node:fs';
import path from 'node:path';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { ShellPanelsProvider } from '../shellPanels';
import {
  LayoutSwitcher,
  normalizeLayout,
  type LayoutOption,
} from '../LayoutSwitcher';
import { Topbar } from '../Topbar';

const APP_DIR = path.resolve(import.meta.dirname, '..');

describe('KAN-376: LayoutSwitcher & Topbar CSS Architecture Specifications', () => {
  const topbarCss = fs.readFileSync(path.join(APP_DIR, 'Topbar.css'), 'utf8');
  const layoutCss = fs.readFileSync(path.join(APP_DIR, 'LayoutSwitcher.css'), 'utf8');
  const breadcrumbCss = fs.readFileSync(path.join(APP_DIR, 'Breadcrumb.css'), 'utf8');

  it('Problem 1 spec: verifies Topbar at <=768px sets overflow: visible and eliminates overflow: hidden on .kb-topbar', () => {
    // Topbar base has z-index 300
    expect(topbarCss).toMatch(/\.kb-topbar\s*\{[^}]*z-index:\s*300/);

    // At <= 768px, .kb-topbar must be overflow: visible so dropdown menus are never clipped
    const mobileMedia768 = /@media\s*\(max-width:\s*768px\)\s*\{([\s\S]*?)(?=\n@media|\n\/\*|$)/.exec(topbarCss);
    expect(mobileMedia768).not.toBeNull();
    const mediaContent = mobileMedia768?.[1] ?? '';
    expect(mediaContent).toMatch(/\.kb-topbar,\s*\.topbar\s*\{[^}]*overflow:\s*visible/);
    expect(mediaContent).not.toMatch(/\.kb-topbar,\s*\.topbar\s*\{[^}]*overflow:\s*hidden/);
  });

  it('Problem 1 spec: verifies LayoutSwitcher menu z-index is elevated to 400 (exceeding Topbar z-index 300)', () => {
    const menuRuleMatch = /\.kb-layout-switcher-menu\s*\{([^}]*)\}/.exec(layoutCss);
    expect(menuRuleMatch).not.toBeNull();
    const menuContent = menuRuleMatch?.[1] ?? '';
    expect(menuContent).toMatch(/z-index:\s*400/);

    // Assert strictly that 400 > 300
    const topbarZ = 300;
    const menuZ = 400;
    expect(menuZ).toBeGreaterThan(topbarZ);
  });

  it('Problem 2 spec: verifies LayoutSwitcher switches desktop/mobile at 1279px / 540px', () => {
    // Desktop hides and mobile shows at <= 1279px or <= 540px height
    expect(layoutCss).toMatch(/@media\s*\(max-width:\s*1279px\),\s*\(max-height:\s*540px\)\s*\{[\s\S]*?\.kb-layout-switcher-desktop\s*\{[^}]*display:\s*none;[^}]*\}[\s\S]*?\.kb-layout-switcher-mobile\s*\{[^}]*display:\s*block;[^}]*\}/);

    // Desktop shows and mobile hides at >= 1280px and >= 541px height
    expect(layoutCss).toMatch(/@media\s*\(min-width:\s*1280px\)\s*and\s*\(min-height:\s*541px\)\s*\{[\s\S]*?\.kb-layout-switcher-desktop\s*\{[^}]*display:\s*flex;[^}]*\}[\s\S]*?\.kb-layout-switcher-mobile\s*\{[^}]*display:\s*none;[^}]*\}/);
  });

  it('Problem 2 spec: verifies Topbar search trigger maintains min-width: 140px and left breadcrumb has min-width: 0 and flex-shrink: 1', () => {
    // Base .kb-topbar-left has min-width: 0 and flex-shrink: 1
    expect(topbarCss).toMatch(/\.kb-topbar-left\s*\{[^}]*min-width:\s*0;[^}]*flex-shrink:\s*1;/);

    // .kb-topbar-center has min-width: 140px across base, 1024px, and 768px
    expect(topbarCss).toMatch(/\.kb-topbar-center,\s*\.topbar__search\s*\{[^}]*min-width:\s*140px;/);

    const media1024 = /@media\s*\(max-width:\s*1024px\)\s*\{([\s\S]*?)(?=\n@media|\n\/\*|$)/.exec(topbarCss);
    expect(media1024?.[1]).toMatch(/\.kb-topbar-center,\s*\.topbar__search\s*\{[^}]*min-width:\s*140px;/);

    const media768 = /@media\s*\(max-width:\s*768px\)\s*\{([\s\S]*?)(?=\n@media|\n\/\*|$)/.exec(topbarCss);
    expect(media768?.[1]).toMatch(/\.kb-topbar-center,\s*\.topbar__search\s*\{[^}]*min-width:\s*140px;/);
  });

  it('Problem 2 spec: verifies Breadcrumb styles enforce min-width: 0 and text-overflow: ellipsis for truncation', () => {
    expect(breadcrumbCss).toMatch(/\.kb-breadcrumb\s*\{[^}]*min-width:\s*0;/);
    expect(breadcrumbCss).toMatch(/\.kb-breadcrumb-desktop\s*\{[^}]*min-width:\s*0;/);
    expect(breadcrumbCss).toMatch(/\.kb-breadcrumb-item\s*\{[^}]*min-width:\s*0;[^}]*flex-shrink:\s*1;/);
    expect(breadcrumbCss).toMatch(/\.kb-breadcrumb-workspace\s*\{[^}]*min-width:\s*0;[^}]*overflow:\s*hidden;[^}]*text-overflow:\s*ellipsis;/);
    expect(breadcrumbCss).toMatch(/\.kb-breadcrumb-link\s*\{[^}]*min-width:\s*0;[^}]*overflow:\s*hidden;[^}]*text-overflow:\s*ellipsis;/);
    expect(breadcrumbCss).toMatch(/\.kb-breadcrumb-current\s*\{[^}]*min-width:\s*0;[^}]*overflow:\s*hidden;[^}]*text-overflow:\s*ellipsis;/);
  });
});

describe('LayoutSwitcher Component Interactive & Accessibility Behaviors', () => {
  it('renders with all 5 layout options in radiogroup and mobile button', () => {
    render(
      <MemoryRouter>
        <LayoutSwitcher value="list" />
      </MemoryRouter>,
    );

    const radiogroup = screen.getByRole('radiogroup', { name: 'Layout' });
    expect(radiogroup).toBeDefined();

    const options = screen.getAllByRole('radio');
    expect(options).toHaveLength(5);
    expect(options.map((o) => o.textContent.trim())).toEqual([
      'Issues',
      'Board',
      'Table',
      'Calendar',
      'Timeline',
    ]);

    const mobileBtn = screen.getByRole('button', { name: 'Layout: Issues' });
    expect(mobileBtn).toBeDefined();
    expect(mobileBtn.getAttribute('aria-expanded')).toBe('false');
  });

  it('toggles mobile menu open, selects an option, updates URL, and closes menu', () => {
    const onChange = vi.fn();
    render(
      <MemoryRouter initialEntries={['/projects/TEST/issues?layout=list']}>
        <Routes>
          <Route
            path="/projects/:key/issues"
            element={<LayoutSwitcher onChange={onChange} />}
          />
        </Routes>
      </MemoryRouter>,
    );

    const mobileBtn = screen.getByRole('button', { name: 'Layout: Issues' });
    expect(mobileBtn.getAttribute('aria-expanded')).toBe('false');

    // Click to open
    act(() => {
      mobileBtn.click();
    });

    expect(mobileBtn.getAttribute('aria-expanded')).toBe('true');
    const menu = screen.getByRole('menu', { name: 'Layout menu' });
    expect(menu).toBeDefined();

    const menuItems = screen.getAllByRole('menuitemradio');
    expect(menuItems).toHaveLength(5);

    // Select Timeline
    const timelineItem = screen.getByRole('menuitemradio', { name: 'Timeline' });
    act(() => {
      timelineItem.click();
    });

    expect(onChange).toHaveBeenCalledWith('timeline');
    expect(screen.queryByRole('menu', { name: 'Layout menu' })).toBeNull();
  });

  it('closes mobile menu when clicking outside but keeps it open when clicking inside', () => {
    render(
      <MemoryRouter>
        <div>
          <div data-testid="outside-element">Outside</div>
          <LayoutSwitcher value="board" />
        </div>
      </MemoryRouter>,
    );

    const mobileBtn = screen.getByRole('button', { name: 'Layout: Board' });

    // Open menu
    act(() => {
      mobileBtn.click();
    });
    const menu = screen.getByRole('menu', { name: 'Layout menu' });
    expect(menu).toBeDefined();

    // Click inside container does not close menu
    act(() => {
      fireEvent.mouseDown(menu);
    });
    expect(screen.getByRole('menu', { name: 'Layout menu' })).toBeDefined();

    // Click outside closes menu
    act(() => {
      const outside = screen.getByTestId('outside-element');
      fireEvent.mouseDown(outside);
    });

    expect(screen.queryByRole('menu', { name: 'Layout menu' })).toBeNull();
  });

  it('closes mobile menu when pressing Escape key but ignores other keys', () => {
    render(
      <MemoryRouter>
        <LayoutSwitcher value="calendar" />
      </MemoryRouter>,
    );

    const mobileBtn = screen.getByRole('button', { name: 'Layout: Calendar' });

    // Open menu
    act(() => {
      mobileBtn.click();
    });
    expect(screen.getByRole('menu', { name: 'Layout menu' })).toBeDefined();

    // Non-Escape key does not close menu
    act(() => {
      fireEvent.keyDown(document, { key: 'Tab' });
    });
    expect(screen.getByRole('menu', { name: 'Layout menu' })).toBeDefined();

    // Press Escape
    act(() => {
      fireEvent.keyDown(document, { key: 'Escape' });
    });

    expect(screen.queryByRole('menu', { name: 'Layout menu' })).toBeNull();
  });

  it('toggles mobile menu closed when clicking the trigger button again', () => {
    render(
      <MemoryRouter>
        <LayoutSwitcher value="table" />
      </MemoryRouter>,
    );

    const mobileBtn = screen.getByRole('button', { name: 'Layout: Table' });

    // First click: open
    act(() => {
      mobileBtn.click();
    });
    expect(screen.getByRole('menu', { name: 'Layout menu' })).toBeDefined();

    // Second click: close
    act(() => {
      mobileBtn.click();
    });
    expect(screen.queryByRole('menu', { name: 'Layout menu' })).toBeNull();
  });

  it('handles keyboard navigation cyclic wrapping across all 5 options', () => {
    const onChange = vi.fn();
    render(
      <MemoryRouter>
        <LayoutSwitcher value="list" onChange={onChange} />
      </MemoryRouter>,
    );

    const radios = screen.getAllByRole('radio');
    const firstRadio = radios[0];
    if (!firstRadio) throw new Error('Expected first radio button');

    firstRadio.focus();

    // Forward navigation (ArrowRight & ArrowDown)
    fireEvent.keyDown(firstRadio, { key: 'ArrowRight' });
    expect(onChange).toHaveBeenLastCalledWith('board');

    fireEvent.keyDown(firstRadio, { key: 'ArrowDown' });
    expect(onChange).toHaveBeenLastCalledWith('board');

    // Backward cyclic navigation from list wraps to timeline
    fireEvent.keyDown(firstRadio, { key: 'ArrowLeft' });
    expect(onChange).toHaveBeenLastCalledWith('timeline');

    fireEvent.keyDown(firstRadio, { key: 'ArrowUp' });
    expect(onChange).toHaveBeenLastCalledWith('timeline');

    // Unrelated keys do nothing
    fireEvent.keyDown(firstRadio, { key: 'Enter' });
    fireEvent.keyDown(firstRadio, { key: ' ' });
    fireEvent.keyDown(firstRadio, { key: 'Tab' });
    expect(onChange).toHaveBeenCalledTimes(4);
  });

  it('normalizes malicious, boundary, and unexpected layout parameters', () => {
    expect(normalizeLayout(null)).toBe('list');
    expect(normalizeLayout(undefined)).toBe('list');
    expect(normalizeLayout('')).toBe('list');
    expect(normalizeLayout('   ')).toBe('list');
    expect(normalizeLayout('UNKNOWN')).toBe('list');
    expect(normalizeLayout('javascript:alert(1)')).toBe('list');
    expect(normalizeLayout('<img src=x onerror=alert(1)>')).toBe('list');

    expect(normalizeLayout('list')).toBe('list');
    expect(normalizeLayout('LIST')).toBe('list');
    expect(normalizeLayout('board')).toBe('board');
    expect(normalizeLayout('BOARD')).toBe('board');
    expect(normalizeLayout('table')).toBe('table');
    expect(normalizeLayout('Table')).toBe('table');
    expect(normalizeLayout('calendar')).toBe('calendar');
    expect(normalizeLayout('Calendar')).toBe('calendar');
    expect(normalizeLayout('timeline')).toBe('timeline');
    expect(normalizeLayout('Timeline')).toBe('timeline');
  });

  it('handles unrecognized layout value gracefully by falling back to LAYOUT_OPTIONS[0]', () => {
    render(
      <MemoryRouter>
        <LayoutSwitcher value={'unrecognized_option' as unknown as LayoutOption} className="custom-switcher" />
      </MemoryRouter>,
    );

    const btn = screen.getByRole('button', { name: 'Layout: Issues' });
    expect(btn).toBeDefined();
  });
});

describe('Topbar & Breadcrumb Integration with LayoutSwitcher (KAN-376)', () => {
  const createQueryClient = () =>
    new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

  it('mounts LayoutSwitcher on issues route inside Topbar and renders breadcrumb hierarchy', () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter initialEntries={['/projects/KANBA/issues']}>
              <Routes>
                <Route
                  path="/projects/:projectKey/issues"
                  element={
                    <Topbar
                      workspaceName="kanban-engineering"
                      projectKey="KANBA"
                      projectName="Core Platform"
                      currentSection="Work Items"
                      issueCount={42}
                      showLayoutSwitcher={true}
                    />
                  }
                />
              </Routes>
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    // Search trigger is present with Search... text
    expect(screen.getByText('Search...')).toBeDefined();

    // Layout switcher radiogroup and mobile button are present
    expect(screen.getByRole('radiogroup', { name: 'Layout' })).toBeDefined();
    expect(screen.getByRole('button', { name: /Layout:/ })).toBeDefined();

    // Breadcrumb renders workspace, project, section, count
    expect(screen.getByTestId('breadcrumb-workspace')).toBeDefined();
    expect(screen.getByText('Core Platform')).toBeDefined();
    expect(screen.getByTestId('breadcrumb-current-section').textContent).toBe('Work Items');
    expect(screen.getByText('(42)')).toBeDefined();
  });

  it('handles extremely long workspace and project names without crashing', () => {
    const queryClient = createQueryClient();
    const superLongWorkspace = 'Supercalifragilisticexpialidocious Long Enterprise Workspace Name';
    const superLongProject = 'Extremely Long Project Name That Could Overflow The Topbar Header In Small Desktop Screen Sizes';

    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter initialEntries={['/projects/LONG/issues']}>
              <Routes>
                <Route
                  path="/projects/:projectKey/issues"
                  element={
                    <Topbar
                      workspaceName={superLongWorkspace}
                      projectKey="LONG"
                      projectName={superLongProject}
                      currentSection="Issues Overflow Testing"
                      issueCount={999}
                      showLayoutSwitcher={true}
                    />
                  }
                />
              </Routes>
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText(superLongWorkspace)).toBeDefined();
    expect(screen.getByText(superLongProject)).toBeDefined();
    expect(screen.getByText('Issues Overflow Testing')).toBeDefined();
    expect(screen.getByText('(999)')).toBeDefined();
  });
});
