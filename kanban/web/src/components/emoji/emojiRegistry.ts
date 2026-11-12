/**
 * Typed 21-Emoji Registry for Semantic Status Hints (KB-P3-31, S6.2).
 * Provides immutable emoji metadata, accessible names, domains, and default hint text.
 */

export type EmojiKey =
  | 'access'
  | 'restricted'
  | 'warning'
  | 'airGap'
  | 'priorityUrgent'
  | 'priorityHigh'
  | 'priorityMedium'
  | 'priorityLow'
  | 'agent'
  | 'gatePending'
  | 'gateVetoed'
  | 'gateApproved'
  | 'externalAssignee'
  | 'creatorOverride'
  | 'sparkle'
  | 'sanitized'
  | 'rawMarkdown'
  | 'stickyPromotion'
  | 'brokenLink'
  | 'scriptedField'
  | 'mediaBackdrop';

export interface EmojiEntry {
  readonly glyph: string;
  readonly domain: string;
  readonly ariaLabel: string;
  readonly defaultHint: string;
}

export const EMOJI_REGISTRY: Readonly<Record<EmojiKey, EmojiEntry>> = Object.freeze({
  access: Object.freeze({
    glyph: '🛡️',
    domain: 'Access Transparency (#1)',
    ariaLabel: 'Access and sharing',
    defaultHint:
      'Scope summary (Project: Platform Core) + counts of Users, Groups, 🤖 Agents, and 🔒 Deny rules; click opens full Access Inspector.',
  }),
  restricted: Object.freeze({
    glyph: '🔒',
    domain: 'Restricted ACL Override',
    ariaLabel: 'Restricted access override',
    defaultHint:
      'Lists explicit DENY overrides or private-only visibility boundary compared to the parent project.',
  }),
  warning: Object.freeze({
    glyph: '⚠️',
    domain: 'Standalone / WIP Warning',
    ariaLabel: 'Warning',
    defaultHint:
      'Header: Standalone docker run mode details & volume persistence status. Board lane: Soft/Hard WIP limit threshold details.',
  }),
  airGap: Object.freeze({
    glyph: '📴',
    domain: 'Air-Gap Local-Only Mode',
    ariaLabel: 'Air-gap local-only mode',
    defaultHint:
      'Confirms external LLM/media egress is disabled at socket level; displays active local ollama endpoint.',
  }),
  priorityUrgent: Object.freeze({
    glyph: '🔥',
    domain: 'Priority (Urgent)',
    ariaLabel: 'Priority: Urgent',
    defaultHint:
      'Displays project-customizable priority name, SLA target window, and sort weight (P to change).',
  }),
  priorityHigh: Object.freeze({
    glyph: '⚡',
    domain: 'Priority (High)',
    ariaLabel: 'Priority: High',
    defaultHint:
      'Displays project-customizable priority name, SLA target window, and sort weight (P to change).',
  }),
  priorityMedium: Object.freeze({
    glyph: '🔹',
    domain: 'Priority (Medium)',
    ariaLabel: 'Priority: Medium',
    defaultHint:
      'Displays project-customizable priority name, SLA target window, and sort weight (P to change).',
  }),
  priorityLow: Object.freeze({
    glyph: '💤',
    domain: 'Priority (Low)',
    ariaLabel: 'Priority: Low',
    defaultHint:
      'Displays project-customizable priority name, SLA target window, and sort weight (P to change).',
  }),
  agent: Object.freeze({
    glyph: '🤖',
    domain: 'Autonomous / OBO Agent',
    ariaLabel: 'Autonomous agent',
    defaultHint:
      'Agent name, harness/model (ollama/qwen2.5-coder, cli: agy -p), OBO human delegator, and effective permission intersection.',
  }),
  gatePending: Object.freeze({
    glyph: '⏳🤖',
    domain: 'Transition Gate Pending',
    ariaLabel: 'Agent gate pending',
    defaultHint:
      'Live elapsed timer, active workflow hook name, harness (codex -p / gemini), and read-only repo mount status.',
  }),
  gateVetoed: Object.freeze({
    glyph: '🛑🤖',
    domain: 'Transition Gate Vetoed',
    ariaLabel: 'Agent gate vetoed',
    defaultHint:
      'Vetoing hook/agent name, timestamp, 2-line markdown reason preview, and 1-click jump to full Activity audit comment.',
  }),
  gateApproved: Object.freeze({
    glyph: '✅🤖',
    domain: 'Transition Gate Approved',
    ariaLabel: 'Agent gate approved',
    defaultHint:
      'Approving hook/agent name, execution latency (ms), and cryptographic verdict hash.',
  }),
  externalAssignee: Object.freeze({
    glyph: '🏷️',
    domain: 'External Free-Text Assignee',
    ariaLabel: 'External free-text assignee',
    defaultHint: 'External free-text label - grants zero access and sends zero notifications',
  }),
  creatorOverride: Object.freeze({
    glyph: '🔄',
    domain: 'Creator Admin Override',
    ariaLabel: 'Created by overridden by admin',
    defaultHint:
      'Original creator -> Project Admin who modified Created by, timestamp, and link to immutable CREATOR_OVERRIDDEN ledger row.',
  }),
  sparkle: Object.freeze({
    glyph: '✨',
    domain: 'Sparkle Cursor Completion',
    ariaLabel: 'Sparkle cursor completion',
    defaultHint:
      'Active FIM provider/model, RLS context scope (Project KAN), and shortcut hint (Right-Click or Tab to accept).',
  }),
  sanitized: Object.freeze({
    glyph: '🧼',
    domain: 'Auto-Sanitized / Converted',
    ariaLabel: 'Auto-sanitized and converted',
    defaultHint: 'Converted pasted HTML to clean Markdown - Cmd+Z to paste plain text',
  }),
  rawMarkdown: Object.freeze({
    glyph: '📝',
    domain: 'Raw Markdown Source View',
    ariaLabel: 'Raw markdown source view',
    defaultHint:
      'Indicates raw canonical Markdown source inspection is active (Cmd/Ctrl+Shift+M to toggle).',
  }),
  stickyPromotion: Object.freeze({
    glyph: '💡📄',
    domain: 'Sticky -> Doc Promotion',
    ariaLabel: 'Sticky to doc promotion',
    defaultHint:
      'Explains why the Sticky exceeded complexity heuristics (740 chars, 2 headings) + 1-click Promote to Doc action.',
  }),
  brokenLink: Object.freeze({
    glyph: '🕸️⚠️',
    domain: 'Broken Object Graph Link',
    ariaLabel: 'Broken object graph link',
    defaultHint:
      'Identifies orphaned/ACL-severed link reason code (PERMISSION_SEVERED) + Admin Inspect & Purge shortcut.',
  }),
  scriptedField: Object.freeze({
    glyph: '🧪',
    domain: 'Sandboxed Scripted Field',
    ariaLabel: 'Sandboxed scripted field',
    defaultHint:
      'Execution tier (Wasmtime / nsjail), token scope (PROJECT), principal (INVOKING_USER), and last compute latency.',
  }),
  mediaBackdrop: Object.freeze({
    glyph: '🌓',
    domain: 'Media Contrast Backdrop',
    ariaLabel: 'Media contrast backdrop',
    defaultHint:
      'Toggles Light / Dark / Checkerboard canvas behind transparent .svg or Mermaid diagrams without flipping app theme.',
  }),
});

export const EXTENDED_EMOJI_REGISTRY: Readonly<Record<string, EmojiEntry>> = Object.freeze({
  externalMedia: Object.freeze({
    glyph: '🌐',
    domain: 'External Media Shield',
    ariaLabel: 'Proxied external image',
    defaultHint: 'Proxied anonymously via Kanban Media Shield',
  }),
});

export type ExtendedEmojiKey = EmojiKey | 'externalMedia';
