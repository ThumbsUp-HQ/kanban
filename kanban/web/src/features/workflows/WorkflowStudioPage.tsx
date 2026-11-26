// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useMemo, type JSX } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { apiFetch, isAal2StepUpCancelled } from '../../api/client';
import { NotFoundView } from '../../app/routes';
import { useAuth } from '../auth/AuthContext';
import { TransitionRuleCard } from './TransitionRuleCard';
import { AttachHookDialog } from './AttachHookDialog';
import { DryRunDrawer } from './DryRunDrawer';
import { GitRepoBindingsSection } from './GitRepoBindingsSection';
import {
  fetchWorkflowHooks,
  createWorkflowHook,
  updateWorkflowHook,
  enableWorkflowHook,
  disableWorkflowHook,
  deleteWorkflowHook,
  reorderWorkflowHooks,
  syncDefaultWorkflowHooks,
  fetchAgentDefinitions,
  fetchProjectStates,
  fetchApprovedWasmModules,
  type WorkflowHook,
  type CreateWorkflowHookPayload,
  type ReorderHooksPayload,
} from './api';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { ErrorHelpHint } from '../../components/help/ErrorHelpHint';
import './workflows.css';

export interface WorkflowStudioPageProps {
  projectKeyOverride?: string;
  workspaceSlugOverride?: string;
  isAdmin?: boolean;
}

