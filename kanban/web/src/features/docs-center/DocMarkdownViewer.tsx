// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { type JSX, type ReactNode } from 'react';
import { MermaidBlockView } from '../../editor/mermaid/MermaidBlockView';
import { slugifyAnchor } from './docsService';
import './DocMarkdownViewer.css';

export interface DocMarkdownViewerProps {
  content: string;
  className?: string;
  testId?: string;
  onNavigateSection?: (anchor: string) => void;
}

function isSafeUrl(url: string): boolean {
  const lower = url.trim().toLowerCase();
  return (
    lower.startsWith('https://') ||
    lower.startsWith('http://') ||
    lower.startsWith('mailto:') ||
    lower.startsWith('#') ||
    lower.startsWith('/docs') ||
    lower.startsWith('/help') ||
    lower.startsWith('/')
  );
}

export function resolveSafeDocImageUrl(url: string): string | null {
  const trimmed = url.trim();
  const lower = trimmed.toLowerCase();
  // 0 external URLs allowed!
  if (
    lower.startsWith('http://') ||
    lower.startsWith('https://') ||
    lower.startsWith('//') ||
    lower.startsWith('data:') ||
    lower.startsWith('javascript:')
  ) {
    return null;
  }
  if (lower.startsWith('images/')) {
    return `/docs-images/${trimmed.slice('images/'.length)}`;
  }
  if (lower.startsWith('./images/')) {
    return `/docs-images/${trimmed.slice('./images/'.length)}`;
  }
  if (lower.startsWith('/docs-images/')) {
    return trimmed;
  }
  if (lower.startsWith('docs-images/')) {
    return `/${trimmed}`;
  }
  return null;
}

