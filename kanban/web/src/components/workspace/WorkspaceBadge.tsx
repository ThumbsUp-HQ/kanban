/**
 * WorkspaceBadge Component (KB-P3-AUDIT-07, KAN-13).
 * Renders a compact 1-2 uppercase initial monogram badge with 6 deterministic
 * theme-safe CSS tone classes. Zero inline styles.
 */

import React, { type JSX } from 'react';
import './WorkspaceBadge.css';

export interface WorkspaceBadgeProps {
  name?: string | null | undefined;
  size?: 'sm' | 'md' | 'lg' | undefined;
  className?: string | undefined;
  testId?: string | undefined;
}

export function getWorkspaceInitials(name?: string | null): string {
  if (!name) return 'K';
  // Strip emojis, brackets, symbols
  const cleaned = name
    .replace(/\[\s*👍\s*\]|[👍]|[[\]]/gu, '')
    .trim();
  if (!cleaned) return 'K';

  const words = cleaned
    .split(/[\s\-_]+/)
    .filter((w) => /[a-zA-Z0-9]/.test(w));

  const w0 = words[0];
  const w1 = words[1];

  if (w0 && w1) {
    const first = w0.charAt(0);
    const second = w1.charAt(0);
    return (first + second).toUpperCase();
  }

  if (w0) {
    const letters = w0.replace(/[^a-zA-Z0-9]/g, '');
    if (letters.length >= 2) {
      return letters.slice(0, 2).toUpperCase();
    }
    return letters.toUpperCase();
  }

  return 'K';
}

export function getWorkspaceTone(name?: string | null): number {
  if (!name) return 1;
  const clean = name.trim().toLowerCase();
  let hash = 0;
  for (let i = 0; i < clean.length; i++) {
    hash = (hash * 31 + clean.charCodeAt(i)) >>> 0;
  }
  return (hash % 6) + 1;
}

export function WorkspaceBadge({
  name,
  size = 'md',
  className = '',
  testId = 'workspace-badge',
}: WorkspaceBadgeProps): JSX.Element {
  const initials = getWorkspaceInitials(name);
  const tone = getWorkspaceTone(name);
  const sizeClass = `workspace-badge--${size}`;
  const toneClass = `workspace-badge--tone-${String(tone)}`;
  const fullClassName = ['workspace-badge', sizeClass, toneClass, className]
    .filter(Boolean)
    .join(' ');

  return (
    <span
      className={fullClassName}
      data-testid={testId}
      aria-hidden="true"
      data-tone={tone}
    >
      {initials}
    </span>
  );
}
