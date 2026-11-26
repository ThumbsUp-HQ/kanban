// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX } from 'react';
import { FieldHelpHint } from '../../components/help/FieldHelpHint';
import { AdvancedSection } from '../../ui/AdvancedSection';
import { useAal2DirtyKeepalive } from '../../components/help/WebSudoModalHost';
import { isAal2StepUpCancelled } from '../../api/client';
import {
  createAiProvider,
  updateAiProvider,
  probeAiModels,
  testAiConnection,
  isLocalEndpoint,
  inferResidencyTier,
  type ProviderConfigPublic,
  type ProviderConfigCreate,
  type ProviderConfigUpdate,
  type ProviderProbeRequest,
} from './aiAdminApi';

interface AiProviderEditorDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  provider: ProviderConfigPublic | null;
  airGapMode: boolean;
  onSaved?: ((saved?: ProviderConfigPublic) => void) | undefined;
  providersCount?: number | undefined;
  projectId?: string | null | undefined;
  workspaceSlug?: string | undefined;
}

interface TestStatusState {
  kind: 'idle' | 'loading' | 'success' | 'error';
  message: string | null;
}

export const MASK_BULLET = '•';

export function computeNextApiKey(
  prevKey: string,
  nextDisplay: string,
  cursorPos?: number | null,
): string {
  if (!nextDisplay) {
    return '';
  }
  if (!prevKey) {
    return nextDisplay;
  }
  const oldMask = MASK_BULLET.repeat(prevKey.length);
  if (nextDisplay === oldMask) {
    return prevKey;
  }

  // If nextDisplay consists solely of mask bullets and is shorter than oldMask,
  // one or more characters were deleted (e.g. Backspace or Delete).
  const isAllBullets = Array.from(nextDisplay).every((ch) => ch === MASK_BULLET);
  if (isAllBullets && nextDisplay.length < oldMask.length) {
    const deletedCount = oldMask.length - nextDisplay.length;
    if (cursorPos !== undefined && cursorPos !== null && cursorPos >= 0 && cursorPos <= prevKey.length) {
      return prevKey.slice(0, cursorPos) + prevKey.slice(cursorPos + deletedCount);
    }
    return prevKey.slice(0, prevKey.length - deletedCount);
  }

  // General diffing: common prefix and suffix
  let prefixLen = 0;
  while (
    prefixLen < oldMask.length &&
    prefixLen < nextDisplay.length &&
    oldMask[prefixLen] === nextDisplay[prefixLen]
  ) {
    prefixLen++;
  }

  let suffixLen = 0;
  while (
    suffixLen < oldMask.length - prefixLen &&
    suffixLen < nextDisplay.length - prefixLen &&
    oldMask[oldMask.length - 1 - suffixLen] === nextDisplay[nextDisplay.length - 1 - suffixLen]
  ) {
    suffixLen++;
  }

  const inserted = nextDisplay.slice(prefixLen, nextDisplay.length - suffixLen);
  const delEnd = prevKey.length - suffixLen;
  return prevKey.slice(0, prefixLen) + inserted + prevKey.slice(delEnd);
}

