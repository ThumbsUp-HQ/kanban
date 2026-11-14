// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, type JSX } from 'react';
import './McpConfigSnippetModal.css';

export interface McpConfigSnippetModalProps {
  rawKey?: string | undefined;
  surface?: ('agent' | 'docs' | 'admin') | undefined;
  workspaceSlug?: string | undefined;
  projectKey?: string | undefined;
  onClose: () => void;
}

type ClientTab = 'gemini' | 'antigravity' | 'claude';
type UrlScope = 'global' | 'workspace' | 'project';

export function McpConfigSnippetModal({
  rawKey,
  surface = 'agent',
  workspaceSlug = 'kanban',
  projectKey = 'KANBA',
  onClose,
}: McpConfigSnippetModalProps): JSX.Element {
  const [activeTab, setActiveTab] = useState<ClientTab>('gemini');
  const [urlScope, setUrlScope] = useState<UrlScope>('project');
  const [keyCopied, setKeyCopied] = useState<boolean>(false);
  const [snippetCopied, setSnippetCopied] = useState<boolean>(false);

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
    path = `/mcp/${surface}/w/${workspaceSlug}/p/${projectKey}`;
  }
  const endpointUrl = `${origin}${path}`;
  const effectiveKey = rawKey ?? '<your-mcp-key>';

  let snippet = '';
  if (activeTab === 'gemini') {
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
  } else if (activeTab === 'antigravity') {
    snippet = JSON.stringify(
      {
        mcpServers: {
          kanban: {
            command: 'agy',
            args: ['mcp', 'connect', '--url', endpointUrl, '--token', effectiveKey],
          },
        },
      },
      null,
      2,
    );
  } else {
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
  }

  const copyToClipboard = async (text: string, isKey: boolean): Promise<void> => {
    try {
      await navigator.clipboard.writeText(text);
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
    } catch {
      // Clipboard write fallback
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
                  void copyToClipboard(rawKey, true);
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
            <option value="project">Project ({`/mcp/${surface}/w/${workspaceSlug}/p/${projectKey}`})</option>
            <option value="workspace">Workspace ({`/mcp/${surface}/w/${workspaceSlug}`})</option>
            <option value="global">Global ({`/mcp/${surface}`})</option>
          </select>
        </div>

        <div className="kb-snippet-tabs-row" role="tablist">
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
            Gemini CLI (.gemini/settings.json)
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
            Antigravity (mcp_config.json)
          </button>
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
            Claude Code / Codex
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
              void copyToClipboard(snippet, false);
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
