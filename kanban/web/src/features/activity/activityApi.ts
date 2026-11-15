/**
 * Typed API client wrappers and domain models for Activity & Comments (KB-P3-44, S7.1, S7.2 8j/8k).
 */

import { ApiProblem } from '../../api/problem';

export type ActivityTab = 'all' | 'comments' | 'history' | 'gates';

export const FROZEN_REACTION_EMOJIS = ['👍', '👎', '😄', '🎉', '😕', '❤️', '🚀', '👀'] as const;
export type ReactionEmoji = (typeof FROZEN_REACTION_EMOJIS)[number];

export interface ActorSummary {
  readonly id?: string;
  readonly type?: 'USER' | 'AGENT';
  readonly slug?: string;
  readonly display_name?: string;
  readonly handle?: string;
  readonly redacted?: boolean;
  readonly label?: string;
}

export interface GatePayload {
  readonly hook_name?: string;
  readonly harness?: string;
  readonly repo_mount_ro?: boolean;
  readonly from_state?: string;
  readonly to_state?: string;
  readonly execution_latency_ms?: number;
  readonly verdict_sha256?: string;
  readonly reason?: string;
  readonly audit_comment_id?: string;
}

export interface CreatorOverridePayload {
  readonly old_created_by?: string;
  readonly new_created_by?: string;
  readonly reason?: string;
  readonly row_hash?: string;
}

export interface ActivityItem {
  readonly id: string;
  readonly category?: 'COMMENT' | 'HISTORY' | 'AGENT_GATE' | undefined;
  readonly event_type: string;
  readonly actor: ActorSummary;
  readonly created_at: string;
  readonly payload?: Record<string, unknown> | GatePayload | CreatorOverridePayload | undefined;
  readonly row_hash?: string | undefined;
  readonly prev_hash?: string | undefined;
  readonly comment?: CommentResponse | undefined;
}

export interface ActivityResponse {
  readonly tab?: ActivityTab | undefined;
  readonly counts: {
    readonly all: number;
    readonly comments: number;
    readonly history: number;
    readonly gates: number;
  };
  readonly items: readonly ActivityItem[];
  readonly next_cursor: string | null;
}

export interface CommentAuthor {
  readonly id: string;
  readonly handle?: string | undefined;
  readonly display_name?: string | undefined;
}

export interface ReactionSummary {
  readonly emoji: string;
  readonly count: number;
  readonly reacted_by_me: boolean;
}

export interface MentionSummary {
  readonly handle: string;
  readonly principal_id: string;
  readonly has_access: boolean;
}

export interface CommentResponse {
  readonly id: string;
  readonly issue_id: string;
  readonly parent_comment_id?: string | null | undefined;
  readonly author_id?: string | undefined;
  readonly author: CommentAuthor;
  readonly body_markdown?: string | null | undefined;
  readonly body_sha256?: string | null | undefined;
  readonly permalink?: string | undefined;
  readonly created_at: string;
  readonly edited_at?: string | null | undefined;
  readonly deleted: boolean;
  readonly etag?: string | undefined;
  readonly reactions: readonly ReactionSummary[];
  readonly replies?: readonly CommentResponse[] | undefined;
  readonly replies_next_cursor?: string | null | undefined;
  readonly mentions?: readonly MentionSummary[] | undefined;
  readonly unnotified_mentions?: readonly MentionSummary[] | undefined;
}

export interface CommentList {
  readonly items: readonly CommentResponse[];
  readonly next_cursor: string | null;
}

export interface MentionAccessWarning {
  readonly code: 'MENTION_ACCESS_WARNING';
  readonly unauthorized_mentions: readonly {
    readonly handle: string;
    readonly principal_id: string;
  }[];
}

export interface AssigneeSuggestion {
  readonly id: string;
  readonly handle: string;
  readonly display_name: string;
  readonly is_agent?: boolean;
}

export interface AssigneeSuggestionsResponse {
  readonly items: readonly AssigneeSuggestion[];
}

const CSRF_COOKIE_RE = /(?:^|;\s*)(?:__Host-kb_csrf|kb_csrf)=([^;]+)/;
let cachedCsrfToken: string | null = null;

export function getActivityCsrfToken(): string | null {
  const cookieStr = typeof document !== 'undefined' ? document.cookie : '';
  const raw = CSRF_COOKIE_RE.exec(cookieStr)?.[1];
  if (raw) {
    return decodeURIComponent(raw);
  }
  return cachedCsrfToken;
}

export function resetActivityCsrfCache(): void {
  cachedCsrfToken = null;
}

interface MutateInit extends Omit<RequestInit, 'headers'> {
  headers?: Record<string, string>;
}

