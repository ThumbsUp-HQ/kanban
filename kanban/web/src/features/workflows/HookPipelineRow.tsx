// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useEffect, useRef, useState, type JSX } from 'react';
import {
  draggable,
  dropTargetForElements,
} from '@atlaskit/pragmatic-drag-and-drop/element/adapter';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { AgentDefinitionSummary, WorkflowHook } from './api';

export interface HookPipelineRowProps {
  hook: WorkflowHook;
  index: number;
  total: number;
  projectKey: string;
  agentTimeoutMs?: number | undefined;
  agents?: AgentDefinitionSummary[] | undefined;
  onMove?: (hookId: string, direction: 'up' | 'down') => void;
  onToggle?: (hookId: string, isEnabled: boolean) => void;
  onEdit?: (hook: WorkflowHook) => void;
  onDetach?: (hookId: string) => void;
  onDropReorder?: (sourceId: string, targetId: string) => void;
  draggableFactory?: typeof draggable;
  dropTargetFactory?: typeof dropTargetForElements;
}

export function HookPipelineRow({
  hook,
  index,
  total,
  projectKey,
  agentTimeoutMs,
  agents,
  onMove,
  onToggle,
  onEdit,
  onDetach,
  onDropReorder,
  draggableFactory = draggable,
  dropTargetFactory = dropTargetForElements,
}: HookPipelineRowProps): JSX.Element {
  const rowRef = useRef<HTMLDivElement | null>(null);
  const copyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [copiedSha, setCopiedSha] = useState(false);

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current !== null) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const el = rowRef.current;
    if (!el) return undefined;

    const cleanupDraggable = draggableFactory({
      element: el,
      getInitialData: () => ({ type: 'hook-row', hookId: hook.id, index }),
      onDragStart: () => { setIsDragging(true); },
      onDrop: () => { setIsDragging(false); },
    });

    const cleanupDropTarget = dropTargetFactory({
      element: el,
      getData: () => ({ type: 'hook-row', hookId: hook.id, index }),
      onDrop: ({ source }) => {
        setIsDragging(false);
        const sourceData = source.data as { type?: string; hookId?: string } | undefined;
        if (sourceData?.type === 'hook-row' && sourceData.hookId && sourceData.hookId !== hook.id) {
          onDropReorder?.(sourceData.hookId, hook.id);
        }
      },
    });

    return () => {
      cleanupDraggable();
      cleanupDropTarget();
    };
  }, [hook.id, index, onDropReorder, draggableFactory, dropTargetFactory]);

  const handleCopySha = async () => {
    try {
      await navigator.clipboard.writeText(hook.manifest_sha256);
      setCopiedSha(true);
      if (copyTimeoutRef.current !== null) {
        clearTimeout(copyTimeoutRef.current);
      }
      copyTimeoutRef.current = setTimeout(() => {
        if (typeof window !== 'undefined') {
          setCopiedSha(false);
        }
      }, 2000);
    } catch {
      // Fallback ignore in test env
    }
  };

  // Determine badge text for Agent Gate
  const getAgentBadgeLabel = (): string => {
    if (hook.harness_kind === 'cli_pipe') {
      return '[CLI Agent Gate]';
    }
    if (hook.harness_kind === 'in_app_sdk') {
      if (hook.provider_kind === 'ollama') {
        return '[Local Ollama Gate]';
      }
      return '[SDK Agent Gate]';
    }
    if (hook.harness_kind === 'remote_runner') {
      return '[Remote WSS Gate]';
    }
    return '[Agent Gate]';
  };

  // Command summary string e.g. (`${context} | agy -p`) or (`ollama/qwen2.5-coder`)
  const getCommandSummary = (): string | null => {
    if (hook.hook_kind !== 'agent_interceptor') return null;
    if (hook.harness_kind === 'cli_pipe') {
      const bin = hook.cli_binary_allowlist_id ?? 'agy';
      const args = hook.cli_args && hook.cli_args.length > 0 ? ` ${hook.cli_args.join(' ')}` : '';
      return `(\${context} | ${bin}${args})`;
    }
    if (hook.harness_kind === 'in_app_sdk' && hook.model_id) {
      return `(${hook.model_id})`;
    }
    return null;
  };

  // Truncated SHA-256 for display
  const truncatedSha = hook.manifest_sha256
    ? `sha256:${hook.manifest_sha256.slice(0, 8)}...`
    : 'sha256:none';

  // Format latency or timeout
  const matchingAgent = agents?.find((a) => a.slug === hook.agent_slug);
  const resolvedAgentTimeout =
    agentTimeoutMs ??
    hook.timeout_ms ??
    matchingAgent?.timeout_ms;

  const latencyOrTimeout =
    hook.hook_kind === 'agent_interceptor'
      ? (resolvedAgentTimeout ? `${String(Math.round(resolvedAgentTimeout / 1000))}s` : '')
      : (hook.target_latency_budget ?? '<25ms');

  const isSync = hook.hook_kind === 'sync_validator' || hook.hook_kind === 'sync_mutator';
  const commandSummary = getCommandSummary();

  const rowClasses = [
    'hook-pipeline-row',
    !hook.is_enabled ? 'is-disabled' : '',
    isDragging ? 'is-dragging' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <article
      ref={rowRef}
      className={rowClasses}
      data-testid={`hook-pipeline-row-${hook.id}`}
      aria-label={`Workflow Hook: ${hook.name}`}
    >
      <div className="hook-pipeline-main">
        <div className="hook-pipeline-left">
          {/* Drag Handle & Order */}
          <button
            type="button"
            className="hook-drag-handle"
            aria-label={`Drag to reorder ${hook.name}`}
            title="Drag to reorder"
          >
            ⋮⋮
          </button>
          <span className="hook-order-number">{index + 1}.</span>

          {/* Hook Type Badge */}
          {isSync ? (
            <span className="hook-type-badge hook-type-sync">
              ⚡ {hook.hook_kind === 'sync_validator' ? '[Sync Wasm Validator]' : '[Sync Wasm Mutator]'}
            </span>
          ) : (
            <span className="hook-type-badge hook-type-agent">
              <EmojiHint
                kind="agent"
                label={getAgentBadgeLabel()}
                testId={`emoji-hint-${hook.id}`}
                content={
                  <div>
                    <strong>{hook.name}</strong>
                    <div>Harness: {hook.harness_kind ?? 'cli_pipe'}</div>
                    {Boolean(hook.repo_binding_slug) && hook.repo_access_mode !== 'none' && (
                      <div>Repo: {hook.repo_binding_slug} (:ro mount)</div>
                    )}
                    <div>MCP: {hook.mcp_access_summary ?? `Read-Only (${projectKey})`}</div>
                  </div>
                }
              />
              <span>{getAgentBadgeLabel()}</span>
            </span>
          )}

          {/* Hook Name & Command Summary */}
          <span className="hook-name">{hook.name}</span>
          {commandSummary && <span className="hook-command-summary">{commandSummary}</span>}
        </div>

        <div className="hook-pipeline-right">
          {/* Latency / Timeout metric pill */}
          {latencyOrTimeout && (
            <span className="hook-metric-pill" data-testid={`hook-latency-${hook.id}`}>
              {latencyOrTimeout}
            </span>
          )}

          {/* Failure Policy badge */}
          <span
            className={`hook-policy-badge ${
              hook.failure_policy === 'fail_closed' ? 'policy-fail-closed' : 'policy-fail-open'
            }`}
          >
            {hook.failure_policy === 'fail_closed' ? 'Fail-Closed' : 'Fail-Open (Warn)'}
          </span>

          {/* Truncated SHA256 Chip */}
          <button
            type="button"
            className="hook-sha256-chip"
            onClick={() => {
              void handleCopySha();
            }}
            title={`Click to copy full SHA-256: ${hook.manifest_sha256}`}
            aria-label={`Copy SHA256: ${truncatedSha}`}
          >
            {copiedSha ? 'Copied!' : truncatedSha}
          </button>

          {/* Keyboard Reordering Buttons */}
          <div className="hook-actions-group" role="group" aria-label="Reorder actions">
            <button
              type="button"
              className="hook-move-btn"
              disabled={index === 0}
              onClick={() => onMove?.(hook.id, 'up')}
              aria-label={`Move ${hook.name} up`}
            >
              Move up
            </button>
            <button
              type="button"
              className="hook-move-btn"
              disabled={index === total - 1}
              onClick={() => onMove?.(hook.id, 'down')}
              aria-label={`Move ${hook.name} down`}
            >
              Move down
            </button>
          </div>

          {/* Toggle Switch */}
          <label className="hook-toggle-switch" htmlFor={`hook-toggle-${hook.id}`} aria-label={`Enable or disable ${hook.name}`}>
            <input
              id={`hook-toggle-${hook.id}`}
              type="checkbox"
              checked={hook.is_enabled}
              onChange={(e) => onToggle?.(hook.id, e.target.checked)}
              aria-label={`Toggle ${hook.name}`}
            />
            <span className="hook-toggle-slider" />
          </label>

          {/* Edit & Detach */}
          <button
            type="button"
            className="workflow-btn workflow-btn-secondary workflow-btn-sm"
            onClick={() => onEdit?.(hook)}
            aria-label={`Edit ${hook.name}`}
          >
            Edit
          </button>
          <button
            type="button"
            className="workflow-btn workflow-btn-danger workflow-btn-sm"
            onClick={() => onDetach?.(hook.id)}
            aria-label={`Detach ${hook.name}`}
          >
            Detach
          </button>
        </div>
      </div>

      {/* Subtitle / Metadata row */}
      <div className="hook-pipeline-subtitle">
        {hook.hook_kind === 'agent_interceptor' ? (
          <>
            {Boolean(hook.repo_binding_slug) && hook.repo_access_mode !== 'none' && (
              <>
                <span>Repo: <code>{hook.repo_binding_slug}</code> (:ro mount)</span>
                <span>|</span>
              </>
            )}
            <span>MCP: {hook.mcp_access_summary ?? `Read-Only (${projectKey})`}</span>
            <span>|</span>
            <span>Mutable Fields:</span>
            <div className="mutable-fields-chips">
              {hook.allowed_mutable_fields && hook.allowed_mutable_fields.length > 0 ? (
                hook.allowed_mutable_fields.map((field) => (
                  <span key={field} className="field-chip">
                    [{field}]
                  </span>
                ))
              ) : (
                <span className="field-chip">[none]</span>
              )}
            </div>
          </>
        ) : (
          <span>{hook.description ?? 'Synchronous Wasm validator executing in isolated runtime.'}</span>
        )}
      </div>
    </article>
  );
}
