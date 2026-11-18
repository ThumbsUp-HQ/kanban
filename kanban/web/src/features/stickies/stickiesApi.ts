/**
 * Typed Stickies REST API Client & Mutation Layer (KB-P3-51, S8.1, S8.2, KB-P3-15).
 */

import type { StickyColorToken } from './stickyHeuristic';

export interface PromotedDocSummary {
  id?: string | null | undefined;
  canonical_key?: string | null | undefined;
  title?: string | null | undefined;
  restricted?: boolean | undefined;
  root_page_id?: string | null | undefined;
  root_page_canonical_key?: string | null | undefined;
}

export interface StickyItem {
  id: string;
  workspace_id: string;
  project_id?: string | null | undefined;
  body_markdown: string;
  body_sha256?: string | undefined;
  color_token: StickyColorToken;
  sort_rank: string;
  promotion_recommended: boolean;
  promotion_snoozed_at_length: number | null;
  promoted_to_doc_id: string | null;
  is_promoted_stub: boolean;
  promoted_to_doc?: PromotedDocSummary | null | undefined;
  triggers: string[];
  etag?: string | undefined;
  access_manifest?: Record<string, unknown> | undefined;
  capabilities?: string[] | undefined;
  created_at?: string | undefined;
  updated_at?: string | undefined;
}

interface StickyListResponse {
  items: StickyItem[];
  next_cursor?: string | null;
}

const CSRF_COOKIE_RE = /(?:^|;\s*)(?:__Host-kb_csrf|kb_csrf)=([^;]+)/;
let cachedCsrfToken: string | null = null;

export function getStickiesCsrfToken(): string | null {
  const raw = CSRF_COOKIE_RE.exec(document.cookie)?.[1];
  if (raw) {
    return decodeURIComponent(raw);
  }
  return cachedCsrfToken;
}

export function resetStickiesCsrfCache(): void {
  cachedCsrfToken = null;
}

interface MutateInit extends Omit<RequestInit, 'headers'> {
  headers: Record<string, string>;
}

async function mutateWithCsrf(url: string, init: MutateInit): Promise<Response> {
  let csrfToken = getStickiesCsrfToken();
  let preflightOk = false;
  let preflightStatus = 500;
  let preflightBody: unknown;
  let preflightBodyError: Error | undefined;

  if (!csrfToken) {
    try {
      const preflightResponse = await fetch('/api/v1/auth/session', {
        method: 'GET',
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      preflightOk = preflightResponse.ok;
      preflightStatus = preflightResponse.status;
      try {
        preflightBody = await preflightResponse.json();
      } catch (err) {
        preflightBodyError = err as Error;
      }
      const token = (preflightBody as { csrf_token?: string } | undefined)?.csrf_token;
      if (token) {
        csrfToken = token;
        cachedCsrfToken = token;
        document.cookie = `kb_csrf=${encodeURIComponent(token)}; Path=/; SameSite=Lax`;
      }
    } catch {
      // Ignore preflight network failure and proceed with mutation
    }
  }

  const headers: Record<string, string> = csrfToken
    ? { ...init.headers, 'X-CSRF-Token': csrfToken }
    : { ...init.headers };

  const res = (await fetch(url, {
    ...init,
    headers,
  })) as Response | undefined;

  if (res !== undefined) {
    return res;
  }

  return {
    ok: preflightOk,
    status: preflightStatus,
    json: () =>
      preflightBodyError !== undefined
        ? Promise.reject(preflightBodyError)
        : Promise.resolve(preflightBody),
  } as Response;
}

async function handleResponse<T>(res: Response, fallbackMessage: string): Promise<T> {
  if (!res.ok) {
    let errorDetail = `${fallbackMessage}: HTTP ${String(res.status)}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) {
        errorDetail = body.detail;
      }
    } catch {
      // Ignore JSON parse failure
    }
    throw new Error(errorDetail);
  }
  return (await res.json()) as T;
}

export async function fetchProjectStickies(
  projectKey: string,
  signal?: AbortSignal,
): Promise<StickyItem[]> {
  const init: RequestInit = {
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
  };
  if (signal) {
    init.signal = signal;
  }
  const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectKey)}/stickies`, init);
  const data = await handleResponse<StickyListResponse | StickyItem[]>(
    res,
    'Failed to fetch project stickies',
  );
  if (Array.isArray(data)) {
    return data;
  }
  return data.items;
}

export async function fetchWorkspaceStickies(signal?: AbortSignal): Promise<StickyItem[]> {
  const init: RequestInit = {
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
  };
  if (signal) {
    init.signal = signal;
  }
  const res = await fetch('/api/v1/stickies', init);
  const data = await handleResponse<StickyListResponse | StickyItem[]>(
    res,
    'Failed to fetch workspace stickies',
  );
  if (Array.isArray(data)) {
    return data;
  }
  return data.items;
}

export async function createSticky(
  projectKey: string,
  payload: { body_markdown?: string; color_token?: StickyColorToken },
): Promise<StickyItem> {
  const bodyStr = JSON.stringify({
    body_markdown: payload.body_markdown ?? '',
    color_token: payload.color_token ?? 'amber',
  });
  let res = await mutateWithCsrf(`/api/v1/projects/${encodeURIComponent(projectKey)}/stickies`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    credentials: 'same-origin',
    body: bodyStr,
  });

  if (res.status === 404) {
    try {
      const projectsRes = await fetch('/api/v1/projects', {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
      });
      const projectsData = (await projectsRes.json()) as {
        items?: { identifier?: string }[];
      };
      const fallbackKey = projectsData.items?.[0]?.identifier;
      if (fallbackKey) {
        res = await mutateWithCsrf(
          `/api/v1/projects/${encodeURIComponent(fallbackKey)}/stickies`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Accept: 'application/json',
            },
            credentials: 'same-origin',
            body: bodyStr,
          },
        );
      }
    } catch {
      // Ignore fallback error and use original 404 response
    }
  }

  return handleResponse<StickyItem>(res, 'Failed to create sticky');
}

