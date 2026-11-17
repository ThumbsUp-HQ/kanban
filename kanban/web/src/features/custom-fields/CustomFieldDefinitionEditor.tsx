// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import type { JSX } from 'react';
import React, { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { NotFoundView } from '../../app/routes';
import {
  createCustomField,
  deleteCustomField,
  fetchProjectCustomFields,
  qk,
  updateCustomField,
  type CustomFieldCreatePayload,
  type CustomFieldCredentialMode,
  type CustomFieldDefinition,
  type CustomFieldTargetScope,
  type CustomFieldTier,
  type CustomFieldUpdatePayload,
  type OutputFormatType,
} from './api';
import { EscalationApprovalPanel } from './EscalationApprovalPanel';
import './custom-fields.css';

export interface CustomFieldDefinitionEditorProps {
  projectKey: string;
  isAdmin?: boolean;
}

const DEFAULT_METADATA_BY_FORMAT: Record<OutputFormatType, Record<string, unknown>> = {
  text: { max_length: 280, prefix: '', monospace: false },
  number: { maximum_fraction_digits: 2, unit_suffix: '' },
  badge: { color_token: 'info', allowed_labels: ['Active', 'Verified'] },
  markdown_snippet: { max_chars: 2000 },
  url: { allowed_schemes: ['https'] },
  json_table: {
    columns: [
      { key: 'metric', label: 'Metric' },
      { key: 'value', label: 'Score' },
    ],
    max_rows: 50,
  },
  severity_pill: {},
};

/**
 * Admin Custom Field Definition Editor with Anti-Enumeration 404 gate (S3.4),
 * manifest_sha256 tracking, and tamper revocation warnings (S13.1, S13.2).
 */
export function CustomFieldDefinitionEditor({
  projectKey,
  isAdmin = true,
}: CustomFieldDefinitionEditorProps): JSX.Element {
  // Selected field for editing (null = creating new)
  const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null);

  // Form states
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [tier, setTier] = useState<CustomFieldTier>('wasm');
  const [outputFormat, setOutputFormat] = useState<OutputFormatType>('text');
  const [metadataText, setMetadataText] = useState(
    JSON.stringify(DEFAULT_METADATA_BY_FORMAT.text, null, 2),
  );
  const [scriptSource, setScriptSource] = useState('// Return field value\nreturn "Hello";');
  const [targetScope, setTargetScope] = useState<CustomFieldTargetScope>('PROJECT');
  const [credentialMode, setCredentialMode] =
    useState<CustomFieldCredentialMode>('INVOKING_USER');
  const [egressText, setEgressText] = useState('');
  const [isEnabled, setIsEnabled] = useState(true);

  // UI / Dialog states
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');
  const [copiedSha, setCopiedSha] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isTamperConfirmOpen, setIsTamperConfirmOpen] = useState(false);

  // Fetch definitions (all hooks declared unconditionally)
  const { data: definitions = [], refetch } = useQuery({
    queryKey: qk.customFields.project(projectKey),
    queryFn: () => fetchProjectCustomFields(projectKey),
    enabled: isAdmin && Boolean(projectKey),
  });

  const selectedField = useMemo(() => {
    return definitions.find((d) => d.id === selectedFieldId) ?? null;
  }, [definitions, selectedFieldId]);

  // Load field into editor form
  const handleSelectField = (field: CustomFieldDefinition) => {
    setSelectedFieldId(field.id);
    setName(field.name);
    setSlug(field.slug);
    setTier(field.tier);
    setOutputFormat(field.output_format);
    setMetadataText(JSON.stringify(field.output_format_metadata, null, 2));
    setScriptSource(field.script_source ?? '');
    setTargetScope(field.target_scope);
    setCredentialMode(field.credential_mode);
    setEgressText(field.egress_allowlist.join('\n'));
    setIsEnabled(field.is_enabled);
    setJsonError(null);
    setSubmitError(null);
  };

  const handleResetNew = () => {
    setSelectedFieldId(null);
    setName('');
    setSlug('');
    setTier('wasm');
    setOutputFormat('text');
    setMetadataText(JSON.stringify(DEFAULT_METADATA_BY_FORMAT.text, null, 2));
    setScriptSource('// Return field value\nreturn "Hello";');
    setTargetScope('PROJECT');
    setCredentialMode('INVOKING_USER');
    setEgressText('');
    setIsEnabled(true);
    setJsonError(null);
    setSubmitError(null);
  };

  // Format change helper
  const handleFormatChange = (fmt: OutputFormatType) => {
    setOutputFormat(fmt);
    setMetadataText(JSON.stringify(DEFAULT_METADATA_BY_FORMAT[fmt], null, 2));
  };

  // Copy SHA helper
  const handleCopySha = (sha: string) => {
    const nav = navigator as unknown as {
      clipboard?: { writeText: (text: string) => Promise<void> };
    };
    if (nav.clipboard) {
      void nav.clipboard.writeText(sha);
    }
    setCopiedSha(true);
    setTimeout(() => {
      setCopiedSha(false);
    }, 2000);
  };

  // Create mutation
  const createMutation = useMutation({
    mutationFn: async (payload: CustomFieldCreatePayload) => {
      return createCustomField(projectKey, payload);
    },
    onSuccess: (newField) => {
      setSubmitError(null);
      void refetch();
      handleSelectField(newField);
    },
    onError: (err: Error) => {
      setSubmitError(err.message);
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: async ({
      fieldId,
      payload,
    }: {
      fieldId: string;
      payload: CustomFieldUpdatePayload;
    }) => {
      return updateCustomField(projectKey, fieldId, payload);
    },
    onSuccess: (updatedField) => {
      setSubmitError(null);
      setIsTamperConfirmOpen(false);
      void refetch();
      handleSelectField(updatedField);
    },
    onError: (err: Error) => {
      setSubmitError(err.message);
      setIsTamperConfirmOpen(false);
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: async (fieldId: string) => {
      return deleteCustomField(projectKey, fieldId);
    },
    onSuccess: () => {
      handleResetNew();
      void refetch();
    },
  });

  // Form submission handler
  const handleSubmit = (e?: React.SyntheticEvent) => {
    if (e) e.preventDefault();
    setJsonError(null);
    setSubmitError(null);

    let parsedMeta: Record<string, unknown> = {};
    try {
      if (metadataText.trim()) {
        parsedMeta = JSON.parse(metadataText) as Record<string, unknown>;
      }
    } catch {
      setJsonError('Invalid JSON in format metadata');
      return;
    }

    const egressList = egressText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);

    // If updating an approved field with elevated scope or credential mode,
    // prompt confirmation of tamper auto-revocation (S13.2)
    if (
      selectedField?.approval_status === 'APPROVED' &&
      !isTamperConfirmOpen
    ) {
      const scriptChanged = scriptSource !== (selectedField.script_source ?? '');
      const metaChanged =
        JSON.stringify(parsedMeta) !==
        JSON.stringify(selectedField.output_format_metadata);
      if (scriptChanged || metaChanged) {
        setIsTamperConfirmOpen(true);
        return;
      }
    }

    if (selectedField) {
      updateMutation.mutate({
        fieldId: selectedField.id,
        payload: {
          name,
          tier,
          output_format: outputFormat,
          output_format_metadata: parsedMeta,
          script_source: scriptSource,
          target_scope: targetScope,
          credential_mode: credentialMode,
          egress_allowlist: egressList,
          is_enabled: isEnabled,
        },
      });
    } else {
      createMutation.mutate({
        slug,
        name,
        tier,
        output_format: outputFormat,
        output_format_metadata: parsedMeta,
        script_source: scriptSource,
        target_scope: targetScope,
        credential_mode: credentialMode,
        egress_allowlist: egressList,
        is_enabled: isEnabled,
      });
    }
  };

  // Anti-enumeration gate: Non-admin users receive uniform 404 (S3.4)
  if (!isAdmin) {
    return <NotFoundView />;
  }

  return (
    <div className="custom-fields-editor-layout" data-testid="custom-fields-editor-layout">
      {/* Sidebar: Existing Definitions List */}
      <aside className="custom-fields-editor-sidebar">
        <div className="custom-fields-editor-sidebar__header">
          <h3 className="custom-fields-editor-sidebar__title">Custom Fields</h3>
          <button
            type="button"
            className="custom-field-btn custom-field-btn--primary custom-field-btn--sm"
            onClick={handleResetNew}
            data-testid="create-new-field-btn"
          >
            + New Field
          </button>
        </div>

        <ul className="custom-fields-def-list" data-testid="custom-fields-list">
          {definitions.map((def: CustomFieldDefinition) => {
            const isSelected = def.id === selectedFieldId;
            return (
              <li
                key={def.id}
                className={`custom-fields-def-item ${isSelected ? 'custom-fields-def-item--selected' : ''}`}
                onClick={() => {
                  handleSelectField(def);
                }}
                data-testid={`field-item-${def.slug}`}
              >
                <div className="custom-fields-def-item__title">{def.name}</div>
                <div className="custom-fields-def-item__meta">
                  <span className="mono">{def.slug}</span>
                  <span className="custom-fields-def-item__format">{def.output_format}</span>
                </div>
              </li>
            );
          })}
        </ul>
      </aside>

      {/* Main Canvas: Form & Security Controls */}
      <main className="custom-fields-editor-main">
        <div className="custom-fields-editor-main__header">
          <h2 className="custom-fields-editor-main__title">
            {selectedField ? `Edit: ${selectedField.name}` : 'New Custom Field Definition'}
          </h2>

          {selectedField?.manifest_sha256 ? (
            <div className="custom-fields-sha-chip" data-testid="manifest-sha256-chip">
              <span className="custom-fields-sha-label">SHA256:</span>
              <span className="custom-fields-sha-val mono">
                {selectedField.manifest_sha256.slice(0, 16)}...
              </span>
              <button
                type="button"
                className="custom-field-copy-btn"
                onClick={() => {
                  handleCopySha(selectedField.manifest_sha256 ?? '');
                }}
                data-testid="copy-manifest-sha-btn"
              >
                {copiedSha ? 'Copied' : 'Copy'}
              </button>
            </div>
          ) : null}
        </div>

        {submitError && (
          <div className="custom-field-error-banner" role="alert">
            {submitError}
          </div>
        )}

        {/* Tab switcher: Basic vs Advanced */}
        <div className="custom-fields-tabs-bar" role="tablist">
          <button
            type="button"
            role="tab"
            id="custom-fields-basic-tab"
            aria-selected={activeTab === 'basic'}
            aria-controls="custom-fields-basic-panel"
            className={`custom-fields-tab-btn ${activeTab === 'basic' ? 'custom-fields-tab-btn--active' : ''}`}
            onClick={() => {
              setActiveTab('basic');
            }}
            data-testid="custom-fields-basic-tab"
          >
            Basic
          </button>
          <button
            type="button"
            role="tab"
            id="custom-fields-advanced-tab"
            aria-selected={activeTab === 'advanced'}
            aria-controls="custom-fields-advanced-panel"
            className={`custom-fields-tab-btn ${activeTab === 'advanced' ? 'custom-fields-tab-btn--active' : ''}`}
            onClick={() => {
              setActiveTab('advanced');
            }}
            data-testid="custom-fields-advanced-tab"
          >
            Advanced
          </button>
        </div>

        <form onSubmit={handleSubmit} className="custom-fields-editor-form">
          <div
            role="tabpanel"
            id="custom-fields-basic-panel"
            aria-labelledby="custom-fields-basic-tab"
            data-testid="custom-fields-basic-panel"
            hidden={activeTab !== 'basic'}
          >
            <div className="custom-fields-form-grid">
              {/* Field Name */}
              <div className="custom-field-form-group">
                <label htmlFor="field-name" className="custom-field-form-label">
                  Field Name
                </label>
                <input
                  id="field-name"
                  type="text"
                  className="custom-field-input"
                  maxLength={80}
                  required
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                  }}
                  data-testid="field-name-input"
                  placeholder="e.g. CVSS Score"
                />
              </div>

              {/* Field Slug */}
              <div className="custom-field-form-group">
                <label htmlFor="field-slug" className="custom-field-form-label">
                  Identifier Slug (a-z0-9-)
                </label>
                <input
                  id="field-slug"
                  type="text"
                  className="custom-field-input mono"
                  maxLength={63}
                  pattern="^[a-z0-9][a-z0-9-]{1,62}$"
                  required
                  disabled={Boolean(selectedField)}
                  value={slug}
                  onChange={(e) => {
                    setSlug(e.target.value.toLowerCase());
                  }}
                  data-testid="field-slug-input"
                  placeholder="cvss-score"
                />
              </div>

              {/* Output Format */}
              <div className="custom-field-form-group">
                <label htmlFor="output-format" className="custom-field-form-label">
                  Output Format
                </label>
                <select
                  id="output-format"
                  className="custom-field-select"
                  value={outputFormat}
                  onChange={(e) => {
                    handleFormatChange(e.target.value as OutputFormatType);
                  }}
                  data-testid="output-format-select"
                >
                  <option value="text">Text (max 280 chars)</option>
                  <option value="number">Number (Intl formatted)</option>
                  <option value="badge">Badge (Design Token Pill)</option>
                  <option value="markdown_snippet">Markdown Snippet (Sanitized)</option>
                  <option value="url">URL (Safe Hostname Anchor)</option>
                  <option value="json_table">JSON Table (Max 50x10)</option>
                  <option value="severity_pill">Severity Pill (low/med/high/crit)</option>
                </select>
              </div>
            </div>

            {/* Format Metadata JSON */}
            <div className="custom-field-form-group">
              <label htmlFor="format-metadata" className="custom-field-form-label">
                Format Configuration Metadata (JSON)
              </label>
              <textarea
                id="format-metadata"
                className="custom-field-textarea mono"
                rows={4}
                value={metadataText}
                onChange={(e) => {
                  setMetadataText(e.target.value);
                }}
                data-testid="format-metadata-textarea"
              />
              {jsonError && <span className="custom-field-input-error">{jsonError}</span>}
            </div>

            {/* Script Source Code */}
            <div className="custom-field-form-group">
              <label htmlFor="script-source" className="custom-field-form-label">
                Script Source Code (Sandboxed, never executed client-side)
              </label>
              <textarea
                id="script-source"
                className="custom-field-textarea mono custom-field-source-editor"
                rows={8}
                required
                value={scriptSource}
                onChange={(e) => {
                  setScriptSource(e.target.value);
                }}
                data-testid="script-source-textarea"
              />
            </div>

            {/* Is Enabled */}
            <div className="custom-field-form-group">
              <label className="custom-field-checkbox-label">
                <input
                  id="is-enabled"
                  type="checkbox"
                  checked={isEnabled}
                  onChange={(e) => {
                    setIsEnabled(e.target.checked);
                  }}
                  data-testid="is-enabled-checkbox"
                />
                Enabled
              </label>
            </div>
          </div>

          <div
            role="tabpanel"
            id="custom-fields-advanced-panel"
            aria-labelledby="custom-fields-advanced-tab"
            data-testid="custom-fields-advanced-panel"
            hidden={activeTab !== 'advanced'}
          >
            <div className="custom-fields-form-grid">
              {/* Execution Tier */}
              <div className="custom-field-form-group">
                <label htmlFor="execution-tier" className="custom-field-form-label">
                  Execution Tier (S13.3)
                </label>
                <select
                  id="execution-tier"
                  className="custom-field-select"
                  value={tier}
                  onChange={(e) => {
                    setTier(e.target.value as CustomFieldTier);
                  }}
                  data-testid="execution-tier-select"
                >
                  <option value="wasm">Tier A: Wasmtime (Sub-millisecond Wasm)</option>
                  <option value="nsjail">Tier B: nsjail (Linux Isolated Cgroup)</option>
                </select>
              </div>

              {/* Target Scope */}
              <div className="custom-field-form-group">
                <label htmlFor="target-scope" className="custom-field-form-label">
                  Token Scope (S13.2)
                </label>
                <select
                  id="target-scope"
                  className="custom-field-select"
                  value={targetScope}
                  onChange={(e) => {
                    setTargetScope(e.target.value as CustomFieldTargetScope);
                  }}
                  data-testid="target-scope-select"
                >
                  <option value="PROJECT">Project (Default)</option>
                  <option value="WORKSPACE">Workspace (Requires Workspace Admin)</option>
                  <option value="SERVER">Server (Requires Server Admin Dual-Control)</option>
                </select>
              </div>

              {/* Credential Mode */}
              <div className="custom-field-form-group">
                <label htmlFor="credential-mode" className="custom-field-form-label">
                  Credential Mode (S13.2)
                </label>
                <select
                  id="credential-mode"
                  className="custom-field-select"
                  value={credentialMode}
                  onChange={(e) => {
                    setCredentialMode(e.target.value as CustomFieldCredentialMode);
                  }}
                  data-testid="credential-mode-select"
                >
                  <option value="INVOKING_USER">Invoking User (Default)</option>
                  <option value="PROJECT_ADMIN_SP">Project Admin Service Principal (SP)</option>
                  <option value="SERVER_ADMIN_SP">Server Admin Service Principal (SP)</option>
                </select>
              </div>
            </div>
          </div>

          {/* Form Actions */}
          <div className="custom-fields-form-actions">
            {selectedField && (
              <button
                type="button"
                className="custom-field-btn custom-field-btn--danger"
                onClick={() => {
                  deleteMutation.mutate(selectedField.id);
                }}
                disabled={deleteMutation.isPending}
                data-testid="delete-field-btn"
              >
                Delete Field
              </button>
            )}

            <button
              type="submit"
              className="custom-field-btn custom-field-btn--primary"
              disabled={createMutation.isPending || updateMutation.isPending}
              data-testid="save-definition-btn"
            >
              {createMutation.isPending || updateMutation.isPending
                ? 'Saving...'
                : selectedField
                  ? 'Save Changes'
                  : 'Create Definition'}
            </button>
          </div>
        </form>

        {/* Escalation & Security Approvals Panel */}
        {selectedField && (
          <EscalationApprovalPanel
            field={selectedField}
            callerTier="WORKSPACE_ADMIN"
            onApproved={() => {
              void refetch();
            }}
          />
        )}
      </main>

      {/* Tamper Confirmation Dialog (S13.2) */}
      {isTamperConfirmOpen && (
        <div
          className="custom-field-modal-overlay"
          role="dialog"
          aria-modal="true"
          data-testid="tamper-confirm-dialog"
        >
          <div className="custom-field-modal">
            <h4 className="custom-field-modal-title">Confirm Manifest Modification</h4>
            <p
              className="custom-field-modal-warning-text"
              data-testid="tamper-warning-literal"
            >
              Saving changes manifest_sha256 and immediately revokes the current approval.
            </p>
            <div className="custom-field-modal-actions">
              <button
                type="button"
                className="custom-field-btn custom-field-btn--secondary"
                onClick={() => {
                  setIsTamperConfirmOpen(false);
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="custom-field-btn custom-field-btn--danger"
                onClick={() => {
                  handleSubmit();
                }}
                data-testid="confirm-tamper-save-btn"
              >
                Confirm & Revoke
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
