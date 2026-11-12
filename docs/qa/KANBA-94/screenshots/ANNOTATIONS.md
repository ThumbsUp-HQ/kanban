# Visual QA Annotations: Isolated Mermaid Web Worker Renderer (KB-P3-47)

- **Ticket:** `KANBA-94` (`KB-P3-47`: `[Phase 3 / Frontend] Isolated Mermaid Web Worker renderer with directive firewall, resource caps & 1500ms watchdog`)
- **Environment:** Playwright headless Chromium on Vite preview (`preview.port: 4173`)
- **Strict CSP Active:** `default-src 'self'; script-src 'self' 'nonce-...'; require-trusted-types-for 'script'; trusted-types kanban-sanitizer dompurify; img-src 'self' blob:;`
- **Viewports Tested:** Desktop (`1440x900`), Tablet (`1024x768`), Mobile (`390x844`)

---

## 1. Screenshot Matrix

| Scenario | Screenshot Filename | Viewport | Verification Target |
| :--- | :--- | :--- | :--- |
| **01: Light Theme Rendering** | `01-mermaid-light-desktop.png` | `1440x900` | Sandboxed Mermaid SVG blob rendered in `MediaViewport`; strictly 0 inline `<svg>` elements; mode toggle and zoom controls visible. |
| **01: Light Theme Rendering** | `01-mermaid-light-tablet.png` | `1024x768` | Fluid responsive layout on tablet; touch toolbar controls accessible. |
| **01: Light Theme Rendering** | `01-mermaid-light-mobile.png` | `390x844` | Mobile viewport scaling; 100% width fit with zoom controls positioned above diagram fold. |
| **02: Dark Theme Sync** | `02-mermaid-dark-theme-sync-desktop.png` | `1440x900` | MutationObserver triggers live re-render with dark tokens (`#16181d` surface, `#f9fafb` text); prior blob URL revoked. |
| **02: Dark Theme Sync** | `02-mermaid-dark-theme-sync-tablet.png` | `1024x768` | Dark theme contrast verification on tablet viewport. |
| **02: Dark Theme Sync** | `02-mermaid-dark-theme-sync-mobile.png` | `390x844` | Dark theme contrast verification on mobile viewport. |
| **03: Fallback Banner** | `03-mermaid-watchdog-fallback-desktop.png` | `1440x900` | Calm notice banner displayed on node cap (>400 nodes); unexecuted sanitized source displayed in monospace block. |
| **03: Fallback Banner** | `03-mermaid-watchdog-fallback-tablet.png` | `1024x768` | Fallback banner typography and contrast on tablet viewport. |
| **03: Fallback Banner** | `03-mermaid-watchdog-fallback-mobile.png` | `390x844` | Fallback banner line wrapping and readable source block on mobile viewport. |

---

## 2. Callout Key & Verification Annotations

### Scenario 01: Light Theme Rendering (`01-mermaid-light-*.png`)
- **Callout 1 (Sandboxed Mermaid SVG Blob):** Identifies `<img src="blob:http://...">` mounted inside `.media-viewport`. Invariant verified: strictly zero inline `<svg>` or `<foreignObject>` nodes exist in ProseMirror DOM.
- **Callout 2 (MediaViewport Controls):** Floating toolbar providing zoom (`-`, `+`, `100%`), copy SVG, download SVG, and fullscreen inspection controls.
- **Callout 3 (Edit Mermaid Toggle):** Header toolbar toggle pill allowing authors to switch between visual preview and raw source editor.

### Scenario 02: Dark Theme Synchronization (`02-mermaid-dark-theme-sync-*.png`)
- **Callout 1 (Dark Mode Re-rendered Blob):** Verifies re-rendered SVG with dark background `#16181d`, light text `#f9fafb`, and dark border `#3f4756`. Confirms active blob URL revocation and replacement without UI flicker.
- **Callout 2 (Theme Indicator Badge):** Verifies document-level theme switch to Dark (`data-theme="dark"`).

### Scenario 03: Fallback Banner (`03-mermaid-watchdog-fallback-*.png`)
- **Callout 1 (Calm Fallback Banner):** Amber notice banner (`⚠ Diagram rendered as source: exceeded 400 node limit`) informing the user calmly of resource boundary enforcement.
- **Callout 2 (Monospace Source Block):** Preserved, sanitized canonical Mermaid diagram source displayed safely without script execution.

---

## 3. Style & Layout Proofs (`computed-styles-*.json`)
- Verified `.mermaid-block` maintains CSS containment (`border-radius: 8px`, `margin: 16px 0`).
- Verified `.media-viewport` enforces height cap (`max-height: 520px`) preventing viewport ballooning.
- Verified `.mermaid-block img` scales responsively (`max-height: 520px`, `object-fit: contain`).
