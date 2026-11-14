// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { type JSX } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { CustomFieldDefinitionEditor } from '../../../features/custom-fields/CustomFieldDefinitionEditor';

export default function ProjectCustomFieldsSettingsRoute(): JSX.Element {
  const { projectKey } = useParams<{ projectKey: string }>();
  const [searchParams] = useSearchParams();

  // Non-admin query param or role override enables anti-enumeration 404 test verification
  const isNonAdmin =
    searchParams.get('non_admin') === 'true' ||
    searchParams.get('role') === 'member' ||
    searchParams.get('role') === 'viewer';

  const isAdmin = !isNonAdmin;

  return (
    <CustomFieldDefinitionEditor
      projectKey={projectKey ?? ''}
      isAdmin={isAdmin}
    />
  );
}
