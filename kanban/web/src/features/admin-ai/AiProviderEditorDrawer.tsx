// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX } from 'react';
import {
  createAiProvider,
  updateAiProvider,
  type ProviderConfigPublic,
  type ProviderConfigCreate,
  type ProviderConfigUpdate,
} from './aiAdminApi';

interface AiProviderEditorDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  provider: ProviderConfigPublic | null;
  airGapMode: boolean;
  onSaved: () => void;
}

function AiProviderEditorContent({
  onClose,
  provider,
  airGapMode,
  onSaved,
}: {
  onClose: () => void;
  provider: ProviderConfigPublic | null;
  airGapMode: boolean;
  onSaved: () => void;
}): JSX.Element {
  const isEditing = provider !== null;

  const defaultKind = airGapMode ? 'ollama' : 'openai';
  const [providerKind, setProviderKind] = useState<string>(
    provider?.provider_kind ?? defaultKind,
  );
  const [displayName, setDisplayName] = useState<string>(
    provider?.display_name ?? (airGapMode ? 'Local Ollama Runtime' : 'Enterprise OpenAI'),
  );
  const [baseUrl, setBaseUrl] = useState<string>(
    provider?.base_url ?? (airGapMode ? 'http://localhost:11434' : ''),
  );
  const [modelAllowlist, setModelAllowlist] = useState<string>(
    provider?.model_allowlist.join(', ') ??
      (airGapMode ? 'qwen2.5-coder:7b, llama3.2:3b' : 'gpt-4o, gpt-4o-mini'),
  );
  const [residencyTier, setResidencyTier] = useState<string>(
    provider?.residency_tier ?? (airGapMode ? 'local' : 'default'),
  );
  const [priority, setPriority] = useState<number>(provider?.priority ?? 100);
  const [apiKey, setApiKey] = useState<string>('');
  const [showApiKey, setShowApiKey] = useState<boolean>(false);
  const [clearExistingKey, setClearExistingKey] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const isCloudKind = providerKind === 'openai' || providerKind === 'gemini';

  const handleKindChange = (newKind: string): void => {
    setProviderKind(newKind);
    if (airGapMode && (newKind === 'openai' || newKind === 'gemini')) {
      setError('Air-Gap mode prohibits configuring cloud providers (OpenAI, Gemini). Use local Ollama.');
    } else {
      setError(null);
    }
    if (!isEditing) {
      if (newKind === 'openai') {
        setDisplayName('Enterprise OpenAI');
        setModelAllowlist('gpt-4o, gpt-4o-mini');
        setBaseUrl('');
      } else if (newKind === 'gemini') {
        setDisplayName('Google Gemini Workspace');
        setModelAllowlist('gemini-2.5-flash, gemini-2.5-pro');
        setBaseUrl('');
      } else if (newKind === 'ollama') {
        setDisplayName('Local Ollama Runtime');
        setBaseUrl('http://localhost:11434');
        setModelAllowlist('qwen2.5-coder:7b, llama3.2:3b');
        setResidencyTier('local');
      } else {
        setDisplayName('Custom AI Provider');
        setBaseUrl('');
        setModelAllowlist('');
      }
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

    const models = modelAllowlist
      .split(',')
      .map((m) => m.trim())
      .filter((m) => m.length > 0);

    try {
      setIsSaving(true);
      setError(null);

      if (provider) {
        const payload: ProviderConfigUpdate = {
          display_name: displayName.trim(),
          model_allowlist: models,
          residency_tier: residencyTier,
          base_url: baseUrl.trim() || null,
          priority,
        };

        if (clearExistingKey) {
          payload.api_key = null;
        } else if (apiKey.trim()) {
          payload.api_key = apiKey.trim();
        }

        await updateAiProvider(provider.id, payload);
      } else {
        const payload: ProviderConfigCreate = {
          provider_kind: providerKind,
          display_name: displayName.trim(),
          model_allowlist: models,
          residency_tier: residencyTier,
          base_url: baseUrl.trim() || null,
          priority,
          api_key: apiKey.trim() ? apiKey.trim() : null,
          is_enabled: true,
        };

        await createAiProvider(payload);
      }

      setIsSaving(false);
      onSaved();
      onClose();
    } catch (err: unknown) {
      setIsSaving(false);
      setError(err instanceof Error ? err.message : 'Failed to save provider configuration');
    }
  };

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
        <div className="kb-form-hint" style={{ color: '#ef4444', margin: '12px 0' }} data-testid="provider-editor-error">
          {error}
        </div>
      )}

      <form noValidate onSubmit={(e) => { void handleSubmit(e); }}>
        <div className="kb-form-group">
          <label htmlFor="provider-kind-select" className="kb-form-label">
            Provider Kind
          </label>
          <select
            id="provider-kind-select"
            className="kb-form-select"
            value={providerKind}
            onChange={(e) => { handleKindChange(e.target.value); }}
            disabled={isEditing}
            data-testid="provider-kind-select"
          >
            <option value="openai">OpenAI (Cloud)</option>
            <option value="gemini">Google Gemini (Cloud)</option>
            <option value="ollama">Ollama (Local / Zero Egress)</option>
            <option value="custom">Custom Compatible</option>
          </select>
        </div>

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
            data-testid="provider-name-input"
          />
        </div>

        <div className="kb-form-group">
          <label htmlFor="provider-base-url-input" className="kb-form-label">
            Custom HTTP Base URL {providerKind === 'ollama' && '(Required for Ollama)'}
          </label>
          <input
            id="provider-base-url-input"
            type="url"
            className="kb-form-input"
            value={baseUrl}
            onChange={(e) => { setBaseUrl(e.target.value); }}
            placeholder={providerKind === 'ollama' ? 'http://localhost:11434' : 'https://api.openai.com/v1'}
            data-testid="provider-base-url-input"
          />
        </div>

        <div className="kb-form-group">
          <label htmlFor="provider-models-input" className="kb-form-label">
            Model Allowlist (comma separated)
          </label>
          <input
            id="provider-models-input"
            type="text"
            className="kb-form-input"
            value={modelAllowlist}
            onChange={(e) => { setModelAllowlist(e.target.value); }}
            placeholder="gpt-4o, gpt-4o-mini"
            data-testid="provider-models-input"
          />
          <span className="kb-form-hint">
            Only models listed here are permitted for completion and agent execution.
          </span>
        </div>

        <div className="kb-form-group">
          <label htmlFor="provider-residency-select" className="kb-form-label">
            Data Residency Tier
          </label>
          <select
            id="provider-residency-select"
            className="kb-form-select"
            value={residencyTier}
            onChange={(e) => { setResidencyTier(e.target.value); }}
            data-testid="provider-residency-select"
          >
            <option value="default">Default / Global</option>
            <option value="local">Local Only (Zero Egress)</option>
            <option value="us-east">US East</option>
            <option value="eu-central">EU Central</option>
          </select>
        </div>

        <div className="kb-form-group">
          <label htmlFor="provider-priority-input" className="kb-form-label">
            Priority Order (lower numbers evaluated first)
          </label>
          <input
            id="provider-priority-input"
            type="number"
            min="1"
            max="999"
            className="kb-form-input"
            value={priority}
            onChange={(e) => { setPriority(parseInt(e.target.value, 10) || 100); }}
            data-testid="provider-priority-input"
          />
        </div>

        <div className="kb-form-group">
          <label htmlFor="provider-key-input" className="kb-form-label">
            API Secret Key (Write-Only Custody)
          </label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              id="provider-key-input"
              type={showApiKey ? 'text' : 'password'}
              className="kb-form-input"
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                setClearExistingKey(false);
              }}
              placeholder={isEditing && provider.api_key_set ? '********' : 'Enter API secret key'}
              disabled={clearExistingKey}
              data-testid="provider-key-input"
            />
            <button
              type="button"
              className="kb-btn kb-btn-secondary"
              style={{ minWidth: '44px', padding: '0 12px' }}
              onClick={() => { setShowApiKey(!showApiKey); }}
              aria-label={showApiKey ? 'Hide secret key' : 'Show secret key'}
              data-testid="toggle-show-key-btn"
            >
              {showApiKey ? '🔒' : '👁️'}
            </button>
          </div>

          <span className="kb-form-hint">
            {isEditing && provider.api_key_set
              ? 'API key is securely stored in write-only custody. Leave blank to preserve the existing key.'
              : 'API keys are envelope-encrypted using master KEK and never returned in plaintext.'}
          </span>

          {isEditing && provider.api_key_set && (
            <div style={{ marginTop: '8px' }}>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
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
            type="submit"
            className="kb-btn kb-btn-primary"
            disabled={isSaving || (airGapMode && isCloudKind)}
            data-testid="save-provider-btn"
          >
            {isSaving ? 'Saving...' : isEditing ? 'Save Changes' : 'Register Provider'}
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
      />
    </div>
  );
}
