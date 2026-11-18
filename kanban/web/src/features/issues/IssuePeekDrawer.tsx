// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { type JSX } from 'react';
import {
  IssueSurfaceRoot,
  IssueSurface,
  type IssueSurfaceRootProps,
} from '../drawer/IssueSurface';

export type IssuePeekDrawerProps = Partial<IssueSurfaceRootProps>;

export function IssuePeekDrawer(props: IssuePeekDrawerProps): JSX.Element {
  if (props.issueKey) {
    return (
      <IssueSurfaceRoot
        issueKey={props.issueKey}
        projectKey={props.projectKey ?? null}
        mode={props.mode ?? 'drawer'}
      />
    );
  }
  return <IssueSurface />;
}

export { IssueSurfaceRoot, IssueSurface };
