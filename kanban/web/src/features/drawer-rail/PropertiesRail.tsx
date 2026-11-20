import React, { useEffect, useState, type JSX } from 'react';
import type { IssueDetail } from '../drawer/slots';
import {
  addAssignee,
  createProjectLabel,
  fetchAssigneeSuggestions,
  fetchProjectCycles,
  fetchProjectLabels,
  fetchProjectMetadata,
  fetchProjectModules,
  fetchProjectPriorities,
  overrideCreator,
  patchIssue,
  removeAssignee,
  updateIssueModules,
  type AssigneeItem,
  type ProjectCycle,
  type ProjectLabel,
  type ProjectMetadata,
  type ProjectModule,
  type ProjectPriority,
} from './railApi';
import { StatePriorityRows } from './StatePriorityRows';
import { AssigneesRow } from './AssigneesRow';
import { CreatedByRow } from './CreatedByRow';
import { DatesCycleModulesRows } from './DatesCycleModulesRows';
import { ParentLabelsRows } from './ParentLabelsRows';
import { CustomFieldsRailSection } from '../custom-fields/CustomFieldsRailSection';
import './PropertiesRail.css';

export interface PropertiesRailProps {
  issue: IssueDetail;
  projectMetadata?: ProjectMetadata | undefined;
  onIssueUpdate?: ((updated: IssueDetail) => void) | undefined;
}

