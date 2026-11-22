/**
 * About 👍kanban Page Component (KB-ABOUT-SBOM, KAN-34).
 * Tagline, Swagger/ReDoc API Docs Links, Apache-2.0 License, and CycloneDX 1.5 SBOM.
 */

import React, { useMemo, useState, type JSX } from 'react';
import { useQuery } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import {
  fetchSystemAbout,
  getSbomDownloadUrl,
  type SbomComponent,
  type SystemAboutData,
} from './aboutApi';
import './AboutPage.css';

export function AboutPage(): JSX.Element {
  const { data, isLoading, error } = useQuery<SystemAboutData>({
    queryKey: qk.systemAbout(),
    queryFn: fetchSystemAbout,
  });

  const [searchQuery, setSearchQuery] = useState('');
  const [ecosystemFilter, setEcosystemFilter] = useState<'all' | 'python' | 'node'>('all');
  const [scopeFilter, setScopeFilter] = useState<'all' | 'runtime'>('runtime');
  const [activeLicenseTab, setActiveLicenseTab] = useState<'license' | 'notice'>('license');
  const [copiedLicense, setCopiedLicense] = useState(false);
  const [copiedPrompt, setCopiedPrompt] = useState(false);

  const components = data?.components;
  const sbomSummary = data?.sbom_summary;

  const { pythonCount, webCount } = useMemo(() => {
    if (!components) {
      return {
        pythonCount: sbomSummary?.python_components ?? 0,
        webCount: sbomSummary?.web_components ?? 0,
      };
    }
    let py = 0;
    let web = 0;
    for (const c of components) {
      if (scopeFilter === 'runtime' && c.scope === 'dev') {
        continue;
      }
      if (c.ecosystem === 'python') {
        py += 1;
      } else {
        web += 1;
      }
    }
    return { pythonCount: py, webCount: web };
  }, [components, scopeFilter, sbomSummary]);

  const filteredComponents = useMemo(() => {
    if (!components) return [];
    return components.filter((c: SbomComponent) => {
      if (ecosystemFilter !== 'all') {
        if (ecosystemFilter === 'python' && c.ecosystem !== 'python') return false;
        if (ecosystemFilter === 'node' && c.ecosystem !== 'node' && c.ecosystem !== 'web') {
          return false;
        }
      }
      if (scopeFilter === 'runtime' && c.scope === 'dev') {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesName = c.name.toLowerCase().includes(q);
        const matchesLic = c.license.toLowerCase().includes(q);
        const matchesPurl = c.purl.toLowerCase().includes(q);
        if (!matchesName && !matchesLic && !matchesPurl) {
          return false;
        }
      }
      return true;
    });
  }, [components, ecosystemFilter, scopeFilter, searchQuery]);

  const handleCopyLicense = async (): Promise<void> => {
    const textToCopy = activeLicenseTab === 'license' ? (data?.license ?? '') : (data?.notice ?? '');
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedLicense(true);
      setTimeout(() => {
        setCopiedLicense(false);
      }, 2000);
    } catch {
      // Fallback if clipboard API unavailable
    }
  };

  const handleCopyOnboardingPrompt = async (): Promise<void> => {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'https://kanban.example.com';
    const textToCopy = `Read ${origin}/llms.txt, learn 👍kanban's ticket workflow, interview me on Execution Mode (Single-Thread, Teamwork, or Swarm), Model/Quota Strategy (Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra), and QA Rigor, and save my preferences to .agents/skills/ and AGENTS.md.`;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedPrompt(true);
      setTimeout(() => {
        setCopiedPrompt(false);
      }, 2000);
    } catch {
      // Fallback if clipboard API unavailable
    }
  };

  if (isLoading) {
    return (
      <div className="kb-about-container">
        <div className="kb-about-loading">Loading system about metadata...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="kb-about-container">
        <div className="kb-about-error">
          Failed to load system information. Please ensure you are authenticated.
        </div>
      </div>
    );
  }

  const {
    platform,
    version,
    license_spdx,
    tagline,
    api_docs_urls,
    sbom_summary,
    license: licenseText,
    notice: noticeText,
  } = data;

  return (
    <div className="kb-about-container" data-testid="about-page-container">
      {/* Hero Card */}
      <section className="kb-about-hero" data-testid="about-hero-card">
        <div className="kb-about-hero-header">
          <div className="kb-about-branding">
            <h1 className="kb-about-title">{platform}</h1>
            <div className="kb-about-badges">
              <span className="kb-about-badge kb-about-badge-version">v{version}</span>
              <span className="kb-about-badge kb-about-badge-license">{license_spdx}</span>
              {data.git_commit && (
                <span className="kb-about-badge kb-about-badge-commit" data-testid="about-build-commit">
                  commit: {data.git_commit.slice(0, 12)}
                </span>
              )}
            </div>
          </div>
          <div className="kb-about-hero-actions">
            <a
              href={getSbomDownloadUrl()}
              download="thumbs-up-kanban-sbom-cdx-1.5.json"
              className="kb-about-btn-primary"
              data-testid="download-sbom-btn"
            >
              <span aria-hidden="true">📦</span>
              Download CycloneDX 1.5 SBOM
            </a>
          </div>
        </div>

        <p className="kb-about-tagline" data-testid="about-tagline">
          "{tagline}"
        </p>
      </section>

      {/* System & Build Metadata Section */}
      <section className="kb-about-section" data-testid="about-metadata-section">
        <div className="kb-about-section-header">
          <h2 className="kb-about-section-title">
            <span aria-hidden="true">⚙️</span>
            System &amp; Build Metadata
          </h2>
        </div>
        <div className="kb-about-metadata-grid">
          <div className="kb-about-meta-item">
            <span className="kb-about-meta-label">Version:</span>
            <code className="kb-about-meta-value" data-testid="about-meta-version">{version}</code>
          </div>
          <div className="kb-about-meta-item">
            <span className="kb-about-meta-label">Build / Git Commit:</span>
            <code className="kb-about-meta-value" data-testid="about-git-commit">{data.git_commit ?? 'unknown'}</code>
          </div>
          {data.build_timestamp && (
            <div className="kb-about-meta-item">
              <span className="kb-about-meta-label">Build Timestamp:</span>
              <span className="kb-about-meta-value">{data.build_timestamp}</span>
            </div>
          )}
          {data.openapi_bundle_hash && (
            <div className="kb-about-meta-item">
              <span className="kb-about-meta-label">OpenAPI Bundle Hash:</span>
              <code className="kb-about-meta-value">{data.openapi_bundle_hash}</code>
            </div>
          )}
          {data.frontend_bundle_hash && (
            <div className="kb-about-meta-item">
              <span className="kb-about-meta-label">Frontend Bundle Hash:</span>
              <code className="kb-about-meta-value">{data.frontend_bundle_hash}</code>
            </div>
          )}
        </div>
      </section>

      {/* REST API & OpenAPI Documentation Section */}
      <section className="kb-about-section" data-testid="about-api-docs-section">
        <div className="kb-about-section-header">
          <h2 className="kb-about-section-title">
            <span aria-hidden="true">🔌</span>
            REST API & OpenAPI Documentation
          </h2>
        </div>
        <div className="kb-about-api-grid">
          <a
            href={api_docs_urls.swagger_ui}
            target="_blank"
            rel="noopener noreferrer"
            className="kb-about-api-card"
            data-testid="about-swagger-link"
          >
            <div className="kb-about-api-card-title">
              <span aria-hidden="true">⚡</span>
              Swagger UI ({api_docs_urls.swagger_ui}) - Interactive Endpoint Explorer
            </div>
            <div className="kb-about-api-card-desc">
              Interactive sandbox explorer allowing authenticated testing of all REST routes and schemas.
            </div>
          </a>

          <a
            href={api_docs_urls.redoc}
            target="_blank"
            rel="noopener noreferrer"
            className="kb-about-api-card"
            data-testid="about-redoc-link"
          >
            <div className="kb-about-api-card-title">
              <span aria-hidden="true">📖</span>
              ReDoc ({api_docs_urls.redoc}) - Schema & Reference Manual
            </div>
            <div className="kb-about-api-card-desc">
              Structured API reference manual with detailed request/response payload models.
            </div>
          </a>

          <a
            href={api_docs_urls.openapi_json}
            target="_blank"
            rel="noopener noreferrer"
            className="kb-about-api-card"
            data-testid="about-openapi-link"
          >
            <div className="kb-about-api-card-title">
              <span aria-hidden="true">📜</span>
              OpenAPI 3.1.0 Spec ({api_docs_urls.openapi_json})
            </div>
            <div className="kb-about-api-card-desc">
              Machine-readable canonical OpenAPI 3.1.0 JSON specification for code generation and tooling.
            </div>
          </a>

          <div
            className="kb-about-api-card kb-about-llms-card"
            data-testid="about-llms-txt-card"
          >
            <div className="kb-about-api-card-title">
              <span aria-hidden="true">🤖</span>
              Agent Instructions (/llms.txt)
            </div>
            <div className="kb-about-api-card-desc">
              Standardized agent onboarding instructions and recommended skill catalog for Claude Code, OpenAI Codex, and Gemini CLI / Antigravity.
            </div>
            <div className="kb-about-llms-links">
              <a
                href="/llms.txt"
                target="_blank"
                rel="noopener noreferrer"
                className="kb-about-llms-link"
                data-testid="about-llms-txt-link"
              >
                View /llms.txt
              </a>
              <span className="kb-about-llms-separator" aria-hidden="true">|</span>
              <a
                href="/llms-full.txt"
                target="_blank"
                rel="noopener noreferrer"
                className="kb-about-llms-link"
                data-testid="about-llms-full-link"
              >
                View /llms-full.txt
              </a>
            </div>
            <div className="kb-about-llms-actions">
              <button
                type="button"
                className="kb-about-copy-prompt-btn"
                data-testid="copy-llms-onboarding-prompt-btn"
                onClick={() => {
                  void handleCopyOnboardingPrompt();
                }}
              >
                {copiedPrompt ? 'Copied Prompt!' : 'Copy Onboarding Prompt'}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Software Bill of Materials & Supply Chain Section */}
      <section className="kb-about-section" data-testid="about-sbom-section">
        <div className="kb-about-section-header">
          <h2 className="kb-about-section-title">
            <span aria-hidden="true">🛡️</span>
            Software Bill of Materials (CycloneDX 1.5)
          </h2>
        </div>

        {/* Summary Metric Cards */}
        <div className="kb-about-metrics-grid" data-testid="sbom-metrics-grid">
          <div className="kb-about-metric-card">
            <div className="kb-about-metric-label">Total Dependencies</div>
            <div className="kb-about-metric-value">{sbom_summary.total_components}</div>
          </div>
          <div className="kb-about-metric-card">
            <div className="kb-about-metric-label">Python Backend</div>
            <div className="kb-about-metric-value">{sbom_summary.python_components}</div>
          </div>
          <div className="kb-about-metric-card">
            <div className="kb-about-metric-label">Web Frontend</div>
            <div className="kb-about-metric-value">{sbom_summary.web_components}</div>
          </div>
          <div className="kb-about-metric-card">
            <div className="kb-about-metric-label">Permissive (Approved)</div>
            <div className="kb-about-metric-value kb-about-metric-value-ok">
              {sbom_summary.permissive_count}
            </div>
          </div>
          <div className="kb-about-metric-card">
            <div className="kb-about-metric-label">Allowlisted Exceptions</div>
            <div className="kb-about-metric-value kb-about-metric-value-warn">
              {sbom_summary.allowlisted_count}
            </div>
          </div>
          <div className="kb-about-metric-card">
            <div className="kb-about-metric-label">Copyleft / Denied</div>
            <div
              className={`kb-about-metric-value ${
                sbom_summary.deny_count > 0 ? 'kb-about-metric-value-deny' : 'kb-about-metric-value-ok'
              }`}
            >
              {sbom_summary.deny_count}
            </div>
          </div>
        </div>

        {/* SBOM Filter Controls */}
        <div className="kb-about-table-controls">
          <div className="kb-about-table-search">
            <input
              type="text"
              placeholder="Search components or licenses..."
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); }}
              className="kb-about-search-input"
              data-testid="sbom-search-input"
            />
          </div>
          <div className="kb-about-table-filters">
            <button
              type="button"
              className={`kb-about-tab-btn ${ecosystemFilter === 'all' ? 'active' : ''}`}
              onClick={() => { setEcosystemFilter('all'); }}
              data-testid="filter-ecosystem-all"
            >
              All Ecosystems
            </button>
            <button
              type="button"
              className={`kb-about-tab-btn ${ecosystemFilter === 'python' ? 'active' : ''}`}
              onClick={() => { setEcosystemFilter('python'); }}
              data-testid="filter-ecosystem-python"
            >
              Python ({pythonCount})
            </button>
            <button
              type="button"
              className={`kb-about-tab-btn ${ecosystemFilter === 'node' ? 'active' : ''}`}
              onClick={() => { setEcosystemFilter('node'); }}
              data-testid="filter-ecosystem-node"
            >
              Web ({webCount})
            </button>
            <button
              type="button"
              className={`kb-about-tab-btn ${scopeFilter === 'runtime' ? 'active' : ''}`}
              onClick={() => {
                setScopeFilter(scopeFilter === 'runtime' ? 'all' : 'runtime');
              }}
              data-testid="toggle-scope-runtime"
            >
              {scopeFilter === 'runtime' ? 'Scope: Runtime Only' : 'Scope: All (Inc. Dev)'}
            </button>
          </div>
        </div>

        {/* SBOM Table */}
        <div className="kb-about-table-wrapper">
          <table className="kb-about-table" data-testid="sbom-table">
            <thead>
              <tr>
                <th>Component</th>
                <th>Version</th>
                <th>Ecosystem</th>
                <th>License</th>
                <th>Verdict</th>
                <th>Scope</th>
              </tr>
            </thead>
            <tbody>
              {filteredComponents.length === 0 ? (
                <tr>
                  <td colSpan={6} className="kb-about-empty-table">
                    No components match your search or filter criteria.
                  </td>
                </tr>
              ) : (
                filteredComponents.map((c) => (
                  <tr key={`${c.ecosystem}-${c.name}-${c.version}`}>
                    <td className="kb-about-pkg-name">{c.name}</td>
                    <td className="kb-about-pkg-version">{c.version}</td>
                    <td>{c.ecosystem}</td>
                    <td>{c.license}</td>
                    <td>
                      <span
                        className={`kb-about-verdict-pill ${
                          c.license_verdict === 'ALLOW'
                            ? 'kb-about-verdict-allow'
                            : c.license_verdict === 'ALLOWLISTED'
                              ? 'kb-about-verdict-allowlisted'
                              : c.license_verdict === 'DENY'
                                ? 'kb-about-verdict-deny'
                                : 'kb-about-verdict-unknown'
                        }`}
                      >
                        {c.license_verdict}
                      </span>
                    </td>
                    <td>{c.scope}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Verbatim Apache-2.0 License & Third-Party Notice Viewer */}
      <section className="kb-about-section" data-testid="about-license-section">
        <div className="kb-about-section-header">
          <div className="kb-about-license-tabs">
            <button
              type="button"
              className={`kb-about-tab-btn ${activeLicenseTab === 'license' ? 'active' : ''}`}
              onClick={() => { setActiveLicenseTab('license'); }}
              data-testid="tab-apache-license"
            >
              Apache-2.0 License
            </button>
            <button
              type="button"
              className={`kb-about-tab-btn ${activeLicenseTab === 'notice' ? 'active' : ''}`}
              onClick={() => { setActiveLicenseTab('notice'); }}
              data-testid="tab-third-party-notice"
            >
              Third-Party NOTICE
            </button>
          </div>
          <button
            type="button"
            className="kb-about-btn-secondary"
            onClick={() => { void handleCopyLicense(); }}
            data-testid="copy-license-btn"
          >
            {copiedLicense ? 'Copied!' : 'Copy License'}
          </button>
        </div>

        <pre
          className="kb-about-license-content"
          data-testid="apache-license-text"
        >
          {activeLicenseTab === 'license' ? licenseText : noticeText}
        </pre>
      </section>
    </div>
  );
}
