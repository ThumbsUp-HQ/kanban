/**
 * DeleteBlastRadiusModal component (KB-P3-43, S7.2 8q).
 *
 * Pre-flight blast radius review modal with `Kb-Blast-Hash` concurrency TOCTOU guard
 * and 412 BLAST_RADIUS_CHANGED in-place reload.
 */

import React, { useCallback, useEffect, useState, type JSX } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate, useSearchParams } from 'react-router';
import { qk } from '../../api/queryKeys';
import { announce } from '../../api/RealtimeStatus';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import type { IssueDetail } from '../drawer/slots';
import {
  deleteIssue,
  fetchDeletePreview,
  type BlastRadiusResponse,
} from './actionsApi';
import './drawerActions.css';

export interface DeleteBlastRadiusModalProps {
  issue: IssueDetail;
  open: boolean;
  onClose: () => void;
}

export function DeleteBlastRadiusModal({
  issue,
  open,
  onClose,
}: DeleteBlastRadiusModalProps): JSX.Element | null {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [, setSearchParams] = useSearchParams();

  const [currentBlast, setCurrentBlast] = useState<BlastRadiusResponse | null>(null);
  const [concurrencyAlert, setConcurrencyAlert] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);

  const { data: previewData, isLoading: isPreviewLoading } = useQuery<BlastRadiusResponse>({
    queryKey: qk.deletePreview(issue.key),
    queryFn: () => fetchDeletePreview(issue.key),
    enabled: open,
    staleTime: 0, // always fresh
  });

  const handleClose = useCallback(() => {
    setCurrentBlast(null);
    setConcurrencyAlert(null);
    setGeneralError(null);
    onClose();
  }, [onClose]);

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

  const deleteMutation = useMutation({
    mutationFn: async (blastHash: string) => {
      setGeneralError(null);
      return await deleteIssue(issue.key, blastHash);
    },
    onSuccess: () => {
      const activeBlast = currentBlast ?? previewData;
      const retention = activeBlast?.retention_days ?? 30;
      announce(`${issue.key} moved to trash (restorable for ${String(retention)} days)`);

      void queryClient.invalidateQueries({ queryKey: qk.project(issue.project_key) });
      handleClose();

      // Close surface
      if (location.pathname.includes('/issues/')) {
        void navigate(`/projects/${issue.project_key}`);
      } else {
        setSearchParams((prev: URLSearchParams) => {
          const next = new URLSearchParams(prev);
          next.delete('peek');
          return next;
        });
      }
    },
    onError: (err: unknown) => {
      // 412 BLAST_RADIUS_CHANGED handling
      let is412 = false;
      let updatedPreview: BlastRadiusResponse | null = null;
      if (err && typeof err === 'object') {
        const anyErr = err as Record<string, unknown>;
        if (anyErr.status === 412 || anyErr.code === 'BLAST_RADIUS_CHANGED') {
          is412 = true;
        }
        if (anyErr.data && typeof anyErr.data === 'object') {
          const dataObj = anyErr.data as Record<string, unknown>;
          if (dataObj.current_preview) {
            updatedPreview = dataObj.current_preview as BlastRadiusResponse;
          }
        } else if (anyErr.current_preview) {
          updatedPreview = anyErr.current_preview as BlastRadiusResponse;
        }
      }

      if (is412) {
        if (updatedPreview) {
          setCurrentBlast(updatedPreview);
        }
        setConcurrencyAlert(
          'Blast radius changed since you opened this dialog. Review the updated counts and confirm again.',
        );
      } else {
        let errorMsg = 'Failed to delete issue';
        if (err && typeof err === 'object') {
          const anyErr = err as Record<string, unknown>;
          if (typeof anyErr.detail === 'string') {
            errorMsg = anyErr.detail;
          } else if (typeof anyErr.message === 'string') {
            errorMsg = anyErr.message;
          }
        }
        setGeneralError(errorMsg);
      }
    },
  });

  if (!open) return null;

  const blast = currentBlast ?? previewData;
  const blastHash = blast?.blast_hash ?? '';
  const retentionDays = blast?.retention_days ?? 30;

  const subIssuesCount = blast ? blast.sub_issues_unparented : 0;
  const inboundCount = blast ? blast.inbound_links_flagged : 0;
  const outboundCount = blast ? blast.outbound_links : 0;
  const commentsCount = blast ? blast.comments : 0;
  const attachmentsCount = blast ? blast.attachments : 0;

  function handleConfirmDelete(e: React.SyntheticEvent): void {
    e.preventDefault();
    deleteMutation.mutate(blastHash);
  }

  return (
    <div className="modal-backdrop" onClick={handleClose} data-testid="delete-blast-backdrop">
      <div
        className="modal-card blast-radius-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-blast-dialog-title"
        onClick={(e) => { e.stopPropagation(); }}
        data-testid="delete-blast-radius-modal"
      >
        <div className="modal-header">
          <h2 id="delete-blast-dialog-title" className="modal-title">
            Move {issue.key} to Trash?
          </h2>
          <button
            type="button"
            className="modal-close-btn"
            aria-label="Close dialog"
            onClick={handleClose}
          >
            ✕
          </button>
        </div>

        {concurrencyAlert && (
          <div
            className="modal-alert modal-alert--warning"
            role="alert"
            data-testid="concurrency-alert"
          >
            {concurrencyAlert}
          </div>
        )}

        {generalError && (
          <div className="modal-alert modal-alert--danger" role="alert" data-testid="delete-general-error">
            {generalError}
          </div>
        )}

        <div className="blast-radius-summary">
          {isPreviewLoading && !blast ? (
            <div className="copy-notice">Calculating blast radius...</div>
          ) : (
            <>
              <div className="blast-radius-text" data-testid="blast-radius-summary-text">
                {subIssuesCount} sub-issues unparented,{' '}
                {inboundCount} inbound object_links flagged
              </div>
              <div className="blast-radius-counts">
                <span>{outboundCount} outbound links</span>
                <span>•</span>
                <span>{commentsCount} comments</span>
                <span>•</span>
                <span>{attachmentsCount} attachments</span>
              </div>
            </>
          )}
        </div>

        <div className="soft-trash-notice-row">
          <p className="soft-trash-notice" data-testid="soft-trash-retention-notice">
            Moved to trash for {retentionDays} days before permanent audited purge.
          </p>
          <FieldHelpHint
            title="Soft-Trash Retention & Purge Policy"
            summary="Items moved to trash remain restorable by workspace administrators during the 30-day retention window. After 30 days, the item and all associated object links undergo a permanent cryptographic purge."
            defaultValue={`${String(retentionDays)} days`}
            docHref="/docs/universal-object-graph-and-link-auditor"
            testId="soft-trash-help-hint"
            ariaLabel="Learn about soft-trash retention and permanent cryptographic purge"
          />
        </div>

        <div className="modal-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={handleClose}
            disabled={deleteMutation.isPending}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn-danger"
            onClick={handleConfirmDelete}
            disabled={isPreviewLoading || !blastHash || deleteMutation.isPending}
            data-testid="confirm-delete-btn"
          >
            {deleteMutation.isPending ? 'Moving to trash...' : `Move ${issue.key} to trash`}
          </button>
        </div>
      </div>
    </div>
  );
}
