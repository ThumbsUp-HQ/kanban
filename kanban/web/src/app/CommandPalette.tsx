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
import './CommandPalette.css';

export interface CommandOption {
  readonly id: string;
  readonly title: string;
  readonly icon: string;
  readonly category: 'navigation' | 'actions' | 'theme' | 'issues';
  readonly onSelect: () => void;
  readonly meta?: string;
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
      previousFocusRef.current =
        typeof document !== 'undefined'
          ? (document.activeElement as HTMLElement)
          : null;
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
        id: 'nav-work-items',
        title: 'Go to Work Items',
        icon: '📋',
        category: 'navigation',
        onSelect: () => {
          void navigate(`/projects/${projectKey}/issues`);
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
        id: 'act-create-issue',
        title: 'Create work item',
        icon: '➕',
        category: 'actions',
        onSelect: () => {
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('kb:create-issue', { bubbles: true }),
            );
          }
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
  }, [navigate, onToggleSidebar, projectKey, themeContext]);

  // Issue command options capped at MAX_ISSUE_RESULTS (20)
  const issueCommands = useMemo<CommandOption[]>(() => {
    return issuesFromCache.slice(0, MAX_ISSUE_RESULTS).map((issue) => ({
      id: `issue-${issue.key}`,
      title: `${issue.key} - ${issue.summary}`,
      icon: '🎫',
      category: 'issues',
      meta: issue.key,
      onSelect: () => {
        void navigate(`/projects/${projectKey}/issues/${issue.key}`);
      },
    }));
  }, [issuesFromCache, navigate, projectKey]);

  // Filtered and scored options
  const filteredOptions = useMemo<CommandOption[]>(() => {
    const all = [...baseCommands, ...issueCommands];
    if (!query.trim()) {
      return all;
    }
    const scored: { option: CommandOption; score: number }[] = [];
    for (const opt of all) {
      const s = Math.max(
        scoreMatch(query, opt.title),
        opt.meta ? scoreMatch(query, opt.meta) : 0,
      );
      if (s > 0) {
        scored.push({ option: opt, score: s });
      }
    }
    scored.sort((a, b) => b.score - a.score);
    return scored.map((item) => item.option);
  }, [baseCommands, issueCommands, query]);

  // Bound selectedIndex
  const selectedIndex =
    filteredOptions.length === 0 ? 0 : Math.min(rawSelectedIndex, filteredOptions.length - 1);

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
            className="kb-palette-input"
            placeholder="Type a command or search issues..."
            value={query}
            onChange={handleInputChange}
          />
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
                    <span className="kb-palette-option-title">
                      {opt.title}
                    </span>
                  </div>
                </li>
              );
            })
          )}
        </ul>
      </div>
    </div>
  );
}
