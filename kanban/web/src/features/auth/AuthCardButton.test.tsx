import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { AuthCardButton } from './AuthCardButton';
import type { AuthCard } from './authApi';

describe('AuthCardButton (KB-P3-35)', () => {
  const oidcCard: AuthCard = {
    id: 'card-1',
    slug: 'okta-workforce',
    provider_kind: 'OIDC',
    display_name: 'Okta SSO',
    button_subtext: 'Single Sign-on for workforce',
    icon_preset: 'building',
  };

  const ldapCard: AuthCard = {
    id: 'card-2',
    slug: 'corp-ad',
    provider_kind: 'LDAP',
    display_name: 'Corp Active Directory',
    button_subtext: 'LDAP login',
    icon_preset: 'lock',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders OIDC card with Primary badge and triggers window.location.assign on click', () => {
    const assignMock = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { assign: assignMock },
    });

    render(<AuthCardButton card={oidcCard} isPrimary={true} next="/projects/KAN/issues" />);

    expect(screen.getByText('Okta SSO')).toBeDefined();
    expect(screen.getByText('Single Sign-on for workforce')).toBeDefined();
    expect(screen.getByText('Primary')).toBeDefined();
    expect(screen.getByLabelText('Continue with Okta SSO')).toBeDefined();

    const btn = screen.getByRole('button', { name: /Continue with Okta SSO/i });
    fireEvent.click(btn);

    expect(assignMock).toHaveBeenCalledWith(
      '/api/v1/auth/cards/okta-workforce/start?next=%2Fprojects%2FKAN%2Fissues',
    );
  });

  it('renders LDAP card without Primary badge and triggers onToggleLdap on click', () => {
    const toggleSpy = vi.fn();
    render(
      <AuthCardButton
        card={ldapCard}
        isPrimary={false}
        isLdapExpanded={false}
        onToggleLdap={toggleSpy}
        formId="test-ldap-form"
      />,
    );

    expect(screen.queryByText('Primary')).toBeNull();
    const btn = screen.getByRole('button', { name: /Sign in with Corp Active Directory/i });
    expect(btn.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(btn);
    expect(toggleSpy).toHaveBeenCalledTimes(1);

    // Re-render with isLdapExpanded=true
    const { unmount } = render(
      <AuthCardButton
        card={ldapCard}
        isPrimary={false}
        isLdapExpanded={true}
        onToggleLdap={toggleSpy}
        formId="test-ldap-form"
      />,
    );
    expect(screen.getByText('▾')).toBeDefined();
    unmount();
  });

  it('renders hostile cards with safe text escaping, clamped characters, and icon fallback (Mandatory Test Case 2)', () => {
    const hostileCard: AuthCard = {
      id: 'card-hostile',
      slug: 'hostile-xss',
      provider_kind: 'OIDC',
      display_name: '<img src=x onerror=alert(1)>',
      button_subtext: '<script>alert(1)</script>',
      icon_preset: 'javascript:alert(1)',
    };

    const { container } = render(<AuthCardButton card={hostileCard} />);

    // Renders literal text
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeDefined();
    expect(screen.getByText('<script>alert(1)</script>')).toBeDefined();

    // Zero <img> or <script> elements created in DOM
    expect(container.querySelectorAll('img').length).toBe(0);
    expect(container.querySelectorAll('script').length).toBe(0);

    // Hostile icon preset falls back to 🔑
    expect(screen.getByText('🔑')).toBeDefined();
  });

  it('clamps 200-char name to 80 chars + ... with full value in title (Mandatory Test Case 2)', () => {
    const longName = 'A'.repeat(200);
    const longSubtext = 'B'.repeat(150);

    const longCard: AuthCard = {
      id: 'card-long',
      slug: 'long-card',
      provider_kind: 'OAUTH2',
      display_name: longName,
      button_subtext: longSubtext,
      icon_preset: 'github',
    };

    render(<AuthCardButton card={longCard} />);

    const clampedDisplayName = 'A'.repeat(80) + '...';
    const clampedSubtext = 'B'.repeat(120) + '...';

    const nameElem = screen.getByText(clampedDisplayName);
    expect(nameElem).toBeDefined();
    expect(nameElem.getAttribute('title')).toBe(longName);

    const subElem = screen.getByText(clampedSubtext);
    expect(subElem).toBeDefined();
    expect(subElem.getAttribute('title')).toBe(longSubtext);

    // Correct icon for github
    expect(screen.getByText('🐙')).toBeDefined();
  });

  it('handles card without button_subtext and uses window.location.assign', () => {
    const assignMock = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { assign: assignMock },
    });

    const noSubtextCard: AuthCard = {
      id: 'card-no-sub',
      slug: 'no-sub',
      provider_kind: 'OIDC',
      display_name: 'No Subtext Provider',
      button_subtext: null,
      icon_preset: 'key',
    };

    render(
      <AuthCardButton
        card={noSubtextCard}
        next="/custom-next"
      />,
    );

    const btn = screen.getByRole('button', { name: /Continue with No Subtext Provider/i });
    fireEvent.click(btn);
    expect(assignMock).toHaveBeenCalledWith(
      '/api/v1/auth/cards/no-sub/start?next=%2Fcustom-next',
    );
  });
});
