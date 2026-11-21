/**
 * PDF Attachment Card Component (KB-ATTACH-PDF-01, S5.4).
 * Renders verified metadata for PDF attachments with zero-canvas forced-download UX.
 */

import React, { useEffect, useState, type JSX } from 'react';
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

interface AttachmentMetaFetched {
  byte_size?: number;
  page_count?: number | null;
  blob_sha256?: string;
}

export function PdfAttachmentCard({
  filename,
  downloadUrl,
  byteSize: initialByteSize,
  pageCount: initialPageCount,
  sha256: initialSha256,
  testId = 'pdf-attachment-card',
}: PdfAttachmentCardProps): JSX.Element {
  const [fetchedMeta, setFetchedMeta] = useState<AttachmentMetaFetched | null>(null);

  useEffect(() => {
    if (initialByteSize !== undefined && initialPageCount !== undefined && initialSha256 !== undefined) {
      return;
    }

    const match =
      /\/attachments\/([0-9a-fA-F-]+)/i.exec(downloadUrl) ??
      /att_([0-9a-fA-F-]+)/i.exec(downloadUrl);
    const attId = match?.[1];
    if (!attId) {
      return;
    }

    let active = true;

    fetch(`/api/v1/attachments/${encodeURIComponent(attId)}/meta`, { credentials: 'same-origin' })
      .then((res) => (res.ok ? (res.json() as Promise<AttachmentMetaFetched>) : null))
      .then((data) => {
        if (active && data) {
          setFetchedMeta(data);
        }
      })
      .catch(() => {
        // Ignore fetch errors gracefully
      });

    return () => {
      active = false;
    };
  }, [downloadUrl, initialByteSize, initialPageCount, initialSha256]);

  const effectiveByteSize = initialByteSize ?? fetchedMeta?.byte_size;
  const effectivePageCount = initialPageCount ?? fetchedMeta?.page_count;
  const effectiveSha256 = initialSha256 ?? fetchedMeta?.blob_sha256;

  const formattedSize = formatByteSize(effectiveByteSize);
  const truncatedSha = effectiveSha256
    ? effectiveSha256.replace(/^sha256:/i, '').slice(0, 8)
    : null;

  // Append ?download=1 (or &download=1 if URL already contains query parameters)
  const hrefWithDownload = downloadUrl.includes('download=1')
    ? downloadUrl
    : downloadUrl.includes('?')
      ? `${downloadUrl}&download=1`
      : `${downloadUrl}?download=1`;

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
          {effectivePageCount && effectivePageCount > 0 ? (
            <span className="kb-pdf-card__badge kb-pdf-card__pages">
              {String(effectivePageCount)} {effectivePageCount === 1 ? 'page' : 'pages'}
            </span>
          ) : null}
          {truncatedSha && effectiveSha256 ? (
            <span
              className="kb-pdf-card__badge kb-pdf-card__sha"
              title={`SHA-256: ${effectiveSha256}`}
            >
              sha256:{truncatedSha}
            </span>
          ) : null}
        </span>
      </span>
      <span className="kb-pdf-card__actions">
        <a
          href={hrefWithDownload}
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
