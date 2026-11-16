import React, { useState, useEffect, useRef, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import type {
  AdminAuthCard,
  CreateAuthCardPayload,
  UpdateAuthCardPayload,
  ProviderKind,
} from './adminAuthApi';
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

export type ProviderPreset =
  | 'google'
  | 'github'
  | 'active-directory'
  | 'openldap'
  | 'custom-oauth';

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

  // Active preset
  const [activePreset, setActivePreset] = useState<ProviderPreset | null>(null);

  // Common metadata
  const [prevCard, setPrevCard] = useState<AdminAuthCard | null>(card);
  const [providerKind, setProviderKind] = useState<ProviderKind>(() => card?.provider_kind ?? 'OIDC');
  const [slug, setSlug] = useState(() => card?.slug ?? '');
  const [displayName, setDisplayName] = useState(() => card?.display_name ?? '');
  const [buttonSubtext, setButtonSubtext] = useState(() => card?.button_subtext ?? '');
  const [iconPreset, setIconPreset] = useState(() => card?.icon_preset ?? 'shield');
  const [autoProvisionUsers, setAutoProvisionUsers] = useState(() => card?.auto_provision_users ?? true);
  const [allowedEmailDomains, setAllowedEmailDomains] = useState(() => card?.allowed_email_domains.join(', ') ?? '');

  // Access policies
  const [accessPolicyMode, setAccessPolicyMode] = useState<'any_user' | 'restricted'>(() => {
    const pub = card?.public_config;
    if (pub?.access_mode === 'group_restricted') return 'restricted';
    if (Array.isArray(pub?.admin_allowlist) && pub.admin_allowlist.length > 0) return 'restricted';
    if (Array.isArray(pub?.user_allowlist) && pub.user_allowlist.length > 0) return 'restricted';
    return 'any_user';
  });
  const [adminAllowlist, setAdminAllowlist] = useState(() => {
    const list = card?.public_config.admin_allowlist;
    return Array.isArray(list) ? list.join(', ') : '';
  });
  const [userAllowlist, setUserAllowlist] = useState(() => {
    const list = card?.public_config.user_allowlist;
    return Array.isArray(list) ? list.join(', ') : '';
  });
  const [adminGroups, setAdminGroups] = useState(() => {
    const list = card?.public_config.admin_groups;
    return Array.isArray(list) ? list.join(', ') : '';
  });
  const [userGroups, setUserGroups] = useState(() => {
    const list = card?.public_config.user_groups;
    return Array.isArray(list) ? list.join(', ') : '';
  });

  // OIDC / OAuth2 fields
  const [issuerUrl, setIssuerUrl] = useState(() => (typeof card?.public_config.issuer_url === 'string' ? card.public_config.issuer_url : (typeof card?.public_config.issuer === 'string' ? card.public_config.issuer : '')));
  const [clientId, setClientId] = useState(() => (typeof card?.public_config.client_id === 'string' ? card.public_config.client_id : ''));
  const [authorizationEndpoint, setAuthorizationEndpoint] = useState(() => (typeof card?.public_config.authorization_endpoint === 'string' ? card.public_config.authorization_endpoint : ''));
  const [tokenEndpoint, setTokenEndpoint] = useState(() => (typeof card?.public_config.token_endpoint === 'string' ? card.public_config.token_endpoint : ''));
  const [userinfoEndpoint, setUserinfoEndpoint] = useState(() => (typeof card?.public_config.userinfo_endpoint === 'string' ? card.public_config.userinfo_endpoint : ''));
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
  const [serverUrl, setServerUrl] = useState(() => (typeof card?.public_config.server_url === 'string' ? card.public_config.server_url : (typeof card?.public_config.url === 'string' ? card.public_config.url : '')));
  const [startTls, setStartTls] = useState(() => Boolean(card?.public_config.start_tls ?? card?.public_config.transport_mode === 'starttls'));
  const [bindDn, setBindDn] = useState(() => (typeof card?.public_config.bind_dn === 'string' ? card.public_config.bind_dn : (typeof card?.public_config.service_bind_dn === 'string' ? card.public_config.service_bind_dn : '')));
  const [baseDn, setBaseDn] = useState(() => (typeof card?.public_config.base_dn === 'string' ? card.public_config.base_dn : ''));
  const [userFilter, setUserFilter] = useState(() =>
    typeof card?.public_config.user_search_filter === 'string'
      ? card.public_config.user_search_filter
      : (typeof card?.public_config.user_filter === 'string' ? card.public_config.user_filter : '(sAMAccountName={username})'),
  );
  const [subjectAttribute, setSubjectAttribute] = useState(() =>
    typeof card?.public_config.subject_attribute === 'string' ? card.public_config.subject_attribute : 'objectGUID',
  );
  const [emailAttribute, setEmailAttribute] = useState(() =>
    typeof card?.public_config.email_attribute === 'string' ? card.public_config.email_attribute : 'mail',
  );
  const [displayNameAttribute, setDisplayNameAttribute] = useState(() =>
    typeof card?.public_config.display_name_attribute === 'string' ? card.public_config.display_name_attribute : 'displayName',
  );
  const [caPem, setCaPem] = useState(() => (typeof card?.public_config.ca_cert_pem === 'string' ? card.public_config.ca_cert_pem : (typeof card?.public_config.ca_pem === 'string' ? card.public_config.ca_pem : '')));
  const [spkiPin, setSpkiPin] = useState(() => {
    const pins = card?.public_config.spki_sha256_pins;
    if (Array.isArray(pins) && pins.length > 0) return pins[0] as string;
    return typeof card?.public_config.spki_sha256_pin === 'string' ? card.public_config.spki_sha256_pin : '';
  });

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
    setActivePreset(null);
    setProviderKind(card?.provider_kind ?? 'OIDC');
    setSlug(card?.slug ?? '');
    setDisplayName(card?.display_name ?? '');
    setButtonSubtext(card?.button_subtext ?? '');
    setIconPreset(card?.icon_preset ?? 'shield');
    setAutoProvisionUsers(card?.auto_provision_users ?? true);
    setAllowedEmailDomains(card?.allowed_email_domains.join(', ') ?? '');

    const pub = card?.public_config;
    if (pub?.access_mode === 'group_restricted' || (Array.isArray(pub?.admin_allowlist) && pub.admin_allowlist.length > 0)) {
      setAccessPolicyMode('restricted');
    } else {
      setAccessPolicyMode('any_user');
    }
    setAdminAllowlist(Array.isArray(pub?.admin_allowlist) ? pub.admin_allowlist.join(', ') : '');
    setUserAllowlist(Array.isArray(pub?.user_allowlist) ? pub.user_allowlist.join(', ') : '');
    setAdminGroups(Array.isArray(pub?.admin_groups) ? pub.admin_groups.join(', ') : '');
    setUserGroups(Array.isArray(pub?.user_groups) ? pub.user_groups.join(', ') : '');

    setIssuerUrl(typeof pub?.issuer_url === 'string' ? pub.issuer_url : (typeof pub?.issuer === 'string' ? pub.issuer : ''));
    setClientId(typeof pub?.client_id === 'string' ? pub.client_id : '');
    setAuthorizationEndpoint(typeof pub?.authorization_endpoint === 'string' ? pub.authorization_endpoint : '');
    setTokenEndpoint(typeof pub?.token_endpoint === 'string' ? pub.token_endpoint : '');
    setUserinfoEndpoint(typeof pub?.userinfo_endpoint === 'string' ? pub.userinfo_endpoint : '');

    const rawScopes = pub?.scopes;
    setScopes(Array.isArray(rawScopes) ? rawScopes.join(', ') : (typeof rawScopes === 'string' ? rawScopes : 'openid, profile, email'));
    setTokenAuthMethod(pub?.token_auth_method === 'private_key_jwt' ? 'private_key_jwt' : 'client_secret_basic');

    setServerUrl(typeof pub?.server_url === 'string' ? pub.server_url : (typeof pub?.url === 'string' ? pub.url : ''));
    setStartTls(Boolean(pub?.start_tls ?? pub?.transport_mode === 'starttls'));
    setBindDn(typeof pub?.bind_dn === 'string' ? pub.bind_dn : (typeof pub?.service_bind_dn === 'string' ? pub.service_bind_dn : ''));
    setBaseDn(typeof pub?.base_dn === 'string' ? pub.base_dn : '');
    setUserFilter(
      typeof pub?.user_search_filter === 'string'
        ? pub.user_search_filter
        : (typeof pub?.user_filter === 'string' ? pub.user_filter : '(sAMAccountName={username})'),
    );
    setSubjectAttribute(typeof pub?.subject_attribute === 'string' ? pub.subject_attribute : 'objectGUID');
    setEmailAttribute(typeof pub?.email_attribute === 'string' ? pub.email_attribute : 'mail');
    setDisplayNameAttribute(typeof pub?.display_name_attribute === 'string' ? pub.display_name_attribute : 'displayName');
    setCaPem(typeof pub?.ca_cert_pem === 'string' ? pub.ca_cert_pem : (typeof pub?.ca_pem === 'string' ? pub.ca_pem : ''));

    const pins = pub?.spki_sha256_pins;
    setSpkiPin(Array.isArray(pins) && pins.length > 0 ? (pins[0] as string) : (typeof pub?.spki_sha256_pin === 'string' ? pub.spki_sha256_pin : ''));

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

  // 1-Click Preset applier
  const applyPreset = (preset: ProviderPreset) => {
    setActivePreset(preset);
    setFieldErrors({});

    if (preset === 'google') {
      setProviderKind('OIDC');
      setSlug('google-oauth');
      setDisplayName('Google Workspace');
      setButtonSubtext('Sign in with your Google account');
      setIconPreset('google');
      setIssuerUrl('https://accounts.google.com');
      setScopes('openid, profile, email');
      setAccessPolicyMode('any_user');
    } else if (preset === 'github') {
      setProviderKind('OAUTH2');
      setSlug('github-oauth');
      setDisplayName('GitHub');
      setButtonSubtext('Sign in with your GitHub account');
      setIconPreset('github');
      setIssuerUrl('https://github.com');
      setAuthorizationEndpoint('https://github.com/login/oauth/authorize');
      setTokenEndpoint('https://github.com/login/oauth/access_token');
      setUserinfoEndpoint('https://api.github.com/user');
      setScopes('read:user, user:email');
      setAccessPolicyMode('any_user');
    } else if (preset === 'active-directory') {
      setProviderKind('LDAP');
      setSlug('ad-ldap');
      setDisplayName('Active Directory');
      setButtonSubtext('Sign in with Windows / AD domain credentials');
      setIconPreset('active-directory');
      setServerUrl('ldaps://ad.corp.local:636');
      setUserFilter('(&(objectCategory=person)(objectClass=user)(sAMAccountName={username}))');
      setSubjectAttribute('objectGUID');
      setEmailAttribute('mail');
      setDisplayNameAttribute('displayName');
      setStartTls(false);
      setAccessPolicyMode('any_user');
    } else if (preset === 'openldap') {
      setProviderKind('LDAP');
      setSlug('openldap');
      setDisplayName('OpenLDAP');
      setButtonSubtext('Sign in with LDAP directory credentials');
      setIconPreset('ldap');
      setServerUrl('ldaps://ldap.corp.local:636');
      setUserFilter('(&(objectClass=person)(uid={username}))');
      setSubjectAttribute('entryUUID');
      setEmailAttribute('mail');
      setDisplayNameAttribute('cn');
      setStartTls(false);
      setAccessPolicyMode('any_user');
    } else {
      setProviderKind('OIDC');
      setSlug('oauth1');
      setDisplayName('Custom SSO');
      setButtonSubtext('Sign in with Single Sign-On');
      setIconPreset('key');
      setScopes('openid, profile, email');
      setAccessPolicyMode('any_user');
    }
  };

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
      if (!clientId.trim()) {
        errors.clientId = 'Client ID is required.';
      }

      if (issuerUrl.trim() && !issuerUrl.trim().toLowerCase().startsWith('https://')) {
        errors.issuerUrl = 'Issuer URL must use HTTPS.';
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

    const parseList = (str: string) =>
      str
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

    let publicConfig: Record<string, unknown> = {};

    if (providerKind === 'OIDC' || providerKind === 'OAUTH2') {
      const scopeList = parseList(scopes);
      publicConfig = {
        kind: providerKind,
        client_id: clientId.trim(),
        scopes: scopeList.length > 0 ? scopeList : ['openid', 'profile', 'email'],
        pkce_method: 'S256',
        token_auth_method: tokenAuthMethod,
        ...(issuerUrl.trim() ? { issuer: issuerUrl.trim(), issuer_url: issuerUrl.trim() } : {}),
        ...(authorizationEndpoint.trim() ? { authorization_endpoint: authorizationEndpoint.trim() } : {}),
        ...(tokenEndpoint.trim() ? { token_endpoint: tokenEndpoint.trim() } : {}),
        ...(userinfoEndpoint.trim() ? { userinfo_endpoint: userinfoEndpoint.trim() } : {}),
        admin_allowlist: accessPolicyMode === 'restricted' ? parseList(adminAllowlist) : [],
        user_allowlist: accessPolicyMode === 'restricted' ? parseList(userAllowlist) : [],
      };
    } else if (providerKind === 'LDAP') {
      const isLdapScheme = serverUrl.trim().toLowerCase().startsWith('ldap://');
      const transportMode = isLdapScheme || startTls ? 'starttls' : 'ldaps';
      publicConfig = {
        kind: 'LDAP',
        url: serverUrl.trim(),
        server_url: serverUrl.trim(),
        transport_mode: transportMode,
        start_tls: isLdapScheme ? true : startTls,
        service_bind_dn: bindDn.trim(),
        bind_dn: bindDn.trim(),
        base_dn: baseDn.trim(),
        user_search_filter: userFilter.trim(),
        user_filter: userFilter.trim(),
        subject_attribute: subjectAttribute.trim() || 'objectGUID',
        email_attribute: emailAttribute.trim() || 'mail',
        display_name_attribute: displayNameAttribute.trim() || 'displayName',
        access_mode: accessPolicyMode === 'restricted' ? 'group_restricted' : 'any_user',
        admin_groups: accessPolicyMode === 'restricted' ? parseList(adminGroups) : [],
        user_groups: accessPolicyMode === 'restricted' ? parseList(userGroups) : [],
        ...(caPem.trim() ? { ca_cert_pem: caPem.trim(), ca_pem: caPem.trim() } : {}),
        ...(spkiPin.trim() ? { spki_sha256_pins: [spkiPin.trim()], spki_sha256_pin: spkiPin.trim() } : {}),
      };
    } else {
      publicConfig = card?.public_config ?? {};
    }

    const effectiveSlug = slug.trim() || (providerKind === 'LDAP' ? 'ldap1' : 'oauth1');

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

        if (replaceSecret && secretInput.trim()) {
          payload.secret = secretInput.trim();
          payload.secret_input = secretInput.trim();
        }

        await onSave(payload, true);
      } else {
        const payload: CreateAuthCardPayload = {
          provider_kind: providerKind,
          slug: effectiveSlug,
          display_name: displayName.trim(),
          button_subtext: buttonSubtext.trim() || null,
          icon_preset: iconPreset,
          auto_provision_users: autoProvisionUsers,
          allowed_email_domains: domains,
          public_config: publicConfig,
          ...(secretInput.trim() ? { secret: secretInput.trim(), secret_input: secretInput.trim() } : {}),
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

        {/* 1-Click Provider Presets */}
        {!isEdit ? (
          <div className="auth-presets-bar">
            <span className="auth-presets-label">1-Click Provider Presets</span>
            <div className="auth-presets-list">
              <button
                type="button"
                className={`auth-preset-btn ${activePreset === 'google' ? 'auth-preset-btn--active' : ''}`}
                onClick={() => { applyPreset('google'); }}
              >
                Google (OAuth 2.0)
              </button>
              <button
                type="button"
                className={`auth-preset-btn ${activePreset === 'github' ? 'auth-preset-btn--active' : ''}`}
                onClick={() => { applyPreset('github'); }}
              >
                GitHub (OAuth 2.0)
              </button>
              <button
                type="button"
                className={`auth-preset-btn ${activePreset === 'active-directory' ? 'auth-preset-btn--active' : ''}`}
                onClick={() => { applyPreset('active-directory'); }}
              >
                Active Directory (sAMAccountName)
              </button>
              <button
                type="button"
                className={`auth-preset-btn ${activePreset === 'openldap' ? 'auth-preset-btn--active' : ''}`}
                onClick={() => { applyPreset('openldap'); }}
              >
                Standard LDAP (OpenLDAP)
              </button>
              <button
                type="button"
                className={`auth-preset-btn ${activePreset === 'custom-oauth' ? 'auth-preset-btn--active' : ''}`}
                onClick={() => { applyPreset('custom-oauth'); }}
              >
                Custom OAuth 2.0 / OIDC
              </button>
            </div>
          </div>
        ) : null}

        <form onSubmit={(e) => { void handleSubmit(e); }} noValidate>
          {card?.provider_kind === 'LOCAL_ADMIN' ? (
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
                Local Administrator passwords use Argon2id hashing with server HMAC pepper and mandatory Passkey or TOTP (AAL2) step-up.
              </p>
            </div>
          ) : (
            <>
              {/* SECTION 1: MANDATORY SETTINGS */}
              <div className="auth-editor-section-title">Mandatory Settings</div>

              {providerKind === 'OIDC' || providerKind === 'OAUTH2' ? (
            <div>
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
                  placeholder="e.g. 123456789-abcdef.apps.googleusercontent.com"
                  required
                />
              </div>
              {fieldErrors.clientId ? (
                <div className="auth-editor-error">{fieldErrors.clientId}</div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-secret">
                  Client Secret
                </label>
                <input
                  id="card-secret"
                  type="password"
                  className="auth-editor-input"
                  value={secretInput}
                  onChange={(e) => { setSecretInput(e.target.value); }}
                  disabled={isSubmitting || (isEdit && !replaceSecret)}
                  placeholder={secretPlaceholder}
                />
              </div>

              {isEdit && card?.has_secret ? (
                <div className="auth-editor-prop-row">
                  <label className="auth-editor-label" htmlFor="card-replace-secret">
                    Replace Stored Secret
                  </label>
                  <input
                    id="card-replace-secret"
                    type="checkbox"
                    checked={replaceSecret}
                    onChange={(e) => {
                      setReplaceSecret(e.target.checked);
                      if (!e.target.checked) setSecretInput('');
                    }}
                    disabled={isSubmitting}
                  />
                </div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-access-policy">
                  Access Policy
                </label>
                <select
                  id="card-access-policy"
                  className="auth-editor-select"
                  value={accessPolicyMode}
                  onChange={(e) => { setAccessPolicyMode(e.target.value as 'any_user' | 'restricted'); }}
                  disabled={isSubmitting}
                >
                  <option value="any_user">Any User in Domain/Directory (Auto-provisions Member)</option>
                  <option value="restricted">Restricted by User/Admin Allowlist</option>
                </select>
              </div>

              {accessPolicyMode === 'restricted' ? (
                <div>
                  <div className="auth-editor-prop-row">
                    <label className="auth-editor-label" htmlFor="card-admin-allowlist">
                      Admin Allowlist
                    </label>
                    <input
                      id="card-admin-allowlist"
                      type="text"
                      className="auth-editor-input"
                      value={adminAllowlist}
                      onChange={(e) => { setAdminAllowlist(e.target.value); }}
                      disabled={isSubmitting}
                      placeholder="e.g. alice@corp.com, admin-user"
                    />
                  </div>
                  <div className="auth-field-helper">
                    Users matching this list receive SERVER_ADMIN automatically.
                  </div>

                  <div className="auth-editor-prop-row">
                    <label className="auth-editor-label" htmlFor="card-user-allowlist">
                      User Allowlist
                    </label>
                    <input
                      id="card-user-allowlist"
                      type="text"
                      className="auth-editor-input"
                      value={userAllowlist}
                      onChange={(e) => { setUserAllowlist(e.target.value); }}
                      disabled={isSubmitting}
                      placeholder="e.g. bob@corp.com, carol@corp.com"
                    />
                  </div>
                  <div className="auth-field-helper">
                    Users matching this list receive WORKSPACE_MEMBER automatically.
                  </div>
                </div>
              ) : null}
            </div>
          ) : providerKind === 'LDAP' ? (
            <div>
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
                  placeholder="ldaps://ad.corp.example.com:636"
                  required
                />
              </div>
              {fieldErrors.serverUrl ? (
                <div className="auth-editor-error">{fieldErrors.serverUrl}</div>
              ) : null}

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
                  placeholder="cn=svc-kanban,ou=services,dc=corp,dc=com"
                  required
                />
              </div>
              {fieldErrors.bindDn ? (
                <div className="auth-editor-error">{fieldErrors.bindDn}</div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-secret">
                  Bind DN Password
                </label>
                <input
                  id="card-secret"
                  type="password"
                  className="auth-editor-input"
                  value={secretInput}
                  onChange={(e) => { setSecretInput(e.target.value); }}
                  disabled={isSubmitting || (isEdit && !replaceSecret)}
                  placeholder={secretPlaceholder}
                />
              </div>

              {isEdit && card?.has_secret ? (
                <div className="auth-editor-prop-row">
                  <label className="auth-editor-label" htmlFor="card-replace-secret">
                    Replace Stored Secret
                  </label>
                  <input
                    id="card-replace-secret"
                    type="checkbox"
                    checked={replaceSecret}
                    onChange={(e) => {
                      setReplaceSecret(e.target.checked);
                      if (!e.target.checked) setSecretInput('');
                    }}
                    disabled={isSubmitting}
                  />
                </div>
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
                  placeholder="dc=corp,dc=com"
                  required
                />
              </div>
              {fieldErrors.baseDn ? (
                <div className="auth-editor-error">{fieldErrors.baseDn}</div>
              ) : null}

              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-access-policy">
                  Access Policy
                </label>
                <select
                  id="card-access-policy"
                  className="auth-editor-select"
                  value={accessPolicyMode}
                  onChange={(e) => { setAccessPolicyMode(e.target.value as 'any_user' | 'restricted'); }}
                  disabled={isSubmitting}
                >
                  <option value="any_user">Any User in Directory (Auto-provisions Member)</option>
                  <option value="restricted">Group-Restricted Access (Admin / User Groups)</option>
                </select>
              </div>

              {accessPolicyMode === 'restricted' ? (
                <div>
                  <div className="auth-editor-prop-row">
                    <label className="auth-editor-label" htmlFor="card-admin-groups">
                      Admin Groups
                    </label>
                    <input
                      id="card-admin-groups"
                      type="text"
                      className="auth-editor-input"
                      value={adminGroups}
                      onChange={(e) => { setAdminGroups(e.target.value); }}
                      disabled={isSubmitting}
                      placeholder="e.g. Domain Admins, Enterprise Admins"
                    />
                  </div>
                  <div className="auth-field-helper">
                    Members of these groups receive SERVER_ADMIN automatically.
                  </div>

                  <div className="auth-editor-prop-row">
                    <label className="auth-editor-label" htmlFor="card-user-groups">
                      User Groups
                    </label>
                    <input
                      id="card-user-groups"
                      type="text"
                      className="auth-editor-input"
                      value={userGroups}
                      onChange={(e) => { setUserGroups(e.target.value); }}
                      disabled={isSubmitting}
                      placeholder="e.g. Engineering, Product, Domain Users"
                    />
                  </div>
                  <div className="auth-field-helper">
                    Members of these groups receive WORKSPACE_MEMBER automatically.
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {/* SECTION 2: OPTIONAL & ADVANCED SETTINGS ACCORDION */}
          <details className="auth-advanced-accordion" open={isEdit}>
            <summary className="auth-advanced-summary">
              Optional &amp; Advanced Settings
            </summary>

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
                placeholder="e.g. oauth1, google-oauth, ad-ldap"
                maxLength={48}
              />
            </div>
            {fieldErrors.slug ? (
              <div className="auth-editor-error">{fieldErrors.slug}</div>
            ) : null}
            <div className="auth-field-helper">
              Unique identifier slug for URLs and card references. Auto-generated if left blank.
            </div>

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
                placeholder="e.g. Google Workspace, Corporate Active Directory"
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
                placeholder="e.g. Sign in with your work email (@corp.com)"
                maxLength={120}
              />
            </div>
            {fieldErrors.buttonSubtext ? (
              <div className="auth-editor-error">{fieldErrors.buttonSubtext}</div>
            ) : null}
            <div className="auth-field-helper">
              Subtitle displayed directly beneath the login button to guide users.
            </div>

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
                <option value="google">🔴 Google</option>
                <option value="github">🐙 GitHub</option>
                <option value="active-directory">🏢 Active Directory</option>
                <option value="ldap">🗂️ LDAP</option>
                <option value="server">🖥️ Server</option>
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

            {/* Provider specific optional fields */}
            {providerKind === 'OIDC' || providerKind === 'OAUTH2' ? (
              <div>
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
                  />
                </div>
                {fieldErrors.issuerUrl ? (
                  <div className="auth-editor-error">{fieldErrors.issuerUrl}</div>
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
                  <label className="auth-editor-label" htmlFor="card-token-auth">
                    Token Auth Method
                  </label>
                  <select
                    id="card-token-auth"
                    className="auth-editor-select"
                    value={tokenAuthMethod}
                    onChange={(e) => {
                      setTokenAuthMethod(e.target.value as 'client_secret_basic' | 'private_key_jwt');
                    }}
                    disabled={isSubmitting}
                  >
                    <option value="client_secret_basic">client_secret_basic</option>
                    <option value="private_key_jwt">private_key_jwt (Asymmetric)</option>
                  </select>
                </div>
              </div>
            ) : providerKind === 'LDAP' ? (
              <div>
                <div className="auth-editor-prop-row">
                  <label className="auth-editor-label" htmlFor="card-starttls">
                    StartTLS
                  </label>
                  <input
                    id="card-starttls"
                    type="checkbox"
                    checked={startTls}
                    onChange={(e) => { setStartTls(e.target.checked); }}
                    disabled={isSubmitting || serverUrl.trim().toLowerCase().startsWith('ldap://')}
                  />
                </div>

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
                    placeholder="(&(objectClass=person)(uid={username}))"
                  />
                </div>

                <div className="auth-editor-prop-row">
                  <label className="auth-editor-label" htmlFor="card-subject-attr">
                    Subject Attribute
                  </label>
                  <input
                    id="card-subject-attr"
                    type="text"
                    className="auth-editor-input"
                    value={subjectAttribute}
                    onChange={(e) => { setSubjectAttribute(e.target.value); }}
                    disabled={isSubmitting}
                    placeholder="objectGUID (AD) or entryUUID (OpenLDAP)"
                  />
                </div>

                <div className="auth-editor-prop-row">
                  <label className="auth-editor-label" htmlFor="card-email-attr">
                    Email Attribute
                  </label>
                  <input
                    id="card-email-attr"
                    type="text"
                    className="auth-editor-input"
                    value={emailAttribute}
                    onChange={(e) => { setEmailAttribute(e.target.value); }}
                    disabled={isSubmitting}
                    placeholder="mail"
                  />
                </div>

                <div className="auth-editor-prop-row">
                  <label className="auth-editor-label" htmlFor="card-display-attr">
                    Full Name Attribute
                  </label>
                  <input
                    id="card-display-attr"
                    type="text"
                    className="auth-editor-input"
                    value={displayNameAttribute}
                    onChange={(e) => { setDisplayNameAttribute(e.target.value); }}
                    disabled={isSubmitting}
                    placeholder="displayName (AD) or cn (OpenLDAP)"
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
                    placeholder="64-character hex digest"
                    maxLength={64}
                  />
                </div>
                {fieldErrors.spkiPin ? (
                  <div className="auth-editor-error">{fieldErrors.spkiPin}</div>
                ) : null}

                <div className="auth-editor-prop-row">
                  <label className="auth-editor-label" htmlFor="card-ca-pem">
                    CA Certificate PEM
                  </label>
                  <textarea
                    id="card-ca-pem"
                    className="auth-editor-textarea"
                    value={caPem}
                    onChange={(e) => { setCaPem(e.target.value); }}
                    disabled={isSubmitting}
                    placeholder="-----BEGIN CERTIFICATE----- ... -----END CERTIFICATE-----"
                    rows={3}
                  />
                </div>
              </div>
            ) : null}
          </details>
          </>
        )}

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
            >
              {isSubmitting ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Card'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
