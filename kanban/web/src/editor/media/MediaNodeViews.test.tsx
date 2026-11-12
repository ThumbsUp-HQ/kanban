/**
 * Unit & Integration Tests for MediaNodeViews, Extensions, and MediaLightbox (KB-P3-48).
 */

import React, { act } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { EditorView, Decoration, DecorationSource } from 'prosemirror-view';
import { editorSchema } from '../schema';
import {
  MediaNodeView,
  SvgCodeBlockNodeView,
  createMediaNodeViews,
  registerMediaExtension,
} from './MediaNodeViews';
import { getRegisteredExtensions } from '../editorSurfaceFactory';
import { MediaLightbox } from './MediaLightbox';

describe('MediaNodeViews and NodeView Extensions', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('creates and renders MediaNodeView for image and image_block nodes', async () => {
    const resolveAttachmentSpy = vi.fn((id: string) => `/api/v1/attachments/${id}`);
    const nodeViews = createMediaNodeViews({
      resolveAttachmentUrl: resolveAttachmentSpy,
      airGapMode: false,
    });

    expect(nodeViews.image).toBeDefined();
    expect(nodeViews.image_block).toBeDefined();

    const viewMock = {} as unknown as EditorView;

    // Test standard image
    const imgNode = editorSchema.nodes.image.create({
      src: 'attachment://att-9988',
      alt: 'Architecture Diagram',
    });

    const imageFn = nodeViews.image;
    if (!imageFn) {
      throw new Error('Expected image nodeView to be defined');
    }

    let imgNodeView!: MediaNodeView;
    act(() => {
      imgNodeView = imageFn(imgNode, viewMock, () => 0) as MediaNodeView;
    });

    expect(imgNodeView.dom).toBeDefined();
    expect(imgNodeView.dom.className).toContain('kb-media-nodeview');
    document.body.appendChild(imgNodeView.dom);

    try {
      await waitFor(() => {
        expect(resolveAttachmentSpy).toHaveBeenCalledWith('att-9988');
      });

      // Test update
      act(() => {
        const updatedImgNode = editorSchema.nodes.image.create({
          src: 'https://example.com/photo.png',
          alt: 'Updated Photo',
        });
        expect(imgNodeView.update(updatedImgNode)).toBe(true);
      });
    } finally {
      document.body.removeChild(imgNodeView.dom);
    }

    // Test update with mismatched node type
    const paragraphNode = editorSchema.nodes.paragraph.create();
    expect(imgNodeView.update(paragraphNode)).toBe(false);

    // Test destroy
    imgNodeView.destroy();

    // Test image_block
    const imgBlockNode = editorSchema.nodes.image_block.create({
      src: 'blob:http://localhost/test-block',
      alt: 'Block Image',
    });
    const imageBlockFn = nodeViews.image_block;
    if (!imageBlockFn) {
      throw new Error('Expected image_block nodeView to be defined');
    }

    let imgBlockNodeView!: MediaNodeView;
    act(() => {
      imgBlockNodeView = imageBlockFn(imgBlockNode, viewMock, () => 0) as MediaNodeView;
    });
    expect(imgBlockNodeView.dom).toBeDefined();
    imgBlockNodeView.destroy();
  });

  it('renders SvgCodeBlockNodeView with safe SVG and handles update and destroy', () => {
    const validSvgText = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>';
    const svgCodeNode = editorSchema.nodes.code_block.create(
      { lang: 'svg' },
      editorSchema.text(validSvgText),
    );

    let svgNodeView!: SvgCodeBlockNodeView;
    act(() => {
      svgNodeView = new SvgCodeBlockNodeView(svgCodeNode);
    });

    expect(svgNodeView.dom).toBeDefined();
    expect(svgNodeView.dom.className).toContain('kb-media-nodeview--svg-block');

    // Update with another SVG code block
    act(() => {
      const updatedSvgNode = editorSchema.nodes.code_block.create(
        { lang: 'svg' },
        editorSchema.text('<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>'),
      );
      expect(svgNodeView.update(updatedSvgNode)).toBe(true);
    });

    // Update with non-svg code block returns false
    const tsCodeNode = editorSchema.nodes.code_block.create(
      { lang: 'typescript' },
      editorSchema.text('console.log("hello");'),
    );
    expect(svgNodeView.update(tsCodeNode)).toBe(false);

    // Destroy twice to cover if (!this.root) branch
    svgNodeView.destroy();
    svgNodeView.destroy();
  });

  it('renders error placeholder in SvgCodeBlockNodeView when SVG sanitization fails', () => {
    // Malformed SVG that fails XML parsing
    const malformedSvgNode = editorSchema.nodes.code_block.create(
      { lang: 'svg' },
      editorSchema.text('<svg><unclosed></svg>'),
    );

    let errorNodeView!: SvgCodeBlockNodeView;
    act(() => {
      errorNodeView = new SvgCodeBlockNodeView(malformedSvgNode);
    });

    expect(errorNodeView.dom).toBeDefined();
    expect(errorNodeView.dom.textContent).toContain('Failed to render safe SVG');
    errorNodeView.destroy();
  });

  it('handles non-svg code blocks with standard pre and code elements', () => {
    const nodeViews = createMediaNodeViews();
    const pythonCodeNode = editorSchema.nodes.code_block.create(
      { lang: 'python' },
      editorSchema.text('print("hello world")'),
    );

    const codeBlockFn = nodeViews.code_block;
    if (!codeBlockFn) {
      throw new Error('Expected code_block to be defined');
    }

    const result = codeBlockFn(pythonCodeNode, {} as EditorView, () => 0);
    expect(result.dom.tagName.toLowerCase()).toBe('pre');
    expect(result.contentDOM?.tagName.toLowerCase()).toBe('code');
  });

  it('registers media extension via registerMediaExtension and exposes nodeViews', () => {
    registerMediaExtension();
    const exts = getRegisteredExtensions('description');
    const mediaExt = exts.find((e) => e.name === 'mediaNodeViews');
    expect(mediaExt).toBeDefined();
    expect(mediaExt?.nodeViews).toBeDefined();

    const nodeViews = mediaExt?.nodeViews?.({ surface: 'description' }) ?? createMediaNodeViews();
    const codeBlockFn = nodeViews.code_block;
    if (!codeBlockFn) {
      throw new Error('Expected code_block to be defined');
    }

    // Call code_block with svg node
    const svgCodeNode = editorSchema.nodes.code_block.create(
      { lang: 'svg' },
      editorSchema.text('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'),
    );
    const viewMock = {} as unknown as EditorView;
    let svgNodeView!: SvgCodeBlockNodeView;
    act(() => {
      svgNodeView = codeBlockFn(
        svgCodeNode,
        viewMock,
        () => 0,
        [] as readonly Decoration[],
        {} as unknown as DecorationSource,
      ) as SvgCodeBlockNodeView;
    });
    expect(svgNodeView.dom).toBeDefined();
    act(() => {
      svgNodeView.destroy();
    });
  });

  it('handles raw inline SVG string in MediaNodeView and revokes blob URL on destroy', async () => {
    const rawSvgSrc = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>';
    const nodeViews = createMediaNodeViews();
    const inlineSvgNode = editorSchema.nodes.image.create({
      src: rawSvgSrc,
      alt: 'Inline SVG Image',
    });

    const revokeSpy = vi.fn();
    const origRevoke = (u: string) => {
      URL.revokeObjectURL(u);
    };
    URL.revokeObjectURL = revokeSpy;

    const imageFn = nodeViews.image;
    if (!imageFn) {
      throw new Error('Expected image nodeView to be defined');
    }

    try {
      let nodeView!: MediaNodeView;
      act(() => {
        nodeView = imageFn(inlineSvgNode, {} as EditorView, () => 0) as MediaNodeView;
      });

      expect(nodeView.dom).toBeDefined();

      // Destroy and advance timeout to ensure root.unmount and URL.revokeObjectURL execute
      nodeView.destroy();
      await new Promise((r) => setTimeout(r, 20));
      expect(revokeSpy).toHaveBeenCalled();
    } finally {
      URL.revokeObjectURL = origRevoke;
    }
  });

  it('handles xml declaration prefix and malformed inline svg in MediaNodeView', async () => {
    const xmlSvgSrc = '<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>';
    const nodeViews = createMediaNodeViews();
    const xmlNode = editorSchema.nodes.image.create({
      src: xmlSvgSrc,
    });

    const imageFn = nodeViews.image;
    if (!imageFn) {
      throw new Error('Expected image nodeView to be defined');
    }

    let nodeView!: MediaNodeView;
    act(() => {
      nodeView = imageFn(xmlNode, {} as EditorView, () => 0) as MediaNodeView;
    });
    expect(nodeView.dom).toBeDefined();
    nodeView.destroy();
    await new Promise((r) => setTimeout(r, 20));

    // Malformed SVG inline (result.ok is false)
    const malformedNode = editorSchema.nodes.image.create({
      src: '<svg><broken-unclosed>',
    });
    act(() => {
      const malformedView = imageFn(malformedNode, {} as EditorView, () => 0) as MediaNodeView;
      expect(malformedView.dom).toBeDefined();
      malformedView.destroy();
    });

    // Node without src or alt attrs and duplicate destroy
    const emptyAttrsNode = editorSchema.nodes.image.create();
    act(() => {
      const emptyView = imageFn(emptyAttrsNode, {} as EditorView, () => 0) as MediaNodeView;
      expect(emptyView.dom).toBeDefined();
      emptyView.destroy();
      emptyView.destroy(); // Second call exercises if (!this.root)
    });
  });
});

