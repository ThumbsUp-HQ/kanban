/**
 * Command Palette Dialog (KB-P3-34, S6.4).
 * Accessible modal palette with fast fuzzy subsequence search, theme toggles, and issue jumping.
 */

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
  type KeyboardEvent,
} from 'react';
import { useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { useTheme } from '../theme/ThemeProvider';
import { apiFetch } from '../api/client';
import './CommandPalette.css';

export interface CommandOption {
  readonly id: string;
  readonly title: string;
  readonly icon: string;
  readonly category:
    | 'navigation'
    | 'actions'
    | 'theme'
    | 'issues'
    | 'docs'
    | 'pages'
    | 'stickies';
  readonly onSelect: () => void;
  readonly meta?: string;
  readonly matchReason?: string | undefined;
}

export interface CachedIssue {
  readonly key: string;
  readonly summary: string;
}

export interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onToggleSidebar?: (() => void) | undefined;
  projectKey?: string | undefined;
  cachedIssues?: readonly CachedIssue[] | undefined;
  user?: { is_server_admin?: boolean; is_workspace_admin?: boolean } | null | undefined;
}

export const MAX_QUERY_LENGTH = 200;
export const MAX_ISSUE_RESULTS = 20;

/**
 * Pure subsequence fuzzy matching with scoring:
 * Prefix (100) > Word-start (75) > Subsequence (50) > None (0).
 */
export function scoreMatch(query: string, text: string): number {
  const q = query.trim().toLowerCase();
  const t = text.toLowerCase();

  if (!q) {
    return 1;
  }
  if (t.startsWith(q)) {
    return 100 - (t.length - q.length);
  }
  const words = t.split(/[\s-_]+/);
  if (words.some((w) => w.startsWith(q))) {
    return 75;
  }

  let qIdx = 0;
  for (let i = 0; i < t.length && qIdx < q.length; i++) {
    if (t[i] === q[qIdx]) {
      qIdx++;
    }
  }
  if (qIdx === q.length) {
    return 50;
  }

  return 0;
}

