import { describe, it, expect } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { PdfAttachmentCard, formatByteSize } from './PdfAttachmentCard';

describe('PdfAttachmentCard backwards-compatibility re-export', () => {
  it('renders re-exported component identically with download=1 parameter', () => {
    render(
      <PdfAttachmentCard
        filename="legacy-import.pdf"
        downloadUrl="/api/v1/attachments/att_legacy"
        byteSize={1024}
        pageCount={1}
      />,
    );

    expect(screen.getByText('legacy-import.pdf')).toBeDefined();
    expect(screen.getByText('1.0 KB')).toBeDefined();
    expect(screen.getByText('1 page')).toBeDefined();
    const link = screen.getByRole('link', { name: 'Download legacy-import.pdf' });
    expect(link.getAttribute('href')).toBe('/api/v1/attachments/att_legacy?download=1');
  });

  it('verifies formatByteSize re-export', () => {
    expect(formatByteSize(2048)).toBe('2.0 KB');
  });
});
