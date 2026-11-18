import React, { useState, type JSX } from 'react';
import type { IssueDetail } from '../drawer/slots';
import type { ProjectLabel } from './railApi';
import { EmojiHint } from '../../components/emoji/EmojiHint';

export interface ParentLabelsRowsProps {
  issue: IssueDetail;
  projectLabels?: ProjectLabel[] | undefined;
  canEdit: boolean;
  onUpdateParent: (parentKey: string | null) => Promise<void>;
  onUpdateLabels: (labelIds: string[]) => Promise<void>;
  onCreateLabel?: ((name: string, colorHex?: string) => Promise<ProjectLabel>) | undefined;
}

const LABEL_PALETTE = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#6b7280'];

export function ParentLabelsRows({
  issue,
  projectLabels = [],
  canEdit,
  onUpdateParent,
  onUpdateLabels,
  onCreateLabel,
}: ParentLabelsRowsProps): JSX.Element {
  const [parentInput, setParentInput] = useState('');
  const [isEditingParent, setIsEditingParent] = useState(false);
  const [parentError, setParentError] = useState<string | null>(null);

  const [labelQuery, setLabelQuery] = useState('');
  const [labelColor, setLabelColor] = useState('#3b82f6');
  const [isLabelMenuOpen, setIsLabelMenuOpen] = useState(false);
  const [exclusiveAnnouncement, setExclusiveAnnouncement] = useState<string | null>(null);

  const parent = issue.parent ?? null;
  const isRestricted = typeof parent === 'object' && parent !== null && parent.restricted === true;

  const currentParentKey =
    typeof parent === 'string'
      ? parent
      : parent?.key ?? '';
  const currentParentSummary = (typeof parent === 'object' && parent !== null ? parent.summary : '') ?? '';

  const handleSaveParent = async (keyToSet: string | null): Promise<void> => {
    setParentError(null);
    try {
      await onUpdateParent(keyToSet);
      setIsEditingParent(false);
      setParentInput('');
    } catch (err: unknown) {
      if (
        typeof err === 'object' &&
        err !== null &&
        (('code' in err && (err as { code: string }).code === 'PARENT_CYCLE') ||
          ('detail' in err && typeof (err).detail === 'string' && ((err as { detail: string }).detail.includes('cycle'))))
      ) {
        setParentError('Cannot set parent: this would create a parent cycle.');
      } else if (
        typeof err === 'object' &&
        err !== null &&
        (('code' in err && (err as { code: string }).code === 'PARENT_DEPTH_EXCEEDED') ||
          ('detail' in err &&
            typeof (err).detail === 'string' &&
            ((err as { detail: string }).detail.includes('depth') ||
              (err as { detail: string }).detail.includes('hierarchy'))))
      ) {
        setParentError('Cannot set parent: maximum hierarchy depth (6) exceeded.');
      } else if (err instanceof Error) {
        setParentError(err.message);
      } else {
        setParentError('Failed to update parent.');
      }
    }
  };

  // Sub-issues rollup computation
  const subIssues = issue.sub_issues ?? [];
  const rollup = issue.sub_issues_rollup ?? null;

  let totalSub = 0;
  let doneSub = 0;
  let percent = 0;

  if (rollup) {
    totalSub = rollup.total;
    doneSub = rollup.completed;
    percent = rollup.percent;
  } else if (subIssues.length > 0) {
    totalSub = subIssues.length;
    doneSub = subIssues.filter(
      (si) => si.state_group === 'completed' || si.state === 'Done',
    ).length;
    percent = totalSub > 0 ? Math.round((doneSub / totalSub) * 100) : 0;
  }

  // Labels logic
  const currentLabelIds: string[] =
    issue.label_ids ??
    issue.labels?.map((l) => (typeof l === 'string' ? l : l.id)) ??
    [];

  const handleToggleLabel = async (label: ProjectLabel): Promise<void> => {
    const isSelected = currentLabelIds.includes(label.id) || currentLabelIds.includes(label.name);
    let updatedIds: string[];

    if (isSelected) {
      updatedIds = currentLabelIds.filter((id) => id !== label.id && id !== label.name);
      setExclusiveAnnouncement(null);
    } else {
      // Exclusive group replacement (Spec S7.2 8i)
      if (label.exclusive_group) {
        const conflicting = projectLabels.find(
          (pl) =>
            pl.exclusive_group === label.exclusive_group &&
            (currentLabelIds.includes(pl.id) || currentLabelIds.includes(pl.name)),
        );
        if (conflicting) {
          updatedIds = currentLabelIds
            .filter((id) => id !== conflicting.id && id !== conflicting.name)
            .concat(label.id);
          setExclusiveAnnouncement(
            `Replaced ${conflicting.name} with ${label.name} (exclusive group: ${label.exclusive_group})`,
          );
        } else {
          updatedIds = [...currentLabelIds, label.id];
          setExclusiveAnnouncement(null);
        }
      } else {
        updatedIds = [...currentLabelIds, label.id];
        setExclusiveAnnouncement(null);
      }
    }

    await onUpdateLabels(updatedIds);
  };

  const handleCreateLabel = async (name: string, colorHex = '#3b82f6'): Promise<void> => {
    if (!onCreateLabel || !name.trim()) return;
    try {
      const created = await onCreateLabel(name.trim(), colorHex);
      await handleToggleLabel(created);
      setLabelQuery('');
      setIsLabelMenuOpen(false);
    } catch {
      // ignore
    }
  };

  return (
    <>
      <div className="prop-row" data-prop="parent">
        <span className="prop-row__label">Parent</span>
        <div className="prop-row__value">
          {isRestricted ? (
            <span className="restricted-parent-chip" data-testid="restricted-parent-chip">
              <EmojiHint
                kind="restricted"
                content="Parent issue is in a restricted scope outside your visibility."
                label="Restricted parent"
              />
              <span>Restricted Parent Issue</span>
            </span>
          ) : isEditingParent ? (
            <div className="parent-row__controls">
              <input
                type="text"
                className="prop-row__input parent-row__input"
                placeholder="e.g. KAN-100"
                value={parentInput}
                onChange={(e) => { setParentInput(e.target.value); }}
                aria-label="Parent issue key"
              />
              <button
                type="button"
                className="creator-row__change-btn"
                onClick={() => void handleSaveParent(parentInput.trim() || null)}
              >
                Set
              </button>
              <button
                type="button"
                className="creator-row__change-btn"
                onClick={() => { setIsEditingParent(false); }}
              >
                Cancel
              </button>
            </div>
          ) : currentParentKey ? (
            <div className="parent-row__current">
              <a
                href={`?peek=${currentParentKey}`}
                className="kb-issue-key-link"
              >
                [{currentParentKey}{currentParentSummary ? ` ${currentParentSummary}` : ''}]
              </a>
              {canEdit ? (
                <>
                  <button
                    type="button"
                    className="creator-row__change-btn"
                    onClick={() => {
                      setParentInput(currentParentKey);
                      setIsEditingParent(true);
                    }}
                  >
                    Change
                  </button>
                  <button
                    type="button"
                    className="creator-row__change-btn"
                    onClick={() => void handleSaveParent(null)}
                  >
                    Clear
                  </button>
                </>
              ) : null}
            </div>
          ) : canEdit ? (
            <button
              type="button"
              className="creator-row__change-btn"
              onClick={() => { setIsEditingParent(true); }}
            >
              + Add Parent
            </button>
          ) : (
            <span className="parent-row__none">None</span>
          )}
        </div>
        {parentError ? (
          <div className="prop-row__alert" role="alert">
            {parentError}
          </div>
        ) : null}
      </div>

      {/* Sub-issues Rollup (S7.1 lines 539-541) */}
      {totalSub > 0 ? (
        <div className="sub-issues-rollup" data-prop="sub-issues-rollup" data-testid="sub-issues-rollup">
          <div className="sub-issues-rollup__header">
            <span>
              Sub-issues ({String(doneSub)}/{String(totalSub)} Done)
            </span>
            <span>{String(percent)}%</span>
          </div>
          <div className="sub-issues-rollup__bar">
            <progress
              className="sub-issues-rollup__progress"
              value={doneSub}
              max={totalSub}
              aria-label={`Sub-issues (${String(doneSub)}/${String(totalSub)} Done)`}
            />
          </div>
        </div>
      ) : null}

      <div className="prop-row" data-prop="labels">
        <span className="prop-row__label">Labels</span>
        <div className="prop-row__value labels-dropdown__container">
          {currentLabelIds.map((lid) => {
            const matched = projectLabels.find((pl) => pl.id === lid || pl.name === lid);
            const displayName = matched?.name ?? lid;
            return (
              <span
                key={lid}
                className="assignee-pill assignee-pill--principal"
              >
                <span>{displayName}</span>
                {canEdit ? (
                  <button
                    type="button"
                    className="assignee-pill__remove"
                    aria-label={`Remove label ${displayName}`}
                    onClick={() => {
                      const next = currentLabelIds.filter((id) => id !== lid && id !== matched?.id);
                      void onUpdateLabels(next);
                    }}
                  >
                    ×
                  </button>
                ) : null}
              </span>
            );
          })}

          {canEdit ? (
            <div className="labels-dropdown__container">
              <button
                type="button"
                className="creator-row__change-btn"
                onClick={() => { setIsLabelMenuOpen((prev) => !prev); }}
                aria-label="Add label"
                aria-expanded={isLabelMenuOpen}
              >
                + Label
              </button>

              {isLabelMenuOpen ? (
                <div className="labels-dropdown__menu">
                  <input
                    type="text"
                    className="prop-row__input labels-dropdown__search"
                    placeholder="Filter or create..."
                    value={labelQuery}
                    onChange={(e) => { setLabelQuery(e.target.value); }}
                  />
                  <div className="labels-dropdown__list">
                    {projectLabels
                      .filter((l) =>
                        labelQuery ? l.name.toLowerCase().includes(labelQuery.toLowerCase()) : true,
                      )
                      .map((label) => {
                        const isChecked =
                          currentLabelIds.includes(label.id) || currentLabelIds.includes(label.name);
                        return (
                          <label
                            key={label.id}
                            className="labels-dropdown__item-btn"
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => void handleToggleLabel(label)}
                            />
                            <span className="labels-dropdown__item-name">{label.name}</span>
                            {label.exclusive_group ? (
                              <span className="labels-dropdown__item-exclusive">
                                ({label.exclusive_group})
                              </span>
                            ) : null}
                          </label>
                        );
                      })}
                  </div>

                  {labelQuery.trim() &&
                  onCreateLabel &&
                  !projectLabels.some((l) => l.name.toLowerCase() === labelQuery.trim().toLowerCase()) ? (
                    <div className="labels-dropdown__create-wrap">
                      <div className="labels-dropdown__color-palette" role="radiogroup" aria-label="Label color">
                        {LABEL_PALETTE.map((c) => (
                          <button
                            key={c}
                            type="button"
                            className={`labels-dropdown__color-swatch ${labelColor === c ? 'labels-dropdown__color-swatch--selected' : ''}`}
                            style={{ backgroundColor: c }}
                            aria-label={`Select color ${c}`}
                            aria-checked={labelColor === c}
                            role="radio"
                            onClick={() => { setLabelColor(c); }}
                          />
                        ))}
                      </div>
                      <button
                        type="button"
                        className="labels-dropdown__clear-btn"
                        onClick={() => void handleCreateLabel(labelQuery, labelColor)}
                      >
                        + Create label &ldquo;{labelQuery.trim()}&rdquo;
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}

          {exclusiveAnnouncement ? (
            <div className="sr-only" aria-live="polite" role="status">
              {exclusiveAnnouncement}
            </div>
          ) : null}
        </div>
      </div>
    </>
  );
}
