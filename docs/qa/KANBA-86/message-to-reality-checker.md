# Reality-Checker Audit Note: KANBA-86 (KB-P3-07)

## Architectural Scope & Technical Implementation
This ticket (`KANBA-86` / `KB-P3-07`: `[Phase 3 / API] Typed object links API, canonical URL helper & restricted-target masking`) implements the typed object links API, canonical URL helper, and restricted-target masking under the Universal Object Graph:

1. **Target Files**:
   - `kanban/api/v1/links.py`: 4 REST endpoints mounted on `build_v1_router()`, wrapped with `timing_floor(floor_ms=25.0)`.
   - `kanban/api/v1/schemas/links.py`: Pydantic request/response schemas with `ConfigDict(extra="forbid")`, supporting `UnrestrictedEndpointOut`, `RestrictedEndpointOut`, `EndpointOut`, `OutboundLinkOut`, `InboundLinkOut`, `LinksListResponse`, and `CanonicalUrlResponse`.
   - `kanban/services/links.py`: Full links service implementing `create_object_link`, `list_object_links`, `delete_object_link`, `build_canonical_url`, user-creatable kind enforcement, and matrix validation.
   - `kanban/services/object_ref.py`: `resolve_object_ref()` resolving UUID, issue keys (`KAN-142`), or project identifiers (`KAN`) up to 64 chars under RLS.
   - `kanban/settings.py`: Added `public_base_url` (`KANBAN_PUBLIC_BASE_URL` / `KB_PUBLIC_BASE_URL`) enforcing `https://` except localhost in standalone mode.
   - `kanban/app.py` & `kanban/api/deps.py`: Mounted `settings` on `app.state` and provided `get_settings()` dependency.
   - `kanban/services/activity.py`: Added `LINK_CREATED` and `LINK_DELETED` under category `HISTORY`.

2. **Security & RLS Invariants**:
   - **Restricted Target Masking**: If the requesting user lacks `VIEW` permissions on the far endpoint of an object link, the endpoint is strictly masked as `{"restricted": true, "label": "🔒 Restricted Object"}` with no `id`, `type`, `key`, `title`, or `target_key_snapshot` leaked.
   - **Anti-Enumeration 422**: Attempting to create a link to an unreadable target vs a nonexistent target returns the identical `422 TARGET_NOT_FOUND` response body.
   - **Anti-Enumeration 404**: Deletion of a link where the source object is unreadable returns `404` even if the link ID is valid.
   - **Direct Deletion Guard on FLAGGED_INVALID**: `FLAGGED_INVALID` links reject direct deletion with `422 FLAGGED_LINK_REQUIRES_AUDITED_PURGE`, protecting the forensic audit trail.
   - **Canonical URL Integrity**: Canonical URLs are derived strictly from `Settings.public_base_url`. The request `Host` header is ignored, preventing host-header injection attacks. Markdown links escape `[]()` characters.
   - **Activity Ledger**: Creation and deletion emit double activity records: once on the source object and once on the target object.

3. **Verification & Quality Status**:
   - **Unit Tests**: 14/14 tests passing in 4.42s with **97.67%** branch + line coverage (`kanban.api.v1.links` 100%, `kanban.services.object_ref` 100%, `kanban.services.links` 97%), exceeding the 95% threshold.
   - **Static Checks**: Ruff check clean, Ruff format clean, Mypy strict clean (128 source files), Lint-imports clean (2 kept, 0 broken), License gate clean (violations=0), Zero non-ASCII dashes repo-wide.
   - **Contract Proof**: `contract-sample.json` captures 7 HTTP wire exchanges (`create_link_201`, `list_links_masked_200`, `target_not_found_422`, `link_type_not_allowed_422`, `link_exists_409`, `canonical_url_200`, `delete_link_204`).
