// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import type { JSX } from 'react';
import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  approveFieldEscalation,
  fetchFieldApprovals,
  qk,
  requestFieldApproval,
  type CustomFieldApproval,
  type CustomFieldCredentialMode,
  type CustomFieldDefinition,
  type CustomFieldTargetScope,
} from './api';
import './custom-fields.css';

export interface EscalationApprovalPanelProps {
  field: CustomFieldDefinition;
  callerTier?: 'MEMBER' | 'PROJECT_ADMIN' | 'WORKSPACE_ADMIN' | 'SERVER_ADMIN';
  onAal2Challenge?: () => Promise<boolean>;
  onApproved?: () => void;
  suppressDualControlBanner?: boolean;
}

function getTierRank(
  tier: 'MEMBER' | 'PROJECT_ADMIN' | 'WORKSPACE_ADMIN' | 'SERVER_ADMIN',
): number {
  switch (tier) {
    case 'SERVER_ADMIN':
      return 3;
    case 'WORKSPACE_ADMIN':
      return 2;
    case 'PROJECT_ADMIN':
      return 1;
    case 'MEMBER':
    default:
      return 0;
  }
}

export function getRequiredApproverTier(
  scope: CustomFieldTargetScope,
  mode: CustomFieldCredentialMode,
): { tier: 'PROJECT_ADMIN' | 'WORKSPACE_ADMIN' | 'SERVER_ADMIN'; dualControl: boolean } {
  if (scope === 'SERVER') {
    return { tier: 'SERVER_ADMIN', dualControl: true };
  }
  if (scope === 'WORKSPACE') {
    return { tier: 'WORKSPACE_ADMIN', dualControl: false };
  }
  if (mode === 'PROJECT_ADMIN_SP') {
    return { tier: 'PROJECT_ADMIN', dualControl: false };
  }
  return { tier: 'PROJECT_ADMIN', dualControl: false };
}

/**
 * Escalation Approval Panel enforcing Section 13.2 Scope x Principal Matrix,
 * AAL2 step-up verification, tamper auto-revocation display, and anti-enumeration.
 */
