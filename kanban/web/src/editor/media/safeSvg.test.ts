/**
 * Unit Tests for Client Safe SVG Blob Sanitizer & <use> DAG Guard (KB-P3-48, S5.4).
 */

import { describe, it, expect, vi } from 'vitest';
import {
  createSafeSvgBlobUrl,
  MAX_CLIENT_SVG_BYTES,
  toTrustedScriptUrl,
  _resetPolicyForTesting,
} from './safeSvg';

describe('safeSvg Sanitizer & DAG Guard', () => {
  it('sanitizes clean SVG, ensures xmlns, and generates revokable blob URL', () => {
    const cleanInput = `<svg viewBox="0 0 100 100"><rect x="10" y="10" width="80" height="80" fill="blue"/></svg>`;
    const result = createSafeSvgBlobUrl(cleanInput);

    expect(result.ok).toBe(true);
    if (!result.ok) return;

    expect(result.blobUrl).toMatch(/^blob:/);
    expect(result.cleanSvg).toContain('xmlns="http://www.w3.org/2000/svg"');
    expect(result.cleanSvg).toContain('<rect');

    const revokeSpy = vi.fn();
    // eslint-disable-next-line @typescript-eslint/unbound-method
    const originalRevoke = URL.revokeObjectURL;
    URL.revokeObjectURL = revokeSpy;
    try {
      result.revoke();
      expect(revokeSpy).toHaveBeenCalledWith(result.blobUrl);
    } finally {
      URL.revokeObjectURL = originalRevoke;
    }
  });

  it('strips hostile elements, event handlers, scripts, and external hrefs', () => {
    const hostileSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
      <script>window.__xss = 1; alert(document.domain);</script>
      <foreignObject width="100" height="100"><body xmlns="http://www.w3.org/1999/xhtml"><iframe src="https://evil.test"></iframe></body></foreignObject>
      <image href="https://evil.test/track.png" xlink:href="https://evil.test/track2.png" width="50" height="50" />
      <style>@import url("https://evil.test/evil.css"); body { background: red; }</style>
      <animate attributeName="href" to="javascript:alert(1)" />
      <animateTransform attributeName="transform" type="rotate" />
      <circle cx="50" cy="50" r="40" onload="alert(1)" onclick="stealCookies()" />
      <use href="https://evil.test/x.svg#remote-symbol" xlink:href="https://evil.test/x2.svg#sym" />
    </svg>`;

    const result = createSafeSvgBlobUrl(hostileSvg);
    expect(result.ok).toBe(true);
    if (!result.ok) return;

    expect(result.cleanSvg).not.toContain('<script');
    expect(result.cleanSvg).not.toContain('<foreignObject');
    expect(result.cleanSvg).not.toContain('<iframe');
    expect(result.cleanSvg).not.toContain('<image');
    expect(result.cleanSvg).not.toContain('<style');
    expect(result.cleanSvg).not.toContain('<animate');
    expect(result.cleanSvg).not.toContain('onload');
    expect(result.cleanSvg).not.toContain('onclick');
    expect(result.cleanSvg).not.toContain('https://evil.test');
    expect(result.cleanSvg).toContain('<circle');
  });

  it('rejects self-referencing and mutual cyclic <use> references (SVG_USE_CYCLE)', () => {
    // Self cycle
    const selfCycleSvg = `<svg xmlns="http://www.w3.org/2000/svg">
      <defs>
        <g id="a">
          <use href="#a" />
        </g>
      </defs>
      <use href="#a" />
    </svg>`;
    const selfRes = createSafeSvgBlobUrl(selfCycleSvg);
    expect(selfRes.ok).toBe(false);
    if (selfRes.ok) return;
    expect(selfRes.error).toBe('SVG_USE_CYCLE');

    // Mutual cycle #a -> #b -> #a
    const mutualCycleSvg = `<svg xmlns="http://www.w3.org/2000/svg">
      <defs>
        <g id="nodeA">
          <use href="#nodeB" />
        </g>
        <g id="nodeB">
          <use href="#nodeA" />
        </g>
      </defs>
      <use href="#nodeA" />
    </svg>`;
    const mutualRes = createSafeSvgBlobUrl(mutualCycleSvg);
    expect(mutualRes.ok).toBe(false);
    if (mutualRes.ok) return;
    expect(mutualRes.error).toBe('SVG_USE_CYCLE');
  });

  it('verifies <use> chain depth: depth 4 passes, depth 5 rejects with SVG_USE_MAX_DEPTH', () => {
    // Depth 4 chain: <use href="#l1"/> -> #l1 has <use #l2> -> #l2 has <use #l3> -> #l3 has <use #l4> -> #l4 has rect
    const depth4Svg = `<svg xmlns="http://www.w3.org/2000/svg">
      <defs>
        <rect id="l4" width="10" height="10" />
        <g id="l3"><use href="#l4" /></g>
        <g id="l2"><use href="#l3" /></g>
        <g id="l1"><use href="#l2" /></g>
      </defs>
      <use href="#l1" />
    </svg>`;
    const depth4Res = createSafeSvgBlobUrl(depth4Svg);
    expect(depth4Res.ok).toBe(true);

    // Depth 5 chain: <use href="#step1"/> -> #step1 -> #step2 -> #step3 -> #step4 -> #step5 (depth 5 exceeds MAX_SVG_USE_DEPTH of 4)
    const depth5Svg = `<svg xmlns="http://www.w3.org/2000/svg">
      <defs>
        <rect id="step5" width="10" height="10" />
        <g id="step4"><use href="#step5" /></g>
        <g id="step3"><use href="#step4" /></g>
        <g id="step2"><use href="#step3" /></g>
        <g id="step1"><use href="#step2" /></g>
      </defs>
      <use href="#step1" />
    </svg>`;
    const depth5Res = createSafeSvgBlobUrl(depth5Svg);
    expect(depth5Res.ok).toBe(false);
    if (depth5Res.ok) return;
    expect(depth5Res.error).toBe('SVG_USE_MAX_DEPTH');
  });

  it('verifies expanded node limit: <= 500 passes, >= 501 rejects with SVG_EXPANSION_LIMIT_EXCEEDED', () => {
    // 1 group + 49 rects = 50 nodes, referenced 10 times -> 500 expanded nodes -> PASSES
    const rects49 = Array.from({ length: 49 }, (_, i) => `<rect id="r${String(i)}" width="1" height="1"/>`).join('');
    const uses10 = Array.from({ length: 10 }, () => `<use href="#baseGroup" />`).join('');
    const svg500 = `<svg xmlns="http://www.w3.org/2000/svg">
      <defs>
        <g id="baseGroup">
          ${rects49}
        </g>
      </defs>
      ${uses10}
    </svg>`;
    const res500 = createSafeSvgBlobUrl(svg500);
    expect(res500.ok).toBe(true);

    // 1 group + 49 rects = 50 nodes, referenced 11 times -> 550 expanded nodes -> EXCEEDED (> 500)
    const uses11 = Array.from({ length: 11 }, () => `<use href="#baseGroup" />`).join('');
    const svg550 = `<svg xmlns="http://www.w3.org/2000/svg">
      <defs>
        <g id="baseGroup">
          ${rects49}
        </g>
      </defs>
      ${uses11}
    </svg>`;
    const res550 = createSafeSvgBlobUrl(svg550);
    expect(res550.ok).toBe(false);
    if (res550.ok) return;
    expect(res550.error).toBe('SVG_EXPANSION_LIMIT_EXCEEDED');
  });

  it('rejects oversized SVGs exceeding 2 MiB (SVG_TOO_LARGE)', () => {
    // Construct string of 2,097,153 bytes
    const base = '<svg viewBox="0 0 10 10"><desc>';
    const close = '</desc></svg>';
    const padLength = MAX_CLIENT_SVG_BYTES + 1 - base.length - close.length;
    const oversized = base + 'A'.repeat(padLength) + close;

    expect(new TextEncoder().encode(oversized).length).toBe(MAX_CLIENT_SVG_BYTES + 1);
    const result = createSafeSvgBlobUrl(oversized);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error).toBe('SVG_TOO_LARGE');
  });

  it('rejects empty inputs and documents with parse errors', () => {
    expect(createSafeSvgBlobUrl('').ok).toBe(false);
    expect(createSafeSvgBlobUrl('   \n  ').ok).toBe(false);

    const badXml = '<svg><unclosed-tag></svg>';
    const badRes = createSafeSvgBlobUrl(badXml);
    // Either parse error or sanitized empty
    expect(badRes.ok).toBe(false);
  });

  it('handles missing use targets safely without failing', () => {
    const missingTargetSvg = `<svg xmlns="http://www.w3.org/2000/svg">
      <use href="#missing-id" />
    </svg>`;
    const res = createSafeSvgBlobUrl(missingTargetSvg);
    expect(res.ok).toBe(true);
  });

  it('rejects markup lacking a root svg element (SVG_EMPTY)', () => {
    // eslint-disable-next-line @typescript-eslint/unbound-method
    const originalParseFromString = DOMParser.prototype.parseFromString;
    let svgCount = 0;
    try {
      DOMParser.prototype.parseFromString = function (markup: string, type: DOMParserSupportedType) {
        if (type === 'image/svg+xml') {
          svgCount++;
          if (svgCount === 2) {
            return originalParseFromString.call(this, '<not-svg><item/></not-svg>', type);
          }
        }
        return originalParseFromString.call(this, markup, type);
      };

      const res = createSafeSvgBlobUrl('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>');
      expect(res.ok).toBe(false);
      if (res.ok) return;
      expect(res.error).toBe('SVG_EMPTY');
      expect(res.message).toBe('No root <svg> element found.');
    } finally {
      DOMParser.prototype.parseFromString = originalParseFromString;
    }
  });

  it('rejects markup that sanitizes to empty string (SVG_EMPTY)', () => {
    const strippedMarkup = '<script>alert(1)</script>';
    const res = createSafeSvgBlobUrl(strippedMarkup);
    expect(res.ok).toBe(false);
    if (res.ok) return;
    expect(res.error).toBe('SVG_EMPTY');
    expect(res.message).toBe('Sanitized SVG content is empty.');
  });

  it('strips non-fragment href and xlink:href and defense-in-depth on* attributes', () => {
    // eslint-disable-next-line @typescript-eslint/unbound-method
    const originalParseFromString = DOMParser.prototype.parseFromString;
    let count = 0;
    try {
      DOMParser.prototype.parseFromString = function (markup: string, type: DOMParserSupportedType) {
        if (type === 'image/svg+xml') {
          count++;
          if (count === 2) {
            const doc = originalParseFromString.call(
              this,
              '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><rect id="r" onclick="evil()" href="javascript:bad()" xlink:href="https://evil.test" /></svg>',
              type,
            );
            return doc;
          }
        }
        return originalParseFromString.call(this, markup, type);
      };

      const res = createSafeSvgBlobUrl('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>');
      expect(res.ok).toBe(true);
      if (!res.ok) return;
      expect(res.cleanSvg).not.toContain('onclick');
      expect(res.cleanSvg).not.toContain('javascript:');
      expect(res.cleanSvg).not.toContain('https://evil.test');
    } finally {
      DOMParser.prototype.parseFromString = originalParseFromString;
    }
  });

  it('handles parsererror in sanitized document step (SVG_PARSE_ERROR)', () => {
    // eslint-disable-next-line @typescript-eslint/unbound-method
    const originalParseFromString = DOMParser.prototype.parseFromString;
    let count = 0;
    try {
      DOMParser.prototype.parseFromString = function (markup: string, type: DOMParserSupportedType) {
        if (type === 'image/svg+xml') {
          count++;
          if (count === 2) {
            return originalParseFromString.call(this, '<parsererror>Malformed sanitized XML</parsererror>', type);
          }
        }
        return originalParseFromString.call(this, markup, type);
      };

      const res = createSafeSvgBlobUrl('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>');
      expect(res.ok).toBe(false);
      if (res.ok) return;
      expect(res.error).toBe('SVG_PARSE_ERROR');
      expect(res.message).toBeDefined();
    } finally {
      DOMParser.prototype.parseFromString = originalParseFromString;
    }
  });

  it('handles environment fallbacks for URL createObjectURL and revokeObjectURL', () => {
    // eslint-disable-next-line @typescript-eslint/unbound-method
    const origCreate = URL.createObjectURL;
    // eslint-disable-next-line @typescript-eslint/unbound-method
    const origRevoke = URL.revokeObjectURL;
    try {
      // Test URL.createObjectURL fallback
      (URL as unknown as { createObjectURL: unknown }).createObjectURL = undefined;
      const res = createSafeSvgBlobUrl('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>');
      expect(res.ok).toBe(true);
      if (res.ok) {
        expect(res.blobUrl).toMatch(/^blob:http:\/\/localhost\//);
      }

      // Test safeRevokeObjectURL fallback when revokeObjectURL is undefined
      (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = undefined;
      if (res.ok) {
        expect(() => {
          res.revoke();
        }).not.toThrow();
      }
    } finally {
      URL.createObjectURL = origCreate;
      URL.revokeObjectURL = origRevoke;
    }
  });

  it('handles existing xmlns and valid local fragment hrefs and xlink:hrefs', () => {
    const svgWithLocalRefs = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
      <defs>
        <circle id="c1" r="5" />
      </defs>
      <use href="#c1" />
      <use xlink:href="#c1" />
    </svg>`;
    const res = createSafeSvgBlobUrl(svgWithLocalRefs);
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.cleanSvg).toContain('href="#c1"');
    expect(res.cleanSvg).toContain('xlink:href="#c1"');
  });

  it('handles nested xlink:href references and use elements without href', () => {
    const xlinkTreeSvg = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
      <defs>
        <circle id="leafNode" r="5" />
        <g id="branchGroup">
          <use xlink:href="#leafNode" />
        </g>
      </defs>
      <use xlink:href="#branchGroup" />
      <use id="orphanUse" />
    </svg>`;
    const res = createSafeSvgBlobUrl(xlinkTreeSvg);
    expect(res.ok).toBe(true);
    if (!res.ok) return;
    expect(res.cleanSvg).toContain('xlink:href="#leafNode"');
  });

  it('supports Trusted Types when available and handles policy creation failure', () => {
    const originalTrustedTypes = (window as unknown as { trustedTypes?: unknown }).trustedTypes;
    const createHtmlSpy = vi.fn((s: string) => `trusted-${s}`);
    const mockFactory = {
      createPolicy: vi.fn((_name: string, rules: { createHTML: (s: string) => string }) => ({
        createHTML: (s: string) => {
          createHtmlSpy(s);
          return rules.createHTML(s);
        },
      })),
    };

    try {
      // Test successful policy creation and HTML creation
      (window as unknown as { trustedTypes: unknown }).trustedTypes = mockFactory;
      _resetPolicyForTesting();

      const res = createSafeSvgBlobUrl('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>');
      expect(res.ok).toBe(true);
      expect(mockFactory.createPolicy).toHaveBeenCalledWith('kanban-sanitizer', expect.any(Object));

      // Test policy creation failure (e.g. throws)
      const throwingFactory = {
        createPolicy: vi.fn(() => {
          throw new Error('Policy creation disallowed');
        }),
      };
      (window as unknown as { trustedTypes: unknown }).trustedTypes = throwingFactory;
      _resetPolicyForTesting();

      const resFallback = createSafeSvgBlobUrl('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>');
      expect(resFallback.ok).toBe(true);

      // Test toTrustedScriptUrl with URL and string under policy and fallback
      expect(toTrustedScriptUrl('https://example.com/lib.js')).toBe('https://example.com/lib.js');
      expect(toTrustedScriptUrl(new URL('https://example.com/lib.js'))).toBe('https://example.com/lib.js');
    } finally {
      (window as unknown as { trustedTypes: unknown }).trustedTypes = originalTrustedTypes;
      _resetPolicyForTesting();
    }

    // Now test with policy that supports createScriptURL
    const policyWithScriptUrl = {
      createPolicy: vi.fn((_name: string, rules: { createHTML: (s: string) => string; createScriptURL: (u: string) => string }) => ({
        createHTML: rules.createHTML,
        createScriptURL: (u: string) => `trusted-url-${u}`,
      })),
    };
    (window as unknown as { trustedTypes: unknown }).trustedTypes = policyWithScriptUrl;
    _resetPolicyForTesting();
    try {
      expect(toTrustedScriptUrl('https://example.com/script.js')).toBe('trusted-url-https://example.com/script.js');
      expect(toTrustedScriptUrl(new URL('https://example.com/worker.js'))).toBe('trusted-url-https://example.com/worker.js');
    } finally {
      (window as unknown as { trustedTypes: unknown }).trustedTypes = originalTrustedTypes;
      _resetPolicyForTesting();
    }
  });
});
