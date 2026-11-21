/**
 * Deterministic zero-HTML safe Markdown preview renderer for comments (KB-P3-44, S5.1).
 * Supports paragraphs, inline code, fenced code blocks, lists, and safe links (http/https/mailto).
 * Exposes registerCommentBodyRenderer for future Phase 3C rich extensions.
 */

import React, { type JSX, type ReactNode } from 'react';
import { MediaViewport } from '../../editor/media/MediaViewport';
import { MermaidBlockView } from '../../editor/mermaid/MermaidBlockView';
import { resolveMediaUrl } from '../../editor/media/mediaUrlResolver';
import { PdfAttachmentCard } from './PdfAttachmentCard';

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
        const lowerUrl = linkUrl.toLowerCase();
        const lowerText = linkText.toLowerCase();
        const isPdfAttachment =
          (lowerUrl.startsWith('attachment://') || lowerUrl.includes('/attachments/')) &&
          (lowerText.endsWith('.pdf') || lowerUrl.endsWith('.pdf'));

        if (isPdfAttachment) {
          const resolved = resolveMediaUrl(linkUrl);
          nodes.push(
            <PdfAttachmentCard
              key={`${keyPrefix}-pdf-${String(tokenIdx)}`}
              filename={linkText}
              downloadUrl={resolved.url}
              testId={`${keyPrefix}-pdf-${String(tokenIdx)}`}
            />,
          );
        } else {
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
        }
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
  const normalized = markdown.replace(/\r\n/g, '\n');
  const lines = normalized.split('\n');
  let inCodeBlock = false;
  let codeLang = '';
  let codeLines: string[] = [];
  let textLines: string[] = [];
  let blockIdx = 0;

  const flushTextLines = (): void => {
    if (textLines.length === 0) return;
    const rawLines = textLines;
    textLines = [];

    let currentListType: 'ul' | 'ol' | null = null;
    let listItems: string[] = [];
    let paraLines: string[] = [];

    const flushList = (): void => {
      if (currentListType === null || listItems.length === 0) return;
      if (currentListType === 'ul') {
        const uIdx = blockIdx++;
        blocks.push(
          <ul key={`ul-${String(uIdx)}`} className="safe-md__ul">
            {listItems.map((item, idx) => (
              <li key={`li-${String(idx)}`}>
                {renderInlineContent(item, `ul-${String(uIdx)}-${String(idx)}`)}
              </li>
            ))}
          </ul>,
        );
      } else {
        const oIdx = blockIdx++;
        blocks.push(
          <ol key={`ol-${String(oIdx)}`} className="safe-md__ol">
            {listItems.map((item, idx) => (
              <li key={`li-${String(idx)}`}>
                {renderInlineContent(item, `ol-${String(oIdx)}-${String(idx)}`)}
              </li>
            ))}
          </ol>,
        );
      }
      currentListType = null;
      listItems = [];
    };

    const flushParagraph = (): void => {
      if (paraLines.length === 0) return;
      const text = paraLines.join('\n').trim();
      paraLines = [];
      if (!text) return;

      const pIdx = blockIdx++;
      const content = renderInlineContent(text, `p-${String(pIdx)}`);
      const hasMedia = text.includes('![');
      if (hasMedia) {
        blocks.push(
          <div key={`p-${String(pIdx)}`} className="safe-md__p safe-md__media-block">
            {content}
          </div>,
        );
      } else {
        blocks.push(
          <p key={`p-${String(pIdx)}`} className="safe-md__p">
            {content}
          </p>,
        );
      }
    };

    for (const rawLine of rawLines) {
      const trimmed = rawLine.trim();
      if (!trimmed) {
        flushList();
        flushParagraph();
        continue;
      }

      // Check Heading: # through ######
      const headingMatch = /^(#{1,6})\s+(.+)$/.exec(trimmed);
      if (headingMatch) {
        flushList();
        flushParagraph();
        const level = (headingMatch[1] ?? '').length;
        const titleText = headingMatch[2] ?? '';
        const hIdx = blockIdx++;
        const content = renderInlineContent(titleText, `h-${String(hIdx)}`);
        const headingClassName = `safe-md__h${String(level)}`;
        switch (level) {
          case 1:
            blocks.push(<h1 key={`h-${String(hIdx)}`} className={headingClassName}>{content}</h1>);
            break;
          case 2:
            blocks.push(<h2 key={`h-${String(hIdx)}`} className={headingClassName}>{content}</h2>);
            break;
          case 3:
            blocks.push(<h3 key={`h-${String(hIdx)}`} className={headingClassName}>{content}</h3>);
            break;
          case 4:
            blocks.push(<h4 key={`h-${String(hIdx)}`} className={headingClassName}>{content}</h4>);
            break;
          case 5:
            blocks.push(<h5 key={`h-${String(hIdx)}`} className={headingClassName}>{content}</h5>);
            break;
          default:
            blocks.push(<h6 key={`h-${String(hIdx)}`} className={headingClassName}>{content}</h6>);
            break;
        }
        continue;
      }

      // Check Unordered List item: - or *
      const bulletMatch = /^[-*]\s+(.+)$/.exec(trimmed);
      if (bulletMatch) {
        if (currentListType !== 'ul') {
          flushList();
          flushParagraph();
          currentListType = 'ul';
        }
        listItems.push(bulletMatch[1] ?? '');
        continue;
      }

      // Check Ordered List item: \d+\.
      const orderedMatch = /^\d+\.\s+(.+)$/.exec(trimmed);
      if (orderedMatch) {
        if (currentListType !== 'ol') {
          flushList();
          flushParagraph();
          currentListType = 'ol';
        }
        listItems.push(orderedMatch[1] ?? '');
        continue;
      }

      // Plain text line: if in list, end list
      if (currentListType !== null) {
        flushList();
      }
      paraLines.push(trimmed);
    }

    flushList();
    flushParagraph();
  };

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      if (inCodeBlock) {
        // Closing code block
        if (codeLang === 'mermaid') {
          blocks.push(
            <MermaidBlockView
              key={`mermaid-${String(blockIdx++)}`}
              source={codeLines.join('\n')}
              readOnly={true}
            />,
          );
        } else if (codeLang === 'svg') {
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
        codeLang = trimmed.slice(3).trim().toLowerCase();
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
