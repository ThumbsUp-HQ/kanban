/**
 * Standalone Status Panel (KB-P3-52, S2.2, S2.4, S6.2).
 * Displays live volume persistence status, sandbox availability, encrypted backup trigger,
 * and 1-click production docker-compose.yml export.
 */

import React, {
  useEffect,
  useRef,
  useState,
  type JSX,
  type SyntheticEvent,
} from 'react';
import { useSystemStatus, type SystemStatus } from '../../app/useSystemStatus';
import { getCsrfToken } from '../../editor/sparkle/sparkleClient';
import { ComposeExportTab } from './ComposeExportTab';
import './StandaloneStatusPanel.css';

export interface StandaloneStatusPanelProps {
  readonly onClose: () => void;
  readonly arg?: unknown;
  readonly initialStatus?: SystemStatus | null;
}

export function StandaloneStatusPanel({
  onClose,
  initialStatus = null,
}: StandaloneStatusPanelProps): JSX.Element {
  const query = useSystemStatus();
  const status = initialStatus ?? query.data ?? null;

  const [copiedDockerRun, setCopiedDockerRun] = useState<boolean>(false);
  const [passphrase, setPassphrase] = useState<string>('');
  const [passphraseError, setPassphraseError] = useState<string>('');
  const [isBackingUp, setIsBackingUp] = useState<boolean>(false);
  const [backupError, setBackupError] = useState<string | null>(null);

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLElement | null>(
    typeof document !== 'undefined'
      ? (document.activeElement as HTMLElement | null)
      : null,
  );

  const isServerAdmin = Boolean(status?.is_server_admin);
  const isPersistent = Boolean(status?.persistent_volume);
  const tierBSandbox = status?.tier_b_sandbox_available ?? true;

  // Restore focus to trigger on unmount
  useEffect(() => {
    const trigger = triggerRef.current;
    return () => {
      if (trigger && typeof trigger.focus === 'function') {
        trigger.focus();
      } else {
        const warningPill = document.querySelector<HTMLElement>(
          '[aria-label*="Standalone"]',
        );
        warningPill?.focus();
      }
    };
  }, []);

  // Trap focus and handle Escape
  useEffect(() => {
    const dialogEl = dialogRef.current;
    if (!dialogEl) return;

    // Focus close button on mount
    const firstFocusable = dialogEl.querySelector<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    firstFocusable?.focus();

    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key === 'Tab') {
        const focusables = dialogEl.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length <= 1) return;

        const first = focusables[0];
        const last = focusables[focusables.length - 1];

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  const handleCopyDockerRun = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(
        'docker run -d -p 8080:8080 -v kanban_data:/var/lib/kanban/data kanban:latest',
      );
      setCopiedDockerRun(true);
      setTimeout(() => {
        setCopiedDockerRun(false);
      }, 2000);
    } catch {
      // Fallback
    }
  };

  const handleBackupSubmit = async (e: SyntheticEvent): Promise<void> => {
    e.preventDefault();
    if (passphrase.length < 16) {
      setPassphraseError('Passphrase must be at least 16 characters');
      return;
    }

    setPassphraseError('');
    setBackupError(null);
    setIsBackingUp(true);

    try {
      const csrf = getCsrfToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'application/octet-stream',
      };
      if (csrf) {
        headers['X-CSRF-Token'] = csrf;
      }

      const res = await fetch('/api/v1/admin/standalone/backup', {
        method: 'POST',
        headers,
        credentials: 'same-origin',
        body: JSON.stringify({ passphrase }),
      });

      if (!res.ok) {
        const errJson = (await res.json().catch(() => ({}))) as {
          detail?: string | { detail?: string };
        };
        const detail = errJson.detail;
        const msg =
          typeof detail === 'string'
            ? detail
            : typeof detail === 'object' && 'detail' in detail && typeof detail.detail === 'string'
              ? detail.detail
              : `Backup failed with status ${String(res.status)}`;
        throw new Error(msg);
      }

      const disposition = res.headers.get('content-disposition') ?? '';
      let filename = 'kanban-backup.kbkp';
      const match = /filename=["']?([^"';]+)["']?/.exec(disposition);
      if (match?.[1]) {
        filename = match[1];
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      setPassphrase('');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Backup export failed';
      setBackupError(msg);
    } finally {
      setIsBackingUp(false);
    }
  };

  return (
    <>
      <div
        className="standalone-panel__backdrop"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Standalone deployment status"
        className="standalone-panel"
      >
        {/* Header */}
        <div className="standalone-panel__header">
          <h2 className="standalone-panel__title">Standalone deployment status</h2>
          <button
            type="button"
            className="standalone-panel__close"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        {/* Section 1: Storage & Sandbox Health */}
        <div className="standalone-panel__section">
          {!isPersistent ? (
            <div className="standalone-panel__warn-banner" role="alert">
              <div className="standalone-panel__warn-text">
                Ephemeral Storage Detected (overlayfs): Mount -v kanban_data:/var/lib/kanban/data to persist data across container removal
              </div>
              <div className="standalone-panel__code-block">
                <code>
                  docker run -d -p 8080:8080 -v kanban_data:/var/lib/kanban/data kanban:latest
                </code>
                <button
                  type="button"
                  className="standalone-panel__copy-btn"
                  onClick={() => {
                    void handleCopyDockerRun();
                  }}
                >
                  {copiedDockerRun ? 'Copied!' : 'Copy docker run command'}
                </button>
              </div>
            </div>
          ) : (
            <div className="standalone-panel__persistent-badge">
              <span className="standalone-panel__badge-icon" aria-hidden="true">
                ✓
              </span>
              <span className="standalone-panel__badge-title">
                Persistent Volume Mounted
              </span>
              <span className="standalone-panel__badge-detail">
                {isServerAdmin && status?.data_mount_point
                  ? `${status.data_mount_point} (${status.data_mount_fstype ?? 'ext4'})`
                  : 'Persistent volume verified'}
              </span>
            </div>
          )}

          <div className="standalone-panel__sandbox-row">
            <span className="standalone-panel__sandbox-item">
              Tier A Wasmtime: Active
            </span>
            <span className="standalone-panel__sandbox-item">
              {tierBSandbox
                ? 'Tier B nsjail CLI Sandbox: Active'
                : 'Tier B nsjail CLI Sandbox: Disabled in Standalone (SANDBOX_UNAVAILABLE_IN_STANDALONE)'}
            </span>
          </div>
        </div>

        {/* Section 2: Encrypted Database Backup */}
        {isServerAdmin ? (
          <div className="standalone-panel__section">
            <h3 className="standalone-panel__section-title">
              Encrypted Database Backup
            </h3>
            <form
              onSubmit={(e) => {
                void handleBackupSubmit(e);
              }}
              className="standalone-panel__backup-form"
            >
              <label
                htmlFor="backup-passphrase"
                className="standalone-panel__label"
              >
                Backup Passphrase
              </label>
              <input
                id="backup-passphrase"
                type="password"
                autoComplete="new-password"
                minLength={16}
                value={passphrase}
                onChange={(e) => {
                  setPassphrase(e.target.value);
                  if (passphraseError && e.target.value.length >= 16) {
                    setPassphraseError('');
                  }
                }}
                className="standalone-panel__input"
                placeholder="Enter passphrase (min 16 characters)"
              />
              <div className="standalone-panel__hint">
                Minimum 16 characters; never stored on server
              </div>

              {passphraseError && (
                <div role="alert" className="standalone-panel__error">
                  {passphraseError}
                </div>
              )}

              {backupError && (
                <div role="alert" className="standalone-panel__error">
                  {backupError}
                </div>
              )}

              <button
                type="submit"
                className="standalone-panel__btn standalone-panel__btn--primary"
                disabled={isBackingUp || passphrase.length < 16}
              >
                {isBackingUp
                  ? 'Exporting Backup...'
                  : 'Download Encrypted Backup (.kbkp)'}
              </button>
            </form>
          </div>
        ) : (
          <div className="standalone-panel__section">
            <p className="standalone-panel__member-notice">
              Contact a Server Administrator to export backups or promote this instance.
            </p>
          </div>
        )}

        {/* Section 3: Compose Export (SERVER_ADMIN only) */}
        {isServerAdmin && (
          <div className="standalone-panel__section">
            <h3 className="standalone-panel__section-title">
              Production Compose Export & Promotion
            </h3>
            <ComposeExportTab />
          </div>
        )}
      </div>
    </>
  );
}
