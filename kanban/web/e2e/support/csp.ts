/**
 * Authoritative production Content-Security-Policy (CSP) header string.
 * Exact specification defined in S5.4 and shared with Vite preview server.
 */
export const PRODUCTION_CSP =
  "default-src 'none'; script-src 'self'; worker-src 'self'; style-src 'self'; img-src 'self' blob: data:image/png data:image/webp; font-src 'self'; connect-src 'self' wss:; media-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; require-trusted-types-for 'script'; trusted-types kanban-sanitizer dompurify";
