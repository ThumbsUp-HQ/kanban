/**
 * API client functions and types for drawer header and overflow actions (KB-P3-43).
 *
 * Traceability: Spec S7.1, S7.2 8l, 8m, 8n, 8o, 8p, 8q, S12.1, S12.3.
 */

import { apiFetch, type Method, type ApiFetchOptions } from '../../api/client';
import type { paths } from '../../api/schema.gen';

async function untypedApiFetch<T>(
  method: Method,
  path: string,
  opts?: ApiFetchOptions,
): Promise<T> {
  const result = await apiFetch(method, path as unknown as keyof paths, opts);
  return result as T;
}

export const MUTABLE_EVENT_TYPES: readonly string[] = [
  'COMMENT_CREATED',
  'ISSUE_STATE_CHANGED',
  'ISSUE_FIELD_CHANGED',
  'ISSUE_DESCRIPTION_CHANGED',
  'ISSUE_LABELS_CHANGED',
  'ASSIGNEE_ADDED',
  'ASSIGNEE_REMOVED',
] as const;

export const EVENT_TYPE_LABELS: Record<string, string> = {
  COMMENT_CREATED: 'Comments',
  ISSUE_STATE_CHANGED: 'State changes',
  ISSUE_FIELD_CHANGED: 'Field updates',
  ISSUE_DESCRIPTION_CHANGED: 'Description changes',
  ISSUE_LABELS_CHANGED: 'Labels changed',
  ASSIGNEE_ADDED: 'Assignee added',
  ASSIGNEE_REMOVED: 'Assignee removed',
};

export const USER_CREATABLE_LINK_TYPES: readonly string[] = [
  'BLOCKS',
  'BLOCKED_BY',
  'RELATES_TO',
  'DUPLICATES',
  'VERIFIED_BY_DOC',
  'DERIVED_FROM_STICKY',
] as const;

export interface SubscriptionResponse {
  subscribed: boolean;
  muted_event_types: string[];
  source: string | null;
}

export interface CanonicalUrlResponse {
  url: string;
  markdown: string;
}

export interface RestrictedEndpoint {
  restricted: true;
  label?: string;
}

export interface UnrestrictedEndpoint {
  restricted?: false;
  id: string;
  type: string;
  key: string;
  title: string;
}

export type EndpointOut = RestrictedEndpoint | UnrestrictedEndpoint;

export interface OutboundLink {
  id: string;
  link_type: string;
  link_state: 'ACTIVE' | 'FLAGGED_INVALID';
  target: EndpointOut;
}

export interface InboundLink {
  id: string;
  link_type: string;
  link_state: 'ACTIVE' | 'FLAGGED_INVALID';
  source: EndpointOut;
}

export interface LinksListResponse {
  outbound: OutboundLink[];
  inbound: InboundLink[];
  truncated?: boolean;
}

export interface CopyIssueRequest {
  include_sub_issues?: boolean;
  include_attachments?: boolean;
  link_as_relates_to?: boolean;
}

export interface CopyIssueResponse {
  issue: {
    key: string;
    summary: string;
    [k: string]: unknown;
  };
  copied_sub_issues?: { source_key: string; copy_key: string }[];
  skipped?: { restricted_sub_issues?: number };
  copied_attachments?: number;
  link_id?: string | null;
}

export interface BlastRadiusResponse {
  issue_key: string;
  sub_issues_unparented: number;
  inbound_links_flagged: number;
  outbound_links: number;
  comments: number;
  attachments: number;
  summary_text: string;
  blast_hash: string;
  retention_days: number;
}

export interface IssueDeleteResponse {
  issue_key: string;
  deleted_at: string;
  purge_after: string;
}

// --- Subscription API ---

export async function fetchSubscription(issueKey: string): Promise<SubscriptionResponse> {
  return await untypedApiFetch<SubscriptionResponse>('GET', '/api/v1/issues/{issue_ref}/subscription', {
    params: { issue_ref: issueKey },
  });
}

export async function subscribeIssue(
  issueKey: string,
  mutedEventTypes?: string[],
): Promise<SubscriptionResponse> {
  return await untypedApiFetch<SubscriptionResponse>('PUT', '/api/v1/issues/{issue_ref}/subscription', {
    params: { issue_ref: issueKey },
    body: mutedEventTypes ? { muted_event_types: mutedEventTypes } : {},
  });
}

export async function unsubscribeIssue(issueKey: string): Promise<void> {
  await untypedApiFetch<unknown>('DELETE', '/api/v1/issues/{issue_ref}/subscription', {
    params: { issue_ref: issueKey },
  });
}

export async function patchSubscription(
  issueKey: string,
  mutedEventTypes: string[],
): Promise<SubscriptionResponse> {
  return await untypedApiFetch<SubscriptionResponse>('PATCH', '/api/v1/issues/{issue_ref}/subscription', {
    params: { issue_ref: issueKey },
    body: { muted_event_types: mutedEventTypes },
  });
}

// --- Links & Canonical URL API ---

export async function fetchCanonicalUrl(objectKey: string): Promise<CanonicalUrlResponse> {
  return await untypedApiFetch<CanonicalUrlResponse>('GET', '/api/v1/objects/{object_ref}/canonical-url', {
    params: { object_ref: objectKey },
  });
}

export async function fetchObjectLinks(objectKey: string): Promise<LinksListResponse> {
  return await untypedApiFetch<LinksListResponse>('GET', '/api/v1/objects/{object_ref}/links', {
    params: { object_ref: objectKey },
  });
}

export async function createObjectLink(
  sourceKey: string,
  target: string,
  linkType: string,
): Promise<OutboundLink> {
  return await untypedApiFetch<OutboundLink>('POST', '/api/v1/objects/{object_ref}/links', {
    params: { object_ref: sourceKey },
    body: { target, link_type: linkType },
  });
}

export async function deleteObjectLink(linkId: string): Promise<void> {
  await untypedApiFetch<unknown>('DELETE', '/api/v1/links/{link_id}', {
    params: { link_id: linkId },
  });
}

// --- Copy API ---

export async function copyIssue(
  issueKey: string,
  request: CopyIssueRequest,
): Promise<CopyIssueResponse> {
  return await untypedApiFetch<CopyIssueResponse>('POST', '/api/v1/issues/{issue_ref}/copy', {
    params: { issue_ref: issueKey },
    body: request,
  });
}

// --- Archive & Unarchive API ---

export async function archiveIssue(issueKey: string): Promise<unknown> {
  return await untypedApiFetch<unknown>('POST', '/api/v1/issues/{issue_ref}/archive', {
    params: { issue_ref: issueKey },
  });
}

export async function unarchiveIssue(issueKey: string): Promise<unknown> {
  return await untypedApiFetch<unknown>('POST', '/api/v1/issues/{issue_ref}/unarchive', {
    params: { issue_ref: issueKey },
  });
}

// --- Delete & Preview API ---

export async function fetchDeletePreview(issueKey: string): Promise<BlastRadiusResponse> {
  return await untypedApiFetch<BlastRadiusResponse>('GET', '/api/v1/issues/{issue_ref}/delete-preview', {
    params: { issue_ref: issueKey },
  });
}

export async function deleteIssue(
  issueKey: string,
  blastHash: string,
): Promise<IssueDeleteResponse> {
  return await untypedApiFetch<IssueDeleteResponse>('DELETE', '/api/v1/issues/{issue_ref}', {
    params: { issue_ref: issueKey },
    headers: { 'Kb-Blast-Hash': blastHash },
  });
}
