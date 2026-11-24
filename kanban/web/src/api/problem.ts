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

export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  code?: string;
  detail?: string;
  instance?: string;
  request_id?: string;
  doc_href?: string;
  help_summary?: string;
  errors?: Array<{ path?: string | string[]; message?: string }>;
  [key: string]: unknown;
}

export class ApiProblem extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string | undefined;
  readonly detail: string | undefined;
  readonly instance: string | undefined;
  readonly docHref: string | undefined;
  readonly helpSummary: string | undefined;
  readonly data: Record<string, unknown>;

  constructor(status: number, data?: unknown) {
    const obj: Record<string, unknown> =
      data !== null && typeof data === 'object' && !Array.isArray(data)
        ? (data as Record<string, unknown>)
        : {};
    const code = pickString(obj, 'code');
    const title = pickString(obj, 'title');
    const detail = pickString(obj, 'detail');
    const docHref = pickString(obj, 'doc_href');
    const helpSummary = pickString(obj, 'help_summary');
    const resolvedCode = code !== undefined && code.trim() !== '' ? code : 'UNKNOWN';
    let message = detail ?? title ?? `API error ${String(status)} (${resolvedCode})`;
    if (Array.isArray(obj.errors) && obj.errors.length > 0) {
      const errorSummaries = obj.errors
        .map((entry) => {
          if (entry !== null && typeof entry === 'object') {
            const p = (entry as Record<string, unknown>).path;
            const m = (entry as Record<string, unknown>).message;
            if (p !== undefined && m !== undefined) {
              let pathStr = '';
              if (Array.isArray(p)) {
                pathStr = p
                  .map((x) => (typeof x === 'string' ? x : typeof x === 'number' ? String(x) : ''))
                  .filter((x) => x !== '')
                  .join('.');
              } else if (typeof p === 'string') {
                pathStr = p;
              } else if (typeof p === 'number') {
                pathStr = String(p);
              }
              const msgStr = typeof m === 'string' ? m : typeof m === 'number' ? String(m) : '';
              if (pathStr && msgStr) {
                return `${pathStr}: ${msgStr}`;
              }
            }
          }
          return null;
        })
        .filter((s): s is string => s !== null);

      if (errorSummaries.length > 0) {
        message = `${message}: ${errorSummaries.join(', ')}`;
      }
    }
    super(message);
    this.data = obj;
    this.name = 'ApiProblem';
    this.status = status;
    this.code = resolvedCode;
    this.title = title;
    this.detail = detail;
    this.instance = pickString(obj, 'instance');
    this.docHref = docHref;
    this.helpSummary = helpSummary;
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
