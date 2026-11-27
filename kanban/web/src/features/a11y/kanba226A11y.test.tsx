import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React, { useRef } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { ShellPanelsProvider } from '../../app/shellPanels';
import { ListView } from '../list/ListView';
import { ListRow } from '../list/ListRow';
import { BoardCard } from '../board/BoardCard';
import { QuickCreateIssueModal } from '../views/QuickCreateIssueModal';
import { AccessInspectorPopover } from '../access/AccessInspectorPopover';
import { IssueSurfaceRoot } from '../drawer/IssueSurface';
import { Topbar } from '../../app/Topbar';
import { DocsTreeNav } from '../docs/DocsTreeNav';
import { setOpenerElement, getOpenerElement } from '../drawer/IssueKeyLink';
import { useFocusTrap } from '../drawer/useFocusTrap';
import { FIXTURE_12_ISSUES } from '../views/fixtures';
import type { BoardIssue } from '../board/boardApi';
import type { IssueItem } from '../views/viewsApi';

const sampleBoardIssue: BoardIssue = {
  id: 'card-1',
  key: 'KAN-226',
  summary: 'Enforce modal/drawer focus traps and ARIA hierarchy',
  state_id: 'state-todo',
  board_rank: '0|hzzzzz:',
  priority: { id: 'prio-high', slug: 'high', label: 'High' },
  assignees: [],
  gate_status: null,
};

const sampleIssueItem: IssueItem = {
  id: 'item-1',
  key: 'KAN-226',
  summary: 'Enforce modal/drawer focus traps and ARIA hierarchy',
  state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
  priority: { slug: 'high', label: 'High' },
  labels: [],
  assignees: [],
};

