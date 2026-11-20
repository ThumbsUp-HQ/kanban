/**
 * Resilient realtime client: WebSocket with SSE `Last-Event-ID` fallback (KB-P3-16, KB-P3-33).
 *
 * Wire contract (server: kanban/api/ws.py, kanban/api/sse.py):
 *   client -> server: `{op:'subscribe', req_id, channels, last_event_id?}`, `{op:'unsubscribe', ...}`, `{op:'pong'}`
 *   server -> client: `{type:'event', topic, channel, event_id, object_id, payload}` plus control frames
 *   (`subscribe_ack`, `subscribe_error`, `channel.revoked`, `resync_required`, `server.draining`, `ping`).
 * The ticket envelope `{id, channel, type, payload}` is accepted as well.
 * Failure modes: invalid/oversize events are dropped and counted in `droppedEvents`; never eval.
 */

import { useEffect } from 'react';
import type { QueryClient } from '@tanstack/react-query';
import { qk } from './queryKeys.ts';
import type { RealtimeState } from './RealtimeStatus.tsx';

export interface RealtimeEvent {
  id: string;
  channel: string;
  type: string;
  payload: Record<string, unknown>;
}

export type RealtimeEventHandler = (evt: RealtimeEvent) => void;
export type StateChangeHandler = (state: RealtimeState) => void;

export const MAX_EVENT_BYTES = 256 * 1024;
export const MAX_EVENT_ID_LENGTH = 128;
export const DEDUP_CAPACITY = 1000;
export const WS_FAILURES_BEFORE_SSE = 3;
export const WS_PROBE_INTERVAL_MS = 60000;
const MAX_BACKOFF_MS = 15000;
const BASE_BACKOFF_MS = 500;

/** SSE delivers server events under their topic name; EventSource needs explicit listeners. */
const SSE_EVENT_NAMES: readonly string[] = [
  'message',
  'resync_required',
  'channel.revoked',
  'server.draining',
  'issue.created',
  'issue.updated',
  'issue.moved',
  'issue.deleted',
  'comment.created',
  'comment.updated',
  'comment.deleted',
  'gate.updated',
];

