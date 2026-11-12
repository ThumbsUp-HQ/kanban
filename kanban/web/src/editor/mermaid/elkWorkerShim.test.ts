/**
 * Unit Tests for elkWorkerShim (KB-P3-47).
 */

import { describe, it, expect } from 'vitest';
import { installElkWorkerShim } from './elkWorkerShim';

describe('installElkWorkerShim', () => {
  it('installs minimal document shim when document is undefined', () => {
    const mockGlobal: Record<string, unknown> = {};
    installElkWorkerShim(mockGlobal);

    expect(mockGlobal.document).toBeDefined();
    const doc = mockGlobal.document as { createElement: () => unknown };
    expect(typeof doc.createElement).toBe('function');
    expect(doc.createElement()).toEqual({});
    expect(mockGlobal.self).toBe(mockGlobal);
  });

  it('preserves existing document if already present', () => {
    const existingDoc = { custom: true };
    const mockGlobal: Record<string, unknown> = {
      document: existingDoc,
    };
    installElkWorkerShim(mockGlobal);

    expect(mockGlobal.document).toBe(existingDoc);
  });

  it('falls back to prototype when Object.defineProperty throws on target', () => {
    const proto: Record<string, unknown> = { self: 'proto-self' };
    const target = Object.create(proto) as Record<string, unknown>;

    // Freeze target to make Object.defineProperty throw
    Object.freeze(target);

    installElkWorkerShim(target);
    expect(proto.self).toBe('proto-self');
  });

  it('handles completely non-configurable targets without throwing', () => {
    const proto: Record<string, unknown> = { self: 'proto-self' };
    Object.freeze(proto);
    const target = Object.create(proto) as Record<string, unknown>;
    Object.freeze(target);

    expect(() => {
      installElkWorkerShim(target);
    }).not.toThrow();
  });
});
