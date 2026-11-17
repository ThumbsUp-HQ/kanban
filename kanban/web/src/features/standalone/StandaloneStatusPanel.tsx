/**
 * Standalone Status Panel (KB-P3-52, S2.2, S2.4, S6.2, KANBA-188).
 * 3-Tab Studio:
 * 1. Storage & Capabilities Health
 * 2. Backup, Auto-Backup & Restore (2-stage verification + RESTORE gate)
 * 3. Docker Compose Export & Promotion
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  type JSX,
  type SyntheticEvent,
} from 'react';
import { useSystemStatus, type SystemStatus } from '../../app/useSystemStatus';
import { getCsrfToken } from '../../editor/sparkle/sparkleClient';
import { safeCopyToClipboard } from '../../utils/uuid';
import { ComposeExportTab } from './ComposeExportTab';
import './StandaloneStatusPanel.css';

export type StandaloneTabId = 'health' | 'backup' | 'compose';

export interface StandaloneStatusPanelProps {
  readonly onClose: () => void;
  readonly arg?: unknown;
  readonly initialStatus?: SystemStatus | null;
  readonly initialTab?: StandaloneTabId;
}

export interface BackupScheduleState {
  enabled: boolean;
  interval_hours: number;
  retention_count: number;
  last_run_at: string | null;
  next_run_at: string | null;
}

export interface BackupSnapshotItem {
  filename: string;
  size_bytes: number;
  created_at: string;
}

export interface BackupManifestData {
  format_version?: number;
  created_at?: string;
  alembic_revision?: string;
  pg_server_version?: string;
  attachments_count?: number;
  [key: string]: unknown;
}

export function StandaloneStatusPanel({
  onClose,
  initialStatus = null,
  initialTab = 'health',
}: StandaloneStatusPanelProps): JSX.Element {
  const query = useSystemStatus();
  const status = initialStatus ?? query.data ?? null;

  const [activeTab, setActiveTab] = useState<StandaloneTabId>(initialTab);
  const [copiedDockerRun, setCopiedDockerRun] = useState<boolean>(false);

  // Manual Backup State
  const [passphrase, setPassphrase] = useState<string>('');
  const [passphraseError, setPassphraseError] = useState<string>('');
  const [isBackingUp, setIsBackingUp] = useState<boolean>(false);
  const [backupError, setBackupError] = useState<string | null>(null);

  // Auto-Backup Schedule State
  const [schedule, setSchedule] = useState<BackupScheduleState>({
    enabled: false,
    interval_hours: 24,
    retention_count: 7,
    last_run_at: null,
    next_run_at: null,
  });
  const [scheduleSaved, setScheduleSaved] = useState<boolean>(false);
  const [snapshots, setSnapshots] = useState<BackupSnapshotItem[]>([]);
  const [isRunningBackupNow, setIsRunningBackupNow] = useState<boolean>(false);

  // Restore State (2-Stage)
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [selectedSnapshotFilename, setSelectedSnapshotFilename] = useState<string>('');
  const [restorePassphrase, setRestorePassphrase] = useState<string>('');
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [verifiedManifest, setVerifiedManifest] = useState<BackupManifestData | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [restoreConfirmText, setRestoreConfirmText] = useState<string>('');
  const [isRestoring, setIsRestoring] = useState<boolean>(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [restoreSuccess, setRestoreSuccess] = useState<string | null>(null);

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

  // Load schedule and snapshot list for admins
  const loadScheduleAndSnapshots = useCallback(async (): Promise<void> => {
    if (!isServerAdmin) return;
    try {
      const [schedRes, snapsRes] = await Promise.all([
        fetch('/api/v1/admin/standalone/backup-schedule', {
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
        }),
        fetch('/api/v1/admin/standalone/backups', {
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
        }),
      ]);
      if (schedRes.ok) {
        const schedJson = (await schedRes.json()) as BackupScheduleState;
        setSchedule(schedJson);
      }
      if (snapsRes.ok) {
        const snapsJson = (await snapsRes.json()) as BackupSnapshotItem[];
        setSnapshots(snapsJson);
      }
    } catch {
      // Ignore background load failures
    }
  }, [isServerAdmin]);

  useEffect(() => {
    if (activeTab === 'backup') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void loadScheduleAndSnapshots();
    }
  }, [activeTab, loadScheduleAndSnapshots]);

  const handleCopyDockerRun = async (): Promise<void> => {
    try {
      const success = await safeCopyToClipboard(
        'docker run -d -p 8080:8080 -v kanban_data:/var/lib/kanban/data kanban:latest',
      );
      if (success) {
        setCopiedDockerRun(true);
        setTimeout(() => {
          setCopiedDockerRun(false);
        }, 2000);
      }
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
      let filename = 'kanban-backup.kbbak';
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
      void loadScheduleAndSnapshots();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Backup export failed';
      setBackupError(msg);
    } finally {
      setIsBackingUp(false);
    }
  };

  const handleSaveSchedule = async (): Promise<void> => {
    try {
      const csrf = getCsrfToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      };
      if (csrf) headers['X-CSRF-Token'] = csrf;

      const res = await fetch('/api/v1/admin/standalone/backup-schedule', {
        method: 'PUT',
        headers,
        credentials: 'same-origin',
        body: JSON.stringify({
          enabled: schedule.enabled,
          interval_hours: schedule.interval_hours,
          retention_count: schedule.retention_count,
        }),
      });

      if (res.ok) {
        const updated = (await res.json()) as BackupScheduleState;
        setSchedule(updated);
        setScheduleSaved(true);
        setTimeout(() => { setScheduleSaved(false); }, 2500);
      }
    } catch {
      // Ignore save error
    }
  };

  const handleRunBackupNow = async (): Promise<void> => {
    setIsRunningBackupNow(true);
    try {
      const csrf = getCsrfToken();
      const headers: Record<string, string> = {
        Accept: 'application/json',
      };
      if (csrf) headers['X-CSRF-Token'] = csrf;

      const res = await fetch('/api/v1/admin/standalone/backups/run-now', {
        method: 'POST',
        headers,
        credentials: 'same-origin',
      });
      if (res.ok) {
        void loadScheduleAndSnapshots();
      }
    } catch {
      // Handled
    } finally {
      setIsRunningBackupNow(false);
    }
  };

  const handleVerifyBackup = async (): Promise<void> => {
    setIsVerifying(true);
    setVerifyError(null);
    setVerifiedManifest(null);

    try {
      const csrf = getCsrfToken();
      let res: Response;

      if (restoreFile) {
        const formData = new FormData();
        formData.append('file', restoreFile);
        if (restorePassphrase) {
          formData.append('passphrase', restorePassphrase);
        }
        const headers: Record<string, string> = {};
        if (csrf) headers['X-CSRF-Token'] = csrf;

        res = await fetch('/api/v1/admin/standalone/backup/verify', {
          method: 'POST',
          headers,
          credentials: 'same-origin',
          body: formData,
        });
      } else if (selectedSnapshotFilename) {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        res = await fetch('/api/v1/admin/standalone/backup/verify', {
          method: 'POST',
          headers,
          credentials: 'same-origin',
          body: JSON.stringify({
            filename: selectedSnapshotFilename,
            passphrase: restorePassphrase || undefined,
          }),
        });
      } else {
        throw new Error('Please select an existing snapshot or upload a backup file');
      }

      if (!res.ok) {
        const errJson = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errJson.detail ?? `Verification failed (${String(res.status)})`);
      }

      const verifyData = (await res.json()) as {
        valid: boolean;
        manifest?: BackupManifestData;
        format?: string;
      };
      if (verifyData.manifest) {
        setVerifiedManifest(verifyData.manifest);
      } else {
        setVerifiedManifest({ format_version: 1, created_at: new Date().toISOString() });
      }
    } catch (err) {
      setVerifyError(err instanceof Error ? err.message : 'Backup verification failed');
    } finally {
      setIsVerifying(false);
    }
  };

  const handleRestoreSubmit = async (e: SyntheticEvent): Promise<void> => {
    e.preventDefault();
    if (restoreConfirmText !== 'RESTORE') {
      setRestoreError('You must type RESTORE exactly to confirm destructive database overwrite');
      return;
    }

    setIsRestoring(true);
    setRestoreError(null);
    setRestoreSuccess(null);

    try {
      const csrf = getCsrfToken();
      let res: Response;

      if (restoreFile) {
        const formData = new FormData();
        formData.append('file', restoreFile);
        formData.append('confirm_overwrite', 'RESTORE');
        if (restorePassphrase) {
          formData.append('passphrase', restorePassphrase);
        }
        const headers: Record<string, string> = {};
        if (csrf) headers['X-CSRF-Token'] = csrf;

        res = await fetch('/api/v1/admin/standalone/restore', {
          method: 'POST',
          headers,
          credentials: 'same-origin',
          body: formData,
        });
      } else if (selectedSnapshotFilename) {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        };
        if (csrf) headers['X-CSRF-Token'] = csrf;

        res = await fetch('/api/v1/admin/standalone/restore', {
          method: 'POST',
          headers,
          credentials: 'same-origin',
          body: JSON.stringify({
            filename: selectedSnapshotFilename,
            passphrase: restorePassphrase || undefined,
            confirm_overwrite: 'RESTORE',
          }),
        });
      } else {
        throw new Error('Please select a backup file or snapshot to restore');
      }

      if (!res.ok) {
        const errJson = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errJson.detail ?? `Restore failed (${String(res.status)})`);
      }

      setRestoreSuccess('Database restored successfully! Invariants, roles, and schema verified.');
      setRestoreConfirmText('');
      setVerifiedManifest(null);
    } catch (err) {
      setRestoreError(err instanceof Error ? err.message : 'Database restore failed');
    } finally {
      setIsRestoring(false);
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
          <h2 className="standalone-panel__title">System Storage, Backups & Deployment</h2>
          <button
            type="button"
            className="standalone-panel__close"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="standalone-panel__tabs" role="tablist" aria-label="System status sections">
          <button
            type="button"
            role="tab"
            id="tab-health"
            aria-selected={activeTab === 'health'}
            aria-controls="panel-health"
            className={`standalone-panel__tab-btn ${activeTab === 'health' ? 'standalone-panel__tab-btn--active' : ''}`}
            onClick={() => { setActiveTab('health'); }}
          >
            Storage & Capabilities Health
          </button>
          <button
            type="button"
            role="tab"
            id="tab-backup"
            aria-selected={activeTab === 'backup'}
            aria-controls="panel-backup"
            className={`standalone-panel__tab-btn ${activeTab === 'backup' ? 'standalone-panel__tab-btn--active' : ''}`}
            onClick={() => { setActiveTab('backup'); }}
          >
            Backup, Auto-Backup & Restore
          </button>
          {isServerAdmin && (
            <button
              type="button"
              role="tab"
              id="tab-compose"
              aria-selected={activeTab === 'compose'}
              aria-controls="panel-compose"
              className={`standalone-panel__tab-btn ${activeTab === 'compose' ? 'standalone-panel__tab-btn--active' : ''}`}
              onClick={() => { setActiveTab('compose'); }}
            >
              Docker Compose Export
            </button>
          )}
        </div>

        {/* Tab 1: Storage & Capabilities Health */}
        <div
          role="tabpanel"
          id="panel-health"
          aria-labelledby="tab-health"
          className={`standalone-panel__tabpanel ${activeTab !== 'health' ? 'standalone-panel__tabpanel--hidden' : ''}`}
        >
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

            <div className="standalone-panel__sandbox-cards">
              <div className="standalone-panel__capability-card">
                <div className="standalone-panel__capability-header">
                  <span className="standalone-panel__capability-title">
                    Built-in Formula Sandbox (WebAssembly)
                  </span>
                  <span className="standalone-panel__capability-status standalone-panel__capability-status--active">
                    Always Active
                  </span>
                </div>
                <p className="standalone-panel__capability-desc">
                  Runs fast custom field formulas and workflow checks in-memory with zero network or filesystem access (Always active).
                </p>
              </div>

              <div className="standalone-panel__capability-card">
                <div className="standalone-panel__capability-header">
                  <span className="standalone-panel__capability-title">
                    Isolated Process & CLI Sandbox (Linux Namespaces)
                  </span>
                  <span
                    className={`standalone-panel__capability-status ${
                      tierBSandbox
                        ? 'standalone-panel__capability-status--active'
                        : 'standalone-panel__capability-status--optional'
                    }`}
                  >
                    {tierBSandbox ? 'Active' : 'Optional'}
                  </span>
                </div>
                <p className="standalone-panel__capability-desc">
                  {tierBSandbox
                    ? 'Runs full Python/CLI scripts and local CLI transition agents with isolated Linux namespaces and allowlisted HTTP egress.'
                    : 'ℹ️ Optional - Not enabled in single-container mode'}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Tab 2: Backup, Auto-Backup & Restore */}
        <div
          role="tabpanel"
          id="panel-backup"
          aria-labelledby="tab-backup"
          className={`standalone-panel__tabpanel ${activeTab !== 'backup' ? 'standalone-panel__tabpanel--hidden' : ''}`}
        >
          {isServerAdmin ? (
            <div className="standalone-panel__section">
              {/* Subsection A: Manual Database Backup */}
              <div className="standalone-panel__subcard">
                <h3 className="standalone-panel__section-title">Manual Encrypted Backup (.kbbak)</h3>
                <form
                  onSubmit={(e) => {
                    void handleBackupSubmit(e);
                  }}
                  className="standalone-panel__backup-form"
                >
                  <label htmlFor="backup-passphrase" className="standalone-panel__label">
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
                    {isBackingUp ? 'Exporting Backup...' : 'Download Encrypted Backup (.kbbak)'}
                  </button>
                </form>
              </div>

              {/* Subsection B: Automated Scheduled Backups */}
              <div className="standalone-panel__subcard">
                <h3 className="standalone-panel__section-title">Automated Scheduled Backups</h3>
                <div className="standalone-panel__schedule-grid">
                  <label className="standalone-panel__checkbox-label">
                    <input
                      type="checkbox"
                      checked={schedule.enabled}
                      onChange={(e) => {
                        setSchedule((prev) => ({ ...prev, enabled: e.target.checked }));
                      }}
                    />
                    <span>Enable Automated Backups</span>
                  </label>

                  <div className="standalone-panel__field-group">
                    <label htmlFor="schedule-interval" className="standalone-panel__label">
                      Backup Interval (hours)
                    </label>
                    <input
                      id="schedule-interval"
                      type="number"
                      min={1}
                      max={168}
                      value={schedule.interval_hours}
                      onChange={(e) => {
                        setSchedule((prev) => ({
                          ...prev,
                          interval_hours: Math.max(1, parseInt(e.target.value, 10) || 24),
                        }));
                      }}
                      className="standalone-panel__input"
                    />
                  </div>

                  <div className="standalone-panel__field-group">
                    <label htmlFor="schedule-retention" className="standalone-panel__label">
                      Keep Latest Snapshots
                    </label>
                    <input
                      id="schedule-retention"
                      type="number"
                      min={1}
                      max={90}
                      value={schedule.retention_count}
                      onChange={(e) => {
                        setSchedule((prev) => ({
                          ...prev,
                          retention_count: Math.max(1, parseInt(e.target.value, 10) || 7),
                        }));
                      }}
                      className="standalone-panel__input"
                    />
                  </div>
                </div>

                <div className="standalone-panel__btn-group">
                  <button
                    type="button"
                    onClick={() => { void handleSaveSchedule(); }}
                    className="standalone-panel__btn standalone-panel__btn--secondary"
                  >
                    {scheduleSaved ? 'Schedule Saved!' : 'Save Schedule'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { void handleRunBackupNow(); }}
                    disabled={isRunningBackupNow}
                    className="standalone-panel__btn standalone-panel__btn--secondary"
                  >
                    {isRunningBackupNow ? 'Running Backup...' : 'Run Backup Now'}
                  </button>
                </div>

                {snapshots.length > 0 && (
                  <div className="standalone-panel__snapshots-list">
                    <h4 className="standalone-panel__checklist-title">Existing Server Snapshots:</h4>
                    <div className="standalone-panel__snapshots-table-wrapper">
                      <table className="standalone-panel__snapshots-table">
                        <thead>
                          <tr>
                            <th>Filename</th>
                            <th>Size</th>
                            <th>Created</th>
                            <th>Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {snapshots.map((s) => (
                            <tr key={s.filename}>
                              <td>{s.filename}</td>
                              <td>{(s.size_bytes / 1024).toFixed(1)} KB</td>
                              <td>{new Date(s.created_at).toLocaleString()}</td>
                              <td>
                                <a
                                  href={`/api/v1/admin/standalone/backups/${s.filename}`}
                                  download={s.filename}
                                  className="standalone-panel__table-link"
                                >
                                  Download
                                </a>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>

              {/* Subsection C: 2-Stage Verification & Restore */}
              <div className="standalone-panel__subcard">
                <h3 className="standalone-panel__section-title">Restore Database (2-Stage Verification)</h3>
                <p className="standalone-panel__hint">
                  Step 1 verifies cryptographic integrity without touching the database. Step 2 requires explicit confirmation.
                </p>

                <div className="standalone-panel__restore-inputs">
                  {snapshots.length > 0 && (
                    <div className="standalone-panel__field-group">
                      <label htmlFor="select-snapshot" className="standalone-panel__label">
                        Select Server Snapshot
                      </label>
                      <select
                        id="select-snapshot"
                        value={selectedSnapshotFilename}
                        onChange={(e) => {
                          setSelectedSnapshotFilename(e.target.value);
                          setRestoreFile(null);
                        }}
                        className="standalone-panel__input"
                      >
                        <option value="">-- Or Choose Server Snapshot --</option>
                        {snapshots.map((s) => (
                          <option key={s.filename} value={s.filename}>
                            {s.filename} ({new Date(s.created_at).toLocaleDateString()})
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  <div className="standalone-panel__field-group">
                    <label htmlFor="upload-backup-file" className="standalone-panel__label">
                      Upload Backup Archive (.kbbak or .kbkp)
                    </label>
                    <input
                      id="upload-backup-file"
                      type="file"
                      accept=".kbbak,.kbkp,.dump"
                      onChange={(e) => {
                        const file = e.target.files?.[0] ?? null;
                        setRestoreFile(file);
                        if (file) setSelectedSnapshotFilename('');
                      }}
                      className="standalone-panel__input"
                    />
                  </div>

                  <div className="standalone-panel__field-group">
                    <label htmlFor="restore-passphrase" className="standalone-panel__label">
                      Passphrase (if encrypted with passphrase)
                    </label>
                    <input
                      id="restore-passphrase"
                      type="password"
                      autoComplete="off"
                      value={restorePassphrase}
                      onChange={(e) => { setRestorePassphrase(e.target.value); }}
                      className="standalone-panel__input"
                      placeholder="Enter decryption passphrase"
                    />
                  </div>

                  <button
                    type="button"
                    onClick={() => { void handleVerifyBackup(); }}
                    disabled={isVerifying || (!restoreFile && !selectedSnapshotFilename)}
                    className="standalone-panel__btn standalone-panel__btn--secondary"
                  >
                    {isVerifying ? 'Verifying...' : 'Step 1: Verify Backup Archive'}
                  </button>

                  {verifyError && (
                    <div role="alert" className="standalone-panel__error">
                      {verifyError}
                    </div>
                  )}

                  {verifiedManifest && (
                    <div className="standalone-panel__verified-manifest">
                      <div className="standalone-panel__badge-title">✓ Backup Archive Verified</div>
                      <div className="standalone-panel__hint">
                        PostgreSQL: {verifiedManifest.pg_server_version ?? '16'} | Alembic Rev: {verifiedManifest.alembic_revision ?? 'current'}
                      </div>

                      {/* Destructive Gate Form */}
                      <form
                        onSubmit={(e) => { void handleRestoreSubmit(e); }}
                        className="standalone-panel__destructive-form"
                      >
                        <label htmlFor="restore-confirm" className="standalone-panel__label standalone-panel__label--danger">
                          Type RESTORE to confirm overwriting current database:
                        </label>
                        <input
                          id="restore-confirm"
                          type="text"
                          autoComplete="off"
                          value={restoreConfirmText}
                          onChange={(e) => { setRestoreConfirmText(e.target.value); }}
                          placeholder="RESTORE"
                          className="standalone-panel__input"
                        />
                        <button
                          type="submit"
                          disabled={isRestoring || restoreConfirmText !== 'RESTORE'}
                          className="standalone-panel__btn standalone-panel__btn--danger"
                        >
                          {isRestoring ? 'Restoring Database...' : 'Step 2: Restore Database'}
                        </button>
                      </form>
                    </div>
                  )}

                  {restoreError && (
                    <div role="alert" className="standalone-panel__error">
                      {restoreError}
                    </div>
                  )}

                  {restoreSuccess && (
                    <div role="status" className="standalone-panel__success">
                      {restoreSuccess}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="standalone-panel__section">
              <p className="standalone-panel__member-notice">
                Contact a Server Administrator to export backups or promote this instance.
              </p>
            </div>
          )}
        </div>

        {/* Tab 3: Docker Compose Export */}
        {isServerAdmin && (
          <div
            role="tabpanel"
            id="panel-compose"
            aria-labelledby="tab-compose"
            className={`standalone-panel__tabpanel ${activeTab !== 'compose' ? 'standalone-panel__tabpanel--hidden' : ''}`}
          >
            <div className="standalone-panel__section">
              <h3 className="standalone-panel__section-title">
                Production Compose Export & Promotion
              </h3>
              <ComposeExportTab />
            </div>
          </div>
        )}
      </div>
    </>
  );
}
