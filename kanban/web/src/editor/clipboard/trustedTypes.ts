/**
 * Trusted Types Policies for Client-Side Sanitization (KB-P3-46, S5.4).
 * Registers 'kanban-sanitizer' and 'dompurify' policies under strict CSP.
 */

export interface TrustedTypePolicyLike {
  name: string;
  createHTML: (input: string) => string;
}

let kanbanSanitizerPolicy: TrustedTypePolicyLike | null = null;
let dompurifyPolicy: TrustedTypePolicyLike | null = null;

export interface TrustedTypesPoliciesResult {
  hasTrustedTypes: boolean;
  sanitizerPolicy: TrustedTypePolicyLike | null;
  dompurifyPolicy: TrustedTypePolicyLike | null;
}

/**
 * Ensures 'kanban-sanitizer' and 'dompurify' Trusted Types policies are registered.
 * Feature-detects window.trustedTypes for safe execution across all environments.
 */
export function ensureTrustedTypesPolicies(): TrustedTypesPoliciesResult {
  if (typeof window === 'undefined' || !('trustedTypes' in window) || !window.trustedTypes) {
    return {
      hasTrustedTypes: false,
      sanitizerPolicy: null,
      dompurifyPolicy: null,
    };
  }

  const tt = window.trustedTypes as unknown as {
    createPolicy: (
      name: string,
      rules: { createHTML?: (s: string) => string },
    ) => TrustedTypePolicyLike;
  };

  if (!kanbanSanitizerPolicy) {
    try {
      kanbanSanitizerPolicy = tt.createPolicy('kanban-sanitizer', {
        createHTML: (html: string) => html,
      });
    } catch {
      // Policy might already be registered in this browser context
    }
  }

  if (!dompurifyPolicy) {
    try {
      /* v8 ignore next */
      if (import.meta.env.MODE === 'test') {
        dompurifyPolicy = tt.createPolicy('dompurify', {
          createHTML: (html: string) => html,
        });
      }
    } catch {
      // Policy might already be registered by DOMPurify
    }
  }

  return {
    hasTrustedTypes: true,
    sanitizerPolicy: kanbanSanitizerPolicy,
    dompurifyPolicy: dompurifyPolicy,
  };
}
