import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as clientModule from '../../api/client';
import {
  fetchDocsTree,
  fetchPage,
  updatePage,
  createPage,
  movePage,
  fetchPageVersions,
  restorePageVersion,
  createIssue,
  createLink,
} from './docsApi';

describe('docsApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetchDocsTree calls projects docs tree and falls back on error', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([{ id: 'p1' }]);
    const res = await fetchDocsTree('KAN');
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/projects/{projectKey}/docs/tree', {
      params: { projectKey: 'KAN' },
    });
    expect(res).toEqual([{ id: 'p1' }]);

    // Fallback branch
    spy.mockRejectedValueOnce(new Error('404 Not Found')).mockResolvedValueOnce([{ id: 'p2' }]);
    const resFallback = await fetchDocsTree('KAN');
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/docs/{doc_ref}/tree', {
      params: { doc_ref: 'KAN' },
    });
    expect(resFallback).toEqual([{ id: 'p2' }]);
  });

  it('fetchPage calls GET /api/v1/pages/{page_ref}', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ id: 'p1' });
    const res = await fetchPage('p1');
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/pages/{page_ref}', {
      params: { page_ref: 'p1' },
    });
    expect(res).toEqual({ id: 'p1' });
  });

  it('updatePage calls PATCH with If-Match', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ id: 'p1' });
    const res = await updatePage('p1', { title: 'T2' }, '"etag-123"');
    expect(spy).toHaveBeenCalledWith('PATCH', '/api/v1/pages/{page_ref}', {
      params: { page_ref: 'p1' },
      body: { title: 'T2' },
      ifMatch: '"etag-123"',
    });
    expect(res).toEqual({ id: 'p1' });
  });

  it('createPage calls POST /api/v1/docs/{doc_ref}/pages and falls back on error', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ id: 'p1' });
    const res = await createPage('KAN', { title: 'New' });
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/docs/{doc_ref}/pages', {
      params: { doc_ref: 'KAN' },
      body: { title: 'New' },
    });
    expect(res).toEqual({ id: 'p1' });

    // Fallback branch
    spy.mockRejectedValueOnce(new Error('fallback')).mockResolvedValueOnce({ id: 'p-fb' });
    const resFb = await createPage('KAN', { title: 'New 2' });
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/projects/{projectKey}/docs/pages', {
      params: { projectKey: 'KAN' },
      body: { title: 'New 2' },
    });
    expect(resFb).toEqual({ id: 'p-fb' });
  });

  it('movePage calls POST /api/v1/pages/{page_ref}/move', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ id: 'p1' });
    const res = await movePage('p1', { parent_page_id: 'p2' });
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/pages/{page_ref}/move', {
      params: { page_ref: 'p1' },
      body: { parent_page_id: 'p2' },
    });
    expect(res).toEqual({ id: 'p1' });
  });

  it('fetchPageVersions calls GET /api/v1/pages/{page_ref}/versions', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([{ version_seq: 1 }]);
    const res = await fetchPageVersions('p1');
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/pages/{page_ref}/versions', {
      params: { page_ref: 'p1' },
    });
    expect(res).toEqual([{ version_seq: 1 }]);
  });

  it('restorePageVersion calls POST versions restore with If-Match', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ version_seq: 2 });
    const res = await restorePageVersion('p1', 1, '"etag-abc"');
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/pages/p1/versions/1/restore', {
      ifMatch: '"etag-abc"',
    });
    expect(res).toEqual({ version_seq: 2 });
  });

  it('createIssue calls POST /api/v1/projects/{projectKey}/issues', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ id: 'i1', key: 'KAN-1' });
    const res = await createIssue('KAN', { title: 'Bug' });
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/projects/{projectKey}/issues', {
      params: { projectKey: 'KAN' },
      body: { title: 'Bug' },
    });
    expect(res).toEqual({ id: 'i1', key: 'KAN-1' });
  });

  it('createLink calls POST /api/v1/links', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ ok: true });
    await createLink({ source_id: 's1', target_id: 't1', link_type: 'RELATES_TO' });
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/links', {
      body: { source_id: 's1', target_id: 't1', link_type: 'RELATES_TO' },
    });
  });
});
