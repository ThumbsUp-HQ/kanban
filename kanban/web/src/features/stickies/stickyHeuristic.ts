/**
 * Sticky Complexity Heuristics and Snooze Engine (KB-P3-51, S8.1, S8.2).
 *
 * Evaluates 5 structural triggers outside fenced code blocks, evaluates >= 1.5x integer
 * snooze thresholds, and determines whether to recommend promotion to permanent Docs.
 */

export type StickyColorToken =
  | 'amber'
  | 'mint'
  | 'sky'
  | 'lavender'
  | 'coral'
  | 'slate'
  | 'yellow'
  | 'pink'
  | 'blue'
  | 'green'
  | 'orange'
  | 'purple';

export const STICKY_COLOR_TOKENS: readonly StickyColorToken[] = [
  'amber',
  'mint',
  'sky',
  'lavender',
  'coral',
  'slate',
] as const;

export const STICKY_COLOR_ALIASES: Record<string, StickyColorToken> = {
  yellow: 'amber',
  green: 'mint',
  blue: 'sky',
  purple: 'lavender',
  orange: 'coral',
  pink: 'coral',
};

export const STICKY_IDLE_DEBOUNCE_MS = 1000;

export interface StickyComplexityEvaluation {
  exceeded: boolean;
  reasons: string[];
  charLength: number;
  shouldShowBanner: boolean;
}

const MAX_CHAR_LENGTH = 600;
const MAX_LINE_COUNT = 10;
const MIN_HEADINGS = 2;
const MAX_CODE_FENCE_LINES = 6;
const MIN_OUTBOUND_LINKS = 3;

