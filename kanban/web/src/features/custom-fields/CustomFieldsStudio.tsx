// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { type JSX } from 'react';
import { CustomFieldDefinitionEditor } from './CustomFieldDefinitionEditor';

export interface CustomFieldsStudioProps {
  projectKey?: string | undefined;
  isAdmin?: boolean | undefined;
  readOnly?: boolean | undefined;
}

export function CustomFieldsStudio(props: CustomFieldsStudioProps): JSX.Element {
  return (
    <div className="kb-custom-fields-studio" data-testid="custom-fields-studio">
      <CustomFieldDefinitionEditor
        projectKey={props.projectKey ?? 'DEFAULT'}
        isAdmin={props.isAdmin ?? !props.readOnly}
      />
    </div>
  );
}

export { CustomFieldDefinitionEditor };
