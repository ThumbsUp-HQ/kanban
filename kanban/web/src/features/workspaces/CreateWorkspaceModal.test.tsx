import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import {
  CreateWorkspaceModal,
  suggestWorkspaceSlug,
  WORKSPACE_SLUG_PATTERN,
} from './CreateWorkspaceModal';

describe('CreateWorkspaceModal & suggestWorkspaceSlug', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('suggestWorkspaceSlug derives kebab-case slugs properly', () => {
    expect(suggestWorkspaceSlug('')).toBe('');
    expect(suggestWorkspaceSlug('Engineering Team')).toBe('engineering-team');
    expect(suggestWorkspaceSlug('Acme & Co. 2026!')).toBe('acme-co-2026');
    expect(suggestWorkspaceSlug('a')).toBe('a-ws');
    expect(suggestWorkspaceSlug('---hyphen---')).toBe('hyphen');
  });

  it('WORKSPACE_SLUG_PATTERN enforces valid slugs', () => {
    expect(WORKSPACE_SLUG_PATTERN.test('acme-corp')).toBe(true);
    expect(WORKSPACE_SLUG_PATTERN.test('eng')).toBe(true);
    expect(WORKSPACE_SLUG_PATTERN.test('ab')).toBe(false); // min 3 chars
    expect(WORKSPACE_SLUG_PATTERN.test('-invalid')).toBe(false);
    expect(WORKSPACE_SLUG_PATTERN.test('invalid-')).toBe(false);
    expect(WORKSPACE_SLUG_PATTERN.test('Upper-Case')).toBe(false);
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <CreateWorkspaceModal isOpen={false} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('handles name input, slug auto-suggestion, submission, and onCreated callback', async () => {
    const onClose = vi.fn();
    const onCreated = vi.fn();

    vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              authenticated: true,
              csrf_token: 'test-csrf-token',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/api/v1/workspaces') && init?.method === 'POST') {
        const body = JSON.parse(init.body as string) as { name: string; slug: string };
        expect(body.name).toBe('Acme Global');
        expect(body.slug).toBe('acme-global');
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'ws-new-123',
              name: 'Acme Global',
              slug: 'acme-global',
            }),
            { status: 201, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    render(
      <CreateWorkspaceModal
        isOpen={true}
        onClose={onClose}
        onCreated={onCreated}
      />,
    );

    const nameInput = screen.getByLabelText(/Workspace Name/);
    const slugInput = screen.getByLabelText(/Slug/);

    fireEvent.change(nameInput, { target: { value: 'Acme Global' } });
    expect((slugInput as HTMLInputElement).value).toBe('acme-global');

    const submitBtn = screen.getByRole('button', { name: 'Create Workspace' });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith({
        id: 'ws-new-123',
        name: 'Acme Global',
        slug: 'acme-global',
      });
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('displays error message when server returns an error', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ detail: 'Workspace slug already exists' }),
        { status: 409, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    render(
      <CreateWorkspaceModal
        isOpen={true}
        onClose={vi.fn()}
      />,
    );

    const nameInput = screen.getByLabelText(/Workspace Name/);
    fireEvent.change(nameInput, { target: { value: 'Duplicate WS' } });

    const submitBtn = screen.getByRole('button', { name: 'Create Workspace' });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
      expect(screen.getByText('Workspace slug already exists')).toBeDefined();
    });
  });

  it('closes dialog on Escape key and Scrim click', () => {
    const onClose = vi.fn();
    render(
      <CreateWorkspaceModal
        isOpen={true}
        onClose={onClose}
      />,
    );

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    const scrim = screen.getByTestId('create-workspace-scrim');
    fireEvent.click(scrim);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
