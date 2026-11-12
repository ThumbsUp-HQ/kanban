import { describe, it, expect } from 'vitest';
import { PRODUCTION_CSP } from './csp';

describe('PRODUCTION_CSP constant', () => {
  it('contains the expected directives in authoritative S5.4 order', () => {
    const expectedDirectives = [
      "default-src 'none'",
      "script-src 'self'",
      "worker-src 'self'",
      "style-src 'self'",
      'img-src \'self\' blob: data:image/png data:image/webp',
      "font-src 'self'",
      "connect-src 'self' wss:",
      "media-src 'self'",
      "object-src 'none'",
      "base-uri 'none'",
      "form-action 'self'",
      "frame-ancestors 'none'",
      "require-trusted-types-for 'script'",
      'trusted-types kanban-sanitizer dompurify',
    ];

    const directives = PRODUCTION_CSP.split(';').map((d) => d.trim()).filter(Boolean);

    expect(directives.length).toBe(expectedDirectives.length);
    for (let i = 0; i < expectedDirectives.length; i++) {
      expect(directives[i]).toBe(expectedDirectives[i]);
    }

    // Ensure each directive appears exactly once
    const directiveNames = directives.map((d) => d.split(' ')[0]);
    const uniqueNames = new Set(directiveNames);
    expect(uniqueNames.size).toBe(directiveNames.length);
  });
});
