// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { type JSX } from 'react';
import { ProjectModulesView } from '../../app/routes';

export function ModulesView(): JSX.Element {
  return (
    <div className="kb-modules-view-wrapper" data-testid="modules-view">
      <ProjectModulesView />
    </div>
  );
}

export { ProjectModulesView };
