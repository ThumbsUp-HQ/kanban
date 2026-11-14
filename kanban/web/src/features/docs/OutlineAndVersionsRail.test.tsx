import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  OutlineAndVersionsRail,
  extractHeadings,
  stripInlineMarkdown,
} from './OutlineAndVersionsRail';
import * as docsApi from './docsApi';

const mockPageData: docsApi.PageResponse = {
  id: 'page-auth-studio',
  canonical_key: 'docs/architecture/auth-studio',
  doc_id: 'doc-arch',
  parent_page_id: 'page-arch',
  workspace_id: 'ws-1',
  title: 'Auth Studio',
  body_markdown:
    '# Overview\n\nAuth Studio specification.\n\n## PKCE S256\n\nEnforce S256.\n\n```bash\n# comment inside code fence\ncurl -X POST /oauth/token\n```\n\n### State TTL\n\nExpires in 300s.\n',
  body_sha256: 'a1b2c3d4e5f6',
  hierarchy_path: 'docs.architecture.auth_studio',
  version_seq: 7,
  sort_rank: '0|hzzzzz:',
  breadcrumbs: [],
  outline: [],
  access_manifest: {},
  capabilities: ['VIEW'],
  object_links: [
    {
      target_key: 'KAN-142',
      target_title: 'Implement PKCE S256',
      link_type: 'RELATES_TO',
      link_id: 'link-1',
    },
    {
      target_key: 'STICKY-9',
      target_title: 'Original Sticky Note',
      link_type: 'PROMOTED_TO_DOC',
      link_id: 'link-2',
    },
  ],
};

const mockVersions: docsApi.PageVersionResponse[] = [
  {
    page_id: 'page-auth-studio',
    version_seq: 7,
    title: 'Auth Studio',
    body_markdown: '# Overview\nv7 content',
    body_sha256: 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678',
    created_by_id: 'adam',
    created_at: '2026-11-13T18:00:00Z',
  },
  {
    page_id: 'page-auth-studio',
    version_seq: 6,
    title: 'Auth Studio',
    body_markdown: '# Overview\nv6 content',
    body_sha256: 'b2c3d4e5f6a10718293a4b5c6d7e8f9012345678',
    created_by_id: 'adam',
    created_at: '2026-11-13T17:00:00Z',
  },
  {
    page_id: 'page-auth-studio',
    version_seq: 5,
    title: 'Auth Studio',
    body_markdown: '# Overview\nv5 content',
    body_sha256: 'c3d4e5f6a1b20718293a4b5c6d7e8f9012345678',
    created_by_id: 'adam',
    created_at: '2026-11-13T16:00:00Z',
  },
];

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
}

