// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useRef, type JSX } from 'react';
import { Link } from 'react-router';
import {
  submitPlaneImport,
  submitImport,
  type ImportDiffReport,
  type ImportSource,
} from './planeImportApi';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import './PlaneImportStudio.css';

export interface EntityCounts {
  projects: number;
  states: number;
  issues: number;
  cycles: number;
  modules: number;
  comments: number;
  members: number;
}

export function extractEntityCounts(bundle: Record<string, unknown> | null): EntityCounts | null {
  if (!bundle) return null;
  return {
    projects: Array.isArray(bundle.projects) ? bundle.projects.length : 0,
    states: Array.isArray(bundle.states) ? bundle.states.length : 0,
    issues: Array.isArray(bundle.issues) ? bundle.issues.length : 0,
    cycles: Array.isArray(bundle.cycles) ? bundle.cycles.length : 0,
    modules: Array.isArray(bundle.modules) ? bundle.modules.length : 0,
    comments: Array.isArray(bundle.issue_comments) ? bundle.issue_comments.length : 0,
    members: Array.isArray(bundle.members) ? bundle.members.length : 0,
  };
}

export function PlaneImportStudio(): JSX.Element {
  const [source, setSource] = useState<ImportSource>('plane');
  const [projectKey, setProjectKey] = useState<string>('');
  const [inputMode, setInputMode] = useState<'upload' | 'paste'>('upload');
  const [rawJson, setRawJson] = useState<string>('');
  const [bundleData, setBundleData] = useState<Record<string, unknown> | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [workspaceSlug, setWorkspaceSlug] = useState<string>('');

  const [stage, setStage] = useState<'input' | 'preview' | 'executing' | 'done'>('input');
  const [diffReport, setDiffReport] = useState<ImportDiffReport | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const parseAndSetBundle = (jsonStr: string, name?: string): boolean => {
    setError(null);
    try {
      const parsed = JSON.parse(jsonStr) as unknown;
      if (source === 'plane') {
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          throw new Error('Plane export bundle must be a JSON object with entity arrays.');
        }
      }
      setBundleData(parsed as Record<string, unknown>);
      if (name) {
        setFileName(name);
      }
      return true;
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(`Invalid JSON: ${err.message}`);
      } else {
        setError('Failed to parse JSON export bundle.');
      }
      setBundleData(null);
      return false;
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      parseAndSetBundle(content, file.name);
    };
    reader.onerror = () => {
      setError('Failed to read uploaded file.');
    };
    reader.readAsText(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      parseAndSetBundle(content, file.name);
    };
    reader.onerror = () => {
      setError('Failed to read dropped file.');
    };
    reader.readAsText(file);
  };

  const handlePasteChange = (e: React.ChangeEvent<HTMLTextAreaElement>): void => {
    const val = e.target.value;
    setRawJson(val);
    if (!val.trim()) {
      setBundleData(null);
      setError(null);
      return;
    }
    parseAndSetBundle(val);
  };

  const getSourceName = (s: ImportSource): string => {
    switch (s) {
      case 'plane':
        return 'Plane';
      case 'jira':
        return 'Jira';
      case 'github':
        return 'GitHub';
      case 'linear':
        return 'Linear';
    }
  };

  const handleRunDryRun = async (): Promise<void> => {
    const sourceName = getSourceName(source);
    if (!bundleData) {
      setError(`Please upload or paste a valid ${sourceName} JSON export bundle.`);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const payload = {
        bundle_data: bundleData,
        project_key: projectKey.trim() || undefined,
        dry_run: true,
        workspace_slug: workspaceSlug.trim() || undefined,
      };
      const report =
        source === 'plane'
          ? await submitPlaneImport(payload)
          : await submitImport(source, payload);
      setDiffReport(report);
      setStage('preview');
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(`Failed to execute ${sourceName} dry-run simulation.`);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteImport = async (): Promise<void> => {
    if (!bundleData) return;
    const sourceName = getSourceName(source);
    setLoading(true);
    setStage('executing');
    setError(null);
    try {
      const payload = {
        bundle_data: bundleData,
        project_key: projectKey.trim() || undefined,
        dry_run: false,
        workspace_slug: workspaceSlug.trim() || undefined,
      };
      const report =
        source === 'plane'
          ? await submitPlaneImport(payload)
          : await submitImport(source, payload);
      setDiffReport(report);
      setStage('done');
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(`${sourceName} live import execution failed.`);
      }
      setStage('preview');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = (): void => {
    setStage('input');
    setDiffReport(null);
    setError(null);
  };

  const entityCounts = extractEntityCounts(bundleData);

  return (
    <div className="kb-plane-import-container" data-testid="plane-import-studio">
      <header className="kb-plane-import-header">
        <div>
          <h1 className="kb-plane-import-title" data-testid="studio-title">
            {source === 'plane' ? 'Plane' : source === 'jira' ? 'Jira' : source === 'github' ? 'GitHub' : 'Linear'} Migration Import Studio
          </h1>
          <p className="kb-plane-import-subtitle">
            Upload or paste {source === 'plane' ? 'Plane' : source.toUpperCase()} export bundles, inspect entity counts, simulate state
            mappings and idempotency diffs in dry-run, and execute live workspace migrations.
          </p>
        </div>
      </header>

      <nav className="kb-mcp-admin-subnav" aria-label="Admin MCP and Governance Navigation">
        <Link to="/admin/mcp" className="kb-mcp-admin-subnav-link" data-testid="tab-admin-mcp">
          Bot API Keys
        </Link>
        <Link to="/admin/oauth" className="kb-mcp-admin-subnav-link" data-testid="tab-admin-oauth">
          OAuth 2.1 Clients
        </Link>
        <Link
          to="/admin/imports"
          className="kb-mcp-admin-subnav-link kb-mcp-admin-subnav-active"
          data-testid="tab-admin-imports"
        >
          Migration Studio
        </Link>
      </nav>

      <div className="kb-plane-mode-row" style={{ margin: '1rem 0' }} data-testid="source-selector-bar">
        <button
          type="button"
          className={`kb-plane-mode-btn ${source === 'plane' ? 'kb-plane-mode-active' : ''}`}
          data-testid="source-plane-btn"
          onClick={() => {
            setSource('plane');
            setBundleData(null);
            setError(null);
          }}
        >
          Plane
        </button>
        <button
          type="button"
          className={`kb-plane-mode-btn ${source === 'jira' ? 'kb-plane-mode-active' : ''}`}
          data-testid="source-jira-btn"
          onClick={() => {
            setSource('jira');
            setBundleData(null);
            setError(null);
          }}
        >
          Jira
        </button>
        <button
          type="button"
          className={`kb-plane-mode-btn ${source === 'github' ? 'kb-plane-mode-active' : ''}`}
          data-testid="source-github-btn"
          onClick={() => {
            setSource('github');
            setBundleData(null);
            setError(null);
          }}
        >
          GitHub
        </button>
        <button
          type="button"
          className={`kb-plane-mode-btn ${source === 'linear' ? 'kb-plane-mode-active' : ''}`}
          data-testid="source-linear-btn"
          onClick={() => {
            setSource('linear');
            setBundleData(null);
            setError(null);
          }}
        >
          Linear
        </button>
      </div>

      {error !== null && (
        <div className="kb-plane-alert kb-plane-alert-error" role="alert" data-testid="error-alert">
          {error}
        </div>
      )}

      {/* Stage 0: Input Bundle Selection */}
      {stage === 'input' && (
        <section className="kb-plane-section" data-testid="import-input-section">
          <h2 className="kb-plane-section-title">
            <EmojiHint kind="rawMarkdown" /> Step 1: Select {source === 'plane' ? 'Plane' : source === 'jira' ? 'Jira' : source === 'github' ? 'GitHub' : 'Linear'} Export Bundle
          </h2>

          <div className="kb-plane-mode-row">
            <button
              type="button"
              className={`kb-plane-mode-btn ${inputMode === 'upload' ? 'kb-plane-mode-active' : ''}`}
              data-testid="mode-upload-btn"
              onClick={() => {
                setInputMode('upload');
              }}
            >
              Upload Export JSON File
            </button>
            <button
              type="button"
              className={`kb-plane-mode-btn ${inputMode === 'paste' ? 'kb-plane-mode-active' : ''}`}
              data-testid="mode-paste-btn"
              onClick={() => {
                setInputMode('paste');
              }}
            >
              Paste Raw JSON
            </button>
          </div>

          {inputMode === 'upload' ? (
            <div
              className={`kb-plane-dropzone ${isDragOver ? 'kb-plane-dropzone-active' : ''}`}
              data-testid="dropzone-area"
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragOver(true);
              }}
              onDragLeave={() => {
                setIsDragOver(false);
              }}
              onDrop={handleDrop}
              onClick={() => {
                fileInputRef.current?.click();
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".json,application/json"
                className="kb-plane-file-input"
                data-testid="file-input"
                onChange={handleFileChange}
              />
              <div className="kb-plane-dropzone-text">
                {fileName ? (
                  <strong>Loaded: {fileName}</strong>
                ) : (
                  'Drag and drop Plane export JSON file here, or click to browse'
                )}
              </div>
              <div className="kb-plane-dropzone-hint">
                Supports single-file Plane JSON export bundles containing projects, states, issues,
                and cycles.
              </div>
            </div>
          ) : (
            <div>
              <textarea
                className="kb-plane-textarea"
                data-testid="paste-textarea"
                placeholder='Paste raw Plane export JSON here... e.g. { "projects": [...], "issues": [...] }'
                value={rawJson}
                onChange={handlePasteChange}
              />
            </div>
          )}

          {/* Parsed Entity Metrics Preview */}
          {entityCounts !== null && (
            <div data-testid="entity-metrics-preview">
              <h3 className="kb-plane-section-title" style={{ marginTop: 24 }}>
                Detected Bundle Entities
              </h3>
              <div className="kb-plane-stats-grid">
                <div className="kb-plane-stat-card" data-testid="stat-projects">
                  <div className="kb-plane-stat-val">{entityCounts.projects}</div>
                  <div className="kb-plane-stat-label">Projects</div>
                </div>
                <div className="kb-plane-stat-card" data-testid="stat-states">
                  <div className="kb-plane-stat-val">{entityCounts.states}</div>
                  <div className="kb-plane-stat-label">States</div>
                </div>
                <div className="kb-plane-stat-card" data-testid="stat-issues">
                  <div className="kb-plane-stat-val">{entityCounts.issues}</div>
                  <div className="kb-plane-stat-label">Issues</div>
                </div>
                <div className="kb-plane-stat-card" data-testid="stat-cycles">
                  <div className="kb-plane-stat-val">{entityCounts.cycles}</div>
                  <div className="kb-plane-stat-label">Cycles</div>
                </div>
                <div className="kb-plane-stat-card" data-testid="stat-modules">
                  <div className="kb-plane-stat-val">{entityCounts.modules}</div>
                  <div className="kb-plane-stat-label">Modules</div>
                </div>
                <div className="kb-plane-stat-card" data-testid="stat-comments">
                  <div className="kb-plane-stat-val">{entityCounts.comments}</div>
                  <div className="kb-plane-stat-label">Comments</div>
                </div>
                <div className="kb-plane-stat-card" data-testid="stat-members">
                  <div className="kb-plane-stat-val">{entityCounts.members}</div>
                  <div className="kb-plane-stat-label">Members</div>
                </div>
              </div>
            </div>
          )}

          <div style={{ marginTop: 20 }}>
            <label
              htmlFor="target-ws-slug"
              style={{
                display: 'block',
                fontSize: '0.825rem',
                fontWeight: 600,
                marginBottom: 6,
                color: 'var(--kb-color-text-secondary)',
              }}
            >
              Target Workspace Slug (Optional, defaults to active workspace):
            </label>
            <input
              id="target-ws-slug"
              type="text"
              className="kb-plane-textarea"
              style={{ minHeight: 40, height: 40, width: '100%', maxWidth: 360 }}
              data-testid="target-ws-slug-input"
              placeholder="e.g. my-workspace"
              value={workspaceSlug}
              onChange={(e) => {
                setWorkspaceSlug(e.target.value);
              }}
            />
          </div>

          {source !== 'plane' && (
            <div style={{ marginTop: 14 }}>
              <label
                htmlFor="target-proj-key"
                style={{
                  display: 'block',
                  fontSize: '0.825rem',
                  fontWeight: 600,
                  marginBottom: 6,
                  color: 'var(--kb-color-text-secondary)',
                }}
              >
                Target Project Key (Optional, default {source === 'jira' ? 'JIRA' : source === 'github' ? 'GH' : 'LIN'}):
              </label>
              <input
                id="target-proj-key"
                type="text"
                className="kb-plane-textarea"
                style={{ minHeight: 40, height: 40, width: '100%', maxWidth: 360 }}
                data-testid="target-project-key-input"
                placeholder={source === 'jira' ? 'JIRA' : source === 'github' ? 'GH' : 'LIN'}
                value={projectKey}
                onChange={(e) => {
                  setProjectKey(e.target.value);
                }}
              />
            </div>
          )}

          <div className="kb-plane-btn-row">
            <button
              type="button"
              className="kb-plane-btn kb-plane-btn-primary"
              data-testid="run-dry-run-btn"
              disabled={loading}
              onClick={() => {
                void handleRunDryRun();
              }}
            >
              {loading ? 'Simulating Dry-Run...' : 'Stage 1: Preview Dry-Run Diff'}
            </button>
          </div>
        </section>
      )}

      {/* Stage 1: Dry-Run Preview */}
      {stage === 'preview' && diffReport !== null && (
        <section className="kb-plane-section" data-testid="dry-run-preview-section">
          <h2 className="kb-plane-section-title">
            <EmojiHint kind="sparkle" /> Stage 1: Dry-Run Simulation Preview
          </h2>
          <p className="kb-plane-import-subtitle">
            Simulation completed with zero database mutations. Review the diff impact and warnings
            below before executing live transaction migration.
          </p>

          <div className="kb-plane-diff-grid">
            <div className="kb-plane-diff-card kb-plane-diff-card-create" data-testid="diff-to-create">
              <div className="kb-plane-diff-val">{diffReport.to_create}</div>
              <div className="kb-plane-diff-label">Issues To Create</div>
            </div>
            <div className="kb-plane-diff-card kb-plane-diff-card-update" data-testid="diff-to-update">
              <div className="kb-plane-diff-val">{diffReport.to_update}</div>
              <div className="kb-plane-diff-label">Issues To Update</div>
            </div>
            <div
              className="kb-plane-diff-card kb-plane-diff-card-unchanged"
              data-testid="diff-unchanged"
            >
              <div className="kb-plane-diff-val">{diffReport.unchanged}</div>
              <div className="kb-plane-diff-label">Issues Unchanged</div>
            </div>
            <div
              className="kb-plane-diff-card kb-plane-diff-card-sequence"
              data-testid="diff-sequence"
            >
              <div className="kb-plane-diff-val">{diffReport.sequence_high_water_mark}</div>
              <div className="kb-plane-diff-label">Sequence Watermark</div>
            </div>
          </div>

          {diffReport.warnings.length > 0 && (
            <div className="kb-plane-warnings-box" data-testid="warnings-box">
              <div className="kb-plane-warnings-title">
                Warnings ({diffReport.warnings.length}):
              </div>
              <ul className="kb-plane-warnings-list">
                {diffReport.warnings.map((warn, i) => (
                  <li key={i}>{warn}</li>
                ))}
              </ul>
            </div>
          )}

          {diffReport.unmapped_members.length > 0 && (
            <div className="kb-plane-warnings-box" data-testid="unmapped-members-box">
              <div className="kb-plane-warnings-title">
                Unmapped Member IDs ({diffReport.unmapped_members.length}):
              </div>
              <ul className="kb-plane-warnings-list">
                {diffReport.unmapped_members.map((mem, i) => (
                  <li key={i}>{mem}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="kb-plane-btn-row">
            <button
              type="button"
              className="kb-plane-btn kb-plane-btn-secondary"
              data-testid="back-to-input-btn"
              onClick={handleReset}
            >
              Back to Input
            </button>
            <button
              type="button"
              className="kb-plane-btn kb-plane-btn-execute"
              data-testid="execute-import-btn"
              disabled={loading}
              onClick={() => {
                void handleExecuteImport();
              }}
            >
              Stage 2: Execute Live Import
            </button>
          </div>
        </section>
      )}

      {/* Stage 2: Executing Progress */}
      {stage === 'executing' && (
        <section className="kb-plane-section" data-testid="executing-section">
          <h2 className="kb-plane-section-title">
            <EmojiHint kind="sparkle" /> Executing Live Migration...
          </h2>
          <p className="kb-plane-import-subtitle">
            Applying Plane entities, mapping states, creating object links, and updating sequence
            counters inside an isolated transaction. Please wait.
          </p>
          <div className="kb-plane-progress-wrap" data-testid="progress-bar">
            <div className="kb-plane-progress-bar" />
          </div>
        </section>
      )}

      {/* Stage 3: Done Summary */}
      {stage === 'done' && diffReport !== null && (
        <section className="kb-plane-section" data-testid="import-done-section">
          <div className="kb-plane-alert kb-plane-alert-success" role="status" data-testid="success-banner">
            Plane export migration completed successfully!
          </div>

          <h2 className="kb-plane-section-title">
            <EmojiHint kind="gateApproved" /> Migration Execution Summary
          </h2>

          <div className="kb-plane-diff-grid">
            <div className="kb-plane-diff-card kb-plane-diff-card-create">
              <div className="kb-plane-diff-val">{diffReport.to_create}</div>
              <div className="kb-plane-diff-label">Created Issues</div>
            </div>
            <div className="kb-plane-diff-card kb-plane-diff-card-update">
              <div className="kb-plane-diff-val">{diffReport.to_update}</div>
              <div className="kb-plane-diff-label">Updated Issues</div>
            </div>
            <div className="kb-plane-diff-card kb-plane-diff-card-unchanged">
              <div className="kb-plane-diff-val">{diffReport.unchanged}</div>
              <div className="kb-plane-diff-label">Unchanged Issues</div>
            </div>
            <div className="kb-plane-diff-card kb-plane-diff-card-sequence">
              <div className="kb-plane-diff-val">{diffReport.sequence_high_water_mark}</div>
              <div className="kb-plane-diff-label">Sequence Watermark</div>
            </div>
          </div>

          <div className="kb-plane-btn-row">
            <button
              type="button"
              className="kb-plane-btn kb-plane-btn-primary"
              data-testid="import-another-btn"
              onClick={handleReset}
            >
              Import Another Bundle
            </button>
            <Link
              to="/admin/mcp"
              className="kb-plane-btn kb-plane-btn-secondary"
              data-testid="return-admin-btn"
            >
              Return to MCP & Governance
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}
