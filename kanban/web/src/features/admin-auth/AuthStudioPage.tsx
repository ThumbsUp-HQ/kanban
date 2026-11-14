import React, { useState, useEffect, useCallback, type JSX } from 'react';
import { apiFetch } from '../../api/client';
import { ApiProblem } from '../../api/problem';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import { AuthCardRow } from './AuthCardRow';
import { AuthCardEditorDrawer } from './AuthCardEditorDrawer';
import { LockoutPreventedBanner } from './LockoutPreventedBanner';
import { midpointRank } from './cardRank';
import {
  fetchAdminAuthCards,
  createAdminAuthCard,
  updateAdminAuthCard,
  toggleAdminAuthCardEnabled,
  reorderAdminAuthCard,
  testAuthCardHandshake,
  deleteAdminAuthCard,
  type AdminAuthCard,
  type CreateAuthCardPayload,
  type UpdateAuthCardPayload,
} from './adminAuthApi';
import { SecondFactorStep } from '../auth/SecondFactorStep';
import type { MfaMethod } from '../auth/authApi';
import './adminAuth.css';

interface CurrentUserResponse {
  id?: string;
  handle?: string;
  is_server_admin?: boolean;
}

interface PendingMutation {
  type: 'toggle' | 'reorder' | 'delete' | 'save';
  card: AdminAuthCard;
  extra?: unknown;
}

function parseLockoutError(
  err: unknown,
): { reasonCode: string | null; detail?: string | null | undefined } | null {
  if (err instanceof ApiProblem && err.code === 'LOCKOUT_PREVENTED') {
    const data = err.data as Record<string, unknown> | undefined;
    return {
      reasonCode: typeof data?.reason_code === 'string' ? data.reason_code : null,
      detail: err.detail ?? null,
    };
  }
  return null;
}

