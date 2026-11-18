import { QueryClient } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DEDUP_CAPACITY,
  RealtimeClient,
  backoffDelay,
  bindQueryInvalidation,
  useRealtime,
  type RealtimeEvent,
} from './realtime.ts';

class FakeWebSocket {
  static readonly OPEN = 1;
  static instances: FakeWebSocket[] = [];
  readyState = 0;
  sent: string[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string): void {
    this.sent.push(data);
  }
  close(): void {
    this.closed = true;
    this.readyState = 3;
  }
  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
  fail(): void {
    this.readyState = 3;
    this.onclose?.();
  }
  push(data: unknown): void {
    this.onmessage?.({ data: typeof data === 'string' ? data : JSON.stringify(data) } as MessageEvent);
  }
  frames(): Record<string, unknown>[] {
    return this.sent.map((s) => JSON.parse(s) as Record<string, unknown>);
  }
}

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  closed = false;
  listeners = new Map<string, (e: Event) => void>();
  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }
  addEventListener(name: string, cb: (e: Event) => void): void {
    this.listeners.set(name, cb);
  }
  close(): void {
    this.closed = true;
  }
  emit(name: string, data: unknown): void {
    const payload = typeof data === 'string' ? data : JSON.stringify(data);
    this.listeners.get(name)?.({ data: payload, type: name } as unknown as Event);
  }
}

function last<T>(items: T[]): T {
  const item = items.at(-1);
  if (item === undefined) {
    throw new Error('no instance created');
  }
  return item;
}
const ws = (): FakeWebSocket => last(FakeWebSocket.instances);
const sse = (): FakeEventSource => last(FakeEventSource.instances);

function serverEvent(id: string, channel = 'project:p1', topic = 'issue.updated', payload: object = {}) {
  return { type: 'event', topic, channel, event_id: id, object_id: 'o', payload };
}

