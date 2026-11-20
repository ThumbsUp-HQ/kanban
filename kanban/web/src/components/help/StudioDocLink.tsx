// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { type JSX } from 'react';
import { useOptionalShellPanels } from '../../app/shellPanels';
import './StudioDocLink.css';

export interface StudioDocLinkProps {
  href: string;
  title?: string;
  label?: string;
  testId?: string;
  className?: string;
}

export function StudioDocLink({
  href,
  title,
  label = 'Documentation ->',
  testId = 'studio-doc-link',
  className = 'kb-studio-doc-link',
}: StudioDocLinkProps): JSX.Element {
  const shellPanels = useOptionalShellPanels();

  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>): void => {
    if (shellPanels && href) {
      e.preventDefault();
      shellPanels.openPanel('help', { href, title: title ?? label });
    }
  };

  return (
    <a
      href={href}
      className={className}
      data-testid={testId}
      onClick={handleClick}
      aria-label={title ?? label}
    >
      <span aria-hidden="true">&#128214;</span>
      <span>{label}</span>
    </a>
  );
}