function AiProviderEditorContent({
  onClose,
  provider,
  airGapMode,
  onSaved,
  providersCount,
  projectId,
  workspaceSlug,
}: {
  onClose: () => void;
  provider: ProviderConfigPublic | null;
  airGapMode: boolean;
  onSaved?: ((saved?: ProviderConfigPublic) => void) | undefined;
  providersCount?: number | undefined;
  projectId?: string | null | undefined;
  workspaceSlug?: string | undefined;
}): JSX.Element {
  const isEditing = provider !== null;

  const defaultKind = airGapMode ? 'ollama' : 'openai';
  const defaultDisplayName = airGapMode ? 'Local Ollama Runtime' : 'OpenAI / OpenAI-Compatible';
  const defaultBaseUrl = airGapMode ? 'http://127.0.0.1:11434' : 'https://api.openai.com/v1';
  const [providerKind, setProviderKind] = useState<string>(
    provider?.provider_kind ?? defaultKind,
  );
  const [displayName, setDisplayName] = useState<string>(
    provider?.display_name ?? defaultDisplayName,
  );
  const [baseUrl, setBaseUrl] = useState<string>(
    provider?.base_url ?? defaultBaseUrl,
  );
  const [modelAllowlist, setModelAllowlist] = useState<string>(
    provider?.model_allowlist ? provider.model_allowlist.join(', ') : '',
  );

  const initialTimeoutMs =
    typeof provider?.settings.timeout_ms === 'number'
      ? provider.settings.timeout_ms
      : 30000;
  const [timeoutMs, setTimeoutMs] = useState<number>(initialTimeoutMs);

  const initialTemp = typeof provider?.settings.temperature === 'number' ? provider.settings.temperature : 0.7;
  const [temperature, setTemperature] = useState<number>(initialTemp);
  const [temperatureModified, setTemperatureModified] = useState<boolean>(false);

  const initialTopP = typeof provider?.settings.top_p === 'number' ? provider.settings.top_p : 1.0;
  const [topP, setTopP] = useState<number>(initialTopP);
  const [topPModified, setTopPModified] = useState<boolean>(false);

  const initialMaxTokens = typeof provider?.settings.max_tokens === 'number' ? provider.settings.max_tokens : 4096;
  const [maxTokens, setMaxTokens] = useState<number>(initialMaxTokens);
  const [maxTokensModified, setMaxTokensModified] = useState<boolean>(false);

  const initialMtlsCert = typeof provider?.settings.mtls_client_cert_pem === 'string' ? provider.settings.mtls_client_cert_pem : '';
  const [mtlsCertPem, setMtlsCertPem] = useState<string>(initialMtlsCert);

  const normalizeResidencyTier = (rawTier: string | null | undefined): string => {
    if (!rawTier) return airGapMode ? 'local_only' : 'cloud_standard';
    if (rawTier === 'cloud') return 'cloud_standard';
    if (rawTier === 'local') return 'local_only';
    return rawTier;
  };

  const initialResidency = normalizeResidencyTier(provider?.residency_tier);
  const [residencyTier, setResidencyTier] = useState<string>(initialResidency);
  const [residencyTierManual, setResidencyTierManual] = useState<boolean>(isEditing);

  const [apiKey, setApiKey] = useState<string>('');
  const [showApiKey, setShowApiKey] = useState<boolean>(false);
  const [clearExistingKey, setClearExistingKey] = useState<boolean>(false);

  const supportsWebkitTextSecurity =
    typeof CSS !== 'undefined' &&
    typeof CSS.supports === 'function' &&
    CSS.supports('-webkit-text-security', 'disc');

  const displayKeyValue = !supportsWebkitTextSecurity && !showApiKey
    ? MASK_BULLET.repeat(apiKey.length)
    : apiKey;

  const handleApiKeyChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const nextRaw = e.target.value;
    setClearExistingKey(false);
    if (!supportsWebkitTextSecurity && !showApiKey) {
      const nextKey = computeNextApiKey(apiKey, nextRaw, e.target.selectionStart);
      setApiKey(nextKey);
    } else {
      setApiKey(nextRaw);
    }
  };
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Probe models state
  const [isProbing, setIsProbing] = useState<boolean>(false);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [probedModels, setProbedModels] = useState<string[] | null>(null);
  const [probedFilter, setProbedFilter] = useState<string>('');

  // Connection test state
  const [isTestingConnection, setIsTestingConnection] = useState<boolean>(false);
  const [testStatus, setTestStatus] = useState<TestStatusState>({ kind: 'idle', message: null });

  const isCloudKind = providerKind === 'openai' || providerKind === 'gemini';
  const isLocal = isLocalEndpoint(providerKind, baseUrl);

  const isDirty = React.useMemo(() => {
    if (!provider) {
      return Boolean(
        apiKey.trim() ||
        providerKind !== defaultKind ||
        displayName.trim() !== defaultDisplayName ||
        baseUrl.trim() !== defaultBaseUrl ||
        modelAllowlist.trim() !== '' ||
        mtlsCertPem.trim() !== '' ||
        timeoutMs !== 30000 ||
        temperatureModified ||
        topPModified ||
        maxTokensModified
      );
    }
    const initialModelAllowlist = provider.model_allowlist.join(', ');
    return (
      displayName !== provider.display_name ||
      apiKey.trim() !== '' ||
      baseUrl !== (provider.base_url ?? '') ||
      clearExistingKey ||
      residencyTier !== initialResidency ||
      providerKind !== provider.provider_kind ||
      modelAllowlist !== initialModelAllowlist ||
      timeoutMs !== initialTimeoutMs ||
      temperatureModified ||
      topPModified ||
      maxTokensModified ||
      mtlsCertPem !== initialMtlsCert
    );
  }, [
    provider,
    apiKey,
    providerKind,
    defaultKind,
    displayName,
    defaultDisplayName,
    baseUrl,
    defaultBaseUrl,
    modelAllowlist,
    mtlsCertPem,
    initialMtlsCert,
    timeoutMs,
    initialTimeoutMs,
    temperatureModified,
    topPModified,
    maxTokensModified,
    clearExistingKey,
    residencyTier,
    initialResidency,
  ]);

  useAal2DirtyKeepalive(isDirty);

  const handleKindChange = (newKind: string): void => {
    setProviderKind(newKind);
    if (airGapMode && (newKind === 'openai' || newKind === 'gemini')) {
      setError('Air-Gap mode prohibits configuring cloud providers (OpenAI, Gemini). Use local Ollama.');
    } else {
      setError(null);
    }

    if (!isEditing) {
      setModelAllowlist('');
      setProbedModels(null);
      if (newKind === 'openai') {
        setDisplayName('OpenAI / OpenAI-Compatible');
        setBaseUrl('https://api.openai.com/v1');
        if (!residencyTierManual) {
          setResidencyTier('cloud_standard');
        }
      } else if (newKind === 'gemini') {
        setDisplayName('Google Gemini Workspace');
        setBaseUrl('https://generativelanguage.googleapis.com');
        if (!residencyTierManual) {
          setResidencyTier('cloud_standard');
        }
      } else if (newKind === 'ollama') {
        setDisplayName('Local Ollama Runtime');
        setBaseUrl('http://127.0.0.1:11434');
        if (!residencyTierManual) {
          setResidencyTier('local_only');
        }
      }
    }
  };

  const applyPreset = (kind: 'ollama' | 'openai' | 'gemini'): void => {
    if (isEditing) return;
    setError(null);
    setProviderKind(kind);
    setProbedModels(null);
    if (kind === 'ollama') {
      setDisplayName('Local Ollama Runtime');
      setBaseUrl('http://127.0.0.1:11434');
      setModelAllowlist('llama3.2, qwen2.5-coder');
      if (!residencyTierManual) {
        setResidencyTier('local_only');
      }
    } else if (kind === 'openai') {
      setDisplayName('OpenAI / OpenAI-Compatible');
      setBaseUrl('https://api.openai.com/v1');
      setModelAllowlist('gpt-4o, gpt-4o-mini');
      if (!residencyTierManual) {
        setResidencyTier('cloud_standard');
      }
    } else {
      setDisplayName('Google Gemini Workspace');
      setBaseUrl('https://generativelanguage.googleapis.com');
      setModelAllowlist('gemini-2.5-pro, gemini-2.5-flash');
      if (!residencyTierManual) {
        setResidencyTier('cloud_standard');
      }
    }
  };

  const handleBaseUrlChange = (newUrl: string): void => {
    setBaseUrl(newUrl);
    if (!residencyTierManual) {
      setResidencyTier(inferResidencyTier(providerKind, newUrl));
    }
  };

  const getSelectedModelsList = (): string[] =>
    modelAllowlist
      .split(',')
      .map((m) => m.trim())
      .filter((m) => m.length > 0);

  const toggleModel = (model: string): void => {
    const current = getSelectedModelsList();
    const exists = current.includes(model);
    const next = exists ? current.filter((m) => m !== model) : [...current, model];
    setModelAllowlist(next.join(', '));
  };

  const handleSelectAllProbed = (): void => {
    setModelAllowlist((probedModels ?? []).join(', '));
  };

  const handleClearModels = (): void => {
    setModelAllowlist('');
  };

  const handleProbeModels = async (): Promise<void> => {
    try {
      setIsProbing(true);
      setProbeError(null);
      const isEndpointModified =
        provider !== null &&
        (baseUrl !== (provider.base_url ?? '') || providerKind !== provider.provider_kind);
      const hasKeyOrNotNeeded = isLocal || apiKey.trim().length > 0;
      const useDraftEndpoint = !provider || (isEndpointModified && hasKeyOrNotNeeded);

      const payload: ProviderProbeRequest = useDraftEndpoint
        ? {
            provider_kind: providerKind,
            base_url: baseUrl.trim() || null,
            api_key: apiKey.trim() || null,
            settings_json: { timeout_ms: timeoutMs },
            ...(projectId ? { project_id: projectId } : {}),
          }
        : {
            ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
            settings_json: { timeout_ms: timeoutMs },
            ...(projectId ? { project_id: projectId } : {}),
          };
      const targetProviderId = useDraftEndpoint ? undefined : provider.id;
      const res = workspaceSlug
        ? await probeAiModels(payload, targetProviderId, workspaceSlug)
        : await probeAiModels(payload, targetProviderId);
      if (res.ok) {
        setProbedModels(res.models);
        if (res.models.length === 0) {
          setProbeError('Connected successfully, but 0 models were discovered.');
        } else {
          setModelAllowlist(res.models.join(', '));
        }
      } else {
        const msg = res.error_code === 'AIR_GAP_EGRESS_DENIED'
          ? (res.message ?? 'Egress denied by Air-Gap policy: cloud endpoints cannot be contacted.')
          : (res.message ?? res.error_code ?? 'Model probing failed');
        setProbeError(msg);
      }
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      setProbeError(err instanceof Error ? err.message : 'Failed to probe models');
    } finally {
      setIsProbing(false);
    }
  };

  const handleTestConnection = async (): Promise<void> => {
    try {
      setIsTestingConnection(true);
      setTestStatus({ kind: 'loading', message: 'Testing connection...' });
      const isEndpointModified =
        provider !== null &&
        (baseUrl !== (provider.base_url ?? '') || providerKind !== provider.provider_kind);
      const hasKeyOrNotNeeded = isLocal || apiKey.trim().length > 0;
      const useDraftEndpoint = !provider || (isEndpointModified && hasKeyOrNotNeeded);

      const payload: ProviderProbeRequest = useDraftEndpoint
        ? {
            provider_kind: providerKind,
            base_url: baseUrl.trim() || null,
            api_key: apiKey.trim() || null,
            settings_json: { timeout_ms: timeoutMs },
            ...(projectId ? { project_id: projectId } : {}),
          }
        : {
            ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
            settings_json: { timeout_ms: timeoutMs },
            ...(projectId ? { project_id: projectId } : {}),
          };
      const targetProviderId = useDraftEndpoint ? undefined : provider.id;
      const res = workspaceSlug
        ? await testAiConnection(payload, targetProviderId, workspaceSlug)
        : await testAiConnection(payload, targetProviderId);
      if (res.ok) {
        setTestStatus({
          kind: 'success',
          message: `Connected in ${String(Math.round(res.latency_ms))}ms - ${String(res.model_count)} models available`,
        });
      } else {
        const msg = res.error_code === 'AIR_GAP_EGRESS_DENIED'
          ? (res.message ?? 'Egress denied by Air-Gap policy: cloud endpoints cannot be contacted.')
          : `${res.error_code ?? 'ERROR'}${res.message ? ` - ${res.message}` : ''}`;
        setTestStatus({
          kind: 'error',
          message: `Connection failed: ${msg}`,
        });
      }
    } catch (err: unknown) {
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      setTestStatus({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Connection test failed',
      });
    } finally {
      setIsTestingConnection(false);
    }
  };

  const handleSubmit = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();
    if (!displayName.trim()) {
      setError('Display name is required');
      return;
    }

    if (airGapMode && isCloudKind) {
      setError('Air-Gap mode prohibits configuring cloud providers (OpenAI, Gemini). Use local Ollama.');
      return;
    }

    const models = getSelectedModelsList();

    try {
      setIsSaving(true);
      setError(null);

      const computeSettings = (baseSettings?: Record<string, unknown>) => {
        const s: Record<string, unknown> = {
          ...(baseSettings ?? {}),
          timeout_ms: timeoutMs,
        };
        if (temperatureModified || (baseSettings && 'temperature' in baseSettings)) {
          s.temperature = temperature;
        }
        if (topPModified || (baseSettings && 'top_p' in baseSettings)) {
          s.top_p = topP;
        }
        if (maxTokensModified || (baseSettings && 'max_tokens' in baseSettings)) {
          s.max_tokens = maxTokens;
        }
        if (mtlsCertPem.trim()) {
          s.mtls_client_cert_pem = mtlsCertPem.trim();
        }
        return s;
      };

      let saved: ProviderConfigPublic | undefined;
      if (provider) {
        const payload: ProviderConfigUpdate = {
          display_name: displayName.trim(),
          model_allowlist: models,
          residency_tier: residencyTier,
          base_url: baseUrl.trim() || null,
          priority: provider.priority,
          settings: computeSettings(provider.settings),
        };

        if (clearExistingKey) {
          payload.api_key = null;
        } else if (apiKey.trim()) {
          payload.api_key = apiKey.trim();
        }

        if (workspaceSlug) {
          saved = await updateAiProvider(provider.id, payload, workspaceSlug);
        } else {
          saved = await updateAiProvider(provider.id, payload);
        }
      } else {
        const nextPriority = providersCount !== undefined ? (providersCount + 1) * 10 : 100;
        const payload: ProviderConfigCreate = {
          provider_kind: providerKind,
          display_name: displayName.trim(),
          model_allowlist: models,
          residency_tier: residencyTier,
          base_url: baseUrl.trim() || null,
          priority: nextPriority,
          api_key: apiKey.trim() ? apiKey.trim() : null,
          is_enabled: true,
          settings: computeSettings(),
          ...(projectId ? { project_id: projectId } : {}),
        };

        if (workspaceSlug) {
          saved = await createAiProvider(payload, workspaceSlug);
        } else {
          saved = await createAiProvider(payload);
        }
      }

      setIsSaving(false);
      onSaved?.(saved);
      onClose();
    } catch (err: unknown) {
      setIsSaving(false);
      if (isAal2StepUpCancelled(err)) {
        return;
      }
      setError(err instanceof Error ? err.message : 'Failed to save provider configuration');
    }
  };

  const filteredProbedModels = (probedModels ?? []).filter((m) =>
    probedFilter.trim() ? m.toLowerCase().includes(probedFilter.trim().toLowerCase()) : true,
  );
  const selectedModels = getSelectedModelsList();

  return (
    <div className="kb-modal-card">
      <div className="kb-modal-header">
        <h2 id="provider-drawer-title">
          {isEditing ? `Edit ${provider.display_name}` : 'Register AI Provider'}
        </h2>
        <button
          type="button"
          className="kb-btn kb-btn-secondary"
          onClick={onClose}
          aria-label="Close dialog"
          data-testid="close-provider-drawer-btn"
        >
          ✕
        </button>
      </div>

      {airGapMode && (
        <div className="kb-air-gap-banner" data-testid="drawer-air-gap-alert">
          <span className="kb-air-gap-banner-icon" aria-hidden="true">
            🛡️
          </span>
          <div className="kb-air-gap-banner-content">
            <strong>Air-Gap Enforcement Active</strong>
            Cloud egress to OpenAI and Gemini is prohibited by workspace security settings. Only local zero-egress providers (Ollama) can be configured.
          </div>
        </div>
      )}

      {error && (
        <div className="kb-form-error" data-testid="provider-editor-error">
          {error}
        </div>
      )}

      <form
        noValidate
        autoComplete="off"
        data-form-type="other"
        onSubmit={(e) => { void handleSubmit(e); }}
      >
        {/* 1. Protocol & Provider Engine */}
        <div className="kb-form-group">
          <label htmlFor="provider-kind-select" className="kb-form-label">
            Protocol & Provider Engine
            <FieldHelpHint
              title="AI Provider Engine"
              summary="The underlying runtime and API protocol for AI completions and evaluations."
              validValues={[
                { label: 'Ollama', description: 'Local, zero-egress self-hosted runtime.' },
                { label: 'OpenAI', description: 'OpenAI API or compatible vLLM/LiteLLM server.' },
                { label: 'Google Gemini', description: 'Cloud Gemini models with high throughput.' },
              ]}
              docHref="/docs/multi-provider-ai-engine-and-runners#supported-runtimes"
              testId="provider-kind-help"
            />
          </label>
          <select
            id="provider-kind-select"
            className="kb-form-select"
            value={providerKind}
            onChange={(e) => { handleKindChange(e.target.value); }}
            disabled={isEditing}
            data-testid="provider-kind-select"
          >
            <option value="ollama">Ollama (Local / Zero Egress)</option>
            <option value="openai" disabled={airGapMode}>
              OpenAI / OpenAI-Compatible (vLLM, LM Studio, llama.cpp, LiteLLM){airGapMode ? ' (Blocked by Air-Gap Policy)' : ''}
            </option>
            <option value="gemini" disabled={airGapMode}>
              Google Gemini (Cloud){airGapMode ? ' (Blocked by Air-Gap Policy)' : ''}
            </option>
          </select>
          <span className="kb-form-hint">
            {providerKind === 'ollama' &&
              'Self-hosted Ollama runtime over loopback or local LAN. Zero external egress.'}
            {providerKind === 'openai' &&
              'OpenAI API or OpenAI-compatible local/remote engines (vLLM, LM Studio, llama.cpp, LiteLLM).'}
            {providerKind === 'gemini' &&
              'Google Gemini generative language API.'}
          </span>
          {!isEditing && (
            <div className="kb-provider-presets-row" data-testid="provider-presets-row">
              <span className="kb-provider-presets-label">Quick Presets:</span>
              <button
                type="button"
                className="kb-btn kb-btn-secondary kb-preset-btn"
                onClick={() => { applyPreset('ollama'); }}
                data-testid="preset-ollama-btn"
              >
                🦙 Ollama Local
              </button>
              <button
                type="button"
                className="kb-btn kb-btn-secondary kb-preset-btn"
                disabled={airGapMode}
                title={airGapMode ? 'Cloud provider egress is blocked by Air-Gap Policy' : undefined}
                onClick={() => { applyPreset('openai'); }}
                data-testid="preset-openai-btn"
              >
                🤖 OpenAI
              </button>
              <button
                type="button"
                className="kb-btn kb-btn-secondary kb-preset-btn"
                disabled={airGapMode}
                title={airGapMode ? 'Cloud provider egress is blocked by Air-Gap Policy' : undefined}
                onClick={() => { applyPreset('gemini'); }}
                data-testid="preset-gemini-btn"
              >
                ✨ Google Gemini
              </button>
            </div>
          )}
        </div>

        {/* 2. Display Name */}
        <div className="kb-form-group">
          <label htmlFor="provider-name-input" className="kb-form-label">
            Display Name
          </label>
          <input
            id="provider-name-input"
            type="text"
            className="kb-form-input"
            value={displayName}
            onChange={(e) => { setDisplayName(e.target.value); }}
            placeholder="e.g. OpenAI GPT-4o Production"
            required
            autoComplete="off"
            data-1p-ignore="true"
            data-lpignore="true"
            data-bwignore="true"
            data-form-type="other"
            data-testid="provider-name-input"
          />
        </div>

        {/* 3. API Secret Key (Moved to TOP of connection fields, ABOVE Base URL & Probe Models) */}
        <div className="kb-form-group">
          <label htmlFor="provider-key-input" className="kb-form-label">
            {isLocal ? 'API Secret Key (Optional for Local Endpoints)' : 'API Secret Key'}
          </label>
          <div className="kb-api-key-row">
            <input
              id="provider-key-input"
              type="text"
              className={`kb-form-input${!showApiKey ? ' kb-masked-api-key' : ''}`}
              value={displayKeyValue}
              onChange={handleApiKeyChange}
              placeholder={
                isEditing && provider.api_key_set
                  ? '********'
                  : isLocal
                    ? 'Optional for local runtime (leave blank if unauthenticated)'
                    : 'Enter API secret key'
              }
              disabled={clearExistingKey}
              autoComplete="off"
              spellCheck={false}
              autoCorrect="off"
              autoCapitalize="off"
              inputMode="text"
              data-1p-ignore="true"
              data-lpignore="true"
              data-bwignore="true"
              data-form-type="other"
              data-testid="provider-key-input"
            />
            <button
              type="button"
              className="kb-btn kb-btn-secondary kb-api-key-toggle-btn"
              onClick={() => { setShowApiKey(!showApiKey); }}
              aria-label={showApiKey ? 'Hide secret key' : 'Show secret key'}
              data-testid="toggle-show-key-btn"
            >
              {showApiKey ? '🔒' : '👁️'}
            </button>
          </div>

          <span className="kb-form-hint">
            {isLocal
              ? '🔓 No Key Required (Local). If your local proxy (vLLM, Ollama, llama.cpp) requires Bearer auth, you may supply one.'
              : isEditing && provider.api_key_set
                ? 'API key is securely stored in write-only custody. Leave blank to preserve the existing key.'
                : 'API keys are envelope-encrypted using master KEK and never returned in plaintext.'}
          </span>

          {isEditing && provider.api_key_set && (
            <div className="kb-clear-key-group">
              <label className="kb-clear-key-label">
                <input
                  type="checkbox"
                  checked={clearExistingKey}
                  onChange={(e) => {
                    setClearExistingKey(e.target.checked);
                    if (e.target.checked) setApiKey('');
                  }}
                  data-testid="clear-key-checkbox"
                />
                Clear existing API secret key
              </label>
            </div>
          )}
        </div>

        {/* 4. HTTP Base URL (Promoted from Advanced into primary connection settings) */}
        <div className="kb-form-group">
          <label htmlFor="provider-base-url-input" className="kb-form-label">
            HTTP Base URL {providerKind === 'ollama' && '(Default: http://127.0.0.1:11434)'}
          </label>
          <input
            id="provider-base-url-input"
            type="url"
            className="kb-form-input"
            value={baseUrl}
            onChange={(e) => { handleBaseUrlChange(e.target.value); }}
            placeholder={
              providerKind === 'ollama'
                ? 'http://127.0.0.1:11434'
                : providerKind === 'gemini'
                  ? 'https://generativelanguage.googleapis.com'
                  : 'https://api.openai.com/v1'
            }
            autoComplete="off"
            data-1p-ignore="true"
            data-lpignore="true"
            data-bwignore="true"
            data-form-type="other"
            data-testid="provider-base-url-input"
          />
          <span className="kb-form-hint">
            {providerKind === 'ollama'
              ? 'Local or LAN endpoint (e.g. http://127.0.0.1:11434 or http://192.168.1.50:11434).'
              : providerKind === 'gemini'
                ? 'Default Google Gemini endpoint: https://generativelanguage.googleapis.com'
                : 'Default OpenAI: https://api.openai.com/v1. For local proxies, use http://127.0.0.1:8000/v1 or http://localhost:1234/v1.'}
          </span>
        </div>

        {/* 4. Configurable Cutoff Timeout (ms) */}
        <div className="kb-form-group">
          <label htmlFor="provider-timeout-ms-input" className="kb-form-label">
            Cutoff Timeout (ms)
            <FieldHelpHint
              title="Cutoff Timeout (ms)"
              summary="Hard cutoff time in milliseconds before aborting slow model inference or failing over."
              defaultValue="30000 ms (30 seconds)"
              validValues={['1000 to 300000 (Default: 30000)']}
              docHref="/docs/multi-provider-ai-engine-and-runners#multi-provider-benchmark-cutoff-timeout-guide"
              testId="provider-timeout-help"
            />
          </label>
          <input
            id="provider-timeout-ms-input"
            type="number"
            min="1000"
            max="300000"
            step="1000"
            className="kb-form-input"
            value={timeoutMs}
            onChange={(e) => {
              const val = parseInt(e.target.value, 10);
              setTimeoutMs(isNaN(val) ? 30000 : val);
            }}
            placeholder="30000"
            data-testid="provider-timeout-ms-input"
          />
          <span className="kb-form-hint">
            Hard cutoff time (ms) before aborting slow model inference or failing over.
          </span>
        </div>

        {/* 6. Model Allowlist & Probing */}
        <div className="kb-form-group">
          <div className="kb-model-allowlist-header">
            <label htmlFor="provider-models-input" className="kb-form-label">
              Model Allowlist (comma separated)
            </label>
            <button
              type="button"
              className="kb-btn kb-btn-secondary kb-probe-btn"
              onClick={() => { void handleProbeModels(); }}
              disabled={isProbing}
              data-testid="probe-models-btn"
            >
              {isProbing ? '⏳ Probing...' : '🔍 Probe Models'}
            </button>
          </div>

          {isProbing && (
            <div className="kb-probe-status-message kb-probe-status-message--loading" data-testid="probe-loading">
              Probing upstream models from endpoint...
            </div>
          )}

          {probeError && (
            <div className="kb-probe-status-message kb-probe-status-message--error" data-testid="probe-error">
              {probeError}
            </div>
          )}

          {probedModels !== null && (
            <div className="kb-probed-models-picker" data-testid="probed-models-picker">
              <div className="kb-probed-models-toolbar">
                <input
                  type="text"
                  className="kb-probed-search-input"
                  placeholder="Filter probed models..."
                  value={probedFilter}
                  onChange={(e) => { setProbedFilter(e.target.value); }}
                  data-testid="probe-model-search-input"
                />
                <div className="kb-probed-actions">
                  <button
                    type="button"
                    className="kb-btn kb-btn-secondary kb-probed-action-btn"
                    onClick={handleSelectAllProbed}
                    data-testid="probe-select-all-btn"
                  >
                    Select All Probed
                  </button>
                  <button
                    type="button"
                    className="kb-btn kb-btn-secondary kb-probed-action-btn"
                    onClick={handleClearModels}
                    data-testid="probe-clear-all-btn"
                  >
                    Clear
                  </button>
                </div>
              </div>

              <div className="kb-probed-models-list" data-testid="probed-models-list">
                {filteredProbedModels.length === 0 ? (
                  <span className="kb-form-hint">No matching models found.</span>
                ) : (
                  filteredProbedModels.map((m) => {
                    const isSelected = selectedModels.includes(m);
                    return (
                      <div key={m} className="kb-probed-chip-item">
                        <button
                          type="button"
                          className={`kb-probed-chip ${isSelected ? 'kb-probed-chip--selected' : ''}`}
                          onClick={() => { toggleModel(m); }}
                          data-testid={`probe-chip-${m}`}
                        >
                          {m} {isSelected ? '✓' : '+'}
                        </button>
                        <button
                          type="button"
                          className="kb-probed-only-btn"
                          onClick={() => { setModelAllowlist(m); }}
                          title={`Select only ${m}`}
                          data-testid={`probe-only-${m}`}
                        >
                          Only This
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}

          <input
            id="provider-models-input"
            type="text"
            className="kb-form-input"
            value={modelAllowlist}
            onChange={(e) => { setModelAllowlist(e.target.value); }}
            placeholder="Click Probe Models above to populate from server, or enter model IDs"
            data-testid="provider-models-input"
          />
          <span className="kb-form-hint">
            Only models listed here are permitted for completion and agent execution.
          </span>
        </div>

        {/* 6. Advanced Model & Harness Configuration */}
        <AdvancedSection
          title="Advanced Settings"
          summary="Temperature, max tokens, mTLS client certificates, and data residency overrides"
          testId="advanced-settings-details"
          className="kb-advanced-model-harness-section"
        >
          <div data-testid="advanced-model-harness-config">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '16px' }}>
              <div className="kb-form-group">
                <label htmlFor="provider-temperature-input" className="kb-form-label">
                  Temperature
                  <FieldHelpHint
                    title="Temperature"
                    summary="Sampling randomness governing creative variance versus deterministic predictability."
                    defaultValue="0.7"
                    validValues={['0.0 to 2.0']}
                    docHref="/docs/multi-provider-ai-engine-and-runners#sampling-parameters"
                    testId="provider-temperature-help"
                  />
                </label>
                <input
                  id="provider-temperature-input"
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  className="kb-form-input"
                  value={temperature}
                  onChange={(e) => {
                    setTemperature(parseFloat(e.target.value) || 0.7);
                    setTemperatureModified(true);
                  }}
                  data-testid="provider-temperature-input"
                />
                <span className="kb-form-hint">Sampling randomness (0.0 to 2.0).</span>
              </div>

              <div className="kb-form-group">
                <label htmlFor="provider-top-p-input" className="kb-form-label">
                  Top-P (Nucleus)
                  <FieldHelpHint
                    title="Top-P (Nucleus)"
                    summary="Nucleus sampling threshold pruning lowest-probability tokens."
                    defaultValue="1.0"
                    validValues={['0.0 to 1.0']}
                    docHref="/docs/multi-provider-ai-engine-and-runners#sampling-parameters"
                    testId="provider-top-p-help"
                  />
                </label>
                <input
                  id="provider-top-p-input"
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  className="kb-form-input"
                  value={topP}
                  onChange={(e) => {
                    setTopP(parseFloat(e.target.value) || 1.0);
                    setTopPModified(true);
                  }}
                  data-testid="provider-top-p-input"
                />
                <span className="kb-form-hint">Nucleus threshold (0.0 to 1.0).</span>
              </div>

              <div className="kb-form-group">
                <label htmlFor="provider-max-tokens-input" className="kb-form-label">
                  Max Tokens
                  <FieldHelpHint
                    title="Max Tokens"
                    summary="Maximum generation token ceiling for completion and reasoning generation."
                    defaultValue="4096 tokens"
                    validValues={['1 to 128000 tokens']}
                    docHref="/docs/multi-provider-ai-engine-and-runners#sampling-parameters"
                    testId="provider-max-tokens-help"
                  />
                </label>
                <input
                  id="provider-max-tokens-input"
                  type="number"
                  min="1"
                  max="128000"
                  step="128"
                  className="kb-form-input"
                  value={maxTokens}
                  onChange={(e) => {
                    setMaxTokens(parseInt(e.target.value, 10) || 4096);
                    setMaxTokensModified(true);
                  }}
                  data-testid="provider-max-tokens-input"
                />
                <span className="kb-form-hint">Output generation token limit.</span>
              </div>
            </div>

            <div className="kb-form-group" style={{ marginTop: '12px' }}>
              <label htmlFor="provider-mtls-cert-input" className="kb-form-label">
                mTLS Client Certificate PEM (Optional)
              </label>
              <textarea
                id="provider-mtls-cert-input"
                className="kb-form-input"
                style={{ fontFamily: 'monospace', fontSize: '0.8rem', minHeight: '80px' }}
                placeholder="-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
                value={mtlsCertPem}
                onChange={(e) => {
                  setMtlsCertPem(e.target.value);
                }}
                data-testid="provider-mtls-cert-input"
              />
              <span className="kb-form-hint">
                Cryptographic client certificate for mutual TLS authentication against secured enterprise AI gateways.
              </span>
            </div>

            <div className="kb-form-group">
              <label htmlFor="provider-residency-select" className="kb-form-label">
                Data Residency Tier (Override)
              </label>
              <select
                id="provider-residency-select"
                className="kb-form-select"
                value={residencyTier}
                onChange={(e) => {
                  setResidencyTier(e.target.value);
                  setResidencyTierManual(true);
                }}
                data-testid="provider-residency-select"
              >
                <option value="local_only">Local Only (Zero Egress)</option>
                <option value="cloud_standard">Cloud Standard</option>
                <option value="default">Default / Global</option>
                <option value="cloud">Cloud (Legacy)</option>
                <option value="local">Local (Legacy)</option>
                <option value="us-east">US East</option>
                <option value="eu-central">EU Central</option>
              </select>
              <span className="kb-form-hint">
                Auto-inferred as &quot;{inferResidencyTier(providerKind, baseUrl)}&quot; ({isLocal ? 'Local / Zero-Egress' : 'Cloud'}) based on protocol and address. Override only when routed through a regional proxy.
              </span>
            </div>
          </div>
        </AdvancedSection>

        {testStatus.kind !== 'idle' && testStatus.message && (
          <div
            className={`kb-drawer-test-status kb-drawer-test-status--${testStatus.kind}`}
            data-testid="drawer-test-status"
          >
            {testStatus.message}
          </div>
        )}

        <div className="kb-modal-footer">
          <button
            type="button"
            className="kb-btn kb-btn-secondary"
            onClick={onClose}
            data-testid="cancel-provider-drawer-btn"
          >
            Cancel
          </button>
          <button
            type="button"
            className="kb-btn kb-btn-secondary"
            onClick={() => { void handleTestConnection(); }}
            disabled={isTestingConnection}
            data-testid="drawer-test-connection-btn"
          >
            {isTestingConnection ? 'Testing...' : 'Test Connection'}
          </button>
          <button
            type="submit"
            className="kb-btn kb-btn-primary"
            disabled={isSaving}
            data-testid="save-provider-btn"
          >
            {isSaving ? 'Saving...' : isEditing ? 'Save Provider' : 'Register Provider'}
          </button>
        </div>
      </form>
    </div>
  );
}

export function AiProviderEditorDrawer({
  isOpen,
  onClose,
  provider,
  airGapMode,
  onSaved,
  providersCount,
  projectId,
  workspaceSlug,
}: AiProviderEditorDrawerProps): JSX.Element | null {
  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="provider-drawer-title"
      className="kb-modal-backdrop"
      data-testid="ai-provider-editor-drawer"
    >
      <AiProviderEditorContent
        key={provider?.id ?? 'new'}
        onClose={onClose}
        provider={provider}
        airGapMode={airGapMode}
        onSaved={onSaved}
        providersCount={providersCount}
        projectId={projectId}
        workspaceSlug={workspaceSlug}
      />
    </div>
  );
}
