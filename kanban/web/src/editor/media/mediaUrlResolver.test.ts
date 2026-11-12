/**
 * Unit Tests for Media URL Resolver & Air-Gap Interceptor (KB-P3-48, S5.4).
 */

import { describe, it, expect } from 'vitest';
import { resolveMediaUrl } from './mediaUrlResolver';

describe('mediaUrlResolver', () => {
  it('resolves external https and http URLs to anonymous media-proxy', () => {
    const raw = 'https://cdn.example.com/assets/arch.png';
    const result = resolveMediaUrl(raw);

    expect(result.kind).toBe('proxied-external');
    expect(result.isExternalProxied).toBe(true);
    expect(result.isAirGapBlocked).toBe(false);
    expect(result.originalHost).toBe('cdn.example.com');
    expect(result.url).toBe(`/api/v1/media-proxy?u=${encodeURIComponent(raw)}`);
    expect(result.originalUrl).toBe(raw);
  });

  it('preserves URLs already containing /api/v1/media-proxy', () => {
    const preProxied = '/api/v1/media-proxy?u=https%3A%2F%2Fother.test%2Fa.png&sig=abcd1234';
    const result = resolveMediaUrl(preProxied);

    expect(result.kind).toBe('proxied-external');
    expect(result.isExternalProxied).toBe(true);
    expect(result.url).toBe(preProxied);

    const fullPreProxied = 'https://kanban.hackedyour.info/api/v1/media-proxy?u=abc';
    const resultFull = resolveMediaUrl(fullPreProxied);
    expect(resultFull.kind).toBe('proxied-external');
    expect(resultFull.isExternalProxied).toBe(true);
    expect(resultFull.url).toBe(fullPreProxied);
  });

  it('blocks external images with zero network calls in air_gap_mode', () => {
    const raw = 'https://external-cdn.evil.test/metrics.png';
    const result = resolveMediaUrl(raw, { airGapMode: true });

    expect(result.kind).toBe('airgap-blocked');
    expect(result.isAirGapBlocked).toBe(true);
    expect(result.isExternalProxied).toBe(false);
    expect(result.url).toBe('');
    expect(result.originalHost).toBe('external-cdn.evil.test');
  });

  it('resolves attachment:// URLs with and without attachment map', () => {
    const raw = 'attachment://att-9988-uuid';
    const withoutMap = resolveMediaUrl(raw);
    expect(withoutMap.kind).toBe('attachment');
    expect(withoutMap.url).toBe('/api/v1/attachments/att-9988-uuid');
    expect(withoutMap.isExternalProxied).toBe(false);
    expect(withoutMap.isAirGapBlocked).toBe(false);

    const withMap = resolveMediaUrl(raw, {
      attachmentMap: {
        'att-9988-uuid': '/custom/signed/download/url',
      },
    });
    expect(withMap.kind).toBe('attachment');
    expect(withMap.url).toBe('/custom/signed/download/url');
  });

  it('handles blob: and data:image/ URIs cleanly', () => {
    const blobUri = 'blob:http://localhost:3000/1234-uuid';
    const blobRes = resolveMediaUrl(blobUri);
    expect(blobRes.kind).toBe('blob');
    expect(blobRes.url).toBe(blobUri);
    expect(blobRes.isExternalProxied).toBe(false);

    const dataUri = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY44YAAAAASUVORK5CYII=';
    const dataRes = resolveMediaUrl(dataUri);
    expect(dataRes.kind).toBe('data');
    expect(dataRes.url).toBe(dataUri);
    expect(dataRes.isExternalProxied).toBe(false);
  });

  it('handles relative local paths', () => {
    const relative = '/static/images/logo.png';
    const result = resolveMediaUrl(relative);
    expect(result.kind).toBe('relative');
    expect(result.url).toBe(relative);
    expect(result.isExternalProxied).toBe(false);
  });

  it('rejects empty, invalid, and dangerous URI schemes', () => {
    expect(resolveMediaUrl('').kind).toBe('invalid');
    expect(resolveMediaUrl('   ').kind).toBe('invalid');
    expect(resolveMediaUrl('javascript:alert(1)').kind).toBe('invalid');
    expect(resolveMediaUrl('data:text/html,<script>').kind).toBe('invalid');
    expect(resolveMediaUrl('file:///etc/passwd').kind).toBe('invalid');
    expect(resolveMediaUrl('http://[::1]:bad_port').kind).toBe('invalid');
  });
});
