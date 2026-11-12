/**
 * Mermaid Worker Client & Dispatcher (KB-P3-47, S5.3).
 * Manages dedicated Web Worker lifecycle with 1,500ms watchdog timer,
 * LRU cache of 64 rendered SVG strings, in-flight request deduplication,
 * and lazy worker respawn after termination.
 */

import {
  MERMAID_WATCHDOG_MS,
  sanitizeAndValidateMermaid,
} from './mermaidFirewall';
import {
  DEFAULT_LIGHT_THEME_TOKENS,
  getMermaidThemeKey,
  type MermaidThemeTokens,
} from './mermaidTheme';
import { toTrustedScriptUrl } from '../media/safeSvg';
import type {
  MermaidWorkerRequest,
  MermaidWorkerResponse,
} from './mermaid.worker';

let isWorkerWrapperInstalled = false;

export function _resetWorkerWrapperForTesting(): void {
  isWorkerWrapperInstalled = false;
}

export function _installTrustedWorkerWrapperForTesting(): void {
  installTrustedWorkerWrapper();
}

function installTrustedWorkerWrapper(): void {
  if (isWorkerWrapperInstalled || typeof window === 'undefined') {
    return;
  }
  const win = window as unknown as { trustedTypes?: unknown; Worker?: typeof Worker };
  if (!win.trustedTypes || typeof win.Worker === 'undefined') {
    return;
  }
  const OriginalWorker = win.Worker;
  const PatchedWorker = function (
    this: Worker,
    scriptURL: string | URL,
    options?: WorkerOptions,
  ): Worker {
    const trusted = toTrustedScriptUrl(scriptURL);
    return new OriginalWorker(trusted, {
      ...options,
      type: 'module',
    });
  } as unknown as typeof Worker;

  PatchedWorker.prototype = OriginalWorker.prototype;
  win.Worker = PatchedWorker;
  isWorkerWrapperInstalled = true;
}

export const MAX_MERMAID_CACHE_ENTRIES = 64;

export interface MermaidClientSuccess {
  readonly ok: true;
  readonly svg: string;
  readonly cached?: boolean;
}

export interface MermaidClientFailure {
  readonly ok: false;
  readonly code: string;
  readonly message: string;
}

export type MermaidClientResult = MermaidClientSuccess | MermaidClientFailure;

interface PendingJob {
  readonly resolve: (result: MermaidClientResult) => void;
  readonly timer: ReturnType<typeof setTimeout>;
  readonly cacheKey: string;
}

export type WorkerFactory = () => Worker;

function defaultWorkerFactory(): Worker {
  installTrustedWorkerWrapper();
  return new Worker(new URL('./mermaid.worker.ts', import.meta.url), {
    type: 'module',
  });
}

export class MermaidWorkerClient {
  private worker: Worker | null = null;
  private readonly workerFactory: WorkerFactory;
  private readonly watchdogMs: number;
  private readonly cache = new Map<string, string>();
  private readonly inFlight = new Map<string, Promise<MermaidClientResult>>();
  private readonly pendingJobs = new Map<string, PendingJob>();
  private requestIdCounter = 0;

  public constructor(options?: {
    workerFactory?: WorkerFactory;
    watchdogMs?: number;
  }) {
    this.workerFactory = options?.workerFactory ?? defaultWorkerFactory;
    this.watchdogMs = options?.watchdogMs ?? MERMAID_WATCHDOG_MS;
  }

  /**
   * Lazily spawns or returns the active Web Worker instance.
   */
  private getOrCreateWorker(): Worker {
    if (!this.worker) {
      this.worker = this.workerFactory();
      this.worker.onmessage = (event: MessageEvent<MermaidWorkerResponse>): void => {
        this.handleWorkerMessage(event.data);
      };
      this.worker.onerror = (err: ErrorEvent): void => {
        this.handleWorkerError(err);
      };
    }
    return this.worker;
  }

  private handleWorkerMessage(data: MermaidWorkerResponse): void {
    const job = this.pendingJobs.get(data.requestId);
    if (!job) {
      return;
    }

    clearTimeout(job.timer);
    this.pendingJobs.delete(data.requestId);
    this.inFlight.delete(job.cacheKey);

    if (data.ok) {
      this.addToCache(job.cacheKey, data.svg);
      job.resolve({ ok: true, svg: data.svg });
    } else {
      job.resolve({ ok: false, code: data.code, message: data.message });
    }
  }

  private handleWorkerError(err: ErrorEvent): void {
    const message = err.message || 'Worker encounter an unhandled execution error';
    this.terminateAndClearAll('WORKER_ERROR', message);
  }

