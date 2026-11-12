import { createContext, useContext, type ComponentType, type RefObject } from 'react';

export interface IssueDetail {
  key: string;
  object_id: string;
  project_key: string;
  project_name: string;
  summary: string;
  description_markdown?: string | null;
  priority?: {
    slug: string;
    label: string;
    emoji: string;
    sort_order: number;
    sla_target?: string | null;
  } | null;
  state?: {
    id?: string;
    name: string;
    group: string;
  } | null;
  etag?: string;
  capabilities?: string[];
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
