// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useRef, type JSX } from 'react';
import { Link } from 'react-router';
import { copyToClipboard } from '../../utils/clipboard';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { StudioDocLink } from '../../components/help/StudioDocLink';
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
  scopeTier?: 'server' | 'workspace' | 'project' | 'all' | undefined;
  onClose: () => void;
}

type SurfaceType = 'agent' | 'docs' | 'admin';
type ToolTab = 'claude' | 'cursor' | 'antigravity' | 'codex' | 'gemini';

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

  const [targetScope, setTargetScope] = useState<'workspace' | 'project' | 'server'>(() => {
    if (scopeTier === 'server') return 'server';
    if (scopeTier === 'project') return 'project';
    if (scopeTier === 'workspace') return 'workspace';
    if (!scopeTier && projectKey) return 'project';
    return 'workspace';
  });

  const [projects, setProjects] = useState<{ key: string; name?: string }[]>([]);
  const [selectedProjectKey, setSelectedProjectKey] = useState<string>(projectKey ?? '');
  const [fetchedProjectKey, setFetchedProjectKey] = useState<string | null>(null);

  const [surface, setSurface] = useState<SurfaceType>('agent');
  const [selectedScopes, setSelectedScopes] = useState<string[]>([...SCOPES_BY_SURFACE.agent]);
  const [activeTab, setActiveTab] = useState<ToolTab>('claude');
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch('/api/v1/projects', {
          method: 'GET',
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
        });
        if (!res.ok) {
          if (isMountedRef.current && !projectKey) {
            setFetchedProjectKey('<PROJECT_KEY>');
          }
          return;
        }
        const data = (await res.json()) as
          | { items?: { key?: string; identifier?: string; name?: string }[] }
          | { key?: string; identifier?: string; name?: string }[];
        if (!isMountedRef.current) return;
        const items = Array.isArray(data) ? data : (data.items ?? []);
        const mapped = items
          .map((p) => {
            const k = p.key ?? p.identifier ?? '';
            return { key: k, name: p.name ?? k };
          })
          .filter((p) => Boolean(p.key));
        setProjects(mapped);
        const firstKey = mapped[0]?.key;
        if (firstKey) {
          setFetchedProjectKey(firstKey);
          setSelectedProjectKey((prev) => (prev ? prev : firstKey));
        } else {
          setFetchedProjectKey('<PROJECT_KEY>');
        }
      } catch {
        if (isMountedRef.current && !projectKey) {
          setFetchedProjectKey('<PROJECT_KEY>');
        }
      }
    })();
  }, [projectKey]);

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

  const origin = window.location.origin;
  const effectiveProject =
    (selectedProjectKey ? selectedProjectKey : undefined) ??
    projectKey ??
    fetchedProjectKey ??
    '<PROJECT_KEY>';
  let resourceUrl = `${origin}/mcp/${surface}/w/${workspaceSlug}`;
  if (targetScope === 'server') {
    resourceUrl = `${origin}/mcp/${surface}`;
  } else if (targetScope === 'project') {
    resourceUrl = `${origin}/mcp/${surface}/w/${workspaceSlug}/p/${effectiveProject}`;
  }
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
            scopes: selectedScopes,
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
            scopes: selectedScopes,
          },
        },
      },
      null,
      2,
    );
    snippet = `${agyJson}\n\n# Or register via agy CLI:\nagy mcp add kanban ${resourceUrl} --auth oauth`;
  } else if (activeTab === 'codex') {
    const codexJson = JSON.stringify(
      {
        mcpServers: {
          kanban: {
            url: resourceUrl,
            auth: 'oauth',
            scopes: selectedScopes,
          },
        },
      },
      null,
      2,
    );
    snippet = `${codexJson}\n\n# Or register via Codex CLI:\ncodex mcp add kanban ${resourceUrl} --auth oauth`;
  } else {
    const scopesList = selectedScopes.length > 0 ? selectedScopes.join(', ') : 'agent:read, agent:write';
    snippet = `# Google Gemini Connected Apps (OAuth 2.1 PKCE)
# 1. In Gemini (gemini.google.com), open Settings > Connected Apps > Add Custom MCP Server
# 2. Set MCP Server URL to:
${resourceUrl}

# 3. Protocol: Streamable HTTP (SSE)
# 4. Authentication: OAuth 2.1 Authorization Code with PKCE S256
# 5. Requested Scopes: ${scopesList}
#
# Click 'Connect'. When prompted, sign into 👍kanban and click 'Approve' on the consent screen.`;
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
          <div className="kb-connect-oauth-header-actions">
            <StudioDocLink
              href="/docs/three-surface-mcp-server-architecture#oauth-21--pkce"
              title="MCP OAuth 2.1 and PKCE Documentation"
              testId="connect-oauth-doc-link"
            />
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
        </div>

        <div className="kb-connect-oauth-body">
          <p className="kb-connect-oauth-desc">
            Connect external MCP clients (Google Gemini, Claude Code, VS Code, Cursor, Codex, Antigravity) using
            OAuth 2.1 with PKCE S256 authorization code or headless RFC 8628 device flow.
          </p>

          <div className="kb-connect-oauth-field">
            <label htmlFor="scope-tier-select" className="kb-connect-oauth-label">
              Target Scope
              <FieldHelpHint
                title="Target Scope"
                summary="Security boundary defining whether OAuth client tokens access all projects across the workspace, a single project, or server-wide resources."
                validValues={[
                  { label: 'Workspace', description: 'Access all projects and resources in the active workspace.' },
                  { label: 'Single Project', description: 'Restricted strictly to the selected project.' },
                  { label: 'Server (Global)', description: 'Server-wide administrative scope across all workspaces (requires admin role).' },
                ]}
                defaultValue="Workspace"
                docHref="/docs/three-surface-mcp-server-architecture#oauth-21--pkce"
                testId="target-scope-help"
              />
            </label>
            <select
              id="scope-tier-select"
              className="kb-connect-oauth-select"
              data-testid="scope-tier-select"
              value={targetScope}
              onChange={(e) => {
                setTargetScope(e.target.value as 'workspace' | 'project' | 'server');
              }}
            >
              <option value="workspace">Workspace ({workspaceSlug})</option>
              <option value="project">Single Project</option>
              <option value="server">Server (Global)</option>
            </select>
          </div>

          {targetScope === 'project' && (
            <div className="kb-connect-oauth-field">
              <label htmlFor="project-select" className="kb-connect-oauth-label">
                Target Project
              </label>
              <select
                id="project-select"
                className="kb-connect-oauth-select"
                data-testid="project-select"
                value={effectiveProject}
                onChange={(e) => {
                  setSelectedProjectKey(e.target.value);
                }}
              >
                {projects.length > 0 ? (
                  projects.map((p) => (
                    <option key={p.key} value={p.key}>
                      {p.name && p.name !== p.key ? `${p.name} (${p.key})` : p.key}
                    </option>
                  ))
                ) : (
                  <option value={effectiveProject}>{effectiveProject}</option>
                )}
              </select>
            </div>
          )}

          <div className="kb-connect-oauth-field">
            <label htmlFor="surface-select" className="kb-connect-oauth-label">
              Target MCP Surface
              <FieldHelpHint
                title="Target MCP Surface"
                summary="The MCP surface endpoint defining available tool namespaces and capability boundaries."
                validValues={[
                  { label: '/mcp/agent', description: 'Core autonomous agent tools for issues, comments, transitions, and stickies.' },
                  { label: '/mcp/docs', description: 'Knowledge base and document querying tools.' },
                  { label: '/mcp/admin', description: 'Administrative operations, user provisioning, and audit logs (requires admin role).' },
                ]}
                defaultValue="/mcp/agent"
                docHref="/docs/three-surface-mcp-server-architecture#oauth-21--pkce"
                testId="target-surface-help"
              />
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
            <span className="kb-connect-oauth-scope-hint" data-testid="scope-hint">
              Selected scopes: {selectedScopes.join(', ') || 'None'}
            </span>
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
              aria-selected={activeTab === 'gemini'}
              className={`kb-connect-oauth-tab ${activeTab === 'gemini' ? 'kb-connect-oauth-tab-active' : ''}`}
              data-testid="tab-gemini-app"
              onClick={() => {
                setActiveTab('gemini');
              }}
            >
              Gemini App
            </button>
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

          {activeTab === 'gemini' && (
            <div className="kb-connect-oauth-gemini-hint" data-testid="gemini-app-instructions">
              <p>
                <strong>Google Gemini Connected Apps:</strong> Connect 👍kanban directly to Google Gemini via OAuth 2.1 PKCE. In Gemini, go to <em>Settings &gt; Connected Apps &gt; Add MCP Server</em> and enter the MCP OAuth Resource URL.
              </p>
              <p>
                Authorization code flow will launch automatically with requested scopes: <code>{selectedScopes.join(', ') || 'agent:read, agent:write'}</code>.
              </p>
            </div>
          )}

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