  private handleWatchdogTimeout(requestId: string): void {
    const job = this.pendingJobs.get(requestId);
    if (!job) {
      return;
    }

    // Immediately terminate the unresponsive worker per S5.3
    if (this.worker) {
      try {
        this.worker.terminate();
      } catch {
        // Ignored
      }
      this.worker = null;
    }

    clearTimeout(job.timer);
    this.pendingJobs.delete(requestId);
    this.inFlight.delete(job.cacheKey);

    job.resolve({
      ok: false,
      code: 'RENDER_TIMEOUT',
      message: `Diagram render exceeded ${String(this.watchdogMs)}ms render budget.`,
    });

    // Also cancel any other pending jobs on this terminated worker
    if (this.pendingJobs.size > 0) {
      this.terminateAndClearAll(
        'WORKER_TERMINATED',
        'Worker was terminated due to a concurrent job timeout.',
      );
    }
  }

  private terminateAndClearAll(code: string, message: string): void {
    if (this.worker) {
      try {
        this.worker.terminate();
      } catch {
        // Ignored
      }
      this.worker = null;
    }

    for (const [id, job] of this.pendingJobs.entries()) {
      clearTimeout(job.timer);
      this.inFlight.delete(job.cacheKey);
      job.resolve({ ok: false, code, message });
      this.pendingJobs.delete(id);
    }
  }

  private addToCache(key: string, svg: string): void {
    if (this.cache.has(key)) {
      this.cache.delete(key);
    } else if (this.cache.size >= MAX_MERMAID_CACHE_ENTRIES) {
      for (const firstKey of this.cache.keys()) {
        this.cache.delete(firstKey);
        break;
      }
    }
    this.cache.set(key, svg);
  }

  /**
   * Main entry to render Mermaid source text with live theme tokens.
   */
  public async render(
    rawSource: string,
    theme: MermaidThemeTokens = DEFAULT_LIGHT_THEME_TOKENS,
  ): Promise<MermaidClientResult> {
    // 1. Main-thread fast fail via firewall
    const firewall = sanitizeAndValidateMermaid(rawSource);
    if (!firewall.ok) {
      return {
        ok: false,
        code: firewall.code,
        message: firewall.message,
      };
    }

    const cacheKey = `${firewall.sanitizedSource}:::${getMermaidThemeKey(theme)}`;

    // 2. Check LRU cache
    const cachedSvg = this.cache.get(cacheKey);
    if (cachedSvg !== undefined) {
      // Refresh recency
      this.cache.delete(cacheKey);
      this.cache.set(cacheKey, cachedSvg);
      return { ok: true, svg: cachedSvg, cached: true };
    }

    // 3. Deduplicate concurrent identical requests
    const existing = this.inFlight.get(cacheKey);
    if (existing) {
      return existing;
    }

    // 4. Dispatch to worker with watchdog
    const promise = new Promise<MermaidClientResult>((resolve) => {
      this.requestIdCounter += 1;
      const requestId = `mermaid_${String(Date.now())}_${String(this.requestIdCounter)}`;

      const timer = setTimeout(() => {
        this.handleWatchdogTimeout(requestId);
      }, this.watchdogMs);

      this.pendingJobs.set(requestId, {
        resolve,
        timer,
        cacheKey,
      });

      try {
        const worker = this.getOrCreateWorker();
        const request: MermaidWorkerRequest = {
          requestId,
          source: firewall.sanitizedSource,
          theme,
        };
        worker.postMessage(request);
      } catch (err: unknown) {
        clearTimeout(timer);
        this.pendingJobs.delete(requestId);
        this.inFlight.delete(cacheKey);
        const message = err instanceof Error ? err.message : String(err);
        resolve({
          ok: false,
          code: 'WORKER_SPAWN_FAILED',
          message: `Failed to dispatch job to Web Worker: ${message}`,
        });
      }
    });

    this.inFlight.set(cacheKey, promise);
    return promise;
  }

  /**
   * Clears cached SVGs and in-flight promises.
   */
  public clearCache(): void {
    this.cache.clear();
  }

  /**
   * Destroys the worker and cleans up all resources.
   */
  public destroy(): void {
    this.terminateAndClearAll('CLIENT_DESTROYED', 'Mermaid client was destroyed.');
    this.cache.clear();
    this.inFlight.clear();
  }

  /**
   * Returns current cache size for testing inspection.
   */
  public getCacheSize(): number {
    return this.cache.size;
  }
}

export const mermaidClient = new MermaidWorkerClient();
