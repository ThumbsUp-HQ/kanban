import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as clientModule from '../../api/client';
import {
  fetchSubscription,
  subscribeIssue,
  unsubscribeIssue,
  patchSubscription,
  fetchCanonicalUrl,
  fetchObjectLinks,
  createObjectLink,
  deleteObjectLink,
  copyIssue,
  archiveIssue,
  unarchiveIssue,
  fetchDeletePreview,
  deleteIssue,
} from './actionsApi';

describe('actionsApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetchSubscription calls GET /api/v1/issues/{issue_ref}/subscription', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ subscribed: true });
    const res = await fetchSubscription('KAN-1');
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/issues/{issue_ref}/subscription', {
      params: { issue_ref: 'KAN-1' },
    });
    expect(res).toEqual({ subscribed: true });
  });

  it('subscribeIssue calls PUT with and without muted types', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ subscribed: true });
    await subscribeIssue('KAN-1');
    expect(spy).toHaveBeenCalledWith('PUT', '/api/v1/issues/{issue_ref}/subscription', {
      params: { issue_ref: 'KAN-1' },
      body: {},
    });

    await subscribeIssue('KAN-1', ['COMMENT_CREATED']);
    expect(spy).toHaveBeenCalledWith('PUT', '/api/v1/issues/{issue_ref}/subscription', {
      params: { issue_ref: 'KAN-1' },
      body: { muted_event_types: ['COMMENT_CREATED'] },
    });
  });

  it('unsubscribeIssue calls DELETE', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(undefined);
    await unsubscribeIssue('KAN-1');
    expect(spy).toHaveBeenCalledWith('DELETE', '/api/v1/issues/{issue_ref}/subscription', {
      params: { issue_ref: 'KAN-1' },
    });
  });

  it('patchSubscription calls PATCH with muted_event_types', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ subscribed: true });
    await patchSubscription('KAN-1', ['ASSIGNEE_ADDED']);
    expect(spy).toHaveBeenCalledWith('PATCH', '/api/v1/issues/{issue_ref}/subscription', {
      params: { issue_ref: 'KAN-1' },
      body: { muted_event_types: ['ASSIGNEE_ADDED'] },
    });
  });

  it('fetchCanonicalUrl calls GET canonical-url', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ url: 'u', markdown: 'm' });
    const res = await fetchCanonicalUrl('KAN-1');
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/objects/{object_ref}/canonical-url', {
      params: { object_ref: 'KAN-1' },
    });
    expect(res).toEqual({ url: 'u', markdown: 'm' });
  });

  it('fetchObjectLinks calls GET links', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ outbound: [], inbound: [] });
    const res = await fetchObjectLinks('KAN-1');
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/objects/{object_ref}/links', {
      params: { object_ref: 'KAN-1' },
    });
    expect(res).toEqual({ outbound: [], inbound: [] });
  });

  it('createObjectLink calls POST links', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ id: 'l1' });
    const res = await createObjectLink('KAN-1', 'KAN-2', 'BLOCKS');
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/objects/{object_ref}/links', {
      params: { object_ref: 'KAN-1' },
      body: { target: 'KAN-2', link_type: 'BLOCKS' },
    });
    expect(res).toEqual({ id: 'l1' });
  });

  it('deleteObjectLink calls DELETE links/{link_id}', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(undefined);
    await deleteObjectLink('link-1');
    expect(spy).toHaveBeenCalledWith('DELETE', '/api/v1/links/{link_id}', {
      params: { link_id: 'link-1' },
    });
  });

  it('copyIssue calls POST copy', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ issue: { key: 'KAN-2' } });
    const req = { include_sub_issues: true };
    const res = await copyIssue('KAN-1', req);
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/issues/{issue_ref}/copy', {
      params: { issue_ref: 'KAN-1' },
      body: req,
    });
    expect(res).toEqual({ issue: { key: 'KAN-2' } });
  });

  it('archiveIssue and unarchiveIssue call POST archive / unarchive', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ ok: true });
    await archiveIssue('KAN-1');
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/issues/{issue_ref}/archive', {
      params: { issue_ref: 'KAN-1' },
    });

    await unarchiveIssue('KAN-1');
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/issues/{issue_ref}/unarchive', {
      params: { issue_ref: 'KAN-1' },
    });
  });

  it('fetchDeletePreview calls GET delete-preview', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ blast_hash: 'abc' });
    const res = await fetchDeletePreview('KAN-1');
    expect(spy).toHaveBeenCalledWith('GET', '/api/v1/issues/{issue_ref}/delete-preview', {
      params: { issue_ref: 'KAN-1' },
    });
    expect(res).toEqual({ blast_hash: 'abc' });
  });

  it('deleteIssue calls DELETE with Kb-Blast-Hash header', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ issue_key: 'KAN-1' });
    const res = await deleteIssue('KAN-1', 'blast123');
    expect(spy).toHaveBeenCalledWith('DELETE', '/api/v1/issues/{issue_ref}', {
      params: { issue_ref: 'KAN-1' },
      headers: { 'Kb-Blast-Hash': 'blast123' },
    });
    expect(res).toEqual({ issue_key: 'KAN-1' });
  });
});