export function CommandPalette({
  isOpen,
  onClose,
  onToggleSidebar,
  projectKey = 'KAN',
  cachedIssues: cachedIssuesProp,
  user,
}: CommandPaletteProps): JSX.Element | null {
  const [query, setQuery] = useState('');
  const [rawSelectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const navigate = useNavigate();
  const themeContext = useTheme();
  const queryClient = useQueryClient();

  // Restore focus on close
  useEffect(() => {
    if (isOpen) {
      previousFocusRef.current = document.activeElement as HTMLElement | null;
      const timer = setTimeout(() => {
        setQuery('');
        setSelectedIndex(0);
        inputRef.current?.focus();
      }, 0);
      return () => {
        clearTimeout(timer);
      };
    } else if (previousFocusRef.current) {
      previousFocusRef.current.focus();
      previousFocusRef.current = null;
    }
  }, [isOpen]);

  // Global Escape handler when palette is open
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handleGlobalEscape = (e: globalThis.KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handleGlobalEscape);
    return () => {
      window.removeEventListener('keydown', handleGlobalEscape);
    };
  }, [isOpen, onClose]);

  // Extract cached issues from TanStack cache if not provided via prop
  const issuesFromCache = useMemo<CachedIssue[]>(() => {
    if (cachedIssuesProp) {
      return [...cachedIssuesProp];
    }
    const results: CachedIssue[] = [];
    const queries = queryClient.getQueryCache().getAll();
    for (const q of queries) {
      const data: unknown = q.state.data;
      if (!data) continue;
      // Array of issues
      if (Array.isArray(data)) {
        for (const item of data) {
          if (item && typeof item === 'object') {
            const rec = item as Record<string, unknown>;
            if (typeof rec.key === 'string' && typeof rec.summary === 'string') {
              results.push({
                key: rec.key,
                summary: rec.summary,
              });
            }
          }
        }
      } else if (typeof data === 'object' && 'issues' in data) {
        const container = data as { issues?: unknown };
        if (Array.isArray(container.issues)) {
          for (const item of container.issues) {
            if (item && typeof item === 'object') {
              const rec = item as Record<string, unknown>;
              if (typeof rec.key === 'string' && typeof rec.summary === 'string') {
                results.push({
                  key: rec.key,
                  summary: rec.summary,
                });
              }
            }
          }
        }
      }
    }
    return results;
  }, [cachedIssuesProp, queryClient]);

  // Built-in commands
  const baseCommands = useMemo<CommandOption[]>(() => {
    return [
      {
        id: 'nav-your-work',
        title: 'Go to Your Work',
        icon: '💼',
        category: 'navigation',
        onSelect: () => {
          void navigate('/your-work');
        },
      },
      {
        id: 'nav-work-items',
        title: 'Go to Work Items',
        icon: '📋',
        category: 'navigation',
        onSelect: () => {
          void navigate(`/projects/${projectKey}/issues`);
        },
      },
      {
        id: 'nav-views',
        title: 'Go to Saved Views',
        icon: '👓',
        category: 'navigation',
        onSelect: () => {
          void navigate(`/projects/${projectKey}/views`);
        },
      },
      {
        id: 'nav-board',
        title: 'Go to Board',
        icon: '⚡',
        category: 'navigation',
        onSelect: () => {
          void navigate(`/projects/${projectKey}/issues?layout=board`);
        },
      },
      {
        id: 'nav-cycles',
        title: 'Go to Cycles',
        icon: '🔄',
        category: 'navigation',
        onSelect: () => {
          void navigate(`/projects/${projectKey}/cycles`);
        },
      },
      {
        id: 'nav-modules',
        title: 'Go to Modules',
        icon: '📦',
        category: 'navigation',
        onSelect: () => {
          void navigate(`/projects/${projectKey}/modules`);
        },
      },
      {
        id: 'nav-overview',
        title: 'Go to Project Overview',
        icon: '📌',
        category: 'navigation',
        onSelect: () => {
          void navigate(`/projects/${projectKey}/overview`);
        },
      },
      {
        id: 'nav-docs',
        title: 'Go to Docs',
        icon: '📄',
        category: 'navigation',
        onSelect: () => {
          void navigate(`/projects/${projectKey}/docs`);
        },
      },
      {
        id: 'nav-stickies',
        title: 'Go to Stickies',
        icon: '🟨',
        category: 'navigation',
        onSelect: () => {
          void navigate('/stickies');
        },
      },
      {
        id: 'nav-project-settings',
        title: 'Go to Project Settings',
        icon: '⚙️',
        category: 'navigation',
        onSelect: () => {
          void navigate(`/projects/${projectKey}/settings`);
        },
      },
      {
        id: 'nav-workspace-settings',
        title: 'Go to Workspace Settings',
        icon: '🏢',
        category: 'navigation',
        onSelect: () => {
          void navigate('/workspaces/settings');
        },
      },
      {
        id: 'nav-profile-settings',
        title: 'Go to Personal Profile',
        icon: '👤',
        category: 'navigation',
        onSelect: () => {
          void navigate('/settings/profile');
        },
      },
      {
        id: 'act-shortcuts',
        title: 'Keyboard Shortcuts Cheat Sheet',
        icon: '⌨️',
        category: 'actions',
        onSelect: () => {
          window.dispatchEvent(
            new CustomEvent('kb:open-shortcuts', { bubbles: true }),
          );
        },
      },
      {
        id: 'act-create-issue',
        title: 'Create work item',
        icon: '➕',
        category: 'actions',
        onSelect: () => {
          window.dispatchEvent(
            new CustomEvent('kb:create-issue', { bubbles: true }),
          );
          void navigate(`/projects/${projectKey}/issues?create=1`);
        },
      },
      {
        id: 'act-create-project',
        title: 'Create project',
        icon: '📁',
        category: 'actions',
        onSelect: () => {
          window.dispatchEvent(
            new CustomEvent('kb:open-create-project', { bubbles: true }),
          );
        },
      },
      ...((user ? Boolean(user.is_server_admin) : true)
        ? [
            {
              id: 'nav-auth-studio',
              title: 'Go to Auth Studio',
              icon: '🛡️',
              category: 'navigation' as const,
              onSelect: () => {
                void navigate('/admin/auth');
              },
            },
          ]
        : []),
      ...((user ? user.is_server_admin === true || user.is_workspace_admin === true : true)
        ? [
            {
              id: 'nav-admin-diagnostics',
              title: 'Go to Diagnostics & Link Inspector',
              icon: '🩺',
              category: 'navigation' as const,
              onSelect: () => {
                void navigate('/admin/diagnostics');
              },
            },
          ]
        : []),
      {
        id: 'nav-mcp-keys',
        title: 'Go to Personal MCP Keys',
        icon: '🔑',
        category: 'navigation',
        onSelect: () => {
          void navigate('/settings/mcp');
        },
      },
      ...((user ? Boolean(user.is_server_admin) : true)
        ? [
            {
              id: 'nav-standalone-status',
              title: 'Go to System Storage, Backups & Deployment',
              icon: '💾',
              category: 'navigation' as const,
              onSelect: () => {
                void navigate('/admin/standalone');
              },
            },
          ]
        : []),
      {
        id: 'nav-about',
        title: 'About 👍kanban (License, API Docs & SBOM)',
        icon: 'ℹ️',
        category: 'navigation',
        onSelect: () => {
          void navigate('/about');
        },
      },
      {
        id: 'act-toggle-sidebar',
        title: 'Toggle sidebar',
        icon: '📐',
        category: 'actions',
        onSelect: () => {
          if (onToggleSidebar) {
            onToggleSidebar();
          }
        },
      },
      {
        id: 'theme-light',
        title: 'Theme: Light',
        icon: '☀️',
        category: 'theme',
        onSelect: () => {
          themeContext.setTheme('light');
        },
      },
      {
        id: 'theme-dark',
        title: 'Theme: Dark',
        icon: '🌙',
        category: 'theme',
        onSelect: () => {
          themeContext.setTheme('dark');
        },
      },
      {
        id: 'theme-system',
        title: 'Theme: System',
        icon: '💻',
        category: 'theme',
        onSelect: () => {
          themeContext.setTheme('system');
        },
      },
    ];
  }, [navigate, onToggleSidebar, projectKey, themeContext, user]);

  // Issue command options capped at MAX_ISSUE_RESULTS (20)
  const issueCommands = useMemo<CommandOption[]>(() => {
    return issuesFromCache.slice(0, MAX_ISSUE_RESULTS).map((issue) => ({
      id: `issue-${issue.key}`,
      title: `${issue.key} - ${issue.summary}`,
      icon: '🎫',
      category: 'issues',
      meta: issue.key,
      onSelect: () => {
        void navigate(`/projects/${projectKey}/issues?peek=${issue.key}`);
      },
    }));
  }, [issuesFromCache, navigate, projectKey]);

  // Live hybrid search across Issues, Docs, Pages, and Stickies
  const [liveSearchResults, setLiveSearchResults] = useState<CommandOption[]>([]);

  useEffect(() => {
    const trimmed = query.trim();
    let active = true;
    const timer = setTimeout(() => {
      if (!trimmed) {
        if (active) setLiveSearchResults([]);
        return;
      }
      void (async () => {
        try {
          const res = (await apiFetch(
            'GET',
            '/api/v1/search' as never,
            { query: { q: trimmed, limit: 15, mode: 'hybrid' } },
          )) as {
            items?: {
              id: string;
              kind: 'issue' | 'doc' | 'page' | 'sticky';
              key?: string | null;
              title: string;
              summary?: string | null;
              snippet?: string | null;
              project_identifier?: string | null;
              match_reason?: string | null;
            }[];
          };
          if (!active) return;
          const rawItems = res.items ?? (res as unknown as { results?: typeof res.items }).results;
          const items = rawItems ?? [];
          const mapped: CommandOption[] = items.map((item) => {
            const pKey = item.project_identifier ?? projectKey;
            const matchReason = item.match_reason ?? undefined;
            if (item.kind === 'issue') {
              const keyStr = item.key ?? '';
              const titlePart = item.title.trim() ? item.title : (item.summary ?? '');
              const displayTitle = keyStr ? `${keyStr} - ${titlePart}` : (titlePart.trim() ? titlePart : 'Work Item');
              return {
                id: `search-issue-${item.id}`,
                title: displayTitle,
                icon: '🎫',
                category: 'issues' as const,
                meta: keyStr,
                matchReason,
                onSelect: () => {
                  void navigate(keyStr ? `/projects/${pKey}/issues?peek=${keyStr}` : `/projects/${pKey}/issues`);
                },
              };
            }
            if (item.kind === 'doc') {
              return {
                id: `search-doc-${item.id}`,
                title: item.title,
                icon: '📄',
                category: 'docs' as const,
                meta: `Doc (${pKey})`,
                matchReason,
                onSelect: () => {
                  void navigate(`/projects/${pKey}/docs`);
                },
              };
            }
            if (item.kind === 'page') {
              return {
                id: `search-page-${item.id}`,
                title: item.title,
                icon: '📑',
                category: 'pages' as const,
                meta: `Page (${pKey})`,
                matchReason,
                onSelect: () => {
                  void navigate(`/projects/${pKey}/docs/${item.id}`);
                },
              };
            }
            const stickyTitle = item.title.trim() ? item.title : (item.snippet ?? 'Sticky Note');
            return {
              id: `search-sticky-${item.id}`,
              title: stickyTitle,
              icon: '🟨',
              category: 'stickies' as const,
              meta: `Sticky (${pKey})`,
              matchReason,
              onSelect: () => {
                void navigate(item.project_identifier ? `/projects/${pKey}/overview` : '/stickies');
              },
            };
          });
          setLiveSearchResults(mapped);
        } catch {
          if (active) setLiveSearchResults([]);
        }
      })();
    }, 150);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [navigate, projectKey, query]);

  // Filtered and scored options
  const filteredOptions = useMemo<CommandOption[]>(() => {
    if (!query.trim()) {
      return baseCommands;
    }

    const seen = new Set<string>();
    const result: CommandOption[] = [];

    // Backend hybrid / synaptic search results preserve exact rank order and are never dropped
    for (const opt of liveSearchResults) {
      const key = `${opt.category}:${opt.title}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(opt);
      }
    }

    // Local fallback commands scored and sorted by match score
    const scoredLocal: { option: CommandOption; score: number }[] = [];
    for (const opt of [...baseCommands, ...issueCommands]) {
      const key = `${opt.category}:${opt.title}`;
      if (seen.has(key)) {
        continue;
      }
      const s = Math.max(
        scoreMatch(query, opt.title),
        opt.meta ? scoreMatch(query, opt.meta) : 0,
      );
      if (s > 0) {
        scoredLocal.push({ option: opt, score: s });
      }
    }
    scoredLocal.sort((a, b) => b.score - a.score);
    for (const item of scoredLocal) {
      const key = `${item.option.category}:${item.option.title}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(item.option);
      }
    }

    return result;
  }, [baseCommands, issueCommands, liveSearchResults, query]);

  // Bound selectedIndex
  const selectedIndex =
    filteredOptions.length === 0 ? 0 : Math.min(rawSelectedIndex, filteredOptions.length - 1);

  useEffect(() => {
    if (filteredOptions[selectedIndex]) {
      const activeEl = document.getElementById(`kb-palette-opt-${filteredOptions[selectedIndex].id}`);
      if (typeof activeEl?.scrollIntoView === 'function') {
        activeEl.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [selectedIndex, filteredOptions]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const raw = e.target.value;
    const truncated = raw.length > MAX_QUERY_LENGTH ? raw.slice(0, MAX_QUERY_LENGTH) : raw;
    setQuery(truncated);
    setSelectedIndex(0);
  };

  const executeOption = useCallback(
    (option: CommandOption) => {
      option.onSelect();
      onClose();
    },
    [onClose],
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (filteredOptions.length > 0) {
        setSelectedIndex((prev) => (prev + 1) % filteredOptions.length);
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (filteredOptions.length > 0) {
        setSelectedIndex(
          (prev) => (prev - 1 + filteredOptions.length) % filteredOptions.length,
        );
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const selected = filteredOptions[selectedIndex];
      if (selected) {
        executeOption(selected);
      }
    } else if (e.key === 'Tab') {
      // Focus trap within the dialog
      e.preventDefault();
      inputRef.current?.focus();
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="kb-palette-scrim"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="kb-palette-dialog"
        data-testid="command-palette-modal"
        onKeyDown={handleKeyDown}
      >
        <div className="kb-palette-input-wrapper">
          <span className="kb-palette-search-icon" aria-hidden="true">
            🔍
          </span>
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-autocomplete="list"
            aria-activedescendant={
              filteredOptions[selectedIndex]
                ? `kb-palette-opt-${filteredOptions[selectedIndex].id}`
                : undefined
            }
            className="kb-palette-input"
            data-testid="command-palette-input"
            placeholder="Type a command or search issues..."
            value={query}
            onChange={handleInputChange}
          />
          <button
            type="button"
            className="kb-palette-close-btn"
            data-testid="command-palette-close-btn"
            aria-label="Close command palette"
            onClick={onClose}
          >
            &#x2715;
          </button>
        </div>

        <ul
          id="command-palette-list"
          role="listbox"
          aria-label="Commands and suggestions"
          className="kb-palette-list"
        >
          {filteredOptions.length === 0 ? (
            <li className="kb-palette-empty">No matching commands or issues.</li>
          ) : (
            filteredOptions.map((opt, i) => {
              const isSelected = i === selectedIndex;
              return (
                <li
                  key={opt.id}
                  id={`kb-palette-opt-${opt.id}`}
                  role="option"
                  aria-selected={isSelected}
                  className="kb-palette-option"
                  onClick={() => { executeOption(opt); }}
                >
                  <span className="kb-palette-option-icon" aria-hidden="true">
                    {opt.icon}
                  </span>
                  <div className="kb-palette-option-content">
                    <div className="kb-palette-option-header">
                      <span className="kb-palette-option-title">
                        {opt.title}
                      </span>
                      {opt.matchReason && (
                        <span
                          className="kb-palette-badge"
                          data-testid={`match-reason-${opt.id}`}
                        >
                          {opt.matchReason}
                        </span>
                      )}
                    </div>
                  </div>
                </li>
              );
            })
          )}
        </ul>

        <footer
          className="kb-palette-footer"
          data-testid="palette-footer-legend"
          aria-label="Keyboard shortcuts legend"
        >
          <span className="kb-palette-footer-item">
            <kbd className="kb-palette-kbd">↑</kbd>
            <kbd className="kb-palette-kbd">↓</kbd>
            <span className="kb-palette-footer-label">Navigate</span>
          </span>
          <span className="kb-palette-footer-item">
            <kbd className="kb-palette-kbd">↵</kbd>
            <span className="kb-palette-footer-label">Select</span>
          </span>
          <span className="kb-palette-footer-item">
            <kbd className="kb-palette-kbd">Esc</kbd>
            <span className="kb-palette-footer-label">Dismiss</span>
          </span>
        </footer>
      </div>
    </div>
  );
}
