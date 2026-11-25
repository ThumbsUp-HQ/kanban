// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, type JSX } from 'react';
import { copyToClipboard } from '../../utils/clipboard';
import { buildAgentOnboardingPrompt } from './agentOnboardingPrompt';
import './McpConfigSnippetModal.css';

export interface McpConfigSnippetModalProps {
  rawKey?: string | undefined;
  surface?: ('agent' | 'docs' | 'admin') | undefined;
  workspaceSlug?: string | undefined;
  projectKey?: string | undefined;
  onClose: () => void;
}

type ClientTab = 'claude' | 'cursor' | 'gemini' | 'antigravity' | 'codex' | 'oauth';
type UrlScope = 'global' | 'workspace' | 'project';

export function McpConfigSnippetModal({
  rawKey,
  surface = 'agent',
  workspaceSlug = 'kanban',
  projectKey = '',
  onClose,
}: McpConfigSnippetModalProps): JSX.Element {
  const [activeTab, setActiveTab] = useState<ClientTab>('claude');
  const [urlScope, setUrlScope] = useState<UrlScope>('project');
  const [keyCopied, setKeyCopied] = useState<boolean>(false);
  const [snippetCopied, setSnippetCopied] = useState<boolean>(false);
  const [promptCopied, setPromptCopied] = useState<boolean>(false);

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

  const origin = typeof window !== 'undefined' ? window.location.origin : 'https://kanban.example.com';

  let path = `/mcp/${surface}`;
  if (urlScope === 'workspace') {
    path = `/mcp/${surface}/w/${workspaceSlug}`;
  } else if (urlScope === 'project') {
    path = projectKey
      ? `/mcp/${surface}/w/${workspaceSlug}/p/${projectKey}`
      : `/mcp/${surface}/w/${workspaceSlug}`;
  }
  const endpointUrl = `${origin}${path}`;
  const effectiveKey = rawKey ?? '<your-mcp-key>';

  let snippet = '';
  if (activeTab === 'claude') {
    const claudeJson = JSON.stringify(
      {
        mcpServers: {
          kanban: {
            type: 'sse',
            url: endpointUrl,
            headers: {
              Authorization: `Bearer ${effectiveKey}`,
            },
          },
        },
      },
      null,
      2,
    );
    const claudeCmd = `claude mcp add kanban ${endpointUrl} --header "Authorization: Bearer ${effectiveKey}"`;
    snippet = `${claudeJson}\n\n# Or add via Claude Code CLI:\n${claudeCmd}`;
  } else if (activeTab === 'cursor') {
    snippet = JSON.stringify(
      {
        mcpServers: {
          kanban: {
            url: endpointUrl,
            headers: {
              Authorization: `Bearer ${effectiveKey}`,
            },
          },
        },
      },
      null,
      2,
    );
  } else if (activeTab === 'gemini' || activeTab === 'antigravity') {
    const agyJson = JSON.stringify(
      {
        mcpServers: {
          kanban: {
            serverUrl: endpointUrl,
            headers: {
              Authorization: `Bearer ${effectiveKey}`,
            },
          },
        },
      },
      null,
      2,
    );
    const agyCmd = `agy mcp add --header "Authorization: Bearer ${effectiveKey}" kanban ${endpointUrl}`;
    snippet = `${agyJson}\n\n# Or add via agy CLI:\n${agyCmd}`;
  } else if (activeTab === 'codex') {
    const codexJson = JSON.stringify(
      {
        mcpServers: {
          kanban: {
            url: endpointUrl,
            headers: {
              Authorization: `Bearer ${effectiveKey}`,
            },
          },
        },
      },
      null,
      2,
    );
    const codexCmd = `codex mcp add kanban ${endpointUrl} --header "Authorization: Bearer ${effectiveKey}"`;
    snippet = `${codexJson}\n\n# Or add via OpenAI Codex CLI:\n${codexCmd}`;
  } else {
    const rfc8414Url = `${origin}/.well-known/oauth-authorization-server`;
    snippet = `# OAuth 2.1 + PKCE S256 Connect
# RFC 8414 Authorization Server Discovery:
# ${rfc8414Url}
# Target Resource Indicator:
# ${endpointUrl}

# Claude Code CLI:
claude mcp add --transport http kanban ${endpointUrl}

# Cursor / VS Code Configuration:
{
  "mcpServers": {
    "kanban": {
      "url": "${endpointUrl}",
      "auth": "oauth"
    }
  }
}

# Codex / Antigravity CLI:
codex mcp add kanban ${endpointUrl} --auth oauth
agy mcp add kanban ${endpointUrl} --auth oauth`;
  }

  const handleCopy = async (text: string, isKey: boolean): Promise<void> => {
    const success = await copyToClipboard(text);
    if (success) {
      if (isKey) {
        setKeyCopied(true);
        /* v8 ignore next 3 */
        setTimeout(() => {
          setKeyCopied(false);
        }, 2000);
      } else {
        setSnippetCopied(true);
        /* v8 ignore next 3 */
        setTimeout(() => {
          setSnippetCopied(false);
        }, 2000);
      }
    }
  };

  const handleCopyPrompt = async (): Promise<void> => {
    const success = await copyToClipboard(
      buildAgentOnboardingPrompt({ origin, projectKey }),
    );
    if (success) {
      setPromptCopied(true);
      /* v8 ignore next 3 */
      setTimeout(() => {
        setPromptCopied(false);
      }, 2000);
    }
  };

  return (
    <div
      className="kb-snippet-modal-backdrop"
      data-testid="mcp-snippet-modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        className="kb-snippet-modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="snippet-modal-title"
        data-testid="mcp-snippet-modal"
      >
        <div className="kb-snippet-modal-header">
          <h2 id="snippet-modal-title" className="kb-snippet-modal-title">
            MCP Access Key & Config Snippet
          </h2>
          <button
            type="button"
            className="kb-snippet-modal-close-btn"
            aria-label="Close modal"
            data-testid="modal-close-button"
            onClick={onClose}
          >
            x
          </button>
        </div>

        {rawKey && (
          <div className="kb-snippet-key-banner" data-testid="raw-key-banner">
            <span className="kb-snippet-key-label">New Secret Key (Shown Once)</span>
            <div className="kb-snippet-key-row">
              <code className="kb-snippet-key-value" data-testid="raw-key-display">
                {rawKey}
              </code>
              <button
                type="button"
                className="kb-snippet-copy-btn"
                data-testid="copy-key-button"
                onClick={() => {
                  void handleCopy(rawKey, true);
                }}
              >
                {keyCopied ? 'Copied!' : 'Copy Key'}
              </button>
            </div>
            <p className="kb-snippet-warning-note">
              This secret will never be shown again. Store it securely in your client config.
            </p>
          </div>
        )}

        <div className="kb-snippet-boundary-note" data-testid="credential-boundary-note">
          <strong>Monotonic Credential Boundary:</strong> Access through this key is monotonically bounded by your account effective permissions. Capability ceilings, allowed CIDRs, and disabled tools narrow access across <code>/mcp/*</code> and <code>/api/v1/*</code> without privilege escalation.
        </div>

        <div className="kb-snippet-llms-callout" data-testid="mcp-llms-txt-callout">
          <div className="kb-snippet-llms-callout-text">
            <span aria-hidden="true">🤖</span>{' '}
            <strong>Recommended Agent Skills:</strong> Give your agent direct onboarding via{' '}
            <a href="/llms.txt" target="_blank" rel="noopener noreferrer">/llms.txt</a>
          </div>
          <button
            type="button"
            className="kb-snippet-copy-prompt-btn"
            data-testid="mcp-copy-llms-prompt-btn"
            onClick={() => {
              void handleCopyPrompt();
            }}
          >
            {promptCopied ? 'Copied Prompt!' : 'Copy Agent Skill Prompt'}
          </button>
        </div>

        <div className="kb-snippet-url-row">
          <label htmlFor="url-scope-select" className="kb-snippet-url-label">
            Target Scope URL:
          </label>
          <select
            id="url-scope-select"
            className="kb-snippet-url-select"
            value={urlScope}
            data-testid="url-scope-select"
            onChange={(e) => {
              setUrlScope(e.target.value as UrlScope);
            }}
          >
            <option value="project">
              Project ({projectKey ? `/mcp/${surface}/w/${workspaceSlug}/p/${projectKey}` : `/mcp/${surface}/w/${workspaceSlug}`})
            </option>
            <option value="workspace">Workspace ({`/mcp/${surface}/w/${workspaceSlug}`})</option>
            <option value="global">Global ({`/mcp/${surface}`})</option>
          </select>
        </div>

        <div className="kb-snippet-tabs-row" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'claude'}
            className={`kb-snippet-tab-btn ${activeTab === 'claude' ? 'kb-snippet-tab-active' : ''}`}
            data-testid="tab-claude"
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
            className={`kb-snippet-tab-btn ${activeTab === 'cursor' ? 'kb-snippet-tab-active' : ''}`}
            data-testid="tab-cursor"
            onClick={() => {
              setActiveTab('cursor');
            }}
          >
            Cursor
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'gemini'}
            className={`kb-snippet-tab-btn ${activeTab === 'gemini' ? 'kb-snippet-tab-active' : ''}`}
            data-testid="tab-gemini"
            onClick={() => {
              setActiveTab('gemini');
            }}
          >
            Gemini CLI
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'antigravity'}
            className={`kb-snippet-tab-btn ${activeTab === 'antigravity' ? 'kb-snippet-tab-active' : ''}`}
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
            className={`kb-snippet-tab-btn ${activeTab === 'codex' ? 'kb-snippet-tab-active' : ''}`}
            data-testid="tab-codex"
            onClick={() => {
              setActiveTab('codex');
            }}
          >
            OpenAI Codex
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'oauth'}
            className={`kb-snippet-tab-btn ${activeTab === 'oauth' ? 'kb-snippet-tab-active' : ''}`}
            data-testid="tab-oauth"
            onClick={() => {
              setActiveTab('oauth');
            }}
          >
            OAuth 2.1
          </button>
        </div>

        <pre className="kb-snippet-code-box" data-testid="snippet-code-box">
          {snippet}
        </pre>

        <div className="kb-snippet-footer-row">
          <button
            type="button"
            className="kb-snippet-copy-btn"
            data-testid="copy-snippet-button"
            onClick={() => {
              void handleCopy(snippet, false);
            }}
          >
            {snippetCopied ? 'Copied!' : 'Copy Snippet'}
          </button>
          <button
            type="button"
            className="kb-snippet-done-btn"
            data-testid="done-button"
            onClick={onClose}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