describe('OutlineAndVersionsRail', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.restoreAllMocks();
    vi.spyOn(docsApi, 'fetchPageVersions').mockResolvedValue(mockVersions);

    // Mock IntersectionObserver
    class MockIntersectionObserver {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
    }
    window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver;
  });

  it('extracts headings outside code blocks and ignores fenced comments', () => {
    const markdown = `# Main Title
Some text.

\`\`\`python
# This is a python comment
def foo(): pass
\`\`\`

## Section Two
~~~
# This is inside a tilde fence
~~~

### Subsection Three
`;
    const headings = extractHeadings(markdown);
    expect(headings).toHaveLength(3);
    expect(headings[0]).toEqual({ level: 1, text: 'Main Title', anchor: 'main-title' });
    expect(headings[1]).toEqual({ level: 2, text: 'Section Two', anchor: 'section-two' });
    expect(headings[2]).toEqual({ level: 3, text: 'Subsection Three', anchor: 'subsection-three' });
  });

  it('strips inline markdown from heading texts properly', () => {
    expect(stripInlineMarkdown('**Bold** [link](url) and `code`')).toBe('Bold link and code');
  });

  it('renders outline headings and linked work items', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <OutlineAndVersionsRail
          pageId="page-auth-studio"
          projectKey="KAN"
          page={mockPageData}
        />
      </QueryClientProvider>,
    );

    // Headings
    expect(screen.getByText('Overview')).toBeDefined();
    expect(screen.getByText('PKCE S256')).toBeDefined();
    expect(screen.getByText('State TTL')).toBeDefined();
    // The code fence comment must NOT be rendered as a heading!
    expect(screen.queryByText('comment inside code fence')).toBeNull();

    // Linked items
    expect(screen.getByText('KAN-142')).toBeDefined();
    expect(screen.getByText('Implement PKCE S256')).toBeDefined();
    expect(screen.getByText('📄 Promoted')).toBeDefined();
  });

  it('switches to history tab, previews selected version, and restores it', async () => {
    const restoreSpy = vi.spyOn(docsApi, 'restorePageVersion').mockResolvedValue({
      ...mockPageData,
      version_seq: 8,
      body_markdown: '# Overview\nv5 content',
    });

    render(
      <QueryClientProvider client={queryClient}>
        <OutlineAndVersionsRail
          pageId="page-auth-studio"
          projectKey="KAN"
          page={mockPageData}
        />
      </QueryClientProvider>,
    );

    // Switch to History tab
    fireEvent.click(screen.getByTestId('rail-tab-history'));

    await waitFor(() => {
      expect(screen.getByTestId('version-item-v7')).toBeDefined();
    });

    expect(screen.getByTestId('version-item-v6')).toBeDefined();
    expect(screen.getByTestId('version-item-v5')).toBeDefined();

    // Select v5
    fireEvent.click(screen.getByTestId('version-item-v5'));

    await waitFor(() => {
      expect(screen.getByTestId('version-preview-pane')).toBeDefined();
    });

    expect(screen.getByTestId('version-preview-body').textContent).toContain('v5 content');

    // Click Restore v5
    fireEvent.click(screen.getByTestId('restore-v5-btn'));

    await waitFor(() => {
      expect(restoreSpy).toHaveBeenCalledWith(
        'page-auth-studio',
        5,
        '"a1b2c3d4e5f6"',
      );
    });
  });

  it('scrolls into view when an outline heading is clicked and handles observer callback', () => {
    let observerCallback: ((entries: IntersectionObserverEntry[]) => void) | undefined;
    class MockIntersectionObserver {
      constructor(cb: (entries: IntersectionObserverEntry[]) => void) {
        observerCallback = cb;
      }
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
    }
    window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver;

    const scrollIntoViewSpy = vi.fn();
    const headingEl = document.createElement('div');
    headingEl.id = 'pkce-s256';
    headingEl.scrollIntoView = scrollIntoViewSpy;
    document.body.appendChild(headingEl);

    render(
      <QueryClientProvider client={queryClient}>
        <OutlineAndVersionsRail
          pageId="page-auth-studio"
          projectKey="KAN"
          page={mockPageData}
        />
      </QueryClientProvider>,
    );

    const pkceLink = screen.getByTestId('outline-heading-pkce-s256');
    fireEvent.click(pkceLink);
    expect(scrollIntoViewSpy).toHaveBeenCalled();

    // Trigger observer callback
    if (observerCallback) {
      observerCallback([
        {
          isIntersecting: true,
          target: headingEl,
        } as unknown as IntersectionObserverEntry,
      ]);
    }

    document.body.removeChild(headingEl);
  });

  it('handles restore error gracefully and calls onAnnounce', async () => {
    vi.spyOn(docsApi, 'restorePageVersion').mockRejectedValue(new Error('Precondition error'));
    const onAnnounce = vi.fn();

    render(
      <QueryClientProvider client={queryClient}>
        <OutlineAndVersionsRail
          pageId="page-auth-studio"
          projectKey="KAN"
          page={mockPageData}
          onAnnounce={onAnnounce}
        />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByTestId('rail-tab-history'));
    await waitFor(() => {
      expect(screen.getByTestId('version-item-v5')).toBeDefined();
    });
    fireEvent.click(screen.getByTestId('version-item-v5'));
    fireEvent.click(screen.getByTestId('restore-v5-btn'));

    await waitFor(() => {
      expect(onAnnounce).toHaveBeenCalledWith('Restore error: Precondition error');
    });
  });
});
