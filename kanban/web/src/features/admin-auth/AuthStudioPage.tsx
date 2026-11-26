import React, { useState, useEffect, useCallback, useRef, type JSX } from 'react';
import { Link, useInRouterContext } from 'react-router';
import { QueryClientContext } from '@tanstack/react-query';
import { apiFetch } from '../../api/client';
import { ApiProblem, isMfaEnrollmentRequiredCode } from '../../api/problem';
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
  testDraftAuthCardHandshake,
  deleteAdminAuthCard,
  fetchAdminPrincipals,
  createLocalUser,
  resetUserPassword,
  updateUserRole,
  isSoleActiveAdminCard,
  type AdminAuthCard,
  type CreateAuthCardPayload,
  type UpdateAuthCardPayload,
  type AdminUserPrincipal,
} from './adminAuthApi';
import { isAal2StepUpCancelled } from '../../api/client';
import { StudioDocLink } from '../../components/help/StudioDocLink';
import { AdminStudioSubnav } from '../admin/AdminStudioSubnav';
import { RbacPolicyBuilder } from '../rbac/RbacPolicyBuilder';
import { RoleLabelPicker } from '../rbac/RoleLabelPicker';
import { ErrorHelpHint } from '../../components/help/ErrorHelpHint';
import './adminAuth.css';

interface CurrentUserResponse {
  id?: string;
  handle?: string;
  is_server_admin?: boolean;
}

const isUuid = (val: string): boolean =>
  /^[0-9a-f]{8}(-[0-9a-f]{4}){0,3}(-[0-9a-f]{4,12})?$/i.test(val.replace(/^@+/, '').trim());

export function formatHandle(
  handle?: string | null,
  fallbackDisplayName?: string | null,
  principalType?: string | null,
): string {
  const isGroup = principalType?.toUpperCase() === 'GROUP';
  const slugify = (str: string): string =>
    str
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^a-z0-9._-]/g, '')
      .replace(/^-+|-+$/g, '');

  if (handle) {
    const clean = handle.trim().replace(/^@+/, '');
    if (clean && !isUuid(clean)) {
      if (isGroup) {
        const slug = slugify(clean);
        return slug ? `@${slug}` : '@group';
      }
      return `@${clean}`;
    }
  }
  if (fallbackDisplayName) {
    const cleanFallback = fallbackDisplayName.trim().replace(/^@+/, '');
    if (cleanFallback && !isUuid(cleanFallback)) {
      const slug = slugify(cleanFallback);
      if (slug) return `@${slug}`;
    }
  }
  return isGroup ? '@group' : '';
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

function getProviderBadgeClass(provider: string | undefined): string {
  const norm = (provider ?? '').toUpperCase();
  if (norm.includes('LOCAL')) return 'auth-badge-provider--local';
  if (norm.includes('GOOGLE')) return 'auth-badge-provider--google';
  if (norm.includes('GITHUB')) return 'auth-badge-provider--github';
  if (norm.includes('DIRECTORY') || norm.includes('AD')) return 'auth-badge-provider--ad';
  if (norm.includes('LDAP')) return 'auth-badge-provider--ldap';
  return 'auth-badge-provider--oauth';
}

