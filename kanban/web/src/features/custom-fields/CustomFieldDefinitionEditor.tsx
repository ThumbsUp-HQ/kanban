// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import type { JSX } from 'react';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSystemStatus } from '../../app/useSystemStatus';
import { NotFoundView } from '../../app/routes';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { useAal2DirtyKeepalive } from '../../components/help/WebSudoModalHost';
import { FlavorDecisionMatrix } from './FlavorDecisionMatrix';
import { PresetGallery } from './PresetGallery';
import type { CustomFieldPreset } from './presets';
import {
  createCustomField,
  deleteCustomField,
  fetchProjectCustomFields,
  qk,
  testExecuteCustomField,
  updateCustomField,
  type CustomFieldCreatePayload,
  type CustomFieldCredentialMode,
  type CustomFieldDefinition,
  type CustomFieldTargetScope,
  type CustomFieldTestExecuteResult,
  type CustomFieldTier,
  type CustomFieldUpdatePayload,
  type FieldFlavor,
  type OutputFormatType,
} from './api';
import { CustomFieldValue } from './CustomFieldValue';
import { EscalationApprovalPanel } from './EscalationApprovalPanel';
import { AdvancedSection } from '../../ui/AdvancedSection';
import { safeJsonParse } from '../../utils/safeJson';
import './custom-fields.css';

export interface CustomFieldDefinitionEditorProps {
  projectKey: string;
  isAdmin?: boolean;
}

const DEFAULT_WASM_BASE64 =
  'AGFzbQEAAAABEQNgAn9/AGABfwF/YAJ/fwF/AhEBA2VudglrYl9vdXRwdXQAAAMDAgECBQMBAAEHHgMGbWVtb3J5AgAIa2JfYWxsb2MAAQZrYl9ydW4AAgoTAgUAQYAQCwsAQYAIQTQQAEEACws7AQBBgAgLNHsibGV2ZWwiOiAiaGlnaCIsICJzY29yZSI6IDguOCwgImxhYmVsIjogIjguOCBIaWdoIn0AKQRuYW1lAQwBAAlrYl9vdXRwdXQCFAIBAQADbGVuAgIAA3B0cgEDbGVu';

const STARTER_TEMPLATES: Record<FieldFlavor, Record<OutputFormatType, string>> = {
  scalar: {
    text: 'scalar: "Verified"',
    number: 'scalar: 42',
    badge: 'scalar: "Active"',
    markdown_snippet: 'scalar: "**Status:** Verified\\n*System is operating normally.*"',
    url: 'scalar: "https://kanban.example.com"',
    json_table:
      'scalar: [{"metric": "Uptime", "value": "99.9%"}, {"metric": "Latency", "value": "12ms"}]',
    severity_pill: 'scalar: {"level": "high", "score": 8.8, "label": "8.8 High"}',
  },
  formula: {
    text: 'formula: issue.key + " - " + issue.summary',
    number: 'formula: issue.summary ? issue.summary.length : 0',
    badge: 'formula: issue.state === "DONE" ? "Completed" : "In Progress"',
    markdown_snippet: 'formula: "### " + issue.key + "\\n" + issue.summary',
    url: 'formula: "https://kanban.example.com/issues/" + issue.key',
    json_table:
      'formula: [{"metric": "Key", "value": issue.key}, {"metric": "State", "value": issue.state}]',
    severity_pill:
      'formula: {"level": issue.priority === "URGENT" ? "critical" : "medium", "score": issue.priority === "URGENT" ? 9.0 : 5.0, "label": issue.priority || "Medium"}',
  },
  wasm: {
    text: `// echo_cvss.wasm - WebAssembly Tier A Module (Base64)\n${DEFAULT_WASM_BASE64}`,
    number: `// echo_cvss.wasm - WebAssembly Tier A Module (Base64)\n${DEFAULT_WASM_BASE64}`,
    badge: `// echo_cvss.wasm - WebAssembly Tier A Module (Base64)\n${DEFAULT_WASM_BASE64}`,
    markdown_snippet: `// echo_cvss.wasm - WebAssembly Tier A Module (Base64)\n${DEFAULT_WASM_BASE64}`,
    url: `// echo_cvss.wasm - WebAssembly Tier A Module (Base64)\n${DEFAULT_WASM_BASE64}`,
    json_table: `// echo_cvss.wasm - WebAssembly Tier A Module (Base64)\n${DEFAULT_WASM_BASE64}`,
    severity_pill: `// echo_cvss.wasm - WebAssembly Tier A Module (Base64)\n${DEFAULT_WASM_BASE64}`,
  },
  nsjail: {
    text: `# Tier B nsjail container Python script (isolated Linux namespaces)
import json
import sys

def main():
    try:
        data = json.loads(sys.stdin.read())
        issue = data.get("issue", {})
        output = f"{issue.get('key', 'UNKNOWN')}: Verified"
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()`,
    number: `# Tier B nsjail container Python script (isolated Linux namespaces)
import json
import sys

def main():
    try:
        data = json.loads(sys.stdin.read())
        issue = data.get("issue", {})
        print(json.dumps(len(issue.get("summary", ""))))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()`,
    badge: `# Tier B nsjail container Python script (isolated Linux namespaces)
import json
import sys

def main():
    try:
        data = json.loads(sys.stdin.read())
        issue = data.get("issue", {})
        output = "Active" if issue.get("state") == "DONE" else "Pending"
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()`,
    markdown_snippet: `# Tier B nsjail container Python script (isolated Linux namespaces)
import json
import sys

def main():
    try:
        data = json.loads(sys.stdin.read())
        issue = data.get("issue", {})
        output = f"**Status:** Verified\\n*Key: {issue.get('key', '')}*"
        print(json.dumps(output))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()`,
    url: `# Tier B nsjail container Python script (isolated Linux namespaces)
import json
import sys

def main():
    try:
        data = json.loads(sys.stdin.read())
        issue = data.get("issue", {})
        print(json.dumps(f"https://kanban.example.com/issues/{issue.get('key', '')}"))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()`,
    json_table: `# Tier B nsjail container Python script (isolated Linux namespaces)
import json
import sys

def main():
    try:
        data = json.loads(sys.stdin.read())
        issue = data.get("issue", {})
        table = [{"metric": "Key", "value": issue.get("key", "")}]
        print(json.dumps(table))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()`,
    severity_pill: `# Tier B nsjail container Python script (isolated Linux namespaces)
import json
import sys

def main():
    try:
        data = json.loads(sys.stdin.read())
        issue = data.get("issue", {})
        pill = {"level": "high", "score": 8.8, "label": "8.8 High"}
        print(json.dumps(pill))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()`,
  },
};

