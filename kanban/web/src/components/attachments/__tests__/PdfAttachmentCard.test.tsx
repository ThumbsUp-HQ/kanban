import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { PdfAttachmentCard, formatByteSize } from '../PdfAttachmentCard';

describe('PdfAttachmentCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

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
    expect(link.getAttribute('href')).toBe('/api/v1/attachments/att_12345?download=1');
    expect(link.getAttribute('download')).toBe('system-architecture.pdf');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('appends &download=1 when downloadUrl already contains query parameters', () => {
    render(
      <PdfAttachmentCard
        filename="report.pdf"
        downloadUrl="/api/v1/attachments/att_123?auth=token"
        byteSize={1024}
        pageCount={1}
      />,
    );

    const link = screen.getByRole('link', { name: 'Download report.pdf' });
    expect(link.getAttribute('href')).toBe('/api/v1/attachments/att_123?auth=token&download=1');
  });

  it('does not duplicate download=1 if already present', () => {
    render(
      <PdfAttachmentCard
        filename="report.pdf"
        downloadUrl="/api/v1/attachments/att_123?download=1"
        byteSize={1024}
      />,
    );

    const link = screen.getByRole('link', { name: 'Download report.pdf' });
    expect(link.getAttribute('href')).toBe('/api/v1/attachments/att_123?download=1');
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

  it('renders gracefully when optional metadata is omitted and fetch fails or is absent', () => {
    render(
      <PdfAttachmentCard
        filename="minimal.pdf"
        downloadUrl="/external/minimal.pdf"
      />,
    );
    expect(screen.getByText('minimal.pdf')).toBeDefined();
    expect(screen.queryByText(/page/i)).toBeNull();
    expect(screen.queryByText(/sha256:/i)).toBeNull();
  });

  it('fetches metadata from /api/v1/attachments/{id}/meta when rendered without initial metadata', async () => {
    const mockMeta = {
      byte_size: 1048576,
      page_count: 5,
      blob_sha256: 'abcdef1234567890abcdef1234567890',
    };

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockMeta),
    } as Response);

    render(
      <PdfAttachmentCard
        filename="async-doc.pdf"
        downloadUrl="/api/v1/attachments/11111111-2222-3333-4444-555555555555"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('1.0 MB')).toBeDefined();
    });
    expect(screen.getByText('5 pages')).toBeDefined();
    expect(screen.getByText('sha256:abcdef12')).toBeDefined();
  });
});
