/**
 * Worker environment compatibility shim for elkjs and beautiful-mermaid (KB-P3-47).
 *
 * elkjs bundled library checks `if (typeof document === 'undefined' && typeof self !== 'undefined')`
 * to detect whether it is executing as a dedicated worker script for ELK. If true, it binds to
 * self.onmessage and does not export its in-memory worker dispatcher, causing `new ELKBundled()`
 * to throw `TypeError: o is not a constructor`.
 *
 * In addition, beautiful-mermaid attempts to temporarily delete and restore `globalThis.self`
 * during synchronous layout, which throws in strict mode if `self` is a read-only accessor
 * on WorkerGlobalScope.
 *
 * This shim must execute before beautiful-mermaid is imported. It provides a minimal dummy document
 * object and ensures `self` has a setter or writable descriptor so the in-memory layout engine
 * executes cleanly inside our dedicated Web Worker.
 */

export function installElkWorkerShim(targetGlobal: unknown = globalThis): void {
  const g = targetGlobal as Record<string, unknown>;

  if (typeof g.document === 'undefined') {
    try {
      const docShim = {
        createElement: () => ({}),
      };
      g.document = docShim;
      docShim.createElement();
    } catch {
      // Non-fatal if target is not extensible
    }
  }

  function noopSetter(_val: unknown): void {
    if (_val !== null) {
      return;
    }
  }

  try {
    const currentSelf = g.self ?? g;
    Object.defineProperty(g, 'self', {
      get: () => currentSelf,
      set: noopSetter,
      configurable: true,
    });
  } catch {
    try {
      const proto = Object.getPrototypeOf(g) as Record<string, unknown> | null;
      if (proto && 'self' in proto) {
        const currentSelf = proto.self ?? g;
        Object.defineProperty(proto, 'self', {
          get: () => currentSelf,
          set: noopSetter,
          configurable: true,
        });
      }
    } catch {
      // Non-fatal if runtime disallows property reconfiguration
    }
  }
}

installElkWorkerShim();
