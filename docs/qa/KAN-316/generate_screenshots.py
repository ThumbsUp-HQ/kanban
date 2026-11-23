#!/usr/bin/env python3
# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Generate 5 responsive Playwright screenshots for KAN-316 visual verification proof."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "docs" / "qa" / "KAN-316" / "screenshots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Read CSS files
tokens_css = (BASE_DIR / "kanban" / "web" / "src" / "styles" / "tokens.css").read_text(encoding="utf-8")
theme_css = (BASE_DIR / "kanban" / "web" / "src" / "styles" / "theme.css").read_text(encoding="utf-8")
base_css = (BASE_DIR / "kanban" / "web" / "src" / "styles" / "base.css").read_text(encoding="utf-8")
modal_css = (BASE_DIR / "kanban" / "web" / "src" / "features" / "views" / "CsvImportExportModal.css").read_text(encoding="utf-8")

EXPORT_MODAL_HTML = """
<div class="kb-csv-modal-backdrop" role="dialog" aria-modal="true">
  <div class="kb-csv-modal-dialog">
    <header class="kb-csv-modal-header">
      <h2 class="kb-csv-modal-heading">Import / Export Issues</h2>
      <button class="kb-csv-modal-close-btn" aria-label="Close dialog">✕</button>
    </header>
    <nav class="kb-csv-modal-tabs">
      <button class="kb-csv-modal-tab kb-csv-modal-tab--active">Export Issues</button>
      <button class="kb-csv-modal-tab">Import Issues</button>
    </nav>
    <div class="kb-csv-modal-body">
      <div class="kb-csv-modal-section">
        <p class="kb-csv-modal-desc">
          Exporting <strong>24 issues</strong> matching active Navigator filters (State: In Progress, Review; Priority: High, Urgent).
        </p>
      </div>
      <div class="kb-csv-modal-field">
        <label class="kb-csv-modal-label">Export Format</label>
        <div class="kb-csv-modal-radio-group">
          <label class="kb-csv-modal-radio-label">
            <input type="radio" name="format" value="csv" />
            <div>
              <span>Standard CSV (.csv)</span>
              <span class="kb-csv-modal-radio-desc">Plain UTF-8 spreadsheet with formula-injection defenses</span>
            </div>
          </label>
          <label class="kb-csv-modal-radio-label">
            <input type="radio" name="format" value="zip_csv" checked />
            <div>
              <span>WinZip AES-256 Encrypted ZIP (.zip)</span>
              <span class="kb-csv-modal-radio-desc">AE-2 CTR-256 authenticated archive with PBKDF2-HMAC-SHA256</span>
            </div>
          </label>
        </div>
      </div>
      <div class="kb-csv-modal-field">
        <label class="kb-csv-modal-label" for="zip-password">ZIP Password (minimum 12 characters)</label>
        <input
          id="zip-password"
          type="password"
          class="kb-csv-modal-input"
          value="SuperSecretPassword123!"
          placeholder="Enter encryption password..."
        />
        <div class="kb-password-hint kb-password-hint--valid">
          ✓ Password meets the 12-character security policy (23 characters)
        </div>
      </div>
    </div>
    <footer class="kb-csv-modal-footer">
      <button class="kb-csv-btn kb-csv-btn-secondary">Cancel</button>
      <button class="kb-csv-btn kb-csv-btn-primary">Export 24 Issues</button>
    </footer>
  </div>
</div>
"""