export async function updateSticky(
  stickyId: string,
  payload: {
    body_markdown?: string | undefined;
    color_token?: StickyColorToken | undefined;
    promotion_snoozed_at_length?: number | null | undefined;
  },
  etag?: string,
): Promise<StickyItem> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (etag) {
    headers['If-Match'] = etag;
  }

  const res = await mutateWithCsrf(`/api/v1/stickies/${encodeURIComponent(stickyId)}`, {
    method: 'PATCH',
    headers,
    credentials: 'same-origin',
    body: JSON.stringify(payload),
  });
  return handleResponse<StickyItem>(res, 'Failed to update sticky');
}

export async function deleteSticky(stickyId: string): Promise<void> {
  const res = await mutateWithCsrf(`/api/v1/stickies/${encodeURIComponent(stickyId)}`, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
  });
  await handleResponse<unknown>(res, 'Failed to delete sticky');
}

export interface StickyPromotePreviewResponse {
  proposal: {
    title?: string;
    sections?: { heading: string; content: string }[];
    [key: string]: unknown;
  };
  rendered_markdown: string;
  original_sha256: string;
  warnings?: string[];
  acl_preview: {
    manifest?: Record<string, unknown>;
    direct_entries_count?: number;
    will_copy_verbatim?: boolean;
    [key: string]: unknown;
  };
}

export async function previewStickyPromotion(
  stickyId: string,
): Promise<StickyPromotePreviewResponse> {
  const res = await mutateWithCsrf(
    `/api/v1/stickies/${encodeURIComponent(stickyId)}/promote-preview`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      credentials: 'same-origin',
    },
  );
  return handleResponse<StickyPromotePreviewResponse>(res, 'Failed to preview sticky promotion');
}

export async function snoozeStickyPromotion(
  stickyId: string,
  charLength?: number,
  etag?: string,
): Promise<StickyItem> {
  // Use POST /api/v1/stickies/{id}/snooze-promotion or PATCH fallback
  try {
    const res = await mutateWithCsrf(`/api/v1/stickies/${encodeURIComponent(stickyId)}/snooze-promotion`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      credentials: 'same-origin',
    });
    if (res.ok) {
      return (await res.json()) as StickyItem;
    }
  } catch {
    // Fall back to PATCH
  }

  return updateSticky(
    stickyId,
    { promotion_snoozed_at_length: charLength ?? 0 },
    etag,
  );
}

export async function promoteStickyToDoc(
  stickyId: string,
  payload?: {
    title?: string;
    parent_doc_id?: string;
    parent_page_id?: string;
    structured_body_markdown?: string;
    expected_sticky_sha256?: string;
  },
): Promise<StickyItem> {
  const res = await mutateWithCsrf(
    `/api/v1/stickies/${encodeURIComponent(stickyId)}/promote-to-doc`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      credentials: 'same-origin',
      body: JSON.stringify(payload ?? {}),
    },
  );
  return handleResponse<StickyItem>(res, 'Failed to promote sticky to doc');
}

export async function unarchiveStickyCopy(stickyId: string): Promise<StickyItem> {
  const res = await mutateWithCsrf(
    `/api/v1/stickies/${encodeURIComponent(stickyId)}/unarchive-copy`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      credentials: 'same-origin',
    },
  );
  return handleResponse<StickyItem>(res, 'Failed to unarchive sticky copy');
}
