# UI Specialist Review: KAN-517

**Ticket:** `KAN-517` (`[UX-SIMPLIFY][ADMIN-OPS-MCP] Low Contrast on Primary CTA Buttons in McpUnifiedStudio (+ Mint MCP Key, + Add Workload Policy)`)
**Commit:** `8eb6138e`
**Reviewer:** UI Designer (`.agents/agents/ui-designer.md`, clean-room audit)

## Scope Verified

Confirmed diff (`docs/qa/KAN-517/git-diff.patch`) modifies only:
- `kanban/web/src/features/settings/McpAccessStudio.css`
- `kanban/web/src/features/settings/__tests__/McpAccessStudio.test.tsx`

## Design System & WCAG AA Contrast Audit

1. **Primary CTA Buttons (`+ Mint MCP Key` and `+ Add Workload Policy`):**
   - Both buttons render with `.kb-mcp-studio-mint-btn` (`McpAccessStudio.tsx` line 761 and `McpUnifiedStudio.tsx` line 263).
   - Default state in `McpAccessStudio.css`: `background-color: #047857`, `border: 1px solid #047857`, `color: var(--accent-primary-fg, #ffffff)` (**5.48:1** contrast in both Light and Dark modes, exceeding WCAG AA 4.5:1).
   - Hover state (`.kb-mcp-studio-mint-btn:hover:not(:disabled)`): `background-color: #065f46`, `border-color: #065f46` (**7.68:1** contrast against `#ffffff`).
2. **Connect CTA Button (`.kb-mcp-connect-btn`):**
   - Updated consistently to `#047857` / `#065f46` (**5.48:1** / **7.68:1**).
3. **Admin Subnav Active Tab (`.kb-mcp-admin-subnav-active`):**
   - Updated to `color: var(--badge-fg) !important` and `border-bottom-color: var(--badge-fg) !important` (**4.86:1+** Light, **9.95:1+** Dark).

## Visual & Responsive Inspection (Screenshots)

- **`desktop-light-1440x900.png` & `desktop-dark-1440x900.png`:** `+ Mint MCP Key` primary emerald CTA (`#047857` fill, crisp white `#ffffff` label) and active `Bot API Keys` tab render with high contrast and zero error banners or toasts.
- **`tablet-768x1024.png` & `mobile-390x844.png`:** Header actions and subnav links wrap cleanly within viewport bounds with zero horizontal overflow, truncation, or error banners.

## Test & Build Verification

- `docs/qa/KAN-517/unit-test-results.txt`: `McpAccessStudio.test.tsx` passed `53/53` tests (exit code `0`).
- `docs/qa/KAN-517/build-check.txt`: `tsc --noEmit`, `eslint . --max-warnings 0`, `tsc -b && vite build`, and `check_no_dashes --all` passed with exit code `0`.

Verdict: APPROVED
