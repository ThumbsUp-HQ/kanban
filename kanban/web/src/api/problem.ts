/**
 * RFC 7807 Problem Details mapping (KB-P2-01, KB-P3-33).
 *
 * UI contract: `isNotFound` treats every 404 uniformly ("Not found or no access"); the client
 * never distinguishes 403 from 404 for unreadable objects.
 */

function pickString(obj: Record<string, unknown>, key: string): string | undefined {
  const value = obj[key];
  return typeof value === 'string' ? value : undefined;
}

export class ApiProblem extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string | undefined;
  readonly detail: string | undefined;
  readonly instance: string | undefined;
  readonly data: unknown;

  constructor(status: number, data?: unknown) {
    const obj: Record<string, unknown> =
      data !== null && typeof data === 'object' && !Array.isArray(data)
        ? (data as Record<string, unknown>)
        : {};
    const code = pickString(obj, 'code');
    const title = pickString(obj, 'title');
    const detail = pickString(obj, 'detail');
    const resolvedCode = code !== undefined && code.trim() !== '' ? code : 'UNKNOWN';
    super(detail ?? title ?? `API error ${String(status)} (${resolvedCode})`);
    this.name = 'ApiProblem';
    this.status = status;
    this.code = resolvedCode;
    this.title = title;
    this.detail = detail;
    this.instance = pickString(obj, 'instance');
    this.data = data;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** True for any 404 (unreadable and nonexistent are indistinguishable by design). */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiProblem && error.status === 404;
}

/** True for HTTP 412 (description ETag conflict). */
export function isPreconditionFailed(error: unknown): boolean {
  return error instanceof ApiProblem && error.status === 412;
}
