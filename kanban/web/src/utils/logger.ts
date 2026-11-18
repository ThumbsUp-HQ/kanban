/**
 * Standardized semantic emoji logging helper (👍 / ⛔ / ❌) for the web client.
 *
 * Ensures all diagnostics and runtime console messages emitted across browser
 * surfaces prepend consistent severity prefixes on every emitted line.
 */

export const STATUS_OK = '👍';
export const STATUS_BLOCKED = '⛔';
export const STATUS_ERROR = '❌';

const STATUS_ICONS = [STATUS_OK, STATUS_BLOCKED, STATUS_ERROR] as const;

/**
 * Prepend a semantic icon prefix to every line in a text string.
 * Deduplicates leading icons if already present.
 */
export function prefixLines(icon: string, text: string): string {
  if (!text) {
    return icon;
  }

  const lines = text.split(/\r?\n/);
  const prefixed = lines.map((line) => {
    let stripped = line.trimStart();
    for (const knownIcon of STATUS_ICONS) {
      if (stripped.startsWith(knownIcon)) {
        stripped = stripped.slice(knownIcon.length).trimStart();
        break;
      }
    }
    return stripped.length > 0 ? `${icon} ${stripped}` : icon;
  });

  return prefixed.join('\n');
}

/**
 * Format arguments for console output with a universal severity prefix on every line.
 */
export function formatLogArgs(icon: string, ...args: unknown[]): unknown[] {
  if (args.length === 0) {
    return [icon];
  }

  const first = args[0];
  if (typeof first === 'string') {
    return [prefixLines(icon, first), ...args.slice(1)];
  }

  if (first instanceof Error) {
    const rawErrorText =
      first.stack && first.stack.length > 0
        ? first.stack
        : `${first.name}: ${first.message}`;
    const formattedMsg = prefixLines(icon, rawErrorText);
    return [formattedMsg, ...args.slice(1)];
  }

  return [icon, ...args];
}

/**
 * Unified frontend logger interface mirroring console logging with semantic prefixes.
 */
export const logger = {
  info: (...args: unknown[]): void => {
    console.info(...formatLogArgs(STATUS_OK, ...args));
  },
  warn: (...args: unknown[]): void => {
    console.warn(...formatLogArgs(STATUS_BLOCKED, ...args));
  },
  error: (...args: unknown[]): void => {
    console.error(...formatLogArgs(STATUS_ERROR, ...args));
  },
  debug: (...args: unknown[]): void => {
    console.debug(...formatLogArgs(STATUS_OK, ...args));
  },
  log: (...args: unknown[]): void => {
    console.log(...formatLogArgs(STATUS_OK, ...args));
  },
};

export const logOk = logger.info;
export const logBlocked = logger.warn;
export const logError = logger.error;
export const logInfo = logger.info;
export const logWarn = logger.warn;
