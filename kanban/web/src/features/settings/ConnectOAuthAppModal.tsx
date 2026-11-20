// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, type JSX } from 'react';
import { Link } from 'react-router';
import { copyToClipboard } from '../../utils/clipboard';
import './ConnectOAuthAppModal.css';

export interface ConnectOAuthAppModalProps {
  user?: {
    is_server_admin?: boolean;
    is_workspace_admin?: boolean;
    is_project_admin?: boolean;
    workspace_role?: string;
  } | null | undefined;
  workspaceSlug?: string | undefined;
  projectKey?: string | undefined;
  scopeTier?: 'server' | 'workspace' | 'project' | undefined;
  onClose: () => void;
}

type SurfaceType = 'agent' | 'docs' | 'admin';
type ToolTab = 'claude' | 'cursor' | 'antigravity' | 'codex';

const SCOPES_BY_SURFACE: Record<SurfaceType, readonly string[]> = {
  agent: ['agent:read', 'agent:write'],
  docs: ['docs:read', 'docs:write'],
  admin: ['admin:read', 'admin:write', 'admin:destructive'],
};

export function ConnectOAuthAppModal({
  user,
  workspaceSlug = 'kanban',
  projectKey,
  scopeTier,
  onClose,
}: ConnectOAuthAppModalProps): JSX.Element {
  const isAdmin =
    user?.is_server_admin === true ||
    user?.is_workspace_admin === true ||
    user?.workspace_role === 'WORKSPACE_ADMIN' ||
    user?.workspace_role === 'SERVER_ADMIN';
  const [surface, setSurface] = useState<SurfaceType>('agent');
  const [selectedScopes, setSelectedScopes] = useState<string[]>([...SCOPES_BY_SURFACE.agent]);
  const [activeTab, setActiveTab] = useState<ToolTab>('claude');
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [fetchedProjectKey, setFetchedProjectKey] = useState<string | null>(null);

  useEffect(() => {
    const isMounted = { current: true };
    if (scopeTier === 'project' && !projectKey) {
      void (async () => {
        try {
          const res = await fetch('/api/v1/projects', {
            method: 'GET',
            headers: { Accept: 'application/json' },
            credentials: 'same-origin',
          });
          if (!res.ok || !isMounted.current) {
            return;
          }
          const data = (await res.json()) as
            | { items?: { key?: string; identifier?: string }[] }
            | { key?: string; identifier?: string }[];
          const items = Array.isArray(data) ? data : (data.items ?? []);
          const firstKey = items[0]?.key ?? items[0]?.identifier;
          setFetchedProjectKey(firstKey ?? '<PROJECT_KEY>');
        } catch {
          setFetchedProjectKey('<PROJECT_KEY>');
        }
      })();
    }
    return () => {
      isMounted.current = false;
    };
  }, [scopeTier, projectKey]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  const handleSurfaceChange = (newSurface: SurfaceType): void => {
    setSurface(newSurface);
    setSelectedScopes([...SCOPES_BY_SURFACE[newSurface]]);
  };

  const toggleScope = (scope: string): void => {
    setSelectedScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    );
  };

  const handleCopy = async (text: string, fieldId: string): Promise<void> => {
    const success = await copyToClipboard(text);
    if (success) {
      setCopiedField(fieldId);
      setTimeout(() => {
        setCopiedField(null);
      }, 2000);
    }
  };

  let resolvedProjectKey: string | null = null;
  if (scopeTier === 'project') {
    resolvedProjectKey = projectKey ?? fetchedProjectKey ?? '<PROJECT_KEY>';
  } else if (!scopeTier && projectKey) {
    resolvedProjectKey = projectKey;
  }

  const origin = window.location.origin;
  const resourceUrl = resolvedProjectKey
    ? `${origin}/mcp/${surface}/w/${workspaceSlug}/p/${resolvedProjectKey}`
    : `${origin}/mcp/${surface}/w/${workspaceSlug}`;
  const rfc8414Url = `${origin}/.well-known/oauth-authorization-server`;

  let snippet = '';
  if (activeTab === 'claude') {
    snippet = `claude mcp add --transport http kanban ${resourceUrl}`;
  } else if (activeTab === 'cursor') {
    snippet = JSON.stringify(
      {
        mcpServers: {
          kanban: {
            url: resourceUrl,
            auth: 'oauth',
          },
        },
      },
      null,
      2,
    );
  } else if (activeTab === 'antigravity') {
    const agyJson = JSON.stringify(
      {
        mcpServers: {
          kanban: {
            serverUrl: resourceUrl,
            auth: 'oauth',
          },
        },
      },
      null,
      2,
    );
    snippet = `${agyJson}\n\n# Or register via agy CLI:\nagy mcp add kanban ${resourceUrl} --auth oauth`;
  } else {
    const codexJson = JSON.stringify(
      {
        mcpServers: {
          kanban: {
            url: resourceUrl,
            auth: 'oauth',
          },
        },
      },
      null,
      2,
    );
    snippet = `${codexJson}\n\n# Or register via Codex CLI:\ncodex mcp add kanban ${resourceUrl} --auth oauth`;
  }

  return (
    <div
      className="kb-connect-oauth-backdrop"
      data-testid="connect-oauth-modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        className="kb-connect-oauth-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="connect-oauth-modal-title"
        data-testid="connect-oauth-app-modal"
      >
        <div className="kb-connect-oauth-header">
          <h2 id="connect-oauth-modal-title" className="kb-connect-oauth-title">
            Connect OAuth Application
          </h2>
          <button
            type="button"
            className="kb-connect-oauth-close"
            aria-label="Close modal"
            data-testid="close-connect-oauth-modal-btn"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <div className="kb-connect-oauth-body">
          <p className="kb-connect-oauth-desc">
            Connect external MCP clients (Claude Code, VS Code, Cursor, Codex, Antigravity) using
            OAuth 2.1 with PKCE S256 authorization code or headless RFC 8628 device flow.
          </p>

          <div className="kb-connect-oauth-field">
            <label htmlFor="surface-select" className="kb-connect-oauth-label">
              Target MCP Surface
            </label>
            <select
              id="surface-select"
              className="kb-connect-oauth-select"
              data-testid="surface-select"
              value={surface}
              onChange={(e) => {
                handleSurfaceChange(e.target.value as SurfaceType);
              }}
            >
              <option value="agent">Agent Surface (/mcp/agent)</option>
              <option value="docs">Docs & Knowledge Surface (/mcp/docs)</option>
              {isAdmin && <option value="admin">Admin Surface (/mcp/admin)</option>}
            </select>
          </div>

          <div className="kb-connect-oauth-field">
            <span className="kb-connect-oauth-label">Required Scopes</span>
            <div className="kb-connect-oauth-scopes" data-testid="scope-picker">
              {SCOPES_BY_SURFACE[surface].map((scope) => (
                <label key={scope} className="kb-connect-oauth-scope-item">
                  <input
                    type="checkbox"
                    checked={selectedScopes.includes(scope)}
                    onChange={() => {
                      toggleScope(scope);
                    }}
                    data-testid={`scope-check-${scope}`}
                  />
                  <code>{scope}</code>
                </label>
              ))}
            </div>
          </div>

          <div className="kb-connect-oauth-endpoints">
            <div className="kb-connect-oauth-endpoint-row">
              <span className="kb-connect-oauth-endpoint-label">MCP OAuth Resource URL:</span>
              <div className="kb-connect-oauth-copy-wrap">
                <code className="kb-connect-oauth-url" data-testid="mcp-resource-url">
                  {resourceUrl}
                </code>
                <button
                  type="button"
                  className="kb-connect-oauth-copy-btn"
                  data-testid="copy-resource-url-btn"
                  onClick={() => {
                    void handleCopy(resourceUrl, 'resource');
                  }}
                >
                  {copiedField === 'resource' ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>

            <div className="kb-connect-oauth-endpoint-row">
              <span className="kb-connect-oauth-endpoint-label">RFC 8414 Authorization Server:</span>
              <div className="kb-connect-oauth-copy-wrap">
                <code className="kb-connect-oauth-url" data-testid="rfc8414-url">
                  {rfc8414Url}
                </code>
                <button
                  type="button"
                  className="kb-connect-oauth-copy-btn"
                  data-testid="copy-rfc8414-url-btn"
                  onClick={() => {
                    void handleCopy(rfc8414Url, 'rfc8414');
                  }}
                >
                  {copiedField === 'rfc8414' ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          </div>

          <div className="kb-connect-oauth-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'claude'}
              className={`kb-connect-oauth-tab ${activeTab === 'claude' ? 'kb-connect-oauth-tab-active' : ''}`}
              data-testid="tab-claude-code"
              onClick={() => {
                setActiveTab('claude');
              }}
            >
              Claude Code
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'cursor'}
              className={`kb-connect-oauth-tab ${activeTab === 'cursor' ? 'kb-connect-oauth-tab-active' : ''}`}
              data-testid="tab-cursor"
              onClick={() => {
                setActiveTab('cursor');
              }}
            >
              VS Code / Cursor
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'antigravity'}
              className={`kb-connect-oauth-tab ${activeTab === 'antigravity' ? 'kb-connect-oauth-tab-active' : ''}`}
              data-testid="tab-antigravity"
              onClick={() => {
                setActiveTab('antigravity');
              }}
            >
              Antigravity
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'codex'}
              className={`kb-connect-oauth-tab ${activeTab === 'codex' ? 'kb-connect-oauth-tab-active' : ''}`}
              data-testid="tab-codex"
              onClick={() => {
                setActiveTab('codex');
              }}
            >
              Codex
            </button>
          </div>

          <div className="kb-connect-oauth-snippet-wrap">
            <pre className="kb-connect-oauth-snippet" data-testid="command-snippet">
              <code>{snippet}</code>
            </pre>
            <button
              type="button"
              className="kb-connect-oauth-snippet-copy"
              data-testid="copy-snippet-btn"
              onClick={() => {
                void handleCopy(snippet, 'snippet');
              }}
            >
              {copiedField === 'snippet' ? 'Copied Command!' : 'Copy Command'}
            </button>
          </div>

          <div className="kb-connect-oauth-headless-note">
            <span>Terminal or Headless Device?</span>
            <Link
              to="/oauth/device"
              className="kb-connect-oauth-device-link"
              data-testid="modal-enter-device-code-btn"
              onClick={onClose}
            >
              Enter Device Code →
            </Link>
          </div>
        </div>

        <div className="kb-connect-oauth-footer">
          <button
            type="button"
            className="kb-connect-oauth-btn"
            data-testid="close-modal-bottom-btn"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
