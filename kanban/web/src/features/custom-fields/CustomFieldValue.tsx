// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import type { JSX, ReactNode } from 'react';
import React from 'react';
import type { OutputFormatType } from './api';

export interface CustomFieldValueProps {
  format: OutputFormatType;
  value: unknown;
  metadata?: Record<string, unknown>;
  testId?: string;
}

const BADGE_COLOR_CLASSES: Record<string, string> = {
  neutral: 'custom-field-badge--neutral',
  info: 'custom-field-badge--info',
  success: 'custom-field-badge--success',
  warning: 'custom-field-badge--warning',
  danger: 'custom-field-badge--danger',
  accent: 'custom-field-badge--accent',
};

const SEVERITY_CLASSES: Record<string, string> = {
  low: 'custom-field-severity--low',
  medium: 'custom-field-severity--medium',
  high: 'custom-field-severity--high',
  critical: 'custom-field-severity--critical',
};

function safeString(val: unknown): string {
  if (typeof val === 'string') return val;
  if (typeof val === 'number' || typeof val === 'boolean' || typeof val === 'bigint') {
    return String(val);
  }
  if (val === null || val === undefined) return '';
  return JSON.stringify(val);
}

/**
 * Pure React tokenizer to render markdown without dangerouslySetInnerHTML.
 * Strips raw HTML tags and images, supporting basic bold, italic, and inline code.
 */
function renderSafeMarkdownSnippet(text: string): ReactNode {
  // Strip <img ...> and raw HTML tags
  const sanitized = text
    .replace(/<img[^>]*>/gi, '')
    .replace(/<[^>]+>/g, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '');

  const lines = sanitized.split('\n');

  return (
    <div className="custom-field-markdown-snippet">
      {lines.map((line, lineIdx) => {
        if (!line.trim()) {
          return <div key={`line-${String(lineIdx)}`} className="custom-field-markdown-empty" />;
        }

        // Tokenize inline bold, italic, code
        const tokens: ReactNode[] = [];
        let remaining = line;
        let tokenKey = 0;

        while (remaining.length > 0) {
          // Bold **text**
          const boldMatch = /^\*\*([^*]+)\*\*/.exec(remaining);
          if (boldMatch) {
            tokens.push(
              <strong key={`b-${String(tokenKey++)}`}>{boldMatch[1]}</strong>,
            );
            remaining = remaining.slice(boldMatch[0].length);
            continue;
          }

          // Inline code `code`
          const codeMatch = /^`([^`]+)`/.exec(remaining);
          if (codeMatch) {
            tokens.push(
              <code key={`c-${String(tokenKey++)}`} className="custom-field-mono">
                {codeMatch[1]}
              </code>,
            );
            remaining = remaining.slice(codeMatch[0].length);
            continue;
          }

          // Italic *text*
          const italicMatch = /^\*([^*]+)\*/.exec(remaining);
          if (italicMatch) {
            tokens.push(
              <em key={`i-${String(tokenKey++)}`}>{italicMatch[1]}</em>,
            );
            remaining = remaining.slice(italicMatch[0].length);
            continue;
          }

          // Plain text up to next special char
          const nextSpecial = remaining.search(/[*`]/);
          if (nextSpecial === -1) {
            tokens.push(remaining);
            break;
          } else if (nextSpecial === 0) {
            // Stray asterisk or backtick
            tokens.push(remaining[0]);
            remaining = remaining.slice(1);
          } else {
            tokens.push(remaining.slice(0, nextSpecial));
            remaining = remaining.slice(nextSpecial);
          }
        }

        return (
          <p key={`p-${String(lineIdx)}`} className="custom-field-markdown-p">
            {tokens}
          </p>
        );
      })}
    </div>
  );
}

/**
 * 7-format safe value renderer for admin-defined scripted custom fields (S13.1).
 * Strictly guarantees ZERO dangerouslySetInnerHTML usage and renders safe React text nodes.
 */
