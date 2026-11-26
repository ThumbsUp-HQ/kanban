// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX } from 'react';
import {
  draggable,
  dropTargetForElements,
} from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { HookPipelineRow } from './HookPipelineRow';
import type { AgentDefinitionSummary, TransitionRule, WorkflowHook } from './api';

export interface TransitionRuleCardProps {
  rule: TransitionRule;
  projectKey: string;
  projectDefaultTimeoutMs?: number | null | undefined;
  agents?: AgentDefinitionSummary[] | undefined;
  onReorder: (
    transition: { from_state: string | null; to_state: string },
    orderedHookIds: string[],
  ) => Promise<void>;
  onToggle: (hookId: string, isEnabled: boolean) => Promise<void>;
  onEdit: (hook: WorkflowHook) => void;
  onDetach: (hookId: string) => Promise<void>;
  onAddHook: (transition: { from_state: string | null; to_state: string }) => void;
  onDryRun: (transition: { from_state: string | null; to_state: string }) => void;
  draggableFactory?: typeof draggable;
  dropTargetFactory?: typeof dropTargetForElements;
}

export function TransitionRuleCard({
  rule,
  projectKey,
  projectDefaultTimeoutMs,
  agents,
  onReorder,
  onToggle,
  onEdit,
  onDetach,
  onAddHook,
  onDryRun,
  draggableFactory = draggable,
  dropTargetFactory = dropTargetForElements,
}: TransitionRuleCardProps): JSX.Element {
  const [localHooks, setLocalHooks] = useState<WorkflowHook[]>(rule.hooks);
  const [reorderError, setReorderError] = useState<string | null>(null);

  // Sync when rule.hooks changes from query refetch
  const effectiveHooks = localHooks.length === rule.hooks.length ? localHooks : rule.hooks;

  const activeCount = effectiveHooks.filter((h) => h.is_enabled).length;
  const fromLabel = rule.from_state ?? '* Any State';
  const toLabel = rule.to_state;

  const handleKeyboardMove = async (hookId: string, direction: 'up' | 'down') => {
    const currentIndex = effectiveHooks.findIndex((h) => h.id === hookId);
    /* v8 ignore next */
    if (currentIndex === -1) return;

    const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1;
    /* v8 ignore next */
    if (targetIndex < 0 || targetIndex >= effectiveHooks.length) return;

    const movedHook = effectiveHooks[currentIndex];
    /* v8 ignore next */
    if (!movedHook) return;
    const newHooks = effectiveHooks.filter((h) => h.id !== hookId);
    newHooks.splice(targetIndex, 0, movedHook);

    // Optimistic update
    const previousHooks = [...effectiveHooks];
    setLocalHooks(newHooks);
    setReorderError(null);

    try {
      await onReorder(
        { from_state: rule.from_state, to_state: rule.to_state },
        newHooks.map((h) => h.id),
      );
    } catch (err: unknown) {
      setLocalHooks(previousHooks);
      if (err instanceof Error) {
        setReorderError(err.message);
      } else {
        setReorderError('Reorder failed: 422 REORDER_SET_MISMATCH');
      }
    }
  };

  const handleDropReorder = async (sourceId: string, targetId: string) => {
    const sourceIndex = effectiveHooks.findIndex((h) => h.id === sourceId);
    const targetIndex = effectiveHooks.findIndex((h) => h.id === targetId);
    if (sourceIndex === -1 || targetIndex === -1 || sourceIndex === targetIndex) return;

    const movedHook = effectiveHooks[sourceIndex];
    /* v8 ignore next */
    if (!movedHook) return;
    const newHooks = effectiveHooks.filter((h) => h.id !== sourceId);
    newHooks.splice(targetIndex, 0, movedHook);

    // Optimistic update
    const previousHooks = [...effectiveHooks];
    setLocalHooks(newHooks);
    setReorderError(null);

    try {
      await onReorder(
        { from_state: rule.from_state, to_state: rule.to_state },
        newHooks.map((h) => h.id),
      );
    } catch (err: unknown) {
      setLocalHooks(previousHooks);
      if (err instanceof Error) {
        setReorderError(err.message);
      } else {
        setReorderError('Reorder failed: 422 REORDER_SET_MISMATCH');
      }
    }
  };

  return (
    <section
      className="transition-rule-card"
      data-testid={`transition-card-${rule.from_state ?? 'any'}-${rule.to_state}`}
      aria-label={`Transition Rule: ${fromLabel} to ${toLabel}`}
    >
      {/* Top arrow bar */}
      <div className="transition-arrow-bar">
        <div className="transition-states-container">
          <span>Transition:</span>
          <span className="state-badge state-badge-from">
            {fromLabel.includes('Review') ? '🟣 ' : '⚪ '}
            {fromLabel}
          </span>
          <div className="transition-arrow-connector">
            <span>========(</span>
            <span className="active-hooks-badge" data-testid="active-hooks-count">
              {activeCount} Active Hook{activeCount === 1 ? '' : 's'}
            </span>
            <span>)========&gt;</span>
          </div>
          <span className="state-badge state-badge-to">
            {toLabel.includes('Done') ? '🟢 ' : '⚪ '}
            {toLabel}
          </span>
        </div>

        <div className="hook-actions-group">
          <button
            type="button"
            className="workflow-btn workflow-btn-secondary workflow-btn-sm"
            onClick={() => {
              onAddHook({ from_state: rule.from_state, to_state: rule.to_state });
            }}
            aria-label={`Add hook to ${fromLabel} to ${toLabel}`}
          >
            + Add Hook
          </button>
        </div>
      </div>

      {/* Accessible Reorder Error Alert */}
      {reorderError && (
        <div className="workflow-alert workflow-alert-danger" role="alert">
          <strong>Reorder Error:</strong> {reorderError}
        </div>
      )}

      {/* Ordered hooks or empty state */}
      {effectiveHooks.length === 0 ? (
        <div className="empty-hooks-cta" data-testid="empty-hooks-cta">
          No hooks configured for this transition. Click &apos;+ Add Hook&apos; to attach a validator or agent gate.
        </div>
      ) : (
        <div className="hook-pipeline-list" role="list" aria-label="Hook Pipeline List">
          {effectiveHooks.map((hook, index) => (
            <HookPipelineRow
              key={hook.id}
              hook={hook}
              index={index}
              total={effectiveHooks.length}
              projectKey={projectKey}
              projectDefaultTimeoutMs={projectDefaultTimeoutMs}
              agents={agents}
              onMove={(id, dir) => {
                void handleKeyboardMove(id, dir);
              }}
              onDropReorder={(src, tgt) => {
                void handleDropReorder(src, tgt);
              }}
              onToggle={(id, isEnabled) => {
                void onToggle(id, isEnabled);
              }}
              onEdit={onEdit}
              onDetach={(id) => {
                void onDetach(id);
              }}
              draggableFactory={draggableFactory}
              dropTargetFactory={dropTargetFactory}
            />
          ))}
        </div>
      )}

      {/* Card bottom actions */}
      <div className="transition-card-footer">
        <span className="hook-command-summary">
          Total configured hooks: {effectiveHooks.length}
        </span>
        <button
          type="button"
          className="workflow-btn workflow-btn-primary"
          onClick={() => {
            onDryRun({ from_state: rule.from_state, to_state: rule.to_state });
          }}
          aria-label={`Dry-run against sample ticket for ${fromLabel} to ${toLabel}`}
        >
          ▶ Dry-Run Against Sample Ticket
        </button>
      </div>
    </section>
  );
}