export function AuthStudioPage(): JSX.Element {
  const inRouter = useInRouterContext();
  const queryClient = React.useContext(QueryClientContext);
  const [currentUser, setCurrentUser] = useState<CurrentUserResponse | null>(null);
  const [isUserLoading, setIsUserLoading] = useState(true);
  const [accessDenied, setAccessDenied] = useState(false);
  const [mfaEnrollmentRequired, setMfaEnrollmentRequired] = useState(false);

  // Studio tab state
  const [activeTab, setActiveTab] = useState<'cards' | 'users' | 'roles'>('cards');

  // Cards state
  const [cards, setCards] = useState<AdminAuthCard[]>([]);
  const [isLoadingCards, setIsLoadingCards] = useState(true);

  // Users state
  const [users, setUsers] = useState<AdminUserPrincipal[]>([]);
  const [principalKindFilter, setPrincipalKindFilter] = useState<'ALL' | 'USER' | 'GROUP' | 'AGENT'>('ALL');
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [userActionError, setUserActionError] = useState<string | null>(null);
  const [userActionSuccess, setUserActionSuccess] = useState<string | null>(null);

  // User Modals state
  const [isAddUserOpen, setIsAddUserOpen] = useState(false);
  const [resetTargetUser, setResetTargetUser] = useState<AdminUserPrincipal | null>(null);

  // New local user/principal form state
  const [newPrincipalType, setNewPrincipalType] = useState<'USER' | 'GROUP' | 'AGENT'>('USER');
  const [newUserHandle, setNewUserHandle] = useState('');
  const [newUserDisplayName, setNewUserDisplayName] = useState('');
  const [newUserEmail, setNewUserEmail] = useState('');
  const [newUserPassword, setNewUserPassword] = useState('');
  const [newUserRole, setNewUserRole] = useState('WORKSPACE_MEMBER');
  const [isSubmittingUser, setIsSubmittingUser] = useState(false);

  // Reset password form state
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isSubmittingPassword, setIsSubmittingPassword] = useState(false);

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

  // Client-side break-glass warning target
  const [breakGlassTarget, setBreakGlassTarget] = useState<{ card: AdminAuthCard; action: 'disable' | 'delete' } | null>(null);

  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // 1. Fetch current user and verify Server Admin access
  useEffect(() => {
    async function checkAccess() {
      try {
        const rawMe = await apiFetch(
          'GET',
          '/api/v1/auth/me' as never,
        );
        const me = rawMe as CurrentUserResponse;
        /* v8 ignore next */
        if (!isMountedRef.current) return;
        setCurrentUser(me);
        if (!me.is_server_admin) {
          setAccessDenied(true);
        }
      } catch (err: unknown) {
        /* v8 ignore next */
        if (!isMountedRef.current) return;
        if (err instanceof ApiProblem && isMfaEnrollmentRequiredCode(err.code)) {
          setMfaEnrollmentRequired(true);
        } else {
          setAccessDenied(true);
        }
      } finally {
        /* v8 ignore next */
        if (isMountedRef.current) {
          setIsUserLoading(false);
        }
      }
    }

    void checkAccess();
  }, []);

  // 2. Fetch cards if admin access confirmed
  const loadCards = useCallback(async () => {
    /* v8 ignore next */
    if (isMountedRef.current) {
      setIsLoadingCards(true);
      setGeneralError(null);
    }
    try {
      const res = await fetchAdminAuthCards();
      /* v8 ignore next */
      if (isMountedRef.current) {
        setCards(res.cards);
      }
    } catch (err: unknown) {
      /* v8 ignore next */
      if (!isMountedRef.current) return;
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      if (err instanceof ApiProblem && isMfaEnrollmentRequiredCode(err.code)) {
        setMfaEnrollmentRequired(true);
      } else if (err instanceof ApiProblem && (err.status === 403 || err.status === 404)) {
        setAccessDenied(true);
      } else if (err instanceof Error) {
        setGeneralError(err.message);
      } else {
        setGeneralError('Failed to load authentication cards.');
      }
    } finally {
      /* v8 ignore next */
      if (isMountedRef.current) {
        setIsLoadingCards(false);
      }
    }
  }, []);

  // 3. Fetch principals if admin access confirmed
  const loadUsers = useCallback(async (filter?: string) => {
    /* v8 ignore next */
    if (isMountedRef.current) {
      setIsLoadingUsers(true);
      setUserActionError(null);
    }
    try {
      const activeFilter = filter !== undefined ? (filter === 'ALL' ? undefined : filter) : (principalKindFilter === 'ALL' ? undefined : principalKindFilter);
      const principals = await fetchAdminPrincipals(activeFilter);
      /* v8 ignore next */
      if (isMountedRef.current) {
        setUsers(Array.isArray(principals) ? principals : []);
      }
    } catch (err: unknown) {
      /* v8 ignore next */
      if (!isMountedRef.current) return;
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      if (err instanceof ApiProblem && isMfaEnrollmentRequiredCode(err.code)) {
        setMfaEnrollmentRequired(true);
      } else if (err instanceof ApiProblem && (err.status === 403 || err.status === 404)) {
        setAccessDenied(true);
      } else if (err instanceof Error) {
        setUserActionError(err.message);
      } else {
        setUserActionError('Failed to load user principals.');
      }
    } finally {
      /* v8 ignore next */
      if (isMountedRef.current) {
        setIsLoadingUsers(false);
      }
    }
  }, [principalKindFilter]);

  useEffect(() => {
    if (!accessDenied && !mfaEnrollmentRequired && currentUser?.is_server_admin) {
      void loadCards();
      void loadUsers();
    }
  }, [accessDenied, currentUser, loadCards, loadUsers, mfaEnrollmentRequired]);

  // Sort cards: non-LOCAL_ADMIN sorted by sort_rank (COLLATE "C"), LOCAL_ADMIN pinned at end
  const externalCards = cards
    .filter((c) => c.provider_kind !== 'LOCAL_ADMIN')
    .sort((a, b) => (a.sort_rank < b.sort_rank ? -1 : a.sort_rank > b.sort_rank ? 1 : 0));
  const localAdminCard = cards.find((c) => c.provider_kind === 'LOCAL_ADMIN');
  const sortedCards = localAdminCard ? [...externalCards, localAdminCard] : externalCards;

  // First enabled external card gets Primary badge
  const primaryCardId = externalCards.find((c) => c.is_enabled)?.id;

  // Toggle card enabled state
  const executeToggleEnabled = async (card: AdminAuthCard, enabled: boolean) => {
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
      setCards(previousCards);

      if (isAal2StepUpCancelled(err)) {
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

  const handleToggleEnabled = async (card: AdminAuthCard, enabled: boolean) => {
    if (!enabled && isSoleActiveAdminCard(card, cards)) {
      setBreakGlassTarget({ card, action: 'disable' });
      return;
    }
    await executeToggleEnabled(card, enabled);
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
                last_health_status: (result.last_health_status ?? 'FAILED'),
                latency_ms: result.latency_ms,
                check_summary: result.check_summary ?? null,
                last_handshake_at: new Date().toISOString(),
              }
            : c,
        ),
      );
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) return;
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
    } catch (err: unknown) {
      setCards(previousCards);
      if (isAal2StepUpCancelled(err)) return;
      setGeneralError('Failed to reorder card.');
    }
  };

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

    const draggedCard = externalCards[draggedIndex];
    if (!draggedCard) return;

    let newRank: string;
    let beforeId: string | null = null;
    let afterId: string | null = null;

    if (draggedIndex < dropIndex) {
      const afterCard = externalCards[dropIndex];
      const beforeCard = externalCards[dropIndex + 1];
      if (!afterCard) return;
      newRank = midpointRank(afterCard.sort_rank, beforeCard ? beforeCard.sort_rank : null);
      afterId = afterCard.id;
      beforeId = beforeCard ? beforeCard.id : null;
    } else {
      const afterCard = externalCards[dropIndex - 1];
      const beforeCard = externalCards[dropIndex];
      if (!beforeCard) return;
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
    } catch (err: unknown) {
      setCards(previousCards);
      if (isAal2StepUpCancelled(err)) return;
      setGeneralError('Failed to reorder card.');
    }
  };

  // Delete card
  const executeDeleteCard = async (card: AdminAuthCard) => {
    if (card.provider_kind === 'LOCAL_ADMIN') return;

    const previousCards = [...cards];
    setCards((prev) => prev.filter((c) => c.id !== card.id));
    setLockoutError(null);

    try {
      await deleteAdminAuthCard(card.id);
    } catch (err: unknown) {
      setCards(previousCards);

      if (isAal2StepUpCancelled(err)) {
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

  const handleDeleteCard = async (card: AdminAuthCard) => {
    if (card.provider_kind === 'LOCAL_ADMIN') return;
    if (card.is_enabled && isSoleActiveAdminCard(card, cards)) {
      setBreakGlassTarget({ card, action: 'delete' });
      return;
    }
    await executeDeleteCard(card);
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

  // Handle role change for user
  const handleRoleChange = async (userId: string, newRole: string, previousRole?: string) => {
    setUserActionError(null);
    setUserActionSuccess(null);
    try {
      await updateUserRole(userId, newRole, previousRole);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, role: newRole } : u)),
      );
      setUserActionSuccess('User role updated successfully.');
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      setUserActionError(err instanceof Error ? err.message : 'Failed to update user role.');
    }
  };

  // Handle Add Local User / Principal
  const handleCreateLocalUserSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (newPrincipalType === 'USER' && (!newUserHandle || !newUserEmail || !newUserPassword)) {
      setUserActionError('Handle, email, and password are required.');
      return;
    }
    if (!newUserHandle) {
      setUserActionError('Handle is required.');
      return;
    }
    setIsSubmittingUser(true);
    setUserActionError(null);
    setUserActionSuccess(null);

    try {
      const payload: Parameters<typeof createLocalUser>[0] = {
        handle: newUserHandle.trim(),
        display_name: (newUserDisplayName || newUserHandle).trim(),
        role: newUserRole,
      };
      if (newUserEmail.trim()) {
        payload.email = newUserEmail.trim();
      }
      if (newUserPassword) {
        payload.password = newUserPassword;
      }
      if (newPrincipalType !== 'USER') {
        payload.type = newPrincipalType;
      }
      const createdUser = await createLocalUser(payload);
      const successMsg =
        newPrincipalType === 'USER'
          ? `Local user @${newUserHandle} created successfully.`
          : `Principal (${newPrincipalType}) @${newUserHandle} created successfully.`;
      setUserActionSuccess(successMsg);

      await loadUsers();
      if (createdUser.id) {
        setUsers((prev) => {
          if (prev.some((u) => u.id === createdUser.id)) return prev;
          return [...prev, createdUser];
        });
      }
      if (queryClient) {
        await queryClient.invalidateQueries({ queryKey: ['admin-principals'] });
        await queryClient.invalidateQueries({ queryKey: ['principals'] });
      }

      setIsAddUserOpen(false);
      setNewPrincipalType('USER');
      setNewUserHandle('');
      setNewUserDisplayName('');
      setNewUserEmail('');
      setNewUserPassword('');
      setNewUserRole('WORKSPACE_MEMBER');
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      setUserActionError(err instanceof Error ? err.message : 'Failed to create principal.');
    } finally {
      setIsSubmittingUser(false);
    }
  };

  // Handle Reset Password Submit
  const handleResetPasswordSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!resetTargetUser) return;
    if (!newPassword || newPassword !== confirmPassword) {
      setUserActionError('Passwords do not match or cannot be empty.');
      return;
    }
    setIsSubmittingPassword(true);
    setUserActionError(null);
    setUserActionSuccess(null);

    try {
      await resetUserPassword(resetTargetUser.id, newPassword);
      setUserActionSuccess(
        `Password reset successfully for ${formatHandle(resetTargetUser.handle ?? resetTargetUser.principal, resetTargetUser.display_name, resetTargetUser.type)}.`,
      );
      setResetTargetUser(null);
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      setUserActionError(err instanceof Error ? err.message : 'Failed to reset password.');
    } finally {
      setIsSubmittingPassword(false);
    }
  };

  // Access denied / non-admin: uniform empty state
  if (accessDenied) {
    return (
      <div className="auth-studio-page" data-testid="auth-studio-page">
        <div className="auth-empty-state" role="alert">
          <h2>Not found or no access</h2>
          <p>The requested page does not exist or you do not have permission to view it.</p>
        </div>
      </div>
    );
  }

  // MFA Enrollment Required: inform server admin to enroll a second factor in profile settings
  if (mfaEnrollmentRequired) {
    return (
      <div className="auth-studio-page" data-testid="auth-studio-page">
        <AdminStudioSubnav activeTab="auth" isServerAdmin={currentUser?.is_server_admin} />
        <div
          className="auth-empty-state kb-mfa-enrollment-banner"
          role="alert"
          data-testid="mfa-enrollment-required-banner"
        >
          <h2>Two-Factor Authentication Required</h2>
          <p>
            Administrative operations require MFA enrollment. Please configure a second factor in your{' '}
            {inRouter ? (
              <Link to="/settings/profile">profile settings</Link>
            ) : (
              <a href="/settings/profile">profile settings</a>
            )}
            .
          </p>
        </div>
      </div>
    );
  }

  // Loading state
  if (isUserLoading || isLoadingCards) {
    return (
      <div className="auth-studio-page" data-testid="auth-studio-page">
        <p className="auth-card-subtext">Loading Authentication Studio...</p>
      </div>
    );
  }

  return (
    <div className="auth-studio-page" data-testid="auth-studio-page">
      <AdminStudioSubnav activeTab="auth" isServerAdmin={currentUser?.is_server_admin} />
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

        <div className="auth-studio-header-actions">
          <StudioDocLink
            href="/docs/multi-card-authentication-studio"
            title="Multi-Card Authentication Studio Documentation"
            testId="auth-studio-doc-link"
          />
          {activeTab === 'cards' ? (
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
          ) : activeTab === 'users' ? (
            <button
              type="button"
              className="auth-studio-add-btn"
              onClick={() => {
                setUserActionError(null);
                setUserActionSuccess(null);
                setIsAddUserOpen(true);
              }}
            >
              + Add Local User
            </button>
          ) : null}
        </div>
      </header>

      {/* Tabs Bar */}
      <div className="auth-tabs-bar" role="tablist" aria-label="Authentication Studio Sections">
        <button
          type="button"
          role="tab"
          id="tab-cards"
          aria-selected={activeTab === 'cards'}
          aria-controls="panel-cards"
          className={`auth-tab-btn ${activeTab === 'cards' ? 'auth-tab-btn--active' : ''}`}
          onClick={() => { setActiveTab('cards'); }}
        >
          Auth Provider Cards
        </button>
        <button
          type="button"
          role="tab"
          id="tab-users"
          aria-selected={activeTab === 'users'}
          aria-controls="panel-users"
          className={`auth-tab-btn ${activeTab === 'users' ? 'auth-tab-btn--active' : ''}`}
          onClick={() => { setActiveTab('users'); }}
        >
          Users &amp; Permissions
        </button>
        <button
          type="button"
          role="tab"
          id="tab-roles"
          data-testid="tab-roles"
          aria-selected={activeTab === 'roles'}
          aria-controls="panel-roles"
          className={`auth-tab-btn ${activeTab === 'roles' ? 'auth-tab-btn--active' : ''}`}
          onClick={() => { setActiveTab('roles'); }}
        >
          Roles &amp; Permissions
        </button>
      </div>

      {activeTab === 'users' && (
        <div className="auth-principal-filters" data-testid="principal-filters">
          {(['ALL', 'USER', 'GROUP', 'AGENT'] as const).map((kind) => (
            <button
              key={kind}
              type="button"
              className={`auth-btn-secondary ${principalKindFilter === kind ? 'auth-btn-primary' : ''}`}
              onClick={() => {
                setPrincipalKindFilter(kind);
                void loadUsers(kind === 'ALL' ? undefined : kind);
              }}
              data-testid={`filter-${kind.toLowerCase()}`}
            >
              {kind === 'ALL' ? 'All Principals' : kind === 'USER' ? 'Users' : kind === 'GROUP' ? 'Groups' : 'Agents'}
            </button>
          ))}
        </div>
      )}

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
            <ErrorHelpHint error={generalError} />
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

      {/* User Action Error or Success Banners */}
      {userActionError ? (
        <div className="auth-lockout-banner" role="alert">
          <div className="auth-lockout-header">
            <span>{userActionError}</span>
            <ErrorHelpHint error={userActionError} />
            <button
              type="button"
              className="auth-btn-secondary"
              onClick={() => { setUserActionError(null); }}
              aria-label="Dismiss error"
            >
              ×
            </button>
          </div>
        </div>
      ) : null}

      {userActionSuccess ? (
        <div className="auth-success-banner" role="status">
          <span>{userActionSuccess}</span>
          <button
            type="button"
            className="auth-btn-secondary"
            onClick={() => { setUserActionSuccess(null); }}
            aria-label="Dismiss notification"
          >
            ×
          </button>
        </div>
      ) : null}

      {/* Tab Panels */}
      {activeTab === 'cards' && (
        <div id="panel-cards" role="tabpanel" aria-labelledby="tab-cards">
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
        </div>
      )}

      {activeTab === 'users' && (
        <div id="panel-users" role="tabpanel" aria-labelledby="tab-users">
          {isLoadingUsers ? (
            <p className="auth-card-subtext">Loading users and permission grants...</p>
          ) : (
            <div className="auth-users-container">
              <table className="auth-users-table" data-testid="auth-users-table">
                <thead>
                  <tr>
                    <th className="auth-users-th">User / Handle</th>
                    <th className="auth-users-th">Email</th>
                    <th className="auth-users-th">Type</th>
                    <th className="auth-users-th">Provider</th>
                    <th className="auth-users-th">Role Grant</th>
                    <th className="auth-users-th">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="auth-users-td">
                        No user principals found.
                      </td>
                    </tr>
                  ) : (
                    users.map((u) => (
                      <tr key={u.id} className="auth-users-tr" data-testid={`auth-user-row-${u.id}`}>
                        <td className="auth-users-td" data-label="User / Handle">
                          <div className="auth-user-name-cell">
                            <span className="auth-user-display-name">
                              {u.display_name || (u.handle ?? u.principal)}
                            </span>
                            <span className="auth-user-handle">
                              {formatHandle(u.handle ?? u.principal, u.display_name, u.type)}
                            </span>
                          </div>
                        </td>
                        <td className="auth-users-td" data-label="Email">
                          <span className="auth-user-email">{u.email ?? '-'}</span>
                        </td>
                        <td className="auth-users-td" data-label="Type">
                          {(() => {
                            const rawType = (u.type ?? 'USER').toUpperCase();
                            const pillClass = rawType === 'GROUP' ? 'group' : rawType === 'AGENT' ? 'agent' : 'user';
                            const pillLabel = rawType === 'GROUP' ? 'Group' : rawType === 'AGENT' ? 'Agent' : 'User';
                            return (
                              <span className={`kb-type-pill kb-type-pill--${pillClass}`} data-testid={`type-pill-${u.id}`}>
                                {pillLabel}
                              </span>
                            );
                          })()}
                        </td>
                        <td className="auth-users-td" data-label="Provider">
                          <span
                            className={`auth-badge-provider ${getProviderBadgeClass(u.provider)}`}
                          >
                            {u.provider ?? 'LOCAL'}
                          </span>
                        </td>
                        <td className="auth-users-td" data-label="Role Grant">
                          <select
                            className="auth-role-select"
                            value={u.role ?? 'WORKSPACE_MEMBER'}
                            onChange={(e) => {
                              void handleRoleChange(u.id, e.target.value, u.role);
                            }}
                            aria-label={`Role for ${formatHandle(u.handle ?? u.principal, u.display_name, u.type)}`}
                          >
                            <option value="SERVER_ADMIN">SERVER_ADMIN (Server Admin)</option>
                            <option value="WORKSPACE_ADMIN">WORKSPACE_ADMIN (Workspace Admin)</option>
                            <option value="WORKSPACE_MEMBER">WORKSPACE_MEMBER (Workspace Member)</option>
                            <option value="WORKSPACE_GUEST">WORKSPACE_GUEST (Workspace Guest)</option>
                          </select>
                          <RoleLabelPicker principalId={u.id} />
                        </td>
                        <td className="auth-users-td" data-label="Actions">
                          {(() => {
                            const rawType = (
                              u.type ??
                              (u as unknown as { kind?: string }).kind ??
                              'USER'
                            ).toUpperCase();
                            const isUser = rawType === 'USER';
                            if (!isUser) {
                              return null;
                            }
                            return (
                              <button
                                type="button"
                                className="auth-btn-secondary"
                                onClick={() => {
                                  setUserActionError(null);
                                  setUserActionSuccess(null);
                                  setResetTargetUser(u);
                                  setNewPassword('');
                                  setConfirmPassword('');
                                }}
                              >
                                Reset Password
                              </button>
                            );
                          })()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'roles' && (
        <div id="panel-roles" role="tabpanel" aria-labelledby="tab-roles" data-testid="auth-roles-section">
          <RbacPolicyBuilder isServerAdmin={true} />
        </div>
      )}

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
        onTestHandshake={async (card, payload) => {
          if (card?.id) {
            return await testAuthCardHandshake(card.id);
          }
          return await testDraftAuthCardHandshake(payload);
        }}
      />

      {/* Break-Glass Anti-Lockout Warning Dialog */}
      {breakGlassTarget && (
        <div className="auth-modal-backdrop" role="presentation">
          <div
            className="auth-modal-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="break-glass-modal-title"
            data-testid="break-glass-warning-dialog"
          >
            <div className="auth-modal-header">
              <h2
                id="break-glass-modal-title"
                className="auth-modal-title"
                style={{ color: 'var(--text-danger, #dc2626)' }}
              >
                ⚠️ Break-Glass Anti-Lockout Warning
              </h2>
              <button
                type="button"
                className="auth-btn-secondary"
                onClick={() => { setBreakGlassTarget(null); }}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <div className="auth-modal-body">
              <p style={{ marginBottom: 12 }}>
                <strong>Warning:</strong> You are attempting to {breakGlassTarget.action === 'disable' ? 'disable' : 'delete'}{' '}
                <strong>{breakGlassTarget.card.display_name}</strong>.
              </p>
              <p style={{ marginBottom: 12 }}>
                This is the sole remaining active authentication card capable of authenticating a Server Administrator. At least one local administrator account or alternative active authentication card must remain configured to prevent lockout.
              </p>
              <div
                style={{
                  background: 'var(--bg-surface-raised, #f8fafc)',
                  border: '1px solid var(--border-subtle, #e2e8f0)',
                  borderRadius: 6,
                  padding: '10px 14px',
                  marginBottom: 16,
                }}
              >
                <p style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: 4 }}>
                  Three-Layer Anti-Lockout Safeguards:
                </p>
                <ol style={{ fontSize: '0.8rem', paddingLeft: 18, margin: 0, lineHeight: 1.5 }}>
                  <li>
                    <strong>Local Admin Card Invariant:</strong> Local Administrator card cannot be disabled without an active alternative provider with a verified login handshake within the past 15 minutes.
                  </li>
                  <li>
                    <strong>Active Administrator Principal Invariant:</strong> At least one active Server Administrator principal must remain bound.
                  </li>
                  <li>
                    <strong>Active Session Step-Up (AAL2):</strong> Elevated administrative operations enforce session keepalive and biometric/password re-auth.
                  </li>
                </ol>
              </div>
            </div>
            <div className="auth-modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                type="button"
                className="auth-btn-secondary"
                data-testid="cancel-break-glass-action"
                onClick={() => { setBreakGlassTarget(null); }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="auth-modal-btn-danger"
                data-testid="confirm-break-glass-action"
                onClick={() => {
                  const target = breakGlassTarget;
                  setBreakGlassTarget(null);
                  if (target.action === 'disable') {
                    void executeToggleEnabled(target.card, false);
                  } else {
                    void executeDeleteCard(target.card);
                  }
                }}
              >
                Confirm &amp; {breakGlassTarget.action === 'disable' ? 'Disable' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Local User Modal */}
      {isAddUserOpen ? (
        <div className="auth-modal-backdrop" role="presentation">
          <div
            className="auth-modal-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-user-modal-title"
          >
            <div className="auth-modal-header">
              <h2 id="add-user-modal-title" className="auth-modal-title">
                + Add Local User
              </h2>
              <button
                type="button"
                className="auth-btn-secondary"
                onClick={() => { setIsAddUserOpen(false); }}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <form onSubmit={(e) => { void handleCreateLocalUserSubmit(e); }}>
              <div className="auth-modal-body">
                <div className="auth-editor-field">
                  <label htmlFor="new-principal-type" className="auth-editor-label">
                    Principal Kind
                  </label>
                  <select
                    id="new-principal-type"
                    className="auth-editor-input"
                    value={newPrincipalType}
                    onChange={(e) => { setNewPrincipalType(e.target.value as 'USER' | 'GROUP' | 'AGENT'); }}
                  >
                    <option value="USER">User (Local)</option>
                    <option value="GROUP">Group</option>
                    <option value="AGENT">Agent</option>
                  </select>
                </div>

                <div className="auth-editor-field">
                  <label htmlFor="new-user-handle" className="auth-editor-label">
                    Username / Handle <span className="auth-editor-required">*</span>
                  </label>
                  <input
                    id="new-user-handle"
                    type="text"
                    className="auth-editor-input"
                    value={newUserHandle}
                    onChange={(e) => { setNewUserHandle(e.target.value); }}
                    placeholder="e.g. jdoe"
                    required
                  />
                </div>

                <div className="auth-editor-field">
                  <label htmlFor="new-user-display" className="auth-editor-label">
                    Display Name
                  </label>
                  <input
                    id="new-user-display"
                    type="text"
                    className="auth-editor-input"
                    value={newUserDisplayName}
                    onChange={(e) => { setNewUserDisplayName(e.target.value); }}
                    placeholder="e.g. John Doe"
                  />
                </div>

                {newPrincipalType === 'USER' && (
                  <>
                    <div className="auth-editor-field">
                      <label htmlFor="new-user-email" className="auth-editor-label">
                        Email Address <span className="auth-editor-required">*</span>
                      </label>
                      <input
                        id="new-user-email"
                        type="email"
                        className="auth-editor-input"
                        value={newUserEmail}
                        onChange={(e) => { setNewUserEmail(e.target.value); }}
                        placeholder="jdoe@example.com"
                        required
                      />
                    </div>

                    <div className="auth-editor-field">
                      <label htmlFor="new-user-pwd" className="auth-editor-label">
                        Password <span className="auth-editor-required">*</span>
                      </label>
                      <input
                        id="new-user-pwd"
                        type="password"
                        className="auth-editor-input"
                        value={newUserPassword}
                        onChange={(e) => { setNewUserPassword(e.target.value); }}
                        placeholder="Minimum 8 characters"
                        required
                        minLength={8}
                      />
                    </div>
                  </>
                )}

                <div className="auth-editor-field">
                  <label htmlFor="new-user-role" className="auth-editor-label">
                    Initial Role Grant
                  </label>
                  <select
                    id="new-user-role"
                    className="auth-editor-select"
                    value={newUserRole}
                    onChange={(e) => { setNewUserRole(e.target.value); }}
                  >
                    <option value="WORKSPACE_MEMBER">WORKSPACE_MEMBER (Workspace Member)</option>
                    <option value="WORKSPACE_ADMIN">WORKSPACE_ADMIN (Workspace Admin)</option>
                    <option value="SERVER_ADMIN">SERVER_ADMIN (Server Admin)</option>
                    <option value="WORKSPACE_GUEST">WORKSPACE_GUEST (Workspace Guest)</option>
                  </select>
                </div>
              </div>

              <div className="auth-modal-footer">
                <button
                  type="button"
                  className="auth-btn-secondary"
                  onClick={() => { setIsAddUserOpen(false); }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="auth-studio-add-btn"
                  disabled={isSubmittingUser}
                >
                  {isSubmittingUser ? 'Creating...' : 'Create User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {/* Reset Password Modal */}
      {resetTargetUser &&
      (
        resetTargetUser.type ??
        (resetTargetUser as unknown as { kind?: string }).kind ??
        'USER'
      ).toUpperCase() === 'USER' ? (
        <div className="auth-modal-backdrop" role="presentation">
          <div
            className="auth-modal-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-pwd-modal-title"
          >
            <div className="auth-modal-header">
              <h2 id="reset-pwd-modal-title" className="auth-modal-title">
                Reset Password: {formatHandle(resetTargetUser.handle ?? resetTargetUser.principal, resetTargetUser.display_name, resetTargetUser.type)}
              </h2>
              <button
                type="button"
                className="auth-btn-secondary"
                onClick={() => { setResetTargetUser(null); }}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <form onSubmit={(e) => { void handleResetPasswordSubmit(e); }}>
              <div className="auth-modal-body">
                <p className="auth-card-subtext">
                  Set a new password for{' '}
                  <strong>{resetTargetUser.display_name || formatHandle(resetTargetUser.handle ?? resetTargetUser.principal, resetTargetUser.display_name, resetTargetUser.type)}</strong> (
                  {resetTargetUser.email ?? formatHandle(resetTargetUser.handle ?? resetTargetUser.principal, resetTargetUser.display_name, resetTargetUser.type)}).
                </p>

                <div className="auth-editor-field">
                  <label htmlFor="reset-pwd-new" className="auth-editor-label">
                    New Password <span className="auth-editor-required">*</span>
                  </label>
                  <input
                    id="reset-pwd-new"
                    type="password"
                    className="auth-editor-input"
                    value={newPassword}
                    onChange={(e) => { setNewPassword(e.target.value); }}
                    placeholder="Minimum 8 characters"
                    required
                    minLength={8}
                  />
                </div>

                <div className="auth-editor-field">
                  <label htmlFor="reset-pwd-confirm" className="auth-editor-label">
                    Confirm New Password <span className="auth-editor-required">*</span>
                  </label>
                  <input
                    id="reset-pwd-confirm"
                    type="password"
                    className="auth-editor-input"
                    value={confirmPassword}
                    onChange={(e) => { setConfirmPassword(e.target.value); }}
                    placeholder="Re-enter password"
                    required
                    minLength={8}
                  />
                </div>
              </div>

              <div className="auth-modal-footer">
                <button
                  type="button"
                  className="auth-btn-secondary"
                  onClick={() => { setResetTargetUser(null); }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="auth-studio-add-btn"
                  disabled={isSubmittingPassword}
                >
                  {isSubmittingPassword ? 'Resetting...' : 'Update Password'}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}
