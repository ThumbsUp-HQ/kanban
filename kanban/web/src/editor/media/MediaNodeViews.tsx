/**
 * ProseMirror NodeViews for Vector & Raster Media (KB-P3-48, S5.4).
 * Mounts interactive <MediaViewport> for image, image_block, and fenced ```svg blocks.
 */

import React from 'react';
import type { Node as ProsemirrorNode } from 'prosemirror-model';
import type { EditorView, NodeView } from 'prosemirror-view';
import { createRoot, type Root } from 'react-dom/client';
import { MediaViewport } from './MediaViewport';
import { createSafeSvgBlobUrl } from './safeSvg';
import { registerEditorExtension } from '../editorSurfaceFactory';
import { MermaidNodeView } from '../mermaid/MermaidBlockView';

export interface MediaNodeViewOptions {
  airGapMode?: boolean;
  resolveAttachmentUrl?: (attachmentId: string) => string;
}

export class MediaNodeView implements NodeView {
  dom: HTMLElement;
  private root: Root | null = null;
  private blobUrlToRevoke: string | null = null;

  constructor(
    node: ProsemirrorNode,
    _view: EditorView,
    _getPos: () => number | undefined,
    private readonly options?: MediaNodeViewOptions,
  ) {
    this.dom = document.createElement('div');
    this.dom.className = 'kb-media-nodeview';
    this.render(node);
  }

  private render(node: ProsemirrorNode): void {
    const src = (node.attrs.src as string) || '';
    const alt = (node.attrs.alt as string) || '';
    let finalSrc = src;
    let rawSource: string | undefined;

    if (src.trim().startsWith('<svg') || src.trim().startsWith('<?xml')) {
      const result = createSafeSvgBlobUrl(src);
      if (result.ok) {
        finalSrc = result.blobUrl;
        this.blobUrlToRevoke = result.blobUrl;
        rawSource = src;
      }
    }

    this.root ??= createRoot(this.dom);

    this.root.render(
      <MediaViewport
        src={finalSrc}
        alt={alt}
        rawSource={rawSource}
        airGapMode={this.options?.airGapMode}
        resolveAttachmentUrl={this.options?.resolveAttachmentUrl}
      />,
    );
  }

  update(node: ProsemirrorNode): boolean {
    if (node.type.name !== 'image' && node.type.name !== 'image_block') {
      return false;
    }
    this.render(node);
    return true;
  }

  destroy(): void {
    const rootToUnmount = this.root;
    this.root = null;
    if (rootToUnmount) {
      setTimeout(() => {
        rootToUnmount.unmount();
      }, 0);
    }
    if (this.blobUrlToRevoke) {
      try {
        URL.revokeObjectURL(this.blobUrlToRevoke);
      } catch {
        // Ignored
      }
      this.blobUrlToRevoke = null;
    }
  }
}

export class SvgCodeBlockNodeView implements NodeView {
  dom: HTMLElement;
  private root: Root | null = null;
  private blobUrlToRevoke: string | null = null;

  constructor(node: ProsemirrorNode) {
    this.dom = document.createElement('div');
    this.dom.className = 'kb-media-nodeview kb-media-nodeview--svg-block';
    this.render(node);
  }

  private render(node: ProsemirrorNode): void {
    const rawSvg = node.textContent;
    const result = createSafeSvgBlobUrl(rawSvg);

    this.root ??= createRoot(this.dom);

    if (result.ok) {
      this.blobUrlToRevoke = result.blobUrl;
      this.root.render(
        <MediaViewport
          src={result.blobUrl}
          rawSource={rawSvg}
          safeFilename="diagram.svg"
        />,
      );
    } else {
      this.root.render(
        <div className="media-airgap-placeholder">
          <span>Failed to render safe SVG ({result.error}): {result.message}</span>
        </div>,
      );
    }
  }

  update(node: ProsemirrorNode): boolean {
    if (node.type.name !== 'code_block' || node.attrs.lang !== 'svg') {
      return false;
    }
    this.render(node);
    return true;
  }

  destroy(): void {
    const rootToUnmount = this.root;
    this.root = null;
    if (rootToUnmount) {
      setTimeout(() => {
        rootToUnmount.unmount();
      }, 0);
    }
    if (this.blobUrlToRevoke) {
      try {
        URL.revokeObjectURL(this.blobUrlToRevoke);
      } catch {
        // Ignored
      }
      this.blobUrlToRevoke = null;
    }
  }
}

/**
 * Creates ProseMirror NodeView constructors for image, image_block, and svg code_blocks.
 */
export function createMediaNodeViews(
  options?: MediaNodeViewOptions,
): Record<string, (node: ProsemirrorNode, view: EditorView, getPos: () => number | undefined) => NodeView> {
  return {
    image: (node, view, getPos) => new MediaNodeView(node, view, getPos, options),
    image_block: (node, view, getPos) => new MediaNodeView(node, view, getPos, options),
    code_block: (node, view, getPos) => {
      if (node.attrs.lang === 'mermaid') {
        return new MermaidNodeView(node, view, getPos);
      }
      if (node.attrs.lang === 'svg') {
        return new SvgCodeBlockNodeView(node);
      }
      const dom = document.createElement('pre');
      const code = document.createElement('code');
      dom.appendChild(code);
      return {
        dom,
        contentDOM: code,
      };
    },
  };
}

/**
 * Registers media nodeViews extension with the global editor surface registry.
 */
export function registerMediaExtension(options?: MediaNodeViewOptions): void {
  registerEditorExtension({
    name: 'mediaNodeViews',
    surfaces: ['description', 'doc', 'sticky', 'comment'],
    nodeViews: () => createMediaNodeViews(options),
  });
}
