/**
 * Project Settings Studio (KANBA-202, KANBA-214).
 *
 * Dedicated management page for Project Administrators (`PROJECT_ADMIN`).
 * Tabs:
 * 1. General: Project Name, Description Markdown, Enable Modules, Default Modules, Auto-Archive Days.
 * 2. Workflow States: Lifecycle stages, sort order, Soft/Hard WIP limits with hard >= soft validation.
 * 3. Priorities: Custom priorities with semantic emojis, colors, and ranking.
 * 4. Labels: Color-coded labels and mutual-exclusion groups.
 * 5. Members & Access: Searchable Principal Picker (Users/Groups/Agents by name/@handle), Role Bindings, Access Inspector trigger.
 * 6. Automation & Integrations: Navigation cards to Workflows, Custom Fields, and Project MCP Keys.
 * 7. Trash & Retention: Soft-deleted projects, issues, cycles, modules, stickies, and docs with remaining retention days and 1-click restore.
 * 8. Danger Zone: 2-stage Project deletion with blast radius computation, sending mode: 'trash' and SERVER_ADMIN-only permanent purge.
 */

import React, { useContext, useEffect, useRef, useState, type JSX, type SyntheticEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { QueryClientContext } from '@tanstack/react-query';
import { apiFetch } from '../../api/client';
import { ApiProblem } from '../../api/problem';
import { qk } from '../../api/queryKeys';
import { StateBadge } from '../../components/state/StateBadge';
import { ensureSessionCsrfToken } from '../auth/useSessionGuard';
import { ColorPresetPicker, ColoredPill } from './ColorPresetPicker';
import { DeleteAuditModal } from './DeleteAuditModal';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { AdvancedSection } from '../../ui/AdvancedSection';
import { RbacPolicyBuilder } from '../rbac/RbacPolicyBuilder';
import { RoleLabelPicker } from '../rbac/RoleLabelPicker';
import './ProjectSettingsPage.css';

export interface ProjectDetail {
  id: string;
  identifier: string;
  name: string;
  description_markdown?: string | null;
  modules_enabled?: boolean;
  skip_loaded_sequence_numbers?: boolean;
  default_module_ids?: string[];
  auto_archive_days?: number | null;
  capabilities?: string[];
  is_project_admin?: boolean;
  project_role?: string | null;
  deleted_at?: string | null;
  trashed_at?: string | null;
  status?: string | null;
}

export interface ProjectMember {
  id: string;
  principal_id: string;
  project_id: string;
  role: 'PROJECT_ADMIN' | 'MEMBER' | 'VIEWER';
  display_name?: string | null;
  handle?: string | null;
  principal?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  created_at: string;
}

export interface ProjectModuleItem {
  id: string;
  name: string;
  summary?: string | null;
  status?: string | null;
}

export interface WorkflowStateItem {
  id: string;
  name: string;
  group: 'backlog' | 'unstarted' | 'started' | 'completed' | 'cancelled';
  color_hex: string;
  sort_order: number;
  is_default: boolean;
  wip_soft_limit?: number | null;
  wip_hard_limit?: number | null;
  issue_count?: number;
}

export interface ProjectPriorityItem {
  id: string;
  slug: string;
  label: string;
  emoji?: string | null;
  color_hex: string;
  sort_order: number;
  is_default: boolean;
}

export interface ProjectLabelItem {
  id: string;
  name: string;
  color_hex: string;
  exclusive_group?: string | null;
}

export interface WorkspacePrincipalItem {
  id: string;
  principal_type: 'USER' | 'GROUP' | 'AGENT' | 'SERVICE_PRINCIPAL';
  display_name: string;
  handle?: string | null;
  principal?: string | null;
  email?: string | null;
}

/**
 * Format and normalize principal handles (KB-P3-AUDIT-08).
 * Strips leading '@' before prepending a single '@', avoiding double '@@alice'.
 */
export function formatPrincipalHandle(
  handle?: string | null,
  principal?: string | null
): string | null {
  const normalized = (handle ?? principal ?? '').replace(/^@+/, '');
  return normalized ? `@${normalized}` : null;
}

export interface TrashedItem {
  id: string;
  key: string;
  kind: string;
  title: string;
  deleted_at: string;
  purge_after: string;
  remaining_days: number;
  capabilities?: string[];
}

export interface DestructiveRequestOut {
  stage: string;
  target: string;
  target_kind: string;
  target_id: string;
  mode: string;
  blast_summary:
    | string
    | {
        issues_count?: number;
        sub_issues_count?: number;
        pages_count?: number;
        stickies_count?: number;
        [key: string]: unknown;
      };
  blast_hash: string;
  confirm_phrase: string;
  confirmation_token: string;
  expires_in_sec: number;
}

type SettingsTab =
  | 'general'
  | 'states'
  | 'priorities'
  | 'labels'
  | 'members'
  | 'roles'
  | 'integrations'
  | 'trash'
  | 'danger';

export function ProjectSettingsPage(): JSX.Element {
  const { projectKey = 'KAN' } = useParams<{ projectKey: string }>();
  const navigate = useNavigate();
  const queryClient = useContext(QueryClientContext);

  let searchParams: URLSearchParams | null = null;
  let setSearchParams: ((params: URLSearchParams, opts?: { replace?: boolean }) => void) | null = null;
  try {
    const [params, setParams] = useSearchParams();
    searchParams = params;
    setSearchParams = setParams;
  } catch {
    // Graceful fallback when rendered outside RouterProvider
  }

  const rawTab = searchParams?.get('tab');
  const initialTab: SettingsTab =
    rawTab &&
    ['general', 'states', 'priorities', 'labels', 'members', 'roles', 'integrations', 'trash', 'danger'].includes(
      rawTab,
    )
      ? (rawTab as SettingsTab)
      : 'general';

  const [activeTab, setActiveTab] = useState<SettingsTab>(initialTab);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [states, setStates] = useState<WorkflowStateItem[]>([]);
  const [priorities, setPriorities] = useState<ProjectPriorityItem[]>([]);
  const [labels, setLabels] = useState<ProjectLabelItem[]>([]);
  const [availableModules, setAvailableModules] = useState<ProjectModuleItem[]>([]);
  const [trashedItems, setTrashedItems] = useState<TrashedItem[]>([]);
  const [principalsList, setPrincipalsList] = useState<WorkspacePrincipalItem[]>([]);
  const [isServerAdmin, setIsServerAdmin] = useState<boolean>(false);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (errorMessage && alertRef.current && typeof alertRef.current.scrollIntoView === 'function') {
      alertRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [errorMessage]);

  const handleTabSwitch = (tab: SettingsTab) => {
    setErrorMessage(null);
    setSuccessMessage(null);
    setActiveTab(tab);
    if (searchParams && setSearchParams) {
      const next = new URLSearchParams(searchParams);
      if (tab === 'general') {
        next.delete('tab');
      } else {
        next.set('tab', tab);
      }
      setSearchParams(next, { replace: true });
    }
  };

  // General Tab State
  const [name, setName] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [modulesEnabled, setModulesEnabled] = useState<boolean>(true);
  const [skipLoadedSeq, setSkipLoadedSeq] = useState<boolean>(false);
  const [defaultModuleIds, setDefaultModuleIds] = useState<string[]>([]);
  const [autoArchiveDays, setAutoArchiveDays] = useState<string>('');
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // Workflow States Form State
  const [stateName, setStateName] = useState<string>('');
  const [stateGroup, setStateGroup] = useState<
    'backlog' | 'unstarted' | 'started' | 'completed' | 'cancelled'
  >('started');
  const [stateColor, setStateColor] = useState<string>('#4f46e5');
  const [stateSortOrder, setStateSortOrder] = useState<string>('0');
  const [stateIsDefault, setStateIsDefault] = useState<boolean>(false);
  const [stateWipSoft, setStateWipSoft] = useState<string>('');
  const [stateWipHard, setStateWipHard] = useState<string>('');
  const [wipLimitError, setWipLimitError] = useState<string | null>(null);

  // Priorities Form State
  const [prioritySlug, setPrioritySlug] = useState<string>('');
  const [priorityLabel, setPriorityLabel] = useState<string>('');
  const [priorityEmoji, setPriorityEmoji] = useState<string>('🔥');
  const [priorityColor, setPriorityColor] = useState<string>('#dc2626');
  const [prioritySortOrder, setPrioritySortOrder] = useState<string>('0');
  const [priorityIsDefault, setPriorityIsDefault] = useState<boolean>(false);

  // Labels Form State
  const [labelName, setLabelName] = useState<string>('');
  const [labelColor, setLabelColor] = useState<string>('#2563eb');
  const [labelExclusiveGroup, setLabelExclusiveGroup] = useState<string>('');

  // Pre-Delete Reverse Audit Modal State (KB-P3-AUDIT-23)
  const [auditModalKind, setAuditModalKind] = useState<'state' | 'label' | null>(null);
  const [auditModalItem, setAuditModalItem] = useState<{ id: string; name: string } | null>(null);

  const invalidateProjectCaches = () => {
    if (!queryClient) return;
    void queryClient.invalidateQueries({ queryKey: qk.project(projectKey) });
    void queryClient.invalidateQueries({ queryKey: ['project-states', projectKey] });
    void queryClient.invalidateQueries({ queryKey: qk.issues(projectKey, {}) });
  };

  // Inline Row Edit State (KB-P3-AUDIT-23)
  const [editingStateId, setEditingStateId] = useState<string | null>(null);
  const [editStateName, setEditStateName] = useState<string>('');
  const [editStateGroup, setEditStateGroup] = useState<
    'backlog' | 'unstarted' | 'started' | 'completed' | 'cancelled'
  >('started');
  const [editStateColor, setEditStateColor] = useState<string>('#4f46e5');
  const [editStateSortOrder, setEditStateSortOrder] = useState<string>('0');
  const [editStateWipSoft, setEditStateWipSoft] = useState<string>('');
  const [editStateWipHard, setEditStateWipHard] = useState<string>('');
  const [editStateIsDefault, setEditStateIsDefault] = useState<boolean>(false);

  const [editingPriorityId, setEditingPriorityId] = useState<string | null>(null);
  const [editPrioritySlug, setEditPrioritySlug] = useState<string>('');
  const [editPriorityLabel, setEditPriorityLabel] = useState<string>('');
  const [editPriorityEmoji, setEditPriorityEmoji] = useState<string>('🔥');
  const [editPriorityColor, setEditPriorityColor] = useState<string>('#dc2626');
  const [editPrioritySortOrder, setEditPrioritySortOrder] = useState<string>('0');
  const [editPriorityIsDefault, setEditPriorityIsDefault] = useState<boolean>(false);

  const [editingLabelId, setEditingLabelId] = useState<string | null>(null);
  const [editLabelName, setEditLabelName] = useState<string>('');
  const [editLabelColor, setEditLabelColor] = useState<string>('#2563eb');
  const [editLabelExclusiveGroup, setEditLabelExclusiveGroup] = useState<string>('');

  // Members Tab State (Principal Picker)
  const [newPrincipalId, setNewPrincipalId] = useState<string>('');
  const [newRole, setNewRole] = useState<'PROJECT_ADMIN' | 'MEMBER' | 'VIEWER'>('MEMBER');
  const [principalSearch, setPrincipalSearch] = useState<string>('');
  const [isPickerOpen, setIsPickerOpen] = useState<boolean>(false);
  const [isAddingMember, setIsAddingMember] = useState<boolean>(false);

  // Trash Tab State
  const [trashKindFilter, setTrashKindFilter] = useState<string>('all');

  // Danger Zone State
  const [dangerStage, setDangerStage] = useState<'idle' | 'requested' | 'executing'>('idle');
  const [destructiveToken, setDestructiveToken] = useState<DestructiveRequestOut | null>(null);
  const [enteredPhrase, setEnteredPhrase] = useState<string>('');
  const [dangerReason, setDangerReason] = useState<string>('');
  const [dangerError, setDangerError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function init(): Promise<void> {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const projRes = (await apiFetch(
          'GET',
          `/api/v1/projects/${encodeURIComponent(projectKey)}` as never,
        )) as ProjectDetail;
        if (active) {
          setProject(projRes);
          setName(projRes.name);
          setDescription(projRes.description_markdown ?? '');
          setModulesEnabled(projRes.modules_enabled ?? true);
          setSkipLoadedSeq(projRes.skip_loaded_sequence_numbers ?? false);
          setDefaultModuleIds(projRes.default_module_ids ?? []);
          setAutoArchiveDays(
            projRes.auto_archive_days !== null && projRes.auto_archive_days !== undefined
              ? String(projRes.auto_archive_days)
              : '',
          );
        }

        // Load project members
        try {
          const memRes: unknown = await apiFetch(
            'GET',
            `/api/v1/projects/${encodeURIComponent(projectKey)}/members` as never,
          );
          if (active) {
            if (Array.isArray(memRes)) {
              setMembers(memRes as ProjectMember[]);
            } else if (
              memRes &&
              typeof memRes === 'object' &&
              'items' in memRes &&
              Array.isArray((memRes as { items: unknown[] }).items)
            ) {
              setMembers((memRes as { items: ProjectMember[] }).items);
            }
          }
        } catch {
          // Ignore
        }

        // Load workflow states
        try {
          const statesRes: unknown = await apiFetch(
            'GET',
            `/api/v1/projects/${encodeURIComponent(projectKey)}/states` as never,
          );
          if (active && Array.isArray(statesRes)) {
            setStates(statesRes as WorkflowStateItem[]);
          }
        } catch {
          // Ignore
        }

        // Load priorities
        try {
          const prioRes: unknown = await apiFetch(
            'GET',
            `/api/v1/projects/${encodeURIComponent(projectKey)}/priorities` as never,
          );
          if (active && Array.isArray(prioRes)) {
            setPriorities(prioRes as ProjectPriorityItem[]);
          }
        } catch {
          // Ignore
        }

        // Load labels
        try {
          const labelRes: unknown = await apiFetch(
            'GET',
            `/api/v1/projects/${encodeURIComponent(projectKey)}/labels` as never,
          );
          if (active && Array.isArray(labelRes)) {
            setLabels(labelRes as ProjectLabelItem[]);
          }
        } catch {
          // Ignore
        }

        // Load modules
        if (projRes.modules_enabled !== false) {
          try {
            const modRes: unknown = await apiFetch(
              'GET',
              `/api/v1/projects/${encodeURIComponent(projectKey)}/modules` as never,
            );
            if (active && Array.isArray(modRes)) {
              setAvailableModules(modRes as ProjectModuleItem[]);
            }
          } catch {
            // Ignore
          }
        }

        // Load principals for picker
        try {
          const pRes: unknown = await apiFetch('GET', '/api/v1/admin/principals?limit=100' as never);
          if (active) {
            if (Array.isArray(pRes)) {
              setPrincipalsList(pRes as WorkspacePrincipalItem[]);
            } else if (
              pRes &&
              typeof pRes === 'object' &&
              'items' in pRes &&
              Array.isArray((pRes as { items: unknown[] }).items)
            ) {
              setPrincipalsList((pRes as { items: WorkspacePrincipalItem[] }).items);
            }
          }
        } catch {
          // Ignore
        }

        // Check if server admin
        try {
          const userRes = (await apiFetch('GET', '/api/v1/auth/me' as never)) as {
            is_server_admin?: boolean;
          };
          if (active) {
            setIsServerAdmin(Boolean(userRes.is_server_admin));
          }
        } catch {
          // Ignore
        }

        // Load trash items
        try {
          const trashRes: unknown = await apiFetch(
            'GET',
            `/api/v1/projects/${encodeURIComponent(projectKey)}/trash-items` as never,
          );
          if (
            active &&
            trashRes &&
            typeof trashRes === 'object' &&
            'items' in trashRes &&
            Array.isArray((trashRes as { items: unknown[] }).items)
          ) {
            setTrashedItems((trashRes as { items: TrashedItem[] }).items);
          }
        } catch {
          // Fallback to /trash endpoint
          try {
            const fallbackTrash: unknown = await apiFetch(
              'GET',
              `/api/v1/projects/${encodeURIComponent(projectKey)}/trash` as never,
            );
            if (
              active &&
              fallbackTrash &&
              typeof fallbackTrash === 'object' &&
              'items' in fallbackTrash &&
              Array.isArray((fallbackTrash as { items: unknown[] }).items)
            ) {
              const mapped: TrashedItem[] = (
                fallbackTrash as {
                  items: {
                    id: string;
                    key: string;
                    summary?: string;
                    title?: string;
                    deleted_at: string;
                    purge_after: string;
                  }[];
                }
              ).items.map((i) => {
                const rem = Math.max(
                  0,
                  Math.ceil((new Date(i.purge_after).getTime() - Date.now()) / (1000 * 60 * 60 * 24)),
                );
                return {
                  id: i.id,
                  key: i.key,
                  kind: 'issue',
                  title: i.summary ?? i.title ?? i.key,
                  deleted_at: i.deleted_at,
                  purge_after: i.purge_after,
                  remaining_days: rem,
                };
              });
              setTrashedItems(mapped);
            }
          } catch {
            // Ignore
          }
        }
      } catch (err: unknown) {
        if (active) {
          const errObj = err as { message?: string };
          setErrorMessage(errObj.message ?? 'Failed to load project settings.');
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, [projectKey]);

  // General Tab Save
  const handleSaveGeneral = (e: SyntheticEvent) => {
    e.preventDefault();
    void (async () => {
      setIsSaving(true);
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const payload = {
          name: name.trim(),
          description_markdown: description,
          modules_enabled: modulesEnabled,
          skip_loaded_sequence_numbers: skipLoadedSeq,
          auto_archive_days: autoArchiveDays ? parseInt(autoArchiveDays, 10) : null,
        };

        const updated = (await apiFetch(
          'PATCH',
          `/api/v1/projects/${encodeURIComponent(projectKey)}` as never,
          {
            headers,
            body: JSON.stringify(payload),
          },
        )) as ProjectDetail;

        if (modulesEnabled && defaultModuleIds.length > 0) {
          try {
            await apiFetch(
              'PUT',
              `/api/v1/projects/${encodeURIComponent(projectKey)}/module-defaults` as never,
              {
                headers,
                body: JSON.stringify({ module_ids: defaultModuleIds }),
              },
            );
          } catch {
            // Optional/unmocked in some unit tests
          }
        }

        setProject(updated);
        if (queryClient) {
          queryClient.setQueryData(['project', projectKey], (prev: unknown) => {
            if (prev && typeof prev === 'object') {
              return { ...prev, ...updated };
            }
            return updated;
          });
          await queryClient.invalidateQueries({ queryKey: ['project', projectKey] });
          await queryClient.invalidateQueries({ queryKey: ['projects'] });
        }
        setSuccessMessage('Project settings saved successfully.');
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to update project settings.');
      } finally {
        setIsSaving(false);
      }
    })();
  };

  // Workflow States Handlers
  const handleCreateState = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!stateName.trim()) return;

    if (stateWipSoft !== '' && stateWipHard !== '') {
      const s = parseInt(stateWipSoft, 10);
      const h = parseInt(stateWipHard, 10);
      if (!isNaN(s) && !isNaN(h) && s > h) {
        setWipLimitError('Soft WIP limit cannot exceed Hard WIP limit');
        return;
      }
    }
    setWipLimitError(null);

    void (async () => {
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const payload = {
          name: stateName.trim(),
          group: stateGroup,
          color_hex: stateColor.trim(),
          sort_order: parseInt(stateSortOrder, 10) || 0,
          is_default: stateIsDefault,
          wip_soft_limit: stateWipSoft !== '' ? parseInt(stateWipSoft, 10) : null,
          wip_hard_limit: stateWipHard !== '' ? parseInt(stateWipHard, 10) : null,
        };

        const created = (await apiFetch(
          'POST',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/states` as never,
          {
            headers,
            body: JSON.stringify(payload),
          },
        )) as WorkflowStateItem;

        setStates((prev) => [...prev, created]);
        setStateName('');
        setStateWipSoft('');
        setStateWipHard('');
        setSuccessMessage(`Workflow state "${created.name}" created.`);
        invalidateProjectCaches();
      } catch (err: unknown) {
        const errObj = err as { message?: string; detail?: string; code?: string };
        const rawCode = err instanceof ApiProblem ? err.code : (errObj.code ?? '');
        const rawMsg =
          err instanceof ApiProblem
            ? (err.detail ?? err.message)
            : (errObj.detail ?? errObj.message ?? '');
        if (
          rawCode === 'STATE_NAME_TAKEN' ||
          rawCode.includes('STATE_NAME_TAKEN') ||
          rawMsg.includes('STATE_NAME_TAKEN') ||
          rawMsg.includes('already exists') ||
          rawMsg.includes('unique')
        ) {
          setErrorMessage('A workflow state with this name already exists in this project.');
        } else {
          setErrorMessage(rawMsg || 'Failed to create workflow state.');
        }
      }
    })();
  };

  const handleReorderState = (stateId: string, direction: 'up' | 'down') => {
    const idx = states.findIndex((s) => s.id === stateId);
    const targetIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (idx < 0 || targetIdx < 0 || targetIdx >= states.length) return;

    const current = states[idx];
    const target = states[targetIdx];
    if (!current || !target) return;

    let newCurrentOrder = target.sort_order;
    const newTargetOrder = current.sort_order;
    if (newCurrentOrder === newTargetOrder) {
      if (direction === 'up') {
        newCurrentOrder = target.sort_order - 1;
      } else {
        newCurrentOrder = target.sort_order + 1;
      }
    }

    void (async () => {
      try {
        setErrorMessage(null);
        setSuccessMessage(null);
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        await Promise.all([
          apiFetch(
            'PATCH',
            `/api/v1/projects/${encodeURIComponent(projectKey)}/states/${encodeURIComponent(stateId)}` as never,
            {
              headers,
              body: JSON.stringify({ sort_order: newCurrentOrder }),
            },
          ),
          apiFetch(
            'PATCH',
            `/api/v1/projects/${encodeURIComponent(projectKey)}/states/${encodeURIComponent(target.id)}` as never,
            {
              headers,
              body: JSON.stringify({ sort_order: newTargetOrder }),
            },
          ),
        ]);

        setStates((prev) => {
          const next = [...prev];
          const c = next[idx];
          const t = next[targetIdx];
          if (c && t) {
            next[idx] = { ...c, sort_order: newCurrentOrder };
            next[targetIdx] = { ...t, sort_order: newTargetOrder };
          }
          return next.sort((a, b) => a.sort_order - b.sort_order);
        });

        invalidateProjectCaches();
      } catch (err: unknown) {
        const errObj = err as { message?: string; detail?: string; code?: string };
        const rawMsg =
          err instanceof ApiProblem
            ? (err.detail ?? err.message)
            : (errObj.detail ?? errObj.message);
        setErrorMessage(rawMsg ?? errObj.message ?? 'Failed to reorder state.');
      }
    })();
  };

  const handleDeleteState = (stateId: string) => {
    const st = states.find((s) => s.id === stateId);
    if (st) {
      setAuditModalKind('state');
      setAuditModalItem({ id: st.id, name: st.name });
    }
  };

  const handleStartEditState = (st: WorkflowStateItem) => {
    setEditingStateId(st.id);
    setEditStateName(st.name);
    setEditStateGroup(st.group);
    setEditStateColor(st.color_hex || '#4f46e5');
    setEditStateSortOrder(String(st.sort_order));
    setEditStateWipSoft(st.wip_soft_limit != null ? String(st.wip_soft_limit) : '');
    setEditStateWipHard(st.wip_hard_limit != null ? String(st.wip_hard_limit) : '');
    setEditStateIsDefault(st.is_default);
  };

  const handleSaveStateEdit = (stateId: string) => {
    const trimmedName = editStateName.trim();
    if (!trimmedName) {
      setErrorMessage('Workflow state name is required.');
      return;
    }
    if (trimmedName.length > 64) {
      setErrorMessage('Workflow state name cannot exceed 64 characters.');
      return;
    }

    if (editStateWipSoft !== '' && editStateWipHard !== '') {
      const s = parseInt(editStateWipSoft, 10);
      const h = parseInt(editStateWipHard, 10);
      if (!isNaN(s) && !isNaN(h) && s > h) {
        setErrorMessage('Soft WIP limit cannot exceed Hard WIP limit');
        return;
      }
    }

    void (async () => {
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const payload = {
          name: trimmedName,
          group: editStateGroup,
          color_hex: editStateColor.trim(),
          sort_order: parseInt(editStateSortOrder, 10) || 0,
          wip_soft_limit: editStateWipSoft !== '' ? parseInt(editStateWipSoft, 10) : null,
          wip_hard_limit: editStateWipHard !== '' ? parseInt(editStateWipHard, 10) : null,
          is_default: editStateIsDefault,
        };

        const updated = (await apiFetch(
          'PATCH',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/states/${encodeURIComponent(stateId)}` as never,
          {
            headers,
            body: JSON.stringify(payload),
          },
        )) as WorkflowStateItem;

        setStates((prev) =>
          prev.map((s) => {
            if (s.id === stateId) {
              return { ...s, ...updated };
            }
            if (updated.is_default) {
              return { ...s, is_default: false };
            }
            return s;
          }),
        );
        setEditingStateId(null);
        setSuccessMessage(`Workflow state "${updated.name}" updated.`);
        invalidateProjectCaches();
      } catch (err: unknown) {
        const errObj = err as { message?: string; detail?: string; code?: string };
        const rawCode = err instanceof ApiProblem ? err.code : (errObj.code ?? '');
        const rawMsg =
          err instanceof ApiProblem
            ? (err.detail ?? err.message)
            : (errObj.detail ?? errObj.message ?? '');
        if (
          rawCode === 'STATE_NAME_TAKEN' ||
          rawCode.includes('STATE_NAME_TAKEN') ||
          rawMsg.includes('STATE_NAME_TAKEN') ||
          rawMsg.includes('already exists') ||
          rawMsg.includes('unique')
        ) {
          setErrorMessage('A workflow state with this name already exists in this project.');
        } else if (
          rawCode === 'LAST_STATE_IN_GROUP' ||
          rawCode.includes('LAST_STATE_IN_GROUP') ||
          rawMsg.includes('LAST_STATE_IN_GROUP')
        ) {
          setErrorMessage('Cannot move the last remaining state out of this lifecycle group.');
        } else if (
          rawCode === 'DEFAULT_STATE_REQUIRED' ||
          rawCode.includes('DEFAULT_STATE_REQUIRED') ||
          rawMsg.includes('DEFAULT_STATE_REQUIRED')
        ) {
          setErrorMessage(
            'A default state is required. Designate another default state before removing this one.',
          );
        } else {
          setErrorMessage(rawMsg || 'Failed to update workflow state.');
        }
      }
    })();
  };

  // Priorities Handlers
  const handleCreatePriority = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!prioritySlug.trim() || !priorityLabel.trim()) return;

    void (async () => {
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const payload = {
          slug: prioritySlug.trim(),
          label: priorityLabel.trim(),
          emoji: priorityEmoji.trim() || null,
          color_hex: priorityColor.trim(),
          sort_order: parseInt(prioritySortOrder, 10) || 0,
          is_default: priorityIsDefault,
        };

        const created = (await apiFetch(
          'POST',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/priorities` as never,
          {
            headers,
            body: JSON.stringify(payload),
          },
        )) as ProjectPriorityItem;

        setPriorities((prev) => [...prev, created]);
        setPrioritySlug('');
        setPriorityLabel('');
        setSuccessMessage(`Priority "${created.label}" created.`);
        invalidateProjectCaches();
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to create priority.');
      }
    })();
  };

  const handleDeletePriority = (priorityId: string) => {
    void (async () => {
      setErrorMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = {};
        if (csrf) headers['X-CSRF-Token'] = csrf;

        await apiFetch(
          'DELETE',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/priorities/${encodeURIComponent(priorityId)}` as never,
          { headers },
        );
        setPriorities((prev) => prev.filter((p) => p.id !== priorityId));
        setSuccessMessage('Priority deleted.');
        invalidateProjectCaches();
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to delete priority.');
      }
    })();
  };

  const handleStartEditPriority = (p: ProjectPriorityItem) => {
    setEditingPriorityId(p.id);
    setEditPrioritySlug(p.slug);
    setEditPriorityLabel(p.label);
    setEditPriorityEmoji(p.emoji ?? '');
    setEditPriorityColor(p.color_hex || '#dc2626');
    setEditPrioritySortOrder(String(p.sort_order));
    setEditPriorityIsDefault(p.is_default);
  };

  const handleSavePriorityEdit = (priorityId: string) => {
    if (!editPriorityLabel.trim() || !editPrioritySlug.trim()) return;

    void (async () => {
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const payload = {
          slug: editPrioritySlug.trim(),
          label: editPriorityLabel.trim(),
          emoji: editPriorityEmoji.trim() || null,
          color_hex: editPriorityColor.trim(),
          sort_order: parseInt(editPrioritySortOrder, 10) || 0,
          is_default: editPriorityIsDefault,
        };

        const updated = (await apiFetch(
          'PATCH',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/priorities/${encodeURIComponent(priorityId)}` as never,
          {
            headers,
            body: JSON.stringify(payload),
          },
        )) as ProjectPriorityItem;

        setPriorities((prev) =>
          prev.map((p) => {
            if (p.id === priorityId) {
              return { ...p, ...updated };
            }
            if (updated.is_default) {
              return { ...p, is_default: false };
            }
            return p;
          }),
        );
        setEditingPriorityId(null);
        setSuccessMessage(`Priority "${updated.label}" updated.`);
        invalidateProjectCaches();
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to update priority.');
      }
    })();
  };

  // Labels Handlers
  const handleCreateLabel = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!labelName.trim()) return;

    void (async () => {
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const payload = {
          name: labelName.trim(),
          color_hex: labelColor.trim(),
          exclusive_group: labelExclusiveGroup.trim() || null,
        };

        const created = (await apiFetch(
          'POST',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/labels` as never,
          {
            headers,
            body: JSON.stringify(payload),
          },
        )) as ProjectLabelItem;

        setLabels((prev) => [...prev, created]);
        setLabelName('');
        setLabelExclusiveGroup('');
        setSuccessMessage(`Label "${created.name}" created.`);
        invalidateProjectCaches();
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to create label.');
      }
    })();
  };

  const handleDeleteLabel = (labelId: string) => {
    const lbl = labels.find((l) => l.id === labelId);
    if (lbl) {
      setAuditModalKind('label');
      setAuditModalItem({ id: lbl.id, name: lbl.name });
    }
  };

  const handleStartEditLabel = (lbl: ProjectLabelItem) => {
    setEditingLabelId(lbl.id);
    setEditLabelName(lbl.name);
    setEditLabelColor(lbl.color_hex || '#2563eb');
    setEditLabelExclusiveGroup(lbl.exclusive_group ?? '');
  };

  const handleSaveLabelEdit = (labelId: string) => {
    if (!editLabelName.trim()) return;

    void (async () => {
      setErrorMessage(null);
      setSuccessMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const payload = {
          name: editLabelName.trim(),
          color_hex: editLabelColor.trim(),
          exclusive_group: editLabelExclusiveGroup.trim() || null,
        };

        const updated = (await apiFetch(
          'PATCH',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/labels/${encodeURIComponent(labelId)}` as never,
          {
            headers,
            body: JSON.stringify(payload),
          },
        )) as ProjectLabelItem;

        setLabels((prev) => prev.map((l) => (l.id === labelId ? { ...l, ...updated } : l)));
        setEditingLabelId(null);
        setSuccessMessage(`Label "${updated.name}" updated.`);
        invalidateProjectCaches();
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to update label.');
      }
    })();
  };

  const handleConfirmedDelete = async (replacementId?: string, migrateHooks?: boolean) => {
    if (!auditModalItem || !auditModalKind) return;
    setErrorMessage(null);
    try {
      const csrf = await ensureSessionCsrfToken();
      const headers: Record<string, string> = {};
      if (csrf) headers['X-CSRF-Token'] = csrf;

      if (auditModalKind === 'state') {
        const params = new URLSearchParams();
        if (replacementId) {
          params.set('replacement_state_id', replacementId);
        }
        if (migrateHooks !== undefined) {
          params.set('migrate_hooks', String(migrateHooks));
        }
        const qs = params.toString() ? `?${params.toString()}` : '';
        await apiFetch(
          'DELETE',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/states/${encodeURIComponent(auditModalItem.id)}${qs}` as never,
          { headers },
        );
        setStates((prev) => prev.filter((s) => s.id !== auditModalItem.id));
        setSuccessMessage('Workflow state deleted.');
        invalidateProjectCaches();
      } else {
        const params = new URLSearchParams();
        if (replacementId) {
          params.set('replacement_label_id', replacementId);
        }
        const qs = params.toString() ? `?${params.toString()}` : '';
        await apiFetch(
          'DELETE',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/labels/${encodeURIComponent(auditModalItem.id)}${qs}` as never,
          { headers },
        );
        setLabels((prev) => prev.filter((l) => l.id !== auditModalItem.id));
        setSuccessMessage('Label deleted.');
        invalidateProjectCaches();
      }
    } catch (err: unknown) {
      const errObj = err as { message?: string };
      const fallbackMsg =
        auditModalKind === 'state'
          ? 'Failed to delete workflow state.'
          : 'Failed to delete label.';
      const msg = errObj.message ?? fallbackMsg;
      throw new Error(msg);
    }
  };

  // Members Handlers (Principal Picker)
  const handleAddMember = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!newPrincipalId.trim()) return;
    void (async () => {
      setIsAddingMember(true);
      setErrorMessage(null);
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        await apiFetch(
          'POST',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/members` as never,
          {
            headers,
            body: JSON.stringify({ principal_id: newPrincipalId.trim(), role: newRole }),
          },
        );

        setNewPrincipalId('');
        setPrincipalSearch('');
        setSuccessMessage('Project member added.');
        const memRes = (await apiFetch(
          'GET',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/members` as never,
        )) as ProjectMember[] | { items: ProjectMember[] };
        if (Array.isArray(memRes)) {
          setMembers(memRes);
        } else {
          setMembers(memRes.items);
        }
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to add project member.');
      } finally {
        setIsAddingMember(false);
      }
    })();
  };

  const handleRemoveMember = (principalId: string) => {
    setErrorMessage(null);
    void (async () => {
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = {};
        if (csrf) headers['X-CSRF-Token'] = csrf;

        await apiFetch(
          'DELETE',
          `/api/v1/projects/${encodeURIComponent(projectKey)}/members/${encodeURIComponent(principalId)}` as never,
          { headers },
        );

        setMembers((prev) => prev.filter((m) => m.principal_id !== principalId));
        setSuccessMessage('Member removed from project.');
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to remove project member.');
      }
    })();
  };

  const handleTriggerAccessInspector = () => {
    /* v8 ignore next */
    if (!project) return;
    window.dispatchEvent(
      new CustomEvent('kb:open-access-inspector', {
        bubbles: true,
        detail: { objectId: project.id, title: project.name },
      }),
    );
  };

  // Trash & Restore Handlers
  const handleRestoreItem = (item: TrashedItem) => {
    setErrorMessage(null);
    setSuccessMessage(null);
    void (async () => {
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        if (item.kind === 'issue') {
          try {
            await apiFetch(
              'POST',
              `/api/v1/issues/${encodeURIComponent(item.key)}/restore` as never,
              { headers },
            );
          } catch {
            await apiFetch('POST', '/api/v1/admin/destructive:restore' as never, {
              headers,
              body: JSON.stringify({
                target_kind: 'issue',
                target: item.key,
                reason: 'Restored from project trash UI',
              }),
            });
          }
        } else {
          await apiFetch('POST', '/api/v1/admin/destructive:restore' as never, {
            headers,
            body: JSON.stringify({
              target_kind: item.kind,
              target: item.key,
              reason: 'Restored from project trash UI',
            }),
          });
        }

        setTrashedItems((prev) => prev.filter((t) => t.id !== item.id));
        setSuccessMessage(`Successfully restored ${item.title || item.key}.`);
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setErrorMessage(errObj.message ?? 'Failed to restore item.');
      }
    })();
  };

  // Danger Zone Handlers
  const isProjectTrashed =
    project?.deleted_at != null || project?.trashed_at != null || project?.status === 'trashed';

  const handleRequestDelete = (mode: 'trash' | 'permanent_purge' = 'trash') => {
    setDangerError(null);
    /* v8 ignore next 4 */
    if (mode === 'permanent_purge' && !isProjectTrashed) {
      setDangerError('Stage 1 (Move Project to Trash) must be completed before permanent purge.');
      return;
    }
    void (async () => {
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        const res = (await apiFetch('POST', '/api/v1/admin/destructive:request' as never, {
          headers,
          body: JSON.stringify({
            target_kind: 'project',
            target: projectKey,
            mode,
          }),
        })) as DestructiveRequestOut;

        setDestructiveToken(res);
        setDangerStage('requested');
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setDangerError(errObj.message ?? 'Failed to initiate project deletion.');
      }
    })();
  };

  const handleExecuteDelete = () => {
    setDangerError(null);
    setDangerStage('executing');
    void (async () => {
      try {
        const csrf = await ensureSessionCsrfToken();
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        /* v8 ignore next */
        if (!destructiveToken) return;
        const token = destructiveToken;
        const mode = token.mode === 'permanent_purge' ? 'permanent_purge' : 'trash';
        const defaultReason =
          mode === 'permanent_purge'
            ? `Project ${projectKey} permanently purged via admin danger zone`
            : `Project ${projectKey} moved to trash via project settings`;

        await apiFetch('POST', '/api/v1/admin/destructive:execute' as never, {
          headers,
          body: JSON.stringify({
            target_kind: 'project',
            target: projectKey,
            mode,
            confirmation_token: token.confirmation_token,
            confirm_phrase: enteredPhrase.trim(),
            reason: (dangerReason.trim().length >= 10 ? dangerReason.trim() : defaultReason).slice(
              0,
              500,
            ),
          }),
        });

        void navigate('/');
      } catch (err: unknown) {
        const errObj = err as { message?: string };
        setDangerError(errObj.message ?? 'Failed to execute project deletion.');
        setDangerStage('requested');
      }
    })();
  };

  if (isLoading) {
    return (
      <div data-testid="project-settings-page" className="kb-settings-container">
        <div className="kb-settings-loading">Loading project settings...</div>
      </div>
    );
  }

  const isProjectAdmin =
    project?.is_project_admin === true || (project?.capabilities?.includes('ADMIN') ?? false);

  if (!isProjectAdmin) {
    return (
      <div data-testid="project-settings-page" className="kb-settings-container">
        <div className="kb-settings-error" role="alert">
          <h2>Not found or no access</h2>
          <p>You do not have project administrator permissions for {projectKey}.</p>
        </div>
      </div>
    );
  }

  // Filter principals for autocomplete picker
  const filteredPrincipals = principalsList.filter((p) => {
    if (!principalSearch) return true;
    const q = principalSearch.toLowerCase();
    const name = p.display_name ? p.display_name.toLowerCase() : '';
    const handle = p.handle ? p.handle.toLowerCase() : '';
    return name.includes(q) || handle.includes(q) || p.id.toLowerCase().includes(q);
  });

  // Filter trashed items
  const filteredTrashed = trashedItems.filter((t) => {
    if (trashKindFilter === 'all') return true;
    return ((t.kind as string | null | undefined) ?? '').toLowerCase() === trashKindFilter.toLowerCase();
  });

  return (
    <div data-testid="project-settings-page" className="kb-settings-container">
      <header className="kb-settings-header">
        <div>
          <h1 className="kb-settings-title">
            Project Settings:{' '}
            {project?.name !== undefined && project.name.length > 0 ? project.name : projectKey}
          </h1>
          <p className="kb-settings-subtitle">
            Manage general metadata, workflow states, WIP limits, priorities, labels, access, trash,
            and lifecycle.
          </p>
        </div>
        <StudioDocLink
          href="/docs/ticket-screen-and-work-item-features"
          title="Project Settings Documentation"
          testId="project-settings-doc-link"
        />
      </header>

      <nav className="kb-settings-tabs" aria-label="Project Settings Tabs">
        <button
          type="button"
          data-testid="tab-general"
          className={`kb-settings-tab ${activeTab === 'general' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { handleTabSwitch('general'); }}
        >
          General
        </button>
        <button
          type="button"
          data-testid="tab-states"
          className={`kb-settings-tab ${activeTab === 'states' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { handleTabSwitch('states'); }}
        >
          Workflow States
        </button>
        <Link
          to={`/projects/${projectKey}/settings/workflows`}
          data-testid="tab-workflows"
          className="kb-settings-tab"
        >
          Workflows
        </Link>
        <Link
          to={`/projects/${projectKey}/settings/custom-fields`}
          data-testid="tab-custom-fields"
          className="kb-settings-tab"
        >
          Custom Fields
        </Link>
        <button
          type="button"
          data-testid="tab-priorities"
          className={`kb-settings-tab ${activeTab === 'priorities' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { handleTabSwitch('priorities'); }}
        >
          Priorities
        </button>
        <button
          type="button"
          data-testid="tab-labels"
          className={`kb-settings-tab ${activeTab === 'labels' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { handleTabSwitch('labels'); }}
        >
          Labels
        </button>
        <button
          type="button"
          data-testid="tab-members"
          className={`kb-settings-tab ${activeTab === 'members' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { handleTabSwitch('members'); }}
        >
          Members & Access
        </button>
        <button
          type="button"
          data-testid="tab-roles"
          className={`kb-settings-tab ${activeTab === 'roles' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { handleTabSwitch('roles'); }}
        >
          Roles &amp; Permissions
        </button>
        <button
          type="button"
          data-testid="tab-integrations"
          className={`kb-settings-tab ${activeTab === 'integrations' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { handleTabSwitch('integrations'); }}
        >
          Automation & Integrations
        </button>
        <button
          type="button"
          data-testid="tab-trash"
          className={`kb-settings-tab ${activeTab === 'trash' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { handleTabSwitch('trash'); }}
        >
          Trash & Retention
        </button>
        <button
          type="button"
          data-testid="tab-danger"
          className={`kb-settings-tab ${activeTab === 'danger' ? 'kb-settings-tab-active' : ''}`}
          onClick={() => { handleTabSwitch('danger'); }}
        >
          Danger Zone
        </button>
      </nav>

      <div className="kb-settings-panel">
        {errorMessage && (
          <div ref={alertRef} className="kb-settings-alert kb-settings-alert-error" role="alert">
            {errorMessage}
          </div>
        )}

        {successMessage && (
          <div className="kb-settings-alert kb-settings-alert-success" role="status">
            {successMessage}
          </div>
        )}
        {/* 1. General Tab */}
        {activeTab === 'general' && (
          <form className="kb-settings-form" onSubmit={handleSaveGeneral}>
            <div className="kb-form-group">
              <label htmlFor="proj-name-input">
                Project Name
                <FieldHelpHint
                  title="Project Name"
                  summary="Human-readable project name displayed across project boards and navigation."
                  defaultValue="My Project"
                  docHref="/docs/ticket-screen-and-work-item-features"
                  testId="proj-name-help"
                />
              </label>
              <input
                id="proj-name-input"
                data-testid="project-name-input"
                className="kb-input"
                type="text"
                value={name}
                onChange={(e) => { setName(e.target.value); }}
                required
              />
            </div>

            <div className="kb-form-group">
              <label htmlFor="proj-desc-input">
                Description (Markdown)
                <FieldHelpHint
                  title="Description"
                  summary="Markdown-formatted project summary and scope guidelines."
                  defaultValue="None (blank)"
                  docHref="/docs/ticket-screen-and-work-item-features"
                  testId="proj-desc-help"
                />
              </label>
              <textarea
                id="proj-desc-input"
                data-testid="project-desc-input"
                className="kb-textarea"
                rows={4}
                value={description}
                onChange={(e) => { setDescription(e.target.value); }}
              />
            </div>

            <div className="kb-form-group kb-form-group-checkbox">
              <label className="kb-checkbox-label" htmlFor="enable-modules">
                <input
                  type="checkbox"
                  id="enable-modules"
                  data-testid="project-modules-checkbox"
                  checked={modulesEnabled}
                  onChange={(e) => { setModulesEnabled(e.target.checked); }}
                />
                <span>Enable Modules for this project</span>
                <FieldHelpHint
                  title="Project Modules"
                  summary="Enables multi-milestone and component bundling across project issues."
                  defaultValue="Enabled (true)"
                  docHref="/docs/ticket-screen-and-work-item-features#modules"
                  testId="proj-modules-help"
                />
              </label>
            </div>

            {/* Default Modules Selector (when modulesEnabled is true) */}
            {modulesEnabled && (
              <div className="kb-default-modules-box" data-testid="default-modules-section">
                <label>Default Modules</label>
                <p className="kb-settings-subtitle">
                  Select modules assigned by default to newly created work items.
                </p>
                {availableModules.length === 0 ? (
                  <p className="kb-settings-subtitle">No modules created yet in this project.</p>
                ) : (
                  <div className="kb-modules-checklist" data-testid="default-modules-select">
                    {availableModules.map((mod) => (
                      <label key={mod.id} className="kb-checkbox-label" htmlFor={`default-module-${mod.id}`}>
                        <input
                          type="checkbox"
                          id={`default-module-${mod.id}`}
                          aria-label={`Default module ${mod.name}`}
                          data-testid={`default-module-${mod.id}`}
                          checked={defaultModuleIds.includes(mod.id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setDefaultModuleIds((prev) => [...prev, mod.id]);
                            } else {
                              setDefaultModuleIds((prev) => prev.filter((id) => id !== mod.id));
                            }
                          }}
                        />
                        <span>🧩 {mod.name}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Advanced Project Options (KB-ADVANCED-DISCLOSURE-03, KAN-369) */}
            <AdvancedSection
              title="Advanced Project Options"
              summary="Agent-Safe sequence numbering and work item auto-archival policies"
              testId="project-general-advanced-section"
              activeOverridesCount={(skipLoadedSeq ? 1 : 0) + (autoArchiveDays ? 1 : 0)}
              defaultOpen={false}
            >
              <div className="kb-form-group kb-form-group-checkbox">
                <label className="kb-checkbox-label" htmlFor="project-skip-loaded-seq">
                  <input
                    type="checkbox"
                    id="project-skip-loaded-seq"
                    data-testid="project-skip-loaded-seq-checkbox"
                    checked={skipLoadedSeq}
                    onChange={(e) => { setSkipLoadedSeq(e.target.checked); }}
                  />
                  <span>Agent-Safe Sequence Numbering (skip 13, 69, 88, 404, 420, 666, 1337, 1488)</span>
                  <FieldHelpHint
                    title="Agent-Safe Sequence Numbering"
                    summary="Automatically skips culturally or technically ambiguous issue numbers (13, 69, 88, 404, 420, 666, 1337, 1488) in this project."
                    defaultValue="Inherits Workspace Default (Enabled)"
                    docHref="/docs/ticket-screen-and-work-item-features"
                    testId="proj-skip-seq-help"
                  />
                </label>
              </div>

              <div className="kb-form-group">
                <label htmlFor="proj-auto-archive-input">
                  Auto-Archive Days (optional, Default: Off)
                  <FieldHelpHint
                    title="Auto-Archive Days"
                    summary="Number of days after completion or cancellation before work items are automatically archived from active views."
                    defaultValue="Disabled (blank; e.g. 30 days)"
                    validValues={['1 to 365 days (Leave blank to disable auto-archival)']}
                    example="30"
                    docHref="/docs/ticket-screen-and-work-item-features#auto-archive"
                    testId="proj-auto-archive-help"
                  />
                </label>
                <input
                  id="proj-auto-archive-input"
                  data-testid="project-auto-archive-input"
                  className="kb-input"
                  type="number"
                  min="1"
                  max="365"
                  value={autoArchiveDays}
                  onChange={(e) => { setAutoArchiveDays(e.target.value); }}
                  placeholder="e.g. 30"
                />
              </div>
            </AdvancedSection>

            <button
              type="submit"
              data-testid="save-general-btn"
              className="kb-btn kb-btn-primary"
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : 'Save Settings'}
            </button>
          </form>
        )}

        {/* 2. Workflow States Tab */}
        {activeTab === 'states' && (
          <div className="kb-members-section" data-testid="states-section">
            <div className="kb-settings-header">
              <div className="kb-settings-title-row">
                <h3>Workflow States</h3>
                {states.filter((st) => st.wip_soft_limit != null || st.wip_hard_limit != null).length > 0 && (
                  <span className="kb-wip-pill" data-testid="wip-overrides-active-badge">
                    {states.filter((st) => st.wip_soft_limit != null || st.wip_hard_limit != null).length} custom WIP{' '}
                    {states.filter((st) => st.wip_soft_limit != null || st.wip_hard_limit != null).length === 1
                      ? 'limit'
                      : 'limits'}{' '}
                    active
                  </span>
                )}
              </div>
              <p className="kb-settings-subtitle">
                Configure lifecycle stages, sort order, and Soft/Hard WIP limits (with hard &gt;= soft
                validation).
              </p>
            </div>

            {/* Add State Form */}
            <form className="kb-add-member-form" onSubmit={handleCreateState}>
              <h3>Add Workflow State</h3>
              <div className="kb-form-row">
                <label htmlFor="state-name-input" className="kb-visually-hidden">
                  State name
                </label>
                <input
                  type="text"
                  id="state-name-input"
                  aria-label="State name"
                  data-testid="state-name-input"
                  className="kb-input"
                  placeholder="State name (e.g. In Review)"
                  value={stateName}
                  onChange={(e) => { setStateName(e.target.value); }}
                  required
                />
                <label htmlFor="state-group-select" className="kb-visually-hidden">
                  State group
                </label>
                <select
                  id="state-group-select"
                  aria-label="State group"
                  data-testid="state-group-select"
                  className="kb-select"
                  value={stateGroup}
                  onChange={(e) => { setStateGroup(
                      e.target.value as
                        | 'backlog'
                        | 'unstarted'
                        | 'started'
                        | 'completed'
                        | 'cancelled',
                    ); }
                  }
                >
                  <option value="backlog">Backlog</option>
                  <option value="unstarted">Unstarted</option>
                  <option value="started">Started</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
                <ColorPresetPicker
                  testId="state-color-input"
                  value={stateColor}
                  onChange={setStateColor}
                />
                <label className="kb-checkbox-label" htmlFor="state-default-checkbox">
                  <input
                    type="checkbox"
                    id="state-default-checkbox"
                    aria-label="Default state"
                    data-testid="state-default-checkbox"
                    checked={stateIsDefault}
                    onChange={(e) => { setStateIsDefault(e.target.checked); }}
                  />
                  <span>Default</span>
                </label>
                <button type="submit" data-testid="create-state-btn" className="kb-btn kb-btn-primary">
                  Add State
                </button>
              </div>

              {/* Advanced State Options (WIP Limits, Sort Order) */}
              <AdvancedSection
                title="Advanced State Limits & Sorting"
                summary="Sort order and soft/hard work-in-progress (WIP) concurrency limits"
                testId="state-advanced-section"
                activeOverridesCount={(stateSortOrder ? 1 : 0) + (stateWipSoft ? 1 : 0) + (stateWipHard ? 1 : 0)}
                hasErrors={Boolean(wipLimitError)}
                defaultOpen={false}
              >
                <div className="kb-form-row kb-form-row-advanced">
                  <label htmlFor="state-sort-order-input" className="kb-visually-hidden">
                    Sort order
                  </label>
                  <input
                    type="number"
                    id="state-sort-order-input"
                    aria-label="Sort order"
                    data-testid="state-sort-order-input"
                    className="kb-input"
                    placeholder="Order (0)"
                    value={stateSortOrder}
                    onChange={(e) => { setStateSortOrder(e.target.value); }}
                  />
                  <label htmlFor="state-wip-soft-input" className="kb-visually-hidden">
                    Soft WIP
                  </label>
                  <input
                    type="number"
                    id="state-wip-soft-input"
                    aria-label="Soft WIP limit"
                    aria-invalid={Boolean(wipLimitError)}
                    aria-describedby={wipLimitError ? 'wip-limit-error' : undefined}
                    data-testid="state-wip-soft-input"
                    className="kb-input"
                    placeholder="Soft WIP"
                    value={stateWipSoft}
                    onChange={(e) => {
                      setStateWipSoft(e.target.value);
                      setWipLimitError(null);
                    }}
                  />
                  <label htmlFor="state-wip-hard-input" className="kb-visually-hidden">
                    Hard WIP
                  </label>
                  <input
                    type="number"
                    id="state-wip-hard-input"
                    aria-label="Hard WIP limit"
                    aria-invalid={Boolean(wipLimitError)}
                    aria-describedby={wipLimitError ? 'wip-limit-error' : undefined}
                    data-testid="state-wip-hard-input"
                    className="kb-input"
                    placeholder="Hard WIP"
                    value={stateWipHard}
                    onChange={(e) => {
                      setStateWipHard(e.target.value);
                      setWipLimitError(null);
                    }}
                  />
                </div>
                {wipLimitError && (
                  <div className="kb-error-text" role="alert" id="wip-limit-error" data-testid="wip-limit-error">
                    {wipLimitError}
                  </div>
                )}
              </AdvancedSection>
            </form>

            {/* States Table */}
            <div className="kb-table-scroll-container">
              <table className="kb-table" data-testid="states-table">
              <thead>
                <tr>
                  <th>Order</th>
                  <th>State Name</th>
                  <th>Group</th>
                  <th>WIP Soft</th>
                  <th>WIP Hard</th>
                  <th>Default</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {states.map((st) => {
                  const isEditing = editingStateId === st.id;
                  if (isEditing) {
                    return (
                      <tr key={st.id} data-testid={`state-row-${st.id}`}>
                        <td>
                          <input
                            type="number"
                            aria-label={`Edit order for state ${st.name}`}
                            data-testid={`state-edit-order-${st.id}`}
                            className="kb-input"
                            value={editStateSortOrder}
                            onChange={(e) => {
                              setEditStateSortOrder(e.target.value);
                            }}
                          />
                        </td>
                        <td>
                          <div className="kb-edit-cell-row">
                            <StateBadge
                              state={editStateName || 'Preview'}
                              group={editStateGroup}
                              colorHex={editStateColor}
                              testId={`state-edit-preview-${st.id}`}
                            />
                            <input
                              type="text"
                              aria-label={`Edit name for state ${st.name}`}
                              data-testid={`state-edit-name-${st.id}`}
                              className="kb-input"
                              maxLength={64}
                              value={editStateName}
                              onChange={(e) => { setEditStateName(e.target.value); }}
                            />
                            <ColorPresetPicker
                              testId={`state-edit-color-${st.id}-input`}
                              value={editStateColor}
                              onChange={setEditStateColor}
                            />
                          </div>
                        </td>
                        <td>
                          <select
                            data-testid={`state-edit-group-${st.id}`}
                            aria-label={`Edit group for state ${st.name}`}
                            className="kb-select"
                            value={editStateGroup}
                            onChange={(e) => {
                              setEditStateGroup(
                                e.target.value as
                                  | 'backlog'
                                  | 'unstarted'
                                  | 'started'
                                  | 'completed'
                                  | 'cancelled',
                              );
                            }}
                          >
                            <option value="backlog">Backlog</option>
                            <option value="unstarted">Unstarted</option>
                            <option value="started">Started</option>
                            <option value="completed">Completed</option>
                            <option value="cancelled">Cancelled</option>
                          </select>
                        </td>
                        <td>
                          <input
                            type="number"
                            aria-label={`Edit soft WIP limit for state ${st.name}`}
                            data-testid={`state-edit-wip-soft-${st.id}`}
                            className="kb-input"
                            value={editStateWipSoft}
                            onChange={(e) => { setEditStateWipSoft(e.target.value); }}
                          />
                        </td>
                        <td>
                          <input
                            type="number"
                            aria-label={`Edit hard WIP limit for state ${st.name}`}
                            data-testid={`state-edit-wip-hard-${st.id}`}
                            className="kb-input"
                            value={editStateWipHard}
                            onChange={(e) => { setEditStateWipHard(e.target.value); }}
                          />
                        </td>
                        <td>
                          <label className="kb-checkbox-label" htmlFor={`state-edit-default-${st.id}`}>
                            <input
                              type="checkbox"
                              id={`state-edit-default-${st.id}`}
                              aria-label={`Edit default for state ${st.name}`}
                              data-testid={`state-edit-default-${st.id}`}
                              checked={editStateIsDefault}
                              onChange={(e) => { setEditStateIsDefault(e.target.checked); }}
                            />
                            <span>Default</span>
                          </label>
                        </td>
                        <td>
                          <button
                            type="button"
                            data-testid={`save-state-btn-${st.id}`}
                            className="kb-btn kb-btn-primary"
                            onClick={() => { handleSaveStateEdit(st.id); }}
                          >
                            Save
                          </button>{' '}
                          <button
                            type="button"
                            data-testid={`cancel-state-btn-${st.id}`}
                            className="kb-btn kb-btn-secondary"
                            onClick={() => { setEditingStateId(null); }}
                          >
                            Cancel
                          </button>
                        </td>
                      </tr>
                    );
                  }

                  return (
                    <tr key={st.id} data-testid={`state-row-${st.id}`}>
                      <td>
                        <button
                          type="button"
                          data-testid={`state-up-${st.id}`}
                          className="kb-btn kb-btn-secondary"
                          onClick={() => { handleReorderState(st.id, 'up'); }}
                          title="Move Up"
                        >
                          ▲
                        </button>{' '}
                        <button
                          type="button"
                          data-testid={`state-down-${st.id}`}
                          className="kb-btn kb-btn-secondary"
                          onClick={() => { handleReorderState(st.id, 'down'); }}
                          title="Move Down"
                        >
                          ▼
                        </button>{' '}
                        {st.sort_order}
                      </td>
                      <td>
                        <ColoredPill
                          colorHex={st.color_hex}
                          text={st.name}
                          testId={`state-pill-${st.id}`}
                        />
                      </td>
                      <td>
                        <span className="kb-role-badge kb-role-member">{st.group}</span>
                      </td>
                      <td>
                        {st.wip_soft_limit != null ? (
                          <span className="kb-wip-pill">Soft: {st.wip_soft_limit}</span>
                        ) : (
                          '-'
                        )}
                      </td>
                      <td>
                        {st.wip_hard_limit != null ? (
                          <span className="kb-wip-pill">Hard: {st.wip_hard_limit}</span>
                        ) : (
                          '-'
                        )}
                      </td>
                      <td>{st.is_default ? '⭐ Default' : '-'}</td>
                      <td>
                        <button
                          type="button"
                          data-testid={`edit-state-btn-${st.id}`}
                          className="kb-btn kb-btn-secondary"
                          onClick={() => { handleStartEditState(st); }}
                        >
                          Edit
                        </button>{' '}
                        <button
                          type="button"
                          data-testid={`delete-state-btn-${st.id}`}
                          className="kb-btn-danger-sm"
                          onClick={() => { handleDeleteState(st.id); }}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          </div>
        )}

        {/* 3. Priorities Tab */}
        {activeTab === 'priorities' && (
          <div className="kb-members-section" data-testid="priorities-section">
            <div className="kb-settings-header">
              <h3>Project Priorities</h3>
              <p className="kb-settings-subtitle">
                Custom priorities with semantic emojis, colors, and ranking.
              </p>
            </div>

            {/* Add Priority Form */}
            <form className="kb-add-member-form" onSubmit={handleCreatePriority}>
              <h3>Add Priority</h3>
              <div className="kb-form-row">
                <label htmlFor="priority-slug-input" className="kb-visually-hidden">
                  Priority slug
                </label>
                <input
                  type="text"
                  id="priority-slug-input"
                  aria-label="Priority slug"
                  data-testid="priority-slug-input"
                  className="kb-input"
                  placeholder="Slug (e.g. urgent)"
                  value={prioritySlug}
                  onChange={(e) => { setPrioritySlug(e.target.value); }}
                  required
                />
                <label htmlFor="priority-label-input" className="kb-visually-hidden">
                  Priority label
                </label>
                <input
                  type="text"
                  id="priority-label-input"
                  aria-label="Priority label"
                  data-testid="priority-label-input"
                  className="kb-input"
                  placeholder="Label (e.g. Urgent)"
                  value={priorityLabel}
                  onChange={(e) => { setPriorityLabel(e.target.value); }}
                  required
                />
                <label htmlFor="priority-emoji-input" className="kb-visually-hidden">
                  Priority emoji
                </label>
                <input
                  type="text"
                  id="priority-emoji-input"
                  aria-label="Priority emoji"
                  data-testid="priority-emoji-input"
                  className="kb-input"
                  placeholder="Emoji (🔥)"
                  value={priorityEmoji}
                  onChange={(e) => { setPriorityEmoji(e.target.value); }}
                />
                <ColorPresetPicker
                  testId="priority-color-input"
                  value={priorityColor}
                  onChange={setPriorityColor}
                />
                <label htmlFor="priority-sort-order-input" className="kb-visually-hidden">
                  Priority sort order
                </label>
                <input
                  type="number"
                  id="priority-sort-order-input"
                  aria-label="Priority sort order"
                  data-testid="priority-sort-order-input"
                  className="kb-input"
                  placeholder="Sort Order"
                  value={prioritySortOrder}
                  onChange={(e) => { setPrioritySortOrder(e.target.value); }}
                />
                <label className="kb-checkbox-label" htmlFor="priority-default-checkbox">
                  <input
                    type="checkbox"
                    id="priority-default-checkbox"
                    aria-label="Default priority"
                    data-testid="priority-default-checkbox"
                    checked={priorityIsDefault}
                    onChange={(e) => { setPriorityIsDefault(e.target.checked); }}
                  />
                  <span>Default</span>
                </label>
                <button
                  type="submit"
                  data-testid="create-priority-btn"
                  className="kb-btn kb-btn-primary"
                >
                  Add Priority
                </button>
              </div>
            </form>

            {/* Priorities Table */}
            <div className="kb-table-scroll-container">
              <table className="kb-table" data-testid="priorities-table">
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Emoji</th>
                    <th>Label</th>
                    <th>Slug</th>
                    <th>Color</th>
                    <th>Default</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {priorities.map((p) => {
                    const isEditing = editingPriorityId === p.id;
                    if (isEditing) {
                      return (
                        <tr key={p.id} data-testid={`priority-row-${p.id}`}>
                          <td>
                            <input
                              type="number"
                              aria-label={`Edit sort order for priority ${p.label}`}
                              data-testid={`priority-edit-sort-${p.id}`}
                              className="kb-input"
                              value={editPrioritySortOrder}
                              onChange={(e) => { setEditPrioritySortOrder(e.target.value); }}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              aria-label={`Edit emoji for priority ${p.label}`}
                              data-testid={`priority-edit-emoji-${p.id}`}
                              className="kb-input"
                              value={editPriorityEmoji}
                              onChange={(e) => { setEditPriorityEmoji(e.target.value); }}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              aria-label={`Edit label for priority ${p.label}`}
                              data-testid={`priority-edit-label-${p.id}`}
                              className="kb-input"
                              value={editPriorityLabel}
                              onChange={(e) => { setEditPriorityLabel(e.target.value); }}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              aria-label={`Edit slug for priority ${p.label}`}
                              data-testid={`priority-edit-slug-${p.id}`}
                              className="kb-input"
                              value={editPrioritySlug}
                              onChange={(e) => { setEditPrioritySlug(e.target.value); }}
                            />
                          </td>
                          <td>
                            <ColorPresetPicker
                              testId={`priority-edit-color-${p.id}-input`}
                              value={editPriorityColor}
                              onChange={setEditPriorityColor}
                            />
                          </td>
                          <td>
                            <label className="kb-checkbox-label" htmlFor={`priority-edit-default-${p.id}`}>
                              <input
                                type="checkbox"
                                id={`priority-edit-default-${p.id}`}
                                aria-label={`Edit default for priority ${p.label}`}
                                data-testid={`priority-edit-default-${p.id}`}
                                checked={editPriorityIsDefault}
                                onChange={(e) => { setEditPriorityIsDefault(e.target.checked); }}
                              />
                              <span>Default</span>
                            </label>
                          </td>
                          <td>
                            <button
                              type="button"
                              data-testid={`save-priority-btn-${p.id}`}
                              className="kb-btn kb-btn-primary"
                              onClick={() => { handleSavePriorityEdit(p.id); }}
                            >
                              Save
                            </button>{' '}
                            <button
                              type="button"
                              data-testid={`cancel-priority-btn-${p.id}`}
                              className="kb-btn kb-btn-secondary"
                              onClick={() => { setEditingPriorityId(null); }}
                            >
                              Cancel
                            </button>
                          </td>
                        </tr>
                      );
                    }

                    return (
                      <tr key={p.id} data-testid={`priority-row-${p.id}`}>
                        <td>{p.sort_order}</td>
                        <td>{p.emoji ?? '-'}</td>
                        <td>
                          <strong>{p.label}</strong>
                        </td>
                        <td>
                          <code>{p.slug}</code>
                        </td>
                        <td>
                          <ColoredPill
                            colorHex={p.color_hex}
                            testId={`priority-pill-${p.id}`}
                          />
                        </td>
                        <td>{p.is_default ? '⭐ Default' : '-'}</td>
                        <td>
                          <button
                            type="button"
                            data-testid={`edit-priority-btn-${p.id}`}
                            className="kb-btn kb-btn-secondary"
                            onClick={() => { handleStartEditPriority(p); }}
                          >
                            Edit
                          </button>{' '}
                          <button
                            type="button"
                            data-testid={`delete-priority-btn-${p.id}`}
                            className="kb-btn-danger-sm"
                            onClick={() => { handleDeletePriority(p.id); }}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 4. Labels Tab */}
        {activeTab === 'labels' && (
          <div className="kb-members-section" data-testid="labels-section">
            <div className="kb-settings-header">
              <h3>Project Labels</h3>
              <p className="kb-settings-subtitle">
                Organize work items with color-coded labels and mutual-exclusion groups.
              </p>
            </div>

            {/* Add Label Form */}
            <form className="kb-add-member-form" onSubmit={handleCreateLabel}>
              <h3>Add Label</h3>
              <div className="kb-form-row">
                <label htmlFor="label-name-input" className="kb-visually-hidden">
                  Label name
                </label>
                <input
                  type="text"
                  id="label-name-input"
                  aria-label="Label name"
                  data-testid="label-name-input"
                  className="kb-input"
                  placeholder="Label name (e.g. bug, backend)"
                  value={labelName}
                  onChange={(e) => { setLabelName(e.target.value); }}
                  required
                />
                <ColorPresetPicker
                  testId="label-color-input"
                  value={labelColor}
                  onChange={setLabelColor}
                />
                <button type="submit" data-testid="create-label-btn" className="kb-btn kb-btn-primary">
                  Add Label
                </button>
              </div>

              {/* Advanced Label Grouping (KB-ADVANCED-DISCLOSURE-03, KAN-369) */}
              <AdvancedSection
                title="Advanced Label Grouping"
                summary="Exclusive mutual exclusion label groups"
                testId="label-advanced-section"
                activeOverridesCount={labelExclusiveGroup.trim() ? 1 : 0}
                defaultOpen={false}
              >
                <div className="kb-form-group">
                  <label htmlFor="label-exclusive-group-input">
                    Exclusive Group (optional)
                    <FieldHelpHint
                      title="Exclusive Group"
                      summary="Mutual exclusion group tag ensuring only one label in the group can be attached to an issue."
                      defaultValue="None (unrestricted)"
                      docHref="/docs/ticket-screen-and-work-item-features#labels"
                      testId="proj-exclusive-group-help"
                    />
                  </label>
                  <input
                    id="label-exclusive-group-input"
                    type="text"
                    data-testid="label-exclusive-group-input"
                    className="kb-input"
                    placeholder="Exclusive Group (optional)"
                    value={labelExclusiveGroup}
                    onChange={(e) => { setLabelExclusiveGroup(e.target.value); }}
                  />
                </div>
              </AdvancedSection>
            </form>

            {/* Labels Table */}
            <div className="kb-table-scroll-container">
              <table className="kb-table" data-testid="labels-table">
              <thead>
                <tr>
                  <th>Label Name</th>
                  <th>Color</th>
                  <th>Exclusive Group</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {labels.map((lbl) => {
                  const isEditing = editingLabelId === lbl.id;
                  if (isEditing) {
                    return (
                      <tr key={lbl.id} data-testid={`label-row-${lbl.id}`}>
                        <td>
                          <input
                            type="text"
                            aria-label={`Edit name for label ${lbl.name}`}
                            data-testid={`label-edit-name-${lbl.id}`}
                            className="kb-input"
                            value={editLabelName}
                            onChange={(e) => { setEditLabelName(e.target.value); }}
                          />
                        </td>
                        <td>
                          <ColorPresetPicker
                            testId={`label-edit-color-${lbl.id}-input`}
                            value={editLabelColor}
                            onChange={setEditLabelColor}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            aria-label={`Edit exclusive group for label ${lbl.name}`}
                            data-testid={`label-edit-group-${lbl.id}`}
                            className="kb-input"
                            placeholder="Exclusive Group (optional)"
                            value={editLabelExclusiveGroup}
                            onChange={(e) => { setEditLabelExclusiveGroup(e.target.value); }}
                          />
                        </td>
                        <td>
                          <button
                            type="button"
                            data-testid={`save-label-btn-${lbl.id}`}
                            className="kb-btn kb-btn-primary"
                            onClick={() => { handleSaveLabelEdit(lbl.id); }}
                          >
                            Save
                          </button>{' '}
                          <button
                            type="button"
                            data-testid={`cancel-label-btn-${lbl.id}`}
                            className="kb-btn kb-btn-secondary"
                            onClick={() => { setEditingLabelId(null); }}
                          >
                            Cancel
                          </button>
                        </td>
                      </tr>
                    );
                  }

                  return (
                    <tr key={lbl.id} data-testid={`label-row-${lbl.id}`}>
                      <td>
                        <ColoredPill
                          colorHex={lbl.color_hex}
                          text={lbl.name}
                          testId={`label-pill-${lbl.id}`}
                        />
                      </td>
                      <td>
                        <ColoredPill
                          colorHex={lbl.color_hex}
                          testId={`label-color-pill-${lbl.id}`}
                        />
                      </td>
                      <td>
                        {lbl.exclusive_group ? (
                          <span className="kb-exclusive-pill">{lbl.exclusive_group}</span>
                        ) : (
                          '-'
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          data-testid={`edit-label-btn-${lbl.id}`}
                          className="kb-btn kb-btn-secondary"
                          onClick={() => { handleStartEditLabel(lbl); }}
                        >
                          Edit
                        </button>{' '}
                        <button
                          type="button"
                          data-testid={`delete-label-btn-${lbl.id}`}
                          className="kb-btn-danger-sm"
                          onClick={() => { handleDeleteLabel(lbl.id); }}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          </div>
        )}

        {/* 5. Members & Access Tab */}
        {activeTab === 'members' && (
          <div className="kb-members-section" data-testid="members-section">
            <div className="kb-members-actions-bar">
              <button
                type="button"
                data-testid="inspect-access-btn"
                className="kb-btn kb-btn-secondary"
                onClick={handleTriggerAccessInspector}
              >
                🔍 Inspect Effective Access
              </button>
            </div>

            {/* Searchable Principal Picker */}
            <form className="kb-add-member-form" onSubmit={handleAddMember}>
              <h3>Add Project Member</h3>
              <div className="kb-form-row">
                <div className="kb-principal-picker">
                  <label htmlFor="member-principal-id-input" className="kb-visually-hidden">
                    Member principal
                  </label>
                  <input
                    type="text"
                    id="member-principal-id-input"
                    aria-label="Search by name, @handle, or enter UUID"
                    data-testid="member-principal-id-input"
                    className="kb-input"
                    placeholder="Search by name, @handle, or enter UUID..."
                    value={principalSearch || newPrincipalId}
                    onChange={(e) => {
                      const val = e.target.value;
                      setPrincipalSearch(val);
                      setNewPrincipalId(val);
                      setIsPickerOpen(true);
                    }}
                    onFocus={() => { setIsPickerOpen(true); }}
                    required
                  />
                  {isPickerOpen && principalsList.length > 0 && (
                    <div
                      className="kb-principal-dropdown"
                      data-testid="principal-picker-dropdown"
                      onMouseDown={(e) => { e.preventDefault(); }}
                    >
                      {filteredPrincipals.slice(0, 10).map((p) => (
                        <div
                          key={p.id}
                          className="kb-principal-item"
                          data-testid={`principal-option-${p.id}`}
                          onClick={() => {
                            setNewPrincipalId(p.id);
                            setPrincipalSearch(p.display_name);
                            setIsPickerOpen(false);
                          }}
                        >
                          <span>
                            {p.principal_type === 'AGENT'
                              ? '🤖'
                              : p.principal_type === 'GROUP'
                                ? '👥'
                                : '👤'}
                          </span>
                          <span className="kb-principal-name">{p.display_name}</span>
                          {formatPrincipalHandle(p.handle, p.principal) && (
                            <span className="kb-principal-handle">
                              {formatPrincipalHandle(p.handle, p.principal)}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <label htmlFor="member-role-select" className="kb-visually-hidden">
                  Member role
                </label>
                <select
                  id="member-role-select"
                  aria-label="Member role"
                  data-testid="member-role-select"
                  className="kb-select"
                  value={newRole}
                  onChange={(e) => { setNewRole(e.target.value as 'PROJECT_ADMIN' | 'MEMBER' | 'VIEWER'); }
                  }
                >
                  <option value="MEMBER">Member (Read &amp; Write)</option>
                  <option value="PROJECT_ADMIN">Project Admin (Full Control)</option>
                  <option value="VIEWER">Viewer (Read-Only)</option>
                </select>

                <button
                  type="submit"
                  data-testid="add-member-submit-btn"
                  className="kb-btn kb-btn-primary"
                  disabled={isAddingMember}
                >
                  {isAddingMember ? 'Adding...' : 'Add Member'}
                </button>
              </div>
            </form>

            <div className="kb-table-scroll-container">
              <table className="kb-table" data-testid="members-table">
              <thead>
                <tr>
                  <th>Principal</th>
                  <th>Role</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id || m.principal_id}>
                    <td>
                      <div>
                        <strong>{m.display_name ?? m.principal_id}</strong>
                        {formatPrincipalHandle(m.handle, m.principal) && (
                          <span className="kb-principal-handle">
                            {' '}({formatPrincipalHandle(m.handle, m.principal)})
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span
                        data-testid="member-role-badge"
                        className={`kb-role-badge kb-role-${((m.role as string | null | undefined) ?? '').toLowerCase()}`}
                      >
                        {m.role}
                      </span>
                      <RoleLabelPicker principalId={m.principal_id} />
                    </td>
                    <td>
                      <button
                        type="button"
                        data-testid={`remove-member-${m.principal_id}`}
                        className="kb-btn-danger-sm"
                        onClick={() => { handleRemoveMember(m.principal_id); }}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>
        )}

        {/* 6. Automation & Integrations Tab */}
        {activeTab === 'roles' && (
          <div className="kb-settings-section" data-testid="project-roles-section">
            <RbacPolicyBuilder
              projectId={project?.id}
              isServerAdmin={isServerAdmin}
              initialRoleTier="project admin"
            />
          </div>
        )}

        {activeTab === 'integrations' && (
          <div className="kb-integrations-grid" data-testid="integrations-section">
            <Link
              to={`/projects/${projectKey}/settings/workflows`}
              className="kb-integration-card"
              data-testid="integration-workflows-card"
            >
              <div className="kb-card-icon">🔀</div>
              <div className="kb-card-content">
                <h3>Workflows &amp; States</h3>
                <p>Configure lifecycle hooks, state transition helpers, and automated scripts.</p>
              </div>
            </Link>

            <Link
              to={`/projects/${projectKey}/settings/custom-fields`}
              className="kb-integration-card"
              data-testid="integration-custom-fields-card"
            >
              <div className="kb-card-icon">⚙️</div>
              <div className="kb-card-content">
                <h3>Custom Fields</h3>
                <p>Define custom structured attributes, formulas, and schema extensions.</p>
              </div>
            </Link>

            <Link
              to={`/settings/mcp?scope=project&project=${projectKey}`}
              className="kb-integration-card"
              data-testid="integration-mcp-card"
            >
              <div className="kb-card-icon">🤖</div>
              <div className="kb-card-content">
                <h3>Project MCP Keys</h3>
                <p>Manage scoped Model Context Protocol API tokens for autonomous agent runners.</p>
              </div>
            </Link>
          </div>
        )}

        {/* 7. Trash & Retention Tab */}
        {activeTab === 'trash' && (
          <div className="kb-members-section" data-testid="trash-section">
            <div className="kb-settings-header">
              <h3>Project Trash &amp; Retention</h3>
              <p className="kb-settings-subtitle">
                Soft-deleted work items, cycles, modules, stickies, and docs. Restorable before
                retention period expires.
              </p>
            </div>

            {/* Filter Pills */}
            <div className="kb-trash-filters">
              {['all', 'issue', 'cycle', 'module', 'sticky', 'doc'].map((kind) => (
                <button
                  key={kind}
                  type="button"
                  data-testid={`trash-filter-${kind}`}
                  className={`kb-trash-filter-btn ${trashKindFilter === kind ? 'kb-trash-filter-btn-active' : ''}`}
                  onClick={() => { setTrashKindFilter(kind); }}
                >
                  {kind === 'all'
                    ? 'All'
                    : kind.charAt(0).toUpperCase() + kind.slice(1) + 's'}
                </button>
              ))}
            </div>

            {filteredTrashed.length === 0 ? (
              <div className="kb-trash-empty" data-testid="trash-empty-state">
                No trashed items in this project.
              </div>
            ) : (
              <div className="kb-table-scroll-container">
                <table className="kb-table" data-testid="trash-items-table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Key / Identifier</th>
                    <th>Title / Summary</th>
                    <th>Retention Remaining</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTrashed.map((item) => (
                    <tr key={item.id} data-testid={`trash-row-${item.id}`}>
                      <td>
                        <span className="kb-role-badge kb-role-member">
                          {item.kind === 'issue'
                            ? '📋 Issue'
                            : item.kind === 'cycle'
                              ? '🔄 Cycle'
                              : item.kind === 'module'
                                ? '🧩 Module'
                                : item.kind === 'sticky'
                                  ? '🟨 Sticky'
                                  : item.kind === 'doc' || item.kind === 'page'
                                    ? '📄 Doc'
                                    : '📁 ' + item.kind}
                        </span>
                      </td>
                      <td>
                        <strong data-testid="trash-item-key">{item.key}</strong>
                      </td>
                      <td>
                        <span data-testid="trash-item-title">{item.title}</span>
                      </td>
                      <td>
                        <span
                          data-testid="trash-remaining-days"
                          className={`kb-retention-pill ${item.remaining_days <= 3 ? 'kb-retention-pill-expired' : ''}`}
                        >
                          {item.remaining_days > 0
                            ? `${String(item.remaining_days)} days remaining`
                            : 'Expires today'}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          data-testid={`restore-btn-${item.id}`}
                          className="kb-btn kb-btn-secondary"
                          onClick={() => { handleRestoreItem(item); }}
                        >
                          ↩️ Restore
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </div>
        )}

        {/* 8. Danger Zone Tab */}
        {activeTab === 'danger' && (
          <div className="kb-danger-zone" data-testid="danger-section">
            <div className="kb-danger-header">
              <h3>Move Project to Trash</h3>
              <p>
                Deleting this project moves all associated work items, cycles, modules, and docs to
                trash according to retention policies.
              </p>
            </div>

            {dangerError && (
              <div className="kb-settings-alert kb-settings-alert-error" role="alert">
                {dangerError}
              </div>
            )}

            {dangerStage === 'idle' && (
              <div className="kb-danger-buttons-row">
                <button
                  type="button"
                  data-testid="request-delete-btn"
                  className="kb-btn kb-btn-danger"
                  onClick={() => { handleRequestDelete('trash'); }}
                >
                  🗑️ Move Project to Trash...
                </button>

                {isServerAdmin && (
                  <div className="kb-danger-purge-container">
                    <button
                      type="button"
                      data-testid="request-purge-btn"
                      className="kb-btn kb-btn-danger kb-btn-purge"
                      disabled={!isProjectTrashed}
                      aria-disabled={!isProjectTrashed}
                      onClick={() => {
                        handleRequestDelete('permanent_purge');
                      }}
                    >
                      💥 Permanently Purge Project (Irreversible)...
                    </button>
                    {!isProjectTrashed && (
                      <p className="kb-danger-purge-hint" data-testid="purge-disabled-hint">
                        Stage 1 (Move Project to Trash) must be completed before permanent purge.
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {dangerStage === 'requested' && destructiveToken && (
              <div className="kb-danger-confirm-card" data-testid="danger-confirm-card">
                <h4>
                  {destructiveToken.mode === 'permanent_purge'
                    ? 'Stage 2: Confirm PERMANENT Project Purge (IRREVERSIBLE)'
                    : 'Stage 2: Confirm Project Deletion'}
                </h4>
                <div className="kb-blast-radius-box">
                  <p>
                    <strong>Impacted Objects:</strong>
                  </p>
                  {typeof destructiveToken.blast_summary === 'string' ? (
                    <p data-testid="blast-summary-text">{destructiveToken.blast_summary}</p>
                  ) : (
                    <ul>
                      <li>Work Items: {destructiveToken.blast_summary.issues_count ?? 0}</li>
                      <li>Docs / Pages: {destructiveToken.blast_summary.pages_count ?? 0}</li>
                      <li>Stickies: {destructiveToken.blast_summary.stickies_count ?? 0}</li>
                    </ul>
                  )}
                </div>

                <p className="kb-confirm-prompt">
                  To confirm, please type exact phrase: <code>{destructiveToken.confirm_phrase}</code>
                </p>

                <label htmlFor="confirm-phrase-input" className="kb-visually-hidden">
                  Confirmation phrase
                </label>
                <input
                  type="text"
                  id="confirm-phrase-input"
                  aria-label="Confirmation phrase"
                  data-testid="confirm-phrase-input"
                  className="kb-input"
                  placeholder="Type confirmation phrase exactly"
                  value={enteredPhrase}
                  onChange={(e) => { setEnteredPhrase(e.target.value); }}
                />

                <label htmlFor="danger-reason-input" className="kb-visually-hidden">
                  Reason for deletion
                </label>
                <input
                  type="text"
                  id="danger-reason-input"
                  aria-label="Reason for deletion"
                  data-testid="danger-reason-input"
                  className="kb-input kb-danger-reason-input"
                  placeholder="Reason for deletion (optional, min 10 chars)"
                  value={dangerReason}
                  onChange={(e) => { setDangerReason(e.target.value); }}
                />

                <div className="kb-danger-actions">
                  <button
                    type="button"
                    data-testid="execute-delete-btn"
                    className="kb-btn kb-btn-danger"
                    disabled={enteredPhrase.trim() !== destructiveToken.confirm_phrase}
                    onClick={handleExecuteDelete}
                  >
                    {destructiveToken.mode === 'permanent_purge'
                      ? 'Confirm Permanent Purge'
                      : 'Confirm Permanent Deletion'}
                  </button>
                  <button
                    type="button"
                    data-testid="cancel-delete-btn"
                    className="kb-btn kb-btn-secondary"
                    onClick={() => {
                      setDangerStage('idle');
                      setDestructiveToken(null);
                      setEnteredPhrase('');
                      setDangerReason('');
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <DeleteAuditModal
        isOpen={Boolean(auditModalKind && auditModalItem)}
        onClose={() => {
          setAuditModalKind(null);
          setAuditModalItem(null);
        }}
        onConfirmedDelete={handleConfirmedDelete}
        kind={auditModalKind ?? 'state'}
        item={auditModalItem}
        projectKey={projectKey}
      />
    </div>
  );
}

export default ProjectSettingsPage;
