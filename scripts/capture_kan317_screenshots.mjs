// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import fs from "node:fs";
import path from "node:path";
import { chromium } from "/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs";

const WORKSPACE_ROOT = process.cwd();
const OUT_DIR = path.join(WORKSPACE_ROOT, "docs/qa/KAN-317/screenshots");

const VIEWPORTS = [
  { prefix: "01-desktop-light-report-export", alt: "1440x900-desktop-light", width: 1440, height: 900, theme: "light" },
  { prefix: "02-desktop-dark-report-export", alt: "1440x900-desktop-dark", width: 1440, height: 900, theme: "dark" },
  { prefix: "03-tablet-report-export", alt: "768x1024-tablet", width: 768, height: 1024, theme: "light" },
  { prefix: "04-mobile-portrait-report-export", alt: "390x844-mobile-portrait", width: 390, height: 844, theme: "light" },
  { prefix: "05-mobile-landscape-report-export", alt: "844x390-mobile-landscape", width: 844, height: 390, theme: "light" },
];

function buildHtml() {
  const tokensCss = fs.readFileSync(path.join(WORKSPACE_ROOT, "kanban/web/src/styles/tokens.css"), "utf-8");
  const themeCss = fs.readFileSync(path.join(WORKSPACE_ROOT, "kanban/web/src/styles/theme.css"), "utf-8");
  const reportsCss = fs.readFileSync(path.join(WORKSPACE_ROOT, "kanban/web/src/features/reports/reports.css"), "utf-8");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Report Export Modal Preview</title>
  <style>
    ${tokensCss}
    ${themeCss}
    ${reportsCss}

    body {
      margin: 0;
      padding: 0;
      font-family: var(--font-sans, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif);
      background-color: var(--bg-canvas, #f7f8fa);
      color: var(--text-primary, #111827);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }
  </style>
</head>
<body>
  <div class="reports-modal-backdrop" style="position: relative; inset: auto; min-height: 100vh; width: 100%; padding: 24px;">
    <div class="reports-modal-container reports-modal-container--wide" role="dialog" aria-modal="true" aria-labelledby="report-export-title">
      
      <!-- Modal Header -->
      <div class="reports-modal-header">
        <div class="reports-modal-title" id="report-export-title">
          <span>📊</span>
          <span>Generate Project Report</span>
        </div>
        <button type="button" class="reports-modal-close-btn" aria-label="Close dialog">✕</button>
      </div>

      <!-- Modal Body -->
      <div class="reports-modal-body">
        
        <!-- Template Selection -->
        <div class="reports-form-group">
          <label for="report-template-select" class="reports-label">
            Report Template
          </label>
          <select id="report-template-select" class="reports-select">
            <option value="security-assessment-report" selected>Security Assessment Report (Built-in)</option>
            <option value="sprint-release-notes">Sprint & Release Notes Report (Built-in)</option>
            <option value="executive-status-risk">Executive Status & Risk Report (Built-in)</option>
          </select>
        </div>

        <!-- Format Selector Pills -->
        <div class="reports-form-group">
          <label class="reports-label">Export Format</label>
          <div class="reports-format-pills">
            <button type="button" class="reports-format-pill reports-format-pill--active" aria-pressed="true">PDF</button>
            <button type="button" class="reports-format-pill" aria-pressed="false">XLSX</button>
            <button type="button" class="reports-format-pill" aria-pressed="false">CSV</button>
            <button type="button" class="reports-format-pill" aria-pressed="false">DOCX</button>
            <button type="button" class="reports-format-pill" aria-pressed="false">ODT</button>
            <button type="button" class="reports-format-pill" aria-pressed="false">HTML</button>
            <button type="button" class="reports-format-pill" aria-pressed="false">MD</button>
          </div>
        </div>

        <!-- Dynamic Template Parameters -->
        <div class="reports-form-group">
          <label class="reports-label">Template Parameters</label>
          <div class="reports-parameters-grid">
            <div class="reports-form-group">
              <label for="param-mission" class="reports-label">Assessment Mission & Scope</label>
              <textarea id="param-mission" class="reports-textarea">Target Environment Security Assessment and Threat Surface Audit.</textarea>
            </div>
            <div class="reports-form-group">
              <label for="param-boilerplate" class="reports-label">Boilerplate & Legal Notice</label>
              <textarea id="param-boilerplate" class="reports-textarea">CONFIDENTIAL // PROPRIETARY - ACME PLATFORM AUDIT TEAM.</textarea>
            </div>
            <div class="reports-form-group">
              <label for="param-executive_summary" class="reports-label">Executive Summary</label>
              <textarea id="param-executive_summary" class="reports-textarea">This assessment identified 3 critical vulnerabilities across authentication, export sanitization, and CSP boundaries.</textarea>
            </div>
            <div class="reports-form-group">
              <label for="param-appendix" class="reports-label">Appendix & Methodology</label>
              <textarea id="param-appendix" class="reports-textarea">All testing conducted under OWASP ASVS 4.0.3 and NIST SP 800-115 standards.</textarea>
            </div>
          </div>
        </div>

        <!-- AES-256 ZIP Password Toggle -->
        <div class="reports-encryption-box">
          <label class="reports-checkbox-row">
            <input type="checkbox" class="reports-checkbox" checked />
            <span class="reports-checkbox-label">
              🔒 Encrypt report in AES-256 password-protected ZIP archive (WinZip AE-2)
            </span>
          </label>
          <div class="reports-form-group">
            <input type="password" class="reports-input" value="SuperSecretAuditPassphrase2026!" placeholder="Enter encryption passphrase (min 4 characters)" />
          </div>
        </div>

        <!-- Live Preview Pane -->
        <div class="reports-preview-container">
          <div style="font-weight: 600; font-size: 0.875rem; margin-bottom: 8px; color: var(--text-secondary, #64748b);">
            Live Preview Output (Security Assessment Report)
          </div>
          <pre class="reports-preview-content"># Target Environment Security Assessment and Threat Surface Audit.
CONFIDENTIAL // PROPRIETARY - ACME PLATFORM AUDIT TEAM.

## Table of Contents
- [Executive Summary](#executive-summary)
- [Details](#details)
  - [2026-11-20 - Remote Code Execution via SSTI in Custom Field Template [URGENT]](#2026-11-20---remote-code-execution-via-ssti-in-custom-field-template-urgent)
  - [2026-11-21 - CWE-1236 Formula Injection in CSV Export [HIGH]](#2026-11-21---cwe-1236-formula-injection-in-csv-export-high)
  - [2026-11-22 - Missing Strict Content-Security-Policy on Report Preview [MEDIUM]](#2026-11-22---missing-strict-content-security-policy-on-report-preview-medium)
- [Appendix](#appendix)

# Executive Summary
This assessment identified 3 critical vulnerabilities across authentication, export sanitization, and CSP boundaries.

| Key | Summary | State | Priority | Assignees | Created Date |
| --- | --- | --- | --- | --- | --- |
| SEC-101 | Remote Code Execution via SSTI in Custom Field Template | In Progress | Urgent | sec-lead, app-sec | 2026-11-20 |
| SEC-102 | CWE-1236 Formula Injection in CSV Export | Resolved | High | backend-eng | 2026-11-21 |
| SEC-103 | Missing Strict Content-Security-Policy on Report Preview | Open | Medium | frontend-eng | 2026-11-22 |</pre>
        </div>

      </div>

      <!-- Modal Footer -->
      <div class="reports-modal-footer">
        <div class="reports-footer-left">
          <button type="button" class="reports-btn reports-btn--secondary">⚙️ Template Studio</button>
          <button type="button" class="reports-btn reports-btn--secondary">👁️ Refresh Preview</button>
        </div>
        <div class="reports-footer-right">
          <button type="button" class="reports-btn reports-btn--secondary">Cancel</button>
          <button type="button" class="reports-btn reports-btn--primary">⬇️ Export Report (PDF)</button>
        </div>
      </div>

    </div>
  </div>
</body>
</html>`;
}

async function run() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  console.log(`Starting Playwright screenshot capture for KAN-317...`);

  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
  });

  const htmlContent = buildHtml();
  const tempHtmlPath = path.join(WORKSPACE_ROOT, "docs/qa/KAN-317/temp-preview.html");
  fs.writeFileSync(tempHtmlPath, htmlContent, "utf-8");

  for (const vp of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
    });

    const page = await context.newPage();
    await page.goto(`file://${tempHtmlPath}`, { waitUntil: "load" });

    if (vp.theme === "dark") {
      await page.evaluate(() => {
        document.documentElement.setAttribute("data-theme", "dark");
        document.documentElement.dataset.theme = "dark";
      });
      await page.waitForTimeout(200);
    } else {
      await page.evaluate(() => {
        document.documentElement.setAttribute("data-theme", "light");
        document.documentElement.dataset.theme = "light";
      });
      await page.waitForTimeout(200);
    }

    const outPath1 = path.join(OUT_DIR, `${vp.prefix}.png`);
    const outPath2 = path.join(OUT_DIR, `${vp.alt}.png`);

    await page.screenshot({ path: outPath1, fullPage: true });
    fs.copyFileSync(outPath1, outPath2);
    console.log(`Saved screenshot: ${outPath1} and ${outPath2}`);

    await context.close();
  }

  // Cleanup temp html file
  if (fs.existsSync(tempHtmlPath)) {
    fs.unlinkSync(tempHtmlPath);
  }

  await browser.close();
  console.log("All 5 responsive Playwright screenshots captured successfully!");
}

run().catch((err) => {
  console.error("Screenshot capture failed:", err);
  process.exit(1);
});
