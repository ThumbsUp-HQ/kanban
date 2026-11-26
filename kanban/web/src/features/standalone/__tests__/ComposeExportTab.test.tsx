// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ComposeExportTab, type ComposeExportData } from '../ComposeExportTab';
import * as clientModule from '../../../api/client';
import { ApiProblem } from '../../../api/problem';
import * as uuidUtils from '../../../utils/uuid';

describe('ComposeExportTab', () => {
  const mockData: ComposeExportData = {
    filename: 'docker-compose.prod.yml',
    compose_yaml: 'version: "3.9"\nservices:\n  kanban:\n    image: thumbs-up-kanban:latest',
    env_template: 'POSTGRES_PASSWORD=secret\nSECRET_KEY=kbbak-key',
    migration_steps_markdown: '# Promotion Steps',
    single_container_compose_yaml: 'services:\n  standalone:\n    image: thumbs-up-kanban:latest',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders with initialData directly without fetching', () => {
    const apiSpy = vi.spyOn(clientModule, 'apiFetch');
    render(<ComposeExportTab initialData={mockData} />);

    expect(apiSpy).not.toHaveBeenCalled();
    expect(screen.getByText('Multi-Container Stack (Production)')).toBeDefined();
    expect(screen.getByText('Download docker-compose.yml')).toBeDefined();
    expect(screen.getByText('Copy .env.example')).toBeDefined();
  });

  it('fetches compose export data on mount when initialData is not provided', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce(mockData);
    render(<ComposeExportTab />);

    await waitFor(() => {
      expect(screen.getByText('Download docker-compose.yml')).toBeDefined();
    });
  });

  it('handles fetch error when apiFetch throws ApiProblem', async () => {
    const problem = new ApiProblem(401, {
      detail: 'Session expired',
    });
    vi.spyOn(clientModule, 'apiFetch').mockRejectedValueOnce(problem);

    render(<ComposeExportTab />);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Failed to load compose export: 401');
    });
  });

  it('handles fetch error when apiFetch throws generic Error or non-Error', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockRejectedValueOnce(new Error('Network offline'));
    const { unmount } = render(<ComposeExportTab />);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Network offline');
    });
    unmount();

    vi.spyOn(clientModule, 'apiFetch').mockRejectedValueOnce('Some string error');
    render(<ComposeExportTab />);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Failed to load export data');
    });
  });

  it('toggles between multi-container and single-container modes', () => {
    render(<ComposeExportTab initialData={mockData} />);

    // Switch to single-container mode
    fireEvent.click(screen.getByText('Single-Container (Standalone)'));
    expect(screen.getByText('Download docker-compose.standalone.yml')).toBeDefined();
    expect(screen.queryByText('Copy .env.example')).toBeNull();
    expect(screen.queryByText('5-Network Architecture Summary')).toBeNull();
    expect(screen.queryByTestId('compose-network-help')).toBeNull();
    expect(screen.getByText(/Runs 👍kanban and embedded PostgreSQL/i)).toBeDefined();

    // Switch back to multi-container mode
    fireEvent.click(screen.getByText('Multi-Container Stack (Production)'));
    expect(screen.getByText('Download docker-compose.yml')).toBeDefined();
    expect(screen.getByText('Copy .env.example')).toBeDefined();
    expect(screen.getByText('5-Network Architecture Summary')).toBeDefined();
    expect(screen.getByTestId('compose-network-help')).toBeDefined();
  });

  it('renders 5-Network Architecture Summary with adjacent FieldHelpHint and docHref', () => {
    render(<ComposeExportTab initialData={mockData} />);

    expect(screen.getByText('5-Network Architecture Summary')).toBeDefined();
    const helpBtn = screen.getByTestId('compose-network-help');
    expect(helpBtn).toBeDefined();
    expect(helpBtn.getAttribute('aria-label')).toContain('5-Network Architecture Summary');

    // Focus to open popover
    fireEvent.focus(helpBtn);
    const popover = screen.getByTestId('compose-network-help-popover');
    expect(popover).toBeDefined();
    expect(popover.textContent).toContain('edge_net');
    expect(popover.textContent).toContain('app_net');
    expect(popover.textContent).toContain('data_net');
    expect(popover.textContent).toContain('sandbox_net');
    expect(popover.textContent).toContain('egress_llm_net');

    const docLink = screen.getByTestId('compose-network-help-doc-link');
    expect(docLink.getAttribute('href')).toBe('/docs/system-topology-and-multi-container-architecture');
  });

  it('handles downloading compose yaml in multi and single mode', async () => {
    const createObjectURLMock = vi.fn().mockReturnValue('blob:http://localhost/mock-blob');
    const revokeObjectURLMock = vi.fn();
    window.URL.createObjectURL = createObjectURLMock;
    window.URL.revokeObjectURL = revokeObjectURLMock;

    render(<ComposeExportTab initialData={mockData} />);

    // Multi mode download
    fireEvent.click(screen.getByText('Download docker-compose.yml'));
    await waitFor(() => {
      expect(createObjectURLMock).toHaveBeenCalled();
      expect(revokeObjectURLMock).toHaveBeenCalledWith('blob:http://localhost/mock-blob');
    });

    // Single mode download
    fireEvent.click(screen.getByText('Single-Container (Standalone)'));
    fireEvent.click(screen.getByText('Download docker-compose.standalone.yml'));
    await waitFor(() => {
      expect(createObjectURLMock).toHaveBeenCalledTimes(2);
    });
  });

  it('handles download failure gracefully', async () => {
    window.URL.createObjectURL = vi.fn(() => {
      throw new Error('Blob creation failed');
    });

    render(<ComposeExportTab initialData={mockData} />);
    fireEvent.click(screen.getByText('Download docker-compose.yml'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Blob creation failed');
    });
  });

  it('handles copying env template and copy failure', async () => {
    const copySpy = vi.spyOn(uuidUtils, 'safeCopyToClipboard').mockResolvedValueOnce(true);

    const { unmount } = render(<ComposeExportTab initialData={mockData} />);
    fireEvent.click(screen.getByText('Copy .env.example'));

    await waitFor(() => {
      expect(copySpy).toHaveBeenCalledWith(mockData.env_template);
      expect(screen.getByText('Copied!')).toBeDefined();
    });
    unmount();

    // Test copy failure
    copySpy.mockResolvedValueOnce(false);
    render(<ComposeExportTab initialData={mockData} />);
    fireEvent.click(screen.getByText('Copy .env.example'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Failed to copy');
    });
  });
});
