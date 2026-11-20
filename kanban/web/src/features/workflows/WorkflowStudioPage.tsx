// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useMemo, type JSX } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { apiFetch } from '../../api/client';
import { ApiProblem } from '../../api/problem';
import { NotFoundView } from '../../app/routes';
import { SecondFactorStep } from '../auth/SecondFactorStep';
import { useAuth } from '../auth/AuthContext';
import type { MfaMethod } from '../auth/authApi';
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
  fetchAgentDefinitions,
  fetchProjectStates,
  fetchApprovedWasmModules,
  type WorkflowHook,
  type CreateWorkflowHookPayload,
  type ReorderHooksPayload,
} from './api';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import './workflows.css';

export interface WorkflowStudioPageProps {
  projectKeyOverride?: string;
  workspaceSlugOverride?: string;
  isAdmin?: boolean;
}

interface PendingMutation {
  type: string;
  execute: () => Promise<void>;
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
        return data as { name?: string; capabilities?: string[] };
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
  const generalError = rulesQuery.error ? rulesQuery.error.message : null;

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

  // AAL2 Step-Up state
  const [aal2Challenge, setAal2Challenge] = useState<{
    challengeId: string;
    methods: MfaMethod[];
  } | null>(null);
  const [pendingMutation, setPendingMutation] = useState<PendingMutation | null>(null);

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
      <main className="workflow-studio" data-testid="workflow-studio-page">
        <div className="empty-hooks-cta">Loading project permissions...</div>
      </main>
    );
  }

  // If user lacks admin permissions, render uniform Not found or no access view (zero write requests)
  if (!isUserAdmin) {
    return <NotFoundView />;
  }

  // Handle AAL2 403 response intercept
  const handleAal2Intercept = (err: unknown, mutation: PendingMutation): boolean => {
    if (err instanceof ApiProblem && err.code === 'AAL2_REQUIRED') {
      setPendingMutation(mutation);
      const data = err.data;
      const challengeId = typeof data.challenge_id === 'string' ? data.challenge_id : 'aal2-stepup';
      const methods = Array.isArray(data.methods)
        ? (data.methods as MfaMethod[])
        : (['webauthn', 'totp'] as MfaMethod[]);
      setAal2Challenge({ challengeId, methods });
      return true;
    }
    return false;
  };

  const handleAal2Success = async () => {
    const mutation = pendingMutation;
    setAal2Challenge(null);
    setPendingMutation(null);
    if (mutation) {
      await mutation.execute();
    }
  };

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
      if (handleAal2Intercept(err, { type: 'reorder', execute: action })) {
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
      if (handleAal2Intercept(err, { type: isEnabled ? 'enable' : 'disable', execute: action })) {
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
      if (handleAal2Intercept(err, { type: 'delete', execute: action })) {
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
      if (handleAal2Intercept(err, { type: editingHook ? 'update' : 'create', execute: action })) {
        return;
      }
      throw err;
    }
  };

  return (
    <main className="workflow-studio" data-testid="workflow-studio-page">
      {/* Studio Header */}
      <header className="workflow-studio-header">
        <h1 className="workflow-studio-title">
          <span>⚙️ Project</span>
          <span className="workflow-studio-title-badge">{projectKey}</span>
          <span>&gt; Scripted Workflows &amp; Transition Helpers</span>
        </h1>
        <div className="workflow-studio-actions">
          <StudioDocLink
            href="/docs/scripted-workflows-and-transition-helpers"
            title="Scripted Workflows &amp; Transition Helpers Documentation"
            testId="workflow-studio-doc-link"
          />
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

      {/* General Alert */}
      {generalError && (
        <div className="workflow-alert workflow-alert-danger" role="alert">
          {generalError}
        </div>
      )}

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
        onAal2Intercept={handleAal2Intercept}
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

      {/* AAL2 Step-Up Modal */}
      {aal2Challenge && (
        <div className="workflow-modal-backdrop" role="presentation">
          <div
            className="workflow-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="aal2-stepup-title"
          >
            <div className="workflow-dialog-header">
              <h2 id="aal2-stepup-title" className="workflow-dialog-title">
                Admin Verification Required (AAL2)
              </h2>
            </div>
            <div className="workflow-dialog-body">
              <SecondFactorStep
                challengeId={aal2Challenge.challengeId}
                methods={aal2Challenge.methods}
                onSuccess={() => {
                  void handleAal2Success();
                }}
                onError={() => {
                  // Handled in SecondFactorStep
                }}
                onSessionExpired={() => {
                  setAal2Challenge(null);
                  setPendingMutation(null);
                }}
                onCancel={() => {
                  setAal2Challenge(null);
                  setPendingMutation(null);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
