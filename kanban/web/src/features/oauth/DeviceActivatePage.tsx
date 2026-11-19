// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, type JSX, type ChangeEvent } from 'react';
import { useSearchParams } from 'react-router';
import {
  fetchDeviceCodeInfo,
  submitDeviceActivation,
  type DeviceCodeInfoResponse,
} from './oauthApi';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import './DeviceActivatePage.css';

const BASE20_CHARS = 'BCDFGHJKLMNPQRSTVWXZ';

export function formatUserCodeInput(raw: string): string {
  const cleaned = raw
    .toUpperCase()
    .split('')
    .filter((ch) => BASE20_CHARS.includes(ch))
    .join('');
  if (cleaned.length <= 4) {
    return cleaned;
  }
  return `${cleaned.slice(0, 4)}-${cleaned.slice(4, 8)}`;
}

export function DeviceActivatePage(): JSX.Element {
  const [searchParams] = useSearchParams();
  const [userCode, setUserCode] = useState<string>(() =>
    formatUserCodeInput(searchParams.get('user_code') ?? ''),
  );
  const [info, setInfo] = useState<DeviceCodeInfoResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [completionStatus, setCompletionStatus] = useState<'approved' | 'denied' | null>(null);
  const [selectedScopes, setSelectedScopes] = useState<string[]>([]);
  const [selectedProjects, setSelectedProjects] = useState<string[]>([]);
  const [invalidCharNotice, setInvalidCharNotice] = useState<string | null>(null);

  useEffect(() => {
    const codeParam = searchParams.get('user_code');
    if (!codeParam) {
      return;
    }
    const formatted = formatUserCodeInput(codeParam);
    if (formatted.length !== 9) {
      return;
    }

    const isMounted = { current: true };
    void (async () => {
      try {
        const data = await fetchDeviceCodeInfo(formatted);
        if (isMounted.current) {
          setInfo(data);
          setSelectedScopes(data.requested_scopes);
          setSelectedProjects(data.allowed_projects ?? ['KANBA']);
        }
      } catch (err: unknown) {
        if (isMounted.current) {
          const errObj = err as { code?: string; message?: string };
          if (errObj.code === 'RATE_LIMIT_EXCEEDED') {
            setErrorMessage('Too many attempts. Please wait 5 minutes before trying again.');
          } else if (errObj.code === 'EXPIRED_CODE') {
            setErrorMessage('This user code has expired. Please initiate device login again.');
          } else if (errObj.code === 'ALREADY_PROCESSED') {
            setErrorMessage('This device code has already been approved or denied.');
          } else {
            setErrorMessage(errObj.message ?? 'Invalid code or code not found.');
          }
          setInfo(null);
        }
      }
    })();

    return () => {
      isMounted.current = false;
    };
  }, [searchParams]);

  const handleLookup = async (codeToLookup: string): Promise<void> => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const data = await fetchDeviceCodeInfo(codeToLookup);
      setInfo(data);
      setSelectedScopes(data.requested_scopes);
      setSelectedProjects(data.allowed_projects ?? ['KANBA']);
    } catch (err: unknown) {
      const errObj = err as { code?: string; message?: string };
      if (errObj.code === 'RATE_LIMIT_EXCEEDED') {
        setErrorMessage('Too many attempts. Please wait 5 minutes before trying again.');
      } else if (errObj.code === 'EXPIRED_CODE') {
        setErrorMessage('This user code has expired. Please initiate device login again.');
      } else if (errObj.code === 'ALREADY_PROCESSED') {
        setErrorMessage('This device code has already been approved or denied.');
      } else {
        setErrorMessage(errObj.message ?? 'Invalid code or code not found.');
      }
      setInfo(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCodeChange = (e: ChangeEvent<HTMLInputElement>): void => {
    const raw = e.target.value;
    const hasVowelsOrDigits = /[AEIOU0-9]/i.test(raw);
    if (hasVowelsOrDigits) {
      setInvalidCharNotice(
        'Vowels (A, E, I, O, U) and numbers are not used in device codes. Only consonants are accepted.',
      );
    } else {
      setInvalidCharNotice(null);
    }
    const formatted = formatUserCodeInput(raw);
    setUserCode(formatted);
    setErrorMessage(null);
  };

  const handleDecision = async (approved: boolean): Promise<void> => {
    /* v8 ignore next 3 - unreachable defensive guard when no info is rendered */
    if (!info) {
      return;
    }
    setSubmitting(true);
    setErrorMessage(null);
    try {
      const res = await submitDeviceActivation({
        user_code: info.user_code,
        approved,
        scopes: approved ? selectedScopes : undefined,
        allowed_projects: approved ? selectedProjects : undefined,
      });
      setCompletionStatus(res.status);
    } catch (err: unknown) {
      const errObj = err as { code?: string; message?: string };
      if (errObj.code === 'AAL2_REQUIRED') {
        setErrorMessage(
          'AAL2 Passkey or TOTP verification required to approve /mcp/admin access.',
        );
      } else {
        setErrorMessage(errObj.message ?? 'An error occurred while processing approval.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const toggleScope = (scope: string): void => {
    setSelectedScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    );
  };

  const toggleProject = (project: string): void => {
    setSelectedProjects((prev) =>
      prev.includes(project) ? prev.filter((p) => p !== project) : [...prev, project],
    );
  };

  const isAdminTarget = info?.surface === 'admin' || (info?.resource ?? '').includes('/mcp/admin');

  return (
    <div className="kb-device-activate-layout" data-testid="device-activate-layout">
      <div className="kb-device-activate-card">
        <header className="kb-device-activate-header">
          <h1 className="kb-device-activate-title">Connect CLI Device</h1>
          <p className="kb-device-activate-subtitle">
            Approve headless CLI or bot access with explicit resource boundaries.
          </p>
        </header>

        {errorMessage && (
          <div className="kb-device-error-banner" role="alert" data-testid="error-banner">
            {errorMessage}
          </div>
        )}

        {completionStatus === 'approved' && (
          <div
            className="kb-device-status-box kb-device-status-success"
            data-testid="completion-approved"
          >
            <h2>Device Approved!</h2>
            <p>You may now return to your terminal or CLI tool.</p>
          </div>
        )}

        {completionStatus === 'denied' && (
          <div
            className="kb-device-status-box kb-device-status-denied"
            data-testid="completion-denied"
          >
            <h2>Device Request Denied</h2>
            <p>The authorization request was rejected. No tokens were issued.</p>
          </div>
        )}

        {!completionStatus && !info && (
          <div className="kb-device-input-group">
            <label htmlFor="user-code-input" className="kb-device-input-label">
              Enter 8-Character Device Code:
            </label>
            <input
              id="user-code-input"
              data-testid="user-code-input"
              type="text"
              className="kb-device-code-input"
              placeholder="XXXX-XXXX"
              maxLength={9}
              value={userCode}
              onChange={handleCodeChange}
              autoComplete="off"
              autoFocus
            />
            <p className="kb-device-helper-caption" data-testid="user-code-helper">
              Device codes consist of 8 consonants (BCDFGHJKLMNPQRSTVWXZ) in XXXX-XXXX format. Vowels and digits are excluded to avoid ambiguity.
            </p>
            {invalidCharNotice && (
              <div
                className="kb-device-input-notice"
                role="status"
                aria-live="polite"
                data-testid="user-code-input-notice"
              >
                {invalidCharNotice}
              </div>
            )}
            <button
              type="button"
              className="kb-device-lookup-button"
              data-testid="lookup-button"
              disabled={userCode.length < 9 || loading}
              onClick={() => {
                void handleLookup(userCode);
              }}
            >
              {loading ? 'Verifying...' : 'Continue'}
            </button>
          </div>
        )}

        {!completionStatus && info && (
          <section className="kb-device-consent-section" data-testid="consent-section">
            <div className="kb-device-app-info">
              <div className="kb-device-app-row">
                <span className="kb-device-app-prop-label">Client Name:</span>
                <span className="kb-device-app-prop-value" data-testid="client-name">
                  {info.client_name}
                </span>
              </div>
              <div className="kb-device-app-row">
                <span className="kb-device-app-prop-label">User Code:</span>
                <span className="kb-device-app-prop-value" data-testid="verified-code">
                  {info.user_code}
                </span>
              </div>
              <div className="kb-device-app-row">
                <span className="kb-device-app-prop-label">Target Resource:</span>
                <span className="kb-device-app-prop-value" data-testid="resource-target">
                  {info.resource}
                </span>
              </div>
              <div className="kb-device-app-row">
                <span className="kb-device-app-prop-label">Access Domain:</span>
                <span className="kb-device-app-prop-value">
                  <EmojiHint kind="access" /> {info.surface.toUpperCase()}
                </span>
              </div>
            </div>

            {isAdminTarget && (
              <div className="kb-device-aal2-banner" data-testid="aal2-banner">
                <EmojiHint kind="restricted" />
                <span>
                  Admin Surface: Approval requires active AAL2 multi-factor authentication.
                </span>
              </div>
            )}

            <div className="kb-device-scopes-group">
              <div className="kb-device-group-title">Requested Scopes:</div>
              {info.requested_scopes.map((scope) => (
                <label key={scope} className="kb-device-checkbox-label">
                  <input
                    type="checkbox"
                    checked={selectedScopes.includes(scope)}
                    onChange={() => {
                      toggleScope(scope);
                    }}
                    data-testid={`scope-checkbox-${scope}`}
                  />
                  <span>{scope}</span>
                </label>
              ))}
            </div>

            <div className="kb-device-projects-group">
              <div className="kb-device-group-title">Project Narrowing:</div>
              {['KANBA'].map((proj) => (
                <label key={proj} className="kb-device-checkbox-label">
                  <input
                    type="checkbox"
                    checked={selectedProjects.includes(proj)}
                    onChange={() => {
                      toggleProject(proj);
                    }}
                    data-testid={`project-checkbox-${proj}`}
                  />
                  <span>Project: {proj}</span>
                </label>
              ))}
            </div>

            <div className="kb-device-actions-row">
              <button
                type="button"
                className="kb-device-deny-button"
                data-testid="deny-button"
                disabled={submitting}
                onClick={() => {
                  void handleDecision(false);
                }}
              >
                Deny
              </button>
              <button
                type="button"
                className="kb-device-approve-button"
                data-testid="approve-button"
                disabled={submitting || selectedScopes.length === 0}
                onClick={() => {
                  void handleDecision(true);
                }}
              >
                {submitting ? 'Approving...' : 'Approve'}
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
