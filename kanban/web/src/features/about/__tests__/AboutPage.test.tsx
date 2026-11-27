import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ShellPanelsProvider, registerShellPanel } from '../../../app/shellPanels';
import { AboutPage } from '../AboutPage';
import * as aboutApi from '../aboutApi';

vi.mock('../aboutApi');

const mockAboutData: aboutApi.SystemAboutData = {
  platform: '👍kanban',
  slug: 'thumbs-up-kanban',
  tagline: 'The difference between a swarm and an Agile team is a kanban.',
  version: '0.2.1205',
  license_spdx: 'Apache-2.0',
  git_commit: '9d5577ad9b50',
  build_timestamp: '2026-11-21T01:14:28Z',
  openapi_version: '0.2.1205',
  openapi_bundle_hash: '1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',
  frontend_bundle_hash: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
  api_docs_urls: {
    swagger_ui: '/api/docs',
    redoc: '/api/redoc',
    openapi_json: '/api/openapi.json',
  },
  license: 'Apache License Version 2.0 (Verbatim Text)',
  notice: 'Third-Party Software Notices (Verbatim Text)',
  sbom_summary: {
    total_components: 4,
    python_components: 2,
    web_components: 2,
    permissive_count: 3,
    allowlisted_count: 1,
    unknown_count: 0,
    deny_count: 0,
  },
  components: [
    {
      name: 'fastapi',
      version: '0.115.0',
      ecosystem: 'python',
      purl: 'pkg:pypi/fastapi@0.115.0',
      license: 'MIT',
      license_verdict: 'ALLOW',
      scope: 'required',
      description: 'FastAPI web framework',
    },
    {
      name: 'pillow',
      version: '13.0.0',
      ecosystem: 'python',
      purl: 'pkg:pypi/pillow@13.0.0',
      license: 'MIT-CMU',
      license_verdict: 'ALLOWLISTED',
      scope: 'required',
    },
    {
      name: 'vitest',
      version: '5.1.0',
      ecosystem: 'node',
      purl: 'pkg:npm/vitest@5.1.0',
      license: 'MIT',
      license_verdict: 'ALLOW',
      scope: 'dev',
    },
    {
      name: 'lucide-react',
      version: '1.0.0',
      ecosystem: 'web',
      purl: 'pkg:npm/lucide-react@1.0.0',
      license: 'ISC',
      license_verdict: 'ALLOW',
      scope: 'required',
    },
  ],
};