export function CustomFieldValue({
  format,
  value,
  metadata,
  testId,
}: CustomFieldValueProps): JSX.Element {
  if (value === null || value === undefined) {
    return (
      <span className="custom-field-unavailable" data-testid={testId}>
        Unavailable
      </span>
    );
  }

  switch (format) {
    case 'text': {
      const rawText = safeString(value);
      const prefix = typeof metadata?.prefix === 'string' ? metadata.prefix : '';
      const maxLength =
        typeof metadata?.max_length === 'number' && metadata.max_length > 0
          ? Math.min(metadata.max_length, 280)
          : 280;
      const isMonospace = Boolean(metadata?.monospace);

      let displayedText = rawText;
      let hasTruncated = false;
      if (rawText.length > maxLength) {
        displayedText = rawText.slice(0, maxLength) + '...';
        hasTruncated = true;
      }

      return (
        <span
          className={`custom-field-text ${isMonospace ? 'custom-field-mono' : ''}`}
          title={hasTruncated ? rawText : undefined}
          data-testid={testId}
        >
          {prefix}
          {displayedText}
        </span>
      );
    }

    case 'number': {
      const num = Number(value);
      if (!Number.isFinite(num)) {
        return (
          <span className="custom-field-unavailable" data-testid={testId}>
            Unavailable
          </span>
        );
      }

      const fractionDigits =
        typeof metadata?.maximum_fraction_digits === 'number'
          ? Math.max(0, Math.min(6, metadata.maximum_fraction_digits))
          : 2;
      const unitSuffix =
        typeof metadata?.unit_suffix === 'string' ? metadata.unit_suffix : '';

      const formatter = new Intl.NumberFormat('en-US', {
        maximumFractionDigits: fractionDigits,
      });

      return (
        <span className="custom-field-number" data-testid={testId}>
          {formatter.format(num)}
          {unitSuffix ? ` ${unitSuffix}` : ''}
        </span>
      );
    }

    case 'badge': {
      const label = safeString(value);
      const rawColor =
        typeof metadata?.color_token === 'string' ? metadata.color_token : 'neutral';
      const colorClass = BADGE_COLOR_CLASSES[rawColor] ?? 'custom-field-badge--neutral';

      return (
        <span className={`custom-field-badge ${colorClass}`} data-testid={testId}>
          {label}
        </span>
      );
    }

    case 'markdown_snippet': {
      const rawText = safeString(value);
      const maxChars =
        typeof metadata?.max_chars === 'number' && metadata.max_chars > 0
          ? Math.min(metadata.max_chars, 2000)
          : 2000;
      const clampedText = rawText.slice(0, maxChars);

      return (
        <div className="custom-field-markdown-wrapper" data-testid={testId}>
          {renderSafeMarkdownSnippet(clampedText)}
        </div>
      );
    }

    case 'url': {
      const rawUrl = safeString(value).trim();
      let isValidScheme = false;
      let hostname = rawUrl;

      try {
        const parsed = new URL(rawUrl);
        if (parsed.protocol === 'https:' || parsed.protocol === 'http:') {
          isValidScheme = true;
          hostname = parsed.hostname;
        }
      } catch {
        isValidScheme = false;
      }

      if (!isValidScheme) {
        return (
          <span className="custom-field-url-text" data-testid={testId}>
            {rawUrl}
          </span>
        );
      }

      return (
        <a
          href={rawUrl}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="custom-field-url-link"
          data-testid={testId}
        >
          {hostname}
        </a>
      );
    }

    case 'json_table': {
      if (!Array.isArray(value) || value.length === 0) {
        return (
          <span className="custom-field-empty-table" data-testid={testId}>
            No table data
          </span>
        );
      }

      const rawRows = value as Record<string, unknown>[];
      const maxRows =
        typeof metadata?.max_rows === 'number' && metadata.max_rows > 0
          ? Math.min(metadata.max_rows, 50)
          : 50;

      // Columns from metadata or inferred from first row (max 10 columns)
      let columns: { key: string; label: string }[] = [];
      if (Array.isArray(metadata?.columns) && metadata.columns.length > 0) {
        columns = (metadata.columns as { key: string; label: string }[]).slice(0, 10);
      } else {
        const firstRow = rawRows[0] ?? {};
        columns = Object.keys(firstRow)
          .slice(0, 10)
          .map((k) => ({ key: k, label: k }));
      }

      const visibleRows = rawRows.slice(0, maxRows);
      const overflowCount = rawRows.length - visibleRows.length;

      return (
        <div className="custom-field-table-container" data-testid={testId}>
          <table className="custom-field-table">
            <thead>
              <tr>
                {columns.map((col) => (
                  <th key={col.key} className="custom-field-th">
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, rowIdx) => (
                <tr key={`row-${String(rowIdx)}`}>
                  {columns.map((col) => {
                    const cellVal = row[col.key];
                    const cellText =
                      cellVal !== null && cellVal !== undefined ? safeString(cellVal) : '';
                    return (
                      <td key={col.key} className="custom-field-td">
                        {cellText}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {overflowCount > 0 && (
            <div className="custom-field-table-overflow">
              +{String(overflowCount)} more rows
            </div>
          )}
        </div>
      );
    }

    case 'severity_pill': {
      let level = '';
      let score: number | undefined;
      let label: string | undefined;

      if (typeof value === 'object') {
        const obj = value as { level?: string; score?: number; label?: string };
        level = (obj.level ?? '').toLowerCase();
        score = typeof obj.score === 'number' && Number.isFinite(obj.score) ? obj.score : undefined;
        label = typeof obj.label === 'string' ? obj.label : undefined;
      } else if (typeof value === 'string') {
        level = value.toLowerCase();
      } else {
        level = safeString(value).toLowerCase();
      }

      const colorClass = SEVERITY_CLASSES[level];
      if (!colorClass) {
        return (
          <span className="custom-field-unavailable" data-testid={testId}>
            Unavailable
          </span>
        );
      }

      const displayScore = score !== undefined ? score.toFixed(1) : null;
      let displayLabel = label ?? (level.charAt(0).toUpperCase() + level.slice(1));
      if (displayScore && displayLabel.startsWith(displayScore)) {
        const trimmed = displayLabel.slice(displayScore.length).trimStart();
        if (trimmed) {
          displayLabel = trimmed;
        }
      }

      return (
        <span
          className={`custom-field-severity-pill ${colorClass}`}
          data-testid={testId}
          data-level={level}
        >
          {displayScore && <span className="custom-field-severity-score">{displayScore}</span>}
          <span className="custom-field-severity-label">{displayLabel}</span>
        </span>
      );
    }

    default:
      return (
        <span className="custom-field-unavailable" data-testid={testId}>
          Unavailable
        </span>
      );
  }
}
