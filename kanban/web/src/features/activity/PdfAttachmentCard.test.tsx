import { describe, it, expect } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { PdfAttachmentCard, formatByteSize } from './PdfAttachmentCard';

describe('PdfAttachmentCard', () => {
  it('renders complete metadata including page count, size, and truncated SHA', () => {
    render(
      <PdfAttachmentCard
        filename="system-architecture.pdf"
        downloadUrl="/api/v1/attachments/att_12345"
        byteSize={2_500_000}
        pageCount={12}
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
      />,
    );

    expect(screen.getByText('system-architecture.pdf')).toBeDefined();
    expect(screen.getByText('2.4 MB')).toBeDefined();
    expect(screen.getByText('12 pages')).toBeDefined();
    expect(screen.getByText('sha256:e3b0c442')).toBeDefined();

    const link = screen.getByRole('link', { name: 'Download system-architecture.pdf' });
    expect(link.getAttribute('href')).toBe('/api/v1/attachments/att_12345');
    expect(link.getAttribute('download')).toBe('system-architecture.pdf');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('renders singular 1 page correctly', () => {
    render(
      <PdfAttachmentCard
        filename="single-page.pdf"
        downloadUrl="/api/v1/attachments/att_999"
        pageCount={1}
        byteSize={512}
      />,
    );
    expect(screen.getByText('1 page')).toBeDefined();
    expect(screen.getByText('512 B')).toBeDefined();
  });

  it('handles formatByteSize boundary values', () => {
    expect(formatByteSize(undefined)).toBe('');
    expect(formatByteSize(0)).toBe('');
    expect(formatByteSize(-10)).toBe('');
    expect(formatByteSize(500)).toBe('500 B');
    expect(formatByteSize(1024)).toBe('1.0 KB');
    expect(formatByteSize(1024 * 1024 * 2)).toBe('2.0 MB');
  });

  it('renders gracefully when optional metadata is omitted', () => {
    render(
      <PdfAttachmentCard
        filename="minimal.pdf"
        downloadUrl="/api/v1/attachments/min"
      />,
    );
    expect(screen.getByText('minimal.pdf')).toBeDefined();
    expect(screen.queryByText(/page/i)).toBeNull();
    expect(screen.queryByText(/sha256:/i)).toBeNull();
  });
});
