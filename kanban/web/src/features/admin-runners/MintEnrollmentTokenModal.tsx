// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX } from 'react';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import {
  mintEnrollmentToken,
  type EnrollmentTokenResponse,
} from './runnersAdminApi';

interface MintEnrollmentTokenModalProps {
  isOpen: boolean;
  onClose: () => void;
  onTokenMinted?: (() => void) | undefined;
}

function MintEnrollmentTokenContent({
  onClose,
  onTokenMinted,
}: {
  onClose: () => void;
  onTokenMinted?: (() => void) | undefined;
}): JSX.Element {
  const [poolSlug, setPoolSlug] = useState<string>('default');
  const [ttlSeconds, setTtlSeconds] = useState<number>(900);
  const [isMinting, setIsMinting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [mintedToken, setMintedToken] = useState<EnrollmentTokenResponse | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [copiedCli, setCopiedCli] = useState<boolean>(false);

  const handleMint = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();
    const cleanPool = poolSlug.trim().toLowerCase();
    if (!/^[a-z0-9][a-z0-9-]{1,62}$/.test(cleanPool)) {
      setError("Pool slug must match '^[a-z0-9][a-z0-9-]{1,62}$' (e.g. default, ci-pool)");
      return;
    }

    try {
      setIsMinting(true);
      setError(null);
      const res = await mintEnrollmentToken({
        pool_slug: cleanPool,
        ttl_seconds: ttlSeconds,
      });
      setMintedToken(res);
      setIsMinting(false);
      onTokenMinted?.();
    } catch (err: unknown) {
      setIsMinting(false);
      setError(err instanceof Error ? err.message : 'Failed to mint enrollment token');
    }
  };

  const handleCopy = async (token: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(token);
    } catch {
      // Fallback
    } finally {
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 2000);
    }
  };

  const handleClose = (): void => {
    // Purge token plaintext from state
    setMintedToken(null);
    setCopied(false);
    setCopiedCli(false);
    onClose();
  };

  const getCliCommand = (token: string, pool: string): string => {
    return `echo "${token}" | uv run kanban-agent-runner enroll --server-url ${window.location.origin} --token-stdin --pool ${pool}`;
  };

  const handleCopyCli = async (command: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(command);
    } catch {
      // Fallback
    } finally {
      setCopiedCli(true);
      setTimeout(() => {
        setCopiedCli(false);
      }, 2000);
    }
  };

  return (
    <div className="kb-modal-card">
      <div className="kb-modal-header">
        <h2 id="mint-token-modal-title">Mint Runner Enrollment Token</h2>
        <button
          type="button"
          className="kb-btn kb-btn-secondary"
          onClick={handleClose}
          aria-label="Close dialog"
          data-testid="close-mint-modal-btn"
        >
          ✕
        </button>
      </div>

      {error && (
        <div className="kb-form-hint kb-mint-token-error" data-testid="mint-token-error">
          {error}
        </div>
      )}

      {!mintedToken ? (
        <form noValidate onSubmit={(e) => { void handleMint(e); }}>
          <p className="kb-runner-studio-subtitle">
            Mint a single-use cryptographically signed enrollment token for an autonomous remote mTLS runner daemon.
          </p>

          <div className="kb-form-group kb-mint-form-group-spaced">
            <label htmlFor="token-pool-slug-input" className="kb-form-label">
              Target Runner Pool Slug
              <FieldHelpHint
                title="Target Runner Pool Slug"
                fieldKey="runner_pool_slug"
                docHref="/docs/multi-provider-ai-engine-and-runners#remote-runners"
                summary="Slug of runner pool that this daemon enrolls into (e.g. default, gpu-cluster, linux-x86)."
                defaultValue="default"
              />
            </label>
            <input
              id="token-pool-slug-input"
              type="text"
              className="kb-form-input"
              value={poolSlug}
              onChange={(e) => { setPoolSlug(e.target.value.toLowerCase()); }}
              placeholder="default"
              required
              data-testid="token-pool-slug-input"
            />
            <span className="kb-form-hint">Alphanumeric with hyphens (e.g. default, ci-cluster).</span>
          </div>

          <div className="kb-form-group">
            <label htmlFor="token-ttl-select" className="kb-form-label">
              Token Expiration (TTL) (Default: 15 minutes)
              <FieldHelpHint
                title="Token Expiration (TTL)"
                summary="Lifetime of the single-use enrollment token before expiry. Enforces 15-minute (900s) default and maximum lifetime, single-use burn-on-first-enrollment (burn-on-first-use) security, and provisions default read-only runner capability scopes until approved."
                defaultValue="15 minutes (900 seconds - Max)"
                docHref="/docs/multi-provider-ai-engine-and-runners#runner-infrastructure-and-protocol-security"
                testId="mint-token-ttl-help"
              />
            </label>
            <select
              id="token-ttl-select"
              className="kb-form-select"
              value={ttlSeconds}
              onChange={(e) => { setTtlSeconds(parseInt(e.target.value, 10)); }}
              data-testid="token-ttl-select"
            >
              <option value={300}>5 minutes (300 seconds)</option>
              <option value={600}>10 minutes (600 seconds)</option>
              <option value={900}>15 minutes (900 seconds - Max)</option>
            </select>
            <span className="kb-form-hint" data-testid="token-ttl-hint">
              15-minute (900s) default and maximum lifetime with single-use burn-on-first-enrollment and default read-only runner capability scopes.
            </span>
          </div>

          <div className="kb-modal-footer">
            <button
              type="button"
              className="kb-btn kb-btn-secondary"
              onClick={handleClose}
              data-testid="cancel-mint-token-btn"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="kb-btn kb-btn-primary"
              disabled={isMinting}
              data-testid="submit-mint-token-btn"
            >
              {isMinting ? 'Minting...' : 'Generate Single-Use Token'}
            </button>
          </div>
        </form>
      ) : (
        <div data-testid="single-reveal-token-view" className="kb-modal-body-container">
          <div className="kb-modal-body">
            <div className="kb-single-reveal-alert" data-testid="single-reveal-warning">
              <strong>Single-Reveal Notice:</strong> This single-use enrollment token is valid for 15 minutes. It is generated once and will never be retrievable again after closing this window. Copy it now and paste it into your runner daemon configuration.
            </div>

            <div className="kb-form-group">
              <label className="kb-form-label">Single-Use Enrollment Token</label>
              <div className="kb-token-display-box">
                <span data-testid="token-plaintext">{mintedToken.enrollment_token}</span>
                <button
                  type="button"
                  className="kb-btn kb-btn-primary kb-copy-token-btn"
                  onClick={() => { void handleCopy(mintedToken.enrollment_token); }}
                  data-testid="copy-token-btn"
                >
                  {copied ? '✓ Copied' : 'Copy'}
                </button>
              </div>
            </div>

            <div className="kb-form-hint kb-mint-expires-hint">
              Expires at: {new Date(mintedToken.expires_at).toLocaleString()} | Pool: <code>{mintedToken.pool_slug}</code>
            </div>

            <div className="kb-form-group">
              <div className="kb-token-label-row">
                <label className="kb-form-label" style={{ marginBottom: 0 }}>
                  Example Runner CLI Ingestion:
                </label>
                <button
                  type="button"
                  className="kb-btn kb-btn-secondary kb-copy-cli-btn"
                  onClick={() => {
                    void handleCopyCli(
                      getCliCommand(mintedToken.enrollment_token, mintedToken.pool_slug),
                    );
                  }}
                  data-testid="copy-runner-cli-btn"
                >
                  {copiedCli ? '✓ Copied!' : 'Copy CLI Command'}
                </button>
              </div>
              <pre className="kb-runner-cli-pre" data-testid="runner-cli-command">
                {getCliCommand(mintedToken.enrollment_token, mintedToken.pool_slug)}
              </pre>
              <div className="kb-form-hint kb-runner-mtls-notice" data-testid="runner-mtls-notice">
                <strong>Dedicated mTLS Endpoint Notice:</strong> Autonomous runners communicate over a dedicated mutual TLS port (default :8444) for Proof-of-Possession handshakes and real-time WebSocket job coordination.
              </div>
            </div>
          </div>

          <div className="kb-modal-footer">
            <button
              type="button"
              className="kb-btn kb-btn-primary"
              onClick={handleClose}
              data-testid="dismiss-mint-modal-btn"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function MintEnrollmentTokenModal({
  isOpen,
  onClose,
  onTokenMinted,
}: MintEnrollmentTokenModalProps): JSX.Element | null {
  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="mint-token-modal-title"
      className="kb-modal-backdrop"
      data-testid="mint-enrollment-token-modal"
    >
      <MintEnrollmentTokenContent
        onClose={onClose}
        onTokenMinted={onTokenMinted}
      />
    </div>
  );
}
