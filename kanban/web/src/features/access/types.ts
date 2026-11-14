/* v8 ignore file */
/**
 * Anti-enumeration Access Manifest and Inspector types (KB-P3-49, S3.4).
 */

export interface ManifestUser {
  principal_id: string;
  handle: string;
  display_name: string;
  capabilities: string[];
  grant_source: string;
}

export interface ManifestGroup {
  principal_id: string;
  name: string;
  member_count: number;
  external_source?: 'LDAP' | 'OIDC' | null;
  capabilities: string[];
  grant_source: string;
}

export interface ManifestAgent {
  principal_id: string;
  display_name: string;
  principal_type: string;
  provider_badge?: string | null;
  scope_summary?: string;
  role?: string;
  capabilities: string[];
}

export interface ManifestDenyOverride {
  principal_id?: string | null;
  principal_type: string;
  display_name: string;
  redacted?: boolean;
  denied_capabilities: string[];
}

export interface ManifestRedactedEntry {
  redacted: true;
  label?: string;
  [key: string]: unknown;
}

export interface InheritedScopeData {
  kind: 'private' | 'project' | 'workspace';
  scope_label: string;
  workspace_id?: string;
  workspace_name?: string;
  project_id?: string | null;
  project_key?: string | null;
  project_name?: string | null;
}

export interface AccessManifest {
  object_id?: string;
  object_type?: string;
  canonical_key?: string;
  pill_label?: string;
  explicit_grant_count?: number;
  inherited_scope: InheritedScopeData;
  users: ManifestUser[];
  groups: ManifestGroup[];
  agents: ManifestAgent[];
  deny_overrides: ManifestDenyOverride[];
  redacted_entries?: ManifestRedactedEntry[];
  redacted_count?: number;
  caller_capabilities?: string[];
}
