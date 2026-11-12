import React, { type ComponentPropsWithoutRef, type JSX, type MouseEvent } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { toPeekPath } from './useIssueSurfaceRoute';

export interface IssueKeyLinkProps extends ComponentPropsWithoutRef<'a'> {
  issueKey: string;
  children?: React.ReactNode;
}

let lastOpenerElement: HTMLElement | null = null;

export function setOpenerElement(el: HTMLElement | null): void {
  lastOpenerElement = el;
}

export function getOpenerElement(): HTMLElement | null {
  if (lastOpenerElement && document.contains(lastOpenerElement)) {
    return lastOpenerElement;
  }
  return null;
}

export function IssueKeyLink({
  issueKey,
  children,
  onClick,
  className,
  ...rest
}: IssueKeyLinkProps): JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const href = toPeekPath(location, issueKey);

  const handleClick = (e: MouseEvent<HTMLAnchorElement>): void => {
    setOpenerElement(e.currentTarget);
    if (onClick) {
      onClick(e);
    }
    if (!e.defaultPrevented && e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) {
      e.preventDefault();
      void navigate(href);
    }
  };

  return (
    <a
      href={href}
      className={className ? `kb-issue-key-link ${className}` : 'kb-issue-key-link'}
      onClick={handleClick}
      data-issue-key={issueKey}
      {...rest}
    >
      {children ?? issueKey}
    </a>
  );
}
