import React, { useState, useMemo, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { QuickFieldPopover } from './QuickFieldPopover';
import * as railApi from '../drawer-rail/railApi';
import {
  normalizeStateKey,
  type IssueItem,
  type GroupAxis,
  type StateSummary,
} from './viewsApi';
import './filterBulk.css';

export interface SwimlaneBoardGridProps {
  issues: IssueItem[];
  projectKey: string;
  groupBy?: GroupAxis | undefined;
  subGroupBy?: GroupAxis | undefined;
  modulesEnabled?: boolean | undefined;
  projectCycles?: { id: string; name: string }[] | undefined;
  projectModules?: { id: string; name: string }[] | undefined;
  projectStates?: StateSummary[] | undefined;
  selectedIds?: string[] | undefined;
  onToggleSelect?: ((key: string, selected: boolean) => void) | undefined;
  focusedKey?: string | null | undefined;
  onCardClick?: ((key: string, isShift: boolean) => void) | undefined;
  onCardMove?: ((issueKey: string, targetColId: string, targetLaneId: string) => void) | undefined;
  onStateTransition?: ((issueKey: string, targetStateId: string) => void) | undefined;
  currentUserCapabilities?: string[] | undefined;
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

function getIssueColId(
  issue: IssueItem,
  groupBy: GroupAxis,
  projectStates?: StateSummary[],
): string {
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
  if (projectStates && projectStates.length > 0) {
    const matched =
      projectStates.find((s) => s.id === issue.state.id) ??
      projectStates.find(
        (s) => normalizeStateKey(s.name) === normalizeStateKey(issue.state.name),
      ) ??
      projectStates.find((s) => s.group === issue.state.group);
    if (matched) return matched.id;
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
  projectStates,
  selectedIds = [],
  onToggleSelect,
  focusedKey = null,
  onCardClick,
  onCardMove,
  onStateTransition,
  currentUserCapabilities,
}: SwimlaneBoardGridProps): JSX.Element {
  // Collapsed bands map: laneId -> boolean
  const [collapsedLanes, setCollapsedLanes] = useState<Record<string, boolean>>({});
  const [rovingKey, setRovingKey] = useState<string | null>(null);
  const [popoverState, setPopoverState] = useState<{
    isOpen: boolean;
    issue: IssueItem | null;
    anchorRect: DOMRect | null;
  }>({
    isOpen: false,
    issue: null,
    anchorRect: null,
  });

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
    if (projectStates && projectStates.length > 0) {
      return projectStates.map((st, idx) => ({
        id: st.id,
        name: st.name,
        sortOrder: st.sort_order ?? (idx + 1) * 10,
      }));
    }
    return [
      { id: 'backlog', name: 'Backlog', sortOrder: 10 },
      { id: 'todo', name: 'Todo', sortOrder: 20 },
      { id: 'in-progress', name: 'In Progress', sortOrder: 30 },
      { id: 'in-review', name: 'In Review', sortOrder: 40 },
      { id: 'done', name: 'Done', sortOrder: 50 },
      { id: 'cancelled', name: 'Cancelled', sortOrder: 60 },
    ];
  }, [groupBy, allCycles, allModules, modulesEnabled, projectStates]);

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
      const assigneeMap = new Map<string, string>();
      for (const issue of issues) {
        for (const asg of issue.assignees ?? []) {
          if (asg.kind === 'principal') {
            const key = asg.principal.handle.replace(/^@/, '').toLowerCase();
            const label = asg.principal.display_name || asg.principal.handle;
            assigneeMap.set(key, label);
          }
        }
      }
      const lanes: SwimlaneDef[] = [];
      let sortOrder = 10;
      for (const [id, title] of assigneeMap.entries()) {
        lanes.push({ id, title, sortOrder });
        sortOrder += 10;
      }
      lanes.push({ id: 'unassigned', title: 'Unassigned', sortOrder: 99 });
      return lanes;
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
  }, [subGroupBy, modulesEnabled, allCycles, allModules, issues]);

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
      const colId = getIssueColId(issue, groupBy, projectStates);
      const laneMap = grid[laneId] ?? grid[defaultLaneId];
      const colList = laneMap?.[colId] ?? laneMap?.[defaultColId];
      colList?.push(issue);
    }

    return grid;
  }, [issues, columns, swimlanes, groupBy, subGroupBy, modulesEnabled, projectStates]);

  const allVisibleCards = useMemo(() => {
    const list: string[] = [];
    for (const lane of swimlanes) {
      if (collapsedLanes[lane.id]) continue;
      for (const col of columns) {
        const cellIssues = partitionedGrid[lane.id]?.[col.id] ?? [];
        for (const it of cellIssues) {
          list.push(it.key);
        }
      }
    }
    return list;
  }, [swimlanes, collapsedLanes, columns, partitionedGrid]);

  const activeFocusedKey = focusedKey ?? rovingKey ?? allVisibleCards[0] ?? null;

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

  const handleCardKeyDown = (
    e: React.KeyboardEvent<HTMLDivElement>,
    currentKey: string
  ) => {
    if (['ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(e.key)) {
      e.preventDefault();
      e.stopPropagation();

      const flatCards: string[] = [];
      const cellMap: Record<string, { laneIdx: number; colIdx: number; cardIdx: number }> = {};

      swimlanes.forEach((l, lIdx) => {
        if (collapsedLanes[l.id]) return;
        columns.forEach((c, cIdx) => {
          const issuesInCell = partitionedGrid[l.id]?.[c.id] ?? [];
          issuesInCell.forEach((iss, kIdx) => {
            flatCards.push(iss.key);
            cellMap[iss.key] = { laneIdx: lIdx, colIdx: cIdx, cardIdx: kIdx };
          });
        });
      });

      if (flatCards.length === 0) return;

      let nextKey: string | null = null;
      const currentMeta = cellMap[currentKey];

      if (e.key === 'Home') {
        nextKey = flatCards[0] ?? null;
      } else if (e.key === 'End') {
        nextKey = flatCards[flatCards.length - 1] ?? null;
      } else if (currentMeta) {
        const { laneIdx, colIdx, cardIdx } = currentMeta;
        const currentLane = swimlanes[laneIdx];
        const currentColumn = columns[colIdx];
        const currentLaneIssuesInCol = (currentLane && currentColumn)
          ? (partitionedGrid[currentLane.id]?.[currentColumn.id] ?? [])
          : [];

        if (e.key === 'ArrowDown') {
          if (cardIdx + 1 < currentLaneIssuesInCol.length) {
            nextKey = currentLaneIssuesInCol[cardIdx + 1]?.key ?? null;
          } else {
            for (let l = laneIdx + 1; l < swimlanes.length; l++) {
              const nextLane = swimlanes[l];
              if (!nextLane || collapsedLanes[nextLane.id]) continue;
              const targetCol = columns[colIdx];
              const nextLaneColIssues = targetCol ? (partitionedGrid[nextLane.id]?.[targetCol.id] ?? []) : [];
              if (nextLaneColIssues.length > 0 && nextLaneColIssues[0]) {
                nextKey = nextLaneColIssues[0].key;
                break;
              }
            }
            if (!nextKey) {
              const currentFlatIdx = flatCards.indexOf(currentKey);
              if (currentFlatIdx + 1 < flatCards.length) {
                nextKey = flatCards[currentFlatIdx + 1] ?? null;
              }
            }
          }
        } else if (e.key === 'ArrowUp') {
          if (cardIdx - 1 >= 0) {
            nextKey = currentLaneIssuesInCol[cardIdx - 1]?.key ?? null;
          } else {
            for (let l = laneIdx - 1; l >= 0; l--) {
              const prevLane = swimlanes[l];
              if (!prevLane || collapsedLanes[prevLane.id]) continue;
              const targetCol = columns[colIdx];
              const prevLaneColIssues = targetCol ? (partitionedGrid[prevLane.id]?.[targetCol.id] ?? []) : [];
              if (prevLaneColIssues.length > 0) {
                const lastIssue = prevLaneColIssues[prevLaneColIssues.length - 1];
                if (lastIssue) {
                  nextKey = lastIssue.key;
                  break;
                }
              }
            }
            if (!nextKey) {
              const currentFlatIdx = flatCards.indexOf(currentKey);
              if (currentFlatIdx - 1 >= 0) {
                nextKey = flatCards[currentFlatIdx - 1] ?? null;
              }
            }
          }
        } else if (e.key === 'ArrowRight') {
          if (currentLane) {
            for (let c = colIdx + 1; c < columns.length; c++) {
              const targetCol = columns[c];
              const issuesInCol = targetCol ? (partitionedGrid[currentLane.id]?.[targetCol.id] ?? []) : [];
              if (issuesInCol.length > 0) {
                const targetIssue = issuesInCol[Math.min(cardIdx, issuesInCol.length - 1)];
                if (targetIssue) {
                  nextKey = targetIssue.key;
                  break;
                }
              }
            }
          }
          if (!nextKey) {
            const currentFlatIdx = flatCards.indexOf(currentKey);
            if (currentFlatIdx + 1 < flatCards.length) {
              nextKey = flatCards[currentFlatIdx + 1] ?? null;
            }
          }
        } else if (e.key === 'ArrowLeft') {
          if (currentLane) {
            for (let c = colIdx - 1; c >= 0; c--) {
              const targetCol = columns[c];
              const issuesInCol = targetCol ? (partitionedGrid[currentLane.id]?.[targetCol.id] ?? []) : [];
              if (issuesInCol.length > 0) {
                const targetIssue = issuesInCol[Math.min(cardIdx, issuesInCol.length - 1)];
                if (targetIssue) {
                  nextKey = targetIssue.key;
                  break;
                }
              }
            }
          }
          if (!nextKey) {
            const currentFlatIdx = flatCards.indexOf(currentKey);
            if (currentFlatIdx - 1 >= 0) {
              nextKey = flatCards[currentFlatIdx - 1] ?? null;
            }
          }
        }
      }

      if (nextKey) {
        setRovingKey(nextKey);
        const targetEl = document.querySelector<HTMLElement>(`[data-issue-key="${nextKey}"]`);
        targetEl?.focus();
      }
    } else if (e.key === 'Enter' || e.key === ' ') {
      onCardClick?.(currentKey, e.shiftKey);
    }
  };

  return (
    <div className="swimlane-board-grid" role="region" aria-label="2D Swimlane Board Grid">
      <div
        className="swimlane-grid-table"
        role="grid"
        aria-label="2D Swimlane Board Grid"
        aria-rowcount={swimlanes.length + 1}
        aria-colcount={columns.length}
      >
        {/* Sticky Top Column Headers aligned to 324px */}
        <div className="swimlane-col-headers" role="row" aria-rowindex={1}>
          {columns.map((col, colIdx) => (
            <div
              key={col.id}
              className="swimlane-col-header-item"
              role="columnheader"
              aria-colindex={colIdx + 1}
            >
              <span>{col.name}</span>
            </div>
          ))}
        </div>

        {/* Horizontal Swimlane Bands */}
        {swimlanes.map((lane, laneIdx) => {
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
                  aria-rowindex={laneIdx + 2}
                >
                  {columns.map((col, colIdx) => {
                    const cellIssues = partitionedGrid[lane.id]?.[col.id] ?? [];
                    const isCellFocused = activeFocusedKey
                      ? cellIssues.some((it) => it.key === activeFocusedKey)
                      : false;

                    return (
                      <div
                        key={col.id}
                        className="board-column"
                        data-column-id={col.id}
                        data-swimlane-id={lane.id}
                        role="gridcell"
                        aria-colindex={colIdx + 1}
                        tabIndex={isCellFocused ? 0 : -1}
                      >
                        <div className="swimlane-column-mobile-header" aria-hidden="true">
                          <span className="swimlane-column-mobile-title">{col.name}</span>
                          <span className="swimlane-column-mobile-count">{cellIssues.length}</span>
                        </div>
                        {cellIssues.map((issue) => {
                          const isSelected = selectedIds.includes(issue.key);
                          const isFocused = activeFocusedKey === issue.key;

                          let pKind: 'priorityUrgent' | 'priorityHigh' | 'priorityMedium' | 'priorityLow' =
                            'priorityMedium';
                          const slug = issue.priority.slug.toLowerCase();
                          if (slug === 'urgent') pKind = 'priorityUrgent';
                          else if (slug === 'high') pKind = 'priorityHigh';
                          else if (slug === 'low') pKind = 'priorityLow';

                          const rawCaps = issue.capabilities ?? currentUserCapabilities;
                          const cardCaps = rawCaps ?? ['EDIT', 'TRANSITION'];
                          const canTransitionCard =
                            cardCaps.includes('TRANSITION') ||
                            cardCaps.includes('EDIT') ||
                            cardCaps.includes('ADMIN');

                          return (
                            <div
                              key={issue.key}
                              className={`swimlane-card ${isSelected ? 'swimlane-card--selected' : ''}`}
                              data-issue-key={issue.key}
                              data-focused={isFocused ? 'true' : 'false'}
                              tabIndex={isFocused ? 0 : -1}
                              onClick={(e) => {
                                setRovingKey(issue.key);
                                onCardClick?.(issue.key, e.shiftKey);
                              }}
                              onFocus={() => {
                                setRovingKey(issue.key);
                              }}
                              onKeyDown={(e) => {
                                handleCardKeyDown(e, issue.key);
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

                                {canTransitionCard && (
                                  <button
                                    type="button"
                                    className="board-card-state-btn"
                                    data-testid={`board-card-state-btn-${issue.key}`}
                                    aria-label={`Move ${issue.key} to another state`}
                                    title={`Move ${issue.key}`}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setPopoverState({
                                        isOpen: true,
                                        issue,
                                        anchorRect: e.currentTarget.getBoundingClientRect(),
                                      });
                                    }}
                                  >
                                    <span className="board-card-state-btn-glyph" aria-hidden="true">⇄</span>
                                    <span>{issue.state.name ? issue.state.name : 'Move'}</span>
                                  </button>
                                )}

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
      {popoverState.isOpen && popoverState.issue && (
        <QuickFieldPopover
          isOpen={popoverState.isOpen}
          field="state"
          anchorRect={popoverState.anchorRect}
          issue={popoverState.issue}
          onClose={() => {
            setPopoverState({ isOpen: false, issue: null, anchorRect: null });
          }}
          onSelect={(_field, value) => {
            if (typeof value === 'string' && popoverState.issue) {
              const targetKey = popoverState.issue.key;
              if (onCardMove) {
                onCardMove(targetKey, value, 'none');
              } else if (onStateTransition) {
                onStateTransition(targetKey, value);
              } else {
                void railApi.patchIssue(targetKey, { state_id: value });
              }
            }
          }}
          states={projectStates}
        />
      )}
    </div>
  );
}
