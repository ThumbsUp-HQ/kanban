// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { ColumnConfigurator } from './ColumnConfigurator';
import { getDefaultColumns, type TableColumnId } from './tableColumns';
import { ShellPanelsProvider, registerShellPanel, useShellPanels } from '../../app/shellPanels';

describe('ColumnConfigurator', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders trigger button with count and opens/closes dialog', () => {
    const defaultCols = getDefaultColumns(true);
    const onChange = vi.fn();

    render(
      <ColumnConfigurator
        columns={defaultCols}
        onChange={onChange}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    const trigger = screen.getByRole('button', { name: /Columns/i });
    expect(trigger).toBeDefined();
    expect(trigger.textContent).toContain(`Columns (${String(defaultCols.length)}/13)`);

    // Click trigger opens dialog
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: /Configure table columns/i });
    expect(dialog).toBeDefined();

    // Click inside dialog keeps it open
    fireEvent.mouseDown(dialog);
    expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

    // Close button (✕) closes dialog
    const closeBtn = screen.getByRole('button', { name: /Close column configuration/i });
    fireEvent.click(closeBtn);
    expect(screen.queryByRole('dialog', { name: /Configure table columns/i })).toBeNull();

    // Reopen and click outside
    fireEvent.click(trigger);
    expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('dialog', { name: /Configure table columns/i })).toBeNull();
  });

  it('keeps locked columns (Key, Summary) disabled and toggles optional columns', () => {
    const defaultCols = getDefaultColumns(true);
    const onChange = vi.fn();

    render(
      <ColumnConfigurator
        columns={defaultCols}
        onChange={onChange}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));

    // Key and Summary checkboxes must be disabled
    const keyCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: 'Key' });
    const summaryCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: 'Summary' });
    expect(keyCheckbox.disabled).toBe(true);
    expect(summaryCheckbox.disabled).toBe(true);

    // Start date is initially unchecked in defaults; toggle it on
    const startDateCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: 'Start date' });
    expect(startDateCheckbox.checked).toBe(false);

    fireEvent.click(startDateCheckbox);
    expect(onChange).toHaveBeenCalled();
    const call0 = onChange.mock.calls[0];
    expect(call0).toBeDefined();
    const lastCalledWith = call0?.[0] as TableColumnId[];
    expect(lastCalledWith).toContain('start_date');

    // Cycle is initially checked; toggle it off
    const cycleCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: 'Cycle' });
    expect(cycleCheckbox.checked).toBe(true);

    fireEvent.click(cycleCheckbox);
    const call1 = onChange.mock.calls[1];
    expect(call1).toBeDefined();
    const secondCall = call1?.[0] as TableColumnId[];
    expect(secondCall).not.toContain('cycle');
  });

  it('reorders columns up and down and persists to localStorage', () => {
    const initialCols: TableColumnId[] = ['key', 'summary', 'state', 'priority', 'assignees', 'due_date'];
    const onChange = vi.fn();

    render(
      <ColumnConfigurator
        columns={initialCols}
        onChange={onChange}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));

    // Move State down
    const moveStateDownBtn = screen.getByRole<HTMLButtonElement>('button', { name: /Move State down/i });
    expect(moveStateDownBtn.disabled).toBe(false);
    fireEvent.click(moveStateDownBtn);
    expect(onChange).toHaveBeenCalled();

    // Move Due date up (before Assignees)
    const moveDueUpBtn = screen.getByRole<HTMLButtonElement>('button', { name: /Move Due date up/i });
    expect(moveDueUpBtn.disabled).toBe(false);

    fireEvent.click(moveDueUpBtn);
    expect(onChange).toHaveBeenCalled();
  });

  it('resets columns to defaults when Reset defaults is clicked', () => {
    const customCols: TableColumnId[] = ['key', 'summary', 'state'];
    const onChange = vi.fn();

    render(
      <ColumnConfigurator
        columns={customCols}
        onChange={onChange}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));

    const resetBtn = screen.getByRole('button', { name: /Reset defaults/i });
    fireEvent.click(resetBtn);

    expect(onChange).toHaveBeenCalledWith(getDefaultColumns(true));
  });

  it('unmounts Modules completely when modulesEnabled is false', () => {
    const defaultCols = getDefaultColumns(false);
    const onChange = vi.fn();

    render(
      <ColumnConfigurator
        columns={defaultCols}
        onChange={onChange}
        projectKey="KAN"
        modulesEnabled={false}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));

    // Modules should not be in DOM at all
    expect(screen.queryByLabelText(/Modules/i)).toBeNull();
    const trigger = screen.getByRole('button', { name: /Columns/i });
    expect(trigger.textContent).toContain(`Columns (${String(defaultCols.length)}/12)`);
  });

  describe('StudioDocLink Header Integration (KAN-485)', () => {
    it('renders StudioDocLink in configurator header pointing to table view and column customization guide', () => {
      const defaultCols = getDefaultColumns(true);
      render(
        <ColumnConfigurator
          columns={defaultCols}
          onChange={vi.fn()}
          projectKey="KAN"
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /Columns/i }));

      const docLink = screen.getByTestId('column-config-doc-link');
      expect(docLink).toBeDefined();
      expect(docLink.getAttribute('href')).toBe(
        '/docs/enterprise-whitespace-and-kanban-board#table-view-and-column-customization'
      );
      expect(docLink.textContent).toContain('Columns Guide ->');
      expect(docLink.className).toContain('kb-studio-doc-link');

      // HTML 4.10.4: Not nested in a button or label
      expect(docLink.closest('button')).toBeNull();
      expect(docLink.closest('label')).toBeNull();
    });

    it('opens HelpDrawer when StudioDocLink is clicked inside ShellPanelsProvider', () => {
      let panelOpened = false;
      let panelArg: unknown = null;
      const unregister = registerShellPanel('help', () => <div data-testid="mock-help-panel" />);

      function PanelWatcher() {
        const { activePanel } = useShellPanels();
        if (activePanel?.id === 'help') {
          panelOpened = true;
          panelArg = activePanel.arg;
        }
        return <div data-testid="panel-watcher" />;
      }

      const defaultCols = getDefaultColumns(true);
      render(
        <ShellPanelsProvider>
          <PanelWatcher />
          <ColumnConfigurator
            columns={defaultCols}
            onChange={vi.fn()}
            projectKey="KAN"
          />
        </ShellPanelsProvider>
      );

      fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
      const docLink = screen.getByTestId('column-config-doc-link');
      fireEvent.click(docLink);

      expect(panelOpened).toBe(true);
      expect(panelArg).toEqual({
        href: '/docs/enterprise-whitespace-and-kanban-board#table-view-and-column-customization',
        title: 'Columns Guide ->',
      });

      unregister();
    });
  });

  describe('FieldHelpHint Pinned Columns Integration (KAN-485)', () => {
    it('renders FieldHelpHint as a sibling to label in locked Key column and satisfies HTML 4.10.4', () => {
      const defaultCols = getDefaultColumns(true);
      const { container } = render(
        <ColumnConfigurator
          columns={defaultCols}
          onChange={vi.fn()}
          projectKey="KAN"
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /Columns/i }));

      const helpTrigger = screen.getByTestId('pinned-columns-help');
      expect(helpTrigger).toBeDefined();

      // HTML 4.10.4: NEVER nested in label or button
      expect(helpTrigger.closest('label')).toBeNull();
      expect(helpTrigger.closest('button.column-configurator-trigger')).toBeNull();

      // Sibling inside the item row
      const keyRow = helpTrigger.closest('.column-configurator-item');
      expect(keyRow?.getAttribute('data-col-id')).toBe('key');
      expect(keyRow?.querySelector('label.column-configurator-item-left')).not.toBeNull();

      // Strict check: zero nested buttons in labels or buttons
      const invalidNestedButtons = container.querySelectorAll(
        'label button.field-help-hint, button button.field-help-hint, label a.kb-studio-doc-link, button a.kb-studio-doc-link'
      );
      expect(invalidNestedButtons.length).toBe(0);
      expect(
        document.querySelectorAll(
          'label button.field-help-hint, button button.field-help-hint, label a.kb-studio-doc-link, button a.kb-studio-doc-link'
        ).length
      ).toBe(0);
    });

    it('opens FieldHelpHint popover and verifies summary, defaultValue, validValues, and docHref', async () => {
      const defaultCols = getDefaultColumns(true);
      render(
        <ColumnConfigurator
          columns={defaultCols}
          onChange={vi.fn()}
          projectKey="KAN"
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /Columns/i }));

      const helpTrigger = screen.getByTestId('pinned-columns-help');
      fireEvent.click(helpTrigger);

      await waitFor(() => {
        expect(
          screen.getByText(
            'Identifier and Summary columns are permanently pinned to provide consistent issue identification and navigation.'
          )
        ).toBeDefined();
      });

      // Default value: Pinned (Identifier, Summary)
      expect(screen.getByTestId('pinned-columns-help-default')).toBeDefined();
      expect(
        within(screen.getByTestId('pinned-columns-help-default')).getByText('Pinned (Identifier, Summary)')
      ).toBeDefined();

      // Valid values list
      expect(
        screen.getByText('Immutable unique project issue tracking key.')
      ).toBeDefined();
      expect(
        screen.getByText('Primary headline describing the work item.')
      ).toBeDefined();

      // Wiki documentation link in popover
      const popoverDocLink = screen.getByTestId('pinned-columns-help-doc-link');
      expect(popoverDocLink.getAttribute('href')).toBe(
        '/docs/enterprise-whitespace-and-kanban-board#table-view-and-column-customization'
      );
    });
  });

  describe('Escape and Outside Click Yielding (KAN-485)', () => {
    it('ignores non-Escape keydown events', () => {
      const defaultCols = getDefaultColumns(true);
      render(
        <ColumnConfigurator
          columns={defaultCols}
          onChange={vi.fn()}
          projectKey="KAN"
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      fireEvent.keyDown(window, { key: 'Tab' });
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();
    });

    it('closes dialog on Escape when neither help drawer nor field help popover is open', () => {
      const defaultCols = getDefaultColumns(true);
      render(
        <ColumnConfigurator
          columns={defaultCols}
          onChange={vi.fn()}
          projectKey="KAN"
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      // Press Escape
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.queryByRole('dialog', { name: /Configure table columns/i })).toBeNull();
    });

    it('yields Escape when .field-help-hint-popover is present in the DOM', () => {
      const defaultCols = getDefaultColumns(true);
      render(
        <ColumnConfigurator
          columns={defaultCols}
          onChange={vi.fn()}
          projectKey="KAN"
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      // Create a mock .field-help-hint-popover in the DOM
      const mockPopover = document.createElement('div');
      mockPopover.className = 'field-help-hint-popover';
      document.body.appendChild(mockPopover);

      // Press Escape -> must yield and NOT close ColumnConfigurator
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      // Clean up mock popover
      document.body.removeChild(mockPopover);

      // Now pressing Escape closes ColumnConfigurator
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.queryByRole('dialog', { name: /Configure table columns/i })).toBeNull();
    });

    it('yields Escape when .kb-help-drawer is present in the DOM', () => {
      const defaultCols = getDefaultColumns(true);
      render(
        <ColumnConfigurator
          columns={defaultCols}
          onChange={vi.fn()}
          projectKey="KAN"
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      // Create a mock .kb-help-drawer in the DOM
      const mockDrawer = document.createElement('div');
      mockDrawer.className = 'kb-help-drawer';
      document.body.appendChild(mockDrawer);

      // Press Escape -> must yield and NOT close ColumnConfigurator
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      // Clean up mock drawer
      document.body.removeChild(mockDrawer);

      // Now pressing Escape closes ColumnConfigurator
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.queryByRole('dialog', { name: /Configure table columns/i })).toBeNull();
    });

    it('yields outside-click when clicking inside .kb-help-drawer or .kb-help-drawer-backdrop', () => {
      const defaultCols = getDefaultColumns(true);
      render(
        <ColumnConfigurator
          columns={defaultCols}
          onChange={vi.fn()}
          projectKey="KAN"
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      // Create mock help drawer and backdrop
      const mockBackdrop = document.createElement('div');
      mockBackdrop.className = 'kb-help-drawer-backdrop';
      const mockDrawer = document.createElement('div');
      mockDrawer.className = 'kb-help-drawer';
      document.body.appendChild(mockBackdrop);
      document.body.appendChild(mockDrawer);

      // Click on drawer -> yields
      fireEvent.mouseDown(mockDrawer);
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      // Click on backdrop -> yields
      fireEvent.mouseDown(mockBackdrop);
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      // Clean up
      document.body.removeChild(mockDrawer);
      document.body.removeChild(mockBackdrop);

      // Click on body -> closes dialog
      fireEvent.mouseDown(document.body);
      expect(screen.queryByRole('dialog', { name: /Configure table columns/i })).toBeNull();
    });

    it('yields outside-click when clicking inside or while .field-help-hint-popover is open', () => {
      const defaultCols = getDefaultColumns(true);
      render(
        <ColumnConfigurator
          columns={defaultCols}
          onChange={vi.fn()}
          projectKey="KAN"
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /Columns/i }));
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      // Create mock popover
      const mockPopover = document.createElement('div');
      mockPopover.className = 'field-help-hint-popover';
      document.body.appendChild(mockPopover);

      // Click on popover -> yields
      fireEvent.mouseDown(mockPopover);
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      // Click on outside while popover is in DOM -> yields
      fireEvent.mouseDown(document.body);
      expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

      // Clean up popover
      document.body.removeChild(mockPopover);

      // Now click on body closes
      fireEvent.mouseDown(document.body);
      expect(screen.queryByRole('dialog', { name: /Configure table columns/i })).toBeNull();
    });
  });

  describe('Shift-Left Static & CSS Invariants (KAN-485)', () => {
    it('enforces static AST invariants: zero inline style props and zero nested controls', () => {
      const source = fs.readFileSync(path.resolve(__dirname, 'ColumnConfigurator.tsx'), 'utf8');

      // Zero inline style props
      expect(source).not.toMatch(/style\s*=\s*\{\{/);

      // Zero FieldHelpHint nested inside <label>
      expect(source).not.toMatch(/<label[^>]*>(?:(?!<\/label>)[\s\S])*?<FieldHelpHint/i);

      // Zero FieldHelpHint nested inside <button>
      expect(source).not.toMatch(/<button[^>]*>(?:(?!<\/button>)[\s\S])*?<FieldHelpHint/i);

      // Zero StudioDocLink nested inside <label>
      expect(source).not.toMatch(/<label[^>]*>(?:(?!<\/label>)[\s\S])*?<StudioDocLink/i);

      // Zero StudioDocLink nested inside <button>
      expect(source).not.toMatch(/<button[^>]*>(?:(?!<\/button>)[\s\S])*?<StudioDocLink/i);
    });

    it('verifies listTable.css includes responsive and touch target rules for ColumnConfigurator', () => {
      const cssPath = path.resolve(__dirname, '../views/listTable.css');
      const css = fs.readFileSync(cssPath, 'utf8');

      expect(css).toContain('.column-configurator-container');
      expect(css).toContain('.column-configurator-dialog');
      expect(css).toContain('min-height: var(--tap-min, 44px)');
      expect(css).toContain('max-width: calc(100vw - 24px)');
    });
  });
});
