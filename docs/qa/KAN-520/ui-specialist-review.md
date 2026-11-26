## Round-2 Clean-Room UI Specialist Re-Audit: KAN-520 (Commit 33f44e51)

**Component:** `AgentOnboardingPromptCard` (`StudioDocLink` in card header action bar)
**Verified Artifacts:** `AgentOnboardingPromptCard.tsx`, `AgentOnboardingPromptCard.css`, `AgentOnboardingPromptCard.test.tsx`, `docs/qa/KAN-520/git-diff.patch`, `unit-test-results.txt`, `build-check.txt`, and all 6 screenshots in `docs/qa/KAN-520/screenshots/`.

### Resolution Verification
1. **390px Mobile Vertical Flex-Basis Fix:** Inside `@media (max-width: 480px)`, `.kb-agent-onboarding-header-main` sets `flex: 0 1 auto; width: 100%;`, eliminating dead vertical whitespace.
2. **Mobile Light & Dark Visual Verification (`390x844`):** Full card header (`Agent Onboarding Prompt (/llms.txt)`, subtitle, and `Documentation ->` pill) is cleanly visible together without clipping or overflow.
3. **Contrast, ARIA, Coverage & Build:** Light (`5.17:1`), Dark & System Dark (`8.73:1`), zero inline styles, `21/21` tests (`100%` coverage), and clean `tsc`/`eslint`/`vite build`/`check_no_dashes` (`exit code 0`).

Verdict: APPROVED