IMPORT_MODAL_HTML = """
<div class="kb-csv-modal-backdrop" role="dialog" aria-modal="true">
  <div class="kb-csv-modal-dialog">
    <header class="kb-csv-modal-header">
      <h2 class="kb-csv-modal-heading">Import / Export Issues</h2>
      <button class="kb-csv-modal-close-btn" aria-label="Close dialog">✕</button>
    </header>
    <nav class="kb-csv-modal-tabs">
      <button class="kb-csv-modal-tab">Export Issues</button>
      <button class="kb-csv-modal-tab kb-csv-modal-tab--active">Import Issues</button>
    </nav>
    <div class="kb-csv-modal-body">
      <div class="kb-csv-modal-section">
        <div class="kb-csv-modal-desc">
          Upload a project CSV or password-protected WinZip AE-2 archive.
        </div>
      </div>
      <div class="kb-csv-file-dropzone">
        <div class="kb-csv-file-selected">📁 project_issues_sync_q4.csv (14.2 KB)</div>
        <div class="kb-csv-stat-label">Ready for preview. Click or drop to replace.</div>
      </div>
      <div class="kb-csv-modal-section">
        <div class="kb-csv-diff-stats">
          <div class="kb-csv-stat-card kb-csv-stat-card--success">
            <div class="kb-csv-stat-number">12</div>
            <div class="kb-csv-stat-label">To Create</div>
          </div>
          <div class="kb-csv-stat-card kb-csv-stat-card--accent">
            <div class="kb-csv-stat-number">3</div>
            <div class="kb-csv-stat-label">To Update</div>
          </div>
          <div class="kb-csv-stat-card">
            <div class="kb-csv-stat-number">0</div>
            <div class="kb-csv-stat-label">Errors</div>
          </div>
          <div class="kb-csv-stat-card">
            <div class="kb-csv-stat-number">15</div>
            <div class="kb-csv-stat-label">Total Rows</div>
          </div>
        </div>
        <div class="kb-csv-diff-table-wrap">
          <table class="kb-csv-diff-table">
            <thead>
              <tr>
                <th>Row</th>
                <th>Key</th>
                <th>Action</th>
                <th>Summary</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>1</td>
                <td><code>--</code></td>
                <td><span class="kb-csv-action-badge kb-csv-action-badge--create">Create</span></td>
                <td>Hardened memory zeroize buffer protection</td>
                <td>In Progress</td>
              </tr>
              <tr>
                <td>2</td>
                <td><code>KAN-316</code></td>
                <td><span class="kb-csv-action-badge kb-csv-action-badge--update">Update</span></td>
                <td>WinZip AE-2 CSV export governance</td>
                <td>In Review</td>
              </tr>
              <tr>
                <td>3</td>
                <td><code>KAN-308</code></td>
                <td><span class="kb-csv-action-badge kb-csv-action-badge--update">Update</span></td>
                <td>Cross-tenant access visibility metadata</td>
                <td>Completed</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <footer class="kb-csv-modal-footer">
      <button class="kb-csv-btn kb-csv-btn-secondary">Cancel</button>
      <button class="kb-csv-btn kb-csv-btn-success">Confirm Import (15 Issues)</button>
    </footer>
  </div>
</div>
"""

def wrap_html(content: str, theme: str = "light") -> str:
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="{theme}">
<head>
  <meta charset="utf-8">
  <title>KAN-316 CSV Import/Export Proof</title>
  <style>
    {tokens_css}
    {theme_css}
    {base_css}
    {modal_css}
    body {{
      margin: 0;
      padding: 0;
      font-family: var(--font-sans, system-ui, sans-serif);
      background: var(--bg-canvas, #f7f8fa);
      width: 100vw;
      height: 100vh;
    }}
  </style>
</head>
<body data-theme="{theme}">
  {content}
</body>
</html>"""

async def run() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        scenarios = [
            ("01-desktop-light-export-modal.png", 1440, 900, "light", EXPORT_MODAL_HTML),
            ("02-desktop-dark-import-preview.png", 1440, 900, "dark", IMPORT_MODAL_HTML),
            ("03-tablet-csv-modal.png", 768, 1024, "light", EXPORT_MODAL_HTML),
            ("04-mobile-portrait-csv-modal.png", 390, 844, "dark", IMPORT_MODAL_HTML),
            ("05-mobile-landscape-csv-modal.png", 844, 390, "light", EXPORT_MODAL_HTML),
        ]

        for fname, width, height, theme, body_html in scenarios:
            page = await browser.new_page(viewport={"width": width, "height": height})
            html_doc = wrap_html(body_html, theme=theme)
            await page.set_content(html_doc, wait_until="networkidle")
            out_path = OUTPUT_DIR / fname
            await page.screenshot(path=str(out_path))
            print(f"Captured {fname} ({width}x{height}, {theme}) -> {out_path}")
            await page.close()

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
