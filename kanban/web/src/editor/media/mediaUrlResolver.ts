/**
 * Media URL Resolver & Air-Gap Shield (KB-P3-48, S5.4).
 * Resolves attachment:// URIs, routes external images through /api/v1/media-proxy,
 * and intercepts requests when air_gap_mode is active.
 */

export type ResolvedMediaKind =
  | 'local'
  | 'attachment'
  | 'proxied-external'
  | 'airgap-blocked'
  | 'blob'
  | 'data'
  | 'relative'
  | 'invalid';

export interface ResolveMediaOptions {
  readonly airGapMode?: boolean;
  readonly attachmentMap?: Readonly<Record<string, string>>;
  readonly resolveAttachmentUrl?: ((attachmentId: string) => string) | undefined;
}

export interface ResolvedMediaUrl {
  readonly kind: ResolvedMediaKind;
  readonly url: string;
  readonly originalUrl: string;
  readonly isExternalProxied: boolean;
  readonly isAirGapBlocked: boolean;
  readonly originalHost?: string;
}

/**
 * Resolves an arbitrary image source URL against security, proxy, and air-gap policies.
 */
export function resolveMediaUrl(
  rawUrl: string,
  options: ResolveMediaOptions = {},
): ResolvedMediaUrl {
  const trimmed = rawUrl ? rawUrl.trim() : '';

  if (!trimmed) {
    return {
      kind: 'invalid',
      url: '',
      originalUrl: rawUrl,
      isExternalProxied: false,
      isAirGapBlocked: false,
    };
  }

  // 1. Handle blob: and data: URIs
  if (trimmed.startsWith('blob:')) {
    return {
      kind: 'blob',
      url: trimmed,
      originalUrl: trimmed,
      isExternalProxied: false,
      isAirGapBlocked: false,
    };
  }

  if (trimmed.startsWith('data:image/')) {
    return {
      kind: 'data',
      url: trimmed,
      originalUrl: trimmed,
      isExternalProxied: false,
      isAirGapBlocked: false,
    };
  }

  // 2. Handle attachment://<id> protocol
  if (trimmed.startsWith('attachment://')) {
    const rawId = trimmed.replace('attachment://', '');
    const cleanId = rawId.replace(/^att_/, '');
    const mapped =
      options.resolveAttachmentUrl?.(cleanId) ??
      options.resolveAttachmentUrl?.(rawId) ??
      options.attachmentMap?.[cleanId] ??
      options.attachmentMap?.[rawId];
    const resolvedUrl = mapped ?? `/api/v1/attachments/${cleanId}`;
    return {
      kind: 'attachment',
      url: resolvedUrl,
      originalUrl: trimmed,
      isExternalProxied: false,
      isAirGapBlocked: false,
    };
  }

  // 3. Handle relative paths
  if (trimmed.startsWith('/') && !trimmed.startsWith('//')) {
    const isProxy = trimmed.startsWith('/api/v1/media-proxy');
    return {
      kind: isProxy ? 'proxied-external' : 'relative',
      url: trimmed,
      originalUrl: trimmed,
      isExternalProxied: isProxy,
      isAirGapBlocked: false,
    };
  }

  // 4. Handle external HTTP / HTTPS URLs
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    let parsedHost = 'external-host';
    try {
      const parsed = new URL(trimmed);
      parsedHost = parsed.hostname;
    } catch {
      // Invalid URL format
      return {
        kind: 'invalid',
        url: '',
        originalUrl: trimmed,
        isExternalProxied: false,
        isAirGapBlocked: false,
      };
    }

    // Air-gap mode check: completely block external media with zero network calls
    if (options.airGapMode) {
      return {
        kind: 'airgap-blocked',
        url: '',
        originalUrl: trimmed,
        isExternalProxied: false,
        isAirGapBlocked: true,
        originalHost: parsedHost,
      };
    }

    // Already routed through /api/v1/media-proxy?
    if (trimmed.includes('/api/v1/media-proxy')) {
      return {
        kind: 'proxied-external',
        url: trimmed,
        originalUrl: trimmed,
        isExternalProxied: true,
        isAirGapBlocked: false,
        originalHost: parsedHost,
      };
    }

    // Route through anonymous media-proxy
    const proxyUrl = `/api/v1/media-proxy?u=${encodeURIComponent(trimmed)}`;
    return {
      kind: 'proxied-external',
      url: proxyUrl,
      originalUrl: trimmed,
      isExternalProxied: true,
      isAirGapBlocked: false,
      originalHost: parsedHost,
    };
  }

  // 5. Unrecognized or disallowed protocol (e.g. javascript:, file:, etc.)
  return {
    kind: 'invalid',
    url: '',
    originalUrl: trimmed,
    isExternalProxied: false,
    isAirGapBlocked: false,
  };
}