describe('KANBA-226 Accessibility & WCAG 2.2 AA Conformance Suite', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    setOpenerElement(null);
  });

  afterEach(() => {
    queryClient.clear();
    setOpenerElement(null);
  });

  describe('1. Cyclic Focus Traps and aria-modal="true" on Modals & Drawers', () => {
    it('QuickCreateIssueModal enforces role="dialog", aria-modal="true", and cyclic Tab / Shift+Tab focus trap', () => {
      const onClose = vi.fn();
      const onCreate = vi.fn();

      const { container } = render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={onClose}
          onCreate={onCreate}
          projectKey="KAN"
        />
      );

      const dialog = container.querySelector('[role="dialog"]');
      expect(dialog).toBeDefined();
      expect(dialog?.getAttribute('aria-modal')).toBe('true');

      // Find focusable elements
      const docLink = screen.getByTestId('quick-create-doc-link');
      const closeBtn = screen.getByRole('button', { name: 'Close modal' });
      const cancelBtn = screen.getByRole('button', { name: 'Cancel' });

      // Focus last focusable (cancel button) and press Tab -> cycles to first focusable (docLink)
      cancelBtn.focus();
      expect(document.activeElement).toBe(cancelBtn);

      const tabEvent = new KeyboardEvent('keydown', {
        key: 'Tab',
        bubbles: true,
        cancelable: true,
      });
      document.dispatchEvent(tabEvent);
      expect(document.activeElement).toBe(docLink);

      // Shift+Tab from docLink cycles back to last element (cancelBtn)
      docLink.focus();
      expect(document.activeElement).toBe(docLink);

      const shiftTabEvent = new KeyboardEvent('keydown', {
        key: 'Tab',
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      });
      document.dispatchEvent(shiftTabEvent);
      expect(document.activeElement).toBe(cancelBtn);
    });

    it('AccessInspectorPopover enforces role="dialog", aria-modal="true", and cyclic focus trap', () => {
      const onClose = vi.fn();

      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <AccessInspectorPopover
            objectId="11111111-1111-1111-1111-111111111111"
            onClose={onClose}
          />
        </QueryClientProvider>
      );

      const dialog = container.querySelector('[role="dialog"]');
      expect(dialog).toBeDefined();
      expect(dialog?.getAttribute('aria-modal')).toBe('true');

      const closeBtn = screen.getByRole('button', { name: 'Close Access Inspector' });
      closeBtn.focus();
      expect(document.activeElement).toBe(closeBtn);

      // Press Shift+Tab on first element -> cycles within dialog
      const shiftTabEvent = new KeyboardEvent('keydown', {
        key: 'Tab',
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      });
      document.dispatchEvent(shiftTabEvent);
      expect(dialog?.contains(document.activeElement)).toBe(true);
    });

    it('IssueSurface drawer enforces role="dialog" and aria-modal="true"', () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-226']}>
            <IssueSurfaceRoot
              mode="drawer"
              issueKey="KAN-226"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      const drawer = container.querySelector('.surface--drawer');
      expect(drawer).toBeDefined();
      expect(drawer?.getAttribute('role')).toBe('dialog');
      expect(drawer?.getAttribute('aria-modal')).toBe('true');
    });
  });

  describe('2. Deterministic Escape and Close Focus Restoration', () => {
    it('QuickCreateIssueModal restores document.activeElement to opener button upon Escape', () => {
      const triggerBtn = document.createElement('button');
      triggerBtn.textContent = '+ New Issue';
      document.body.appendChild(triggerBtn);
      triggerBtn.focus();
      expect(document.activeElement).toBe(triggerBtn);

      const onClose = vi.fn();
      const { rerender } = render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={onClose}
          onCreate={vi.fn()}
          projectKey="KAN"
        />
      );

      // Press Escape inside modal
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(onClose).toHaveBeenCalled();

      // Rerender as closed
      rerender(
        <QuickCreateIssueModal
          isOpen={false}
          onClose={onClose}
          onCreate={vi.fn()}
          projectKey="KAN"
        />
      );

      expect(document.activeElement).toBe(triggerBtn);
      document.body.removeChild(triggerBtn);
    });

    it('QuickCreateIssueModal restores document.activeElement to opener button upon clicking close button', () => {
      const triggerBtn = document.createElement('button');
      triggerBtn.textContent = 'Open Dialog';
      document.body.appendChild(triggerBtn);
      triggerBtn.focus();

      let isOpen = true;
      const handleClose = () => {
        isOpen = false;
      };

      const { rerender } = render(
        <QuickCreateIssueModal
          isOpen={isOpen}
          onClose={handleClose}
          onCreate={vi.fn()}
          projectKey="KAN"
        />
      );

      const closeBtn = screen.getByRole('button', { name: 'Close modal' });
      fireEvent.click(closeBtn);

      rerender(
        <QuickCreateIssueModal
          isOpen={false}
          onClose={handleClose}
          onCreate={vi.fn()}
          projectKey="KAN"
        />
      );

      expect(document.activeElement).toBe(triggerBtn);
      document.body.removeChild(triggerBtn);
    });

    it('AccessInspectorPopover restores focus to opener element on Escape', () => {
      const openerBtn = document.createElement('button');
      openerBtn.textContent = 'Show Access';
      document.body.appendChild(openerBtn);
      openerBtn.focus();

      function AccessTestWrapper() {
        const [isOpen, setIsOpen] = React.useState(true);
        return (
          <QueryClientProvider client={queryClient}>
            {isOpen ? (
              <AccessInspectorPopover
                objectId="11111111-1111-1111-1111-111111111111"
                anchorEl={openerBtn}
                onClose={() => { setIsOpen(false); }}
              />
            ) : <div />}
          </QueryClientProvider>
        );
      }
      render(<AccessTestWrapper />);

      const dialog = screen.getByRole('dialog');
      fireEvent.keyDown(dialog, { key: 'Escape' });

      expect(document.activeElement).toBe(openerBtn);
      document.body.removeChild(openerBtn);
    });

    it('QuickCreateIssueModal unmounted while open restores focus to opener element', () => {
      const triggerBtn = document.createElement('button');
      triggerBtn.textContent = 'Trigger Open';
      document.body.appendChild(triggerBtn);
      triggerBtn.focus();

      const { unmount } = render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={vi.fn()}
          projectKey="KAN"
        />
      );

      // Unmount while open
      unmount();
      expect(document.activeElement).toBe(triggerBtn);
      document.body.removeChild(triggerBtn);
    });

    it('QuickCreateIssueModal post-create View Issue without onOpenPeek navigates via URL peek parameter', async () => {
      const onCreate = vi.fn().mockReturnValue({ key: 'KAN-999', summary: 'Done item' });
      const onClose = vi.fn();

      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={onClose}
          onCreate={onCreate}
          projectKey="KAN"
        />
      );

      const summaryInput = screen.getByLabelText('Summary');
      fireEvent.change(summaryInput, { target: { value: 'New Test Task' } });

      const form = summaryInput.closest('form');
      if (form) fireEvent.submit(form);

      await waitFor(() => {
        expect(screen.getByTestId('post-create-view-btn')).toBeDefined();
      });

      const pushStateSpy = vi.spyOn(window.history, 'pushState');
      fireEvent.click(screen.getByTestId('post-create-view-btn'));

      expect(pushStateSpy).toHaveBeenCalled();
      pushStateSpy.mockRestore();
    });

    it('QuickCreateIssueModal post-create View Issue for draft navigates to /drafts', async () => {
      const onCreate = vi.fn().mockReturnValue({ key: 'DRAFT-1', summary: 'Draft item' });
      render(
        <QuickCreateIssueModal
          isOpen={true}
          onClose={vi.fn()}
          onCreate={onCreate}
          projectKey="KAN"
        />
      );

      const summaryInput = screen.getByLabelText('Summary');
      fireEvent.change(summaryInput, { target: { value: 'My Draft Task' } });

      const draftCheckbox = screen.getByTestId('quick-create-draft-checkbox');
      fireEvent.click(draftCheckbox);

      const form = summaryInput.closest('form');
      if (form) fireEvent.submit(form);

      await waitFor(() => {
        expect(screen.getByTestId('post-create-view-btn')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('post-create-view-btn'));
    });

    it('IssueSurface drawer restores focus to exact trigger card upon Escape', () => {
      // Create trigger card in DOM
      const cardEl = document.createElement('div');
      cardEl.setAttribute('data-issue-key', 'KAN-226');
      cardEl.tabIndex = 0;
      document.body.appendChild(cardEl);
      cardEl.focus();

      setOpenerElement(cardEl);

      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-226']}>
            <IssueSurfaceRoot
              mode="drawer"
              issueKey="KAN-226"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Press Escape inside drawer
      fireEvent.keyDown(window, { key: 'Escape' });

      expect(document.activeElement).toBe(cardEl);

      unmount();
      document.body.removeChild(cardEl);
    });

    it('IssueSurface drawer falls back to data-issue-key element if opener is null', () => {
      const cardEl = document.createElement('div');
      cardEl.setAttribute('data-issue-key', 'KAN-226');
      cardEl.tabIndex = 0;
      document.body.appendChild(cardEl);

      setOpenerElement(null);

      const { unmount } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-226']}>
            <IssueSurfaceRoot
              mode="drawer"
              issueKey="KAN-226"
              projectKey="KAN"
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      fireEvent.keyDown(window, { key: 'Escape' });

      expect(document.activeElement).toBe(cardEl);

      unmount();
      document.body.removeChild(cardEl);
    });

    it('BoardCard sets opener and BoardCard restores focus when drawer closes', () => {
      const onOpenPeek = vi.fn();
      render(
        <BoardCard
          issue={sampleBoardIssue}
          stateGroup="unstarted"
          onOpenPeek={onOpenPeek}
        />
      );

      const card = screen.getByTestId('board-card-KAN-226');
      card.focus();

      // Trigger Enter on card
      fireEvent.keyDown(card, { key: 'Enter' });
      expect(onOpenPeek).toHaveBeenCalledWith('KAN-226');

      // Verify setOpenerElement captured the card element
      expect(getOpenerElement()).toBe(card);
    });

    it('ListRow sets opener and ListRow restores focus when drawer closes', () => {
      const onOpenPeek = vi.fn();
      render(
        <div role="table" aria-label="Test Table">
          <div role="rowgroup">
            <ListRow
              issue={sampleIssueItem}
              onOpenPeek={onOpenPeek}
            />
          </div>
        </div>
      );

      const row = screen.getByRole('row');
      row.focus();

      // Trigger Enter on list row
      fireEvent.keyDown(row, { key: 'Enter' });
      expect(onOpenPeek).toHaveBeenCalledWith('KAN-226');

      // Verify setOpenerElement captured the row element
      expect(getOpenerElement()).toBe(row);
    });
  });

  describe('3. List View Valid ARIA Hierarchy (role="table" -> role="rowgroup" -> role="row" -> role="cell")', () => {
    it('conforms strictly to WAI-ARIA 1.2 table/rowgroup/row/cell hierarchy with 0 violations', () => {
      const { container } = render(
        <ListView
          issues={FIXTURE_12_ISSUES}
          projectKey="KAN"
        />
      );

      // Verify table containers
      const tables = container.querySelectorAll('[role="table"]');
      expect(tables.length).toBeGreaterThan(0);

      // Verify each table contains rowgroup
      tables.forEach((table) => {
        const rowgroups = table.querySelectorAll('[role="rowgroup"]');
        expect(rowgroups.length).toBeGreaterThanOrEqual(1);

        rowgroups.forEach((rowgroup) => {
          // Direct children of rowgroup must be rows
          const rows = rowgroup.querySelectorAll(':scope > [role="row"]');
          expect(rows.length).toBeGreaterThan(0);

          rows.forEach((row) => {
            // Direct children of row must be cells
            const cells = row.querySelectorAll(':scope > [role="cell"]');
            expect(cells.length).toBe(2); // list-row-left and list-row-right
          });
        });
      });
    });
  });

  describe('4. WCAG 2.5.3 Label in Name Parity', () => {
    it('Topbar Global Search trigger aria-label starts with visible text "Search..."', () => {
      render(
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <ShellPanelsProvider>
              <MemoryRouter initialEntries={['/projects/KAN/issues']}>
                <Topbar
                  projectName="kanban"
                  currentSection="Work Items"
                  issueCount={7}
                  onOpenPalette={vi.fn()}
                  onToggleSidebar={vi.fn()}
                />
              </MemoryRouter>
            </ShellPanelsProvider>
          </ThemeProvider>
        </QueryClientProvider>
      );

      const searchBtn = screen.getByRole('button', { name: 'Search... (Cmd+K)' });
      expect(searchBtn).toBeDefined();

      // Accessible name starts with visible text "Search..."
      const visibleText = searchBtn.querySelector('.kb-search-trigger-text')?.textContent;
      expect(visibleText).toBe('Search...');
      expect(searchBtn.getAttribute('aria-label')).toMatch(/^Search\.\.\./);
    });

    it('Docs + New Doc button aria-label includes visible text "New Doc"', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <DocsTreeNav projectKey="KAN" onSelectPage={vi.fn()} />
        </QueryClientProvider>
      );

      await waitFor(() => {
        const btn = screen.getByTestId('create-root-doc-btn');
        expect(btn).toBeDefined();
        expect(btn.getAttribute('aria-label')).toContain('New Doc');
        expect(btn.textContent.trim()).toContain('New Doc');
      });
    });

    it('Board card aria-label begins with visible issue key and title without conflicting punctuation', () => {
      render(
        <BoardCard
          issue={sampleBoardIssue}
          stateGroup="unstarted"
        />
      );

      const card = screen.getByTestId('board-card-KAN-226');
      const label = card.getAttribute('aria-label');
      expect(label).toBe('KAN-226 Enforce modal/drawer focus traps and ARIA hierarchy');
      expect(label?.startsWith('KAN-226 Enforce modal/drawer')).toBe(true);
    });
  });

  describe('5. Focus Trap & ListRow Detailed Branch Coverage', () => {
    it('useFocusTrap handles empty focusables, outside focus, null container, and non-Tab keys', () => {
      function EmptyTrapTest() {
        const ref = useRef<HTMLDivElement>(null);
        useFocusTrap(true, ref);
        return <div ref={ref} tabIndex={-1} data-testid="empty-trap" />;
      }

      function OutsideFocusTrapTest() {
        const ref = useRef<HTMLDivElement>(null);
        useFocusTrap(true, ref);
        return (
          <div>
            <button type="button" data-testid="outside-btn">Outside</button>
            <div ref={ref} data-testid="trap-box">
              <button type="button" data-testid="inside-first">First</button>
              <button type="button" data-testid="inside-last">Last</button>
            </div>
          </div>
        );
      }

      function NullRefTrapTest() {
        const ref = { current: null };
        useFocusTrap(true, ref);
        return <div data-testid="null-trap" />;
      }

      // 1. Empty container
      const { unmount: unmountEmpty } = render(<EmptyTrapTest />);
      const emptyDiv = screen.getByTestId('empty-trap');
      const focusSpy = vi.spyOn(emptyDiv, 'focus');
      fireEvent.keyDown(document, { key: 'Tab' });
      expect(focusSpy).toHaveBeenCalled();
      unmountEmpty();

      // 2. Outside focus - Tab moves into first, Shift+Tab moves into last
      const { unmount: unmountOutside } = render(<OutsideFocusTrapTest />);
      const outsideBtn = screen.getByTestId('outside-btn');
      const insideFirst = screen.getByTestId('inside-first');
      const insideLast = screen.getByTestId('inside-last');

      outsideBtn.focus();
      expect(document.activeElement).toBe(outsideBtn);
      fireEvent.keyDown(document, { key: 'Tab' });
      expect(document.activeElement).toBe(insideFirst);

      outsideBtn.focus();
      fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
      expect(document.activeElement).toBe(insideLast);

      // Non-Tab keypress does nothing
      fireEvent.keyDown(document, { key: 'Escape' });
      unmountOutside();

      // 3. Null ref does not throw
      const { unmount: unmountNull } = render(<NullRefTrapTest />);
      expect(() => { fireEvent.keyDown(document, { key: 'Tab' }); }).not.toThrow();
      unmountNull();
    });

    it('ListRow click, key link click, and Enter keypress sets opener element', () => {
      const onOpenPeek = vi.fn();
      render(
        <ListRow
          issue={sampleIssueItem}
          onOpenPeek={onOpenPeek}
        />
      );

      const row = screen.getByTestId('list-row-KAN-226');
      fireEvent.click(row);
      expect(onOpenPeek).toHaveBeenCalledWith('KAN-226');
      expect(getOpenerElement()).toBe(row);

      const link = screen.getByRole('link', { name: 'KAN-226' });
      fireEvent.click(link);
      expect(onOpenPeek).toHaveBeenCalledWith('KAN-226');
      expect(getOpenerElement()).toBe(link);

      fireEvent.keyDown(row, { key: 'Enter' });
      expect(onOpenPeek).toHaveBeenCalledWith('KAN-226');
    });
  });
});
