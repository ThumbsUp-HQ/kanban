import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { computeCurrentSection } from '../AppShell';
import { Topbar } from '../Topbar';
import { Sidebar } from '../Sidebar';
import { CommandPalette } from '../CommandPalette';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { ShellPanelsProvider } from '../shellPanels';
import { PersonalSettingsPage } from '../../features/settings/PersonalSettingsPage';
import * as personalApi from '../../features/settings/personalSettingsApi';
import * as authApi from '../../features/auth/authApi';

vi.mock('../../features/settings/personalSettingsApi');
vi.mock('../../features/auth/authApi');

describe('About Navigation Entry Points (KB-ABOUT-SBOM, KAN-34)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.restoreAllMocks();
  });

  it('computeCurrentSection correctly maps /about and /settings/about to "About"', () => {
    expect(computeCurrentSection('/about')).toBe('About');
    expect(computeCurrentSection('/settings/about')).toBe('About');
    expect(computeCurrentSection('/projects/KAN/issues')).toBe('Work Items');
  });

  it('Topbar renders ℹ️ About 👍kanban menu item above final logout divider', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <ShellPanelsProvider>
            <MemoryRouter initialEntries={['/projects/KAN/issues']}>
              <Topbar
                onOpenPalette={vi.fn()}
                onToggleSidebar={vi.fn()}
                projectKey="KAN"
                projectName="kanban"
                currentSection="Work Items"
              />
            </MemoryRouter>
          </ShellPanelsProvider>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    // Open avatar menu
    const avatarBtn = screen.getByRole('button', { name: 'User profile and settings' });
    fireEvent.click(avatarBtn);

    // Verify About 👍kanban link exists
    const aboutLink = screen.getByTestId('topbar-about-link');
    expect(aboutLink).toBeDefined();
    expect(aboutLink.getAttribute('href')).toBe('/about');
    expect(aboutLink.textContent).toContain('About 👍kanban');
  });

  it('Sidebar renders muted ℹ️ version link in footer', () => {
    render(
      <MemoryRouter initialEntries={['/projects/KAN/issues']}>
        <Sidebar projectKey="KAN" projectName="kanban" modulesEnabled={true} />
      </MemoryRouter>,
    );

    const sidebarAboutLink = screen.getByTestId('sidebar-about-link');
    expect(sidebarAboutLink).toBeDefined();
    expect(sidebarAboutLink.getAttribute('href')).toBe('/about');
    expect(sidebarAboutLink.textContent).toMatch(/v0\.2\./);
  });

  it('CommandPalette includes "About 👍kanban (License, API Docs & SBOM)" navigation command', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/projects/KAN/issues']}>
            <CommandPalette
              isOpen={true}
              onClose={vi.fn()}
              projectKey="KAN"
            />
          </MemoryRouter>
        </ThemeProvider>
      </QueryClientProvider>,
    );

    const input = screen.getByTestId('command-palette-input');
    fireEvent.change(input, { target: { value: 'About' } });

    expect(
      screen.getByText(/About 👍kanban \(License, API Docs & SBOM\)/i),
    ).toBeDefined();
  });

  it('PersonalSettingsPage renders muted footer link to /about', async () => {
    vi.mocked(personalApi.fetchMyProfile).mockResolvedValueOnce({
      principal_id: 'usr-1',
      username: 'testuser',
      display_name: 'Test User',
      email: 'test@example.com',
      avatar_url: null,
      timezone: 'UTC',
      is_server_admin: false,
    });
    vi.mocked(personalApi.fetchMfaStatus).mockResolvedValueOnce({
      totp_enabled: false,
      passkeys_count: 0,
      recovery_codes_remaining: 0,
    });
    vi.mocked(personalApi.fetchPasskeys).mockResolvedValueOnce([]);
    vi.mocked(personalApi.fetchExternalIdentities).mockResolvedValueOnce([]);
    vi.mocked(authApi.fetchAuthCards).mockResolvedValueOnce({ cards: [] });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/settings/profile']}>
          <PersonalSettingsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const footerAboutLink = await screen.findByTestId('personal-settings-about-link');
    expect(footerAboutLink).toBeDefined();
    expect(footerAboutLink.getAttribute('href')).toBe('/about');
    expect(footerAboutLink.textContent).toContain('About 👍kanban');
  });
});
