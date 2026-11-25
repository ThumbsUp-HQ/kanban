// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect } from 'vitest';
import { buildAgentOnboardingPrompt } from '../agentOnboardingPrompt';

describe('buildAgentOnboardingPrompt helper', () => {
  it('builds canonical prompt with defaults (local_only)', () => {
    const prompt = buildAgentOnboardingPrompt({ origin: 'https://kanban.example.com' });
    expect(prompt).toBe(
      "Read https://kanban.example.com/llms.txt, learn 👍kanban's ticket workflow, " +
        'interview me on Execution Mode (Single-Thread, Teamwork, or Swarm), ' +
        'Model/Quota Strategy (Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra), ' +
        'and QA Rigor, and save my preferences strictly to the local project folder (.agents/skills/ and AGENTS.md) - ' +
        'do NOT modify global home/system directories (~/.claude, ~/.codex, ~/.gemini, ~/.agents) ' +
        'unless I explicitly request global installation.',
    );
  });

  it('includes project clause when projectKey is provided', () => {
    const prompt = buildAgentOnboardingPrompt({
      origin: 'https://kanban.example.com',
      projectKey: 'KAN-403',
    });
    expect(prompt).toContain("learn 👍kanban's ticket workflow for project KAN-403");
  });

  it('builds global scope instruction when scope is global_allowed', () => {
    const prompt = buildAgentOnboardingPrompt({
      origin: 'https://kanban.example.com',
      scope: 'global_allowed',
    });
    expect(prompt).toContain(
      'save my preferences to both the local project folder and global workstation directories ' +
        '(~/.claude, ~/.codex, ~/.gemini, ~/.agents).',
    );
    expect(prompt).not.toContain('strictly to the local project folder');
  });

  it('appends custom notes when provided', () => {
    const prompt = buildAgentOnboardingPrompt({
      origin: 'https://kanban.example.com',
      customNotes: 'Never modify production auth tables without approval.',
    });
    expect(prompt).toContain('Notes: Never modify production auth tables without approval.');
  });

  it('handles window.location.origin fallback when origin is omitted', () => {
    const prompt = buildAgentOnboardingPrompt({});
    expect(prompt).toContain('/llms.txt, learn 👍kanban');
  });

  it('handles fallback origin when window is undefined', () => {
    const originalWindow = globalThis.window;
    // @ts-expect-error simulate non-browser environment
    delete globalThis.window;
    try {
      const prompt = buildAgentOnboardingPrompt({});
      expect(prompt).toContain('https://kanban.example.com/llms.txt');
    } finally {
      globalThis.window = originalWindow;
    }
  });

  it('reflects selected executionMode, modelStrategy, and qaRigor in prompt text', () => {
    const prompt = buildAgentOnboardingPrompt({
      origin: 'https://kanban.example.com',
      executionMode: 'swarm',
      modelStrategy: 'quota_sipping_flash',
      qaRigor: 'strict_forensic',
    });
    expect(prompt).toContain('Execution Mode (default: Swarm)');
    expect(prompt).toContain('Model/Quota Strategy (default: Quota-Sipping Flash 3.8)');
    expect(prompt).toContain('QA Rigor (default: Strict Forensic reality-checker)');
  });

  it('supports single option overrides cleanly', () => {
    const p1 = buildAgentOnboardingPrompt({ executionMode: 'single_thread' });
    expect(p1).toContain('Execution Mode (default: Single-Thread)');
    expect(p1).toContain(
      'Model/Quota Strategy (Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra)',
    );
    expect(p1).toContain('QA Rigor (Standard or Strict Forensic)');

    const p2 = buildAgentOnboardingPrompt({
      executionMode: 'teamwork',
      modelStrategy: 'hybrid',
      qaRigor: 'standard',
    });
    expect(p2).toContain('Execution Mode (default: Teamwork)');
    expect(p2).toContain('Model/Quota Strategy (default: Hybrid)');
    expect(p2).toContain('QA Rigor (default: Standard)');

    const p3 = buildAgentOnboardingPrompt({ modelStrategy: 'unconstrained_max' });
    expect(p3).toContain(
      'Model/Quota Strategy (default: Unconstrained Sol MAX / Claude Ultra)',
    );
  });
});
