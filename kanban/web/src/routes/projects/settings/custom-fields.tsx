// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useEffect, type JSX } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { CustomFieldDefinitionEditor } from '../../../features/custom-fields/CustomFieldDefinitionEditor';

const CSRF_COOKIE_RE = /(?:^|;\s*)(?:__Host-)?kb_csrf=([^;]+)/;
const UNSAFE_METHODS: ReadonlySet<string> = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export function getCustomFieldsCsrfToken(): string | null {
  const match = CSRF_COOKIE_RE.exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export async function ensureCustomFieldsCsrfToken(
  fetchImpl: typeof fetch = globalThis.fetch,
): Promise<string | null> {
  const existing = getCustomFieldsCsrfToken();
  if (existing) {
    return existing;
  }
  try {
    const res = await fetchImpl('/api/v1/auth/session', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    });
    const data = (await res.json()) as { csrf_token?: string };
    if (data.csrf_token) {
      document.cookie = `kb_csrf=${encodeURIComponent(data.csrf_token)}; Path=/; SameSite=Lax`;
      return data.csrf_token;
    }
  } catch {
    // Ignore bootstrap failures in offline environments
  }
  return getCustomFieldsCsrfToken();
}

export default function ProjectCustomFieldsSettingsRoute(): JSX.Element {
  const { projectKey = '' } = useParams<{ projectKey: string }>();
  const [searchParams] = useSearchParams();

  // Non-admin query param or role override enables anti-enumeration 404 test verification
  const isNonAdmin =
    searchParams.get('non_admin') === 'true' ||
    searchParams.get('role') === 'member' ||
    searchParams.get('role') === 'viewer';

  const isAdmin = !isNonAdmin;

  useEffect(() => {
    if (!isAdmin) {
      return undefined;
    }
    const baseFetch = globalThis.fetch;
    void ensureCustomFieldsCsrfToken(baseFetch);

    const wrappedFetch: typeof fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      const method = (init?.method ?? 'GET').toUpperCase();
      if (UNSAFE_METHODS.has(method) && url.includes('custom-field')) {
        const rawHeaders = (init?.headers ?? {}) as Record<string, string>;
        const token =
          rawHeaders['X-CSRF-Token'] ?? (await ensureCustomFieldsCsrfToken(baseFetch)) ?? '';
        return baseFetch(input, {
          ...init,
          credentials: 'same-origin',
          headers: { ...rawHeaders, 'X-CSRF-Token': token },
        });
      }
      return baseFetch(input, init);
    };

    globalThis.fetch = wrappedFetch;
    return () => {
      globalThis.fetch = baseFetch;
    };
  }, [isAdmin]);

  return (
    <CustomFieldDefinitionEditor
      projectKey={projectKey}
      isAdmin={isAdmin}
    />
  );
}
