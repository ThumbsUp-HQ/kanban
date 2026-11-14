import React, { useState, useEffect, useRef, type JSX } from 'react';
import type { IssueItem } from './viewsApi';
import './filterBulk.css';

export interface QuickCreateIssueModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (newIssue: Partial<IssueItem>) => void;
  projectKey: string;
  modulesEnabled?: boolean;
  defaultStateId?: string;
  defaultPrioritySlug?: string;
  defaultModuleIds?: string[];
}

export function QuickCreateIssueModal({
  isOpen,
  onClose,
  onCreate,
  projectKey,
  modulesEnabled = true,
  defaultStateId = 'state-todo',
  defaultPrioritySlug = 'medium',
  defaultModuleIds = ['mod-1'],
}: QuickCreateIssueModalProps): JSX.Element | null {
  const [summary, setSummary] = useState('');
  const [description, setDescription] = useState('');
  const [stateId, setStateId] = useState(defaultStateId);
  const [prioritySlug, setPrioritySlug] = useState(defaultPrioritySlug);
  const [selectedModuleIds, setSelectedModuleIds] = useState<string[]>(
    modulesEnabled ? defaultModuleIds : []
  );

  const summaryInputRef = useRef<HTMLInputElement>(null);

  // Focus input on open
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        summaryInputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  // Listen for custom event 'kb:create-issue'
  useEffect(() => {
    const handleCustomCreate = () => {
      // Triggered by external buttons / CommandPalette
    };
    window.addEventListener('kb:create-issue', handleCustomCreate);
    return () => { window.removeEventListener('kb:create-issue', handleCustomCreate); };
  }, []);

  // Escape key handler
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => { window.removeEventListener('keydown', handleKeyDown); };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  const handleSubmit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!summary.trim()) return;

    const payload: Partial<IssueItem> = {
      summary: summary.trim(),
      state: {
        id: stateId,
        name: stateId.includes('progress') ? 'In Progress' : stateId.includes('todo') ? 'Todo' : 'Backlog',
        group: stateId.includes('progress') ? 'started' : stateId.includes('todo') ? 'unstarted' : 'backlog',
      },
      priority: {
        slug: prioritySlug,
        label: prioritySlug.charAt(0).toUpperCase() + prioritySlug.slice(1),
        emoji: prioritySlug === 'urgent' ? '🔥' : prioritySlug === 'high' ? '⚡' : '🔹',
      },
    };

    if (description.trim()) {
      payload.description_markdown = description.trim();
    }
    if (modulesEnabled) {
      payload.module_ids = selectedModuleIds;
    }

    onCreate(payload);

    setSummary('');
    setDescription('');
    onClose();
  };

  return (
    <div
      className="quick-create-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="quick-create-title"
    >
      <div className="quick-create-modal">
        <div className="quick-create-header">
          <h2 id="quick-create-title" className="quick-create-title">
            Create work item in {projectKey}
          </h2>
          <button
            type="button"
            className="filter-chip-remove"
            onClick={onClose}
            aria-label="Close modal"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="quick-create-form">
          <div className="quick-create-input-group">
            <label htmlFor="quick-create-summary" className="quick-create-label">
              Summary
            </label>
            <input
              ref={summaryInputRef}
              id="quick-create-summary"
              type="text"
              className="quick-create-input"
              placeholder="What needs to be done?"
              value={summary}
              onChange={(e) => { setSummary(e.target.value); }}
              required
            />
          </div>

          <div className="quick-create-input-group">
            <label
              htmlFor="quick-create-description"
              className="quick-create-label"
            >
              Description (Markdown)
            </label>
            <textarea
              id="quick-create-description"
              className="quick-create-textarea"
              placeholder="Add details, acceptance criteria, or Mermaid diagrams..."
              value={description}
              onChange={(e) => { setDescription(e.target.value); }}
            />
          </div>

          <div className="quick-create-row-fields">
            <div className="quick-create-input-group quick-create-input-group--flex1">
              <label htmlFor="quick-create-state" className="quick-create-label">
                State
              </label>
              <select
                id="quick-create-state"
                className="quick-create-select"
                value={stateId}
                onChange={(e) => { setStateId(e.target.value); }}
              >
                <option value="state-backlog">Backlog</option>
                <option value="state-todo">Todo</option>
                <option value="state-in-progress">In Progress</option>
                <option value="state-done">Done</option>
              </select>
            </div>

            <div className="quick-create-input-group quick-create-input-group--flex1">
              <label
                htmlFor="quick-create-priority"
                className="quick-create-label"
              >
                Priority
              </label>
              <select
                id="quick-create-priority"
                className="quick-create-select"
                value={prioritySlug}
                onChange={(e) => { setPrioritySlug(e.target.value); }}
              >
                <option value="urgent">🔥 Urgent</option>
                <option value="high">⚡ High</option>
                <option value="medium">🔹 Medium</option>
                <option value="low">💤 Low</option>
                <option value="none">None</option>
              </select>
            </div>

            {/* Modules field: conditionally mounted ONLY when modulesEnabled is true (S7.2 8f) */}
            {modulesEnabled && (
              <div className="quick-create-input-group quick-create-input-group--flex1">
                <label
                  htmlFor="quick-create-module"
                  className="quick-create-label"
                >
                  Module
                </label>
                <select
                  id="quick-create-module"
                  className="quick-create-select"
                  value={selectedModuleIds[0] ?? ''}
                  onChange={(e) => { setSelectedModuleIds(e.target.value ? [e.target.value] : []); }
                  }
                >
                  <option value="">No Module</option>
                  <option value="mod-1">Auth Core</option>
                  <option value="mod-2">Kanban Board</option>
                </select>
              </div>
            )}
          </div>

          <div className="quick-create-footer">
            <button
              type="button"
              className="quick-create-btn-cancel"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="quick-create-btn-submit"
              disabled={!summary.trim()}
            >
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
