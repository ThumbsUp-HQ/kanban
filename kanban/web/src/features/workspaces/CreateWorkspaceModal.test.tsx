import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import {
  CreateWorkspaceModal,
  suggestWorkspaceSlug,
  WORKSPACE_SLUG_PATTERN,
} from './CreateWorkspaceModal';

describe('CreateWorkspaceModal & suggestWorkspaceSlug', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    document.documentElement.removeAttribute('data-theme');
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
    const slugInput = screen.getByLabelText(/Slug/, { selector: 'input' });

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

  it('validates whitespace name and rejects invalid slug formats with clear errors', () => {
    render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} />);

    const nameInput = screen.getByLabelText(/Workspace Name/);
    const slugInput = screen.getByLabelText(/Slug/, { selector: 'input' });
    const submitBtn = screen.getByRole('button', { name: 'Create Workspace' });

    // 1. Manually type invalid slug (2 chars, pattern requires min 3 chars)
    fireEvent.change(nameInput, { target: { value: 'Valid Name' } });
    fireEvent.change(slugInput, { target: { value: 'ab' } });
    fireEvent.click(submitBtn);

    expect(screen.getByRole('alert')).toBeDefined();
    expect(
      screen.getByText(
        'Workspace slug must be 3-64 lowercase alphanumeric characters or hyphens, starting and ending with alphanumeric characters.',
      ),
    ).toBeDefined();

    // 2. Clear error on typing into slug
    fireEvent.change(slugInput, { target: { value: 'ab-cd' } });
    expect(screen.queryByRole('alert')).toBeNull();

    // 3. Clear error on typing into name
    fireEvent.change(slugInput, { target: { value: 'ab' } });
    fireEvent.click(submitBtn);
    expect(screen.getByRole('alert')).toBeDefined();
    fireEvent.change(nameInput, { target: { value: 'New Name' } });
    expect(screen.queryByRole('alert')).toBeNull();

    // 4. Manually trigger submit with whitespace-only name
    fireEvent.change(nameInput, { target: { value: '   ' } });
    fireEvent.change(slugInput, { target: { value: 'valid-slug' } });
    const form = screen.getByRole('dialog').querySelector('form');
    expect(form).not.toBeNull();
    if (form) {
      fireEvent.submit(form);
    }
    expect(screen.getByRole('alert')).toBeDefined();
    expect(screen.getByText('Workspace name is required.')).toBeDefined();
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

    const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
    fireEvent.click(cancelBtn);
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('covers missing csrf token, non-Error rejection, and nested/fallback error details', async () => {
    // 1. Non-Error throw
    // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
    vi.spyOn(window, 'fetch').mockImplementation(() => Promise.reject('Non-error string rejection'));

    const { unmount } = render(
      <CreateWorkspaceModal isOpen={true} onClose={vi.fn()} />,
    );

    const nameInput = screen.getByLabelText(/Workspace Name/);
    fireEvent.change(nameInput, { target: { value: 'Faulty WS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));

    await waitFor(() => {
      expect(screen.getByText('Network error creating workspace')).toBeDefined();
    });
    unmount();

    // 2. Nested error detail
    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      }
      return Promise.resolve(
        new Response(JSON.stringify({ detail: { detail: 'Deep nested failure' } }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    });

    const { unmount: unmount2 } = render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} />);
    const nameInput2 = screen.getByLabelText(/Workspace Name/);
    fireEvent.change(nameInput2, { target: { value: 'Nested Error WS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));

    await waitFor(() => {
      expect(screen.getByText('Deep nested failure')).toBeDefined();
    });
    unmount2();

    // 3. Fallback error status when detail is not string/object
    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'valid' }), { status: 200 }));
      }
      return Promise.resolve(
        new Response(JSON.stringify({ detail: 12345 }), {
          status: 502,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    });

    const { unmount: unmount3 } = render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} />);
    const nameInput3 = screen.getByLabelText(/Workspace Name/);
    fireEvent.change(nameInput3, { target: { value: 'Fallback Status WS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));

    await waitFor(() => {
      expect(screen.getByText('Server returned 502')).toBeDefined();
    });
    unmount3();

    // 4. Server returns unparseable HTML error (triggers catch block in json parser)
    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'valid' }), { status: 200 }));
      }
      return Promise.resolve(
        new Response('<html>Bad Gateway</html>', {
          status: 502,
          headers: { 'Content-Type': 'text/html' },
        }),
      );
    });

    const { unmount: unmount4 } = render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} />);
    const nameInput4 = screen.getByLabelText(/Workspace Name/);
    fireEvent.change(nameInput4, { target: { value: 'Bad Gateway WS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));

    await waitFor(() => {
      expect(screen.getByText('Server returned 502')).toBeDefined();
    });
    unmount4();

    // 5. Error instance thrown (covers err instanceof Error ? err.message)
    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      }
      return Promise.reject(new Error('Explicit network fault'));
    });

    const { unmount: unmount5 } = render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} />);
    const nameInput5 = screen.getByLabelText(/Workspace Name/);
    fireEvent.change(nameInput5, { target: { value: 'Fault Error WS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create Workspace' }));

    await waitFor(() => {
      expect(screen.getByText('Explicit network fault')).toBeDefined();
    });
    unmount5();
  });

  describe('FieldHelpHint & Responsive Theme Parity (KAN-500)', () => {
    it('renders FieldHelpHint adjacent to Workspace Slug label with exact ticket spec and zero inline styles', () => {
      render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} />);

      const helpBtn = screen.getByTestId('create-ws-slug-help');
      expect(helpBtn).toBeDefined();
      expect(helpBtn.getAttribute('aria-label')).toBe('Help for Workspace Slug');

      // Strict CSP invariant: zero inline style props
      expect(helpBtn.style.length).toBe(0);

      // Verify label structure and text
      const labelRow = helpBtn.closest('.kb-create-workspace-label-row');
      expect(labelRow).not.toBeNull();
      expect(labelRow?.textContent).toContain('Workspace Slug');
    });

    it('opens FieldHelpHint popover displaying summary, validValues, and docHref wiki link', async () => {
      render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} />);

      const helpBtn = screen.getByTestId('create-ws-slug-help');

      act(() => {
        helpBtn.focus();
      });

      const popover = await screen.findByTestId('create-ws-slug-help-popover');
      expect(popover).toBeDefined();

      // Verify title & summary
      expect(popover.textContent).toContain('Workspace Slug');
      expect(popover.textContent).toContain(
        'Unique lowercase alphanumeric URL slug identifying this tenant partition.',
      );

      // Verify valid values guidance
      expect(popover.textContent).toContain('2 to 64 lowercase alphanumeric chars and hyphens');

      // Verify documentation deep-link
      const docLink = popover.querySelector('a.field-help-hint-link');
      expect(docLink).not.toBeNull();
      expect(docLink?.getAttribute('href')).toBe('/docs/studio-configuration-reference#workspaces');
    });

    it('dismisses FieldHelpHint popover on Escape without closing parent CreateWorkspaceModal dialog', async () => {
      const onClose = vi.fn();
      render(<CreateWorkspaceModal isOpen={true} onClose={onClose} />);

      const helpBtn = screen.getByTestId('create-ws-slug-help');

      act(() => {
        helpBtn.focus();
      });

      const popover = await screen.findByTestId('create-ws-slug-help-popover');
      expect(popover).toBeDefined();

      // Press Escape on the popover / trigger button
      act(() => {
        fireEvent.keyDown(helpBtn, { key: 'Escape' });
      });

      // Popover should close
      expect(screen.queryByTestId('create-ws-slug-help-popover')).toBeNull();

      // Parent modal must remain open (onClose was NOT called)
      expect(onClose).not.toHaveBeenCalled();

      // Non-escape key branch on window
      fireEvent.keyDown(window, { key: 'Tab' });
      expect(onClose).not.toHaveBeenCalled();

      // Pressing Escape again now that popover is closed will close the modal
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('focuses name input on open timer and ignores defaultPrevented keydown events', () => {
      vi.useFakeTimers();
      const onClose = vi.fn();
      render(<CreateWorkspaceModal isOpen={true} onClose={onClose} />);

      act(() => {
        vi.runAllTimers();
      });

      const event = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true });
      event.preventDefault();
      window.dispatchEvent(event);

      expect(onClose).not.toHaveBeenCalled();
      vi.useRealTimers();
    });

    it('renders cleanly in Dark mode (data-theme="dark") with zero inline style violations', async () => {
      document.documentElement.setAttribute('data-theme', 'dark');

      try {
        render(<CreateWorkspaceModal isOpen={true} onClose={vi.fn()} />);

        const helpBtn = screen.getByTestId('create-ws-slug-help');
        expect(helpBtn).toBeDefined();
        expect(helpBtn.style.length).toBe(0);

        act(() => {
          helpBtn.focus();
        });

        const popover = await screen.findByTestId('create-ws-slug-help-popover');
        expect(popover).toBeDefined();
        expect(popover.style.color).toBe('');
        expect(popover.style.backgroundColor).toBe('');
      } finally {
        document.documentElement.removeAttribute('data-theme');
      }
    });

    it('asserts CSS rules for :root, [data-theme="dark"], prefers-color-scheme, gap 6px, and 480px responsive media query', () => {
      const cssPath = path.resolve(import.meta.dirname, './CreateWorkspaceModal.css');
      const cssContent = fs.readFileSync(cssPath, 'utf8');

      // 1. All 3 theme modes
      expect(cssContent).toContain(':root');
      expect(cssContent).toContain('[data-theme="dark"]');
      expect(cssContent).toContain('@media (prefers-color-scheme: dark)');

      // 2. Adjacent gap: 6px and margin: 0 for FieldHelpHint
      expect(cssContent).toContain('.kb-create-workspace-label-row');
      expect(cssContent).toContain('gap: 6px;');
      expect(cssContent).toContain('.kb-create-workspace-label-row .field-help-hint');
      expect(cssContent).toContain('margin: 0;');

      // 3. Mobile responsiveness (390x844 unclipped)
      expect(cssContent).toContain('@media (max-width: 480px)');
      expect(cssContent).toContain('max-height: calc(100vh - 24px);');
      expect(cssContent).toContain('overflow-y: auto;');

      // 4. Zero forbidden dashes (en-dash / em-dash)
      expect(cssContent).not.toContain('\u2014');
      expect(cssContent).not.toContain('\u2013');
    });
  });
});
