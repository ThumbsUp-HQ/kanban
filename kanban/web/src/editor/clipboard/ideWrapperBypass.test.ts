/**
 * Unit Tests for IDE Syntax-Highlighted Code Wrapper Bypass (KB-P3-46, S5.2).
 */

import { describe, it, expect } from 'vitest';
import { detectIdeCodePaste } from './ideWrapperBypass';

function createMockDataTransfer(data: Record<string, string>): DataTransfer {
  return {
    getData: (format: string) => data[format] ?? '',
    types: Object.keys(data),
    files: [] as unknown as FileList,
    items: [] as unknown as DataTransferItemList,
    clearData: () => undefined,
    setData: () => undefined,
    dropEffect: 'none',
    effectAllowed: 'none',
  } as unknown as DataTransfer;
}

describe('ideWrapperBypass', () => {
  it('Case 3: Branch 2 (VS Code / IDE Wrapper) detects vscode-editor-data and maps mode', () => {
    const dt = createMockDataTransfer({
      'vscode-editor-data': JSON.stringify({ mode: 'typescript' }),
      'text/html': '<div><span style="color:#d4d4d4">const x = 1;</span></div>',
      'text/plain': 'const x = 1;',
    });

    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(true);
    expect(result.language).toBe('ts');
    expect(result.codeText).toBe('const x = 1;');
  });

  it('detects single pre/div wrapper with color spans without vscode-editor-data', () => {
    const dt = createMockDataTransfer({
      'text/html': '<pre><span style="color: #ff0000">fn main() {}</span></pre>',
      'text/plain': 'fn main() {}',
    });

    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(true);
    expect(result.codeText).toBe('fn main() {}');
  });

  it('detects language from language-* class on wrapper', () => {
    const dt = createMockDataTransfer({
      'text/html': '<div class="language-python"><span style="color: blue">def foo(): pass</span></div>',
      'text/plain': 'def foo(): pass',
    });

    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(true);
    expect(result.language).toBe('py');

    // Unknown language fallback to raw language string
    const dt2 = createMockDataTransfer({
      'text/html': '<div class="language-customlang"><span style="color: blue">code</span></div>',
      'text/plain': 'code',
    });
    const result2 = detectIdeCodePaste(dt2);
    expect(result2.isIdeCode).toBe(true);
    expect(result2.language).toBe('customlang');
  });

  it('detects code wrapper with monospace font-family styling', () => {
    const dt = createMockDataTransfer({
      'text/html': '<pre style="font-family: monospace">let y = 10;</pre>',
      'text/plain': 'let y = 10;',
    });
    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(true);
    expect(result.codeText).toBe('let y = 10;');
  });

  it('handles vscode-editor-data without mode or with empty mode', () => {
    const dt = createMockDataTransfer({
      'vscode-editor-data': JSON.stringify({}),
      'text/plain': 'echo test',
    });
    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(true);
    expect(result.language).toBe('');
    expect(result.codeText).toBe('echo test');
  });

  it('rejects rich HTML containing semantic block tags (p, h2, table, a, img)', () => {
    const dt = createMockDataTransfer({
      'text/html': '<div><p>Paragraph</p><span style="color: red">Code</span></div>',
      'text/plain': 'Paragraph Code',
    });

    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(false);
  });

  it('rejects HTML with multiple root elements', () => {
    const dt = createMockDataTransfer({
      'text/html': '<div>line 1</div><div>line 2</div>',
      'text/plain': 'line 1\nline 2',
    });

    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(false);
  });

  it('rejects HTML when root is not pre or div', () => {
    const dt = createMockDataTransfer({
      'text/html': '<section><span style="color:red">test</span></section>',
      'text/plain': 'test',
    });

    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(false);
  });

  it('rejects HTML containing disallowed tags inside wrapper', () => {
    const dt = createMockDataTransfer({
      'text/html': '<div><button>Click</button></div>',
      'text/plain': 'Click',
    });

    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(false);
  });

  it('rejects wrapper without code styling or language class', () => {
    const dt = createMockDataTransfer({
      'text/html': '<div><span>simple text</span></div>',
      'text/plain': 'simple text',
    });

    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(false);
  });

  it('handles malformed vscode-editor-data gracefully', () => {
    const dt = createMockDataTransfer({
      'vscode-editor-data': '{malformed json',
      'text/html': '<div><span style="color: #fff">clean</span></div>',
      'text/plain': 'clean',
    });

    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(true);
    expect(result.codeText).toBe('clean');
  });

  it('returns false for empty clipboard data', () => {
    const dt = createMockDataTransfer({});
    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(false);
  });

  it('handles vscode-editor-data with unknown or invalid mode characters', () => {
    const dt = createMockDataTransfer({
      'vscode-editor-data': JSON.stringify({ mode: 'invalid;chars<script>' }),
      'text/plain': 'some code',
    });

    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(true);
    expect(result.language).toBe('');
  });

  it('falls back to doc.body.textContent when text/plain is empty for styled HTML wrapper', () => {
    const dt = createMockDataTransfer({
      'text/html': '<pre style="color: #fff"><span>fallback code</span></pre>',
      'text/plain': '',
    });

    const result = detectIdeCodePaste(dt);
    expect(result.isIdeCode).toBe(true);
    expect(result.codeText).toBe('fallback code');
  });
});
