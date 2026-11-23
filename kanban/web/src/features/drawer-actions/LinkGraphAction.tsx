/**
 * LinkGraphAction component (KB-P3-43, S7.2 8m).
 *
 * `[🔗]` button with canonical URL copy, Cmd/Ctrl+Shift+C Markdown link copy,
 * and typed Object Graph links manager with restricted-target masking (🔒)
 * and broken link indicators (🕸️⚠️).
 */

import React, { useEffect, useRef, useState, type JSX } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { qk } from '../../api/queryKeys';
import { announce } from '../../api/RealtimeStatus';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type { IssueDetail } from '../drawer/slots';
import {
  USER_CREATABLE_LINK_TYPES,
  createObjectLink,
  deleteObjectLink,
  fetchCanonicalUrl,
  fetchObjectLinks,
  type CanonicalUrlResponse,
  type LinksListResponse,
  type OutboundLink,
} from './actionsApi';
import './drawerActions.css';

export interface LinkGraphActionProps {
  issue: IssueDetail;
}

function isEditableElement(element: Element | null): boolean {
  if (!element) return false;
  const tag = element.tagName.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
  return (element as HTMLElement).isContentEditable;
}

function safeWriteClipboard(text: string): void {
  const nav = navigator as unknown as {
    clipboard?: { writeText: (t: string) => Promise<void> };
  };
  if (nav.clipboard) {
    void nav.clipboard.writeText(text).catch(() => {
      // Ignore background clipboard errors
    });
  }
}

