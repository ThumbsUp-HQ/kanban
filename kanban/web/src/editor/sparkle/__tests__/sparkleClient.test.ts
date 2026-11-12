/**
 * Mandatory Unit Tests for Sparkle SSE Client (KB-P5-08, Cases 5 & 6).
 * Validates text/event-stream line parsing, CSRF headers, 8 KiB cap,
 * unknown event rejection, and all 7 JSON SSE test fixtures.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  fetchSparkle,
  getCsrfToken,
  parseSseEvents,
  type SparkleClientOptions,
} from '../sparkleClient';

interface SseFixture {
  name: string;
  status_code: number;
  headers: Record<string, string>;
  raw: string;
}

function loadSseFixture(fileName: string): SseFixture {
  const fullPath = resolve(
    import.meta.dirname,
    '../../../../../../tests/fixtures/ai/web',
    fileName,
  );
  const content = readFileSync(fullPath, 'utf-8');
  return JSON.parse(content) as SseFixture;
}

function createMockReadableStream(text: string, chunkSize = 64): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const bytes = encoder.encode(text);
  let offset = 0;

  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (offset >= bytes.length) {
        controller.close();
        return;
      }
      const nextChunk = bytes.slice(offset, offset + chunkSize);
      offset += chunkSize;
      controller.enqueue(nextChunk);
    },
  });
}

describe('sparkleClient SSE streaming and fixtures', () => {
  const baseOptions: SparkleClientOptions = {
    projectId: '11111111-1111-1111-1111-111111111111',
    objectId: '22222222-2222-2222-2222-222222222222',
    surface: 'doc',
    prefix: 'Writing documentation for the system',
    suffix: ' and verifying security boundaries.',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('Case 1: parses sparkle_stream_ok.json fixture successfully', async () => {
    const fixture = loadSseFixture('sparkle_stream_ok.json');
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(createMockReadableStream(fixture.raw), {
        status: 200,
        headers: fixture.headers,
      }),
    );

    const result = await fetchSparkle({
      ...baseOptions,
      fetchFn: mockFetch,
    });

    expect(result.status).toBe('ok');
    expect(result.text).toBe(' is an open-source platform');
    expect(result.tokens).toBe(6);
    expect(result.ttft_ms).toBe(18);
    expect(result.total_ms).toBe(35);
  });

  it('Case 2: parses sparkle_stream_empty.json fixture returning empty status', async () => {
    const fixture = loadSseFixture('sparkle_stream_empty.json');
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(createMockReadableStream(fixture.raw), {
        status: 200,
        headers: fixture.headers,
      }),
    );

    const result = await fetchSparkle({
      ...baseOptions,
      fetchFn: mockFetch,
    });

    expect(result.status).toBe('empty');
    expect(result.text).toBe('');
    expect(result.ttft_ms).toBe(12);
  });

  it('Case 3: parses sparkle_stream_secret_scrubbed.json fixture returning secret_scrubbed', async () => {
    const fixture = loadSseFixture('sparkle_stream_secret_scrubbed.json');
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(createMockReadableStream(fixture.raw), {
        status: 200,
        headers: fixture.headers,
      }),
    );

    const result = await fetchSparkle({
      ...baseOptions,
      fetchFn: mockFetch,
    });

    expect(result.status).toBe('secret_scrubbed');
    expect(result.text).toBe('');
  });

  it('Case 4: parses sparkle_stream_timeout.json fixture returning timeout', async () => {
    const fixture = loadSseFixture('sparkle_stream_timeout.json');
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(createMockReadableStream(fixture.raw), {
        status: 200,
        headers: fixture.headers,
      }),
    );

    const result = await fetchSparkle({
      ...baseOptions,
      fetchFn: mockFetch,
    });

    expect(result.status).toBe('timeout');
    expect(result.text).toBe('');
    expect(result.ttft_ms).toBe(150);
  });

  it('Case 5 (Security): rejects sparkle_stream_unknown_event.json with an error', async () => {
    const fixture = loadSseFixture('sparkle_stream_unknown_event.json');
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(createMockReadableStream(fixture.raw), {
        status: 200,
        headers: fixture.headers,
      }),
    );

    await expect(
      fetchSparkle({
        ...baseOptions,
        fetchFn: mockFetch,
      }),
    ).rejects.toThrow(/Unknown SSE event received/);
  });

  it('Case 5 (Security): aborts sparkle_stream_oversize.json exceeding 8 KiB', async () => {
    const fixture = loadSseFixture('sparkle_stream_oversize.json');
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(createMockReadableStream(fixture.raw, 1024), {
        status: 200,
        headers: fixture.headers,
      }),
    );

    await expect(
      fetchSparkle({
        ...baseOptions,
        fetchFn: mockFetch,
      }),
    ).rejects.toThrow(/exceeded 8192 bytes limit/);
  });

  it('Case 5 (Security): parses sparkle_stream_html_text.json preserving literal raw <b>x</b> string', async () => {
    const fixture = loadSseFixture('sparkle_stream_html_text.json');
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(createMockReadableStream(fixture.raw), {
        status: 200,
        headers: fixture.headers,
      }),
    );

    const result = await fetchSparkle({
      ...baseOptions,
      fetchFn: mockFetch,
    });

    expect(result.status).toBe('ok');
    expect(result.text).toBe('<b>x</b>');
    expect(result.tokens).toBe(3);
  });

  it('Case 6 (Fault): handles rejected fetch (network error)', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error('Network connection failed'));

    await expect(
      fetchSparkle({
        ...baseOptions,
        fetchFn: mockFetch,
      }),
    ).rejects.toThrow('Network connection failed');
  });

  it('Case 6 (Fault): handles HTTP 500 server error', async () => {
    const mockFetch = vi.fn().mockResolvedValue(
      new Response('Internal server error', { status: 500 }),
    );

    await expect(
      fetchSparkle({
        ...baseOptions,
        fetchFn: mockFetch,
      }),
    ).rejects.toThrow(/Sparkle endpoint error: HTTP 500/);
  });

  it('Case 6 (Fault): handles stream ended without done event', async () => {
    const rawSse = 'event: completion\ndata: {"text": "incomplete"}\n\n';
    const mockFetch = vi.fn().mockResolvedValue(
      new Response(createMockReadableStream(rawSse), { status: 200 }),
    );

    await expect(
      fetchSparkle({
        ...baseOptions,
        fetchFn: mockFetch,
      }),
    ).rejects.toThrow(/Sparkle stream ended without done event/);
  });

  it('Case 6 (Fault): supports non-stream response.text() fallback and oversize check', async () => {
    const rawSse =
      'event: completion\ndata: {"text": "hello"}\n\nevent: done\ndata: {"status": "ok"}\n\n';
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: null,
      text: () => Promise.resolve(rawSse),
    });

    const result = await fetchSparkle({
      ...baseOptions,
      fetchFn: mockFetch,
    });

    expect(result.status).toBe('ok');
    expect(result.text).toBe('hello');

    // Test text fallback oversize
    const oversizeText = 'event: done\ndata: {"status": "ok"}\n\n' + 'A'.repeat(9000);
    const mockOversizeFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: null,
      text: () => Promise.resolve(oversizeText),
    });

    await expect(
      fetchSparkle({
        ...baseOptions,
        fetchFn: mockOversizeFetch,
      }),
    ).rejects.toThrow(/exceeded 8192 bytes limit/);
  });

  it('handles client timeout abort', async () => {
    const mockFetch = vi.fn().mockImplementation((_url, init: RequestInit) => {
      return new Promise((_, reject) => {
        init.signal?.addEventListener('abort', () => {
          reject(new Error('Client aborted'));
        });
      });
    });

    await expect(
      fetchSparkle({
        ...baseOptions,
        fetchFn: mockFetch,
        timeoutMs: 10,
      }),
    ).rejects.toThrow(/aborted/i);
  });

  it('handles caller signal that is already aborted', async () => {
    const controller = new AbortController();
    controller.abort(new Error('Caller cancelled'));

    await expect(
      fetchSparkle({
        ...baseOptions,
        signal: controller.signal,
      }),
    ).rejects.toThrow('Caller cancelled');
  });

  it('resolves CSRF token from document cookie and meta tag', () => {
    // 1. From __Host-kb_csrf cookie
    Object.defineProperty(document, 'cookie', {
      value: '__Host-kb_csrf=csrf-host-token-123',
      writable: true,
      configurable: true,
    });
    expect(getCsrfToken()).toBe('csrf-host-token-123');

    // 2. From kb_csrf cookie
    document.cookie = 'kb_csrf=csrf-simple-456';
    expect(getCsrfToken()).toBe('csrf-simple-456');

    // 3. Clear cookie and test meta element
    document.cookie = '';
    const meta = document.createElement('meta');
    meta.setAttribute('name', 'csrf-token');
    meta.setAttribute('content', 'csrf-meta-token-789');
    document.head.appendChild(meta);

    expect(getCsrfToken()).toBe('csrf-meta-token-789');
    meta.remove();

    expect(getCsrfToken()).toBeNull();
  });

  it('verifies parseSseEvents with various line formats and comments', () => {
    const raw = ': comment line\nevent: completion\ndata: {"text": "abc"}\n\n';
    const events = parseSseEvents(raw);
    expect(events.length).toBe(1);
    expect(events[0]?.event).toBe('completion');
    expect(events[0]?.data).toBe('{"text": "abc"}');
  });
});
