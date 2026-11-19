import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AssigneesRow } from './AssigneesRow';
import type { AssigneeItem, AssigneeSuggestionItem } from './railApi';
import type { IssueDetail } from '../drawer/slots';

const mockAssignees: AssigneeItem[] = [
  {
    id: 'asg-1',
    kind: 'principal',
    principal: { id: 'u1', handle: 'maya', display_name: 'Maya Lin', type: 'USER' },
  },
  {
    id: 'asg-2',
    kind: 'principal',
    principal: { id: 'u2', handle: 'kb-bot', display_name: 'KB Bot', type: 'AGENT' },
  },
  {
    id: 'asg-3',
    kind: 'free_text',
    free_text: 'vendor-contact@example.com',
  },
];

const baseIssue: IssueDetail = {
  key: 'KAN-142',
  summary: 'Assignees test',
  project_key: 'KAN',
  assignees: mockAssignees,
};

describe('AssigneesRow', () => {
  it('renders principals and free-text pills with correct emoji hints and text', () => {
    render(
      <AssigneesRow
        issue={baseIssue}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={vi.fn()}
        onRemoveAssignee={vi.fn()}
      />,
    );

    const mayaPill = screen.getByTestId('assignee-principal-maya');
    expect(mayaPill.textContent).toContain('@maya');

    const agentPill = screen.getByTestId('assignee-principal-kb-bot');
    expect(agentPill.textContent).toContain('@kb-bot');

    const externalPill = screen.getByTestId('assignee-freetext-vendor-contact@example.com');
    expect(externalPill.className).toContain('assignee-pill--external');
    expect(externalPill.textContent).toContain('vendor-contact@example.com');
  });

  it('normalizes string assignees with and without @ prefix', () => {
    const stringAssigneesIssue: IssueDetail = {
      ...baseIssue,
      assignees: ['@maya', 'free-agent@corp.com'] as never,
    };

    render(
      <AssigneesRow
        issue={stringAssigneesIssue}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={vi.fn()}
        onRemoveAssignee={vi.fn()}
      />,
    );

    expect(screen.getByTestId('assignee-principal-maya')).toBeDefined();
    expect(screen.getByTestId('assignee-freetext-free-agent@corp.com')).toBeDefined();
  });

  it('fetches suggestions with debounce, adds assignee via click and keyboard Enter', async () => {
    const mockSuggestions: AssigneeSuggestionItem[] = [
      { id: 'u-alex', handle: 'alex', display_name: 'Alex R', type: 'AGENT' },
    ];
    const fetchSuggestions = vi.fn().mockResolvedValue(mockSuggestions);
    const onAddAssignee = vi.fn().mockResolvedValue(undefined);

    render(
      <AssigneesRow
        issue={{ ...baseIssue, assignees: [] }}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={onAddAssignee}
        onRemoveAssignee={vi.fn()}
        fetchSuggestions={fetchSuggestions}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'ale' } });

    await waitFor(
      () => {
        expect(fetchSuggestions).toHaveBeenCalledWith('KAN', 'ale');
      },
      { timeout: 3000 },
    );

    const suggestionBtn = await screen.findByRole('button', { name: /@alex/i });
    expect(suggestionBtn).toBeDefined();

    // Keyboard trigger with Enter
    fireEvent.keyDown(suggestionBtn, { key: 'Enter' });
    expect(onAddAssignee).toHaveBeenCalledWith({ principal: 'alex' });

    // Keyboard trigger with Space
    fireEvent.keyDown(suggestionBtn, { key: ' ' });
    expect(onAddAssignee).toHaveBeenCalledWith({ principal: 'alex' });

    // Keyboard trigger with other key (does nothing)
    fireEvent.keyDown(suggestionBtn, { key: 'ArrowDown' });
  });

  it('allows adding free-text external assignee', async () => {
    const fetchSuggestions = vi.fn().mockResolvedValue([]);
    const onAddAssignee = vi.fn().mockResolvedValue(undefined);

    render(
      <AssigneesRow
        issue={{ ...baseIssue, assignees: [] }}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={onAddAssignee}
        onRemoveAssignee={vi.fn()}
        fetchSuggestions={fetchSuggestions}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'contractor@corp.com' } });

    const addFreeTextBtn = await screen.findByRole(
      'button',
      { name: /Add external label: “contractor@corp\.com”/i },
      { timeout: 3000 },
    );
    fireEvent.click(addFreeTextBtn);

    expect(onAddAssignee).toHaveBeenCalledWith({ free_text: 'contractor@corp.com' });
  });

  it('triggers onRemoveAssignee for principal and free-text', () => {
    const onRemoveAssignee = vi.fn();

    render(
      <AssigneesRow
        issue={baseIssue}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={vi.fn()}
        onRemoveAssignee={onRemoveAssignee}
      />,
    );

    const removeMaya = screen.getByRole('button', { name: 'Remove @maya' });
    fireEvent.click(removeMaya);
    expect(onRemoveAssignee).toHaveBeenCalledWith('asg-1');

    const removeVendor = screen.getByRole('button', { name: 'Remove vendor-contact@example.com' });
    fireEvent.click(removeVendor);
    expect(onRemoveAssignee).toHaveBeenCalledWith('asg-3');
  });

  it('enforces 20 total assignees limit on selection and free-text', async () => {
    const twentyAssignees: AssigneeItem[] = Array.from({ length: 20 }, (_, i) => ({
      id: `asg-${String(i)}`,
      kind: 'principal',
      principal: { id: `u${String(i)}`, handle: `user${String(i)}`, display_name: `U${String(i)}`, type: 'USER' },
    }));

    const onAddAssignee = vi.fn();

    render(
      <AssigneesRow
        issue={{ ...baseIssue, assignees: twentyAssignees }}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={onAddAssignee}
        onRemoveAssignee={vi.fn()}
        fetchSuggestions={vi.fn().mockResolvedValue([{ id: 'u21', handle: 'user21', display_name: 'User 21', type: 'USER' }])}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'user21' } });

    const addBtn = await screen.findByRole('button', { name: /@user21/i }, { timeout: 3000 });
    fireEvent.click(addBtn);

    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Maximum limit of 20 assignees reached.');
    expect(onAddAssignee).not.toHaveBeenCalled();
  });

  it('enforces 10 free-text assignees limit', async () => {
    const tenFreeText: AssigneeItem[] = Array.from({ length: 10 }, (_, i) => ({
      id: `asg-ft-${String(i)}`,
      kind: 'free_text',
      free_text: `ext${String(i)}@corp.com`,
    }));

    const onAddAssignee = vi.fn();

    render(
      <AssigneesRow
        issue={{ ...baseIssue, assignees: tenFreeText }}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={onAddAssignee}
        onRemoveAssignee={vi.fn()}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'ext11@corp.com' } });

    const addBtn = await screen.findByRole('button', { name: /Add external label/i }, { timeout: 3000 });
    fireEvent.click(addBtn);

    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Maximum limit of 10 free-text assignees reached.');
    expect(onAddAssignee).not.toHaveBeenCalled();
  });

  it('clears suggestions when query is empty and closes on outside click', () => {
    render(
      <AssigneesRow
        issue={baseIssue}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={vi.fn()}
        onRemoveAssignee={vi.fn()}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'test' } });
    fireEvent.change(input, { target: { value: '' } });

    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('list')).toBeNull();
  });

  it('handles addAssignee and free-text errors gracefully', async () => {
    const onAddAssignee = vi
      .fn()
      .mockRejectedValueOnce(new Error('Network error'))
      .mockRejectedValueOnce(new Error('Free text failed'));

    render(
      <AssigneesRow
        issue={{ ...baseIssue, assignees: [] }}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={onAddAssignee}
        onRemoveAssignee={vi.fn()}
        fetchSuggestions={vi.fn().mockResolvedValue([{ id: 'u1', handle: 'sam', display_name: 'Sam', type: 'USER' }])}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'sam' } });

    const btn = await screen.findByRole('button', { name: /@sam/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Network error');
    });

    fireEvent.change(input, { target: { value: 'custom-text' } });
    const freeTextBtn = await screen.findByRole('button', { name: /Add external label/i });
    fireEvent.click(freeTextBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Free text failed');
    });
  });

  it('hides edit controls when canEdit is false', () => {
    render(
      <AssigneesRow
        issue={baseIssue}
        projectKey="KAN"
        canEdit={false}
        onAddAssignee={vi.fn()}
        onRemoveAssignee={vi.fn()}
      />,
    );

    expect(screen.queryByRole('combobox')).toBeNull();
    expect(screen.queryByRole('button', { name: /Remove/i })).toBeNull();
  });

  it('handles fetchSuggestions network rejection and hides free-text when exact match exists', async () => {
    const fetchSuggestions = vi
      .fn()
      .mockRejectedValueOnce(new Error('Suggestions failed'))
      .mockResolvedValueOnce([
        { id: 'u-exact', handle: 'exactuser', display_name: 'Exact User', type: 'USER' },
      ]);

    render(
      <AssigneesRow
        issue={{ ...baseIssue, assignees: [] }}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={vi.fn()}
        onRemoveAssignee={vi.fn()}
        fetchSuggestions={fetchSuggestions}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'failing' } });

    await waitFor(() => {
      expect(fetchSuggestions).toHaveBeenCalledWith('KAN', 'failing');
    });

    // Exact match query test
    fireEvent.change(input, { target: { value: 'exactuser' } });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /@exactuser/i })).toBeDefined();
      expect(screen.queryByRole('button', { name: /Add external label/i })).toBeNull();
    });
  });

  it('enforces totalCount limit on free-text addition and handles non-Error rejection', async () => {
    const twentyAssignees: AssigneeItem[] = Array.from({ length: 20 }, (_, i) => ({
      id: `asg-${String(i)}`,
      kind: 'principal',
      principal: { id: `u${String(i)}`, handle: `user${String(i)}`, display_name: `U${String(i)}`, type: 'USER' },
    }));

    const onAddAssignee = vi.fn().mockRejectedValue('raw string failure');

    render(
      <AssigneesRow
        issue={{ ...baseIssue, assignees: twentyAssignees }}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={onAddAssignee}
        onRemoveAssignee={vi.fn()}
        fetchSuggestions={vi.fn().mockResolvedValue([])}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'overflow@corp.com' } });

    const addBtn = await screen.findByRole('button', { name: /Add external label/i });
    fireEvent.click(addBtn);

    expect(screen.getByRole('alert').textContent).toContain('Maximum limit of 20 assignees reached.');
  });

  it('handles non-Error rejection on suggestion selection and renders USER suggestions without agent hint', async () => {
    const onAddAssignee = vi.fn().mockRejectedValue('raw suggestion rejection');
    const mockSuggestions: AssigneeSuggestionItem[] = [
      { id: 'u-sam', handle: 'sam', display_name: 'Sam User', type: 'USER' },
    ];

    render(
      <AssigneesRow
        issue={{ ...baseIssue, assignees: [] }}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={onAddAssignee}
        onRemoveAssignee={vi.fn()}
        fetchSuggestions={vi.fn().mockResolvedValue(mockSuggestions)}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'sam' } });

    const btn = await screen.findByRole('button', { name: /@sam/i });
    expect(screen.queryByLabelText('Autonomous agent')).toBeNull();
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Failed to add assignee');
    });
  });

  it('handles non-Error rejection on free text addition and renders Searching loading indicator', async () => {
    let resolveSlowFetch: ((val: AssigneeSuggestionItem[]) => void) | undefined;
    const slowFetch = vi.fn().mockImplementation(
      () =>
        new Promise<AssigneeSuggestionItem[]>((resolve) => {
          resolveSlowFetch = resolve;
        }),
    );
    const onAddAssignee = vi.fn().mockRejectedValue('raw freetext rejection');

    render(
      <AssigneesRow
        issue={{ ...baseIssue, assignees: [] }}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={onAddAssignee}
        onRemoveAssignee={vi.fn()}
        fetchSuggestions={slowFetch}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'loadingtest' } });

    await waitFor(() => {
      expect(screen.getByText('Searching...')).toBeDefined();
    });

    resolveSlowFetch?.([]);

    // Free text non-Error rejection
    const addBtn = await screen.findByRole('button', { name: /Add external label/i });
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Failed to add free-text assignee');
    });
  });

  it('handles undefined assignees and cleans up debounce timer on rapid input', () => {
    const { unmount } = render(
      <AssigneesRow
        issue={{ ...baseIssue, assignees: undefined }}
        projectKey="KAN"
        canEdit={true}
        onAddAssignee={vi.fn()}
        onRemoveAssignee={vi.fn()}
        fetchSuggestions={vi.fn().mockResolvedValue([])}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'first' } });
    fireEvent.change(input, { target: { value: 'second' } });
    unmount();
  });
});
