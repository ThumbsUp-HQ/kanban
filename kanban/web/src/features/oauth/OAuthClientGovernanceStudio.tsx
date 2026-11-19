// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, type JSX } from 'react';
import { Link } from 'react-router';
import {
  fetchAdminOAuthClients,
  patchAdminOAuthClient,
  deleteAdminOAuthClient,
  type OAuthClientItem,
} from './oauthApi';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import './OAuthClientGovernanceStudio.css';

export function OAuthClientGovernanceStudio(): JSX.Element {
  const [clients, setClients] = useState<OAuthClientItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null);
  const [inspectClient, setInspectClient] = useState<OAuthClientItem | null>(null);

  useEffect(() => {
    const isMounted = { current: true };
    void (async () => {
      try {
        const data = await fetchAdminOAuthClients();
        if (isMounted.current) {
          setClients(data);
          setLoading(false);
        }
      } catch (err: unknown) {
        if (isMounted.current) {
          if (err instanceof Error) {
            setError(err.message);
          } else {
            setError('Failed to load registered OAuth clients.');
          }
          setLoading(false);
        }
      }
    })();
    return () => {
      isMounted.current = false;
    };
  }, []);

  const loadClients = async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAdminOAuthClients();
      setClients(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to load registered OAuth clients.');
      }
    } finally {
      setLoading(false);
    }
  };

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
    </div>
  );
}
