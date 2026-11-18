import React, { useRef, useLayoutEffect, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { StateBadge } from '../../components/state/StateBadge';
import { PriorityIcon } from '../../components/icons/KanbanIcons';
import type { IssueItem } from '../views/viewsApi';

export interface ListRowProps {
  issue: IssueItem;
  isSelected?: boolean | undefined;
  onToggleSelect?: ((key: string, selected: boolean) => void) | undefined;
  modulesEnabled?: boolean | undefined;
  isFocused?: boolean | undefined;
  onOpenPeek?: ((issueKey: string) => void) | undefined;
  isActive?: boolean | undefined;
}

const HEX_COLOR_REGEX = /^#[0-9A-Fa-f]{6}$/;

function LabelDot({ colorHex }: { colorHex: string }): JSX.Element {
  const dotRef = useRef<HTMLSpanElement>(null);
  const isValidHex = HEX_COLOR_REGEX.test(colorHex);

  useLayoutEffect(() => {
    if (dotRef.current && isValidHex) {
      dotRef.current.style.backgroundColor = colorHex;
    }
  }, [colorHex, isValidHex]);

  return <span ref={dotRef} className="label-dot" aria-hidden="true" />;
}

export function ListRow({
  issue,
  isSelected = false,
  onToggleSelect,
  modulesEnabled = true,
  isFocused = false,
  onOpenPeek,
  isActive = false,
}: ListRowProps): JSX.Element {
  const rowRef = useRef<HTMLLIElement>(null);

  // Priority EmojiHint kind mapping
  let priorityKind: 'priorityUrgent' | 'priorityHigh' | 'priorityMedium' | 'priorityLow' =
    'priorityMedium';
  const pSlug = issue.priority.slug.toLowerCase();
  if (pSlug === 'urgent') priorityKind = 'priorityUrgent';
  else if (pSlug === 'high') priorityKind = 'priorityHigh';
  else if (pSlug === 'low') priorityKind = 'priorityLow';

  // Overdue check (S7.2 8e): suppressed when state.group is 'completed' or 'cancelled'
  const isTerminalState =
    issue.state.group === 'completed' || issue.state.group === 'cancelled';
  let isOverdue = false;
  if (issue.due_date && !isTerminalState) {
    const today = new Date().toISOString().slice(0, 10);
    if (issue.due_date < today) {
      isOverdue = true;
    }
  }

  // Gate EmojiHint mapping
  let gateKind: 'gatePending' | 'gateVetoed' | 'gateApproved' | null = null;
  if (issue.gate_status === 'pending') gateKind = 'gatePending';
  else if (issue.gate_status === 'vetoed') gateKind = 'gateVetoed';
  else if (issue.gate_status === 'approved') gateKind = 'gateApproved';

  const labels = issue.labels ?? [];
  const visibleLabels = labels.slice(0, 2);
  const overflowLabelCount = labels.length - visibleLabels.length;

  const handleClick = (e: React.MouseEvent<HTMLLIElement>) => {
    const target = e.target as HTMLElement;
    if (target.closest('input, button, a')) return;
    onOpenPeek?.(issue.key);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLLIElement>) => {
    if (e.key === 'Enter') {
      if (onOpenPeek) {
        onOpenPeek(issue.key);
      } else {
        window.location.href = `?layout=list&peek=${encodeURIComponent(issue.key)}`;
      }
    }
  };

  return (
    <li
      ref={rowRef}
      role="row"
      data-issue-key={issue.key}
      tabIndex={isFocused ? 0 : -1}
      className={`list-row ${isSelected ? 'list-row--selected' : ''} ${
        isActive ? 'list-row--active' : ''
      }`}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      aria-selected={isSelected}
    >
      <div className="list-row-left">
        {onToggleSelect && (
          <span className="list-row-checkbox-wrap">
            <input
              type="checkbox"
              className="list-row-checkbox"
              checked={isSelected}
              aria-label={`Select ${issue.key}`}
              onChange={(e) => { onToggleSelect(issue.key, e.target.checked); }}
            />
          </span>
        )}

        <StateBadge
          state={issue.state}
          showLabel={false}
          className="list-row-state-icon"
        />
        <span hidden aria-hidden="true">
          ●
        </span>

        <PriorityIcon
          priority={issue.priority.slug}
          size={14}
          className="list-row-priority-icon"
        />

        <EmojiHint kind={priorityKind} testId={`hint-prio-${priorityKind}`} />
        {pSlug === 'low' && (
          <span hidden aria-hidden="true">
            💤
          </span>
        )}

        <a
          href={`?layout=list&peek=${encodeURIComponent(issue.key)}`}
          className="list-row-key mono"
          onClick={(e) => {
            if (onOpenPeek) {
              e.preventDefault();
              onOpenPeek(issue.key);
            }
          }}
        >
          {issue.key}
        </a>

        <span className="list-row-summary">{issue.summary}</span>
      </div>

      <div className="list-row-right">
        {gateKind && <EmojiHint kind={gateKind} />}

        {Boolean(issue.has_explicit_acl) && <EmojiHint kind="access" testId="hint-access" />}

        {visibleLabels.map((lbl) => (
          <span key={lbl.id} className="label-pill">
            <LabelDot colorHex={lbl.color_hex} />
            <span>{lbl.name}</span>
          </span>
        ))}

        {overflowLabelCount > 0 && (
          <span className="label-pill">+{overflowLabelCount}</span>
        )}

        {issue.cycle_id && <span className="cycle-pill">Cycle</span>}

        {modulesEnabled && Boolean(issue.module_ids && issue.module_ids.length > 0) && (
          <span className="module-pill">Modules</span>
        )}

        {issue.due_date && (
          <span className={`due-pill ${isOverdue ? 'due-pill--overdue' : ''}`}>
            📅 {issue.due_date}
          </span>
        )}

        {issue.assignees?.map((a) => {
          if (a.kind === 'free_text') {
            return (
              <span
                key={a.id}
                className="assignee-chip assignee-chip--external"
              >
                <EmojiHint kind="externalAssignee" testId="hint-external-assignee" />
                <span>{a.free_text}</span>
              </span>
            );
          }
          return (
            <span key={a.id} className="assignee-chip">
              <span>{a.principal.display_name || a.principal.handle}</span>
            </span>
          );
        })}
      </div>
    </li>
  );
}
