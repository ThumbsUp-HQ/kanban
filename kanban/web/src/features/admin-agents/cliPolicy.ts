// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

export const BANNED_CLI_FLAGS: readonly string[] = [
  '--yolo',
  '--dangerously-bypass-approvals-and-sandbox',
  '--dangerously-skip-permissions',
  '--full-auto',
  '--allow-all-tools',
];

export const ALLOWED_CLI_BINARIES: Record<string, string> = {
  agy: '/usr/local/bin/agy',
  codex: '/usr/local/bin/codex',
  'gemini-cli': '/usr/local/bin/gemini',
  'claude-code': '/usr/local/bin/claude',
};

export const CODEX_PINNED_PREFIX: readonly string[] = ['exec', '-s', 'read-only', '-'];

export interface CliValidationResult {
  valid: boolean;
  error?: string;
}

export function validateCliArguments(binaryId: string, args: readonly string[]): CliValidationResult {
  if (!ALLOWED_CLI_BINARIES[binaryId]) {
    return {
      valid: false,
      error: `Binary identifier '${binaryId}' is not allowlisted. Permitted: ${Object.keys(ALLOWED_CLI_BINARIES).join(', ')}`,
    };
  }

  for (let i = 0; i < args.length; i++) {
    const arg = args[i] ?? '';
    const folded = arg.toLowerCase();

    if (
      BANNED_CLI_FLAGS.includes(folded) ||
      BANNED_CLI_FLAGS.some((banned) => folded.startsWith(`${banned}=`)) ||
      folded.startsWith('--dangerously')
    ) {
      return {
        valid: false,
        error: `Argument '${arg}' violates banned CLI flag policy (no sandbox bypass or --yolo allowed)`,
      };
    }

    if (arg.includes('\0') || arg.includes('\r') || arg.includes('\n')) {
      return {
        valid: false,
        error: `Argument at index ${String(i)} contains forbidden control characters`,
      };
    }
  }

  if (binaryId === 'codex') {
    if (args.length < CODEX_PINNED_PREFIX.length) {
      return {
        valid: false,
        error: `codex binary requires initial pinned arguments: ${CODEX_PINNED_PREFIX.join(' ')}`,
      };
    }
    for (let i = 0; i < CODEX_PINNED_PREFIX.length; i++) {
      if (args[i] !== CODEX_PINNED_PREFIX[i]) {
        return {
          valid: false,
          error: `codex binary argument at position ${String(i)} must be '${String(CODEX_PINNED_PREFIX[i])}'`,
        };
      }
    }
  }

  return { valid: true };
}
