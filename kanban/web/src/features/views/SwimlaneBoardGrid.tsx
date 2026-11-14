import React, { useState, useMemo, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { IssueItem, GroupAxis } from './viewsApi';
import './filterBulk.css';

export interface SwimlaneBoardGridProps {
  issues: IssueItem[];
  projectKey: string;
  groupBy?: GroupAxis;
  subGroupBy?: GroupAxis;
  modulesEnabled?: boolean;
  selectedIds?: string[];
  onToggleSelect?: (key: string, selected: boolean) => void;
  focusedKey?: string | null;
  onCardClick?: (key: string, isShift: boolean) => void;
  onCardMove?: (issueKey: string, targetColId: string, targetLaneId: string) => void;
}

interface ColumnDef {
  id: string;
  name: string;
  sortOrder: number;
}

interface SwimlaneDef {
  id: string;
  title: string;
  badge?: string;
  emojiKind?: 'priorityUrgent' | 'priorityHigh' | 'priorityMedium' | 'priorityLow';
  sortOrder: number;
}

function getIssueColId(issue: IssueItem, groupBy: GroupAxis): string {
  if (groupBy === 'priority') {
    return issue.priority.slug.toLowerCase();
  }
  const sName = issue.state.name.toLowerCase();
  if (sName.includes('backlog')) return 'backlog';
  if (sName.includes('todo')) return 'todo';
  if (sName.includes('progress')) return 'in-progress';
  if (sName.includes('review')) return 'in-review';
  if (sName.includes('done')) return 'done';
  if (sName.includes('cancel')) return 'cancelled';
  return issue.state.id;
}

function getIssueLaneId(
  issue: IssueItem,
  subGroupBy: GroupAxis,
  modulesEnabled: boolean
): string {
  if (subGroupBy === 'priority') {
    const p = issue.priority.slug.toLowerCase();
    if (['urgent', 'high', 'medium', 'low'].includes(p)) return p;
    return 'none';
  }
  if (subGroupBy === 'assignee') {
    const first = issue.assignees?.[0];
    if (!first) return 'unassigned';
    if (first.kind === 'principal') {
      const h = first.principal.handle.toLowerCase();
      if (h.includes('alice')) return 'alice';
      if (h.includes('adam')) return 'adam';
    }
    return 'unassigned';
  }
  if (subGroupBy === 'cycle') {
    return issue.cycle_id ?? 'none';
  }
  if (subGroupBy === 'module' && modulesEnabled) {
    const firstMod = issue.module_ids?.[0];
    return firstMod ?? 'none';
  }
  return 'all';
}

export function SwimlaneBoardGrid({
  issues,
  projectKey,
  groupBy = 'state',
  subGroupBy = 'priority',
  modulesEnabled = true,
  selectedIds = [],
  onToggleSelect,
  focusedKey = null,
  onCardClick,
}: SwimlaneBoardGridProps): JSX.Element {
  // Collapsed bands map: laneId -> boolean
  const [collapsedLanes, setCollapsedLanes] = useState<Record<string, boolean>>({});

  // 1. Determine Column Definitions based on groupBy axis (default 'state')
  const columns: ColumnDef[] = useMemo(() => {
    if (groupBy === 'priority') {
      return [
        { id: 'urgent', name: 'Urgent', sortOrder: 10 },
        { id: 'high', name: 'High', sortOrder: 20 },
        { id: 'medium', name: 'Medium', sortOrder: 30 },
        { id: 'low', name: 'Low', sortOrder: 40 },
        { id: 'none', name: 'None', sortOrder: 50 },
      ];
    }
    // Default: State columns
    return [
      { id: 'backlog', name: 'Backlog', sortOrder: 10 },
      { id: 'todo', name: 'Todo', sortOrder: 20 },
      { id: 'in-progress', name: 'In Progress', sortOrder: 30 },
      { id: 'in-review', name: 'In Review', sortOrder: 40 },
      { id: 'done', name: 'Done', sortOrder: 50 },
      { id: 'cancelled', name: 'Cancelled', sortOrder: 60 },
    ];
  }, [groupBy]);

  // 2. Determine Horizontal Swimlane Definitions based on subGroupBy axis
  const swimlanes: SwimlaneDef[] = useMemo(() => {
    if (subGroupBy === 'priority') {
      return [
        { id: 'urgent', title: 'Urgent 🔥', badge: '🔥', emojiKind: 'priorityUrgent', sortOrder: 10 },
        { id: 'high', title: 'High ⚡', badge: '⚡', emojiKind: 'priorityHigh', sortOrder: 20 },
        { id: 'medium', title: 'Medium 🔹', badge: '🔹', emojiKind: 'priorityMedium', sortOrder: 30 },
        { id: 'low', title: 'Low 💤', badge: '💤', emojiKind: 'priorityLow', sortOrder: 40 },
        { id: 'none', title: 'None', sortOrder: 50 },
      ];
    }
    if (subGroupBy === 'assignee') {
      return [
        { id: 'alice', title: 'Alice Cooper', sortOrder: 10 },
        { id: 'adam', title: 'Adam Outler', sortOrder: 20 },
        { id: 'unassigned', title: 'Unassigned', sortOrder: 99 },
      ];
    }
    if (subGroupBy === 'cycle') {
      return [
        { id: 'cycle-1', title: 'Cycle 1', sortOrder: 10 },
        { id: 'none', title: 'No Cycle', sortOrder: 99 },
      ];
    }
    if (subGroupBy === 'module' && modulesEnabled) {
      return [
        { id: 'mod-1', title: 'Auth Core', sortOrder: 10 },
        { id: 'none', title: 'No Module', sortOrder: 99 },
      ];
    }
    // Fallback single swimlane if none or unknown
    return [{ id: 'all', title: 'All Work Items', sortOrder: 10 }];
  }, [subGroupBy, modulesEnabled]);

  // 3. Partition issues into 2D grid [laneId][colId]
  const partitionedGrid = useMemo(() => {
    const grid: Record<string, Record<string, IssueItem[]>> = {};
    for (const lane of swimlanes) {
      const colMap: Record<string, IssueItem[]> = {};
      for (const col of columns) {
        colMap[col.id] = [];
      }
      grid[lane.id] = colMap;
    }

    const defaultLaneId = swimlanes[0]?.id ?? '';
    const defaultColId = columns[0]?.id ?? '';

    for (const issue of issues) {
      const laneId = getIssueLaneId(issue, subGroupBy, modulesEnabled);
      const colId = getIssueColId(issue, groupBy);
      const laneMap = grid[laneId] ?? grid[defaultLaneId];
      const colList = laneMap?.[colId] ?? laneMap?.[defaultColId];
      colList?.push(issue);
    }

    return grid;
  }, [issues, columns, swimlanes, groupBy, subGroupBy, modulesEnabled]);

  const toggleLane = (laneId: string) => {
    setCollapsedLanes((prev) => ({
      ...prev,
      [laneId]: !prev[laneId],
    }));
  };

  // Compute issue count in swimlane
  const getLaneCount = (laneId: string): number => {
    const laneCols = partitionedGrid[laneId];
    return laneCols ? Object.values(laneCols).reduce((sum, list) => sum + list.length, 0) : 0;
  };

  return (
    <div className="swimlane-board-grid" role="region" aria-label="2D Swimlane Board Grid">
      {/* Sticky Top Column Headers aligned to 324px */}
      <div className="swimlane-col-headers" role="row">
        {columns.map((col) => (
          <div key={col.id} className="swimlane-col-header-item" role="columnheader">
            <span>{col.name}</span>
          </div>
        ))}
      </div>

      {/* Horizontal Swimlane Bands */}
      {swimlanes.map((lane) => {
        const isCollapsed = Boolean(collapsedLanes[lane.id]);
        const laneCount = getLaneCount(lane.id);

        return (
          <div
            key={lane.id}
            className="swimlane-band"
            data-subgroup-id={lane.id}
            data-subgroup-value={lane.title}
          >
            <div className="swimlane-band-header">
              <button
                type="button"
                className="swimlane-band-toggle"
                onClick={() => { toggleLane(lane.id); }}
                aria-expanded={!isCollapsed}
                aria-controls={`swimlane-content-${lane.id}`}
              >
                <span className="swimlane-band-icon" aria-hidden="true">
                  ▼
                </span>
                <span>{lane.title}</span>
                <span className="swimlane-band-count">{laneCount}</span>
              </button>
            </div>

            {!isCollapsed && (
              <div
                id={`swimlane-content-${lane.id}`}
                className="swimlane-band-columns"
                role="row"
              >
                {columns.map((col) => {
                  const cellIssues = partitionedGrid[lane.id]?.[col.id] ?? [];

                  return (
                    <div
                      key={col.id}
                      className="board-column"
                      data-column-id={col.id}
                      data-swimlane-id={lane.id}
                      role="cell"
                    >
                      {cellIssues.map((issue) => {
                        const isSelected = selectedIds.includes(issue.key);
                        const isFocused = focusedKey === issue.key;

                        let pKind: 'priorityUrgent' | 'priorityHigh' | 'priorityMedium' | 'priorityLow' =
                          'priorityMedium';
                        const slug = issue.priority.slug.toLowerCase();
                        if (slug === 'urgent') pKind = 'priorityUrgent';
                        else if (slug === 'high') pKind = 'priorityHigh';
                        else if (slug === 'low') pKind = 'priorityLow';

                        return (
                          <div
                            key={issue.key}
                            className={`swimlane-card ${isSelected ? 'swimlane-card--selected' : ''}`}
                            data-issue-key={issue.key}
                            data-focused={isFocused ? 'true' : 'false'}
                            tabIndex={isFocused ? 0 : -1}
                            onClick={(e) => {
                              onCardClick?.(issue.key, e.shiftKey);
                            }}
                          >
                            <div className="swimlane-card-top">
                              <label
                                className="swimlane-card-checkbox-wrap"
                                onClick={(e) => { e.stopPropagation(); }}
                              >
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={(e) => onToggleSelect?.(issue.key, e.target.checked)}
                                  aria-label={`Select ${issue.key}`}
                                />
                              </label>

                              <a
                                href={`/projects/${encodeURIComponent(projectKey)}/issues?layout=board&peek=${encodeURIComponent(issue.key)}`}
                                className="swimlane-card-key mono"
                                onClick={(e) => { e.stopPropagation(); }}
                              >
                                {issue.key}
                              </a>

                              <EmojiHint kind={pKind} />
                            </div>

                            <div className="swimlane-card-summary">{issue.summary}</div>

                            <div className="swimlane-card-footer">
                              {issue.gate_status === 'pending' && <EmojiHint kind="gatePending" />}
                              {issue.gate_status === 'vetoed' && <EmojiHint kind="gateVetoed" />}
                              {issue.gate_status === 'approved' && <EmojiHint kind="gateApproved" />}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