export function PropertiesRail({
  issue: initialIssue,
  projectMetadata: initialMetadata,
  onIssueUpdate,
}: PropertiesRailProps): JSX.Element {
  const [currentIssue, setCurrentIssue] = useState<IssueDetail>(initialIssue);
  const [prevInitialIssue, setPrevInitialIssue] = useState<IssueDetail>(initialIssue);
  if (initialIssue !== prevInitialIssue) {
    setPrevInitialIssue(initialIssue);
    setCurrentIssue(initialIssue);
  }

  const [metadata, setMetadata] = useState<ProjectMetadata | undefined>(initialMetadata);
  const [priorities, setPriorities] = useState<ProjectPriority[]>(initialMetadata?.priorities ?? []);
  const [modules, setModules] = useState<ProjectModule[]>([]);
  const [cycles, setCycles] = useState<ProjectCycle[]>([]);
  const [labels, setLabels] = useState<ProjectLabel[]>(initialMetadata?.labels ?? []);

  const rawProject = currentIssue.project_key;
  const projectKey: string =
    rawProject && rawProject !== 'undefined'
      ? rawProject
      : (currentIssue.key.includes('-') ? (currentIssue.key.split('-')[0] ?? '') : '');
  const capabilities = currentIssue.capabilities ?? ['EDIT', 'TRANSITION'];
  const canEdit = capabilities.includes('EDIT') || capabilities.includes('ADMIN');
  const canTransition = capabilities.includes('TRANSITION') || capabilities.includes('ADMIN');
  const isAdmin = capabilities.includes('ADMIN');

  const modulesEnabled =
    metadata?.modules_enabled ?? initialMetadata?.modules_enabled ?? true;

  // Fetch project auxiliary configuration
  useEffect(() => {
    let isMounted = true;
    async function loadAux(): Promise<void> {
      if (!projectKey || projectKey === 'undefined') {
        return;
      }
      let resolvedMeta = initialMetadata;
      try {
        if (!resolvedMeta) {
          resolvedMeta = await fetchProjectMetadata(projectKey);
          if (isMounted) setMetadata(resolvedMeta);
        }
      } catch {
        // Fallback gracefully
      }

      try {
        const [prios, lbls, cycs] = await Promise.all([
          fetchProjectPriorities(projectKey).catch(() => []),
          fetchProjectLabels(projectKey).catch(() => []),
          fetchProjectCycles(projectKey).catch(() => []),
        ]);
        if (isMounted) {
          if (prios.length > 0) setPriorities(prios);
          if (lbls.length > 0) setLabels(lbls);
          if (cycs.length > 0) setCycles(cycs);
        }
      } catch {
        // Ignore in tests
      }

      const shouldLoadModules = resolvedMeta?.modules_enabled ?? modulesEnabled;
      if (shouldLoadModules) {
        try {
          const mods = await fetchProjectModules(projectKey);
          if (isMounted) setModules(mods);
        } catch {
          // Ignore
        }
      }
    }

    void loadAux();
    return () => {
      isMounted = false;
    };
  }, [projectKey, modulesEnabled, initialMetadata]);

  const updateLocalIssue = (patch: Partial<IssueDetail>): void => {
    setCurrentIssue((prev) => {
      const updated: IssueDetail = { ...prev, ...patch };
      if (onIssueUpdate) {
        onIssueUpdate(updated);
      }
      return updated;
    });
  };

  const handleStateChange = async (stateId: string): Promise<void> => {
    const selectedState = metadata?.states?.find((s) => s.id === stateId);
    updateLocalIssue({
      state: selectedState
        ? { id: selectedState.id, name: selectedState.name, group: selectedState.group }
        : { id: stateId, name: stateId, group: 'started' },
    });
    try {
      await patchIssue(currentIssue.key, { state_id: stateId }, currentIssue.etag);
    } catch {
      // Keep optimistic
    }
  };

  const handlePriorityChange = async (prioritySlug: string): Promise<void> => {
    const found = priorities.find((p) => p.slug === prioritySlug);
    updateLocalIssue({
      priority: {
        slug: prioritySlug,
        label: found?.label ?? found?.name ?? prioritySlug,
        emoji: found?.emoji ?? found?.icon ?? '',
        sort_order: found?.sort_order ?? 1,
      },
    });
    try {
      await patchIssue(currentIssue.key, { priority: prioritySlug }, currentIssue.etag);
    } catch {
      // Keep optimistic
    }
  };

  const handleAddAssignee = async (payload: { principal?: string; free_text?: string }): Promise<void> => {
    const res = await addAssignee(currentIssue.key, payload);
    const existing: AssigneeItem[] = currentIssue.assignees as AssigneeItem[];
    updateLocalIssue({ assignees: [...existing, res] });
  };

  const handleRemoveAssignee = async (assigneeId: string): Promise<void> => {
    await removeAssignee(currentIssue.key, assigneeId);
    const existing: AssigneeItem[] = currentIssue.assignees as AssigneeItem[];
    updateLocalIssue({ assignees: existing.filter((a) => a.id !== assigneeId) });
  };

  const handleOverrideCreator = async (payload: { created_by: string; reason: string }): Promise<void> => {
    const updated = await overrideCreator(currentIssue.key, payload);
    updateLocalIssue({
      provenance: updated.provenance ?? {
        created_by: { handle: payload.created_by },
        overridden: true,
        reason: payload.reason,
      },
    });
  };

  const handleUpdateDates = async (dates: {
    start_date?: string | null | undefined;
    due_date?: string | null | undefined;
  }): Promise<void> => {
    updateLocalIssue({
      start_date: dates.start_date ?? null,
      due_date: dates.due_date ?? null,
    });
    try {
      const updated = await patchIssue(currentIssue.key, dates, currentIssue.etag);
      if (updated.etag) {
        updateLocalIssue({ etag: updated.etag });
      }
    } catch {
      // Keep optimistic
    }
  };

  const handleUpdateModules = async (moduleIds: string[]): Promise<void> => {
    const selectedMods = modules.filter((m) => moduleIds.includes(m.id));
    updateLocalIssue({
      module_ids: moduleIds,
      modules: selectedMods.map((m) => ({ id: m.id, name: m.name })),
    });
    try {
      await updateIssueModules(currentIssue.key, moduleIds);
    } catch {
      // Keep optimistic
    }
  };

  const handleUpdateCycle = async (cycleId: string | null): Promise<void> => {
    const foundCycle = cycles.find((c) => c.id === cycleId);
    updateLocalIssue({
      cycle_id: cycleId,
      cycle: foundCycle ? { id: foundCycle.id, name: foundCycle.name } : null,
    });
    try {
      const updated = await patchIssue(currentIssue.key, { cycle_id: cycleId }, currentIssue.etag);
      if (updated.etag) {
        updateLocalIssue({ etag: updated.etag });
      }
    } catch {
      // Keep optimistic
    }
  };

  const handleUpdateParent = async (parentKey: string | null): Promise<void> => {
    updateLocalIssue({
      parent: parentKey ? { key: parentKey, restricted: false } : null,
    });
    await patchIssue(currentIssue.key, { parent: parentKey }, currentIssue.etag);
  };

  const handleUpdateLabels = async (labelIds: string[]): Promise<void> => {
    updateLocalIssue({ label_ids: labelIds });
    await patchIssue(currentIssue.key, { label_ids: labelIds }, currentIssue.etag);
  };

  const handleCreateLabel = async (name: string, colorHex = '#3b82f6'): Promise<ProjectLabel> => {
    const created = await createProjectLabel(projectKey, { name, color_hex: colorHex });
    setLabels((prev) => [...prev, created]);
    return created;
  };

  return (
    <aside className="surface__rail" aria-label="Properties">
      <StatePriorityRows
        issue={currentIssue}
        projectStates={metadata?.states}
        projectPriorities={priorities}
        canEdit={canEdit}
        canTransition={canTransition}
        onStateChange={handleStateChange}
        onPriorityChange={handlePriorityChange}
      />

      <AssigneesRow
        issue={currentIssue}
        projectKey={projectKey}
        canEdit={canEdit}
        onAddAssignee={handleAddAssignee}
        onRemoveAssignee={handleRemoveAssignee}
        fetchSuggestions={fetchAssigneeSuggestions}
      />

      <CreatedByRow
        issue={currentIssue}
        isAdmin={isAdmin}
        onOverrideCreator={handleOverrideCreator}
      />

      <DatesCycleModulesRows
        issue={currentIssue}
        modulesEnabled={modulesEnabled}
        projectModules={modules}
        projectCycles={cycles}
        canEdit={canEdit}
        onUpdateDates={handleUpdateDates}
        onUpdateModules={handleUpdateModules}
        onUpdateCycle={handleUpdateCycle}
      />

      <ParentLabelsRows
        issue={currentIssue}
        projectLabels={labels}
        canEdit={canEdit}
        onUpdateParent={handleUpdateParent}
        onUpdateLabels={handleUpdateLabels}
        onCreateLabel={handleCreateLabel}
      />

      {/* Admin-Defined Custom Fields section (KB-P5-15) */}
      <div data-slot="custom-fields-rail">
        <CustomFieldsRailSection
          projectKey={projectKey}
          issueKey={currentIssue.key}
          canEdit={canEdit}
        />
      </div>
    </aside>
  );
}
