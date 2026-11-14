import React, { type JSX } from 'react';
import type { IssueDetail } from '../drawer/slots';
import type { ProjectPriority, ProjectWorkflowState } from './railApi';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { EmojiKey } from '../../components/emoji/emojiRegistry';
import { GateStatusPill } from '../gates/GateStatusPill';

export interface StatePriorityRowsProps {
  issue: IssueDetail;
  projectStates?: ProjectWorkflowState[] | undefined;
  projectPriorities?: ProjectPriority[] | undefined;
  canEdit: boolean;
  canTransition: boolean;
  onStateChange: (stateId: string) => Promise<void>;
  onPriorityChange: (prioritySlug: string) => Promise<void>;
}

const DEFAULT_STATES: ProjectWorkflowState[] = [
  { id: 'state-backlog', name: 'Backlog', group: 'backlog' },
  { id: 'state-todo', name: 'Todo', group: 'unstarted' },
  { id: 'state-in-progress', name: 'In Progress', group: 'started' },
  { id: 'state-in-review', name: 'In Review', group: 'started' },
  { id: 'state-done', name: 'Done', group: 'completed' },
  { id: 'state-canceled', name: 'Canceled', group: 'cancelled' },
];

const DEFAULT_PRIORITIES: ProjectPriority[] = [
  { slug: 'urgent', name: 'Urgent', emoji: '🔥' },
  { slug: 'high', name: 'High', emoji: '⚡' },
  { slug: 'medium', name: 'Medium', emoji: '🔹' },
  { slug: 'low', name: 'Low', emoji: '💤' },
  { slug: 'none', name: 'None', emoji: '' },
];

const STATE_GROUPS: { key: ProjectWorkflowState['group']; label: string }[] = [
  { key: 'backlog', label: 'Backlog' },
  { key: 'unstarted', label: 'Unstarted' },
  { key: 'started', label: 'Started' },
  { key: 'completed', label: 'Completed' },
  { key: 'cancelled', label: 'Cancelled' },
];

export function StatePriorityRows({
  issue,
  projectStates,
  projectPriorities,
  canEdit,
  canTransition,
  onStateChange,
  onPriorityChange,
}: StatePriorityRowsProps): JSX.Element {
  const states = projectStates && projectStates.length > 0 ? projectStates : DEFAULT_STATES;
  const priorities =
    projectPriorities && projectPriorities.length > 0 ? projectPriorities : DEFAULT_PRIORITIES;

  const currentStateId = issue.state?.id ?? '';
  const currentPrioritySlug = issue.priority?.slug ?? 'none';

  const handleStateSelect = (e: React.ChangeEvent<HTMLSelectElement>): void => {
    void onStateChange(e.target.value);
  };

  const handlePrioritySelect = (e: React.ChangeEvent<HTMLSelectElement>): void => {
    void onPriorityChange(e.target.value);
  };

  const priorityEmojiKind: Record<string, EmojiKey> = {
    urgent: 'priorityUrgent',
    high: 'priorityHigh',
    medium: 'priorityMedium',
    low: 'priorityLow',
  };

  const activeEmojiKind = priorityEmojiKind[currentPrioritySlug.toLowerCase()];

  return (
    <>
      <div className="prop-row" data-prop="state">
        <label htmlFor="prop-state-select" className="prop-row__label">
          State
        </label>
        <div className="prop-row__value">
          {issue.pending_gate && (
            <GateStatusPill
              status="pending"
              pendingGate={issue.pending_gate}
              issueKey={issue.key}
              canCancel={canTransition}
              testId="drawer-gate-pending"
            />
          )}
          {!issue.pending_gate && issue.latest_gate_verdict?.decision === 'reject' && (
            <GateStatusPill
              status="rejected"
              latestVerdict={issue.latest_gate_verdict}
              issueKey={issue.key}
              testId="drawer-gate-vetoed"
            />
          )}
          {!issue.pending_gate && issue.latest_gate_verdict?.decision === 'approve' && (
            <GateStatusPill
              status="approved"
              latestVerdict={issue.latest_gate_verdict}
              issueKey={issue.key}
              testId="drawer-gate-approved"
            />
          )}
          <select
            id="prop-state-select"
            aria-label="State"
            className="prop-row__select"
            value={currentStateId}
            disabled={!canTransition}
            onChange={handleStateSelect}
          >
            {STATE_GROUPS.map((group) => {
              const groupStates = states.filter((s) => s.group === group.key);
              if (groupStates.length === 0) return null;
              return (
                <optgroup key={group.key} label={group.label}>
                  {groupStates.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </optgroup>
              );
            })}
          </select>
        </div>
      </div>

      <div className="prop-row" data-prop="priority">
        <label htmlFor="prop-priority-select" className="prop-row__label">
          Priority
        </label>
        <div className="prop-row__value">
          {activeEmojiKind ? (
            <EmojiHint kind={activeEmojiKind} label={`Priority: ${currentPrioritySlug}`} />
          ) : null}
          <select
            id="prop-priority-select"
            aria-label="Priority"
            className="prop-row__select"
            value={currentPrioritySlug}
            disabled={!canEdit}
            onChange={handlePrioritySelect}
          >
            {priorities.map((p) => {
              const slug = p.slug;
              const display = `${p.emoji ?? p.icon ?? ''} ${p.label ?? p.name ?? slug}`.trim();
              return (
                <option key={slug} value={slug}>
                  {display}
                </option>
              );
            })}
          </select>
        </div>
      </div>
    </>
  );
}
