import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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
});
