// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

export interface AgentOnboardingPromptOptions {
  origin?: string | undefined;
  scope?: ('local_only' | 'global_allowed') | undefined;
  executionMode?: ('single_thread' | 'teamwork' | 'swarm') | undefined;
  modelStrategy?: ('quota_sipping_flash' | 'hybrid' | 'unconstrained_max') | undefined;
  qaRigor?: ('standard' | 'strict_forensic') | undefined;
  customNotes?: string | undefined;
  projectKey?: string | undefined;
}

export function buildAgentOnboardingPrompt(options: AgentOnboardingPromptOptions = {}): string {
  const origin = options.origin ?? (typeof window !== 'undefined' ? window.location.origin : 'https://kanban.example.com');
  const scope = options.scope ?? 'local_only';
  const projectKey = options.projectKey;

  const projectClause = projectKey ? ` for project ${projectKey}` : '';

  let scopeClause: string;
  if (scope === 'local_only') {
    scopeClause =
      'save my preferences strictly to the local project folder (.agents/skills/ and AGENTS.md) - ' +
      'do NOT modify global home/system directories (~/.claude, ~/.codex, ~/.gemini, ~/.agents) ' +
      'unless I explicitly request global installation.';
  } else {
    scopeClause =
      'save my preferences to both the local project folder and global workstation directories ' +
      '(~/.claude, ~/.codex, ~/.gemini, ~/.agents).';
  }

  let prompt = `Read ${origin}/llms.txt, learn 👍kanban's ticket workflow${projectClause}, interview me on Execution Mode (Single-Thread, Teamwork, or Swarm), Model/Quota Strategy (Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra), and QA Rigor, and ${scopeClause}`;

  if (options.customNotes && options.customNotes.trim().length > 0) {
    prompt += ` Notes: ${options.customNotes.trim()}`;
  }

  return prompt;
}
