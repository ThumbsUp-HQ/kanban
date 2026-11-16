// Copyright 2026 👍kanban Platform Contributors
// Comprehensive Playwright Automated QA & Screenshot Capture for UT-01 through UT-16

import fs from "node:fs";
import path from "node:path";
import { chromium } from "/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs";

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:8921";
const IMAGES_DIR = "/home/adamoutler/kanban/thumbs-up-kanban.wiki/images";

fs.mkdirSync(IMAGES_DIR, { recursive: true });

async function capture() {
  console.log(`Starting QA screenshot capture against ${BASE_URL}...`);
  console.log(`Saving screenshots to ${IMAGES_DIR}...`);

  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox", "--disable-gpu"],
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  });

  const page = await context.newPage();

  page.on("pageerror", err => console.log("  [Browser PageError]:", err.message));
  page.on("console", msg => {
    if (msg.type() === "error") console.log("  [Browser Console Error]:", msg.text());
  });

  // --------------------------------------------------------------------------
  // UT-01: First-Boot Setup Claim Wizard
  // --------------------------------------------------------------------------
  console.log("\n[UT-01] First-Boot Setup Claim Wizard...");
  const setupToken = "kb_setup_" + "A".repeat(43);
  await page.goto(`${BASE_URL}/setup?token=${setupToken}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(IMAGES_DIR, "01-first-boot-setup.png") });
  console.log("  -> Captured 01-first-boot-setup.png");

  // --------------------------------------------------------------------------
  // UT-02: Multi-Card Login & Passkey/TOTP Prompt
  // --------------------------------------------------------------------------
  console.log("\n[UT-02] Multi-Card Login...");
  await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(IMAGES_DIR, "02-multi-card-login.png") });
  console.log("  -> Captured 02-multi-card-login.png");

  // --------------------------------------------------------------------------
  // UT-03: Admin Auth Studio Management
  // --------------------------------------------------------------------------
  console.log("\n[UT-03] Admin Auth Studio...");
  await page.goto(`${BASE_URL}/admin/auth`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(IMAGES_DIR, "03-admin-auth-studio.png") });
  console.log("  -> Captured 03-admin-auth-studio.png");

  // --------------------------------------------------------------------------
  // UT-04: Standalone Status Panel & Compose Export
  // --------------------------------------------------------------------------
  console.log("\n[UT-04] Standalone Status Panel...");
  await page.goto(`${BASE_URL}/admin/standalone`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(IMAGES_DIR, "04-standalone-status-panel.png") });
  console.log("  -> Captured 04-standalone-status-panel.png");

  // --------------------------------------------------------------------------
  // UT-05: Workspace Home & Project Creation Modal
  // --------------------------------------------------------------------------
  console.log("\n[UT-05] Workspace Home & Project Creation Modal...");
  await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  const createProjBtn = await page.$("button:has-text('+ Project'), button:has-text('Create Project'), button:has-text('+ Create Project')");
  if (createProjBtn) {
    await createProjBtn.click();
    await page.waitForTimeout(500);
  }
  await page.screenshot({ path: path.join(IMAGES_DIR, "05-workspace-home.png") });
  console.log("  -> Captured 05-workspace-home.png");
  // Close modal if open
  const closeBtn = await page.$("button:has-text('Cancel'), button:has-text('✕'), button:has-text('Close')");
  if (closeBtn) await closeBtn.click();
  await page.waitForTimeout(300);

  // --------------------------------------------------------------------------
  // UT-06: Kanban Board View & Optimistic Drag
  // --------------------------------------------------------------------------
  console.log("\n[UT-06] Kanban Board View...");
  await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  // Hover over an emoji or badge to show tooltip
  const emojiBadge = await page.$("[title*='Urgent'], [aria-label*='Urgent'], span:has-text('🔥')");
  if (emojiBadge) await emojiBadge.hover();
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(IMAGES_DIR, "06-board-view.png") });
  console.log("  -> Captured 06-board-view.png");

  // --------------------------------------------------------------------------
  // UT-07: Multi-Layout Switching: List, Table, Calendar, Timeline
  // --------------------------------------------------------------------------
  console.log("\n[UT-07] Multi-Layout (Table View)...");
  await page.goto(`${BASE_URL}/projects/KAN/issues?layout=table`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(IMAGES_DIR, "07-list-table-calendar-timeline.png") });
  console.log("  -> Captured 07-list-table-calendar-timeline.png");

  // --------------------------------------------------------------------------
  // UT-08: Quick-Create Work Item Modal (C)
  // --------------------------------------------------------------------------
  console.log("\n[UT-08] Quick-Create Work Item Modal...");
  await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  const newWorkItemBtn = await page.$("button:has-text('+ New work item'), button:has-text('New work item')");
  if (newWorkItemBtn) {
    await newWorkItemBtn.click();
  } else {
    await page.keyboard.press("c");
  }
  await page.waitForTimeout(600);
  // Enter title into summary/title field if present
  const titleInput = await page.$("input[placeholder*='Title'], input[placeholder*='Summary'], input[name='title'], input[name='summary']");
  if (titleInput) {
    await titleInput.fill("Enforce UTF-16 lone-surrogate rejection in media proxy");
  }
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(IMAGES_DIR, "08-quick-create-modal.png") });
  console.log("  -> Captured 08-quick-create-modal.png");
  // Close modal
  const cancelIssueBtn = await page.$("button:has-text('Cancel'), button:has-text('×'), button:has-text('✕')");
  if (cancelIssueBtn) await cancelIssueBtn.click();
  await page.waitForTimeout(300);

  // --------------------------------------------------------------------------
  // UT-09: Ticket Peek Drawer (?peek=) & 17 Features
  // --------------------------------------------------------------------------
  console.log("\n[UT-09] Ticket Peek Drawer...");
  await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board&peek=KAN-101`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(IMAGES_DIR, "09-ticket-peek-drawer.png") });
  console.log("  -> Captured 09-ticket-peek-drawer.png");

  // --------------------------------------------------------------------------
  // UT-10: Workspace & Project Stickies + Smart AI Doc Promotion
  // --------------------------------------------------------------------------
  console.log("\n[UT-10] Stickies & Doc Promotion...");
  await page.goto(`${BASE_URL}/stickies`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(IMAGES_DIR, "10-stickies-and-doc-promotion.png") });
  console.log("  -> Captured 10-stickies-and-doc-promotion.png");

  // --------------------------------------------------------------------------
  // UT-11: Hierarchical Docs (ltree), Outline & Version History
  // --------------------------------------------------------------------------
  console.log("\n[UT-11] Hierarchical Docs View...");
  await page.goto(`${BASE_URL}/projects/KAN/docs`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(IMAGES_DIR, "11-docs-hierarchy-view.png") });
  console.log("  -> Captured 11-docs-hierarchy-view.png");

  // --------------------------------------------------------------------------
  // UT-12: Canonical Markdown Editor, Mermaid Diagrams & Sparkle (✨) FIM
  // --------------------------------------------------------------------------
  console.log("\n[UT-12] Editor with Mermaid & Sparkle...");
  await page.goto(`${BASE_URL}/__dev/editor`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(IMAGES_DIR, "12-editor-mermaid-and-sparkle.png") });
  console.log("  -> Captured 12-editor-mermaid-and-sparkle.png");

  // --------------------------------------------------------------------------
  // UT-13: Scopable MCP Keys, Per-Tool Toggles & Device Activation
  // --------------------------------------------------------------------------
  console.log("\n[UT-13] MCP Access Studio...");
  await page.goto(`${BASE_URL}/settings/mcp`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(IMAGES_DIR, "13-mcp-access-studio.png") });
  console.log("  -> Captured 13-mcp-access-studio.png");

  // --------------------------------------------------------------------------
  // UT-14: Custom Scripted Fields (🧪) & Tiered Privilege Escalation
  // --------------------------------------------------------------------------
  console.log("\n[UT-14] Custom Fields Studio...");
  await page.goto(`${BASE_URL}/projects/KAN/settings/custom-fields`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(IMAGES_DIR, "14-custom-fields-studio.png") });
  console.log("  -> Captured 14-custom-fields-studio.png");

  // --------------------------------------------------------------------------
  // UT-15: Admin Workflow Transition Studio & Dry-Run Drawer
  // --------------------------------------------------------------------------
  console.log("\n[UT-15] Workflow Transition Studio & Dry-Run...");
  await page.goto(`${BASE_URL}/projects/KAN/settings/workflows`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  const dryRunBtn = await page.$("button:has-text('Dry-Run Against Sample Ticket'), button:has-text('Dry-Run')");
  if (dryRunBtn) {
    console.log("  Opening Dry-Run Drawer...");
    await dryRunBtn.click();
    await page.waitForTimeout(500);
    const runBtn = await page.$("button:has-text('Run Dry-Run')");
    if (runBtn) {
      console.log("  Executing Dry-Run...");
      await runBtn.click();
      await page.waitForTimeout(600);
    }
  }
  await page.screenshot({ path: path.join(IMAGES_DIR, "15-workflow-transition-studio.png") });
  console.log("  -> Captured 15-workflow-transition-studio.png");

  // --------------------------------------------------------------------------
  // UT-16: Async Agent Gate Lifecycle on Board
  // --------------------------------------------------------------------------
  console.log("\n[UT-16] Async Agent Gate States...");
  await page.goto(`${BASE_URL}/projects/KAN/issues?layout=board&peek=KAN-102`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  const gatesTab = await page.$("button:has-text('Gates'), button:has-text('🤖 Gates')");
  if (gatesTab) {
    await gatesTab.click();
    await page.waitForTimeout(500);
  }
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(IMAGES_DIR, "16-async-agent-gate-states.png") });
  console.log("  -> Captured 16-async-agent-gate-states.png");

  await browser.close();
  console.log("\n=== ALL 16 USER TASKS SUCCESSFULLY CAPTURED! ===");
}

capture().catch(err => {
  console.error("Execution failed:", err);
  process.exit(1);
});
