import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import {
  SafeMarkdownPreview,
  registerCommentBodyRenderer,
  getCommentBodyRenderer,
} from './SafeMarkdownPreview';

describe('SafeMarkdownPreview', () => {
  beforeEach(() => {
    registerCommentBodyRenderer(null);
  });

  describe('Test Case 5: Negative / security & rendering', () => {
    it('neutralizes HTML tags (<script>, <img>) by rendering them as escaped text without DOM nodes', () => {
      const malicious = '<script>alert(1)</script><img src="x" onerror="alert(1)" />';
      const { container } = render(<SafeMarkdownPreview markdown={malicious} />);

      expect(container.querySelector('script')).toBeNull();
      expect(container.querySelector('img')).toBeNull();
      expect(container.textContent).toContain('<script>alert(1)</script>');
    });

    it('strips javascript: and vbscript: URIs to plain text without creating clickable links', () => {
      const maliciousLinks = '[click me](javascript:alert(1)) and [vbs](vbscript:evil())';
      const { container } = render(<SafeMarkdownPreview markdown={maliciousLinks} />);

      const links = container.querySelectorAll('a');
      expect(links.length).toBe(0);
      expect(container.textContent).toContain('click me and vbs');
    });

    it('renders safe https: and mailto: links with noopener noreferrer', () => {
      const markdown = 'Visit [Google](https://google.com) or email [Support](mailto:support@example.com)';
      render(<SafeMarkdownPreview markdown={markdown} />);

      const link = screen.getByRole('link', { name: 'Google' });
      expect(link.getAttribute('href')).toBe('https://google.com');
      expect(link.getAttribute('rel')).toBe('noopener noreferrer');

      const mailLink = screen.getByRole('link', { name: 'Support' });
      expect(mailLink.getAttribute('href')).toBe('mailto:support@example.com');
    });

    it('renders fenced code blocks and inline code safely', () => {
      const markdown = 'Here is inline `const x = 42;` and a block:\n\n```typescript\nfunction hello() {\n  return "world";\n}\n```';
      const { container } = render(<SafeMarkdownPreview markdown={markdown} />);

      const inlineCode = screen.getByText('const x = 42;');
      expect(inlineCode.tagName.toLowerCase()).toBe('code');

      const pre = container.querySelector('pre');
      expect(pre).not.toBeNull();
      expect(pre?.textContent).toContain('function hello()');
    });

    it('renders unordered lists with bullet markers', () => {
      const markdown = '- First item\n- Second item\n* Third item';
      const { container } = render(<SafeMarkdownPreview markdown={markdown} />);

      const listItems = container.querySelectorAll('li');
      expect(listItems.length).toBe(3);
      expect(screen.getByText('First item')).toBeDefined();
      expect(screen.getByText('Second item')).toBeDefined();
      expect(screen.getByText('Third item')).toBeDefined();
    });

    it('renders ordered numbered lists with numbers', () => {
      const markdown = '1. First ordered item\n2. Second ordered item';
      const { container } = render(<SafeMarkdownPreview markdown={markdown} />);

      const listItems = container.querySelectorAll('ol li');
      expect(listItems.length).toBe(2);
      expect(screen.getByText('First ordered item')).toBeDefined();
      expect(screen.getByText('Second ordered item')).toBeDefined();
    });

    it('exposes getCommentBodyRenderer', () => {
      expect(getCommentBodyRenderer()).toBeNull();
    });

    it('handles empty paragraphs and multiline whitespace gracefully', () => {
      const { container } = render(<SafeMarkdownPreview markdown={"\n\n   \n\nParagraph 1\n\n\n\nParagraph 2\n\n"} />);
      const paragraphs = container.querySelectorAll('p');
      expect(paragraphs.length).toBe(2);
    });

    it('renders bold and italic formatting', () => {
      const markdown = 'This is **bold** and *italic* text.';
      render(<SafeMarkdownPreview markdown={markdown} />);

      const boldEl = screen.getByText('bold');
      expect(boldEl.tagName.toLowerCase()).toBe('strong');

      const italicEl = screen.getByText('italic');
      expect(italicEl.tagName.toLowerCase()).toBe('em');
    });

    it('renders PDF attachment links as PdfAttachmentCard', () => {
      const markdown = 'See attached doc: [specification.pdf](attachment://att_spec_1)';
      render(<SafeMarkdownPreview markdown={markdown} />);

      expect(screen.getByTestId('p-0-pdf-0')).toBeDefined();
      expect(screen.getByText('specification.pdf')).toBeDefined();
      const link = screen.getByRole('link', { name: 'Download specification.pdf' });
      expect(link.getAttribute('href')).toBe('/api/v1/attachments/spec_1');
      expect(link.getAttribute('download')).toBe('specification.pdf');
    });

    it('supports pluggable custom renderer via registerCommentBodyRenderer', () => {
      registerCommentBodyRenderer((md) => {
        if (md.startsWith('CUSTOM:')) {
          return <div data-testid="custom-rendered">{md.slice(7)}</div>;
        }
        return null;
      });

      try {
        const { unmount } = render(<SafeMarkdownPreview markdown="CUSTOM:Hello Custom" />);
        expect(screen.getByTestId('custom-rendered').textContent).toBe('Hello Custom');
        unmount();

        // Default markdown still falls back
        render(<SafeMarkdownPreview markdown="Regular text" />);
        expect(screen.getByText('Regular text')).toBeDefined();
      } finally {
        registerCommentBodyRenderer(null);
      }

      // After unregister, custom prefix renders as standard markdown
      render(<SafeMarkdownPreview markdown="CUSTOM:Hello Custom 2" />);
      expect(screen.queryByTestId('custom-rendered')).toBeNull();
      expect(screen.getByText(/CUSTOM:Hello Custom 2/)).toBeDefined();
    });

    it('renders Markdown images via MediaViewport and disarms unsafe image urls', () => {
      const markdown = 'Here is a photo: ![Sample Photo](https://example.com/photo.png) and unsafe: ![Evil](javascript:alert(1)) and no alt: ![](https://example.com/empty.png) and unsafe no alt: ![](javascript:void(0))';
      const { container } = render(<SafeMarkdownPreview markdown={markdown} />);

      // MediaViewport should be rendered for safe URL
      const mediaViewport = container.querySelector('.media-viewport');
      expect(mediaViewport).not.toBeNull();

      // Unsafe image scheme is converted to alt text
      expect(container.textContent).toContain('Evil');

      // Whitespace only lines before code block
      const wsBeforeBlock = '   \n   \n```\ncode\n```\n   ';
      const { container: wsContainer } = render(<SafeMarkdownPreview markdown={wsBeforeBlock} />);
      expect(wsContainer.querySelector('pre')).not.toBeNull();
    });

    it('renders fenced svg code blocks via MediaViewport and handles unclosed code blocks', () => {
      const svgMarkdown = '```svg\n<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="5"/></svg>\n```';
      const { container: svgContainer } = render(<SafeMarkdownPreview markdown={svgMarkdown} />);
      expect(svgContainer.querySelector('.media-viewport')).not.toBeNull();

      // Code block without language tag
      const noLangMarkdown = '```\nplain code block\n```';
      const { container: noLangContainer } = render(<SafeMarkdownPreview markdown={noLangMarkdown} />);
      const codeEl = noLangContainer.querySelector('code');
      expect(codeEl).not.toBeNull();
      expect(codeEl?.className).toBe('');

      // Unclosed code block with and without language
      const unclosedMarkdown = '```python\nprint("hello")';
      const { container: unclosedContainer } = render(<SafeMarkdownPreview markdown={unclosedMarkdown} />);
      expect(unclosedContainer.querySelector('pre')).not.toBeNull();
      expect(unclosedContainer.textContent).toContain('print("hello")');

      const unclosedNoLang = '```\nprint("unclosed no lang")';
      const { container: unclosedNoLangContainer } = render(<SafeMarkdownPreview markdown={unclosedNoLang} />);
      expect(unclosedNoLangContainer.querySelector('pre')).not.toBeNull();
    });

    it('renders fenced mermaid code blocks via MermaidBlockView with CRLF and case normalization', () => {
      const mermaidMarkdown = '```MERMAID\r\ngraph TD;\r\n  A-->B;\r\n```';
      render(<SafeMarkdownPreview markdown={mermaidMarkdown} />);
      const mermaidEl = screen.getByTestId('mermaid-block');
      expect(mermaidEl).toBeDefined();
      expect(mermaidEl.getAttribute('data-lang')).toBe('mermaid');
      expect(screen.queryByTestId('mermaid-block-toggle-btn')).toBeNull();
    });
  });
});