describe('AboutPage', () => {
  let queryClient: QueryClient;
  let writeTextMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.mocked(aboutApi.getSbomDownloadUrl).mockReturnValue('/api/v1/system/sbom?download=true');
    writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });
  });

  const renderPage = (): ReturnType<typeof render> =>
    render(
      <QueryClientProvider client={queryClient}>
        <AboutPage />
      </QueryClientProvider>,
    );

  it('renders loading state initially', () => {
    vi.mocked(aboutApi.fetchSystemAbout).mockReturnValue(
      new Promise<aboutApi.SystemAboutData>(() => undefined),
    );
    renderPage();
    expect(screen.getByText('Loading system about metadata...')).toBeDefined();
  });

  it('renders error state on query failure', async () => {
    vi.mocked(aboutApi.fetchSystemAbout).mockRejectedValueOnce(new Error('Network error'));
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText(/Failed to load system information/i),
      ).toBeDefined();
    });
  });

  it('renders hero card with branding, tagline, version, license pill, and download SBOM button', async () => {
    vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValueOnce(mockAboutData);
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('about-tagline')).toBeDefined();
    });

    expect(screen.getByTestId('about-tagline').textContent).toContain(
      'The difference between a swarm and an Agile team is a kanban.',
    );
    expect(screen.getByText('👍kanban')).toBeDefined();
    expect(screen.getByText('v0.2.1205')).toBeDefined();
    expect(screen.getByText('Apache-2.0')).toBeDefined();
    expect(screen.getByTestId('about-build-commit')).toBeDefined();
    expect(screen.getByTestId('about-build-commit').textContent).toContain('9d5577ad9b50');
    expect(screen.getByTestId('about-git-commit').textContent).toBe('9d5577ad9b50');
    expect(screen.getByTestId('about-meta-version').textContent).toBe('0.2.1205');

    const downloadBtn = screen.getByTestId('download-sbom-btn');
    expect(downloadBtn.getAttribute('href')).toBe('/api/v1/system/sbom?download=true');
  });

  it('renders REST API & OpenAPI documentation links with interactive targets', async () => {
    vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValueOnce(mockAboutData);
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('about-api-docs-section')).toBeDefined();
    });

    const swaggerLink = screen.getByTestId('about-swagger-link');
    expect(swaggerLink.getAttribute('href')).toBe('/api/docs');
    expect(swaggerLink.getAttribute('target')).toBe('_blank');

    const redocLink = screen.getByTestId('about-redoc-link');
    expect(redocLink.getAttribute('href')).toBe('/api/redoc');

    const openapiLink = screen.getByTestId('about-openapi-link');
    expect(openapiLink.getAttribute('href')).toBe('/api/openapi.json');
  });

  it('renders supply-chain summary metrics and filters SBOM table by search, ecosystem, and scope', async () => {
    vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValueOnce(mockAboutData);
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('sbom-table')).toBeDefined();
    });

    // Summary metrics
    expect(screen.getByText('4')).toBeDefined(); // Total
    expect(screen.getAllByText('2').length).toBeGreaterThan(0); // Python and Web count

    // Default: scope is runtime only, so vitest (dev) is hidden, fastapi, pillow, and lucide-react shown
    expect(screen.getByText('fastapi')).toBeDefined();
    expect(screen.getByText('pillow')).toBeDefined();
    expect(screen.getByText('lucide-react')).toBeDefined();
    expect(screen.queryByText('vitest')).toBeNull();

    // Verify dynamic ecosystem button counts match runtime scope
    expect(screen.getByTestId('filter-ecosystem-python').textContent).toContain('Python (2)');
    expect(screen.getByTestId('filter-ecosystem-node').textContent).toContain('Web (1)');

    // Toggle scope to all (inc dev)
    fireEvent.click(screen.getByTestId('toggle-scope-runtime'));
    expect(screen.getByText('vitest')).toBeDefined();

    // Verify dynamic ecosystem button counts update to all scope
    expect(screen.getByTestId('filter-ecosystem-python').textContent).toContain('Python (2)');
    expect(screen.getByTestId('filter-ecosystem-node').textContent).toContain('Web (2)');

    // Filter by Python ecosystem
    fireEvent.click(screen.getByTestId('filter-ecosystem-python'));
    expect(screen.getByText('fastapi')).toBeDefined();
    expect(screen.queryByText('vitest')).toBeNull();
    expect(screen.queryByText('lucide-react')).toBeNull();

    // Filter by Web ecosystem (covers both 'node' and 'web' ecosystems)
    fireEvent.click(screen.getByTestId('filter-ecosystem-node'));
    expect(screen.getByText('vitest')).toBeDefined();
    expect(screen.getByText('lucide-react')).toBeDefined();
    expect(screen.queryByText('fastapi')).toBeNull();

    // Filter all ecosystems
    fireEvent.click(screen.getByTestId('filter-ecosystem-all'));

    // Search query
    const searchInput = screen.getByTestId('sbom-search-input');
    fireEvent.change(searchInput, { target: { value: 'fast' } });
    expect(screen.getByText('fastapi')).toBeDefined();
    expect(screen.queryByText('vitest')).toBeNull();

    // Search nonexistent query
    fireEvent.change(searchInput, { target: { value: 'nonexistent-xyz' } });
    expect(screen.getByText(/No components match your search/i)).toBeDefined();
  });

  it('switches between Apache-2.0 License and Third-Party NOTICE and copies to clipboard', async () => {
    vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValueOnce(mockAboutData);
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('apache-license-text')).toBeDefined();
    });

    // Initial: Apache-2.0 tab active
    expect(screen.getByTestId('apache-license-text').textContent).toContain(
      'Apache License Version 2.0 (Verbatim Text)',
    );

    // Click Copy License button and test timeout reset
    const copyBtn = screen.getByTestId('copy-license-btn');
    fireEvent.click(copyBtn);
    await waitFor(() => {
      expect(screen.getByText('Copied!')).toBeDefined();
    });
    expect(writeTextMock).toHaveBeenCalledWith(
      'Apache License Version 2.0 (Verbatim Text)',
    );

    // Wait for timeout to revert copied state
    await waitFor(
      () => {
        expect(screen.getByText('Copy License')).toBeDefined();
      },
      { timeout: 3000 },
    );

    // Switch to Third-Party NOTICE tab
    fireEvent.click(screen.getByTestId('tab-third-party-notice'));
    expect(screen.getByTestId('apache-license-text').textContent).toContain(
      'Third-Party Software Notices (Verbatim Text)',
    );

    // Switch back to Apache-2.0 tab (covers line 343 onClick)
    fireEvent.click(screen.getByTestId('tab-apache-license'));
    expect(screen.getByTestId('apache-license-text').textContent).toContain(
      'Apache License Version 2.0 (Verbatim Text)',
    );

    // Copy notice text
    fireEvent.click(screen.getByTestId('tab-third-party-notice'));
    fireEvent.click(screen.getByTestId('copy-license-btn'));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith(
        'Third-Party Software Notices (Verbatim Text)',
      );
    });
  });

  it('handles clipboard copy error gracefully and renders DENY/UNKNOWN pills', async () => {
    const dataWithDeny: aboutApi.SystemAboutData = {
      ...mockAboutData,
      sbom_summary: {
        ...mockAboutData.sbom_summary,
        deny_count: 1,
      },
      components: [
        {
          name: 'gpl-pkg',
          version: '1.0.0',
          ecosystem: 'python',
          purl: 'pkg:pypi/gpl-pkg@1.0.0',
          license: 'GPL-3.0',
          license_verdict: 'DENY',
          scope: 'required',
        },
        {
          name: 'unknown-pkg',
          version: '1.0.0',
          ecosystem: 'node',
          purl: 'pkg:npm/unknown-pkg@1.0.0',
          license: 'CUSTOM',
          license_verdict: 'UNKNOWN',
          scope: 'required',
        },
      ],
    };

    vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValueOnce(dataWithDeny);
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockRejectedValueOnce(new Error('Clipboard denied')),
      },
    });

    renderPage();
    await waitFor(() => {
      expect(screen.getByText('gpl-pkg')).toBeDefined();
    });

    expect(screen.getByText('DENY')).toBeDefined();
    expect(screen.getByText('UNKNOWN')).toBeDefined();

    const copyBtn = screen.getByTestId('copy-license-btn');
    act(() => {
      fireEvent.click(copyBtn);
    });
    // Should not throw or crash
    expect(screen.queryByText('Copied!')).toBeNull();
  });

  it('renders Agent Instructions (/llms.txt) card and copies onboarding prompt', async () => {
    vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValueOnce(mockAboutData);
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('about-llms-txt-card')).toBeDefined();
    });

    const llmsCard = screen.getByTestId('about-llms-txt-card');
    expect(llmsCard.textContent).toContain('Agent Instructions (/llms.txt)');
    expect(screen.getByTestId('about-llms-txt-link').getAttribute('href')).toBe('/llms.txt');
    expect(screen.getByTestId('about-llms-full-link').getAttribute('href')).toBe('/llms-full.txt');

    const copyBtn = screen.getByTestId('copy-llms-onboarding-prompt-btn');
    expect(copyBtn.textContent).toBe('Copy Onboarding Prompt');

    fireEvent.click(copyBtn);
    await waitFor(() => {
      expect(screen.getByText('Copied Prompt!')).toBeDefined();
    });
    expect(writeTextMock).toHaveBeenCalledWith(
      expect.stringContaining("/llms.txt, learn 👍kanban's ticket workflow"),
    );

    // Wait for timeout reset
    await waitFor(
      () => {
        expect(screen.getByText('Copy Onboarding Prompt')).toBeDefined();
      },
      { timeout: 3000 },
    );

    // Test copy error fallback without crashing
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockRejectedValueOnce(new Error('Copy failed')),
      },
    });
    fireEvent.click(copyBtn);
  });

  it('Case 3: renders version and release channel with raw build hashes in AdvancedSection', async () => {
    vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValueOnce(mockAboutData);
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('about-meta-version')).toBeDefined();
    });

    // Version and Release Channel are visible
    expect(screen.getByTestId('about-meta-version').textContent).toBe('0.2.1205');
    expect(screen.getByTestId('about-release-channel').textContent).toBe('Stable');
    expect(screen.getByTestId('about-git-commit').textContent).toBe('9d5577ad9b50');

    // Advanced technical details section is collapsed by default
    const advancedSection = screen.getByTestId('about-advanced-technical-details');
    expect(advancedSection).toBeDefined();
    expect(advancedSection.hasAttribute('open')).toBe(false);

    // Expand the advanced section
    const toggle = screen.getByTestId('about-advanced-technical-details-toggle');
    fireEvent.click(toggle);

    expect(advancedSection.hasAttribute('open')).toBe(true);
    expect(screen.getByTestId('about-openapi-bundle-hash').textContent).toBe(
      mockAboutData.openapi_bundle_hash,
    );
    expect(screen.getByTestId('about-frontend-bundle-hash').textContent).toBe(
      mockAboutData.frontend_bundle_hash,
    );
    expect(screen.getByTestId('about-build-timestamp').textContent).toBe(
      mockAboutData.build_timestamp,
    );
  });

  it('filters SBOM table by license and purl searches, and handles empty component datasets', async () => {
    vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValueOnce(mockAboutData);
    const { unmount: unmountFirst } = renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('sbom-table')).toBeDefined();
    });

    const searchInput = screen.getByTestId('sbom-search-input');

    // Search by license (MIT-CMU)
    fireEvent.change(searchInput, { target: { value: 'CMU' } });
    expect(screen.getByText('pillow')).toBeDefined();
    expect(screen.queryByText('fastapi')).toBeNull();

    // Search by purl (pkg:npm)
    fireEvent.change(searchInput, { target: { value: 'pkg:npm' } });
    expect(screen.getByText('lucide-react')).toBeDefined();
    expect(screen.queryByText('pillow')).toBeNull();

    unmountFirst();

    // Render with components empty and optional build hashes omitted
    const emptyData: aboutApi.SystemAboutData = {
      platform: mockAboutData.platform,
      slug: mockAboutData.slug,
      tagline: mockAboutData.tagline,
      version: mockAboutData.version,
      license_spdx: mockAboutData.license_spdx,
      api_docs_urls: mockAboutData.api_docs_urls,
      sbom_summary: mockAboutData.sbom_summary,
      license: '',
      notice: '',
      components: [],
    };
    vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValueOnce(emptyData);
    const { unmount } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <AboutPage />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('about-tagline')).toBeDefined();
    });
    expect(screen.getByText('No components match your search or filter criteria.')).toBeDefined();
    expect(screen.getByTestId('about-git-commit').textContent).toBe('unknown');
    expect(screen.queryByTestId('about-build-commit')).toBeNull();

    // Copy with undefined license
    const copyBtn = screen.getByTestId('copy-license-btn');
    fireEvent.click(copyBtn);
    expect(writeTextMock).toHaveBeenCalledWith('');

    unmount();
  });

  describe('StudioDocLink Header Integration and Responsive Invariants (KAN-512)', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
    });

    it('renders about-doc-link with correct href, label, and title in hero header actions next to download-sbom-btn in Light and Dark themes', async () => {
      vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValue(mockAboutData);

      for (const theme of ['light', 'dark'] as const) {
        document.documentElement.setAttribute('data-theme', theme);
        const { unmount } = renderPage();

        await waitFor(() => {
          expect(screen.getByTestId('about-doc-link')).toBeDefined();
        });

        const docLink = screen.getByTestId('about-doc-link');
        expect(docLink.getAttribute('href')).toBe('/docs/system-topology-and-multi-container-architecture');
        expect(docLink.getAttribute('aria-label')).toBe('Architecture & System Topology');
        expect(docLink.textContent).toContain('Documentation ->');

        // Verify placement inside hero actions next to download sbom button
        const heroActions = docLink.closest('.kb-about-hero-actions');
        expect(heroActions).not.toBeNull();
        const downloadBtn = heroActions?.querySelector('[data-testid="download-sbom-btn"]');
        expect(downloadBtn).not.toBeNull();

        unmount();
      }
    });

    it('supports keyboard focus navigation on about-doc-link', async () => {
      vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValue(mockAboutData);
      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId('about-doc-link')).toBeDefined();
      });

      const docLink = screen.getByTestId('about-doc-link');
      docLink.focus();
      expect(document.activeElement).toBe(docLink);
    });

    it('activates in-app help panel via ShellPanelsProvider when doc link is clicked', async () => {
      vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValue(mockAboutData);

      const unregister = registerShellPanel('help', ({ arg }) => (
        <div data-testid="in-app-help-panel">
          Help Drawer for {(arg as { href?: string; title?: string } | undefined)?.title} at {(arg as { href?: string } | undefined)?.href}
        </div>
      ));

      try {
        render(
          <ShellPanelsProvider>
            <QueryClientProvider client={queryClient}>
              <AboutPage />
            </QueryClientProvider>
          </ShellPanelsProvider>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('about-doc-link')).toBeDefined();
        });

        const docLink = screen.getByTestId('about-doc-link');
        fireEvent.click(docLink);

        await waitFor(() => {
          expect(screen.getByTestId('in-app-help-panel')).toBeDefined();
        });

        const helpPanel = screen.getByTestId('in-app-help-panel');
        expect(helpPanel.textContent).toContain('Architecture & System Topology');
        expect(helpPanel.textContent).toContain('/docs/system-topology-and-multi-container-architecture');
      } finally {
        unregister();
      }
    });

    it('verifies AboutPage.tsx contains zero inline style attributes (KAN-512 CSP invariant)', () => {
      const tsxPath = path.resolve(__dirname, '../AboutPage.tsx');
      const content = fs.readFileSync(tsxPath, 'utf8');

      // Reject any style={{...}} prop in TSX
      const inlineStyleMatch = /style=\{\{/.exec(content);
      expect(inlineStyleMatch).toBeNull();
    });

    it('verifies AboutPage.css enforces canonical tokens, zero raw hex color literals, and 38px/44px button heights', () => {
      const cssPath = path.resolve(__dirname, '../AboutPage.css');
      const cssContent = fs.readFileSync(cssPath, 'utf8');

      // Zero raw hex colors
      expect(cssContent).not.toMatch(/#[0-9a-fA-F]{3,8}/);

      // Hero actions and doc link matching desktop height and nowrap
      expect(cssContent).toContain('.kb-about-hero-actions .kb-studio-doc-link');
      expect(cssContent).toContain('min-height: var(--prop-row-h, 38px)');
      expect(cssContent).toContain('white-space: nowrap');

      // Primary download button matching 38px desktop height
      expect(cssContent).toMatch(/\.kb-about-btn-primary\s*\{[^}]*min-height:\s*var\(--prop-row-h,\s*38px\)/);

      // Mobile media query with 44px tap target height
      expect(cssContent).toContain('@media (max-width: 767px)');
      expect(cssContent).toContain('min-height: var(--tap-min, 44px)');

      // Badge commit WCAG AA contrast token and badge wrapping
      expect(cssContent).toMatch(/\.kb-about-badge-commit\s*\{[^}]*color:\s*var\(--badge-fg\)/);
      expect(cssContent).toMatch(/\.kb-about-badges\s*\{[^}]*flex-wrap:\s*wrap/);
    });
  });

  describe('FieldHelpHint SBOM Filter Search Integration (KAN-513)', () => {
    it('renders FieldHelpHint adjacent to SBOM dependency search input label in .kb-about-search-label-row wrapper', async () => {
      vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValue(mockAboutData);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId('sbom-search-input')).toBeDefined();
      });

      const label = screen.getByText('Search Components & Licenses');
      const trigger = screen.getByTestId('sbom-search-help-hint');
      const input = screen.getByTestId('sbom-search-input');

      expect(label).toBeDefined();
      expect(trigger).toBeDefined();
      expect(input).toBeDefined();
      expect(trigger.getAttribute('aria-label')).toBe('Help for Search Components & Licenses');
      expect(label.getAttribute('for')).toBe('sbom-search-input');
      expect(input.getAttribute('id')).toBe('sbom-search-input');

      // MANDATORY INVARIANT: never nest FieldHelpHint inside label!
      expect(label.contains(trigger)).toBe(false);
      expect(document.querySelectorAll('label button.field-help-hint').length).toBe(0);
      expect(document.querySelectorAll('label .field-help-hint').length).toBe(0);

      // Sibling elements in .kb-about-search-label-row wrapper
      const labelRow = trigger.closest('.kb-about-search-label-row');
      expect(labelRow).not.toBeNull();
      expect(labelRow?.contains(label)).toBe(true);
      expect(labelRow?.contains(trigger)).toBe(true);
      expect(label.parentElement).toBe(labelRow);
      expect(trigger.parentElement).toBe(labelRow);
    });

    it('opens FieldHelpHint popover on focus with summary, defaultValue, and system topology docHref', async () => {
      vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValue(mockAboutData);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId('sbom-search-help-hint')).toBeDefined();
      });

      const trigger = screen.getByTestId('sbom-search-help-hint');

      act(() => {
        trigger.focus();
      });

      const popover = screen.getByTestId('sbom-search-help-hint-popover');
      expect(popover).toBeDefined();
      expect(popover.textContent).toContain('Search Components & Licenses');
      expect(popover.textContent).toContain('Filtering matches both package names and SPDX license identifiers');
      expect(popover.textContent).toContain('MIT');
      expect(popover.textContent).toContain('Apache-2.0');
      expect(popover.textContent).toContain('All Ecosystems');

      const docLink = popover.querySelector('a');
      expect(docLink).not.toBeNull();
      expect(docLink?.getAttribute('href')).toBe('/docs/system-topology-and-multi-container-architecture');
    });

    it('dismisses FieldHelpHint popover on Escape key and restores focus', async () => {
      vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValue(mockAboutData);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId('sbom-search-help-hint')).toBeDefined();
      });

      const trigger = screen.getByTestId('sbom-search-help-hint');

      act(() => {
        trigger.focus();
      });

      expect(screen.getByTestId('sbom-search-help-hint-popover')).toBeDefined();

      act(() => {
        fireEvent.keyDown(trigger, { key: 'Escape' });
      });

      expect(screen.queryByTestId('sbom-search-help-hint-popover')).toBeNull();
    });

    it('verifies HTML 4.10.4 zero nested label-button violations across entire AboutPage DOM', async () => {
      vi.mocked(aboutApi.fetchSystemAbout).mockResolvedValue(mockAboutData);

      renderPage();

      await waitFor(() => {
        expect(screen.getByTestId('about-page-container')).toBeDefined();
      });

      const nestedButtons = document.querySelectorAll('label button.field-help-hint');
      expect(nestedButtons.length).toBe(0);

      const anyNestedButtons = document.querySelectorAll('label button');
      expect(anyNestedButtons.length).toBe(0);
    });

    it('verifies AboutPage.css enforces .kb-about-search-label-row flex styling, canonical tokens, and 44px mobile touch targets', () => {
      const cssPath = path.resolve(__dirname, '../AboutPage.css');
      const cssContent = fs.readFileSync(cssPath, 'utf8');

      // Canonical tokens and flex layout
      expect(cssContent).toContain('.kb-about-search-label-row');
      expect(cssContent).toContain('display: inline-flex');
      expect(cssContent).toContain('align-items: center');
      expect(cssContent).toContain('gap: 6px');

      // Search input desktop 38px height and tokens
      expect(cssContent).toMatch(/\.kb-about-search-input\s*\{[^}]*min-height:\s*var\(--prop-row-h,\s*38px\)/);

      // Mobile 44px tap target in media query
      expect(cssContent).toMatch(/@media\s*\(max-width:\s*767px\)[^}]*\{[\s\S]*\.kb-about-search-input\s*\{[^}]*min-height:\s*var\(--tap-min,\s*44px\)/);
      expect(cssContent).toMatch(/@media\s*\(max-width:\s*767px\)[^}]*\{[\s\S]*\.kb-about-tab-btn\s*\{[^}]*min-height:\s*var\(--tap-min,\s*44px\)/);
    });
  });
});
