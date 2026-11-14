import React, { type JSX } from 'react';
import { useQuery } from '@tanstack/react-query';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { qk } from '../../api/queryKeys';
import type { IssueDetail } from './slots';
import './AccessPill.css';

export interface AccessPillProps {
  issue: IssueDetail;
}

export interface AccessSummaryData {
  users?: number | unknown[];
  groups?: number | unknown[];
  agents?: number | unknown[];
  deny_rules?: number | unknown[];
  explicit_grant_count?: number;
  scope_label?: string;
  redacted_count?: number;
}

function formatNoun(count: number, singular: string, plural: string): string {
  return `${String(count)} ${count === 1 ? singular : plural}`;
}

function getCount(val: unknown): number {
  if (typeof val === 'number') {
    return val;
  }
  if (Array.isArray(val)) {
    return val.length;
  }
  return 0;
}

export function AccessPill({ issue }: AccessPillProps): JSX.Element {
  const objectId = issue.object_id;
  const projectName = issue.project_name || 'Project';

  const { data, isLoading, isError } = useQuery<AccessSummaryData>({
    queryKey: qk.access(objectId),
    queryFn: async ({ signal }) => {
      const res = await fetch(`/api/v1/objects/${objectId}/access`, {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin',
        signal,
      });
      if (!res.ok) {
        throw new Error(`Failed to load access summary: ${String(res.status)}`);
      }
      return (await res.json()) as AccessSummaryData;
    },
    enabled: Boolean(objectId),
  });

  const scopeLabel = data?.scope_label ?? 'Project';
  const grantCount = data?.explicit_grant_count ?? 0;
  const visibleText = grantCount > 0 ? `${scopeLabel} + ${String(grantCount)}` : scopeLabel;

  const handleActivate = (): void => {
    window.dispatchEvent(
      new CustomEvent('kb:open-access-inspector', {
        detail: { objectId },
      }),
    );
  };

  const renderContent = (): string => {
    if (isLoading) {
      return 'Loading access summary...';
    }
    if (isError || !data) {
      return 'Access summary unavailable.';
    }

    const uCount = getCount(data.users);
    const gCount = getCount(data.groups);
    const aCount = getCount(data.agents);
    const dCount = getCount(data.deny_rules);
    const rCount = data.redacted_count ?? 0;

    let text = `Project: ${projectName} - ${formatNoun(uCount, 'user', 'users')}, ${formatNoun(gCount, 'group', 'groups')}, ${formatNoun(aCount, 'agent', 'agents')}, ${formatNoun(dCount, 'deny rule', 'deny rules')}. Inherited from Project.`;
    if (rCount > 0) {
      text += ` +${String(rCount)} outside your visibility`;
    }
    return text;
  };

  return (
    <div className="surface__access-pill" data-testid="access-pill">
      <EmojiHint
        kind="access"
        variant="interactive"
        label={`Access: ${visibleText}`}
        testId="access-hint"
        activateLabel="Open Access Inspector"
        onActivate={handleActivate}
        content={renderContent()}
      />
      <span className="surface__access-label">{visibleText}</span>
    </div>
  );
}
