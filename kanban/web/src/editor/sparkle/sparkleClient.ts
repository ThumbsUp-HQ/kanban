/**
 * Sparkle Completion SSE Client (KB-P5-08, KB-P5-07, S9.1, S9.3, S15.2).
 * Issues POST to /api/v1/sparkle/complete with same-origin credentials and CSRF token.
 * Parses text/event-stream with a hand-written streaming line parser; caps response at 8 KiB.
 */

import type { SparkleDoneStatus } from './sparkleMachine';

export type EditorSurfaceKind =
  | 'summary'
  | 'description'
  | 'comment'
  | 'sticky'
  | 'doc';

export interface SparkleRequestPayload {
  project_id: string;
  object_id: string | null;
  surface: EditorSurfaceKind;
  prefix: string;
  suffix: string;
  client_request_id: string;
}

export interface SparkleClientOptions {
  projectId: string;
  objectId?: string | null | undefined;
  surface: EditorSurfaceKind;
  prefix: string;
  suffix: string;
  clientRequestId?: string | undefined;
  csrfToken?: string | null | undefined;
  signal?: AbortSignal | undefined;
  endpoint?: string | undefined;
  fetchFn?: typeof fetch | undefined;
  timeoutMs?: number | undefined;
  maxBytes?: number | undefined;
}

export interface SparkleResponse {
  status: SparkleDoneStatus;
  text: string;
  tokens?: number | undefined;
  ttft_ms?: number | undefined;
  total_ms?: number | undefined;
}

export const DEFAULT_SPARKLE_TIMEOUT_MS = 200;
export const MAX_SPARKLE_RESPONSE_BYTES = 8192; // 8 KiB cap

/**
 * Resolves CSRF token from document cookie or meta element.
 */
export function getCsrfToken(): string | null {
  if (typeof document === 'undefined') return null;
  const match = /(?:^|;\s*)(?:__Host-kb_csrf|kb_csrf)=([^;]+)/.exec(
    document.cookie,
  );
  if (match?.[1]) return decodeURIComponent(match[1]);
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) return meta.getAttribute('content');
  return null;
}

/**
 * Parses raw SSE text chunk into individual event blocks.
 */
export function parseSseEvents(
  rawText: string,
): { event: string; data: string }[] {
  const normalized = rawText.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const blocks = normalized.split('\n\n');
  const results: { event: string; data: string }[] = [];

  for (const block of blocks) {
    const trimmed = block.trim();
    if (!trimmed) continue;

    let eventType = '';
    const dataLines: string[] = [];

    const lines = trimmed.split('\n');
    for (const line of lines) {
      if (line.startsWith(':')) {
        continue;
      }
      if (line.startsWith('event:')) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim());
      }
    }

    if (eventType || dataLines.length > 0) {
      results.push({
        event: eventType || 'message',
        data: dataLines.join('\n'),
      });
    }
  }

  return results;
}

/**
 * Generates a standard client request ID UUIDv4.
 */
export function generateClientRequestId(): string {
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.randomUUID === 'function'
  ) {
    return crypto.randomUUID();
  }
  return '00000000-0000-4000-8000-000000000000';
}

interface MutableStreamResult {
  completionText: string;
  completionTokens: number | undefined;
  doneStatus: SparkleDoneStatus | null;
  ttftMs: number | undefined;
  totalMs: number | undefined;
}

function processSseBlock(block: string, res: MutableStreamResult): void {
  const events = parseSseEvents(block);
  for (const ev of events) {
    if (ev.event !== 'completion' && ev.event !== 'done') {
      throw new Error(`Unknown SSE event received: ${ev.event}`);
    }
    if (ev.event === 'completion') {
      const parsed = JSON.parse(ev.data) as {
        text?: string;
        tokens?: number;
      };
      if (typeof parsed.text === 'string') {
        res.completionText = parsed.text;
      }
      if (typeof parsed.tokens === 'number') {
        res.completionTokens = parsed.tokens;
      }
    } else {
      const parsed = JSON.parse(ev.data) as {
        status?: SparkleDoneStatus;
        ttft_ms?: number;
        total_ms?: number;
      };
      if (parsed.status) {
        res.doneStatus = parsed.status;
      }
      res.ttftMs = parsed.ttft_ms;
      res.totalMs = parsed.total_ms;
    }
  }
}