describe('RealtimeClient', () => {
  let client: RealtimeClient;
  let events: RealtimeEvent[];

  beforeEach(() => {
    vi.useFakeTimers();
    FakeWebSocket.instances = [];
    FakeEventSource.instances = [];
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.stubGlobal('EventSource', FakeEventSource);
    client = new RealtimeClient({ random: () => 0.5 });
    events = [];
  });

  afterEach(() => {
    client.close();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function connectOpen(): void {
    client.connect();
    ws().open();
  }

  function failWs(times: number): void {
    for (let i = 0; i < times; i += 1) {
      ws().fail();
      vi.runOnlyPendingTimers();
    }
  }

  it('derives the ws url from location and reports state transitions', () => {
    const states: string[] = [];
    const off = client.onStateChange((s) => states.push(s));
    client.connect();
    expect(ws().url).toBe(`ws://${window.location.host}/ws`);
    ws().open();
    expect(states).toEqual(['connecting', 'open']);
    off();
    client.close();
    expect(states).toEqual(['connecting', 'open']);
  });

  it('uses wss when the page is https', () => {
    vi.stubGlobal('location', { protocol: 'https:', host: 'kb.test', origin: 'https://kb.test' });
    client.connect();
    expect(ws().url).toBe('wss://kb.test/ws');
  });

  it('subscribes after open and re-subscribes on every reconnect', () => {
    client.subscribe('project:p1', () => undefined);
    connectOpen();
    expect(ws().frames()[0]).toMatchObject({ op: 'subscribe', channels: ['project:p1'] });
    ws().fail();
    expect(client.state).toBe('reconnecting');
    vi.runOnlyPendingTimers();
    ws().open();
    expect(ws().frames()[0]).toMatchObject({ op: 'subscribe', channels: ['project:p1'] });
  });

  it('sends subscribe/unsubscribe frames live and carries last_event_id', () => {
    connectOpen();
    const off = client.subscribe('issue:i1', (e) => events.push(e));
    ws().push(serverEvent('7', 'issue:i1'));
    expect(events.map((e) => e.id)).toEqual(['7']);
    client.subscribe('issue:i2', () => undefined);
    expect(ws().frames()[1]).toMatchObject({ op: 'subscribe', channels: ['issue:i2'], last_event_id: '7' });
    off();
    expect(ws().frames().at(-1)).toMatchObject({ op: 'unsubscribe', channels: ['issue:i1'] });
    off();
  });

  it('keeps a channel while any handler remains', () => {
    connectOpen();
    const a = client.subscribe('issue:i1', () => undefined);
    const b = client.subscribe('issue:i1', () => undefined);
    const sentBefore = ws().sent.length;
    a();
    expect(ws().sent.length).toBe(sentBefore);
    b();
    expect(ws().sent.length).toBe(sentBefore + 1);
  });

  it('does not send frames while the socket is not open', () => {
    client.connect();
    client.subscribe('issue:i1', () => undefined);
    expect(ws().sent).toEqual([]);
  });

  it('bounds backoff by min(15000, 500*2^n) with full jitter', () => {
    expect(backoffDelay(0, () => 0.999)).toBeLessThanOrEqual(500);
    expect(backoffDelay(3, () => 0.999)).toBeLessThanOrEqual(4000);
    expect(backoffDelay(10, () => 0.999)).toBeLessThanOrEqual(15000);
    expect(backoffDelay(10, () => 0)).toBe(0);
    client.connect();
    ws().fail();
    const before = FakeWebSocket.instances.length;
    vi.advanceTimersByTime(249);
    expect(FakeWebSocket.instances.length).toBe(before);
    vi.advanceTimersByTime(1);
    expect(FakeWebSocket.instances.length).toBe(before + 1);
  });

  it('switches to SSE after 3 consecutive failures and tracks Last-Event-ID', () => {
    client.subscribe('project:p1', (e) => events.push(e));
    client.subscribe('issue:i1', () => undefined);
    connectOpen();
    ws().push(serverEvent('5'));
    failWs(1);
    expect(client.state).toBe('reconnecting');
    failWs(2);
    expect(client.state).toBe('sse-fallback');
    expect(sse().url).toContain('/sse?channels=project%3Ap1%2Cissue%3Ai1');
    sse().emit('issue.updated', serverEvent('6'));
    expect(events.map((e) => e.id)).toEqual(['5', '6']);
    expect(client.lastEventId).toBe('6');
  });

  it('dedupes by id across the WS->SSE handover', () => {
    client.subscribe('project:p1', (e) => events.push(e));
    connectOpen();
    ws().push(serverEvent('5'));
    failWs(3);
    sse().emit('issue.updated', serverEvent('5'));
    sse().emit('issue.updated', serverEvent('5'));
    expect(events).toHaveLength(1);
  });

  it('returns to WS after a successful 60s probe and closes SSE', () => {
    client.subscribe('project:p1', () => undefined);
    connectOpen();
    failWs(3);
    const source = sse();
    vi.advanceTimersByTime(60000);
    const probe = ws();
    expect(client.state).toBe('sse-fallback');
    vi.advanceTimersByTime(60000);
    expect(FakeWebSocket.instances.filter((s) => s === probe)).toHaveLength(1);
    probe.open();
    expect(client.state).toBe('open');
    expect(source.closed).toBe(true);
    expect(probe.frames()[0]).toMatchObject({ op: 'subscribe' });
    probe.push(serverEvent('9'));
    expect(client.lastEventId).toBe('9');
  });

  it('stays on SSE when the probe fails and probes again later', () => {
    connectOpen();
    failWs(3);
    vi.advanceTimersByTime(60000);
    ws().fail();
    expect(client.state).toBe('sse-fallback');
    const count = FakeWebSocket.instances.length;
    vi.advanceTimersByTime(60000);
    expect(FakeWebSocket.instances.length).toBe(count + 1);
  });

  it('ignores a stale probe close and closes a pending probe on close()', () => {
    connectOpen();
    failWs(3);
    vi.advanceTimersByTime(60000);
    const probe = ws();
    client.close();
    expect(probe.closed).toBe(true);
    probe.fail();
  });

  it('drops oversize, malformed, schema-invalid and long-id events and counts them', () => {
    connectOpen();
    client.subscribe('project:p1', (e) => events.push(e));
    ws().push('x'.repeat(256 * 1024 + 1));
    ws().push('{not json');
    ws().push('[]');
    ws().push('"str"');
    ws().push(serverEvent('a'.repeat(129)));
    ws().push({ ...serverEvent('1'), payload: [] });
    ws().push({ ...serverEvent('2'), payload: 'x' });
    ws().push({ ...serverEvent('3'), channel: 7 });
    ws().push({ type: 'event', channel: 'project:p1', event_id: '4', payload: {} });
    ws().push({ ...serverEvent(''), event_id: '' });
    ws().onmessage?.({ data: new ArrayBuffer(2) } as MessageEvent);
    expect(events).toHaveLength(0);
    expect(client.droppedEvents).toBe(11);
  });

  it('accepts the ticket envelope {id, channel, type, payload}', () => {
    connectOpen();
    client.subscribe('project:p1', (e) => events.push(e));
    ws().push({ id: 'z1', channel: 'project:p1', type: 'issue.moved', payload: { a: 1 } });
    expect(events[0]).toEqual({ id: 'z1', channel: 'project:p1', type: 'issue.moved', payload: { a: 1 } });
  });

  it('accepts event id at the 128 char boundary', () => {
    connectOpen();
    client.subscribe('project:p1', (e) => events.push(e));
    ws().push(serverEvent('a'.repeat(128)));
    expect(events).toHaveLength(1);
  });

  it('evicts the oldest id after 1001 distinct ids (LRU capacity 1000)', () => {
    connectOpen();
    client.subscribe('project:p1', (e) => events.push(e));
    for (let i = 1; i <= DEDUP_CAPACITY + 1; i += 1) {
      ws().push(serverEvent(`id${String(i)}`));
    }
    expect(events).toHaveLength(1001);
    ws().push(serverEvent('id1'));
    expect(events).toHaveLength(1002);
    ws().push(serverEvent('id1000'));
    expect(events).toHaveLength(1002);
  });

  it('answers ping with pong and ignores acks, errors and draining notices', () => {
    connectOpen();
    ws().push({ type: 'ping' });
    ws().push({ type: 'subscribe_ack', req_id: 'c1', channels: [] });
    ws().push({ type: 'subscribe_error', req_id: 'c1', channel: 'x', code: 'NOT_FOUND' });
    ws().push({ type: 'server.draining', retry_ms: 1000 });
    expect(ws().frames()).toEqual([{ op: 'pong' }]);
    expect(client.droppedEvents).toBe(0);
  });

  it('emits channel.revoked, removes the subscription and handles resync_required', () => {
    connectOpen();
    client.subscribe('issue:i1', (e) => events.push(e));
    const global: RealtimeEvent[] = [];
    client.onEvent((e) => global.push(e));
    ws().push({ type: 'channel.revoked', channel: 'issue:i1' });
    ws().push({ type: 'channel.revoked' });
    ws().push({ type: 'resync_required', latest_event_id: '12' });
    ws().push({ type: 'resync_required' });
    expect(events.map((e) => e.type)).toEqual(['channel.revoked']);
    expect(global.map((e) => e.type)).toEqual(['channel.revoked', 'channel.revoked', 'resync_required', 'resync_required']);
    expect(global[2]?.id).toBe('resync:12');
    expect(global[3]?.id).toBe('resync:');
  });

  it('uses the SSE event name when the frame has no type, and ignores non-string SSE data', () => {
    client.subscribe('project:p1', (e) => events.push(e));
    connectOpen();
    failWs(3);
    sse().emit('resync_required', { latest_event_id: '3' });
    sse().emit('message', { id: 'm1', channel: 'project:p1', topic: 'issue.updated', payload: {} });
    sse().listeners.get('issue.updated')?.({ data: 5, type: 'issue.updated' } as unknown as Event);
    expect(events.map((e) => e.id)).toEqual(['m1']);
  });

  it('isolates failures of listeners by letting them propagate to the caller only once', () => {
    connectOpen();
    client.subscribe('project:p1', (e) => events.push(e));
    client.onEvent(() => undefined);
    ws().push(serverEvent('1'));
    expect(events).toHaveLength(1);
  });

  it('close() clears every timer and is idempotent', () => {
    client.subscribe('project:p1', () => undefined);
    connectOpen();
    ws().fail();
    client.close();
    expect(vi.getTimerCount()).toBe(0);
    client.close();
    expect(client.state).toBe('closed');
    const socket = ws();
    vi.runOnlyPendingTimers();
    expect(ws()).toBe(socket);
  });

  it('close() during SSE fallback clears the probe interval and closes the stream', () => {
    connectOpen();
    failWs(3);
    const source = sse();
    client.close();
    expect(source.closed).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('a late ws close after close() does not schedule reconnects', () => {
    connectOpen();
    const socket = ws();
    client.close();
    socket.fail();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('connect() clears a pending reconnect timer', () => {
    client.connect();
    ws().fail();
    expect(vi.getTimerCount()).toBe(1);
    client.connect();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('a reconnect timer firing after close() does nothing', () => {
    client.connect();
    ws().fail();
    const count = FakeWebSocket.instances.length;
    client.state = 'closed';
    vi.runOnlyPendingTimers();
    expect(FakeWebSocket.instances.length).toBe(count);
  });

  it('probe is skipped when not in fallback or already probing', () => {
    connectOpen();
    failWs(3);
    vi.advanceTimersByTime(60000);
    const count = FakeWebSocket.instances.length;
    vi.advanceTimersByTime(60000);
    expect(FakeWebSocket.instances.length).toBe(count);
  });
});

describe('useRealtime', () => {
  beforeEach(() => {
    vi.stubGlobal('WebSocket', FakeWebSocket);
    FakeWebSocket.instances = [];
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('subscribes for the component lifetime and skips a null channel', () => {
    const client = new RealtimeClient();
    const handler = vi.fn();
    const { rerender, unmount } = renderHook(({ channel }) => { useRealtime(client, channel, handler); }, {
      initialProps: { channel: null as string | null },
    });
    rerender({ channel: 'issue:i1' });
    const spy = vi.spyOn(client, 'subscribe');
    rerender({ channel: 'issue:i2' });
    expect(spy).toHaveBeenCalledWith('issue:i2', handler);
    unmount();
  });
});

describe('bindQueryInvalidation', () => {
  function setup() {
    const client = new RealtimeClient();
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();
    const off = bindQueryInvalidation(client, queryClient);
    const ctx = client as unknown as { emit: (e: RealtimeEvent, dedupe: boolean) => void };
    return { invalidate, off, send: (e: RealtimeEvent) => { ctx.emit(e, false); } };
  }

  it('invalidates the issue and project issue lists on issue.updated', () => {
    const { invalidate, send } = setup();
    send({ id: '1', channel: 'project:p', type: 'issue.updated', payload: { key: 'KAN-1', project_key: 'KAN' } });
    expect(invalidate).toHaveBeenCalledTimes(2);
    expect(invalidate.mock.calls[0]?.[0]).toEqual({ queryKey: ['issue', 'KAN-1'] });
    const predicate = (invalidate.mock.calls[1]?.[0] as unknown as { predicate: (q: { queryKey: unknown[] }) => boolean }).predicate;
    expect(predicate({ queryKey: ['issues', 'KAN', {}] })).toBe(true);
    expect(predicate({ queryKey: ['issues', 'OTHER', {}] })).toBe(false);
    expect(predicate({ queryKey: ['issue', 'KAN'] })).toBe(false);
  });

  it('invalidates every issues list when the project is unknown and tolerates a missing key', () => {
    const { invalidate, send } = setup();
    send({ id: '2', channel: 'c', type: 'issue.updated', payload: { n: 1 } });
    expect(invalidate).toHaveBeenCalledTimes(1);
    const predicate = (invalidate.mock.calls[0]?.[0] as unknown as { predicate: (q: { queryKey: unknown[] }) => boolean }).predicate;
    expect(predicate({ queryKey: ['issues', 'ANY'] })).toBe(true);
  });

  it('reads issue_key / issueKey aliases and ignores non-string fields', () => {
    const { invalidate, send } = setup();
    send({ id: '3', channel: 'c', type: 'issue.updated', payload: { issue_key: 'A-1' } });
    send({ id: '4', channel: 'c', type: 'issue.updated', payload: { issueKey: 'A-2', key: 5 } });
    expect(invalidate.mock.calls.filter((c) => (c[0] as { queryKey?: unknown }).queryKey !== undefined)).toHaveLength(2);
  });

  it('invalidates everything on resync_required and ignores other types', () => {
    const { invalidate, send } = setup();
    send({ id: 'r', channel: '*', type: 'resync_required', payload: {} });
    expect(invalidate).toHaveBeenCalledWith();
    invalidate.mockClear();
    send({ id: 'x', channel: 'c', type: 'comment.created', payload: {} });
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('invalidates issue and activity on comment events when issueKey is present', () => {
    const { invalidate, send } = setup();
    send({ id: 'c1', channel: 'issue:KAN-5', type: 'comment.created', payload: { issue_key: 'KAN-5' } });
    expect(invalidate).toHaveBeenCalledTimes(2);
    expect(invalidate.mock.calls[0]?.[0]).toEqual({ queryKey: ['issue', 'KAN-5'] });
    const predicate = (invalidate.mock.calls[1]?.[0] as unknown as { predicate: (q: { queryKey: unknown[] }) => boolean }).predicate;
    expect(predicate({ queryKey: ['activity', 'KAN-5'] })).toBe(true);
    expect(predicate({ queryKey: ['activity', 'KAN-99'] })).toBe(false);
  });

  it('invalidates stickies and docs on sticky lifecycle events', () => {
    const { invalidate, send } = setup();
    send({ id: 's1', channel: 'project:KAN', type: 'sticky.created', payload: { project_key: 'KAN' } });
    expect(invalidate).toHaveBeenCalledTimes(1);
    const predicate1 = (invalidate.mock.calls[0]?.[0] as unknown as { predicate: (q: { queryKey: unknown[] }) => boolean }).predicate;
    expect(predicate1({ queryKey: ['stickies', 'KAN'] })).toBe(true);
    expect(predicate1({ queryKey: ['stickies', 'OTHER'] })).toBe(false);

    invalidate.mockClear();
    send({ id: 's2', channel: 'project:KAN', type: 'sticky.promoted', payload: { project_key: 'KAN' } });
    expect(invalidate).toHaveBeenCalledTimes(2);
    const predicateDocs = (invalidate.mock.calls[1]?.[0] as unknown as { predicate: (q: { queryKey: unknown[] }) => boolean }).predicate;
    expect(predicateDocs({ queryKey: ['docs', 'sub', 'KAN'] })).toBe(true);
    expect(predicateDocs({ queryKey: ['docs', 'sub', 'OTHER'] })).toBe(false);
  });

  it('invalidates issue and issues list on gate.updated and issue lifecycle events', () => {
    const { invalidate, send } = setup();
    send({ id: 'g1', channel: 'project:KAN', type: 'gate.updated', payload: { key: 'KAN-10', project_key: 'KAN' } });
    expect(invalidate).toHaveBeenCalledTimes(2);
    expect(invalidate.mock.calls[0]?.[0]).toEqual({ queryKey: ['issue', 'KAN-10'] });

    invalidate.mockClear();
    send({ id: 'i1', channel: 'project:KAN', type: 'issue.transitioned', payload: { key: 'KAN-10', project_key: 'KAN' } });
    expect(invalidate).toHaveBeenCalledTimes(2);
    expect(invalidate.mock.calls[0]?.[0]).toEqual({ queryKey: ['issue', 'KAN-10'] });
  });

  it('unbinds', () => {
    const { invalidate, off, send } = setup();
    off();
    send({ id: '5', channel: 'c', type: 'issue.updated', payload: {} });
    expect(invalidate).not.toHaveBeenCalled();
  });
});
