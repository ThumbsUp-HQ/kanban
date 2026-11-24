// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { ApiProblem } from '../../api/problem';

export interface ErrorHelpEntry {
  code: string;
  title: string;
  summary: string;
  remediation: string;
  docHref: string;
  isAal2StepUp: boolean;
}

export const ERROR_HELP_CATALOG: Record<string, ErrorHelpEntry> = {
  AAL2_STALE: {
    code: 'AAL2_STALE',
    title: '2FA Verification Window Expired (AAL2 Stale)',
    summary:
      'Authenticator Assurance Level 2 (AAL2) is our 15-minute (900-second) Multi-Factor Authentication security window for administrative and sensitive actions. The numbers (e.g. 64520s > 900s) mean your last 2FA check was 64,520 seconds (~18 hours) ago, exceeding the 900-second (15-minute) limit.',
    remediation:
      'Click "Verify 2FA Now" to re-verify with your Passkey or TOTP Authenticator app, or re-authenticate from Personal Settings.',
    docHref: '/docs/multi-card-authentication-studio#aal2-step-up',
    isAal2StepUp: true,
  },
  AAL2_REQUIRED: {
    code: 'AAL2_REQUIRED',
    title: 'Multi-Factor Authentication Required (AAL2)',
    summary:
      'This administrative or security-sensitive action requires an active Authenticator Assurance Level 2 (2FA) session verified within the last 15 minutes (900s).',
    remediation:
      'Click "Verify 2FA Now" to complete Passkey or TOTP step-up verification.',
    docHref: '/docs/multi-card-authentication-studio#aal2-step-up',
    isAal2StepUp: true,
  },
  MFA_ENROLLMENT_REQUIRED: {
    code: 'MFA_ENROLLMENT_REQUIRED',
    title: 'MFA Enrollment Required',
    summary:
      'Administrators must enroll a Passkey (WebAuthn) or TOTP Authenticator app before accessing administrative studios.',
    remediation:
      'Navigate to Personal Settings to enroll your first security key or authenticator app.',
    docHref: '/docs/multi-card-authentication-studio#mfa-enrollment',
    isAal2StepUp: false,
  },
  AUTHENTICATION_REQUIRED: {
    code: 'AUTHENTICATION_REQUIRED',
    title: 'Authentication Required',
    summary: 'Your session is missing or has expired.',
    remediation: 'Please log in again to renew your session credentials.',
    docHref: '/docs/multi-card-authentication-studio',
    isAal2StepUp: false,
  },
  FORBIDDEN: {
    code: 'FORBIDDEN',
    title: 'Access Denied (Forbidden)',
    summary: 'Your account role or token lacks permission for this operation.',
    remediation:
      'Request role elevation or appropriate permissions from your workspace administrator.',
    docHref: '/docs/role-and-permission-matrix',
    isAal2StepUp: false,
  },
  INSUFFICIENT_SCOPE: {
    code: 'INSUFFICIENT_SCOPE',
    title: 'Insufficient Scope Tier',
    summary: 'The active token or session lacks the required OAuth/MCP scope tier.',
    remediation:
      'Verify the API key or OAuth grant has been granted the required scope tier in MCP Access Studio.',
    docHref: '/docs/three-surface-mcp-server-architecture#scope-tiers',
    isAal2StepUp: false,
  },
  INSUFFICIENT_CAPABILITY: {
    code: 'INSUFFICIENT_CAPABILITY',
    title: 'Insufficient Capability',
    summary:
      'Your effective role or capability bitmask does not include the required capability.',
    remediation:
      'Contact your project administrator to update your project role assignments.',
    docHref: '/docs/role-and-permission-matrix',
    isAal2StepUp: false,
  },
  KEY_SCOPE_VIOLATION: {
    code: 'KEY_SCOPE_VIOLATION',
    title: 'MCP Key Scope Violation',
    summary:
      'The MCP access key is restricted to a narrower project or workspace scope.',
    remediation:
      'Mint a new access key with broader scope in MCP Access Studio or use a key authorized for this target project.',
    docHref: '/docs/three-surface-mcp-server-architecture#scope-tiers',
    isAal2StepUp: false,
  },
  CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED: {
    code: 'CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED',
    title: 'Cross-Scope Read-Taint Guard',
    summary:
      'Session read-taint guard requires explicit confirmation before writing across project boundaries.',
    remediation:
      'Acknowledge the cross-scope data flow or clear session read-taint high water mark before retrying.',
    docHref:
      '/docs/zero-trust-security-and-access-visibility#read-taint-high-water-mark',
    isAal2StepUp: false,
  },
  MCP_TAINT_BLOCKED: {
    code: 'MCP_TAINT_BLOCKED',
    title: 'MCP Read-Taint Blocked',
    summary:
      'Cross-project write blocked by session read-taint exfiltration protection.',
    remediation:
      'Reset the agent session or use isolated sub-agent workspaces for cross-project queries.',
    docHref:
      '/docs/zero-trust-security-and-access-visibility#read-taint-high-water-mark',
    isAal2StepUp: false,
  },
  LOCKOUT_PREVENTED: {
    code: 'LOCKOUT_PREVENTED',
    title: 'Lockout Prevention Safeguard',
    summary:
      'Cannot disable or delete the last active administrator authentication card.',
    remediation:
      'Ensure at least one other active admin auth card or account exists before removing this card.',
    docHref: '/docs/multi-card-authentication-studio#lockout-prevention',
    isAal2StepUp: false,
  },
  HARD_WIP_LIMIT_EXCEEDED: {
    code: 'HARD_WIP_LIMIT_EXCEEDED',
    title: 'Work-In-Progress (WIP) Limit Exceeded',
    summary: 'The target column has reached its Hard Work-In-Progress (WIP) limit.',
    remediation:
      'Move existing work items to Done or another column, or adjust column WIP limits in Project Settings.',
    docHref: '/docs/enterprise-whitespace-and-kanban-board#wip-limits',
    isAal2StepUp: false,
  },
  GATE_TIMEOUT: {
    code: 'GATE_TIMEOUT',
    title: 'Workflow Transition Gate Timeout',
    summary:
      'A synchronous workflow validator or transition gate exceeded its execution timeout.',
    remediation:
      'Check external webhook or custom validator script latency and retry.',
    docHref: '/docs/scripted-workflows-and-transition-helpers',
    isAal2StepUp: false,
  },
  SCRIPT_RECURSION_BLOCKED: {
    code: 'SCRIPT_RECURSION_BLOCKED',
    title: 'Script Recursion Guard Triggered',
    summary:
      'Re-entrant script call to test-execute or dry-run was blocked by recursion guard.',
    remediation:
      'Ensure custom fields or workflow scripts do not invoke nested dry-run execution.',
    docHref: '/docs/custom-scripts-and-json-security-architecture',
    isAal2StepUp: false,
  },
  INVALID_UTF8_SURROGATE: {
    code: 'INVALID_UTF8_SURROGATE',
    title: 'Invalid UTF-8 Surrogate Code Point',
    summary:
      'Payload contains invalid UTF-16 lone surrogate code points (0xD800-0xDFFF).',
    remediation:
      'Cleanse raw pasted text or binary strings of lone surrogates before submitting.',
    docHref: '/docs/canonical-markdown-and-safe-media-pipeline',
    isAal2StepUp: false,
  },
  JSON_DEPTH_EXCEEDED: {
    code: 'JSON_DEPTH_EXCEEDED',
    title: 'JSON Nesting Depth Limit Exceeded',
    summary: 'JSON payload nesting depth exceeds the 32-level security limit.',
    remediation:
      'Flatten nested structures before submitting custom field values or API bodies.',
    docHref: '/docs/custom-scripts-and-json-security-architecture',
    isAal2StepUp: false,
  },
  JSON_KEYS_EXCEEDED: {
    code: 'JSON_KEYS_EXCEEDED',
    title: 'JSON Key Count Limit Exceeded',
    summary: 'JSON payload object key count exceeds the 5,000-key limit.',
    remediation:
      'Split large JSON dictionary payloads into smaller batches or files.',
    docHref: '/docs/custom-scripts-and-json-security-architecture',
    isAal2StepUp: false,
  },
  PAYLOAD_TOO_LARGE: {
    code: 'PAYLOAD_TOO_LARGE',
    title: 'Payload Too Large',
    summary: 'Request body exceeds the maximum allowed payload size limit.',
    remediation:
      'Reduce attachment size or payload body content before retrying.',
    docHref: '/docs/custom-scripts-and-json-security-architecture',
    isAal2StepUp: false,
  },
  BLAST_RADIUS_CHANGED: {
    code: 'BLAST_RADIUS_CHANGED',
    title: 'Entity Blast Radius Changed',
    summary:
      'The entity graph changed since the deletion preview was computed.',
    remediation:
      'Re-run preview to inspect updated blast radius and confirm deletion.',
    docHref: '/docs/production-promotion-and-backup-runbook',
    isAal2StepUp: false,
  },
  MANIFEST_MISMATCH: {
    code: 'MANIFEST_MISMATCH',
    title: 'Definition Manifest Mismatch',
    summary:
      'The custom field manifest SHA-256 changed since opening.',
    remediation:
      'Reload the definition to review recent changes before approving.',
    docHref: '/docs/admin-custom-scripted-fields-and-sandbox',
    isAal2StepUp: false,
  },
  VALIDATION_FAILED: {
    code: 'VALIDATION_FAILED',
    title: 'Request Validation Error',
    summary:
      'One or more request parameters or form fields failed schema validation.',
    remediation:
      'Check the highlighted fields for format errors, missing values, or range violations.',
    docHref: '/docs/rest-api-architecture-and-openapi-guide',
    isAal2StepUp: false,
  },
  VALIDATION_ERROR: {
    code: 'VALIDATION_ERROR',
    title: 'Validation Error',
    summary: 'Request payload failed validation constraints.',
    remediation:
      'Check parameter types and constraints and correct offending values.',
    docHref: '/docs/rest-api-architecture-and-openapi-guide',
    isAal2StepUp: false,
  },
  RATE_LIMITED: {
    code: 'RATE_LIMITED',
    title: 'Rate Limit Exceeded',
    summary: 'Too many requests in the current window.',
    remediation: 'Please wait a moment before retrying the operation.',
    docHref: '/docs/zero-trust-security-and-access-visibility',
    isAal2StepUp: false,
  },
  NOT_FOUND: {
    code: 'NOT_FOUND',
    title: 'Resource Not Found',
    summary:
      'The requested resource was not found or you do not have access to view it.',
    remediation:
      'Verify the URL or identifier. If the object exists, ensure your account has read access.',
    docHref: '/docs/zero-trust-security-and-access-visibility',
    isAal2StepUp: false,
  },
};