function wsUrl(customPath = '/ws'): string {
  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${window.location.host}${customPath}`;
}

function sseUrl(channels: readonly string[]): string {
  const url = new URL('/sse', window.location.origin);
  url.searchParams.set('channels', channels.join(','));
  return url.toString();
}

/** Full-jitter delay: random(0, min(15000, 500 * 2^attempt)). */
export function backoffDelay(attempt: number, random: () => number): number {
  const cap = Math.min(MAX_BACKOFF_MS, BASE_BACKOFF_MS * 2 ** attempt);
  return Math.floor(random() * cap);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export interface RealtimeSessionState {
  authenticated?: boolean;
  mfa_pending?: boolean;
  [key: string]: unknown;
}

export interface RealtimeClientOptions {
  random?: () => number;
  wsPath?: string;
  session?: RealtimeSessionState | null;
}

export class RealtimeClient {
  state: RealtimeState = 'closed';
  droppedEvents = 0;
  lastEventId: string | undefined;

  private ws: WebSocket | null = null;
  private probe: WebSocket | null = null;
  private sse: EventSource | null = null;
  private session: RealtimeSessionState | null = null;
  private attempt = 0;
  private failures = 0;
  private reqCounter = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private probeTimer: ReturnType<typeof setInterval> | null = null;
  private readonly subscriptions = new Map<string, Set<RealtimeEventHandler>>();
  private readonly stateListeners = new Set<StateChangeHandler>();
  private readonly eventListeners = new Set<RealtimeEventHandler>();
  private readonly seen = new Set<string>();
  private readonly random: () => number;
  readonly wsPath: string;

  constructor(options: RealtimeClientOptions = {}) {
    this.random = options.random ?? Math.random;
    this.wsPath = options.wsPath ?? '/ws';
    if (options.session !== undefined) {
      this.session = options.session;
    }
  }

  setSession(session: RealtimeSessionState | null): void {
    const prevAllowed = this.isSessionAllowed();
    this.session = session;
    const nextAllowed = this.isSessionAllowed();

    if (!nextAllowed && prevAllowed) {
      this.close();
    }
  }

  getSession(): RealtimeSessionState | null {
    return this.session;
  }

  isSessionAllowed(): boolean {
    if (this.session === null) {
      return true;
    }
    return this.session.authenticated === true && this.session.mfa_pending !== true;
  }

  onStateChange(cb: StateChangeHandler): () => void {
    this.stateListeners.add(cb);
    return () => {
      this.stateListeners.delete(cb);
    };
  }

  /** Receives every accepted event regardless of channel (used by cache invalidation). */
  onEvent(cb: RealtimeEventHandler): () => void {
    this.eventListeners.add(cb);
    return () => {
      this.eventListeners.delete(cb);
    };
  }

  connect(): void {
    if (!this.isSessionAllowed()) {
      return;
    }
    this.clearTimers();
    this.setState('connecting');
    this.openWebSocket();
  }

  close(): void {
    this.setState('closed');
    this.clearTimers();
    this.closeProbe();
    this.closeSse();
    if (this.ws) {
      const socket = this.ws;
      this.ws = null;
      socket.close();
    }
  }

  subscribe(channel: string, handler: RealtimeEventHandler): () => void {
    let handlers = this.subscriptions.get(channel);
    if (!handlers) {
      handlers = new Set();
      this.subscriptions.set(channel, handlers);
      this.sendSubscribe([channel]);
    }
    handlers.add(handler);
    return () => {
      const current = this.subscriptions.get(channel);
      if (!current) {
        return;
      }
      current.delete(handler);
      if (current.size === 0) {
        this.subscriptions.delete(channel);
        this.sendFrame({ op: 'unsubscribe', req_id: this.nextReqId(), channels: [channel] });
      }
    };
  }

  private setState(next: RealtimeState): void {
    if (this.state === next) {
      return;
    }
    this.state = next;
    for (const listener of this.stateListeners) {
      listener(next);
    }
  }

  private nextReqId(): string {
    this.reqCounter += 1;
    return `c${String(this.reqCounter)}`;
  }

  private sendFrame(frame: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(frame));
    }
  }

  private sendSubscribe(channels: string[]): void {
    if (channels.length === 0) {
      return;
    }
    const frame: Record<string, unknown> = {
      op: 'subscribe',
      req_id: this.nextReqId(),
      channels,
    };
    if (this.lastEventId !== undefined) {
      frame.last_event_id = this.lastEventId;
    }
    this.sendFrame(frame);
  }

  private attachSocket(socket: WebSocket): void {
    socket.onmessage = (event: MessageEvent) => {
      if (typeof event.data === 'string') {
        this.handleFrame(event.data);
      } else {
        this.droppedEvents += 1;
      }
    };
    socket.onclose = (event?: CloseEvent) => {
      if (this.ws !== socket) {
        return;
      }
      this.ws = null;
      if (this.state !== 'closed') {
        if (event?.code === 4401 || event?.code === 4403 || event?.code === 1008 || !this.isSessionAllowed()) {
          this.close();
          return;
        }
        this.onWsFailure();
      }
    };
  }

  private openWebSocket(): void {
    /* v8 ignore next 3 */
    if (typeof window === 'undefined' || typeof WebSocket === 'undefined') {
      return;
    }
    const socket = new WebSocket(wsUrl(this.wsPath));
    this.ws = socket;
    this.attachSocket(socket);
    socket.onopen = () => {
      this.attempt = 0;
      this.failures = 0;
      this.closeSse();
      this.setState('open');
      this.sendSubscribe([...this.subscriptions.keys()]);
    };
  }

  private onWsFailure(): void {
    if (!this.isSessionAllowed()) {
      this.close();
      return;
    }
    this.failures += 1;
    if (this.failures >= WS_FAILURES_BEFORE_SSE) {
      this.startSseFallback();
      return;
    }
    this.setState('reconnecting');
    const delay = backoffDelay(this.attempt, this.random);
    this.attempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.state !== 'closed' && this.isSessionAllowed()) {
        this.openWebSocket();
      }
    }, delay);
  }

  private startSseFallback(): void {
    /* v8 ignore next 3 */
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') {
      return;
    }
    this.setState('sse-fallback');
    this.closeSse();
    const source = new EventSource(sseUrl([...this.subscriptions.keys()]));
    this.sse = source;
    const listener = (event: Event): void => {
      const message = event as MessageEvent;
      if (typeof message.data === 'string') {
        this.handleFrame(message.data, message.type);
      }
    };
    for (const name of SSE_EVENT_NAMES) {
      source.addEventListener(name, listener);
    }
    this.probeTimer ??= setInterval(() => {
      this.probeWebSocket();
    }, WS_PROBE_INTERVAL_MS);
  }

  private probeWebSocket(): void {
    if (this.state !== 'sse-fallback' || this.probe) {
      return;
    }
    const socket = new WebSocket(wsUrl(this.wsPath));
    this.probe = socket;
    socket.onopen = () => {
      this.probe = null;
      this.closeSse();
      this.attempt = 0;
      this.failures = 0;
      this.ws = socket;
      this.attachSocket(socket);
      this.setState('open');
      this.sendSubscribe([...this.subscriptions.keys()]);
    };
    socket.onclose = () => {
      if (this.probe === socket) {
        this.probe = null;
      }
    };
  }

  private closeProbe(): void {
    if (this.probe) {
      const socket = this.probe;
      this.probe = null;
      socket.close();
    }
  }

  private closeSse(): void {
    if (this.sse) {
      this.sse.close();
      this.sse = null;
    }
    if (this.probeTimer !== null) {
      clearInterval(this.probeTimer);
      this.probeTimer = null;
    }
  }

  private clearTimers(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.probeTimer !== null) {
      clearInterval(this.probeTimer);
      this.probeTimer = null;
    }
  }

  private remember(id: string): boolean {
    if (this.seen.has(id)) {
      return false;
    }
    this.seen.add(id);
    if (this.seen.size > DEDUP_CAPACITY) {
      const oldest = this.seen.values().next();
      if (!oldest.done) {
        this.seen.delete(oldest.value);
      }
    }
    return true;
  }

  private handleFrame(raw: string, sseName?: string): void {
    if (raw.length > MAX_EVENT_BYTES) {
      this.droppedEvents += 1;
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      this.droppedEvents += 1;
      return;
    }
    const obj = asRecord(parsed);
    if (!obj) {
      this.droppedEvents += 1;
      return;
    }
    const kind = typeof obj.type === 'string' ? obj.type : sseName;
    switch (kind) {
      case 'ping':
        this.sendFrame({ op: 'pong' });
        return;
      case 'subscribe_ack':
      case 'subscribe_error':
      case 'server.draining':
        return;
      case 'resync_required':
        this.emit({ id: `resync:${typeof obj.latest_event_id === 'string' ? obj.latest_event_id : ''}`, channel: '*', type: kind, payload: {} }, false);
        return;
      case 'channel.revoked': {
        const channel = typeof obj.channel === 'string' ? obj.channel : '';
        this.emit({ id: `revoked:${channel}`, channel, type: kind, payload: {} }, false);
        this.subscriptions.delete(channel);
        return;
      }
      default:
        this.handleDomainEvent(obj);
    }
  }

  private handleDomainEvent(obj: Record<string, unknown>): void {
    const rawId = obj.id ?? obj.event_id;
    const topic = obj.topic ?? obj.type;
    const payload = asRecord(obj.payload);
    if (
      typeof rawId !== 'string' ||
      rawId.length === 0 ||
      rawId.length > MAX_EVENT_ID_LENGTH ||
      typeof obj.channel !== 'string' ||
      typeof topic !== 'string' ||
      topic === 'event' ||
      payload === null
    ) {
      this.droppedEvents += 1;
      return;
    }
    this.lastEventId = rawId;
    this.emit({ id: rawId, channel: obj.channel, type: topic, payload }, true);
  }

  private emit(event: RealtimeEvent, dedupe: boolean): void {
    if (dedupe && !this.remember(event.id)) {
      return;
    }
    for (const listener of this.eventListeners) {
      listener(event);
    }
    const handlers = this.subscriptions.get(event.channel);
    if (handlers) {
      for (const handler of handlers) {
        handler(event);
      }
    }
  }

  /** Testability hook: simulate a realtime event directly without network. */
  simulateEvent(event: RealtimeEvent): void {
    this.emit(event, true);
  }

  /** Testability hook: simulate receiving a raw WebSocket frame string. */
  simulateFrame(raw: string, sseName?: string): void {
    this.handleFrame(raw, sseName);
  }

  /** Testability hook: reset internal state, seen dedup set, and timers for tests. */
  resetForTesting(): void {
    this.close();
    this.seen.clear();
    this.droppedEvents = 0;
    this.attempt = 0;
    this.failures = 0;
    this.lastEventId = undefined;
  }
}

let defaultClient: RealtimeClient | null = null;

export function getRealtimeClient(): RealtimeClient {
  defaultClient ??= new RealtimeClient();
  return defaultClient;
}

export function setRealtimeClient(client: RealtimeClient | null): void {
  defaultClient = client;
}

/** Subscribes to `channel` for the component lifetime. */
export function useRealtime(
  client: RealtimeClient,
  channel: string | null,
  handler: RealtimeEventHandler,
): void {
  useEffect(() => {
    if (channel === null) {
      return undefined;
    }
    return client.subscribe(channel, handler);
  }, [client, channel, handler]);
}

function stringField(payload: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === 'string') {
      return value;
    }
  }
  return undefined;
}

/**
 * Maps incoming realtime events to active TanStack Query cache invalidations.
 * Handles issue, comment, sticky, gate, and resync events in < 1s.
 */
export function bindQueryInvalidation(client: RealtimeClient, queryClient: QueryClient): () => void {
  return client.onEvent((event) => {
    if (event.type === 'resync_required') {
      void queryClient.invalidateQueries();
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('kb:issue-updated', { detail: event }));
      }
      return;
    }

    // 1. Issue lifecycle & mutation events
    if (
      event.type === 'issue.created' ||
      event.type === 'issue.updated' ||
      event.type === 'issue.moved' ||
      event.type === 'issue.transitioned' ||
      event.type === 'issue.deleted'
    ) {
      const issueKey = stringField(event.payload, 'key', 'issue_key', 'issueKey');
      const projectKey = stringField(event.payload, 'project_key', 'projectKey');

      if (issueKey !== undefined) {
        void queryClient.invalidateQueries({ queryKey: qk.issue(issueKey) });
      }
      void queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey[0] === 'issues' && (projectKey === undefined || query.queryKey[1] === projectKey),
      });
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('kb:issue-updated', { detail: event }));
      }
      return;
    }

    // 2. Comment lifecycle events
    if (
      event.type === 'comment.created' ||
      event.type === 'comment.updated' ||
      event.type === 'comment.deleted'
    ) {
      const issueKey = stringField(event.payload, 'issue_key', 'issueKey', 'key');
      if (issueKey !== undefined) {
        void queryClient.invalidateQueries({ queryKey: qk.issue(issueKey) });
        void queryClient.invalidateQueries({
          predicate: (query) =>
            query.queryKey[0] === 'activity' && (query.queryKey[1] === issueKey || query.queryKey[1] === undefined),
        });
      }
      return;
    }

    // 3. Project Stickies lifecycle events
    if (
      event.type === 'sticky.created' ||
      event.type === 'sticky.updated' ||
      event.type === 'sticky.promoted' ||
      event.type === 'sticky.deleted'
    ) {
      const projectKey = stringField(event.payload, 'project_key', 'projectKey');
      void queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey[0] === 'stickies' &&
          (projectKey === undefined || query.queryKey[1] === projectKey || query.queryKey[1] === 'workspace'),
      });
      if (event.type === 'sticky.promoted') {
        void queryClient.invalidateQueries({
          predicate: (query) =>
            query.queryKey[0] === 'docs' && (projectKey === undefined || query.queryKey[2] === projectKey),
        });
      }
      return;
    }

    // 4. Gate status events
    if (event.type === 'gate.updated') {
      const issueKey = stringField(event.payload, 'issue_key', 'issueKey', 'key');
      const projectKey = stringField(event.payload, 'project_key', 'projectKey');
      if (issueKey !== undefined) {
        void queryClient.invalidateQueries({ queryKey: qk.issue(issueKey) });
      }
      void queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey[0] === 'issues' && (projectKey === undefined || query.queryKey[1] === projectKey),
      });
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('kb:issue-updated', { detail: event }));
      }
      return;
    }
  });
}