/**
 * Initiates an SSE completion request to the Sparkle FIM backend.
 */
export async function fetchSparkle(
  options: SparkleClientOptions,
): Promise<SparkleResponse> {
  const fetcher = options.fetchFn ?? fetch;
  const endpoint = options.endpoint ?? '/api/v1/sparkle/complete';
  const timeoutMs = options.timeoutMs ?? DEFAULT_SPARKLE_TIMEOUT_MS;
  const maxBytes = options.maxBytes ?? MAX_SPARKLE_RESPONSE_BYTES;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort(new Error('Sparkle client timeout exceeded'));
  }, timeoutMs);

  const cleanupSignal = (): void => {
    clearTimeout(timeoutId);
    if (options.signal) {
      options.signal.removeEventListener('abort', onCallerAbort);
    }
  };

  const onCallerAbort = (): void => {
    controller.abort(options.signal?.reason);
  };

  if (options.signal) {
    if (options.signal.aborted) {
      clearTimeout(timeoutId);
      throw options.signal.reason ?? new Error('Aborted');
    }
    options.signal.addEventListener('abort', onCallerAbort);
  }

  const payload: SparkleRequestPayload = {
    project_id: options.projectId,
    object_id: options.objectId ?? null,
    surface: options.surface,
    prefix: options.prefix,
    suffix: options.suffix,
    client_request_id: options.clientRequestId ?? generateClientRequestId(),
  };

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  };

  const csrf = options.csrfToken ?? getCsrfToken();
  if (csrf) {
    headers['X-CSRF-Token'] = csrf;
  }

  try {
    const response = await fetcher(endpoint, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      credentials: 'same-origin',
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Sparkle endpoint error: HTTP ${String(response.status)}`);
    }

    const streamResult: MutableStreamResult = {
      completionText: '',
      completionTokens: undefined,
      doneStatus: null,
      ttftMs: undefined,
      totalMs: undefined,
    };

    if (response.body && typeof response.body.getReader === 'function') {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let totalBytes = 0;
      let buffer = '';

      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;

          totalBytes += value.byteLength;
          if (totalBytes > maxBytes) {
            await reader.cancel('Oversize stream');
            throw new Error(
              `Sparkle stream exceeded ${String(maxBytes)} bytes limit`,
            );
          }
          buffer += decoder.decode(value, { stream: true });

          let eventBoundaryIndex = buffer.indexOf('\n\n');
          while (eventBoundaryIndex !== -1) {
            const block = buffer.slice(0, eventBoundaryIndex);
            buffer = buffer.slice(eventBoundaryIndex + 2);
            processSseBlock(block, streamResult);
            eventBoundaryIndex = buffer.indexOf('\n\n');
          }
        }
      } finally {
        reader.releaseLock();
      }

      if (buffer.trim()) {
        processSseBlock(buffer, streamResult);
      }
    } else {
      const fullText = await response.text();
      const encodedLength = new TextEncoder().encode(fullText).byteLength;
      if (encodedLength > maxBytes) {
        throw new Error(`Sparkle stream exceeded ${String(maxBytes)} bytes limit`);
      }
      processSseBlock(fullText, streamResult);
    }

    if (!streamResult.doneStatus) {
      throw new Error('Sparkle stream ended without done event');
    }

    if (streamResult.doneStatus === 'ok' && streamResult.completionText.length > 0) {
      return {
        status: 'ok',
        text: streamResult.completionText,
        tokens: streamResult.completionTokens,
        ttft_ms: streamResult.ttftMs,
        total_ms: streamResult.totalMs,
      };
    }

    return {
      status: streamResult.doneStatus,
      text: '',
      tokens: streamResult.completionTokens,
      ttft_ms: streamResult.ttftMs,
      total_ms: streamResult.totalMs,
    };
  } finally {
    cleanupSignal();
  }
}
