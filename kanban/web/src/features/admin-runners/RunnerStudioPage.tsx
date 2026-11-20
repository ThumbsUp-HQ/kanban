// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useCallback, type JSX } from 'react';
import {
  fetchRemoteRunners,
  revokeRemoteRunner,
  type RemoteRunnerResponse,
} from './runnersAdminApi';
import { MintEnrollmentTokenModal } from './MintEnrollmentTokenModal';
import { StudioDocLink } from '../../components/help/StudioDocLink';
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

  const handleConfirmRevoke = async (): Promise<void> => {
    if (!runnerToRevoke) return;
    try {
      setIsRevoking(true);
      setError(null);
      await revokeRemoteRunner(runnerToRevoke.id);
      setIsRevoking(false);
      setRunnerToRevoke(null);
      refreshRunners();
    } catch (err: unknown) {
      setIsRevoking(false);
      setError(err instanceof Error ? err.message : 'Failed to revoke remote runner');
    }
  };

  return (
    <section className="kb-runner-studio" data-testid="runner-studio-page">
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
                    <span>Cert Fingerprint:</span>
                    <code>{r.client_cert_sha256_hex.slice(0, 16)}...</code>
                  </div>

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
                onClick={() => { void handleConfirmRevoke(); }}
                data-testid="confirm-revoke-btn"
              >
                {isRevoking ? 'Revoking...' : 'Revoke Runner Immediately'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default RunnerStudioPage;
