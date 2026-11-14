// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CustomFieldValue } from '../CustomFieldValue';
import type { OutputFormatType } from '../api';

describe('CustomFieldValue', () => {
  describe('text format', () => {
    it('renders normal text with prefix', () => {
      render(
        <CustomFieldValue
          format="text"
          value="Production Server"
          metadata={{ prefix: 'Env: ' }}
          testId="cf-text"
        />,
      );
      expect(screen.getByTestId('cf-text').textContent).toContain('Env: Production Server');
    });

    it('truncates text over max_length (280) with ellipsis and title', () => {
      const longText = 'A'.repeat(281);
      render(
        <CustomFieldValue
          format="text"
          value={longText}
          metadata={{ max_length: 280 }}
          testId="cf-text-long"
        />,
      );
      const el = screen.getByTestId('cf-text-long');
      expect(el.textContent).toBe('A'.repeat(280) + '...');
      expect(el.getAttribute('title')).toBe(longText);
    });

    it('supports monospace styling', () => {
      render(
        <CustomFieldValue
          format="text"
          value="commit-sha"
          metadata={{ monospace: true }}
          testId="cf-mono"
        />,
      );
      expect(screen.getByTestId('cf-mono').className).toContain('custom-field-mono');
    });
  });

  describe('number format', () => {
    it('formats number with default fraction digits (2) and unit suffix', () => {
      render(
        <CustomFieldValue
          format="number"
          value={99.8765}
          metadata={{ maximum_fraction_digits: 2, unit_suffix: 'ms' }}
          testId="cf-num"
        />,
      );
      expect(screen.getByTestId('cf-num').textContent).toContain('99.88 ms');
    });

    it('renders Unavailable for non-finite numbers', () => {
      render(
        <CustomFieldValue format="number" value={NaN} testId="cf-num-nan" />,
      );
      expect(screen.getByTestId('cf-num-nan').textContent).toBe('Unavailable');

      render(
        <CustomFieldValue format="number" value={Infinity} testId="cf-num-inf" />,
      );
      expect(screen.getByTestId('cf-num-inf').textContent).toBe('Unavailable');
    });
  });

  describe('badge format', () => {
    it('renders text badge with token color class', () => {
      render(
        <CustomFieldValue
          format="badge"
          value="Approved"
          metadata={{ color_token: 'success' }}
          testId="cf-badge"
        />,
      );
      const el = screen.getByTestId('cf-badge');
      expect(el.textContent).toBe('Approved');
      expect(el.className).toContain('custom-field-badge--success');
    });

    it('ignores arbitrary server CSS/hex and falls back to neutral token', () => {
      render(
        <CustomFieldValue
          format="badge"
          value="Dangerous"
          metadata={{ color_token: '#ff0000;background:url(x)' }}
          testId="cf-badge-unsafe"
        />,
      );
      const el = screen.getByTestId('cf-badge-unsafe');
      expect(el.className).toContain('custom-field-badge--neutral');
    });
  });

  describe('markdown_snippet format', () => {
    it('renders safe markdown snippet (bold, italic, code) without raw HTML', () => {
      const snippet = 'This is **bold** and *italic* and `code`.';
      render(
        <CustomFieldValue
          format="markdown_snippet"
          value={snippet}
          testId="cf-md"
        />,
      );
      const container = screen.getByTestId('cf-md');
      expect(container.querySelector('strong')?.textContent).toBe('bold');
      expect(container.querySelector('em')?.textContent).toBe('italic');
      expect(container.querySelector('code')?.textContent).toBe('code');
    });

    it('strips <img src=x onerror=alert(1)> and retains safe formatting', () => {
      const payload = '<img src=x onerror=alert(1)>**b**';
      const { container } = render(
        <CustomFieldValue
          format="markdown_snippet"
          value={payload}
          testId="cf-md-xss"
        />,
      );
      expect(container.querySelector('img')).toBeNull();
      expect(container.innerHTML).not.toContain('onerror');
      expect(container.innerHTML).not.toContain('alert(1)');
      const strong = screen.getByText('b');
      expect(strong.tagName.toLowerCase()).toBe('strong');
    });

    it('clamps markdown to max_chars', () => {
      const longMd = 'x'.repeat(2500);
      render(
        <CustomFieldValue
          format="markdown_snippet"
          value={longMd}
          metadata={{ max_chars: 2000 }}
          testId="cf-md-clamp"
        />,
      );
      expect(screen.getByTestId('cf-md-clamp').textContent.length).toBe(2000);
    });

    it('handles empty lines and tokens correctly', () => {
      const multiLine = 'First line\n\nSecond line with *italic*';
      render(
        <CustomFieldValue
          format="markdown_snippet"
          value={multiLine}
          testId="cf-md-multi"
        />,
      );
      expect(screen.getByTestId('cf-md-multi').textContent).toContain('First line');
      expect(screen.getByTestId('cf-md-multi').textContent).toContain('Second line with italic');
    });
  });

  describe('url format', () => {
    it('renders safe https anchor with hostname as link text and security attributes', () => {
      render(
        <CustomFieldValue
          format="url"
          value="https://security.example.com/reports/123"
          testId="cf-url"
        />,
      );
      const link = screen.getByTestId('cf-url');
      expect(link.tagName.toLowerCase()).toBe('a');
      expect(link.getAttribute('href')).toBe('https://security.example.com/reports/123');
      expect(link.getAttribute('target')).toBe('_blank');
      expect(link.getAttribute('rel')).toBe('noopener noreferrer nofollow');
      expect(link.textContent).toBe('security.example.com');
    });

    it('renders javascript:alert(1) as plain text with no anchor element', () => {
      const { container } = render(
        <CustomFieldValue
          format="url"
          value="javascript:alert(1)"
          testId="cf-url-unsafe"
        />,
      );
      expect(container.querySelector('a')).toBeNull();
      expect(screen.getByTestId('cf-url-unsafe').textContent).toBe('javascript:alert(1)');
    });
  });

  describe('json_table format', () => {
    it('renders tabular data capped at max_rows (50) and max_cols (10) with overflow footer', () => {
      // 120 rows x 14 columns
      const rows = Array.from({ length: 120 }, (_, rIdx) => {
        const row: Record<string, string> = {};
        for (let c = 0; c < 14; c++) {
          row[`col_${String(c)}`] = `val_${String(rIdx)}_${String(c)}`;
        }
        return row;
      });

      render(
        <CustomFieldValue
          format="json_table"
          value={rows}
          metadata={{ max_rows: 50 }}
          testId="cf-table"
        />,
      );

      const table = screen.getByTestId('cf-table');
      const tableRows = table.querySelectorAll('tbody tr');
      expect(tableRows.length).toBe(50);

      // Verify columns capped at 10
      const headerCols = table.querySelectorAll('thead th');
      expect(headerCols.length).toBe(10);

      // Overflow footer
      expect(table.textContent).toContain('+70 more rows');
    });

    it('renders empty message when value is empty array', () => {
      render(
        <CustomFieldValue
          format="json_table"
          value={[]}
          testId="cf-table-empty"
        />,
      );
      expect(screen.getByTestId('cf-table-empty').textContent).toBe('No table data');
    });
  });

  describe('severity_pill format', () => {
    it('renders severity score and label with design token styling', () => {
      render(
        <CustomFieldValue
          format="severity_pill"
          value={{ level: 'high', score: 8.8, label: 'High' }}
          testId="cf-sev"
        />,
      );
      const el = screen.getByTestId('cf-sev');
      expect(el.className).toContain('custom-field-severity--high');
      expect(el.textContent).toContain('8.8');
      expect(el.textContent).toContain('High');
    });

    it('renders all 4 severity levels (low, medium, high, critical)', () => {
      const levels = ['low', 'medium', 'high', 'critical'] as const;
      for (const lvl of levels) {
        const { unmount } = render(
          <CustomFieldValue
            format="severity_pill"
            value={lvl}
            testId={`cf-sev-${lvl}`}
          />,
        );
        expect(screen.getByTestId(`cf-sev-${lvl}`).className).toContain(`custom-field-severity--${lvl}`);
        unmount();
      }
    });

    it('renders Unavailable for unknown severity level', () => {
      render(
        <CustomFieldValue
          format="severity_pill"
          value={{ level: 'catastrophic' }}
          testId="cf-sev-unknown"
        />,
      );
      expect(screen.getByTestId('cf-sev-unknown').textContent).toBe('Unavailable');
    });
  });

  describe('null / undefined / unknown format', () => {
    it('handles stray asterisk in markdown snippet', () => {
      render(
        <CustomFieldValue
          format="markdown_snippet"
          value="Single * asterisk remaining"
          testId="cf-md-stray"
        />,
      );
      expect(screen.getByTestId('cf-md-stray').textContent).toContain('Single * asterisk remaining');
    });

    it('renders plain text for invalid URL syntax', () => {
      render(
        <CustomFieldValue
          format="url"
          value="ht tp://invalid-url-with-spaces"
          testId="cf-url-invalid"
        />,
      );
      expect(screen.getByTestId('cf-url-invalid').textContent).toBe('ht tp://invalid-url-with-spaces');
    });

    it('uses explicit columns in json_table when provided', () => {
      const data = [{ service: 'auth-svc', port: 8080 }];
      render(
        <CustomFieldValue
          format="json_table"
          value={data}
          metadata={{ columns: [{ key: 'service', label: 'Service Name' }] }}
          testId="cf-table-cols"
        />,
      );
      expect(screen.getByTestId('cf-table-cols').textContent).toContain('Service Name');
      expect(screen.getByTestId('cf-table-cols').textContent).toContain('auth-svc');
    });

    it('renders empty json_table gracefully', () => {
      render(
        <CustomFieldValue format="json_table" value={[]} testId="cf-table-empty" />,
      );
      expect(screen.getByTestId('cf-table-empty')).toBeDefined();
    });

    it('renders table cells with null and undefined values as empty strings', () => {
      render(
        <CustomFieldValue
          format="json_table"
          value={[{ a: null, b: undefined, c: 'hello' }]}
          testId="cf-table-null-cells"
        />,
      );
      expect(screen.getByTestId('cf-table-null-cells').textContent).toContain('hello');
    });

    it('handles severity_pill with string value', () => {
      render(
        <CustomFieldValue format="severity_pill" value="critical" testId="cf-sev-str" />,
      );
      expect(screen.getByTestId('cf-sev-str').textContent).toBe('Critical');
    });

    it('falls back to neutral badge on unrecognized color token', () => {
      render(
        <CustomFieldValue
          format="badge"
          value="TestBadge"
          metadata={{ color_token: 'nonexistent_color' }}
          testId="cf-badge-fallback"
        />,
      );
      expect(screen.getByTestId('cf-badge-fallback').className).toContain(
        'custom-field-badge--neutral',
      );
    });

    it('renders badge without metadata using neutral default', () => {
      render(
        <CustomFieldValue format="badge" value="SimpleBadge" testId="cf-badge-simple" />,
      );
      expect(screen.getByTestId('cf-badge-simple').textContent).toBe('SimpleBadge');
    });

    it('renders number without metadata using default formatting', () => {
      render(<CustomFieldValue format="number" value={42} testId="cf-num-simple" />);
      expect(screen.getByTestId('cf-num-simple').textContent).toBe('42');
    });

    it('infers columns in json_table when metadata columns not provided', () => {
      render(
        <CustomFieldValue
          format="json_table"
          value={[{ host: 'srv-1', port: 443 }]}
          testId="cf-table-inferred"
        />,
      );
      expect(screen.getByTestId('cf-table-inferred').textContent).toContain('host');
      expect(screen.getByTestId('cf-table-inferred').textContent).toContain('srv-1');
    });

    it('handles severity_pill object without level', () => {
      render(
        <CustomFieldValue
          format="severity_pill"
          value={{ score: 5 }}
          testId="cf-sev-no-level"
        />,
      );
      expect(screen.getByTestId('cf-sev-no-level').textContent).toBe('Unavailable');
    });

    it('renders Unavailable for null or undefined values', () => {
      render(<CustomFieldValue format="text" value={null} testId="cf-null" />);
      expect(screen.getByTestId('cf-null').textContent).toBe('Unavailable');

      render(<CustomFieldValue format="text" value={undefined} testId="cf-undef" />);
      expect(screen.getByTestId('cf-undef').textContent).toBe('Unavailable');
    });

    it('renders Unavailable for unrecognized format', () => {
      render(
        <CustomFieldValue
          format={'unsupported_format' as unknown as OutputFormatType}
          value="hello"
          testId="cf-unrec"
        />,
      );
      expect(screen.getByTestId('cf-unrec').textContent).toBe('Unavailable');
    });

    it('handles non-string primitive and object values across format renderers', () => {
      render(<CustomFieldValue format="text" value={12345} testId="cf-num" />);
      expect(screen.getByTestId('cf-num').textContent).toContain('12345');

      render(<CustomFieldValue format="text" value={true} testId="cf-bool" />);
      expect(screen.getByTestId('cf-bool').textContent).toContain('true');

      render(<CustomFieldValue format="text" value={{ foo: 'bar' }} testId="cf-obj" />);
      expect(screen.getByTestId('cf-obj').textContent).toContain('{"foo":"bar"}');

      render(<CustomFieldValue format="severity_pill" value={999} testId="cf-sev-num" />);
      expect(screen.getByTestId('cf-sev-num').textContent).toBe('Unavailable');
    });
  });
});
