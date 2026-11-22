import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchSystemAbout, getSbomDownloadUrl } from '../aboutApi';
import { apiFetch } from '../../../api/client';

vi.mock('../../../api/client', () => ({
  apiFetch: vi.fn(),
}));

const mockApiFetch = vi.mocked(apiFetch);

describe('aboutApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetchSystemAbout calls /api/v1/system/about and returns typed payload', async () => {
    const mockData = {
      platform: '👍kanban',
      slug: 'thumbs-up-kanban',
      tagline: 'The difference between a swarm and an Agile team is a kanban.',
      version: '0.2.1205',
      license_spdx: 'Apache-2.0',
      api_docs_urls: {
        swagger_ui: '/api/docs',
        redoc: '/api/redoc',
        openapi_json: '/api/openapi.json',
      },
      license: 'Apache-2.0 License Text',
      notice: 'Third-Party Notice Text',
      sbom_summary: {
        total_components: 10,
        python_components: 6,
        web_components: 4,
        permissive_count: 10,
        allowlisted_count: 0,
        unknown_count: 0,
        deny_count: 0,
      },
      components: [
        {
          name: 'fastapi',
          version: '0.115.0',
          ecosystem: 'python' as const,
          purl: 'pkg:pypi/fastapi@0.115.0',
          license: 'MIT',
          license_verdict: 'ALLOW' as const,
          scope: 'required',
        },
      ],
    };

    mockApiFetch.mockResolvedValueOnce(mockData);

    const result = await fetchSystemAbout();
    expect(mockApiFetch).toHaveBeenCalledWith('GET', '/api/v1/system/about');
    expect(result).toEqual(mockData);
  });

  it('getSbomDownloadUrl returns attachment download URL', () => {
    expect(getSbomDownloadUrl()).toBe('/api/v1/system/sbom?download=true');
  });
});
