import React, { type ComponentType, type JSX } from 'react';
import { ListView } from '../list/ListView';
import { TableView } from '../table/TableView';
import { CalendarView } from '../calendar/CalendarView';
import { TimelineView } from '../timeline/TimelineView';
import type { IssueItem } from './viewsApi';

export interface ViewComponentProps {
  issues: IssueItem[];
  projectKey: string;
  modulesEnabled?: boolean;
  selectedIds?: string[];
  onToggleSelect?: (key: string, selected: boolean) => void;
  onSelectAll?: (selected: boolean) => void;
  onCreateIssue?: () => void;
  nextCursor?: string | null;
  onLoadMore?: () => void;
  isLoading?: boolean;
}

export type ViewComponent = ComponentType<ViewComponentProps>;

export const VIEW_REGISTRY: Record<string, ViewComponent> = {
  list: ListView as ViewComponent,
  table: TableView as ViewComponent,
  calendar: CalendarView as ViewComponent,
  timeline: TimelineView as ViewComponent,
};

export interface ViewHostProps extends ViewComponentProps {
  layout?: string;
}

/**
 * Shared layout host rendering the appropriate registered view (KB-P3-38, S6.4 item 2).
 */
export function ViewHost({
  layout = 'list',
  ...props
}: ViewHostProps): JSX.Element {
  const normalizedLayout = layout.toLowerCase();
  const Component = VIEW_REGISTRY[normalizedLayout] ?? ListView;

  return <Component {...props} />;
}
