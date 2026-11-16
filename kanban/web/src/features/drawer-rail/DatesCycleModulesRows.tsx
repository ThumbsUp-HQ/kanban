import React, { useState, type JSX } from 'react';
import type { IssueDetail } from '../drawer/slots';
import type { ProjectCycle, ProjectModule } from './railApi';

export interface DatesCycleModulesRowsProps {
  issue: IssueDetail;
  modulesEnabled: boolean;
  projectModules?: ProjectModule[] | undefined;
  projectCycles?: ProjectCycle[] | undefined;
  canEdit: boolean;
  onUpdateDates: (dates: { start_date?: string | null | undefined; due_date?: string | null | undefined }) => Promise<void>;
  onUpdateModules: (moduleIds: string[]) => Promise<void>;
  onUpdateCycle: (cycleId: string | null) => Promise<void>;
}

export function DatesCycleModulesRows({
  issue,
  modulesEnabled,
  projectModules = [],
  projectCycles = [],
  canEdit,
  onUpdateDates,
  onUpdateModules,
  onUpdateCycle,
}: DatesCycleModulesRowsProps): JSX.Element {
  const [dateAlert, setDateAlert] = useState<string | null>(null);

  const startDate = issue.start_date ?? '';
  const dueDate = issue.due_date ?? '';

  const initialRangeInvalid = Boolean(startDate && dueDate && dueDate < startDate);
  const activeAlert = dateAlert ?? (initialRangeInvalid ? 'Due date cannot be earlier than start date.' : null);

  const stateGroup = issue.state?.group ?? (issue.state?.name === 'Done' ? 'completed' : '');
  const isResolved = stateGroup === 'completed' || stateGroup === 'cancelled';

  const todayStr = new Date().toISOString().slice(0, 10);
  const isOverdue = Boolean(dueDate && dueDate < todayStr && !isResolved);

  const handleStartDateChange = async (e: React.ChangeEvent<HTMLInputElement>): Promise<void> => {
    const val = e.target.value || null;
    if (val && dueDate && dueDate < val) {
      setDateAlert('Due date cannot be earlier than start date.');
      return;
    }
    setDateAlert(null);
    await onUpdateDates({ start_date: val, due_date: dueDate || null });
  };

  const handleDueDateChange = async (e: React.ChangeEvent<HTMLInputElement>): Promise<void> => {
    const val = e.target.value || null;
    if (val && startDate && val < startDate) {
      setDateAlert('Due date cannot be earlier than start date.');
      return;
    }
    setDateAlert(null);
    await onUpdateDates({ start_date: startDate || null, due_date: val });
  };

  // Modules handling
  const rawModules = issue.module_ids ?? issue.modules?.map((m) => m.id) ?? [];
  const selectedModuleId = rawModules[0] ?? '';

  const handleModuleSelect = async (e: React.ChangeEvent<HTMLSelectElement>): Promise<void> => {
    const val = e.target.value;
    const newIds = val ? [val] : [];
    await onUpdateModules(newIds);
  };

  // Cycle handling
  const rawCycleId = issue.cycle_id ?? issue.cycle?.id ?? '';
  const currentCycle = projectCycles.find((c) => c.id === rawCycleId || c.name === rawCycleId);

  const handleCycleSelect = async (e: React.ChangeEvent<HTMLSelectElement>): Promise<void> => {
    const val = e.target.value || null;
    await onUpdateCycle(val);
  };

  return (
    <>
      <div className="prop-row" data-prop="start-date">
        <label htmlFor="prop-start-date-input" className="prop-row__label">
          Start date
        </label>
        <div className="prop-row__value">
          <input
            id="prop-start-date-input"
            type="date"
            aria-label="Start date"
            className="prop-row__input"
            value={startDate}
            disabled={!canEdit}
            onChange={(e) => void handleStartDateChange(e)}
          />
        </div>
      </div>

      <div className="prop-row" data-prop="due-date">
        <label htmlFor="prop-due-date-input" className="prop-row__label">
          Due date
        </label>
        <div className="prop-row__value">
          <input
            id="prop-due-date-input"
            type="date"
            aria-label="Due date"
            className="prop-row__input"
            value={dueDate}
            disabled={!canEdit}
            onChange={(e) => void handleDueDateChange(e)}
          />
          {isOverdue ? (
            <span className="overdue-badge" data-testid="overdue-badge">
              Overdue
            </span>
          ) : null}
        </div>
        {activeAlert ? (
          <div className="prop-row__alert" role="alert">
            {activeAlert}
          </div>
        ) : null}
      </div>

      {/* S7.2 8f INVARIANT: 100% UNMOUNTED from DOM if modulesEnabled is false */}
      {modulesEnabled ? (
        <div className="prop-row" data-prop="modules">
          <label htmlFor="prop-modules-select" className="prop-row__label">
            Modules
          </label>
          <div className="prop-row__value">
            <select
              id="prop-modules-select"
              aria-label="Modules"
              className="prop-row__select"
              value={selectedModuleId}
              disabled={!canEdit}
              onChange={(e) => void handleModuleSelect(e)}
            >
              <option value="">None</option>
              {projectModules.map((m) => (
                <option key={m.id} value={m.id}>
                  {`${m.emoji ?? '🧩'} ${m.name}`}
                </option>
              ))}
            </select>
          </div>
        </div>
      ) : null}

      <div className="prop-row" data-prop="cycle">
        <label htmlFor="prop-cycle-select" className="prop-row__label">
          Cycle
        </label>
        <div className="prop-row__value">
          <select
            id="prop-cycle-select"
            aria-label="Cycle"
            className="prop-row__select"
            value={currentCycle?.id ?? rawCycleId}
            disabled={!canEdit}
            onChange={(e) => void handleCycleSelect(e)}
          >
            <option value="">None (Clear)</option>
            {projectCycles.map((c) => {
              const countText =
                c.issue_count !== undefined
                  ? ` (${String(c.completed_count ?? 0)}/${String(c.issue_count)})`
                  : '';
              const statusText = c.status ? ` [${c.status}]` : '';
              return (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {statusText}
                  {countText}
                </option>
              );
            })}
          </select>
        </div>
      </div>
    </>
  );
}
