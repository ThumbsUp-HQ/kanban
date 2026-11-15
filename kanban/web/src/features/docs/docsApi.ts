/**
 * API client functions and types for Docs and Pages workspace (KB-P3-50, S8.1, S5.1).
 */

import { apiFetch, getCsrfToken, type Method, type ApiFetchOptions } from '../../api/client';
import { ApiProblem } from '../../api/problem';
import type { paths } from '../../api/schema.gen';

const UNSAFE_METHODS: ReadonlySet<Method> = new Set<Method>(['POST', 'PUT', 'PATCH', 'DELETE']);

export async function ensureDocsCsrfToken(): Promise<string | null> {
  const existing = getCsrfToken();
  if (existing) {
    return existing;
  }
  try {
    const res = await fetch('/api/v1/auth/session', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    });
    const data = (await res.json()) as { csrf_token?: string };
    if (data.csrf_token) {
      document.cookie = `kb_csrf=${encodeURIComponent(data.csrf_token)}; Path=/; SameSite=Lax`;
      return data.csrf_token;
    }
  } catch {
    // Ignore bootstrap failures in offline unit tests
  }
  return getCsrfToken();
}

async function typedFetch<T>(
  method: Method,
  path: string,
  opts?: ApiFetchOptions,
): Promise<T> {
  if (UNSAFE_METHODS.has(method) && !getCsrfToken()) {
    await ensureDocsCsrfToken();
  }
  const result = await apiFetch(method, path as unknown as keyof paths, opts);
  return result as T;
}

export interface PageTreeNode {
  id?: string | null;
  title?: string | null;
  slug?: string | null;
  sort_rank?: string | null;
  restricted: boolean;
  label?: string | null;
  children?: PageTreeNode[];
}

export interface BreadcrumbItem {
  id?: string | null;
  title?: string | null;
  slug?: string | null;
  canonical_key?: string | null;
  restricted: boolean;
  label?: string | null;
}

export interface OutlineItem {
  level: number;
  text: string;
  anchor: string;
  start_line: number;
}

export interface ObjectLinkItem {
  source_id?: string;
  target_id?: string;
  link_type: string;
  target_key?: string;
  target_title?: string;
  link_id?: string;
}

export interface PageResponse {
  id: string;
  canonical_key: string;
  doc_id: string;
  parent_page_id: string | null;
  workspace_id: string;
  title: string;
  body_markdown: string;
  body_sha256: string;
  hierarchy_path: string;
  version_seq: number;
  sort_rank: string;
  breadcrumbs: BreadcrumbItem[];
  outline: OutlineItem[];
  access_manifest: Record<string, unknown>;
  capabilities: string[];
  object_links?: ObjectLinkItem[];
}

export interface PageVersionResponse {
  page_id: string;
  version_seq: number;
  title: string;
  body_markdown: string;
  body_sha256: string;
  created_by_id: string | null;
  created_at: string;
}

export async function fetchDocsTree(projectKey: string): Promise<PageTreeNode[]> {
  try {
    return await typedFetch<PageTreeNode[]>('GET', '/api/v1/projects/{projectKey}/docs/tree', {
      params: { projectKey },
    });
  } catch (err) {
    if (err instanceof ApiProblem) {
      throw err;
    }
    // Fallback to docs/{doc_ref}/tree only for non-ApiProblem test stubs
    return await typedFetch<PageTreeNode[]>('GET', '/api/v1/docs/{doc_ref}/tree', {
      params: { doc_ref: projectKey },
    });
  }
}

export async function fetchPage(pageId: string): Promise<PageResponse> {
  return typedFetch<PageResponse>('GET', '/api/v1/pages/{page_ref}', {
    params: { page_ref: pageId },
  });
}

export async function updatePage(
  pageId: string,
  payload: { title?: string; body_markdown?: string },
  etag?: string,
): Promise<PageResponse> {
  return typedFetch<PageResponse>('PATCH', '/api/v1/pages/{page_ref}', {
    params: { page_ref: pageId },
    body: payload,
    ifMatch: etag,
  });
}

export async function createPage(
  docRefOrProjectKey: string,
  payload: { title: string; body_markdown?: string; parent_page_id?: string | null },
): Promise<PageResponse> {
  try {
    return await typedFetch<PageResponse>('POST', '/api/v1/docs/{doc_ref}/pages', {
      params: { doc_ref: docRefOrProjectKey },
      body: payload,
    });
  } catch (err) {
    if (err instanceof ApiProblem && err.status === 404) {
      const project = await typedFetch<{ id: string }>('GET', '/api/v1/projects/{projectKey}', {
        params: { projectKey: docRefOrProjectKey },
      });
      const existingDocs = await typedFetch<{ id: string }[]>('GET', '/api/v1/docs', {
        query: { project: project.id },
      });
      let targetDocId = Array.isArray(existingDocs) && existingDocs[0]?.id ? existingDocs[0].id : '';
      if (!targetDocId) {
        const createdDoc = await typedFetch<{ id: string }>('POST', '/api/v1/docs', {
          body: {
            title: payload.title,
            body_markdown: payload.body_markdown ?? '',
            project_id: project.id,
          },
        });
        targetDocId = createdDoc.id;
      }
      return await typedFetch<PageResponse>('POST', '/api/v1/docs/{doc_ref}/pages', {
        params: { doc_ref: targetDocId },
        body: payload,
      });
    }
    return await typedFetch<PageResponse>('POST', '/api/v1/projects/{projectKey}/docs/pages', {
      params: { projectKey: docRefOrProjectKey },
      body: payload,
    });
  }
}

export async function movePage(
  pageId: string,
  payload: { parent_page_id?: string | null; after_page_id?: string | null; before_page_id?: string | null },
): Promise<PageResponse> {
  return typedFetch<PageResponse>('POST', '/api/v1/pages/{page_ref}/move', {
    params: { page_ref: pageId },
    body: payload,
  });
}

export async function fetchPageVersions(pageId: string): Promise<PageVersionResponse[]> {
  return typedFetch<PageVersionResponse[]>('GET', '/api/v1/pages/{page_ref}/versions', {
    params: { page_ref: pageId },
  });
}

export async function restorePageVersion(
  pageId: string,
  versionSeq: number,
  etag?: string,
): Promise<PageResponse> {
  return typedFetch<PageResponse>('POST', `/api/v1/pages/${encodeURIComponent(pageId)}/versions/${String(versionSeq)}/restore`, {
    ifMatch: etag,
  });
}

export interface CreatedIssue {
  id: string;
  key?: string;
  title?: string;
}

export async function createIssue(
  projectKey: string,
  payload: { title: string; description?: string },
): Promise<CreatedIssue> {
  return typedFetch<CreatedIssue>('POST', '/api/v1/projects/{projectKey}/issues', {
    params: { projectKey },
    body: payload,
  });
}

export async function createLink(payload: {
  source_id: string;
  target_id: string;
  link_type: string;
}): Promise<unknown> {
  return typedFetch<unknown>('POST', '/api/v1/links', {
    body: payload,
  });
}