export const DEFAULT_ERROR_HELP: ErrorHelpEntry = {
  code: 'UNKNOWN_ERROR',
  title: 'Application Diagnostic Error',
  summary: 'Review the error details and open the platform documentation for troubleshooting steps.',
  remediation:
    'Consult platform logs in Admin Diagnostics Studio or contact your system administrator.',
  docHref: '/docs/admin-diagnostics-and-link-inspector-studio',
  isAal2StepUp: false,
};

function catalogEntry(key: string): ErrorHelpEntry {
  return ERROR_HELP_CATALOG[key] ?? DEFAULT_ERROR_HELP;
}

function extractMessage(errorOrMessage: unknown): string {
  if (typeof errorOrMessage === 'string') {
    return errorOrMessage;
  }
  if (errorOrMessage instanceof ApiProblem) {
    return errorOrMessage.message || (errorOrMessage.detail ?? '');
  }
  if (errorOrMessage instanceof Error) {
    return errorOrMessage.message;
  }
  if (errorOrMessage !== null && typeof errorOrMessage === 'object') {
    const obj = errorOrMessage as Record<string, unknown>;
    if (typeof obj.message === 'string') return obj.message;
    if (typeof obj.detail === 'string') return obj.detail;
    if (typeof obj.title === 'string') return obj.title;
  }
  return '';
}

