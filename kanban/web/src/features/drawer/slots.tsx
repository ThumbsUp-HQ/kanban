import { createContext, useContext, type ComponentType, type RefObject } from 'react';
import type { AssigneeItem, ProjectCycle, ProjectLabel, ProjectModule } from '../drawer-rail/railApi';
import type { PendingGateInfo, LatestGateVerdict } from '../gates/types';

export interface CreatorSummary {
  id?: string;
  handle?: string;
  display_name?: string;
  redacted?: boolean;
  label?: string;
}

export interface IssueProvenance {
  created_by?: CreatorSummary;
  original_created_by?: CreatorSummary;
  overridden?: boolean;
  creator_modified_by?: CreatorSummary;
  creator_modified_at?: string;
  reason?: string;
}

export interface SubIssueItem {
  key: string;
  summary?: string;
  state_group?: string;
  state?: string;
}

export interface ParentIssueInfo {
  key?: string;
  summary?: string;
  restricted?: boolean;
  label?: string;
}

export interface IssueDetail {
  key: string;
  object_id?: string | undefined;
  project_key: string;
  project_name?: string | undefined;
  summary: string;
  description_markdown?: string | null | undefined;
  priority?: {
    slug: string;
    label: string;
    emoji: string;
    sort_order?: number | undefined;
    sla_target?: string | null | undefined;
  } | null | undefined;
  state?: {
    id?: string | undefined;
    name: string;
    group: string;
  } | null | undefined;
  etag?: string | undefined;
  capabilities?: string[] | undefined;
  assignees?: AssigneeItem[] | string[] | undefined;
  provenance?: IssueProvenance | undefined;
  start_date?: string | null | undefined;
  due_date?: string | null | undefined;
  module_ids?: string[] | undefined;
  modules?: ProjectModule[] | undefined;
  cycle_id?: string | null | undefined;
  cycle?: ProjectCycle | null | undefined;
  parent?: ParentIssueInfo | string | null | undefined;
  sub_issues?: SubIssueItem[] | undefined;
  sub_issues_rollup?: {
    total: number;
    completed: number;
    percent: number;
  } | undefined;
  label_ids?: string[] | undefined;
  labels?: ProjectLabel[] | string[] | undefined;
  pending_gate?: PendingGateInfo | null | undefined;
  latest_gate_verdict?: LatestGateVerdict | null | undefined;
  [key: string]: unknown;
}

export interface IssueSurfaceSlots {
  subscribe?: ComponentType<{ issue: IssueDetail }>;
  link?: ComponentType<{ issue: IssueDetail }>;
  overflow?: ComponentType<{ issue: IssueDetail; mode: 'drawer' | 'full'; toggleFullScreen: () => void }>;
  rail?: ComponentType<{ issue: IssueDetail }>;
  description?: ComponentType<{ issue: IssueDetail; focusRef: RefObject<HTMLElement | null> }>;
  activity?: ComponentType<{ issue: IssueDetail }>;
}

export const IssueSurfaceSlotsContext = createContext<IssueSurfaceSlots>({});

export function useIssueSurfaceSlots(): IssueSurfaceSlots {
  return useContext(IssueSurfaceSlotsContext);
}
