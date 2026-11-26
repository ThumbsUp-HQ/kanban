// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useEffect, useState, type JSX } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AdminStudioSubnav } from '../admin/AdminStudioSubnav';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { ErrorHelpHint } from '../../components/help/ErrorHelpHint';
import { isAal2StepUpCancelled } from '../../api/client';
import {
  fetchDefaultWorkflowHooks,
  createDefaultWorkflowHook,
  updateDefaultWorkflowHook,
  deleteDefaultWorkflowHook,
  DEFAULT_WASM_MODULES,
  type DefaultWorkflowHook,
  type DefaultHookScopeKind,
  type CreateDefaultWorkflowHookPayload,
  type UpdateDefaultWorkflowHookPayload,
} from './api';
import './workflows.css';

export interface DefaultWorkflowHooksStudioProps {
  scopeKind?: DefaultHookScopeKind | undefined;
  workspaceId?: string | undefined;
  showSubnav?: boolean | undefined;
}

export function DefaultWorkflowHooksStudio({
  scopeKind = 'system',
  workspaceId,
  showSubnav = true,
}: DefaultWorkflowHooksStudioProps): JSX.Element {
  const queryClient = useQueryClient();
  const queryKey = ['default-workflow-hooks', scopeKind, workspaceId ?? 'all'];

  const {
    data: templates = [],
    isLoading,
    error,
  } = useQuery({
    queryKey,
    queryFn: () => fetchDefaultWorkflowHooks(scopeKind, workspaceId),
  });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<DefaultWorkflowHook | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Form fields
  const [formName, setFormName] = useState('');
  const [formFromState, setFormFromState] = useState('');
  const [formToState, setFormToState] = useState('Done');
  const [formHookKind, setFormHookKind] = useState('agent_interceptor');
  const [formAgentSlug, setFormAgentSlug] = useState('@reality-checker');
  const [formWasmSha256, setFormWasmSha256] = useState<string>(DEFAULT_WASM_MODULES[0]?.sha256 ?? '');
  const [formSortRank, setFormSortRank] = useState(100);
  const [formTimeoutMs, setFormTimeoutMs] = useState<number | ''>(60000);
  const [formFailurePolicy, setFormFailurePolicy] = useState<'fail_closed' | 'fail_open_warn'>('fail_closed');
  const [formMaxRework, setFormMaxRework] = useState(3);

  // Close on Escape key press
  useEffect(() => {
    if (!dialogOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setDialogOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [dialogOpen]);

  const openCreateDialog = () => {
    setEditingTemplate(null);
    setFormName('');
    setFormFromState('');
    setFormToState('Done');
    setFormHookKind('agent_interceptor');
    setFormAgentSlug('@reality-checker');
    setFormWasmSha256(DEFAULT_WASM_MODULES[0]?.sha256 ?? '');
    setFormSortRank(100);
    setFormTimeoutMs(60000);
    setFormFailurePolicy('fail_closed');
    setFormMaxRework(3);
    setErrorMessage(null);
    setDialogOpen(true);
  };

  const openEditDialog = (template: DefaultWorkflowHook) => {
    setEditingTemplate(template);
    setFormName(template.name);
    setFormFromState(template.from_state_name ?? '');
    setFormToState(template.to_state_name);

    let initialKind = template.hook_kind;
    if (initialKind === 'agent_async' || initialKind === 'agent_interceptor') {
      initialKind = 'agent_interceptor';
    } else if (
      initialKind === 'wasm_sync' ||
      initialKind === 'wasm_validator' ||
      initialKind === 'sync_validator' ||
      initialKind === 'sync_mutator'
    ) {
      initialKind = 'wasm_validator';
    } else if (initialKind === 'builtin') {
      initialKind = 'builtin';
    }
    setFormHookKind(initialKind);

    setFormAgentSlug(template.agent_slug ? `@${template.agent_slug.replace(/^@+/, '')}` : '');
    setFormWasmSha256(template.wasm_module_sha256 ?? DEFAULT_WASM_MODULES[0]?.sha256 ?? '');
    setFormSortRank(template.sort_rank);
    setFormTimeoutMs(template.timeout_ms ?? '');
    setFormFailurePolicy(template.failure_policy === 'fail_open_warn' ? 'fail_open_warn' : 'fail_closed');
    setFormMaxRework(Math.max(1, Math.min(20, template.max_rework_attempts || 1)));
    setErrorMessage(null);
    setDialogOpen(true);
  };

  const handleToggle = async (template: DefaultWorkflowHook) => {
    try {
      await updateDefaultWorkflowHook(
        template.id,
        { is_enabled: !template.is_enabled },
        workspaceId,
      );
      await queryClient.invalidateQueries({ queryKey });
    } catch (err: unknown) {
      if (!isAal2StepUpCancelled(err)) {
        setErrorMessage(err instanceof Error ? err.message : 'Failed to toggle template status.');
      }
    }
  };

  const handleDelete = async (templateId: string) => {
    if (!window.confirm('Are you sure you want to delete this default hook template?')) {
      return;
    }
    try {
      await deleteDefaultWorkflowHook(templateId, workspaceId);
      await queryClient.invalidateQueries({ queryKey });
    } catch (err: unknown) {
      if (!isAal2StepUpCancelled(err)) {
        setErrorMessage(err instanceof Error ? err.message : 'Failed to delete template.');
      }
    }
  };

  const handleSave = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!formName.trim()) {
      setErrorMessage('Template name is required.');
      return;
    }
    if (!formToState.trim()) {
      setErrorMessage('Target state is required.');
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    const fromStateValue = formFromState.trim();
    const cleanFromState =
      fromStateValue === '' || fromStateValue === '*' ? null : fromStateValue;

    const cleanAgentSlug = formAgentSlug.trim().replace(/^@+/, '') || null;
    const timeoutValue = formTimeoutMs === '' ? null : formTimeoutMs;
    if (timeoutValue !== null) {
      if (Number.isNaN(timeoutValue) || timeoutValue < 1000 || timeoutValue > 600000) {
        setErrorMessage('Timeout must be between 1000 and 600000 ms (1s to 10m).');
        setIsSubmitting(false);
        return;
      }
    }

    try {
      if (formHookKind === 'agent_interceptor') {
        const cleanAgentSlug = formAgentSlug.trim().replace(/^@+/, '') || null;
        if (!cleanAgentSlug) {
          setErrorMessage('Agent slug is required for agent gate hooks.');
          setIsSubmitting(false);
          return;
        }
        if (editingTemplate) {
          const payload: UpdateDefaultWorkflowHookPayload = {
            name: formName.trim(),
            from_state_name: cleanFromState,
            to_state_name: formToState.trim(),
            hook_kind: 'agent_async',
            agent: `@${cleanAgentSlug}`,
            agent_slug: cleanAgentSlug,
            agent_definition_id: null,
            wasm_module_sha256: null,
            sort_rank: formSortRank,
            timeout_ms: timeoutValue,
            failure_policy: formFailurePolicy,
            max_rework_attempts: formMaxRework,
          };
          await updateDefaultWorkflowHook(editingTemplate.id, payload, workspaceId);
        } else {
          const payload: CreateDefaultWorkflowHookPayload = {
            name: formName.trim(),
            scope_kind: scopeKind,
            workspace_id: scopeKind === 'workspace' ? (workspaceId ?? null) : null,
            from_state_name: cleanFromState,
            to_state_name: formToState.trim(),
            hook_kind: 'agent_async',
            agent: `@${cleanAgentSlug}`,
            agent_slug: cleanAgentSlug,
            wasm_module_sha256: null,
            sort_rank: formSortRank,
            timeout_ms: timeoutValue,
            failure_policy: formFailurePolicy,
            max_rework_attempts: formMaxRework,
          };
          await createDefaultWorkflowHook(payload, workspaceId);
        }
      } else if (formHookKind === 'wasm_validator') {
        const cleanWasmSha = formWasmSha256.trim();
        if (!cleanWasmSha) {
          setErrorMessage('Wasm module SHA-256 is required for wasm validator hooks.');
          setIsSubmitting(false);
          return;
        }
        if (editingTemplate) {
          const payload: UpdateDefaultWorkflowHookPayload = {
            name: formName.trim(),
            from_state_name: cleanFromState,
            to_state_name: formToState.trim(),
            hook_kind: 'wasm_sync',
            agent: null,
            agent_slug: null,
            agent_definition_id: null,
            wasm_module_sha256: cleanWasmSha,
            sort_rank: formSortRank,
            timeout_ms: timeoutValue,
            failure_policy: formFailurePolicy,
            max_rework_attempts: formMaxRework,
          };
          await updateDefaultWorkflowHook(editingTemplate.id, payload, workspaceId);
        } else {
          const payload: CreateDefaultWorkflowHookPayload = {
            name: formName.trim(),
            scope_kind: scopeKind,
            workspace_id: scopeKind === 'workspace' ? (workspaceId ?? null) : null,
            from_state_name: cleanFromState,
            to_state_name: formToState.trim(),
            hook_kind: 'wasm_sync',
            agent: null,
            agent_slug: null,
            wasm_module_sha256: cleanWasmSha,
            sort_rank: formSortRank,
            timeout_ms: timeoutValue,
            failure_policy: formFailurePolicy,
            max_rework_attempts: formMaxRework,
          };
          await createDefaultWorkflowHook(payload, workspaceId);
        }
      } else {
        // builtin
        const cleanWasmSha = formWasmSha256.trim() || (DEFAULT_WASM_MODULES[0]?.sha256 ?? '');
        if (!cleanWasmSha) {
          setErrorMessage('Builtin module SHA-256 is required for builtin guard hooks.');
          setIsSubmitting(false);
          return;
        }
        if (editingTemplate) {
          const payload: UpdateDefaultWorkflowHookPayload = {
            name: formName.trim(),
            from_state_name: cleanFromState,
            to_state_name: formToState.trim(),
            hook_kind: 'builtin',
            agent: null,
            agent_slug: null,
            agent_definition_id: null,
            wasm_module_sha256: cleanWasmSha,
            sort_rank: formSortRank,
            timeout_ms: timeoutValue,
            failure_policy: formFailurePolicy,
            max_rework_attempts: formMaxRework,
          };
          await updateDefaultWorkflowHook(editingTemplate.id, payload, workspaceId);
        } else {
          const payload: CreateDefaultWorkflowHookPayload = {
            name: formName.trim(),
            scope_kind: scopeKind,
            workspace_id: scopeKind === 'workspace' ? (workspaceId ?? null) : null,
            from_state_name: cleanFromState,
            to_state_name: formToState.trim(),
            hook_kind: 'builtin',
            agent: null,
            agent_slug: null,
            wasm_module_sha256: cleanWasmSha,
            sort_rank: formSortRank,
            timeout_ms: timeoutValue,
            failure_policy: formFailurePolicy,
            max_rework_attempts: formMaxRework,
          };
          await createDefaultWorkflowHook(payload, workspaceId);
        }
      }
      await queryClient.invalidateQueries({ queryKey });
      setDialogOpen(false);
    } catch (err: unknown) {
      if (!isAal2StepUpCancelled(err)) {
        setErrorMessage(err instanceof Error ? err.message : 'Failed to save template.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const isSystem = scopeKind === 'system';

  return (
    <div
      className="workflow-studio default-workflow-hooks-studio"
      data-testid="default-workflow-hooks-studio"
      style={{ padding: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}
    >
      {isSystem && showSubnav && <AdminStudioSubnav activeTab="workflows" />}

      {/* Header */}
      <header
        className="workflow-studio-header"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '1.5rem',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <h1 className="workflow-studio-title" style={{ fontSize: '1.5rem', margin: '0 0 0.5rem 0' }}>
            <span>⚡ {isSystem ? 'System-Wide Default Workflow Hooks' : 'Workspace Default Workflow Hooks'}</span>
          </h1>
          <p style={{ margin: 0, color: 'var(--fg-secondary)', fontSize: '0.875rem' }}>
            {isSystem
              ? 'Define system-wide default workflow hook templates inherited automatically by all new projects across workspaces. Removable at the project level.'
              : 'Define workspace-level workflow hook templates inherited by newly created projects in this workspace, overriding system-wide templates.'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <StudioDocLink
            href="/docs/scripted-workflows-and-transition-helpers"
            title="Default Workflow Hooks Documentation"
            testId="default-workflow-hooks-doc-link"
          />
          <button
            type="button"
            className="workflow-btn workflow-btn-primary"
            data-testid="create-default-hook-btn"
            onClick={() => { openCreateDialog(); }}
          >
            + Add Default Hook Template
          </button>
        </div>
      </header>

      {/* Error Banner (shown on page when dialog is closed) */}
      {!dialogOpen && (errorMessage !== null || error !== null) && (
        <div className="workflow-alert workflow-alert-danger" role="alert" style={{ marginBottom: '1.5rem' }}>
          <span>{errorMessage ?? (error instanceof Error ? error.message : 'An error occurred')}</span>
          {errorMessage && <ErrorHelpHint error={errorMessage} />}
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--fg-secondary)' }}>
          Loading default workflow hook templates...
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && templates.length === 0 && (
        <div
          data-testid="empty-templates-notice"
          style={{
            padding: '3rem',
            textAlign: 'center',
            background: 'var(--bg-surface)',
            border: '1px dashed var(--border-subtle)',
            borderRadius: '8px',
          }}
        >
          <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>⚡</div>
          <h3 style={{ margin: '0 0 0.5rem 0', fontSize: '1.125rem' }}>No Default Workflow Hook Templates</h3>
          <p style={{ margin: '0 0 1rem 0', color: 'var(--fg-secondary)', fontSize: '0.875rem' }}>
            {isSystem
              ? 'No system default hook templates defined yet. New projects will be created without inherited transition gates.'
              : 'No workspace default hook templates defined yet. New projects will inherit system defaults if configured.'}
          </p>
          <button
            type="button"
            className="workflow-btn workflow-btn-primary"
            onClick={() => { openCreateDialog(); }}
          >
            Create First Template
          </button>
        </div>
      )}

      {/* Templates List */}
      {!isLoading && templates.length > 0 && (
        <div
          className="default-hooks-list"
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem',
          }}
        >
          {templates.map((tpl) => {
            const fromText = tpl.from_state_name ?? '* Any State';
            const toText = tpl.to_state_name;
            const isAgent = tpl.hook_kind.includes('agent');

            return (
              <article
                key={tpl.id}
                className={`hook-pipeline-row ${!tpl.is_enabled ? 'is-disabled' : ''}`}
                data-testid={`template-row-${tpl.id}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '1rem',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '8px',
                  gap: '1rem',
                  flexWrap: 'wrap',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', flex: 1 }}>
                  {/* Scope Badge */}
                  <span
                    className={`workflow-studio-title-badge ${
                      tpl.scope_kind === 'system'
                        ? 'template-scope-badge-system'
                        : 'template-scope-badge-workspace'
                    }`}
                    style={{
                      textTransform: 'uppercase',
                      fontSize: '0.7rem',
                      fontWeight: 600,
                    }}
                  >
                    {tpl.scope_kind}
                  </span>

                  {/* Hook Kind Badge */}
                  <span
                    className={`hook-type-badge ${isAgent ? 'hook-type-agent' : 'hook-type-sync'}`}
                    style={{ fontSize: '0.75rem' }}
                  >
                    {isAgent ? '🤖 [Agent Gate]' : '⚡ [Sync Validator]'}
                  </span>

                  {/* Template Name */}
                  <strong
                    className="hook-name"
                    data-testid={`template-name-${tpl.id}`}
                    style={{ fontSize: '1rem' }}
                  >
                    {tpl.name}
                  </strong>

                  {/* Transition Rule Badge */}
                  <span
                    className="state-badge"
                    data-testid={`template-transition-${tpl.id}`}
                    style={{ fontSize: '0.8rem', padding: '2px 8px' }}
                  >
                    <span>{fromText}</span>
                    <span style={{ margin: '0 4px' }}>&rarr;</span>
                    <span style={{ fontWeight: 600 }}>{toText}</span>
                  </span>

                  {/* Agent Slug */}
                  {tpl.agent_slug && (
                    <span
                      data-testid={`template-agent-slug-${tpl.id}`}
                      style={{
                        fontFamily: 'var(--font-mono, monospace)',
                        fontSize: '0.8rem',
                        color: 'var(--fg-secondary)',
                      }}
                    >
                      @{tpl.agent_slug.replace(/^@+/, '')}
                    </span>
                  )}

                  {/* WASM Module SHA */}
                  {tpl.wasm_module_sha256 && (
                    <span
                      data-testid={`template-wasm-sha-${tpl.id}`}
                      style={{
                        fontFamily: 'var(--font-mono, monospace)',
                        fontSize: '0.8rem',
                        color: 'var(--fg-secondary)',
                      }}
                      title={tpl.wasm_module_sha256}
                    >
                      SHA: {tpl.wasm_module_sha256.slice(0, 8)}...
                    </span>
                  )}

                  {/* Timeout */}
                  {tpl.timeout_ms && (
                    <span className="hook-metric-pill" style={{ fontSize: '0.75rem' }}>
                      {tpl.timeout_ms / 1000}s
                    </span>
                  )}

                  {/* Failure Policy */}
                  <span
                    className={`hook-policy-badge ${
                      tpl.failure_policy === 'fail_closed' ? 'policy-fail-closed' : 'policy-fail-open'
                    }`}
                  >
                    {tpl.failure_policy === 'fail_closed' ? 'Fail-Closed' : 'Fail-Open (Warn)'}
                  </span>
                </div>

                {/* Right Actions */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  {/* Status Toggle */}
                  <label
                    className="hook-toggle-switch"
                    htmlFor={`template-toggle-${tpl.id}`}
                    title={tpl.is_enabled ? 'Template is enabled' : 'Template is disabled'}
                  >
                    <input
                      id={`template-toggle-${tpl.id}`}
                      data-testid={`template-toggle-${tpl.id}`}
                      type="checkbox"
                      checked={tpl.is_enabled}
                      onChange={() => {
                        void handleToggle(tpl);
                      }}
                      aria-label={`Toggle ${tpl.name}`}
                    />
                    <span className="hook-toggle-slider" />
                  </label>

                  {/* Edit Button */}
                  <button
                    type="button"
                    className="workflow-btn workflow-btn-secondary workflow-btn-sm"
                    data-testid={`template-edit-btn-${tpl.id}`}
                    onClick={() => { openEditDialog(tpl); }}
                  >
                    Edit
                  </button>

                  {/* Delete Button */}
                  <button
                    type="button"
                    className="workflow-btn workflow-btn-danger workflow-btn-sm"
                    data-testid={`template-delete-btn-${tpl.id}`}
                    onClick={() => {
                      void handleDelete(tpl.id);
                    }}
                  >
                    Delete
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* Modal Dialog for Create / Edit */}
      {dialogOpen && (
        <div
          className="workflow-modal-backdrop"
          role="presentation"
          onClick={() => { setDialogOpen(false); }}
        >
          <div
            className="workflow-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="template-dialog-title"
            data-testid="template-dialog"
            onClick={(e) => { e.stopPropagation(); }}
          >
            <div className="workflow-dialog-header">
              <h2 id="template-dialog-title" className="workflow-dialog-title">
                {editingTemplate ? 'Edit Default Hook Template' : 'Add Default Hook Template'}
              </h2>
            </div>

            <form onSubmit={(e) => void handleSave(e)} className="workflow-dialog-form">
              <div className="workflow-dialog-body">
                {errorMessage && (
                  <div
                    className="workflow-alert workflow-alert-danger"
                    role="alert"
                    style={{ marginBottom: '0.5rem' }}
                  >
                    <span>{errorMessage}</span>
                    <ErrorHelpHint error={errorMessage} />
                  </div>
                )}

                {/* Template Name */}
                <div>
                  <label
                    htmlFor="template-name-input"
                    style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}
                  >
                    Template Name *
                  </label>
                  <input
                    id="template-name-input"
                    data-testid="template-name-input"
                    type="text"
                    className="workflow-form-control"
                    style={{ width: '100%' }}
                    placeholder="e.g. reality-checker-gate"
                    value={formName}
                    onChange={(e) => { setFormName(e.target.value); }}
                    required
                    maxLength={120}
                  />
                </div>

                {/* Transition States: From & To */}
                <div className="workflow-form-grid-2">
                  <div>
                    <label
                      htmlFor="template-from-state-input"
                      style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}
                    >
                      From State (Optional)
                    </label>
                    <input
                      id="template-from-state-input"
                      data-testid="template-from-state-input"
                      type="text"
                      className="workflow-form-control"
                      style={{ width: '100%' }}
                      placeholder="* Any State"
                      value={formFromState}
                      onChange={(e) => { setFormFromState(e.target.value); }}
                      maxLength={80}
                    />
                    <small style={{ color: 'var(--fg-secondary)', fontSize: '0.75rem' }}>
                      Leave blank or * for Any State wildcard
                    </small>
                  </div>
                  <div>
                    <label
                      htmlFor="template-to-state-input"
                      style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}
                    >
                      To State *
                    </label>
                    <input
                      id="template-to-state-input"
                      data-testid="template-to-state-input"
                      type="text"
                      className="workflow-form-control"
                      style={{ width: '100%' }}
                      placeholder="e.g. Done"
                      value={formToState}
                      onChange={(e) => { setFormToState(e.target.value); }}
                      required
                      maxLength={80}
                    />
                  </div>
                </div>

                {/* Hook Kind & Target Configuration */}
                <div className="workflow-form-grid-2">
                  <div>
                    <label
                      htmlFor="template-hook-kind-select"
                      style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}
                    >
                      Hook Kind *
                    </label>
                    <select
                      id="template-hook-kind-select"
                      data-testid="template-hook-kind-select"
                      className="workflow-form-control"
                      style={{ width: '100%' }}
                      value={formHookKind}
                      onChange={(e) => {
                        const newKind = e.target.value;
                        setFormHookKind(newKind);
                        if (newKind === 'builtin' || newKind === 'wasm_validator') {
                          if (!formWasmSha256) {
                            setFormWasmSha256(DEFAULT_WASM_MODULES[0]?.sha256 ?? '');
                          }
                        }
                      }}
                    >
                      <option value="agent_interceptor">Agent Gate (Async)</option>
                      <option value="wasm_validator">Wasm Validator (Sync)</option>
                      <option value="builtin">Builtin Guard</option>
                    </select>
                  </div>

                  {formHookKind === 'agent_interceptor' && (
                    <div>
                      <label
                        htmlFor="template-agent-slug-input"
                        style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}
                      >
                        Agent Slug *
                      </label>
                      <input
                        id="template-agent-slug-input"
                        data-testid="template-agent-slug-input"
                        type="text"
                        className="workflow-form-control"
                        style={{ width: '100%' }}
                        placeholder="@reality-checker"
                        value={formAgentSlug}
                        onChange={(e) => { setFormAgentSlug(e.target.value); }}
                        maxLength={80}
                        required
                      />
                    </div>
                  )}

                  {formHookKind === 'wasm_validator' && (
                    <div>
                      <label
                        htmlFor="template-wasm-sha-input"
                        style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}
                      >
                        Wasm Module SHA-256 *
                      </label>
                      <input
                        id="template-wasm-sha-input"
                        data-testid="template-wasm-sha-input"
                        type="text"
                        className="workflow-form-control"
                        style={{ width: '100%' }}
                        placeholder="64-character hex SHA-256"
                        value={formWasmSha256}
                        onChange={(e) => { setFormWasmSha256(e.target.value); }}
                        required
                      />
                    </div>
                  )}

                  {formHookKind === 'builtin' && (
                    <div>
                      <label
                        htmlFor="template-builtin-select"
                        style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}
                      >
                        Builtin Guard *
                      </label>
                      <select
                        id="template-builtin-select"
                        data-testid="template-builtin-select"
                        className="workflow-form-control"
                        style={{ width: '100%' }}
                        value={formWasmSha256}
                        onChange={(e) => { setFormWasmSha256(e.target.value); }}
                      >
                        {DEFAULT_WASM_MODULES.map((m) => (
                          <option key={m.sha256} value={m.sha256}>
                            {m.name} ({m.target_latency_budget ?? '<25ms'})
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>

                {/* Timeout & Failure Policy */}
                <div className="workflow-form-grid-2">
                  <div>
                    <label
                      htmlFor="template-timeout-input"
                      style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}
                    >
                      Timeout (ms)
                    </label>
                    <input
                      id="template-timeout-input"
                      data-testid="template-timeout-input"
                      type="number"
                      min={1000}
                      max={600000}
                      step={1000}
                      className="workflow-form-control"
                      style={{ width: '100%' }}
                      placeholder="60000"
                      value={formTimeoutMs}
                      onChange={(e) => { setFormTimeoutMs(e.target.value === '' ? '' : Number(e.target.value)); }}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="template-policy-select"
                      style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}
                    >
                      Failure Policy *
                    </label>
                    <select
                      id="template-policy-select"
                      data-testid="template-policy-select"
                      className="workflow-form-control"
                      style={{ width: '100%' }}
                      value={formFailurePolicy}
                      onChange={(e) => { setFormFailurePolicy(e.target.value as 'fail_closed' | 'fail_open_warn'); }}
                    >
                      <option value="fail_closed">Fail Closed (Block transition)</option>
                      <option value="fail_open_warn">Fail Open (Warn only)</option>
                    </select>
                  </div>
                </div>

                {/* Sort Rank & Max Rework Attempts */}
                <div className="workflow-form-grid-2">
                  <div>
                    <label
                      htmlFor="template-sort-rank-input"
                      style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}
                    >
                      Sort Rank
                    </label>
                    <input
                      id="template-sort-rank-input"
                      data-testid="template-sort-rank-input"
                      type="number"
                      min={0}
                      className="workflow-form-control"
                      style={{ width: '100%' }}
                      value={formSortRank}
                      onChange={(e) => { setFormSortRank(Number(e.target.value)); }}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="template-rework-input"
                      style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.25rem' }}
                    >
                      Max Rework Attempts
                    </label>
                    <input
                      id="template-rework-input"
                      data-testid="template-rework-input"
                      type="number"
                      min={1}
                      max={20}
                      className="workflow-form-control"
                      style={{ width: '100%' }}
                      value={formMaxRework}
                      onChange={(e) => { setFormMaxRework(Number(e.target.value)); }}
                    />
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="workflow-dialog-actions">
                <button
                  type="button"
                  className="workflow-btn workflow-btn-secondary"
                  data-testid="cancel-template-btn"
                  onClick={() => { setDialogOpen(false); }}
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="workflow-btn workflow-btn-primary"
                  data-testid="save-template-btn"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? 'Saving...' : editingTemplate ? 'Update Template' : 'Create Template'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
