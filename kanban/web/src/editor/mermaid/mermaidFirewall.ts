/**
 * Mermaid Directive & Resource Firewall (KB-P3-47, S5.3).
 * Sanitizes input Mermaid diagrams by stripping insecure directives,
 * callbacks (click, href, call), @import rules, and raw HTML tags inside labels.
 * Enforces strict byte, node, edge, and supported diagram type bounds.
 */

export const MAX_MERMAID_BYTES = 65536;
export const MAX_MERMAID_NODES = 400;
export const MAX_MERMAID_EDGES = 1000;
export const MERMAID_WATCHDOG_MS = 1500;

export const SUPPORTED_DIAGRAM_TYPES: readonly string[] = Object.freeze([
  'flowchart',
  'graph',
  'sequenceDiagram',
  'stateDiagram-v2',
  'stateDiagram',
  'classDiagram',
  'erDiagram',
  'xychart-beta',
]);

export type MermaidFirewallErrorCode =
  | 'SOURCE_TOO_LARGE'
  | 'EMPTY_SOURCE'
  | 'UNSUPPORTED_DIAGRAM_TYPE'
  | 'NODE_LIMIT_EXCEEDED'
  | 'EDGE_LIMIT_EXCEEDED';

export interface MermaidFirewallSuccess {
  readonly ok: true;
  readonly sanitizedSource: string;
  readonly nodeCount: number;
  readonly edgeCount: number;
  readonly diagramType: string;
  readonly strippedDirectives: readonly string[];
}

export interface MermaidFirewallFailure {
  readonly ok: false;
  readonly code: MermaidFirewallErrorCode;
  readonly message: string;
}

export type MermaidFirewallResult = MermaidFirewallSuccess | MermaidFirewallFailure;

const RESERVED_TOKENS = new Set([
  'flowchart',
  'graph',
  'sequenceDiagram',
  'stateDiagram-v2',
  'stateDiagram',
  'classDiagram',
  'erDiagram',
  'xychart-beta',
  'subgraph',
  'end',
  'direction',
  'TD',
  'TB',
  'BT',
  'RL',
  'LR',
  'autonumber',
  'title',
  'accTitle',
  'accDescr',
  'participant',
  'actor',
  'state',
  'class',
  'note',
  'loop',
  'alt',
  'else',
  'opt',
  'par',
]);

const EDGE_REGEX =
  /(-->|---|-.->|-\.-|==>|===|<--|<-->|<==>|->>|-->>|->|--x|-x|--\)|-\)|<\|--|--\|>|<\|\.\.|\.\.\|>|\*--|--\*|o--|--o|\.\.>|\.\.|[|o}{]{1,2}[-.]{2}[|o}{]{1,2})/g;

function stripDangerousHtml(input: string): string {
  // Strip dangerous block tags and their content
  let cleaned = input.replace(
    /<(?:script|style|foreignObject|iframe|object)[\s\S]*?<\/(?:script|style|foreignObject|iframe|object)>/gi,
    '',
  );
  // Strip any remaining or self-closing HTML tags (<tag ...> or </tag>)
  cleaned = cleaned.replace(/<\/?([a-zA-Z][a-zA-Z0-9:-]*)(?:\s+[^>]*)?\/?>/gi, '');
  return cleaned;
}

function detectDiagramType(source: string): { type: string | null; firstToken: string } {
  const lines = source.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('%%')) {
      continue;
    }
    const tokenMatch = /^([a-zA-Z0-9_-]+)/.exec(trimmed);
    const token = tokenMatch?.[1] ?? '';
    for (const supported of SUPPORTED_DIAGRAM_TYPES) {
      if (
        trimmed === supported ||
        trimmed.startsWith(`${supported} `) ||
        trimmed.startsWith(`${supported}\t`) ||
        trimmed.startsWith(`${supported}\n`) ||
        trimmed.startsWith(`${supported}:`)
      ) {
        return { type: supported, firstToken: token };
      }
    }
    return { type: null, firstToken: token };
  }
  return { type: null, firstToken: '' };
}