describe('MediaLightbox Component Direct Tests', () => {
  it('returns null when isOpen is false', () => {
    const handleClose = vi.fn();
    const handleBackdrop = vi.fn();

    const { container } = render(
      <MediaLightbox
        isOpen={false}
        onClose={handleClose}
        src="blob:http://localhost/test"
        backdrop="theme"
        onBackdropChange={handleBackdrop}
      />,
    );

    expect(container.firstChild).toBeNull();
    expect(screen.queryByRole('dialog', { name: /media lightbox/i })).toBeNull();
  });

  it('renders dialog, handles backdrop clicks and inner clicks, and calls onClose', () => {
    const handleClose = vi.fn();
    const handleBackdrop = vi.fn();
    const triggerBtn = document.createElement('button');
    document.body.appendChild(triggerBtn);
    const triggerRef = { current: triggerBtn };

    const { unmount } = render(
      <MediaLightbox
        isOpen={true}
        onClose={handleClose}
        src="blob:http://localhost/test-lightbox"
        alt="Test Lightbox Modal"
        backdrop="theme"
        onBackdropChange={handleBackdrop}
        triggerRef={triggerRef}
      />,
    );

    const dialog = screen.getByRole('dialog', { name: /media lightbox/i });
    expect(dialog).toBeDefined();

    // Click inside the dialog content (e.target !== e.currentTarget) -> should NOT close
    const innerContent = dialog.querySelector('.media-lightbox-content');
    expect(innerContent).toBeDefined();
    if (innerContent) {
      fireEvent.click(innerContent);
      expect(handleClose).not.toHaveBeenCalled();
    }

    // Click the overlay directly (e.target === e.currentTarget) -> should close
    fireEvent.click(dialog);
    expect(handleClose).toHaveBeenCalledTimes(1);

    // Click close button -> should close
    const closeBtn = screen.getByRole('button', { name: /close lightbox/i });
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(2);

    // Non-Escape keydown should NOT close
    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(handleClose).toHaveBeenCalledTimes(2);

    // Escape keydown on window -> should close
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(3);

    unmount();
    document.body.removeChild(triggerBtn);
  });

  it('handles lightbox mounting without triggerRef and falls back to document.activeElement', () => {
    const handleClose = vi.fn();
    const handleBackdrop = vi.fn();

    const { unmount } = render(
      <MediaLightbox
        isOpen={true}
        onClose={handleClose}
        src="blob:http://localhost/no-trigger-ref"
        backdrop="dark"
        onBackdropChange={handleBackdrop}
      />,
    );

    expect(screen.getByRole('dialog', { name: /media lightbox/i })).toBeDefined();
    unmount();
  });
});
