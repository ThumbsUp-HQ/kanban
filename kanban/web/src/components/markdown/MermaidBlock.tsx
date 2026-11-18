// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { type JSX } from 'react';
import {
  MermaidBlockView,
  type MermaidBlockViewProps,
} from '../../editor/mermaid/MermaidBlockView';

export type MermaidBlockProps = MermaidBlockViewProps;

export function MermaidBlock(props: MermaidBlockProps): JSX.Element {
  return <MermaidBlockView {...props} />;
}

export { MermaidBlockView };
