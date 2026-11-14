import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { AuthCardRow } from './AuthCardRow';
import type { AdminAuthCard } from './adminAuthApi';

describe('AuthCardRow (KB-P3-36)', () => {
  const oidcCard: AdminAuthCard = {
    id: 'c-oidc',
    provider_kind: 'OIDC',
    slug: 'okta',
    display_name: 'Okta SSO',
    button_subtext: 'Corporate Identity',
    icon_preset: 'shield',
    is_enabled: true,
    sort_rank: '1',
    auto_provision_users: true,
    allowed_email_domains: ['example.com'],
    has_secret: true,
    dek_kid: 'dek-1',
    last_health_status: 'HEALTHY',
    last_handshake_at: '2026-11-13T20:00:00Z',
    check_summary: 'OK',
    latency_ms: 42,
    public_config: { issuer_url: 'https://idp.example.com' },
  };

  const localAdminCard: AdminAuthCard = {
    id: 'c-local',
    provider_kind: 'LOCAL_ADMIN',
    slug: 'local-admin',
    display_name: 'Local Administrator',
    button_subtext: 'Break-glass access',
    icon_preset: 'lock',
    is_enabled: true,
    sort_rank: 'z',
    auto_provision_users: false,
    allowed_email_domains: [],
    has_secret: false,
    dek_kid: null,
    last_health_status: 'HEALTHY',
    last_handshake_at: null,
    check_summary: null,
    latency_ms: null,
    public_config: {},
  };

  const failedLdapCard: AdminAuthCard = {
    id: 'c-ldap',
    provider_kind: 'LDAP',
    slug: 'corp-ad',
    display_name: 'Corporate Active Directory',
    button_subtext: 'LDAPS directory',
    icon_preset: 'lock',
    is_enabled: true,
    sort_rank: '2',
    auto_provision_users: false,
    allowed_email_domains: [],
    has_secret: true,
    dek_kid: 'dek-2',
    last_health_status: 'FAILED',
    last_handshake_at: '2026-11-13T21:00:00Z',
    check_summary: 'Connection timeout to ldaps://dc01.corp:636',
    latency_ms: null,
    public_config: { server_url: 'ldaps://dc01.corp' },
  };

  it('renders card row with Primary badge, latency chip, and triggers edit/toggle', () => {
    const onToggle = vi.fn();
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const onHandshake = vi.fn();

    render(
      <AuthCardRow
        card={oidcCard}
        index={0}
        totalCards={3}
        isPrimary={true}
        onToggleEnabled={onToggle}
        onTestHandshake={onHandshake}
        onEdit={onEdit}
        onDelete={onDelete}
      />,
    );

    expect(screen.getByText('Okta SSO')).toBeDefined();
    expect(screen.getByText('Primary')).toBeDefined();
    expect(screen.getByText('HEALTHY (42 ms)')).toBeDefined();

    const toggle = screen.getByRole('switch', { name: /Enable Okta SSO/i });
    expect(toggle).toBeDefined();
    fireEvent.click(toggle);
    expect(onToggle).toHaveBeenCalledWith(oidcCard, false);

    const editBtn = screen.getByRole('button', { name: /^Edit$/i });
    fireEvent.click(editBtn);
    expect(onEdit).toHaveBeenCalledWith(oidcCard);

    const testBtn = screen.getByRole('button', { name: /Test handshake/i });
    fireEvent.click(testBtn);
    expect(onHandshake).toHaveBeenCalledWith(oidcCard);

    const deleteBtn = screen.getByRole('button', { name: /Delete Okta SSO/i });
    fireEvent.click(deleteBtn);
    expect(onDelete).toHaveBeenCalledWith(oidcCard);
  });

  it('pins LOCAL_ADMIN row: disables reorder and delete buttons', () => {
    const onMoveUp = vi.fn();
    const onMoveDown = vi.fn();

    render(
      <AuthCardRow
        card={localAdminCard}
        index={2}
        totalCards={3}
        onMoveUp={onMoveUp}
        onMoveDown={onMoveDown}
        onToggleEnabled={vi.fn()}
        onTestHandshake={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    const reorderBtns = screen.getAllByRole('button', {
      name: /Local Admin always appears in the break-glass disclosure/i,
    });
    expect(reorderBtns.length).toBe(2);
    expect(reorderBtns[0]?.hasAttribute('disabled')).toBe(true);
    expect(reorderBtns[1]?.hasAttribute('disabled')).toBe(true);

    const deleteBtn = screen.getByRole('button', {
      name: /Local Admin cannot be deleted/i,
    });
    expect(deleteBtn.hasAttribute('disabled')).toBe(true);

    // LOCAL_ADMIN does not render Test Handshake button
    expect(screen.queryByRole('button', { name: /Test handshake/i })).toBeNull();
  });

  it('renders FAILED health status with warning EmojiHint showing check summary', () => {
    const { rerender } = render(
      <AuthCardRow
        card={failedLdapCard}
        index={1}
        totalCards={3}
        onToggleEnabled={vi.fn()}
        onTestHandshake={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText('FAILED')).toBeDefined();
    const hint = screen.getByRole('button', { name: /Health check failure/i });
    expect(hint).toBeDefined();

    // Test fallback when check_summary and button_subtext are null/empty
    const failedNoSummary: AdminAuthCard = {
      ...failedLdapCard,
      button_subtext: null,
      check_summary: null,
      last_handshake_at: null,
    };
    rerender(
      <AuthCardRow
        card={failedNoSummary}
        index={1}
        totalCards={3}
        onToggleEnabled={vi.fn()}
        onTestHandshake={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText('FAILED')).toBeDefined();
  });

  it('supports keyboard reordering via Move Up and Move Down', () => {
    const onMoveUp = vi.fn();
    const onMoveDown = vi.fn();

    render(
      <AuthCardRow
        card={failedLdapCard}
        index={1}
        totalCards={4}
        onMoveUp={onMoveUp}
        onMoveDown={onMoveDown}
        onToggleEnabled={vi.fn()}
        onTestHandshake={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    const upBtn = screen.getByRole('button', {
      name: /Move Corporate Active Directory up/i,
    });
    fireEvent.click(upBtn);
    expect(onMoveUp).toHaveBeenCalledWith(failedLdapCard);

    const downBtn = screen.getByRole('button', {
      name: /Move Corporate Active Directory down/i,
    });
    fireEvent.click(downBtn);
    expect(onMoveDown).toHaveBeenCalledWith(failedLdapCard);
  });

  it('triggers drag and drop callbacks for non-pinned cards', () => {
    const onDragStart = vi.fn();
    const onDragOver = vi.fn();
    const onDrop = vi.fn();

    render(
      <AuthCardRow
        card={oidcCard}
        index={0}
        totalCards={3}
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDrop={onDrop}
        onToggleEnabled={vi.fn()}
        onTestHandshake={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    const row = screen.getByTestId('auth-card-row-okta');
    fireEvent.dragStart(row);
    expect(onDragStart).toHaveBeenCalledTimes(1);

    fireEvent.dragOver(row);
    expect(onDragOver).toHaveBeenCalledTimes(1);

    fireEvent.drop(row);
    expect(onDrop).toHaveBeenCalledTimes(1);
  });

  it('displays loading indicator and disabled state when testing handshake or toggling', () => {
    render(
      <AuthCardRow
        card={oidcCard}
        index={0}
        totalCards={3}
        isTestingHandshake={true}
        isToggling={true}
        onToggleEnabled={vi.fn()}
        onTestHandshake={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText('Testing...')).toBeDefined();
    const testBtn = screen.getByRole('button', { name: /Testing.../i });
    expect(testBtn.hasAttribute('disabled')).toBe(true);

    const toggle = screen.getByRole('switch', { name: /Enable Okta SSO/i });
    expect(toggle.hasAttribute('disabled')).toBe(true);
  });

  it('renders UNVERIFIED and HEALTHY without latency chips correctly', () => {
    const unverifiedCard: AdminAuthCard = {
      ...oidcCard,
      last_health_status: 'UNVERIFIED',
      latency_ms: null,
      icon_preset: 'custom',
    };

    const { rerender } = render(
      <AuthCardRow
        card={unverifiedCard}
        index={0}
        totalCards={3}
        onToggleEnabled={vi.fn()}
        onTestHandshake={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText('UNVERIFIED')).toBeDefined();

    const healthyNoLatencyCard: AdminAuthCard = {
      ...oidcCard,
      last_health_status: 'HEALTHY',
      latency_ms: null,
    };

    rerender(
      <AuthCardRow
        card={healthyNoLatencyCard}
        index={0}
        totalCards={3}
        onToggleEnabled={vi.fn()}
        onTestHandshake={vi.fn()}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText('HEALTHY')).toBeDefined();
  });
});
