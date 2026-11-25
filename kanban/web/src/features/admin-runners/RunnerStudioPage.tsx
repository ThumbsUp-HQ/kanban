// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useCallback, type JSX } from 'react';
import {
  fetchRemoteRunners,
  revokeRemoteRunner,
  type RemoteRunnerResponse,
} from './runnersAdminApi';
import { MintEnrollmentTokenModal } from './MintEnrollmentTokenModal';
import { SecondFactorStep } from '../auth/SecondFactorStep';
import type { MfaMethod } from '../auth/authApi';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { AdminStudioSubnav } from '../admin/AdminStudioSubnav';
import { AdvancedSection } from '../../ui/AdvancedSection';
import './runnerStudio.css';

export function RunnerStudioPage(): JSX.Element {
  const [runners, setRunners] = useState<RemoteRunnerResponse[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Modals state
  const [isMintModalOpen, setIsMintModalOpen] = useState<boolean>(false);
  const [runnerToRevoke, setRunnerToRevoke] = useState<RemoteRunnerResponse | null>(null);
  const [isRevoking, setIsRevoking] = useState<boolean>(false);

  // Inline AAL2 challenge state
  const [aal2Challenge, setAal2Challenge] = useState<{
    challengeId: string;
    methods: MfaMethod[];
  } | null>(null);
  const [pendingAction, setPendingAction] = useState<(() => Promise<void>) | null>(null);

  const [reloadCounter, setReloadCounter] = useState<number>(0);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const queryStatus = statusFilter === 'all' ? undefined : statusFilter;
        const list = await fetchRemoteRunners(undefined, queryStatus);
        if (!active) return;
        setRunners(list);
      } catch (err: unknown) {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Failed to load remote runners');
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, [statusFilter, reloadCounter]);

  const refreshRunners = useCallback((): void => {
    setReloadCounter((c) => c + 1);
  }, []);

  const handleConfirmRevoke = async (runnerId: string): Promise<void> => {
    try {
      setIsRevoking(true);
      setError(null);
      await revokeRemoteRunner(runnerId);
      setIsRevoking(false);
      setRunnerToRevoke(null);
      refreshRunners();
    } catch (err: unknown) {
      setIsRevoking(false);
      if (
        typeof err === 'object' &&
        err !== null &&
        'code' in err &&
        (err.code === 'AAL2_REQUIRED' || err.code === 'AAL2_STALE')
      ) {
        const data = (err as { data?: { challenge_id?: string; methods?: MfaMethod[] } }).data ?? {};
        const challengeId = typeof data.challenge_id === 'string' ? data.challenge_id : 'aal2-stepup';
        const methods = Array.isArray(data.methods)
          ? data.methods
          : (['webauthn', 'totp'] as MfaMethod[]);
        setAal2Challenge({ challengeId, methods });
        setPendingAction(() => async () => {
          await revokeRemoteRunner(runnerId);
          setRunnerToRevoke(null);
          refreshRunners();
        });
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to revoke remote runner');
    }
  };

  const handleAal2Success = async (): Promise<void> => {
    const action = pendingAction;
    setAal2Challenge(null);
    setPendingAction(null);
    await action?.();
  };

  return (
    <section className="kb-runner-studio" data-testid="runner-studio-page">
      <AdminStudioSubnav activeTab="runners" />
      <div className="kb-runner-studio-header">
        <div className="kb-runner-studio-title-group">
          <h1>
            <span aria-hidden="true">🚀</span> Remote mTLS Runners Studio
          </h1>
          <p className="kb-runner-studio-subtitle">
            Manage distributed worker runners connecting via outbound mutual TLS (mTLS) with single-use enrollment and immediate revocation.
          </p>
        </div>

        <div className="kb-runner-studio-header-actions">
          <StudioDocLink
            href="/docs/multi-provider-ai-engine-and-runners#remote-runners"
            title="Remote Runners Documentation"
            testId="runner-studio-doc-link"
          />
          <button
            type="button"
            className="kb-btn kb-btn-primary"
            onClick={() => { setIsMintModalOpen(true); }}
            data-testid="open-mint-modal-btn"
          >
            + Mint Enrollment Token
          </button>
        </div>
      </div>

      <div
        className="kb-runner-rotation-guidance"
        data-testid="runner-rotation-guidance"
        style={{
          padding: '12px 16px',
          background: 'rgba(56, 189, 248, 0.08)',
          border: '1px solid rgba(56, 189, 248, 0.25)',
          borderRadius: '8px',
          marginBottom: '16px',
        }}
      >
        <h3 style={{ margin: '0 0 6px 0', fontSize: '0.95rem', fontWeight: 600, color: '#38bdf8' }}>
          🔄 Certificate Rotation & Runner Lifecycle Guidance
        </h3>
        <p style={{ margin: '0 0 6px 0', fontSize: '0.85rem', color: 'var(--text-secondary, #94a3b8)' }}>
          Remote runner mTLS client certificates are cryptographically bound to the daemon instance and cannot be modified in place. To rotate expired or compromised certificates:
        </p>
        <ol style={{ margin: 0, paddingLeft: '20px', fontSize: '0.825rem', color: 'var(--text-secondary, #94a3b8)' }}>
          <li>Revoke the target runner using 1-Click Revoke (AAL2 verification required).</li>
          <li>Mint a fresh single-use enrollment token for the designated runner pool.</li>
          <li>Re-enroll the runner daemon with fresh keypairs: <code>echo &quot;&lt;token&gt;&quot; | uv run kanban-agent-runner enroll --server-url {typeof window !== 'undefined' ? window.location.origin : 'https://kanban.example.com'} --token-stdin --pool &lt;pool&gt;</code></li>
        </ol>
      </div>

      <div className="kb-runner-filters" data-testid="runner-status-filters">
        <button
          type="button"
          className={`kb-filter-pill ${statusFilter === 'all' ? 'kb-filter-pill--active' : ''}`}
          onClick={() => { setStatusFilter('all'); }}
          data-testid="filter-all-btn"
        >
          All Runners
        </button>
        <button
          type="button"
          className={`kb-filter-pill ${statusFilter === 'active' ? 'kb-filter-pill--active' : ''}`}
          onClick={() => { setStatusFilter('active'); }}
          data-testid="filter-active-btn"
        >
          Active
        </button>
        <button
          type="button"
          className={`kb-filter-pill ${statusFilter === 'revoked' ? 'kb-filter-pill--active' : ''}`}
          onClick={() => { setStatusFilter('revoked'); }}
          data-testid="filter-revoked-btn"
        >
          Revoked
        </button>
        <button
          type="button"
          className={`kb-filter-pill ${statusFilter === 'offline' ? 'kb-filter-pill--active' : ''}`}
          onClick={() => { setStatusFilter('offline'); }}
          data-testid="filter-offline-btn"
        >
          Offline
        </button>
      </div>

      {error && (
        <div className="kb-form-hint kb-runner-studio-error" data-testid="runner-studio-error">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="kb-loading-state" data-testid="runner-studio-loading">
          Loading remote runners...
        </div>
      ) : runners.length === 0 ? (
        <div
          className="kb-empty-runners-placeholder"
          data-testid="empty-runners-placeholder"
        >
          <p className="kb-empty-runners-text">
            No remote runners registered for this filter. Mint an enrollment token to connect a new runner.
          </p>
        </div>
      ) : (
        <div className="kb-runners-grid" data-testid="runners-grid">
          {runners.map((r) => {
            const isRevoked = r.status === 'revoked';

            return (
              <div
                key={r.id}
                className="kb-runner-card"
                data-testid={`runner-card-${r.id}`}
              >
                <div>
                  <div className="kb-runner-card-header">
                    <span
                      className={`kb-runner-status-badge kb-runner-status-badge--${r.status}`}
                      data-testid={`runner-status-${r.id}`}
                    >
                      {r.status}
                    </span>
                    <span className="kb-runner-pool-badge">
                      Pool: <strong>{r.pool_slug}</strong>
                    </span>
                  </div>

                  <h3 className="kb-runner-hostname">{r.hostname}</h3>

                  <div className="kb-runner-meta-row">
                    <span>Cert Expires:</span>
                    <span>{new Date(r.cert_expires_at).toLocaleDateString()}</span>
                  </div>

                  <div className="kb-runner-meta-row">
                    <span>Heartbeat:</span>
                    <span>
                      {r.last_heartbeat_at
                        ? new Date(r.last_heartbeat_at).toLocaleTimeString()
                        : 'Never'}
                    </span>
                  </div>

                  <AdvancedSection
                    title="Advanced Technical Details"
                    summary="mTLS client certificate fingerprint and cryptographic parameters"
                    testId={`runner-advanced-details-${r.id}`}
                  >
                    <div className="kb-runner-meta-row" style={{ marginTop: '8px' }}>
                      <span>Full Cert SHA-256:</span>
                      <code style={{ wordBreak: 'break-all', fontSize: '0.75rem' }}>{r.client_cert_sha256_hex}</code>
                    </div>
                    <div className="kb-runner-meta-row">
                      <span>Cert Fingerprint:</span>
                      <code>{r.client_cert_sha256_hex.slice(0, 16)}...</code>
                    </div>
                  </AdvancedSection>

                  {Object.keys(r.capabilities).length > 0 && (
                    <div className="kb-runner-caps-container">
                      <span className="kb-runner-caps-label">
                        Capabilities:
                      </span>
                      <div className="kb-runner-caps-chips">
                        {Object.entries(r.capabilities).map(([k, v]) => (
                          <span key={k} className="kb-model-chip">
                            {k}: {String(v)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="kb-runner-card-actions">
                  <button
                    type="button"
                    className="kb-btn kb-btn-danger"
                    disabled={isRevoked}
                    onClick={() => { setRunnerToRevoke(r); }}
                    data-testid={`revoke-runner-btn-${r.id}`}
                  >
                    {isRevoked ? 'Revoked' : '1-Click Revoke (AAL2)'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Mint Enrollment Token Modal */}
      <MintEnrollmentTokenModal
        isOpen={isMintModalOpen}
        onClose={() => { setIsMintModalOpen(false); }}
        onTokenMinted={refreshRunners}
      />

      {/* Revocation Confirmation Modal */}
      {runnerToRevoke && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="revoke-runner-title"
          className="kb-modal-backdrop"
          data-testid="revoke-runner-modal"
        >
          <div className="kb-modal-card">
            <h2 id="revoke-runner-title" className="kb-revoke-runner-title">
              Confirm Remote Runner Revocation
            </h2>
            <p className="kb-revoke-runner-text">
              Are you sure you want to revoke remote runner <strong>{runnerToRevoke.hostname}</strong> (Pool: <code>{runnerToRevoke.pool_slug}</code>)?
            </p>
            <div className="kb-air-gap-banner kb-revoke-runner-banner">
              <span className="kb-air-gap-banner-icon" aria-hidden="true">
                ⚠️
              </span>
              <div>
                <strong>Immediate Disconnect (AAL2 Required)</strong>
                Revocation will immediately terminate active WebSocket connections, cancel any in-flight execution jobs, and permanently invalidate the runner client certificate.
              </div>
            </div>
            <p className="kb-revoke-runner-rotation-note" data-testid="revoke-rotation-note" style={{ fontSize: '0.85rem', color: '#94a3b8', marginTop: '8px' }}>
              <strong>Rotation Procedure:</strong> Confirming revocation terminates active connections and invalidates client certificates. To complete rotation, mint a fresh enrollment token to re-enroll this runner daemon.
            </p>
            <div className="kb-modal-footer">
              <button
                type="button"
                className="kb-btn kb-btn-secondary"
                onClick={() => { setRunnerToRevoke(null); }}
                data-testid="cancel-revoke-btn"
              >
                Cancel
              </button>
              <button
                type="button"
                className="kb-btn kb-btn-danger"
                disabled={isRevoking}
                onClick={() => { void handleConfirmRevoke(runnerToRevoke.id); }}
                data-testid="confirm-revoke-btn"
              >
                {isRevoking ? 'Revoking...' : 'Revoke Runner Immediately'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Inline AAL2 Step-Up Modal */}
      {aal2Challenge && (
        <div className="kb-modal-backdrop" data-testid="aal2-modal-backdrop">
          <div
            className="kb-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="runner-aal2-modal-title"
            data-testid="aal2-modal-card"
          >
            <div className="kb-modal-header">
              <h2 id="runner-aal2-modal-title">Admin Verification Required (AAL2)</h2>
              <button
                type="button"
                className="kb-btn kb-btn-secondary"
                onClick={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
                aria-label="Close dialog"
                data-testid="close-aal2-modal-btn"
              >
                ✕
              </button>
            </div>
            <div className="kb-runner-studio-section" style={{ padding: '16px 0' }}>
              <SecondFactorStep
                challengeId={aal2Challenge.challengeId}
                methods={aal2Challenge.methods}
                onSuccess={() => {
                  void handleAal2Success();
                }}
                onError={() => {
                  // Handled inside SecondFactorStep
                }}
                onSessionExpired={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
                onCancel={() => {
                  setAal2Challenge(null);
                  setPendingAction(null);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default RunnerStudioPage;
