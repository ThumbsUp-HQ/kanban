// Playwright Screenshot Capture for KAN-81, KAN-77, KAN-82 against kanban-local-import
import fs from "node:fs";
import path from "node:path";
import { chromium } from "/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs";

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:18970";
const SESSION_COOKIE = process.env.SESSION_COOKIE || "mQAV_wc8buURW1I9Upkzw6FyK6SuRM-Gu5RWgmsQ7OM.7KSrDAnhxTamyUDDpVJ7fVqqWDSdUaEPnN8nAo7Z8Bc";

const VIEWPORTS = [
  { name: "1440x900-desktop-light", width: 1440, height: 900, theme: "light" },
  { name: "1440x900-desktop-dark", width: 1440, height: 900, theme: "dark" },
  { name: "768x1024-tablet", width: 768, height: 1024, theme: "light" },
  { name: "390x844-mobile-portrait", width: 390, height: 844, theme: "light" },
  { name: "844x390-mobile-landscape", width: 844, height: 390, theme: "light" },
];

const TARGETS = [
  {
    ticket: "KAN-81",
    url: `${BASE_URL}/projects/KAN/issues?layout=board&peek=KAN-81`,
    outDir: "/home/adamoutler/kanban/docs/qa/KAN-81/screenshots",
  },
  {
    ticket: "KAN-77",
    url: `${BASE_URL}/projects/KAN/issues?layout=board&peek=KANBA-1`,
    outDir: "/home/adamoutler/kanban/docs/qa/KAN-77/screenshots",
  },
  {
    ticket: "KAN-82",
    url: `${BASE_URL}/projects/KAN/issues?layout=board`,
    outDir: "/home/adamoutler/kanban/docs/qa/KAN-82/screenshots",
  },
];

async function run() {
  console.log(`Starting Playwright screenshot capture against ${BASE_URL}...`);
  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
  });

  for (const target of TARGETS) {
    fs.mkdirSync(target.outDir, { recursive: true });
    console.log(`\n=== Capturing screenshots for ${target.ticket} ===`);

    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: 1,
      });

      // Inject session cookie
      await context.addCookies([
        {
          name: "kb_session",
          value: SESSION_COOKIE,
          domain: "127.0.0.1",
          path: "/",
          httpOnly: true,
          sameSite: "Lax",
        },
      ]);

      const page = await context.newPage();

      try {
        await page.goto(target.url, { waitUntil: "networkidle", timeout: 15000 });
      } catch (err) {
        console.warn(`Warning loading ${target.url}:`, err.message);
      }

      await page.waitForTimeout(1000);

      if (vp.theme === "dark") {
        await page.evaluate(() => {
          document.documentElement.setAttribute("data-theme", "dark");
          document.documentElement.dataset.theme = "dark";
          localStorage.setItem("theme", "dark");
        });
        await page.waitForTimeout(300);
      } else {
        await page.evaluate(() => {
          document.documentElement.setAttribute("data-theme", "light");
          document.documentElement.dataset.theme = "light";
          localStorage.setItem("theme", "light");
        });
        await page.waitForTimeout(200);
      }

      const outPath = path.join(target.outDir, `${vp.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`  -> Saved ${outPath}`);

      await context.close();
    }
  }

  await browser.close();
  console.log("\nAll screenshots successfully captured!");
}

run().catch(err => {
  console.error("Screenshot capture failed:", err);
  process.exit(1);
});
