// Playwright Screenshot Capture for KAN-81, KAN-77, KAN-82 against kanban-local-import
import fs from "node:fs";
import path from "node:path";
import { chromium } from "/home/adamoutler/kanban/kanban/web/node_modules/@playwright/test/index.mjs";

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:18970";
const SESSION_COOKIE = process.env.SESSION_COOKIE || "8he88j3caSZNFWU2ktkmGF7L87BH32rHQJSvGw-_JwY.O0T3UR_uw5OgTWALPTJh88wdvuTd6GoOPE-zkrNenN8";

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
    action: async (page) => {
      await page.waitForTimeout(1500);
      await page.evaluate(() => {
        const el = document.querySelector(".kb-pdf-card") ||
                   document.querySelector('[aria-label^="PDF Attachment:"]') ||
                   document.querySelector('[data-testid="pdf-attachment-card"]') ||
                   document.querySelector('.split-section-attachments');
        if (el) {
          el.scrollIntoView({ behavior: "instant", block: "center" });
        }
      });
      await page.waitForTimeout(500);
    },
  },
  {
    ticket: "KAN-77",
    url: `${BASE_URL}/admin/imports`,
    outDir: "/home/adamoutler/kanban/docs/qa/KAN-77/screenshots",
    action: async (page) => {
      await page.waitForTimeout(1500);
      await page.evaluate(() => {
        const main = document.querySelector("main.kb-main-canvas");
        if (main) {
          main.scrollTop = 0;
        }
        window.scrollTo(0, 0);
      });
      await page.waitForTimeout(500);
    },
    extra: async (page) => {
      await page.evaluate(() => {
        const panel = document.querySelector('[data-testid="portable-export-panel"]');
        if (panel) {
          panel.scrollIntoView({ behavior: "instant", block: "center" });
        }
      });
      await page.waitForTimeout(500);
      const outPath = path.join("/home/adamoutler/kanban/docs/qa/KAN-77/screenshots", "1440x900-portable-export-card.png");
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`  -> Saved ${outPath}`);
    },
  },
  {
    ticket: "KAN-82",
    url: `${BASE_URL}/projects/KAN/issues?layout=board&peek=KANBA-1`,
    outDir: "/home/adamoutler/kanban/docs/qa/KAN-82/screenshots",
    action: async (page) => {
      await page.waitForTimeout(1500);
    },
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

      if (target.action) {
        try {
          await target.action(page);
        } catch (e) {
          console.warn(`Action failed for ${target.ticket}:`, e.message);
        }
      }

      const outPath = path.join(target.outDir, `${vp.name}.png`);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`  -> Saved ${outPath}`);

      if (target.extra && vp.name === "1440x900-desktop-light") {
        try {
          await target.extra(page);
        } catch (e) {
          console.warn(`Extra screenshot failed for ${target.ticket}:`, e.message);
        }
      }

      await context.close();
    }
  }

  await browser.close();
  console.log("\nAll screenshots successfully captured!");
}

run().catch((err) => {
  console.error("Screenshot capture failed:", err);
  process.exit(1);
});