export function AuthStudioPage(): JSX.Element {
  const [currentUser, setCurrentUser] = useState<CurrentUserResponse | null>(null);
  const [isUserLoading, setIsUserLoading] = useState(true);
  const [accessDenied, setAccessDenied] = useState(false);

  const [cards, setCards] = useState<AdminAuthCard[]>([]);
  const [isLoadingCards, setIsLoadingCards] = useState(true);

  // Drawer state
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [editingCard, setEditingCard] = useState<AdminAuthCard | null>(null);

  // Lockout error state
  const [lockoutError, setLockoutError] = useState<{
    reasonCode: string | null;
    detail?: string | null | undefined;
  } | null>(null);

  // General error or notification
  const [generalError, setGeneralError] = useState<string | null>(null);

  // Active testing or toggling card IDs
  const [testingCardIds, setTestingCardIds] = useState<Set<string>>(new Set());
  const [togglingCardIds, setTogglingCardIds] = useState<Set<string>>(new Set());

  // Drag and drop state
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  // AAL2 Step-Up state
  const [aal2Challenge, setAal2Challenge] = useState<{
    challengeId: string;
    methods: MfaMethod[];
  } | null>(null);
  const [pendingMutation, setPendingMutation] = useState<PendingMutation | null>(null);

  // 1. Fetch current user and verify Server Admin access
  useEffect(() => {
    async function checkAccess() {
      try {
        const rawMe = await apiFetch(
          'GET',
          '/api/v1/auth/me' as never,
        );
        const me = rawMe as CurrentUserResponse;
        setCurrentUser(me);
        if (!me.is_server_admin) {
          setAccessDenied(true);
        }
      } catch {
        setAccessDenied(true);
      } finally {
        setIsUserLoading(false);
      }
    }

    void checkAccess();
  }, []);

  // 2. Fetch cards if admin access confirmed
  const loadCards = useCallback(async () => {
    setIsLoadingCards(true);
    setGeneralError(null);
    try {
      const res = await fetchAdminAuthCards();
      setCards(res.cards);
    } catch (err: unknown) {
      if (err instanceof ApiProblem && (err.status === 403 || err.status === 404)) {
        setAccessDenied(true);
      } else if (err instanceof Error) {
        setGeneralError(err.message);
      } else {
        setGeneralError('Failed to load authentication cards.');
      }
    } finally {
      setIsLoadingCards(false);
    }
  }, []);

  useEffect(() => {
    if (!accessDenied && currentUser?.is_server_admin) {
      void loadCards();
    }
  }, [accessDenied, currentUser, loadCards]);

  // Sort cards: non-LOCAL_ADMIN sorted by sort_rank (COLLATE "C"), LOCAL_ADMIN pinned at end
  const externalCards = cards
    .filter((c) => c.provider_kind !== 'LOCAL_ADMIN')
    .sort((a, b) => (a.sort_rank < b.sort_rank ? -1 : a.sort_rank > b.sort_rank ? 1 : 0));
  const localAdminCard = cards.find((c) => c.provider_kind === 'LOCAL_ADMIN');
  const sortedCards = localAdminCard ? [...externalCards, localAdminCard] : externalCards;

  // First enabled external card gets Primary badge
  const primaryCardId = externalCards.find((c) => c.is_enabled)?.id;

  // AAL2 Step-Up handler
  const handleAal2Intercept = (err: unknown, mutation: PendingMutation): boolean => {
    if (err instanceof ApiProblem && err.code === 'AAL2_REQUIRED') {
      setPendingMutation(mutation);
      const data = err.data;
      const challengeId = typeof data.challenge_id === 'string' ? data.challenge_id : 'aal2-stepup';
      const methods = Array.isArray(data.methods) ? (data.methods as MfaMethod[]) : (['webauthn', 'totp'] as MfaMethod[]);
      setAal2Challenge({ challengeId, methods });
      return true;
    }
    return false;
  };

  const handleAal2Success = async () => {
    const mutation = pendingMutation;
    setAal2Challenge(null);
    setPendingMutation(null);

    if (!mutation) return;

    // Replay pending mutation
    if (mutation.type === 'toggle') {
      await handleToggleEnabled(mutation.card, Boolean(mutation.extra));
    } else if (mutation.type === 'delete') {
      await handleDeleteCard(mutation.card);
    }
  };

  // Toggle card enabled state
  const handleToggleEnabled = async (card: AdminAuthCard, enabled: boolean) => {
    // Optimistic mutation
    const previousCards = [...cards];
    setCards((prev) =>
      prev.map((c) => (c.id === card.id ? { ...c, is_enabled: enabled } : c)),
    );
    setTogglingCardIds((prev) => new Set(prev).add(card.id));
    setLockoutError(null);

    try {
      const updated = await toggleAdminAuthCardEnabled(card.id, enabled);
      setCards((prev) => prev.map((c) => (c.id === card.id ? updated : c)));
    } catch (err: unknown) {
      // Rollback optimistic state
      setCards(previousCards);

      if (handleAal2Intercept(err, { type: 'toggle', card, extra: enabled })) {
        return;
      }

      const lockout = parseLockoutError(err);
      if (lockout) {
        setLockoutError(lockout);
        return;
      }

      setGeneralError(err instanceof Error ? err.message : 'Failed to update card status.');
    } finally {
      setTogglingCardIds((prev) => {
        const next = new Set(prev);
        next.delete(card.id);
        return next;
      });
    }
  };

  // Test Handshake
  const handleTestHandshake = async (card: AdminAuthCard) => {
    setTestingCardIds((prev) => new Set(prev).add(card.id));
    setGeneralError(null);

    try {
      const result = await testAuthCardHandshake(card.id);
      setCards((prev) =>
        prev.map((c) =>
          c.id === card.id
            ? {
                ...c,
                last_health_status: result.last_health_status,
                latency_ms: result.latency_ms,
                check_summary: result.check_summary,
                last_handshake_at: new Date().toISOString(),
              }
            : c,
        ),
      );
    } catch (err: unknown) {
      setCards((prev) =>
        prev.map((c) =>
          c.id === card.id
            ? {
                ...c,
                last_health_status: 'FAILED',
                latency_ms: null,
                check_summary: err instanceof Error ? err.message : 'Handshake failed',
                last_handshake_at: new Date().toISOString(),
              }
            : c,
        ),
      );
    } finally {
      setTestingCardIds((prev) => {
        const next = new Set(prev);
        next.delete(card.id);
        return next;
      });
    }
  };

  // Reorder Cards
  const handleMove = async (
    card: AdminAuthCard,
    direction: 'up' | 'down',
  ) => {
    const listIndex = externalCards.findIndex((c) => c.id === card.id);
    const targetIndex = direction === 'up' ? listIndex - 1 : listIndex + 1;
    const targetCard = externalCards[targetIndex];
    if (!targetCard) return;

    let newRank: string;
    let beforeId: string | null = null;
    let afterId: string | null = null;

    if (direction === 'up') {
      const prevPrev = externalCards[targetIndex - 1];
      newRank = midpointRank(prevPrev ? prevPrev.sort_rank : null, targetCard.sort_rank);
      beforeId = targetCard.id;
      afterId = prevPrev ? prevPrev.id : null;
    } else {
      const nextNext = externalCards[targetIndex + 1];
      newRank = midpointRank(targetCard.sort_rank, nextNext ? nextNext.sort_rank : null);
      afterId = targetCard.id;
      beforeId = nextNext ? nextNext.id : null;
    }

    const previousCards = [...cards];
    // Optimistic reorder
    setCards((prev) =>
      prev.map((c) => (c.id === card.id ? { ...c, sort_rank: newRank } : c)),
    );

    try {
      const updated = await reorderAdminAuthCard(card.id, {
        before_card_id: beforeId,
        after_card_id: afterId,
        sort_rank: newRank,
      });
      setCards((prev) => prev.map((c) => (c.id === card.id ? updated : c)));
    } catch {
      // Rollback
      setCards(previousCards);
      setGeneralError('Failed to reorder card.');
    }
  };

  // Drag and drop events
  const handleDragStart = (
    _e: React.DragEvent<HTMLLIElement>,
    index: number,
  ) => {
    setDraggedIndex(index);
  };

  const handleDragOver = (e: React.DragEvent<HTMLLIElement>) => {
    e.preventDefault();
  };

  const handleDrop = async (
    e: React.DragEvent<HTMLLIElement>,
    dropIndex: number,
  ) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === dropIndex) {
      setDraggedIndex(null);
      return;
    }

    // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
    const draggedCard = externalCards[draggedIndex]!;

    let newRank: string;
    let beforeId: string | null = null;
    let afterId: string | null = null;

    if (draggedIndex < dropIndex) {
      // Moving down
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      const afterCard = externalCards[dropIndex]!;
      const beforeCard = externalCards[dropIndex + 1];
      newRank = midpointRank(afterCard.sort_rank, beforeCard ? beforeCard.sort_rank : null);
      afterId = afterCard.id;
      beforeId = beforeCard ? beforeCard.id : null;
    } else {
      // Moving up
      const afterCard = externalCards[dropIndex - 1];
      // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
      const beforeCard = externalCards[dropIndex]!;
      newRank = midpointRank(afterCard ? afterCard.sort_rank : null, beforeCard.sort_rank);
      afterId = afterCard ? afterCard.id : null;
      beforeId = beforeCard.id;
    }

    setDraggedIndex(null);
    const previousCards = [...cards];
    setCards((prev) =>
      prev.map((c) => (c.id === draggedCard.id ? { ...c, sort_rank: newRank } : c)),
    );

    try {
      const updated = await reorderAdminAuthCard(draggedCard.id, {
        before_card_id: beforeId,
        after_card_id: afterId,
        sort_rank: newRank,
      });
      setCards((prev) => prev.map((c) => (c.id === draggedCard.id ? updated : c)));
    } catch {
      setCards(previousCards);
      setGeneralError('Failed to reorder card.');
    }
  };

  // Delete card
  const handleDeleteCard = async (card: AdminAuthCard) => {
    if (card.provider_kind === 'LOCAL_ADMIN') return;

    const previousCards = [...cards];
    setCards((prev) => prev.filter((c) => c.id !== card.id));
    setLockoutError(null);

    try {
      await deleteAdminAuthCard(card.id);
    } catch (err: unknown) {
      setCards(previousCards);

      if (handleAal2Intercept(err, { type: 'delete', card })) {
        return;
      }

      const lockout = parseLockoutError(err);
      if (lockout) {
        setLockoutError(lockout);
        return;
      }

      setGeneralError(err instanceof Error ? err.message : 'Failed to delete card.');
    }
  };

  // Save card from drawer
  const handleSaveDrawer = async (
    payload: CreateAuthCardPayload | UpdateAuthCardPayload,
    isEdit: boolean,
  ) => {
    if (isEdit && editingCard) {
      try {
        const updated = await updateAdminAuthCard(
          editingCard.id,
          payload,
        );
        setCards((prev) =>
          prev.map((c) => (c.id === editingCard.id ? updated : c)),
        );
      } catch (err: unknown) {
        const lockout = parseLockoutError(err);
        if (lockout) {
          setLockoutError(lockout);
        }
        throw err;
      }
    } else {
      const created = await createAdminAuthCard(payload as CreateAuthCardPayload);
      setCards((prev) => [...prev, created]);
    }
  };

  // Access denied / non-admin: render uniform "Not found or no access" state
  if (accessDenied) {
    return (
      <main className="auth-studio-page" data-testid="auth-studio-page">
        <div className="auth-empty-state" role="alert">
          <h2>Not found or no access</h2>
          <p>The requested page does not exist or you do not have permission to view it.</p>
        </div>
      </main>
    );
  }

  // Loading state
  if (isUserLoading || isLoadingCards) {
    return (
      <main className="auth-studio-page" data-testid="auth-studio-page">
        <p className="auth-card-subtext">Loading Authentication Studio...</p>
      </main>
    );
  }

  return (
    <main className="auth-studio-page" data-testid="auth-studio-page">
      {/* Studio Header */}
      <header className="auth-studio-header">
        <div className="auth-studio-title-row">
          <h1 className="auth-studio-title">Authentication Studio</h1>
          <EmojiHint
            kind="access"
            label="Authentication architecture info"
            content="Simultaneous OIDC, OAuth2, LDAPS/StartTLS, and Local Admin cards. Matching email addresses never auto-merge accounts across cards (bound strictly by auth_card_id + immutable_subject_id)."
          />
        </div>

        <button
          type="button"
          className="auth-studio-add-btn"
          onClick={() => {
            setEditingCard(null);
            setIsDrawerOpen(true);
          }}
        >
          + Add auth card
        </button>
      </header>

      {/* LOCKOUT_PREVENTED Alert Banner */}
      {lockoutError ? (
        <LockoutPreventedBanner
          reasonCode={lockoutError.reasonCode}
          detail={lockoutError.detail}
          onDismiss={() => { setLockoutError(null); }}
        />
      ) : null}

      {/* General Error Banner */}
      {generalError ? (
        <div className="auth-lockout-banner" role="alert">
          <div className="auth-lockout-header">
            <span>{generalError}</span>
            <button
              type="button"
              className="auth-btn-secondary"
              onClick={() => { setGeneralError(null); }}
              aria-label="Dismiss error"
            >
              ×
            </button>
          </div>
        </div>
      ) : null}

      {/* Cards List */}
      <ol className="auth-studio-list" role="list">
        {sortedCards.map((card, idx) => (
          <AuthCardRow
            key={card.id}
            card={card}
            index={idx}
            totalCards={sortedCards.length}
            isPrimary={card.id === primaryCardId}
            onMoveUp={() => {
              void handleMove(card, 'up');
            }}
            onMoveDown={() => {
              void handleMove(card, 'down');
            }}
            onToggleEnabled={(c, enabled) => {
              void handleToggleEnabled(c, enabled);
            }}
            onTestHandshake={(c) => {
              void handleTestHandshake(c);
            }}
            onEdit={(c) => {
              setEditingCard(c);
              setIsDrawerOpen(true);
            }}
            onDelete={(c) => {
              void handleDeleteCard(c);
            }}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDrop={(e, i) => {
              void handleDrop(e, i);
            }}
            isTestingHandshake={testingCardIds.has(card.id)}
            isToggling={togglingCardIds.has(card.id)}
          />
        ))}
      </ol>

      {/* Create / Edit Drawer */}
      <AuthCardEditorDrawer
        key={editingCard ? editingCard.id : (isDrawerOpen ? 'open-new' : 'closed')}
        isOpen={isDrawerOpen}
        card={editingCard}
        onClose={() => {
          setIsDrawerOpen(false);
          setEditingCard(null);
        }}
        onSave={handleSaveDrawer}
      />

      {/* AAL2 Step-Up Modal Dialog */}
      {aal2Challenge ? (
        <div className="auth-drawer-backdrop" role="presentation">
          <div
            className="auth-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="aal2-stepup-title"
          >
            <h2 id="aal2-stepup-title" className="auth-title">
              Admin Verification Required (AAL2)
            </h2>
            <SecondFactorStep
              challengeId={aal2Challenge.challengeId}
              methods={aal2Challenge.methods}
              onSuccess={() => {
                void handleAal2Success();
              }}
              onError={() => {
                // Handled in SecondFactorStep
              }}
              onSessionExpired={() => {
                setAal2Challenge(null);
                setPendingMutation(null);
                setGeneralError('Session expired. Please sign in again.');
              }}
              onCancel={() => {
                setAal2Challenge(null);
                setPendingMutation(null);
              }}
            />
          </div>
        </div>
      ) : null}
    </main>
  );
}
