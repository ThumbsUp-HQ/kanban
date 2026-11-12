/**
 * Unit Tests for Mermaid Directive & Resource Firewall (KB-P3-47, S5.3).
 */

import { describe, it, expect } from 'vitest';
import {
  sanitizeAndValidateMermaid,
  MAX_MERMAID_BYTES,
  SUPPORTED_DIAGRAM_TYPES,
} from './mermaidFirewall';

describe('mermaidFirewall', () => {
  it('passes all supported diagram types', () => {
    const validDiagrams: Record<string, string> = {
      flowchart: 'flowchart TD\n  A[Start] --> B[End]',
      graph: 'graph LR\n  X --> Y',
      sequenceDiagram: 'sequenceDiagram\n  autonumber\n  Alice->>Bob: Hello\n  Bob-->>Alice: Hi',
      'stateDiagram-v2': 'stateDiagram-v2\n  [*] --> State1\n  State1 --> State2\n  State2 --> [*]',
      stateDiagram: 'stateDiagram\n  state "Active" as S1\n  [*] --> S1',
      classDiagram: 'classDiagram\n  class Animal\n  Animal <|-- Duck',
      erDiagram: 'erDiagram\n  CUSTOMER ||--o{ ORDER : places',
      'xychart-beta': 'xychart-beta\n  title "Performance"\n  x-axis ["Q1", "Q2"]\n  y-axis "Score" 0 --> 100\n  bar [80, 95]',
    };

    for (const [, source] of Object.entries(validDiagrams)) {
      const result = sanitizeAndValidateMermaid(source);
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(SUPPORTED_DIAGRAM_TYPES).toContain(result.diagramType);
        expect(result.sanitizedSource.length).toBeGreaterThan(0);
      }
    }
  });

  it('strips %%{...}%% directives, click/href callbacks, @import, and HTML tags', () => {
    const raw = `
%%{init: {'securityLevel': 'loose', 'theme': 'forest'}}%%
flowchart TD
  @import url("https://evil.test/x.css");
  A["<script>alert(1)</script><foreignObject><b>x</b></foreignObject>Auth"] --> B["Label (Extra Info)"]
  click A href "javascript:alert(1)"
  click B call alert()
  href "https://evil.test"
  call evil()
`;

    const result = sanitizeAndValidateMermaid(raw);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.strippedDirectives).toHaveLength(1);
      expect(result.strippedDirectives[0]).toContain('securityLevel');
      expect(result.sanitizedSource).not.toContain('securityLevel');
      expect(result.sanitizedSource).not.toContain('@import');
      expect(result.sanitizedSource).not.toContain('click A');
      expect(result.sanitizedSource).not.toContain('javascript:alert(1)');
      expect(result.sanitizedSource).not.toContain('<script>');
      expect(result.sanitizedSource).not.toContain('<foreignObject>');
      expect(result.sanitizedSource).not.toContain('<b>');
      expect(result.sanitizedSource).toContain('A["Auth"]');
      expect(result.sanitizedSource).toContain('B["Label (Extra Info)"]');
    }
  });

  describe('boundary limits', () => {
    it('verifies byte length cap (65,536 bytes passes; 65,537 bytes fails)', () => {
      const header = 'graph TD\n';
      const fillChar = ' ';
      const neededBytes = MAX_MERMAID_BYTES - header.length;
      const exactSource = header + fillChar.repeat(neededBytes);

      const encoder = new TextEncoder();
      expect(encoder.encode(exactSource).length).toBe(65536);

      const passResult = sanitizeAndValidateMermaid(exactSource);
      expect(passResult.ok).toBe(true);

      const overSource = exactSource + 'x';
      expect(encoder.encode(overSource).length).toBe(65537);

      const failResult = sanitizeAndValidateMermaid(overSource);
      expect(failResult.ok).toBe(false);
      if (!failResult.ok) {
        expect(failResult.code).toBe('SOURCE_TOO_LARGE');
        expect(failResult.message).toContain('65537');
      }
    });

    it('verifies node limit cap (400 nodes passes; 401 nodes fails)', () => {
      let passSrc = 'graph TD\n';
      for (let i = 0; i < 400; i++) {
        passSrc += `  N${String(i)}["Node ${String(i)}"]\n`;
      }
      const passResult = sanitizeAndValidateMermaid(passSrc);
      expect(passResult.ok).toBe(true);
      if (passResult.ok) {
        expect(passResult.nodeCount).toBe(400);
      }

      let failSrc = 'graph TD\n';
      for (let i = 0; i <= 400; i++) {
        failSrc += `  N${String(i)}["Node ${String(i)}"]\n`;
      }
      const failResult = sanitizeAndValidateMermaid(failSrc);
      expect(failResult.ok).toBe(false);
      if (!failResult.ok) {
        expect(failResult.code).toBe('NODE_LIMIT_EXCEEDED');
        expect(failResult.message).toContain('401');
      }
    });

    it('verifies edge limit cap (1,000 edges passes; 1,001 edges fails)', () => {
      let passSrc = 'graph TD\n';
      for (let i = 0; i < 1000; i++) {
        passSrc += '  A --> B\n';
      }
      const passResult = sanitizeAndValidateMermaid(passSrc);
      expect(passResult.ok).toBe(true);
      if (passResult.ok) {
        expect(passResult.edgeCount).toBe(1000);
      }

      let failSrc = 'graph TD\n';
      for (let i = 0; i <= 1000; i++) {
        failSrc += '  A --> B\n';
      }
      const failResult = sanitizeAndValidateMermaid(failSrc);
      expect(failResult.ok).toBe(false);
      if (!failResult.ok) {
        expect(failResult.code).toBe('EDGE_LIMIT_EXCEEDED');
        expect(failResult.message).toContain('1001');
      }
    });
  });

  describe('unsupported diagram types and empty sources', () => {
    it('rejects unsupported diagram types (gantt, mindmap, pie, gitGraph)', () => {
      const unsupported = [
        'gantt\n  title A Gantt Diagram',
        'mindmap\n  root((mindmap))',
        'pie title Pets\n  "Dogs" : 386',
        'gitGraph\n  commit',
      ];

      for (const src of unsupported) {
        const result = sanitizeAndValidateMermaid(src);
        expect(result.ok).toBe(false);
        if (!result.ok) {
          expect(result.code).toBe('UNSUPPORTED_DIAGRAM_TYPE');
        }
      }
    });

    it('rejects empty or whitespace-only source (EMPTY_SOURCE)', () => {
      const result = sanitizeAndValidateMermaid('   \n\t  ');
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.code).toBe('EMPTY_SOURCE');
      }
    });

    it('rejects source containing only comments', () => {
      const result = sanitizeAndValidateMermaid('%% This is a comment\n%% Another comment');
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.code).toBe('EMPTY_SOURCE');
      }
    });
  });

  describe('sequence, state, and class node/edge counting branches', () => {
    it('counts participant declarations and messages in sequence diagrams', () => {
      const src = `
sequenceDiagram
  participant Alice
  actor Bob
  Alice->>Bob: Hello
  Bob-->>Charlie: Forward
`;
      const result = sanitizeAndValidateMermaid(src);
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.nodeCount).toBe(3);
        expect(result.edgeCount).toBe(2);
      }
    });

    it('counts states and transitions in state diagrams', () => {
      const src = `
stateDiagram
  state Initial
  [*] --> Initial
  Initial --> Active
  Active --> [*]
`;
      const result = sanitizeAndValidateMermaid(src);
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.nodeCount).toBe(2);
        expect(result.edgeCount).toBe(3);
      }
    });

    it('counts classes and relations in class diagrams', () => {
      const src = `
classDiagram
  class BaseVehicle
  Car <|-- BaseVehicle
  Car --> Engine
`;
      const result = sanitizeAndValidateMermaid(src);
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.nodeCount).toBe(3);
        expect(result.edgeCount).toBe(2);
      }
    });

    it('counts entities in er diagrams', () => {
      const src = `
erDiagram
  USER ||--o{ POST : writes
  POST ||--|{ COMMENT : contains
`;
      const result = sanitizeAndValidateMermaid(src);
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.nodeCount).toBe(3);
        expect(result.edgeCount).toBe(2);
      }
    });

    it('counts nodes and handles reserved tokens in class and xychart diagrams', () => {
      const classSrc = `
classDiagram
  direction LR
  classDiagram --|> B
  Car --> Engine
`;
      const classResult = sanitizeAndValidateMermaid(classSrc);
      expect(classResult.ok).toBe(true);

      const xySrc = `
xychart-beta
  title "Chart"
  x-axis [1, 2]
  y-axis "Y" 0 --> 10
  bar [1, 2]
`;
      const xyResult = sanitizeAndValidateMermaid(xySrc);
      expect(xyResult.ok).toBe(true);
      if (xyResult.ok) {
        expect(xyResult.nodeCount).toBe(1);
      }

      // Diagram starting with non-alphanumeric token
      const nonAlphaResult = sanitizeAndValidateMermaid('~invalid diagram');
      expect(nonAlphaResult.ok).toBe(false);
      if (!nonAlphaResult.ok) {
        expect(nonAlphaResult.code).toBe('EMPTY_SOURCE');
      }
    });
  });
});
