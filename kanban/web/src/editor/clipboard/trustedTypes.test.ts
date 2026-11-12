/**
 * Unit Tests for Trusted Types Policies (KB-P3-46, S5.4).
 */

import { describe, it, expect } from 'vitest';
import { ensureTrustedTypesPolicies } from './trustedTypes';

describe('trustedTypes', () => {
  it('handles environment without window.trustedTypes gracefully', () => {
    const result = ensureTrustedTypesPolicies();
    expect(result).toHaveProperty('hasTrustedTypes');
  });

  it('registers and retrieves policies when window.trustedTypes is available', () => {
    const createdPolicies = new Map<string, unknown>();

    const fakeTrustedTypes = {
      createPolicy: (name: string, rules: { createHTML?: (s: string) => string }) => {
        const policy = {
          name,
          createHTML: rules.createHTML ?? ((s: string) => s),
        };
        createdPolicies.set(name, policy);
        return policy;
      },
    };

    const originalTT = (window as unknown as { trustedTypes?: unknown }).trustedTypes;
    try {
      (window as unknown as { trustedTypes: unknown }).trustedTypes = fakeTrustedTypes;
      const res = ensureTrustedTypesPolicies();
      expect(res.hasTrustedTypes).toBe(true);
      expect(res.sanitizerPolicy).not.toBeNull();
      expect(res.sanitizerPolicy?.name).toBe('kanban-sanitizer');
      expect(res.sanitizerPolicy?.createHTML('<b>test</b>')).toBe('<b>test</b>');
      expect(res.dompurifyPolicy?.createHTML('<i>clean</i>')).toBe('<i>clean</i>');
    } finally {
      (window as unknown as { trustedTypes?: unknown }).trustedTypes = originalTT;
    }
  });

  it('handles existing duplicate policy error gracefully', () => {
    const fakeTrustedTypes = {
      createPolicy: (name: string) => {
        throw new Error(`Policy ${name} already registered`);
      },
    };

    const originalTT = (window as unknown as { trustedTypes?: unknown }).trustedTypes;
    try {
      (window as unknown as { trustedTypes: unknown }).trustedTypes = fakeTrustedTypes;
      const res = ensureTrustedTypesPolicies();
      expect(res.hasTrustedTypes).toBe(true);
    } finally {
      (window as unknown as { trustedTypes?: unknown }).trustedTypes = originalTT;
    }
  });
});
