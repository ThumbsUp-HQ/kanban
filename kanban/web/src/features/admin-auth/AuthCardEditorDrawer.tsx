import React, { useState, useEffect, useRef, type JSX } from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import {
  Google,
  GitHub,
  ActiveDirectory,
  Ldap,
  Key,
  renderAuthIcon,
} from '../../components/icons/KanbanIcons';
import type {
  AdminAuthCard,
  CreateAuthCardPayload,
  UpdateAuthCardPayload,
  ProviderKind,
  GoogleOAuthJsonPreviewResponse,
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
  const [issuerUrl, setIssuerUrl] = useState(() => (typeof card?.public_config.issuer === 'string' ? card.public_config.issuer : (typeof card?.public_config.issuer_url === 'string' ? card.public_config.issuer_url : '')));
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
    card?.public_config.client_auth === 'private_key_jwt' || card?.public_config.token_auth_method === 'private_key_jwt'
      ? 'private_key_jwt'
      : 'client_secret_basic',
  );

  // LDAP fields
  const [serverUrl, setServerUrl] = useState(() => (typeof card?.public_config.url === 'string' ? card.public_config.url : (typeof card?.public_config.server_url === 'string' ? card.public_config.server_url : '')));
  const [startTls, setStartTls] = useState(() => Boolean(card?.public_config.transport_mode === 'starttls' || card?.public_config.start_tls));
  const [bindDn, setBindDn] = useState(() => (typeof card?.public_config.service_bind_dn === 'string' ? card.public_config.service_bind_dn : (typeof card?.public_config.bind_dn === 'string' ? card.public_config.bind_dn : '')));
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


  // Google OAuth JSON Importer state (KB-AUTH-JSON)
  const [googleJsonPasteOpen, setGoogleJsonPasteOpen] = useState(false);
  const [googleJsonPasteText, setGoogleJsonPasteText] = useState('');
  const [googleJsonError, setGoogleJsonError] = useState<string | null>(null);
  const [googleJsonPreview, setGoogleJsonPreview] = useState<GoogleOAuthJsonPreviewResponse | null>(null);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  // Secret input and write-only state
  const [secretInput, setSecretInput] = useState('');
  const [replaceSecret, setReplaceSecret] = useState(() => !card);
  const [copiedCallback, setCopiedCallback] = useState(false);

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

    setIssuerUrl(typeof pub?.issuer === 'string' ? pub.issuer : (typeof pub?.issuer_url === 'string' ? pub.issuer_url : ''));
    setClientId(typeof pub?.client_id === 'string' ? pub.client_id : '');
    setAuthorizationEndpoint(typeof pub?.authorization_endpoint === 'string' ? pub.authorization_endpoint : '');
    setTokenEndpoint(typeof pub?.token_endpoint === 'string' ? pub.token_endpoint : '');
    setUserinfoEndpoint(typeof pub?.userinfo_endpoint === 'string' ? pub.userinfo_endpoint : '');

    const rawScopes = pub?.scopes;
    setScopes(Array.isArray(rawScopes) ? rawScopes.join(', ') : (typeof rawScopes === 'string' ? rawScopes : 'openid, profile, email'));
    setTokenAuthMethod(
      pub?.client_auth === 'private_key_jwt' || pub?.token_auth_method === 'private_key_jwt'
        ? 'private_key_jwt'
        : 'client_secret_basic',
    );

    setServerUrl(typeof pub?.url === 'string' ? pub.url : (typeof pub?.server_url === 'string' ? pub.server_url : ''));
    setStartTls(Boolean(pub?.transport_mode === 'starttls' || pub?.start_tls));
    setBindDn(typeof pub?.service_bind_dn === 'string' ? pub.service_bind_dn : (typeof pub?.bind_dn === 'string' ? pub.bind_dn : ''));
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


  // Accessibility: focus trap & initial focus (KB-AUTH-JSON)
  useEffect(() => {
    if (!isOpen) return;
    const titleEl = document.getElementById("drawer-title");
    titleEl?.focus();

    const handleTabKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || !drawerRef.current) return;
      const focusable = drawerRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          last?.focus();
          e.preventDefault();
        }
      } else {
        if (document.activeElement === last) {
          first?.focus();
          e.preventDefault();
        }
      }
    };

    window.addEventListener("keydown", handleTabKey);
    return () => {
      window.removeEventListener("keydown", handleTabKey);
    };
  }, [isOpen]);

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


  const processGoogleJsonContent = (rawText: string) => {
    setGoogleJsonError(null);
    try {
      if (rawText.length > 32768) {
        setGoogleJsonError('Google OAuth JSON exceeds maximum allowed size of 32,768 bytes.');
        return;
      }
      interface GoogleClientSecretWeb {
        client_id?: unknown;
        client_secret?: unknown;
        auth_uri?: unknown;
        token_uri?: unknown;
        project_id?: unknown;
        redirect_uris?: unknown;
        javascript_origins?: unknown;
      }
      interface GoogleClientSecretPayload {
        web?: GoogleClientSecretWeb;
        installed?: unknown;
      }
      const parsed = JSON.parse(rawText) as GoogleClientSecretPayload;
      if (parsed.installed && !parsed.web) {
        setGoogleJsonError('Google OAuth JSON is for an Installed/Desktop client; create a Web application OAuth client in Google Cloud Console.');
        return;
      }
      if (!parsed.web || typeof parsed.web !== 'object') {
        setGoogleJsonError("Google OAuth JSON must contain a top-level 'web' configuration object.");
        return;
      }
      const web = parsed.web;
      if (typeof web.client_id !== 'string' || !web.client_id) {
        setGoogleJsonError("Field 'client_id' is missing or invalid in Google JSON.");
        return;
      }
      if (typeof web.client_secret !== 'string' || !web.client_secret) {
        setGoogleJsonError("Field 'client_secret' is missing or invalid in Google JSON.");
        return;
      }

      const allowedAuth = ['https://accounts.google.com/o/oauth2/auth', 'https://accounts.google.com/o/oauth2/v2/auth'];
      const allowedToken = ['https://oauth2.googleapis.com/token', 'https://accounts.google.com/o/oauth2/token', 'https://www.googleapis.com/oauth2/v4/token'];
      if (typeof web.auth_uri === 'string' && !allowedAuth.includes(web.auth_uri)) {
        setGoogleJsonError("Field 'auth_uri' does not match allowed Google authorization endpoints.");
        return;
      }
      if (typeof web.token_uri === 'string' && !allowedToken.includes(web.token_uri)) {
        setGoogleJsonError("Field 'token_uri' does not match allowed Google token endpoints.");
        return;
      }

      const activeSlug = slug.trim() || 'google-oauth';
      const expectedCallback = `${window.location.origin}/api/v1/auth/oidc/${activeSlug}/callback`;
      const redirectUris: string[] = Array.isArray(web.redirect_uris)
        ? web.redirect_uris.filter((item): item is string => typeof item === 'string')
        : [];
      const isMatched = redirectUris.includes(expectedCallback);

      setClientId(web.client_id);
      setSecretInput(web.client_secret);
      setReplaceSecret(true);
      setIssuerUrl('https://accounts.google.com');
      setProviderKind('OIDC');
      setIconPreset('google');
      if (!slug.trim()) setSlug('google-oauth');
      if (!displayName.trim()) setDisplayName('Google Workspace');
      if (!buttonSubtext.trim()) setButtonSubtext('Sign in with your Google account');
      setScopes('openid, profile, email');

      setGoogleJsonPreview({
        client_id: web.client_id,
        project_id: typeof web.project_id === 'string' ? web.project_id : null,
        issuer: 'https://accounts.google.com',
        redirect_uris: redirectUris,
        javascript_origins: Array.isArray(web.javascript_origins)
          ? web.javascript_origins.filter((item): item is string => typeof item === 'string')
          : [],
        expected_callback_uri: expectedCallback,
        callback_uri_matched: isMatched,
        has_client_secret: true,
      });

      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      setGoogleJsonPasteText('');
    } catch (err: unknown) {
      setGoogleJsonError('Failed to parse JSON: ' + (err instanceof Error ? err.message : String(err)));
    }
  };

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
        client_auth: tokenAuthMethod,
        ...(issuerUrl.trim() ? { issuer: issuerUrl.trim() } : {}),
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
        transport_mode: transportMode,
        service_bind_dn: bindDn.trim(),
        base_dn: baseDn.trim(),
        user_search_filter: userFilter.trim(),
        subject_attribute: subjectAttribute.trim() || 'objectGUID',
        email_attribute: emailAttribute.trim() || 'mail',
        display_name_attribute: displayNameAttribute.trim() || 'displayName',
        access_mode: accessPolicyMode === 'restricted' ? 'group_restricted' : 'any_user',
        admin_groups: accessPolicyMode === 'restricted' ? parseList(adminGroups) : [],
        user_groups: accessPolicyMode === 'restricted' ? parseList(userGroups) : [],
        ...(caPem.trim() ? { ca_cert_pem: caPem.trim() } : {}),
        ...(spkiPin.trim() ? { spki_sha256_pins: [spkiPin.trim()] } : {}),
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
          ...(secretInput.trim() ? { secret: secretInput.trim() } : {}),
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
                onClick={() => { applyPreset('google'); }} aria-pressed={activePreset === 'google'}
              >
                <Google size={14} className="auth-preset-icon" />
                <span>Google (OAuth 2.0)</span>
              </button>
              <button
                type="button"
                className={`auth-preset-btn ${activePreset === 'github' ? 'auth-preset-btn--active' : ''}`}
                onClick={() => { applyPreset('github'); }} aria-pressed={activePreset === 'github'}
              >
                <GitHub size={14} className="auth-preset-icon" />
                <span>GitHub (OAuth 2.0)</span>
              </button>
              <button
                type="button"
                className={`auth-preset-btn ${activePreset === 'active-directory' ? 'auth-preset-btn--active' : ''}`}
                onClick={() => { applyPreset('active-directory'); }} aria-pressed={activePreset === 'active-directory'}
              >
                <ActiveDirectory size={14} className="auth-preset-icon" />
                <span>Active Directory (sAMAccountName)</span>
              </button>
              <button
                type="button"
                className={`auth-preset-btn ${activePreset === 'openldap' ? 'auth-preset-btn--active' : ''}`}
                onClick={() => { applyPreset('openldap'); }} aria-pressed={activePreset === 'openldap'}
              >
                <Ldap size={14} className="auth-preset-icon" />
                <span>Standard LDAP (OpenLDAP)</span>
              </button>
              <button
                type="button"
                className={`auth-preset-btn ${activePreset === 'custom-oauth' ? 'auth-preset-btn--active' : ''}`}
                onClick={() => { applyPreset('custom-oauth'); }} aria-pressed={activePreset === 'custom-oauth'}
              >
                <Key size={14} className="auth-preset-icon" />
                <span>Custom OAuth 2.0 / OIDC</span>
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

              {/* Google OAuth JSON Importer Section (KB-AUTH-JSON) */}
              {(providerKind === 'OIDC' || providerKind === 'OAUTH2') && (
                <div className="auth-google-json-section" data-testid="google-json-import-section">
                  <div className="auth-google-json-header">
                    <span className="auth-google-json-title">
                      <Google size={14} />
                      <span>Google OAuth Client Secret JSON (client_secret_*.json)</span>
                    </span>
                    <button
                      type="button"
                      className="auth-btn-secondary"
                      data-testid="google-json-paste-toggle"
                      aria-expanded={googleJsonPasteOpen}
                      onClick={() => {
                        setGoogleJsonPasteOpen(!googleJsonPasteOpen);
                      }}
                    >
                      {googleJsonPasteOpen ? 'Hide Paste' : 'Paste JSON'}
                    </button>
                  </div>

                  {googleJsonError && (
                    <div className="auth-editor-error" role="alert" data-testid="google-json-error">
                      {googleJsonError}
                    </div>
                  )}

                  {/* Drag-and-drop & File Upload Button */}
                  <div
                    className={`auth-google-json-dropzone ${isDraggingOver ? 'auth-google-json-dropzone--active' : ''}`}
                    data-testid="google-json-dropzone"
                    onDragOver={(e) => {
                      e.preventDefault();
                      setIsDraggingOver(true);
                    }}
                    onDragLeave={() => {
                      setIsDraggingOver(false);
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      setIsDraggingOver(false);
                      const file = e.dataTransfer.files[0];
                      if (file) {
                        const reader = new FileReader();
                        reader.onload = (ev) => {
                          const text = ev.target?.result;
                          if (typeof text === 'string') {
                            processGoogleJsonContent(text);
                          }
                        };
                        reader.readAsText(file);
                      }
                    }}
                  >
                    <p>Drag and drop <code>client_secret_*.json</code> here, or</p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".json,application/json"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          const reader = new FileReader();
                          reader.onload = (ev) => {
                            const text = ev.target?.result;
                            if (typeof text === 'string') {
                              processGoogleJsonContent(text);
                            }
                          };
                          reader.readAsText(file);
                        }
                      }}
                    />
                    <button
                      type="button"
                      className="auth-btn-secondary"
                      data-testid="google-json-upload-btn"
                      style={{ marginTop: '8px' }}
                      onClick={() => {
                        fileInputRef.current?.click();
                      }}
                    >
                      Upload JSON File
                    </button>
                  </div>

                  {/* Paste JSON Disclosure */}
                  {googleJsonPasteOpen && (
                    <div className="auth-google-json-paste-box">
                      <textarea
                        className="auth-google-json-textarea"
                        placeholder="Paste full Google Cloud Console web client JSON here..."
                        value={googleJsonPasteText}
                        onChange={(e) => {
                          setGoogleJsonPasteText(e.target.value);
                        }}
                        aria-label="Paste Google Cloud Console client JSON"
                      />
                      <button
                        type="button"
                        className="auth-studio-add-btn"
                        data-testid="google-json-apply-btn"
                        onClick={() => {
                          processGoogleJsonContent(googleJsonPasteText);
                        }}
                      >
                        Apply Google JSON
                      </button>
                    </div>
                  )}

                  {/* Status announcement and redirect URI match feedback */}
                  {googleJsonPreview && (
                    googleJsonPreview.callback_uri_matched ? (
                      <div
                        role="status"
                        aria-live="polite"
                        className="auth-google-json-status auth-google-json-status--ok"
                        data-testid="google-json-redirect-ok"
                      >
                        <span>✓ Authorized Redirect URI matched in uploaded Google client configuration.</span>
                      </div>
                    ) : (
                      <div
                        role="status"
                        aria-live="polite"
                        className="auth-google-json-status auth-google-json-status--warning"
                        data-testid="google-json-redirect-warning"
                      >
                        <strong>⚠️ Authorized Redirect URI mismatch</strong>
                        <span>
                          Expected: <code>{googleJsonPreview.expected_callback_uri}</code>
                        </span>
                        <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
                          <button
                            type="button"
                            className="auth-btn-secondary"
                            onClick={() => {
                              if (googleJsonPreview.expected_callback_uri) {
                                void navigator.clipboard.writeText(googleJsonPreview.expected_callback_uri);
                              }
                            }}
                          >
                            Copy Expected Callback URL
                          </button>
                        </div>
                        {googleJsonPreview.redirect_uris.length > 0 && (
                          <details style={{ marginTop: "6px" }}>
                            <summary style={{ cursor: "pointer" }}>
                              URIs found in Google JSON ({googleJsonPreview.redirect_uris.length})
                            </summary>
                            <ul className="auth-google-json-uris-list">
                              {googleJsonPreview.redirect_uris.map((uri, idx) => (
                                <li key={idx}>{uri}</li>
                              ))}
                            </ul>
                          </details>
                        )}
                      </div>
                    )
                  )}
                </div>
              )}


              {providerKind === 'OIDC' || providerKind === 'OAUTH2' ? (
            <div>
              <div className="auth-editor-prop-row">
                <label className="auth-editor-label" htmlFor="card-callback-url">
                  Authorized Redirect URI (Callback URL)
                </label>
                <div className="auth-editor-input-group">
                  <input
                    id="card-callback-url"
                    data-testid="oauth-callback-url"
                    type="text"
                    className="auth-editor-input"
                    value={
                      `${window.location.origin}/api/v1/auth/oidc/${slug.trim() || 'oauth1'}/callback`
                    }
                    readOnly
                  />
                  <button
                    type="button"
                    className="auth-btn-secondary"
                    onClick={() => {
                      const url = `${window.location.origin}/api/v1/auth/oidc/${slug.trim() || 'oauth1'}/callback`;
                      void navigator.clipboard.writeText(url);
                      setCopiedCallback(true);
                      setTimeout(() => { setCopiedCallback(false); }, 2000);
                    }}
                    data-testid="copy-callback-url-btn"
                  >
                    {copiedCallback ? 'Copied!' : 'Copy'}
                  </button>
                </div>
              </div>

              <div className="auth-editor-prop-row">
                <span className="auth-editor-label">Authorized JavaScript Origin</span>
                <span className="auth-field-helper" data-testid="oauth-js-origin">
                  {window.location.origin}
                </span>
              </div>

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
              <div className="auth-editor-input-group">
                <select
                  id="card-icon-preset"
                  className="auth-editor-select"
                  value={iconPreset}
                  onChange={(e) => { setIconPreset(e.target.value); }}
                  disabled={isSubmitting}
                >
                  <option value="shield">Shield</option>
                  <option value="key">Key</option>
                  <option value="lock">Lock</option>
                  <option value="globe">Globe</option>
                  <option value="google">Google</option>
                  <option value="github">GitHub</option>
                  <option value="active-directory">Active Directory</option>
                  <option value="ldap">LDAP</option>
                  <option value="local-admin">Local Administrator</option>
                </select>
                <span className="auth-card-icon-preview" aria-hidden="true">
                  {renderAuthIcon(iconPreset, 20)}
                </span>
              </div>
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
