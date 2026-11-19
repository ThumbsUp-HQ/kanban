// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, type JSX } from 'react';
import {
  fetchBudgets,
  setBudget,
  type BudgetRecord,
  type ProviderConfigPublic,
} from './aiAdminApi';

interface AiBudgetModalProps {
  isOpen: boolean;
  onClose: () => void;
  provider: ProviderConfigPublic | null;
  onBudgetUpdated?: (() => void) | undefined;
}

function AiBudgetModalContent({
  onClose,
  provider,
  onBudgetUpdated,
}: {
  onClose: () => void;
  provider: ProviderConfigPublic;
  onBudgetUpdated?: (() => void) | undefined;
}): JSX.Element {
  const [budgets, setBudgets] = useState<BudgetRecord[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [periodKind, setPeriodKind] = useState<'daily' | 'monthly'>('monthly');
  const [tokenCap, setTokenCap] = useState<string>('1000000');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        const records = await fetchBudgets(provider.id);
        if (!active) return;
        setBudgets(records);
        const monthly = records.find((b) => b.period_kind === 'monthly');
        if (monthly) {
          setTokenCap(String(monthly.token_cap));
          setPeriodKind('monthly');
        } else if (records[0]) {
          setTokenCap(String(records[0].token_cap));
          setPeriodKind(records[0].period_kind);
        }
      } catch (err: unknown) {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Failed to load budgets');
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, [provider.id]);

  const currentBudget = budgets.find((b) => b.period_kind === periodKind) ?? budgets[0];
  const capNum = currentBudget?.token_cap ?? 0;
  const usedNum = currentBudget?.tokens_used ?? 0;
  const reservedNum = currentBudget?.tokens_reserved ?? 0;
  const percentUsed = capNum > 0 ? Math.min(100, Math.round(((usedNum + reservedNum) / capNum) * 100)) : 0;

  const handleSaveBudget = async (e: React.SyntheticEvent): Promise<void> => {
    e.preventDefault();
    const cap = parseInt(tokenCap, 10);
    if (isNaN(cap) || cap < 0) {
      setError('Token cap must be a non-negative integer');
      return;
    }

    try {
      setIsSaving(true);
      setError(null);
      await setBudget({
        provider_config_id: provider.id,
        project_id: provider.project_id ?? undefined,
        period_kind: periodKind,
        token_cap: cap,
      });
      const updated = await fetchBudgets(provider.id);
      setBudgets(updated);
      setIsSaving(false);
      onBudgetUpdated?.();
    } catch (err: unknown) {
      setIsSaving(false);
      setError(err instanceof Error ? err.message : 'Failed to update token budget cap');
    }
  };

  return (
    <div className="kb-modal-card">
      <div className="kb-modal-header">
        <h2 id="budget-modal-title">Token Budget & Usage Ledger</h2>
        <button
          type="button"
          className="kb-btn kb-btn-secondary"
          onClick={onClose}
          aria-label="Close dialog"
          data-testid="close-budget-modal-btn"
        >
          ✕
        </button>
      </div>

      <p className="kb-ai-studio-subtitle">
        Configure monthly and daily token caps and inspect consumption for {provider.display_name}.
      </p>

      {error && (
        <div className="kb-form-hint" style={{ color: '#ef4444', margin: '8px 0' }} data-testid="budget-error">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="kb-loading-state" data-testid="budget-loading">
          Loading budget ledger...
        </div>
      ) : (
        <>
          <div className="kb-budget-progress-container" data-testid="budget-ledger-summary">
            <div className="kb-budget-stats-row">
              <span>
                <strong>Usage:</strong> {usedNum.toLocaleString()} tokens
                {reservedNum > 0 && ` (+${reservedNum.toLocaleString()} reserved)`}
              </span>
              <span>
                <strong>Cap:</strong> {capNum > 0 ? `${capNum.toLocaleString()} tokens` : 'Unlimited'}
              </span>
            </div>

            <div className="kb-budget-progress-bar-bg" role="progressbar" aria-valuenow={percentUsed} aria-valuemin={0} aria-valuemax={100}>
              <div
                className={`kb-budget-progress-bar-fill ${
                  percentUsed >= 90
                    ? 'kb-budget-progress-bar-fill--danger'
                    : percentUsed >= 70
                      ? 'kb-budget-progress-bar-fill--warning'
                      : ''
                }`}
                style={{ width: `${String(percentUsed)}%` }}
              />
            </div>

            <div className="kb-budget-stats-row">
              <span>{String(percentUsed)}% consumed</span>
              <span>
                {capNum > usedNum + reservedNum
                  ? `${(capNum - (usedNum + reservedNum)).toLocaleString()} tokens remaining`
                  : capNum > 0
                    ? '0 tokens remaining'
                    : 'No cap enforced'}
              </span>
            </div>
          </div>

          <form noValidate onSubmit={(e) => { void handleSaveBudget(e); }}>
            <div className="kb-form-group">
              <label htmlFor="budget-period-select" className="kb-form-label">
                Accounting Period
              </label>
              <select
                id="budget-period-select"
                className="kb-form-select"
                value={periodKind}
                onChange={(e) => { setPeriodKind(e.target.value as 'daily' | 'monthly'); }}
                data-testid="budget-period-select"
              >
                <option value="monthly">Monthly Cap</option>
                <option value="daily">Daily Cap</option>
              </select>
            </div>

            <div className="kb-form-group">
              <label htmlFor="budget-token-cap-input" className="kb-form-label">
                Maximum Token Cap
              </label>
              <input
                id="budget-token-cap-input"
                type="number"
                min="0"
                max="10000000000"
                className="kb-form-input"
                value={tokenCap}
                onChange={(e) => { setTokenCap(e.target.value); }}
                placeholder="e.g. 5000000"
                data-testid="budget-token-cap-input"
                required
              />
              <span className="kb-form-hint">
                Enter 0 for zero-allowance freeze or an integer token quota (e.g. 1,000,000).
              </span>
            </div>

            <div className="kb-modal-footer">
              <button
                type="button"
                className="kb-btn kb-btn-secondary"
                onClick={onClose}
                data-testid="budget-cancel-btn"
              >
                Close
              </button>
              <button
                type="submit"
                className="kb-btn kb-btn-primary"
                disabled={isSaving}
                data-testid="save-budget-btn"
              >
                {isSaving ? 'Updating Cap...' : 'Save Token Cap'}
              </button>
            </div>
          </form>
        </>
      )}
    </div>
  );
}

export function AiBudgetModal({
  isOpen,
  onClose,
  provider,
  onBudgetUpdated,
}: AiBudgetModalProps): JSX.Element | null {
  if (!isOpen || !provider) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="budget-modal-title"
      className="kb-modal-backdrop"
      data-testid="ai-budget-modal"
    >
      <AiBudgetModalContent
        key={provider.id}
        onClose={onClose}
        provider={provider}
        onBudgetUpdated={onBudgetUpdated}
      />
    </div>
  );
}
