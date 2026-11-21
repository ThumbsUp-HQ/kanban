import { useEffect } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router';

export const ISSUE_KEY_REGEX = /^[A-Z][A-Z0-9]{1,9}-[1-9][0-9]{0,8}$/;
export const FULL_SCREEN_PATH_REGEX = /^(?:\/projects|\/w\/[^/]+\/p)\/([^/]+)\/issues\/([^/?#]+)/;
export const PROJECT_PATH_REGEX = /^(?:\/projects|\/w\/[^/]+\/p)\/([^/]+)/;

export interface IssueSurfaceRouteState {
  readonly issueKey: string | null;
  readonly projectKey: string | null;
  readonly mode: 'drawer' | 'full' | null;
}

export function isValidIssueKey(
  key: string | null | undefined,
  projectKey: string | null | undefined,
): boolean {
  if (!key || !projectKey) {
    return false;
  }
  return ISSUE_KEY_REGEX.test(key);
}

export function toFullScreenPath(
  projectKey: string,
  issueKey: string,
  search?: string | URLSearchParams | { search?: string | undefined },
): string {
  let rawSearch = '';
  if (typeof search === 'string') {
    rawSearch = search;
  } else if (search && typeof search === 'object' && 'search' in search) {
    rawSearch = search.search ?? '';
  } else if (search instanceof URLSearchParams) {
    rawSearch = search.toString();
  }
  const params = new URLSearchParams(rawSearch);
  params.delete('peek');
  const qs = params.toString();
  return `/projects/${projectKey}/issues/${issueKey}${qs ? `?${qs}` : ''}`;
}

export function toPeekPath(
  location: { pathname: string; search?: string | undefined },
  issueKey: string | null,
): string {
  const params = new URLSearchParams(location.search ?? '');
  if (issueKey) {
    params.set('peek', issueKey);
  } else {
    params.delete('peek');
  }
  const qs = params.toString();

  let basePath = location.pathname;
  const fullMatch = /^(?:\/projects|\/w\/[^/]+\/p)\/([^/]+)\/issues\/[^/?#]+/.exec(basePath);
  if (fullMatch?.[1]) {
    basePath = basePath.includes('/w/')
      ? basePath.replace(/\/issues\/[^/?#]+.*$/, '/issues')
      : `/projects/${fullMatch[1]}/issues`;
  }

  return `${basePath}${qs ? `?${qs}` : ''}`;
}

export function useIssueSurfaceRoute(): IssueSurfaceRouteState {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useParams<{ projectKey?: string; issueKey?: string }>();
  const [searchParams] = useSearchParams();

  const pathname = location.pathname;
  const rawPeek = searchParams.get('peek');

  const pathMatch = PROJECT_PATH_REGEX.exec(pathname);
  const rawProject = params.projectKey ?? (pathMatch?.[1] ?? null);
  const isDevRoute = pathname.startsWith('/__dev/');
  const projectKey = rawProject ?? (isDevRoute && rawPeek ? (rawPeek.split('-')[0] ?? null) : null);

  const isInvalidPeek = rawPeek !== null && !isValidIssueKey(rawPeek, projectKey);

  useEffect(() => {
    if (isInvalidPeek) {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete('peek');
      const nextQs = nextParams.toString();
      const nextUrl = `${pathname}${nextQs ? `?${nextQs}` : ''}`;
      void navigate(nextUrl, { replace: true });
    }
  }, [isInvalidPeek, searchParams, pathname, navigate]);

  const fullMatch = FULL_SCREEN_PATH_REGEX.exec(pathname);
  if (fullMatch) {
    const routeProject = params.projectKey ?? (fullMatch[1] ?? '');
    const routeIssue = params.issueKey ?? (fullMatch[2] ?? '');
    if (isValidIssueKey(routeIssue, routeProject)) {
      return {
        issueKey: routeIssue,
        projectKey: routeProject,
        mode: 'full',
      };
    }
    return {
      issueKey: null,
      projectKey: routeProject,
      mode: null,
    };
  }

  if (rawPeek !== null) {
    if (isValidIssueKey(rawPeek, projectKey)) {
      return {
        issueKey: rawPeek,
        projectKey,
        mode: 'drawer',
      };
    }

    return {
      issueKey: null,
      projectKey,
      mode: null,
    };
  }

  return {
    issueKey: null,
    projectKey,
    mode: null,
  };
}
