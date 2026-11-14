/**
 * MakeCopyDialog component (KB-P3-43, S7.2 8n).
 *
 * Checklist dialog for `POST /api/v1/issues/{key}/copy`.
 */

import React, { useCallback, useEffect, useState, type JSX } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate, useSearchParams } from 'react-router';
import { apiFetch } from '../../api/client';
import { qk } from '../../api/queryKeys';
import { announce } from '../../api/RealtimeStatus';
import type { IssueDetail } from '../drawer/slots';
import { copyIssue, type CopyIssueResponse } from './actionsApi';
import './drawerActions.css';

export interface MakeCopyDialogProps {
  issue: IssueDetail;
  open: boolean;
  onClose: () => void;
}

import type { paths } from '../../api/schema.gen';

function extractErrorMessage(err: unknown): string {
  if (err && typeof err === 'object') {
    const rec = err as Record<string, unknown>;
    if (typeof rec.detail === 'string') return rec.detail;
    if (typeof rec.message === 'string') return rec.message;
  }
  return 'Failed to copy issue';
}

export function MakeCopyDialog({ issue, open, onClose }: MakeCopyDialogProps): JSX.Element | null {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [, setSearchParams] = useSearchParams();

  const [includeSubIssues, setIncludeSubIssues] = useState(false);
  const [includeAttachments, setIncludeAttachments] = useState(false);
  const [linkAsRelatesTo, setLinkAsRelatesTo] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleClose = useCallback(() => {
    setIncludeSubIssues(false);
    setIncludeAttachments(false);
    setLinkAsRelatesTo(false);
    setErrorMessage(null);
    onClose();
  }, [onClose]);

  const { data: meData } = useQuery<{ handle?: string }>({
    queryKey: qk.me(),
    queryFn: async () => (await apiFetch('GET', '/api/v1/auth/me' as unknown as keyof paths)) as { handle?: string },
    staleTime: 60000,
  });

  const meHandle = (meData && typeof meData.handle === 'string') ? meData.handle : 'currentUser';

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        handleClose();
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => { document.removeEventListener('keydown', handleKeyDown); };
  }, [open, handleClose]);

  const copyMutation = useMutation({
    mutationFn: async () => {
      setErrorMessage(null);
      return await copyIssue(issue.key, {
        include_sub_issues: includeSubIssues,
        include_attachments: includeAttachments,
        link_as_relates_to: linkAsRelatesTo,
      });
    },
    onSuccess: (data: CopyIssueResponse) => {
      const copyKey = data.issue.key;
      const skippedCount = (data.skipped && typeof data.skipped.restricted_sub_issues === 'number')
        ? data.skipped.restricted_sub_issues
        : 0;

      if (skippedCount > 0) {
        announce(`Copied to ${copyKey} (${String(skippedCount)} restricted sub-issue(s) skipped)`);
      } else {
        announce(`Copied to ${copyKey}`);
      }

      void queryClient.invalidateQueries({ queryKey: qk.project(issue.project_key) });
      handleClose();

      // Navigate to new copy
      if (location.pathname.includes('/issues/')) {
        void navigate(`/projects/${issue.project_key}/issues/${copyKey}`);
      } else {
        setSearchParams((prev: URLSearchParams) => {
          const next = new URLSearchParams(prev);
          next.set('peek', copyKey);
          return next;
        });
      }
    },
    onError: (err: unknown) => {
      setErrorMessage(extractErrorMessage(err));
    },
  });

  if (!open) return null;

  const issueSummary = issue.summary ? issue.summary : '';
  const rawSummary = `[Copy] ${issueSummary}`;
  const previewTitle = rawSummary.length > 500 ? rawSummary.slice(0, 500) : rawSummary;

  function handleSubmit(e: React.SyntheticEvent): void {
    e.preventDefault();
    copyMutation.mutate();
  }

  return (
    <div className="modal-backdrop" onClick={handleClose} data-testid="make-copy-backdrop">
      <div
        className="modal-card make-copy-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="make-copy-dialog-title"
        onClick={(e) => { e.stopPropagation(); }}
        data-testid="make-copy-dialog"
      >
        <div className="modal-header">
          <h2 id="make-copy-dialog-title" className="modal-title">
            Make a Copy
          </h2>
          <button
            type="button"
            className="modal-close-btn"
            aria-label="Close dialog"
            onClick={handleClose}
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="copy-checkbox-list">
          <div>
            <label className="copy-notice copy-preview-label">
              Summary Preview
            </label>
            <div className="copy-preview-title" data-testid="copy-preview-title">
              {previewTitle}
            </div>
          </div>

          <label className="mute-checkbox-label">
            <input
              type="checkbox"
              checked={includeSubIssues}
              onChange={(e) => { setIncludeSubIssues(e.target.checked); }}
              data-testid="copy-include-sub-issues"
            />
            <span>Include sub-issues</span>
          </label>

          <label className="mute-checkbox-label">
            <input
              type="checkbox"
              checked={includeAttachments}
              onChange={(e) => { setIncludeAttachments(e.target.checked); }}
              data-testid="copy-include-attachments"
            />
            <span>Include attachments</span>
          </label>

          <label className="mute-checkbox-label">
            <input
              type="checkbox"
              checked={linkAsRelatesTo}
              onChange={(e) => { setLinkAsRelatesTo(e.target.checked); }}
              data-testid="copy-link-relates-to"
            />
            <span>Link as RELATES_TO</span>
          </label>

          <p className="copy-notice" data-testid="copy-creator-notice">
            Created by will be set to @{meHandle}
          </p>

          {errorMessage && (
            <div className="modal-alert modal-alert--danger" role="alert" data-testid="copy-error-alert">
              {errorMessage}
            </div>
          )}

          <div className="modal-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={handleClose}
              disabled={copyMutation.isPending}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={copyMutation.isPending}
              data-testid="confirm-copy-btn"
            >
              {copyMutation.isPending ? 'Copying...' : 'Make Copy'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