async function mutateWithCsrf(url: string, init: MutateInit): Promise<Response> {
  let csrfToken = getActivityCsrfToken();
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
        if (typeof document !== 'undefined') {
          document.cookie = `kb_csrf=${encodeURIComponent(token)}; Path=/; SameSite=Lax`;
        }
      } else {
        csrfToken = getActivityCsrfToken();
      }
    } catch {
      // Ignore preflight network failure and proceed with mutation
    }
  }

  const baseHeaders = init.headers ?? {};
  const headers: Record<string, string> = csrfToken
    ? { ...baseHeaders, 'X-CSRF-Token': csrfToken }
    : { ...baseHeaders };

  const res = (await fetch(url, {
    ...init,
    headers,
    credentials: 'same-origin',
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

async function parseErrorBody(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return {};
  }
}

export async function fetchActivity(
  issueKey: string,
  tab: ActivityTab = 'all',
  cursor?: string | null,
): Promise<ActivityResponse> {
  const query: Record<string, string> = { tab };
  if (cursor) {
    query.cursor = cursor;
  }
  const res = await fetch(`/api/v1/issues/${encodeURIComponent(issueKey)}/activity?${new URLSearchParams(query).toString()}`, {
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
  });
  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw new ApiProblem(res.status, errorBody);
  }
  return (await res.json()) as ActivityResponse;
}

export async function fetchComments(
  issueKey: string,
  cursor?: string | null,
): Promise<CommentList> {
  const query: Record<string, string> = {};
  if (cursor) {
    query.cursor = cursor;
  }
  const qs = new URLSearchParams(query).toString();
  const url = `/api/v1/issues/${encodeURIComponent(issueKey)}/comments${qs ? `?${qs}` : ''}`;
  const res = await fetch(url, {
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
  });
  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw new ApiProblem(res.status, errorBody);
  }
  return (await res.json()) as CommentList;
}

export async function createComment(
  issueKey: string,
  body: {
    body_markdown: string;
    parent_comment_id?: string | null | undefined;
    acknowledge_mentions?: readonly string[] | undefined;
  },
): Promise<CommentResponse> {
  const res = await mutateWithCsrf(`/api/v1/issues/${encodeURIComponent(issueKey)}/comments`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    credentials: 'same-origin',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw new ApiProblem(res.status, errorBody);
  }
  return (await res.json()) as CommentResponse;
}

export async function patchComment(
  commentId: string,
  body: {
    body_markdown: string;
    acknowledge_mentions?: readonly string[] | undefined;
  },
  etag?: string,
): Promise<CommentResponse> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (etag) {
    headers['If-Match'] = etag;
  }
  const res = await mutateWithCsrf(`/api/v1/comments/${encodeURIComponent(commentId)}`, {
    method: 'PATCH',
    headers,
    credentials: 'same-origin',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw new ApiProblem(res.status, errorBody);
  }
  return (await res.json()) as CommentResponse;
}

export async function deleteComment(commentId: string): Promise<void> {
  const res = await mutateWithCsrf(`/api/v1/comments/${encodeURIComponent(commentId)}`, {
    method: 'DELETE',
    credentials: 'same-origin',
  });
  if (!res.ok && res.status !== 204) {
    const errorBody = await parseErrorBody(res);
    throw new ApiProblem(res.status, errorBody);
  }
}

export async function addReaction(
  commentId: string,
  emoji: string,
): Promise<ReactionSummary> {
  const res = await mutateWithCsrf(
    `/api/v1/comments/${encodeURIComponent(commentId)}/reactions/${encodeURIComponent(emoji)}`,
    {
      method: 'PUT',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    },
  );
  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw new ApiProblem(res.status, errorBody);
  }
  return (await res.json()) as ReactionSummary;
}

export async function removeReaction(
  commentId: string,
  emoji: string,
): Promise<void> {
  const res = await mutateWithCsrf(
    `/api/v1/comments/${encodeURIComponent(commentId)}/reactions/${encodeURIComponent(emoji)}`,
    {
      method: 'DELETE',
      credentials: 'same-origin',
    },
  );
  if (!res.ok && res.status !== 204) {
    const errorBody = await parseErrorBody(res);
    throw new ApiProblem(res.status, errorBody);
  }
}

export async function fetchAssigneeSuggestions(
  projectKey: string,
  query: string,
): Promise<AssigneeSuggestionsResponse> {
  const qs = new URLSearchParams({ q: query, limit: '10' }).toString();
  const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectKey)}/assignee-suggestions?${qs}`, {
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
  });
  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw new ApiProblem(res.status, errorBody);
  }
  return (await res.json()) as AssigneeSuggestionsResponse;
}
