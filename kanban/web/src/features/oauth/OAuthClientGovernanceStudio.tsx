// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useCallback, type JSX } from 'react';
import {
  fetchAdminOAuthClients,
  patchAdminOAuthClient,
  deleteAdminOAuthClient,
  bulkDeleteAdminOAuthClients,
  registerAdminOAuthClient,
  type OAuthClientItem,
  type OAuthClientStatus,
} from './oauthApi';
import { copyToClipboard } from '../../utils/clipboard';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { AdminStudioSubnav } from '../admin/AdminStudioSubnav';
import { AdvancedSection } from '../../ui/AdvancedSection';
import { ErrorHelpHint } from '../../components/help/ErrorHelpHint';
import { isAal2StepUpCancelled } from '../../api/client';
import './OAuthClientGovernanceStudio.css';

export interface OAuthClientGovernanceStudioProps {
  isServerAdmin?: boolean;
}

export function OAuthClientGovernanceStudio({ isServerAdmin = true }: OAuthClientGovernanceStudioProps = {}): JSX.Element {
  const [clients, setClients] = useState<OAuthClientItem[]>([]);
  const [totalClients, setTotalClients] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Filters and Pagination
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'suspended' | 'revoked'>('all');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const pageSize = 50;

  // Selection
  const [selectedClientIds, setSelectedClientIds] = useState<Set<string>>(new Set());

  // Confirmations
  const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmBulkDelete, setConfirmBulkDelete] = useState<boolean>(false);
  const [confirmPurge, setConfirmPurge] = useState<boolean>(false);

  // Inspect Modal
  const [inspectClient, setInspectClient] = useState<OAuthClientItem | null>(null);

  // Register Modal
  const [showRegisterModal, setShowRegisterModal] = useState<boolean>(false);
  const [registerName, setRegisterName] = useState<string>('');
  const [registerUris, setRegisterUris] = useState<string>('');
  const [registerClientType, setRegisterClientType] = useState<'public' | 'confidential'>('public');
  const [registerAuthMethod, setRegisterAuthMethod] = useState<
    'none' | 'private_key_jwt' | 'client_secret_basic' | 'client_secret_post'
  >('none');
  const [registerPkceEnforce, setRegisterPkceEnforce] = useState<boolean>(true);
  const [registerAccessTokenTtl, setRegisterAccessTokenTtl] = useState<number>(3600);
  const [registerGrantTypes, setRegisterGrantTypes] = useState<string>(
    'authorization_code,refresh_token',
  );
  const [registerSubmitting, setRegisterSubmitting] = useState<boolean>(false);
  const [registerError, setRegisterError] = useState<string | null>(null);
  const [registeredClient, setRegisteredClient] = useState<OAuthClientItem | null>(null);
  const [copiedClientId, setCopiedClientId] = useState<boolean>(false);
  const [copiedClientSecret, setCopiedClientSecret] = useState<boolean>(false);

  // Edit URIs Modal
  const [editClient, setEditClient] = useState<OAuthClientItem | null>(null);
  const [editUris, setEditUris] = useState<string>('');
  const [editSubmitting, setEditSubmitting] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);

  const loadClients = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const offset = (currentPage - 1) * pageSize;
      const res = await fetchAdminOAuthClients({
        q: searchQuery.trim() || undefined,
        status: statusFilter,
        limit: pageSize,
        offset,
        envelope: true,
      });
      if (Array.isArray(res)) {
        setClients(res);
        setTotalClients(res.length);
      } else if (Array.isArray(res.items)) {
        setClients(res.items);
        setTotalClients(res.total);
      } else {
        setClients([]);
        setTotalClients(0);
      }
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to load registered OAuth clients.');
    } finally {
      setLoading(false);
    }
  }, [currentPage, pageSize, searchQuery, statusFilter]);

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
      if (isAal2StepUpCancelled(err)) {
        return;
      }
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
      if (isAal2StepUpCancelled(err)) {
        return;
      }
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
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(`Failed to revoke client ${clientId}.`);
      }
    } finally {
      setConfirmRevokeId(null);
    }
  };

  const handleConfirmDelete = async (clientId: string): Promise<void> => {
    setError(null);
    setSuccessMsg(null);
    try {
      await deleteAdminOAuthClient(clientId, { permanent: true });
      setClients((prev) => prev.filter((c) => c.client_id !== clientId));
      setTotalClients((prev) => Math.max(0, prev - 1));
      setSelectedClientIds((prev) => {
        const next = new Set(prev);
        next.delete(clientId);
        return next;
      });
      setSuccessMsg(`Client ${clientId} permanently deleted.`);
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(`Failed to delete client ${clientId}.`);
      }
    } finally {
      setConfirmDeleteId(null);
    }
  };

  const handleBulkDelete = async (): Promise<void> => {
    if (selectedClientIds.size === 0) {
      return;
    }
    setError(null);
    setSuccessMsg(null);
    try {
      const ids = Array.from(selectedClientIds);
      const res = await bulkDeleteAdminOAuthClients({ client_ids: ids });
      setSelectedClientIds(new Set());
      setSuccessMsg(`Permanently deleted ${String(res.deleted_count)} selected OAuth client(s).`);
      void loadClients();
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to delete selected OAuth clients.');
      }
    } finally {
      setConfirmBulkDelete(false);
    }
  };

  const handlePurgeStale = async (): Promise<void> => {
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await bulkDeleteAdminOAuthClients({
        purge_unused_dcr: true,
        purge_revoked: true,
      });
      setSelectedClientIds(new Set());
      setSuccessMsg(`Purged ${String(res.deleted_count)} unused DCR and revoked OAuth client(s).`);
      void loadClients();
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to purge stale OAuth clients.');
      }
    } finally {
      setConfirmPurge(false);
    }
  };

  const handleToggleSelectAll = (): void => {
    if (selectedClientIds.size === clients.length && clients.length > 0) {
      setSelectedClientIds(new Set());
    } else {
      setSelectedClientIds(new Set(clients.map((c) => c.client_id)));
    }
  };

  const handleToggleSelectRow = (clientId: string): void => {
    setSelectedClientIds((prev) => {
      const next = new Set(prev);
      if (next.has(clientId)) {
        next.delete(clientId);
      } else {
        next.add(clientId);
      }
      return next;
    });
  };

  const handleOpenRegister = (): void => {
    setRegisterName('');
    setRegisterUris('');
    setRegisterClientType('public');
    setRegisterAuthMethod('none');
    setRegisterPkceEnforce(true);
    setRegisterAccessTokenTtl(3600);
    setRegisterGrantTypes('authorization_code,refresh_token');
    setRegisterError(null);
    setRegisteredClient(null);
    setCopiedClientId(false);
    setCopiedClientSecret(false);
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
      const grants = registerGrantTypes
        .split(/[\n,]/)
        .map((g) => g.trim())
        .filter(Boolean);
      const created = await registerAdminOAuthClient({
        client_name: registerName.trim() || 'MCP Client',
        redirect_uris: uris,
        client_type: registerClientType,
        token_endpoint_auth_method: registerAuthMethod,
        pkce_enforce: registerPkceEnforce,
        access_token_ttl: registerAccessTokenTtl,
        grant_types: grants.length > 0 ? grants : undefined,
      });
      setRegisteredClient(created);
      setClients((prev) => [created, ...prev]);
      setTotalClients((prev) => prev + 1);
      setSuccessMsg(`Client "${created.client_name ?? 'Client'}" registered successfully.`);
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
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

  const handleCopyClientSecret = async (secret: string): Promise<void> => {
    const success = await copyToClipboard(secret);
    if (success) {
      setCopiedClientSecret(true);
      setTimeout(() => {
        setCopiedClientSecret(false);
      }, 2000);
    }
  };

  const handleOpenEditUris = (client: OAuthClientItem): void => {
    setEditClient(client);
    setEditUris(client.redirect_uris.join('\n'));
    setEditError(null);
  };

  const handleEditUrisSubmit = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();
    if (!editClient) {
      return;
    }
    setEditError(null);
    const uris = editUris
      .split(/[\n,]/)
      .map((u) => u.trim())
      .filter(Boolean);
    if (uris.length === 0) {
      setEditError('At least one redirect URI is required.');
      return;
    }
    if (uris.length > 16) {
      setEditError('Maximum 16 redirect URIs permitted.');
      return;
    }
    setEditSubmitting(true);
    try {
      await patchAdminOAuthClient(editClient.client_id, { redirect_uris: uris });
      setClients((prev) =>
        prev.map((c) =>
          c.client_id === editClient.client_id ? { ...c, redirect_uris: uris } : c,
        ),
      );
      setSuccessMsg(`Redirect URIs updated for client ${editClient.client_id}.`);
      setEditClient(null);
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      if (err instanceof Error) {
        setEditError(err.message);
      } else {
        setEditError('Failed to update redirect URIs.');
      }
    } finally {
      setEditSubmitting(false);
    }
  };

  const getStatusBadge = (status: OAuthClientStatus): JSX.Element => {
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
      case 'pending_admin_approval':
        return (
          <span
            className="kb-oauth-gov-badge kb-oauth-gov-badge-pending"
            data-testid="status-badge-pending"
          >
            Pending
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

  const totalPages = Math.max(1, Math.ceil(totalClients / pageSize));
  const startItem = totalClients === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalClients);

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

      <AdminStudioSubnav activeTab="oauth" isServerAdmin={isServerAdmin} />

      {error !== null && (
        <div className="kb-oauth-gov-alert kb-oauth-gov-alert-error" role="alert" data-testid="error-alert">
          <span>{error}</span>
          <ErrorHelpHint error={error} />
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

        {/* Toolbar: Search, Status Filter Pills, Bulk Delete, Purge */}
        <div className="kb-oauth-gov-toolbar" data-testid="oauth-clients-toolbar">
          <div className="kb-oauth-gov-toolbar-left">
            <div className="kb-oauth-gov-search-wrap">
              <input
                type="text"
                className="kb-oauth-gov-search-input"
                data-testid="search-clients-input"
                placeholder="Search clients, IDs, URIs..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
              />
            </div>
            <div className="kb-oauth-filter-pills" role="radiogroup" aria-label="Filter by client status">
              <button
                type="button"
                className={`kb-oauth-filter-pill ${statusFilter === 'all' ? 'kb-oauth-filter-pill-active' : ''}`}
                data-testid="filter-pill-all"
                onClick={() => {
                  setStatusFilter('all');
                  setCurrentPage(1);
                }}
              >
                All
              </button>
              <button
                type="button"
                className={`kb-oauth-filter-pill ${statusFilter === 'active' ? 'kb-oauth-filter-pill-active' : ''}`}
                data-testid="filter-pill-active"
                onClick={() => {
                  setStatusFilter('active');
                  setCurrentPage(1);
                }}
              >
                Active
              </button>
              <button
                type="button"
                className={`kb-oauth-filter-pill ${statusFilter === 'suspended' ? 'kb-oauth-filter-pill-active' : ''}`}
                data-testid="filter-pill-suspended"
                onClick={() => {
                  setStatusFilter('suspended');
                  setCurrentPage(1);
                }}
              >
                Suspended
              </button>
              <button
                type="button"
                className={`kb-oauth-filter-pill ${statusFilter === 'revoked' ? 'kb-oauth-filter-pill-active' : ''}`}
                data-testid="filter-pill-revoked"
                onClick={() => {
                  setStatusFilter('revoked');
                  setCurrentPage(1);
                }}
              >
                Revoked
              </button>
            </div>
          </div>

          <div className="kb-oauth-gov-toolbar-right">
            {selectedClientIds.size > 0 && (
              <>
                {confirmBulkDelete ? (
                  <div className="kb-oauth-gov-bulk-confirm-bar" data-testid="bulk-delete-confirm-bar">
                    <button
                      type="button"
                      className="kb-oauth-gov-cancel-btn"
                      data-testid="cancel-bulk-delete-btn"
                      onClick={() => {
                        setConfirmBulkDelete(false);
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="kb-oauth-gov-confirm-delete-btn"
                      data-testid="confirm-bulk-delete-btn"
                      onClick={() => {
                        void handleBulkDelete();
                      }}
                    >
                      Confirm Delete ({selectedClientIds.size})
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="kb-oauth-gov-bulk-delete-btn"
                    data-testid="delete-selected-btn"
                    onClick={() => {
                      setConfirmBulkDelete(true);
                    }}
                  >
                    Delete Selected ({selectedClientIds.size})
                  </button>
                )}
              </>
            )}

            {confirmPurge ? (
              <div className="kb-oauth-gov-bulk-confirm-bar" data-testid="purge-confirm-bar">
                <button
                  type="button"
                  className="kb-oauth-gov-cancel-btn"
                  data-testid="cancel-purge-btn"
                  onClick={() => {
                    setConfirmPurge(false);
                  }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="kb-oauth-gov-confirm-delete-btn"
                  data-testid="confirm-purge-btn"
                  onClick={() => {
                    void handlePurgeStale();
                  }}
                >
                  Confirm Purge
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="kb-oauth-gov-purge-btn"
                data-testid="purge-clients-btn"
                onClick={() => {
                  setConfirmPurge(true);
                }}
              >
                Purge Unused / Revoked Clients
              </button>
            )}
          </div>
        </div>

        <div className="kb-oauth-gov-table-wrap">
          <table className="kb-oauth-gov-table" data-testid="clients-table">
            <thead>
              <tr>
                <th className="kb-oauth-gov-th kb-oauth-gov-col-select">
                  <input
                    type="checkbox"
                    className="kb-oauth-gov-checkbox"
                    data-testid="select-all-clients-checkbox"
                    aria-label="Select all clients"
                    checked={clients.length > 0 && selectedClientIds.size === clients.length}
                    onChange={handleToggleSelectAll}
                  />
                </th>
                <th className="kb-oauth-gov-th kb-oauth-gov-col-app">Application / Client ID</th>
                <th className="kb-oauth-gov-th kb-oauth-gov-col-type">Type</th>
                <th className="kb-oauth-gov-th kb-oauth-gov-col-status">Status</th>
                <th className="kb-oauth-gov-th kb-oauth-gov-col-uris">Redirect URIs</th>
                <th className="kb-oauth-gov-th kb-oauth-gov-col-date">Registered</th>
                <th className="kb-oauth-gov-th kb-oauth-gov-col-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {clients.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="kb-oauth-gov-empty-state" data-testid="empty-clients">
                    No OAuth 2.1 clients registered. Dynamic client registration (RFC 7591)
                    is available via POST /oauth/register.
                  </td>
                </tr>
              )}
              {clients.map((client) => {
                const isConfirmingRevoke = confirmRevokeId === client.client_id;
                const isConfirmingDelete = confirmDeleteId === client.client_id;
                const isRevoked = client.status === 'revoked';
                const isSelected = selectedClientIds.has(client.client_id);

                return (
                  <tr
                    key={client.client_id}
                    className="kb-oauth-gov-tr"
                    data-testid={`client-row-${client.client_id}`}
                  >
                    <td className="kb-oauth-gov-td kb-oauth-gov-col-select">
                      <input
                        type="checkbox"
                        className="kb-oauth-gov-checkbox"
                        data-testid={`select-client-checkbox-${client.client_id}`}
                        aria-label={`Select ${client.client_name ?? client.client_id}`}
                        checked={isSelected}
                        onChange={() => {
                          handleToggleSelectRow(client.client_id);
                        }}
                      />
                    </td>
                    <td className="kb-oauth-gov-td kb-oauth-gov-col-app">
                      <div className="kb-oauth-gov-client-name" data-testid={`client-name-${client.client_id}`}>
                        {client.client_name ?? client.client_id}
                      </div>
                      <code className="kb-oauth-gov-client-id">{client.client_id}</code>
                    </td>
                    <td className="kb-oauth-gov-td kb-oauth-gov-col-type">
                      <span>{client.client_type}</span>
                    </td>
                    <td className="kb-oauth-gov-td kb-oauth-gov-col-status" data-testid={`client-status-${client.client_id}`}>
                      {getStatusBadge(client.status)}
                    </td>
                    <td className="kb-oauth-gov-td kb-oauth-gov-col-uris">
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
                    <td className="kb-oauth-gov-td kb-oauth-gov-col-date">
                      {client.created_at ? new Date(client.created_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="kb-oauth-gov-td kb-oauth-gov-col-actions kb-oauth-gov-td-actions">
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

                        {!isRevoked && (
                          <button
                            type="button"
                            className="kb-oauth-gov-btn"
                            data-testid={`edit-uris-btn-${client.client_id}`}
                            onClick={() => {
                              handleOpenEditUris(client);
                            }}
                          >
                            Edit URIs
                          </button>
                        )}

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
                            {isConfirmingRevoke ? (
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

                        {isConfirmingDelete ? (
                          <div
                            className="kb-oauth-gov-confirm-bar"
                            data-testid={`confirm-delete-bar-${client.client_id}`}
                          >
                            <button
                              type="button"
                              className="kb-oauth-gov-cancel-btn"
                              data-testid={`cancel-delete-${client.client_id}`}
                              autoFocus
                              onClick={() => {
                                setConfirmDeleteId(null);
                              }}
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              className="kb-oauth-gov-confirm-delete-btn"
                              data-testid={`confirm-delete-${client.client_id}`}
                              onClick={() => {
                                void handleConfirmDelete(client.client_id);
                              }}
                            >
                              Confirm Delete
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            className="kb-oauth-gov-btn kb-oauth-gov-btn-delete"
                            data-testid={`delete-btn-${client.client_id}`}
                            onClick={() => {
                              setConfirmDeleteId(client.client_id);
                            }}
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination controls */}
        {totalClients > 0 && (
          <div className="kb-oauth-gov-pagination" data-testid="oauth-clients-pagination">
            <span className="kb-oauth-gov-page-info" data-testid="pagination-info">
              Showing {startItem}-{endItem} of {totalClients}
            </span>
            <div className="kb-oauth-gov-page-controls">
              <button
                type="button"
                className="kb-oauth-gov-page-btn"
                data-testid="prev-page-btn"
                disabled={currentPage <= 1}
                onClick={() => {
                  setCurrentPage((prev) => Math.max(1, prev - 1));
                }}
              >
                Previous
              </button>
              <button
                type="button"
                className="kb-oauth-gov-page-btn"
                data-testid="next-page-btn"
                disabled={currentPage >= totalPages}
                onClick={() => {
                  setCurrentPage((prev) => Math.min(totalPages, prev + 1));
                }}
              >
                Next
              </button>
            </div>
          </div>
        )}
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
              {inspectClient.client_secret_prefix && (
                <div className="kb-oauth-detail-row">
                  <span className="kb-oauth-detail-label">Client Secret</span>
                  <span className="kb-oauth-detail-value" data-testid="inspect-client-secret-prefix">
                    {inspectClient.client_secret_prefix} (Masked)
                  </span>
                </div>
              )}
              {inspectClient.token_endpoint_auth_method && (
                <div className="kb-oauth-detail-row">
                  <span className="kb-oauth-detail-label">Auth Method</span>
                  <span className="kb-oauth-detail-value">{inspectClient.token_endpoint_auth_method}</span>
                </div>
              )}
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

      {/* Register OAuth Client Modal */}
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
                {registeredClient.client_secret && (
                  <div className="kb-oauth-client-secret-panel" data-testid="client-secret-panel">
                    <div className="kb-oauth-secret-warning" role="alert" data-testid="secret-warning">
                      <strong>Important:</strong> Copy this Client Secret immediately. For security, it will never be displayed again.
                    </div>
                    <div className="kb-oauth-detail-row">
                      <span className="kb-oauth-detail-label">Client Secret</span>
                      <div className="kb-oauth-copy-row">
                        <code className="kb-oauth-secret-code" data-testid="registered-client-secret">
                          {registeredClient.client_secret}
                        </code>
                        <button
                          type="button"
                          className="kb-oauth-copy-btn"
                          data-testid="copy-client-secret-btn"
                          onClick={() => {
                            const secret = registeredClient.client_secret;
                            if (secret) {
                              void handleCopyClientSecret(secret);
                            }
                          }}
                        >
                          {copiedClientSecret ? 'Copied!' : 'Copy Client Secret'}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
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
                    <label htmlFor="reg-client-type" className="kb-oauth-form-label">
                      <span className="kb-oauth-label-text">
                        Client Type{' '}
                        <span
                          className="kb-oauth-default-indicator"
                          data-testid="reg-client-type-default-indicator"
                        >
                          (Default: Public (PKCE only))
                        </span>
                      </span>
                      <FieldHelpHint
                        title="Client Type"
                        summary="Client classification under RFC 9700 and OAuth 2.1. Public clients (desktop apps, SPAs, CLI tools) cannot securely hold client credentials and must use PKCE S256. Confidential clients execute on protected backend servers and authenticate using client secrets or private key JWTs."
                        defaultValue="Public (PKCE only)"
                        validValues={[
                          {
                            label: 'public',
                            description:
                              'Public (PKCE only) - Native apps, single-page apps, and CLI agents unable to protect client credentials (RFC 9700)',
                          },
                          {
                            label: 'confidential',
                            description:
                              'Confidential (Client Secret + PKCE) - Secure backend workloads and daemon services holding protected secrets',
                          },
                        ]}
                        docHref="/docs/three-surface-mcp-server-architecture#oauth-21--pkce"
                        testId="reg-client-type-help"
                        ariaLabel="Help for Client Type"
                      />
                    </label>
                    <select
                      id="reg-client-type"
                      aria-describedby="reg-client-type-hint"
                      className="kb-oauth-form-select"
                      data-testid="select-client-type"
                      value={registerClientType}
                      onChange={(e) => {
                        const type = e.target.value as 'public' | 'confidential';
                        setRegisterClientType(type);
                        if (type === 'confidential') {
                          setRegisterAuthMethod('client_secret_basic');
                        } else {
                          setRegisterAuthMethod('none');
                        }
                      }}
                      disabled={registerSubmitting}
                    >
                      <option value="public">Public (PKCE only)</option>
                      <option value="confidential">Confidential (Client Secret + PKCE)</option>
                    </select>
                    <span id="reg-client-type-hint" className="kb-oauth-help-text">
                      Default: Public (PKCE only) - RFC 9700 OAuth 2.1 public client
                    </span>
                  </div>

                  <div className="kb-oauth-form-field">
                    <label htmlFor="reg-auth-method" className="kb-oauth-form-label">
                      <span className="kb-oauth-label-text">
                        Token Endpoint Authentication Method{' '}
                        <span
                          className="kb-oauth-default-indicator"
                          data-testid="reg-auth-method-default-indicator"
                        >
                          (Default: none)
                        </span>
                      </span>
                      <FieldHelpHint
                        title="Token Endpoint Authentication Method"
                        summary="Authentication mechanism used by the client when communicating with the token endpoint (/oauth/token) under RFC 9700 and OAuth 2.1. Public clients default to none (relying on PKCE S256 proof of possession)."
                        defaultValue="none"
                        validValues={[
                          {
                            label: 'none',
                            description:
                              'none - Public client authentication with PKCE S256 proof of possession (RFC 7636, RFC 9700)',
                          },
                          {
                            label: 'client_secret_basic',
                            description:
                              'client_secret_basic - HTTP Basic Authorization header with client ID and secret (Confidential clients)',
                          },
                          {
                            label: 'client_secret_post',
                            description:
                              'client_secret_post - Client credentials included in application/x-www-form-urlencoded request body',
                          },
                          {
                            label: 'private_key_jwt',
                            description:
                              'private_key_jwt - Asymmetric client assertion signed with an RSA or EC private key (RFC 7523)',
                          },
                        ]}
                        docHref="/docs/three-surface-mcp-server-architecture#oauth-21--pkce"
                        testId="reg-auth-method-help"
                        ariaLabel="Help for Token Endpoint Authentication Method"
                      />
                    </label>
                    <select
                      id="reg-auth-method"
                      aria-describedby="reg-auth-method-hint"
                      className="kb-oauth-form-select"
                      data-testid="select-auth-method"
                      value={registerAuthMethod}
                      onChange={(e) => {
                        setRegisterAuthMethod(
                          e.target.value as
                            | 'none'
                            | 'private_key_jwt'
                            | 'client_secret_basic'
                            | 'client_secret_post',
                        );
                      }}
                      disabled={registerSubmitting}
                    >
                      {registerClientType === 'confidential' ? (
                        <>
                          <option value="client_secret_basic">
                            client_secret_basic (HTTP Basic Auth + PKCE)
                          </option>
                          <option value="client_secret_post">
                            client_secret_post (Form POST Body + PKCE)
                          </option>
                          <option value="private_key_jwt">
                            private_key_jwt (Asymmetric client authentication)
                          </option>
                        </>
                      ) : (
                        <>
                          <option value="none">none (Public client with PKCE S256)</option>
                          <option value="private_key_jwt">
                            private_key_jwt (Asymmetric client authentication)
                          </option>
                        </>
                      )}
                    </select>
                    <span id="reg-auth-method-hint" className="kb-oauth-help-text">
                      Default: none - PKCE S256 code challenge
                    </span>
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

                  <AdvancedSection
                    title="Advanced OAuth Parameters"
                    summary="PKCE S256 enforcement, token lifetimes, and grant type restrictions"
                    testId="advanced-oauth-parameters"
                  >
                    <div className="kb-oauth-form-field">
                      <label className="kb-oauth-form-label" htmlFor="reg-pkce-toggle">
                        <input
                          id="reg-pkce-toggle"
                          type="checkbox"
                          data-testid="toggle-pkce-s256"
                          checked={registerPkceEnforce}
                          onChange={(e) => {
                            setRegisterPkceEnforce(e.target.checked);
                          }}
                          disabled={registerSubmitting}
                          style={{ marginRight: '8px' }}
                        />
                        Enforce PKCE S256 (RFC 9700 Mandatory)
                      </label>
                      <span className="kb-form-hint" style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                        Enforces SHA-256 code challenge for authorization code exchange. Plain code verifiers are strictly prohibited.
                      </span>
                    </div>

                    <div className="kb-oauth-form-field">
                      <label htmlFor="reg-access-token-ttl" className="kb-oauth-form-label">
                        Access Token TTL (seconds)
                      </label>
                      <input
                        id="reg-access-token-ttl"
                        type="number"
                        className="kb-oauth-form-input"
                        data-testid="input-access-token-ttl"
                        min={60}
                        max={86400}
                        value={registerAccessTokenTtl}
                        onChange={(e) => {
                          setRegisterAccessTokenTtl(Number(e.target.value) || 3600);
                        }}
                        disabled={registerSubmitting}
                      />
                    </div>

                    <div className="kb-oauth-form-field">
                      <label htmlFor="reg-grant-types" className="kb-oauth-form-label">
                        Allowed Grant Types (comma separated)
                      </label>
                      <input
                        id="reg-grant-types"
                        type="text"
                        className="kb-oauth-form-input"
                        data-testid="input-grant-types"
                        value={registerGrantTypes}
                        onChange={(e) => {
                          setRegisterGrantTypes(e.target.value);
                        }}
                        disabled={registerSubmitting}
                      />
                    </div>
                  </AdvancedSection>
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

      {/* Edit Redirect URIs Modal */}
      {editClient !== null && (
        <div
          className="kb-oauth-modal-backdrop"
          data-testid="edit-uris-modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget && !editSubmitting) {
              setEditClient(null);
            }
          }}
        >
          <div
            className="kb-oauth-modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-uris-modal-title"
            data-testid="edit-uris-modal"
          >
            <div className="kb-oauth-modal-header">
              <h3
                id="edit-uris-modal-title"
                data-testid="edit-uris-modal-title"
                className="kb-oauth-modal-title"
              >
                Edit Redirect URIs: {editClient.client_name ?? editClient.client_id}
              </h3>
              <button
                type="button"
                className="kb-oauth-modal-close"
                aria-label="Close modal"
                data-testid="close-edit-uris-btn"
                onClick={() => {
                  setEditClient(null);
                }}
              >
                ✕
              </button>
            </div>
            <form
              onSubmit={(e) => {
                void handleEditUrisSubmit(e);
              }}
              data-testid="edit-uris-form"
            >
              <div className="kb-oauth-modal-body">
                {editError && (
                  <div
                    className="kb-oauth-gov-alert kb-oauth-gov-alert-error"
                    role="alert"
                    data-testid="edit-uris-error"
                  >
                    {editError}
                  </div>
                )}
                <div className="kb-oauth-form-field">
                  <label htmlFor="edit-redirect-uris" className="kb-oauth-form-label">
                    Redirect URIs (up to 16 URIs, one per line, HTTPS or loopback HTTP)
                  </label>
                  <textarea
                    id="edit-redirect-uris"
                    className="kb-oauth-form-textarea"
                    data-testid="input-edit-redirect-uris"
                    rows={6}
                    value={editUris}
                    onChange={(e) => {
                      setEditUris(e.target.value);
                    }}
                    required
                    disabled={editSubmitting}
                  />
                </div>
              </div>
              <div className="kb-oauth-modal-footer">
                <button
                  type="button"
                  className="kb-oauth-gov-btn"
                  data-testid="cancel-edit-uris-btn"
                  disabled={editSubmitting}
                  onClick={() => {
                    setEditClient(null);
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="kb-oauth-gov-btn kb-oauth-gov-btn-primary"
                  data-testid="submit-edit-uris-btn"
                  disabled={editSubmitting}
                >
                  {editSubmitting ? 'Saving...' : 'Save Redirect URIs'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
