/**
 * Compose Export & Production Promotion Tab (KB-P3-52, S2.4).
 * Provides 1-click docker-compose.yml download, copyable .env.example, and 4-step migration runbook.
 */

import React, { useCallback, useEffect, useState, type JSX } from 'react';

export interface ComposeExportData {
  readonly filename: string;
  readonly compose_yaml: string;
  readonly env_template: string;
  readonly migration_steps_markdown: string;
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

  const fetchExportData = useCallback(async (): Promise<ComposeExportData | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/admin/standalone/compose-export', {
        method: 'GET',
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      if (!res.ok) {
        throw new Error(`Failed to load compose export: ${String(res.status)}`);
      }
      const json = (await res.json()) as ComposeExportData;
      setData(json);
      return json;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load export data';
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
      exportData ??= await fetchExportData();
      if (!exportData) {
        return;
      }
      const blob = new Blob([exportData.compose_yaml], {
        type: 'application/x-yaml;charset=utf-8',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = exportData.filename || 'docker-compose.yml';
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
      exportData ??= await fetchExportData();
      if (!exportData) {
        return;
      }
      await navigator.clipboard.writeText(exportData.env_template);
      setCopiedEnv(true);
      setTimeout(() => {
        setCopiedEnv(false);
      }, 2000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to copy';
      setError(msg);
    }
  };

  return (
    <div className="standalone-panel__compose-container">
      {error && (
        <div role="alert" className="standalone-panel__error">
          {error}
        </div>
      )}

      <div className="standalone-panel__btn-group">
        <button
          type="button"
          onClick={() => {
            void handleDownload();
          }}
          disabled={isLoading || isDownloading}
          className="standalone-panel__btn standalone-panel__btn--primary"
        >
          {isDownloading ? 'Downloading...' : 'Download docker-compose.yml'}
        </button>

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
      </div>

      <div className="standalone-panel__checklist-card">
        <h4 className="standalone-panel__checklist-title">
          PostgreSQL 16 Promotion Runbook:
        </h4>
        <pre className="standalone-panel__checklist-pre">
{`1. Generate secrets
2. Download encrypted backup (.kbkp)
3. docker compose up -d postgres
4. kanban-ctl restore / pg_restore into external PostgreSQL 16`}
        </pre>
      </div>
    </div>
  );
}
