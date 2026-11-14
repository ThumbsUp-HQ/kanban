// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, type JSX } from 'react';
import { useParams } from 'react-router';
import {
  fetchPersonalMcpKeys,
  mintPersonalMcpKey,
  revokePersonalMcpKey,
  fetchConnectedApps,
  revokeConnectedApp,
  type McpApiKeyItem,
  type OAuthConnectedApp,
  type ScopeTier,
} from './settingsApi';
import { McpConfigSnippetModal } from './McpConfigSnippetModal';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import './McpAccessStudio.css';

export interface McpAccessStudioProps {
  tier?: ('personal' | 'project' | 'workspace' | 'global') | undefined;
}

export function McpAccessStudio({ tier = 'personal' }: McpAccessStudioProps): JSX.Element {
  const { projectKey = 'KANBA' } = useParams<{ projectKey?: string }>();
  const [keys, setKeys] = useState<McpApiKeyItem[]>([]);
  const [connectedApps, setConnectedApps] = useState<OAuthConnectedApp[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // Mint modal state
  const [showMintModal, setShowMintModal] = useState<boolean>(false);
  const [newKeyLabel, setNewKeyLabel] = useState<string>('');
  const [newKeySurface, setNewKeySurface] = useState<'agent' | 'docs' | 'admin'>('agent');
  const [newKeyExpiry, setNewKeyExpiry] = useState<number>(60);
  const [minting, setMinting] = useState<boolean>(false);

  // Snippet modal state (ephemeral secret)
  const [activeSnippetKey, setActiveSnippetKey] = useState<string | undefined>(undefined);
  const [showSnippetModal, setShowSnippetModal] = useState<boolean>(false);

  // 2-step inline revocation confirmation states
  const [confirmRevokeKeyId, setConfirmRevokeKeyId] = useState<string | null>(null);
  const [confirmRevokeAppId, setConfirmRevokeAppId] = useState<string | null>(null);

  useEffect(() => {
    const isMounted = { current: true };
    void (async () => {
      try {
        const [fetchedKeys, fetchedApps] = await Promise.all([
          fetchPersonalMcpKeys(),
          fetchConnectedApps(),
        ]);
        if (isMounted.current) {
          setKeys(fetchedKeys);
          setConnectedApps(fetchedApps);
          setLoading(false);
        }
      } catch {
        if (isMounted.current) {
          setLoading(false);
        }
      }
    })();

    return () => {
      isMounted.current = false;
    };
  }, [tier, projectKey]);

  const handleMintSubmit = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();
    if (!newKeyLabel.trim()) {
      return;
    }
    setMinting(true);
    try {
      const minted = await mintPersonalMcpKey({
        label: newKeyLabel.trim(),
        surface: newKeySurface,
        scopes: [`${newKeySurface}:read`, `${newKeySurface}:write`],
        allowed_projects: tier === 'project' ? [projectKey] : undefined,
        expires_in_days: newKeyExpiry,
      });

      // Update keys table (table receives key item with display_hint only)
      setKeys((prev) => [minted, ...prev]);

      // Open Snippet modal with ephemeral plaintext key
      setActiveSnippetKey(minted.raw_key);
      setShowMintModal(false);
      setShowSnippetModal(true);
      setNewKeyLabel('');
    } catch {
      // Handle error
    } finally {
      setMinting(false);
    }
  };

  const handleConfirmRevokeKey = async (keyId: string): Promise<void> => {
    try {
      await revokePersonalMcpKey(keyId);
      setKeys((prev) =>
        prev.map((k) =>
          k.id === keyId ? { ...k, revoked_at: new Date().toISOString() } : k,
        ),
      );
    } catch {
      // Handle error
    } finally {
      setConfirmRevokeKeyId(null);
    }
  };

  const handleConfirmRevokeApp = async (grantId: string): Promise<void> => {
    try {
      await revokeConnectedApp(grantId);
      setConnectedApps((prev) => prev.filter((app) => app.id !== grantId));
    } catch {
      // Handle error
    } finally {
      setConfirmRevokeAppId(null);
    }
  };

  const getTierBadge = (keyTier: ScopeTier): JSX.Element => {
    if (keyTier === 'global') {
      return (
        <span className="kb-mcp-tier-badge kb-mcp-tier-global" data-testid="tier-badge-global">
          <EmojiHint kind="access" /> Global
        </span>
      );
    }
    if (keyTier === 'workspace') {
      return (
        <span className="kb-mcp-tier-badge kb-mcp-tier-workspace" data-testid="tier-badge-workspace">
          <EmojiHint kind="access" /> Workspace: kanban
        </span>
      );
    }
    if (keyTier === 'project') {
      return (
        <span className="kb-mcp-tier-badge kb-mcp-tier-project" data-testid="tier-badge-project">
          <EmojiHint kind="access" /> Project: {projectKey}
        </span>
      );
    }
    return (
      <span className="kb-mcp-tier-badge kb-mcp-tier-personal" data-testid="tier-badge-personal">
        <EmojiHint kind="access" /> Personal
      </span>
    );
  };

  const titleForTier = {
    personal: 'Personal MCP Keys & Connected Apps',
    project: `Project (${projectKey}) MCP Bot Keys`,
    workspace: 'Workspace MCP Bot Keys & Client Approvals',
    global: 'Global Cross-Workspace Bot Keys (meatloaf-bot)',
  }[tier];

  return (
    <div className="kb-mcp-studio-container" data-testid="mcp-access-studio">
      <header className="kb-mcp-studio-header">
        <div>
          <h1 className="kb-mcp-studio-title" data-testid="studio-title">{titleForTier}</h1>
          <p className="kb-mcp-studio-subtitle">
            Mint and manage Model Context Protocol API keys with explicit scope tiers and one-click revocation.
          </p>
        </div>
        <button
          type="button"
          className="kb-mcp-studio-mint-btn"
          data-testid="mint-key-button"
          onClick={() => {
            setShowMintModal(true);
          }}
        >
          + Mint MCP Key
        </button>
      </header>

      {/* MCP Keys Table Section */}
      <section className="kb-mcp-studio-section" data-testid="mcp-keys-section">
        <h2 className="kb-mcp-section-title">
          <EmojiHint kind="agent" /> Active MCP Keys
        </h2>
        <div className="kb-mcp-table-wrap">
          <table className="kb-mcp-table" data-testid="mcp-keys-table">
            <thead>
              <tr>
                <th className="kb-mcp-th">Label</th>
                <th className="kb-mcp-th">Key Hint</th>
                <th className="kb-mcp-th">Scope Tier</th>
                <th className="kb-mcp-th">Surface</th>
                <th className="kb-mcp-th">Status</th>
                <th className="kb-mcp-th">Actions</th>
              </tr>
            </thead>
            <tbody>
              {keys.length === 0 && !loading && (
                <tr>
                  <td colSpan={6} className="kb-mcp-empty-state">
                    No active MCP keys configured. Click "+ Mint MCP Key" to create one.
                  </td>
                </tr>
              )}
              {keys.map((k) => {
                const isRevoked = Boolean(k.revoked_at);
                const isConfirming = confirmRevokeKeyId === k.id;
                const prefix = k.surface === 'agent' ? 'kb_agt_' : k.surface === 'docs' ? 'kb_doc_' : 'kb_adm_';

                return (
                  <tr key={k.id} className="kb-mcp-tr" data-testid={`key-row-${k.id}`}>
                    <td className="kb-mcp-td">
                      <span className={isRevoked ? 'kb-mcp-status-revoked' : ''}>{k.label}</span>
                    </td>
                    <td className="kb-mcp-td">
                      <code className="kb-mcp-key-hint" data-testid={`key-hint-${k.id}`}>
                        {prefix}...{k.display_hint}
                      </code>
                    </td>
                    <td className="kb-mcp-td">{getTierBadge(k.scope_tier)}</td>
                    <td className="kb-mcp-td">{k.surface.toUpperCase()}</td>
                    <td className="kb-mcp-td">
                      {isRevoked ? (
                        <span className="kb-mcp-status-revoked" data-testid="status-revoked">Revoked</span>
                      ) : (
                        <span>Active</span>
                      )}
                    </td>
                    <td className="kb-mcp-td">
                      {!isRevoked && (
                        <>
                          {isConfirming ? (
                            <div className="kb-mcp-confirm-bar" data-testid="confirm-revoke-bar">
                              <button
                                type="button"
                                className="kb-mcp-cancel-btn"
                                data-testid="cancel-revoke-btn"
                                autoFocus
                                onClick={() => {
                                  setConfirmRevokeKeyId(null);
                                }}
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                className="kb-mcp-confirm-revoke-btn"
                                data-testid="confirm-revoke-btn"
                                onClick={() => {
                                  void handleConfirmRevokeKey(k.id);
                                }}
                              >
                                Confirm Revoke
                              </button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              className="kb-mcp-action-btn"
                              data-testid={`revoke-btn-${k.id}`}
                              onClick={() => {
                                setConfirmRevokeKeyId(k.id);
                              }}
                            >
                              Revoke
                            </button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Connected OAuth Apps Section */}
      <section className="kb-mcp-studio-section" data-testid="connected-apps-section">
        <h2 className="kb-mcp-section-title">
          <EmojiHint kind="restricted" /> Connected OAuth Apps
        </h2>
        <div className="kb-mcp-table-wrap">
          <table className="kb-mcp-table" data-testid="connected-apps-table">
            <thead>
              <tr>
                <th className="kb-mcp-th">Application</th>
                <th className="kb-mcp-th">Client ID</th>
                <th className="kb-mcp-th">Surface</th>
                <th className="kb-mcp-th">Connected Date</th>
                <th className="kb-mcp-th">Actions</th>
              </tr>
            </thead>
            <tbody>
              {connectedApps.length === 0 && !loading && (
                <tr>
                  <td colSpan={5} className="kb-mcp-empty-state">
                    No external OAuth applications currently connected.
                  </td>
                </tr>
              )}
              {connectedApps.map((app) => {
                const isConfirming = confirmRevokeAppId === app.id;

                return (
                  <tr key={app.id} className="kb-mcp-tr" data-testid={`app-row-${app.id}`}>
                    <td className="kb-mcp-td" data-testid={`app-name-${app.id}`}>
                      {/* Render client_name strictly as text node against XSS */}
                      <span>{app.client_name ?? app.client_id}</span>
                    </td>
                    <td className="kb-mcp-td">
                      <code>{app.client_id}</code>
                    </td>
                    <td className="kb-mcp-td">{app.surface.toUpperCase()}</td>
                    <td className="kb-mcp-td">
                      {new Date(app.created_at).toLocaleDateString()}
                    </td>
                    <td className="kb-mcp-td">
                      {isConfirming ? (
                        <div className="kb-mcp-confirm-bar" data-testid="confirm-disconnect-bar">
                          <button
                            type="button"
                            className="kb-mcp-cancel-btn"
                            data-testid="cancel-disconnect-btn"
                            autoFocus
                            onClick={() => {
                              setConfirmRevokeAppId(null);
                            }}
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            className="kb-mcp-confirm-revoke-btn"
                            data-testid="confirm-disconnect-btn"
                            onClick={() => {
                              void handleConfirmRevokeApp(app.id);
                            }}
                          >
                            Confirm Disconnect
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="kb-mcp-action-btn"
                          data-testid={`disconnect-btn-${app.id}`}
                          onClick={() => {
                            setConfirmRevokeAppId(app.id);
                          }}
                        >
                          Disconnect
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Mint Key Modal */}
      {showMintModal && (
        <div
          className="kb-snippet-modal-backdrop"
          data-testid="mint-modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowMintModal(false);
            }
          }}
        >
          <div
            className="kb-snippet-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mint-modal-title"
          >
            <div className="kb-snippet-modal-header">
              <h2 id="mint-modal-title" className="kb-snippet-modal-title">Mint New MCP Access Key</h2>
              <button
                type="button"
                className="kb-snippet-modal-close-btn"
                onClick={() => {
                  setShowMintModal(false);
                }}
              >
                x
              </button>
            </div>
            <form
              onSubmit={(e) => {
                void handleMintSubmit(e);
              }}
              className="kb-mcp-mint-form"
            >
              <div className="kb-mcp-form-row">
                <label htmlFor="mint-label-input" className="kb-mcp-form-label">
                  Key Label:
                </label>
                <input
                  id="mint-label-input"
                  type="text"
                  className="kb-mcp-form-input"
                  data-testid="mint-label-input"
                  placeholder="e.g. CI Agent Token"
                  value={newKeyLabel}
                  onChange={(e) => {
                    setNewKeyLabel(e.target.value);
                  }}
                  autoFocus
                  required
                />
              </div>

              <div className="kb-mcp-form-row">
                <label htmlFor="mint-surface-select" className="kb-mcp-form-label">
                  Target Surface:
                </label>
                <select
                  id="mint-surface-select"
                  className="kb-mcp-form-select"
                  data-testid="mint-surface-select"
                  value={newKeySurface}
                  onChange={(e) => {
                    setNewKeySurface(e.target.value as 'agent' | 'docs' | 'admin');
                  }}
                >
                  <option value="agent">/mcp/agent (Standard Tools)</option>
                  <option value="docs">/mcp/docs (Knowledge & Markdown)</option>
                  <option value="admin">/mcp/admin (Administrative Ops)</option>
                </select>
              </div>

              <div className="kb-mcp-form-row">
                <label htmlFor="mint-expiry-select" className="kb-mcp-form-label">
                  Expiration:
                </label>
                <select
                  id="mint-expiry-select"
                  className="kb-mcp-form-select"
                  data-testid="mint-expiry-select"
                  value={newKeyExpiry}
                  onChange={(e) => {
                    setNewKeyExpiry(Number(e.target.value));
                  }}
                >
                  <option value={30}>30 Days</option>
                  <option value={60}>60 Days</option>
                  <option value={90}>90 Days</option>
                  <option value={365}>1 Year</option>
                </select>
              </div>

              <div className="kb-mcp-form-actions">
                <button
                  type="button"
                  className="kb-snippet-copy-btn"
                  onClick={() => {
                    setShowMintModal(false);
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kb-snippet-done-btn"
                  data-testid="mint-submit-btn"
                  disabled={minting || !newKeyLabel.trim()}
                >
                  {minting ? 'Minting...' : 'Mint Key'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Snippet / Plaintext Key Modal */}
      {showSnippetModal && (
        <McpConfigSnippetModal
          rawKey={activeSnippetKey}
          surface={newKeySurface}
          projectKey={projectKey}
          onClose={() => {
            // Memory wipe: clear plaintext secret from state upon close
            setActiveSnippetKey(undefined);
            setShowSnippetModal(false);
          }}
        />
      )}
    </div>
  );
}
