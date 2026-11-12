import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, useLocation, Route, Routes } from 'react-router';
import {
  useIssueSurfaceRoute,
  isValidIssueKey,
  toFullScreenPath,
  toPeekPath,
  ISSUE_KEY_REGEX,
} from './useIssueSurfaceRoute';

describe('useIssueSurfaceRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('isValidIssueKey', () => {
    it('validates keys against regex and projectKey prefix strictly', () => {
      expect(isValidIssueKey('KAN-142', 'KAN')).toBe(true);
      expect(isValidIssueKey('PROJ-1', 'PROJ')).toBe(true);
      expect(isValidIssueKey('KAN-0', 'KAN')).toBe(false); // cannot be 0
      expect(isValidIssueKey('KAN-142', 'OTHER')).toBe(false); // prefix mismatch
      expect(isValidIssueKey('javascript:alert(1)', 'KAN')).toBe(false);
      expect(isValidIssueKey('<img src=x>', 'KAN')).toBe(false);
      expect(isValidIssueKey('../../admin', 'KAN')).toBe(false);
      expect(isValidIssueKey(null, 'KAN')).toBe(false);
      expect(isValidIssueKey('KAN-142', null)).toBe(false);
    });

    it('validates ISSUE_KEY_REGEX boundaries', () => {
      expect(ISSUE_KEY_REGEX.test('A-1')).toBe(false); // prefix min 2
      expect(ISSUE_KEY_REGEX.test('AB-1')).toBe(true);
      expect(ISSUE_KEY_REGEX.test('TOOLONGPREFIX-1')).toBe(false); // prefix max 10
      expect(ISSUE_KEY_REGEX.test('KAN-123456789')).toBe(true);
      expect(ISSUE_KEY_REGEX.test('KAN-1234567890')).toBe(false); // number max 9 digits
    });
  });

  describe('path formatting helpers', () => {
    it('toFullScreenPath builds relative path preserving search params without peek', () => {
      expect(toFullScreenPath('KAN', 'KAN-142')).toBe('/projects/KAN/issues/KAN-142');
      expect(toFullScreenPath('KAN', 'KAN-142', '?layout=board&peek=KAN-142')).toBe(
        '/projects/KAN/issues/KAN-142?layout=board',
      );
      expect(toFullScreenPath('KAN', 'KAN-142', { search: '?layout=board' })).toBe(
        '/projects/KAN/issues/KAN-142?layout=board',
      );
      expect(toFullScreenPath('KAN', 'KAN-142', new URLSearchParams('layout=board'))).toBe(
        '/projects/KAN/issues/KAN-142?layout=board',
      );
    });

    it('toPeekPath updates peek param preserving other params', () => {
      const loc = { pathname: '/projects/KAN/issues', search: '?layout=board' };
      expect(toPeekPath(loc, 'KAN-142')).toBe('/projects/KAN/issues?layout=board&peek=KAN-142');
      expect(toPeekPath({ pathname: '/projects/KAN/issues' }, 'KAN-142')).toBe(
        '/projects/KAN/issues?peek=KAN-142',
      );
      expect(toPeekPath({ pathname: '/projects/KAN/issues', search: '?peek=KAN-142' }, null)).toBe(
        '/projects/KAN/issues',
      );
    });
  });

  describe('Required Test Case 2: Security & negative peek validation', () => {
    const maliciousValues = [
      'javascript:alert(1)',
      '<img src=x>',
      '../../admin',
      'OTHER-1',
      'A'.repeat(10000),
    ];

    for (const badPeek of maliciousValues) {
      it(`removes invalid peek "${badPeek.slice(0, 20)}" via replace navigation and returns null`, () => {
        let currentLocation: { pathname: string; search: string } | null = null;

        const wrapper = ({ children }: { children?: React.ReactNode }) => {
          return React.createElement(
            MemoryRouter,
            {
              initialEntries: [
                `/projects/KAN/issues?layout=board&peek=${encodeURIComponent(badPeek)}`,
              ],
            },
            React.createElement(LocationTracker, {
              onLocation: (loc) => {
                currentLocation = loc;
              },
            }),
            children,
          );
        };

        const { result } = renderHook(() => useIssueSurfaceRoute(), { wrapper });

        expect(result.current.issueKey).toBeNull();
        expect(result.current.mode).toBeNull();

        // Check that peek was stripped from URL
        const loc = currentLocation as { pathname: string; search: string } | null;
        expect(loc?.search).not.toContain('peek');
        expect(loc?.search).toBe('?layout=board');
      });
    }

    it('returns mode: "full" when on full-screen issue path', () => {
      const wrapper = ({ children }: { children?: React.ReactNode }) =>
        React.createElement(
          MemoryRouter,
          { initialEntries: ['/projects/KAN/issues/KAN-142'] },
          children,
        );

      const { result } = renderHook(() => useIssueSurfaceRoute(), { wrapper });

      expect(result.current.mode).toBe('full');
      expect(result.current.issueKey).toBe('KAN-142');
      expect(result.current.projectKey).toBe('KAN');
    });

    it('returns mode: "drawer" when valid peek is present on project path', () => {
      const wrapper = ({ children }: { children?: React.ReactNode }) =>
        React.createElement(
          MemoryRouter,
          { initialEntries: ['/projects/KAN/issues?peek=KAN-142'] },
          children,
        );

      const { result } = renderHook(() => useIssueSurfaceRoute(), { wrapper });

      expect(result.current.mode).toBe('drawer');
      expect(result.current.issueKey).toBe('KAN-142');
      expect(result.current.projectKey).toBe('KAN');
    });

    it('returns mode: null when neither peek nor issue detail route is active', () => {
      const wrapper = ({ children }: { children?: React.ReactNode }) =>
        React.createElement(
          MemoryRouter,
          { initialEntries: ['/projects/KAN/issues'] },
          children,
        );

      const { result } = renderHook(() => useIssueSurfaceRoute(), { wrapper });

      expect(result.current.mode).toBeNull();
      expect(result.current.issueKey).toBeNull();
    });

    it('returns mode: "drawer" when valid peek is on dev story route', () => {
      const wrapper = ({ children }: { children?: React.ReactNode }) =>
        React.createElement(
          MemoryRouter,
          { initialEntries: ['/__dev/drawer?peek=KAN-142'] },
          children,
        );

      const { result } = renderHook(() => useIssueSurfaceRoute(), { wrapper });

      expect(result.current.mode).toBe('drawer');
      expect(result.current.issueKey).toBe('KAN-142');
      expect(result.current.projectKey).toBe('KAN');
    });

    it('returns mode: null when full-screen path has invalid issue key', () => {
      const wrapper = ({ children }: { children?: React.ReactNode }) =>
        React.createElement(
          MemoryRouter,
          { initialEntries: ['/projects/KAN/issues/INVALID'] },
          children,
        );

      const { result } = renderHook(() => useIssueSurfaceRoute(), { wrapper });

      expect(result.current.mode).toBeNull();
      expect(result.current.issueKey).toBeNull();
      expect(result.current.projectKey).toBe('KAN');
    });

    it('extracts projectKey and issueKey from route params', () => {
      const wrapper = ({ children }: { children?: React.ReactNode }) =>
        React.createElement(
          MemoryRouter,
          { initialEntries: ['/projects/KAN/issues/KAN-142'] },
          React.createElement(
            Routes,
            null,
            React.createElement(Route, {
              path: '/projects/:projectKey/issues/:issueKey',
              element: children as React.ReactElement,
            }),
          ),
        );

      const { result } = renderHook(() => useIssueSurfaceRoute(), { wrapper });

      expect(result.current.mode).toBe('full');
      expect(result.current.issueKey).toBe('KAN-142');
      expect(result.current.projectKey).toBe('KAN');
    });

    it('handles isValidIssueKey falsy inputs correctly', () => {
      expect(isValidIssueKey(null, 'KAN')).toBe(false);
      expect(isValidIssueKey('KAN-1', null)).toBe(false);
      expect(isValidIssueKey('invalid', 'KAN')).toBe(false);
      expect(isValidIssueKey('KAN-1', 'OTHER')).toBe(false);
    });
  });
});

function LocationTracker({
  onLocation,
}: {
  onLocation: (loc: { pathname: string; search: string }) => void;
}) {
  const loc = useLocation();
  React.useEffect(() => {
    onLocation(loc);
  }, [loc, onLocation]);
  return null;
}
