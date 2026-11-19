/**
 * Project Saved Views Management Screen (KANBA-221, S6.4, S3.4).
 * Lists, opens, and deletes persisted views for a project.
 */

import React, { useContext, type JSX } from 'react';
import { useParams, Link } from 'react-router';
import { useQuery, useMutation, useQueryClient, QueryClientContext } from '@tanstack/react-query';
import { apiFetch } from '../../api/client';
import { qk } from '../../api/queryKeys';
import type { ViewLayout } from './viewRegistry';
import './ProjectSavedViewsView.css';

export interface SavedViewRecord {
  id: string;
  name: string;
  description_markdown?: string | null;
  layout: ViewLayout;
  group_by?: string | null;
  sub_group_by?: string | null;
  filters?: {
    state_ids?: string[];
    priority_ids?: string[];
    assignee_ids?: string[];
    cycle_ids?: string[];
    module_ids?: string[];
    search_query?: string | null;
  } | null;
  is_shared?: boolean;
  created_at?: string;
}

interface SavedViewsResponse {
  views?: SavedViewRecord[];
}

export function ProjectSavedViewsViewInner({ projectKey }: { projectKey: string }): JSX.Element {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery<SavedViewsResponse | SavedViewRecord[]>({
    queryKey: qk.savedViews(projectKey),
    queryFn: async (): Promise<SavedViewsResponse | SavedViewRecord[]> => {
      const res = (await apiFetch(
        'GET',
        `/api/v1/projects/${encodeURIComponent(projectKey)}/views` as never,
      )) as SavedViewsResponse | SavedViewRecord[];
      return res;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (viewId: string) => {
      await apiFetch('DELETE', `/api/v1/views/${encodeURIComponent(viewId)}` as never);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.savedViews(projectKey) });
    },
  });

  const views: SavedViewRecord[] = Array.isArray(data)
    ? data
    : (data?.views ?? []);

  return (
    <section data-testid="project-views-view" className="kb-workspace-section kb-views-view">
      <div className="kb-views-header">
        <div>
          <h1>Views ({projectKey})</h1>
          <p>Switch between saved layouts and filter presets for {projectKey}:</p>
        </div>
        <div className="kb-views-links-row">
          <Link to={`/projects/${projectKey}/issues?layout=list`}>List View</Link>
          <Link to={`/projects/${projectKey}/issues?layout=board`}>Board View</Link>
          <Link to={`/projects/${projectKey}/issues?layout=table`}>Table View</Link>
          <Link to={`/projects/${projectKey}/issues?layout=calendar`}>Calendar View</Link>
          <Link to={`/projects/${projectKey}/issues?layout=timeline`}>Timeline View</Link>
        </div>
      </div>

      {isLoading && (
        <div data-testid="loading-views" className="kb-empty-views">
          Loading saved views...
        </div>
      )}

      {error && (
        <div data-testid="error-views" className="kb-error-banner" role="alert">
          {error instanceof Error ? error.message : 'Failed to load saved views'}
        </div>
      )}

      {!isLoading && !error && views.length === 0 && (
        <div data-testid="no-saved-views" className="kb-empty-views">
          No custom saved views found for {projectKey}. Use &quot;Save as view&quot; from the display settings in any issue view to create one.
        </div>
      )}

      {!isLoading && !error && views.length > 0 && (
        <div className="kb-saved-views-list" data-testid="saved-views-list">
          {views.map((view) => {
            const openUrl = `/projects/${projectKey}/issues?layout=${view.layout}&view=${view.id}`;
            const groupInfo = view.group_by && view.group_by !== 'none' ? `Group: ${view.group_by}` : null;
            const subGroupInfo = view.sub_group_by && view.sub_group_by !== 'none' ? `Sub-group: ${view.sub_group_by}` : null;

            return (
              <div key={view.id} className="kb-saved-view-card" data-testid={`saved-view-card-${view.id}`}>
                <div className="kb-saved-view-main">
                  <div className="kb-saved-view-title-row">
                    <Link to={openUrl} className="kb-saved-view-title" data-testid={`view-title-${view.id}`}>
                      {view.name}
                    </Link>
                    <span className="kb-view-badge kb-view-badge--layout">{view.layout}</span>
                    <span
                      className={`kb-view-badge ${view.is_shared ? 'kb-view-badge--shared' : 'kb-view-badge--private'}`}
                    >
                      {view.is_shared ? 'Shared' : 'Private'}
                    </span>
                  </div>
                  {view.description_markdown && (
                    <p className="kb-saved-view-desc">{view.description_markdown}</p>
                  )}
                  <div className="kb-saved-view-meta">
                    {groupInfo && <span>{groupInfo}</span>}
                    {subGroupInfo && <span>{subGroupInfo}</span>}
                    {view.filters?.search_query && (
                      <span>Search: &quot;{view.filters.search_query}&quot;</span>
                    )}
                  </div>
                </div>

                <div className="kb-saved-view-actions">
                  <Link to={openUrl} className="kb-view-open-btn" data-testid={`open-view-${view.id}`}>
                    Open
                  </Link>
                  <button
                    type="button"
                    className="kb-view-delete-btn"
                    data-testid={`delete-view-${view.id}`}
                    disabled={deleteMutation.isPending}
                    onClick={() => {
                      deleteMutation.mutate(view.id);
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

export function ProjectSavedViewsView(): JSX.Element {
  const { projectKey } = useParams<{ projectKey: string }>();
  const key = projectKey ?? 'KAN';
  const client = useContext(QueryClientContext);

  if (!client) {
    return (
      <section data-testid="project-views-view" className="kb-workspace-section">
        <h1>Views ({key})</h1>
        <p>Switch between saved layouts and filter presets for {key}:</p>
        <div className="kb-views-links-row">
          <Link to={`/projects/${key}/issues?layout=list`}>List View</Link>
          <Link to={`/projects/${key}/issues?layout=board`}>Board View</Link>
          <Link to={`/projects/${key}/issues?layout=table`}>Table View</Link>
          <Link to={`/projects/${key}/issues?layout=calendar`}>Calendar View</Link>
          <Link to={`/projects/${key}/issues?layout=timeline`}>Timeline View</Link>
        </div>
      </section>
    );
  }

  return <ProjectSavedViewsViewInner projectKey={key} />;
}
