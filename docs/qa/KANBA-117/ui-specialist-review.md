# UI Specialist Gate Review: KANBA-117 (KB-P3-52)

- **Ticket**: `KANBA-117` (`KB-P3-52`: Standalone status panel: volume persistence, encrypted backup trigger & docker-compose.yml export)
- **Reviewer**: `@ui-specialist` (Frontend & UI/UX Specialist)
- **Branch**: `feat/KANBA-117`
- **Worktree**: `/tmp/kb-wt-KANBA-117`
- **Scope**: `kanban/web/src/features/standalone/`, `kanban/web/src/app/HeaderPills.tsx`, `kanban/web/src/app/AppShell.tsx`, `kanban/web/e2e/standalone/`
- **Board Ref**: UI/UX ergonomics guidance in Swarm Message #839

---

### 1. Visual Verification & Layout Ergonomics Audit

#### A. Modal Geometry, Whitespace & Responsive Rhythm (Spec S6.1, S2.2)
- **Desktop/Tablet (> 767px)**:
  - Centered breathable dialog (`width: min(640px, 100vw - 32px)`, `max-height: min(720px, 90vh)`).
  - Probed computed styles in `computed-styles-desktop.json` confirm exact `24px` padding and `24px` section gap.
  - Header pill trigger conforms to 24px x 24px geometry with centered flex alignment.
- **Mobile (<= 767px)**:
  - Responsive bottom-sheet design with 16px top border radius.
  - Touch target ergonomics: All action buttons, input fields, and copy controls exceed the 44px touch target minimum.
  - Full mobile viewport scrollability tested with zero clipping.

#### B. Ephemeral Warning vs Persistent Calm Visual Design (Spec S2.2 item 1 & 5)
- **Ephemeral Storage Detected (`persistent_volume: false`)**:
  - High-visibility amber warning banner (`background: #fef3c7`, `color: #78350f`). Contrast ratio exceeds 7.1:1, well above WCAG AA 4.5:1 requirement.
  - Clear copyable run command block with 1-click copy button providing visual "Copied!" feedback and auto-reset after 2000ms.
- **Persistent Volume Mounted (`persistent_volume: true`)**:
  - Calm green checkmark badge (`background: #dcfce7`, `color: #166534`).
  - Correct role scoping: displays `/var/lib/kanban/data (ext4)` for server admins while showing non-disclosing `Persistent volume verified` for regular members.

#### C. Keyboard Lifecycle & A11y Verification (Spec S6.2)
- Focus trapped inside dialog while open (`role="dialog" aria-modal="true"`).
- Initial focus placed on the primary close button on mount.
- Full Tab and Shift+Tab cycling verified across focusable controls.
- `Escape` key closes the dialog and cleanly returns focus to the triggering `⚠️` HeaderPill.

#### D. Encrypted Backup & Promotion Runbook UX (Spec S2.4, S3.5)
- **Passphrase Form**: Password input with `minLength={16}`, live validation hint, and defensive submission gating.
- **Export Progress**: Visual state updates during backup export and 1-click compose download, with immediate `blob:` URL revocation preventing memory bloat.
- **Monospace Promotion Checklist**: Clear 4-step runbook rendered in monospace card format, with 1-click `.env.example` template copying.
- **Non-Admin View**: Completely unmounts backup form, host paths, and compose controls. Displays calm guidance: `Contact a Server Administrator to export backups or promote this instance.`

#### E. Strict CSP Compliance (Spec S5.4)
- Verified zero inline JSX `style={{...}}` attributes in `StandaloneStatusPanel.tsx` and `ComposeExportTab.tsx`. All styles are encapsulated in `StandaloneStatusPanel.css`.

---

### 2. Specialist Verdict

The Standalone Status Panel delivers high-contrast warning legibility without alarmist clutter, exemplary keyboard and focus accessibility, clean role-scoped redaction, and strict CSP compliance across desktop, tablet, and mobile viewports.

**VERDICT: APPROVED**