export function LinkGraphAction({ issue }: LinkGraphActionProps): JSX.Element {
  const queryClient = useQueryClient();
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [linkType, setLinkType] = useState<string>('RELATES_TO');
  const [targetRef, setTargetRef] = useState<string>('');
  const [linkError, setLinkError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const capabilities = (issue.capabilities && Array.isArray(issue.capabilities))
    ? issue.capabilities
    : ['EDIT', 'ADMIN'];
  const canEdit = capabilities.includes('EDIT') || capabilities.includes('ADMIN');

  const { data: canonical } = useQuery<CanonicalUrlResponse>({
    queryKey: qk.canonicalUrl(issue.key),
    queryFn: () => fetchCanonicalUrl(issue.key),
    staleTime: 60000,
  });

  const { data: linksData } = useQuery<LinksListResponse>({
    queryKey: qk.objectLinks(issue.key),
    queryFn: () => fetchObjectLinks(issue.key),
    staleTime: 10000,
    enabled: popoverOpen,
  });

  // Global shortcut Cmd/Ctrl+Shift+C
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent): void {
      if (
        (e.key === 'C' || e.key === 'c') &&
        (e.metaKey || e.ctrlKey) &&
        e.shiftKey &&
        !isEditableElement(document.activeElement)
      ) {
        e.preventDefault();
        const urlStr = canonical?.url ?? '';
        const mdText =
          canonical?.markdown !== undefined && canonical.markdown !== ''
            ? canonical.markdown
            : `[${issue.key}](${urlStr})`;
        safeWriteClipboard(mdText);
        announce(`Copied [${issue.key}](...) to clipboard`);
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => { window.removeEventListener('keydown', handleKeyDown); };
  }, [canonical, issue.key]);

  // Close popover on Escape or click outside
  useEffect(() => {
    if (!popoverOpen) return;

    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        setPopoverOpen(false);
      }
    }

    function handleClickOutside(e: MouseEvent): void {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setPopoverOpen(false);
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [popoverOpen]);

  const addLinkMutation = useMutation({
    mutationFn: async () => {
      setLinkError(null);
      return await createObjectLink(issue.key, targetRef.trim(), linkType);
    },
    onSuccess: () => {
      setTargetRef('');
      void queryClient.invalidateQueries({ queryKey: qk.objectLinks(issue.key) });
    },
    onError: (err: unknown) => {
      let msg = 'Failed to add link';
      if (err && typeof err === 'object') {
        const rec = err as Record<string, unknown>;
        if (typeof rec.detail === 'string') msg = rec.detail;
        else if (typeof rec.message === 'string') msg = rec.message;
      }
      setLinkError(msg);
    },
  });

  const deleteLinkMutation = useMutation({
    mutationFn: async (linkId: string) => {
      await deleteObjectLink(linkId);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.objectLinks(issue.key) });
    },
  });

  function handleCopyUrl(): void {
    const url = canonical?.url ?? '';
    if (url) {
      safeWriteClipboard(url);
    }
    announce('Copied URL to clipboard');
  }

  function handleCopyMarkdown(): void {
    const urlStr = canonical?.url ?? '';
    const md =
      canonical?.markdown !== undefined && canonical.markdown !== ''
        ? canonical.markdown
        : `[${issue.key}](${urlStr})`;
    safeWriteClipboard(md);
    announce(`Copied [${issue.key}](...) to clipboard`);
  }

  function handleAddLinkSubmit(e: React.SyntheticEvent): void {
    e.preventDefault();
    if (!targetRef.trim()) return;
    addLinkMutation.mutate();
  }

  const outboundLinks = linksData?.outbound ?? [];
  const inboundLinks = linksData?.inbound ?? [];

  return (
    <div className="link-graph-container" ref={containerRef}>
      <button
        type="button"
        className={`drawer-action-btn ${popoverOpen ? 'drawer-action-btn--active' : ''}`}
        aria-label="Link and Object Graph"
        aria-haspopup="dialog"
        aria-expanded={popoverOpen}
        onClick={() => { setPopoverOpen((prev) => !prev); }}
        data-testid="link-graph-trigger"
      >
        <span aria-hidden="true">🕸️</span>
      </button>

      {popoverOpen && (
        <div
          className="link-graph-popover"
          role="dialog"
          aria-label="Link and Object Graph details"
          data-testid="link-graph-popover"
        >
          {/* Canonical Copy Actions */}
          <div className="link-actions-row">
            <button
              type="button"
              className="drawer-action-btn link-copy-btn"
              onClick={() => { handleCopyUrl(); }}
              data-testid="copy-canonical-url-btn"
            >
              <span>Copy URL</span>
            </button>
            <button
              type="button"
              className="drawer-action-btn link-copy-btn"
              onClick={() => { handleCopyMarkdown(); }}
              data-testid="copy-markdown-btn"
            >
              <span>Copy [KEY](url) (Cmd+Shift+C)</span>
            </button>
          </div>

          <div className="link-graph-divider" />

          {/* Outbound Links */}
          <div className="link-graph-section">
            <div className="link-graph-section__title">Outbound Links</div>
            {outboundLinks.length === 0 ? (
              <div className="copy-notice">No outbound links.</div>
            ) : (
              <ul className="link-graph-list" data-testid="outbound-links-list">
                {outboundLinks.map((link: OutboundLink) => {
                  const isFlaggedInvalid = link.link_state === 'FLAGGED_INVALID';
                  return (
                    <li key={link.id} className="link-item-row" data-testid={`link-item-${link.id}`}>
                      <div className="link-item-info">
                        <span className="link-badge">{link.link_type}</span>
                        {isFlaggedInvalid && (
                          <EmojiHint
                            kind="brokenLink"
                            content="Flagged by Object Link Auditor - target deleted, archived, or ACL-severed."
                          />
                        )}
                        {link.target.restricted ? (
                          <span className="link-restricted-label">
                            <EmojiHint
                              kind="restricted"
                              content="Linked object is outside your visibility boundary."
                            />
                            <span>Restricted Object</span>
                          </span>
                        ) : (
                          <>
                            <span className="link-item-key">{link.target.key}</span>
                            <span className="link-item-title">{link.target.title}</span>
                          </>
                        )}
                      </div>
                      {canEdit && (
                        <button
                          type="button"
                          className="link-delete-btn"
                          aria-label={`Delete link ${link.id}`}
                          onClick={() => { deleteLinkMutation.mutate(link.id); }}
                          data-testid={`delete-link-${link.id}`}
                        >
                          ×
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Inbound Links */}
          <div className="link-graph-section">
            <div className="link-graph-section__title">Inbound Links</div>
            {inboundLinks.length === 0 ? (
              <div className="copy-notice">No inbound links.</div>
            ) : (
              <ul className="link-graph-list" data-testid="inbound-links-list">
                {inboundLinks.map((link) => {
                  const isFlaggedInvalid = link.link_state === 'FLAGGED_INVALID';
                  return (
                    <li key={link.id} className="link-item-row">
                      <div className="link-item-info">
                        <span className="link-badge">{link.link_type}</span>
                        {isFlaggedInvalid && (
                          <EmojiHint
                            kind="brokenLink"
                            content="Flagged by Object Link Auditor - target deleted, archived, or ACL-severed."
                          />
                        )}
                        {link.source.restricted ? (
                          <span className="link-restricted-label">
                            <EmojiHint
                              kind="restricted"
                              content="Linked object is outside your visibility boundary."
                            />
                            <span>Restricted Object</span>
                          </span>
                        ) : (
                          <>
                            <span className="link-item-key">{link.source.key}</span>
                            <span className="link-item-title">{link.source.title}</span>
                          </>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {canEdit && (
            <>
              <div className="link-graph-divider" />

              {/* Add Link Form */}
              <form className="add-link-form" onSubmit={handleAddLinkSubmit}>
                <select
                  className="add-link-select"
                  value={linkType}
                  onChange={(e) => { setLinkType(e.target.value); }}
                  aria-label="Link type"
                  data-testid="link-type-select"
                >
                  {USER_CREATABLE_LINK_TYPES.map((lt) => (
                    <option key={lt} value={lt}>
                      {lt}
                    </option>
                  ))}
                </select>
                <input
                  type="text"
                  className="add-link-input"
                  placeholder="Target key (e.g. KAN-7)"
                  value={targetRef}
                  onChange={(e) => { setTargetRef(e.target.value); }}
                  aria-label="Target issue key"
                  data-testid="link-target-input"
                />
                <button
                  type="submit"
                  className="drawer-action-btn"
                  disabled={!targetRef.trim() || addLinkMutation.isPending}
                  data-testid="add-link-submit-btn"
                >
                  Add Link
                </button>
              </form>
            </>
          )}
          {linkError && (
            <div className="modal-alert modal-alert--danger" role="alert">
              {linkError}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
