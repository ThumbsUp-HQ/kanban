import React, { useEffect, useRef, useState, type JSX } from 'react';
import type { IssueDetail } from '../drawer/slots';
import {
  type AssigneeItem,
  type AssigneeSuggestionItem,
  fetchAssigneeSuggestions,
} from './railApi';
import { EmojiHint } from '../../components/emoji/EmojiHint';

export interface AssigneesRowProps {
  issue: IssueDetail;
  projectKey: string;
  canEdit: boolean;
  onAddAssignee: (payload: { principal?: string; free_text?: string }) => Promise<void>;
  onRemoveAssignee: (assigneeId: string) => Promise<void>;
  fetchSuggestions?: ((projectKey: string, query: string) => Promise<AssigneeSuggestionItem[]>) | undefined;
}

const MAX_TOTAL_ASSIGNEES = 20;
const MAX_FREE_TEXT_ASSIGNEES = 10;
const FREE_TEXT_TOOLTIP =
  'External free-text label - grants zero access and sends zero notifications';

export function AssigneesRow({
  issue,
  projectKey,
  canEdit,
  onAddAssignee,
  onRemoveAssignee,
  fetchSuggestions = fetchAssigneeSuggestions,
}: AssigneesRowProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<AssigneeSuggestionItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Normalize assignees from issue
  const rawAssignees = issue.assignees ?? [];
  const assignees: AssigneeItem[] = rawAssignees.map((a, idx) => {
    if (typeof a === 'string') {
      if (a.startsWith('@')) {
        return {
          id: `asg-${String(idx)}`,
          kind: 'principal',
          principal: {
            id: `user-${String(idx)}`,
            handle: a.slice(1),
            display_name: a.slice(1),
            type: 'USER',
          },
        };
      }
      return {
        id: `asg-${String(idx)}`,
        kind: 'free_text',
        free_text: a,
      };
    }
    return a;
  });

  // Debounced search (120ms per Spec S7.2 8b)
  useEffect(() => {
    if (!isOpen || !query.trim()) {
      return;
    }

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      setIsLoading(true);
      void fetchSuggestions(projectKey, query.trim())
        .then((results) => {
          setSuggestions(results);
        })
        .catch(() => {
          setSuggestions([]);
        })
        .finally(() => {
          setIsLoading(false);
        });
    }, 120);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [query, isOpen, projectKey, fetchSuggestions]);

  // Click outside listener
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent): void => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setSuggestions([]);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => { document.removeEventListener('mousedown', handleOutsideClick); };
  }, []);

  const totalCount = assignees.length;
  const freeTextCount = assignees.filter((a) => a.kind === 'free_text').length;

  const handleSelectSuggestion = async (item: AssigneeSuggestionItem): Promise<void> => {
    if (totalCount >= MAX_TOTAL_ASSIGNEES) {
      setErrorMessage(`Maximum limit of ${String(MAX_TOTAL_ASSIGNEES)} assignees reached.`);
      return;
    }
    setErrorMessage(null);
    try {
      await onAddAssignee({ principal: item.handle });
      setQuery('');
      setSuggestions([]);
      setIsOpen(false);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to add assignee');
    }
  };

  const handleAddFreeText = async (trimmed: string): Promise<void> => {
    if (totalCount >= MAX_TOTAL_ASSIGNEES) {
      setErrorMessage(`Maximum limit of ${String(MAX_TOTAL_ASSIGNEES)} assignees reached.`);
      return;
    }
    if (freeTextCount >= MAX_FREE_TEXT_ASSIGNEES) {
      setErrorMessage(`Maximum limit of ${String(MAX_FREE_TEXT_ASSIGNEES)} free-text assignees reached.`);
      return;
    }
    setErrorMessage(null);
    try {
      await onAddAssignee({ free_text: trimmed });
      setQuery('');
      setSuggestions([]);
      setIsOpen(false);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to add free-text assignee');
    }
  };

  const trimmedQuery = query.trim();
  const hasExactMatch = suggestions.some(
    (s) => s.handle.toLowerCase() === trimmedQuery.toLowerCase(),
  );

  return (
    <div className="prop-row" data-prop="assignees">
      <span className="prop-row__label">Assignees</span>
      <div className="prop-row__value" ref={containerRef}>
        {assignees.map((asg) => {
          if (asg.kind === 'free_text') {
            return (
              <span
                key={asg.id}
                className="assignee-pill assignee-pill--external"
                data-testid={`assignee-freetext-${asg.free_text}`}
              >
                <EmojiHint
                  kind="externalAssignee"
                  content={FREE_TEXT_TOOLTIP}
                  label="External assignee"
                />
                <span className="assignee-pill__text">{asg.free_text}</span>
                {canEdit ? (
                  <button
                    type="button"
                    className="assignee-pill__remove"
                    aria-label={`Remove ${asg.free_text}`}
                    onClick={() => void onRemoveAssignee(asg.id)}
                  >
                    ×
                  </button>
                ) : null}
              </span>
            );
          }

          const isAgent = asg.principal.type === 'AGENT';
          return (
            <span
              key={asg.id}
              className="assignee-pill assignee-pill--principal"
              data-testid={`assignee-principal-${asg.principal.handle}`}
            >
              {isAgent ? <EmojiHint kind="agent" label="Autonomous agent" /> : null}
              <span className="assignee-pill__text">@{asg.principal.handle}</span>
              {canEdit ? (
                <button
                  type="button"
                  className="assignee-pill__remove"
                  aria-label={`Remove @${asg.principal.handle}`}
                  onClick={() => void onRemoveAssignee(asg.id)}
                >
                  ×
                </button>
              ) : null}
            </span>
          );
        })}

        {canEdit ? (
          <div className="assignees-combobox">
            <input
              type="text"
              className="prop-row__input assignees-combobox__input"
              placeholder="+ Assignee"
              value={query}
              onFocus={() => { setIsOpen(true); }}
              onChange={(e) => {
                const val = e.target.value;
                setQuery(val);
                if (!val.trim()) {
                  setSuggestions([]);
                }
                setIsOpen(true);
              }}
              aria-label="Add assignee"
              role="combobox"
              aria-expanded={isOpen}
            />

            {isOpen && (trimmedQuery.length > 0 || suggestions.length > 0) ? (
              <ul className="assignees-menu">
                {isLoading ? (
                  <li className="assignees-menu__loading">
                    Searching...
                  </li>
                ) : null}

                {suggestions.map((item) => (
                  <li key={item.id}>
                    <div
                      role="button"
                      tabIndex={0}
                      className="assignees-menu__item-btn"
                      onClick={() => void handleSelectSuggestion(item)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          void handleSelectSuggestion(item);
                        }
                      }}
                    >
                      {item.type === 'AGENT' ? <EmojiHint kind="agent" label="Autonomous agent" /> : null}
                      <span>@{item.handle}</span>
                      <span className="assignees-menu__item-name">
                        {item.display_name}
                      </span>
                    </div>
                  </li>
                ))}

                {trimmedQuery.length > 0 && !hasExactMatch ? (
                  <li className={suggestions.length > 0 ? 'assignees-menu__divider' : undefined}>
                    <button
                      type="button"
                      className="assignees-menu__freetext-btn"
                      onClick={() => void handleAddFreeText(trimmedQuery)}
                    >
                      Add external label: &ldquo;{trimmedQuery}&rdquo; (no access or notifications)
                    </button>
                  </li>
                ) : null}
              </ul>
            ) : null}
          </div>
        ) : null}

        {errorMessage ? (
          <div className="prop-row__alert" role="alert">
            {errorMessage}
          </div>
        ) : null}
      </div>
    </div>
  );
}
