// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX } from 'react';
import { Link } from 'react-router';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import {
  MUTABLE_FIELD_UNIVERSE,
  IMMUTABLE_FIELDS_NOTICE,
  DEFAULT_WASM_MODULES,
  type WorkflowHook,
  type HookKind,
  type FailurePolicy,
  type CreateWorkflowHookPayload,
  type AgentDefinitionSummary,
  type ProjectStateSummary,
  type WasmModuleSummary,
} from './api';

export interface AttachHookDialogProps {
  isOpen: boolean;
  projectKey: string;
  initialTransition?: { from_state: string | null; to_state: string } | undefined;
  editingHook?: WorkflowHook | null | undefined;
  states: ProjectStateSummary[];
  agentDefinitions: AgentDefinitionSummary[];
  wasmModules?: WasmModuleSummary[] | undefined;
  onSave: (payload: CreateWorkflowHookPayload) => Promise<void> | void;
  onClose: () => void;
}

function AttachHookDialogInner({
  initialTransition,
  editingHook,
  states,
  agentDefinitions,
  wasmModules = DEFAULT_WASM_MODULES,
  onSave,
  onClose,
}: Omit<AttachHookDialogProps, 'isOpen' | 'projectKey'>): JSX.Element {
  const [name, setName] = useState<string>(editingHook ? editingHook.name : '');
  const [fromState, setFromState] = useState<string | null>(
    editingHook ? editingHook.from_state : (initialTransition?.from_state ?? null),
  );
  const [toState, setToState] = useState<string>(
    editingHook
      ? editingHook.to_state
      : (initialTransition?.to_state ?? (states[1]?.name ?? states[0]?.name ?? 'Done')),
  );
  const [hookKind, setHookKind] = useState<HookKind>(
    editingHook ? editingHook.hook_kind : 'sync_validator',
  );
  const [failurePolicy, setFailurePolicy] = useState<FailurePolicy>(
    editingHook ? editingHook.failure_policy : 'fail_closed',
  );
  const [selectedWasmSha, setSelectedWasmSha] = useState<string>(
    editingHook?.wasm_module_sha256 ?? wasmModules[0]?.sha256 ?? '',
  );
  const [selectedAgentSlug, setSelectedAgentSlug] = useState<string>(
    editingHook?.agent_slug ?? agentDefinitions[0]?.slug ?? '',
  );
  const [allowedMutableFields, setAllowedMutableFields] = useState<string[]>(
    editingHook?.allowed_mutable_fields ?? [],
  );
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleToggleMutableField = (field: string) => {
    // Invariant: state and description_markdown are forbidden
    if (field === 'state' || field === 'description_markdown') return;

    setAllowedMutableFields((prev) =>
      prev.includes(field) ? prev.filter((f) => f !== field) : [...prev, field],
    );
  };

  const selectedAgent = agentDefinitions.find((a) => a.slug === selectedAgentSlug);

  const handleSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    setError(null);

    const trimmedName = name.trim();
    if (!trimmedName) {
      setError('Hook name is required.');
      return;
    }

    if (!toState) {
      setError('Target state (to_state) is required.');
      return;
    }

    if (fromState !== null && fromState === toState) {
      setError('from_state and to_state cannot be identical.');
      return;
    }

    const payload: CreateWorkflowHookPayload = {
      name: trimmedName,
      from_state: fromState,
      to_state: toState,
      hook_kind: hookKind,
      failure_policy: failurePolicy,
      allowed_mutable_fields: hookKind === 'sync_validator' ? [] : allowedMutableFields,
    };

    if (hookKind === 'sync_validator' || hookKind === 'sync_mutator') {
      payload.wasm_module_sha256 = selectedWasmSha;
    } else {
      payload.agent = selectedAgentSlug;
      if (selectedAgent?.timeout_ms) {
        payload.timeout_ms = selectedAgent.timeout_ms;
      }
    }

    try {
      setIsSubmitting(true);
      await onSave(payload);
      onClose();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to attach workflow hook.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Group agents by harness
  const cliAgents = agentDefinitions.filter((a) => a.harness_kind === 'cli_pipe');
  const sdkAgents = agentDefinitions.filter((a) => a.harness_kind === 'in_app_sdk');
  const remoteAgents = agentDefinitions.filter((a) => a.harness_kind === 'remote_runner');

  const isSubmitDisabled =
    isSubmitting || (hookKind === 'agent_interceptor' && agentDefinitions.length === 0);

  return (
    <div className="workflow-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="workflow-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="attach-hook-title"
        onClick={(e) => { e.stopPropagation(); }}
      >
        <div className="workflow-dialog-header">
          <h2 id="attach-hook-title" className="workflow-dialog-title">
            {editingHook ? `Edit Hook: ${editingHook.name}` : 'Attach Workflow Helper Hook'}
          </h2>
        </div>

        <form onSubmit={(e) => { void handleSubmit(e); }} className="workflow-dialog-form">
          <div className="workflow-dialog-body">
            {error && (
              <div className="workflow-alert workflow-alert-danger" role="alert">
                {error}
              </div>
            )}

            {/* Transition states */}
            <div className="workflow-form-group">
              <label htmlFor="from-state-select" className="workflow-form-label">
                From State
              </label>
              <select
                id="from-state-select"
                className="workflow-form-control"
                value={fromState ?? '*'}
                onChange={(e) => { setFromState(e.target.value === '*' ? null : e.target.value); }}
              >
                <option value="*">* Any State</option>
                {states.map((s) => (
                  <option key={s.id} value={s.name}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="workflow-form-group">
              <label htmlFor="to-state-select" className="workflow-form-label">
                To State (Required)
              </label>
              <select
                id="to-state-select"
                className="workflow-form-control"
                value={toState}
                onChange={(e) => { setToState(e.target.value); }}
                required
              >
                {states.map((s) => (
                  <option key={s.id} value={s.name}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Hook Name */}
            <div className="workflow-form-group">
              <label htmlFor="hook-name-input" className="workflow-form-label">
                Hook Name
              </label>
              <input
                id="hook-name-input"
                type="text"
                className="workflow-form-control"
                placeholder="e.g. require-qa-proof-link"
                value={name}
                onChange={(e) => { setName(e.target.value); }}
                required
              />
            </div>

            {/* Hook Kind RadioGroup */}
            <div className="workflow-form-group">
              <label className="workflow-form-label">
                Hook Kind
                <FieldHelpHint
                  title="Workflow Hook Kind"
                  summary="The execution tier for this transition helper rule."
                  validValues={[
                    { label: 'Sync Wasm Validator', description: 'Fast <25ms in-process WebAssembly validator that checks conditions and can veto.' },
                    { label: 'Async Wasm Post-Mutation', description: 'Background WebAssembly post-action that mutates allowed fields.' },
                    { label: 'Agent Transition Helper', description: 'Autonomous agent (CLI, SDK, or Runner) executing forensic QA gates.' },
                  ]}
                  docHref="/docs/scripted-workflows-and-transition-helpers#helper-architecture"
                  testId="hook-kind-help"
                />
              </label>
              <div className="workflow-radiogroup" role="radiogroup" aria-label="Hook Kind">
                <label className="workflow-radio-label">
                  <input
                    type="radio"
                    name="hook_kind"
                    value="sync_validator"
                    checked={hookKind === 'sync_validator'}
                    onChange={() => { setHookKind('sync_validator'); }}
                  />
                  Sync Wasm Validator
                </label>
                <label className="workflow-radio-label">
                  <input
                    type="radio"
                    name="hook_kind"
                    value="sync_mutator"
                    checked={hookKind === 'sync_mutator'}
                    onChange={() => { setHookKind('sync_mutator'); }}
                  />
                  Sync Wasm Mutator
                </label>
                <label className="workflow-radio-label">
                  <input
                    type="radio"
                    name="hook_kind"
                    value="agent_interceptor"
                    checked={hookKind === 'agent_interceptor'}
                    onChange={() => { setHookKind('agent_interceptor'); }}
                  />
                  Agent Transition Helper
                </label>
              </div>
            </div>

            {/* Conditional: Wasm Module selector */}
            {(hookKind === 'sync_validator' || hookKind === 'sync_mutator') && (
              <div className="workflow-form-group">
                <label htmlFor="wasm-module-select" className="workflow-form-label">
                  Approved WebAssembly Module (Built-in Formula Sandbox)
                </label>
                <select
                  id="wasm-module-select"
                  className="workflow-form-control"
                  value={selectedWasmSha}
                  onChange={(e) => { setSelectedWasmSha(e.target.value); }}
                >
                  {wasmModules.map((m) => (
                    <option key={m.sha256} value={m.sha256}>
                      {m.name} ({m.sha256.slice(0, 8)}... - {m.target_latency_budget ?? '<25ms'})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Conditional: Agent Transition Helper selector */}
            {hookKind === 'agent_interceptor' && (
              agentDefinitions.length === 0 ? (
                <div className="workflow-alert workflow-alert-warning" data-testid="no-agents-warning">
                  <strong>No Agent Definitions configured</strong>
                  <p style={{ margin: '4px 0 8px' }}>
                    There are no active Agent Definitions registered in this workspace. Configure an Agent Definition before attaching an Agent Transition Helper hook.
                  </p>
                  <Link
                    to="/workspaces/settings"
                    className="workflow-btn workflow-btn-secondary workflow-btn-sm"
                    data-testid="configure-agents-link"
                    style={{ display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }}
                  >
                    Configure Agent Definitions &rarr;
                  </Link>
                </div>
              ) : (
                <>
                  <div className="workflow-form-group">
                    <label htmlFor="agent-def-select" className="workflow-form-label">
                      Agent Definition
                    </label>
                    <select
                      id="agent-def-select"
                      className="workflow-form-control"
                      value={selectedAgentSlug}
                      onChange={(e) => { setSelectedAgentSlug(e.target.value); }}
                    >
                      {cliAgents.length > 0 && (
                        <optgroup label="CLI Pipe Agents (agy, codex)">
                          {cliAgents.map((a) => (
                            <option key={a.id} value={a.slug}>
                              {a.display_name} ({a.cli_binary_allowlist_id ?? 'cli'})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {sdkAgents.length > 0 && (
                        <optgroup label="In-App SDK Agents (Ollama, Gemini, OpenAI)">
                          {sdkAgents.map((a) => (
                            <option key={a.id} value={a.slug}>
                              {a.display_name} ({a.model_id ?? a.provider_kind})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {remoteAgents.length > 0 && (
                        <optgroup label="Remote Runner Pools">
                          {remoteAgents.map((a) => (
                            <option key={a.id} value={a.slug}>
                              {a.display_name}
                            </option>
                          ))}
                        </optgroup>
                      )}
                    </select>
                  </div>

                  {/* Agent read-only details summary */}
                  {selectedAgent && (
                    <div className="workflow-notice" data-testid="agent-details-summary">
                      <strong>Agent Config Summary:</strong>
                      <div>Harness: {selectedAgent.harness_kind}</div>
                      {selectedAgent.cli_args.length > 0 && (
                        <div>Validated CLI Args: <code>{selectedAgent.cli_args.join(' ')}</code></div>
                      )}
                      <div>Repo Access Mode: <code>{selectedAgent.repo_access_mode}</code></div>
                      <div>Timeout: {Math.round(selectedAgent.timeout_ms / 1000)}s</div>
                    </div>
                  )}
                </>
              )
            )}

            {/* Failure Policy */}
            <div className="workflow-form-group">
              <label htmlFor="failure-policy-select" className="workflow-form-label">
                Failure Policy
                <FieldHelpHint
                  title="Failure Policy"
                  summary="Specifies behavior when helper times out, returns an error, or crashes."
                  validValues={[
                    { label: 'Fail-Closed', description: 'Blocks transition immediately, rejecting state change.' },
                    { label: 'Fail-Open (Warn)', description: 'Records audit warning and allows transition to proceed.' },
                  ]}
                  docHref="/docs/scripted-workflows-and-transition-helpers#failure-policies"
                  testId="failure-policy-help"
                />
              </label>
              <select
                id="failure-policy-select"
                className="workflow-form-control"
                value={failurePolicy}
                onChange={(e) => { setFailurePolicy(e.target.value as FailurePolicy); }}
              >
                <option value="fail_closed">Fail-Closed (Blocks transition on failure or veto)</option>
                <option value="fail_open_warn">Fail-Open (Warn) (Logs warning but allows transition)</option>
              </select>
            </div>

            {/* Allowed Mutable Fields */}
            <div className="workflow-form-group">
              <label className="workflow-form-label">
                Allowed Mutable Fields
                {hookKind === 'sync_validator' && ' (Disabled for Validators)'}
              </label>
              <div className="mutable-fields-picker">
                {MUTABLE_FIELD_UNIVERSE.map((field) => {
                  const isChecked = allowedMutableFields.includes(field);
                  const isDisabled = hookKind === 'sync_validator';
                  const labelClass = [
                    'workflow-radio-label',
                    isDisabled ? 'is-disabled' : '',
                  ]
                    .filter(Boolean)
                    .join(' ');
                  return (
                    <label key={field} className={labelClass}>
                      <input
                        type="checkbox"
                        checked={isChecked && !isDisabled}
                        disabled={isDisabled}
                        onChange={() => { handleToggleMutableField(field); }}
                      />
                      <code>{field}</code>
                    </label>
                  );
                })}
              </div>
              <div className="workflow-notice">
                {IMMUTABLE_FIELDS_NOTICE}
              </div>
            </div>
          </div>

          {/* Actions - Sticky Footer */}
          <div className="workflow-dialog-actions">
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="workflow-btn workflow-btn-primary"
              disabled={isSubmitDisabled}
            >
              {isSubmitting ? 'Saving...' : editingHook ? 'Update Hook' : 'Attach Hook'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function AttachHookDialog({
  isOpen,
  ...innerProps
}: AttachHookDialogProps): JSX.Element | null {
  if (!isOpen) return null;
  return (
    <AttachHookDialogInner
      key={innerProps.editingHook?.id ?? 'new-hook'}
      {...innerProps}
    />
  );
}