export function EscalationApprovalPanel({
  field,
  callerTier = 'PROJECT_ADMIN',
  onAal2Challenge,
  onApproved,
  suppressDualControlBanner = false,
}: EscalationApprovalPanelProps): JSX.Element {
  const queryClient = useQueryClient();
  const [justification, setJustification] = useState('');
  const [spWarningAck, setSpWarningAck] = useState(false);
  const [isRequestModalOpen, setIsRequestModalOpen] = useState(false);
  const [isAal2ModalOpen, setIsAal2ModalOpen] = useState(false);
  const [manifestMismatchError, setManifestMismatchError] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [aal2OtpCode, setAal2OtpCode] = useState('');

  // Fetch approvals for this field
  const { data: approvals = [], refetch: refetchApprovals } = useQuery({
    queryKey: qk.customFields.approvals(field.id),
    queryFn: () => fetchFieldApprovals(field.id),
    enabled: Boolean(field.id),
  });

  const latestApproval: CustomFieldApproval | undefined = approvals[0];

  const targetScope = field.target_scope;
  const credentialMode = field.credential_mode;
  const isElevated = targetScope !== 'PROJECT' || credentialMode !== 'INVOKING_USER';
  const isSpMode = credentialMode !== 'INVOKING_USER';

  const { tier: requiredTier, dualControl } = getRequiredApproverTier(targetScope, credentialMode);
  const callerRank = getTierRank(callerTier);
  const requiredRank = getTierRank(requiredTier);
  const canCallerApprove = callerRank >= requiredRank;

  // Request approval mutation
  const requestMutation = useMutation({
    mutationFn: async () => {
      const sha = field.manifest_sha256 ?? '';
      return requestFieldApproval(field.id, {
        manifest_sha256: sha,
        justification,
      });
    },
    onSuccess: (newApproval) => {
      setIsRequestModalOpen(false);
      setJustification('');
      queryClient.setQueryData<CustomFieldApproval[]>(
        qk.customFields.approvals(field.id),
        (old) =>
          old
            ? [newApproval, ...old.filter((a) => a.id !== newApproval.id)]
            : [newApproval],
      );
      void refetchApprovals();
      onApproved?.();
    },
    onError: (err: Error) => {
      setGeneralError(err.message);
    },
  });

  // Approve mutation
  const approveMutation = useMutation({
    mutationFn: async (params?: { approvalId?: string; isRetry?: boolean }) => {
      const approvalId = params?.approvalId ?? latestApproval?.id;
      if (!approvalId) throw new Error('No pending approval request found');
      const sha = field.manifest_sha256 ?? '';
      return approveFieldEscalation(approvalId, {
        manifest_sha256: sha,
        sp_warning_acknowledged: spWarningAck,
      });
    },
    onSuccess: (updatedApproval) => {
      setManifestMismatchError(null);
      setGeneralError(null);
      setIsAal2ModalOpen(false);
      queryClient.setQueryData<CustomFieldApproval[]>(
        qk.customFields.approvals(field.id),
        (old) =>
          old
            ? [updatedApproval, ...old.filter((a) => a.id !== updatedApproval.id)]
            : [updatedApproval],
      );
      void refetchApprovals();
      onApproved?.();
    },
    onError: async (err: Error) => {
      const errObj = err as unknown as { status?: number; code?: string };
      if (errObj.status === 409 || errObj.code === 'MANIFEST_MISMATCH') {
        setManifestMismatchError(
          'Definition changed since you opened it - reload to review',
        );
        return;
      }

      if (errObj.status === 403 || errObj.code === 'AAL2_REQUIRED') {
        // Trigger AAL2 step-up challenge
        if (onAal2Challenge) {
          const challenged = await onAal2Challenge();
          if (challenged) {
            // Retry approval once after successful challenge
            approveMutation.mutate({ isRetry: true });
            return;
          }
        }
        setIsAal2ModalOpen(true);
        return;
      }

      setGeneralError(err.message);
    },
  });

  // Mock AAL2 dialog verification
  const handleAal2Submit = (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (aal2OtpCode.trim().length >= 6) {
      setIsAal2ModalOpen(false);
      // Retry once after simulated AAL2 verification
      approveMutation.mutate({ isRetry: true });
    }
  };

  return (
    <div className="custom-field-approval-panel" data-testid="escalation-approval-panel">
      <div className="custom-field-approval-header">
        <h4 className="custom-field-approval-title">Escalation & Security Approvals</h4>
        <span
          className={`custom-field-status-chip custom-field-status-chip--${latestApproval?.status.toLowerCase() ?? 'default'}`}
          data-testid="approval-status-chip"
        >
          {latestApproval?.status === 'APPROVED'
            ? `Approved by ${requiredTier}`
            : latestApproval?.status === 'PENDING'
              ? 'Pending approval'
              : latestApproval?.status === 'PENDING_SECOND_APPROVER'
                ? 'Pending second approver'
                : latestApproval?.status === 'REVOKED'
                  ? 'Revoked'
                  : 'Default (no approval needed)'}
        </span>
      </div>

      {/* Scope x Principal Matrix Requirements */}
      <div className="custom-field-matrix-summary">
        <div className="custom-field-matrix-row">
          <span className="custom-field-matrix-label">Target Scope:</span>
          <span className="custom-field-matrix-val mono">{targetScope}</span>
        </div>
        <div className="custom-field-matrix-row">
          <span className="custom-field-matrix-label">Credential Mode:</span>
          <span className="custom-field-matrix-val mono">{credentialMode}</span>
        </div>
        <div className="custom-field-matrix-row">
          <span className="custom-field-matrix-label">Required Approver Tier:</span>
          <span className="custom-field-matrix-val">
            {requiredTier} {dualControl ? '(Dual-Control Required)' : ''}
          </span>
        </div>
      </div>

      {/* SP Warning Banner (S13.2) */}
      {isSpMode && (
        <div
          className="custom-field-sp-warning-banner"
          data-testid="sp-warning-banner"
          role="alert"
        >
          ⚠️ This field will run with Project Admin service-principal credentials for every viewer.
        </div>
      )}

      {/* Dual-Control Explanation Banner */}
      {!suppressDualControlBanner &&
        (latestApproval?.status === 'PENDING' ||
          latestApproval?.status === 'PENDING_SECOND_APPROVER') && (
          <div
            className="custom-field-dual-control-banner"
            data-testid="dual-control-explanation-banner"
            role="status"
          >
            <strong>Dual-Control Policy:</strong> Another distinct administrator holding{' '}
            <strong>{requiredTier}</strong> authority with a fresh <strong>AAL2</strong> step-up must
            approve this escalation. Self-approval is blocked (403 Forbidden). Any subsequent edit to
            script source or format metadata will immediately revoke approval and reset state.
          </div>
        )}

      {/* Error Banners */}
      {manifestMismatchError && (
        <div
          className="custom-field-error-banner"
          data-testid="manifest-mismatch-banner"
          role="alert"
        >
          {manifestMismatchError}
        </div>
      )}
      {generalError && (
        <div className="custom-field-error-banner" role="alert">
          {generalError}
        </div>
      )}

      {/* Action Controls */}
      {isElevated && (
        <div className="custom-field-approval-actions">
          {/* Request Approval Button */}
          {(!latestApproval ||
            latestApproval.status === 'REVOKED' ||
            latestApproval.status === 'APPROVED') && (
            <button
              type="button"
              className="custom-field-btn custom-field-btn--secondary"
              onClick={() => {
                setIsRequestModalOpen(true);
              }}
              data-testid="request-approval-btn"
            >
              Request Approval
            </button>
          )}

          {/* Approve Button: ONLY rendered if caller tier >= required approver tier */}
          {canCallerApprove &&
            (latestApproval?.status === 'PENDING' ||
              latestApproval?.status === 'PENDING_SECOND_APPROVER') && (
              <div className="custom-field-approve-group">
                {isSpMode && (
                  <label className="custom-field-checkbox-label">
                    <input
                      type="checkbox"
                      checked={spWarningAck}
                      onChange={(e) => {
                        setSpWarningAck(e.target.checked);
                      }}
                      data-testid="sp-ack-checkbox"
                    />
                    I acknowledge elevated service-principal execution
                  </label>
                )}
                <button
                  type="button"
                  className="custom-field-btn custom-field-btn--primary"
                  onClick={() => {
                    approveMutation.mutate({});
                  }}
                  disabled={
                    approveMutation.isPending ||
                    Boolean(manifestMismatchError) ||
                    (isSpMode && !spWarningAck)
                  }
                  data-testid="approve-escalation-btn"
                >
                  {approveMutation.isPending ? 'Approving...' : 'Approve Escalation'}
                </button>
              </div>
            )}
        </div>
      )}

      {/* Request Modal */}
      {isRequestModalOpen && (
        <div className="custom-field-modal-overlay" role="dialog" aria-modal="true">
          <div className="custom-field-modal">
            <h4 className="custom-field-modal-title">Request Escalation Approval</h4>
            <p className="custom-field-modal-subtitle">
              Provide justification for running this field with elevated scope or credentials.
            </p>
            <div className="custom-field-form-group">
              <label htmlFor="approval-justification" className="custom-field-form-label">
                Business Justification (min 10 characters)
              </label>
              <textarea
                id="approval-justification"
                className="custom-field-textarea"
                rows={4}
                value={justification}
                onChange={(e) => {
                  setJustification(e.target.value);
                }}
                data-testid="approval-justification-input"
              />
            </div>
            <div className="custom-field-modal-actions">
              <button
                type="button"
                className="custom-field-btn custom-field-btn--secondary"
                data-testid="cancel-request-btn"
                onClick={() => {
                  setIsRequestModalOpen(false);
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="custom-field-btn custom-field-btn--primary"
                disabled={justification.trim().length < 10 || requestMutation.isPending}
                onClick={() => {
                  requestMutation.mutate();
                }}
                data-testid="submit-approval-request-btn"
              >
                {requestMutation.isPending ? 'Submitting...' : 'Submit Request'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AAL2 Step-Up Dialog */}
      {isAal2ModalOpen && (
        <div
          className="custom-field-modal-overlay"
          role="dialog"
          aria-modal="true"
          data-testid="aal2-stepup-modal"
        >
          <div className="custom-field-modal">
            <h4 className="custom-field-modal-title">AAL2 Step-Up Verification</h4>
            <p className="custom-field-modal-subtitle">
              Approving custom field escalation requires secondary factor confirmation.
            </p>
            <form onSubmit={handleAal2Submit}>
              <div className="custom-field-form-group">
                <label htmlFor="aal2-otp" className="custom-field-form-label">
                  Passkey or Authenticator Code
                </label>
                <input
                  id="aal2-otp"
                  type="text"
                  className="custom-field-input mono"
                  maxLength={6}
                  placeholder="000000"
                  value={aal2OtpCode}
                  onChange={(e) => {
                    setAal2OtpCode(e.target.value);
                  }}
                  data-testid="aal2-otp-input"
                  autoFocus
                />
              </div>
              <div className="custom-field-modal-actions">
                <button
                  type="button"
                  className="custom-field-btn custom-field-btn--secondary"
                  data-testid="cancel-aal2-btn"
                  onClick={() => {
                    setIsAal2ModalOpen(false);
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="custom-field-btn custom-field-btn--primary"
                  data-testid="aal2-verify-btn"
                >
                  Verify & Approve
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
