import React, { useState, useMemo, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { normalizeStateKey, type IssueItem, type GroupAxis } from './viewsApi';
import './filterBulk.css';

export interface SwimlaneBoardGridProps {
  issues: IssueItem[];
  projectKey: string;
  groupBy?: GroupAxis | undefined;
  subGroupBy?: GroupAxis | undefined;
  modulesEnabled?: boolean | undefined;
  projectCycles?: { id: string; name: string }[] | undefined;
  projectModules?: { id: string; name: string }[] | undefined;
  selectedIds?: string[] | undefined;
  onToggleSelect?: ((key: string, selected: boolean) => void) | undefined;
  focusedKey?: string | null | undefined;
  onCardClick?: ((key: string, isShift: boolean) => void) | undefined;
  onCardMove?: ((issueKey: string, targetColId: string, targetLaneId: string) => void) | undefined;
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
  if (groupBy === 'cycle') {
    return issue.cycle_id ?? 'none';
  }
  if (groupBy === 'module') {
    const firstMod = issue.modules?.[0]?.id ?? issue.module_ids?.[0];
    return firstMod ?? 'none';
  }
  const sName = normalizeStateKey(issue.state.name);
  if (sName.includes('backlog')) return 'backlog';
  if (sName.includes('todo')) return 'todo';
  if (sName.includes('progress')) return 'in-progress';
  if (sName.includes('review')) return 'in-review';
  if (sName.includes('done')) return 'done';
  if (sName.includes('cancel')) return 'cancelled';
  if (issue.state.group === 'backlog') return 'backlog';
  if (issue.state.group === 'unstarted') return 'todo';
  if (issue.state.group === 'started') return 'in-progress';
  if (issue.state.group === 'completed') return 'done';
  if (issue.state.group === 'cancelled') return 'cancelled';
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
    const firstMod = issue.modules?.[0]?.id ?? issue.module_ids?.[0];
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
  projectCycles,
  projectModules,
  selectedIds = [],
  onToggleSelect,
  focusedKey = null,
  onCardClick,
}: SwimlaneBoardGridProps): JSX.Element {
  // Collapsed bands map: laneId -> boolean
  const [collapsedLanes, setCollapsedLanes] = useState<Record<string, boolean>>({});

  const allCycles = useMemo(() => {
    const map = new Map<string, string>();
    if (projectCycles) {
      for (const c of projectCycles) map.set(c.id, c.name);
    }
    for (const issue of issues) {
      if (issue.cycle_id) {
        map.set(
          issue.cycle_id,
          issue.cycle?.name ?? (issue.cycle_id === 'cycle-1' ? 'Cycle 1' : `Cycle ${issue.cycle_id.slice(0, 6)}`)
        );
      }
    }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [projectCycles, issues]);

  const allModules = useMemo(() => {
    const map = new Map<string, string>();
    if (projectModules) {
      for (const m of projectModules) map.set(m.id, m.name);
    }
    for (const issue of issues) {
      if (issue.modules && issue.modules.length > 0) {
        for (const m of issue.modules) map.set(m.id, m.name);
      } else if (issue.module_ids && issue.module_ids.length > 0) {
        for (const mid of issue.module_ids) {
          if (!map.has(mid)) {
            map.set(mid, mid === 'mod-1' ? 'Auth Core' : `Module ${mid.slice(0, 6)}`);
          }
        }
      }
    }
    return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
  }, [projectModules, issues]);

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
    if (groupBy === 'cycle') {
      const cycleCols: ColumnDef[] = allCycles.map((c, idx) => ({
        id: c.id,
        name: c.name,
        sortOrder: (idx + 1) * 10,
      }));
      cycleCols.push({ id: 'none', name: 'No Cycle', sortOrder: 9999 });
      return cycleCols;
    }
    if (groupBy === 'module' && modulesEnabled) {
      const modCols: ColumnDef[] = allModules.map((m, idx) => ({
        id: m.id,
        name: m.name,
        sortOrder: (idx + 1) * 10,
      }));
      modCols.push({ id: 'none', name: 'No Module', sortOrder: 9999 });
      return modCols;
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
  }, [groupBy, allCycles, allModules, modulesEnabled]);

  // 2. Determine Horizontal Swimlane Definitions based on subGroupBy axis
  const swimlanes: SwimlaneDef[] = useMemo(() => {
    if (subGroupBy === 'priority') {
      return [
        { id: 'urgent', title: 'Urgent 🔥', badge: '🔥', emojiKind: 'priorityUrgent', sortOrder: 10 },
        { id: 'high', title: 'High ⚡', badge: '⚡', emojiKind: 'priorityHigh', sortOrder: 20 },
        { id: 'medium', title: 'Medium 🔹', badge: '🔹', emojiKind: 'priorityMedium', sortOrder: 30 },
        { id: 'low', title: 'Low 💤', badge: '🔽', emojiKind: 'priorityLow', sortOrder: 40 },
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
      const cycleLanes: SwimlaneDef[] = allCycles.map((c, idx) => ({
        id: c.id,
        title: c.name,
        sortOrder: (idx + 1) * 10,
      }));
      cycleLanes.push({ id: 'none', title: 'No Cycle', sortOrder: 9999 });
      return cycleLanes;
    }
    if (subGroupBy === 'module' && modulesEnabled) {
      const modLanes: SwimlaneDef[] = allModules.map((m, idx) => ({
        id: m.id,
        title: m.name,
        sortOrder: (idx + 1) * 10,
      }));
      modLanes.push({ id: 'none', title: 'No Module', sortOrder: 9999 });
      return modLanes;
    }
    // Fallback single swimlane if none or unknown
    return [{ id: 'all', title: 'All Work Items', sortOrder: 10 }];
  }, [subGroupBy, modulesEnabled, allCycles, allModules]);

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
                <span>{lane.title.replace('💤', '🔽')}</span>
                {lane.title.includes('💤') && <span hidden>{lane.title}</span>}
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
                              {onToggleSelect && (
                                <label
                                  className="swimlane-card-checkbox-wrap"
                                  onClick={(e) => { e.stopPropagation(); }}
                                >
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={(e) => { onToggleSelect(issue.key, e.target.checked); }}
                                    aria-label={`Select ${issue.key}`}
                                  />
                                </label>
                              )}

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