export function WorkflowStudioPage({
  projectKeyOverride,
  workspaceSlugOverride,
  isAdmin: propIsAdmin,
}: WorkflowStudioPageProps): JSX.Element {
  const params = useParams<{ projectKey?: string; workspaceSlug?: string }>();
  const [searchParams] = useSearchParams();
  const auth = useAuth();
  const projectKey = projectKeyOverride ?? params.projectKey ?? 'KAN';
  const queryClient = useQueryClient();

  const activeWorkspaceSlug =
    workspaceSlugOverride ??
    params.workspaceSlug ??
    (auth.session?.workspace_id ?? 'current');

  // Query parameter overrides for non-admin testing
  const queryNonAdmin =
    searchParams.get('non_admin') === 'true' ||
    searchParams.get('role') === 'member' ||
    searchParams.get('role') === 'viewer';

  // Check project details & capabilities
  const projectQuery = useQuery({
    queryKey: qk.project(projectKey),
    queryFn: async () => {
      try {
        const data: unknown = await apiFetch('GET', `/api/v1/projects/${encodeURIComponent(projectKey)}` as never);
        return data as { name?: string; capabilities?: string[]; default_gate_timeout_ms?: number | null };
      } catch {
        return null;
      }
    },
    enabled: propIsAdmin === undefined && !queryNonAdmin,
    staleTime: 60000,
  });

  const isUserAdmin = useMemo(() => {
    if (queryNonAdmin) return false;
    if (propIsAdmin !== undefined) return propIsAdmin;
    const caps = projectQuery.data?.capabilities;
    if (caps && Array.isArray(caps)) {
      return caps.includes('ADMIN') || caps.includes('PROJECT_ADMIN');
    }
    return false;
  }, [queryNonAdmin, propIsAdmin, projectQuery.data]);

  // Main rules query
  const rulesQuery = useQuery({
    queryKey: ['workflow-hooks', projectKey],
    queryFn: () => fetchWorkflowHooks(projectKey),
    enabled: isUserAdmin,
  });

  const rules = rulesQuery.data ?? [];
  const isLoading = rulesQuery.isLoading;
  const generalError =
    rulesQuery.error && !isAal2StepUpCancelled(rulesQuery.error)
      ? rulesQuery.error.message
      : null;

  // Dialog and drawer state
  const attachParam = searchParams.get('attach');
  const toStateParam = searchParams.get('to_state');
  const shouldAutoOpen = attachParam === '1' || attachParam === 'true';

  const [isAttachDialogOpen, setIsAttachDialogOpen] = useState(() => shouldAutoOpen);
  const [editingHook, setEditingHook] = useState<WorkflowHook | null>(null);
  const [activeTransition, setActiveTransition] = useState<{
    from_state: string | null;
    to_state: string;
  } | null>(() => (shouldAutoOpen && toStateParam ? { from_state: null, to_state: toStateParam } : null));

  const [dryRunTransition, setDryRunTransition] = useState<{
    from_state: string | null;
    to_state: string;
  } | null>(null);

  // Project default gate timeout state
  const [overrideTimeout, setOverrideTimeout] = useState<number | null | undefined>(undefined);
  const projectDefaultTimeout =
    overrideTimeout !== undefined
      ? overrideTimeout
      : (projectQuery.data?.default_gate_timeout_ms ?? null);
  const [isSavingTimeout, setIsSavingTimeout] = useState(false);
  const [timeoutSuccess, setTimeoutSuccess] = useState<string | null>(null);
  const [timeoutError, setTimeoutError] = useState<string | null>(null);

  // Sync default workflow hooks state
  const [isSyncingDefaults, setIsSyncingDefaults] = useState(false);
  const [syncStatusMessage, setSyncStatusMessage] = useState<string | null>(null);

  const handleSaveProjectTimeout = async (val: number | null) => {
    if (val !== null && (Number.isNaN(val) || val < 1000 || val > 600000)) {
      setTimeoutError('Timeout must be between 1,000 and 600,000 ms (up to 10 minutes).');
      return;
    }
    try {
      setIsSavingTimeout(true);
      setTimeoutError(null);
      setTimeoutSuccess(null);
      await apiFetch('PATCH', `/api/v1/projects/${encodeURIComponent(projectKey)}` as never, {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ default_gate_timeout_ms: val }),
      });
      setOverrideTimeout(val);
      setTimeoutSuccess(
        val !== null
          ? `Project default gate timeout set to ${String(val)} ms.`
          : 'Project default gate timeout reset to agent defaults.',
      );
      await queryClient.invalidateQueries({ queryKey: qk.project(projectKey) });
      await queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] });
    } catch (err: unknown) {
      if (err instanceof Error) {
        setTimeoutError(err.message);
      } else {
        setTimeoutError('Failed to update project default gate timeout.');
      }
    } finally {
      setIsSavingTimeout(false);
    }
  };


  // Auxiliary data queries
  const statesQuery = useQuery({
    queryKey: ['project-states', projectKey],
    queryFn: () => fetchProjectStates(projectKey),
    enabled: isUserAdmin,
  });

  const agentsQuery = useQuery({
    queryKey: ['agent-definitions', activeWorkspaceSlug],
    queryFn: () => fetchAgentDefinitions(activeWorkspaceSlug),
    enabled: isUserAdmin,
  });

  const wasmModulesQuery = useQuery({
    queryKey: ['approved-wasm-modules', projectKey],
    queryFn: () => fetchApprovedWasmModules(projectKey),
    enabled: isUserAdmin,
  });

  // If checking project permissions, show loading
  if (projectQuery.isLoading && propIsAdmin === undefined && !queryNonAdmin) {
    return (
      <div className="workflow-studio" data-testid="workflow-studio-page">
        <div className="empty-hooks-cta">Loading project permissions...</div>
      </div>
    );
  }

  // If user lacks admin permissions, render uniform Not found or no access view (zero write requests)
  if (!isUserAdmin) {
    return <NotFoundView />;
  }

  // Reorder hooks handler
  const handleReorder = async (
    transition: { from_state: string | null; to_state: string },
    orderedHookIds: string[],
  ) => {
    const payload: ReorderHooksPayload = {
      transition,
      ordered_hook_ids: orderedHookIds,
    };

    const action = async () => {
      await reorderWorkflowHooks(projectKey, payload);
      await queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] });
    };

    try {
      await action();
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      throw err;
    }
  };

  // Toggle hook enabled / disabled
  const handleToggle = async (hookId: string, isEnabled: boolean) => {
    const action = async () => {
      if (isEnabled) {
        await enableWorkflowHook(hookId);
      } else {
        await disableWorkflowHook(hookId);
      }
      await queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] });
    };

    try {
      await action();
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
    }
  };

  // Detach hook
  const handleDetach = async (hookId: string) => {
    const action = async () => {
      await deleteWorkflowHook(hookId);
      await queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] });
    };

    try {
      await action();
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
    }
  };

  // Save hook (create or update)
  const handleSaveHook = async (payload: CreateWorkflowHookPayload) => {
    const action = async () => {
      if (editingHook) {
        await updateWorkflowHook(editingHook.id, {
          name: payload.name,
          failure_policy: payload.failure_policy,
          allowed_mutable_fields: payload.allowed_mutable_fields,
          wasm_module_sha256: payload.wasm_module_sha256,
          agent: payload.agent,
          timeout_ms: payload.timeout_ms,
        });
      } else {
        await createWorkflowHook(projectKey, payload);
      }
      await queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] });
    };

    try {
      await action();
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      throw err;
    }
  };

  // Handler to sync default workflow hooks onto this project
  const handleSyncDefaults = async () => {
    try {
      setIsSyncingDefaults(true);
      setSyncStatusMessage(null);
      const synced = await syncDefaultWorkflowHooks(projectKey);
      await queryClient.invalidateQueries({ queryKey: ['workflow-hooks', projectKey] });
      setSyncStatusMessage(
        synced.length > 0
          ? `Successfully synced ${String(synced.length)} default hook template(s).`
          : 'All default hook templates are already present on this project.',
      );
    } catch (err: unknown) {
      if (!isAal2StepUpCancelled(err)) {
        setSyncStatusMessage('Failed to sync default workflow hook templates.');
      }
    } finally {
      setIsSyncingDefaults(false);
    }
  };

  return (
    <div className="workflow-studio" data-testid="workflow-studio-page">
      {/* Studio Header */}
      <header className="workflow-studio-header">
        <h1 className="workflow-studio-title">
          <span className="workflow-studio-title-prefix">
            <span>⚙️ Project</span>
            <span className="workflow-studio-title-badge">{projectKey}</span>
          </span>
          <span className="workflow-studio-title-suffix">&gt; Scripted Workflows &amp; Transition Helpers</span>
        </h1>
        <div className="workflow-studio-actions">
          <StudioDocLink
            href="/docs/scripted-workflows-and-transition-helpers"
            title="Scripted Workflows & Transition Helpers Documentation"
            testId="workflow-studio-doc-link"
          />
          <button
            type="button"
            className="workflow-btn workflow-btn-secondary"
            data-testid="sync-default-hooks-btn"
            onClick={() => {
              void handleSyncDefaults();
            }}
            disabled={isSyncingDefaults}
            aria-label="Sync Default Hooks"
          >
            {isSyncingDefaults ? 'Syncing...' : '🔄 Sync Default Hooks'}
          </button>
          <button
            type="button"
            className="workflow-btn workflow-btn-primary"
            onClick={() => {
              setEditingHook(null);
              setActiveTransition(null);
              setIsAttachDialogOpen(true);
            }}
            aria-label="Add Transition Rule"
          >
            + Add Transition Rule
          </button>
        </div>
      </header>

      {/* Sync Status Banner */}
      {syncStatusMessage && (
        <div
          className="workflow-alert workflow-alert-info"
          role="status"
          data-testid="sync-defaults-status"
          style={{ marginBottom: '1rem' }}
        >
          <span>{syncStatusMessage}</span>
          <button
            type="button"
            className="workflow-btn workflow-btn-secondary workflow-btn-sm"
            style={{ marginLeft: 'auto' }}
            onClick={() => { setSyncStatusMessage(null); }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* General Alert */}
      {generalError && (
        <div className="workflow-alert workflow-alert-danger" role="alert">
          <span>{generalError}</span>
          <ErrorHelpHint error={generalError} />
        </div>
      )}

      {/* Project Default Gate Timeout Control */}
      <section
        className="workflow-project-timeout-panel"
        data-testid="project-gate-timeout-panel"
      >
        <div className="workflow-project-timeout-row">
          <div className="workflow-project-timeout-title-group">
            <h2 className="workflow-project-timeout-heading">
              <span>⏱️ Project Default Gate Timeout</span>
              <span className="workflow-studio-title-badge" data-testid="project-timeout-current-badge">
                {projectDefaultTimeout !== null ? `${String(projectDefaultTimeout)} ms` : 'Agent Default'}
              </span>
            </h2>
            <p className="workflow-project-timeout-description">
              Inherited timeout for all workflow interceptor gates in this project unless overridden by a hook. Max 10 minutes (600,000 ms).
            </p>
          </div>
          <div className="workflow-project-timeout-controls">
            <input
              type="number"
              min="1000"
              max="600000"
              step="1000"
              className="workflow-form-control"
              style={{ width: '130px' }}
              placeholder="Inherit agent"
              value={projectDefaultTimeout !== null ? String(projectDefaultTimeout) : ''}
              onChange={(e) => {
                const v = e.target.value.trim();
                if (v === '') {
                  setOverrideTimeout(null);
                  setTimeoutError(null);
                } else {
                  const parsed = parseInt(v, 10);
                  setOverrideTimeout(Number.isNaN(parsed) ? null : parsed);
                  if (!Number.isNaN(parsed) && (parsed < 1000 || parsed > 600000)) {
                    setTimeoutError('Timeout must be between 1,000 and 600,000 ms (up to 10 minutes).');
                  } else {
                    setTimeoutError(null);
                  }
                }
              }}
              data-testid="project-default-gate-timeout-input"
            />
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary workflow-btn-xs"
              onClick={() => {
                setOverrideTimeout(60000);
                setTimeoutError(null);
              }}
              data-testid="project-timeout-preset-60s"
            >
              60s
            </button>
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary workflow-btn-xs"
              onClick={() => {
                setOverrideTimeout(180000);
                setTimeoutError(null);
              }}
              data-testid="project-timeout-preset-3m"
            >
              3m
            </button>
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary workflow-btn-xs"
              onClick={() => {
                setOverrideTimeout(300000);
                setTimeoutError(null);
              }}
              data-testid="project-timeout-preset-5m"
            >
              5m
            </button>
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary workflow-btn-xs"
              onClick={() => {
                setOverrideTimeout(600000);
                setTimeoutError(null);
              }}
              data-testid="project-timeout-preset-10m"
            >
              10m
            </button>
            <button
              type="button"
              className="workflow-btn workflow-btn-secondary workflow-btn-xs"
              onClick={() => {
                setOverrideTimeout(null);
                setTimeoutError(null);
              }}
              data-testid="project-timeout-preset-clear"
            >
              Inherit
            </button>
            <button
              type="button"
              className="workflow-btn workflow-btn-primary workflow-btn-sm"
              onClick={() => void handleSaveProjectTimeout(projectDefaultTimeout)}
              disabled={isSavingTimeout}
              data-testid="save-project-gate-timeout-btn"
            >
              {isSavingTimeout ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
        {timeoutSuccess && (
          <div className="workflow-project-timeout-success" role="status" data-testid="project-timeout-success">
            {timeoutSuccess}
          </div>
        )}
        {timeoutError && (
          <div className="workflow-project-timeout-error" role="alert" data-testid="project-timeout-error">
            {timeoutError}
          </div>
        )}
      </section>

      {/* Loading State */}
      {isLoading ? (
        <div className="empty-hooks-cta">Loading workflow helper rules...</div>
      ) : rules.length === 0 ? (
        <div className="empty-hooks-cta" data-testid="empty-studio-state">
          No workflow transition rules configured for Project {projectKey}. Click &apos;+ Add Transition Rule&apos; to create one.
        </div>
      ) : (
        rules.map((rule) => (
          <TransitionRuleCard
            key={`${rule.from_state ?? 'any'}-${rule.to_state}`}
            rule={rule}
            projectKey={projectKey}
            projectDefaultTimeoutMs={projectDefaultTimeout}
            agents={agentsQuery.data ?? []}
            onReorder={handleReorder}
            onToggle={handleToggle}
            onEdit={(hook) => {
              setEditingHook(hook);
              setActiveTransition({ from_state: hook.from_state, to_state: hook.to_state });
              setIsAttachDialogOpen(true);
            }}
            onDetach={handleDetach}
            onAddHook={(transition) => {
              setEditingHook(null);
              setActiveTransition(transition);
              setIsAttachDialogOpen(true);
            }}
            onDryRun={(transition) => {
              setDryRunTransition(transition);
            }}
          />
        ))
      )}

      {/* Git Repository Bindings Section */}
      <GitRepoBindingsSection
        projectKey={projectKey}
        isUserAdmin={isUserAdmin}
      />

      {/* Attach / Edit Hook Dialog */}
      <AttachHookDialog
        isOpen={isAttachDialogOpen}
        projectKey={projectKey}
        initialTransition={activeTransition ?? undefined}
        editingHook={editingHook}
        states={statesQuery.data ?? []}
        agentDefinitions={agentsQuery.data ?? []}
        wasmModules={wasmModulesQuery.data ?? []}
        onSave={handleSaveHook}
        onClose={() => {
          setIsAttachDialogOpen(false);
          setEditingHook(null);
          setActiveTransition(null);
        }}
      />

      {/* Dry-Run Drawer */}
      {dryRunTransition && (
        <DryRunDrawer
          isOpen={Boolean(dryRunTransition)}
          projectKey={projectKey}
          transition={dryRunTransition}
          onClose={() => {
            setDryRunTransition(null);
          }}
        />
      )}


    </div>
  );
}