function extractCode(errorOrMessage: unknown, explicitCode?: string): string | undefined {
  if (explicitCode && explicitCode.trim() !== '') {
    return explicitCode.trim();
  }
  if (errorOrMessage instanceof ApiProblem) {
    return errorOrMessage.code;
  }
  if (errorOrMessage !== null && typeof errorOrMessage === 'object') {
    const obj = errorOrMessage as Record<string, unknown>;
    if (typeof obj.code === 'string' && obj.code.trim() !== '') {
      return obj.code.trim();
    }
  }
  return undefined;
}

/**
 * Universal Error Help Resolver (KB-UX-ERROR-DOCS-AAL2, KAN-393).
 * Maps every error message or ApiProblem into human-readable guidance,
 * documentation links, and AAL2 step-up actions.
 */
export function resolveErrorHelp(
  errorOrMessage: unknown,
  explicitCode?: string,
): ErrorHelpEntry {
  const code = extractCode(errorOrMessage, explicitCode);
  const msg = extractMessage(errorOrMessage);

  // 1. Direct Catalog Match by Code
  if (code && Object.prototype.hasOwnProperty.call(ERROR_HELP_CATALOG, code)) {
    const entry = ERROR_HELP_CATALOG[code];
    if (entry) {
      let customSummary = entry.summary;
      let customDocHref = entry.docHref;

      if (errorOrMessage instanceof ApiProblem) {
        if (errorOrMessage.helpSummary) {
          customSummary = errorOrMessage.helpSummary;
        }
        if (errorOrMessage.docHref) {
          customDocHref = errorOrMessage.docHref;
        }
      }

      return {
        code,
        title: entry.title,
        summary: customSummary,
        remediation: entry.remediation,
        docHref: customDocHref,
        isAal2StepUp: entry.isAal2StepUp,
      };
    }
  }

  // 2. Pattern Matching on Code or Message
  const lowerMsg = `${code ?? ''} ${msg}`.toLowerCase();

  // AAL2 Stale pattern
  if (
    code === 'AAL2_STALE' ||
    /aal2 verification is stale|aal2.*stale|900s\b/i.test(lowerMsg)
  ) {
    const entry = catalogEntry('AAL2_STALE');
    return {
      code: 'AAL2_STALE',
      title: entry.title,
      summary:
        errorOrMessage instanceof ApiProblem && errorOrMessage.helpSummary
          ? errorOrMessage.helpSummary
          : entry.summary,
      remediation: entry.remediation,
      docHref:
        errorOrMessage instanceof ApiProblem && errorOrMessage.docHref
          ? errorOrMessage.docHref
          : entry.docHref,
      isAal2StepUp: true,
    };
  }

  // AAL2 Required pattern
  if (
    code === 'AAL2_REQUIRED' ||
    /aal2.*required|multi-factor.*required|second-factor.*required|admin.*2fa/i.test(lowerMsg)
  ) {
    const entry = catalogEntry('AAL2_REQUIRED');
    return {
      code: 'AAL2_REQUIRED',
      title: entry.title,
      summary:
        errorOrMessage instanceof ApiProblem && errorOrMessage.helpSummary
          ? errorOrMessage.helpSummary
          : entry.summary,
      remediation: entry.remediation,
      docHref:
        errorOrMessage instanceof ApiProblem && errorOrMessage.docHref
          ? errorOrMessage.docHref
          : entry.docHref,
      isAal2StepUp: true,
    };
  }

  // MFA Enrollment Required pattern
  if (/mfa.*enroll|passkey.*enroll|totp.*enroll/i.test(lowerMsg)) {
    return catalogEntry('MFA_ENROLLMENT_REQUIRED');
  }

  // Authentication Required pattern (401)
  if (/authentication.*required|session.*missing|unauthorized|\b401\b/i.test(lowerMsg)) {
    return catalogEntry('AUTHENTICATION_REQUIRED');
  }

  // Forbidden / Permissions pattern (403)
  if (/forbidden|permission.*denied|lacks.*permission|access.*denied|\b403\b/i.test(lowerMsg)) {
    return catalogEntry('FORBIDDEN');
  }

  // Not Found pattern (404)
  if (/not.*found|\b404\b/i.test(lowerMsg)) {
    return catalogEntry('NOT_FOUND');
  }

  // MCP / Scope pattern
  if (/scope.*violation|insufficient.*scope|scope.*tier/i.test(lowerMsg)) {
    return catalogEntry('INSUFFICIENT_SCOPE');
  }

  // Taint Guard pattern
  if (/taint.*guard|read-taint|cross-scope.*taint/i.test(lowerMsg)) {
    return catalogEntry('CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED');
  }

  // Lockout prevention pattern
  if (/lockout.*prevented|last.*active.*admin/i.test(lowerMsg)) {
    return catalogEntry('LOCKOUT_PREVENTED');
  }

  // WIP limit pattern
  if (/wip.*limit/i.test(lowerMsg)) {
    return catalogEntry('HARD_WIP_LIMIT_EXCEEDED');
  }

  // Gate timeout pattern
  if (/gate.*timeout|workflow.*timeout|validator.*timeout/i.test(lowerMsg)) {
    return catalogEntry('GATE_TIMEOUT');
  }

  // Script recursion / JSON depth pattern
  if (/recursion|re-entrant/i.test(lowerMsg)) {
    return catalogEntry('SCRIPT_RECURSION_BLOCKED');
  }

  if (/utf-16|surrogate|0xd800/i.test(lowerMsg)) {
    return catalogEntry('INVALID_UTF8_SURROGATE');
  }

  if (/json.*depth|nesting.*depth/i.test(lowerMsg)) {
    return catalogEntry('JSON_DEPTH_EXCEEDED');
  }

  if (/json.*key|key.*count/i.test(lowerMsg)) {
    return catalogEntry('JSON_KEYS_EXCEEDED');
  }

  if (/payload.*large|entity too large|\b413\b/i.test(lowerMsg)) {
    return catalogEntry('PAYLOAD_TOO_LARGE');
  }

  if (/blast.*radius/i.test(lowerMsg)) {
    return catalogEntry('BLAST_RADIUS_CHANGED');
  }

  if (/manifest.*mismatch|definition changed/i.test(lowerMsg)) {
    return catalogEntry('MANIFEST_MISMATCH');
  }

  // Validation pattern
  if (/validation.*failed|validation.*error|schema validation|\b422\b/i.test(lowerMsg)) {
    return catalogEntry('VALIDATION_FAILED');
  }

  // Rate limit pattern (429)
  if (/rate.*limit|too many requests|\b429\b/i.test(lowerMsg)) {
    return catalogEntry('RATE_LIMITED');
  }

  // Check ApiProblem docHref / helpSummary fallback
  let docHref = DEFAULT_ERROR_HELP.docHref;
  let summary = DEFAULT_ERROR_HELP.summary;

  if (errorOrMessage instanceof ApiProblem) {
    if (errorOrMessage.docHref) {
      docHref = errorOrMessage.docHref;
    }
    if (errorOrMessage.helpSummary) {
      summary = errorOrMessage.helpSummary;
    }
  }

  return {
    code: code ?? 'UNKNOWN_ERROR',
    title: DEFAULT_ERROR_HELP.title,
    summary,
    remediation: DEFAULT_ERROR_HELP.remediation,
    docHref,
    isAal2StepUp: false,
  };
}