function countNodesAndEdges(
  source: string,
  diagramType: string,
): { nodeCount: number; edgeCount: number } {
  const lines = source.split('\n');
  const nodeSet = new Set<string>();
  let edgeCount = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('%%')) {
      continue;
    }

    const edgeMatches = trimmed.match(EDGE_REGEX);
    if (edgeMatches) {
      edgeCount += edgeMatches.length;
    }

    switch (diagramType) {
      case 'flowchart':
      case 'graph': {
        const nodeDefRegex =
          /\b([a-zA-Z0-9_#-]+)(?=\s*(?:\[|\(|\{|\>|\/|\||-->|---|-.->|-\.-|==>|===|<--|<-->|<==>|\s*$))/g;
        let m: RegExpExecArray | null;
        while ((m = nodeDefRegex.exec(trimmed)) !== null) {
          const id = m[1];
          if (id && !RESERVED_TOKENS.has(id) && !/^\d+$/.test(id)) {
            nodeSet.add(id);
          }
        }
        break;
      }
      case 'sequenceDiagram': {
        const pMatch = /^(?:participant|actor)\s+([a-zA-Z0-9_]+(?:-[a-zA-Z0-9_]+)*)/i.exec(trimmed);
        if (pMatch?.[1]) {
          nodeSet.add(pMatch[1]);
        } else {
          const mMatch = /^([a-zA-Z0-9_]+(?:-[a-zA-Z0-9_]+)*)\s*(?:->>|-->>|->|-->)\s*([a-zA-Z0-9_]+(?:-[a-zA-Z0-9_]+)*)/.exec(trimmed);
          if (mMatch?.[1] && mMatch[2]) {
            nodeSet.add(mMatch[1]);
            nodeSet.add(mMatch[2]);
          }
        }
        break;
      }
      case 'stateDiagram':
      case 'stateDiagram-v2': {
        const sMatch = /^state\s+([a-zA-Z0-9_#-]+)/i.exec(trimmed);
        if (sMatch?.[1]) {
          nodeSet.add(sMatch[1]);
        } else {
          const tMatch = /^(\[\*\]|[a-zA-Z0-9_#-]+)\s*-->\s*(\[\*\]|[a-zA-Z0-9_#-]+)/.exec(trimmed);
          if (tMatch?.[1] && tMatch[2]) {
            if (tMatch[1] !== '[*]') nodeSet.add(tMatch[1]);
            if (tMatch[2] !== '[*]') nodeSet.add(tMatch[2]);
          }
        }
        break;
      }
      case 'classDiagram': {
        const cMatch = /^class\s+([a-zA-Z0-9_#-]+)/i.exec(trimmed);
        if (cMatch?.[1]) {
          nodeSet.add(cMatch[1]);
        } else {
          const rMatch = /^([a-zA-Z0-9_#-]+)\s*[<|\*\.o-]+\s*([a-zA-Z0-9_#-]+)/.exec(trimmed);
          if (rMatch?.[1] && rMatch[2] && !RESERVED_TOKENS.has(rMatch[1])) {
            nodeSet.add(rMatch[1]);
            nodeSet.add(rMatch[2]);
          }
        }
        break;
      }
      case 'erDiagram': {
        const erMatch = /^([a-zA-Z0-9_#-]+)\s*[|o}{.-]+\s*([a-zA-Z0-9_#-]+)/.exec(trimmed);
        if (erMatch?.[1] && erMatch[2] && !RESERVED_TOKENS.has(erMatch[1])) {
          nodeSet.add(erMatch[1]);
          nodeSet.add(erMatch[2]);
        }
        break;
      }
      case 'xychart-beta':
        nodeSet.add('xychart');
        break;
    }
  }

  return { nodeCount: nodeSet.size, edgeCount };
}

/**
 * Validates and sanitizes untrusted Mermaid diagram source text.
 */
export function sanitizeAndValidateMermaid(rawSource: string): MermaidFirewallResult {
  // Normalize escaped \n if rawSource contains no real newlines (e.g. from attributes or JSON)
  let normalizedSource = rawSource;
  if (!normalizedSource.includes('\n') && normalizedSource.includes('\\n')) {
    normalizedSource = normalizedSource.replace(/\\n/g, '\n');
  }

  // 1. Rejects UTF-8 byte length > 65536
  const encoder = new TextEncoder();
  const byteLength = encoder.encode(normalizedSource).length;
  if (byteLength > MAX_MERMAID_BYTES) {
    return {
      ok: false,
      code: 'SOURCE_TOO_LARGE',
      message: `Diagram source byte length (${String(byteLength)}) exceeds maximum of ${String(MAX_MERMAID_BYTES)} bytes.`,
    };
  }

  // 2. Strip all %%{...}%% directives and record them
  const strippedDirectives: string[] = [];
  let source = normalizedSource.replace(/%%\{[\s\S]*?\}%%/g, (match) => {
    strippedDirectives.push(match.trim());
    return '';
  });

  // 3. Strip CSS @import rules
  source = source.replace(/@import\s+[^;\n]+;?/gi, '');

  // 4. Strip interactive click statements, hrefs, and callbacks line-by-line
  const rawLines = source.split('\n');
  const filteredLines: string[] = [];
  for (const line of rawLines) {
    const trimmed = line.trim();
    if (/^click\s+/i.test(trimmed)) {
      continue;
    }
    if (/^href\s+/i.test(trimmed) || /^call\s+/i.test(trimmed)) {
      continue;
    }
    filteredLines.push(line);
  }
  source = filteredLines.join('\n');

  // 5. Strip raw HTML tags inside labels
  source = stripDangerousHtml(source);

  // 6. Verify first non-comment diagram header token is in supported allowlist
  const { type: diagramType, firstToken } = detectDiagramType(source);
  if (!diagramType) {
    if (!firstToken) {
      return {
        ok: false,
        code: 'EMPTY_SOURCE',
        message: 'Diagram source is empty or contains only comments.',
      };
    }
    return {
      ok: false,
      code: 'UNSUPPORTED_DIAGRAM_TYPE',
      message: `Diagram type '${firstToken}' is not supported. Supported types: ${SUPPORTED_DIAGRAM_TYPES.join(', ')}.`,
    };
  }

  // 7. Count nodes and edges and enforce caps
  const { nodeCount, edgeCount } = countNodesAndEdges(source, diagramType);
  if (nodeCount > MAX_MERMAID_NODES) {
    return {
      ok: false,
      code: 'NODE_LIMIT_EXCEEDED',
      message: `Diagram node count (${String(nodeCount)}) exceeds maximum limit of ${String(MAX_MERMAID_NODES)}.`,
    };
  }
  if (edgeCount > MAX_MERMAID_EDGES) {
    return {
      ok: false,
      code: 'EDGE_LIMIT_EXCEEDED',
      message: `Diagram edge count (${String(edgeCount)}) exceeds maximum limit of ${String(MAX_MERMAID_EDGES)}.`,
    };
  }

  return {
    ok: true,
    sanitizedSource: source.trim(),
    nodeCount,
    edgeCount,
    diagramType,
    strippedDirectives,
  };
}
