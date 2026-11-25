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

  const execLabel =
    options.executionMode === 'single_thread'
      ? 'Single-Thread'
      : options.executionMode === 'teamwork'
        ? 'Teamwork'
        : options.executionMode === 'swarm'
          ? 'Swarm'
          : undefined;

  const modelLabel =
    options.modelStrategy === 'quota_sipping_flash'
      ? 'Quota-Sipping Flash 3.8'
      : options.modelStrategy === 'hybrid'
        ? 'Hybrid'
        : options.modelStrategy === 'unconstrained_max'
          ? 'Unconstrained Sol MAX / Claude Ultra'
          : undefined;

  const qaLabel =
    options.qaRigor === 'standard'
      ? 'Standard'
      : options.qaRigor === 'strict_forensic'
        ? 'Strict Forensic reality-checker'
        : undefined;

  let interviewClause: string;
  if (execLabel || modelLabel || qaLabel) {
    const execDesc = execLabel ? `default: ${execLabel}` : 'Single-Thread, Teamwork, or Swarm';
    const modelDesc = modelLabel
      ? `default: ${modelLabel}`
      : 'Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra';
    const qaDesc = qaLabel ? `default: ${qaLabel}` : 'Standard or Strict Forensic';
    interviewClause = `interview me on Execution Mode (${execDesc}), Model/Quota Strategy (${modelDesc}), and QA Rigor (${qaDesc})`;
  } else {
    interviewClause =
      'interview me on Execution Mode (Single-Thread, Teamwork, or Swarm), ' +
      'Model/Quota Strategy (Quota-Sipping Flash 3.8, Hybrid, or Unconstrained Sol MAX / Claude Ultra), ' +
      'and QA Rigor';
  }

  let prompt = `Read ${origin}/llms.txt, learn 👍kanban's ticket workflow${projectClause}, ${interviewClause}, and ${scopeClause}`;

  if (options.customNotes && options.customNotes.trim().length > 0) {
    prompt += ` Notes: ${options.customNotes.trim()}`;
  }

  return prompt;
}
