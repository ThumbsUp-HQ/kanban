/**
 * System About & SBOM API client functions and types (KAN-34).
 */

import { apiFetch } from '../../api/client';

export interface ApiDocsUrls {
  readonly swagger_ui: string;
  readonly redoc: string;
  readonly openapi_json: string;
}

export interface SbomSummary {
  readonly total_components: number;
  readonly python_components: number;
  readonly web_components: number;
  readonly permissive_count: number;
  readonly allowlisted_count: number;
  readonly unknown_count: number;
  readonly deny_count: number;
}

export interface SbomComponent {
  readonly name: string;
  readonly version: string;
  readonly ecosystem: 'python' | 'node' | 'web';
  readonly purl: string;
  readonly license: string;
  readonly license_verdict: 'ALLOW' | 'DENY' | 'UNKNOWN' | 'ALLOWLISTED';
  readonly scope: string;
  readonly description?: string;
}

export interface SystemAboutData {
  readonly platform: string;
  readonly slug: string;
  readonly tagline: string;
  readonly version: string;
  readonly license_spdx: string;
  readonly api_docs_urls: ApiDocsUrls;
  readonly license: string;
  readonly notice: string;
  readonly sbom_summary: SbomSummary;
  readonly components: readonly SbomComponent[];
}

export async function fetchSystemAbout(): Promise<SystemAboutData> {
  const result = (await apiFetch('GET', '/api/v1/system/about' as never)) as SystemAboutData;
  return result;
}

export function getSbomDownloadUrl(): string {
  return '/api/v1/system/sbom?download=true';
}
