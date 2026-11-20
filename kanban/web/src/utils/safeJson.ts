/**
 * Safe JSON parsing utilities preventing prototype pollution (KB-P3-AUDIT-11).
 */

/**
 * Safely parses a JSON string, stripping forbidden prototype pollution keys
 * ('__proto__', 'constructor', 'prototype') recursively.
 *
 * @param text The raw JSON string to parse.
 * @returns The parsed data with prototype pollution keys stripped.
 */
// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters
export function safeJsonParse<T = unknown>(text: string): T {
  const parsed: unknown = JSON.parse(text, (key, value: unknown) => {
    if (key === '__proto__' || key === 'constructor' || key === 'prototype') {
      return undefined;
    }
    return value;
  });
  return parsed as T;
}
