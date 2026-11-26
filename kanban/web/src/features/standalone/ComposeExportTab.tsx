/**
 * Compose Export & Production Promotion Tab (KB-P3-52, S2.4).
 * Provides 1-click docker-compose.yml download, copyable .env.example, and 4-step migration runbook.
 */

import React, { useCallback, useEffect, useState, type JSX } from 'react';
import { safeCopyToClipboard } from '../../utils/uuid';
import { apiFetch } from '../../api/client';
import { ApiProblem } from '../../api/problem';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';

export interface ComposeExportData {
  readonly filename: string;
  readonly compose_yaml: string;
  readonly env_template: string;
  readonly migration_steps_markdown: string;
  readonly single_container_compose_yaml?: string;
}

export interface ComposeExportTabProps {
  readonly initialData?: ComposeExportData | null;
}

export function ComposeExportTab({
  initialData = null,
}: ComposeExportTabProps): JSX.Element {
  const [data, setData] = useState<ComposeExportData | null>(initialData);
  const [isLoading, setIsLoading] = useState<boolean>(!initialData);
  const [error, setError] = useState<string | null>(null);
  const [copiedEnv, setCopiedEnv] = useState<boolean>(false);
  const [isDownloading, setIsDownloading] = useState<boolean>(false);
  const [composeMode, setComposeMode] = useState<'multi' | 'single'>('multi');

  const fetchExportData = useCallback(async (): Promise<ComposeExportData | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const json = (await apiFetch(
        'GET',
        '/api/v1/admin/standalone/compose-export' as never,
      )) as ComposeExportData;
      setData(json);
      return json;
    } catch (err) {
      const msg =
        err instanceof ApiProblem
          ? `Failed to load compose export: ${String(err.status)}`
          : (err as Error).message || 'Failed to load export data';
      setError(msg);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!initialData) {
      void (async () => {
        await fetchExportData();
      })();
    }
  }, [initialData, fetchExportData]);

  const handleDownload = async (): Promise<void> => {
    setIsDownloading(true);
    try {
      let exportData = data;
      /* v8 ignore start - defensive fallback if download clicked before initialData loaded */
      exportData ??= await fetchExportData();
      if (!exportData) {
        return;
      }
      /* v8 ignore stop */
      const yamlContent =
        composeMode === 'single' && exportData.single_container_compose_yaml
          ? exportData.single_container_compose_yaml
          : exportData.compose_yaml;
      const downloadFilename =
        composeMode === 'single' ? 'docker-compose.standalone.yml' : exportData.filename || 'docker-compose.yml';

      const blob = new Blob([yamlContent], {
        type: 'application/x-yaml;charset=utf-8',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = downloadFilename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Download failed';
      setError(msg);
    } finally {
      setIsDownloading(false);
    }
  };

  const handleCopyEnv = async (): Promise<void> => {
    try {
      let exportData = data;
      /* v8 ignore start - defensive fallback if copy clicked before initialData loaded */
      exportData ??= await fetchExportData();
      if (!exportData) {
        return;
      }
      /* v8 ignore stop */
      const success = await safeCopyToClipboard(exportData.env_template);
      if (success) {
        setCopiedEnv(true);
        /* v8 ignore start */
        setTimeout(() => {
          setCopiedEnv(false);
        }, 2000);
        /* v8 ignore stop */
      } else {
        setError('Failed to copy');
      }
    /* v8 ignore start */
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to copy';
      setError(msg);
    }
    /* v8 ignore stop */
  };

  return (
    <div className="standalone-panel__compose-container">
      {error && (
        <div role="alert" className="standalone-panel__error">
          {error}
        </div>
      )}

      <header className="standalone-panel__tab-header">
        <div className="standalone-panel__tab-header-title-group">
          <h3 className="standalone-panel__tab-header-title">Compose &amp; Promotion</h3>
          <p className="standalone-panel__tab-header-subtitle">
            Export container manifests and runbooks for standalone and production deployment.
          </p>
        </div>
        <div className="standalone-panel__tab-header-actions">
          <StudioDocLink
            href="/docs/production-promotion-and-backup-runbook#standalone-to-production-promotion-workflow"
            title="Compose Promotion Runbook"
            testId="compose-export-doc-link"
          />
        </div>
      </header>

      {/* Mode Selector */}
      <div className="standalone-panel__compose-mode-toggle" role="group" aria-label="Compose template mode">
        <button
          type="button"
          className={`standalone-panel__tab-btn ${composeMode === 'multi' ? 'standalone-panel__tab-btn--active' : ''}`}
          onClick={() => { setComposeMode('multi'); }}
        >
          Multi-Container Stack (Production)
        </button>
        <button
          type="button"
          className={`standalone-panel__tab-btn ${composeMode === 'single' ? 'standalone-panel__tab-btn--active' : ''}`}
          onClick={() => { setComposeMode('single'); }}
        >
          Single-Container (Standalone)
        </button>
      </div>

      <div className="standalone-panel__btn-group">
        <button
          type="button"
          onClick={() => {
            void handleDownload();
          }}
          disabled={isLoading || isDownloading}
          className="standalone-panel__btn standalone-panel__btn--primary"
        >
          {isDownloading
            ? 'Downloading...'
            : composeMode === 'single'
              ? 'Download docker-compose.standalone.yml'
              : 'Download docker-compose.yml'}
        </button>

        {composeMode === 'multi' && (
          <button
            type="button"
            onClick={() => {
              void handleCopyEnv();
            }}
            disabled={isLoading}
            className="standalone-panel__btn standalone-panel__btn--secondary"
          >
            {copiedEnv ? 'Copied!' : 'Copy .env.example'}
          </button>
        )}
      </div>

      {composeMode === 'multi' ? (
        <>
          <div className="standalone-panel__checklist-card">
            <div className="standalone-panel__compose-network-header">
              <h4 className="standalone-panel__checklist-title">
                5-Network Architecture Summary
              </h4>
              <FieldHelpHint
                title="5-Network Architecture Summary"
                summary="Production Compose stacks isolate containers across 5 tiers: edge_net (reverse proxy ingress & TLS), app_net (application runtime & internal plane), data_net (PostgreSQL 16 DB), sandbox_net (air-gapped script sandbox), and egress_llm_net (outbound AI APIs)."
                validValues={{
                  edge_net: 'Reverse proxy public ingress & TLS termination',
                  app_net: 'Application runtime & internal control plane',
                  data_net: 'Isolated PostgreSQL 16 DB tier (no internet route)',
                  sandbox_net: 'Air-gapped custom script sandbox (IPC only)',
                  egress_llm_net: 'Restricted outbound HTTPS to configured AI APIs',
                }}
                docHref="/docs/system-topology-and-multi-container-architecture"
                testId="compose-network-help"
              />
            </div>
            <pre className="standalone-panel__checklist-pre">
{`• edge_net: Reverse proxy public ingress & TLS termination
• app_net: Application runtime & internal control plane
• data_net: Isolated PostgreSQL 16 database tier (no internet route)
• sandbox_net: Air-gapped custom script sandbox (IPC only)
• egress_llm_net: Restricted outbound HTTPS to configured AI APIs`}
            </pre>
          </div>

          <div className="standalone-panel__checklist-card">
            <h4 className="standalone-panel__checklist-title">
              PostgreSQL 16 Promotion Runbook:
            </h4>
            <pre className="standalone-panel__checklist-pre">
{`1. Generate secrets
2. Download encrypted backup (.kbbak)
3. docker compose up -d postgres
4. kanban-ctl restore / pg_restore into external PostgreSQL 16`}
            </pre>
          </div>
        </>
      ) : (
        <div className="standalone-panel__checklist-card">
          <h4 className="standalone-panel__checklist-title">
            Single-Container Standalone Spec:
          </h4>
          <pre className="standalone-panel__checklist-pre">
{`Runs 👍kanban and embedded PostgreSQL in a single container with a persistent volume named kanban_data.
Run with: docker compose -f docker-compose.standalone.yml up -d`}
          </pre>
        </div>
      )}
    </div>
  );
}
