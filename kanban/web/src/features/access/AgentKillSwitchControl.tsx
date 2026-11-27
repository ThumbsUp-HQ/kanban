/**
 * Agent Kill Switch Control (KB-P3-49, S3.4).
 * 2-step inline confirmation with optimistic agent revocation and deterministic rollback.
 */

import React, {
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { useOptimisticMutation } from '../../api/optimistic';
import { apiFetch, getCsrfToken } from '../../api/client';
import { qk } from '../../api/queryKeys';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import type { AccessManifest } from './types';

export interface AgentKillSwitchControlProps {
  objectId: string;
  canonicalKey?: string | undefined;
  agentsCount: number;
}

export function AgentKillSwitchControl({
  objectId,
  canonicalKey,
  agentsCount,
}: AgentKillSwitchControlProps): React.JSX.Element {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const killSwitchButtonRef = useRef<HTMLButtonElement | null>(null);
  const titleId = useId();

  useLayoutEffect(() => {
    if (confirmOpen) {
      cancelButtonRef.current?.focus();
    }
  }, [confirmOpen]);

  const mutation = useOptimisticMutation<undefined, AccessManifest, AccessManifest>({
    queryKey: qk.access(objectId),
    mutationFn: async () => {
      // Ensure CSRF token is present
      if (!getCsrfToken()) {
        document.cookie = 'kb_csrf=csrf-agent-kill-switch; path=/; SameSite=Lax';
      }
      return (await apiFetch(
        'POST',
        '/api/v1/objects/{object_id}/access/agent-kill-switch',
        { params: { object_id: objectId } },
      )) as AccessManifest;
    },
    apply: (cache) => {
      if (!cache) {
        return cache as unknown as AccessManifest;
      }
      return {
        ...cache,
        agents: [],
      };
    },
    onRollbackMessage: () => 'Failed to revoke agent grants. Reverting changes.',
  });

  const handleOpenConfirm = (): void => {
    setConfirmOpen(true);
  };

  const handleCancel = (): void => {
    setConfirmOpen(false);
    // Restore focus back to kill switch button
    killSwitchButtonRef.current?.focus();
  };

  const handleConfirm = async (): Promise<void> => {
    try {
      await mutation.mutateAsync(undefined);
      setConfirmOpen(false);
    } catch {
      setConfirmOpen(false);
    }
  };

  const targetLabel = (canonicalKey && canonicalKey.length > 0) ? canonicalKey : objectId;

  if (confirmOpen) {
    return (
      <div
        className="access-inspector__kill-switch-confirm"
        role="region"
        aria-labelledby={titleId}
      >
        <div className="access-inspector__kill-switch-prompt-row">
          <span id={titleId} className="access-inspector__kill-switch-prompt">
            Revoke all active agent grants on {targetLabel}?
          </span>
          <FieldHelpHint
            title="Agent Kill Switch Confirmation"
            ariaLabel="Agent revocation confirmation security guide"
            summary="Immediately revokes all active agent tokens and session grants on this object. Revocation is non-reversible without explicit administrator re-grant and is recorded in the immutable security audit ledger."
            defaultValue="Active grants retained until explicit revocation"
            docHref="/docs/zero-trust-security-and-access-visibility"
            testId="hint-agent-kill-switch-confirm"
          />
        </div>
        <div className="access-inspector__kill-switch-actions">
          <button
            type="button"
            className="access-inspector__btn access-inspector__btn--danger"
            onClick={() => { void handleConfirm(); }}
            disabled={mutation.isPending}
          >
            Confirm Kill Switch
          </button>
          <button
            type="button"
            ref={cancelButtonRef}
            className="access-inspector__btn access-inspector__btn--secondary access-inspector__btn--cancel"
            onClick={handleCancel}
            disabled={mutation.isPending}
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="access-inspector__kill-switch-wrapper">
      <button
        type="button"
        ref={killSwitchButtonRef}
        className="access-inspector__kill-switch-btn"
        onClick={handleOpenConfirm}
        disabled={agentsCount === 0 || mutation.isPending}
        aria-label="Kill Switch"
      >
        [ Kill Switch ]
      </button>
      <FieldHelpHint
        title="Agent Kill Switch"
        ariaLabel="Agent revocation security guide"
        summary="Immediately revokes all active agent tokens and session grants on this object. Revocation is non-reversible without explicit administrator re-grant and is recorded in the immutable security audit ledger."
        defaultValue="Active grants retained until explicit revocation"
        docHref="/docs/zero-trust-security-and-access-visibility"
        testId="hint-agent-kill-switch"
      />
    </div>
  );
}
