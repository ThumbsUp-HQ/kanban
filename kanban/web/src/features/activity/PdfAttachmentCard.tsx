/**
 * PDF Attachment Card Component (KB-ATTACH-PDF-01, S5.4).
 * Renders verified metadata for PDF attachments with zero-canvas forced-download UX.
 */

import React, { type JSX } from 'react';
import './PdfAttachmentCard.css';

export interface PdfAttachmentCardProps {
  readonly filename: string;
  readonly downloadUrl: string;
  readonly byteSize?: number | undefined;
  readonly pageCount?: number | null | undefined;
  readonly sha256?: string | undefined;
  readonly testId?: string | undefined;
}

export function formatByteSize(bytes: number | undefined): string {
  if (bytes === undefined || bytes <= 0) {
    return '';
  }
  if (bytes < 1024) {
    return `${String(bytes)} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function PdfAttachmentCard({
  filename,
  downloadUrl,
  byteSize,
  pageCount,
  sha256,
  testId = 'pdf-attachment-card',
}: PdfAttachmentCardProps): JSX.Element {
  const formattedSize = formatByteSize(byteSize);
  const truncatedSha = sha256 ? sha256.replace(/^sha256:/i, '').slice(0, 8) : null;

  return (
    <span
      className="kb-pdf-card"
      data-testid={testId}
      role="region"
      aria-label={`PDF Attachment: ${filename}`}
    >
      <span className="kb-pdf-card__icon" aria-hidden="true">
        <span>📄</span>
      </span>
      <span className="kb-pdf-card__details">
        <span className="kb-pdf-card__filename" title={filename}>
          {filename}
        </span>
        <span className="kb-pdf-card__meta">
          {formattedSize ? (
            <span className="kb-pdf-card__badge kb-pdf-card__size">{formattedSize}</span>
          ) : null}
          {pageCount && pageCount > 0 ? (
            <span className="kb-pdf-card__badge kb-pdf-card__pages">
              {String(pageCount)} {pageCount === 1 ? 'page' : 'pages'}
            </span>
          ) : null}
          {truncatedSha && sha256 ? (
            <span className="kb-pdf-card__badge kb-pdf-card__sha" title={`SHA-256: ${sha256}`}>
              sha256:{truncatedSha}
            </span>
          ) : null}
        </span>
      </span>
      <span className="kb-pdf-card__actions">
        <a
          href={downloadUrl}
          download={filename}
          className="kb-pdf-card__download"
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Download ${filename}`}
          data-testid={`${testId}-download`}
        >
          ⬇ Download
        </a>
      </span>
    </span>
  );
}
