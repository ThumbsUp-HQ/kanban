/**
 * Unit tests for WorkspaceBadge (KB-P3-AUDIT-07, KAN-13).
 */

import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  WorkspaceBadge,
  getWorkspaceInitials,
  getWorkspaceTone,
} from './WorkspaceBadge';

describe('WorkspaceBadge', () => {
  describe('getWorkspaceInitials', () => {
    it('returns K for empty, undefined, or null input', () => {
      expect(getWorkspaceInitials()).toBe('K');
      expect(getWorkspaceInitials(null)).toBe('K');
      expect(getWorkspaceInitials('')).toBe('K');
      expect(getWorkspaceInitials('   ')).toBe('K');
    });

    it('strips emoji and thumbs-up prefixes', () => {
      expect(getWorkspaceInitials('👍kanban')).toBe('KA');
      expect(getWorkspaceInitials('[👍] Default Workspace')).toBe('DW');
      expect(getWorkspaceInitials('[👍]')).toBe('K');
      expect(getWorkspaceInitials('👍')).toBe('K');
    });

    it('handles multi-word workspace names', () => {
      expect(getWorkspaceInitials('Alpha Beta')).toBe('AB');
      expect(getWorkspaceInitials('Platform Engineering Team')).toBe('PE');
      expect(getWorkspaceInitials('core-infra')).toBe('CI');
      expect(getWorkspaceInitials('sec_ops')).toBe('SO');
    });

    it('handles single-word workspace names', () => {
      expect(getWorkspaceInitials('kanban')).toBe('KA');
      expect(getWorkspaceInitials('Engineering')).toBe('EN');
      expect(getWorkspaceInitials('X')).toBe('X');
    });

    it('handles non-alphanumeric fallback', () => {
      expect(getWorkspaceInitials('***')).toBe('K');
    });
  });

  describe('getWorkspaceTone', () => {
    it('returns tone 1 for falsy names', () => {
      expect(getWorkspaceTone(null)).toBe(1);
      expect(getWorkspaceTone('')).toBe(1);
    });

    it('deterministically returns a tone between 1 and 6', () => {
      const tone1 = getWorkspaceTone('kanban');
      const tone2 = getWorkspaceTone('kanban');
      expect(tone1).toBe(tone2);
      expect(tone1).toBeGreaterThanOrEqual(1);
      expect(tone1).toBeLessThanOrEqual(6);

      const names = ['Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta', 'Eta'];
      for (const n of names) {
        const t = getWorkspaceTone(n);
        expect(t).toBeGreaterThanOrEqual(1);
        expect(t).toBeLessThanOrEqual(6);
      }
    });
  });

  describe('Rendering', () => {
    it('renders with default props', () => {
      render(<WorkspaceBadge name="kanban" />);
      const badge = screen.getByTestId('workspace-badge');
      expect(badge).toBeDefined();
      expect(badge.textContent).toBe('KA');
      expect(badge.className).toContain('workspace-badge--md');
      expect(badge.className).toContain('workspace-badge--tone-');
      expect(badge.getAttribute('aria-hidden')).toBe('true');
    });

    it('supports custom size, className, and testId', () => {
      render(
        <WorkspaceBadge
          name="Dev Team"
          size="sm"
          className="custom-class"
          testId="custom-badge"
        />,
      );
      const badge = screen.getByTestId('custom-badge');
      expect(badge.textContent).toBe('DT');
      expect(badge.className).toContain('workspace-badge--sm');
      expect(badge.className).toContain('custom-class');
    });

    it('supports size lg', () => {
      render(<WorkspaceBadge name="Platform" size="lg" />);
      const badge = screen.getByTestId('workspace-badge');
      expect(badge.className).toContain('workspace-badge--lg');
    });

    it('renders fallback K when name is missing', () => {
      render(<WorkspaceBadge />);
      const badge = screen.getByTestId('workspace-badge');
      expect(badge.textContent).toBe('K');
    });
  });
});