function detectFlavor(field: CustomFieldDefinition): FieldFlavor {
  const src = field.script_source?.trim() ?? '';
  if (src.startsWith('scalar:')) return 'scalar';
  if (src.startsWith('formula:')) return 'formula';
  if (field.tier === 'nsjail') return 'nsjail';
  return 'wasm';
}

export function normalizeScriptSource(flavor: FieldFlavor, source: string): string {
  const trimmed = source.trim();
  if (!trimmed) {
    return source;
  }
  if (flavor === 'formula') {
    if (!trimmed.startsWith('formula:') && !trimmed.startsWith('return ')) {
      return `formula: ${trimmed}`;
    }
    return trimmed;
  }
  if (flavor === 'scalar') {
    if (!trimmed.startsWith('scalar:')) {
      return `scalar: ${trimmed}`;
    }
    return trimmed;
  }
  return source;
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
  const queryClient = useQueryClient();
  const { data: systemStatus } = useSystemStatus();
  const isTierBAvailable = systemStatus?.tier_b_sandbox_available !== false;

  // Selected field for editing (null = creating new)
  const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null);

  // Form states
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [flavor, setFlavor] = useState<FieldFlavor>('scalar');
  const [tier, setTier] = useState<CustomFieldTier>('wasm');
  const [outputFormat, setOutputFormat] = useState<OutputFormatType>('text');
  const [metadataText, setMetadataText] = useState(
    JSON.stringify(DEFAULT_METADATA_BY_FORMAT.text, null, 2),
  );
  const [scriptSource, setScriptSource] = useState(STARTER_TEMPLATES.scalar.text);
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
  const [appliedPresetName, setAppliedPresetName] = useState<string | null>(null);

  const snapshotRef = useRef<{
    name: string;
    slug: string;
    flavor: FieldFlavor;
    tier: CustomFieldTier;
    outputFormat: OutputFormatType;
    metadataText: string;
    scriptSource: string;
    targetScope: CustomFieldTargetScope;
    credentialMode: CustomFieldCredentialMode;
    egressText: string;
  } | null>(null);

  // Test execute states
  const [testIssueKey, setTestIssueKey] = useState('');
  const [testResult, setTestResult] = useState<CustomFieldTestExecuteResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [isTesting, setIsTesting] = useState(false);

  // Fetch definitions (all hooks declared unconditionally)
  const { data: definitions = [], refetch } = useQuery({
    queryKey: qk.customFields.project(projectKey),
    queryFn: () => fetchProjectCustomFields(projectKey),
    enabled: isAdmin && Boolean(projectKey),
  });

  const selectedField = useMemo(() => {
    return definitions.find((d) => d.id === selectedFieldId) ?? null;
  }, [definitions, selectedFieldId]);

  const manifestSha = selectedField?.manifest_sha256;

  const isDirty = useMemo(() => {
    if (selectedField) {
      const origMeta = JSON.stringify(selectedField.output_format_metadata, null, 2);
      const origEgress = selectedField.egress_allowlist.join('\n');
      return (
        name !== selectedField.name ||
        tier !== selectedField.tier ||
        outputFormat !== selectedField.output_format ||
        metadataText !== origMeta ||
        scriptSource !== (selectedField.script_source ?? '') ||
        targetScope !== selectedField.target_scope ||
        credentialMode !== selectedField.credential_mode ||
        egressText !== origEgress ||
        isEnabled !== selectedField.is_enabled
      );
    }
    const defaultMeta = JSON.stringify(DEFAULT_METADATA_BY_FORMAT.text, null, 2);
    return (
      name !== '' ||
      slug !== '' ||
      scriptSource !== STARTER_TEMPLATES.scalar.text ||
      egressText !== '' ||
      metadataText !== defaultMeta ||
      targetScope !== 'PROJECT' ||
      credentialMode !== 'INVOKING_USER'
    );
  }, [
    selectedField,
    name,
    slug,
    tier,
    outputFormat,
    metadataText,
    scriptSource,
    targetScope,
    credentialMode,
    egressText,
    isEnabled,
  ]);

  useAal2DirtyKeepalive(isDirty);

  const [showRawMetadata, setShowRawMetadata] = useState(false);

  const parsedMetadata = useMemo<Record<string, unknown>>(() => {
    try {
      const obj: unknown = JSON.parse(metadataText);
      return typeof obj === 'object' && obj !== null ? (obj as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }, [metadataText]);

  const updateMetadataField = (key: string, value: unknown) => {
    const current = { ...parsedMetadata, [key]: value };
    setMetadataText(JSON.stringify(current, null, 2));
    setJsonError(null);
  };

  const [pendingSha, setPendingSha] = useState<string>('sha256-pending-recompute');

  useEffect(() => {
    let isMounted = true;
    const computeSha = async () => {
      try {
        const payload = `${normalizeScriptSource(flavor, scriptSource)}:${metadataText}:${egressText}`;
        if (
          typeof crypto !== 'undefined' &&
          'subtle' in crypto &&
          typeof crypto.subtle.digest === 'function'
        ) {
          const msgBuffer = new TextEncoder().encode(payload);
          const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
          const hashArray = Array.from(new Uint8Array(hashBuffer));
          const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
          if (isMounted) setPendingSha(hashHex);
        /* v8 ignore start */
        } else {
          let h = 0;
          for (let i = 0; i < payload.length; i++) {
            h = (Math.imul(31, h) + payload.charCodeAt(i)) | 0;
          }
          if (isMounted) setPendingSha(`sha256-sim-${Math.abs(h).toString(16).padStart(8, '0')}`);
        }
      } catch {
        if (isMounted) setPendingSha('sha256-pending-recompute');
      }
      /* v8 ignore stop */
    };
    void computeSha();
    return () => {
      isMounted = false;
    };
  }, [flavor, scriptSource, metadataText, egressText]);

  const handleApplyPreset = (preset: CustomFieldPreset) => {
    snapshotRef.current = {
      name,
      slug,
      flavor,
      tier,
      outputFormat,
      metadataText,
      scriptSource,
      targetScope,
      credentialMode,
      egressText,
    };
    setAppliedPresetName(preset.name);
    setName(preset.name);
    /* v8 ignore next 3 */
    if (!selectedField) {
      setSlug(preset.slug);
    }
    setFlavor(preset.flavor);
    setTier(preset.tier);
    setOutputFormat(preset.outputFormat);
    setMetadataText(preset.metadataText);
    setScriptSource(preset.scriptSource);
    setTargetScope(preset.targetScope);
    setCredentialMode(preset.credentialMode);
    setEgressText(preset.egressAllowlist.join('\n'));
    setJsonError(null);
  };

  const handleUndoPreset = () => {
    /* v8 ignore next */
    if (snapshotRef.current) {
      const snap = snapshotRef.current;
      setName(snap.name);
      /* v8 ignore next 3 */
      if (!selectedField) {
        setSlug(snap.slug);
      }
      setFlavor(snap.flavor);
      setTier(snap.tier);
      setOutputFormat(snap.outputFormat);
      setMetadataText(snap.metadataText);
      setScriptSource(snap.scriptSource);
      setTargetScope(snap.targetScope);
      setCredentialMode(snap.credentialMode);
      setEgressText(snap.egressText);
      snapshotRef.current = null;
    }
    setAppliedPresetName(null);
  };

  // Load field into editor form
  const handleSelectField = (field: CustomFieldDefinition) => {
    setSelectedFieldId(field.id);
    setName(field.name);
    setSlug(field.slug);
    setTier(field.tier);
    setOutputFormat(field.output_format);
    setMetadataText(JSON.stringify(field.output_format_metadata, null, 2));
    setScriptSource(field.script_source ?? '');
    setFlavor(detectFlavor(field));
    setTargetScope(field.target_scope);
    setCredentialMode(field.credential_mode);
    setEgressText(field.egress_allowlist.join('\n'));
    setIsEnabled(field.is_enabled);
    setJsonError(null);
    setSubmitError(null);
    setTestResult(null);
    setTestError(null);
    setAppliedPresetName(null);
    snapshotRef.current = null;
  };

  const handleResetNew = () => {
    setSelectedFieldId(null);
    setName('');
    setSlug('');
    setTier('wasm');
    setFlavor('scalar');
    setOutputFormat('text');
    setMetadataText(JSON.stringify(DEFAULT_METADATA_BY_FORMAT.text, null, 2));
    setScriptSource(STARTER_TEMPLATES.scalar.text);
    setTargetScope('PROJECT');
    setCredentialMode('INVOKING_USER');
    setEgressText('');
    setIsEnabled(true);
    setJsonError(null);
    setSubmitError(null);
    setTestResult(null);
    setTestError(null);
    setAppliedPresetName(null);
    snapshotRef.current = null;
  };

  // Format change helper
  const handleFormatChange = (fmt: OutputFormatType) => {
    setOutputFormat(fmt);
    setMetadataText(JSON.stringify(DEFAULT_METADATA_BY_FORMAT[fmt], null, 2));
    if (!selectedFieldId) {
      setScriptSource(STARTER_TEMPLATES[flavor][fmt]);
    }
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

  // Create mutation with immediate cache update to prevent F5 refresh race
  const createMutation = useMutation({
    mutationFn: async (payload: CustomFieldCreatePayload) => {
      return createCustomField(projectKey, payload);
    },
    onSuccess: (newField) => {
      queryClient.setQueryData<CustomFieldDefinition[]>(
        qk.customFields.project(projectKey),
        (old = []) => [...old, newField],
      );
      setSubmitError(null);
      void refetch();
      handleSelectField(newField);
    },
    onError: (err: Error) => {
      setSubmitError(err.message);
    },
  });

  // Update mutation with immediate cache update to prevent F5 refresh race
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
      queryClient.setQueryData<CustomFieldDefinition[]>(
        qk.customFields.project(projectKey),
        (old = []) => old.map((d) => (d.id === updatedField.id ? updatedField : d)),
      );
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

  // Delete mutation with immediate cache update
  const deleteMutation = useMutation({
    mutationFn: async (fieldId: string) => {
      return deleteCustomField(projectKey, fieldId);
    },
    onSuccess: (_data, fieldId) => {
      queryClient.setQueryData<CustomFieldDefinition[]>(
        qk.customFields.project(projectKey),
        (old = []) => old.filter((d) => d.id !== fieldId),
      );
      handleResetNew();
      void refetch();
    },
  });

  // Test execution handler
  const handleTestExecute = async () => {
    if (!testIssueKey.trim()) {
      setTestError('Please provide an issue key to test execute');
      return;
    }
    setIsTesting(true);
    setTestError(null);
    setTestResult(null);

    let parsedMeta: Record<string, unknown> = {};
    try {
      if (metadataText.trim()) {
        parsedMeta = safeJsonParse<Record<string, unknown>>(metadataText);
      }
    } catch {
      setTestError('Invalid JSON in format metadata');
      setIsTesting(false);
      return;
    }

    const effectiveScriptSource = normalizeScriptSource(flavor, scriptSource);

    try {
      const result = await testExecuteCustomField(projectKey, {
        issue_key: testIssueKey.trim(),
        tier,
        output_format: outputFormat,
        output_format_metadata: parsedMeta,
        script_source: effectiveScriptSource,
        target_scope: targetScope,
        credential_mode: credentialMode,
      });
      setTestResult(result);
    } catch (err: unknown) {
      setTestError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsTesting(false);
    }
  };

  // Form submission handler
  const handleSubmit = (e?: React.SyntheticEvent) => {
    if (e) e.preventDefault();
    setJsonError(null);
    setSubmitError(null);

    let parsedMeta: Record<string, unknown> = {};
    try {
      if (metadataText.trim()) {
        parsedMeta = safeJsonParse<Record<string, unknown>>(metadataText);
      }
    } catch {
      setJsonError('Invalid JSON in format metadata');
      return;
    }

    const egressList = egressText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);

    const effectiveScriptSource = normalizeScriptSource(flavor, scriptSource);

    // If updating an approved field with elevated scope or credential mode,
    // prompt confirmation of tamper auto-revocation (S13.2)
    if (
      selectedField?.approval_status === 'APPROVED' &&
      !isTamperConfirmOpen
    ) {
      const scriptChanged = effectiveScriptSource !== (selectedField.script_source ?? '');
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
          script_source: effectiveScriptSource,
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
        script_source: effectiveScriptSource,
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
      <section className="custom-fields-editor-main" aria-label="Custom Field Configuration">
        <div className="custom-fields-editor-main__header">
          <h2 className="custom-fields-editor-main__title">
            {selectedField ? `Edit: ${selectedField.name}` : 'New Custom Field Definition'}
          </h2>

          {manifestSha ? (
            <div className="custom-fields-sha-chip" data-testid="manifest-sha256-chip">
              <span className="custom-fields-sha-label">SHA256:</span>
              <span className="custom-fields-sha-val mono">
                {manifestSha.slice(0, 16)}...
              </span>
              <button
                type="button"
                className="custom-field-copy-btn"
                onClick={() => {
                  handleCopySha(manifestSha);
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

        {/* Inline Guidance Callout for Standalone Mode */}
        {!isTierBAvailable && (
          <div
            className="custom-field-standalone-callout"
            role="status"
            data-testid="standalone-guidance-callout"
          >
            <span className="custom-field-standalone-callout-icon" aria-hidden="true">
              💡
            </span>
            <div className="custom-field-standalone-callout-text">
              <strong>Standalone Mode Active:</strong> Scalar (&lt;1ms), Formula (&lt;5ms), and WebAssembly (&lt;25ms) work out of the box in Standalone mode.{' '}
              <a
                href="/docs/Guide-Custom-Fields"
                className="custom-field-callout-link"
                data-testid="link-guide-custom-fields"
              >
                [Guide] How to Use Custom Fields &rarr;
              </a>{' '}
              <a
                href="/admin/standalone"
                className="custom-field-callout-link"
                data-testid="link-promote-multi-container"
              >
                Promote to Multi-Container &rarr;
              </a>
            </div>
          </div>
        )}

        {/* Warning Banner for Pre-Existing nsjail Field from Backup */}
        {selectedField?.tier === 'nsjail' && !isTierBAvailable && (
          <div
            className="custom-field-warning-banner"
            role="alert"
            data-testid="preexisting-nsjail-warning-banner"
          >
            <span className="custom-field-warning-banner-icon" aria-hidden="true">
              ⚠️
            </span>
            <div className="custom-field-warning-banner-text">
              <strong>Pre-Existing nsjail Field (Imported from Backup):</strong> Execution sandbox is unavailable in Standalone mode. You can inspect and edit configuration, but execution requires promoting to multi-container compose.
            </div>
          </div>
        )}

        {/* Starter Presets & 4-Flavor Decision Matrix (when creating new definition) */}
        {!selectedField && (
          <div className="custom-fields-starter-toolkit" data-testid="custom-fields-starter-toolkit">
            <FlavorDecisionMatrix
              selectedFlavor={flavor}
              tierBAvailable={isTierBAvailable}
              onSelectFlavor={(f) => {
                setFlavor(f);
                if (f === 'nsjail') {
                  setTier('nsjail');
                } else {
                  setTier('wasm');
                }
                setScriptSource(STARTER_TEMPLATES[f][outputFormat]);
              }}
            />

            <PresetGallery
              onApplyPreset={handleApplyPreset}
              isDirty={isDirty}
              onUndo={handleUndoPreset}
              appliedPresetName={appliedPresetName}
              tierBAvailable={isTierBAvailable}
              onDismissUndo={() => {
                setAppliedPresetName(null);
              }}
            />
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
                  <FieldHelpHint
                    title="Display Name"
                    summary="The human-readable label displayed on issue detail rails, tables, and boards."
                    example="CVSS 3.1 Score"
                    docHref="/docs/custom-fields#display-name"
                    testId="hint-field-name"
                  />
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
                  <FieldHelpHint
                    title="Identifier Slug"
                    summary="Unique lowercase alphanumeric identifier used in API requests, formulas, and queries."
                    validValues={{
                      pattern: 'Lowercase letters, digits, and hyphens (a-z0-9-)',
                      length: '2 to 63 characters',
                      immutability: 'Immutable once created to protect API and script bindings',
                    }}
                    caution="Cannot be modified after creation."
                    docHref="/docs/custom-fields#slug"
                    testId="hint-field-slug"
                  />
                </label>
                <input
                  id="field-slug"
                  type="text"
                  className="custom-field-input mono"
                  maxLength={63}
                  pattern={'^[a-z0-9][a-z0-9\\-]{1,62}$'}
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

              {/* Field Flavor */}
              <div className="custom-field-form-group">
                <label htmlFor="field-flavor" className="custom-field-form-label">
                  Field Flavor
                  <FieldHelpHint
                    title="Field Flavor"
                    summary="The execution paradigm determining compute speed, sandbox isolation, and capabilities."
                    validValues={[
                      { label: 'Scalar', description: 'Static literal or JSON constant (<1ms)' },
                      { label: 'Formula', description: 'Single-issue AST math on issue.* (<5ms)' },
                      { label: 'WebAssembly', description: 'Compiled bytecode module in Tier A sandbox (<25ms)' },
                      { label: 'nsjail Script', description: 'Isolated Linux namespace script with optional egress (<=3,000ms)' },
                    ]}
                    docHref="/docs/custom-fields#flavors"
                    testId="hint-field-flavor"
                  />
                </label>
                <select
                  id="field-flavor"
                  className="custom-field-select"
                  value={flavor}
                  onChange={(e) => {
                    const next = e.target.value as FieldFlavor;
                    setFlavor(next);
                    if (next === 'nsjail') {
                      setTier('nsjail');
                    } else {
                      setTier('wasm');
                    }
                    setScriptSource(STARTER_TEMPLATES[next][outputFormat]);
                  }}
                  data-testid="field-flavor-select"
                >
                  <option value="scalar">Scalar Value (Static literal or JSON object)</option>
                  <option value="formula">Formula Expression (AST safe issue evaluation)</option>
                  <option value="wasm">WebAssembly (Tier A sandboxed bytecode)</option>
                  <option value="nsjail" disabled={!isTierBAvailable}>
                    nsjail Advanced Script (Linux namespaces){!isTierBAvailable ? ' [Multi-Container Compose Required]' : ''}
                  </option>
                </select>
                {!isTierBAvailable && (
                  <span
                    className="custom-field-badge custom-field-badge--warning"
                    data-testid="flavor-nsjail-disabled-badge"
                  >
                    nsjail option requires Multi-Container Compose
                  </span>
                )}
                <div className="custom-field-flavor-guidance" data-testid="flavor-guidance-callout">
                  <span className="custom-field-guidance-pill">
                    {flavor === 'nsjail'
                      ? 'Tier B (nsjail): Isolated Linux namespace sandbox with network boundary controls'
                      : 'Tier A (Wasm / Built-in): High-speed in-process sandbox with zero external egress'}
                  </span>
                </div>
              </div>

              {/* Output Format */}
              <div className="custom-field-form-group">
                <label htmlFor="output-format" className="custom-field-form-label">
                  Output Format
                  <FieldHelpHint
                    title="Output Format"
                    summary="Specifies how evaluated output values are sanitized, validated, and rendered in the UI."
                    validValues={[
                      { label: 'text', description: 'Plain text string (max 280 characters)' },
                      { label: 'number', description: 'Formatted numeric value with fraction digits and unit suffix' },
                      { label: 'badge', description: 'Design token status badge (info, success, warning, danger)' },
                      { label: 'markdown_snippet', description: 'Sanitized markdown markup (max 2000 characters)' },
                      { label: 'url', description: 'Validated HTTPS hyperlink anchor' },
                      { label: 'json_table', description: 'Structured tabular data grid (max 50 rows)' },
                      { label: 'severity_pill', description: 'Security threat level pill (low, medium, high, critical)' },
                    ]}
                    docHref="/docs/custom-fields#output-formats"
                    testId="hint-output-format"
                  />
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

            {/* Advanced Format & Sandbox Script Settings (KB-ADVANCED-DISCLOSURE-03, KAN-369) */}
            <AdvancedSection
              title="Advanced Format & Sandbox Script Settings"
              summary="Format configuration metadata (JSON), execution source code, and live sandbox evaluation"
              testId="custom-field-advanced-section"
              activeOverridesCount={
                (scriptSource.trim() !== '' ? 1 : 0) +
                (metadataText.trim() !== '' && metadataText.trim() !== '{}' ? 1 : 0)
              }
              hasErrors={Boolean(jsonError ?? testError)}
              defaultOpen={false}
            >
              {/* Structured Format Metadata Editor */}
              {['text', 'number', 'badge'].includes(outputFormat) && (
                <div className="custom-field-structured-metadata" data-testid="structured-format-metadata">
                  <div className="custom-field-structured-metadata-header">
                    <span className="custom-field-structured-metadata-title">
                      {outputFormat.toUpperCase()} Format Configuration
                    </span>
                    <button
                      type="button"
                      className="custom-field-btn custom-field-btn--secondary custom-field-btn--xs"
                      data-testid="toggle-raw-metadata-btn"
                      onClick={() => {
                        setShowRawMetadata((prev) => !prev);
                      }}
                    >
                      {showRawMetadata ? 'Hide Raw JSON' : 'Edit Raw JSON'}
                    </button>
                  </div>

                  {outputFormat === 'text' && (
                    <div className="custom-field-structured-grid" data-testid="structured-meta-text">
                      <div className="custom-field-structured-field">
                        <label htmlFor="meta-text-max-length">Max Length</label>
                        <input
                          id="meta-text-max-length"
                          type="number"
                          className="custom-field-input"
                          data-testid="meta-text-max-length"
                          value={typeof parsedMetadata.max_length === 'number' ? parsedMetadata.max_length : 280}
                          onChange={(e) => {
                            updateMetadataField('max_length', Number(e.target.value));
                          }}
                        />
                      </div>
                      <div className="custom-field-structured-field">
                        <label htmlFor="meta-text-prefix">Prefix</label>
                        <input
                          id="meta-text-prefix"
                          type="text"
                          className="custom-field-input"
                          data-testid="meta-text-prefix"
                          placeholder="e.g. ID: "
                          value={typeof parsedMetadata.prefix === 'string' ? parsedMetadata.prefix : ''}
                          onChange={(e) => {
                            updateMetadataField('prefix', e.target.value);
                          }}
                        />
                      </div>
                      <div className="custom-field-structured-field custom-field-structured-field--checkbox">
                        <label className="custom-field-checkbox-label" htmlFor="meta-text-monospace">
                          <input
                            id="meta-text-monospace"
                            type="checkbox"
                            data-testid="meta-text-monospace"
                            checked={Boolean(parsedMetadata.monospace)}
                            onChange={(e) => {
                              updateMetadataField('monospace', e.target.checked);
                            }}
                          />
                          <span>Monospace font</span>
                        </label>
                      </div>
                    </div>
                  )}

                  {outputFormat === 'number' && (
                    <div className="custom-field-structured-grid" data-testid="structured-meta-number">
                      <div className="custom-field-structured-field">
                        <label htmlFor="meta-number-precision">Max Decimals</label>
                        <input
                          id="meta-number-precision"
                          type="number"
                          className="custom-field-input"
                          data-testid="meta-number-precision"
                          value={typeof parsedMetadata.maximum_fraction_digits === 'number' ? parsedMetadata.maximum_fraction_digits : 2}
                          onChange={(e) => {
                            updateMetadataField('maximum_fraction_digits', Number(e.target.value));
                          }}
                        />
                      </div>
                      <div className="custom-field-structured-field">
                        <label htmlFor="meta-number-unit-suffix">Unit Suffix</label>
                        <input
                          id="meta-number-unit-suffix"
                          type="text"
                          className="custom-field-input"
                          data-testid="meta-number-unit-suffix"
                          placeholder="e.g. pts, ms, USD"
                          value={typeof parsedMetadata.unit_suffix === 'string' ? parsedMetadata.unit_suffix : ''}
                          onChange={(e) => {
                            updateMetadataField('unit_suffix', e.target.value);
                          }}
                        />
                      </div>
                      <div className="custom-field-structured-field">
                        <label htmlFor="meta-number-currency">Currency Symbol</label>
                        <input
                          id="meta-number-currency"
                          type="text"
                          className="custom-field-input"
                          data-testid="meta-number-currency"
                          placeholder="e.g. $, €"
                          value={typeof parsedMetadata.currency_symbol === 'string' ? parsedMetadata.currency_symbol : ''}
                          onChange={(e) => {
                            updateMetadataField('currency_symbol', e.target.value);
                          }}
                        />
                      </div>
                    </div>
                  )}

                  {outputFormat === 'badge' && (
                    <div className="custom-field-structured-grid" data-testid="structured-meta-badge">
                      <div className="custom-field-structured-field">
                        <label htmlFor="meta-badge-color">Color Token</label>
                        <input
                          id="meta-badge-color"
                          type="text"
                          className="custom-field-input"
                          data-testid="meta-badge-color"
                          placeholder="info, success, warning, danger"
                          value={typeof parsedMetadata.color_token === 'string' ? parsedMetadata.color_token : 'info'}
                          onChange={(e) => {
                            updateMetadataField('color_token', e.target.value);
                          }}
                        />
                      </div>
                      <div className="custom-field-structured-field">
                        <label htmlFor="meta-badge-labels">Allowed Labels (comma-separated)</label>
                        <input
                          id="meta-badge-labels"
                          type="text"
                          className="custom-field-input"
                          data-testid="meta-badge-labels"
                          placeholder="Active, Verified, Pending"
                          value={Array.isArray(parsedMetadata.allowed_labels) ? parsedMetadata.allowed_labels.join(', ') : ''}
                          onChange={(e) => {
                            const labels = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
                            updateMetadataField('allowed_labels', labels);
                          }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Format Metadata JSON */}
              <div
                className={`custom-field-form-group ${
                  !showRawMetadata && ['text', 'number', 'badge'].includes(outputFormat)
                    ? 'custom-field-raw-meta-collapsed'
                    : ''
                }`}
              >
                <label htmlFor="format-metadata" className="custom-field-form-label">
                  Format Configuration Metadata (JSON)
                  <FieldHelpHint
                    title="Format Metadata JSON"
                    summary="JSON configuration dictionary tailoring display options for the selected output format."
                    validValues={[
                      { label: 'text', description: 'max_length, prefix, monospace' },
                      { label: 'number', description: 'maximum_fraction_digits, unit_suffix' },
                      { label: 'badge', description: 'color_token, allowed_labels' },
                      { label: 'markdown_snippet', description: 'max_chars' },
                      { label: 'url', description: 'allowed_schemes (e.g. ["https"])' },
                      { label: 'json_table', description: 'columns ([{key, label}]), max_rows' },
                      { label: 'severity_pill', description: 'Optional severity score thresholds' },
                    ]}
                    example={JSON.stringify({ maximum_fraction_digits: 2, unit_suffix: ' pts' })}
                    docHref="/docs/custom-fields#format-metadata"
                    testId="hint-format-metadata"
                  />
                </label>
                <textarea
                  id="format-metadata"
                  className="custom-field-textarea mono"
                  rows={8}
                  value={metadataText}
                  onChange={(e) => {
                    setMetadataText(e.target.value);
                  }}
                  data-testid="format-metadata-textarea"
                  aria-invalid={Boolean(jsonError)}
                  aria-describedby={jsonError ? 'format-metadata-error' : undefined}
                />
                {jsonError && (
                  <span id="format-metadata-error" role="alert" className="custom-field-input-error">
                    {jsonError}
                  </span>
                )}
              </div>

              {/* Script Source Code */}
              <div className="custom-field-form-group">
                <label htmlFor="script-source" className="custom-field-form-label">
                  Script Source Code (Sandboxed, never executed client-side)
                  <FieldHelpHint
                    title="Script / Formula Source"
                    summary="Source code or AST formula evaluated in the server sandbox to compute the field value."
                    example='formula: issue.state === "DONE" ? "Completed" : "In Progress"'
                    caution="Scripts run inside hardened server sandboxes and are never executed inside the browser client."
                    docHref="/docs/custom-fields#script-source"
                    testId="hint-script-source"
                  />
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

              {/* Test Execute Section */}
              <div className="custom-field-test-panel" data-testid="custom-field-test-panel">
                <div className="custom-field-test-controls">
                  <label htmlFor="test-issue-key" className="custom-field-form-label">
                    Test With Issue Key
                  </label>
                  <div className="custom-field-test-input-row">
                    <input
                      id="test-issue-key"
                      type="text"
                      className="custom-field-input mono"
                      placeholder="e.g. KANBA-1"
                      value={testIssueKey}
                      onChange={(e) => {
                        setTestIssueKey(e.target.value.toUpperCase());
                      }}
                      data-testid="test-issue-key-input"
                      aria-invalid={Boolean(testError)}
                      aria-describedby={testError ? 'test-execute-error' : undefined}
                    />
                    <button
                      type="button"
                      className="custom-field-btn custom-field-btn--secondary"
                      onClick={() => {
                        void handleTestExecute();
                      }}
                      disabled={isTesting}
                      data-testid="test-execute-btn"
                    >
                      {isTesting ? 'Evaluating...' : 'Test Execute'}
                    </button>
                  </div>
                </div>

                {testError && (
                  <div
                    id="test-execute-error"
                    role="alert"
                    className="custom-field-input-error custom-field-test-error-mt"
                    data-testid="test-execute-error"
                  >
                    {testError}
                  </div>
                )}

                {testResult && (
                  <div className="custom-field-test-result" data-testid="test-execute-result-panel">
                    <div className="custom-field-test-meta custom-field-test-meta-row">
                      <span>
                        <strong>Status:</strong>{' '}
                        <span
                          className={`custom-field-status-pill custom-field-status-pill--${testResult.status.toLowerCase()}`}
                        >
                          {testResult.status}
                        </span>
                      </span>
                      <span data-testid="test-latency">
                        <strong>Latency:</strong> {testResult.latency_ms.toFixed(1)} ms
                      </span>
                    </div>

                    <div className="custom-field-test-preview-wrap">
                      <strong>Rendered Output Pill:</strong>
                      <div
                        className="custom-field-pill-preview custom-field-pill-preview-mt"
                        data-testid="test-output-pill"
                      >
                        <CustomFieldValue
                          format={outputFormat}
                          value={testResult.value}
                          metadata={(() => {
                            try {
                              return safeJsonParse<Record<string, unknown>>(metadataText);
                            } catch {
                              return {};
                            }
                          })()}
                          testId="test-result-value"
                        />
                      </div>
                    </div>

                    {testResult.logs && (
                      <div>
                        <strong>Truncated Logs:</strong>
                        <pre className="custom-field-test-logs mono" data-testid="test-logs">
                          {testResult.logs}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </AdvancedSection>

            {/* Is Enabled */}
            <div className="custom-field-form-group">
              <label htmlFor="is-enabled" className="custom-field-checkbox-label">
                <input
                  id="is-enabled"
                  type="checkbox"
                  aria-label="Enabled"
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
                  Execution Sandbox (S13.3)
                  <FieldHelpHint
                    title="Sandbox Tier"
                    summary="The isolation boundary executing custom field code."
                    validValues={[
                      {
                        label: 'wasm',
                        description:
                          'In-memory WebAssembly sandbox with CPU/memory limits and zero network',
                      },
                      {
                        label: 'nsjail',
                        description:
                          'Isolated Linux namespace container with optional allowlisted HTTP egress',
                      },
                    ]}
                    docHref="/docs/custom-fields#sandbox-tier"
                    testId="hint-execution-tier"
                  />
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
                  <option value="wasm">Built-in Formula Sandbox (WebAssembly)</option>
                  <option value="nsjail" disabled={!isTierBAvailable}>
                    Isolated Process & CLI Sandbox (Linux Namespaces){!isTierBAvailable ? ' [Multi-Container Compose Required]' : ''}
                  </option>
                </select>
                {!isTierBAvailable && (
                  <span
                    className="custom-field-badge custom-field-badge--warning"
                    data-testid="tier-nsjail-disabled-badge"
                  >
                    nsjail option requires Multi-Container Compose
                  </span>
                )}
                <div className="custom-field-form-hint">
                  {tier === 'wasm'
                    ? 'Runs fast custom field formulas and workflow checks in-memory with zero network or filesystem access (Always active).'
                    : 'Runs full Python/CLI scripts and local CLI transition agents with isolated Linux namespaces and allowlisted HTTP egress.'}
                </div>
              </div>

              {/* Target Scope */}
              <div className="custom-field-form-group">
                <label htmlFor="target-scope" className="custom-field-form-label">
                  Token Scope (S13.2)
                  <FieldHelpHint
                    title="Target Scope"
                    summary="The permission boundary for API tokens granted to script executions."
                    validValues={[
                      {
                        label: 'PROJECT',
                        description: 'Scoped strictly to current project issues (Default)',
                      },
                      {
                        label: 'WORKSPACE',
                        description:
                          'Scoped across all projects in the workspace (Requires Workspace Admin approval)',
                      },
                      {
                        label: 'SERVER',
                        description:
                          'Scoped server-wide (Requires Server Admin dual-control approval)',
                      },
                    ]}
                    caution="Elevating scope beyond PROJECT requires formal administrative approval."
                    docHref="/docs/custom-fields#target-scope"
                    testId="hint-target-scope"
                  />
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

              {/* Immediate Dual-Control Explanation Banner (KB-P3-AUDIT-04, S13.2) */}
              {(targetScope === 'WORKSPACE' || targetScope === 'SERVER') && (
                <div
                  className="custom-field-dual-control-banner"
                  data-testid="dual-control-explanation-banner"
                  role="status"
                >
                  <span className="custom-field-dual-control-icon">🛡️</span>
                  <div className="custom-field-dual-control-text">
                    <strong>Dual-Control Policy:</strong> Another distinct administrator holding{' '}
                    <strong>{targetScope === 'SERVER' ? 'SERVER_ADMIN' : 'WORKSPACE_ADMIN'}</strong> authority
                    with a fresh <strong>AAL2</strong> step-up must approve this escalation. Self-approval is
                    blocked (403 Forbidden). Any subsequent edit to script source or format metadata will
                    immediately revoke approval and reset state.
                  </div>
                </div>
              )}

              {/* Credential Mode */}
              <div className="custom-field-form-group">
                <label htmlFor="credential-mode" className="custom-field-form-label">
                  Credential Mode (S13.2)
                  <FieldHelpHint
                    title="Credential Mode"
                    summary="The identity and authority assumed by custom field executions."
                    validValues={[
                      {
                        label: 'INVOKING_USER',
                        description:
                          'Executes under the viewing user credentials and permissions (Default)',
                      },
                      {
                        label: 'PROJECT_ADMIN_SP',
                        description:
                          'Runs with Project Admin Service Principal credentials for all viewers',
                      },
                      {
                        label: 'SERVER_ADMIN_SP',
                        description:
                          'Runs with Server Admin Service Principal credentials (Dual-control required)',
                      },
                    ]}
                    caution="Service Principal execution grants elevated privileges regardless of who is viewing the issue."
                    docHref="/docs/custom-fields#credential-mode"
                    testId="hint-credential-mode"
                  />
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

              {/* Egress Allowlist */}
              <div className="custom-field-form-group">
                <label htmlFor="egress-allowlist" className="custom-field-form-label">
                  Egress Allowlist
                  <FieldHelpHint
                    title="Egress Allowlist"
                    summary="Line-delimited list of approved hostnames or IP addresses for nsjail scripts."
                    validValues={{
                      format: 'Line-delimited FQDNs or IPs (e.g. api.github.com, 127.0.0.1)',
                      scope: 'Applied strictly to nsjail isolated process network namespace',
                    }}
                    example={'api.github.com\n127.0.0.1'}
                    caution="Only active in nsjail sandbox; WebAssembly formulas have zero network egress."
                    docHref="/docs/custom-fields#egress-allowlist"
                    testId="hint-egress-allowlist"
                  />
                </label>
                <textarea
                  id="egress-allowlist"
                  className="custom-field-textarea mono"
                  rows={4}
                  value={egressText}
                  onChange={(e) => {
                    setEgressText(e.target.value);
                  }}
                  data-testid="egress-allowlist-textarea"
                  placeholder="e.g. api.github.com&#10;127.0.0.1"
                />
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
            suppressDualControlBanner={targetScope === 'WORKSPACE' || targetScope === 'SERVER'}
            onApproved={() => {
              void refetch();
            }}
          />
        )}
      </section>

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
            <div className="custom-field-tamper-digests" data-testid="tamper-digests-box">
              <div className="custom-field-tamper-digest-row">
                <span className="custom-field-tamper-label">Current Approved SHA-256:</span>
                <code className="custom-field-tamper-code" data-testid="tamper-old-sha">
                  {selectedField?.manifest_sha256 ?? 'unknown'}
                </code>
              </div>
              <div className="custom-field-tamper-digest-row">
                <span className="custom-field-tamper-label">Pending Modified SHA-256:</span>
                <code className="custom-field-tamper-code" data-testid="tamper-new-sha">
                  {pendingSha}
                </code>
              </div>
            </div>
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
