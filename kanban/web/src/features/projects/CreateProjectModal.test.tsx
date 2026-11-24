import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import {
  CreateProjectModal,
  suggestProjectIdentifier,
} from './CreateProjectModal';
import {
  ensureSessionCsrfToken,
  useSessionGuard,
} from '../auth/useSessionGuard';

function GuardProbe({ enabled = true }: { enabled?: boolean }) {
  const state = useSessionGuard(enabled);
  return <div data-testid="guard-status">{state.status}</div>;
}

describe('CreateProjectModal & useSessionGuard', () => {
  beforeEach(() => {
    document.cookie = '__Host-kb_csrf=; Max-Age=0; path=/';
    document.cookie = 'kb_csrf=; Max-Age=0; path=/';
    vi.restoreAllMocks();
  });

  it('suggestProjectIdentifier generates valid uppercase 2-10 char keys', () => {
    expect(suggestProjectIdentifier('')).toBe('');
    expect(suggestProjectIdentifier('Platform Security')).toBe('PLSE');
    expect(suggestProjectIdentifier('Ops')).toBe('OPS');
    expect(suggestProjectIdentifier('A')).toBe('A1');
    expect(suggestProjectIdentifier('123')).toBe('PRJ');
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <MemoryRouter>
        <CreateProjectModal isOpen={false} onClose={vi.fn()} />
      </MemoryRouter>,
    );
    expect(container.firstChild).toBeNull();
  });

  it('validates name and identifier, bootstraps CSRF token, posts to /api/v1/projects, and calls onCreated', async () => {
    const onClose = vi.fn();
    const onCreated = vi.fn();

    vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              authenticated: true,
              csrf_token: 'csrf-tok-123',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/api/v1/projects') && init?.method === 'POST') {
        const headers = init.headers as Record<string, string>;
        expect(headers['X-CSRF-Token']).toBe('csrf-tok-123');
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'proj-1',
              identifier: 'SECOPS',
              name: 'Security Operations',
              description_markdown: 'Hardened project',
              modules_enabled: true,
            }),
            { status: 201, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    render(
      <MemoryRouter>
        <CreateProjectModal
          isOpen={true}
          onClose={onClose}
          onCreated={onCreated}
        />
      </MemoryRouter>,
    );

    const nameInput = screen.getByLabelText('Project Name');
    const idInput = screen.getByLabelText('Identifier (Key)');
    const descInput = screen.getByLabelText('Description (Markdown)');

    // Auto-derived identifier from name
    fireEvent.change(nameInput, { target: { value: 'Security Operations' } });
    expect((idInput as HTMLInputElement).value).toBe('SEOP');

    // Manual identifier override
    fireEvent.change(idInput, { target: { value: 'secops' } });
    expect((idInput as HTMLInputElement).value).toBe('SECOPS');

    // Name change when identifier is touched leaves manual identifier untouched
    fireEvent.change(nameInput, { target: { value: 'Security Operations Updated' } });
    expect((idInput as HTMLInputElement).value).toBe('SECOPS');

    fireEvent.change(descInput, { target: { value: 'Hardened project' } });

    fireEvent.click(screen.getByTestId('create-project-submit'));

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith(
        expect.objectContaining({
          identifier: 'SECOPS',
          name: 'Security Operations',
        }),
      );
    });
    expect(onClose).toHaveBeenCalled();
  });

  it('shows validation errors and API error details cleanly', async () => {
    const onClose = vi.fn();
    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(
          new Response(JSON.stringify({ csrf_token: 'tok-999' }), { status: 200 }),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({ detail: 'Project identifier already exists' }),
          { status: 409, headers: { 'Content-Type': 'application/json' } },
        ),
      );
    });

    render(
      <MemoryRouter>
        <CreateProjectModal isOpen={true} onClose={onClose} />
      </MemoryRouter>,
    );

    const form = screen.getByTestId('create-project-submit').closest('form');
    expect(form).not.toBeNull();
    if (form) {
      fireEvent.submit(form);
    }
    expect(screen.getByTestId('create-project-error').textContent).toContain(
      'Project name is required.',
    );

    const nameInput = screen.getByLabelText('Project Name');
    const idInput = screen.getByLabelText('Identifier (Key)');
    fireEvent.change(nameInput, { target: { value: 'Valid Name' } });
    fireEvent.change(idInput, { target: { value: '1' } });
    if (form) {
      fireEvent.submit(form);
    }
    expect(screen.getByTestId('create-project-error').textContent).toContain(
      'Identifier must be 2-10 uppercase characters',
    );

    fireEvent.change(idInput, { target: { value: 'DUPE' } });
    if (form) {
      fireEvent.submit(form);
    }

    await waitFor(() => {
      expect(screen.getByTestId('create-project-error').textContent).toContain(
        'Project identifier already exists',
      );
    });

    // Non-Escape key does not close
    fireEvent.keyDown(window, { key: 'Tab' });
    expect(onClose).not.toHaveBeenCalled();

    // Close on Escape and scrim click
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('create-project-scrim'));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('ensureSessionCsrfToken reads existing cookie when present and handles 404/network error gracefully', async () => {
    document.cookie = 'kb_csrf=existing-cookie-token; path=/';
    const token = await ensureSessionCsrfToken();
    expect(token).toBe('existing-cookie-token');

    document.cookie = 'kb_csrf=; Max-Age=0; path=/';
    vi.spyOn(window, 'fetch').mockResolvedValueOnce(new Response(null, { status: 404 }));
    expect(await ensureSessionCsrfToken()).toBeNull();

    vi.spyOn(window, 'fetch').mockRejectedValueOnce(new Error('Offline'));
    expect(await ensureSessionCsrfToken()).toBeNull();
  });

  it('useSessionGuard redirects to /setup when initialized is false and /login when authenticated is false', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/setup/status')) {
        return Promise.resolve(
          new Response(JSON.stringify({ initialized: false }), { status: 200 }),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    const { unmount } = render(
      <MemoryRouter initialEntries={['/']}>
        <GuardProbe />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('guard-status').textContent).toBe('redirecting');
    });
    unmount();

    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/setup/status')) {
        return Promise.resolve(
          new Response(JSON.stringify({ initialized: true }), { status: 200 }),
        );
      }
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ authenticated: false, csrf_token: 'pre-csrf' }),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    render(
      <MemoryRouter initialEntries={['/']}>
        <GuardProbe />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('guard-status').textContent).toBe('redirecting');
    });
  });

  it('useSessionGuard sets authenticated when session is active and redirects when mfa_pending is true', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/setup/status')) {
        return Promise.resolve(
          new Response(JSON.stringify({ initialized: true }), { status: 200 }),
        );
      }
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              authenticated: true,
              mfa_pending: true,
              principal_id: 'p-1',
              workspace_id: 'w-1',
              aal_level: 1,
              csrf_token: 'tok-mfa',
            }),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    const { unmount } = render(
      <MemoryRouter initialEntries={['/']}>
        <GuardProbe />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('guard-status').textContent).toBe('redirecting');
    });
    unmount();

    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/setup/status')) {
        return Promise.resolve(
          new Response(JSON.stringify({ initialized: true }), { status: 200 }),
        );
      }
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              authenticated: true,
              mfa_pending: false,
              principal_id: 'p-1',
              workspace_id: 'w-1',
              aal_level: 2,
              csrf_token: 'tok-ok',
            }),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    render(
      <MemoryRouter initialEntries={['/']}>
        <GuardProbe />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('guard-status').textContent).toBe('authenticated');
    });
  });

  it('renders skip culturally loaded sequence numbers checkbox and includes it in POST payload', async () => {
    const onClose = vi.fn();
    const onCreated = vi.fn();
    let sentPayload: Record<string, unknown> | null = null;

    vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              authenticated: true,
              csrf_token: 'csrf-tok-456',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/api/v1/projects') && init?.method === 'POST') {
        sentPayload = typeof init.body === 'string'
          ? (JSON.parse(init.body) as Record<string, unknown>)
          : null;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'proj-safe-seq',
              identifier: 'SAFE',
              name: 'Safe Sequences Project',
              description_markdown: 'No loaded numbers',
              modules_enabled: true,
              skip_loaded_sequence_numbers: true,
            }),
            { status: 201, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    render(
      <MemoryRouter>
        <CreateProjectModal
          isOpen={true}
          onClose={onClose}
          onCreated={onCreated}
        />
      </MemoryRouter>,
    );

    const nameInput = screen.getByLabelText('Project Name');
    fireEvent.change(nameInput, { target: { value: 'Safe Sequences Project' } });
    const idInput = screen.getByLabelText('Identifier (Key)');
    fireEvent.change(idInput, { target: { value: 'SAFE' } });

    const skipCheckbox = screen.getByTestId<HTMLInputElement>('create-project-skip-loaded-seq');
    expect(skipCheckbox).toBeDefined();
    expect(skipCheckbox.checked).toBe(false);

    // Toggle checkbox on
    fireEvent.click(skipCheckbox);
    expect(skipCheckbox.checked).toBe(true);

    const modulesCheckbox = screen.getByLabelText<HTMLInputElement>('Enable project modules');
    expect(modulesCheckbox.checked).toBe(true);
    fireEvent.click(modulesCheckbox);
    expect(modulesCheckbox.checked).toBe(false);

    fireEvent.click(screen.getByTestId('create-project-submit'));

    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith(
        expect.objectContaining({
          identifier: 'SAFE',
          name: 'Safe Sequences Project',
          skip_loaded_sequence_numbers: true,
        }),
      );
    });

    expect(sentPayload).toEqual({
      name: 'Safe Sequences Project',
      identifier: 'SAFE',
      description_markdown: '',
      modules_enabled: false,
      skip_loaded_sequence_numbers: true,
    });
    expect(onClose).toHaveBeenCalled();
  });

  it('handles error response variants, modal buttons, and outside router context', async () => {
    const onClose = vi.fn();
    let errorMode: 'nested' | 'generic' | 'reject' = 'nested';

    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'csrf-1' }), { status: 200 }));
      }
      if (url.includes('/api/v1/projects')) {
        if (errorMode === 'nested') {
          return Promise.resolve(
            new Response(
              JSON.stringify({ detail: { detail: 'Nested detail error' } }),
              { status: 422, headers: { 'Content-Type': 'application/json' } },
            ),
          );
        }
        if (errorMode === 'generic') {
          return Promise.resolve(new Response('Server error', { status: 500 }));
        }
        return Promise.reject(new Error('network failure'));
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    const { unmount } = render(
      <CreateProjectModal isOpen={true} onClose={onClose} />,
    );

    fireEvent.change(screen.getByLabelText('Project Name'), { target: { value: 'Err Proj' } });
    fireEvent.click(screen.getByTestId('create-project-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('create-project-error').textContent).toBe('Nested detail error');
    });

    // 2. Generic HTTP status error
    errorMode = 'generic';
    fireEvent.click(screen.getByTestId('create-project-submit'));
    await waitFor(() => {
      expect(screen.getByTestId('create-project-error').textContent).toBe(
        'Failed to create project (HTTP 500)',
      );
    });

    // 3. Network error throw
    errorMode = 'reject';
    fireEvent.click(screen.getByTestId('create-project-submit'));
    await waitFor(() => {
      expect(screen.getByTestId('create-project-error').textContent).toBe('network failure');
    });

    // 4. Click inside modal dialog does not trigger close
    fireEvent.click(screen.getByTestId('create-project-modal'));
    expect(onClose).not.toHaveBeenCalled();

    // 5. Close button '✕' triggers close
    fireEvent.click(screen.getByLabelText('Close create project modal'));
    expect(onClose).toHaveBeenCalledTimes(1);

    unmount();

    // 6. Suggest project identifier branch where name has single word
    expect(suggestProjectIdentifier('Testing')).toBe('TESTI');
  });

  it('pre-checks skip loaded sequences from workspace settings and omits field if untouched', async () => {
    let sentPayload: Record<string, unknown> | null = null;
    vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/admin/workspace-settings')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ default_skip_loaded_sequence_numbers: true }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(
          new Response(JSON.stringify({ csrf_token: 'csrf-tok' }), { status: 200 }),
        );
      }
      if (url.includes('/api/v1/projects') && init?.method === 'POST') {
        sentPayload = typeof init.body === 'string'
          ? (JSON.parse(init.body) as Record<string, unknown>)
          : null;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'p-1',
              identifier: 'INHR',
              name: 'Inherited Project',
            }),
            { status: 201, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    render(
      <MemoryRouter>
        <CreateProjectModal isOpen={true} onClose={vi.fn()} onCreated={vi.fn()} />
      </MemoryRouter>,
    );

    const nameInput = screen.getByLabelText('Project Name');
    fireEvent.change(nameInput, { target: { value: 'Inherited Project' } });

    const checkbox = await screen.findByTestId<HTMLInputElement>('create-project-skip-loaded-seq');
    // Hydrated from workspace settings
    await waitFor(() => {
      expect(checkbox.checked).toBe(true);
    });

    fireEvent.click(screen.getByTestId('create-project-submit'));

    await waitFor(() => {
      expect(sentPayload).not.toBeNull();
      // Since user did not touch the checkbox, it must be omitted so backend inherits workspace settings
      expect(sentPayload?.skip_loaded_sequence_numbers).toBeUndefined();
    });
  });

  it('covers missing csrfToken, non-Error throw, and omitted onCreated callback', async () => {
    const onClose = vi.fn();
    vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(new Response(JSON.stringify({ authenticated: true }), { status: 200 }));
      }
      if (url.includes('/api/v1/projects') && init?.method === 'POST') {
        const headers = init.headers as Record<string, string>;
        expect(headers['X-CSRF-Token']).toBeUndefined();
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'p-no-csrf',
              identifier: 'NOCSRF',
              name: 'No CSRF Project',
            }),
            { status: 201, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    render(
      <MemoryRouter>
        <CreateProjectModal isOpen={true} onClose={onClose} />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Project Name'), { target: { value: 'No CSRF Project' } });
    fireEvent.click(screen.getByTestId('create-project-submit'));

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('handles non-Error throw in submission catch block', async () => {
    vi.spyOn(window, 'fetch').mockImplementation((input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/admin/workspace-settings')) {
        return Promise.resolve(new Response(JSON.stringify({ default_skip_loaded_sequence_numbers: false }), { status: 200 }));
      }
      if (url.includes('/api/v1/auth/session')) {
        return Promise.resolve(new Response(JSON.stringify({ csrf_token: 'csrf' }), { status: 200 }));
      }
      if (url.includes('/api/v1/projects') && init?.method === 'POST') {
        // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
        return Promise.reject('raw network failure string');
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    render(
      <MemoryRouter>
        <CreateProjectModal isOpen={true} onClose={vi.fn()} />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText('Project Name'), { target: { value: 'Fail Project' } });
    fireEvent.click(screen.getByTestId('create-project-submit'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Could not create project.');
    });
  });

  it('renders Agent-Safe Sequence Numbering help hint with default value (KAN-394)', () => {
    vi.spyOn(window, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (url.includes('/api/v1/admin/workspace-settings')) {
        return Promise.resolve(new Response(JSON.stringify({ default_skip_loaded_sequence_numbers: true }), { status: 200 }));
      }
      return Promise.resolve(new Response(null, { status: 404 }));
    });

    render(
      <MemoryRouter>
        <CreateProjectModal isOpen={true} onClose={vi.fn()} />
      </MemoryRouter>,
    );

    const hintTrigger = screen.getByTestId('create-proj-skip-seq-help');
    expect(hintTrigger).toBeDefined();
    fireEvent.focus(hintTrigger);

    const popover = screen.getByTestId('create-proj-skip-seq-help-popover');
    expect(popover.textContent).toContain('Default:');
    expect(popover.textContent).toContain('Enabled (true)');
  });
});
