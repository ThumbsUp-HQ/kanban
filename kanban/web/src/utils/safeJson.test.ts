/**
 * Unit tests for safeJsonParse (KB-P3-AUDIT-11).
 */

import { describe, it, expect } from 'vitest';
import { safeJsonParse } from './safeJson';

describe('safeJsonParse', () => {
  it('parses valid JSON primitives and arrays', () => {
    expect(safeJsonParse('123')).toBe(123);
    expect(safeJsonParse('"hello"')).toBe('hello');
    expect(safeJsonParse('true')).toBe(true);
    expect(safeJsonParse('false')).toBe(false);
    expect(safeJsonParse('null')).toBeNull();
    expect(safeJsonParse('[1, 2, 3]')).toEqual([1, 2, 3]);
  });

  it('parses normal JSON objects cleanly', () => {
    const raw = '{"name": "test", "count": 42, "nested": {"active": true}}';
    const result = safeJsonParse<Record<string, unknown>>(raw);
    expect(result).toEqual({
      name: 'test',
      count: 42,
      nested: { active: true },
    });
  });

  it('strips __proto__ keys from JSON objects', () => {
    const raw = '{"title": "safe", "__proto__": {"polluted": true}}';
    const result = safeJsonParse<Record<string, unknown>>(raw);
    expect(result.title).toBe('safe');
    expect(Object.prototype.hasOwnProperty.call(result, '__proto__')).toBe(false);
    expect((Object.prototype as unknown as Record<string, unknown>).polluted).toBeUndefined();
  });

  it('strips constructor and prototype keys from JSON objects', () => {
    const raw = '{"valid": 1, "constructor": "bad", "prototype": {"hack": true}}';
    const result = safeJsonParse<Record<string, unknown>>(raw);
    expect(result.valid).toBe(1);
    expect(Object.prototype.hasOwnProperty.call(result, 'constructor')).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(result, 'prototype')).toBe(false);
    expect(result.constructor).toBe(Object);
  });

  it('recursively strips pollution keys from nested objects and arrays', () => {
    const raw = JSON.stringify({
      users: [
        { id: 1, name: 'Alice', __proto__: { admin: true } },
        { id: 2, name: 'Bob', constructor: 'evil', prototype: 'bad' },
      ],
      meta: {
        deeper: {
          __proto__: { backdoor: true },
          ok: 'yes',
        },
      },
    });

    const result = safeJsonParse<{
      users: Record<string, unknown>[];
      meta: { deeper: Record<string, unknown> };
    }>(raw);

    const user0 = result.users[0];
    const user1 = result.users[1];
    expect(user0).toBeDefined();
    expect(user1).toBeDefined();
    if (user0 && user1) {
      expect(user0.name).toBe('Alice');
      expect(Object.prototype.hasOwnProperty.call(user0, '__proto__')).toBe(false);
      expect(Object.prototype.hasOwnProperty.call(user1, 'constructor')).toBe(false);
      expect(Object.prototype.hasOwnProperty.call(user1, 'prototype')).toBe(false);
      expect(user1.constructor).toBe(Object);
    }
    expect(result.meta.deeper.ok).toBe('yes');
    expect(Object.prototype.hasOwnProperty.call(result.meta.deeper, '__proto__')).toBe(false);
  });

  it('throws SyntaxError for malformed JSON text', () => {
    expect(() => safeJsonParse('{invalid')).toThrow(SyntaxError);
  });
});
