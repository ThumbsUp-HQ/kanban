// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useCallback, type JSX } from 'react';
import { Link } from 'react-router';
import {
  fetchAdminOAuthClients,
  patchAdminOAuthClient,
  deleteAdminOAuthClient,
  registerAdminOAuthClient,
  type OAuthClientItem,
} from './oauthApi';
import { copyToClipboard } from '../../utils/clipboard';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import './OAuthClientGovernanceStudio.css';

export function OAuthClientGovernanceStudio(): JSX.Element {
  const [clients, setClients] = useState<OAuthClientItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null);
  const [inspectClient, setInspectClient] = useState<OAuthClientItem | null>(null);
  const [showRegisterModal, setShowRegisterModal] = useState<boolean>(false);
  const [registerName, setRegisterName] = useState<string>('');
  const [registerUris, setRegisterUris] = useState<string>('');
  const [registerAuthMethod, setRegisterAuthMethod] = useState<'none' | 'private_key_jwt'>('none');
  const [registerSubmitting, setRegisterSubmitting] = useState<boolean>(false);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [registeredClient, setRegisteredClient] = useState<OAuthClientItem | null>(null);
  const [copiedClientId, setCopiedClientId] = useState<boolean>(false);

  const loadClients = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAdminOAuthClients();
      setClients(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load registered OAuth clients.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(() => {
      void loadClients();
    });
  }, [loadClients]);

  const handleApprove = async (clientId: string): Promise<void> => {
    setError(null);
    setSuccessMsg(null);
    try {
      await patchAdminOAuthClient(clientId, { status: 'active' });
      setClients((prev) =>
        prev.map((c) => (c.client_id === clientId ? { ...c, status: 'active' } : c)),
      );
      setSuccessMsg(`Client ${clientId} activated successfully.`);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(`Failed to activate client ${clientId}.`);
      }
    }
  };

  const handleSuspend = async (clientId: string): Promise<void> => {
    setError(null);
    setSuccessMsg(null);
    try {
      await patchAdminOAuthClient(clientId, { status: 'suspended' });
      setClients((prev) =>
        prev.map((c) => (c.client_id === clientId ? { ...c, status: 'suspended' } : c)),
      );
      setSuccessMsg(`Client ${clientId} suspended and active grants revoked.`);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(`Failed to suspend client ${clientId}.`);
      }
    }
  };

  const handleConfirmRevoke = async (clientId: string): Promise<void> => {
    setError(null);
    setSuccessMsg(null);
    try {
      await deleteAdminOAuthClient(clientId);
      setClients((prev) =>
        prev.map((c) => (c.client_id === clientId ? { ...c, status: 'revoked' } : c)),
      );
      setSuccessMsg(`Client ${clientId} revoked permanently.`);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(`Failed to revoke client ${clientId}.`);
      }
    } finally {
      setConfirmRevokeId(null);
    }
  };

  const handleOpenRegister = (): void => {
    setRegisterName('');
    setRegisterUris('');
    setRegisterAuthMethod('none');
    setRegisterError(null);
    setRegisteredClient(null);
    setCopiedClientId(false);
    setShowRegisterModal(true);
  };

  const handleRegisterSubmit = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();
    setRegisterError(null);
    const uris = registerUris
      .split(/[\n,]/)
      .map((u) => u.trim())
      .filter(Boolean);
    if (uris.length === 0) {
      setRegisterError('At least one redirect URI is required.');
      return;
    }
    setRegisterSubmitting(true);
    try {
      const created = await registerAdminOAuthClient({
        client_name: registerName.trim() || 'MCP Client',
        redirect_uris: uris,
        client_type: 'public',
        token_endpoint_auth_method: registerAuthMethod,
      });
      setRegisteredClient(created);
      setClients((prev) => [created, ...prev]);
      setSuccessMsg(`Client "${created.client_name ?? 'Client'}" registered successfully.`);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setRegisterError(err.message);
      } else {
        setRegisterError('Failed to register OAuth client.');
      }
    } finally {
      setRegisterSubmitting(false);
    }
  };

  const handleCopyClientId = async (clientId: string): Promise<void> => {
    const success = await copyToClipboard(clientId);
    if (success) {
      setCopiedClientId(true);
      setTimeout(() => {
        setCopiedClientId(false);
      }, 2000);
    }
  };

  const getStatusBadge = (status: string): JSX.Element => {
    switch (status) {
      case 'active':
        return (
          <span
            className="kb-oauth-gov-badge kb-oauth-gov-badge-active"
            data-testid="status-badge-active"
          >
            Active
          </span>
        );
      case 'suspended':
        return (
          <span
            className="kb-oauth-gov-badge kb-oauth-gov-badge-suspended"
            data-testid="status-badge-suspended"
          >
            Suspended
          </span>
        );
      case 'disabled':
        return (
          <span
            className="kb-oauth-gov-badge kb-oauth-gov-badge-disabled"
            data-testid="status-badge-disabled"
          >
            Disabled
          </span>
        );
      case 'revoked':
      default:
        return (
          <span
            className="kb-oauth-gov-badge kb-oauth-gov-badge-revoked"
            data-testid="status-badge-revoked"
          >
            Revoked
          </span>
        );
    }
  };

  return (
    <div className="kb-oauth-gov-container" data-testid="oauth-client-governance-studio">
      <header className="kb-oauth-gov-header">
        <div>
          <h1 className="kb-oauth-gov-title" data-testid="studio-title">
            OAuth 2.1 + PKCE Client Governance
          </h1>
          <p className="kb-oauth-gov-subtitle">
            Administer registered OAuth 2.1 clients, redirect URIs, and authorization grants
            with zero-trust administrative approval and revocation.
          </p>
        </div>
        <div className="kb-oauth-header-actions">
          <StudioDocLink
            href="/docs/three-surface-mcp-server-architecture"
            title="OAuth 2.1 Governance Documentation"
            testId="oauth-studio-doc-link"
          />
          <button
            type="button"
            className="kb-oauth-gov-refresh-btn"
            data-testid="refresh-clients-btn"
            onClick={() => {
              void loadClients();
            }}
          >
            <span aria-hidden="true">🔄</span> Refresh
          </button>
        </div>
      </header>

      <nav className="kb-mcp-admin-subnav" aria-label="Admin MCP and Governance Navigation">
        <Link to="/admin/mcp" className="kb-mcp-admin-subnav-link" data-testid="tab-admin-mcp">
          Bot API Keys
        </Link>
        <Link
          to="/admin/oauth"
          className="kb-mcp-admin-subnav-link kb-mcp-admin-subnav-active"
          data-testid="tab-admin-oauth"
        >
          OAuth 2.1 Clients
        </Link>
        <Link
          to="/admin/imports"
          className="kb-mcp-admin-subnav-link"
          data-testid="tab-admin-imports"
        >
          Plane Migration Studio
        </Link>
      </nav>

      {error !== null && (
        <div className="kb-oauth-gov-alert kb-oauth-gov-alert-error" role="alert" data-testid="error-alert">
          {error}
        </div>
      )}

      {successMsg !== null && (
        <div
          className="kb-oauth-gov-alert kb-oauth-gov-alert-success"
          role="status"
          data-testid="success-alert"
        >
          {successMsg}
        </div>
      )}

      <section className="kb-oauth-gov-section" data-testid="oauth-clients-section">
        <div className="kb-oauth-gov-section-header">
          <h2 className="kb-oauth-gov-section-title">
            <EmojiHint kind="access" /> Registered OAuth 2.1 Clients
          </h2>
          <button
            type="button"
            className="kb-oauth-gov-register-btn"
            data-testid="register-client-btn"
            onClick={handleOpenRegister}
          >
            + Register OAuth Client
          </button>
        </div>

        <div className="kb-oauth-gov-table-wrap">
          <table className="kb-oauth-gov-table" data-testid="clients-table">
            <thead>
              <tr>
                <th className="kb-oauth-gov-th">Application / Client ID</th>
                <th className="kb-oauth-gov-th">Type</th>
                <th className="kb-oauth-gov-th">Status</th>
                <th className="kb-oauth-gov-th">Redirect URIs</th>
                <th className="kb-oauth-gov-th">Registered</th>
                <th className="kb-oauth-gov-th">Actions</th>
              </tr>
            </thead>
            <tbody>
              {clients.length === 0 && !loading && (
                <tr>
                  <td colSpan={6} className="kb-oauth-gov-empty-state" data-testid="empty-clients">
                    No OAuth 2.1 clients registered. Dynamic client registration (RFC 7591)
                    is available via POST /oauth/register.
                  </td>
                </tr>
              )}
              {clients.map((client) => {
                const isConfirming = confirmRevokeId === client.client_id;
                const isRevoked = client.status === 'revoked';

                return (
                  <tr
                    key={client.client_id}
                    className="kb-oauth-gov-tr"
                    data-testid={`client-row-${client.client_id}`}
                  >
                    <td className="kb-oauth-gov-td">
                      <div className="kb-oauth-gov-client-name" data-testid={`client-name-${client.client_id}`}>
                        {client.client_name ?? client.client_id}
                      </div>
                      <code className="kb-oauth-gov-client-id">{client.client_id}</code>
                    </td>
                    <td className="kb-oauth-gov-td">
                      <span>{client.client_type}</span>
                    </td>
                    <td className="kb-oauth-gov-td" data-testid={`client-status-${client.client_id}`}>
                      {getStatusBadge(client.status)}
                    </td>
                    <td className="kb-oauth-gov-td">
                      <div className="kb-oauth-gov-uri-list">
                        {client.redirect_uris.slice(0, 2).map((uri) => (
                          <span key={uri} className="kb-oauth-gov-uri-code" title={uri}>
                            {uri}
                          </span>
                        ))}
                        {client.redirect_uris.length > 2 && (
                          <span className="kb-oauth-gov-uri-code">
                            +{client.redirect_uris.length - 2} more
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="kb-oauth-gov-td">
                      {client.created_at ? new Date(client.created_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="kb-oauth-gov-td">
                      <div className="kb-oauth-gov-btn-group">
                        <button
                          type="button"
                          className="kb-oauth-gov-btn"
                          data-testid={`inspect-btn-${client.client_id}`}
                          onClick={() => {
                            setInspectClient(client);
                          }}
                        >
                          Inspect
                        </button>

                        {client.status !== 'active' && !isRevoked && (
                          <button
                            type="button"
                            className="kb-oauth-gov-btn kb-oauth-gov-btn-approve"
                            data-testid={`approve-btn-${client.client_id}`}
                            onClick={() => {
                              void handleApprove(client.client_id);
                            }}
                          >
                            Activate
                          </button>
                        )}

                        {client.status === 'active' && (
                          <button
                            type="button"
                            className="kb-oauth-gov-btn kb-oauth-gov-btn-suspend"
                            data-testid={`suspend-btn-${client.client_id}`}
                            onClick={() => {
                              void handleSuspend(client.client_id);
                            }}
                          >
                            Suspend
                          </button>
                        )}

                        {!isRevoked && (
                          <>
                            {isConfirming ? (
                              <div
                                className="kb-oauth-gov-confirm-bar"
                                data-testid={`confirm-revoke-bar-${client.client_id}`}
                              >
                                <button
                                  type="button"
                                  className="kb-oauth-gov-cancel-btn"
                                  data-testid={`cancel-revoke-${client.client_id}`}
                                  autoFocus
                                  onClick={() => {
                                    setConfirmRevokeId(null);
                                  }}
                                >
                                  Cancel
                                </button>
                                <button
                                  type="button"
                                  className="kb-oauth-gov-confirm-revoke-btn"
                                  data-testid={`confirm-revoke-${client.client_id}`}
                                  onClick={() => {
                                    void handleConfirmRevoke(client.client_id);
                                  }}
                                >
                                  Confirm Revoke
                                </button>
                              </div>
                            ) : (
                              <button
                                type="button"
                                className="kb-oauth-gov-btn kb-oauth-gov-btn-revoke"
                                data-testid={`revoke-btn-${client.client_id}`}
                                onClick={() => {
                                  setConfirmRevokeId(client.client_id);
                                }}
                              >
                                Revoke
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Inspect Client Modal */}
      {inspectClient !== null && (
        <div
          className="kb-oauth-modal-backdrop"
          data-testid="inspect-modal-backdrop"
          onClick={() => {
            setInspectClient(null);
          }}
        >
          <div
            className="kb-oauth-modal-card"
            data-testid="inspect-modal-card"
            onClick={(e) => {
              e.stopPropagation();
            }}
          >
            <div className="kb-oauth-modal-header">
              <h3 className="kb-oauth-section-title">
                OAuth Client Details: {inspectClient.client_name ?? inspectClient.client_id}
              </h3>
              <button
                type="button"
                className="kb-oauth-gov-btn"
                data-testid="close-inspect-btn"
                onClick={() => {
                  setInspectClient(null);
                }}
              >
                Close
              </button>
            </div>
            <div className="kb-oauth-modal-body">
              <div className="kb-oauth-detail-row">
                <span className="kb-oauth-detail-label">Client ID</span>
                <code className="kb-oauth-detail-value">{inspectClient.client_id}</code>
              </div>
              <div className="kb-oauth-detail-row">
                <span className="kb-oauth-detail-label">Client Type</span>
                <span className="kb-oauth-detail-value">{inspectClient.client_type}</span>
              </div>
              <div className="kb-oauth-detail-row">
                <span className="kb-oauth-detail-label">Status</span>
                <span className="kb-oauth-detail-value">{getStatusBadge(inspectClient.status)}</span>
              </div>
              <div className="kb-oauth-detail-row">
                <span className="kb-oauth-detail-label">Security Controls</span>
                <span className="kb-oauth-detail-value">
                  PKCE S256 Mandatory - Wildcard Redirects Prohibited (RFC 9700)
                </span>
              </div>
              <div className="kb-oauth-detail-row">
                <span className="kb-oauth-detail-label">Registered Redirect URIs</span>
                <div className="kb-oauth-gov-uri-list">
                  {inspectClient.redirect_uris.map((uri) => (
                    <code key={uri} className="kb-oauth-gov-uri-code">
                      {uri}
                    </code>
                  ))}
                </div>
              </div>
            </div>
            <div className="kb-oauth-modal-footer">
              <button
                type="button"
                className="kb-oauth-gov-btn"
                onClick={() => {
                  setInspectClient(null);
                }}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
      {showRegisterModal && (
        <div
          className="kb-oauth-modal-backdrop"
          data-testid="register-modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget && !registerSubmitting) {
              setShowRegisterModal(false);
            }
          }}
        >
          <div
            className="kb-oauth-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="register-client-modal-title"
            data-testid="register-client-modal"
          >
            <div className="kb-oauth-modal-header">
              <h3 id="register-client-modal-title" className="kb-oauth-modal-title">
                {registeredClient ? 'OAuth Client Registered' : 'Register OAuth 2.1 Client'}
              </h3>
              <button
                type="button"
                className="kb-oauth-modal-close"
                aria-label="Close modal"
                data-testid="close-register-modal-btn"
                onClick={() => {
                  setShowRegisterModal(false);
                }}
              >
                ✕
              </button>
            </div>

            {registeredClient ? (
              <div className="kb-oauth-modal-body" data-testid="register-success-view">
                <p className="kb-oauth-modal-desc">
                  The client application has been registered with status <strong>active</strong>.
                  Copy the assigned Client ID below.
                </p>
                <div className="kb-oauth-detail-row">
                  <span className="kb-oauth-detail-label">Client ID</span>
                  <div className="kb-oauth-copy-row">
                    <code className="kb-oauth-id-code" data-testid="registered-client-id">
                      {registeredClient.client_id}
                    </code>
                    <button
                      type="button"
                      className="kb-oauth-copy-btn"
                      data-testid="copy-client-id-btn"
                      onClick={() => {
                        void handleCopyClientId(registeredClient.client_id);
                      }}
                    >
                      {copiedClientId ? 'Copied!' : 'Copy Client ID'}
                    </button>
                  </div>
                </div>
                <div className="kb-oauth-detail-row">
                  <span className="kb-oauth-detail-label">Client Name</span>
                  <span className="kb-oauth-detail-value">{registeredClient.client_name}</span>
                </div>
                <div className="kb-oauth-detail-row">
                  <span className="kb-oauth-detail-label">Redirect URIs</span>
                  <div className="kb-oauth-gov-uri-list">
                    {registeredClient.redirect_uris.map((uri) => (
                      <code key={uri} className="kb-oauth-gov-uri-code">
                        {uri}
                      </code>
                    ))}
                  </div>
                </div>
                <div className="kb-oauth-modal-footer">
                  <button
                    type="button"
                    className="kb-oauth-gov-btn kb-oauth-gov-btn-primary"
                    data-testid="done-register-btn"
                    onClick={() => {
                      setShowRegisterModal(false);
                    }}
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <form
                onSubmit={(e) => {
                  void handleRegisterSubmit(e);
                }}
                data-testid="register-client-form"
              >
                <div className="kb-oauth-modal-body">
                  {registerError && (
                    <div
                      className="kb-oauth-gov-alert kb-oauth-gov-alert-error"
                      role="alert"
                      data-testid="register-error-alert"
                    >
                      {registerError}
                    </div>
                  )}
                  <div className="kb-oauth-form-field">
                    <label htmlFor="reg-client-name" className="kb-oauth-form-label">
                      Application Name
                    </label>
                    <input
                      id="reg-client-name"
                      type="text"
                      className="kb-oauth-form-input"
                      data-testid="input-client-name"
                      placeholder="e.g. Claude Code or IDE Plugin"
                      value={registerName}
                      onChange={(e) => {
                        setRegisterName(e.target.value);
                      }}
                      disabled={registerSubmitting}
                    />
                  </div>

                  <div className="kb-oauth-form-field">
                    <label htmlFor="reg-redirect-uris" className="kb-oauth-form-label">
                      Redirect URIs (one per line, HTTPS or loopback HTTP)
                      <FieldHelpHint
                        title="Redirect URIs"
                        summary="Strict allowlist of OAuth redirect destinations. RFC 8252 requires HTTPS for web or 127.0.0.1 loopback for native clients."
                        caution="Wildcards, non-loopback http://, and fragments (#) are strictly rejected."
                        docHref="/docs/three-surface-mcp-server-architecture#oauth-21--pkce"
                        testId="reg-redirect-uris-help"
                      />
                    </label>
                    <textarea
                      id="reg-redirect-uris"
                      className="kb-oauth-form-textarea"
                      data-testid="input-redirect-uris"
                      rows={3}
                      placeholder="https://my-app.example.com/oauth/callback&#10;http://127.0.0.1:8080/callback"
                      value={registerUris}
                      onChange={(e) => {
                        setRegisterUris(e.target.value);
                      }}
                      required
                      disabled={registerSubmitting}
                    />
                  </div>

                  <div className="kb-oauth-form-field">
                    <label htmlFor="reg-auth-method" className="kb-oauth-form-label">
                      Token Endpoint Authentication Method
                    </label>
                    <select
                      id="reg-auth-method"
                      className="kb-oauth-form-select"
                      data-testid="select-auth-method"
                      value={registerAuthMethod}
                      onChange={(e) => {
                        setRegisterAuthMethod(e.target.value as 'none' | 'private_key_jwt');
                      }}
                      disabled={registerSubmitting}
                    >
                      <option value="none">none (Public client with PKCE S256)</option>
                      <option value="private_key_jwt">
                        private_key_jwt (Asymmetric client authentication)
                      </option>
                    </select>
                  </div>
                </div>

                <div className="kb-oauth-modal-footer">
                  <button
                    type="button"
                    className="kb-oauth-gov-btn"
                    data-testid="cancel-register-btn"
                    disabled={registerSubmitting}
                    onClick={() => {
                      setShowRegisterModal(false);
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="kb-oauth-gov-btn kb-oauth-gov-btn-primary"
                    data-testid="submit-register-btn"
                    disabled={registerSubmitting}
                  >
                    {registerSubmitting ? 'Registering...' : 'Register Client'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
