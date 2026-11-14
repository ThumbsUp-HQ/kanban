import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { LocalAdminDisclosure } from './LocalAdminDisclosure';
import * as authApi from './authApi';
import type { AuthLoginResponse } from './authApi';
import { ApiProblem } from '../../api/problem';

describe('LocalAdminDisclosure (KB-P3-35)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('toggles aria-expanded and renders form inputs on click (Mandatory Test Case 9)', () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();

    render(<LocalAdminDisclosure onSuccess={onSuccess} onError={onError} />);

    const trigger = screen.getByRole('button', {
      name: /Sign in with Local Admin \+ Passkey \/ TOTP/i,
    });
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByLabelText(/Local Administrator Username/i)).toBeNull();

    // Expand disclosure
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByLabelText(/Local Administrator Username/i)).toBeDefined();
    expect(screen.getByLabelText(/Password/i)).toBeDefined();

    // Collapse disclosure on second click
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByLabelText(/Local Administrator Username/i)).toBeNull();
  });

  it('collapses on Escape key and returns focus to the trigger (Mandatory Test Case 9)', () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();

    render(<LocalAdminDisclosure onSuccess={onSuccess} onError={onError} />);

    const trigger = screen.getByRole('button', {
      name: /Sign in with Local Admin \+ Passkey \/ TOTP/i,
    });
    fireEvent.click(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');

    // Press non-Escape key inside the form panel
    const userInput = screen.getByLabelText(/Local Administrator Username/i);
    fireEvent.keyDown(userInput, { key: 'Tab' });
    expect(trigger.getAttribute('aria-expanded')).toBe('true');

    // Press Escape inside the form panel
    fireEvent.keyDown(userInput, { key: 'Escape' });

    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(trigger);
  });

  it('volatile secret: clears password input and state after failed submit (Mandatory Test Case 4)', async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();

    vi.spyOn(authApi, 'submitLocalAdminLogin').mockRejectedValueOnce(
      new ApiProblem(401, { code: 'INVALID_CREDENTIALS', detail: 'Invalid password' }),
    );

    render(<LocalAdminDisclosure onSuccess={onSuccess} onError={onError} />);

    const trigger = screen.getByRole('button', {
      name: /Sign in with Local Admin \+ Passkey \/ TOTP/i,
    });
    fireEvent.click(trigger);

    const userInput = screen.getByLabelText<HTMLInputElement>(/Local Administrator Username/i);
    const pwdInput = screen.getByLabelText<HTMLInputElement>(/Password/i);

    fireEvent.change(userInput, { target: { value: 'admin' } });
    fireEvent.change(pwdInput, { target: { value: 'SuperSecret1234!' } });
    expect(pwdInput.value).toBe('SuperSecret1234!');

    const submitBtn = screen.getByRole('button', { name: /Sign in as Local Administrator/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(onError).toHaveBeenCalledTimes(1);
    });

    // Password input value MUST be cleared to ''
    expect(pwdInput.value).toBe('');
  });

  it('calls onSuccess when local admin credentials succeed', async () => {
    const onSuccess = vi.fn();
    const onError = vi.fn();

    vi.spyOn(authApi, 'submitLocalAdminLogin').mockResolvedValueOnce({
      status: 'mfa_required',
      challenge_id: 'chall-123',
      methods: ['webauthn', 'totp'],
    });

    render(<LocalAdminDisclosure onSuccess={onSuccess} onError={onError} />);

    fireEvent.click(
      screen.getByRole('button', { name: /Sign in with Local Admin \+ Passkey \/ TOTP/i }),
    );

    fireEvent.change(screen.getByLabelText(/Local Administrator Username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'ValidPass12345!' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Sign in as Local Administrator/i }));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith({
        status: 'mfa_required',
        challenge_id: 'chall-123',
        methods: ['webauthn', 'totp'],
      });
    });
  });

  it('prevents double submission when already submitting', () => {
    let resolveLogin: ((val: AuthLoginResponse) => void) | undefined;
    const loginPromise = new Promise<AuthLoginResponse>((resolve) => {
      resolveLogin = resolve;
    });

    const submitSpy = vi.spyOn(authApi, 'submitLocalAdminLogin').mockReturnValue(loginPromise);

    render(<LocalAdminDisclosure onSuccess={vi.fn()} onError={vi.fn()} />);

    fireEvent.click(
      screen.getByRole('button', { name: /Sign in with Local Admin \+ Passkey \/ TOTP/i }),
    );

    fireEvent.change(screen.getByLabelText(/Local Administrator Username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'ValidPass12345!' },
    });

    const form = screen.getByRole('button', { name: /Sign in as Local Administrator/i }).closest('form');
    expect(form).not.toBeNull();
    if (form) {
      fireEvent.submit(form);
      expect(submitSpy).toHaveBeenCalledTimes(1);

      fireEvent.submit(form);
      expect(submitSpy).toHaveBeenCalledTimes(1);
    }

    resolveLogin?.({ status: 'authenticated' });
  });

  it('handles finally block when unmounted during submission', () => {
    let resolveLogin: ((val: AuthLoginResponse) => void) | undefined;
    vi.spyOn(authApi, 'submitLocalAdminLogin').mockReturnValue(
      new Promise<AuthLoginResponse>((resolve) => {
        resolveLogin = resolve;
      }),
    );

    const { unmount } = render(<LocalAdminDisclosure onSuccess={vi.fn()} onError={vi.fn()} />);

    fireEvent.click(
      screen.getByRole('button', { name: /Sign in with Local Admin \+ Passkey \/ TOTP/i }),
    );

    fireEvent.change(screen.getByLabelText(/Local Administrator Username/i), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'pwd' },
    });

    const form = screen.getByRole('button', { name: /Sign in as Local Administrator/i }).closest('form');
    expect(form).not.toBeNull();
    if (form) {
      fireEvent.submit(form);
    }
    unmount();
    resolveLogin?.({ status: 'authenticated' });
  });
});