export function renderInlineMarkdown(
  text: string,
  keyPrefix: string,
  onNavigateSection?: (anchor: string) => void,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern =
    /(!\[([^\]]*)\]\(((?:[^()]+|\([^()]*\))*)\))|(`[^`]+`)|(\[([^\]]+)\]\(((?:[^()]+|\([^()]*\))*)\))|(\*\*([^*]+)\*\*)|(\*([^*]+)\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let tokenIdx = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const [
      ,
      imgMatch,
      imgAlt,
      imgSrc,
      codeSpan,
      linkMatch,
      linkText,
      linkUrl,
      ,
      boldText,
      ,
      italicText,
    ] = match;

    if (imgMatch !== undefined && imgSrc !== undefined) {
      const safeSrc = resolveSafeDocImageUrl(imgSrc);
      if (safeSrc) {
        const altLabel = (imgAlt ?? '').trim();
        nodes.push(
          <img
            key={`${keyPrefix}-img-${String(tokenIdx)}`}
            src={safeSrc}
            alt={altLabel.length > 0 ? altLabel : 'Documentation image'}
            className="kb-doc-image"
            loading="lazy"
            data-testid="doc-inline-image"
          />,
        );
      } else {
        nodes.push(imgAlt ?? '');
      }
    } else if (codeSpan) {
      nodes.push(
        <code key={`${keyPrefix}-code-${String(tokenIdx)}`} className="kb-doc-inline-code">
          {codeSpan.slice(1, -1)}
        </code>,
      );
    } else if (linkMatch && linkText && linkUrl) {
      if (isSafeUrl(linkUrl)) {
        if (linkUrl.startsWith('#') && onNavigateSection) {
          nodes.push(
            <a
              key={`${keyPrefix}-link-${String(tokenIdx)}`}
              href={linkUrl}
              className="kb-doc-link"
              onClick={(e) => {
                e.preventDefault();
                onNavigateSection(linkUrl.slice(1));
              }}
            >
              {linkText}
            </a>,
          );
        } else {
          nodes.push(
            <a
              key={`${keyPrefix}-link-${String(tokenIdx)}`}
              href={linkUrl}
              className="kb-doc-link"
              target={linkUrl.startsWith('http') ? '_blank' : undefined}
              rel={linkUrl.startsWith('http') ? 'noopener noreferrer' : undefined}
            >
              {linkText}
            </a>,
          );
        }
      } else {
        nodes.push(linkText);
      }
    } else if (boldText !== undefined) {
      nodes.push(<strong key={`${keyPrefix}-b-${String(tokenIdx)}`}>{boldText}</strong>);
    } else if (italicText !== undefined) {
      nodes.push(<em key={`${keyPrefix}-i-${String(tokenIdx)}`}>{italicText}</em>);
    }

    tokenIdx += 1;
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

function parseMarkdownTable(lines: string[], keyPrefix: string): JSX.Element | null {
  if (lines.length < 2) return null;
  /* v8 ignore next */
  const headerLine = lines[0];
  if (!headerLine) return null;
  const bodyLines = lines.slice(2); // skip separator line | :--- | :--- |

  const splitCells = (line: string): string[] => {
    return line
      .trim()
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((c) => c.trim());
  };

  const headers = splitCells(headerLine);

  return (
    <div key={keyPrefix} className="kb-doc-table-container">
      <table className="kb-doc-table">
        <thead>
          <tr className="kb-doc-tr">
            {headers.map((h, i) => (
              <th key={`th-${String(i)}`} className="kb-doc-th">
                {renderInlineMarkdown(h, `${keyPrefix}-th-${String(i)}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bodyLines.map((b, rowIdx) => {
            const cells = splitCells(b);
            return (
              <tr key={`tr-${String(rowIdx)}`} className="kb-doc-tr">
                {cells.map((cell, colIdx) => (
                  <td key={`td-${String(rowIdx)}-${String(colIdx)}`} className="kb-doc-td">
                    {renderInlineMarkdown(cell, `${keyPrefix}-td-${String(rowIdx)}-${String(colIdx)}`)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function DocMarkdownViewer({
  content,
  className = 'kb-doc-viewer',
  testId = 'kb-doc-viewer',
  onNavigateSection,
}: DocMarkdownViewerProps): JSX.Element {
  const blocks: ReactNode[] = [];
  const normalized = content.replace(/\r\n/g, '\n');
  const lines = normalized.split('\n');

  let inCodeBlock = false;
  let codeLang = '';
  let codeLines: string[] = [];
  let inTable = false;
  let tableLines: string[] = [];
  let blockquoteLines: string[] = [];
  let listLines: string[] = [];
  let isNumberedList = false;
  let textLines: string[] = [];
  let blockIdx = 0;

  const flushTextLines = (): void => {
    if (textLines.length === 0) return;
    const text = textLines.join('\n').trim();
    textLines = [];
    if (!text) return;

    const paragraphs = text.split(/\n\s*\n/).filter((p) => p.trim() !== '');
    paragraphs.forEach((p, pIdx) => {
      blocks.push(
        <p key={`p-${String(blockIdx++)}-${String(pIdx)}`} className="kb-doc-p">
          {renderInlineMarkdown(p.trim(), `p-${String(blockIdx)}-${String(pIdx)}`, onNavigateSection)}
        </p>,
      );
    });
  };

  const flushTable = (): void => {
    if (tableLines.length === 0) return;
    const tableEl = parseMarkdownTable(tableLines, `tbl-${String(blockIdx++)}`);
    if (tableEl) {
      blocks.push(tableEl);
    }
    tableLines = [];
    inTable = false;
  };

  const flushBlockquote = (): void => {
    if (blockquoteLines.length === 0) return;
    const bqText = blockquoteLines.join(' ').trim();
    blockquoteLines = [];
    blocks.push(
      <blockquote key={`bq-${String(blockIdx++)}`} className="kb-doc-blockquote">
        {renderInlineMarkdown(bqText, `bq-${String(blockIdx)}`, onNavigateSection)}
      </blockquote>,
    );
  };

  const flushList = (): void => {
    if (listLines.length === 0) return;
    const currentLines = [...listLines];
    const numbered = isNumberedList;
    listLines = [];
    isNumberedList = false;

    if (numbered) {
      blocks.push(
        <ol key={`ol-${String(blockIdx++)}`} className="kb-doc-ol">
          {currentLines.map((l, i) => (
            <li key={`li-${String(i)}`} className="kb-doc-li">
              {renderInlineMarkdown(
                l.trim().replace(/^\d+\.\s*/, ''),
                `ol-${String(blockIdx)}-${String(i)}`,
                onNavigateSection,
              )}
            </li>
          ))}
        </ol>,
      );
    } else {
      blocks.push(
        <ul key={`ul-${String(blockIdx++)}`} className="kb-doc-ul">
          {currentLines.map((l, i) => (
            <li key={`li-${String(i)}`} className="kb-doc-li">
              {renderInlineMarkdown(
                l.trim().replace(/^[-*]\s*/, ''),
                `ul-${String(blockIdx)}-${String(i)}`,
                onNavigateSection,
              )}
            </li>
          ))}
        </ul>,
      );
    }
  };

  const flushAll = (): void => {
    flushTable();
    flushBlockquote();
    flushList();
    flushTextLines();
  };

  for (const line of lines) {
    const trimmed = line.trim();

    // Code block toggle
    if (trimmed.startsWith('```')) {
      if (inCodeBlock) {
        if (codeLang === 'mermaid') {
          blocks.push(
            <MermaidBlockView
              key={`mermaid-${String(blockIdx++)}`}
              source={codeLines.join('\n')}
              readOnly={true}
            />,
          );
        } else {
          blocks.push(
            <pre key={`code-${String(blockIdx++)}`} className="kb-doc-code-block">
              <code className={`kb-doc-code ${codeLang ? `language-${codeLang}` : ''}`}>
                {codeLines.join('\n')}
              </code>
            </pre>,
          );
        }
        inCodeBlock = false;
        codeLang = '';
        codeLines = [];
      } else {
        flushAll();
        inCodeBlock = true;
        codeLang = trimmed.slice(3).trim().toLowerCase();
        codeLines = [];
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    // Markdown Table line
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      flushBlockquote();
      flushList();
      flushTextLines();
      inTable = true;
      tableLines.push(line);
      continue;
    } else if (inTable) {
      flushTable();
    }

    // Blockquote
    if (trimmed.startsWith('>')) {
      flushList();
      flushTextLines();
      blockquoteLines.push(trimmed.replace(/^>\s*/, ''));
      continue;
    } else if (blockquoteLines.length > 0) {
      flushBlockquote();
    }

    // Horizontal Rule
    if (trimmed === '---' || trimmed === '***' || trimmed === '___') {
      flushAll();
      blocks.push(<hr key={`hr-${String(blockIdx++)}`} className="kb-doc-hr" />);
      continue;
    }

    // Standalone Image Line
    const standaloneImgMatch = /^!\[([^\]]*)\]\(((?:[^()]+|\([^()]*\))*)\)$/.exec(trimmed);
    if (standaloneImgMatch?.[1] !== undefined && standaloneImgMatch[2] !== undefined) {
      flushAll();
      const altText = standaloneImgMatch[1].trim();
      const safeSrc = resolveSafeDocImageUrl(standaloneImgMatch[2]);
      if (safeSrc) {
        blocks.push(
          <figure key={`fig-${String(blockIdx++)}`} className="kb-doc-figure">
            <img
              src={safeSrc}
              alt={altText || 'Documentation media'}
              className="kb-doc-image"
              loading="lazy"
              data-testid="doc-image"
            />
            {altText && (
              <figcaption className="kb-doc-figcaption">{altText}</figcaption>
            )}
          </figure>,
        );
      }
      continue;
    }

    // Headings H1, H2, H3
    const h1Match = /^#\s+(.+)$/.exec(trimmed);
    if (h1Match?.[1] !== undefined) {
      flushAll();
      const rawTitle = h1Match[1].trim();
      const headingId = slugifyAnchor(rawTitle);
      blocks.push(
        <h1 key={`h1-${String(blockIdx++)}`} id={headingId} className="kb-doc-h1">
          {rawTitle}
        </h1>,
      );
      continue;
    }

    const h2Match = /^##\s+(.+)$/.exec(trimmed);
    if (h2Match?.[1] !== undefined) {
      flushAll();
      const rawTitle = h2Match[1].trim();
      const headingId = slugifyAnchor(rawTitle);
      blocks.push(
        <h2 key={`h2-${String(blockIdx++)}`} id={headingId} className="kb-doc-h2">
          {rawTitle}
          <a
            href={`#${headingId}`}
            className="kb-doc-anchor-link"
            aria-label={`Link to ${rawTitle}`}
            onClick={(e) => {
              if (onNavigateSection) {
                e.preventDefault();
                onNavigateSection(headingId);
              }
            }}
          >
            #
          </a>
        </h2>,
      );
      continue;
    }

    const h3Match = /^###\s+(.+)$/.exec(trimmed);
    if (h3Match?.[1] !== undefined) {
      flushAll();
      const rawTitle = h3Match[1].trim();
      const headingId = slugifyAnchor(rawTitle);
      blocks.push(
        <h3 key={`h3-${String(blockIdx++)}`} id={headingId} className="kb-doc-h3">
          {rawTitle}
          <a
            href={`#${headingId}`}
            className="kb-doc-anchor-link"
            aria-label={`Link to ${rawTitle}`}
            onClick={(e) => {
              if (onNavigateSection) {
                e.preventDefault();
                onNavigateSection(headingId);
              }
            }}
          >
            #
          </a>
        </h3>,
      );
      continue;
    }

    // Lists
    const isBulletItem = trimmed.startsWith('- ') || trimmed.startsWith('* ');
    const isNumberItem = /^\d+\.\s/.test(trimmed);

    if (isBulletItem || isNumberItem) {
      flushTextLines();
      if (listLines.length === 0) {
        isNumberedList = isNumberItem;
      }
      listLines.push(trimmed);
      continue;
    } else if (listLines.length > 0) {
      flushList();
    }

    // Blank line flushes paragraphs
    if (!trimmed) {
      flushTextLines();
      continue;
    }

    textLines.push(line);
  }

  flushAll();

  return (
    <div className={className} data-testid={testId}>
      {blocks}
    </div>
  );
}