const FENCE_START_RE = /^ {0,3}(`{3,}|~{3,})(.*)$/;
const HEADING_RE = /^ {0,3}#{1,6}\s+\S/;
const GFM_DELIMITER_RE = /^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$/;
const MD_LINK_RE = /\[[^\]]+\]\([^\s)]+\)/g;
const AUTOLINK_RE = /<(?:https?|mailto):[^>]+>/g;
const ISSUE_REF_RE = /\[([A-Za-z0-9_]+-\d+)\]/g;
const SVG_REF_RE = /\.svg(?:[?#\s"')\]>]|$)/i;

interface BlockAnalysis {
  headingCount: number;
  outboundLinkCount: number;
  hasGfmTable: boolean;
  hasMermaid: boolean;
  hasSvg: boolean;
  hasLargeCodeFence: boolean;
}

function countOutboundLinks(textLine: string): number {
  let count = 0;

  // 1. Standard markdown links [label](url)
  const mdMatches = textLine.match(MD_LINK_RE);
  if (mdMatches) {
    count += mdMatches.length;
  }
  const lineNoMd = textLine.replace(MD_LINK_RE, ' ');

  // 2. Autolinks <https://...> or <mailto:...>
  const autoMatches = lineNoMd.match(AUTOLINK_RE);
  if (autoMatches) {
    count += autoMatches.length;
  }
  const lineNoAuto = lineNoMd.replace(AUTOLINK_RE, ' ');

  // 3. Issue references [KEY-123]
  const issueMatches = lineNoAuto.match(ISSUE_REF_RE);
  if (issueMatches) {
    count += issueMatches.length;
  }

  return count;
}

function analyzeBlocks(bodyMarkdown: string): BlockAnalysis {
  const analysis: BlockAnalysis = {
    headingCount: 0,
    outboundLinkCount: 0,
    hasGfmTable: false,
    hasMermaid: false,
    hasSvg: false,
    hasLargeCodeFence: false,
  };

  const lines = bodyMarkdown ? bodyMarkdown.split(/\r?\n/) : [];
  let inFence = false;
  let fenceChar = '';
  let fenceLen = 0;
  let fenceInnerLines = 0;
  let prevLineHasPipe = false;

  for (const line of lines) {
    if (!inFence) {
      const fenceMatch = FENCE_START_RE.exec(line);
      if (fenceMatch?.[1]) {
        const chars = fenceMatch[1];
        const info = (fenceMatch[2] ?? '').trim().toLowerCase();
        inFence = true;
        fenceChar = chars.charAt(0);
        fenceLen = chars.length;
        fenceInnerLines = 0;
        prevLineHasPipe = false;
        if (info.startsWith('mermaid')) {
          analysis.hasMermaid = true;
        }
        if (info.startsWith('svg')) {
          analysis.hasSvg = true;
        }
        continue;
      }

      if (HEADING_RE.test(line)) {
        analysis.headingCount += 1;
      }
      if (prevLineHasPipe && GFM_DELIMITER_RE.test(line)) {
        analysis.hasGfmTable = true;
      }
      if (SVG_REF_RE.test(line)) {
        analysis.hasSvg = true;
      }
      analysis.outboundLinkCount += countOutboundLinks(line);
      prevLineHasPipe = line.includes('|');
    } else {
      const closeRe = new RegExp(`^ {0,3}\\${fenceChar}{${String(fenceLen)},}\\s*$`);
      if (closeRe.test(line)) {
        if (fenceInnerLines > MAX_CODE_FENCE_LINES) {
          analysis.hasLargeCodeFence = true;
        }
        inFence = false;
      } else {
        fenceInnerLines += 1;
      }
    }
  }

  if (inFence && fenceInnerLines > MAX_CODE_FENCE_LINES) {
    analysis.hasLargeCodeFence = true;
  }

  return analysis;
}

/**
 * Evaluates sticky body markdown against 5 S8.2 complexity heuristics and snooze threshold.
 *
 * @param bodyMarkdown - Raw markdown body content
 * @param promotionSnoozedAtLength - Unicode length at which user previously clicked snooze (or null)
 * @param promotedToDocId - If already promoted, returns immediately without triggers
 */
export function evaluateStickyComplexity(
  bodyMarkdown: string,
  promotionSnoozedAtLength: number | null = null,
  promotedToDocId: string | null = null,
): StickyComplexityEvaluation {
  if (promotedToDocId !== null) {
    return {
      exceeded: false,
      reasons: [],
      charLength: Array.from(bodyMarkdown).length,
      shouldShowBanner: false,
    };
  }

  const charLength = Array.from(bodyMarkdown).length;
  const lineCount = bodyMarkdown ? bodyMarkdown.split(/\r?\n/).length : 0;
  const analysis = analyzeBlocks(bodyMarkdown);
  const reasons: string[] = [];

  // Trigger 1: Char length > 600
  if (charLength > MAX_CHAR_LENGTH) {
    reasons.push(`${String(charLength)} chars (> 600)`);
  }

  // Trigger 2: Line count > 10
  if (lineCount > MAX_LINE_COUNT) {
    reasons.push(`${String(lineCount)} lines (> 10)`);
  }

  // Trigger 3: Headings outside code fence >= 2
  if (analysis.headingCount >= MIN_HEADINGS) {
    reasons.push(`${String(analysis.headingCount)} headings (>= 2)`);
  }

  // Trigger 4: Structured block (GFM table, mermaid, svg, or code fence > 6 inner lines)
  if (
    analysis.hasGfmTable ||
    analysis.hasMermaid ||
    analysis.hasSvg ||
    analysis.hasLargeCodeFence
  ) {
    reasons.push('table, diagram, or >6-line code block');
  }

  // Trigger 5: Outbound links outside code fence >= 3
  if (analysis.outboundLinkCount >= MIN_OUTBOUND_LINKS) {
    reasons.push(`${String(analysis.outboundLinkCount)} links (>= 3)`);
  }

  const exceeded = reasons.length > 0;

  // Snooze rule: If snoozed, stays hidden until sticky grows by at least +50% over snoozed length
  let shouldShowBanner = exceeded;
  if (promotionSnoozedAtLength !== null) {
    let snoozeCleared = false;
    if (promotionSnoozedAtLength === 0) {
      snoozeCleared = charLength > 0;
    } else {
      snoozeCleared = charLength * 2 >= promotionSnoozedAtLength * 3;
    }
    shouldShowBanner = exceeded && snoozeCleared;
  }

  return {
    exceeded,
    reasons,
    charLength,
    shouldShowBanner,
  };
}
