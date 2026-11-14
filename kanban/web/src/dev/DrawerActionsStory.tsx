/**
 * DrawerActionsStory Component (KB-P3-43, S7.1, S7.2 8l-8q).
 * Interactive development gallery hosting Subscribe, Link Graph, and Overflow actions.
 */

import React, { useState, type JSX } from 'react';
import { SubscribeAction } from '../features/drawer-actions/SubscribeAction';
import { LinkGraphAction } from '../features/drawer-actions/LinkGraphAction';
import { IssueOverflowMenu } from '../features/drawer-actions/IssueOverflowMenu';
import type { IssueDetail } from '../features/drawer/slots';
import './DrawerActionsStory.css';

const mockIssueStarted: IssueDetail = {
  key: 'KAN-142',
  object_id: '018f0000-0000-7000-8000-000000000142',
  project_key: 'KAN',
  project_name: 'Kanban Platform',
  summary: 'Harden OAuth and MCP token security',
  state: { name: 'In Progress', group: 'started' },
  capabilities: ['VIEW', 'EDIT', 'DELETE'],
};

const mockIssueDone: IssueDetail = {
  key: 'KAN-143',
  object_id: '018f0000-0000-7000-8000-000000000143',
  project_key: 'KAN',
  project_name: 'Kanban Platform',
  summary: 'Universal Object Graph Link Auditor & Purger',
  state: { name: 'Done', group: 'completed' },
  capabilities: ['VIEW', 'EDIT', 'DELETE'],
};

export function DrawerActionsStory(): JSX.Element {
  const [selectedKey, setSelectedKey] = useState<'KAN-142' | 'KAN-143'>('KAN-142');
  const [mode, setMode] = useState<'drawer' | 'full'>('drawer');

  const currentIssue = selectedKey === 'KAN-142' ? mockIssueStarted : mockIssueDone;

  return (
    <div className="drawer-actions-story" data-testid="drawer-actions-story">
      <header className="drawer-actions-story__header">
        <h1>Ticket Header & Overflow Actions Story (KB-P3-43)</h1>
        <p>Interactive verification harness for Subscribe 🔔, Link Graph 🔗, and Overflow Menu ⋯</p>
      </header>

      <div className="drawer-actions-story__controls">
        <button
          type="button"
          className={`drawer-action-btn ${selectedKey === 'KAN-142' ? 'drawer-action-btn--active' : ''}`}
          onClick={() => { setSelectedKey('KAN-142'); }}
          data-testid="select-started-btn"
        >
          Select KAN-142 (In Progress)
        </button>
        <button
          type="button"
          className={`drawer-action-btn ${selectedKey === 'KAN-143' ? 'drawer-action-btn--active' : ''}`}
          onClick={() => { setSelectedKey('KAN-143'); }}
          data-testid="select-done-btn"
        >
          Select KAN-143 (Completed)
        </button>
        <span data-testid="story-mode-status">Mode: {mode}</span>
      </div>

      <div className="drawer-actions-story__surface">
        <div className="drawer-actions-story__top-row" data-testid="ticket-header-row">
          <div className="drawer-actions-story__issue-title">
            <span className="drawer-actions-story__key">{currentIssue.key}</span>
            <span className="drawer-actions-story__summary">{currentIssue.summary}</span>
          </div>

          <div className="drawer-actions-story__actions-slot" data-slot="header-actions">
            <SubscribeAction issue={currentIssue} />
            <LinkGraphAction issue={currentIssue} />
            <IssueOverflowMenu
              issue={currentIssue}
              mode={mode}
              toggleFullScreen={() => { setMode((prev) => (prev === 'drawer' ? 'full' : 'drawer')); }}
            />
          </div>
        </div>

        <div className="drawer-actions-story__body">
          <p>Prose and properties surface placeholder for {currentIssue.key}.</p>
        </div>
      </div>
    </div>
  );
}
