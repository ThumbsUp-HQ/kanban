// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import type { JSX } from 'react';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import { QueryClientContext, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import {
  executeCustomField,
  fetchIssueCustomFields,
  fetchProjectCustomFields,
  qk,
  type CustomFieldDefinition,
  type CustomFieldExecutionResult,
  type CustomFieldTier,
} from './api';
import { CustomFieldValue } from './CustomFieldValue';
import './custom-fields.css';

export interface CustomFieldsRailSectionProps {
  projectKey: string;
  issueKey: string;
  canEdit?: boolean;
}

const ERROR_CODE_MAP: Record<string, string> = {
  SCRIPT_TIMEOUT: 'Timed out',
  SCRIPT_FUEL_EXHAUSTED: 'Compute limit reached',
  APPROVAL_REVOKED: 'Approval revoked - admin re-sign required',
  SANDBOX_UNAVAILABLE_IN_STANDALONE: 'Tier B unavailable in standalone',
};

function mapServerErrorCode(errorCode?: string): string {
  if (!errorCode) return 'Unavailable';
  return ERROR_CODE_MAP[errorCode] ?? 'Unavailable';
}

/**
 * Properties-rail section for Admin-Defined Custom Fields (S7.1, S6.2).
 * Unmounts when 0 definitions exist, provides in-flight deduplicated execution,
 * and displays execution metadata via 🧪 EmojiHint popover.
 */
function CustomFieldsRailSectionInner({
  projectKey,
  issueKey,
  canEdit = true,
}: CustomFieldsRailSectionProps): JSX.Element | null {
  const queryClient = useQueryClient();
  const [inFlightFieldIds, setInFlightFieldIds] = useState<Set<string>>(new Set());
  const inFlightRef = useRef<Set<string>>(new Set());

  // Fetch project custom field definitions
  const { data: definitions = [], isLoading: isLoadingDefs } = useQuery({
    queryKey: qk.customFields.project(projectKey),
    queryFn: () => fetchProjectCustomFields(projectKey),
    enabled: Boolean(projectKey),
  });

  // Fetch issue custom field cached values
  const { data: results = [] } = useQuery({
    queryKey: qk.customFields.issue(issueKey),
    queryFn: () => fetchIssueCustomFields(issueKey),
    enabled: Boolean(issueKey && definitions.length > 0),
  });

  // Map results by field_id for fast lookup
  const resultsByFieldId = useMemo(() => {
    const map = new Map<string, CustomFieldExecutionResult>();
    for (const r of results) {
      map.set(r.field_id, r);
    }
    return map;
  }, [results]);

  // Execute mutation with TanStack Query
  const executeMutation = useMutation({
    mutationFn: async (fieldId: string) => {
      return executeCustomField(issueKey, fieldId);
    },
    onSuccess: (updatedResult, fieldId) => {
      queryClient.setQueryData<CustomFieldExecutionResult[]>(
        qk.customFields.issue(issueKey),
        (old = []) => {
          const index = old.findIndex((r) => r.field_id === fieldId);
          if (index >= 0) {
            const next = [...old];
            next[index] = updatedResult;
            return next;
          }
          return [...old, updatedResult];
        },
      );
    },
    onSettled: (_data, _error, fieldId) => {
      inFlightRef.current.delete(fieldId);
      setInFlightFieldIds(new Set(inFlightRef.current));
    },
  });

  // In-flight deduplication handler for refresh click
  const handleRefresh = useCallback(
    (fieldId: string) => {
      if (inFlightRef.current.has(fieldId)) {
        return; // Deduplicate in-flight click
      }
      inFlightRef.current.add(fieldId);
      setInFlightFieldIds(new Set(inFlightRef.current));
      executeMutation.mutate(fieldId);
    },
    [executeMutation],
  );

  // If loading or project has 0 custom fields, do not mount section in DOM (S7.1)
  if (!isLoadingDefs && definitions.length === 0) {
    return null;
  }
  if (definitions.length === 0) {
    return null;
  }

  return (
    <section
      className="custom-fields-rail-section"
      aria-label="Custom Fields (Admin-Defined 🧪)"
      data-testid="custom-fields-rail-section"
    >
      <h3 className="custom-fields-rail-header custom-fields-rail-title">Custom Fields (Admin-Defined 🧪)</h3>
      <div className="custom-fields-rail-rows">
        {definitions.map((def: CustomFieldDefinition) => {
          const result = resultsByFieldId.get(def.id);
          const isInFlight = inFlightFieldIds.has(def.id);

          const defTier = def.tier as CustomFieldTier | null | undefined;
          const tier: string | null | undefined =
            result?.tier ?? (defTier === 'wasm' ? 'Wasmtime' : defTier === 'nsjail' ? 'nsjail' : defTier);
          const tokenScope = result?.token_scope ?? def.target_scope;
          const credentialMode = result?.credential_mode ?? def.credential_mode;
          const latencyMs = result?.last_latency_ms;

          const hasError = result?.status === 'ERROR';
          const errorMessage = hasError ? mapServerErrorCode(result.error_code) : null;

          return (
            <div
              key={def.id}
              className="custom-fields-rail-row"
              data-testid={`custom-field-row-${def.slug}`}
            >
              <div className="custom-fields-rail-label" title={def.name}>
                {def.name}
              </div>

              <div className="custom-fields-rail-pill">
                <EmojiHint
                  kind="scriptedField"
                  testId={`custom-field-emoji-hint-${def.slug}`}
                  content={
                    <div
                      className="custom-field-hint-content"
                      data-testid={`custom-field-hint-popover-${def.slug}`}
                    >
                      {tier !== null && tier !== undefined && (
                        <>
                          <div className="custom-field-hint-line">
                            <strong>Tier:</strong> {tier}
                          </div>
                          <div className="custom-field-hint-line">
                            <strong>Scope:</strong> {tokenScope}
                          </div>
                          <div className="custom-field-hint-line">
                            <strong>Principal:</strong> {credentialMode}
                          </div>
                        </>
                      )}
                      <div className="custom-field-hint-line">
                        <strong>Latency:</strong>{' '}
                        {latencyMs !== undefined ? `${String(latencyMs)}ms` : 'N/A'}
                      </div>
                    </div>
                  }
                />

                <div className="custom-fields-rail-value">
                  {hasError ? (
                    <span
                      className="custom-field-error-inline"
                      data-testid={`custom-field-error-${def.slug}`}
                    >
                      {errorMessage}
                    </span>
                  ) : result ? (
                    <CustomFieldValue
                      format={def.output_format}
                      value={result.value}
                      metadata={def.output_format_metadata}
                      testId={`custom-field-value-${def.slug}`}
                    />
                  ) : (
                    <span
                      className="custom-field-uncomputed"
                      data-testid={`custom-field-uncomputed-${def.slug}`}
                    >
                      Uncomputed
                    </span>
                  )}
                </div>

                {canEdit && (
                  <button
                    type="button"
                    className="custom-fields-refresh-btn"
                    aria-label={`Refresh ${def.name}`}
                    aria-busy={isInFlight ? 'true' : 'false'}
                    disabled={isInFlight}
                    onClick={() => {
                      handleRefresh(def.id);
                    }}
                    data-testid={`refresh-field-${def.slug}`}
                  >
                    ↻
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/**
 * Properties-rail section wrapper. Safe when mounted without QueryClientProvider.
 */
export function CustomFieldsRailSection(
  props: CustomFieldsRailSectionProps,
): JSX.Element | null {
  const client = React.useContext(QueryClientContext);
  if (!client) {
    return null;
  }
  return <CustomFieldsRailSectionInner {...props} />;
}

