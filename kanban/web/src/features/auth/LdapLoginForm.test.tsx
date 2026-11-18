import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { LdapLoginForm } from './LdapLoginForm';
import * as authApi from './authApi';
import type { AuthCard, AuthLoginResponse } from './authApi';
import { ApiProblem } from '../../api/problem';

describe('LdapLoginForm (KB-P3-35)', () => {
  const ldapCard: AuthCard = {
    id: 'c-ldap',
    slug: 'corp-ad',
    provider_kind: 'LDAP',
    display_name: 'Corp AD',
    button_subtext: 'Domain login',
    icon_preset: 'lock',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('submits username and password, invokes onSuccess, and cleans up password memory (Mandatory Test Case 4)', async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onCollapse = vi.fn();

    const submitSpy = vi.spyOn(authApi, 'submitLdapLogin').mockResolvedValueOnce({
      status: 'authenticated',
    });

    render(
      <LdapLoginForm
        card={ldapCard}
        formId="test-ldap-form"
        onSuccess={onSuccess}
        onError={onError}
        onCollapse={onCollapse}
      />,
    );

    const userInput = screen.getByLabelText<HTMLInputElement>(/Username/i);
    const pwdInput = screen.getByLabelText<HTMLInputElement>(/Password/i);

    fireEvent.change(userInput, { target: { value: 'alice' } });
    fireEvent.change(pwdInput, { target: { value: 'SecretPass123!' } });
    expect(pwdInput.value).toBe('SecretPass123!');

    const submitBtn = screen.getByRole('button', { name: /Sign in to Corp AD/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(submitSpy).toHaveBeenCalledWith('corp-ad', {
        username: 'alice',
        password: 'SecretPass123!',
        remember_me: true,
      });
      expect(onSuccess).toHaveBeenCalledWith({ status: 'authenticated' });
    });

    // Password input value MUST be cleared to ''
    expect(pwdInput.value).toBe('');
  });

  it('handles LDAP login failure and clears password value', async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onCollapse = vi.fn();

    vi.spyOn(authApi, 'submitLdapLogin').mockRejectedValueOnce(
      new ApiProblem(401, { code: 'INVALID_CREDENTIALS', detail: 'Invalid LDAP credentials' }),
    );

    render(
      <LdapLoginForm
        card={ldapCard}
        formId="test-ldap-form"
        onSuccess={onSuccess}
        onError={onError}
        onCollapse={onCollapse}
      />,
    );

    const userInput = screen.getByLabelText(/Username/i);
    const pwdInput = screen.getByLabelText<HTMLInputElement>(/Password/i);

    fireEvent.change(userInput, { target: { value: 'bob' } });
    fireEvent.change(pwdInput, { target: { value: 'BadPassword123!' } });

    fireEvent.click(screen.getByRole('button', { name: /Sign in to Corp AD/i }));

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Sign-in failed. Check your credentials and try again.',
          code: 'INVALID_CREDENTIALS',
        }),
      );
    });

    expect(pwdInput.value).toBe('');
  });

  it('collapses on Escape key press (Mandatory Test Case 9)', () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onCollapse = vi.fn();

    render(
      <LdapLoginForm
        card={ldapCard}
        formId="test-ldap-form"
        onSuccess={onSuccess}
        onError={onError}
        onCollapse={onCollapse}
      />,
    );

    const userInput = screen.getByLabelText(/Username/i);
    fireEvent.keyDown(userInput, { key: 'Tab' });
    expect(onCollapse).not.toHaveBeenCalled();

    fireEvent.keyDown(userInput, { key: 'Escape' });
    expect(onCollapse).toHaveBeenCalledTimes(1);
  });

  it('early returns when submit is triggered while already submitting', () => {
    let resolveLogin: ((val: AuthLoginResponse) => void) | undefined;
    const loginPromise = new Promise<AuthLoginResponse>((resolve) => {
      resolveLogin = resolve;
    });

    const submitSpy = vi.spyOn(authApi, 'submitLdapLogin').mockReturnValue(loginPromise);

    render(
      <LdapLoginForm
        card={ldapCard}
        formId="test-ldap-form"
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onCollapse={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'pwd' } });

    const form = screen.getByRole('button', { name: /Sign in to Corp AD/i }).closest('form');
    expect(form).not.toBeNull();
    if (form) {
      // Submit first time
      fireEvent.submit(form);
      expect(submitSpy).toHaveBeenCalledTimes(1);

      // Submit second time while isSubmitting is true
      fireEvent.submit(form);
      expect(submitSpy).toHaveBeenCalledTimes(1);
    }

    resolveLogin?.({ status: 'authenticated' });
  });

  it('handles finally block when unmounted during submission', () => {
    let resolveLogin: ((val: AuthLoginResponse) => void) | undefined;
    vi.spyOn(authApi, 'submitLdapLogin').mockReturnValue(
      new Promise<AuthLoginResponse>((resolve) => {
        resolveLogin = resolve;
      }),
    );

    const { unmount } = render(
      <LdapLoginForm
        card={ldapCard}
        formId="test-ldap-form"
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onCollapse={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: 'alice' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'pwd' } });

    const form = screen.getByRole('button', { name: /Sign in to Corp AD/i }).closest('form');
    expect(form).not.toBeNull();
    if (form) {
      fireEvent.submit(form);
    }
    unmount();
    resolveLogin?.({ status: 'authenticated' });
  });

  it('toggles password visibility between text and password', () => {
    render(
      <LdapLoginForm
        card={ldapCard}
        formId="test-ldap-form"
        onSuccess={vi.fn()}
        onError={vi.fn()}
        onCollapse={vi.fn()}
      />,
    );
    const pwdInput = screen.getByLabelText<HTMLInputElement>(/Password/i);
    expect(pwdInput.type).toBe('password');
    const toggleBtn = screen.getByRole('button', { name: /Show/i });
    fireEvent.click(toggleBtn);
    expect(pwdInput.type).toBe('text');
    fireEvent.click(screen.getByRole('button', { name: /Hide/i }));
    expect(pwdInput.type).toBe('password');
  });
});
