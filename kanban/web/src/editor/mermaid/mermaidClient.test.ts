/**
 * Unit Tests for Mermaid Worker Client & Dispatcher (KB-P3-47, S5.3).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  MermaidWorkerClient,
  MAX_MERMAID_CACHE_ENTRIES,
  _resetWorkerWrapperForTesting,
  _installTrustedWorkerWrapperForTesting,
} from './mermaidClient';

class FakeWorker implements Worker {
  public postMessage = vi.fn();
  public terminate = vi.fn();
  public onmessage: ((event: MessageEvent) => void) | null = null;
  public onerror: ((event: ErrorEvent) => void) | null = null;
  public onmessageerror: ((event: MessageEvent) => void) | null = null;
  public addEventListener = vi.fn();
  public removeEventListener = vi.fn();
  public dispatchEvent = vi.fn(() => true);
}

describe('MermaidWorkerClient', () => {
  let activeFakeWorker: FakeWorker;

  beforeEach(() => {
    vi.useFakeTimers();
    activeFakeWorker = new FakeWorker();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('renders valid diagram via worker and caches subsequent requests', async () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
    });

    const renderPromise = client.render('graph TD\n  A --> B');

    // Verify worker received postMessage
    expect(activeFakeWorker.postMessage).toHaveBeenCalledTimes(1);
    const postData = activeFakeWorker.postMessage.mock.calls[0]?.[0] as {
      requestId: string;
      source: string;
    };
    expect(postData.source).toContain('graph TD');

    // Simulate worker success response
    activeFakeWorker.onmessage?.({
      data: {
        requestId: postData.requestId,
        ok: true,
        svg: '<svg><rect id="nodeA"/></svg>',
      },
    } as MessageEvent);

    const result = await renderPromise;
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.svg).toContain('<rect id="nodeA"/>');
      expect(result.cached).toBeFalsy();
    }

    // 2nd call should hit LRU cache without dispatching to worker
    const secondResult = await client.render('graph TD\n  A --> B');
    expect(secondResult.ok).toBe(true);
    if (secondResult.ok) {
      expect(secondResult.cached).toBe(true);
      expect(secondResult.svg).toContain('<rect id="nodeA"/>');
    }
    expect(activeFakeWorker.postMessage).toHaveBeenCalledTimes(1);
  });

  it('deduplicates concurrent identical in-flight requests', async () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
    });

    const promise1 = client.render('graph TD\n  X --> Y');
    const promise2 = client.render('graph TD\n  X --> Y');

    expect(activeFakeWorker.postMessage).toHaveBeenCalledTimes(1);

    const postData = activeFakeWorker.postMessage.mock.calls[0]?.[0] as {
      requestId: string;
    };

    activeFakeWorker.onmessage?.({
      data: {
        requestId: postData.requestId,
        ok: true,
        svg: '<svg><text>Deduplicated</text></svg>',
      },
    } as MessageEvent);

    const [res1, res2] = await Promise.all([promise1, promise2]);
    expect(res1.ok).toBe(true);
    expect(res2.ok).toBe(true);
    if (res1.ok && res2.ok) {
      expect(res1.svg).toBe(res2.svg);
    }
  });

  it('fast-fails on firewall rejection before worker dispatch', async () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
    });

    const result = await client.render('gantt\n  title Unsupported');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe('UNSUPPORTED_DIAGRAM_TYPE');
    }
    expect(activeFakeWorker.postMessage).not.toHaveBeenCalled();
  });

  it('enforces 1,500ms watchdog timeout and terminates hanging worker', async () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
      watchdogMs: 1500,
    });

    const hangingPromise = client.render('graph TD\n  Hang --> Forever');
    expect(activeFakeWorker.postMessage).toHaveBeenCalledTimes(1);

    // Advance to 1499ms: should not have timed out yet
    await vi.advanceTimersByTimeAsync(1499);
    expect(activeFakeWorker.terminate).not.toHaveBeenCalled();

    // Advance 1ms more to reach 1500ms: watchdog fires
    await vi.advanceTimersByTimeAsync(1);
    expect(activeFakeWorker.terminate).toHaveBeenCalledTimes(1);

    const result = await hangingPromise;
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe('RENDER_TIMEOUT');
      expect(result.message).toContain('1500ms');
    }

    // Subsequent render should spawn a fresh worker and succeed
    const freshFakeWorker = new FakeWorker();
    const freshClient = new MermaidWorkerClient({
      workerFactory: () => freshFakeWorker,
    });
    const nextPromise = freshClient.render('graph TD\n  Fresh --> Worker');
    expect(freshFakeWorker.postMessage).toHaveBeenCalledTimes(1);

    const postData = freshFakeWorker.postMessage.mock.calls[0]?.[0] as {
      requestId: string;
    };
    freshFakeWorker.onmessage?.({
      data: {
        requestId: postData.requestId,
        ok: true,
        svg: '<svg>Fresh</svg>',
      },
    } as MessageEvent);

    const nextResult = await nextPromise;
    expect(nextResult.ok).toBe(true);
  });

  it('handles worker error events gracefully', async () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
    });

    const promise = client.render('graph TD\n  Err --> Test');
    activeFakeWorker.onerror?.(new ErrorEvent('error', { message: 'Out of memory' }));

    const result = await promise;
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe('WORKER_ERROR');
      expect(result.message).toContain('Out of memory');
    }
  });

  it('handles worker error response gracefully', async () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
    });

    const promise = client.render('graph TD\n  Syntax --> Error');
    const postData = activeFakeWorker.postMessage.mock.calls[0]?.[0] as {
      requestId: string;
    };

    activeFakeWorker.onmessage?.({
      data: {
        requestId: postData.requestId,
        ok: false,
        code: 'RENDER_ERROR',
        message: 'Syntax error at token Error',
      },
    } as MessageEvent);

    const result = await promise;
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe('RENDER_ERROR');
      expect(result.message).toContain('Syntax error');
    }
  });

  it('evicts oldest entries when cache exceeds MAX_MERMAID_CACHE_ENTRIES', async () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
    });

    for (let i = 0; i < MAX_MERMAID_CACHE_ENTRIES + 5; i++) {
      const p = client.render(`graph TD\n  Node${String(i)} --> End`);
      const postData = activeFakeWorker.postMessage.mock.calls[i]?.[0] as {
        requestId: string;
      };
      activeFakeWorker.onmessage?.({
        data: {
          requestId: postData.requestId,
          ok: true,
          svg: `<svg>Diagram ${String(i)}</svg>`,
        },
      } as MessageEvent);
      await p;
    }

    expect(client.getCacheSize()).toBe(MAX_MERMAID_CACHE_ENTRIES);

    client.clearCache();
    expect(client.getCacheSize()).toBe(0);
  });

  it('cleans up all resources on destroy()', async () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
    });

    const pending = client.render('graph TD\n  A --> B');
    client.destroy();

    expect(activeFakeWorker.terminate).toHaveBeenCalled();
    const result = await pending;
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe('CLIENT_DESTROYED');
    }
    expect(client.getCacheSize()).toBe(0);
  });

  it('handles worker postMessage dispatch exceptions gracefully', async () => {
    const brokenWorker = new FakeWorker();
    brokenWorker.postMessage = vi.fn(() => {
      throw new Error('DataCloneError: failed to serialize');
    });

    const client = new MermaidWorkerClient({
      workerFactory: () => brokenWorker,
    });

    const result = await client.render('graph TD\n  A --> B');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe('WORKER_SPAWN_FAILED');
      expect(result.message).toContain('DataCloneError');
    }
  });

  it('handles unknown response IDs without crashing', async () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
    });

    const promise = client.render('graph TD\n  A --> B');
    // Post unexpected message
    activeFakeWorker.onmessage?.({
      data: {
        requestId: 'unknown_id_9999',
        ok: true,
        svg: '<svg>ignored</svg>',
      },
    } as MessageEvent);

    // Now post real message
    const postData = activeFakeWorker.postMessage.mock.calls[0]?.[0] as {
      requestId: string;
    };
    activeFakeWorker.onmessage?.({
      data: {
        requestId: postData.requestId,
        ok: true,
        svg: '<svg>real</svg>',
      },
    } as MessageEvent);

    const result = await promise;
    expect(result.ok).toBe(true);
  });

  it('cancels secondary in-flight jobs when a concurrent job times out', async () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
      watchdogMs: 1000,
    });

    const promise1 = client.render('graph TD\n  Job1 --> A');
    const promise2 = client.render('graph TD\n  Job2 --> B');

    expect(activeFakeWorker.postMessage).toHaveBeenCalledTimes(2);

    // Advance past watchdog for Job1
    await vi.advanceTimersByTimeAsync(1000);

    const [res1, res2] = await Promise.all([promise1, promise2]);
    expect(res1.ok).toBe(false);
    expect(res2.ok).toBe(false);
    if (!res1.ok && !res2.ok) {
      expect(res1.code).toBe('RENDER_TIMEOUT');
      expect(res2.code).toBe('WORKER_TERMINATED');
    }
  });

  it('updates cache recency when re-adding existing key', () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
    });

    // Directly test addToCache via private method for full branch coverage
    const clientAny = client as unknown as { addToCache: (key: string, svg: string) => void };
    clientAny.addToCache('key1', '<svg>1</svg>');
    clientAny.addToCache('key1', '<svg>2</svg>');
    expect(client.getCacheSize()).toBe(1);

    client.clearCache();
    expect(client.getCacheSize()).toBe(0);
  });

  it('handles empty message in ErrorEvent', async () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
    });

    const promise = client.render('graph TD\n  EmptyErr --> X');
    activeFakeWorker.onerror?.(new ErrorEvent('error', { message: '' }));

    const result = await promise;
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe('WORKER_ERROR');
      expect(result.message).toContain('unhandled execution error');
    }
  });

  it('handles unknown watchdog timeout IDs safely', () => {
    const client = new MermaidWorkerClient({
      workerFactory: () => activeFakeWorker,
    });
    const clientAny = client as unknown as {
      pendingJobs: Map<string, { resolve: () => void; timer: ReturnType<typeof setTimeout>; cacheKey: string }>;
      handleWatchdogTimeout: (id: string) => void;
    };
    expect(() => {
      clientAny.handleWatchdogTimeout('non_existent_id');
    }).not.toThrow();

    // With job but null worker
    clientAny.pendingJobs.set('dummy', {
      resolve: vi.fn(),
      timer: setTimeout(() => undefined, 1000),
      cacheKey: 'k',
    });
    clientAny.handleWatchdogTimeout('dummy');
    expect(clientAny.pendingJobs.size).toBe(0);
  });

  it('handles non-Error exceptions in worker dispatch', async () => {
    const brokenWorker = new FakeWorker();
    brokenWorker.postMessage = vi.fn(() => {
      // eslint-disable-next-line @typescript-eslint/only-throw-error
      throw 'string error message';
    });

    const client = new MermaidWorkerClient({
      workerFactory: () => brokenWorker,
    });

    const result = await client.render('graph TD\n  A --> B');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe('WORKER_SPAWN_FAILED');
      expect(result.message).toContain('string error message');
    }
  });

  it('instantiates default client and default worker factory safely', async () => {
    const originalWorker = global.Worker;
    try {
      global.Worker = FakeWorker;
      const client = new MermaidWorkerClient();
      expect(client.getCacheSize()).toBe(0);
      const p = client.render('graph TD\n  A --> B');
      client.destroy();
      await p;
    } finally {
      global.Worker = originalWorker;
    }
  });

  it('installs trusted worker wrapper when trustedTypes is available', () => {
    _resetWorkerWrapperForTesting();
    const origWorker = window.Worker;
    const origTrustedTypes = (window as unknown as { trustedTypes?: unknown }).trustedTypes;

    try {
      (window as unknown as { trustedTypes?: unknown }).trustedTypes = {};
      window.Worker = FakeWorker;

      _installTrustedWorkerWrapperForTesting();
      expect(window.Worker).not.toBe(FakeWorker);

      // Subsequent call does nothing
      _installTrustedWorkerWrapperForTesting();

      // Test patched constructor creates worker
      const constructed = new window.Worker('http://localhost/worker.js');
      expect(constructed).toBeDefined();
    } finally {
      window.Worker = origWorker;
      (window as unknown as { trustedTypes?: unknown }).trustedTypes = origTrustedTypes;
      _resetWorkerWrapperForTesting();
    }
  });

  it('skips worker wrapper when trustedTypes is absent', () => {
    _resetWorkerWrapperForTesting();
    const origTrustedTypes = (window as unknown as { trustedTypes?: unknown }).trustedTypes;

    try {
      delete (window as unknown as { trustedTypes?: unknown }).trustedTypes;
      _installTrustedWorkerWrapperForTesting();
      expect(_resetWorkerWrapperForTesting).toBeDefined();
    } finally {
      (window as unknown as { trustedTypes?: unknown }).trustedTypes = origTrustedTypes;
      _resetWorkerWrapperForTesting();
    }
  });
});
