/**
 * Deterministic zero-HTML safe Markdown preview renderer for comments (KB-P3-44, S5.1).
 * Supports paragraphs, inline code, fenced code blocks, lists, and safe links (http/https/mailto).
 * Exposes registerCommentBodyRenderer for future Phase 3C rich extensions.
 */

import React, { type JSX, type ReactNode } from 'react';
import { MediaViewport } from '../../editor/media/MediaViewport';

export type CommentBodyRenderer = (markdown: string) => ReactNode;

let customRenderer: CommentBodyRenderer | null = null;

export function registerCommentBodyRenderer(renderer: CommentBodyRenderer | null): void {
  customRenderer = renderer;
}

export function getCommentBodyRenderer(): CommentBodyRenderer | null {
  return customRenderer;
}

interface SafeMarkdownPreviewProps {
  readonly markdown: string;
  readonly className?: string;
}

function isSafeUrl(url: string): boolean {
  const lower = url.trim().toLowerCase();
  return (
    lower.startsWith('https://') ||
    lower.startsWith('http://') ||
    lower.startsWith('mailto:') ||
    lower.startsWith('blob:') ||
    lower.startsWith('attachment://') ||
    lower.startsWith('/api/') ||
    lower.startsWith('/')
  );
}

export function renderInlineContent(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  // Tokenize images ![alt](url), code spans `...`, links [text](url), bold **...**, italic *...*
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
      imgUrl,
      codeSpan,
      linkMatch,
      linkText,
      linkUrl,
      ,
      boldText,
      ,
      italicText,
    ] = match;

    if (imgMatch && imgUrl) {
      if (isSafeUrl(imgUrl)) {
        nodes.push(
          <MediaViewport
            key={`${keyPrefix}-media-${String(tokenIdx)}`}
            src={imgUrl}
            alt={imgAlt ?? ''}
            testId={`${keyPrefix}-media-${String(tokenIdx)}`}
          />,
        );
      } else {
        nodes.push(imgAlt ?? '');
      }
    } else if (codeSpan) {
      nodes.push(
        <code key={`${keyPrefix}-code-${String(tokenIdx)}`} className="safe-md__inline-code">
          {codeSpan.slice(1, -1)}
        </code>,
      );
    } else if (linkMatch && linkText && linkUrl) {
      if (isSafeUrl(linkUrl)) {
        nodes.push(
          <a
            key={`${keyPrefix}-link-${String(tokenIdx)}`}
            href={linkUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="safe-md__link"
          >
            {linkText}
          </a>,
        );
      } else {
        // Strip unsafe schemes like javascript: to plain text
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

export function SafeMarkdownPreview({
  markdown,
  className = 'safe-md-preview',
}: SafeMarkdownPreviewProps): JSX.Element {
  if (customRenderer) {
    const customResult = customRenderer(markdown);
    if (customResult !== null && customResult !== undefined) {
      return <div className={className}>{customResult}</div>;
    }
  }

  // Parse blocks: fenced code blocks vs standard blocks
  const blocks: ReactNode[] = [];
  const lines = markdown.split('\n');
  let inCodeBlock = false;
  let codeLang = '';
  let codeLines: string[] = [];
  let textLines: string[] = [];
  let blockIdx = 0;

  const flushTextLines = (): void => {
    if (textLines.length === 0) return;
    const text = textLines.join('\n').trim();
    textLines = [];
    if (!text) return;

    // Check if it's a list
    const sublines = text.split('\n');
    const isBulletList = sublines.every((l) => l.trim().startsWith('- ') || l.trim().startsWith('* '));
    const isNumberedList = sublines.every((l) => /^\d+\.\s/.test(l.trim()));

    if (isBulletList) {
      blocks.push(
        <ul key={`ul-${String(blockIdx++)}`} className="safe-md__ul">
          {sublines.map((l, i) => (
            <li key={`li-${String(i)}`}>
              {renderInlineContent(l.trim().replace(/^[-*]\s+/, ''), `ul-${String(blockIdx)}-${String(i)}`)}
            </li>
          ))}
        </ul>,
      );
    } else if (isNumberedList) {
      blocks.push(
        <ol key={`ol-${String(blockIdx++)}`} className="safe-md__ol">
          {sublines.map((l, i) => (
            <li key={`li-${String(i)}`}>
              {renderInlineContent(l.trim().replace(/^\d+\.\s+/, ''), `ol-${String(blockIdx)}-${String(i)}`)}
            </li>
          ))}
        </ol>,
      );
    } else {
      // Split into paragraphs by blank lines
      const paragraphs = text.split(/\n\s*\n/).filter((p) => p.trim() !== '');
      paragraphs.forEach((p, pIdx) => {
        const content = renderInlineContent(p.trim(), `p-${String(blockIdx)}-${String(pIdx)}`);
        const hasMedia = p.includes('![');
        if (hasMedia) {
          blocks.push(
            <div key={`p-${String(blockIdx++)}-${String(pIdx)}`} className="safe-md__p safe-md__media-block">
              {content}
            </div>,
          );
        } else {
          blocks.push(
            <p key={`p-${String(blockIdx++)}-${String(pIdx)}`} className="safe-md__p">
              {content}
            </p>,
          );
        }
      });
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      if (inCodeBlock) {
        // Closing code block
        if (codeLang === 'svg') {
          const rawSvg = codeLines.join('\n');
          const dataUri = `data:image/svg+xml;utf8,${encodeURIComponent(rawSvg)}`;
          blocks.push(
            <MediaViewport
              key={`svg-${String(blockIdx++)}`}
              src={dataUri}
              rawSource={rawSvg}
              testId={`safe-md-svg-${String(blockIdx)}`}
            />,
          );
        } else {
          blocks.push(
            <pre key={`code-${String(blockIdx++)}`} className="safe-md__code-block">
              <code className={codeLang ? `language-${codeLang}` : undefined}>
                {codeLines.join('\n')}
              </code>
            </pre>,
          );
        }
        inCodeBlock = false;
        codeLang = '';
        codeLines = [];
      } else {
        // Opening code block
        flushTextLines();
        inCodeBlock = true;
        codeLang = trimmed.slice(3).trim();
        codeLines = [];
      }
    } else if (inCodeBlock) {
      codeLines.push(line);
    } else {
      textLines.push(line);
    }
  }

  if (inCodeBlock) {
    blocks.push(
      <pre key={`code-${String(blockIdx++)}`} className="safe-md__code-block">
        <code className={codeLang ? `language-${codeLang}` : undefined}>
          {codeLines.join('\n')}
        </code>
      </pre>,
    );
  } else {
    flushTextLines();
  }

  return <div className={className}>{blocks}</div>;
}
