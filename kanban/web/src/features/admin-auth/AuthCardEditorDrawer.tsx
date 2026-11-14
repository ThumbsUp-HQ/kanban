import React, { useState, useEffect, useRef, type JSX } from 'react';
import type {
  AdminAuthCard,
  CreateAuthCardPayload,
  UpdateAuthCardPayload,
  ProviderKind,
} from './adminAuthApi';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import './adminAuth.css';

export interface AuthCardEditorDrawerProps {
  isOpen: boolean;
  card: AdminAuthCard | null; // null = create new card
  onClose: () => void;
  onSave: (
    payload: CreateAuthCardPayload | UpdateAuthCardPayload,
    isEdit: boolean,
  ) => Promise<void>;
}

const SLUG_REGEX = /^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$/;
const SPKI_REGEX = /^[A-Fa-f0-9]{64}$/;

export function AuthCardEditorDrawer({
  isOpen,
  card,
  onClose,
  onSave,
}: AuthCardEditorDrawerProps): JSX.Element | null {
  const isEdit = Boolean(card);
  const drawerRef = useRef<HTMLDivElement | null>(null);

  // Common metadata
  const [prevCard, setPrevCard] = useState<AdminAuthCard | null>(card);
  const [providerKind, setProviderKind] = useState<ProviderKind>(() => card?.provider_kind ?? 'OIDC');
  const [slug, setSlug] = useState(() => card?.slug ?? '');
  const [displayName, setDisplayName] = useState(() => card?.display_name ?? '');
  const [buttonSubtext, setButtonSubtext] = useState(() => card?.button_subtext ?? '');
  const [iconPreset, setIconPreset] = useState(() => card?.icon_preset ?? 'shield');
  const [autoProvisionUsers, setAutoProvisionUsers] = useState(() => card?.auto_provision_users ?? true);
  const [allowedEmailDomains, setAllowedEmailDomains] = useState(() => card?.allowed_email_domains.join(', ') ?? '');

  // OIDC / OAuth2 fields
  const [issuerUrl, setIssuerUrl] = useState(() => (typeof card?.public_config.issuer_url === 'string' ? card.public_config.issuer_url : ''));
  const [clientId, setClientId] = useState(() => (typeof card?.public_config.client_id === 'string' ? card.public_config.client_id : ''));
  const [scopes, setScopes] = useState(() => {
    const sc = card?.public_config.scopes;
    if (Array.isArray(sc)) return sc.join(', ');
    if (typeof sc === 'string') return sc;
    return 'openid, profile, email';
  });
  const [tokenAuthMethod, setTokenAuthMethod] = useState<'client_secret_basic' | 'private_key_jwt'>(() =>
    card?.public_config.token_auth_method === 'private_key_jwt' ? 'private_key_jwt' : 'client_secret_basic',
  );

  // LDAP fields
  const [serverUrl, setServerUrl] = useState(() => (typeof card?.public_config.server_url === 'string' ? card.public_config.server_url : ''));
  const [startTls, setStartTls] = useState(() => Boolean(card?.public_config.start_tls));
  const [bindDn, setBindDn] = useState(() => (typeof card?.public_config.bind_dn === 'string' ? card.public_config.bind_dn : ''));
  const [baseDn, setBaseDn] = useState(() => (typeof card?.public_config.base_dn === 'string' ? card.public_config.base_dn : ''));
  const [userFilter, setUserFilter] = useState(() =>
    typeof card?.public_config.user_filter === 'string' ? card.public_config.user_filter : '(sAMAccountName={username})',
  );
  const [caPem, setCaPem] = useState(() => (typeof card?.public_config.ca_pem === 'string' ? card.public_config.ca_pem : ''));
  const [spkiPin, setSpkiPin] = useState(() =>
    typeof card?.public_config.spki_sha256_pin === 'string' ? card.public_config.spki_sha256_pin : '',
  );

  // Secret input and write-only state
  const [secretInput, setSecretInput] = useState('');
  const [replaceSecret, setReplaceSecret] = useState(() => !card);

  // Submission & Validation errors
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // Synchronize state during rendering when card changes
  if (card !== prevCard) {
    setPrevCard(card);
    setProviderKind(card?.provider_kind ?? 'OIDC');
    setSlug(card?.slug ?? '');
    setDisplayName(card?.display_name ?? '');
    setButtonSubtext(card?.button_subtext ?? '');
    setIconPreset(card?.icon_preset ?? 'shield');
    setAutoProvisionUsers(card?.auto_provision_users ?? true);
    setAllowedEmailDomains(card?.allowed_email_domains.join(', ') ?? '');
    setIssuerUrl(typeof card?.public_config.issuer_url === 'string' ? card.public_config.issuer_url : '');
    setClientId(typeof card?.public_config.client_id === 'string' ? card.public_config.client_id : '');
    const rawScopes = card?.public_config.scopes;
    setScopes(Array.isArray(rawScopes) ? rawScopes.join(', ') : (typeof rawScopes === 'string' ? rawScopes : 'openid, profile, email'));
    setTokenAuthMethod(card?.public_config.token_auth_method === 'private_key_jwt' ? 'private_key_jwt' : 'client_secret_basic');
    setServerUrl(typeof card?.public_config.server_url === 'string' ? card.public_config.server_url : '');
    setStartTls(Boolean(card?.public_config.start_tls));
    setBindDn(typeof card?.public_config.bind_dn === 'string' ? card.public_config.bind_dn : '');
    setBaseDn(typeof card?.public_config.base_dn === 'string' ? card.public_config.base_dn : '');
    setUserFilter(typeof card?.public_config.user_filter === 'string' ? card.public_config.user_filter : '(sAMAccountName={username})');
    setCaPem(typeof card?.public_config.ca_pem === 'string' ? card.public_config.ca_pem : '');
    setSpkiPin(typeof card?.public_config.spki_sha256_pin === 'string' ? card.public_config.spki_sha256_pin : '');
    setSecretInput('');
    setReplaceSecret(!card);
    setFormError(null);
    setFieldErrors({});
  }

  // Trap Escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Enforce LDAP start_tls locked when scheme is ldap://
  const handleServerUrlChange = (val: string) => {
    setServerUrl(val);
    if (val.trim().toLowerCase().startsWith('ldap://')) {
      setStartTls(true);
    }
  };

  const validate = (): boolean => {
    const errors: Record<string, string> = {};

    if (!isEdit) {
      if (!slug.trim()) {
        errors.slug = 'Slug is required.';
      } else if (!SLUG_REGEX.test(slug.trim())) {
        errors.slug = 'Slug must be 3-48 lowercase alphanumeric characters or hyphens.';
      }
    }

    if (!displayName.trim() || displayName.length > 80) {
      errors.displayName = 'Display name must be between 1 and 80 characters.';
    }

    if (buttonSubtext.length > 120) {
      errors.buttonSubtext = 'Subtext must not exceed 120 characters.';
    }

    if (providerKind === 'OIDC' || providerKind === 'OAUTH2') {
      if (!issuerUrl.trim()) {
        errors.issuerUrl = 'Issuer URL is required.';
      } else if (!issuerUrl.trim().toLowerCase().startsWith('https://')) {
        errors.issuerUrl = 'Issuer URL must use HTTPS.';
      }

      if (!clientId.trim()) {
        errors.clientId = 'Client ID is required.';
      }
    }

    if (providerKind === 'LDAP') {
      const sUrl = serverUrl.trim().toLowerCase();
      if (!sUrl) {
        errors.serverUrl = 'Server URL is required.';
      } else if (!sUrl.startsWith('ldaps://') && !sUrl.startsWith('ldap://')) {
        errors.serverUrl = 'Server URL must start with ldaps:// or ldap://';
      } else if (sUrl.startsWith('ldap://') && !startTls) {
        errors.serverUrl = 'ldap:// requires StartTLS to be enabled.';
      }

      if (!bindDn.trim()) {
        errors.bindDn = 'Bind DN is required.';
      }
      if (!baseDn.trim()) {
        errors.baseDn = 'Base DN is required.';
      }

      if (spkiPin.trim() && !SPKI_REGEX.test(spkiPin.trim())) {
        errors.spkiPin = 'SPKI pin must be exactly 64 hexadecimal characters.';
      }
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();

    if (!validate()) {
      return;
    }

    setIsSubmitting(true);
    setFormError(null);

    const domains = allowedEmailDomains
      .split(',')
      .map((d) => d.trim().toLowerCase())
      .filter(Boolean);

    let publicConfig: Record<string, unknown> = {};

    if (providerKind === 'OIDC' || providerKind === 'OAUTH2') {
      const scopeList = scopes
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      publicConfig = {
        issuer_url: issuerUrl.trim(),
        client_id: clientId.trim(),
        scopes: scopeList,
        pkce_method: 'S256',
        token_auth_method: tokenAuthMethod,
      };
    } else if (providerKind === 'LDAP') {
      publicConfig = {
        server_url: serverUrl.trim(),
        start_tls: serverUrl.trim().toLowerCase().startsWith('ldap://') ? true : startTls,
        bind_dn: bindDn.trim(),
        base_dn: baseDn.trim(),
        user_filter: userFilter.trim(),
        ...(caPem.trim() ? { ca_pem: caPem.trim() } : {}),
        ...(spkiPin.trim() ? { spki_sha256_pin: spkiPin.trim() } : {}),
      };
    } else {
      publicConfig = card?.public_config ?? {};
    }

    try {
      if (isEdit) {
        const payload: UpdateAuthCardPayload = {
          display_name: displayName.trim(),
          button_subtext: buttonSubtext.trim() || null,
          icon_preset: iconPreset,
          auto_provision_users: autoProvisionUsers,
          allowed_email_domains: domains,
          public_config: publicConfig,
        };

        // Write-only contract: include secret_input ONLY when replaceSecret is checked
        if (replaceSecret && secretInput.trim()) {
          payload.secret_input = secretInput.trim();
        }

        await onSave(payload, true);
      } else {
        const payload: CreateAuthCardPayload = {
          provider_kind: providerKind,
          slug: slug.trim(),
          display_name: displayName.trim(),
          button_subtext: buttonSubtext.trim() || null,
          icon_preset: iconPreset,
          auto_provision_users: autoProvisionUsers,
          allowed_email_domains: domains,
          public_config: publicConfig,
          ...(secretInput.trim() ? { secret_input: secretInput.trim() } : {}),
        };

        await onSave(payload, false);
      }

      onClose();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setFormError(err.message);
      } else {
        setFormError('Failed to save authentication card.');
      }
    } finally {
      // Volatile secret cleanup in finally block
      setSecretInput('');
      setIsSubmitting(false);
    }
  };

  const secretPlaceholder =
    isEdit && card?.has_secret
      ? `Stored encrypted (dek_kid: ${card.dek_kid ?? 'active'}) - leave blank to keep current secret`
      : 'Enter secret value';

  return (
    <div className="auth-drawer-backdrop" onClick={onClose} role="presentation">
      <div
        ref={drawerRef}
        className="auth-editor-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        onClick={(e) => { e.stopPropagation(); }}
      >
        <div className="auth-editor-header">
          <h2 id="drawer-title" className="auth-editor-title">
            {card ? `Edit ${card.display_name}` : 'Add Authentication Card'}
          </h2>
          <button
            type="button"
            className="auth-btn-secondary"
            onClick={onClose}
            aria-label="Close drawer"
          >
            ×
          </button>
        </div>

        {formError ? (
          <div className="auth-editor-error" role="alert">
            {formError}
          </div>
        ) : null}

        <form onSubmit={(e) => { void handleSubmit(e); }} noValidate>
          {/* Section: General Configuration */}
          <div className="auth-editor-section-title">General Settings</div>

          <div className="auth-editor-prop-row">
            <label className="auth-editor-label" htmlFor="card-provider-kind">
              Provider Kind
            </label>
            <select
              id="card-provider-kind"
              className="auth-editor-select"
              value={providerKind}
              onChange={(e) => { setProviderKind(e.target.value as ProviderKind); }}
              disabled={isEdit || isSubmitting}
            >
              <option value="OIDC">OIDC</option>
              <option value="OAUTH2">OAuth 2.0</option>
              <option value="LDAP">LDAP / Active Directory</option>
              {isEdit && providerKind === 'LOCAL_ADMIN' ? (
                <option value="LOCAL_ADMIN">Local Administrator</option>
              ) : null}
            </select>
          </div>

          <div className="auth-editor-prop-row">
            <label className="auth-editor-label" htmlFor="card-slug">
              Slug Identifier
            </label>
            <input
              id="card-slug"
              type="text"
              className="auth-editor-input"
              value={slug}
              onChange={(e) => { setSlug(e.target.value); }}
              disabled={isEdit || isSubmitting}
              placeholder="e.g. corp-ad"
              maxLength={48}
              required
            />
          </div>
          {fieldErrors.slug ? (
            <div className="auth-editor-error">{fieldErrors.slug}</div>
          ) : null}

          <div className="auth-editor-prop-row">
            <label className="auth-editor-label" htmlFor="card-display-name">
              Display Name
            </label>
            <input
              id="card-display-name"
              type="text"
              className="auth-editor-input"
              value={displayName}
              onChange={(e) => { setDisplayName(e.target.value); }}
              disabled={isSubmitting}
              placeholder="e.g. Corporate Active Directory"
              maxLength={80}
              required
            />
          </div>
          {fieldErrors.displayName ? (
            <div className="auth-editor-error">{fieldErrors.displayName}</div>
          ) : null}

          <div className="auth-editor-prop-row">
            <label className="auth-editor-label" htmlFor="card-subtext">
              Button Subtext
            </label>
            <input
              id="card-subtext"
              type="text"
              className="auth-editor-input"
              value={buttonSubtext}
              onChange={(e) => { setButtonSubtext(e.target.value); }}
              disabled={isSubmitting}
              placeholder="e.g. Domain accounts (@corp.com)"
              maxLength={120}
            />
          </div>
          {fieldErrors.buttonSubtext ? (
            <div className="auth-editor-error">{fieldErrors.buttonSubtext}</div>
          ) : null}

          <div className="auth-editor-prop-row">
            <label className="auth-editor-label" htmlFor="card-icon-preset">
              Icon Preset
            </label>
            <select
              id="card-icon-preset"
              className="auth-editor-select"
              value={iconPreset}
              onChange={(e) => { setIconPreset(e.target.value); }}
              disabled={isSubmitting}
            >
              <option value="shield">🛡️ Shield</option>
              <option value="key">🔑 Key</option>
              <option value="lock">🔒 Lock</option>
              <option value="globe">🌐 Globe</option>
              <option value="user-check">👤 User Check</option>
            </select>
          </div>

          <div className="auth-editor-prop-row">
            <label className="auth-editor-label" htmlFor="card-auto-provision">
              Auto-provision Users
            </label>
            <input
              id="card-auto-provision"
              type="checkbox"
              checked={autoProvisionUsers}
              onChange={(e) => { setAutoProvisionUsers(e.target.checked); }}
              disabled={isSubmitting}
            />
          </div>

          <div className="auth-editor-prop-row">
            <label className="auth-editor-label" htmlFor="card-email-domains">
              Allowed Email Domains
            </label>
            <input
              id="card-email-domains"
              type="text"
              className="auth-editor-input"
              value={allowedEmailDomains}
              onChange={(e) => { setAllowedEmailDomains(e.target.value); }}
              disabled={isSubmitting}
              placeholder="e.g. corp.example.com, example.org"
            />
          </div>

          {/* Section: Provider Specific Config */}
          {providerKind === 'OIDC' || providerKind === 'OAUTH2' ? (
            <div>
              <div className="auth-editor-section-title">OIDC / OAuth 2.0 Settings</div>

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-issuer-url">
                  Issuer URL
                </label>
                <input
                  id="card-issuer-url"
                  type="url"
                  className="auth-editor-input"
                  value={issuerUrl}
                  onChange={(e) => { setIssuerUrl(e.target.value); }}
                  disabled={isSubmitting}
                  placeholder="https://accounts.google.com"
                  required
                />
              </div>
              {fieldErrors.issuerUrl ? (
                <div className="auth-editor-error">{fieldErrors.issuerUrl}</div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-client-id">
                  Client ID
                </label>
                <input
                  id="card-client-id"
                  type="text"
                  className="auth-editor-input"
                  value={clientId}
                  onChange={(e) => { setClientId(e.target.value); }}
                  disabled={isSubmitting}
                  required
                />
              </div>
              {fieldErrors.clientId ? (
                <div className="auth-editor-error">{fieldErrors.clientId}</div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-scopes">
                  Scopes
                </label>
                <input
                  id="card-scopes"
                  type="text"
                  className="auth-editor-input"
                  value={scopes}
                  onChange={(e) => { setScopes(e.target.value); }}
                  disabled={isSubmitting}
                  placeholder="openid, profile, email"
                />
              </div>

              <div className="auth-editor-prop-row">
                <span className="auth-editor-label">PKCE Enforcement</span>
                <span className="auth-badge-primary auth-badge--pkce">PKCE S256 (enforced)</span>
              </div>

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-token-auth">
                  Token Auth Method
                </label>
                <select
                  id="card-token-auth"
                  className="auth-editor-select"
                  value={tokenAuthMethod}
                  onChange={(e) => { setTokenAuthMethod(
                      e.target.value as 'client_secret_basic' | 'private_key_jwt',
                    ); }
                  }
                  disabled={isSubmitting}
                >
                  <option value="client_secret_basic">client_secret_basic</option>
                  <option value="private_key_jwt">private_key_jwt</option>
                </select>
              </div>

              {/* Write-only secret field */}
              <div className="auth-editor-section-title">Credentials</div>

              {isEdit && card?.has_secret ? (
                <div className="auth-editor-prop-row">
                  <label className="auth-editor-label" htmlFor="card-replace-secret">
                    Replace Stored Secret
                  </label>
                  <input
                    id="card-replace-secret"
                    type="checkbox"
                    checked={replaceSecret}
                    onChange={(e) => { setReplaceSecret(e.target.checked); }}
                    disabled={isSubmitting}
                  />
                </div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-client-secret">
                  Client Secret
                </label>
                <input
                  id="card-client-secret"
                  type="password"
                  className="auth-editor-input"
                  value={secretInput}
                  onChange={(e) => { setSecretInput(e.target.value); }}
                  placeholder={secretPlaceholder}
                  disabled={!replaceSecret || isSubmitting}
                  autoComplete="new-password"
                />
              </div>
            </div>
          ) : providerKind === 'LDAP' ? (
            <div>
              <div className="auth-editor-section-title">LDAP / Active Directory Settings</div>

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-server-url">
                  Server URL
                </label>
                <input
                  id="card-server-url"
                  type="text"
                  className="auth-editor-input"
                  value={serverUrl}
                  onChange={(e) => { handleServerUrlChange(e.target.value); }}
                  disabled={isSubmitting}
                  placeholder="ldaps://dc01.corp.example.com"
                  required
                />
              </div>
              {fieldErrors.serverUrl ? (
                <div className="auth-editor-error">{fieldErrors.serverUrl}</div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-start-tls">
                  StartTLS
                </label>
                <input
                  id="card-start-tls"
                  type="checkbox"
                  checked={startTls}
                  onChange={(e) => {
                    setStartTls(e.target.checked);
                  }}
                  disabled={
                    serverUrl.trim().toLowerCase().startsWith('ldap://') || isSubmitting
                  }
                />
              </div>

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-bind-dn">
                  Bind DN
                </label>
                <input
                  id="card-bind-dn"
                  type="text"
                  className="auth-editor-input"
                  value={bindDn}
                  onChange={(e) => { setBindDn(e.target.value); }}
                  disabled={isSubmitting}
                  placeholder="cn=read-only,dc=corp,dc=example,dc=com"
                  required
                />
              </div>
              {fieldErrors.bindDn ? (
                <div className="auth-editor-error">{fieldErrors.bindDn}</div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-base-dn">
                  Base DN
                </label>
                <input
                  id="card-base-dn"
                  type="text"
                  className="auth-editor-input"
                  value={baseDn}
                  onChange={(e) => { setBaseDn(e.target.value); }}
                  disabled={isSubmitting}
                  placeholder="ou=Users,dc=corp,dc=example,dc=com"
                  required
                />
              </div>
              {fieldErrors.baseDn ? (
                <div className="auth-editor-error">{fieldErrors.baseDn}</div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-user-filter">
                  User Filter
                </label>
                <input
                  id="card-user-filter"
                  type="text"
                  className="auth-editor-input"
                  value={userFilter}
                  onChange={(e) => { setUserFilter(e.target.value); }}
                  disabled={isSubmitting}
                  placeholder="(sAMAccountName={username})"
                />
              </div>

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-spki-pin">
                  SPKI SHA-256 Pin
                </label>
                <input
                  id="card-spki-pin"
                  type="text"
                  className="auth-editor-input"
                  value={spkiPin}
                  onChange={(e) => { setSpkiPin(e.target.value); }}
                  disabled={isSubmitting}
                  placeholder="64-character hexadecimal hash"
                  maxLength={64}
                />
              </div>
              {fieldErrors.spkiPin ? (
                <div className="auth-editor-error">{fieldErrors.spkiPin}</div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-ca-pem">
                  CA Certificate (PEM)
                </label>
                <textarea
                  id="card-ca-pem"
                  className="auth-editor-textarea"
                  value={caPem}
                  onChange={(e) => { setCaPem(e.target.value); }}
                  disabled={isSubmitting}
                  placeholder="-----BEGIN CERTIFICATE-----..."
                />
              </div>

              {/* Write-only secret field */}
              <div className="auth-editor-section-title">Credentials</div>

              {isEdit && card?.has_secret ? (
                <div className="auth-editor-prop-row">
                  <label className="auth-editor-label" htmlFor="card-replace-bind-pwd">
                    Replace Stored Secret
                  </label>
                  <input
                    id="card-replace-bind-pwd"
                    type="checkbox"
                    checked={replaceSecret}
                    onChange={(e) => { setReplaceSecret(e.target.checked); }}
                    disabled={isSubmitting}
                  />
                </div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-bind-password">
                  Bind DN Password
                </label>
                <input
                  id="card-bind-password"
                  type="password"
                  className="auth-editor-input"
                  value={secretInput}
                  onChange={(e) => { setSecretInput(e.target.value); }}
                  placeholder={secretPlaceholder}
                  disabled={!replaceSecret || isSubmitting}
                  autoComplete="new-password"
                />
              </div>
            </div>
          ) : (
            <div>
              <div className="auth-editor-section-title">Local Administrator Security Policy</div>
              <div className="auth-editor-prop-row">
                <span className="auth-editor-label">Security Profile</span>
                <EmojiHint
                  kind="restricted"
                  label="Local Admin security"
                  content="Argon2id (m=64MiB, t=3, p=4) + server HMAC pepper + mandatory Passkey or TOTP (AAL2)."
                />
              </div>
              <p className="auth-card-subtext">
                Local Administrator passwords use Argon2id hashing with server HMAC pepper and mandatory
                Passkey or TOTP (AAL2) second factor.
              </p>
            </div>
          )}

          {/* Drawer Actions */}
          <div className="auth-editor-actions">
            <button
              type="button"
              className="auth-btn-secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="auth-studio-add-btn"
              disabled={isSubmitting}
              aria-busy={isSubmitting}
            >
              {isSubmitting ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Card'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
