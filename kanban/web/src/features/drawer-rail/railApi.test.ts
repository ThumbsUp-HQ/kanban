import { describe, expect, it, vi, beforeEach } from 'vitest';
import * as client from '../../api/client';
import {
  fetchProjectMetadata,
  fetchProjectPriorities,
  patchIssue,
  fetchAssigneeSuggestions,
  addAssignee,
  removeAssignee,
  overrideCreator,
  fetchProjectModules,
  updateIssueModules,
  fetchProjectCycles,
  fetchProjectLabels,
  createProjectLabel,
} from './railApi';

vi.mock('../../api/client', () => ({
  apiFetch: vi.fn(),
}));

describe('railApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetchProjectMetadata calls GET /api/v1/projects/{project_ref}', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce({
      key: 'KAN',
      name: 'Kanban',
      modules_enabled: true,
    });

    const res = await fetchProjectMetadata('KAN');
    expect(client.apiFetch).toHaveBeenCalledWith(
      'GET',
      '/api/v1/projects/{project_ref}',
      { params: { project_ref: 'KAN' } },
    );
    expect(res.key).toBe('KAN');
  });

  it('patchIssue sends PATCH with optional ifMatch', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce({ key: 'KAN-1' });

    const res = await patchIssue('KAN-1', { priority: 'high' }, '"etag-1"');
    expect(client.apiFetch).toHaveBeenCalledWith(
      'PATCH',
      '/api/v1/issues/{issue_ref}',
      {
        params: { issue_ref: 'KAN-1' },
        body: { priority: 'high' },
        ifMatch: '"etag-1"',
      },
    );
    expect(res.key).toBe('KAN-1');
  });

  it('patchIssue sends PATCH without ifMatch when omitted', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce({ key: 'KAN-1' });

    await patchIssue('KAN-1', { priority: 'low' });
    expect(client.apiFetch).toHaveBeenCalledWith(
      'PATCH',
      '/api/v1/issues/{issue_ref}',
      {
        params: { issue_ref: 'KAN-1' },
        body: { priority: 'low' },
      },
    );
  });

  it('fetchProjectPriorities calls GET /api/v1/projects/{project_ref}/priorities and handles array/items', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce({
      items: [{ slug: 'urgent', name: 'Urgent' }],
    });

    const items = await fetchProjectPriorities('KAN');
    expect(client.apiFetch).toHaveBeenCalledWith(
      'GET',
      '/api/v1/projects/{project_ref}/priorities',
      { params: { project_ref: 'KAN' } },
    );
    expect(items).toHaveLength(1);

    vi.mocked(client.apiFetch).mockResolvedValueOnce([{ slug: 'high', name: 'High' }] as never);
    const items2 = await fetchProjectPriorities('KAN');
    expect(items2).toHaveLength(1);

    vi.mocked(client.apiFetch).mockResolvedValueOnce(undefined);
    const items3 = await fetchProjectPriorities('KAN');
    expect(items3).toEqual([]);
  });

  it('fetchAssigneeSuggestions searches assignees', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce({
      items: [
        { id: 'u1', handle: 'maya', display_name: 'Maya', type: 'USER' },
        { id: 'u2', handle: 'agent-bot', display_name: 'Agent Bot', type: 'AGENT' },
      ],
    });

    const items = await fetchAssigneeSuggestions('KAN', 'may');
    expect(client.apiFetch).toHaveBeenCalledWith(
      'GET',
      '/api/v1/projects/{project_ref}/assignee-suggestions',
      {
        params: { project_ref: 'KAN' },
        query: { q: 'may', limit: 10 },
      },
    );
    expect(items).toHaveLength(2);
  });

  it('fetchAssigneeSuggestions returns empty array when items missing', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce({});
    const items = await fetchAssigneeSuggestions('KAN', 'nobody');
    expect(items).toEqual([]);
  });

  it('addAssignee calls POST /api/v1/issues/{issue_ref}/assignees', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce({
      id: 'asg-1',
      kind: 'principal',
      principal: { id: 'u1', handle: 'maya', display_name: 'Maya', type: 'USER' },
    });

    const res = await addAssignee('KAN-1', { principal: 'maya' });
    expect(client.apiFetch).toHaveBeenCalledWith(
      'POST',
      '/api/v1/issues/{issue_ref}/assignees',
      {
        params: { issue_ref: 'KAN-1' },
        body: { principal: 'maya' },
      },
    );
    expect(res.id).toBe('asg-1');
  });

  it('removeAssignee calls DELETE /api/v1/issues/{issue_ref}/assignees/{assignee_id}', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce(undefined);

    await removeAssignee('KAN-1', 'asg-1');
    expect(client.apiFetch).toHaveBeenCalledWith(
      'DELETE',
      '/api/v1/issues/{issue_ref}/assignees/{assignee_id}',
      {
        params: { issue_ref: 'KAN-1', assignee_id: 'asg-1' },
      },
    );
  });

  it('overrideCreator calls PATCH /api/v1/issues/{issue_ref}/created-by', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce({
      key: 'KAN-1',
      provenance: {
        created_by: { handle: 'maya' },
        overridden: true,
        reason: 'Reassigned to true author',
      },
    });

    const res = await overrideCreator('KAN-1', {
      created_by: 'maya',
      reason: 'Reassigned to true author',
    });
    expect(client.apiFetch).toHaveBeenCalledWith(
      'PATCH',
      '/api/v1/issues/{issue_ref}/created-by',
      {
        params: { issue_ref: 'KAN-1' },
        body: { created_by: 'maya', reason: 'Reassigned to true author' },
      },
    );
    expect(res.key).toBe('KAN-1');
  });

  it('fetchProjectModules calls GET /api/v1/projects/{project_ref}/modules and handles array/items', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce([
      { id: 'm1', name: 'Auth' },
    ] as never);

    const items = await fetchProjectModules('KAN');
    expect(client.apiFetch).toHaveBeenCalledWith(
      'GET',
      '/api/v1/projects/{project_ref}/modules',
      { params: { project_ref: 'KAN' } },
    );
    expect(items).toHaveLength(1);

    vi.mocked(client.apiFetch).mockResolvedValueOnce({ items: [{ id: 'm2', name: 'UI' }] });
    const items2 = await fetchProjectModules('KAN');
    expect(items2).toHaveLength(1);

    vi.mocked(client.apiFetch).mockResolvedValueOnce(undefined);
    const items3 = await fetchProjectModules('KAN');
    expect(items3).toEqual([]);
  });

  it('updateIssueModules calls PUT /api/v1/issues/{issue_ref}/modules', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce(undefined);

    await updateIssueModules('KAN-1', ['m1', 'm2']);
    expect(client.apiFetch).toHaveBeenCalledWith(
      'PUT',
      '/api/v1/issues/{issue_ref}/modules',
      {
        params: { issue_ref: 'KAN-1' },
        body: { module_ids: ['m1', 'm2'] },
      },
    );
  });

  it('fetchProjectCycles calls GET /api/v1/projects/{project_ref}/cycles and handles array/items', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce({
      items: [{ id: 'c1', name: 'Sprint 1' }],
    });

    const items = await fetchProjectCycles('KAN');
    expect(client.apiFetch).toHaveBeenCalledWith(
      'GET',
      '/api/v1/projects/{project_ref}/cycles',
      { params: { project_ref: 'KAN' } },
    );
    expect(items).toHaveLength(1);

    vi.mocked(client.apiFetch).mockResolvedValueOnce([{ id: 'c2', name: 'Sprint 2' }] as never);
    const items2 = await fetchProjectCycles('KAN');
    expect(items2).toHaveLength(1);

    vi.mocked(client.apiFetch).mockResolvedValueOnce(undefined);
    const items3 = await fetchProjectCycles('KAN');
    expect(items3).toEqual([]);
  });

  it('fetchProjectLabels calls GET /api/v1/projects/{project_ref}/labels', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce({
      items: [{ id: 'l1', name: 'frontend' }],
    });

    const items = await fetchProjectLabels('KAN');
    expect(client.apiFetch).toHaveBeenCalledWith(
      'GET',
      '/api/v1/projects/{project_ref}/labels',
      { params: { project_ref: 'KAN' } },
    );
    expect(items).toHaveLength(1);

    vi.mocked(client.apiFetch).mockResolvedValueOnce([{ id: 'l2', name: 'backend' }] as never);
    const items2 = await fetchProjectLabels('KAN');
    expect(items2).toHaveLength(1);

    vi.mocked(client.apiFetch).mockResolvedValueOnce(undefined);
    const items3 = await fetchProjectLabels('KAN');
    expect(items3).toEqual([]);
  });

  it('createProjectLabel calls POST /api/v1/projects/{project_ref}/labels', async () => {
    vi.mocked(client.apiFetch).mockResolvedValueOnce({
      id: 'l1',
      name: 'frontend',
    });

    const res = await createProjectLabel('KAN', { name: 'frontend' });
    expect(client.apiFetch).toHaveBeenCalledWith(
      'POST',
      '/api/v1/projects/{project_ref}/labels',
      {
        params: { project_ref: 'KAN' },
        body: { name: 'frontend' },
      },
    );
    expect(res.name).toBe('frontend');
  });

  it('covers project key guards and label creation options', async () => {
    // Guards on undefined / empty projectKey
    expect(await fetchProjectPriorities('')).toEqual([]);
    expect(await fetchProjectPriorities('undefined')).toEqual([]);
    expect(await fetchAssigneeSuggestions('', 'query')).toEqual([]);
    expect(await fetchAssigneeSuggestions('undefined', 'query')).toEqual([]);
    expect(await fetchProjectModules('')).toEqual([]);
    expect(await fetchProjectModules('undefined')).toEqual([]);
    expect(await fetchProjectCycles('')).toEqual([]);
    expect(await fetchProjectCycles('undefined')).toEqual([]);
    expect(await fetchProjectLabels('')).toEqual([]);
    expect(await fetchProjectLabels('undefined')).toEqual([]);

    await expect(createProjectLabel('', { name: 'test' })).rejects.toThrow(
      'Project key is required to create a label',
    );
    await expect(createProjectLabel('undefined', { name: 'test' })).rejects.toThrow(
      'Project key is required to create a label',
    );

    // createProjectLabel with color, color_hex, and exclusive_group
    vi.mocked(client.apiFetch).mockResolvedValueOnce({ id: 'l2', name: 'colored' });
    await createProjectLabel('KAN', {
      name: 'colored',
      color: '#ff0000',
      exclusive_group: 'team',
    });
    expect(client.apiFetch).toHaveBeenLastCalledWith(
      'POST',
      '/api/v1/projects/{project_ref}/labels',
      {
        params: { project_ref: 'KAN' },
        body: { name: 'colored', color_hex: '#ff0000', exclusive_group: 'team' },
      },
    );

    vi.mocked(client.apiFetch).mockResolvedValueOnce({ id: 'l3', name: 'hex_only' });
    await createProjectLabel('KAN', {
      name: 'hex_only',
      color_hex: '#00ff00',
    });
    expect(client.apiFetch).toHaveBeenLastCalledWith(
      'POST',
      '/api/v1/projects/{project_ref}/labels',
      {
        params: { project_ref: 'KAN' },
        body: { name: 'hex_only', color_hex: '#00ff00' },
      },
    );
  });
});
